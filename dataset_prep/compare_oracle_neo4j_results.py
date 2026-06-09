from __future__ import annotations

# ruff: noqa: E402,I001

import argparse
import csv
import json
import logging
import os
from pathlib import Path
import re
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    from neo4j import GraphDatabase, Query
except ImportError:  # pragma: no cover - depends on local environment.
    GraphDatabase = None
    Query = None

from app.core.validator.db_client import QueryStatus
from app.impl.oracle_sqlpgq.db_client.oracle_db_client import OracleDBClient
from app.impl.oracle_sqlpgq.utils.sqlpgq import OracleNameSanitizer
from dataset_prep.cypher_schema import CypherSchema, CypherSchemaIssue
from dataset_prep.discover import DatabaseUnit, discover_database_units
from dataset_prep.oracle_loader import DatasetOracleLoader
from dataset_prep.reporting import append_jsonl, write_json


DEFAULT_VALID_ORACLE_STATUSES = {"success", "no_record"}
logging.getLogger("neo4j.notifications").setLevel(logging.ERROR)


@dataclass(frozen=True)
class StableExecutionQueries:
    oracle_sqlpgq: str
    cypher: str
    applied: bool = False
    reason: str = ""


@dataclass(frozen=True)
class CypherReturnItem:
    expression: str
    alias: str
    order_term: str


