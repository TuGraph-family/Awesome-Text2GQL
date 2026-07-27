from __future__ import annotations

# ruff: noqa: E402,I001

import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.impl.oracle_sqlpgq.db_client.oracle_db_client import OracleDBClient
from dataset_prep.compare_oracle_neo4j_results import (
    DEFAULT_VALID_ORACLE_STATUSES,
    DatasetNeo4jLoader,
    compare_record,
    load_enriched_records,
    oracle_element_label_aliases,
    select_records_for_range,
    skip_reason_for_record,
)
from dataset_prep.discover import DatabaseUnit, discover_database_units
from dataset_prep.oracle_loader import DatasetOracleLoader
from dataset_prep.reporting import write_json
from dataset_prep.translate_validate import graph_name_for


ORACLE_EXPORT_PREFIX = "oracle_"
SOURCE_QUERY_FIELD_NAMES = ("initial_cypher", "initial_gql", "cypher", "query")


def main() -> None:
    args = parse_args()
    dataset_root = Path(args.dataset_root).resolve()
    output_root = Path(args.output_root)
    prepare_output_root(output_root, overwrite=args.overwrite)

    units = discover_database_units(dataset_root, args.splits)
    if args.databases:
        requested = {name.lower() for name in args.databases}
        units = [unit for unit in units if unit.database.lower() in requested]
    if args.limit_databases:
        units = units[: args.limit_databases]
    if not units:
        raise SystemExit("No dataset units matched the requested filters.")

    query_paths = {unit.query_path.resolve() for unit in units}
    if args.copy_assets:
        copy_dataset_assets(units, dataset_root, output_root, query_paths)

    oracle_client = OracleDBClient(
        {
            "dsn": os.environ["ORACLE_DSN"],
            "user": os.environ["ORACLE_USER"],
            "password": os.environ["ORACLE_PASSWORD"],
        }
    )
    summaries: List[Dict[str, Any]] = []
    try:
        for unit in units:
            print(f"[start] {unit.split}/{unit.database}", flush=True)
            summary = export_unit(unit, oracle_client, dataset_root, output_root, args)
            summaries.append(summary)
            print(
                f"[done] {unit.split}/{unit.database}: "
                f"exported={summary['exported']} failed={summary['failed']} "
                f"skipped={summary['skipped']}",
                flush=True,
            )
    finally:
        oracle_client.close()

    write_json(output_root / "export_summary.json", merge_export_summaries(summaries))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Export only Oracle SQL/PGQ records whose translated SQL/PGQ and source "
            "Cypher results match on Oracle and Neo4j."
        )
    )
    parser.add_argument("--dataset-root", default="dataset")
    parser.add_argument("--dataset-output-root", default="output/dataset_prep")
    parser.add_argument("--output-root", default="output/oracle_sqlpgq_dataset")
    parser.add_argument("--splits", nargs="+", default=["train", "dev", "test"])
    parser.add_argument("--databases", nargs="*", default=[])
    parser.add_argument("--limit-databases", type=int, default=0)
    parser.add_argument("--limit-queries", type=int, default=0)
    parser.add_argument("--query-offset", type=int, default=0)
    parser.add_argument("--graph-prefix", default="T2GQL")
    parser.add_argument("--sql-pgq-field", default="initial_sql_pgq")
    parser.add_argument("--include-oracle-metadata", action="store_true")
    parser.add_argument("--copy-assets", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument(
        "--oracle-statuses",
        nargs="+",
        default=sorted(DEFAULT_VALID_ORACLE_STATUSES),
        help="Prior Oracle validation statuses eligible for export.",
    )
    parser.add_argument("--include-all-translatable", action="store_true")
    parser.add_argument("--oracle-timeout-ms", type=int, default=60000)
    parser.add_argument("--neo4j-timeout-s", type=float, default=60.0)
    parser.add_argument("--neo4j-uri", default=os.environ.get("NEO4J_URI", "bolt://localhost:7687"))
    parser.add_argument("--neo4j-user", default=os.environ.get("NEO4J_USER", "neo4j"))
    parser.add_argument("--neo4j-password", default=os.environ.get("NEO4J_PASSWORD", "password"))
    parser.add_argument("--neo4j-database", default=os.environ.get("NEO4J_DATABASE", "neo4j"))
    parser.add_argument("--neo4j-batch-size", type=int, default=1000)
    parser.add_argument("--keep-loaded", action="store_true")
    parser.add_argument(
        "--reuse-loaded",
        action="store_true",
        help="Skip Oracle/Neo4j load setup and export against already-loaded graphs.",
    )
    parser.add_argument("--progress-every", type=int, default=0)
    return parser.parse_args()


def prepare_output_root(output_root: Path, overwrite: bool = False) -> None:
    if output_root.exists() and any(output_root.iterdir()):
        if not overwrite:
            raise SystemExit(
                f"Output root already exists and is not empty: {output_root}. "
                "Use --overwrite or choose a different --output-root."
            )
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)


