"""
Generate an Oracle SQL/PGQ corpus with live Oracle validation.

Required environment variables:
- ORACLE_DSN
- ORACLE_USER
- ORACLE_PASSWORD
"""

import json
import logging
import os
from pathlib import Path
from typing import Any

from app.core.generator.corpus_generator import CorpusGenerator
from app.core.llm.llm_client import LlmClient
from app.core.validator.db_client import QueryResult, QueryStatus
from app.core.validator.validator import CorpusValidator

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("OracleSqlPgqCorpusGenerator")


def summarize_result(result: QueryResult) -> str:
    if len(str(result.data)) > 500:
        return str(result.data)[:500] + "..."
    return str(result.data)


def save_json(data: list[dict[str, Any]], file_path: Path) -> None:
    with open(file_path, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, ensure_ascii=False)
    logger.info("Saved %s records to %s", len(data), file_path)


def validate_and_repair_pairs(
    *,
    generator: CorpusGenerator,
    validator: CorpusValidator,
    schema_json: str,
    raw_pairs: list[dict[str, str]],
    max_repair_attempts: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    client = validator._get_client()
    valid_pairs = []
    rejected_pairs = []

    for pair in raw_pairs:
        candidate = pair
        last_failure: dict[str, Any] | None = None
        for attempt in range(max_repair_attempts + 1):
            result = client.execute_query(candidate.get("query", ""))
            if result.status_code == QueryStatus.SUCCESS:
                valid_pairs.append(
                    {
                        "question": candidate["question"],
                        "query": candidate["query"],
                        "result": summarize_result(result),
                    }
                )
                break

            last_failure = {
                "question": candidate.get("question", ""),
                "query": candidate.get("query", ""),
                "status_code": result.status_code,
                "error": result.error,
                "attempt": attempt,
            }
            if attempt >= max_repair_attempts:
                rejected_pairs.append(last_failure)
                break

            error_context = (
                "Previous query failed Oracle validation. Correct it.\n"
                f"Previous query:\n{candidate.get('query', '')}\n"
                f"Oracle status code: {result.status_code}\n"
                f"Oracle error:\n{result.error}\n"
            )
            repaired = generator.generate_translation_batch(
                schema_json=schema_json,
                questions=[candidate.get("question", "")],
                error_context=error_context,
            )
            if not repaired:
                rejected_pairs.append(last_failure)
                break
            candidate = repaired[0]

    return valid_pairs, rejected_pairs


def main():
    graph_name = "TEXT2GQL_GRAPH"
    schema_file = Path("examples/Oracle_SQLPGQ_Instance/TEXT2GQL_GRAPH_oracle_schema.json")
    output_file = Path("examples/generated_corpus/oracle_sqlpgq_example_corpus.json")
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

    with open(schema_file, encoding="utf-8") as file:
        schema_json = json.dumps(json.load(file), ensure_ascii=False)

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
        graph_name=graph_name,
    )

    seed_queries = [
        {
            "question": "Show a small sample of connected graph elements.",
            "query": (
                'SELECT * FROM GRAPH_TABLE ("TEXT2GQL_GRAPH" '
                'MATCH (a)-[e]->(b) COLUMNS (VERTEX_ID(a) AS A_ID, VERTEX_ID(b) AS B_ID)) gt '
                "FETCH FIRST 5 ROWS ONLY"
            ),
        },
        {
            "question": "Which movies belong to the Science Fiction genre?",
            "query": (
                'SELECT * FROM GRAPH_TABLE ("TEXT2GQL_GRAPH" '
                'MATCH (m IS "MOVIE")-[b IS "BELONGS_TO"]->(g IS "GENRE") '
                'WHERE g."name" = \'Science Fiction\' '
                'COLUMNS (m."title" AS movie_title, g."name" AS genre_name)) gt'
            ),
        },
        {
            "question": "Which users gave ratings above 4.5, and what movies were rated?",
            "query": (
                'SELECT * FROM GRAPH_TABLE ("TEXT2GQL_GRAPH" '
                'MATCH (u IS "USER")-[ur IS "RATES"]->(r IS "RATING")-[rm IS "RATES"]->(m IS "MOVIE") '
                'WHERE r."score" > 4.5 '
                'COLUMNS (u."USER_id" AS user_id, m."title" AS movie_title, r."score" AS score)) gt'
            ),
        },
        {
            "question": "Which movie was tagged as classic?",
            "query": (
                'SELECT * FROM GRAPH_TABLE ("TEXT2GQL_GRAPH" '
                'MATCH (u IS "USER")-[ut IS "TAGS"]->(t IS "TAG")-[tm IS "TAGS"]->(m IS "MOVIE") '
                'WHERE t."text_content" = \'classic\' '
                'COLUMNS (u."USER_id" AS user_id, m."title" AS movie_title, t."text_content" AS tag_text)) gt'
            ),
        },
        {
            "question": "Which users are friends with user 1?",
            "query": (
                'SELECT * FROM GRAPH_TABLE ("TEXT2GQL_GRAPH" '
                'MATCH (u IS "USER")-[f IS "FRIENDS_WITH"]->(friend IS "USER") '
                'WHERE u."USER_id" = 1 '
                'COLUMNS (friend."USER_id" AS friend_id, f."connection_strength" AS connection_strength)) gt'
            ),
        },
        {
            "question": "Which movies are similar to Inception?",
            "query": (
                'SELECT * FROM GRAPH_TABLE ("TEXT2GQL_GRAPH" '
                'MATCH (m1 IS "MOVIE")-[s IS "SIMILAR_TO"]->(m2 IS "MOVIE") '
                'WHERE m1."title" = \'Inception\' '
                'COLUMNS (m2."title" AS similar_movie, s."similarity_score" AS similarity_score)) gt'
            ),
        },
        {
            "question": "Which Science Fiction movies found through the graph can be joined back to the movie table with their release year?",
            "query": (
                "WITH graph_movies AS ("
                'SELECT gt.movie_id, gt.movie_title FROM GRAPH_TABLE ("TEXT2GQL_GRAPH" '
                'MATCH (m IS "MOVIE")-[b IS "BELONGS_TO"]->(g IS "GENRE") '
                'WHERE g."name" = \'Science Fiction\' '
                'COLUMNS (m."MOVIE_id" AS movie_id, m."title" AS movie_title)) gt'
                ") "
                'SELECT gm.movie_title, m."release_year" AS release_year '
                'FROM graph_movies gm JOIN "MOVIE" m ON m."MOVIE_id" = gm.movie_id '
                'ORDER BY m."release_year" DESC'
            ),
        },
        {
            "question": "Show movies that come either from the base movie table after 2010 or from the graph as Action movies.",
            "query": (
                'SELECT \'TABLE\' AS source_type, m."title" AS movie_title FROM "MOVIE" m '
                'WHERE m."release_year" >= 2010 '
                "UNION ALL "
                'SELECT \'GRAPH\' AS source_type, gt.movie_title FROM GRAPH_TABLE ("TEXT2GQL_GRAPH" '
                'MATCH (m IS "MOVIE")-[b IS "BELONGS_TO"]->(g IS "GENRE") '
                'WHERE g."name" = \'Action\' '
                'COLUMNS (m."title" AS movie_title)) gt'
            ),
        },
        {
            "question": "Rank the highest graph ratings and show the user, movie, score, and rank.",
            "query": (
                'SELECT gt.user_id, gt.movie_title, gt.score, '
                "ROW_NUMBER() OVER (ORDER BY gt.score DESC) AS score_rank "
                'FROM GRAPH_TABLE ("TEXT2GQL_GRAPH" '
                'MATCH (u IS "USER")-[ur IS "RATES"]->(r IS "RATING")-[rm IS "RATES"]->(m IS "MOVIE") '
                'COLUMNS (u."USER_id" AS user_id, m."title" AS movie_title, r."score" AS score)) gt '
                "ORDER BY score_rank FETCH FIRST 5 ROWS ONLY"
            ),
        },
        {
            "question": "Which movies have at least one rating, and what is their average score?",
            "query": (
                'SELECT gt.movie_title, AVG(gt.score) AS average_score, COUNT(*) AS rating_count '
                'FROM GRAPH_TABLE ("TEXT2GQL_GRAPH" '
                'MATCH (u IS "USER")-[ur IS "RATES"]->(r IS "RATING")-[rm IS "RATES"]->(m IS "MOVIE") '
                'COLUMNS (m."title" AS movie_title, r."score" AS score)) gt '
                "GROUP BY gt.movie_title HAVING COUNT(*) >= 1 ORDER BY average_score DESC"
            ),
        },
        {
            "question": "Show one row per friendship step for paths up to three hops between users.",
            "query": (
                'SELECT * FROM GRAPH_TABLE ("TEXT2GQL_GRAPH" '
                'MATCH (start_user IS "USER")-[friend_path IS "FRIENDS_WITH"]->{1,3}(end_user IS "USER") '
                "ONE ROW PER STEP (step_source, step_edge, step_target) "
                'COLUMNS (MATCHNUM() AS match_number, ELEMENT_NUMBER(step_edge) AS step_number, '
                'step_source."USER_id" AS source_user_id, EDGE_ID(step_edge) AS edge_id, '
                'step_target."USER_id" AS target_user_id)) gt FETCH FIRST 10 ROWS ONLY'
            ),
        },
    ]
    seed_context = validator.execute_with_results(seed_queries)
    if not seed_context:
        raise RuntimeError("No seed queries validated successfully; cannot generate corpus.")
    save_json(seed_context, seed_validation_output_file)

    target_size = int(os.getenv("ORACLE_SQLPGQ_CORPUS_SIZE", "10"))
    if target_size <= 0:
        logger.info("Seed validation only: %s seed queries validated successfully.", len(seed_context))
        return

    num_per_iteration = int(os.getenv("ORACLE_SQLPGQ_NUM_PER_ITERATION", "3"))
    max_repair_attempts = int(os.getenv("ORACLE_SQLPGQ_REPAIR_ATTEMPTS", "1"))
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
        "Validated Oracle SQL/PGQ corpus: %s valid, %s rejected",
        len(valid_pairs),
        len(rejected_pairs),
    )


if __name__ == "__main__":
    main()
