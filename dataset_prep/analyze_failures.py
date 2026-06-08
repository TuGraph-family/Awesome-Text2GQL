from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import re
from typing import Any, Dict, Iterable, List

from dataset_prep.cypher_schema import CypherSchema
from dataset_prep.discover import discover_database_units
from dataset_prep.translate_validate import (
    has_expensive_bounded_variable_length_path,
    has_quantified_relationship_property_map,
)

FAILURE_STATUSES = {"syntax_error", "runtime_error", "unsupported", "load_error"}


def main() -> None:
    args = parse_args()
    output_root = Path(args.output_root)
    records = list(iter_enriched_records(output_root))
    failure_records = [
        record for record in records if record.get("oracle_validation_status") in FAILURE_STATUSES
    ]

    report = build_report(
        failure_records,
        output_root=output_root,
        dataset_root=Path(args.dataset_root) if args.dataset_root else None,
        splits=args.splits,
        sample_limit=args.sample_limit,
    )
    write_json(output_root / "failure_analysis.json", report)
    write_markdown(output_root / "failure_analysis.md", report)
    print(f"Wrote {output_root / 'failure_analysis.json'}")
    print(f"Wrote {output_root / 'failure_analysis.md'}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Group dataset_prep translation failures by root-cause signature."
    )
    parser.add_argument("--output-root", default="output/dataset_prep")
    parser.add_argument("--dataset-root", default="dataset")
    parser.add_argument("--splits", nargs="+", default=["train", "dev", "test"])
    parser.add_argument("--sample-limit", type=int, default=5)
    return parser.parse_args()


def iter_enriched_records(output_root: Path) -> Iterable[Dict[str, Any]]:
    for path in sorted(output_root.glob("*/*/oracle_sqlpgq_enriched.jsonl")):
        with open(path, encoding="utf-8") as file:
            for line_number, line in enumerate(file, start=1):
                if not line.strip():
                    continue
                record = json.loads(line)
                meta = record.setdefault("oracle_dataset_meta", {})
                meta.setdefault("output_file", str(path))
                meta.setdefault("output_line", line_number)
                yield record


def build_report(
    records: List[Dict[str, Any]],
    output_root: Path,
    dataset_root: Path | None,
    splits: List[str],
    sample_limit: int,
) -> Dict[str, Any]:
    status_counts = Counter(record.get("oracle_validation_status") for record in records)
    signature_counts: Counter[tuple[str, str]] = Counter()
    by_signature: dict[tuple[str, str], list[Dict[str, Any]]] = defaultdict(list)
    by_database: Counter[str] = Counter()

    for record in records:
        status = record.get("oracle_validation_status", "unknown")
        signature = failure_signature(record)
        signature_counts[(status, signature)] += 1
        by_signature[(status, signature)].append(record)
        meta = record.get("oracle_dataset_meta", {})
        by_database[f"{meta.get('split')}/{meta.get('database')}"] += 1

    missing_outputs = []
    if dataset_root is not None and dataset_root.exists():
        completed = {
            str(path.relative_to(output_root)).split("/summary.json", 1)[0]
            for path in output_root.glob("*/*/summary.json")
        }
        expected = {
            f"{unit.split}/{unit.database}"
            for unit in discover_database_units(dataset_root, splits)
        }
        missing_outputs = sorted(expected - completed)

    top_signatures = []
    for (status, signature), count in signature_counts.most_common():
        top_signatures.append(
            {
                "status": status,
                "signature": signature,
                "count": count,
                "likely_next_action": likely_next_action(status, signature),
                "samples": [
                    sample_record(record)
                    for record in by_signature[(status, signature)][:sample_limit]
                ],
            }
        )

    return {
        "output_root": str(output_root),
        "total_failures": len(records),
        "status_counts": dict(status_counts),
        "top_databases_by_failures": dict(by_database.most_common(30)),
        "databases_without_completed_output": missing_outputs,
        "top_signatures": top_signatures,
    }