def export_unit(
    unit: DatabaseUnit,
    oracle_client: OracleDBClient,
    dataset_root: Path,
    output_root: Path,
    args: argparse.Namespace,
) -> Dict[str, Any]:
    graph_name = graph_name_for(unit, args.graph_prefix)
    oracle_loader = DatasetOracleLoader(
        oracle_client,
        unit.import_config_path,
        unit.csv_root,
        graph_name,
    )
    neo4j_loader = DatasetNeo4jLoader(
        args.neo4j_uri,
        args.neo4j_user,
        args.neo4j_password,
        args.neo4j_database,
        unit.import_config_path,
        unit.csv_root,
        args.neo4j_batch_size,
    )
    summary: Dict[str, Any] = {
        "split": unit.split,
        "database": unit.database,
        "query_file": str(unit.query_path),
        "import_config": str(unit.import_config_path),
        "graph_name": graph_name,
        "total_records": 0,
        "selected_records": 0,
        "considered": 0,
        "exported": 0,
        "failed": 0,
        "skipped": 0,
        "skip_reasons": {},
        "failure_reasons": {},
        "output_query_file": str(output_root / unit.query_path.relative_to(dataset_root)),
    }
    exported_records: List[Dict[str, Any]] = []
    element_label_aliases = oracle_element_label_aliases(oracle_loader)
    valid_statuses = set(args.oracle_statuses)
    try:
        if args.reuse_loaded:
            summary["loaded"] = {"reused": True}
            print(f"[load] {unit.split}/{unit.database}: reusing loaded graphs", flush=True)
        else:
            print(f"[load] {unit.split}/{unit.database}: oracle", flush=True)
            oracle_counts = oracle_loader.setup()
            print(f"[load] {unit.split}/{unit.database}: neo4j", flush=True)
            neo4j_counts = neo4j_loader.setup(clear=True)
            summary["loaded"] = {"oracle": oracle_counts, "neo4j": neo4j_counts}
            print(f"[load] {unit.split}/{unit.database}: done", flush=True)

        all_records = load_enriched_records(unit, Path(args.dataset_output_root))
        records = select_records_for_range(all_records, args.query_offset, args.limit_queries)
        summary["total_records"] = len(all_records)
        summary["query_offset"] = max(args.query_offset, 0)
        summary["selected_records"] = len(records)
        if args.limit_queries:
            summary["limit_queries"] = args.limit_queries

        for selected_index, record in enumerate(records, start=1):
            if args.progress_every and selected_index % args.progress_every == 0:
                print(
                    f"[progress] {unit.split}/{unit.database}: "
                    f"{selected_index}/{len(records)} selected records",
                    flush=True,
                )
            skip_reason = skip_reason_for_record(
                record,
                valid_statuses=valid_statuses,
                include_all_translatable=args.include_all_translatable,
            )
            if skip_reason:
                summary["skipped"] += 1
                increment(summary["skip_reasons"], skip_reason)
                continue

            summary["considered"] += 1
            comparison = compare_record(
                record,
                oracle_client,
                neo4j_loader,
                args,
                element_label_aliases=element_label_aliases,
            )
            if comparison["matched"]:
                exported_records.append(project_export_record(record, args))
                summary["exported"] += 1
                continue

            if comparison["reason"] in {
                "nondeterministic_limit_without_order",
                "nondeterministic_with_limit_without_order",
                "suspected_order_by_limit_tie",
                "source_invalid",
            }:
                summary["skipped"] += 1
                increment(summary["skip_reasons"], comparison["reason"])
                continue

            summary["failed"] += 1
            increment(summary["failure_reasons"], comparison["reason"] or "unknown")

        write_records_like_source(
            unit.query_path,
            output_root / unit.query_path.relative_to(dataset_root),
            exported_records,
        )
        return summary
    finally:
        if not args.keep_loaded:
            if not args.reuse_loaded:
                oracle_loader.cleanup(ignore_errors=True)
                try:
                    neo4j_loader.clear()
                except Exception:
                    pass
        neo4j_loader.close()


