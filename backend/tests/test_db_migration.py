"""
_add_missing_columns() is the stopgap that lets an EXISTING database (e.g.
Render's persistent Postgres, already holding companies from before Phase 1
shipped) pick up Evidence.claim_id without Alembic and without a destructive
reset. These tests simulate that exact scenario: a database created BEFORE
the column existed, then upgraded.
"""
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from app.db import Base, _add_missing_columns
import app.db as db_module


def test_add_missing_columns_adds_claim_id_to_a_pre_existing_evidence_table(monkeypatch):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})

    # Simulate the pre-Phase-1 schema: create every table via metadata, then drop
    # and recreate `evidence` WITHOUT claim_id, mirroring a database that existed
    # before this column was introduced.
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE evidence"))
        conn.execute(text(
            "CREATE TABLE evidence (id VARCHAR PRIMARY KEY, company_id VARCHAR NOT NULL, module VARCHAR)"
        ))

    inspector = inspect(engine)
    columns_before = {c["name"] for c in inspector.get_columns("evidence")}
    assert "claim_id" not in columns_before

    monkeypatch.setattr(db_module, "engine", engine)
    _add_missing_columns()

    inspector = inspect(engine)
    columns_after = {c["name"] for c in inspector.get_columns("evidence")}
    assert "claim_id" in columns_after


def test_add_missing_columns_is_idempotent(monkeypatch):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)  # already has claim_id via create_all on a fresh DB

    monkeypatch.setattr(db_module, "engine", engine)
    # Running it twice must not raise (e.g. "duplicate column") - a fresh deploy
    # calls init_db() once, but nothing about this helper should assume that.
    _add_missing_columns()
    _add_missing_columns()

    inspector = inspect(engine)
    columns = {c["name"] for c in inspector.get_columns("evidence")}
    assert "claim_id" in columns


def test_add_missing_columns_skips_tables_that_do_not_exist_yet(monkeypatch):
    # An empty database (no tables at all) must not raise - create_all() runs
    # first in init_db(), but this helper should be safe standalone too.
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    monkeypatch.setattr(db_module, "engine", engine)
    _add_missing_columns()  # should be a no-op, not an error
