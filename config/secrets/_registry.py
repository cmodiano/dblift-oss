"""Secrets registry stub for OSS edition."""


def is_secret_uri(value: object) -> bool:
    """In OSS, no secret URI schemes are supported — always returns False."""
    return False
