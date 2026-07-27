from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List


def write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def append_jsonl(path: Path, records: Iterable[Dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with open(path, "a", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")
            count += 1
    return count


def summarize_records(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    status_counts: Dict[str, int] = {}
    category_counts: Dict[str, int] = {}
    for record in records:
        status = record.get("oracle_validation_status", "unknown")
        category = record.get("oracle_translation_category", "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
        category_counts[category] = category_counts.get(category, 0) + 1
    return {
        "total": len(records),
        "translation_categories": category_counts,
        "validation_statuses": status_counts,
        "complete": True,
    }


def merge_global_summaries(summaries: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    total = 0
    status_counts: Dict[str, int] = {}
    category_counts: Dict[str, int] = {}
    databases = 0
    for summary in summaries:
        databases += 1
        total += int(summary.get("total", 0))
        for key, value in summary.get("validation_statuses", {}).items():
            status_counts[key] = status_counts.get(key, 0) + int(value)
        for key, value in summary.get("translation_categories", {}).items():
            category_counts[key] = category_counts.get(key, 0) + int(value)
    return {
        "databases": databases,
        "total": total,
        "translation_categories": category_counts,
        "validation_statuses": status_counts,
    }
