from sqlalchemy import text

from db.native_connection_manager import NativeConnectionManager


class _DB:
    type = "sqlite"
    path = ":memory:"


class _Cfg:
    database = _DB()


def test_creates_usable_connection():
    mgr = NativeConnectionManager(_Cfg())
    conn = mgr.create_connection()
    assert conn.execute(text("SELECT 1")).scalar() == 1
    mgr.close()


def test_engine_is_reused_across_connections():
    mgr = NativeConnectionManager(_Cfg())
    mgr.create_connection()
    e1 = mgr.engine
    mgr.create_connection()
    assert mgr.engine is e1
    mgr.close()


def test_close_disposes_engine():
    mgr = NativeConnectionManager(_Cfg())
    mgr.create_connection()
    mgr.close()
    assert mgr._engine is None


def test_create_connection_closes_previous():
    mgr = NativeConnectionManager(_Cfg())
    c1 = mgr.create_connection()
    c2 = mgr.create_connection()
    assert c1.closed is True  # previous connection must not leak
    assert c2.closed is False
    mgr.close()
