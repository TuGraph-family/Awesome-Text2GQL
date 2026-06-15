from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
from typing import Any, Dict, List

from app.core.validator.db_client import QueryStatus
from app.impl.oracle_sqlpgq.db_client.oracle_db_client import OracleDBClient
from app.impl.oracle_sqlpgq.utils.sqlpgq import OracleNameSanitizer
from dataset_prep.cypher_schema import CypherSchema
from dataset_prep.discover import DatabaseUnit, discover_database_units, source_query
from dataset_prep.oracle_loader import DatasetOracleLoader
from dataset_prep.preflight import run_preflight
from dataset_prep.reporting import merge_global_summaries, summarize_records, write_json
from examples.cypher2oracle_sqlpgq import cypher2oracle_sqlpgq

UNSUPPORTED_PATTERNS = {
    "shortest_path": re.compile(r"\b(ANY|ALL)\s+SHORTEST\b|\bSHORTEST\b", re.IGNORECASE),
    "cost": re.compile(
        r"\b(?:ANY|ALL)\s+CHEAPEST\b|\bTOTAL\s+COST\b|\bCOST\s*\(",
        re.IGNORECASE,
    ),
    "inline_subquery": re.compile(r"\bCALL\s*\{|\bEXISTS\s*\{", re.IGNORECASE),
    "lateral": re.compile(r"\bLATERAL\b", re.IGNORECASE),
    "optional_match": re.compile(r"\bOPTIONAL\s+MATCH\b", re.IGNORECASE),
    "relative_duration": re.compile(r"\bdate\s*\(\s*\)\s*[-+]\s*duration\s*\(", re.IGNORECASE),
    "unwind": re.compile(r"\bUNWIND\b", re.IGNORECASE),
    "open_ended_variable_length_path": re.compile(
        r"-\s*\[[^\]]*\*\s*(?:(?:\d+\s*)?\.\.\s*|\.\.\s*\d+)\]\s*(?:->|-)|"
        r"(?:<-|-)\s*\[[^\]]*\*\s*(?:(?:\d+\s*)?\.\.\s*|\.\.\s*\d+)\]\s*-|"
        r"-\s*\[[^\]]*\*\s*\]\s*(?:->|-)|"
        r"(?:<-|-)\s*\[[^\]]*\*\s*\]\s*-",
        re.IGNORECASE,
    ),
    "case_label_predicate": re.compile(
        r"\bCASE\b(?:(?!\bEND\b).)*\b[A-Za-z_][A-Za-z0-9_]*\s*:",
        re.IGNORECASE | re.DOTALL,
    ),
}


