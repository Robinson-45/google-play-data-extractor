thonimport csv
import json
import logging
from pathlib import Path
from typing import Any, Dict, Iterable, List

LOGGER = logging.getLogger(__name__)

def _ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

def export_to_json(records: Iterable[Dict[str, Any]], path: Path) -> None:
    _ensure_parent_dir(path)
    data: List[Dict[str, Any]] = list(records)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    LOGGER.info("Exported %d records to JSON: %s", len(data), path)

def export_to_csv(records: Iterable[Dict[str, Any]], path: Path) -> None:
    _ensure_parent_dir(path)
    rows: List[Dict[str, Any]] = list(records)
    if not rows:
        LOGGER.warning("No records to export to CSV.")
        return

    # Collect all field names across records to keep CSV schema flexible
    fieldnames: List[str] = []
    for row in rows:
        for key in row.keys():
            if key not in fieldnames:
                fieldnames.append(key)

    # Convert lists to comma-separated strings for CSV
    def serialize(value: Any) -> Any:
        if isinstance(value, list):
            return ", ".join(str(v) for v in value)
        if isinstance(value, bool):
            return "true" if value else "false"
        return value

    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: serialize(v) for k, v in row.items()})

    LOGGER.info("Exported %d records to CSV: %s", len(rows), path)