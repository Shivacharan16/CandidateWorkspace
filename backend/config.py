import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

DATABASE_DIR = BASE_DIR / "database"
DATABASE_PATH = Path(os.environ.get("CDC_DB_PATH", DATABASE_DIR / "cdc_pipeline.db"))
SCHEMA_PATH = DATABASE_DIR / "schema.sql"

SAMPLE_DATA_DIR = BASE_DIR / "sample_data"
FRONTEND_DIR = BASE_DIR / "frontend"

API_HOST = os.environ.get("CDC_API_HOST", "127.0.0.1")
API_PORT = int(os.environ.get("CDC_API_PORT", 8000))

BATCH_SIZE = int(os.environ.get("CDC_BATCH_SIZE", 5000))
DEFAULT_RANDOM_SEED = 42
