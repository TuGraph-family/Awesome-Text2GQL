import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.clauses.clause import Clause
from app.core.clauses.match_clause import EdgePattern, MatchClause, NodePattern, PathPattern
from app.core.clauses.return_clause import ReturnBody, ReturnClause, ReturnItem
from app.impl.oracle_sqlpgq.translator.oracle_sqlpgq_query_translator import (
    OracleSqlPgqQueryTranslator,
)


@dataclass(frozen=True)
class OracleGeneralizedQuery:
    query: str
    source_pattern_length: int
    labels: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "source_pattern_length": self.source_pattern_length,
            "labels": self.labels,
        }


class OracleSqlPgqQueryGeneralizer:
    """Generalize Graph-IL path patterns over an Oracle SQL/PGQ manifest."""

    def __init__(self, manifest: dict[str, Any], graph_name: str | None = None):
        self.manifest = manifest
        self.graph_name = graph_name or manifest.get("graph_name") or "GRAPH"
        self.vertices = list(manifest.get("vertices") or [])
        self.edges = list(manifest.get("edges") or [])
        self.vertex_by_label = {vertex["label"]: vertex for vertex in self.vertices}
        self.translator = OracleSqlPgqQueryTranslator(graph_name=self.graph_name)

    @classmethod
    def from_file(
        cls, manifest_path: str | Path, graph_name: str | None = None
    ) -> "OracleSqlPgqQueryGeneralizer":
        with open(manifest_path, encoding="utf-8") as file:
            manifest = json.load(file)
        return cls(manifest, graph_name=graph_name)

    def generalize(
        self, query_pattern: list[Clause], target_size: int | None = None
    ) -> list[OracleGeneralizedQuery]:
        path_length = self._path_length(query_pattern)
        if path_length <= 0:
            return []

        generalized = []
        for label_path in self._schema_paths(path_length):
            graph_il = self._build_query_pattern(label_path, query_pattern)
            generalized.append(
                OracleGeneralizedQuery(
                    query=self.translator.translate(graph_il),
                    source_pattern_length=path_length,
                    labels=label_path,
                )
            )
            if target_size is not None and len(generalized) >= target_size:
                break
        return generalized

    def generalize_dicts(
        self, query_pattern: list[Clause], target_size: int | None = None
    ) -> list[dict[str, Any]]:
        return [item.to_dict() for item in self.generalize(query_pattern, target_size)]

    def _path_length(self, query_pattern: list[Clause]) -> int:
        for clause in query_pattern:
            if isinstance(clause, MatchClause):
                path_pattern = clause.path_pattern
                if isinstance(path_pattern, list):
                    path_pattern = path_pattern[0]
                return len(path_pattern.edge_pattern_list)
        return 0

    def _schema_paths(self, path_length: int) -> list[list[str]]:
        paths = []

        def walk(current_label: str, remaining: int, labels: list[str]) -> None:
            if remaining == 0:
                paths.append(labels)
                return
            for edge in self.edges:
                if edge["src"] != current_label:
                    continue
                walk(edge["dst"], remaining - 1, labels + [edge["label"], edge["dst"]])

        for vertex in self.vertices:
            walk(vertex["label"], path_length, [vertex["label"]])
        return paths

    def _build_query_pattern(
        self, label_path: list[str], source_pattern: list[Clause]
    ) -> list[Clause]:
        source_hops = self._source_hop_ranges(source_pattern)
        nodes = []
        edges = []
        for index in range(0, len(label_path), 2):
            nodes.append(NodePattern(f"n{len(nodes) + 1}", label_path[index], []))
        for index in range(1, len(label_path), 2):
            edge_number = len(edges) + 1
            hop_range = source_hops[edge_number - 1] if edge_number <= len(source_hops) else (-1, -1)
            edges.append(
                EdgePattern(
                    symbolic_name=f"e{edge_number}",
                    label=label_path[index],
                    property_maps=[],
                    direction="right",
                    hop_range=hop_range,
                )
            )

        final_node = nodes[-1]
        final_property = self._display_property(final_node.label)
        return [
            MatchClause(PathPattern(nodes, edges)),
            ReturnClause(
                ReturnBody(
                    return_item_list=[
                        ReturnItem(
                            symbolic_name=final_node.symbolic_name,
                            property=final_property,
                            alias=f"{final_node.label}_{final_property}",
                        )
                    ],
                    sort_item_list=[],
                    limit=20,
                )
            ),
        ]

    def _source_hop_ranges(self, query_pattern: list[Clause]) -> list[tuple[int, int]]:
        for clause in query_pattern:
            if isinstance(clause, MatchClause):
                path_pattern = clause.path_pattern
                if isinstance(path_pattern, list):
                    path_pattern = path_pattern[0]
                return [edge.hop_range for edge in path_pattern.edge_pattern_list]
        return []

    def _display_property(self, label: str) -> str:
        vertex = self.vertex_by_label[label]
        columns = list(vertex.get("columns") or [])
        for column in columns:
            type_name = str(column.get("type", "")).upper()
            if "CHAR" in type_name or "CLOB" in type_name:
                return column["name"]
        return columns[0]["name"]

