"""Per-dialect ``BaseDatabaseConfig`` subclass modules.

This package holds the dialect-specific configuration classes that used to
live in ``config/database_config.py``. Each module imports
:class:`config.database_config.BaseDatabaseConfig` and uses
``@register_database_type`` so its class is wired into the
``BaseDatabaseConfig._registry`` at import time.

The :mod:`config.database_config` facade imports every submodule here to
keep the legacy ``from config.database_config import XxxConfig`` import
sites working unchanged.
"""
