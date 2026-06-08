import json
from pathlib import Path

from app.core.validator.db_client import QueryResult, QueryStatus
from dataset_prep.analyze_failures import failure_signature, unsupported_query_signature
from dataset_prep.compare_oracle_neo4j_results import (
    DatasetNeo4jLoader,
    compare_record,
    comparison_result,
    is_nondeterministic_limit_without_order,
    is_order_by_limit_query,
    normalize_rows,
    result_diagnostics,
    select_records_for_range,
    stable_execution_queries,
)
from dataset_prep.cypher_schema import CypherSchema
from dataset_prep.discover import DatabaseUnit, discover_database_units, source_query
from dataset_prep.oracle_loader import DatasetOracleLoader
from dataset_prep.translate_validate import detect_unsupported_features, graph_name_for


def _schema(config: dict) -> CypherSchema:
    return CypherSchema(config)


def test_discover_train_and_dev_layouts(tmp_path: Path):
    train_db = tmp_path / "train" / "movies"
    train_config = train_db / "cypher" / "movies_tugraph_new"
    train_config.mkdir(parents=True)
    (train_db / "4_level_results_ek_results.json").write_text("[]", encoding="utf-8")
    (train_config / "import_config.json").write_text(
        json.dumps({"schema": [], "files": []}),
        encoding="utf-8",
    )

    dev_db = tmp_path / "dev" / "Disney" / "Cypher"
    dev_config = dev_db / "disney__tugraph2"
    dev_config.mkdir(parents=True)
    (dev_db / "disney_cypher.json").write_text("[]", encoding="utf-8")
    (dev_db / "4_level_results_ek_results_refined.json").write_text("[]", encoding="utf-8")
    (dev_config / "import_config.json").write_text(
        json.dumps({"schema": [], "files": []}),
        encoding="utf-8",
    )

    units = discover_database_units(tmp_path, ["train", "dev"])

    assert [(unit.split, unit.database) for unit in units] == [
        ("dev", "Disney"),
        ("train", "movies"),
    ]
    assert units[0].query_path.name == "disney_cypher.json"
    assert units[1].csv_root == train_config


def test_source_query_prefers_cypher_then_gql():
    assert source_query({"initial_cypher": "MATCH (n) RETURN n", "initial_gql": "gql"}) == (
        "initial_cypher",
        "MATCH (n) RETURN n",
    )
    assert source_query({"initial_gql": "MATCH (n) RETURN n"}) == (
        "initial_gql",
        "MATCH (n) RETURN n",
    )


def test_graph_name_is_oracle_safe():
    unit = DatabaseUnit(
        split="test",
        database="Manufacturing_BOM(Bill_Of_Materials)",
        root=Path("."),
        query_path=Path("query.json"),
        import_config_path=Path("import_config.json"),
        csv_root=Path("."),
    )
    name = graph_name_for(unit, "T2GQL")
    assert "-" not in name
    assert "(" not in name
    assert len(name) <= 128


def test_detect_unsupported_oracle_sqlpgq_features():
    assert not detect_unsupported_features("MATCH p = (a)-[e]->(b) RETURN p")
    assert not detect_unsupported_features("MATCH (a)-[:A|B]->(b) RETURN b")
    assert not detect_unsupported_features(
        "MATCH (a) RETURN count(CASE WHEN a.type = 'x' THEN 1 ELSE NULL END)"
    )
    assert "case_label_predicate" in detect_unsupported_features(
        "MATCH (a) RETURN CASE WHEN a:ACCOUNT THEN 1 ELSE 0 END"
    )
    assert not detect_unsupported_features("OPTIONAL MATCH (a)-->(b) RETURN a.name, count(b)")
    assert not detect_unsupported_features(
        "MATCH (g:Group) WITH g ORDER BY g.created_date DESC LIMIT 1 "
        "OPTIONAL MATCH (g)<-[:BelongsTo]-(u:User) RETURN g.name, COUNT(u)"
    )
    assert not detect_unsupported_features(
        "MATCH (q:Question) OPTIONAL MATCH (q)<-[:COMMENTED_ON]-(c:Comment) "
        "WITH q, count(c) AS commentCount RETURN q.title, commentCount"
    )
    assert not detect_unsupported_features(
        "MATCH (q:Question) OPTIONAL MATCH (q)<-[:COMMENTED_ON]-(c:Comment) "
        "WHERE c IS NULL RETURN q.title"
    )
    assert not detect_unsupported_features("MATCH (a) OPTIONAL MATCH (a)--(b) RETURN b")
    assert "optional_match" in detect_unsupported_features(
        "OPTIONAL MATCH (a)-->(b) OPTIONAL MATCH (b)-->(c) RETURN c"
    )
    assert "optional_match" in detect_unsupported_features("MATCH (a) OPTIONAL MATCH (b) RETURN b")
    assert "optional_match" in detect_unsupported_features(
        "OPTIONAL MATCH (a)-->(b) RETURN count(*)"
    )
    assert "multiple_with" in detect_unsupported_features(
        "MATCH (a) WITH a MATCH (a)-->(b) WITH b RETURN b"
    )
    assert "unwind" not in detect_unsupported_features(
        "MATCH (q:Question {title: 'use UNWIND and FOREACH safely'}) RETURN q.title"
    )
    assert "multiple_with" not in detect_unsupported_features(
        'MATCH (q:Question {title: "WITH examples in a title"}) RETURN q.title'
    )
    assert "expensive_variable_length_path" in detect_unsupported_features(
        "MATCH (a:ACCOUNT)-[*..10]-(t:TRANSACTION) RETURN t LIMIT 1"
    )
    assert "expensive_variable_length_path" not in detect_unsupported_features(
        "MATCH (person:PERSON)-[:KNOWS*..3]->(friend:PERSON) RETURN friend"
    )
    assert "cost" not in detect_unsupported_features("MATCH (p:Product) RETURN p.cost")
    assert "cost" in detect_unsupported_features(
        "MATCH p = ANY CHEAPEST (a)-[:ROUTE]->(b) RETURN p"
    )
    assert "open_ended_variable_length_path" in detect_unsupported_features(
        "MATCH (person:PERSON)-[:KNOWS*1..]->(friend:PERSON) RETURN friend"
    )
    assert "open_ended_variable_length_path" in detect_unsupported_features(
        "MATCH (person:PERSON)-[*..]->(friend:PERSON) RETURN friend"
    )
    assert "open_ended_variable_length_path" not in detect_unsupported_features(
        "MATCH (person:PERSON)-[:KNOWS*1..3]->(friend:PERSON) RETURN friend"
    )
    assert "expensive_variable_length_path" in detect_unsupported_features(
        'MATCH (u:USER)-[*2..5]->(n) WHERE u.user_id = "U000001" RETURN n.user_id'
    )
    assert "expensive_variable_length_path" not in detect_unsupported_features(
        'MATCH (u:USER)-[*1..2]->(n) WHERE u.user_id = "U000001" RETURN n.user_id'
    )
    assert "quantified_relationship_property_map" in detect_unsupported_features(
        "MATCH (d:DEVICE)-[:CONNECTS_TO*1..2 {connectionType: 'WiFi'}]->(:GATEWAY) RETURN d"
    )


