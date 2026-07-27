import json

from app.impl.oracle_sqlpgq.generator.template_instantiator import (
    OracleSqlPgqTemplateInstantiator,
)
from app.impl.oracle_sqlpgq.utils.sqlpgq import validate_graph_table_query


def _manifest():
    return {
        "backend": "oracle_sqlpgq",
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
        ],
        "edges": [
            {
                "label": "ACTED_IN",
                "src": "PERSON",
                "dst": "MOVIE",
                "columns": [
                    {"name": "EDGE_ID", "type": "NUMBER"},
                    {"name": "SRC_ID", "type": "NUMBER"},
                    {"name": "DST_ID", "type": "NUMBER"},
                    {"name": "role", "type": "VARCHAR2(4000)"},
                ],
            },
            {
                "label": "SIMILAR_TO",
                "src": "MOVIE",
                "dst": "MOVIE",
                "columns": [
                    {"name": "EDGE_ID", "type": "NUMBER"},
                    {"name": "SRC_ID", "type": "NUMBER"},
                    {"name": "DST_ID", "type": "NUMBER"},
                    {"name": "score", "type": "BINARY_FLOAT"},
                ],
            },
        ],
    }


def test_template_instantiator_generates_valid_graph_table_queries():
    pairs = OracleSqlPgqTemplateInstantiator(_manifest()).generate()

    assert pairs
    assert all(validate_graph_table_query(pair.query) for pair in pairs)
    assert any(pair.category == "one_hop_traversal" for pair in pairs)
    assert any(pair.category == "aggregation" for pair in pairs)
    assert any(pair.category == "bounded_path" for pair in pairs)
    assert any("source_MOVIE_title" in pair.query for pair in pairs)
    assert any("target_MOVIE_title" in pair.query for pair in pairs)


def test_template_instantiator_can_load_manifest_file(tmp_path):
    manifest_path = tmp_path / "oracle_schema.json"
    manifest_path.write_text(json.dumps(_manifest()), encoding="utf-8")

    pairs = OracleSqlPgqTemplateInstantiator.from_file(manifest_path).generate_dicts(
        target_size=2,
        include_metadata=False,
    )

    assert len(pairs) == 2
    assert set(pairs[0]) == {"question", "query"}
