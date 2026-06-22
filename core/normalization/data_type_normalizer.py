"""Re-export shim - DataTypeNormalizer now lives in core.normalization.type_normalizer."""

from core.normalization.type_normalizer import DataTypeNormalizer  # noqa: F401

__all__ = ["DataTypeNormalizer"]
