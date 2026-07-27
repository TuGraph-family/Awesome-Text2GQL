from app.core.clauses.match_clause import EdgePattern, MatchClause, NodePattern, PathPattern
from app.impl.oracle_sqlpgq.generator.query_generalizer import OracleSqlPgqQueryGeneralizer
from app.impl.oracle_sqlpgq.utils.sqlpgq import validate_graph_table_query


def _manifest():
    return {
        "graph_name": "MOVIE_GRAPH",
        "vertices": [
            {
                "label": "PERSON",
                "columns": [
                    {"name": "PERSON_id", "type": "NUMBER(19)"},
                    {"name": "name", "type": "VARCHAR2(4000)"},
                ],
            },
            {
                "label": "MOVIE",
                "columns": [
                    {"name": "MOVIE_id", "type": "NUMBER(19)"},
                    {"name": "title", "type": "VARCHAR2(4000)"},
                ],
            },
            {
                "label": "GENRE",
                "columns": [
                    {"name": "GENRE_id", "type": "NUMBER(19)"},
                    {"name": "name", "type": "VARCHAR2(4000)"},
                ],
            },
        ],
        "edges": [
            {"label": "ACTED_IN", "src": "PERSON", "dst": "MOVIE"},
            {"label": "BELONGS_TO", "src": "MOVIE", "dst": "GENRE"},
            {"label": "SIMILAR_TO", "src": "MOVIE", "dst": "MOVIE"},
        ],
    }


def _one_hop_pattern():
    return [
        MatchClause(
            PathPattern(
                [NodePattern("a", "", []), NodePattern("b", "", [])],
                [EdgePattern("e", "", [], "right")],
            )
        )
    ]


def _two_hop_pattern():
    return [
        MatchClause(
            PathPattern(
                [NodePattern("a", "", []), NodePattern("b", "", []), NodePattern("c", "", [])],
                [
                    EdgePattern("e1", "", [], "right"),
                    EdgePattern("e2", "", [], "right"),
                ],
            )
        )
    ]


def test_oracle_query_generalizer_emits_oracle_queries_for_seed_path_length():
    generated = OracleSqlPgqQueryGeneralizer(_manifest()).generalize(_one_hop_pattern())

    assert len(generated) == 3
    assert all(validate_graph_table_query(item.query) for item in generated)
    assert any('MATCH (n1 IS "PERSON")-[e1 IS "ACTED_IN"]->(n2 IS "MOVIE")' in item.query for item in generated)


def test_oracle_query_generalizer_supports_two_hop_shapes():
    generated = OracleSqlPgqQueryGeneralizer(_manifest()).generalize(_two_hop_pattern())

    assert generated
    assert all(item.source_pattern_length == 2 for item in generated)
    assert any(item.labels == ["PERSON", "ACTED_IN", "MOVIE", "BELONGS_TO", "GENRE"] for item in generated)

