import os

import pytest

from app.core.validator.db_client import QueryStatus
from app.impl.oracle_sqlpgq.db_client.oracle_db_client import OracleDBClient, oracledb


pytestmark = pytest.mark.oracle


@pytest.mark.skipif(oracledb is None, reason="oracledb package is not installed")
@pytest.mark.skipif(
    not all(os.getenv(name) for name in ["ORACLE_DSN", "ORACLE_USER", "ORACLE_PASSWORD"]),
    reason="ORACLE_DSN, ORACLE_USER, and ORACLE_PASSWORD are required",
)
def test_oracle_db_client_live_smoke():
    client = OracleDBClient(
        {
            "dsn": os.environ["ORACLE_DSN"],
            "user": os.environ["ORACLE_USER"],
            "password": os.environ["ORACLE_PASSWORD"],
        }
    )
    try:
        result = client.execute_query("SELECT 1 AS VALUE FROM dual")
        assert result.status_code == QueryStatus.SUCCESS
        assert result.data == [{"VALUE": 1}]
    finally:
        client.close()

