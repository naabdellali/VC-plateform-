from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, declarative_base

from app.config import get_settings

settings = get_settings()

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Additive-only columns added to a table that already existed before this column was
# introduced. `create_all()` only creates missing TABLES, never missing COLUMNS on a
# table that's already there - so a brand-new deploy gets `evidence.claim_id` for
# free via create_all, but an existing database (e.g. Render's persistent Postgres,
# already holding companies from earlier sessions) would silently keep the old
# schema and every INSERT referencing the new column would fail. Listed here and
# applied by `_add_missing_columns()` below rather than pulling in Alembic for a
# single nullable column - a real migration tool still belongs in Phase 2 once the
# schema stabilizes, per the original MVP note.
_ADDITIVE_COLUMNS = [
    # (table, column, DDL type - kept deliberately simple/portable across SQLite and Postgres)
    ("evidence", "claim_id", "VARCHAR"),
]


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _add_missing_columns() -> None:
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    with engine.begin() as conn:
        for table, column, ddl_type in _ADDITIVE_COLUMNS:
            if table not in existing_tables:
                continue  # create_all() will have created it fresh, with the column already present
            columns = {c["name"] for c in inspector.get_columns(table)}
            if column not in columns:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}"))


def init_db():
    # MVP: create_all is enough for new tables. A real migration tool (alembic)
    # belongs in Phase 2 once the schema stabilizes - _add_missing_columns() is a
    # deliberately minimal stopgap for additive columns on tables that already exist.
    from app import models  # noqa: F401  (ensure models are registered)

    Base.metadata.create_all(bind=engine)
    _add_missing_columns()
