"""OSS license manager stub — no key required."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


@dataclass
class License:
    """License metadata returned by OSS stubs."""

    customer_name: str = "Open Source"
    customer_email: str = "oss@dblift.local"
    issued_at: datetime = datetime.now(timezone.utc)
    expires_at: Optional[datetime] = None
    license_id: str = "oss"


class LicenseManager:
    """OSS installs run without license validation."""

    def __init__(
        self, license_path: str = "~/.dblift/license.key", public_key: Optional[str] = None
    ) -> None:
        """Record the configured license path without validating a key."""
        self._license_path = Path(license_path)

    @property
    def license_path(self) -> Path:
        """Return the configured no-op license path."""
        return self._license_path

    def resolve(self, cli_token: Optional[str] = None) -> License:
        """Resolve to the built-in OSS license metadata."""
        return License()

    def get_info(self, cli_token: Optional[str] = None) -> Dict[str, Any]:
        """Return public OSS license status information."""
        return {
            "valid": True,
            "tier": "oss",
            "customer_name": "Open Source",
            "customer_email": "oss@dblift.local",
            "license_id": "oss",
            "expires_at": None,
            "days_remaining": None,
        }

    def validate(self, token: str) -> License:
        """Accept any token and return OSS metadata."""
        return License()
