import json
from pathlib import Path
from typing import Any

from app.core.validator.db_client import QueryStatus
from app.core.validator.validator import CorpusValidator


class OracleSqlPgqCorpusCombiner:
    """Combine Oracle SQL/PGQ corpus files into a normalized dataset."""

    def __init__(self, backend: str = "oracle_sqlpgq"):
        self.backend = backend

    def combine_files(
        self,
        input_paths: list[str | Path],
        *,
        split: bool = False,
        validator: CorpusValidator | None = None,
        result_preview_chars: int = 500,
    ) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for path in input_paths:
            source_path = Path(path)
            if not source_path.exists():
                continue
            with open(source_path, encoding="utf-8") as file:
                payload = json.load(file)
            records.extend(self._normalize_records(payload, source_path))
        records = self._deduplicate(records)
        if validator is not None:
            self.validate_records(
                records,
                validator=validator,
                result_preview_chars=result_preview_chars,
            )
        if split:
            self._assign_splits(records)
        return records

    def write_combined(
        self,
        input_paths: list[str | Path],
        output_path: str | Path,
        *,
        split: bool = False,
        validator: CorpusValidator | None = None,
        result_preview_chars: int = 500,
    ) -> list[dict[str, Any]]:
        records = self.combine_files(
            input_paths,
            split=split,
            validator=validator,
            result_preview_chars=result_preview_chars,
        )
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        with open(output, "w", encoding="utf-8") as file:
            json.dump(records, file, indent=2, ensure_ascii=False)
        return records

    def validate_records(
        self,
        records: list[dict[str, Any]],
        *,
        validator: CorpusValidator,
        result_preview_chars: int = 500,
    ) -> dict[str, int]:
        client = validator._get_client()
        if client is None:
            raise RuntimeError("CorpusValidator has no database client.")

        summary = {"passed": 0, "failed": 0}
        for record in records:
            result = client.execute_query(record["query"])
            record["validation_status_code"] = result.status_code
            if result.status_code == QueryStatus.SUCCESS:
                record["validation"] = "passed"
                record["validation_error"] = ""
                record["result"] = self._preview(result.data, result_preview_chars)
                summary["passed"] += 1
            else:
                record["validation"] = "failed"
                record["validation_error"] = self._preview(result.error, result_preview_chars)
                record["result"] = ""
                summary["failed"] += 1
        return summary

    def _normalize_records(
        self, payload: Any, source_path: Path
    ) -> list[dict[str, Any]]:
        if isinstance(payload, dict):
            payload = [payload]
        if not isinstance(payload, list):
            return []

        normalized = []
        for index, item in enumerate(payload):
            if not isinstance(item, dict):
                continue
            question = str(item.get("question") or "").strip()
            query = str(item.get("query") or item.get("oracle_sqlpgq") or "").strip()
            if not question and item.get("labels"):
                question = self._question_from_labels(item["labels"])
            if not question or not query:
                continue
            normalized.append(
                {
                    "id": self._record_id(source_path, index),
                    "backend": self.backend,
                    "question": question,
                    "query": query,
                    "source_file": str(source_path),
                    "source_index": index,
                    "category": item.get("category") or self._infer_category(query),
                    "template_id": item.get("template_id", ""),
                    "labels": item.get("labels", []),
                    "validation": item.get("validation", "not_run"),
                    "result": item.get("result", ""),
                }
            )
        return normalized

    def _deduplicate(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen = set()
        deduped = []
        for record in records:
            key = (
                " ".join(record["question"].lower().split()),
                " ".join(record["query"].lower().split()),
            )
            if key in seen:
                continue
            seen.add(key)
            record["id"] = f"oracle_sqlpgq_{len(deduped) + 1:06d}"
            deduped.append(record)
        return deduped

    def _assign_splits(self, records: list[dict[str, Any]]) -> None:
        total = len(records)
        train_cutoff = int(total * 0.8)
        dev_cutoff = int(total * 0.9)
        for index, record in enumerate(records):
            if index < train_cutoff:
                record["split"] = "train"
            elif index < dev_cutoff:
                record["split"] = "dev"
            else:
                record["split"] = "test"

    def _record_id(self, source_path: Path, index: int) -> str:
        return f"{source_path.stem}_{index + 1}"

    def _infer_category(self, query: str) -> str:
        normalized = " ".join(query.upper().split())
        if "GROUP BY" in normalized or "COUNT(" in normalized or "AVG(" in normalized:
            return "aggregation"
        if "UNION" in normalized or " JOIN " in normalized:
            return "relational_sql_composition"
        if "->{1," in normalized or "ONE ROW PER STEP" in normalized:
            return "path_query"
        if "EDGE_ID(" in normalized or "VERTEX_ID(" in normalized:
            return "element_identity"
        return "graph_traversal"

    def _question_from_labels(self, labels: list[str]) -> str:
        return "Show Oracle SQL/PGQ results for " + " to ".join(str(label) for label in labels) + "."

    def _preview(self, value: Any, max_chars: int) -> str:
        text = str(value)
        if len(text) <= max_chars:
            return text
        return text[:max_chars] + "..."
