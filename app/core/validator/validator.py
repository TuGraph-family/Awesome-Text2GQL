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

    def validate_and_filter_pairs(self, pairs: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        """
        Validate all pairs and filter out pairs that fail execution or have empty results.
        """
        client = self._get_client()
        if not client or not client.client:
            logger.error("Database connection is not ready. Skipping validation.")
            raise Exception("Database connection is not ready.")

        print("\n--- Validating generated pairs against the database ---")
        valid_pairs = []
        valid_num = 0

        for pair in pairs:
            question = pair.get("question")
            query = pair.get("query")

            if not question or not query:
                logger.warning(f"Invalid pair found (missing keys): {pair}")
                continue

            # 1. Construct validation query
            validation_query = query + " LIMIT 1" if "LIMIT" not in query.upper() else query

            # 2. Call unified execute_query
            result: QueryResult = client.execute_query(validation_query)

            # 3. Unified status code judgment
            if result.status_code == QueryStatus.SUCCESS:
                # Successfully executed and result is not empty
                valid_num += 1
                valid_pairs.append(pair)
            elif result.status_code == QueryStatus.NO_RECORD:
                # Query successful but no records found
                # logger.warning(f"Query successful but no record found: '{question}'")
                continue
            elif result.status_code == QueryStatus.CLIENT_ERROR:
                # Cypher syntax error or parameter error
                # logger.warning(f"Query syntax failed (CLIENT_ERROR) for"
                #    f" '{question}': {result.error}")
                continue
            else:  # SERVER_ERROR or other unexpected errors
                # logger.error(f"Query execution failed (SERVER_ERROR) for"
                #  f" '{question}': {result.error}")
                continue

        logger.info(f"{valid_num}/{len(pairs)} pairs passed validation. ")
        return valid_pairs

    def execute_and_get_context(self, pairs: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        """
        Execute queries and get results as context.
        """
        client = self._get_client()
        if not client or not client.client:
            logger.error("Database client is not available for context generation.")
            return []

        context_items = []
        valid_num = 0
        for pair in pairs:
            # 1. execute query
            result: QueryResult = client.execute_query(pair["query"])

            if result.status_code == QueryStatus.SUCCESS:
                # Successfully obtained data
                if len(str(result.data)) > 500:
                    res_summary = str(result.data)[:500] + "..."
                else:
                    res_summary = str(result.data)
                context_items.append(
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
        return context_items
