"""Database URL resolution.

Config reads the environment in its class body, so each case reloads the module
with a different environment. This matters because the deploy now ships its own
Postgres and `DATABASE_URL` is authoritative — a stale `SUPABASE_URL` left in
backend/.env must not quietly pull the app back to a managed database.
"""
import importlib

import pytest


def _db_uri(monkeypatch, **env):
    """Reload config with exactly the given DB vars set, and return the URI.

    config calls load_dotenv() on import, which would re-seed the vars we just
    cleared from whatever backend/.env holds on this machine. Stub it out so the
    test measures the precedence rule and nothing else. It has to be patched on
    the dotenv module, not on config: reloading config re-runs its
    `from dotenv import load_dotenv` and would pick the real one back up.
    """
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: False)
    for key in ("DATABASE_URL", "SUPABASE_URL"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    import config
    importlib.reload(config)
    return config.Config.SQLALCHEMY_DATABASE_URI


@pytest.fixture(autouse=True)
def _restore_config():
    """Whatever a case does, put the real module back afterwards."""
    yield
    import config
    importlib.reload(config)


def test_database_url_is_used(monkeypatch):
    uri = _db_uri(monkeypatch, DATABASE_URL="postgresql://u:p@db:5432/invoiceparsed")
    assert uri == "postgresql+psycopg2://u:p@db:5432/invoiceparsed"


def test_database_url_wins_over_supabase(monkeypatch):
    """The bundled Postgres is the default; an old SUPABASE_URL must not win."""
    uri = _db_uri(
        monkeypatch,
        DATABASE_URL="postgresql://u:p@db:5432/invoiceparsed",
        SUPABASE_URL="postgresql://old:old@pooler.supabase.com:6543/postgres",
    )
    assert uri == "postgresql+psycopg2://u:p@db:5432/invoiceparsed"


def test_supabase_url_still_works_alone(monkeypatch):
    """Kept as a fallback so an existing managed install runs until migrated."""
    uri = _db_uri(monkeypatch, SUPABASE_URL="postgresql://old:old@pooler:6543/postgres")
    assert uri == "postgresql+psycopg2://old:old@pooler:6543/postgres"


def test_falls_back_to_sqlite(monkeypatch):
    """Host-local dev with neither set."""
    assert _db_uri(monkeypatch) == "sqlite:///invoiceparsed.db"


def test_postgres_scheme_is_normalised(monkeypatch):
    """SQLAlchemy rejects the bare "postgres://" some providers hand out."""
    uri = _db_uri(monkeypatch, DATABASE_URL="postgres://u:p@db:5432/invoiceparsed")
    assert uri == "postgresql+psycopg2://u:p@db:5432/invoiceparsed"


def test_scheme_normalisation_applies_to_supabase_too(monkeypatch):
    uri = _db_uri(monkeypatch, SUPABASE_URL="postgres://u:p@pooler:6543/postgres")
    assert uri.startswith("postgresql+psycopg2://")


# ─── Driver pinning ──────────────────────────────────────────────────────────
# SQLAlchemy 2.1 changed the default DBAPI for a driver-less "postgresql://"
# from psycopg2 to psycopg (v3). requirements.txt installs psycopg2-binary, so
# an unpinned URL makes the app die on "No module named 'psycopg'" at startup.

def test_driverless_postgres_url_is_pinned_to_psycopg2(monkeypatch):
    uri = _db_uri(monkeypatch, DATABASE_URL="postgresql://u:p@db:5432/d")
    assert uri.startswith("postgresql+psycopg2://")


def test_an_explicit_driver_is_left_alone(monkeypatch):
    """Someone who installs psycopg v3 and asks for it by name gets it."""
    uri = _db_uri(monkeypatch, DATABASE_URL="postgresql+psycopg://u:p@db:5432/d")
    assert uri == "postgresql+psycopg://u:p@db:5432/d"


def test_the_pinned_url_actually_builds_an_engine(monkeypatch):
    """The whole point: creating the engine must not raise ModuleNotFoundError.
    Nothing connects here — create_engine only resolves and imports the DBAPI."""
    from sqlalchemy import create_engine

    uri = _db_uri(monkeypatch, DATABASE_URL="postgresql://u:p@db:5432/invoiceparsed")
    assert create_engine(uri).dialect.driver == "psycopg2"


def test_sqlite_is_untouched(monkeypatch):
    uri = _db_uri(monkeypatch, DATABASE_URL="sqlite:///somewhere.db")
    assert uri == "sqlite:///somewhere.db"
