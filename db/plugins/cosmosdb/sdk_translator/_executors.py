"""CosmosDB SDK Executor Mixin — execute_sdk_operation and _execute_* methods.

This module contains the _CosmosDbExecutorMixin class which implements
all SDK operation execution methods for CosmosDB.
"""

from typing import Any, Dict, Optional, Tuple


class _CosmosDbExecutorMixin:
    """Mixin providing execute_sdk_operation and all _execute_* methods."""

    # Must be provided by the concrete class
    connection_manager: Any
    log: Any

    # OCP-02: data-driven dispatch for execute_sdk_operation.
    # Value is (method_name, needs_operation) — add new op_types here without
    # touching execute_sdk_operation.
    _OP_EXECUTOR_MAP: Dict[str, Tuple[str, bool]] = {
        "delete_container": ("_execute_delete_container", False),
        "replace_container": ("_execute_replace_container", True),
        "set_throughput": ("_execute_set_throughput", True),
        "set_autoscale": ("_execute_set_autoscale", True),
        "show_throughput": ("_execute_show_throughput", False),
        "create_composite_index": ("_execute_create_composite_index", True),
        "drop_composite_index": ("_execute_drop_composite_index", True),
        "exclude_index_path": ("_execute_exclude_index_path", True),
        "include_index_path": ("_execute_include_index_path", True),
        "set_ttl": ("_execute_set_ttl", True),
    }

    def execute_sdk_operation(self, operation: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Execute an SDK operation.

        Args:
            operation: Operation dictionary from translate_to_sdk_operation()

        Returns:
            Tuple of (success: bool, error_message: Optional[str])
        """
        try:
            if self.connection_manager is None:
                return False, "Connection manager not initialized"

            database = self.connection_manager.database
            if not database:
                self.connection_manager.create_connection()
                database = self.connection_manager.database

            if database is None:
                return False, "Database not initialized"

            container_name = operation["container_name"]
            op_type = operation["operation"]

            # Handle error operations
            if op_type == "error":
                return False, operation.get("warning", "Unknown error in operation")

            # Data-driven dispatch via _OP_EXECUTOR_MAP (OCP-02)
            entry = self._OP_EXECUTOR_MAP.get(op_type)
            if entry is None:
                return False, f"Unknown operation type: {op_type}"
            method_name, needs_operation = entry
            method = getattr(self, method_name)
            if needs_operation:
                return method(database, container_name, operation)  # type: ignore[no-any-return]
            return method(database, container_name)  # type: ignore[no-any-return]

        except Exception as e:
            error_msg = f"Error executing SDK operation: {str(e)}"
            self.log.error(error_msg)
            return False, error_msg

    # =========================================================================
    # SDK Operation Executors
    # =========================================================================

    def _execute_delete_container(
        self, database: Any, container_name: str
    ) -> Tuple[bool, Optional[str]]:
        """Execute delete container operation."""
        database.delete_container(container=container_name)
        self.log.info(f"Deleted container: {container_name}")
        return True, None

    def _execute_replace_container(
        self, database: Any, container_name: str, operation: Dict[str, Any]
    ) -> Tuple[bool, Optional[str]]:
        """Execute replace container operation."""
        container_client = database.get_container_client(container_name)
        container_properties = container_client.read()

        throughput_value = None
        other_properties = {}

        for key, value in operation["parameters"].items():
            if key == "offer_throughput":
                throughput_value = value
            else:
                if key == "indexingPolicy":
                    other_properties["indexing_policy"] = value
                elif key == "defaultTtl":
                    other_properties["default_ttl"] = value
                elif key == "uniqueKeyPolicy":
                    other_properties["unique_key_policy"] = value
                else:
                    other_properties[key] = value

        if throughput_value is not None:
            try:
                container_client.replace_throughput(throughput_value)
                self.log.info(
                    f"Updated container '{container_name}' throughput to {throughput_value}"
                )
            except Exception as e:
                self.log.warning(f"Could not update throughput: {e}")

        if other_properties:
            for key, value in other_properties.items():
                container_properties[key] = value
            # replace_container lives on DatabaseProxy, not ContainerProxy
            database.replace_container(
                container_client,
                partition_key=container_properties.get("partitionKey"),
                indexing_policy=container_properties.get("indexingPolicy"),
                default_ttl=container_properties.get("defaultTtl"),
            )
            self.log.info(
                f"Updated container '{container_name}' properties: {list(other_properties.keys())}"
            )

        return True, None

    def _execute_set_throughput(
        self, database: Any, container_name: str, operation: Dict[str, Any]
    ) -> Tuple[bool, Optional[str]]:
        """Execute set throughput operation."""
        container_client = database.get_container_client(container_name)
        throughput = operation["parameters"]["throughput"]

        try:
            container_client.replace_throughput(throughput)
            self.log.info(f"Set throughput on container '{container_name}' to {throughput} RU/s")
            return True, None
        except Exception as e:
            error_msg = f"Failed to set throughput: {str(e)}"
            self.log.error(error_msg)
            return False, error_msg

    def _execute_set_autoscale(
        self, database: Any, container_name: str, operation: Dict[str, Any]
    ) -> Tuple[bool, Optional[str]]:
        """Execute set autoscale operation."""
        try:
            from azure.cosmos import ThroughputProperties
        except ImportError:
            return False, "Azure Cosmos SDK not installed"

        container_client = database.get_container_client(container_name)
        max_throughput = operation["parameters"]["max_throughput"]

        try:
            throughput_properties = ThroughputProperties(auto_scale_max_throughput=max_throughput)
            container_client.replace_throughput(throughput_properties)
            self.log.info(
                f"Set autoscale on container '{container_name}' to max {max_throughput} RU/s"
            )
            return True, None
        except Exception as e:
            error_msg = f"Failed to set autoscale: {str(e)}"
            self.log.error(error_msg)
            return False, error_msg

    def _execute_show_throughput(
        self, database: Any, container_name: str
    ) -> Tuple[bool, Optional[str]]:
        """Execute show throughput operation (returns info in error message slot)."""
        container_client = database.get_container_client(container_name)

        try:
            offer = container_client.read_offer()
            throughput = offer.offer_throughput
            # Check if autoscale
            content = offer.properties.get("content", {})
            autopilot = content.get("offerAutopilotSettings")
            if autopilot:
                max_throughput = autopilot.get("maxThroughput", throughput)
                info = f"Autoscale: max {max_throughput} RU/s (current: {throughput} RU/s)"
            else:
                info = f"Fixed: {throughput} RU/s"

            self.log.info(f"Throughput for container '{container_name}': {info}")
            # Return info in a special way (success=True, info in message)
            return True, info
        except Exception as e:
            error_msg = f"Failed to get throughput: {str(e)}"
            self.log.error(error_msg)
            return False, error_msg

    def _execute_create_composite_index(
        self, database: Any, container_name: str, operation: Dict[str, Any]
    ) -> Tuple[bool, Optional[str]]:
        """Execute create composite index operation."""
        container_client = database.get_container_client(container_name)
        columns = operation["parameters"]["columns"]

        try:
            container_props = container_client.read()
            indexing_policy = container_props.get("indexingPolicy", {})
            composite_indexes = indexing_policy.get("compositeIndexes", [])

            # Add the new composite index
            composite_indexes.append(columns)
            indexing_policy["compositeIndexes"] = composite_indexes

            # replace_container lives on DatabaseProxy, not ContainerProxy
            database.replace_container(
                container_client,
                partition_key=container_props["partitionKey"],
                indexing_policy=indexing_policy,
            )

            self.log.info(f"Created composite index on container '{container_name}'")
            return True, None
        except Exception as e:
            error_msg = f"Failed to create composite index: {str(e)}"
            self.log.error(error_msg)
            return False, error_msg

    def _execute_drop_composite_index(
        self, database: Any, container_name: str, operation: Dict[str, Any]
    ) -> Tuple[bool, Optional[str]]:
        """Execute drop composite index operation."""
        container_client = database.get_container_client(container_name)
        index_name = operation["parameters"]["index_name"]

        try:
            container_props = container_client.read()
            indexing_policy = container_props.get("indexingPolicy", {})
            # Access composite_indexes for reference (even if not used directly)
            _ = indexing_policy.get("compositeIndexes", [])

            # Note: Cosmos DB doesn't name composite indexes, so we can't identify by name
            # This is a limitation - user needs to identify index by structure
            self.log.warning(
                f"DROP INDEX '{index_name}' - Cosmos DB indexes don't have names. "
                "You may need to manually identify and remove the index by its structure."
            )

            # For now, we just log the operation
            return True, "Composite index removal requires manual identification"
        except Exception as e:
            error_msg = f"Failed to drop composite index: {str(e)}"
            self.log.error(error_msg)
            return False, error_msg

    def _execute_exclude_index_path(
        self, database: Any, container_name: str, operation: Dict[str, Any]
    ) -> Tuple[bool, Optional[str]]:
        """Execute exclude index path operation."""
        container_client = database.get_container_client(container_name)
        path = operation["parameters"]["path"]

        try:
            container_props = container_client.read()
            indexing_policy = container_props.get("indexingPolicy", {})
            excluded_paths = indexing_policy.get("excludedPaths", [])

            # Add path to excluded paths
            excluded_paths.append({"path": path})
            indexing_policy["excludedPaths"] = excluded_paths

            # replace_container lives on DatabaseProxy, not ContainerProxy
            database.replace_container(
                container_client,
                partition_key=container_props["partitionKey"],
                indexing_policy=indexing_policy,
            )

            self.log.info(f"Excluded path '{path}' from indexing on container '{container_name}'")
            return True, None
        except Exception as e:
            error_msg = f"Failed to exclude index path: {str(e)}"
            self.log.error(error_msg)
            return False, error_msg

    def _execute_include_index_path(
        self, database: Any, container_name: str, operation: Dict[str, Any]
    ) -> Tuple[bool, Optional[str]]:
        """Execute include index path operation."""
        container_client = database.get_container_client(container_name)
        path = operation["parameters"]["path"]

        try:
            container_props = container_client.read()
            indexing_policy = container_props.get("indexingPolicy", {})
            included_paths = indexing_policy.get("includedPaths", [])
            excluded_paths = indexing_policy.get("excludedPaths", [])

            # Add path to included paths
            included_paths.append({"path": path})
            indexing_policy["includedPaths"] = included_paths

            # Remove from excluded paths if present
            excluded_paths = [p for p in excluded_paths if p.get("path") != path]
            indexing_policy["excludedPaths"] = excluded_paths

            # replace_container lives on DatabaseProxy, not ContainerProxy
            database.replace_container(
                container_client,
                partition_key=container_props["partitionKey"],
                indexing_policy=indexing_policy,
            )

            self.log.info(f"Included path '{path}' in indexing on container '{container_name}'")
            return True, None
        except Exception as e:
            error_msg = f"Failed to include index path: {str(e)}"
            self.log.error(error_msg)
            return False, error_msg

    def _execute_set_ttl(
        self, database: Any, container_name: str, operation: Dict[str, Any]
    ) -> Tuple[bool, Optional[str]]:
        """Execute set TTL operation."""
        container_client = database.get_container_client(container_name)
        ttl_seconds = operation["parameters"]["ttl_seconds"]

        try:
            container_props = container_client.read()

            if ttl_seconds is None:
                # Disable TTL
                if "defaultTtl" in container_props:
                    del container_props["defaultTtl"]
                action = "disabled"
            else:
                container_props["defaultTtl"] = ttl_seconds
                action = f"set to {ttl_seconds} seconds"

            # replace_container lives on DatabaseProxy, not ContainerProxy
            database.replace_container(
                container_client,
                partition_key=container_props.get("partitionKey"),
                indexing_policy=container_props.get("indexingPolicy"),
                default_ttl=container_props.get("defaultTtl"),
            )

            self.log.info(f"TTL {action} on container '{container_name}'")
            return True, None
        except Exception as e:
            error_msg = f"Failed to set TTL: {str(e)}"
            self.log.error(error_msg)
            return False, error_msg
