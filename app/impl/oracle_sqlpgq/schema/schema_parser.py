import json
from pathlib import Path
from typing import Any, Dict, List

from app.core.schema.edge import Edge
from app.core.schema.node import Node
from app.core.schema.schema_graph import SchemaGraph
from app.core.schema.schema_parser import SchemaParser
from app.impl.oracle_sqlpgq.utils.sqlpgq import (
    OracleNameSanitizer,
    OracleTypeMapper,
    property_list,
)


class OracleSqlPgqSchemaParser(SchemaParser):
    """Parse and emit Oracle SQL Property Graph artifacts.

    Oracle SQL property graphs are metadata over relational vertex and edge
    tables. This adapter therefore emits table DDL first, then a
    CREATE PROPERTY GRAPH statement over those tables.
    """

    def __init__(
        self,
        db_id: str = "",
        instance_path: str = "",
        enforced: bool = True,
        include_foreign_keys: bool = True,
        promote_mixed_property_types: bool = False,
    ):
        self.db_id = db_id or "graph"
        self.instance_path = Path(instance_path) if instance_path else None
        self.enforced = enforced
        self.include_foreign_keys = include_foreign_keys
        self.promote_mixed_property_types = promote_mixed_property_types
        self.schema_graph = SchemaGraph(self.db_id)
        self._raw_config: Dict[str, Any] | List[Dict[str, Any]] | None = None
        if self.instance_path:
            self._load()

    def _load(self) -> None:
        path = self.instance_path
        if path is None:
            return
        candidates = []
        if path.is_file():
            candidates.append(path)
        else:
            candidates.extend(
                [
                    path / "oracle_schema.json",
                    path / "schema.json",
                    path / "import_config.json",
                    path / "example_schema.json",
                ]
            )
        for candidate in candidates:
            if candidate.exists():
                with open(candidate, encoding="utf-8") as file:
                    self._raw_config = json.load(file)
                self.schema_graph = self._schema_graph_from_json(self._raw_config)
                return
        print(f"[ERROR] Oracle SQL/PGQ schema file not found under {path}")

    def _schema_graph_from_json(self, data: Dict[str, Any] | List[Dict[str, Any]]) -> SchemaGraph:
        graph = SchemaGraph(self.db_id)
        schema_items = data.get("schema", []) if isinstance(data, dict) else data
        for item in schema_items:
            if item.get("type") == "VERTEX":
                graph.add_node(
                    Node(
                        label=item["label"],
                        properties=item.get("properties", []),
                        primary=item.get("primary", "id"),
                    )
                )
        for item in schema_items:
            if item.get("type") == "EDGE":
                constraints = item.get("constraints", [])
                graph.add_edge(
                    Edge(
                        label=item["label"],
                        properties=item.get("properties", []),
                        src_dst_list=[list(pair) for pair in constraints],
                    )
                )
        return graph

    def get_schema_graph(self) -> SchemaGraph:
        return self.schema_graph

    def save_schema_to_file(
        self, output_dir, schema_graph: SchemaGraph, domain: str, subdomain: str
    ):
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        base_name = f"{domain.replace(' ', '_')}_{subdomain.replace(' ', '_')}".strip("_")
        if not base_name:
            base_name = schema_graph.db_id or "oracle_graph"
        graph_name = OracleNameSanitizer.clean(base_name, fallback="GRAPH")

        manifest = self.build_manifest(schema_graph, graph_name)

        manifest_path = output_dir / f"{base_name}_oracle_schema.json"
        table_ddl_path = output_dir / f"{base_name}_oracle_tables.sql"
        graph_ddl_path = output_dir / f"{base_name}_oracle_property_graph.sql"
        loader_path = output_dir / f"{base_name}_oracle_loader.py"

        with open(manifest_path, "w", encoding="utf-8") as file:
            json.dump(manifest, file, indent=2, ensure_ascii=False)
        table_ddl_path.write_text(manifest["table_ddl"], encoding="utf-8")
        graph_ddl_path.write_text(manifest["property_graph_ddl"], encoding="utf-8")
        loader_path.write_text(self._loader_template(manifest), encoding="utf-8")

        return str(manifest_path)

    def build_manifest(self, schema_graph: SchemaGraph, graph_name: str | None = None) -> Dict:
        graph_name = graph_name or OracleNameSanitizer.clean(schema_graph.db_id, fallback="GRAPH")
        vertex_meta = self._vertex_metadata(schema_graph)
        edge_meta = self._edge_metadata(schema_graph, vertex_meta)
        self._assign_unique_graph_labels(vertex_meta, edge_meta)
        if self.promote_mixed_property_types:
            self._promote_mixed_property_types(vertex_meta, edge_meta)
        table_ddl = self._build_table_ddl(vertex_meta, edge_meta)
        property_graph_ddl = self._build_property_graph_ddl(graph_name, vertex_meta, edge_meta)
        return {
            "backend": "oracle_sqlpgq",
            "graph_name": graph_name,
            "schema": self._schema_json(schema_graph),
            "vertices": vertex_meta,
            "edges": edge_meta,
            "table_ddl": table_ddl,
            "property_graph_ddl": property_graph_ddl,
            "load_order": [item["table"] for item in vertex_meta]
            + [item["table"] for item in edge_meta],
        }

    def _schema_json(self, schema_graph: SchemaGraph) -> List[Dict[str, Any]]:
        schema_data: List[Dict[str, Any]] = []
        for label, node in schema_graph.node_dict.items():
            schema_data.append(
                {
                    "type": "VERTEX",
                    "label": label,
                    "properties": node.properties,
                    "primary": node.primary,
                }
            )
        for label, edge in schema_graph.edge_dict.items():
            schema_data.append(
                {
                    "type": "EDGE",
                    "label": label,
                    "properties": edge.properties,
                    "constraints": edge.src_dst_list,
                }
            )
        return schema_data

    def _vertex_metadata(self, schema_graph: SchemaGraph) -> List[Dict[str, Any]]:
        vertices = []
        for label, node in schema_graph.node_dict.items():
            columns = []
            pk = node.primary or "id"
            has_pk = False
            for prop_name, prop_type in property_list(node.properties):
                if prop_name == pk:
                    has_pk = True
                columns.append(
                    {
                        "name": prop_name,
                        "quoted": OracleNameSanitizer.quote(prop_name, fallback="COL"),
                        "type": OracleTypeMapper.to_oracle(prop_type),
                        "nullable": prop_name != pk,
                    }
                )
            if not has_pk:
                columns.insert(
                    0,
                    {
                        "name": pk,
                        "quoted": OracleNameSanitizer.quote(pk, fallback="ID"),
                        "type": "VARCHAR2(4000)",
                        "nullable": False,
                    },
                )
            vertices.append(
                {
                        "label": label,
                        "graph_label": label,
                        "table": OracleNameSanitizer.clean(label, fallback="VERTEX"),
                        "quoted_table": OracleNameSanitizer.quote(label, fallback="VERTEX"),
                        "quoted_label": OracleNameSanitizer.quote(label, fallback="VERTEX"),
                    "primary": pk,
                    "quoted_primary": OracleNameSanitizer.quote(pk, fallback="ID"),
                    "columns": columns,
                }
            )
        return vertices

    def _edge_metadata(
        self, schema_graph: SchemaGraph, vertex_meta: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        vertex_by_label = {item["label"]: item for item in vertex_meta}
        edges = []
        for label, edge in schema_graph.edge_dict.items():
            for src, dst in edge.src_dst_list:
                src_meta = vertex_by_label.get(src)
                dst_meta = vertex_by_label.get(dst)
                if src_meta is None or dst_meta is None:
                    continue
                table_name = OracleNameSanitizer.clean(f"{src}_{label}_{dst}", fallback="EDGE")
                columns = [
                    {
                        "name": "EDGE_ID",
                        "quoted": OracleNameSanitizer.quote("EDGE_ID"),
                        "type": "NUMBER GENERATED BY DEFAULT AS IDENTITY",
                        "nullable": False,
                    },
                    {
                        "name": "SRC_ID",
                        "quoted": OracleNameSanitizer.quote("SRC_ID"),
                        "type": self._primary_type(src_meta),
                        "nullable": False,
                    },
                    {
                        "name": "DST_ID",
                        "quoted": OracleNameSanitizer.quote("DST_ID"),
                        "type": self._primary_type(dst_meta),
                        "nullable": False,
                    },
                ]
                for prop_name, prop_type in property_list(edge.properties):
                    columns.append(
                        {
                            "name": prop_name,
                            "quoted": OracleNameSanitizer.quote(prop_name, fallback="COL"),
                            "type": OracleTypeMapper.to_oracle(prop_type),
                            "nullable": True,
                        }
                    )
                edges.append(
                    {
                        "label": label,
                        "graph_label": label,
                        "table": table_name,
                        "quoted_table": OracleNameSanitizer.quote(table_name, fallback="EDGE"),
                        "quoted_label": OracleNameSanitizer.quote(label, fallback="EDGE"),
                        "primary": "EDGE_ID",
                        "quoted_primary": OracleNameSanitizer.quote("EDGE_ID"),
                        "src": src,
                        "dst": dst,
                        "src_table": src_meta["quoted_table"],
                        "dst_table": dst_meta["quoted_table"],
                        "src_pk": src_meta["quoted_primary"],
                        "dst_pk": dst_meta["quoted_primary"],
                        "columns": columns,
                    }
                )
        return edges

    def _assign_unique_graph_labels(
        self,
        vertex_meta: List[Dict[str, Any]],
        edge_meta: List[Dict[str, Any]],
    ) -> None:
        used_labels = set()
        for vertex in vertex_meta:
            graph_label = self._unique_label(vertex["label"], used_labels)
            vertex["graph_label"] = graph_label
            vertex["quoted_label"] = OracleNameSanitizer.quote(graph_label, fallback="VERTEX")
        for edge in edge_meta:
            graph_label = self._unique_label(edge["table"], used_labels)
            edge["graph_label"] = graph_label
            edge["quoted_label"] = OracleNameSanitizer.quote(graph_label, fallback="EDGE")

    def _unique_label(self, preferred: str, used_labels: set[str]) -> str:
        base = OracleNameSanitizer.clean(preferred, fallback="LABEL")
        candidate = base
        suffix = 1
        while candidate.upper() in used_labels:
            suffix += 1
            max_base_len = 128 - len(f"_{suffix}")
            candidate = f"{base[:max_base_len]}_{suffix}"
        used_labels.add(candidate.upper())
        return candidate

    def _primary_type(self, vertex_meta: Dict[str, Any]) -> str:
        for column in vertex_meta["columns"]:
            if column["name"] == vertex_meta["primary"]:
                return column["type"]
        return "VARCHAR2(4000)"

    def _build_table_ddl(
        self, vertex_meta: List[Dict[str, Any]], edge_meta: List[Dict[str, Any]]
    ) -> str:
        statements = []
        for vertex in vertex_meta:
            statements.append(self._create_table(vertex))
        for edge in edge_meta:
            statements.append(self._create_table(edge, is_edge=True))
        return "\n\n".join(statements) + "\n"

    def _create_table(self, item: Dict[str, Any], is_edge: bool = False) -> str:
        lines = []
        for column in item["columns"]:
            nullable = " NOT NULL" if not column["nullable"] else ""
            lines.append(f"  {column['quoted']} {column['type']}{nullable}")
        constraint_name = OracleNameSanitizer.quote(f"{item['table']}_PK", fallback="PK")
        lines.append(f"  CONSTRAINT {constraint_name} PRIMARY KEY ({item['quoted_primary']})")
        if is_edge and self.include_foreign_keys:
            src_fk = OracleNameSanitizer.quote(f"{item['table']}_SRC_FK", fallback="SRC_FK")
            dst_fk = OracleNameSanitizer.quote(f"{item['table']}_DST_FK", fallback="DST_FK")
            lines.append(
                f"  CONSTRAINT {src_fk} FOREIGN KEY ({OracleNameSanitizer.quote('SRC_ID')}) "
                f"REFERENCES {item['src_table']} ({item['src_pk']})"
            )
            lines.append(
                f"  CONSTRAINT {dst_fk} FOREIGN KEY ({OracleNameSanitizer.quote('DST_ID')}) "
                f"REFERENCES {item['dst_table']} ({item['dst_pk']})"
            )
        return f"CREATE TABLE {item['quoted_table']} (\n" + ",\n".join(lines) + "\n);"

    def _build_property_graph_ddl(
        self, graph_name: str, vertex_meta: List[Dict[str, Any]], edge_meta: List[Dict[str, Any]]
    ) -> str:
        vertex_defs = []
        for vertex in vertex_meta:
            props = self._properties_clause(vertex, exclude=set())
            vertex_defs.append(
                f"    {vertex['quoted_table']}\n"
                f"      KEY ({vertex['quoted_primary']})\n"
                f"      LABEL {vertex['quoted_label']}{props}"
            )
        edge_defs = []
        for edge in edge_meta:
            props = self._properties_clause(edge, exclude={"EDGE_ID", "SRC_ID", "DST_ID"})
            edge_defs.append(
                f"    {edge['quoted_table']}\n"
                f"      KEY ({edge['quoted_primary']})\n"
                f"      SOURCE KEY ({OracleNameSanitizer.quote('SRC_ID')}) "
                f"REFERENCES {edge['src_table']} ({edge['src_pk']})\n"
                f"      DESTINATION KEY ({OracleNameSanitizer.quote('DST_ID')}) "
                f"REFERENCES {edge['dst_table']} ({edge['dst_pk']})\n"
                f"      LABEL {edge['quoted_label']}{props}"
            )
        enforced = "\n  OPTIONS (ENFORCED MODE)" if self.enforced else ""
        quoted_graph = OracleNameSanitizer.quote(graph_name, fallback="GRAPH")
        return (
            f"CREATE OR REPLACE PROPERTY GRAPH {quoted_graph}\n"
            "  VERTEX TABLES (\n"
            + ",\n".join(vertex_defs)
            + "\n  )\n"
            "  EDGE TABLES (\n"
            + ",\n".join(edge_defs)
            + "\n  )"
            + enforced
            + ";\n"
        )

    def _properties_clause(self, item: Dict[str, Any], exclude: set[str]) -> str:
        columns = [column["quoted"] for column in item["columns"] if column["name"] not in exclude]
        if not columns:
            return ""
        return "\n      PROPERTIES (" + ", ".join(columns) + ")"

    def _promote_mixed_property_types(
        self,
        vertex_meta: List[Dict[str, Any]],
        edge_meta: List[Dict[str, Any]],
    ) -> None:
        structural = {"EDGE_ID", "SRC_ID", "DST_ID"}
        by_name: Dict[str, set[str]] = {}
        for item in vertex_meta + edge_meta:
            for column in item["columns"]:
                if column["name"] in structural:
                    continue
                by_name.setdefault(column["name"], set()).add(column["type"].upper())

        mixed_names = {name for name, types in by_name.items() if len(types) > 1}
        if not mixed_names:
            return
        for item in vertex_meta + edge_meta:
            for column in item["columns"]:
                if column["name"] in mixed_names:
                    column["type"] = "VARCHAR2(4000)"

    def _loader_template(self, manifest: Dict[str, Any]) -> str:
        compact = json.dumps(
            {
                "load_order": manifest["load_order"],
                "vertices": manifest["vertices"],
                "edges": manifest["edges"],
            },
            indent=2,
            ensure_ascii=False,
        )
        return f'''"""CSV loader template for Oracle SQL/PGQ artifacts.

Set ORACLE_DSN, ORACLE_USER, ORACLE_PASSWORD and place CSV files next to this script.
CSV filenames are expected to match table names with .csv suffix.
"""

import csv
import os
from pathlib import Path

import oracledb


MANIFEST = {compact}


def main():
    connection = oracledb.connect(
        user=os.environ["ORACLE_USER"],
        password=os.environ["ORACLE_PASSWORD"],
        dsn=os.environ["ORACLE_DSN"],
    )
    connection.autocommit = False
    root = Path(__file__).resolve().parent
    with connection.cursor() as cursor:
        for table_name in MANIFEST["load_order"]:
            csv_path = root / f"{{table_name}}.csv"
            if not csv_path.exists():
                print(f"Skipping missing {{csv_path}}")
                continue
            with open(csv_path, newline="", encoding="utf-8") as file:
                reader = csv.DictReader(file)
                rows = list(reader)
            if not rows:
                continue
            columns = list(rows[0].keys())
            column_sql = ", ".join(f'"{{column}}"' for column in columns)
            bind_sql = ", ".join(f":{{index + 1}}" for index in range(len(columns)))
            sql = f'INSERT INTO "{{table_name}}" ({{column_sql}}) VALUES ({{bind_sql}})'
            cursor.executemany(sql, [[row.get(column) for column in columns] for row in rows])
            print(f"Loaded {{len(rows)}} rows into {{table_name}}")
    connection.commit()
    connection.close()


if __name__ == "__main__":
    main()
'''
