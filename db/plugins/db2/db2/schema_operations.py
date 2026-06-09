"""
DB2 schema operations and metadata queries.

This module handles DB2-specific schema operations including schema creation,
cleaning, and metadata queries for tables, columns, and other database objects.
"""

from typing import Any, List, Optional

from core.logger import Log, NullLog
from core.migration.clean_summary import CleanExecutionSummary
from db.exceptions import DB_OPERATION_EXCEPTIONS
from db.plugins.base_schema_operations import BaseSchemaOperations


class Db2SchemaOperations(BaseSchemaOperations):
    """Handles DB2 schema operations and metadata queries."""

    def __init__(self, query_executor: Any, log: Optional[Log] = None) -> None:
        """Initialize the schema operations manager.

        Args:
            query_executor: Query executor instance
            log: Optional logger
        """
        self.query_executor = query_executor
        self.log = log if log is not None else NullLog()

    def create_schema_if_not_exists(self, connection: Any, schema: str) -> None:
        """Create a schema if it doesn't exist in DB2.

        Args:
            schema: Schema name to create
        """
        self.log.info(f"Creating schema if not exists: {schema}")

        # Check if schema exists using DB2 system catalogs.
        # Use case-sensitive matching: dblift always creates the schema via a
        # double-quoted identifier (see get_quoted_schema_name below), which
        # preserves the exact case the caller supplied. DB2's SYSCAT.SCHEMATA
        # stores SCHEMANAME with the case the CREATE SCHEMA DDL recorded, so
        # we must match that case exactly — otherwise a case-insensitive hit
        # on e.g. ``DB2INST1`` when the caller asked for ``db2inst1`` would
        # report "already exists" and the quoted DDL that follows would then
        # target a non-existent lowercase schema.
        clean_schema = schema.replace('"', "").strip()
        check_sql = "SELECT SCHEMANAME FROM SYSCAT.SCHEMATA WHERE SCHEMANAME = ?"
        schema_exists = (
            len(self.query_executor.execute_query(connection, check_sql, [clean_schema])) > 0
        )

        if not schema_exists:
            # Use the centralized quoted-schema helper so every dblift SQL
            # construction site references schemas identically (double-quoted,
            # case-preserving via the base query executor).
            quoted_schema = self.query_executor.get_quoted_schema_name(clean_schema)
            create_sql = f"CREATE SCHEMA {quoted_schema}"
            try:
                self.query_executor.execute_statement(connection, create_sql)

                # CRITICAL: Commit schema creation immediately (DB2 uses autoCommit=False)
                if connection:
                    try:
                        connection.commit()
                        self.log.debug("Committed schema creation")
                    except DB_OPERATION_EXCEPTIONS as commit_e:
                        self.log.warning(f"Could not commit schema creation: {commit_e}")

                self.log.info(f"Schema created: {schema}")
            except DB_OPERATION_EXCEPTIONS:
                # Rollback on error
                if connection:
                    try:
                        connection.rollback()
                    except DB_OPERATION_EXCEPTIONS as rb_e:
                        self.log.debug(
                            f"Could not rollback DB2 schema creation transaction: {rb_e}"
                        )
                raise
        else:
            self.log.info(f"Schema already exists: {schema}")

    def set_current_schema(self, connection: Any, schema: str) -> None:
        """Set the default schema for the connection.

        Args:
            schema: Schema name
        """
        self.log.debug(f"Setting current schema to: {schema}")

        # Clean schema name then route through the centralized quoted-schema
        # helper so every dblift SQL construction site references schemas
        # identically (double-quoted, case-preserving).
        clean_schema = schema.replace('"', "").strip()
        quoted_schema = self.query_executor.get_quoted_schema_name(clean_schema)
        set_schema_sql = f"SET SCHEMA {quoted_schema}"
        try:
            self.query_executor.execute_statement(connection, set_schema_sql)
            self.log.debug(f"Current schema set to: {schema}")
        except DB_OPERATION_EXCEPTIONS as e:
            error_msg = f"Failed to set current schema: {str(e)}"
            self.log.warning(error_msg)
            raise

    def get_database_version(self, connection: Any) -> str:
        """Get the DB2 version information.

        Returns:
            Database version string
        """
        version_sql = "SELECT SERVICE_LEVEL, FIXPACK_NUM FROM SYSIBMADM.ENV_INST_INFO"
        try:
            results = self.query_executor.execute_query(connection, version_sql)

            if results and len(results) > 0:
                service_level = results[0].get("SERVICE_LEVEL", "")
                fixpack_num = results[0].get("FIXPACK_NUM", "")
                return f"DB2 {service_level} FixPack {fixpack_num}"

            # Alternative query if the above doesn't work
            fallback_sql = "SELECT CURRENT SERVER AS DB_NAME FROM SYSIBM.SYSDUMMY1"
            results = self.query_executor.execute_query(connection, fallback_sql)
            if results and len(results) > 0:
                return f"DB2 {results[0].get('DB_NAME', 'Unknown')}"

            return "DB2 Unknown Version"
        except DB_OPERATION_EXCEPTIONS as e:
            self.log.warning(f"Error getting DB2 version: {str(e)}")
            return "DB2 Unknown Version"

    def clean_schema(self, connection: Any, schema: str) -> CleanExecutionSummary:
        """Clean a DB2 schema by dropping all objects in the correct order.

        Args:
            schema: Schema name

        Returns:
            CleanExecutionSummary describing executed statements and dropped objects.
        """
        self.log.info(f"Cleaning DB2 schema: {schema}")

        summary = CleanExecutionSummary()

        # Ensure clean transaction state before clean operations
        try:
            if not connection.getAutoCommit():
                # Rollback any existing uncommitted transaction
                connection.rollback()
                self.log.debug("Rolled back existing transaction before clean")
        except DB_OPERATION_EXCEPTIONS as e:
            self.log.debug(f"Error checking/rolling back transaction: {e}")

        # Set current schema to the schema being cleaned
        self.set_current_schema(connection, schema)

        # Clean schema name for queries (remove quotes)
        clean_schema = schema.replace('"', "").strip()

        try:
            # DB2: skip schema-wide SET INTEGRITY as it's not valid; we drop in dependency order instead
            self.log.debug("Skipping schema-wide SET INTEGRITY; will drop objects directly")

            # 1. Drop triggers first
            self._drop_triggers(connection, clean_schema, summary)
            self._commit_if_needed(connection, "triggers")

            # 2. Drop foreign keys to avoid circular dependencies
            self._drop_foreign_keys(connection, clean_schema, summary)
            self._commit_if_needed(connection, "foreign keys")

            # 3. Drop views
            self._drop_views(connection, clean_schema, summary)
            self._commit_if_needed(connection, "views")

            # 4. Drop materialized query tables (MQTs) - DB2-specific
            self._drop_materialized_query_tables(connection, clean_schema, summary)
            self._commit_if_needed(connection, "materialized query tables")

            # 5. Drop tables (drop everything, including internal tables; lock table will be recreated)
            self._drop_tables(connection, clean_schema, summary)
            self._commit_if_needed(connection, "tables")

            # 5a. Explicitly drop migration lock table if it exists (ensure it's cleaned up)
            self._drop_migration_lock_table(connection, clean_schema, summary)
            self._commit_if_needed(connection, "migration lock table")

            # 6. Drop aliases - DB2-specific object type
            self._drop_aliases(connection, clean_schema, summary)
            self._commit_if_needed(connection, "aliases")

            # 7. Drop sequences
            self._drop_sequences(connection, clean_schema, summary)
            self._commit_if_needed(connection, "sequences")

            # 8. Drop user-defined functions
            self._drop_functions(connection, clean_schema, summary)
            self._commit_if_needed(connection, "functions")

            # 9. Drop procedures
            self._drop_procedures(connection, clean_schema, summary)
            self._commit_if_needed(connection, "procedures")

            # 10. Drop user-defined types (UDTs)
            self._drop_types(connection, clean_schema, summary)
            self._commit_if_needed(connection, "types")

            # 11. Drop global temporary tables - DB2-specific objects
            self._drop_global_temporary_tables(connection, clean_schema, summary)
            self._commit_if_needed(connection, "global temporary tables")

            # 12. Drop modules (packages) - DB2-specific objects
            self._drop_modules(connection, clean_schema, summary)
            self._commit_if_needed(connection, "modules")

            # 13. Drop indexes (drop these last to avoid auto-recreation)
            self._drop_indexes(connection, clean_schema, summary)
            self._commit_if_needed(connection, "indexes")

            # Final commit to ensure all operations are persisted
            self._commit_if_needed(connection, "final clean")

            # CRITICAL: Commit cleanup operations for DB2 to prevent hanging
            # DB2 DDL operations need explicit commit when autoCommit=False
            try:
                if hasattr(connection, "commit"):
                    if hasattr(connection, "getAutoCommit"):
                        if not connection.getAutoCommit():
                            connection.commit()
                            self.log.debug("Committed DB2 cleanup transaction")
                    else:
                        # If we can't check autoCommit, commit anyway for safety
                        connection.commit()
                        self.log.debug("Committed DB2 cleanup transaction (autoCommit unknown)")
            except DB_OPERATION_EXCEPTIONS as commit_err:
                self.log.warning(f"Failed to commit cleanup transaction: {commit_err}")
                # Try rollback if commit fails
                try:
                    if hasattr(connection, "rollback"):
                        connection.rollback()
                        self.log.debug("Rolled back DB2 cleanup transaction after commit failure")
                except DB_OPERATION_EXCEPTIONS as rb_e:
                    self.log.debug(f"Could not rollback DB2 cleanup transaction: {rb_e}")

            self.log.info(
                f"Schema cleanup completed. Executed {len(summary.statements)} statements."
            )

            return summary

        except DB_OPERATION_EXCEPTIONS as e:
            # CRITICAL: Always rollback on error to prevent hanging transactions
            try:
                connection.rollback()
                self.log.debug("Rolled back transaction after clean error")
            except DB_OPERATION_EXCEPTIONS as rb_e:
                self.log.debug(f"Could not rollback DB2 transaction after clean error: {rb_e}")

            error_msg = f"Error cleaning schema {schema}: {str(e)}"
            self.log.error(error_msg)
            raise

    def _commit_if_needed(self, connection: Any, operation: str) -> None:
        """Commit transaction if autoCommit is False (for DB2).

        Args:
            connection: Active database connection (provided by Provider)
            operation: Description of the operation for logging
        """
        try:
            if not connection.getAutoCommit():
                connection.commit()
                self.log.debug(f"Committed transaction after {operation}")
        except DB_OPERATION_EXCEPTIONS as e:
            self.log.debug(f"Could not commit after {operation}: {e}")

    def _drop_triggers(self, connection: Any, schema: str, summary: CleanExecutionSummary) -> None:
        """Drop all triggers in the schema."""

        # Use case-insensitive matching in WHERE clause (UPPER() in SQL)
        # But preserve original case in results
        triggers_query = """
        SELECT TRIGNAME, TRIGSCHEMA
        FROM SYSCAT.TRIGGERS
        WHERE UPPER(TRIGSCHEMA) = UPPER(?)
        """
        triggers = self.query_executor.execute_query(connection, triggers_query, params=[schema])

        for trigger in triggers:
            trigger_name = trigger.get("TRIGNAME")
            if trigger_name:
                try:
                    # Use get_schema_qualified_name to ensure proper quoting
                    qualified_trigger = self.query_executor.get_schema_qualified_name(
                        schema, trigger_name
                    )
                    drop_sql = f"DROP TRIGGER {qualified_trigger}"
                    self.query_executor.execute_statement(connection, drop_sql)
                    summary.record_drop(
                        drop_sql,
                        object_type="trigger",
                        name=trigger_name,
                        schema=schema,
                    )
                    self.log.debug(f"Dropped trigger {schema}.{trigger_name}")
                except DB_OPERATION_EXCEPTIONS as e:
                    self.log.warning(f"Failed to drop trigger {schema}.{trigger_name}: {str(e)}")

    def _drop_foreign_keys(
        self, connection: Any, schema: str, summary: CleanExecutionSummary
    ) -> None:
        """Drop all foreign key constraints in the schema."""

        # Use case-insensitive matching in WHERE clause (UPPER() in SQL)
        # But preserve original case in results
        fk_query = """
        SELECT CONSTNAME, TABNAME
        FROM SYSCAT.TABCONST
        WHERE UPPER(TABSCHEMA) = UPPER(?)
        AND TYPE = 'F'
        """
        foreign_keys = self.query_executor.execute_query(connection, fk_query, params=[schema])

        for fk in foreign_keys:
            fk_name = fk.get("CONSTNAME")
            table_name = fk.get("TABNAME")
            if fk_name and table_name:
                try:
                    # Use get_schema_qualified_name to ensure proper quoting
                    qualified_table = self.query_executor.get_schema_qualified_name(
                        schema, table_name
                    )
                    # Constraint names don't need quoting if they're system-generated, but quote for safety
                    clean_fk_name = fk_name.replace('"', "").strip()
                    drop_sql = f'ALTER TABLE {qualified_table} DROP CONSTRAINT "{clean_fk_name}"'
                    self.query_executor.execute_statement(connection, drop_sql)
                    summary.record_drop(
                        drop_sql,
                        object_type="foreign_key",
                        name=fk_name,
                        schema=schema,
                        details={"table": table_name},
                    )
                    self.log.debug(f"Dropped foreign key {schema}.{table_name}.{fk_name}")
                except DB_OPERATION_EXCEPTIONS as e:
                    self.log.warning(
                        f"Failed to drop foreign key {schema}.{table_name}.{fk_name}: {str(e)}"
                    )

    def _drop_views(self, connection: Any, schema: str, summary: CleanExecutionSummary) -> None:
        """Drop all views in the schema."""

        # Use case-insensitive matching in WHERE clause (UPPER() in SQL)
        # But preserve original case in results
        views_query = """
        SELECT TABNAME
        FROM SYSCAT.TABLES
        WHERE UPPER(TABSCHEMA) = UPPER(?)
        AND TYPE = 'V'
        """
        views = self.query_executor.execute_query(connection, views_query, params=[schema])

        for view in views:
            view_name = view.get("TABNAME")
            if view_name:
                try:
                    # Use get_schema_qualified_name to ensure proper quoting
                    qualified_view = self.query_executor.get_schema_qualified_name(
                        schema, view_name
                    )
                    drop_sql = f"DROP VIEW {qualified_view}"
                    self.query_executor.execute_statement(connection, drop_sql)
                    summary.record_drop(drop_sql, object_type="view", name=view_name, schema=schema)
                    self.log.debug(f"Dropped view {schema}.{view_name}")
                except DB_OPERATION_EXCEPTIONS as e:
                    self.log.warning(f"Failed to drop view {schema}.{view_name}: {str(e)}")

    def _drop_materialized_query_tables(
        self, connection: Any, schema: str, summary: CleanExecutionSummary
    ) -> None:
        """Drop all materialized query tables (MQTs) - DB2-specific."""

        # Use case-insensitive matching in WHERE clause (UPPER() in SQL)
        # But preserve original case in results
        mqt_query = """
        SELECT TABNAME
        FROM SYSCAT.TABLES
        WHERE UPPER(TABSCHEMA) = UPPER(?)
        AND TYPE = 'S'
        """
        mqts = self.query_executor.execute_query(connection, mqt_query, params=[schema])

        for mqt in mqts:
            mqt_name = mqt.get("TABNAME")
            if mqt_name:
                try:
                    # Use get_schema_qualified_name to ensure proper quoting
                    qualified_mqt = self.query_executor.get_schema_qualified_name(schema, mqt_name)
                    drop_sql = f"DROP TABLE {qualified_mqt}"
                    self.query_executor.execute_statement(connection, drop_sql)
                    summary.record_drop(
                        drop_sql,
                        object_type="materialized_query_table",
                        name=mqt_name,
                        schema=schema,
                    )
                    self.log.debug(f"Dropped materialized query table {schema}.{mqt_name}")
                except DB_OPERATION_EXCEPTIONS as e:
                    self.log.warning(
                        f"Failed to drop materialized query table {schema}.{mqt_name}: {str(e)}"
                    )

    def _drop_tables(self, connection: Any, schema: str, summary: CleanExecutionSummary) -> None:
        """Drop all regular tables in the schema (excluding history table)."""

        # Use case-insensitive matching in WHERE clause (UPPER() in SQL)
        # But preserve original case in results
        tables_query = """
        SELECT TABNAME
        FROM SYSCAT.TABLES
        WHERE UPPER(TABSCHEMA) = UPPER(?)
        AND TYPE = 'T'
        """
        tables = self.query_executor.execute_query(connection, tables_query, params=[schema])

        for table in tables:
            table_name = table.get("TABNAME")
            # Drop everything including internal tables; lock table will be recreated as needed
            if table_name:
                try:
                    # Use get_schema_qualified_name to ensure proper quoting
                    qualified_table = self.query_executor.get_schema_qualified_name(
                        schema, table_name
                    )
                    drop_sql = f"DROP TABLE {qualified_table}"
                    self.query_executor.execute_statement(connection, drop_sql)
                    summary.record_drop(
                        drop_sql, object_type="table", name=table_name, schema=schema
                    )
                    self.log.debug(f"Dropped table {schema}.{table_name}")
                except DB_OPERATION_EXCEPTIONS as e:
                    self.log.warning(f"Failed to drop table {schema}.{table_name}: {str(e)}")

    def _drop_migration_lock_table(
        self, connection: Any, schema: str, summary: CleanExecutionSummary
    ) -> None:
        """Explicitly drop the migration lock table if it exists.

        This ensures the lock table is properly cleaned up and recorded in the summary.

        Args:
            schema: Schema name
            summary: Clean execution summary to record drops
        """
        from db.object_naming import get_normalized_object_name
        from db.plugins.db2.db2.locking_manager import Db2LockingManager

        # Use database-specific default case for dblift objects
        lock_table_name = Db2LockingManager.MIGRATION_LOCK_TABLE
        dblift_lock_table = get_normalized_object_name(lock_table_name, "db2")

        # Check if lock table exists
        if not self.query_executor.table_exists(connection, schema, dblift_lock_table):
            self.log.debug(f"Migration lock table does not exist in schema {schema}")
            return

        try:
            # Use get_schema_qualified_name to ensure proper quoting
            qualified_table = self.query_executor.get_schema_qualified_name(
                schema, dblift_lock_table
            )
            drop_sql = f"DROP TABLE {qualified_table}"
            self.query_executor.execute_statement(connection, drop_sql)
            summary.record_drop(
                drop_sql, object_type="table", name=dblift_lock_table, schema=schema
            )
            self.log.debug(f"Dropped migration lock table {schema}.{dblift_lock_table}")
        except DB_OPERATION_EXCEPTIONS as e:
            self.log.warning(
                f"Failed to drop migration lock table {schema}.{dblift_lock_table}: {str(e)}"
            )

    def _drop_aliases(self, connection: Any, schema: str, summary: CleanExecutionSummary) -> None:
        """Drop all aliases - DB2-specific object type."""

        # Use case-insensitive matching in WHERE clause (UPPER() in SQL)
        # But preserve original case in results
        aliases_query = """
        SELECT TABNAME
        FROM SYSCAT.TABLES
        WHERE UPPER(TABSCHEMA) = UPPER(?)
        AND TYPE = 'A'
        """
        aliases = self.query_executor.execute_query(connection, aliases_query, params=[schema])

        for alias in aliases:
            alias_name = alias.get("TABNAME")
            if alias_name:
                try:
                    # Use get_schema_qualified_name to ensure proper quoting
                    qualified_alias = self.query_executor.get_schema_qualified_name(
                        schema, alias_name
                    )
                    drop_sql = f"DROP ALIAS {qualified_alias}"
                    self.query_executor.execute_statement(connection, drop_sql)
                    summary.record_drop(
                        drop_sql, object_type="alias", name=alias_name, schema=schema
                    )
                    self.log.debug(f"Dropped alias {schema}.{alias_name}")
                except DB_OPERATION_EXCEPTIONS as e:
                    self.log.warning(f"Failed to drop alias {schema}.{alias_name}: {str(e)}")

    def _drop_sequences(self, connection: Any, schema: str, summary: CleanExecutionSummary) -> None:
        """Drop all sequences in the schema."""

        # Use case-insensitive matching in WHERE clause (UPPER() in SQL)
        # But preserve original case in results
        sequences_query = """
        SELECT SEQNAME
        FROM SYSCAT.SEQUENCES
        WHERE UPPER(SEQSCHEMA) = UPPER(?)
        """
        sequences = self.query_executor.execute_query(connection, sequences_query, params=[schema])

        for sequence in sequences:
            sequence_name = sequence.get("SEQNAME")
            if sequence_name:
                try:
                    # Use get_schema_qualified_name to ensure proper quoting
                    qualified_sequence = self.query_executor.get_schema_qualified_name(
                        schema, sequence_name
                    )
                    drop_sql = f"DROP SEQUENCE {qualified_sequence}"
                    self.query_executor.execute_statement(connection, drop_sql)
                    summary.record_drop(
                        drop_sql,
                        object_type="sequence",
                        name=sequence_name,
                        schema=schema,
                    )
                    self.log.debug(f"Dropped sequence {schema}.{sequence_name}")
                except DB_OPERATION_EXCEPTIONS as e:
                    self.log.warning(f"Failed to drop sequence {schema}.{sequence_name}: {str(e)}")

    def _drop_functions(self, connection: Any, schema: str, summary: CleanExecutionSummary) -> None:
        """Drop all user-defined functions in the schema."""

        # Use case-insensitive matching in WHERE clause (UPPER() in SQL)
        # But preserve original case in results
        functions_query = """
        SELECT FUNCNAME, FUNCSCHEMA, SPECIFICNAME
        FROM SYSCAT.FUNCTIONS
        WHERE UPPER(FUNCSCHEMA) = UPPER(?)
        AND ORIGIN = 'U'
        """
        functions = self.query_executor.execute_query(connection, functions_query, params=[schema])

        for function in functions:
            function_name = function.get("FUNCNAME")
            specific_name = function.get("SPECIFICNAME")
            if function_name and specific_name:
                try:
                    # Use get_schema_qualified_name to ensure proper quoting
                    qualified_function = self.query_executor.get_schema_qualified_name(
                        schema, specific_name
                    )
                    drop_sql = f"DROP SPECIFIC FUNCTION {qualified_function}"
                    self.query_executor.execute_statement(connection, drop_sql)
                    summary.record_drop(
                        drop_sql,
                        object_type="function",
                        name=function_name,
                        schema=schema,
                        details={"specific_name": specific_name},
                    )
                    self.log.debug(f"Dropped function {schema}.{function_name}")
                except DB_OPERATION_EXCEPTIONS as e:
                    self.log.warning(f"Failed to drop function {schema}.{function_name}: {str(e)}")

    def _drop_procedures(
        self, connection: Any, schema: str, summary: CleanExecutionSummary
    ) -> None:
        """Drop all procedures in the schema."""

        # Use case-insensitive matching in WHERE clause (UPPER() in SQL)
        # But preserve original case in results
        procedures_query = """
        SELECT PROCNAME, PROCSCHEMA, SPECIFICNAME
        FROM SYSCAT.PROCEDURES
        WHERE UPPER(PROCSCHEMA) = UPPER(?)
        """
        procedures = self.query_executor.execute_query(
            connection, procedures_query, params=[schema]
        )

        for procedure in procedures:
            procedure_name = procedure.get("PROCNAME")
            specific_name = procedure.get("SPECIFICNAME")
            if procedure_name and specific_name:
                try:
                    # Use get_schema_qualified_name to ensure proper quoting
                    qualified_procedure = self.query_executor.get_schema_qualified_name(
                        schema, specific_name
                    )
                    drop_sql = f"DROP SPECIFIC PROCEDURE {qualified_procedure}"
                    self.query_executor.execute_statement(connection, drop_sql)
                    summary.record_drop(
                        drop_sql,
                        object_type="procedure",
                        name=procedure_name,
                        schema=schema,
                        details={"specific_name": specific_name},
                    )
                    self.log.debug(f"Dropped procedure {schema}.{procedure_name}")
                except DB_OPERATION_EXCEPTIONS as e:
                    self.log.warning(
                        f"Failed to drop procedure {schema}.{procedure_name}: {str(e)}"
                    )

    def _drop_types(self, connection: Any, schema: str, summary: CleanExecutionSummary) -> None:
        """Drop all user-defined types (UDTs) in the schema."""

        # Use case-insensitive matching in WHERE clause (UPPER() in SQL)
        # But preserve original case in results
        types_query = """
        SELECT TYPENAME
        FROM SYSCAT.DATATYPES
        WHERE UPPER(TYPESCHEMA) = UPPER(?)
        """
        types = self.query_executor.execute_query(connection, types_query, params=[schema])

        for udt in types:
            type_name = udt.get("TYPENAME")
            if type_name:
                try:
                    # Use get_schema_qualified_name to ensure proper quoting
                    qualified_type = self.query_executor.get_schema_qualified_name(
                        schema, type_name
                    )
                    drop_sql = f"DROP TYPE {qualified_type}"
                    self.query_executor.execute_statement(connection, drop_sql)
                    summary.record_drop(drop_sql, object_type="type", name=type_name, schema=schema)
                    self.log.debug(f"Dropped type {schema}.{type_name}")
                except DB_OPERATION_EXCEPTIONS as e:
                    self.log.warning(f"Failed to drop type {schema}.{type_name}: {str(e)}")

    def _drop_global_temporary_tables(
        self, connection: Any, schema: str, summary: CleanExecutionSummary
    ) -> None:
        """Drop all global temporary tables - DB2-specific objects."""

        # Use case-insensitive matching in WHERE clause (UPPER() in SQL)
        # But preserve original case in results
        gtt_query = """
        SELECT TABNAME
        FROM SYSCAT.TABLES
        WHERE UPPER(TABSCHEMA) = UPPER(?)
          AND TYPE = 'G'
        """

        try:
            gtt_tables = self.query_executor.execute_query(connection, gtt_query, params=[schema])

            for gtt in gtt_tables:
                gtt_name = gtt.get("TABNAME")
                if gtt_name:
                    try:
                        # Use get_schema_qualified_name to ensure proper quoting
                        qualified_gtt = self.query_executor.get_schema_qualified_name(
                            schema, gtt_name
                        )
                        drop_sql = f"DROP TABLE {qualified_gtt}"
                        self.query_executor.execute_statement(connection, drop_sql)
                        summary.record_drop(
                            drop_sql,
                            object_type="global_temporary_table",
                            name=gtt_name,
                            schema=schema,
                        )
                        self.log.debug(f"Dropped global temporary table {schema}.{gtt_name}")
                    except DB_OPERATION_EXCEPTIONS as e:
                        self.log.warning(
                            f"Failed to drop global temporary table {schema}.{gtt_name}: {str(e)}"
                        )
        except DB_OPERATION_EXCEPTIONS as e:
            self.log.warning(f"Error checking for global temporary tables: {str(e)}")

    def _drop_modules(self, connection: Any, schema: str, summary: CleanExecutionSummary) -> None:
        """Drop all modules (packages) - DB2-specific objects."""

        # Use case-insensitive matching in WHERE clause (UPPER() in SQL)
        # But preserve original case in results
        modules_query = """
        SELECT MODULENAME
        FROM SYSCAT.MODULES
        WHERE UPPER(MODULESCHEMA) = UPPER(?)
        """

        try:
            modules = self.query_executor.execute_query(connection, modules_query, params=[schema])

            for module in modules:
                module_name = module.get("MODULENAME")
                if module_name:
                    try:
                        # Use get_schema_qualified_name to ensure proper quoting
                        qualified_module = self.query_executor.get_schema_qualified_name(
                            schema, module_name
                        )
                        drop_sql = f"DROP MODULE {qualified_module}"
                        self.query_executor.execute_statement(connection, drop_sql)
                        summary.record_drop(
                            drop_sql, object_type="module", name=module_name, schema=schema
                        )
                        self.log.debug(f"Dropped module {schema}.{module_name}")
                    except DB_OPERATION_EXCEPTIONS as e:
                        self.log.warning(f"Failed to drop module {schema}.{module_name}: {str(e)}")
        except DB_OPERATION_EXCEPTIONS as e:
            self.log.warning(f"Error checking for modules: {str(e)}")

    def _drop_indexes(self, connection: Any, schema: str, summary: CleanExecutionSummary) -> None:
        """Drop all indexes in the schema."""

        # Use case-insensitive matching in WHERE clause (UPPER() in SQL)
        # But preserve original case in results
        indexes_query = """
        SELECT INDNAME, TABNAME
        FROM SYSCAT.INDEXES
        WHERE UPPER(INDSCHEMA) = UPPER(?)
        """
        indexes = self.query_executor.execute_query(connection, indexes_query, params=[schema])

        for index in indexes:
            index_name = index.get("INDNAME")
            table_name = index.get("TABNAME")
            if index_name:
                try:
                    # Use get_schema_qualified_name to ensure proper quoting
                    qualified_index = self.query_executor.get_schema_qualified_name(
                        schema, index_name
                    )
                    drop_sql = f"DROP INDEX {qualified_index}"
                    self.query_executor.execute_statement(connection, drop_sql)
                    details = {"table": table_name} if table_name else None
                    summary.record_drop(
                        drop_sql,
                        object_type="index",
                        name=index_name,
                        schema=schema,
                        details=details,
                    )
                    self.log.debug(f"Dropped index {schema}.{index_name}")
                except DB_OPERATION_EXCEPTIONS as e:
                    self.log.warning(f"Failed to drop index {schema}.{index_name}: {str(e)}")
                    # This is often expected since tables were dropped earlier

    def get_columns_query(self, schema: str, table: str) -> tuple[str, List[str]]:
        """Get a DB2-specific query to retrieve column information from a table.

        Args:
            schema: Schema name
            table: Table name

        Returns:
            tuple[str, List[str]]: SQL query and parameters [schema, table]
        """
        # Use case-insensitive matching in WHERE clause (UPPER() in SQL)
        # But preserve original case in results
        # Clean schema and table of quotes for parameter passing
        clean_schema = schema.replace('"', "").strip()
        clean_table = table.replace('"', "").strip()
        query = """
        SELECT colname as column_name, typename as data_type
        FROM syscat.columns
        WHERE UPPER(tabschema) = UPPER(?) AND UPPER(tabname) = UPPER(?)
        ORDER BY colno
        """
        return (query, [clean_schema, clean_table])

    def get_add_column_sql(self, schema: str, table: str, column: str, type_def: str) -> str:
        """Generate DB2-specific SQL to add a column to a table.

        Args:
            schema: Schema name
            table: Table name
            column: Column name to add
            type_def: Column data type definition

        Returns:
            str: SQL for adding the column
        """
        qualified_table = self.query_executor.get_schema_qualified_name(schema, table)
        return f'ALTER TABLE {qualified_table} ADD COLUMN "{column}" {type_def}'

    def get_parameter_placeholders(self, count: int) -> str:
        """Get DB2-specific parameter placeholders for prepared statements.

        Args:
            count: Number of parameters

        Returns:
            str: Parameter placeholders string
        """
        # DB2 uses ? placeholders
        return ", ".join(["?" for _ in range(count)])

    def get_tables(self, connection: Any, schema: str) -> List[str]:
        """Get list of table names in the specified schema.

        Args:
            schema: Schema name

        Returns:
            List of table names in the schema
        """
        self.log.debug(f"Getting tables in schema: {schema}")

        try:
            # Use DB2 system catalogs to get table names
            # Use case-insensitive matching in WHERE clause (UPPER() in SQL)
            # But preserve original case in results
            clean_schema = schema.replace('"', "").strip()
            query = """
            SELECT TABNAME as table_name
            FROM SYSCAT.TABLES
            WHERE UPPER(TABSCHEMA) = UPPER(?) AND TYPE = 'T'
            ORDER BY TABNAME
            """

            result = self.query_executor.execute_query(connection, query, params=[clean_schema])
            tables = [
                str(row["table_name"] if "table_name" in row else row["TABLE_NAME"])
                for row in result
            ]

            self.log.debug(f"Found {len(tables)} tables in schema {schema}: {tables}")

            return tables
        except DB_OPERATION_EXCEPTIONS as e:
            error_msg = f"Error getting tables in schema {schema}: {str(e)}"
            self.log.error(error_msg)
            return []

    def get_schemas(self, connection: Any) -> List[str]:
        """Get list of schema names available in the DB2 database.

        Returns:
            List of schema names that the current user can access
        """
        self.log.debug("Getting available schemas from DB2")

        try:
            # Query to get schemas that the current user can access
            # Exclude system schemas
            query = """
            SELECT SCHEMANAME as schema_name
            FROM SYSCAT.SCHEMATA
            WHERE SCHEMANAME NOT IN (
                'SYSIBM', 'SYSCAT', 'SYSSTAT', 'SYSFUN', 'SYSPROC',
                'SYSPUBLIC', 'SYSTOOLS', 'SYSIBMADM'
            )
            ORDER BY SCHEMANAME
            """

            result = self.query_executor.execute_query(connection, query)
            schemas = [
                str(row["schema_name"] if "schema_name" in row else row["SCHEMA_NAME"])
                for row in result
            ]

            self.log.debug(f"Found {len(schemas)} accessible schemas")

            return schemas
        except DB_OPERATION_EXCEPTIONS as e:
            error_msg = f"Error getting schemas: {str(e)}"
            self.log.error(error_msg)
            return []
