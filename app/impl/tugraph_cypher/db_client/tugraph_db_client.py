from typing import Any, Dict

from TuGraphClient import TuGraphClient

from app.core.validator.db_client import DB_Client, QueryResult, QueryStatus


class TuGraphDBClient(DB_Client):
    """
    TuGraphDBClient is a concrete implementation of DB_Client
    for connecting to and operating TuGraph database.
    """

    def __init__(self, db_client_params: Dict[str, Any]):
        """
        Initialize TuGraphDBClient instance and create database connection.
        Implements the functionality of the abstract method create_client.
        """
        self.client: TuGraphClient | None = None
        # Call internal method to handle connection creation logic
        self.client = self.create_client(db_client_params)

    def create_client(self, db_client_params: Dict[str, Any]) -> TuGraphClient | None:
        """
        Create a new TuGraphClient instance (implementing abstract method).
        """
        try:
            client = TuGraphClient(**db_client_params)

            # Execute a simple test query to verify connection
            client.call_cypher("RETURN 1", timeout=5)
            print("Successfully created/reconnected TuGraphClient.")
            return client

        except Exception as e:
            # Connection failed or test query failed
            print(f"Failed to create TuGraphClient: {e}")
            return None

    def execute_query(self, query: str) -> QueryResult:
        """
        Execute a TuGraph Cypher query statement.

        :param query: Query string to execute.
        :return: Unified QueryResult object.
        """
        if not self.client:
            # Database client not successfully initialized
            return QueryResult(
                status_code=QueryStatus.SERVER_ERROR,
                error="TuGraph client is not initialized or connection failed.",
            )

        try:
            # Assume TuGraphClient's call_cypher method returns query result
            result = self.client.call_cypher(query, timeout=30)

            # Assume result is a list or dictionary containing data
            if not result or isinstance(result, str) or not result.get("result"):
                # Query successful but no records found
                return QueryResult(status_code=QueryStatus.NO_RECORD, data=[])

            # Successfully executed and returned data
            return QueryResult(status_code=QueryStatus.SUCCESS, data=result.get("result"))

        except Exception as e:
            error_msg = str(e)
            print(f"Error executing query: {error_msg}")

            # Simply determine client error vs server error through error message
            if "Cypher" in error_msg or "syntax" in error_msg.lower():
                status_code = QueryStatus.CLIENT_ERROR
            else:
                status_code = QueryStatus.SERVER_ERROR

            return QueryResult(status_code=status_code, error=error_msg)