def main() -> None:
    args = parse_args()
    dataset_root = Path(args.dataset_root)
    output_root = Path(args.output_root)
    preflight = run_preflight(require_oracle_env=not args.skip_live_validation)
    for warning in preflight.warnings:
        print(f"[preflight warning] {warning}")
    if not preflight.ok:
        for error in preflight.errors:
            print(f"[preflight error] {error}")
        raise SystemExit(2)

    units = discover_database_units(dataset_root, args.splits)
    if args.databases:
        requested = {name.lower() for name in args.databases}
        units = [unit for unit in units if unit.database.lower() in requested]
    if args.limit_databases:
        units = units[: args.limit_databases]

    global_summaries: List[Dict[str, Any]] = []
    unsupported_samples: List[Dict[str, Any]] = []
    for unit in units:
        summary_path = output_root / unit.split / unit.database / "summary.json"
        if args.resume and summary_path.exists():
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            if summary.get("complete"):
                global_summaries.append(summary)
                print(f"[skip] {unit.split}/{unit.database}")
                continue
        try:
            print(f"[start] {unit.split}/{unit.database}", flush=True)
            summary, samples = process_unit(unit, output_root, args)
            global_summaries.append(summary)
            unsupported_samples.extend(samples)
            print(f"[done] {unit.split}/{unit.database}: {summary['validation_statuses']}")
        except Exception as exc:
            print(f"[error] {unit.split}/{unit.database}: {exc}")
            if args.fail_fast:
                raise

    write_json(output_root / "global_summary.json", merge_global_summaries(global_summaries))
    if unsupported_samples:
        write_jsonl(output_root / "unsupported_samples.jsonl", unsupported_samples)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Translate Text2GQL dataset queries to Oracle SQL/PGQ."
    )
    parser.add_argument("--dataset-root", default="dataset")
    parser.add_argument("--output-root", default="output/dataset_prep")
    parser.add_argument("--splits", nargs="+", default=["train", "dev", "test"])
    parser.add_argument("--databases", nargs="*", default=[])
    parser.add_argument("--graph-prefix", default="T2GQL")
    parser.add_argument("--limit-databases", type=int, default=0)
    parser.add_argument("--limit-queries", type=int, default=0)
    parser.add_argument(
        "--query-offset",
        type=int,
        default=0,
        help="Skip this many source records before applying --limit-queries.",
    )
    parser.add_argument(
        "--progress-every",
        type=int,
        default=0,
        help="Print query progress every N selected records. Use 1 for every record.",
    )
    parser.add_argument("--keep-db-on-failure", action="store_true")
    parser.add_argument("--skip-live-validation", action="store_true")
    parser.add_argument(
        "--oracle-validation-timeout-ms",
        type=int,
        default=int(os.environ.get("ORACLE_VALIDATION_TIMEOUT_MS", "60000")),
        help="Oracle timeout for each translated query validation call. Use 0 to disable.",
    )
    parser.add_argument(
        "--oracle-validation-fetch-limit",
        type=int,
        default=int(os.environ.get("ORACLE_VALIDATION_FETCH_LIMIT", "1")),
        help="Rows fetched for each translated query validation call. Use 0 to fetch all.",
    )
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--fail-fast", action="store_true")
    return parser.parse_args()


def process_unit(
    unit: DatabaseUnit,
    output_root: Path,
    args: argparse.Namespace,
) -> tuple[Dict[str, Any], List[Dict[str, Any]]]:
    graph_name = graph_name_for(unit, args.graph_prefix)
    out_dir = output_root / unit.split / unit.database
    out_dir.mkdir(parents=True, exist_ok=True)
    output_path = out_dir / "oracle_sqlpgq_enriched.jsonl"
    all_records = load_records(unit.query_path)
    query_offset = max(args.query_offset, 0)
    records = all_records[query_offset:]
    if args.limit_queries:
        records = records[: args.limit_queries]

    client = None
    loader = None
    load_counts: Dict[str, int] = {}
    node_label_map: Dict[str, List[str]] = {}
    edge_label_map: Dict[str, List[str]] = {}
    property_type_map: Dict[str, Dict[str, str]] = {}
    node_primary_key_map: Dict[str, str] = {}
    edge_primary_key_map: Dict[str, str] = {}
    source_schema = CypherSchema.from_path(unit.import_config_path)

    enriched: List[Dict[str, Any]] = []
    unsupported_samples: List[Dict[str, Any]] = []
    try:
        if not args.skip_live_validation:
            client = OracleDBClient(
                {
                    "dsn": os.environ["ORACLE_DSN"],
                    "user": os.environ["ORACLE_USER"],
                    "password": os.environ["ORACLE_PASSWORD"],
                }
            )
            loader = DatasetOracleLoader(client, unit.import_config_path, unit.csv_root, graph_name)
            load_counts = loader.setup()
            node_label_map = loader.node_label_map()
            edge_label_map = loader.edge_label_map()
            property_type_map = loader.property_type_map()
            node_primary_key_map = loader.node_primary_key_map()
            edge_primary_key_map = loader.edge_primary_key_map()

        for selected_index, record in enumerate(records):
            source_index = query_offset + selected_index
            if args.progress_every and selected_index % args.progress_every == 0:
                print(
                    "[query] "
                    f"{unit.split}/{unit.database} "
                    f"selected_index={selected_index} "
                    f"record_index={source_index} "
                    f"id={record.get('id')}",
                    flush=True,
                )
            enriched_record = translate_record(
                record,
                graph_name,
                client,
                node_label_map=node_label_map,
                edge_label_map=edge_label_map,
                property_type_map=property_type_map,
                node_primary_key_map=node_primary_key_map,
                edge_primary_key_map=edge_primary_key_map,
                source_schema=source_schema,
                validation_timeout_ms=args.oracle_validation_timeout_ms,
                validation_fetch_limit=args.oracle_validation_fetch_limit,
            )
            enriched_record["oracle_dataset_meta"] = {
                "split": unit.split,
                "database": unit.database,
                "query_file": str(unit.query_path),
                "import_config": str(unit.import_config_path),
                "graph_name": graph_name,
                "record_index": source_index,
                "selected_index": selected_index,
            }
            enriched.append(enriched_record)
            if enriched_record["oracle_validation_status"] == "unsupported":
                unsupported_samples.append(
                    {
                        "split": unit.split,
                        "database": unit.database,
                        "id": record.get("id"),
                        "unsupported_features": enriched_record["oracle_unsupported_features"],
                        "query": enriched_record.get("oracle_source_query"),
                    }
                )
        write_jsonl(output_path, enriched)
        summary = summarize_records(enriched)
        summary.update(
            {
                "split": unit.split,
                "database": unit.database,
                "graph_name": graph_name,
                "query_file": str(unit.query_path),
                "import_config": str(unit.import_config_path),
                "query_offset": query_offset,
                "load_counts": load_counts,
            }
        )
        write_json(out_dir / "summary.json", summary)
        return summary, unsupported_samples
    except Exception:
        if not args.keep_db_on_failure and loader is not None:
            loader.cleanup(ignore_errors=True)
        raise
    finally:
        if loader is not None and not args.keep_db_on_failure:
            loader.cleanup(ignore_errors=True)
        if client is not None:
            client.close()


