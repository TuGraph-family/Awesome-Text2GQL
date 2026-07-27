from importlib import import_module
import logging
from typing import Any, Dict, List

from app.core.validator.db_client import DB_Client, QueryResult, QueryStatus

logger = logging.getLogger("CorpusValidator")


class CorpusValidator:
    CLIENTS = {
        "tugraph_cypher": (
            "app.impl.tugraph_cypher.db_client.tugraph_db_client",
            "TuGraphDBClient",
        ),
        "tugraph": (
            "app.impl.tugraph_cypher.db_client.tugraph_db_client",
            "TuGraphDBClient",
        ),
        "oracle_sqlpgq": (
            "app.impl.oracle_sqlpgq.db_client.oracle_db_client",
            "OracleDBClient",
        ),
        "oracle": (
            "app.impl.oracle_sqlpgq.db_client.oracle_db_client",
            "OracleDBClient",
        ),
    }

    def __init__(
        self,
        tu_client_params: dict | None = None,
        backend: str = "tugraph_cypher",
        db_client_params: dict | None = None,
        db_client: DB_Client | None = None,
    ):
        """
        Initialize validator and instantiate the selected database client implementation.

        Args:
            tu_client_params: Backward-compatible TuGraph parameters.
            backend: One of tugraph_cypher or oracle_sqlpgq.
            db_client_params: Backend-specific connection parameters.
            db_client: Optional prebuilt client, useful for tests.
        """
        self.backend = backend
        self._client_params = db_client_params if db_client_params is not None else tu_client_params
        self._client_params = self._client_params or {}
        self._client: DB_Client | None = db_client

        if self._client is None:
            client_class = self._resolve_client_class(backend)
            self._client = client_class(self._client_params)

        if not self._is_client_ready(self._client):
            logger.error(
                f"Database client for backend '{backend}' failed to initialize or connect."
            )

    def _get_client(self) -> DB_Client | None:
        """Return the created client instance."""
        return self._client

    def _resolve_client_class(self, backend: str):
        target = self.CLIENTS.get(backend)
        if target is None:
            supported = ", ".join(sorted(self.CLIENTS))
            raise ValueError(
                f"Unsupported backend '{backend}'. Supported backends: {supported}"
            )
        module_path, class_name = target
        module = import_module(module_path)
        return getattr(module, class_name)

    def _is_client_ready(self, client: DB_Client | None) -> bool:
        if client is None:
            return False
        for attr in ("client", "connection", "driver"):
            if hasattr(client, attr):
                return getattr(client, attr) is not None
        return True

    def execute_with_results(self, pairs: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        """
        Validate all pairs and get query result,
        filter out pairs that fail execution or have empty results.
        """
        client = self._get_client()
        if not self._is_client_ready(client):
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
