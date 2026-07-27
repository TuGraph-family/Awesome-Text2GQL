import json

from app.core.validator.db_client import DB_Client, QueryResult, QueryStatus
from app.impl.oracle_sqlpgq.generator.corpus_combiner import OracleSqlPgqCorpusCombiner
from app.core.validator.validator import CorpusValidator


def test_oracle_corpus_combiner_normalizes_and_deduplicates(tmp_path):
    first = tmp_path / "template.json"
    second = tmp_path / "raw.json"
    first.write_text(
        json.dumps(
            [
                {
                    "question": "Show movies.",
                    "query": "SELECT * FROM GRAPH_TABLE (\"G\" MATCH (m IS \"MOVIE\") COLUMNS (m.\"title\" AS title)) gt",
                    "category": "one_hop",
                    "labels": ["MOVIE"],
                }
            ]
        ),
        encoding="utf-8",
    )
    second.write_text(
        json.dumps(
            [
                {
                    "question": "Show movies.",
                    "query": "SELECT * FROM GRAPH_TABLE (\"G\" MATCH (m IS \"MOVIE\") COLUMNS (m.\"title\" AS title)) gt",
                },
                {
                    "question": "Count movies.",
                    "query": "SELECT gt.title, COUNT(*) AS c FROM GRAPH_TABLE (\"G\" MATCH (m IS \"MOVIE\") COLUMNS (m.\"title\" AS title)) gt GROUP BY gt.title",
                },
            ]
        ),
        encoding="utf-8",
    )

    records = OracleSqlPgqCorpusCombiner().combine_files([first, second], split=True)

    assert len(records) == 2
    assert records[0]["id"] == "oracle_sqlpgq_000001"
    assert records[0]["backend"] == "oracle_sqlpgq"
    assert records[1]["category"] == "aggregation"
    assert {record["split"] for record in records} <= {"train", "dev", "test"}


class FakeOracleClient(DB_Client):
    client = object()

    def create_client(self, db_client_params: dict):
        return self.client

    def execute_query(self, query: str) -> QueryResult:
        if "BROKEN" in query:
            return QueryResult(QueryStatus.CLIENT_ERROR, error="broken query")
        return QueryResult(QueryStatus.SUCCESS, data=[{"ok": 1}])


def test_oracle_corpus_combiner_can_live_validate_records(tmp_path):
    source = tmp_path / "records.json"
    source.write_text(
        json.dumps(
            [
                {"question": "ok?", "query": "SELECT * FROM GRAPH_TABLE (\"G\" MATCH (n IS \"MOVIE\") COLUMNS (n.\"title\" AS title)) gt"},
                {"question": "bad?", "query": "BROKEN"},
            ]
        ),
        encoding="utf-8",
    )
    validator = CorpusValidator(backend="oracle_sqlpgq", db_client=FakeOracleClient())

    records = OracleSqlPgqCorpusCombiner().combine_files([source], validator=validator)

    assert records[0]["validation"] == "passed"
    assert records[0]["result"] == "[{'ok': 1}]"
    assert records[1]["validation"] == "failed"
    assert records[1]["validation_error"] == "broken query"
