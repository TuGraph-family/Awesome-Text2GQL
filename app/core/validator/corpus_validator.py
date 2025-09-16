from typing import Any, Dict, List

import httpx
from TuGraphClient import TuGraphClient


class CorpusValidator:
    def __init__(self, tu_client: TuGraphClient):
        self.tu_client = tu_client

    def _is_db_alive(self) -> bool:
        """Execute a simple query to check if the database is responsive."""
        try:
            self.tu_client.call_cypher("MATCH (n) RETURN count(n) LIMIT 1", timeout=5)
            return True
        except (httpx.ReadError, httpx.ConnectError, httpx.TimeoutException):
            return False
        except Exception:
            return False

    def validate_and_filter_pairs(self, pairs: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        """
        Validate a list of question-query pairs against the database.
        Returns a new list containing only valid pairs.
        """
        print("\n--- Validating generated pairs against the database ---")
        valid_pairs = []
        for pair in pairs:
            question = pair.get("question")
            query = pair.get("query")

            if not question or not query:
                print(f"  - Invalid pair found (missing keys): {pair}")
                continue

            try:
                # Use LIMIT 1 to quickly validate query validity without returning large data
                validation_query = query + " LIMIT 1" if "LIMIT" not in query.upper() else query
                res = self.tu_client.call_cypher(validation_query, timeout=30)
                
                # A successful query should return a result, even if it's empty data
                if res and res.get("result") is not None:
                    print(f"Valid pair: '{question}'")
                    valid_pairs.append(pair)
                else:
                    print(f"Invalid pair (empty result or malformed response): '{question}'")
            except Exception as e:
                print(f"Invalid pair (query failed): '{question}' - Error: {e}")
        
        return valid_pairs
        
    def execute_and_get_context(self, pairs: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        """
        Execute a list of queries and format the results as context entries.
        Only includes pairs with non-empty results.
        """
        context_items = []
        for pair in pairs:
            try:
                res = self.tu_client.call_cypher(pair["query"], timeout=60)
                if res and res.get("result"):
                    res_summary = str(res)[:500] + "..." if len(str(res)) > 500 else str(res)
                    context_items.append({
                        "question": pair["question"],
                        "query": pair["query"],
                        "result": res_summary
                    })
            except Exception:
                # Silently skip pairs that fail or have empty results
                continue
        return context_items