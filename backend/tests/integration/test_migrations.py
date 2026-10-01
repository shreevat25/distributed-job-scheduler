"""Alembic migration tests: single head, clean round-trip, and no model drift.

Each test run migrates a throwaway database created next to the test
database, so the session-scoped create_all schema used by other tests is
never touched.
"""

import asyncio
import os
import subprocess
import sys
import uuid
from pathlib import Path

import asyncpg
import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _alembic(database_url: str, *args: str) -> subprocess.CompletedProcess:
    """Run the alembic CLI against database_url (env.py uses asyncio.run, so it needs its own process)."""
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_DIR,
        env={**os.environ, "DATABASE_URL": database_url},
        capture_output=True,
        text=True,
    )


def _admin_dsn(url) -> str:
    """Plain asyncpg DSN for the server's maintenance database."""
    return url.set(drivername="postgresql", database="postgres").render_as_string(hide_password=False)


async def _execute(dsn: str, sql: str) -> None:
    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute(sql)
    finally:
        await conn.close()


async def _public_tables(dsn: str) -> set[str]:
    conn = await asyncpg.connect(dsn)
    try:
        rows = await conn.fetch("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        return {r["tablename"] for r in rows}
    finally:
        await conn.close()


@pytest.fixture
def migration_db_url():
    """Create an empty database for migration tests and drop it afterwards."""
    test_url = make_url(os.environ["DATABASE_URL"])
    name = f"djs_migrations_{uuid.uuid4().hex[:12]}"
    admin_dsn = _admin_dsn(test_url)

    try:
        asyncio.run(_execute(admin_dsn, f'CREATE DATABASE "{name}"'))
    except asyncpg.InsufficientPrivilegeError:
        pytest.skip("test database role cannot CREATE DATABASE")

    try:
        yield test_url.set(database=name).render_as_string(hide_password=False)
    finally:
        asyncio.run(_execute(admin_dsn, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))


def test_single_migration_head():
    """Revisions form a single linear history."""
    script = ScriptDirectory.from_config(Config(str(BACKEND_DIR / "alembic.ini")))
    assert len(script.get_heads()) == 1


def test_upgrade_matches_models_and_downgrade_round_trips(migration_db_url):
    """upgrade head -> no drift vs models -> downgrade base -> upgrade head."""
    sync_dsn = make_url(migration_db_url).set(drivername="postgresql").render_as_string(hide_password=False)

    upgrade = _alembic(migration_db_url, "upgrade", "head")
    assert upgrade.returncode == 0, upgrade.stderr

    check = _alembic(migration_db_url, "check")
    assert check.returncode == 0, f"Models and migrations have drifted:\n{check.stdout}{check.stderr}"

    downgrade = _alembic(migration_db_url, "downgrade", "base")
    assert downgrade.returncode == 0, downgrade.stderr
    assert asyncio.run(_public_tables(sync_dsn)) <= {"alembic_version"}

    reupgrade = _alembic(migration_db_url, "upgrade", "head")
    assert reupgrade.returncode == 0, reupgrade.stderr
