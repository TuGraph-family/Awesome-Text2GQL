import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from app.impl.oracle_sqlpgq.utils.sqlpgq import OracleNameSanitizer, validate_graph_table_query


INTERNAL_EDGE_COLUMNS = {"EDGE_ID", "SRC_ID", "DST_ID"}
TEXT_TYPES = {"STRING", "TEXT", "VARCHAR2"}
NUMERIC_TYPES = {
    "BOOL",
    "BOOLEAN",
    "INT8",
    "INT16",
    "INT32",
    "INT64",
    "INTEGER",
    "LONG",
    "FLOAT",
    "DOUBLE",
    "NUMBER",
}


@dataclass(frozen=True)
class OracleTemplateCorpusPair:
    question: str
    query: str
    template_id: str
    category: str
    labels: list[str]

    def to_dict(self, include_metadata: bool = True) -> dict[str, Any]:
        item: dict[str, Any] = {"question": self.question, "query": self.query}
        if include_metadata:
            item.update(
                {
                    "template_id": self.template_id,
                    "category": self.category,
                    "labels": self.labels,
                }
            )
        return item


class OracleSqlPgqTemplateInstantiator:
    """Instantiate deterministic Oracle SQL/PGQ corpus templates from a manifest.

    The manifest is the JSON emitted by OracleSqlPgqSchemaParser. The generated
    queries intentionally avoid literal predicates, so they are schema-driven and
    can be validated against any graph instance created from the manifest.
    """

    def __init__(self, manifest: dict[str, Any], graph_name: str | None = None):
        self.manifest = manifest
        self.graph_name = graph_name or manifest.get("graph_name") or "GRAPH"
        self.vertices = list(manifest.get("vertices") or [])
        self.edges = list(manifest.get("edges") or [])
        self.vertex_by_label = {vertex["label"]: vertex for vertex in self.vertices}

    @classmethod
    def from_file(
        cls, manifest_path: str | Path, graph_name: str | None = None
    ) -> "OracleSqlPgqTemplateInstantiator":
        with open(manifest_path, encoding="utf-8") as file:
            manifest = json.load(file)
        return cls(manifest, graph_name=graph_name)

    def generate(self, target_size: int | None = None) -> list[OracleTemplateCorpusPair]:
        pairs: list[OracleTemplateCorpusPair] = []
        pairs.extend(self._one_hop_templates())
        pairs.extend(self._edge_identity_templates())
        pairs.extend(self._aggregate_templates())
        pairs.extend(self._two_hop_templates())
        pairs.extend(self._bounded_path_templates())

        valid_pairs = [pair for pair in pairs if validate_graph_table_query(pair.query)]
        if target_size is not None:
            return valid_pairs[:target_size]
        return valid_pairs

    def generate_dicts(
        self, target_size: int | None = None, include_metadata: bool = True
    ) -> list[dict[str, Any]]:
        return [
            pair.to_dict(include_metadata=include_metadata)
            for pair in self.generate(target_size=target_size)
        ]

    def _one_hop_templates(self) -> list[OracleTemplateCorpusPair]:
        pairs = []
        for index, edge in enumerate(self.edges, start=1):
            src = self.vertex_by_label.get(edge["src"])
            dst = self.vertex_by_label.get(edge["dst"])
            if src is None or dst is None:
                continue

            src_prop = self._display_property(src)
            dst_prop = self._display_property(dst)
            edge_prop = self._display_property(edge, exclude=INTERNAL_EDGE_COLUMNS)
            columns = [
                self._property_column("src", src_prop, f"source_{edge['src']}_{src_prop['name']}"),
                self._property_column("dst", dst_prop, f"target_{edge['dst']}_{dst_prop['name']}"),
            ]
            if edge_prop is not None:
                columns.append(
                    self._property_column("rel", edge_prop, f"{edge['label']}_{edge_prop['name']}")
                )
            query = self._graph_table_query(
                match=(
                    f'(src IS {self._q(edge["src"])})'
                    f'-[rel IS {self._q(edge["label"])}]->'
                    f'(dst IS {self._q(edge["dst"])})'
                ),
                columns=columns,
                suffix="FETCH FIRST 20 ROWS ONLY",
            )
            pairs.append(
                OracleTemplateCorpusPair(
                    question=(
                        f"Show sample {edge['src']} to {edge['dst']} relationships "
                        f"through {edge['label']}."
                    ),
                    query=query,
                    template_id=f"one_hop_{index}",
                    category="one_hop_traversal",
                    labels=[edge["src"], edge["label"], edge["dst"]],
                )
            )
        return pairs

    def _edge_identity_templates(self) -> list[OracleTemplateCorpusPair]:
        pairs = []
        for index, edge in enumerate(self.edges, start=1):
            query = self._graph_table_query(
                match=(
                    f'(src IS {self._q(edge["src"])})'
                    f'-[rel IS {self._q(edge["label"])}]->'
                    f'(dst IS {self._q(edge["dst"])})'
                ),
                columns=[
                    "VERTEX_ID(src) AS source_vertex_id",
                    "EDGE_ID(rel) AS edge_id",
                    "VERTEX_ID(dst) AS target_vertex_id",
                ],
                suffix="FETCH FIRST 20 ROWS ONLY",
            )
            pairs.append(
                OracleTemplateCorpusPair(
                    question=(
                        f"List graph element identifiers for {edge['label']} edges "
                        f"from {edge['src']} to {edge['dst']}."
                    ),
                    query=query,
                    template_id=f"edge_identity_{index}",
                    category="element_identity",
                    labels=[edge["src"], edge["label"], edge["dst"]],
                )
            )
        return pairs

    def _aggregate_templates(self) -> list[OracleTemplateCorpusPair]:
        pairs = []
        for index, edge in enumerate(self.edges, start=1):
            dst = self.vertex_by_label.get(edge["dst"])
            if dst is None:
                continue
            dst_prop = self._display_property(dst)
            alias = self._alias(f"{edge['dst']}_{dst_prop['name']}")
            query = self._graph_table_query(
                match=(
                    f'(src IS {self._q(edge["src"])})'
                    f'-[rel IS {self._q(edge["label"])}]->'
                    f'(dst IS {self._q(edge["dst"])})'
                ),
                columns=[
                    self._property_column("dst", dst_prop, alias),
                    "EDGE_ID(rel) AS edge_id",
                ],
                select_prefix=f"SELECT gt.{alias}, COUNT(gt.edge_id) AS relationship_count",
                group_order_suffix=(
                    f"GROUP BY gt.{alias} "
                    f"ORDER BY relationship_count DESC, gt.{alias} "
                    "FETCH FIRST 20 ROWS ONLY"
                ),
            )
            pairs.append(
                OracleTemplateCorpusPair(
                    question=(
                        f"Count {edge['label']} relationships grouped by each "
                        f"{edge['dst']} {dst_prop['name']}."
                    ),
                    query=query,
                    template_id=f"aggregate_by_target_{index}",
                    category="aggregation",
                    labels=[edge["src"], edge["label"], edge["dst"]],
                )
            )
        return pairs

    def _two_hop_templates(self) -> list[OracleTemplateCorpusPair]:
        pairs = []
        edge_pairs = []
        for first in self.edges:
            for second in self.edges:
                if first["dst"] == second["src"]:
                    edge_pairs.append((first, second))

        for index, (first, second) in enumerate(edge_pairs, start=1):
            start = self.vertex_by_label.get(first["src"])
            end = self.vertex_by_label.get(second["dst"])
            if start is None or end is None:
                continue
            start_prop = self._display_property(start)
            end_prop = self._display_property(end)
            query = self._graph_table_query(
                match=(
                    f'(start_node IS {self._q(first["src"])})'
                    f'-[first_edge IS {self._q(first["label"])}]->'
                    f'(middle_node IS {self._q(first["dst"])})'
                    f'-[second_edge IS {self._q(second["label"])}]->'
                    f'(end_node IS {self._q(second["dst"])})'
                ),
                columns=[
                    self._property_column(
                        "start_node", start_prop, f"start_{first['src']}_{start_prop['name']}"
                    ),
                    self._property_column(
                        "end_node", end_prop, f"end_{second['dst']}_{end_prop['name']}"
                    ),
                ],
                suffix="FETCH FIRST 20 ROWS ONLY",
            )
            pairs.append(
                OracleTemplateCorpusPair(
                    question=(
                        f"Show two-hop paths from {first['src']} through "
                        f"{first['label']} and {second['label']} to {second['dst']}."
                    ),
                    query=query,
                    template_id=f"two_hop_{index}",
                    category="two_hop_traversal",
                    labels=[
                        first["src"],
                        first["label"],
                        first["dst"],
                        second["label"],
                        second["dst"],
                    ],
                )
            )
        return pairs

    def _bounded_path_templates(self) -> list[OracleTemplateCorpusPair]:
        pairs = []
        recursive_edges = [edge for edge in self.edges if edge["src"] == edge["dst"]]
        for index, edge in enumerate(recursive_edges, start=1):
            vertex = self.vertex_by_label.get(edge["src"])
            if vertex is None:
                continue
            vertex_prop = self._display_property(vertex)
            query = self._graph_table_query(
                match=(
                    f'(start_node IS {self._q(edge["src"])})'
                    f'-[path_edge IS {self._q(edge["label"])}]->{{1,3}}'
                    f'(end_node IS {self._q(edge["dst"])})'
                ),
                columns=[
                    "MATCHNUM() AS match_number",
                    "VERTEX_ID(start_node) AS source_vertex_id",
                    "VERTEX_ID(end_node) AS target_vertex_id",
                    self._property_column(
                        "end_node", vertex_prop, f"{edge['dst']}_{vertex_prop['name']}"
                    ),
                ],
                suffix="FETCH FIRST 20 ROWS ONLY",
            )
            pairs.append(
                OracleTemplateCorpusPair(
                    question=(
                        f"Find {edge['dst']} vertices reachable through one to three "
                        f"{edge['label']} hops."
                    ),
                    query=query,
                    template_id=f"bounded_path_{index}",
                    category="bounded_path",
                    labels=[edge["src"], edge["label"], edge["dst"]],
                )
            )
        return pairs

    def _graph_table_query(
        self,
        *,
        match: str,
        columns: Iterable[str],
        suffix: str = "",
        select_prefix: str = "SELECT *",
        group_order_suffix: str = "",
    ) -> str:
        query = (
            f"{select_prefix} FROM GRAPH_TABLE ("
            f"{self._q(self.graph_name)} MATCH {match} "
            f"COLUMNS ({', '.join(columns)})) gt"
        )
        if group_order_suffix:
            return f"{query} {group_order_suffix}"
        if suffix:
            return f"{query} {suffix}"
        return query

    def _display_property(
        self, item: dict[str, Any], exclude: set[str] | None = None
    ) -> dict[str, Any]:
        exclude = exclude or set()
        properties = [
            column
            for column in item.get("columns") or []
            if column.get("name") not in exclude
        ]
        if not properties:
            raise ValueError(f"No display properties found for {item.get('label')}")

        for prop in properties:
            if self._type_family(prop) in TEXT_TYPES:
                return prop
        for prop in properties:
            if self._type_family(prop) in NUMERIC_TYPES:
                return prop
        return properties[0]

    def _property_column(self, variable: str, prop: dict[str, Any], alias: str) -> str:
        return f"{variable}.{self._q(prop['name'])} AS {self._alias(alias)}"

    def _type_family(self, prop: dict[str, Any]) -> str:
        return str(prop.get("type", "")).split("(", 1)[0].upper()

    def _q(self, name: str) -> str:
        return OracleNameSanitizer.quote(name)

    def _alias(self, name: str) -> str:
        return OracleNameSanitizer.alias(name)
