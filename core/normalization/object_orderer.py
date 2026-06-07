"""
Canonical ordering of SQL objects.

Provides deterministic ordering of objects for consistent output
across different databases and introspection runs.
"""

from typing import Dict, List, Optional

from core.sql_model.base import SqlObject, SqlObjectType


class ObjectOrderer:
    """
    Orders SQL objects in a canonical, deterministic way.

    Ordering rules:
    1. By object type (tables, views, indexes, sequences, procedures, triggers)
    2. By schema (alphabetically)
    3. By name (alphabetically, case-insensitive)
    4. By dependency order (if dependencies are known)
    """

    # Type priority order (lower number = earlier)
    # Default priority for unknown types
    DEFAULT_PRIORITY = 99

    @classmethod
    def _get_type_priority_map(cls) -> Dict[SqlObjectType, int]:
        """Get type priority mapping, handling missing enum values gracefully."""
        priority_map = {
            SqlObjectType.TABLE: 1,
            SqlObjectType.VIRTUAL_TABLE: 1,
            SqlObjectType.VIEW: 2,
            SqlObjectType.INDEX: 3,
            SqlObjectType.SEQUENCE: 4,
            SqlObjectType.PROCEDURE: 5,
            SqlObjectType.FUNCTION: 5,
            SqlObjectType.TRIGGER: 6,
        }

        # Add optional types if they exist
        if hasattr(SqlObjectType, "MATERIALIZED_VIEW"):
            priority_map[SqlObjectType.MATERIALIZED_VIEW] = 2
        if hasattr(SqlObjectType, "SYNONYM"):
            priority_map[SqlObjectType.SYNONYM] = 7
        if hasattr(SqlObjectType, "USER_DEFINED_TYPE"):
            priority_map[SqlObjectType.USER_DEFINED_TYPE] = 8

        return priority_map

    @classmethod
    def get_type_priority(cls, obj: SqlObject) -> int:
        """Get priority for object type.

        Args:
            obj: SQL object

        Returns:
            Priority number (lower = earlier)
        """
        priority_map = cls._get_type_priority_map()
        priority: int = priority_map.get(obj.object_type, cls.DEFAULT_PRIORITY)
        return priority

    @classmethod
    def normalize_name(cls, name: Optional[str]) -> str:
        """Normalize name for comparison (case-insensitive).

        Args:
            name: Object name

        Returns:
            Normalized name (lowercase, stripped)
        """
        if name is None:
            return ""
        return str(name).lower().strip()

    @classmethod
    def normalize_schema(cls, schema: Optional[str]) -> str:
        """Normalize schema for comparison.

        Args:
            schema: Schema name

        Returns:
            Normalized schema (lowercase, or 'public' if None)
        """
        if schema is None:
            return "public"
        return str(schema).lower().strip()

    @classmethod
    def sort_objects(cls, objects: List[SqlObject]) -> List[SqlObject]:
        """Sort objects in canonical order.

        Args:
            objects: List of SQL objects to sort

        Returns:
            Sorted list of objects
        """

        def sort_key(obj: SqlObject) -> tuple:
            """Generate sort key for object."""
            type_priority = cls.get_type_priority(obj)
            schema = cls.normalize_schema(getattr(obj, "schema", None))
            name = cls.normalize_name(obj.name)
            return (type_priority, schema, name)

        return sorted(objects, key=sort_key)

    @classmethod
    def sort_by_dependencies(
        cls,
        objects: List[SqlObject],
        dependency_map: Optional[dict] = None,
    ) -> List[SqlObject]:
        """Sort objects considering dependencies.

        Args:
            objects: List of SQL objects to sort
            dependency_map: Optional dictionary mapping object names to dependencies

        Returns:
            Sorted list of objects (dependencies first)

        Note:
            This is a simplified implementation. A full topological sort
            would be needed for complex dependency graphs.
        """
        if not dependency_map:
            # Fall back to canonical ordering if no dependencies
            return cls.sort_objects(objects)

        # Simple approach: sort by type first, then by dependency depth
        # Objects with no dependencies come first
        # Memoization cache to avoid recalculating depths
        depth_cache: Dict[str, int] = {}

        def get_dependency_depth(obj: SqlObject, visited: Optional[set] = None) -> int:
            """Get dependency depth (0 = no dependencies).

            Args:
                obj: SQL object to get depth for
                visited: Set of object keys in current path (for cycle detection)

            Returns:
                Dependency depth (0 = no dependencies)

            Raises:
                ValueError: If circular dependency is detected
            """
            if visited is None:
                visited = set()

            obj_key = f"{getattr(obj, 'schema', '')}.{obj.name}"

            # Check for circular dependency
            if obj_key in visited:
                cycle_path = list(visited) + [obj_key]
                raise ValueError(f"Circular dependency detected: {' -> '.join(cycle_path)}")

            # Check cache first
            if obj_key in depth_cache:
                return depth_cache[obj_key]

            deps = dependency_map.get(obj_key, [])
            if not deps:
                depth_cache[obj_key] = 0
                return 0

            # Add current object to visited set for cycle detection
            visited.add(obj_key)

            # Return max depth of dependencies + 1
            max_depth = 0
            for dep in deps:
                dep_key = (
                    dep if isinstance(dep, str) else f"{getattr(dep, 'schema', '')}.{dep.name}"
                )
                dep_obj = next(
                    (o for o in objects if f"{getattr(o, 'schema', '')}.{o.name}" == dep_key), None
                )
                if dep_obj:
                    max_depth = max(max_depth, get_dependency_depth(dep_obj, visited))

            # Remove from visited set before returning (backtracking)
            visited.remove(obj_key)

            depth = max_depth + 1
            depth_cache[obj_key] = depth
            return depth

        def sort_key(obj: SqlObject) -> tuple:
            """Generate sort key with dependency depth."""
            type_priority = cls.get_type_priority(obj)
            dependency_depth = get_dependency_depth(obj)
            schema = cls.normalize_schema(getattr(obj, "schema", None))
            name = cls.normalize_name(obj.name)
            return (type_priority, dependency_depth, schema, name)

        return sorted(objects, key=sort_key)

    @classmethod
    def group_by_type(cls, objects: List[SqlObject]) -> Dict[SqlObjectType, List[SqlObject]]:
        """Group objects by type.

        Args:
            objects: List of SQL objects

        Returns:
            Dictionary mapping object types to lists of objects
        """
        from core.sql_model.base import SqlObject

        grouped: Dict[SqlObjectType, List[SqlObject]] = {}
        for obj in objects:
            obj_type = obj.object_type
            if obj_type not in grouped:
                grouped[obj_type] = []
            grouped[obj_type].append(obj)

        # Sort each group
        for obj_type in grouped:
            sorted_objs = cls.sort_objects(grouped[obj_type])
            grouped[obj_type] = sorted_objs  # type: ignore[assignment]

        return grouped  # type: ignore[return-value]
