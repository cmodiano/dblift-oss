"""
Normalization utilities for schema objects.

This module provides utilities for:
- Canonical ordering of objects
- Type normalization
- Identifier normalization
- Dependency resolution
"""

from typing import TYPE_CHECKING, Any

from core.normalization.dependency_resolver import DependencyResolver
from core.normalization.object_orderer import ObjectOrderer

if TYPE_CHECKING:
    from core.normalization.type_mapper import CanonicalTypeMapper

__all__ = [
    "CanonicalTypeMapper",
    "DependencyResolver",
    "ObjectOrderer",
]


def __getattr__(name: str) -> Any:
    if name == "CanonicalTypeMapper":
        from core.normalization.type_mapper import CanonicalTypeMapper

        return CanonicalTypeMapper
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return list(__all__)