def failure_signature(record: Dict[str, Any]) -> str:
    status = record.get("oracle_validation_status", "")
    if status == "unsupported":
        query_signature = unsupported_query_signature(record.get("oracle_source_query") or "")
        if query_signature in {
            "multiple_with_skipped",
            "standalone_optional_match",
            "optional_match_left_join_required",
        }:
            return query_signature
        schema_signature = schema_mismatch_signature(record)
        if schema_signature:
            return schema_signature
        features = record.get("oracle_unsupported_features") or []
        if features:
            return ",".join(features)
        return query_signature or record.get("oracle_translation_category") or "unsupported"

    error = str(record.get("oracle_validation_error") or "").strip()
    if not error:
        return "empty_error"
    ora_match = re.search(r"\bORA-\d{5}\b", error)
    if ora_match:
        first_line = error.splitlines()[0]
        return f"{ora_match.group(0)} {first_line.split(':', 1)[-1].strip()}"
    return error.splitlines()[0][:240]


def unsupported_query_signature(query: str) -> str:
    normalized = " ".join(str(query or "").split())
    if not normalized:
        return ""
    if len(re.findall(r"\bWITH\b", normalized, flags=re.IGNORECASE)) > 1:
        return "multiple_with_skipped"
    if re.search(
        r"\.(?:bad_alias|role_type|contradiction_severity|support_strength)\b",
        normalized,
        flags=re.IGNORECASE,
    ) or re.search(
        r"\bc\.validity_start\b|\bs\.name\b|\bn2\.sensitivity_level\b|\bg\.created_date\b",
        normalized,
        flags=re.IGNORECASE,
    ):
        return "invalid_schema_property"
    if re.search(r"\bOPTIONAL\s+MATCH\b", normalized, flags=re.IGNORECASE):
        if re.match(r"^OPTIONAL\s+MATCH\b", normalized, flags=re.IGNORECASE):
            return "standalone_optional_match"
        return "optional_match_left_join_required"
    if re.search(
        r"\b(?:AVG|SUM)\s*\([^)]*(?:date|timestamp)[^)]*\)",
        normalized,
        flags=re.IGNORECASE,
    ):
        return "temporal_numeric_aggregate"
    if re.search(
        r"\bMATCH\s+`?[A-Za-z_][A-Za-z0-9_]*`?\s*=",
        normalized,
        flags=re.IGNORECASE,
    ):
        return "path_variable_return"
    if re.search(
        r"-\s*\[[^\]]*\*\s*(?:\d+\s*)?\.\.\s*\]\s*(?:->|-)|"
        r"(?:<-|-)\s*\[[^\]]*\*\s*(?:\d+\s*)?\.\.\s*\]\s*-",
        normalized,
        flags=re.IGNORECASE,
    ):
        return "open_ended_variable_length_path"
    if has_quantified_relationship_property_map(normalized):
        return "quantified_relationship_property_map"
    if has_expensive_bounded_variable_length_path(normalized):
        return "expensive_variable_length_path"
    if re.search(r"\bWITH\b.+\bMATCH\b", normalized, flags=re.IGNORECASE):
        return "with_match_pipeline"
    match_prefix = normalized.split(" WHERE ", 1)[0].split(" WITH ", 1)[0].split(" RETURN ", 1)[0]
    if "," in match_prefix:
        return "multi_pattern_match"
    return ""


def schema_mismatch_signature(record: Dict[str, Any]) -> str:
    query = str(record.get("oracle_source_query") or "")
    meta = record.get("oracle_dataset_meta") or {}
    import_config = meta.get("import_config")
    if not query or not import_config:
        return ""
    config_path = Path(import_config)
    if not config_path.exists():
        return ""
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return ""
    for issue in CypherSchema(config).validation_issues(query):
        if issue.signature in {
            "invalid_schema_label",
            "invalid_schema_property",
            "invalid_schema_direction",
            "unsafe_numeric_conversion",
            "unsafe_temporal_numeric_comparison",
        }:
            return issue.signature
    return ""


def _cypher_variable_labels(query: str) -> tuple[dict[str, str], dict[str, str]]:
    node_labels: dict[str, str] = {}
    edge_labels: dict[str, str] = {}
    for match in re.finditer(
        r"\(\s*(?P<var>[A-Za-z_][A-Za-z0-9_]*)?\s*:\s*`?(?P<label>[^`(){},\s]+)`?", query
    ):
        variable = match.group("var")
        if variable:
            node_labels[variable] = _clean_schema_name(match.group("label"))
    for match in re.finditer(
        r"\[\s*(?P<var>[A-Za-z_][A-Za-z0-9_]*)?\s*:\s*`?(?P<label>[^`\]{}\s]+)`?", query
    ):
        variable = match.group("var")
        if variable:
            edge_labels[variable] = _clean_schema_name(match.group("label"))
    return node_labels, edge_labels


