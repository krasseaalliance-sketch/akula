import os
import runpy
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect


def _run_alembic(root: Path, backend: Path, database_url: str, *arguments: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment.update({"DATABASE_URL": database_url, "PYTHONPATH": str(backend)})
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(root / "alembic.ini"), *arguments],
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def test_fresh_sqlite_database_upgrades_to_alembic_head(tmp_path: Path):
    root = Path(__file__).resolve().parents[2]
    backend = root / "backend"
    database = tmp_path / "fresh.sqlite3"
    database_url = f"sqlite:///{database.as_posix()}"

    result = _run_alembic(root, backend, database_url, "upgrade", "head")

    assert result.returncode == 0, result.stdout + result.stderr
    current = _run_alembic(root, backend, database_url, "current")
    assert current.returncode == 0, current.stdout + current.stderr
    assert "0025_core_day4_production_evidence" in current.stdout

    engine = create_engine(database_url)
    try:
        columns = {column["name"] for column in inspect(engine).get_columns("leads")}
        assert "source_message_id" in columns
    finally:
        engine.dispose()


def test_initial_migration_orders_all_foreign_key_dependencies_before_message_drafts():
    root = Path(__file__).resolve().parents[2]
    migration = runpy.run_path(str(root / "backend/migrations/versions/0001_initial.py"))
    tables = migration["INITIAL_TABLES"]

    assert tables.index("community_style_profiles") < tables.index("human_writing_runs")
    assert tables.index("human_writing_runs") < tables.index("human_writing_variants")
    assert tables.index("human_writing_variants") < tables.index("message_drafts")