def load_records(query_path: Path) -> List[Dict[str, Any]]:
    data = json.loads(query_path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        return [
            dict(value, id=key) if isinstance(value, dict) else {"id": key, "value": value}
            for key, value in data.items()
        ]
    return list(data)


def translate_record(
    record: Dict[str, Any],
    graph_name: str,
    client: OracleDBClient | None,
    node_label_map: Dict[str, List[str]] | None = None,
    edge_label_map: Dict[str, List[str]] | None = None,
    property_type_map: Dict[str, Dict[str, str]] | None = None,
    node_primary_key_map: Dict[str, str] | None = None,
    edge_primary_key_map: Dict[str, str] | None = None,
    source_schema: CypherSchema | None = None,
    validation_timeout_ms: int = 0,
    validation_fetch_limit: int = 0,
) -> Dict[str, Any]:
    output = dict(record)
    query_field, query = source_query(record)
    output["oracle_source_query_field"] = query_field
    output["oracle_source_query"] = query
    output["oracle_unsupported_features"] = detect_unsupported_features(
        query,
        source_schema=source_schema,
    )
    if not query:
        output.update(
            _status(None, "missing_source_query", "unsupported", "No source query found.")
        )
        return output
    if output["oracle_unsupported_features"]:
        output.update(
            _status(
                None,
                "Graph-IL Not Support",
                "unsupported",
                "Query uses constructs intentionally not emitted for Oracle SQL/PGQ.",
            )
        )
        return output

    translated, category = cypher2oracle_sqlpgq(
        query,
        graph_name=graph_name,
        node_label_map=node_label_map,
        edge_label_map=edge_label_map,
        property_type_map=property_type_map,
        node_primary_key_map=node_primary_key_map,
        edge_primary_key_map=edge_primary_key_map,
        strict_property_validation=bool(property_type_map),
    )
    if category != "Graph-IL Translatable":
        output.update(_status(None, category, "unsupported", translated))
        return output

    validation_status = "syntax_ok"
    error = ""
    if client is not None:
        result = client.execute_query(
            translated,
            fetch_limit=validation_fetch_limit,
            call_timeout_ms=validation_timeout_ms,
        )
        if result.status_code == QueryStatus.SUCCESS:
            validation_status = "success"
        elif result.status_code == QueryStatus.NO_RECORD:
            validation_status = "no_record"
        elif result.status_code == QueryStatus.CLIENT_ERROR:
            validation_status = "syntax_error"
            error = result.error or ""
        else:
            validation_status = "runtime_error"
            error = result.error or ""

    output.update(_status(translated, category, validation_status, error))
    return output


def detect_unsupported_features(
    query: str,
    source_schema: CypherSchema | None = None,
) -> List[str]:
    searchable_query = mask_string_literals(query or "")
    features = [
        name
        for name, pattern in UNSUPPORTED_PATTERNS.items()
        if query and pattern.search(searchable_query)
    ]
    if query and has_quantified_relationship_property_map(searchable_query):
        features.append("quantified_relationship_property_map")
    if query and has_expensive_undirected_variable_length_path(searchable_query):
        features.append("expensive_variable_length_path")
    if query and len(re.findall(r"\bWITH\b", searchable_query, flags=re.IGNORECASE)) > 1:
        features.append("multiple_with")
    if source_schema is not None:
        features.extend(issue.signature for issue in source_schema.validation_issues(query))
    if "optional_match" in features and is_supported_correlated_optional_match(query):
        features.remove("optional_match")
    if "optional_match" in features and is_supported_standalone_optional_match(query):
        features.remove("optional_match")
    if "optional_match" in features and is_supported_optional_after_with_match(query):
        features.remove("optional_match")
    if "optional_match" in features and is_supported_match_optional_with(query):
        features.remove("optional_match")
    if "optional_match" in features and is_supported_optional_null_antijoin(query):
        features.remove("optional_match")
    return list(dict.fromkeys(features))


def has_quantified_relationship_property_map(query: str) -> bool:
    return bool(
        re.search(
            r"\[[^\]]*\*\s*(?:\d+\s*)?(?:\.\.\s*\d*)?[^\]]*\{[^}]+\}[^\]]*\]|"
            r"\[[^\]]*\{[^}]+\}[^\]]*\*\s*(?:\d+\s*)?(?:\.\.\s*\d*)?[^\]]*\]",
            query,
            flags=re.IGNORECASE,
        )
    )


def has_expensive_undirected_variable_length_path(query: str) -> bool:
    for match in re.finditer(
        r"(?<!<)-\s*\[[^\]]*\*\s*(?P<lower>\d+)\s*\.\.\s*(?P<upper>\d+)\s*\]\s*-(?!>)",
        query,
        flags=re.IGNORECASE,
    ):
        upper = int(match.group("upper"))
        if upper > 3:
            return True
    return False


def mask_string_literals(query: str) -> str:
    result: List[str] = []
    index = 0
    while index < len(query):
        quote = query[index]
        if quote not in {"'", '"'}:
            result.append(quote)
            index += 1
            continue
        result.append(quote)
        index += 1
        while index < len(query):
            char = query[index]
            if char == "\\" and index + 1 < len(query):
                result.append(" ")
                result.append(" ")
                index += 2
                continue
            if char == quote:
                if quote == "'" and index + 1 < len(query) and query[index + 1] == "'":
                    result.append(" ")
                    result.append(" ")
                    index += 2
                    continue
                result.append(quote)
                index += 1
                break
            result.append(" " if not char.isspace() else char)
            index += 1
    return "".join(result)


def is_supported_correlated_optional_match(query: str) -> bool:
    normalized = " ".join(str(query or "").split())
    if re.match(r"^OPTIONAL\s+MATCH\b", normalized, flags=re.IGNORECASE):
        return False
    if len(re.findall(r"\bOPTIONAL\s+MATCH\b", normalized, flags=re.IGNORECASE)) != 1:
        return False
    if len(re.findall(r"\bWITH\b", normalized, flags=re.IGNORECASE)) > 1:
        return False
    optional_match = re.search(r"\bOPTIONAL\s+MATCH\b", normalized, flags=re.IGNORECASE)
    if not optional_match:
        return False
    base_fragment = normalized[: optional_match.start()]
    optional_tail = normalized[optional_match.end() :]
    optional_end = len(optional_tail)
    for keyword_match in re.finditer(r"\b(?:WITH|RETURN)\b", optional_tail, flags=re.IGNORECASE):
        optional_end = keyword_match.start()
        break
    optional_fragment = optional_tail[:optional_end]
    base_variables = set(_declared_cypher_variables(base_fragment))
    optional_variables = set(_declared_cypher_variables(optional_fragment))
    return bool(base_variables & optional_variables)


def _declared_cypher_variables(fragment: str) -> List[str]:
    variables: List[str] = []
    for pattern in (
        r"\(\s*(?P<var>[A-Za-z_][A-Za-z0-9_]*)\s*(?::|[){])",
        r"\[\s*(?P<var>[A-Za-z_][A-Za-z0-9_]*)\s*(?::|[\]{])",
    ):
        for match in re.finditer(pattern, fragment or ""):
            variable = match.group("var")
            if variable not in variables:
                variables.append(variable)
    return variables


def is_supported_standalone_optional_match(query: str) -> bool:
    normalized = " ".join(str(query or "").split())
    if not re.match(r"^OPTIONAL\s+MATCH\b", normalized, flags=re.IGNORECASE):
        return False
    if len(re.findall(r"\bOPTIONAL\s+MATCH\b", normalized, flags=re.IGNORECASE)) != 1:
        return False
    if re.search(r"\bWITH\b", normalized, flags=re.IGNORECASE):
        return False
    if re.search(r"\bRETURN\s+count\s*\(\s*\*\s*\)", normalized, flags=re.IGNORECASE):
        return False
    return True


def is_supported_optional_after_with_match(query: str) -> bool:
    normalized = " ".join(str(query or "").split())
    if re.match(r"^OPTIONAL\s+MATCH\b", normalized, flags=re.IGNORECASE):
        return False
    if len(re.findall(r"\bOPTIONAL\s+MATCH\b", normalized, flags=re.IGNORECASE)) != 1:
        return False
    if len(re.findall(r"\bWITH\b", normalized, flags=re.IGNORECASE)) != 1:
        return False
    if re.search(r"\bRETURN\s+count\s*\(\s*\*\s*\)", normalized, flags=re.IGNORECASE):
        return False
    return bool(
        re.search(
            r"\bMATCH\b.+\bWITH\b.+\bOPTIONAL\s+MATCH\b.+\bRETURN\b",
            normalized,
            flags=re.IGNORECASE,
        )
    )


def is_supported_match_optional_with(query: str) -> bool:
    normalized = " ".join(str(query or "").split())
    if re.match(r"^OPTIONAL\s+MATCH\b", normalized, flags=re.IGNORECASE):
        return False
    if len(re.findall(r"\bOPTIONAL\s+MATCH\b", normalized, flags=re.IGNORECASE)) != 1:
        return False
    if len(re.findall(r"\bWITH\b", normalized, flags=re.IGNORECASE)) != 1:
        return False
    return bool(
        re.search(
            r"^\s*MATCH\b.+\bOPTIONAL\s+MATCH\b.+\bWITH\b.+\bRETURN\b",
            normalized,
            flags=re.IGNORECASE,
        )
    )


def is_supported_optional_null_antijoin(query: str) -> bool:
    normalized = " ".join(str(query or "").split())
    if re.match(r"^OPTIONAL\s+MATCH\b", normalized, flags=re.IGNORECASE):
        return False
    if len(re.findall(r"\bOPTIONAL\s+MATCH\b", normalized, flags=re.IGNORECASE)) != 1:
        return False
    if re.search(r"\bWITH\b", normalized, flags=re.IGNORECASE):
        return False
    return bool(
        re.search(
            r"^\s*MATCH\b.+\bOPTIONAL\s+MATCH\b.+\bWHERE\s+"
            r"[A-Za-z_][A-Za-z0-9_]*\s+IS\s+NULL\b.+\bRETURN\b",
            normalized,
            flags=re.IGNORECASE,
        )
    )


def _status(
    sqlpgq: str | None,
    category: str,
    validation_status: str,
    error: str,
) -> Dict[str, Any]:
    return {
        "oracle_sqlpgq": sqlpgq,
        "oracle_translation_category": category,
        "oracle_validation_status": validation_status,
        "oracle_validation_error": error,
    }


def graph_name_for(unit: DatabaseUnit, prefix: str) -> str:
    return OracleNameSanitizer.clean(f"{prefix}_{unit.split}_{unit.database}", fallback="GRAPH")


def write_jsonl(path: Path, records: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