def _cypher_property_references(query: str) -> list[tuple[str, str]]:
    protected = re.sub(r"'(?:\\'|[^'])*'|\"(?:\\\"|[^\"])*\"", "''", query)
    references = []
    for match in re.finditer(
        r"\b(?P<var>[A-Za-z_][A-Za-z0-9_]*)\."
        r"(?:`(?P<quoted>[^`]+)`|(?P<bare>[A-Za-z_][A-Za-z0-9_$#-]*))",
        protected,
    ):
        references.append(
            (match.group("var"), _clean_schema_name(match.group("quoted") or match.group("bare")))
        )
    return references


def _cypher_property_maps(query: str, node: bool) -> list[tuple[str, list[str]]]:
    open_char, close_char = ("(", ")") if node else ("[", "]")
    escaped_open = re.escape(open_char)
    escaped_close = re.escape(close_char)
    pattern = re.compile(
        escaped_open
        + r"\s*(?:[A-Za-z_][A-Za-z0-9_]*)?\s*:\s*`?(?P<label>[^`(){}\]\[,\s]+)`?"
        + r"\s*\{(?P<body>[^}]*)\}"
        + escaped_close
    )
    maps = []
    for match in pattern.finditer(query):
        properties = [
            _clean_schema_name(prop.group("prop"))
            for prop in re.finditer(
                r"`?(?P<prop>[A-Za-z_][A-Za-z0-9_$#-]*)`?\s*:", match.group("body")
            )
        ]
        maps.append((_clean_schema_name(match.group("label")), properties))
    return maps


def _cypher_edge_triples(query: str) -> list[tuple[str, str, str, str]]:
    node = (
        r"\(\s*(?:[A-Za-z_][A-Za-z0-9_]*)?\s*:\s*`?"
        r"(?P<NAME>[^`(){}\]\[,\s]+)`?(?:\s*\{[^}]*\})?\s*\)"
    )
    edge = r"\[\s*(?:[A-Za-z_][A-Za-z0-9_]*)?\s*:\s*`?(?P<edge>[^`\]{}\s]+)`?(?:\s*\{[^}]*\})?\s*\]"
    triples = []
    right_pattern = (
        node.replace("NAME", "left")
        + r"\s*-\s*"
        + edge
        + r"\s*->\s*"
        + node.replace("NAME", "right")
    )
    left_pattern = (
        node.replace("NAME", "left")
        + r"\s*<-\s*"
        + edge
        + r"\s*-\s*"
        + node.replace("NAME", "right")
    )
    for start in range(len(query)):
        match = re.match(right_pattern, query[start:])
        if match:
            triples.append(
                (
                    _clean_schema_name(match.group("left")),
                    "right",
                    _clean_schema_name(match.group("edge")),
                    _clean_schema_name(match.group("right")),
                )
            )
        match = re.match(left_pattern, query[start:])
        if match:
            triples.append(
                (
                    _clean_schema_name(match.group("left")),
                    "left",
                    _clean_schema_name(match.group("edge")),
                    _clean_schema_name(match.group("right")),
                )
            )
    return triples


def _property_exists(property_name: str, properties: set[str]) -> bool:
    clean = _clean_schema_name(property_name)
    snake = re.sub(r"(?<!^)(?=[A-Z])", "_", clean).lower()
    candidates = {clean, snake, clean.lower(), snake.lower()}
    return any(prop in candidates or prop.lower() in candidates for prop in properties)


def _clean_schema_name(value: str) -> str:
    return str(value or "").strip().strip("`").strip('"')


