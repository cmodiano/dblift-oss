"""Undo Script Generator — DDL Reverser Mixin.

Contains methods for reversing DDL statements: CREATE, ALTER, DROP, COMMENT.
"""

# mypy: disable-error-code="attr-defined"

import re
from typing import Any, Callable, Dict, Optional, Tuple

from core.migration.scripting.undo_script_generator._models import UndoStatement


class _UndoDdlReverserMixin:
    """Mixin providing methods to reverse DDL statements.

    Requires the host class to provide:
      - self._quote_identifier(identifier)
      - self._generate_drop_statement(obj_type, obj_name, schema)
      - self._extract_create_object(sql)
      - self._extract_column_name_from_add(sql)
      - self._extract_constraint_name_from_add(sql)
      - self.dialect (str)
    """

    # Must be provided by the concrete class
    dialect: str
    _quote_identifier: Callable[..., str]
    _generate_drop_statement: Callable[..., str]
    _extract_create_object: Callable[..., Optional[Tuple[str, str, Optional[str]]]]
    _extract_column_name_from_add: Callable[..., Optional[str]]
    _extract_constraint_name_from_add: Callable[..., Optional[str]]

    def _reverse_create_from_parsed(self, stmt: Any) -> Optional[UndoStatement]:
        """Reverse a CREATE statement from parsed SqlStatement.

        Args:
            stmt: SqlStatement object with CREATE statement

        Returns:
            UndoStatement with DROP statement
        """
        sql = stmt.sql_text
        # Get the object being created from affected_objects (more accurate)
        if stmt.affected_objects:
            obj = stmt.affected_objects[0]
            obj_type = obj.object_type.value
            obj_name = obj.name
            schema = obj.schema
        elif stmt.objects:
            obj = stmt.objects[0]
            obj_type = obj.object_type.value
            obj_name = obj.name
            schema = obj.schema
        else:
            # Fallback to regex extraction
            obj_info = self._extract_create_object(sql)
            if not obj_info:
                return UndoStatement(
                    sql="-- WARNING: Could not extract object from CREATE statement",
                    original_statement=sql,
                    operation_type="CREATE",
                    warning="Could not parse CREATE statement",
                    requires_manual_review=True,
                )
            obj_type, obj_name, schema = obj_info

        # Generate DROP statement based on object type
        if obj_type in ("TABLE", "INDEX", "VIEW", "SEQUENCE", "TRIGGER", "PROCEDURE", "FUNCTION"):
            drop_sql = self._generate_drop_statement(obj_type, obj_name, schema)
            return UndoStatement(
                sql=drop_sql,
                original_statement=sql,
                operation_type="CREATE",
            )
        else:
            return UndoStatement(
                sql=f"-- WARNING: Cannot reverse CREATE {obj_type}",
                original_statement=sql,
                operation_type="CREATE",
                warning=f"CREATE {obj_type} reversal not yet implemented",
                requires_manual_review=True,
            )

    def _reverse_create(self, sql: str, analysis: Dict[str, Any]) -> Optional[UndoStatement]:
        """Reverse a CREATE statement.

        Args:
            sql: CREATE statement
            analysis: Statement analysis result

        Returns:
            UndoStatement with DROP statement
        """
        # Extract object name and type
        objects = analysis.get("objects", [])
        if not objects:
            # Try regex extraction
            obj_info = self._extract_create_object(sql)
            if not obj_info:
                return UndoStatement(
                    sql="-- WARNING: Could not extract object from CREATE statement",
                    original_statement=sql,
                    operation_type="CREATE",
                    warning="Could not parse CREATE statement",
                    requires_manual_review=True,
                )
            obj_type, obj_name, schema = obj_info
        else:
            obj = objects[0]
            obj_type = obj.get("object_type", "UNKNOWN").upper()
            obj_name = obj.get("object_name", "")
            schema = obj.get("schema")

        # Generate DROP statement based on object type
        if obj_type in ("TABLE", "INDEX", "VIEW", "SEQUENCE", "TRIGGER", "PROCEDURE", "FUNCTION"):
            drop_sql = self._generate_drop_statement(obj_type, obj_name, schema)
            return UndoStatement(
                sql=drop_sql,
                original_statement=sql,
                operation_type="CREATE",
            )
        else:
            return UndoStatement(
                sql=f"-- WARNING: Cannot reverse CREATE {obj_type}",
                original_statement=sql,
                operation_type="CREATE",
                warning=f"CREATE {obj_type} reversal not yet implemented",
                requires_manual_review=True,
            )

    def _reverse_alter_from_parsed(self, stmt: Any) -> Optional[UndoStatement]:
        """Reverse an ALTER statement from parsed SqlStatement.

        Args:
            stmt: SqlStatement object with ALTER statement

        Returns:
            UndoStatement with reverse ALTER statement
        """
        sql = stmt.sql_text
        sql_upper = sql.strip().upper()

        # Get table name from affected_objects
        if stmt.affected_objects:
            table_obj = stmt.affected_objects[0]
            table_name = table_obj.name
            schema = table_obj.schema
        elif stmt.objects:
            table_obj = stmt.objects[0]
            table_name = table_obj.name
            schema = table_obj.schema
        else:
            return UndoStatement(
                sql="-- WARNING: Could not extract table from ALTER statement",
                original_statement=sql,
                operation_type="ALTER",
                warning="Could not parse ALTER statement",
                requires_manual_review=True,
            )

        # Format table name
        if schema:
            formatted_table = (
                f"{self._quote_identifier(schema)}.{self._quote_identifier(table_name)}"
            )
        else:
            formatted_table = self._quote_identifier(table_name)

        # Handle different ALTER operations
        if "ADD COLUMN" in sql_upper:
            column_name = self._extract_column_name_from_add(sql)
            if column_name:
                drop_sql = f"ALTER TABLE {formatted_table} DROP COLUMN {self._quote_identifier(column_name)};"
                return UndoStatement(
                    sql=drop_sql,
                    original_statement=sql,
                    operation_type="ALTER",
                )
            else:
                return UndoStatement(
                    sql="-- WARNING: Could not extract column name from ADD COLUMN statement",
                    original_statement=sql,
                    operation_type="ALTER",
                    warning="Could not extract column name",
                    requires_manual_review=True,
                )
        elif "DROP COLUMN" in sql_upper:
            return UndoStatement(
                sql="-- WARNING: Cannot reverse DROP COLUMN without original column definition",
                original_statement=sql,
                operation_type="ALTER",
                warning="DROP COLUMN cannot be reversed without original column definition",
                requires_manual_review=True,
            )
        elif (
            "ADD CONSTRAINT" in sql_upper
            or "ADD PRIMARY KEY" in sql_upper
            or "ADD FOREIGN KEY" in sql_upper
        ):
            constraint_name = self._extract_constraint_name_from_add(sql)
            if constraint_name:
                if "PRIMARY KEY" in sql_upper:
                    drop_sql = f"ALTER TABLE {formatted_table} DROP PRIMARY KEY;"
                elif "FOREIGN KEY" in sql_upper:
                    drop_sql = f"ALTER TABLE {formatted_table} DROP FOREIGN KEY {self._quote_identifier(constraint_name)};"
                else:
                    drop_sql = f"ALTER TABLE {formatted_table} DROP CONSTRAINT {self._quote_identifier(constraint_name)};"
                return UndoStatement(
                    sql=drop_sql,
                    original_statement=sql,
                    operation_type="ALTER",
                )
            else:
                return UndoStatement(
                    sql="-- WARNING: Could not extract constraint name from ADD CONSTRAINT statement",
                    original_statement=sql,
                    operation_type="ALTER",
                    warning="Could not extract constraint name",
                    requires_manual_review=True,
                )
        elif (
            "DROP CONSTRAINT" in sql_upper
            or "DROP PRIMARY KEY" in sql_upper
            or "DROP FOREIGN KEY" in sql_upper
        ):
            return UndoStatement(
                sql="-- WARNING: Cannot reverse DROP CONSTRAINT without original constraint definition",
                original_statement=sql,
                operation_type="ALTER",
                warning="DROP CONSTRAINT cannot be reversed without original constraint definition",
                requires_manual_review=True,
            )
        elif "MODIFY COLUMN" in sql_upper or "ALTER COLUMN" in sql_upper:
            return UndoStatement(
                sql="-- WARNING: Cannot reverse MODIFY/ALTER COLUMN without original column definition",
                original_statement=sql,
                operation_type="ALTER",
                warning="MODIFY/ALTER COLUMN cannot be reversed without original column definition",
                requires_manual_review=True,
            )
        else:
            return UndoStatement(
                sql="-- WARNING: ALTER operation type not supported for reversal",
                original_statement=sql,
                operation_type="ALTER",
                warning="This ALTER operation type cannot be automatically reversed",
                requires_manual_review=True,
            )

    def _reverse_alter(self, sql: str, analysis: Dict[str, Any]) -> Optional[UndoStatement]:
        """Reverse an ALTER statement.

        Args:
            sql: ALTER statement
            analysis: Statement analysis result

        Returns:
            UndoStatement with reverse ALTER statement
        """
        sql_upper = sql.strip().upper()

        # Extract table name
        objects = analysis.get("objects", [])
        if not objects:
            return UndoStatement(
                sql="-- WARNING: Could not extract table from ALTER statement",
                original_statement=sql,
                operation_type="ALTER",
                warning="Could not parse ALTER statement",
                requires_manual_review=True,
            )

        table_obj = objects[0]
        table_name = table_obj.get("object_name", "")
        schema = table_obj.get("schema")

        # Format table name
        if schema:
            formatted_table = (
                f"{self._quote_identifier(schema)}.{self._quote_identifier(table_name)}"
            )
        else:
            formatted_table = self._quote_identifier(table_name)

        # Handle different ALTER operations
        if "ADD COLUMN" in sql_upper:
            # ALTER TABLE ... ADD COLUMN col -> ALTER TABLE ... DROP COLUMN col
            column_name = self._extract_column_name_from_add(sql)
            if column_name:
                drop_sql = f"ALTER TABLE {formatted_table} DROP COLUMN {self._quote_identifier(column_name)};"
                return UndoStatement(
                    sql=drop_sql,
                    original_statement=sql,
                    operation_type="ALTER",
                )
            else:
                return UndoStatement(
                    sql="-- WARNING: Could not extract column name from ADD COLUMN statement",
                    original_statement=sql,
                    operation_type="ALTER",
                    warning="Could not extract column name",
                    requires_manual_review=True,
                )
        elif "DROP COLUMN" in sql_upper:
            # ALTER TABLE ... DROP COLUMN col -> Cannot reverse without original definition
            return UndoStatement(
                sql="-- WARNING: Cannot reverse DROP COLUMN without original column definition",
                original_statement=sql,
                operation_type="ALTER",
                warning="DROP COLUMN cannot be reversed without original column definition",
                requires_manual_review=True,
            )
        elif (
            "ADD CONSTRAINT" in sql_upper
            or "ADD PRIMARY KEY" in sql_upper
            or "ADD FOREIGN KEY" in sql_upper
        ):
            # ALTER TABLE ... ADD CONSTRAINT -> ALTER TABLE ... DROP CONSTRAINT
            constraint_name = self._extract_constraint_name_from_add(sql)
            if constraint_name:
                if "PRIMARY KEY" in sql_upper:
                    drop_sql = f"ALTER TABLE {formatted_table} DROP PRIMARY KEY;"
                elif "FOREIGN KEY" in sql_upper:
                    drop_sql = f"ALTER TABLE {formatted_table} DROP FOREIGN KEY {self._quote_identifier(constraint_name)};"
                else:
                    drop_sql = f"ALTER TABLE {formatted_table} DROP CONSTRAINT {self._quote_identifier(constraint_name)};"
                return UndoStatement(
                    sql=drop_sql,
                    original_statement=sql,
                    operation_type="ALTER",
                )
            else:
                return UndoStatement(
                    sql="-- WARNING: Could not extract constraint name from ADD CONSTRAINT statement",
                    original_statement=sql,
                    operation_type="ALTER",
                    warning="Could not extract constraint name",
                    requires_manual_review=True,
                )
        elif (
            "DROP CONSTRAINT" in sql_upper
            or "DROP PRIMARY KEY" in sql_upper
            or "DROP FOREIGN KEY" in sql_upper
        ):
            return UndoStatement(
                sql="-- WARNING: Cannot reverse DROP CONSTRAINT without original constraint definition",
                original_statement=sql,
                operation_type="ALTER",
                warning="DROP CONSTRAINT cannot be reversed without original constraint definition",
                requires_manual_review=True,
            )
        elif "MODIFY COLUMN" in sql_upper or "ALTER COLUMN" in sql_upper:
            return UndoStatement(
                sql="-- WARNING: Cannot reverse MODIFY/ALTER COLUMN without original column definition",
                original_statement=sql,
                operation_type="ALTER",
                warning="MODIFY/ALTER COLUMN cannot be reversed without original column definition",
                requires_manual_review=True,
            )
        else:
            return UndoStatement(
                sql="-- WARNING: ALTER operation type not supported for reversal",
                original_statement=sql,
                operation_type="ALTER",
                warning="This ALTER operation type cannot be automatically reversed",
                requires_manual_review=True,
            )

    def _reverse_drop_from_parsed(self, stmt: Any) -> Optional[UndoStatement]:
        """Reverse a DROP statement from parsed SqlStatement.

        Args:
            stmt: SqlStatement object with DROP statement

        Returns:
            UndoStatement with warning (DROP cannot be reversed)
        """
        return UndoStatement(
            sql="-- WARNING: Cannot reverse DROP statement without original object definition",
            original_statement=stmt.sql_text,
            operation_type="DROP",
            warning="DROP statements cannot be reversed without original object definition",
            requires_manual_review=True,
        )

    def _reverse_drop(self, sql: str, analysis: Dict[str, Any]) -> Optional[UndoStatement]:
        """Reverse a DROP statement.

        Args:
            sql: DROP statement
            analysis: Statement analysis result

        Returns:
            UndoStatement with warning (DROP cannot be reversed)
        """
        return UndoStatement(
            sql="-- WARNING: Cannot reverse DROP statement without original object definition",
            original_statement=sql,
            operation_type="DROP",
            warning="DROP statements cannot be reversed without original object definition",
            requires_manual_review=True,
        )

    def _reverse_comment_from_parsed(self, stmt: Any) -> Optional[UndoStatement]:
        """Reverse a COMMENT statement from parsed SqlStatement.

        Args:
            stmt: SqlStatement object with COMMENT statement

        Returns:
            UndoStatement with COMMENT ... IS NULL to remove comment
        """
        sql = stmt.sql_text

        # Get object from affected_objects or objects
        if stmt.affected_objects:
            obj = stmt.affected_objects[0]
        elif stmt.objects:
            obj = stmt.objects[0]
        else:
            return self._reverse_comment(sql)  # Fallback to regex parsing

        obj_type = obj.object_type.value.upper()
        obj_name = obj.name
        schema = obj.schema

        # Format object name
        if schema:
            formatted_name = f"{self._quote_identifier(schema)}.{self._quote_identifier(obj_name)}"
        else:
            formatted_name = self._quote_identifier(obj_name)

        # Remove comment by setting to NULL
        reverse_sql = f"COMMENT ON {obj_type} {formatted_name} IS NULL;"
        return UndoStatement(
            sql=reverse_sql,
            original_statement=sql,
            operation_type="COMMENT",
        )

    def _reverse_comment(self, sql: str) -> Optional[UndoStatement]:
        """Reverse a COMMENT statement.

        Args:
            sql: COMMENT statement

        Returns:
            UndoStatement with COMMENT ... IS NULL to remove comment
        """
        # Extract object type and name from COMMENT ON
        # Pattern: COMMENT ON TABLE/COLUMN schema.object IS 'text'
        match = re.search(
            r"COMMENT\s+ON\s+(\w+)\s+(?:(\w+)\.)?(\w+)(?:\s+IS\s+.*)?",
            sql,
            re.IGNORECASE,
        )
        if match:
            obj_type = match.group(1).upper()
            schema = match.group(2)
            obj_name = match.group(3)

            # Format object name
            if schema:
                formatted_name = (
                    f"{self._quote_identifier(schema)}.{self._quote_identifier(obj_name)}"
                )
            else:
                formatted_name = self._quote_identifier(obj_name)

            # Remove comment by setting to NULL
            reverse_sql = f"COMMENT ON {obj_type} {formatted_name} IS NULL;"
            return UndoStatement(
                sql=reverse_sql,
                original_statement=sql,
                operation_type="COMMENT",
            )
        else:
            return UndoStatement(
                sql="-- WARNING: Could not parse COMMENT statement",
                original_statement=sql,
                operation_type="COMMENT",
                warning="Could not parse COMMENT statement",
                requires_manual_review=True,
            )
