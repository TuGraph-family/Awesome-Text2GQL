import logging
from typing import Any, Dict, List

from app.core.validator.db_client import DB_Client, QueryResult, QueryStatus
from app.impl.tugraph_cypher.db_client.tugraph_db_client import TuGraphDBClient

logger = logging.getLogger("CorpusValidator")


class CorpusValidator:
    def __init__(self, tu_client_params: dict):
        # Store parameters instead of the client object itself
        """
        Initialize validator and for instantiating TuGraph database client implementation.
        """
        self._tu_client_params = tu_client_params
        self._client: DB_Client | None = None

        # Create connection during initialization and store the instance
        self._client = TuGraphDBClient(self._tu_client_params)

        # Immediately check if connection was successful
        if not self._client or not self._client.client:
            logger.error("Database client failed to initialize or connect.")

    def _get_client(self) -> DB_Client | None:
        """Return the created client instance."""
        return self._client

    def execute_with_results(self, pairs: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        """
        Validate all pairs and get query result,
        filter out pairs that fail execution or have empty results.
        """
        client = self._get_client()
        if not client or not client.client:
            logger.error("Database connection is not ready. Skipping validation.")
            raise Exception("Database connection is not ready.")

        print("\n--- Validating generated pairs against the database ---")
        valid_pairs = []
        valid_num = 0

        valid_pairs = []
        valid_num = 0
        for pair in pairs:
            question = pair.get("question")
            query = pair.get("query")

            if not question or not query:
                logger.warning(f"Invalid pair found (missing keys): {pair}")
                continue

            # 1. execute query
            result: QueryResult = client.execute_query(pair["query"])

            if result.status_code == QueryStatus.SUCCESS:
                # Successfully obtained data
                if len(str(result.data)) > 500:
                    res_summary = str(result.data)[:500] + "..."
                else:
                    res_summary = str(result.data)
                valid_pairs.append(
                    {"question": pair["question"], "query": pair["query"], "result": res_summary}
                )
                valid_num += 1
            else:
                # Query failed or no records, skip directly (continue)
                logger.warning(
                    f"Skipping pair due to non-successful result "
                    f"(Code {result.status_code}): {pair['question']}"
                )
                continue

        logger.info(f"{valid_num}/{len(pairs)} pairs had successful query results. ")
        return valid_pairs