def project_export_record(record: Dict[str, Any], args: argparse.Namespace) -> Dict[str, Any]:
    sql_pgq = record.get("oracle_sqlpgq")
    if not args.include_oracle_metadata:
        base_record = {
            key: value
            for key, value in record.items()
            if not key.startswith(ORACLE_EXPORT_PREFIX)
        }
    else:
        base_record = dict(record)
    return insert_sql_pgq_field(base_record, args.sql_pgq_field, sql_pgq)


def insert_sql_pgq_field(
    record: Dict[str, Any],
    field_name: str,
    sql_pgq: Any,
) -> Dict[str, Any]:
    query_field_positions = [
        index for index, key in enumerate(record) if key in SOURCE_QUERY_FIELD_NAMES
    ]
    insert_after = max(query_field_positions) if query_field_positions else len(record) - 1
    output: Dict[str, Any] = {}
    inserted = False
    for index, (key, value) in enumerate(record.items()):
        if key == field_name:
            continue
        output[key] = value
        if index == insert_after:
            output[field_name] = sql_pgq
            inserted = True
    if not inserted:
        output[field_name] = sql_pgq
    return output


def write_records_like_source(
    source_path: Path,
    output_path: Path,
    records: Sequence[Dict[str, Any]],
) -> None:
    source_data = json.loads(source_path.read_text(encoding="utf-8"))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(source_data, dict):
        keyed_records = {
            str(record.get("id", index)): record for index, record in enumerate(records)
        }
        output_path.write_text(
            json.dumps(keyed_records, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return
    output_path.write_text(
        json.dumps(list(records), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def copy_dataset_assets(
    units: Sequence[DatabaseUnit],
    dataset_root: Path,
    output_root: Path,
    query_paths: set[Path],
) -> None:
    copied_roots: set[Path] = set()
    for unit in units:
        root = unit.root.resolve()
        if root in copied_roots:
            continue
        copied_roots.add(root)
        for source_path in root.rglob("*"):
            if source_path.is_dir() or source_path.resolve() in query_paths:
                continue
            relative_path = source_path.relative_to(dataset_root)
            target_path = output_root / relative_path
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, target_path)


def merge_export_summaries(summaries: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    merged: Dict[str, Any] = {
        "databases": 0,
        "total_records": 0,
        "selected_records": 0,
        "considered": 0,
        "exported": 0,
        "failed": 0,
        "skipped": 0,
        "skip_reasons": {},
        "failure_reasons": {},
        "units": [],
    }
    for summary in summaries:
        merged["databases"] += 1
        for key in (
            "total_records",
            "selected_records",
            "considered",
            "exported",
            "failed",
            "skipped",
        ):
            merged[key] += int(summary.get(key, 0))
        for key, value in summary.get("skip_reasons", {}).items():
            increment(merged["skip_reasons"], key, int(value))
        for key, value in summary.get("failure_reasons", {}).items():
            increment(merged["failure_reasons"], key, int(value))
        merged["units"].append(summary)
    return merged


def increment(counter: Dict[str, int], key: str, amount: int = 1) -> None:
    counter[key] = counter.get(key, 0) + amount


if __name__ == "__main__":
    main()