def test_detect_schema_direction_and_numeric_source_issues():
    schema = _schema(
        {
            "schema": [
                {
                    "label": "DataConsumer",
                    "type": "VERTEX",
                    "primary": "DataConsumer_id",
                    "properties": [{"name": "DataConsumer_id", "type": "STRING"}],
                },
                {
                    "label": "DataAsset",
                    "type": "VERTEX",
                    "primary": "DataAsset_id",
                    "properties": [{"name": "DataAsset_id", "type": "STRING"}],
                },
                {
                    "label": "ProcessingJob",
                    "type": "VERTEX",
                    "primary": "ProcessingJob_id",
                    "properties": [
                        {"name": "success_rate", "type": "DOUBLE"},
                        {"name": "sla_requirements", "type": "STRING"},
                    ],
                },
                {
                    "label": "Transforms",
                    "type": "EDGE",
                    "constraints": [["ProcessingJob", "DataAsset"]],
                    "properties": [],
                },
            ]
        }
    )

    assert "invalid_schema_direction" in detect_unsupported_features(
        "MATCH (da:DataAsset)-[:Transforms]->(pj:ProcessingJob) RETURN da",
        source_schema=schema,
    )
    assert "invalid_schema_direction" not in detect_unsupported_features(
        "MATCH (pj:ProcessingJob)-[:Transforms]->(da:DataAsset) RETURN da",
        source_schema=schema,
    )
    assert "unsafe_numeric_conversion" in detect_unsupported_features(
        "MATCH (pj:ProcessingJob) WHERE toInteger(pj.sla_requirements) > 24 RETURN pj",
        source_schema=schema,
    )


def test_failure_analysis_groups_unsupported_query_shapes():
    def record(query: str) -> dict:
        return {
            "oracle_validation_status": "unsupported",
            "oracle_translation_category": "Graph-IL Not Support",
            "oracle_source_query": query,
            "oracle_unsupported_features": [],
        }

    assert (
        failure_signature(record("MATCH (a) WITH a MATCH (a)-->(b) WITH a RETURN a"))
        == "multiple_with_skipped"
    )
    multi_with_optional = record("MATCH (a) WITH a OPTIONAL MATCH (a)-->(b) WITH a RETURN a")
    multi_with_optional["oracle_unsupported_features"] = ["optional_match"]
    assert failure_signature(multi_with_optional) == "multiple_with_skipped"
    standalone_optional = record("OPTIONAL MATCH (a)-->(b) RETURN a")
    standalone_optional["oracle_unsupported_features"] = ["optional_match"]
    assert failure_signature(standalone_optional) == "standalone_optional_match"
    optional_after_binding = record("MATCH (a) OPTIONAL MATCH (a)-->(b) RETURN a")
    optional_after_binding["oracle_unsupported_features"] = ["optional_match"]
    assert failure_signature(optional_after_binding) == "optional_match_left_join_required"
    assert (
        failure_signature(record("MATCH p=(a)-[:KNOWS*1..3]->(b) RETURN p"))
        == "path_variable_return"
    )
    assert (
        failure_signature(record("MATCH (p:Policy) RETURN AVG(p.effective_date) AS value"))
        == "temporal_numeric_aggregate"
    )
    assert (
        failure_signature(record("MATCH (a)-[e]->(b) RETURN count(DISTINCT e.bad_alias)"))
        == "invalid_schema_property"
    )
    assert (
        failure_signature(record("MATCH (a:Assertion) WHERE a.contradiction_severity > 1 RETURN a"))
        == "invalid_schema_property"
    )
    assert (
        failure_signature(
            record(
                "MATCH (g:Group) WITH g ORDER BY g.created_date DESC LIMIT 1 "
                "OPTIONAL MATCH (g)<-[:BelongsTo]-(u:User) RETURN g.name, COUNT(u)"
            )
        )
        == "invalid_schema_property"
    )
    assert failure_signature(record("MATCH (s:Source) RETURN s.name")) == "invalid_schema_property"
    assert (
        failure_signature(
            record(
                "MATCH p=(n1:Resource)-[e]-(n2:Policy) "
                "WHERE n2.sensitivity_level <> 'Internal' RETURN p"
            )
        )
        == "invalid_schema_property"
    )
    assert (
        unsupported_query_signature(
            "MATCH (s:Supplier)-[:SUPPLIES]->(p:Product)-[:ORDERS]->(o:Order) "
            "WITH s.supplierID AS supplierID, COUNT(DISTINCT o.shipCity) AS cityCount "
            "WHERE cityCount > 3 RETURN supplierID"
        )
        != "multi_pattern_match"
    )
    assert (
        unsupported_query_signature("MATCH (a)-[:KNOWS*1..]->(b) RETURN b")
        == "open_ended_variable_length_path"
    )


