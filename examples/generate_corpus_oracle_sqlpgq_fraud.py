"""
Generate an Oracle SQL/PGQ corpus for the fraud/payments graph with live validation.

Required environment variables:
- ORACLE_DSN
- ORACLE_USER
- ORACLE_PASSWORD
"""

import json
import logging
import os
from pathlib import Path

from app.core.generator.corpus_generator import CorpusGenerator
from app.core.llm.llm_client import LlmClient
from app.core.validator.validator import CorpusValidator
from examples.generate_corpus_oracle_sqlpgq import save_json, validate_and_repair_pairs
from examples.setup_oracle_sqlpgq_fraud_db import GRAPH_NAME, build_manifest


logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("OracleSqlPgqFraudCorpusGenerator")


def env_int(name: str, default: int) -> int:
    return int(os.getenv(name, os.getenv(name.replace("FRAUD_", ""), str(default))))


def main() -> None:
    output_file = Path("examples/generated_corpus/oracle_sqlpgq_fraud_corpus.json")
    raw_output_file = output_file.with_name(f"{output_file.stem}_raw{output_file.suffix}")
    rejected_output_file = output_file.with_name(
        f"{output_file.stem}_rejected{output_file.suffix}"
    )
    validated_output_file = output_file.with_name(
        f"{output_file.stem}_validated_with_results{output_file.suffix}"
    )
    seed_validation_output_file = output_file.with_name(
        f"{output_file.stem}_seed_validated_with_results{output_file.suffix}"
    )
    output_file.parent.mkdir(parents=True, exist_ok=True)

    schema_json = json.dumps(build_manifest()["schema"], ensure_ascii=False)
    validator = CorpusValidator(
        backend="oracle_sqlpgq",
        db_client_params={
            "dsn": os.environ["ORACLE_DSN"],
            "user": os.environ["ORACLE_USER"],
            "password": os.environ["ORACLE_PASSWORD"],
        },
    )
    generator = CorpusGenerator(
        llm_client=LlmClient(
            model=os.getenv("LLM_MODEL", "qwen3-coder-plus-2025-07-22"),
            platform=os.getenv("LLM_PLATFORM", ""),
        ),
        query_language="oracle_sqlpgq",
        graph_name=GRAPH_NAME,
    )

    seed_queries = [
        {
            "question": "Show a small sample of connected fraud graph elements.",
            "query": (
                f'SELECT * FROM GRAPH_TABLE ("{GRAPH_NAME}" '
                'MATCH (a)-[e]->(b) COLUMNS (VERTEX_ID(a) AS source_id, EDGE_ID(e) AS edge_id, VERTEX_ID(b) AS destination_id)) gt '
                "FETCH FIRST 5 ROWS ONLY"
            ),
        },
        {
            "question": "Which high-risk customers initiated fraudulent transactions above 1000?",
            "query": (
                f'SELECT * FROM GRAPH_TABLE ("{GRAPH_NAME}" '
                'MATCH (c IS "CUSTOMER")-[o IS "OWNS"]->(a IS "ACCOUNT")-[i IS "INITIATED"]->(t IS "TRANSACTION") '
                'WHERE c."RISK_SCORE" > 0.7 AND t."AMOUNT" > 1000 AND t."FRAUD_FLAG" = 1 '
                'COLUMNS (c."NAME" AS customer_name, t."TRANSACTION_ID" AS transaction_id, t."AMOUNT" AS amount)) gt'
            ),
        },
        {
            "question": "Which merchants received online transactions over 500?",
            "query": (
                f'SELECT * FROM GRAPH_TABLE ("{GRAPH_NAME}" '
                'MATCH (a IS "ACCOUNT")-[i IS "INITIATED"]->(t IS "TRANSACTION")-[p IS "PAID"]->(m IS "MERCHANT") '
                'WHERE t."CHANNEL" = \'online\' AND t."AMOUNT" > 500 '
                'COLUMNS (m."NAME" AS merchant_name, m."CATEGORY" AS category, t."AMOUNT" AS amount)) gt'
            ),
        },
        {
            "question": "Which transactions used an untrusted device?",
            "query": (
                f'SELECT * FROM GRAPH_TABLE ("{GRAPH_NAME}" '
                'MATCH (t IS "TRANSACTION")-[u IS "USED_DEVICE"]->(d IS "DEVICE") '
                'WHERE d."TRUSTED" = 0 '
                'COLUMNS (t."TRANSACTION_ID" AS transaction_id, t."AMOUNT" AS amount, d."DEVICE_TYPE" AS device_type)) gt'
            ),
        },
        {
            "question": "Which customers live in Casablanca?",
            "query": (
                f'SELECT * FROM GRAPH_TABLE ("{GRAPH_NAME}" '
                'MATCH (c IS "CUSTOMER")-[l IS "LIVES_IN"]->(city IS "CITY") '
                'WHERE city."NAME" = \'Casablanca\' '
                'COLUMNS (c."NAME" AS customer_name, c."SEGMENT" AS segment)) gt'
            ),
        },
        {
            "question": "What merchant categories have fraudulent transactions?",
            "query": (
                f'SELECT gt.category, COUNT(*) AS fraud_transaction_count FROM GRAPH_TABLE ("{GRAPH_NAME}" '
                'MATCH (t IS "TRANSACTION")-[p IS "PAID"]->(m IS "MERCHANT") '
                'WHERE t."FRAUD_FLAG" = 1 '
                'COLUMNS (m."CATEGORY" AS category, t."TRANSACTION_ID" AS transaction_id)) gt '
                "GROUP BY gt.category"
            ),
        },
        {
            "question": "Which fraudulent graph transactions belong to customers whose base table risk score is above 0.7?",
            "query": (
                "WITH graph_tx AS ("
                f'SELECT gt.customer_id, gt.customer_name, gt.transaction_id, gt.amount FROM GRAPH_TABLE ("{GRAPH_NAME}" '
                'MATCH (c IS "CUSTOMER")-[o IS "OWNS"]->(a IS "ACCOUNT")-[i IS "INITIATED"]->(t IS "TRANSACTION") '
                'WHERE t."FRAUD_FLAG" = 1 '
                'COLUMNS (c."CUSTOMER_ID" AS customer_id, c."NAME" AS customer_name, '
                't."TRANSACTION_ID" AS transaction_id, t."AMOUNT" AS amount)) gt'
                ") "
                'SELECT graph_tx.customer_name, c."RISK_SCORE" AS risk_score, graph_tx.transaction_id, graph_tx.amount '
                'FROM graph_tx JOIN "CUSTOMER" c ON c."CUSTOMER_ID" = graph_tx.customer_id '
                'WHERE c."RISK_SCORE" > 0.7'
            ),
        },
        {
            "question": "Combine high-risk customers from the customer table with customers found through fraudulent graph transactions.",
            "query": (
                'SELECT \'HIGH_RISK_TABLE\' AS source_type, c."NAME" AS customer_name FROM "CUSTOMER" c '
                'WHERE c."RISK_SCORE" > 0.8 '
                "UNION ALL "
                f'SELECT \'FRAUD_GRAPH\' AS source_type, gt.customer_name FROM GRAPH_TABLE ("{GRAPH_NAME}" '
                'MATCH (c IS "CUSTOMER")-[o IS "OWNS"]->(a IS "ACCOUNT")-[i IS "INITIATED"]->(t IS "TRANSACTION") '
                'WHERE t."FRAUD_FLAG" = 1 '
                'COLUMNS (c."NAME" AS customer_name)) gt'
            ),
        },
        {
            "question": "Rank fraudulent graph transactions by amount within each merchant category.",
            "query": (
                "SELECT gt.category, gt.transaction_id, gt.amount, "
                "ROW_NUMBER() OVER (PARTITION BY gt.category ORDER BY gt.amount DESC) AS category_amount_rank "
                f'FROM GRAPH_TABLE ("{GRAPH_NAME}" '
                'MATCH (t IS "TRANSACTION")-[p IS "PAID"]->(m IS "MERCHANT") '
                'WHERE t."FRAUD_FLAG" = 1 '
                'COLUMNS (m."CATEGORY" AS category, t."TRANSACTION_ID" AS transaction_id, t."AMOUNT" AS amount)) gt '
                "ORDER BY gt.category, category_amount_rank"
            ),
        },
        {
            "question": "Which merchants have at least one online graph transaction and also exist in the merchant table outside the graph?",
            "query": (
                f'SELECT m."NAME" AS merchant_name, m."CATEGORY" AS category '
                'FROM "MERCHANT" m '
                "WHERE EXISTS ("
                f'SELECT 1 FROM GRAPH_TABLE ("{GRAPH_NAME}" '
                'MATCH (t IS "TRANSACTION")-[p IS "PAID"]->(merchant IS "MERCHANT") '
                'WHERE t."CHANNEL" = \'online\' '
                'COLUMNS (merchant."MERCHANT_ID" AS merchant_id)) gt '
                'WHERE gt.merchant_id = m."MERCHANT_ID")'
            ),
        },
        {
            "question": "Show one row per step along the customer-account-transaction-merchant payment path.",
            "query": (
                f'SELECT * FROM GRAPH_TABLE ("{GRAPH_NAME}" '
                'MATCH (c IS "CUSTOMER")-[o IS "OWNS"]->(a IS "ACCOUNT")-[i IS "INITIATED"]->'
                '(t IS "TRANSACTION")-[p IS "PAID"]->(m IS "MERCHANT") '
                "ONE ROW PER STEP (step_source, step_edge, step_target) "
                "COLUMNS (MATCHNUM() AS match_number, ELEMENT_NUMBER(step_edge) AS step_number, "
                "VERTEX_ID(step_source) AS source_id, EDGE_ID(step_edge) AS edge_id, "
                "VERTEX_ID(step_target) AS target_id)) gt FETCH FIRST 10 ROWS ONLY"
            ),
        },
    ]
    seed_context = validator.execute_with_results(seed_queries)
    if not seed_context:
        raise RuntimeError("No fraud seed queries validated successfully; cannot generate corpus.")
    save_json(seed_context, seed_validation_output_file)

    target_size = env_int("FRAUD_ORACLE_SQLPGQ_CORPUS_SIZE", 10)
    if target_size <= 0:
        logger.info(
            "Fraud seed validation only: %s seed queries validated successfully.",
            len(seed_context),
        )
        return

    num_per_iteration = env_int("FRAUD_ORACLE_SQLPGQ_NUM_PER_ITERATION", 3)
    max_repair_attempts = env_int("FRAUD_ORACLE_SQLPGQ_REPAIR_ATTEMPTS", 1)
    raw_pairs = generator.run_generation_loop(
        schema_json=schema_json,
        seeds_corpus_with_context=seed_context,
        num_per_iteration=num_per_iteration,
        complexity_corpus_size=target_size,
    )
    save_json(raw_pairs, raw_output_file)
    valid_pairs, rejected_pairs = validate_and_repair_pairs(
        generator=generator,
        validator=validator,
        schema_json=schema_json,
        raw_pairs=raw_pairs,
        max_repair_attempts=max_repair_attempts,
    )
    save_json(rejected_pairs, rejected_output_file)
    save_json(valid_pairs, validated_output_file)
    save_json(
        [{"question": item["question"], "query": item["query"]} for item in valid_pairs],
        output_file,
    )
    logger.info(
        "Validated fraud Oracle SQL/PGQ corpus: %s valid, %s rejected",
        len(valid_pairs),
        len(rejected_pairs),
    )


if __name__ == "__main__":
    main()
