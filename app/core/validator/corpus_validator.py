import logging
import time
from typing import Any, Dict, List

from TuGraphClient import TuGraphClient

logger = logging.getLogger("CorpusValidator")


class CorpusValidator:
    def __init__(self, tu_client_params: dict):
        # Store parameters instead of the client object itself
        self._tu_client_params = tu_client_params
        self._tu_client = self._create_client()
        self._last_checked_time = time.time()
        
    def _create_client(self, attempts: int = 3, delay: float = 5.0):
        """Helper method to create a new TuGraphClient instance with retry logic."""
        for attempt in range(1, attempts + 1):
            try:
                client = TuGraphClient(**self._tu_client_params)
                client.call_cypher("RETURN 1", timeout=5)
                logger.info("Successfully created/reconnected TuGraphClient.")
                return client
            except Exception as e:
                logger.error(f"Failed to create/reconnect TuGraphClient: {e}")
                if attempt < attempts:
                    time.sleep(delay*attempt)
        return None

    # @property
    # def tu_client(self):
    #     # A simple flag to avoid checking too frequently
    #     if time.time() - self._last_checked_time > 60:
    #         self._last_checked_time = time.time()
    #         if self._tu_client is None or not self._check_connection_internal():
    #             logger.warning("DB connection seems lost. Attempting to reconnect...")
    #             self._tu_client = self._create_client()

    #     return self._tu_client

    # def _check_connection_internal(self) -> bool:
    #     """Internal check to see if the current client instance is working."""
    #     try:
    #         self._tu_client.call_cypher("MATCH (n) RETURN 1 LIMIT 1", timeout=5)
    #         return True
    #     except Exception as e:
    #         logger.error(f"Existing client connection failed check: {e}")
    #         return False

    def validate_and_filter_pairs(self, pairs: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        """
        Validate all pairs in 'pairs' and filter those whose execution succeeds and
        result is not None.
        """
        # client = self.tu_client
        client = self._create_client()
        if not client:
            logger.error("Database connection is not ready. Skipping validation.")
            return []
            
        print("\n--- Validating generated pairs against the database ---")
        valid_pairs = []
        for pair in pairs:
            question = pair.get("question")
            query = pair.get("query")
            
            if not question or not query:
                logger.warning(f"Invalid pair found (missing keys): {pair}")
                continue

            try:
                validation_query = query + " LIMIT 1" if "LIMIT" not in query.upper() else query
                # Use the 'client' variable returned by the property
                res = client.call_cypher(validation_query, timeout=30)
                
                if res and res.get("result") is not None:
                    # logger.info(f"Valid pair: '{question}'")
                    valid_pairs.append(pair)
                else:
                    logger.warning("Invalid pair "
                                   f"(empty result or malformed response): '{question}'")
            except Exception as e:
                logger.error(f"Query for '{question}' failed: {e}")

        return valid_pairs

    # execute_and_get_context method would use self.tu_client just like validate_and_filter_pairs
    def execute_and_get_context(self, pairs: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        # client = self.tu_client
        client = self._create_client()
        if not client:
            logger.error("Database connection is not ready. Skipping context generation.")
            return []
        
        context_items = []
        for pair in pairs:
            try:
                res = client.call_cypher(pair["query"], timeout=60)
                if res and res.get("result"):
                    res_summary = str(res)[:500] + "..." if len(str(res)) > 500 else str(res)
                    context_items.append({
                        "question": pair["question"], 
                        "query": pair["query"], 
                        "result": res_summary })
            except Exception:
                continue
        return context_items