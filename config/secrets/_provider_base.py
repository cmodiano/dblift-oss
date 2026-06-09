"""Secrets provider base stub for OSS edition.

Enterprise provider base classes (vault, AWS, Azure, GCP) are not available
in the OSS edition. This stub provides the minimum interface to keep the
config layer importable.
"""

from __future__ import annotations


class SecretsResolutionError(Exception):
    """Raised when a secret URI cannot be resolved.

    In OSS, secret URIs are unsupported — this error is never raised in
    practice, but the class must exist for code that catches it.
    """
