"""
Data layer for loading JSONL files from the Data folder into DuckDB.
"""

import json
import os
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from .schema_config import TABLE_CONFIG


class DataLayer:
    def __init__(self, data_root: Path, use_firebase: bool = False):
        self.data_root = data_root
        self.use_firebase = use_firebase and os.getenv("FIREBASE_CREDENTIALS_JSON")
        self.conn = duckdb.connect(database=":memory:")
        self.table_columns: dict[str, list[str]] = {}
        
        # Download from Firebase if needed
        if self.use_firebase:
            self._ensure_data_downloaded()
    
    def _ensure_data_downloaded(self) -> None:
        """Download Data folder from Firebase if not present locally."""
        if not self.data_root.exists() or not list(self.data_root.glob("*")):
            print("Data folder not found locally. Downloading from Firebase...")
            try:
                from .firebase_storage import FirebaseStorage
                firebase = FirebaseStorage()
                firebase.download_data_folder(self.data_root)
                print("Download successful!")
            except Exception as e:
                print(f"Warning: Could not download from Firebase: {e}")
                print("Continuing with local data if available...")


    def _read_jsonl_file(self, file_path: Path) -> list[dict[str, Any]]:
        """Read a single JSONL file."""
        rows: list[dict[str, Any]] = []
        with file_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
        return rows

    def _flatten_time_obj(self, value: Any) -> Any:
        """Convert time objects like {hours, minutes, seconds} to HH:MM:SS string."""
        if isinstance(value, dict) and {"hours", "minutes", "seconds"}.issubset(set(value.keys())):
            return f"{int(value.get('hours', 0)):02d}:{int(value.get('minutes', 0)):02d}:{int(value.get('seconds', 0)):02d}"
        return value

    def load_tables(self) -> dict[str, int]:
        """Load all JSONL files into DuckDB tables. Returns row counts per table."""
        stats: dict[str, int] = {}

        for table_name in TABLE_CONFIG.keys():
            table_dir = self.data_root / table_name
            if not table_dir.exists():
                continue

            all_rows: list[dict[str, Any]] = []
            for file_path in sorted(table_dir.glob("*.jsonl")):
                all_rows.extend(self._read_jsonl_file(file_path))

            if not all_rows:
                continue

            # Normalize time objects to strings
            normalized_rows = []
            for row in all_rows:
                normalized_rows.append({k: self._flatten_time_obj(v) for k, v in row.items()})

            df = pd.DataFrame(normalized_rows)
            self.table_columns[table_name] = list(df.columns)

            # Register with DuckDB
            self.conn.register("tmp_df", df)
            self.conn.execute(f"CREATE OR REPLACE TABLE {table_name} AS SELECT * FROM tmp_df")
            self.conn.unregister("tmp_df")
            stats[table_name] = len(df)

        return stats

    def execute_sql(self, sql: str) -> pd.DataFrame:
        """Execute a SQL query against the loaded tables."""
        return self.conn.execute(sql).fetchdf()

    def get_schema_prompt_text(self) -> str:
        """Generate schema text for LLM prompts."""
        lines = []
        for table, cols in self.table_columns.items():
            lines.append(f"{table}({', '.join(cols)})")
        return "\n".join(lines)
