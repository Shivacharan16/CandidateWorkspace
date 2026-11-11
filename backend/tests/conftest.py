import os
import tempfile
import pytest
from pathlib import Path
from backend.storage.db import get_connection, init_db
from backend.storage.repository import CDCRepository
from backend.transformation.cdc_engine import CDCEngine
from backend.ingestion.reader import BatchIngestionPipeline

@pytest.fixture
def temp_db(tmp_path):
    """Provides a fresh isolated SQLite database with full schema for each test."""
    db_file = tmp_path / "test_cdc.db"
    init_db(db_file)
    conn = get_connection(db_file)
    repo = CDCRepository(conn)
    engine = CDCEngine(repo)
    pipeline = BatchIngestionPipeline(db_file)

    yield {
        "db_path": db_file,
        "conn": conn,
        "repo": repo,
        "engine": engine,
        "pipeline": pipeline
    }

    conn.close()
