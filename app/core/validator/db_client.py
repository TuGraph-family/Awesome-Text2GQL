from abc import ABC, abstractmethod
from typing import Any


class QueryResult:
    """
    Unified query result return class.
    Encapsulates query status code, actual data, and error information.
    """

    def __init__(self, status_code: int, data: Any | None = None, error: str | None = None):
        # Status code:
        # 200 - Success,
        # 101 - Client error/Syntax error,
        # 102 - Server error/Connection error, etc.
        self.status_code: int = status_code
        # Actual query result data (such as nodes, relationships, properties, etc.)
        self.data: Any | None = data
        # If there's an error, store the error message
        self.error: str | None = error

    def is_success(self) -> bool:
        """Check if the query was successful (status code 200)"""
        return self.status_code == 200


class QueryStatus:
    """Define unified status code constants for query results."""

    SUCCESS = 200  # Successfully executed
    CLIENT_ERROR = 101  # Client error (e.g., Cypher syntax error, parameter error)
    SERVER_ERROR = 102  # Server error (e.g., database connection failure, internal error)
    NO_RECORD = 103  # Query successful but no records found


class DB_Client(ABC):
    """
    Abstract database client, defining basic methods that all graph database clients must implement.
    """

    @abstractmethod
    def create_client(self, db_client_params: dict):
        """
        Create a new DB_Client instance.
        """

    @abstractmethod
    def execute_query(self, query: str) -> QueryResult:
        """
        Execute a Cypher (or corresponding database syntax) query statement.

        :param query: Query string to execute.
        :return: Unified QueryResult object.
        """
