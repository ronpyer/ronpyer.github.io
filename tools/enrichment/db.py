import json
import sqlite3
from pathlib import Path


SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def connect_db(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def apply_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_PATH.read_text())


def create_run(
    conn: sqlite3.Connection,
    *,
    run_type: str,
    model_name: str | None = None,
    classifier_model: str | None = None,
    detector_model: str | None = None,
    embedder_model: str | None = None,
    parameters: dict | None = None,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO enrichment_runs (
          run_type, model_name, classifier_model, detector_model, embedder_model, parameters_json
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            run_type,
            model_name,
            classifier_model,
            detector_model,
            embedder_model,
            json.dumps(parameters or {}, sort_keys=True),
        ),
    )
    return int(cur.lastrowid)


def normalize_tag(tag: str) -> str:
    return " ".join(tag.strip().lower().split())
