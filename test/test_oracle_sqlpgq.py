from pathlib import Path

from app.core.clauses.match_clause import EdgePattern, MatchClause, NodePattern, PathPattern
from app.core.clauses.return_clause import ReturnBody, ReturnClause, ReturnItem, SortItem
from app.core.clauses.where_clause import CompareExpression, WhereClause
from app.core.schema.edge import Edge
from app.core.schema.node import Node
from app.core.schema.schema_graph import SchemaGraph
from app.core.validator.db_client import DB_Client, QueryResult, QueryStatus
from app.core.validator.validator import CorpusValidator
from app.impl.oracle_sqlpgq.ast_visitor.oracle_sqlpgq_ast_visitor import OracleSqlPgqAstVisitor
from app.impl.oracle_sqlpgq.schema.schema_parser import OracleSqlPgqSchemaParser
from app.impl.oracle_sqlpgq.translator.oracle_sqlpgq_query_translator import (
    OracleSqlPgqQueryTranslator,
)


def _schema_graph() -> SchemaGraph:
    graph = SchemaGraph("movie_graph")
    graph.add_node(
        Node(
            label="PERSON",
            primary="PERSON_id",
            properties=[
                {"name": "PERSON_id", "type": "INT64"},
                {"name": "name", "type": "STRING"},
            ],
        )
    )
    graph.add_node(
        Node(
            label="MOVIE",
            primary="MOVIE_id",
            properties=[
                {"name": "MOVIE_id", "type": "INT64"},
                {"name": "title", "type": "STRING"},
            ],
        )
    )
    graph.add_edge(
        Edge(
            label="ACTED_IN",
            properties=[{"name": "role", "type": "STRING"}],
            src_dst_list=[["PERSON", "MOVIE"]],
        )
    )
    return graph


def _query_pattern():
    path = PathPattern(
        node_pattern_list=[
            NodePattern("p", "PERSON", []),
            NodePattern("m", "MOVIE", []),
        ],
        edge_pattern_list=[EdgePattern("a", "ACTED_IN", [], "right")],
    )
    return [
        MatchClause(path),
        WhereClause(CompareExpression("p", "name", "equal", "'Tom Hanks'")),
        ReturnClause(
            ReturnBody(
                return_item_list=[ReturnItem("m", "title", "movie_title")],
                sort_item_list=[SortItem("m", "title", "ASC")],
                skip=5,
                limit=10,
            )
        ),
    ]


def test_oracle_schema_parser_generates_table_and_graph_ddl(tmp_path):
    parser = OracleSqlPgqSchemaParser(db_id="movie_graph")
    manifest_path = parser.save_schema_to_file(tmp_path, _schema_graph(), "movie", "oracle")

    manifest_file = Path(manifest_path)
    table_ddl = (tmp_path / "movie_oracle_oracle_tables.sql").read_text()
    graph_ddl = (tmp_path / "movie_oracle_oracle_property_graph.sql").read_text()

    assert manifest_file.exists()
    assert 'CREATE TABLE "PERSON"' in table_ddl
    assert 'CREATE TABLE "PERSON_ACTED_IN_MOVIE"' in table_ddl
    assert 'CREATE OR REPLACE PROPERTY GRAPH "movie_oracle"' in graph_ddl
    assert "VERTEX TABLES" in graph_ddl
    assert "EDGE TABLES" in graph_ddl
    assert "ENFORCED MODE" in graph_ddl


def test_oracle_sqlpgq_translator_renders_graph_table_query():
    translator = OracleSqlPgqQueryTranslator(graph_name="MOVIE_GRAPH")

    query = translator.translate(_query_pattern())

    assert query.startswith("SELECT *\nFROM GRAPH_TABLE")
    assert '"MOVIE_GRAPH"' in query
    assert 'MATCH (p IS "PERSON")-[a IS "ACTED_IN"]->(m IS "MOVIE")' in query
    assert 'WHERE p."name" = \'Tom Hanks\'' in query
    assert 'COLUMNS (m."title" AS movie_title)' in query
    assert "ORDER BY movie_title ASC" in query
    assert "OFFSET 5 ROWS" in query
    assert "FETCH FIRST 10 ROWS ONLY" in query
    assert translator.grammar_check(query)


def test_oracle_sqlpgq_translator_projects_element_ids_when_returning_whole_nodes():
    translator = OracleSqlPgqQueryTranslator(graph_name="MOVIE_GRAPH")
    path = PathPattern([NodePattern("p", "PERSON", [])], [])

    query = translator.translate(
        [MatchClause(path), ReturnClause(ReturnBody([ReturnItem("p", "", "")], []))]
    )

    assert "VERTEX_ID(p) AS p_VALUE" in query


def test_oracle_sqlpgq_ast_visitor_parses_translator_subset():
    query = OracleSqlPgqQueryTranslator(graph_name="MOVIE_GRAPH").translate(_query_pattern())

    success, clauses = OracleSqlPgqAstVisitor().get_query_pattern(query)

    assert success
    assert isinstance(clauses[0], MatchClause)
    assert isinstance(clauses[1], WhereClause)
    assert isinstance(clauses[2], ReturnClause)
    assert clauses[2].return_body.sort_item_list[0].symbolic_name == "movie_title"
    assert clauses[2].return_body.sort_item_list[0].order == "ASC"
    assert clauses[2].return_body.skip == 5
    assert clauses[2].return_body.limit == 10


class FakeDBClient(DB_Client):
    client = object()

    def create_client(self, db_client_params: dict):
        return self.client

    def execute_query(self, query: str) -> QueryResult:
        if "empty" in query:
            return QueryResult(QueryStatus.NO_RECORD, data=[])
        return QueryResult(QueryStatus.SUCCESS, data=[{"ok": 1}])


def test_corpus_validator_accepts_oracle_backend_with_injected_client():
    validator = CorpusValidator(backend="oracle_sqlpgq", db_client=FakeDBClient())

    valid = validator.execute_with_results(
        [
            {"question": "ok?", "query": "select ok"},
            {"question": "empty?", "query": "select empty"},
        ]
    )

    assert valid == [{"question": "ok?", "query": "select ok", "result": "[{'ok': 1}]"}]