def test_failure_analysis_uses_manifest_for_invalid_schema(tmp_path: Path):
    import_config = tmp_path / "import_config.json"
    import_config.write_text(
        json.dumps(
            {
                "schema": [
                    {
                        "label": "Product",
                        "type": "VERTEX",
                        "properties": [{"name": "productName"}, {"name": "productID"}],
                    },
                    {
                        "label": "Order",
                        "type": "VERTEX",
                        "properties": [{"name": "freight"}, {"name": "orderDate"}],
                    },
                    {
                        "label": "ORDERS",
                        "type": "EDGE",
                        "properties": [{"name": "quantity"}],
                        "constraints": [["Order", "Product"]],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    def record(query: str) -> dict:
        return {
            "oracle_validation_status": "unsupported",
            "oracle_translation_category": "Graph-IL Not Support",
            "oracle_source_query": query,
            "oracle_unsupported_features": [],
            "oracle_dataset_meta": {"import_config": str(import_config)},
        }

    assert (
        failure_signature(record("MATCH (p:Product)-[:ORDERS]->(o:Order) RETURN o.freight"))
        == "invalid_schema_direction"
    )
    assert (
        failure_signature(record("MATCH (p:Product) RETURN p.missingProperty"))
        == "invalid_schema_property"
    )


def test_loader_converts_oracle_date_values():
    loader = DatasetOracleLoader.__new__(DatasetOracleLoader)

    assert loader._convert_value("2015-12-29", "DATE").isoformat() == "2015-12-29"
    assert (
        loader._convert_value("2025-05-18 12:14:48", "TIMESTAMP").isoformat()
        == "2025-05-18T12:14:48"
    )
    assert loader._convert_value("", "DATE") is None
    assert loader._convert_value("True", "NUMBER(1)") == 1
    assert loader._convert_value("False", "NUMBER(1)") == 0
    assert loader._convert_value("abcde", "VARCHAR2(3)") == "abc"
    assert loader._convert_value("ééé", "VARCHAR2(4)") == "éé"


def test_compare_normalizes_temporal_strings_and_numeric_precision():
    class FakeNeo4jDateTime:
        def iso_format(self):
            return "2025-01-01T12:00:00.000000000"

    oracle_rows = [{"created_at": "2025-01-01T12:00:00", "score": 1}]
    neo4j_rows = [{"created_at": "2025-01-01T12:00:00.000000000", "score": 1.0}]

    assert normalize_rows(oracle_rows) == normalize_rows(neo4j_rows)
    assert normalize_rows([{"created_at": "2025-01-01T12:00:00"}]) == normalize_rows(
        [{"created_at": FakeNeo4jDateTime()}]
    )
    assert normalize_rows([{"created_at": "2025-01-01T12:00:00.1"}]) == normalize_rows(
        [{"created_at": "2025-01-01T12:00:00.100000000"}]
    )
    assert normalize_rows([{"allocation": 0.764800012112}]) == normalize_rows(
        [{"allocation": 0.7648}]
    )
    assert normalize_rows([{"epoch": 1613446786}]) == normalize_rows(
        [{"epoch": 1613446786.0000002}]
    )
    assert normalize_rows([{"date_value": "2025-01-01T00:00:00"}]) == normalize_rows(
        [{"date_value": "2025-01-01"}]
    )


def test_compare_normalizes_oracle_and_neo4j_node_identity():
    class FakeNode:
        labels = {"director"}

        def items(self):
            return {
                "_id": 57,
                "name": "Pinocchio",
                "director": "Ben Sharpsteen",
            }.items()

    oracle_rows = [
        {
            "director": {
                "ELEM_TABLE": "director",
                "GRAPH_NAME": "G",
                "GRAPH_OWNER": "SYSTEM",
                "KEY_VALUE": {"_id": 57},
            }
        }
    ]
    neo4j_rows = [{"director": FakeNode()}]

    assert normalize_rows(oracle_rows, {"director": "_id"}) == normalize_rows(
        neo4j_rows,
        {"director": "_id"},
    )


def test_compare_normalizes_single_neo4j_path_to_flat_element_sequence():
    class FakeNode:
        def __init__(self, label: str, key: str, value: str):
            self.labels = {label}
            self._props = {key: value}

        def items(self):
            return self._props.items()

    class FakeRelationship:
        type = "POSTS"

        def items(self):
            return {}.items()

    class FakePath:
        nodes = [FakeNode("USER", "user_id", "U000001"), FakeNode("POST", "post_id", "P000001")]
        relationships = [FakeRelationship()]

    oracle_rows = [
        {
            "p_n1_ID": {"ELEM_TABLE": "USER", "KEY_VALUE": {"user_id": "U000001"}},
            "p_e1_ID": {"ELEM_TABLE": "POSTS", "KEY_VALUE": {}},
            "p_x_ID": {"ELEM_TABLE": "POST", "KEY_VALUE": {"post_id": "P000001"}},
        }
    ]
    neo4j_rows = [{"p": FakePath()}]

    assert normalize_rows(oracle_rows, {"USER": "user_id", "POST": "post_id"}) == normalize_rows(
        neo4j_rows,
        {"USER": "user_id", "POST": "post_id"},
    )


def test_compare_normalizes_oracle_and_neo4j_edge_identity():
    class FakeRelationship:
        type = "AllocatedTo"

        def items(self):
            return {"EDGE_ID": 6, "priority": 1}.items()

    oracle_rows = [
        {
            "r": {
                "ELEM_TABLE": "BUDGET_AllocatedTo_ACCOUNT",
                "KEY_VALUE": {"EDGE_ID": 6},
            }
        }
    ]
    neo4j_rows = [{"r": FakeRelationship()}]

    aliases = {"BUDGET_AllocatedTo_ACCOUNT": "AllocatedTo"}

    assert normalize_rows(oracle_rows, element_label_aliases=aliases) == normalize_rows(
        neo4j_rows,
        element_label_aliases=aliases,
    )


def test_compare_detects_nondeterministic_limit_without_order_by():
    assert is_nondeterministic_limit_without_order("MATCH (n) RETURN n LIMIT 10")
    assert not is_nondeterministic_limit_without_order(
        "MATCH (n) RETURN n ORDER BY n.name LIMIT 10"
    )
    assert is_nondeterministic_limit_without_order(
        "MATCH (n) WITH n ORDER BY n.created LIMIT 1 RETURN n LIMIT 10"
    )
    assert not is_nondeterministic_limit_without_order(
        "MATCH (n {text: 'ORDER BY words LIMIT examples'}) RETURN n"
    )
    assert is_order_by_limit_query("MATCH (n) RETURN n ORDER BY n.name LIMIT 10")


def test_compare_builds_stable_execution_queries_for_unordered_scalar_limit():
    stable = stable_execution_queries(
        "SELECT name, score FROM graph_table(...) FETCH FIRST 10 ROWS ONLY",
        "MATCH (n) RETURN n.name AS name, n.score AS score LIMIT 10",
    )

    assert stable.applied
    assert stable.reason == "unordered_paging"
    assert stable.cypher == (
        "MATCH (n) RETURN n.name AS name, n.score AS score ORDER BY name, score LIMIT 10"
    )
    assert stable.oracle_sqlpgq == (
        "SELECT name, score FROM graph_table(...)\nORDER BY 1, 2\nFETCH FIRST 10 ROWS ONLY"
    )


def test_compare_adds_stable_tiebreakers_to_ordered_scalar_limit():
    stable = stable_execution_queries(
        "SELECT name, score FROM graph_table(...) ORDER BY score FETCH FIRST 1 ROWS ONLY",
        "MATCH (n) RETURN n.name AS name, n.score AS score ORDER BY score LIMIT 1",
    )

    assert stable.applied
    assert stable.reason == "ordered_paging_tiebreaker"
    assert stable.cypher == (
        "MATCH (n) RETURN n.name AS name, n.score AS score ORDER BY score, name LIMIT 1"
    )
    assert stable.oracle_sqlpgq == (
        "SELECT name, score FROM graph_table(...) ORDER BY score, 1, 2 FETCH FIRST 1 ROWS ONLY"
    )


def test_compare_does_not_stabilize_bare_entity_or_path_limit():
    node_return = stable_execution_queries(
        "SELECT n_VALUE FROM graph_table(...) FETCH FIRST 10 ROWS ONLY",
        "MATCH (n:User) RETURN n LIMIT 10",
    )
    path_return = stable_execution_queries(
        "SELECT p_n1_ID FROM graph_table(...) FETCH FIRST 1 ROWS ONLY",
        "MATCH p = (n)-[r]->(m) RETURN p LIMIT 1",
    )

    assert not node_return.applied
    assert not path_return.applied


def test_compare_executes_matching_nondeterministic_limit_query():
    class FakeOracle:
        def __init__(self):
            self.query = ""

        def execute_query(self, query: str, **kwargs):
            self.query = query
            return QueryResult(QueryStatus.SUCCESS, data=[{"name": "A"}])

    class FakeNeo4j:
        primary_by_label = {}

        def __init__(self):
            self.query = ""

        def execute(self, query: str, timeout_s=None):
            self.query = query
            return "success", [{"name": "A"}], ""

    args = type("Args", (), {"oracle_timeout_ms": 0, "neo4j_timeout_s": 0})()
    oracle = FakeOracle()
    neo4j = FakeNeo4j()
    comparison = compare_record(
        {
            "oracle_sqlpgq": "SELECT 'A' AS name FROM dual FETCH FIRST 1 ROWS ONLY",
            "oracle_source_query": "MATCH (n) RETURN n.name LIMIT 1",
        },
        oracle,
        neo4j,
        args,
    )

    assert comparison["matched"]
    assert "ORDER BY 1" in oracle.query
    assert "ORDER BY n.name LIMIT 1" in neo4j.query


def test_compare_fails_stabilized_mismatched_limit_query():
    class FakeOracle:
        def execute_query(self, query: str, **kwargs):
            return QueryResult(QueryStatus.SUCCESS, data=[{"name": "A"}])

    class FakeNeo4j:
        primary_by_label = {}

        def execute(self, query: str, timeout_s=None):
            return "success", [{"name": "B"}], ""

    args = type("Args", (), {"oracle_timeout_ms": 0, "neo4j_timeout_s": 0})()
    comparison = compare_record(
        {
            "oracle_sqlpgq": "SELECT 'A' AS name FROM dual FETCH FIRST 1 ROWS ONLY",
            "oracle_source_query": "MATCH (n) RETURN n.name LIMIT 1",
        },
        FakeOracle(),
        FakeNeo4j(),
        args,
    )

    assert not comparison["matched"]
    assert comparison["reason"] == "result_mismatch"
    assert comparison["deterministic_ordering"]["reason"] == "unordered_paging"


def test_compare_skips_unsafe_mismatched_nondeterministic_limit_query():
    class FakeOracle:
        def execute_query(self, query: str, **kwargs):
            return QueryResult(QueryStatus.SUCCESS, data=[{"n": {"KEY_VALUE": {"id": 1}}}])

    class FakeNeo4j:
        primary_by_label = {}

        def execute(self, query: str, timeout_s=None):
            return "success", [{"n": {"KEY_VALUE": {"id": 2}}}], ""

    args = type("Args", (), {"oracle_timeout_ms": 0, "neo4j_timeout_s": 0})()
    comparison = compare_record(
        {
            "oracle_sqlpgq": "SELECT n_VALUE AS n FROM graph_table(...) FETCH FIRST 1 ROWS ONLY",
            "oracle_source_query": "MATCH (n) RETURN n LIMIT 1",
        },
        FakeOracle(),
        FakeNeo4j(),
        args,
    )

    assert not comparison["matched"]
    assert comparison["reason"] == "nondeterministic_limit_without_order"


def test_compare_skips_schema_invalid_source_before_execution():
    class FakeOracle:
        def execute_query(self, query: str, **kwargs):
            raise AssertionError("Oracle should not execute schema-invalid source queries")

    class FakeNeo4j:
        primary_by_label = {}
        cypher_schema = _schema(
            {
                "schema": [
                    {
                        "label": "DataConsumer",
                        "type": "VERTEX",
                        "properties": [{"name": "DataConsumer_id"}],
                    },
                    {
                        "label": "DataAsset",
                        "type": "VERTEX",
                        "properties": [{"name": "DataAsset_id"}],
                    },
                    {
                        "label": "Consumes",
                        "type": "EDGE",
                        "constraints": [["DataConsumer", "DataAsset"]],
                        "properties": [],
                    },
                ]
            }
        )

        def source_validation_issues(self, query: str):
            return self.cypher_schema.validation_issues(query)

        def execute(self, query: str, timeout_s=None):
            raise AssertionError("Neo4j should not execute schema-invalid source queries")

    args = type("Args", (), {"oracle_timeout_ms": 0, "neo4j_timeout_s": 0})()
    comparison = compare_record(
        {
            "oracle_sqlpgq": "SELECT 1 AS value FROM dual",
            "oracle_source_query": (
                "MATCH (da:DataAsset)-[:Consumes]->(dc:DataConsumer) RETURN da"
            ),
        },
        FakeOracle(),
        FakeNeo4j(),
        args,
    )

    assert comparison["reason"] == "source_invalid"
    assert comparison["oracle_status"] == "not_executed"
    assert "invalid_schema_direction" in comparison["neo4j_error"]


def test_compare_classifies_failed_neo4j_query_as_source_invalid():
    class FakeOracle:
        def execute_query(self, query: str, **kwargs):
            return QueryResult(QueryStatus.SUCCESS, data=[{"name": "A"}])

    class FakeNeo4j:
        primary_by_label = {}

        def execute(self, query: str, timeout_s=None):
            return "syntax_error", [], "Invalid input"

    args = type("Args", (), {"oracle_timeout_ms": 0, "neo4j_timeout_s": 0})()
    comparison = compare_record(
        {
            "oracle_sqlpgq": "SELECT 'A' AS name FROM dual",
            "oracle_source_query": "MATCH (n) RETURN n.invalid.source",
        },
        FakeOracle(),
        FakeNeo4j(),
        args,
    )

    assert not comparison["matched"]
    assert comparison["reason"] == "source_invalid"
    assert comparison["neo4j_status"] == "syntax_error"
    assert "result_diagnostics" not in comparison


def test_compare_result_mismatch_reports_full_result_diagnostics():
    oracle_rows = [{"name": "A"}, {"name": "A"}, {"name": "B"}]
    neo4j_rows = [{"name": "A"}, {"name": "C"}]

    diagnostics = result_diagnostics(oracle_rows, neo4j_rows)

    assert diagnostics["oracle_row_count"] == 3
    assert diagnostics["neo4j_row_count"] == 2
    assert diagnostics["missing_from_neo4j_count"] == 2
    assert diagnostics["extra_in_neo4j_count"] == 1
    assert diagnostics["missing_from_neo4j_sample"] == [["A"], ["B"]]
    assert diagnostics["extra_in_neo4j_sample"] == [["C"]]

    comparison = comparison_result(
        False,
        "result_mismatch",
        "MATCH (n) RETURN n.name",
        "SELECT name FROM graph_table(...)",
        "success",
        "success",
        "",
        "",
        oracle_rows,
        neo4j_rows,
    )

    assert comparison["result_diagnostics"] == diagnostics


def test_compare_fails_ordered_limit_mismatch_without_boundary_tie():
    class FakeOracle:
        def __init__(self):
            self.calls = 0

        def execute_query(self, query: str, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return QueryResult(QueryStatus.SUCCESS, data=[{"name": "A", "score": 1}])
            return QueryResult(
                QueryStatus.SUCCESS,
                data=[{"name": "A", "score": 1}, {"name": "C", "score": 2}],
            )

    class FakeNeo4j:
        primary_by_label = {}

        def __init__(self):
            self.calls = 0

        def execute(self, query: str, timeout_s=None):
            self.calls += 1
            if self.calls == 1:
                return "success", [{"name": "B", "score": 2}], ""
            return "success", [{"name": "B", "score": 2}, {"name": "D", "score": 3}], ""

    args = type("Args", (), {"oracle_timeout_ms": 0, "neo4j_timeout_s": 0})()
    comparison = compare_record(
        {
            "oracle_sqlpgq": (
                "SELECT 'A' AS name, 1 AS score FROM dual ORDER BY score FETCH FIRST 1 ROWS ONLY"
            ),
            "oracle_source_query": (
                "MATCH (n) RETURN n.name AS name, n.score AS score ORDER BY score LIMIT 1"
            ),
        },
        FakeOracle(),
        FakeNeo4j(),
        args,
    )

    assert not comparison["matched"]
    assert comparison["reason"] == "result_mismatch"


def test_compare_skips_ordered_limit_mismatch_with_boundary_tie():
    class FakeOracle:
        def __init__(self):
            self.calls = 0

        def execute_query(self, query: str, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return QueryResult(QueryStatus.SUCCESS, data=[{"n": "A", "score": 1}])
            return QueryResult(
                QueryStatus.SUCCESS,
                data=[{"n": "A", "score": 1}, {"n": "C", "score": 1}],
            )

    class FakeNeo4j:
        primary_by_label = {}

        def execute(self, query: str, timeout_s=None):
            return "success", [{"n": "B", "score": 1}, {"n": "D", "score": 1}], ""

    args = type("Args", (), {"oracle_timeout_ms": 0, "neo4j_timeout_s": 0})()
    comparison = compare_record(
        {
            "oracle_sqlpgq": (
                "SELECT 'A' AS n, 1 AS score FROM dual ORDER BY score FETCH FIRST 1 ROWS ONLY"
            ),
            "oracle_source_query": ("MATCH (n) RETURN n ORDER BY score LIMIT 1"),
        },
        FakeOracle(),
        FakeNeo4j(),
        args,
    )

    assert not comparison["matched"]
    assert comparison["reason"] == "suspected_order_by_limit_tie"


def test_compare_selects_offset_query_ranges():
    records = [{"id": index} for index in range(5)]

    assert select_records_for_range(records, query_offset=2, limit_queries=2) == [
        {"id": 2},
        {"id": 3},
    ]
    assert select_records_for_range(records, query_offset=3) == [{"id": 3}, {"id": 4}]
    assert select_records_for_range(records, query_offset=-10, limit_queries=1) == [{"id": 0}]


def test_neo4j_compare_prepares_string_backed_boolean_literals():
    loader = DatasetNeo4jLoader.__new__(DatasetNeo4jLoader)
    loader.property_types_by_label = {
        "Question": {"answered": "STRING"},
        "Answer": {"is_accepted": "STRING"},
        "Product": {"discontinued": "STRING"},
        "Role": {"is_compliant": "BOOL"},
    }

    assert (
        loader.prepare_query("MATCH (q:Question {answered: true}) RETURN q")
        == "MATCH (q:Question {answered: 'true'}) RETURN q"
    )
    assert (
        loader.prepare_query("MATCH (p:Product) WHERE p.discontinued = false RETURN p")
        == "MATCH (p:Product) WHERE p.discontinued = 'false' RETURN p"
    )
    assert (
        loader.prepare_query("MATCH (q:Question) WHERE NOT q.answered RETURN q")
        == "MATCH (q:Question) WHERE q.answered = 'false' RETURN q"
    )
    assert (
        loader.prepare_query("MATCH (r:Role) WHERE r.is_compliant = true RETURN r")
        == "MATCH (r:Role) WHERE r.is_compliant = true RETURN r"
    )


def test_neo4j_compare_prepares_string_backed_date_comparisons():
    loader = DatasetNeo4jLoader.__new__(DatasetNeo4jLoader)
    loader.property_types_by_label = {
        "Director": {"died": "STRING"},
        "Movie": {"release_date": "STRING"},
        "Question": {"createdAt": "STRING"},
        "Event": {"event_date": "DATE"},
    }

    assert (
        loader.prepare_query("MATCH (d:Director) WHERE d.died > date('2000-01-01') RETURN d")
        == "MATCH (d:Director) WHERE date(d.died) > date('2000-01-01') RETURN d"
    )
    assert (
        loader.prepare_query("MATCH (m:Movie) WHERE date('2000-01-01') > m.release_date RETURN m")
        == "MATCH (m:Movie) WHERE date('2000-01-01') > date(m.release_date) RETURN m"
    )
    assert (
        loader.prepare_query("MATCH (e:Event) WHERE e.event_date > date('2000-01-01') RETURN e")
        == "MATCH (e:Event) WHERE e.event_date > date('2000-01-01') RETURN e"
    )
    assert (
        loader.prepare_query("MATCH (q:Question) WHERE date(q.createdAt).day = 1 RETURN q")
        == "MATCH (q:Question) WHERE datetime(q.createdAt).day = 1 RETURN q"
    )
    assert (
        loader.prepare_query("MATCH (q:Question) WHERE q.createdAt.day = 1 RETURN q")
        == "MATCH (q:Question) WHERE datetime(q.createdAt).day = 1 RETURN q"
    )


def test_neo4j_compare_prepares_string_backed_numeric_comparisons():
    loader = DatasetNeo4jLoader.__new__(DatasetNeo4jLoader)
    loader.property_types_by_label = {
        "Answer": {"uuid": "STRING"},
        "Product": {"unitsOnOrder": "STRING", "reorderLevel": "INT64"},
        "Order": {"freight": "STRING"},
    }

    assert (
        loader.prepare_query("MATCH (p:Product) WHERE p.unitsOnOrder > 50 RETURN p")
        == "MATCH (p:Product) WHERE p.unitsOnOrder > '50' RETURN p"
    )
    assert (
        loader.prepare_query("MATCH (o:Order) WHERE 100 < o.freight RETURN o")
        == "MATCH (o:Order) WHERE '100' < o.freight RETURN o"
    )
    assert (
        loader.prepare_query("MATCH (p:Product) WHERE p.reorderLevel > 50 RETURN p")
        == "MATCH (p:Product) WHERE p.reorderLevel > 50 RETURN p"
    )
    assert (
        loader.prepare_query("MATCH (a:Answer {uuid: 69273049}) RETURN a")
        == "MATCH (a:Answer {uuid: '69273049'}) RETURN a"
    )


def test_neo4j_compare_rewrites_sanitized_schema_aliases():
    loader = DatasetNeo4jLoader.__new__(DatasetNeo4jLoader)
    loader.vertex_labels = {"characters", "voice_actors"}
    loader.edge_labels = {"HERO"}
    loader.property_types_by_label = {
        "characters": {"movie_title": "STRING"},
        "voice_actors": {"voice_actor": "STRING", "movie": "STRING"},
    }
    loader.node_label_aliases = loader._schema_name_aliases(loader.vertex_labels)
    loader.edge_type_aliases = loader._schema_name_aliases(loader.edge_labels)
    loader.property_aliases_by_label = {
        label: loader._schema_name_aliases(properties)
        for label, properties in loader.property_types_by_label.items()
    }
    loader.global_property_aliases = loader._global_property_aliases()

    assert loader.prepare_query(
        "MATCH (t1:characters)-[hero:HERO]->(t2:`voice-actors`) "
        "WHERE t2.movie = t1.movie_title AND t2.movie <> 'voice-actor' "
        "RETURN t2.`voice-actor`"
    ) == (
        "MATCH (t1:characters)-[hero:HERO]->(t2:voice_actors) "
        "WHERE t2.movie = t1.movie_title AND t2.movie <> 'voice-actor' "
        "RETURN t2.voice_actor"
    )


def test_neo4j_compare_rewrites_identity_and_adjacent_edge_properties():
    loader = DatasetNeo4jLoader.__new__(DatasetNeo4jLoader)
    config = {
        "schema": [
            {
                "label": "PaymentTransaction",
                "type": "VERTEX",
                "primary": "transaction_id",
                "properties": [{"name": "transaction_id", "type": "STRING"}],
            },
            {
                "label": "USER",
                "type": "VERTEX",
                "primary": "user_id",
                "properties": [{"name": "user_id", "type": "STRING"}],
            },
            {
                "label": "REPORT",
                "type": "VERTEX",
                "primary": "report_id",
                "properties": [{"name": "report_id", "type": "STRING"}],
            },
            {
                "label": "Approves",
                "type": "EDGE",
                "constraints": [["USER", "REPORT"]],
                "properties": [
                    {"name": "EDGE_ID", "type": "INT64"},
                    {"name": "approval_date", "type": "TIMESTAMP"},
                ],
            },
        ]
    }
    loader.cypher_schema = CypherSchema(config)
    loader.vertex_labels = {"PaymentTransaction", "USER", "REPORT"}
    loader.edge_labels = {"Approves"}
    loader.primary_by_label = {"PaymentTransaction": "transaction_id", "USER": "user_id"}
    loader.property_types_by_label = loader.cypher_schema.property_types_by_label
    loader.node_label_aliases = loader._schema_name_aliases(loader.vertex_labels)
    loader.edge_type_aliases = loader._schema_name_aliases(loader.edge_labels)
    loader.property_aliases_by_label = {
        label: loader._schema_name_aliases(properties)
        for label, properties in loader.property_types_by_label.items()
    }
    loader.global_property_aliases = loader._global_property_aliases()

    assert (
        loader.prepare_query("MATCH (n:PaymentTransaction) RETURN count(n.identity), count(n.id)")
        == "MATCH (n:PaymentTransaction) RETURN count(n.transaction_id), "
        "count(n.transaction_id)"
    )
    assert (
        loader.prepare_query("MATCH (u:USER)-[r:Approves]->(report:REPORT) RETURN r.identity")
        == "MATCH (u:USER)-[r:Approves]->(report:REPORT) RETURN r.EDGE_ID"
    )
    assert (
        loader.prepare_query(
            "MATCH (approver:USER)-[r:Approves]->(report:REPORT) RETURN approver.approval_date"
        )
        == "MATCH (approver:USER)-[r:Approves]->(report:REPORT) RETURN r.approval_date"
    )


def test_loader_uses_vertex_file_when_edge_label_collides():
    loader = DatasetOracleLoader.__new__(DatasetOracleLoader)
    loader.config = {
        "files": [
            {"label": "zip_data", "path": "zip_data.csv", "columns": ["_id"]},
            {
                "label": "zip_data",
                "path": "statezip_dataCBSA.csv",
                "SRC_ID": "state",
                "DST_ID": "CBSA",
                "columns": ["SRC_ID", "DST_ID"],
            },
        ]
    }
    loader.manifest = {
        "vertices": [{"label": "zip_data", "table": "zip_data", "columns": []}],
        "edges": [],
    }
    calls = []

    def fake_load_file(item, file_item, is_edge=False):
        calls.append((item["label"], file_item["path"], is_edge))
        return 1

    loader._load_file = fake_load_file

    assert loader._load_csv_files() == {"zip_data": 1}
    assert calls == [("zip_data", "zip_data.csv", False)]


def test_loader_does_not_reuse_edge_file_for_different_constraint():
    loader = DatasetOracleLoader.__new__(DatasetOracleLoader)
    loader.config = {
        "files": [
            {
                "label": "GENERATES",
                "path": "GENERATES_Device.csv",
                "SRC_ID": "DEVICE",
                "DST_ID": "ALERT",
                "columns": ["SRC_ID", "DST_ID"],
            }
        ]
    }
    loader.manifest = {
        "vertices": [],
        "edges": [
            {
                "label": "GENERATES",
                "src": "DEVICE",
                "dst": "ALERT",
                "table": "DEVICE_GENERATES_ALERT",
                "columns": [],
            },
            {
                "label": "GENERATES",
                "src": "SENSOR",
                "dst": "ALERT",
                "table": "SENSOR_GENERATES_ALERT",
                "columns": [],
            },
        ],
    }
    calls = []

    def fake_load_file(item, file_item, is_edge=False):
        calls.append((item["table"], file_item["path"], is_edge))
        return 1

    loader._load_file = fake_load_file

    assert loader._load_csv_files() == {"DEVICE_GENERATES_ALERT": 1}
    assert calls == [("DEVICE_GENERATES_ALERT", "GENERATES_Device.csv", True)]


def test_loader_exposes_oracle_graph_label_map_for_collisions():
    loader = DatasetOracleLoader.__new__(DatasetOracleLoader)
    loader.manifest = {
        "vertices": [{"label": "book", "graph_label": "book"}],
        "edges": [
            {"label": "book", "graph_label": "book_language_book_publisher"},
            {"label": "book", "graph_label": "book_author_book"},
        ],
    }

    assert loader.node_label_map() == {"book": ["book"]}
    assert loader.edge_label_map() == {"book": ["book_language_book_publisher", "book_author_book"]}


def test_loader_exposes_file_stem_label_aliases():
    loader = DatasetOracleLoader.__new__(DatasetOracleLoader)
    loader.config = {
        "files": [
            {"label": "InfoSource", "path": "Source.csv", "columns": ["infosource_id"]},
        ]
    }
    loader.manifest = {
        "vertices": [{"label": "InfoSource", "graph_label": "InfoSource"}],
        "edges": [],
    }

    assert loader.node_label_map() == {
        "InfoSource": ["InfoSource"],
        "Source": ["InfoSource"],
    }


def test_dataset_loader_manifest_is_tolerant_for_benchmark_data(tmp_path: Path):
    config = {
        "schema": [
            {
                "label": "A",
                "type": "VERTEX",
                "primary": "id",
                "properties": [
                    {"name": "id", "type": "INT64"},
                    {"name": "score", "type": "INT64"},
                ],
            },
            {
                "label": "B",
                "type": "VERTEX",
                "primary": "id",
                "properties": [
                    {"name": "id", "type": "INT64"},
                    {"name": "score", "type": "STRING"},
                ],
            },
            {
                "label": "REL",
                "type": "EDGE",
                "constraints": [["A", "B"]],
                "properties": [],
            },
        ],
        "files": [],
    }
    config_path = tmp_path / "import_config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")

    loader = DatasetOracleLoader.__new__(DatasetOracleLoader)
    loader.import_config_path = config_path
    loader.graph_name = "G"
    manifest = loader._build_manifest()

    assert "FOREIGN KEY" not in manifest["table_ddl"]
    assert "ENFORCED MODE" not in manifest["property_graph_ddl"]
    score_types = [
        column["type"]
        for item in manifest["vertices"]
        for column in item["columns"]
        if column["name"] == "score"
    ]
    assert score_types == ["VARCHAR2(4000)", "VARCHAR2(4000)"]