def likely_next_action(status: str, signature: str) -> str:
    if status == "unsupported":
        if signature == "multiple_with_skipped":
            return (
                "Skipped by policy: do not spend translator work on queries with more "
                "than one WITH."
            )
        if signature == "path_variable_return":
            return (
                "Keep unsupported unless grouped path projection semantics are added "
                "for Oracle SQL/PGQ."
            )
        if signature == "temporal_numeric_aggregate":
            return (
                "Keep unsupported unless the source query explicitly converts temporal "
                "values to numeric durations."
            )
        if signature == "expensive_variable_length_path":
            return (
                "Skip broad undirected variable-length paths that can exhaust Oracle "
                "validation resources."
            )
        if signature == "open_ended_variable_length_path":
            return (
                "Keep unsupported or add an explicit max bound; Oracle SQL/PGQ rejects "
                "open-ended bounded quantifiers."
            )
        if signature == "invalid_schema_property":
            return "Treat as invalid source/schema mismatch; do not emit SQL for absent properties."
        if signature == "optional_match":
            return (
                "Correlated OPTIONAL MATCH should translate through the Graph IR LEFT "
                "JOIN path; inspect unsupported samples for unsupported optional shapes."
            )
        if signature == "standalone_optional_match":
            return (
                "Standalone OPTIONAL MATCH differs from MATCH only for empty-match "
                "null-row semantics; keep unsupported unless that behavior is modeled."
            )
        if signature == "optional_match_left_join_required":
            return (
                "Retry with Graph IR OPTIONAL MATCH support; remaining cases likely "
                "lack correlation or exceed the v1 optional scope."
            )
        if signature == "with_match_pipeline":
            return (
                "Inspect whether this single-WITH pipeline is covered by staged SQL "
                "support; add a focused test if fixable."
            )
        if signature == "multi_pattern_match":
            return (
                "Inspect comma-separated path patterns for schema validity and "
                "shared-variable support."
            )
        return (
            "Decide whether this Cypher feature maps to documented Oracle SQL/PGQ; "
            "otherwise keep classified as unsupported."
        )
    if "ORA-40996" in signature:
        return (
            "Check whether a string literal was emitted as a double-quoted identifier "
            "or a variable was used without a MATCH declaration."
        )
    if "ORA-00936" in signature or "ORA-00904" in signature:
        return (
            "Inspect generated SELECT/ORDER BY aliases; project any outer SQL "
            "references through GRAPH_TABLE COLUMNS."
        )
    if "ORA-42414" in signature:
        return "Fix graph DDL property typing or omit mixed-type properties from colliding labels."
    if "ORA-02291" in signature:
        return (
            "Investigate CSV referential integrity, or add an unenforced import mode "
            "for benchmark data."
        )
    if "ORA-12899" in signature:
        return (
            "Use CLOB or wider text columns for long STRING/TEXT properties during dataset loading."
        )
    return (
        "Inspect sample source query and generated SQL, then add a focused translator "
        "or loader test."
    )


def sample_record(record: Dict[str, Any]) -> Dict[str, Any]:
    meta = record.get("oracle_dataset_meta", {})
    return {
        "split": meta.get("split"),
        "database": meta.get("database"),
        "record_index": meta.get("record_index"),
        "id": record.get("id"),
        "source_query": record.get("oracle_source_query"),
        "oracle_sqlpgq": record.get("oracle_sqlpgq"),
        "error": record.get("oracle_validation_error"),
        "output_file": meta.get("output_file"),
        "output_line": meta.get("output_line"),
    }


def write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def write_markdown(path: Path, report: Dict[str, Any]) -> None:
    lines = [
        "# Dataset Prep Failure Analysis",
        "",
        f"- Output root: `{report['output_root']}`",
        f"- Total query failures: `{report['total_failures']}`",
        f"- Status counts: `{json.dumps(report['status_counts'], sort_keys=True)}`",
        "",
        "## Top Databases",
        "",
    ]
    for database, count in report["top_databases_by_failures"].items():
        lines.append(f"- `{database}`: `{count}`")

    if report["databases_without_completed_output"]:
        lines += ["", "## Databases Without Completed Output", ""]
        for database in report["databases_without_completed_output"]:
            lines.append(f"- `{database}`")

    lines += ["", "## Top Failure Signatures", ""]
    for item in report["top_signatures"]:
        lines.append(f"### {item['status']} / {item['signature']} / {item['count']}")
        lines.append("")
        lines.append(item["likely_next_action"])
        lines.append("")
        for sample in item["samples"]:
            lines.append(
                f"- `{sample['split']}/{sample['database']}` "
                f"record `{sample['record_index']}` id `{sample['id']}`"
            )
            lines.append(f"  - Source: `{sample['source_query']}`")
            lines.append(f"  - SQL: `{sample['oracle_sqlpgq']}`")
            if sample.get("error"):
                lines.append(f"  - Error: `{sample['error'].splitlines()[0]}`")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
