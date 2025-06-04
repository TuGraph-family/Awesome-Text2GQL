from typing import List

from app.core.clauses.clause import Clause
from app.core.clauses.match_clause import EdgePattern, MatchClause, NodePattern, PathPattern
from app.core.clauses.return_clause import ReturnBody, ReturnClause
from app.core.clauses.where_clause import CompareExpression, WhereClause
from app.core.schema.schema_graph import SchemaGraph
from app.core.schema.schema_parser import SchemaParser
from app.impl.tugraph_cypher.schema.schema_parser import TuGraphSchemaParser


class QueryGeneralizer:
    def __init__(self, db_id, instance_path):
        self.db_id = db_id
        self.instance_path = instance_path
        self.schema_parser: SchemaParser = TuGraphSchemaParser(db_id, instance_path)
        self.schema_graph: SchemaGraph = self.schema_parser.get_schema_graph()

    def generalize(self, query_pattern: List[Clause]) -> List[str]:
        match_clause: MatchClause = query_pattern[0]
        path_pattern = match_clause.path_pattern
        path_pattern_list = self.schema_graph.match_path_pattern(path_pattern)

        query_pattern_list = []
        for path_pattern in path_pattern_list:
            match_clause = MatchClause(path_pattern)

            # add where clause
            compare_expression: CompareExpression = self.schema_graph.match_where_expression(
                path_pattern.node_pattern_list[0].symbolic_name,
                path_pattern.node_pattern_list[0].label,
            )
            where_clause: WhereClause = WhereClause(compare_expression=compare_expression)

            # add return clause
            return_body: ReturnBody = self.schema_graph.match_return_body(
                [
                    (
                        path_pattern.node_pattern_list[-1].symbolic_name,
                        path_pattern.node_pattern_list[-1].label,
                    )
                ]
            )
            return_clause: ReturnClause = ReturnClause(return_body=return_body)

            new_query_pattern = [match_clause, where_clause, return_clause]

            query_pattern_list.append(new_query_pattern)
        return query_pattern_list

    def generalize_from_llm(self, query_template: str) -> List[str]:
        # TODO: use llm to generalize new query.
        return []

    def generalize_from_cypher(self, query_template: str) -> List[str]:
        # TODO: use original awesome-text2gql to generalize new query.
        from app.impl.tugraph_cypher.generalizer.graph_query_generalizer import (
            GraphQueryGeneralizer as CypherGeneralizer,
        )

        cypher_generalizer = CypherGeneralizer(self.db_id, self.instance_path)
        return cypher_generalizer.generalize(query_template)

    def test_schema_graph(self):
        self.schema_graph.print_schema_graph()

    def test_match_path_pattern(self):
        path_pattern = PathPattern([], [])
        path_pattern.node_pattern_list.append(NodePattern("n1", "n_a"))
        path_pattern.node_pattern_list.append(NodePattern("n2", "n_b"))
        path_pattern.edge_pattern_list.append(EdgePattern("e1", "e_a", "right"))

        path_pattern_list = self.schema_graph.match_path_pattern(path_pattern)
        for path_pattern in path_pattern_list:
            match_clause = MatchClause(path_pattern)
            print(match_clause.to_string())
