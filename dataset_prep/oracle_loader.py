from __future__ import annotations

import csv
from datetime import date, datetime
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List

from app.core.validator.db_client import QueryStatus
from app.impl.oracle_sqlpgq.db_client.oracle_db_client import OracleDBClient
from app.impl.oracle_sqlpgq.schema.schema_parser import OracleSqlPgqSchemaParser
from app.impl.oracle_sqlpgq.utils.sqlpgq import OracleNameSanitizer, split_sql_statements


class DatasetOracleLoader:
    def __init__(
        self,
        client: OracleDBClient,
        import_config_path: Path,
        csv_root: Path,
        graph_name: str,
    ):
        self.client = client
        self.import_config_path = import_config_path
        self.csv_root = csv_root
        self.graph_name = OracleNameSanitizer.clean(graph_name, fallback="GRAPH")
        self.config = json.loads(import_config_path.read_text(encoding="utf-8"))
        self.manifest = self._build_manifest()

    def setup(self) -> Dict[str, int]:
        self.cleanup(ignore_errors=True)
        self._execute_script(self.manifest["table_ddl"])
        counts = self._load_csv_files()
        self._execute_script(self.manifest["property_graph_ddl"])
        return counts

    def node_label_map(self) -> Dict[str, List[str]]:
        return self._label_map(self.manifest["vertices"])

    def edge_label_map(self) -> Dict[str, List[str]]:
        return self._label_map(self.manifest["edges"])

    def property_type_map(self) -> Dict[str, Dict[str, str]]:
        mapping: Dict[str, Dict[str, str]] = {}
        for item in self.manifest["vertices"] + self.manifest["edges"]:
            mapping.setdefault(item["label"], {})
            mapping.setdefault(item.get("graph_label", item["label"]), {})
            for column in item["columns"]:
                mapping[item["label"]][column["name"]] = column["type"]
                mapping[item.get("graph_label", item["label"])][column["name"]] = column["type"]
        return mapping

    def node_primary_key_map(self) -> Dict[str, str]:
        mapping: Dict[str, str] = {}
        for vertex in self.manifest["vertices"]:
            mapping[vertex["label"]] = vertex["primary"]
            mapping[vertex.get("graph_label", vertex["label"])] = vertex["primary"]
        return mapping

    def edge_primary_key_map(self) -> Dict[str, str]:
        mapping: Dict[str, str] = {}
        for edge in self.manifest["edges"]:
            mapping[edge["label"]] = edge["primary"]
            mapping[edge.get("graph_label", edge["label"])] = edge["primary"]
        return mapping

    def cleanup(self, ignore_errors: bool = False) -> None:
        self._execute(
            f"DROP PROPERTY GRAPH {OracleNameSanitizer.quote(self.graph_name)}",
            ignore_errors=ignore_errors,
        )
        for edge in reversed(self.manifest["edges"]):
            self._execute(f"DROP TABLE {edge['quoted_table']} CASCADE CONSTRAINTS PURGE", True)
        for vertex in reversed(self.manifest["vertices"]):
            self._execute(f"DROP TABLE {vertex['quoted_table']} CASCADE CONSTRAINTS PURGE", True)

    def _build_manifest(self) -> Dict[str, Any]:
        parser = OracleSqlPgqSchemaParser(
            db_id=self.graph_name,
            instance_path=str(self.import_config_path),
            enforced=False,
            include_foreign_keys=False,
            promote_mixed_property_types=True,
        )
        return parser.build_manifest(parser.get_schema_graph(), graph_name=self.graph_name)

    def _label_map(self, items: Iterable[Dict[str, Any]]) -> Dict[str, List[str]]:
        mapping: Dict[str, List[str]] = {}
        files_by_label: Dict[str, List[Dict[str, Any]]] = {}
        for file_item in getattr(self, "config", {}).get("files", []):
            files_by_label.setdefault(file_item.get("label", ""), []).append(file_item)
        for item in items:
            graph_label = item.get("graph_label", item["label"])
            mapping.setdefault(item["label"], []).append(graph_label)
            for file_item in files_by_label.get(item["label"], []):
                alias = Path(str(file_item.get("path", ""))).stem
                if alias and alias != item["label"]:
                    mapping.setdefault(alias, []).append(graph_label)
        return mapping

    def _execute_script(self, script: str) -> None:
        for statement in split_sql_statements(script):
            self._execute(statement)

    def _execute(self, sql: str, ignore_errors: bool = False) -> None:
        result = self.client.execute_query(sql)
        if result.status_code == QueryStatus.SUCCESS:
            return
        if ignore_errors and result.error:
            return
        raise RuntimeError(f"Oracle SQL failed:\n{sql}\n\nError:\n{result.error}")

    def _load_csv_files(self) -> Dict[str, int]:
        files = self.config.get("files", [])
        counts: Dict[str, int] = {}
        by_label = {item["label"]: item for item in files if "SRC_ID" not in item}
        for vertex in self.manifest["vertices"]:
            file_item = by_label.get(vertex["label"])
            if file_item:
                counts[vertex["table"]] = self._load_file(vertex, file_item)
        for edge in self.manifest["edges"]:
            file_item = self._find_edge_file(edge, files)
            if file_item:
                counts[edge["table"]] = self._load_file(edge, file_item, is_edge=True)
        return counts

    def _find_edge_file(self, edge: Dict[str, Any], files: Iterable[Dict[str, Any]]):
        same_label_files = []
        for file_item in files:
            if file_item.get("label") != edge["label"]:
                continue
            same_label_files.append(file_item)
            if file_item.get("SRC_ID") == edge["src"] and file_item.get("DST_ID") == edge["dst"]:
                return file_item
        if any("SRC_ID" in item or "DST_ID" in item for item in same_label_files):
            return None
        if same_label_files:
            return same_label_files[0]
        return None

    def _load_file(
        self,
        item: Dict[str, Any],
        file_item: Dict[str, Any],
        is_edge: bool = False,
    ) -> int:
        csv_path = self.csv_root / file_item["path"]
        if not csv_path.exists():
            raise FileNotFoundError(f"CSV file not found: {csv_path}")
        source_columns = list(file_item.get("columns", []))
        target_columns = [column["name"] for column in item["columns"]]
        if is_edge:
            target_columns = [column for column in target_columns if column != "EDGE_ID"]
        insert_columns = [column for column in source_columns if column in target_columns]
        type_by_column = {column["name"]: column["type"] for column in item["columns"]}
        rows = self._read_rows(
            csv_path,
            int(file_item.get("header", 0)),
            source_columns,
            insert_columns,
            type_by_column,
        )
        if not rows:
            return 0
        quoted_columns = ", ".join(OracleNameSanitizer.quote(column) for column in insert_columns)
        binds = ", ".join(f":{index + 1}" for index in range(len(insert_columns)))
        statement = f"INSERT INTO {item['quoted_table']} ({quoted_columns}) VALUES ({binds})"
        result = self.client.executemany(statement, rows)
        if result.status_code != QueryStatus.SUCCESS:
            raise RuntimeError(f"Failed loading {csv_path}: {result.error}")
        return len(rows)

    def _read_rows(
        self,
        csv_path: Path,
        header_rows: int,
        source_columns: List[str],
        insert_columns: List[str],
        type_by_column: Dict[str, str],
    ) -> List[List[Any]]:
        positions = [source_columns.index(column) for column in insert_columns]
        rows: List[List[Any]] = []
        with open(csv_path, newline="", encoding="utf-8-sig") as file:
            reader = csv.reader(file)
            for index, row in enumerate(reader):
                if index < header_rows:
                    continue
                rows.append(
                    [
                        self._convert_value(row[position], type_by_column[insert_columns[item]])
                        for item, position in enumerate(positions)
                    ]
                )
        return rows

    def _convert_value(self, value: str, oracle_type: str) -> Any:
        if value == "":
            return None
        normalized_type = oracle_type.upper()
        if normalized_type.startswith("VARCHAR2("):
            max_length = self._varchar2_length(normalized_type)
            if max_length:
                return self._truncate_utf8(value, max_length)
            return value
        if normalized_type == "NUMBER(1)" and value.lower() in ("true", "false"):
            return 1 if value.lower() == "true" else 0
        if normalized_type.startswith("DATE"):
            parsed = self._parse_datetime(value)
            return parsed.date() if isinstance(parsed, datetime) else parsed
        if normalized_type.startswith("TIMESTAMP"):
            parsed = self._parse_datetime(value)
            if isinstance(parsed, date) and not isinstance(parsed, datetime):
                return datetime.combine(parsed, datetime.min.time())
            return parsed
        return value

    def _varchar2_length(self, oracle_type: str) -> int:
        if not oracle_type.startswith("VARCHAR2("):
            return 0
        length = oracle_type.removeprefix("VARCHAR2(").split(")", 1)[0]
        return int(length) if length.isdigit() else 0

    def _truncate_utf8(self, value: str, max_bytes: int) -> str:
        encoded = value.encode("utf-8")
        if len(encoded) <= max_bytes:
            return value
        return encoded[:max_bytes].decode("utf-8", errors="ignore")

    def _parse_datetime(self, value: str) -> date | datetime:
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
