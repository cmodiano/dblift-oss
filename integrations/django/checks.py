"""System check that warns when dblift migrations are pending."""

from __future__ import annotations

from typing import Any

from django.core.checks import Warning as DjangoWarning
from django.core.checks import register


@register()
def pending_migrations_check(app_configs: Any, **kwargs: Any) -> list[Any]:
    """Return a warning for pending dblift migrations, or [] on no pending work."""
    try:
        from integrations.django._client import get_client
        from integrations.fastapi import _pending_ids_from_info

        client = get_client()
        try:
            info = client.info()
        finally:
            client.close()
        pending = _pending_ids_from_info(info)
    except Exception:
        return []

    if not pending:
        return []
    return [
        DjangoWarning(
            f"dblift: {len(pending)} pending migration(s): {pending}",
            hint="Apply with `python manage.py dblift_migrate`.",
            id="dblift.W001",
        )
    ]