class DatasetNeo4jLoader:
    def __init__(
        self,
        uri: str,
        user: str,
        password: str,
        database: str,
        import_config_path: Path,
        csv_root: Path,
        batch_size: int = 1000,
    ):
        if GraphDatabase is None:
            raise RuntimeError("Install the 'neo4j' package before running this script.")
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        self.database = database
        self.import_config_path = import_config_path
        self.csv_root = csv_root
        self.batch_size = batch_size
        self.clear_batch_size = max(batch_size, 1000)
        self.config = json.loads(import_config_path.read_text(encoding="utf-8"))
        self.cypher_schema = CypherSchema(self.config)
        self.schema = list(self.config.get("schema", []))
        self.files = list(self.config.get("files", []))
        self.vertices = [item for item in self.schema if item.get("type") == "VERTEX"]
        self.edges = [item for item in self.schema if item.get("type") == "EDGE"]
        self.vertex_by_label = {item["label"]: item for item in self.vertices}
        self.primary_by_label = {
            item["label"]: item.get("primary", "_id") for item in self.vertices
        }
        self.property_types_by_label = {
            item["label"]: {
                prop["name"]: prop.get("type", "STRING")
                for prop in item.get("properties", [])
                if prop.get("name")
            }
            for item in self.schema
        }
        self.vertex_labels = {item["label"] for item in self.vertices}
        self.edge_labels = {item["label"] for item in self.edges}
        self.node_label_aliases = self._schema_name_aliases(self.vertex_labels)
        self.edge_type_aliases = self._schema_name_aliases(self.edge_labels)
        self.property_aliases_by_label = {
            label: self._schema_name_aliases(properties)
            for label, properties in self.property_types_by_label.items()
        }
        self.global_property_aliases = self._global_property_aliases()

    def close(self) -> None:
        self.driver.close()

    def setup(self, clear: bool = True) -> Dict[str, int]:
        with self.driver.session(database=self.database) as session:
            if clear:
                self.clear(session)
            self._create_constraints(session)
        counts = self._load_vertices()
        counts.update(self._load_edges())
        return counts

    def clear(self, session: Any | None = None) -> None:
        if session is not None:
            self._clear_with_session(session)
            return
        with self.driver.session(database=self.database) as owned_session:
            self._clear_with_session(owned_session)

    def _clear_with_session(self, session: Any) -> None:
        rel_delete = "MATCH ()-[r]-() WITH r LIMIT $limit DELETE r RETURN count(r) AS deleted"
        node_delete = "MATCH (n) WITH n LIMIT $limit DELETE n RETURN count(n) AS deleted"
        self._delete_until_empty(session, rel_delete)
        self._delete_until_empty(session, node_delete)

    def _delete_until_empty(self, session: Any, query: str) -> None:
        while True:
            record = session.run(query, limit=self.clear_batch_size).single()
            deleted = record["deleted"] if record else 0
            if deleted == 0:
                return

    def execute(self, query: str, timeout_s: float | None = None) -> tuple[str, list[dict], str]:
        query = self.prepare_query(query)
        try:
            with self.driver.session(database=self.database) as session:
                executable = (
                    Query(query, timeout=timeout_s) if Query is not None and timeout_s else query
                )
                result = session.run(executable)
                return "success", [dict(record) for record in result], ""
        except Exception as exc:
            error = str(exc)
            status = "client_error" if "syntax" in error.lower() else "server_error"
            return status, [], error

    def prepare_query(self, query: str) -> str:
        query = self._rewrite_schema_aliases(query)
        query = self._coerce_string_backed_boolean_literals(query)
        query = self._coerce_string_backed_numeric_comparisons(query)
        query = self._coerce_string_backed_date_comparisons(query)
        return query

    def source_validation_issues(self, query: str) -> list[CypherSchemaIssue]:
        schema = getattr(self, "cypher_schema", None)
        if schema is None:
            return []
        return schema.validation_issues(query)

    def _rewrite_schema_aliases(self, query: str) -> str:
        query = _rewrite_outside_string_literals(query, self._rewrite_node_labels)
        query = _rewrite_outside_string_literals(query, self._rewrite_relationship_types)
        variables = self._query_variable_labels(query)
        edge_variables = self._query_edge_variable_labels(query)
        full_query = query
        return _rewrite_outside_string_literals(
            query,
            lambda segment: self._rewrite_property_accesses(
                segment,
                variables,
                edge_variables,
                full_query,
            ),
        )

    def _rewrite_node_labels(self, query: str) -> str:
        def replace(match: re.Match) -> str:
            label = match.group("quoted_label") or match.group("label")
            canonical = self._canonical_node_label(label)
            return f"{match.group('prefix')}{_cypher_identifier(canonical)}"

        return re.sub(
            r"(?P<prefix>\(\s*(?:[A-Za-z_][A-Za-z0-9_]*\s*)?:\s*)"
            r"(?:`(?P<quoted_label>[^`]+)`|(?P<label>[A-Za-z_][A-Za-z0-9_$#-]*))",
            replace,
            query,
        )

    def _rewrite_relationship_types(self, query: str) -> str:
        def rewrite_type(raw_type: str) -> str:
            stripped = raw_type.strip()
            if not stripped:
                return raw_type
            if stripped.startswith("`") and stripped.endswith("`"):
                label = stripped[1:-1]
            else:
                label = stripped
            return _cypher_identifier(self._canonical_edge_type(label))

        def replace(match: re.Match) -> str:
            types = [rewrite_type(item) for item in match.group("types").split("|")]
            return f"{match.group('prefix')}{'|'.join(types)}"

        return re.sub(
            r"(?P<prefix>\[\s*(?:[A-Za-z_][A-Za-z0-9_]*\s*)?:\s*)"
            r"(?P<types>`[^`]+`|[A-Za-z_][A-Za-z0-9_$#-]*"
            r"(?:\s*\|\s*(?:`[^`]+`|[A-Za-z_][A-Za-z0-9_$#-]*))*)",
            replace,
            query,
        )

    def _rewrite_property_accesses(
        self,
        query: str,
        variables: Dict[str, str],
        edge_variables: Dict[str, str] | None = None,
        full_query: str | None = None,
    ) -> str:
        edge_variables = edge_variables or {}
        full_query = full_query or query

        def replace(match: re.Match) -> str:
            variable = match.group("variable")
            property_name = match.group("quoted_property") or match.group("property")
            target_variable, canonical = self._canonical_property_reference(
                full_query,
                variable,
                property_name,
                variables,
                edge_variables,
            )
            return f"{target_variable}.{_cypher_identifier(canonical)}"

        return re.sub(
            r"\b(?P<variable>[A-Za-z_][A-Za-z0-9_]*)\.\s*"
            r"(?:`(?P<quoted_property>[^`]+)`|"
            r"(?P<property>[A-Za-z_][A-Za-z0-9_$#-]*))",
            replace,
            query,
        )

    def _canonical_node_label(self, label: str) -> str:
        return self._canonical_schema_name(
            label,
            getattr(self, "node_label_aliases", {}),
        )

    def _canonical_edge_type(self, edge_type: str) -> str:
        return self._canonical_schema_name(
            edge_type,
            getattr(self, "edge_type_aliases", {}),
        )

    def _canonical_property_name(
        self,
        variable: str,
        property_name: str,
        variables: Dict[str, str],
    ) -> str:
        target_variable, canonical = self._canonical_property_reference(
            "",
            variable,
            property_name,
            variables,
            {},
        )
        return canonical if target_variable else property_name

    def _canonical_property_reference(
        self,
        query: str,
        variable: str,
        property_name: str,
        variables: Dict[str, str],
        edge_variables: Dict[str, str],
    ) -> tuple[str, str]:
        if property_name.lower() in {"identity", "id"}:
            if variable in variables:
                primary_key = self.primary_by_label.get(variables[variable])
                if primary_key:
                    return variable, primary_key
            if variable in edge_variables:
                return variable, "EDGE_ID"
        schema = getattr(self, "cypher_schema", None)
        if schema is not None and query:
            redirected_variable, redirected_property = schema.redirected_property_target(
                query,
                variable,
                property_name,
            )
            if redirected_variable and redirected_property:
                return redirected_variable, redirected_property
        label = variables.get(variable, "")
        aliases_by_label = getattr(self, "property_aliases_by_label", {})
        if label in aliases_by_label:
            canonical = self._canonical_schema_name(property_name, aliases_by_label[label])
            if canonical != property_name:
                return variable, canonical
        return variable, self._canonical_schema_name(
            property_name,
            getattr(self, "global_property_aliases", {}),
        )

    def _canonical_schema_name(self, name: str, aliases: Dict[str, str]) -> str:
        cleaned = OracleNameSanitizer.clean(name, fallback=name)
        return (
            aliases.get(name)
            or aliases.get(cleaned)
            or aliases.get(name.lower())
            or aliases.get(cleaned.lower())
            or name
        )

    def _schema_name_aliases(self, names: Iterable[str]) -> Dict[str, str]:
        aliases: Dict[str, str] = {}
        for name in names:
            cleaned = OracleNameSanitizer.clean(name, fallback=name)
            for alias in {name, cleaned, name.lower(), cleaned.lower()}:
                aliases.setdefault(alias, name)
        return aliases

    def _global_property_aliases(self) -> Dict[str, str]:
        candidates: Dict[str, set[str]] = {}
        for properties in getattr(self, "property_types_by_label", {}).values():
            for property_name in properties:
                cleaned = OracleNameSanitizer.clean(property_name, fallback=property_name)
                for alias in {property_name, cleaned, property_name.lower(), cleaned.lower()}:
                    candidates.setdefault(alias, set()).add(property_name)
        return {alias: next(iter(names)) for alias, names in candidates.items() if len(names) == 1}

    def _coerce_string_backed_boolean_literals(self, query: str) -> str:
        variables = self._query_variable_labels(query)

        def replace_not_property(match: re.Match) -> str:
            variable = match.group("variable")
            property_name = match.group("property")
            if not self._is_string_property(variables.get(variable, ""), property_name):
                return match.group(0)
            return f"{variable}.{property_name} = 'false'"

        query = re.sub(
            r"\bNOT\s+(?P<variable>[A-Za-z_][A-Za-z0-9_]*)\."
            r"(?P<property>[A-Za-z_][A-Za-z0-9_$#]*)\b",
            replace_not_property,
            query,
            flags=re.IGNORECASE,
        )

        def replace_comparison(match: re.Match) -> str:
            variable = match.group("variable")
            property_name = match.group("property")
            value = match.group("value").lower()
            if not self._is_string_property(variables.get(variable, ""), property_name):
                return match.group(0)
            return f"{variable}.{property_name} {match.group('operator')} '{value}'"

        query = re.sub(
            r"\b(?P<variable>[A-Za-z_][A-Za-z0-9_]*)\."
            r"(?P<property>[A-Za-z_][A-Za-z0-9_$#]*)\s*"
            r"(?P<operator>=|<>)\s*(?P<value>true|false)\b",
            replace_comparison,
            query,
            flags=re.IGNORECASE,
        )

        def replace_map_literal(match: re.Match) -> str:
            property_name = match.group("property")
            value = match.group("value").lower()
            if not self._has_string_property(property_name):
                return match.group(0)
            return f"{property_name}: '{value}'"

        return re.sub(
            r"\b(?P<property>[A-Za-z_][A-Za-z0-9_$#]*)\s*:\s*"
            r"(?P<value>true|false)\b",
            replace_map_literal,
            query,
            flags=re.IGNORECASE,
        )

    def _coerce_string_backed_numeric_comparisons(self, query: str) -> str:
        variables = self._query_variable_labels(query)

        def replace_left(match: re.Match) -> str:
            variable = match.group("variable")
            property_name = match.group("property")
            if not self._is_string_property(variables.get(variable, ""), property_name):
                return match.group(0)
            return f"{variable}.{property_name} {match.group('operator')} '{match.group('value')}'"

        query = re.sub(
            r"\b(?P<variable>[A-Za-z_][A-Za-z0-9_]*)\."
            r"(?P<property>[A-Za-z_][A-Za-z0-9_$#]*)\s*"
            r"(?P<operator><=|>=|<>|=|<|>)\s*"
            r"(?P<value>-?\d+(?:\.\d+)?)\b",
            replace_left,
            query,
        )

        def replace_right(match: re.Match) -> str:
            variable = match.group("variable")
            property_name = match.group("property")
            if not self._is_string_property(variables.get(variable, ""), property_name):
                return match.group(0)
            return f"'{match.group('value')}' {match.group('operator')} {variable}.{property_name}"

        query = re.sub(
            r"\b(?P<value>-?\d+(?:\.\d+)?)\s*"
            r"(?P<operator><=|>=|<>|=|<|>)\s*"
            r"(?P<variable>[A-Za-z_][A-Za-z0-9_]*)\."
            r"(?P<property>[A-Za-z_][A-Za-z0-9_$#]*)\b",
            replace_right,
            query,
        )

        def replace_map_literal(match: re.Match) -> str:
            property_name = match.group("property")
            value = match.group("value")
            if not self._has_string_property(property_name):
                return match.group(0)
            return f"{property_name}: '{value}'"

        return re.sub(
            r"\b(?P<property>[A-Za-z_][A-Za-z0-9_$#]*)\s*:\s*"
            r"(?P<value>-?\d+(?:\.\d+)?)\b",
            replace_map_literal,
            query,
        )

    def _coerce_string_backed_date_comparisons(self, query: str) -> str:
        variables = self._query_variable_labels(query)

        query = self._coerce_string_backed_date_accessors(query, variables)

        def replace_left(match: re.Match) -> str:
            variable = match.group("variable")
            property_name = match.group("property")
            left = match.group("left")
            if not self._is_string_property(variables.get(variable, ""), property_name):
                return match.group(0)
            if re.fullmatch(r"\s*date\s*\(", left, flags=re.IGNORECASE):
                return match.group(0)
            return (
                f"date({variable}.{property_name}) {match.group('operator')} {match.group('right')}"
            )

        query = re.sub(
            r"(?P<left>\b(?P<variable>[A-Za-z_][A-Za-z0-9_]*)\."
            r"(?P<property>[A-Za-z_][A-Za-z0-9_$#]*))\s*"
            r"(?P<operator><=|>=|<>|=|<|>)\s*"
            r"(?P<right>date\s*\([^)]+\))",
            replace_left,
            query,
            flags=re.IGNORECASE,
        )

        def replace_right(match: re.Match) -> str:
            variable = match.group("variable")
            property_name = match.group("property")
            if not self._is_string_property(variables.get(variable, ""), property_name):
                return match.group(0)
            return (
                f"{match.group('left')} {match.group('operator')} date({variable}.{property_name})"
            )

        return re.sub(
            r"(?P<left>date\s*\([^)]+\))\s*"
            r"(?P<operator><=|>=|<>|=|<|>)\s*"
            r"(?P<variable>[A-Za-z_][A-Za-z0-9_]*)\."
            r"(?P<property>[A-Za-z_][A-Za-z0-9_$#]*)\b",
            replace_right,
            query,
            flags=re.IGNORECASE,
        )

    def _coerce_string_backed_date_accessors(
        self,
        query: str,
        variables: Dict[str, str],
    ) -> str:
        def accessor_expression(variable: str, property_name: str, accessor: str) -> str:
            base = (
                f"datetime({variable}.{property_name})"
                if self._looks_like_datetime_string_property(variable, property_name)
                else f"date({variable}.{property_name})"
            )
            return f"{base}.{accessor}"

        def replace_date_call(match: re.Match) -> str:
            variable = match.group("variable")
            property_name = match.group("property")
            if not self._is_string_property(variables.get(variable, ""), property_name):
                return match.group(0)
            return accessor_expression(variable, property_name, match.group("accessor"))

        query = re.sub(
            r"\bdate\s*\(\s*(?P<variable>[A-Za-z_][A-Za-z0-9_]*)\."
            r"(?P<property>[A-Za-z_][A-Za-z0-9_$#]*)\s*\)\."
            r"(?P<accessor>year|month|day|weekday|dayOfWeek)\b",
            replace_date_call,
            query,
            flags=re.IGNORECASE,
        )

        def replace_direct_accessor(match: re.Match) -> str:
            variable = match.group("variable")
            property_name = match.group("property")
            if not self._is_string_property(variables.get(variable, ""), property_name):
                return match.group(0)
            return accessor_expression(variable, property_name, match.group("accessor"))

        return re.sub(
            r"\b(?P<variable>[A-Za-z_][A-Za-z0-9_]*)\."
            r"(?P<property>[A-Za-z_][A-Za-z0-9_$#]*)\."
            r"(?P<accessor>year|month|day|weekday|dayOfWeek)\b",
            replace_direct_accessor,
            query,
            flags=re.IGNORECASE,
        )

    def _looks_like_datetime_string_property(self, variable: str, property_name: str) -> bool:
        return property_name.lower().endswith(("at", "time", "timestamp", "datetime"))

    def _query_variable_labels(self, query: str) -> Dict[str, str]:
        labels: Dict[str, str] = {}
        for match in re.finditer(
            r"\(\s*(?P<variable>[A-Za-z_][A-Za-z0-9_]*)\s*:\s*"
            r"(?:`(?P<quoted_label>[^`]+)`|(?P<label>[A-Za-z_][A-Za-z0-9_$#-]*))",
            query,
        ):
            labels[match.group("variable")] = match.group("quoted_label") or match.group("label")
        return labels

    def _query_edge_variable_labels(self, query: str) -> Dict[str, str]:
        labels: Dict[str, str] = {}
        for match in re.finditer(
            r"\[\s*(?P<variable>[A-Za-z_][A-Za-z0-9_]*)\s*:\s*"
            r"(?:`(?P<quoted_label>[^`]+)`|(?P<label>[A-Za-z_][A-Za-z0-9_$#|.-]*))",
            query,
        ):
            label = match.group("quoted_label") or match.group("label")
            if "|" not in label:
                labels[match.group("variable")] = label
        return labels

    def _is_string_property(self, label: str, property_name: str) -> bool:
        if not label:
            return False
        label_types = self.property_types_by_label.get(label, {})
        return label_types.get(property_name, "").upper() == "STRING"

    def _has_string_property(self, property_name: str) -> bool:
        return any(
            properties.get(property_name, "").upper() == "STRING"
            for properties in self.property_types_by_label.values()
        )

    def _create_constraints(self, session: Any) -> None:
        for vertex in self.vertices:
            label = vertex["label"]
            primary = vertex.get("primary")
            if not primary:
                continue
            name = _safe_identifier(f"constraint_{label}_{primary}")
            session.run(
                f"CREATE CONSTRAINT `{name}` IF NOT EXISTS "
                f"FOR (n:`{_escape_backticks(label)}`) "
                f"REQUIRE n.`{_escape_backticks(primary)}` IS UNIQUE"
            ).consume()

    def _load_vertices(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        files_by_label = {item["label"]: item for item in self.files if "SRC_ID" not in item}
        for vertex in self.vertices:
            file_item = files_by_label.get(vertex["label"])
            if not file_item:
                continue
            rows = self._read_file(vertex, file_item, is_edge=False)
            self._write_vertex_batches(vertex, rows)
            counts[f"vertex:{vertex['label']}"] = len(rows)
        return counts

    def _load_edges(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for file_item in [item for item in self.files if "SRC_ID" in item and "DST_ID" in item]:
            edge = self._find_edge_schema(file_item)
            if not edge:
                continue
            rows = self._read_file(edge, file_item, is_edge=True)
            self._write_edge_batches(edge, file_item, rows)
            key = f"edge:{file_item['SRC_ID']}-[{edge['label']}]->{file_item['DST_ID']}"
            counts[key] = len(rows)
        return counts

    def _find_edge_schema(self, file_item: Dict[str, Any]) -> Dict[str, Any] | None:
        label = file_item.get("label")
        src = file_item.get("SRC_ID")
        dst = file_item.get("DST_ID")
        for edge in self.edges:
            if edge.get("label") != label:
                continue
            if [src, dst] in edge.get("constraints", []):
                return edge
        for edge in self.edges:
            if edge.get("label") == label:
                return edge
        return None

    def _read_file(
        self,
        schema_item: Dict[str, Any],
        file_item: Dict[str, Any],
        is_edge: bool,
    ) -> List[Dict[str, Any]]:
        path = self.csv_root / file_item["path"]
        source_columns = list(file_item.get("columns", []))
        schema_types = {
            prop["name"]: prop.get("type", "STRING") for prop in schema_item.get("properties", [])
        }
        header_rows = int(file_item.get("header", 0))
        rows: List[Dict[str, Any]] = []
        with open(path, newline="", encoding="utf-8-sig") as file:
            reader = csv.reader(file)
            for index, raw in enumerate(reader):
                if index < header_rows:
                    continue
                row = {
                    column: raw[position] if position < len(raw) else ""
                    for position, column in enumerate(source_columns)
                }
                converted = {}
                for column, value in row.items():
                    if is_edge and column == "SRC_ID":
                        converted[column] = _convert_value(
                            value,
                            self._vertex_primary_type(file_item["SRC_ID"]),
                        )
                    elif is_edge and column == "DST_ID":
                        converted[column] = _convert_value(
                            value,
                            self._vertex_primary_type(file_item["DST_ID"]),
                        )
                    else:
                        converted[column] = _convert_value(
                            value,
                            schema_types.get(column, "STRING"),
                        )
                rows.append(converted)
        return rows

    def _vertex_primary_type(self, label: str) -> str:
        vertex = self.vertex_by_label.get(label, {})
        primary = vertex.get("primary", "_id")
        for prop in vertex.get("properties", []):
            if prop.get("name") == primary:
                return prop.get("type", "STRING")
        return "STRING"

    def _write_vertex_batches(self, vertex: Dict[str, Any], rows: List[Dict[str, Any]]) -> None:
        if not rows:
            return
        label = _escape_backticks(vertex["label"])
        primary = _escape_backticks(vertex.get("primary", "_id"))
        query = (
            f"UNWIND $batch AS row "
            f"MERGE (n:`{label}` {{`{primary}`: row.`{primary}`}}) "
            f"SET n += row"
        )
        self._run_batches(query, rows)

    def _write_edge_batches(
        self,
        edge: Dict[str, Any],
        file_item: Dict[str, Any],
        rows: List[Dict[str, Any]],
    ) -> None:
        if not rows:
            return
        src_label = file_item["SRC_ID"]
        dst_label = file_item["DST_ID"]
        src_pk = self.primary_by_label.get(src_label, "_id")
        dst_pk = self.primary_by_label.get(dst_label, "_id")
        rel_type = _escape_backticks(edge["label"])
        query = (
            f"UNWIND $batch AS row "
            f"MATCH (src:`{_escape_backticks(src_label)}` "
            f"{{`{_escape_backticks(src_pk)}`: row.SRC_ID}}) "
            f"MATCH (dst:`{_escape_backticks(dst_label)}` "
            f"{{`{_escape_backticks(dst_pk)}`: row.DST_ID}}) "
            f"CREATE (src)-[r:`{rel_type}`]->(dst) "
            f"SET r += row.props"
        )
        batch_rows = []
        for index, row in enumerate(rows, start=1):
            props = {key: value for key, value in row.items() if key not in ("SRC_ID", "DST_ID")}
            # Oracle edge tables use a per-table generated EDGE_ID. Adding the
            # same validation-only value to Neo4j lets returned relationships
            # normalize to the same identity across backends.
            props.setdefault("EDGE_ID", index)
            batch_rows.append(
                {
                    "SRC_ID": row["SRC_ID"],
                    "DST_ID": row["DST_ID"],
                    "props": props,
                }
            )
        self._run_batches(query, batch_rows)

    def _run_batches(self, query: str, rows: List[Dict[str, Any]]) -> None:
        with self.driver.session(database=self.database) as session:
            for start in range(0, len(rows), self.batch_size):
                session.run(query, batch=rows[start : start + self.batch_size]).consume()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare Oracle SQL/PGQ query results with Neo4j Cypher results."
    )
    parser.add_argument("--dataset-root", default="dataset")
    parser.add_argument("--dataset-output-root", default="output/dataset_prep")
    parser.add_argument("--output-root", default="output/oracle_neo4j_compare")
    parser.add_argument("--splits", nargs="+", default=["train", "dev", "test"])
    parser.add_argument("--databases", nargs="*", default=[])
    parser.add_argument("--limit-databases", type=int, default=0)
    parser.add_argument("--limit-queries", type=int, default=0)
    parser.add_argument(
        "--query-offset",
        type=int,
        default=0,
        help="Skip this many enriched query records before applying --limit-queries.",
    )
    parser.add_argument("--graph-prefix", default="T2GQL")
    parser.add_argument(
        "--oracle-statuses",
        nargs="+",
        default=sorted(DEFAULT_VALID_ORACLE_STATUSES),
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
        help="Skip Oracle/Neo4j load setup and validate against already-loaded graphs.",
    )
    parser.add_argument(
        "--progress-every",
        type=int,
        default=0,
        help="Print query progress every N selected records.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_root = Path(args.output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    failures_path = output_root / "mismatched_or_failed_queries.jsonl"
    failures_path.write_text("", encoding="utf-8")
    units = discover_database_units(Path(args.dataset_root), args.splits)
    if args.databases:
        requested = {name.lower() for name in args.databases}
        units = [unit for unit in units if unit.database.lower() in requested]
    if args.limit_databases:
        units = units[: args.limit_databases]

    oracle_client = OracleDBClient(
        {
            "dsn": os.environ["ORACLE_DSN"],
            "user": os.environ["ORACLE_USER"],
            "password": os.environ["ORACLE_PASSWORD"],
        }
    )
    all_summaries: List[Dict[str, Any]] = []
    try:
        for unit in units:
            print(f"[start] {unit.split}/{unit.database}", flush=True)
            summary = compare_unit(unit, oracle_client, args, failures_path)
            all_summaries.append(summary)
            matched = summary["matched"]
            failed = summary["failed"]
            skipped = summary["skipped"]
            print(
                f"[done] {unit.split}/{unit.database}: "
                f"matched={matched} failed={failed} skipped={skipped}",
                flush=True,
            )
    finally:
        oracle_client.close()

    write_json(output_root / "summary.json", merge_compare_summaries(all_summaries))


def compare_unit(
    unit: DatabaseUnit,
    oracle_client: OracleDBClient,
    args: argparse.Namespace,
    failures_path: Path,
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
        "loaded": {},
        "considered": 0,
        "matched": 0,
        "failed": 0,
        "skipped": 0,
        "skip_reasons": {},
        "failure_reasons": {},
    }
    element_label_aliases = oracle_element_label_aliases(oracle_loader)
    failures: List[Dict[str, Any]] = []
    try:
        if args.reuse_loaded:
            print(f"[load] {unit.split}/{unit.database}: reusing loaded graphs", flush=True)
            summary["loaded"] = {"reused": True}
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
        summary["query_offset"] = args.query_offset
        summary["selected_records"] = len(records)
        if args.limit_queries:
            summary["limit_queries"] = args.limit_queries
        valid_statuses = set(args.oracle_statuses)
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
                summary["matched"] += 1
                continue
            if comparison["reason"] in {
                "nondeterministic_limit_without_order",
                "suspected_order_by_limit_tie",
                "source_invalid",
            }:
                summary["skipped"] += 1
                increment(summary["skip_reasons"], comparison["reason"])
                continue
            summary["failed"] += 1
            increment(summary["failure_reasons"], comparison["reason"])
            failures.append(
                {
                    "split": unit.split,
                    "database": unit.database,
                    "record_id": record.get("id"),
                    "record_index": record.get("oracle_dataset_meta", {}).get("record_index"),
                    "reason": comparison["reason"],
                    "cypher": comparison["cypher"],
                    "oracle_sqlpgq": comparison["oracle_sqlpgq"],
                    "oracle_status": comparison["oracle_status"],
                    "neo4j_status": comparison["neo4j_status"],
                    "oracle_error": comparison["oracle_error"],
                    "neo4j_error": comparison["neo4j_error"],
                    "oracle_rows_sample": comparison["oracle_rows_sample"],
                    "neo4j_rows_sample": comparison["neo4j_rows_sample"],
                    "result_diagnostics": comparison.get("result_diagnostics", {}),
                    "deterministic_ordering": comparison.get("deterministic_ordering", {}),
                }
            )
            if len(failures) >= 100:
                append_jsonl(failures_path, failures)
                failures = []
        if failures:
            append_jsonl(failures_path, failures)
        write_json(
            Path(args.output_root) / unit.split / unit.database / "summary.json",
            summary,
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


def compare_record(
    record: Dict[str, Any],
    oracle_client: OracleDBClient,
    neo4j_loader: DatasetNeo4jLoader,
    args: argparse.Namespace,
    element_label_aliases: Dict[str, str] | None = None,
) -> Dict[str, Any]:
    oracle_sqlpgq = record.get("oracle_sqlpgq") or ""
    cypher = (
        record.get("oracle_source_query")
        or record.get("initial_cypher")
        or record.get("cypher")
        or ""
    )
    source_validator = getattr(neo4j_loader, "source_validation_issues", None)
    source_issues = source_validator(cypher) if source_validator else []
    if source_issues:
        return comparison_result(
            False,
            "source_invalid",
            cypher,
            oracle_sqlpgq,
            "not_executed",
            "source_invalid",
            "",
            "; ".join(f"{issue.signature}: {issue.message}" for issue in source_issues),
            [],
            [],
            neo4j_loader.primary_by_label,
            element_label_aliases,
        )
    execution_queries = stable_execution_queries(
        oracle_sqlpgq,
        cypher,
    )
    oracle_result = oracle_client.execute_query(
        execution_queries.oracle_sqlpgq,
        call_timeout_ms=args.oracle_timeout_ms,
    )
    neo4j_status, neo4j_rows, neo4j_error = neo4j_loader.execute(
        execution_queries.cypher,
        args.neo4j_timeout_s,
    )
    oracle_status = query_status_name(oracle_result.status_code)
    oracle_rows = oracle_result.data if isinstance(oracle_result.data, list) else []
    if neo4j_status != "success":
        return comparison_result(
            False,
            "source_invalid",
            cypher,
            oracle_sqlpgq,
            oracle_status,
            neo4j_status,
            oracle_result.error or "",
            neo4j_error,
            oracle_rows,
            neo4j_rows,
            neo4j_loader.primary_by_label,
            element_label_aliases,
            execution_queries,
        )
    if oracle_status not in ("success", "no_record"):
        return comparison_result(
            False,
            "execution_error",
            cypher,
            oracle_sqlpgq,
            oracle_status,
            neo4j_status,
            oracle_result.error or "",
            neo4j_error,
            oracle_rows,
            neo4j_rows,
            neo4j_loader.primary_by_label,
            element_label_aliases,
            execution_queries,
        )
    oracle_counter = normalized_counter(
        oracle_rows,
        neo4j_loader.primary_by_label,
        element_label_aliases,
    )
    neo4j_counter = normalized_counter(
        neo4j_rows,
        neo4j_loader.primary_by_label,
        element_label_aliases,
    )
    matched = oracle_counter == neo4j_counter or normalized_rows_match_with_numeric_tolerance(
        oracle_rows,
        neo4j_rows,
        neo4j_loader.primary_by_label,
        element_label_aliases,
    )
    reason = "result_mismatch" if not matched else ""
    if (
        not matched
        and is_nondeterministic_limit_without_order(cypher)
        and not execution_queries.applied
        and oracle_rows
        and neo4j_rows
    ):
        reason = "nondeterministic_limit_without_order"
    elif (
        not matched
        and is_order_by_limit_query(cypher)
        and not execution_queries.applied
        and oracle_rows
        and neo4j_rows
    ):
        has_tie = has_order_by_limit_boundary_tie(
            cypher,
            oracle_sqlpgq,
            oracle_client,
            neo4j_loader,
            args,
            element_label_aliases,
        )
        if has_tie is not False:
            reason = "suspected_order_by_limit_tie"
    return comparison_result(
        matched,
        reason,
        cypher,
        oracle_sqlpgq,
        oracle_status,
        neo4j_status,
        "",
        "",
        oracle_rows,
        neo4j_rows,
        neo4j_loader.primary_by_label,
        element_label_aliases,
        execution_queries,
    )


def comparison_result(
    matched: bool,
    reason: str,
    cypher: str,
    oracle_sqlpgq: str,
    oracle_status: str,
    neo4j_status: str,
    oracle_error: str,
    neo4j_error: str,
    oracle_rows: Sequence[Dict[str, Any]],
    neo4j_rows: Sequence[Dict[str, Any]],
    primary_by_label: Dict[str, str] | None = None,
    element_label_aliases: Dict[str, str] | None = None,
    execution_queries: StableExecutionQueries | None = None,
) -> Dict[str, Any]:
    result = {
        "matched": matched,
        "reason": reason,
        "cypher": cypher,
        "oracle_sqlpgq": oracle_sqlpgq,
        "oracle_status": oracle_status,
        "neo4j_status": neo4j_status,
        "oracle_error": oracle_error,
        "neo4j_error": neo4j_error,
        "oracle_rows_sample": normalize_rows(
            oracle_rows[:5],
            primary_by_label,
            element_label_aliases,
        ),
        "neo4j_rows_sample": normalize_rows(
            neo4j_rows[:5],
            primary_by_label,
            element_label_aliases,
        ),
    }
    if execution_queries and execution_queries.applied:
        result["deterministic_ordering"] = {
            "reason": execution_queries.reason,
            "oracle_sqlpgq": execution_queries.oracle_sqlpgq,
            "cypher": execution_queries.cypher,
        }
    if not matched and reason == "result_mismatch":
        result["result_diagnostics"] = result_diagnostics(
            oracle_rows,
            neo4j_rows,
            primary_by_label,
            element_label_aliases,
        )
    return result


def load_enriched_records(unit: DatabaseUnit, output_root: Path) -> List[Dict[str, Any]]:
    path = output_root / unit.split / unit.database / "oracle_sqlpgq_enriched.jsonl"
    if not path.exists():
        raise FileNotFoundError(
            f"Missing enriched Oracle SQL/PGQ records for {unit.split}/{unit.database}: {path}"
        )
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def select_records_for_range(
    records: Sequence[Dict[str, Any]],
    query_offset: int = 0,
    limit_queries: int = 0,
) -> List[Dict[str, Any]]:
    start = max(query_offset, 0)
    if limit_queries > 0:
        return list(records[start : start + limit_queries])
    return list(records[start:])


def skip_reason_for_record(
    record: Dict[str, Any],
    valid_statuses: set[str],
    include_all_translatable: bool,
) -> str:
    if record.get("oracle_translation_category") != "Graph-IL Translatable":
        return "not_translatable"
    if not record.get("oracle_sqlpgq"):
        return "missing_oracle_sqlpgq"
    if not (
        record.get("oracle_source_query") or record.get("initial_cypher") or record.get("cypher")
    ):
        return "missing_cypher"
    if include_all_translatable:
        return ""
    status = record.get("oracle_validation_status")
    if status not in valid_statuses:
        return f"oracle_status:{status}"
    return ""


def stable_execution_queries(oracle_sqlpgq: str, cypher: str) -> StableExecutionQueries:
    cypher_query = _stable_cypher_paging_query(cypher)
    if cypher_query is None:
        return StableExecutionQueries(oracle_sqlpgq, cypher)
    oracle_query = _stable_oracle_paging_query(
        oracle_sqlpgq,
        cypher_query.projected_column_count,
        has_existing_order=cypher_query.had_order_by,
    )
    if oracle_query is None:
        return StableExecutionQueries(oracle_sqlpgq, cypher)
    return StableExecutionQueries(
        oracle_sqlpgq=oracle_query,
        cypher=cypher_query.query,
        applied=True,
        reason=cypher_query.reason,
    )


@dataclass(frozen=True)
class StableCypherQuery:
    query: str
    projected_column_count: int
    had_order_by: bool
    reason: str


@dataclass(frozen=True)
class FinalCypherPaging:
    return_start: int
    return_end: int
    body_start: int
    body_end: int
    pagination_start: int
    has_order_by: bool
    order_body_start: int = -1
    order_body_end: int = -1
    has_limit: bool = False
    has_skip: bool = False


def _stable_cypher_paging_query(query: str) -> StableCypherQuery | None:
    final = _final_cypher_paging(query)
    if final is None:
        return None
    return_body = query[final.body_start : final.body_end].strip()
    return_items = _parse_cypher_return_items(return_body, query[: final.return_start])
    if not return_items:
        return None
    order_terms = [item.order_term for item in return_items]
    if final.has_order_by:
        existing_terms = _order_by_expressions_from_body(
            query[final.order_body_start : final.order_body_end]
        )
        missing_terms = _missing_order_terms(existing_terms, order_terms)
        if not missing_terms:
            return None
        updated = (
            query[: final.order_body_end].rstrip()
            + ", "
            + ", ".join(missing_terms)
            + " "
            + query[final.order_body_end :].lstrip()
        )
        return StableCypherQuery(
            query=updated,
            projected_column_count=len(return_items),
            had_order_by=True,
            reason="ordered_paging_tiebreaker",
        )
    updated = (
        query[: final.pagination_start].rstrip()
        + " ORDER BY "
        + ", ".join(order_terms)
        + " "
        + query[final.pagination_start :].lstrip()
    )
    return StableCypherQuery(
        query=updated,
        projected_column_count=len(return_items),
        had_order_by=False,
        reason="unordered_paging",
    )


def _stable_oracle_paging_query(
    query: str,
    projected_column_count: int,
    has_existing_order: bool,
) -> str | None:
    if projected_column_count < 1:
        return None
    stripped = query.rstrip().rstrip(";")
    masked = _mask_string_literals(stripped)
    if re.search(r"\bUNION\b", masked, flags=re.IGNORECASE):
        return None
    pagination_span = _trailing_sql_pagination_span(masked)
    if pagination_span is None:
        return None
    order_terms = ", ".join(str(index) for index in range(1, projected_column_count + 1))
    pagination_start, _ = pagination_span
    if has_existing_order:
        order_span = _final_top_level_sql_order_body_span(masked, pagination_start)
        if order_span is None:
            return None
        _, order_body_end = order_span
        return stripped[:order_body_end].rstrip() + ", " + order_terms + stripped[order_body_end:]
    return (
        stripped[:pagination_start].rstrip()
        + "\nORDER BY "
        + order_terms
        + "\n"
        + stripped[pagination_start:].lstrip()
    )


def _parse_cypher_return_items(
    return_body: str,
    query_before_return: str,
) -> List[CypherReturnItem]:
    body = re.sub(r"^\s*DISTINCT\b", "", return_body, flags=re.IGNORECASE).strip()
    if not body:
        return []
    graph_variables = _graph_variables(query_before_return)
    items: List[CypherReturnItem] = []
    for raw_item in _split_top_level_commas(body):
        expression, alias = _split_cypher_alias(raw_item)
        if not _is_safe_stable_order_expression(expression, graph_variables):
            return []
        order_term = _cypher_identifier(alias) if alias else expression.strip()
        if not order_term or order_term == "*":
            return []
        items.append(
            CypherReturnItem(
                expression=expression.strip(),
                alias=alias,
                order_term=order_term,
            )
        )
    return items


def _split_cypher_alias(item: str) -> tuple[str, str]:
    masked = _mask_string_literals(item)
    matches = list(re.finditer(r"\s+AS\s+", masked, flags=re.IGNORECASE))
    if not matches:
        return item.strip(), ""
    match = matches[-1]
    expression = item[: match.start()].strip()
    alias = _unquote_cypher_identifier(item[match.end() :].strip())
    return expression, alias


def _is_safe_stable_order_expression(expression: str, graph_variables: set[str]) -> bool:
    stripped = expression.strip()
    if not stripped or stripped == "*":
        return False
    if stripped in graph_variables:
        return False
    if re.search(
        r"\b(?:collect|labels|nodes|properties|relationships)\s*\(",
        stripped,
        flags=re.IGNORECASE,
    ):
        return False
    return True


def _graph_variables(query: str) -> set[str]:
    masked = _mask_string_literals(query)
    variables = {
        match.group("variable")
        for match in re.finditer(
            r"\(\s*(?P<variable>[A-Za-z_][A-Za-z0-9_]*)"
            r"(?=\s*(?::|\{|\)|WHERE\b))",
            masked,
            flags=re.IGNORECASE,
        )
    }
    variables.update(
        match.group("variable")
        for match in re.finditer(
            r"\[\s*(?P<variable>[A-Za-z_][A-Za-z0-9_]*)"
            r"(?=\s*(?::|\*|\]|\{))",
            masked,
            flags=re.IGNORECASE,
        )
    )
    variables.update(
        match.group("variable")
        for match in re.finditer(
            r"\b(?:MATCH|OPTIONAL\s+MATCH)\s+(?P<variable>[A-Za-z_][A-Za-z0-9_]*)\s*=",
            masked,
            flags=re.IGNORECASE,
        )
    )
    return variables


def _final_cypher_paging(query: str) -> FinalCypherPaging | None:
    masked = _mask_string_literals(query)
    return_matches = list(re.finditer(r"\bRETURN\b", masked, flags=re.IGNORECASE))
    if not return_matches:
        return None
    return_match = return_matches[-1]
    after_return = masked[return_match.end() :]
    order_match = re.search(r"\bORDER\s+BY\b", after_return, flags=re.IGNORECASE)
    skip_match = re.search(r"\bSKIP\s+\d+\b", after_return, flags=re.IGNORECASE)
    limit_match = re.search(r"\bLIMIT\s+\d+\b", after_return, flags=re.IGNORECASE)
    if skip_match is None and limit_match is None:
        return None
    pagination_offsets = [match.start() for match in (skip_match, limit_match) if match is not None]
    pagination_start = return_match.end() + min(pagination_offsets)
    has_order_by = bool(order_match and return_match.end() + order_match.start() < pagination_start)
    if has_order_by and order_match is not None:
        body_end = return_match.end() + order_match.start()
        order_body_start = return_match.end() + order_match.end()
        order_body_end = pagination_start
    else:
        body_end = pagination_start
        order_body_start = -1
        order_body_end = -1
    return FinalCypherPaging(
        return_start=return_match.start(),
        return_end=return_match.end(),
        body_start=return_match.end(),
        body_end=body_end,
        pagination_start=pagination_start,
        has_order_by=has_order_by,
        order_body_start=order_body_start,
        order_body_end=order_body_end,
        has_limit=limit_match is not None,
        has_skip=skip_match is not None,
    )


def _order_by_expressions_from_body(order_body: str) -> List[str]:
    expressions = []
    for item in _split_top_level_commas(order_body):
        cleaned = re.sub(r"\s+(?:ASC|DESC)\s*$", "", item.strip(), flags=re.IGNORECASE)
        if cleaned:
            expressions.append(cleaned)
    return expressions


def _missing_order_terms(existing_terms: Sequence[str], order_terms: Sequence[str]) -> List[str]:
    existing = {_normalize_order_term(term) for term in existing_terms}
    return [term for term in order_terms if _normalize_order_term(term) not in existing]


def _normalize_order_term(term: str) -> str:
    return re.sub(r"\s+", "", _unquote_cypher_identifier(term.strip())).lower()


def _trailing_sql_pagination_span(masked_sql: str) -> tuple[int, int] | None:
    patterns = [
        r"\s+OFFSET\s+\d+\s+ROWS\s+FETCH\s+FIRST\s+\d+\s+ROWS\s+ONLY\s*$",
        r"\s+FETCH\s+FIRST\s+\d+\s+ROWS\s+ONLY\s*$",
        r"\s+OFFSET\s+\d+\s+ROWS\s*$",
    ]
    for pattern in patterns:
        match = re.search(pattern, masked_sql, flags=re.IGNORECASE)
        if match:
            return match.span()
    return None


def _final_top_level_sql_order_body_span(
    masked_sql: str,
    search_end: int,
) -> tuple[int, int] | None:
    last_match: re.Match | None = None
    for match in re.finditer(r"\bORDER\s+BY\b", masked_sql[:search_end], flags=re.IGNORECASE):
        if _paren_depth_at(masked_sql, match.start()) == 0:
            last_match = match
    if last_match is None:
        return None
    return last_match.end(), search_end


def _paren_depth_at(value: str, position: int) -> int:
    depth = 0
    for char in value[:position]:
        if char == "(":
            depth += 1
        elif char == ")":
            depth = max(depth - 1, 0)
    return depth


def is_nondeterministic_limit_without_order(query: str) -> bool:
    paging = _final_cypher_paging(query)
    return bool(paging and paging.has_limit and not paging.has_order_by)


def is_order_by_limit_query(query: str) -> bool:
    paging = _final_cypher_paging(query)
    return bool(paging and paging.has_limit and paging.has_order_by)


def has_order_by_limit_boundary_tie(
    cypher: str,
    oracle_sqlpgq: str,
    oracle_client: OracleDBClient,
    neo4j_loader: DatasetNeo4jLoader,
    args: argparse.Namespace,
    element_label_aliases: Dict[str, str] | None = None,
) -> bool | None:
    limit = _trailing_cypher_limit(cypher)
    if limit is None or limit < 1:
        return None
    sort_expressions = _order_by_expressions(cypher)
    if not sort_expressions:
        return None
    expanded_cypher = _replace_trailing_cypher_limit(cypher, limit + 1)
    expanded_sql = _replace_trailing_sql_fetch(oracle_sqlpgq, limit + 1)
    if expanded_cypher == cypher or expanded_sql == oracle_sqlpgq:
        return None

    oracle_result = oracle_client.execute_query(
        expanded_sql,
        call_timeout_ms=args.oracle_timeout_ms,
    )
    neo4j_status, neo4j_rows, _ = neo4j_loader.execute(expanded_cypher, args.neo4j_timeout_s)
    if query_status_name(oracle_result.status_code) not in {"success", "no_record"}:
        return None
    if neo4j_status != "success":
        return None
    oracle_rows = oracle_result.data if isinstance(oracle_result.data, list) else []
    oracle_tie = _rows_have_boundary_tie(
        oracle_rows,
        limit,
        sort_expressions,
        element_label_aliases,
    )
    neo4j_tie = _rows_have_boundary_tie(
        neo4j_rows,
        limit,
        sort_expressions,
        element_label_aliases,
    )
    if oracle_tie is True or neo4j_tie is True:
        return True
    if oracle_tie is False and neo4j_tie is False:
        return False
    return None


def _rows_have_boundary_tie(
    rows: Sequence[Dict[str, Any]],
    limit: int,
    sort_expressions: Sequence[str],
    element_label_aliases: Dict[str, str] | None = None,
) -> bool | None:
    if len(rows) <= limit:
        return False
    before = _sort_key_for_row(rows[limit - 1], sort_expressions, element_label_aliases)
    after = _sort_key_for_row(rows[limit], sort_expressions, element_label_aliases)
    if before is None or after is None:
        return None
    return before == after


def _sort_key_for_row(
    row: Dict[str, Any],
    sort_expressions: Sequence[str],
    element_label_aliases: Dict[str, str] | None = None,
) -> tuple[Any, ...] | None:
    values = []
    for expression in sort_expressions:
        value = _row_value_for_sort_expression(row, expression)
        if value is _MISSING:
            return None
        values.append(_normalize_value(value, element_label_aliases=element_label_aliases))
    return tuple(values)


_MISSING = object()


def _row_value_for_sort_expression(row: Dict[str, Any], expression: str) -> Any:
    candidates = _sort_expression_candidates(expression)
    for candidate in candidates:
        if candidate in row:
            return row[candidate]
    lower_by_key = {str(key).lower(): key for key in row}
    for candidate in candidates:
        key = lower_by_key.get(candidate.lower())
        if key is not None:
            return row[key]
    return _MISSING


def _sort_expression_candidates(expression: str) -> List[str]:
    expression = expression.strip()
    expression = re.sub(r"^`(?P<name>.*)`$", r"\g<name>", expression)
    candidates = [expression]
    if "." in expression:
        candidates.append(expression.rsplit(".", 1)[1].strip("`"))
    candidates.append(OracleNameSanitizer.clean(expression, fallback=expression))
    candidates.append(OracleNameSanitizer.alias(expression))
    return list(dict.fromkeys(candidate for candidate in candidates if candidate))


def _order_by_expressions(query: str) -> List[str]:
    masked = _strip_string_literals(query)
    match = re.search(
        r"\bORDER\s+BY\s+(?P<body>.*?)(?:\bSKIP\b|\bLIMIT\b|$)",
        masked,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return []
    expressions = []
    for item in _split_top_level_commas(match.group("body")):
        cleaned = re.sub(r"\s+(?:ASC|DESC)\s*$", "", item.strip(), flags=re.IGNORECASE)
        if cleaned:
            expressions.append(cleaned)
    return expressions


def _split_top_level_commas(value: str) -> List[str]:
    parts = []
    start = 0
    depths = {"(": 0, "[": 0, "{": 0}
    quote = ""
    index = 0
    while index < len(value):
        char = value[index]
        if quote:
            if char == "\\" and quote in {"'", '"'}:
                index += 2
                continue
            if char == quote:
                if index + 1 < len(value) and value[index + 1] == quote:
                    index += 2
                    continue
                quote = ""
            index += 1
            continue
        if char in {"'", '"', "`"}:
            quote = char
        elif char == "(":
            depths["("] += 1
        elif char == ")":
            depths["("] = max(depths["("] - 1, 0)
        elif char == "[":
            depths["["] += 1
        elif char == "]":
            depths["["] = max(depths["["] - 1, 0)
        elif char == "{":
            depths["{"] += 1
        elif char == "}":
            depths["{"] = max(depths["{"] - 1, 0)
        elif char == "," and not any(depths.values()):
            parts.append(value[start:index].strip())
            start = index + 1
        index += 1
    parts.append(value[start:].strip())
    return [part for part in parts if part]


def _trailing_cypher_limit(query: str) -> int | None:
    match = re.search(r"\bLIMIT\s+(?P<limit>\d+)\s*$", query.strip(), flags=re.IGNORECASE)
    return int(match.group("limit")) if match else None


def _replace_trailing_cypher_limit(query: str, limit: int) -> str:
    return re.sub(
        r"\bLIMIT\s+\d+\s*$",
        f"LIMIT {limit}",
        query.strip(),
        count=1,
        flags=re.IGNORECASE,
    )


def _replace_trailing_sql_fetch(query: str, limit: int) -> str:
    return re.sub(
        r"\bFETCH\s+FIRST\s+\d+\s+ROWS\s+ONLY\s*$",
        f"FETCH FIRST {limit} ROWS ONLY",
        query.strip(),
        count=1,
        flags=re.IGNORECASE,
    )


def _strip_string_literals(query: str) -> str:
    return re.sub(r"'(?:''|\\'|[^'])*'|\"(?:\\\"|[^\"])*\"", "''", query or "")


def _mask_string_literals(query: str) -> str:
    if not query:
        return ""
    chars = list(query)
    index = 0
    while index < len(chars):
        char = chars[index]
        if char not in {"'", '"', "`"}:
            index += 1
            continue
        quote = char
        index += 1
        while index < len(chars):
            if chars[index] == "\\" and quote in {"'", '"'}:
                chars[index] = " "
                if index + 1 < len(chars):
                    chars[index + 1] = " "
                index += 2
                continue
            if chars[index] == quote:
                if index + 1 < len(chars) and chars[index + 1] == quote:
                    chars[index] = " "
                    chars[index + 1] = " "
                    index += 2
                    continue
                index += 1
                break
            chars[index] = " "
            index += 1
    return "".join(chars)


def _rewrite_outside_string_literals(value: str, rewrite) -> str:
    parts = []
    start = 0
    index = 0
    while index < len(value):
        char = value[index]
        if char not in ("'", '"'):
            index += 1
            continue
        if start < index:
            parts.append(rewrite(value[start:index]))
        literal_start = index
        quote = char
        index += 1
        while index < len(value):
            if value[index] == "\\":
                index += 2
                continue
            if value[index] == quote:
                if index + 1 < len(value) and value[index + 1] == quote:
                    index += 2
                    continue
                index += 1
                break
            index += 1
        parts.append(value[literal_start:index])
        start = index
    if start < len(value):
        parts.append(rewrite(value[start:]))
    return "".join(parts)


def _cypher_identifier(value: str) -> str:
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        return value
    return f"`{value.replace('`', '``')}`"


def _unquote_cypher_identifier(value: str) -> str:
    stripped = value.strip()
    if stripped.startswith("`") and stripped.endswith("`") and len(stripped) >= 2:
        return stripped[1:-1].replace("``", "`")
    return stripped


def normalized_counter(
    rows: Sequence[Dict[str, Any]],
    primary_by_label: Dict[str, str] | None = None,
    element_label_aliases: Dict[str, str] | None = None,
) -> Counter[str]:
    return Counter(
        json.dumps(row, sort_keys=True, ensure_ascii=False)
        for row in normalize_rows(rows, primary_by_label, element_label_aliases)
    )


def normalized_rows_match_with_numeric_tolerance(
    oracle_rows: Sequence[Dict[str, Any]],
    neo4j_rows: Sequence[Dict[str, Any]],
    primary_by_label: Dict[str, str] | None = None,
    element_label_aliases: Dict[str, str] | None = None,
    absolute_tolerance: float = 1e-4,
    relative_tolerance: float = 1e-8,
) -> bool:
    if len(oracle_rows) != len(neo4j_rows):
        return False
    oracle_normalized = normalize_rows(oracle_rows, primary_by_label, element_label_aliases)
    neo4j_normalized = normalize_rows(neo4j_rows, primary_by_label, element_label_aliases)
    unmatched = list(neo4j_normalized)
    for oracle_row in oracle_normalized:
        match_index = next(
            (
                index
                for index, neo4j_row in enumerate(unmatched)
                if _values_equal_with_numeric_tolerance(
                    oracle_row,
                    neo4j_row,
                    absolute_tolerance,
                    relative_tolerance,
                )
            ),
            -1,
        )
        if match_index == -1:
            return False
        unmatched.pop(match_index)
    return not unmatched


def _values_equal_with_numeric_tolerance(
    left: Any,
    right: Any,
    absolute_tolerance: float,
    relative_tolerance: float,
) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        delta = abs(float(left) - float(right))
        allowed = max(
            absolute_tolerance, relative_tolerance * max(abs(float(left)), abs(float(right)), 1.0)
        )
        return delta <= allowed
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(
            _values_equal_with_numeric_tolerance(
                left_item,
                right_item,
                absolute_tolerance,
                relative_tolerance,
            )
            for left_item, right_item in zip(left, right, strict=True)
        )
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(
            _values_equal_with_numeric_tolerance(
                left[key],
                right[key],
                absolute_tolerance,
                relative_tolerance,
            )
            for key in left
        )
    return left == right


def result_diagnostics(
    oracle_rows: Sequence[Dict[str, Any]],
    neo4j_rows: Sequence[Dict[str, Any]],
    primary_by_label: Dict[str, str] | None = None,
    element_label_aliases: Dict[str, str] | None = None,
    sample_limit: int = 5,
) -> Dict[str, Any]:
    oracle_counter = normalized_counter(
        oracle_rows,
        primary_by_label,
        element_label_aliases,
    )
    neo4j_counter = normalized_counter(
        neo4j_rows,
        primary_by_label,
        element_label_aliases,
    )
    missing_from_neo4j = oracle_counter - neo4j_counter
    extra_in_neo4j = neo4j_counter - oracle_counter
    return {
        "oracle_row_count": len(oracle_rows),
        "neo4j_row_count": len(neo4j_rows),
        "oracle_distinct_row_count": len(oracle_counter),
        "neo4j_distinct_row_count": len(neo4j_counter),
        "missing_from_neo4j_count": sum(missing_from_neo4j.values()),
        "extra_in_neo4j_count": sum(extra_in_neo4j.values()),
        "missing_from_neo4j_sample": _counter_rows_sample(
            missing_from_neo4j,
            sample_limit,
        ),
        "extra_in_neo4j_sample": _counter_rows_sample(extra_in_neo4j, sample_limit),
    }


def _counter_rows_sample(counter: Counter[str], sample_limit: int) -> List[Any]:
    rows: List[Any] = []
    for encoded_row, count in counter.items():
        row = json.loads(encoded_row)
        for _ in range(count):
            rows.append(row)
            if len(rows) >= sample_limit:
                return rows
    return rows


def normalize_rows(
    rows: Sequence[Dict[str, Any]],
    primary_by_label: Dict[str, str] | None = None,
    element_label_aliases: Dict[str, str] | None = None,
) -> List[Any]:
    return [normalize_row(row, primary_by_label, element_label_aliases) for row in rows]


def normalize_row(
    row: Dict[str, Any],
    primary_by_label: Dict[str, str] | None = None,
    element_label_aliases: Dict[str, str] | None = None,
) -> Any:
    # Compare return values rather than aliases: Oracle aliases often differ from Cypher aliases.
    values = list(row.values())
    if len(values) == 1 and _looks_like_path(values[0]):
        return _normalize_path(values[0], primary_by_label, element_label_aliases)
    return [_normalize_value(value, primary_by_label, element_label_aliases) for value in values]


def _normalize_value(
    value: Any,
    primary_by_label: Dict[str, str] | None = None,
    element_label_aliases: Dict[str, str] | None = None,
) -> Any:
    if value is None:
        return None
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else round(float(value), 6)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if value.is_integer():
            return int(value)
        rounded = round(value, 6)
        return int(rounded) if rounded.is_integer() else rounded
    if isinstance(value, timedelta):
        return value.total_seconds()
    if isinstance(value, datetime):
        if value.hour == value.minute == value.second == value.microsecond == 0:
            return value.date().isoformat()
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        return _normalize_temporal_string(value)
    if _looks_like_path(value):
        return _normalize_path(value, primary_by_label, element_label_aliases)
    if isinstance(value, (list, tuple)):
        return [_normalize_value(item, primary_by_label, element_label_aliases) for item in value]
    if isinstance(value, dict):
        oracle_identity = _normalize_oracle_graph_identity(
            value,
            primary_by_label,
            element_label_aliases,
        )
        if oracle_identity is not None:
            return oracle_identity
        return {
            str(key): _normalize_value(item, primary_by_label, element_label_aliases)
            for key, item in sorted(value.items())
        }
    if hasattr(value, "items") and hasattr(value, "labels"):
        return _normalize_neo4j_node(value, primary_by_label, element_label_aliases)
    if hasattr(value, "items") and hasattr(value, "type"):
        return _normalize_neo4j_relationship(
            value,
            primary_by_label,
            element_label_aliases,
        )
    if hasattr(value, "iso_format"):
        return _normalize_temporal_string(str(value.iso_format()))
    if hasattr(value, "isoformat"):
        return _normalize_temporal_string(str(value.isoformat()))
    return value


def _normalize_temporal_string(value: str) -> str:
    match = re.fullmatch(
        r"(?P<date>\d{4}-\d{2}-\d{2})[T ]"
        r"(?P<time>\d{2}:\d{2}:\d{2})"
        r"(?:\.(?P<fraction>\d{1,9}))?"
        r"(?P<zone>Z|[+-]\d{2}:\d{2})?",
        value,
    )
    if match:
        fraction = (match.group("fraction") or "").rstrip("0")
        zone = match.group("zone") or ""
        if zone in ("Z", "+00:00"):
            zone = ""
        if match.group("time") == "00:00:00" and not fraction and not zone:
            return match.group("date")
        base = f"{match.group('date')}T{match.group('time')}"
        return f"{base}{'.' + fraction if fraction else ''}{zone}"
    return value


def _normalize_oracle_graph_identity(
    value: Dict[str, Any],
    primary_by_label: Dict[str, str] | None = None,
    element_label_aliases: Dict[str, str] | None = None,
) -> Dict[str, Any] | None:
    if "ELEM_TABLE" not in value or "KEY_VALUE" not in value:
        return None
    label = _canonical_element_label(str(value["ELEM_TABLE"]), element_label_aliases)
    normalized = {
        "element": label,
    }
    key = _normalize_value(value["KEY_VALUE"], primary_by_label, element_label_aliases)
    if key:
        normalized["key"] = key
    return normalized


def _normalize_neo4j_node(
    value: Any,
    primary_by_label: Dict[str, str] | None = None,
    element_label_aliases: Dict[str, str] | None = None,
) -> Dict[str, Any]:
    labels = sorted(str(label) for label in value.labels)
    label = _canonical_element_label(labels[0] if labels else "", element_label_aliases)
    properties = dict(value.items())
    key = _node_key(label, properties, primary_by_label)
    if key:
        return {
            "element": OracleNameSanitizer.clean(label, fallback=label),
            "key": _normalize_value(key, primary_by_label, element_label_aliases),
        }
    return {
        "element": label,
        "properties": _normalize_value(properties, primary_by_label, element_label_aliases),
    }


def _normalize_neo4j_relationship(
    value: Any,
    primary_by_label: Dict[str, str] | None = None,
    element_label_aliases: Dict[str, str] | None = None,
) -> Dict[str, Any]:
    rel_type = _canonical_element_label(str(value.type), element_label_aliases)
    normalized: Dict[str, Any] = {
        "element": rel_type,
    }
    properties = dict(value.items())
    edge_id = properties.get("EDGE_ID")
    if edge_id is not None:
        normalized["key"] = {"EDGE_ID": _normalize_value(edge_id, primary_by_label)}
        return normalized
    if properties:
        normalized["properties"] = _normalize_value(
            properties,
            primary_by_label,
            element_label_aliases,
        )
    return normalized


def _node_key(
    label: str,
    properties: Dict[str, Any],
    primary_by_label: Dict[str, str] | None = None,
) -> Dict[str, Any]:
    candidates = []
    if primary_by_label:
        candidates.extend(
            [
                primary_by_label.get(label),
                primary_by_label.get(OracleNameSanitizer.clean(label, fallback=label)),
            ]
        )
    candidates.extend(["_id", "vid", "id", f"{label}_id"])
    candidates.extend(sorted(key for key in properties if key.lower().endswith("_id")))
    for candidate in candidates:
        if candidate and candidate in properties:
            return {candidate: properties[candidate]}
    return {}


def _looks_like_path(value: Any) -> bool:
    return hasattr(value, "nodes") and hasattr(value, "relationships")


def _normalize_path(
    value: Any,
    primary_by_label: Dict[str, str] | None = None,
    element_label_aliases: Dict[str, str] | None = None,
) -> List[Any]:
    nodes = list(value.nodes)
    relationships = list(value.relationships)
    normalized = []
    for index, node in enumerate(nodes):
        normalized.append(_normalize_value(node, primary_by_label, element_label_aliases))
        if index < len(relationships):
            normalized.append(
                _normalize_value(
                    relationships[index],
                    primary_by_label,
                    element_label_aliases,
                )
            )
    return normalized


def _canonical_element_label(
    label: str,
    element_label_aliases: Dict[str, str] | None = None,
) -> str:
    cleaned = OracleNameSanitizer.clean(label, fallback=label)
    if not element_label_aliases:
        return cleaned
    return element_label_aliases.get(cleaned, element_label_aliases.get(label, cleaned))


def oracle_element_label_aliases(loader: DatasetOracleLoader) -> Dict[str, str]:
    aliases: Dict[str, str] = {}
    for vertex in loader.manifest.get("vertices", []):
        graph_label = OracleNameSanitizer.clean(
            vertex.get("graph_label", vertex["label"]),
            fallback=vertex["label"],
        )
        source_label = OracleNameSanitizer.clean(vertex["label"], fallback=vertex["label"])
        aliases[graph_label] = source_label
    for edge in loader.manifest.get("edges", []):
        graph_label = OracleNameSanitizer.clean(
            edge.get("graph_label", edge["label"]),
            fallback=edge["label"],
        )
        source_label = OracleNameSanitizer.clean(edge["label"], fallback=edge["label"])
        aliases[graph_label] = source_label
    return aliases


def _convert_value(value: str, type_name: str) -> Any:
    if value == "":
        return None
    normalized = type_name.upper()
    if normalized in ("INT8", "INT16", "INT32", "INT64", "INTEGER"):
        return int(float(value))
    if normalized in ("FLOAT", "DOUBLE", "FLOAT32", "FLOAT64"):
        return float(value)
    if normalized in ("BOOL", "BOOLEAN"):
        return value.strip().lower() in ("true", "1", "yes", "y")
    if normalized == "DATE":
        parsed = _parse_datetime(value)
        return parsed.date() if isinstance(parsed, datetime) else parsed
    if normalized in ("DATETIME", "TIMESTAMP"):
        parsed = _parse_datetime(value)
        if isinstance(parsed, date) and not isinstance(parsed, datetime):
            return datetime.combine(parsed, datetime.min.time())
        return parsed
    return value


def _parse_datetime(value: str) -> date | datetime | str:
    normalized = value.strip()
    try:
        return datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError:
        pass
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%m/%d/%Y %H:%M:%S",
        "%m/%d/%Y",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d",
    ):
        try:
            parsed = datetime.strptime(normalized, fmt)
            if fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d"):
                return parsed.date()
            return parsed
        except ValueError:
            continue
    return normalized


def graph_name_for(unit: DatabaseUnit, prefix: str) -> str:
    return OracleNameSanitizer.clean(
        f"{prefix}_{unit.split}_{unit.database}",
        fallback="T2GQL_GRAPH",
    )


def query_status_name(status: QueryStatus) -> str:
    if status == QueryStatus.SUCCESS:
        return "success"
    if status == QueryStatus.NO_RECORD:
        return "no_record"
    if status == QueryStatus.CLIENT_ERROR:
        return "client_error"
    if status == QueryStatus.SERVER_ERROR:
        return "server_error"
    return str(status)


def increment(mapping: Dict[str, int], key: str) -> None:
    mapping[key] = mapping.get(key, 0) + 1


def merge_compare_summaries(summaries: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    merged: Dict[str, Any] = {
        "databases": 0,
        "considered": 0,
        "matched": 0,
        "failed": 0,
        "skipped": 0,
        "skip_reasons": {},
        "failure_reasons": {},
        "units": [],
    }
    for summary in summaries:
        merged["databases"] += 1
        for key in ("considered", "matched", "failed", "skipped"):
            merged[key] += int(summary.get(key, 0))
        for key, value in summary.get("skip_reasons", {}).items():
            merged["skip_reasons"][key] = merged["skip_reasons"].get(key, 0) + int(value)
        for key, value in summary.get("failure_reasons", {}).items():
            merged["failure_reasons"][key] = merged["failure_reasons"].get(key, 0) + int(value)
        merged["units"].append(summary)
    return merged


def _escape_backticks(value: str) -> str:
    return value.replace("`", "``")


def _safe_identifier(value: str) -> str:
    cleaned = "".join(char if char.isalnum() else "_" for char in value)
    return cleaned[:120] or "constraint_name"


if __name__ == "__main__":
    main()
