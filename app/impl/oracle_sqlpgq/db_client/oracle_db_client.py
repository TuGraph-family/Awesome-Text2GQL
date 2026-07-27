from typing import Any, Dict, Iterable, List

try:
    import oracledb
except ImportError:  # pragma: no cover - exercised only when dependency is absent.
    oracledb = None

from app.core.validator.db_client import DB_Client, QueryResult, QueryStatus
from app.impl.oracle_sqlpgq.utils.sqlpgq import split_sql_statements


class OracleDBClient(DB_Client):
    """Oracle Database client for SQL/PGQ validation and corpus execution."""

    def __init__(self, db_client_params: Dict[str, Any]):
        self.db_client_params = db_client_params
        self.connection = self.create_client(db_client_params)
        self.client = self.connection

    def create_client(self, db_client_params: Dict[str, Any]):
        if oracledb is None:
            print("Failed to create OracleDBClient: install the 'oracledb' package first.")
            return None

        try:
            connection = oracledb.connect(
                user=db_client_params.get("user") or db_client_params.get("username"),
                password=db_client_params.get("password"),
                dsn=db_client_params.get("dsn"),
                config_dir=db_client_params.get("config_dir"),
                wallet_location=db_client_params.get("wallet_location"),
                wallet_password=db_client_params.get("wallet_password"),
            )
            connection.autocommit = db_client_params.get("autocommit", True)
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1 FROM dual")
                cursor.fetchone()
            print("Successfully created OracleDBClient.")
            return connection
        except Exception as exc:
            print(f"Failed to create OracleDBClient: {exc}")
            return None

    def execute_query(
        self,
        query: str,
        fetch_limit: int = 0,
        call_timeout_ms: int = 0,
    ) -> QueryResult:
        if not self.connection:
            return QueryResult(
                status_code=QueryStatus.SERVER_ERROR,
                error="Oracle connection is not initialized or connection failed.",
            )

        previous_call_timeout = getattr(self.connection, "call_timeout", 0)
        try:
            if call_timeout_ms > 0:
                self.connection.call_timeout = call_timeout_ms
            with self.connection.cursor() as cursor:
                cursor.execute(query)
                if cursor.description:
                    columns = [col[0] for col in cursor.description]
                    rows = cursor.fetchmany(fetch_limit) if fetch_limit > 0 else cursor.fetchall()
                    data = [dict(zip(columns, row, strict=False)) for row in rows]
                    if not data:
                        return QueryResult(status_code=QueryStatus.NO_RECORD, data=[])
                    return QueryResult(status_code=QueryStatus.SUCCESS, data=data)
                return QueryResult(
                    status_code=QueryStatus.SUCCESS,
                    data={"rowcount": cursor.rowcount},
                )
        except Exception as exc:
            error = str(exc)
            status_code = (
                QueryStatus.CLIENT_ERROR
                if self._looks_like_client_error(error)
                else QueryStatus.SERVER_ERROR
            )
            return QueryResult(status_code=status_code, error=error)
        finally:
            if call_timeout_ms > 0 and self.connection:
                self.connection.call_timeout = previous_call_timeout

    def execute_script(self, script: str) -> List[QueryResult]:
        return [self.execute_query(statement) for statement in split_sql_statements(script)]

    def executemany(self, statement: str, rows: Iterable[Iterable[Any]]) -> QueryResult:
        if not self.connection:
            return QueryResult(
                status_code=QueryStatus.SERVER_ERROR,
                error="Oracle connection is not initialized or connection failed.",
            )
        try:
            with self.connection.cursor() as cursor:
                cursor.executemany(statement, rows)
                return QueryResult(
                    status_code=QueryStatus.SUCCESS,
                    data={"rowcount": cursor.rowcount},
                )
        except Exception as exc:
            error = str(exc)
            status_code = (
                QueryStatus.CLIENT_ERROR
                if self._looks_like_client_error(error)
                else QueryStatus.SERVER_ERROR
            )
            return QueryResult(status_code=status_code, error=error)

    def close(self) -> None:
        if self.connection:
            self.connection.close()
            self.connection = None
            self.client = None
            print("Oracle connection closed.")

    def _looks_like_client_error(self, error: str) -> bool:
        lower = error.lower()
        return any(token in lower for token in ["syntax", "ora-009", "ora-040", "invalid"])

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
