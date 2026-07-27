"""
Create and populate a scalable Oracle SQL/PGQ fraud/payments graph.

Required environment variables:
- ORACLE_DSN
- ORACLE_USER
- ORACLE_PASSWORD

This example is intentionally separate from the movie graph so SQL/PGQ corpus
generation can be tested across different graph domains.
"""

import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import random
from typing import Any

from app.core.schema.edge import Edge
from app.core.schema.node import Node
from app.core.schema.schema_graph import SchemaGraph
from app.core.validator.db_client import QueryStatus
from app.impl.oracle_sqlpgq.db_client.oracle_db_client import OracleDBClient
from app.impl.oracle_sqlpgq.schema.schema_parser import OracleSqlPgqSchemaParser


GRAPH_NAME = "TEXT2GQL_FRAUD_GRAPH"
ARTIFACT_DIR = Path("examples/Oracle_SQLPGQ_Instance")
BASE_NAME = GRAPH_NAME
Row = tuple[Any, ...]


@dataclass(frozen=True)
class FraudConfig:
    customers: int
    accounts: int
    merchants: int
    transactions: int
    devices: int
    cities: int
    seed: int
    batch_size: int


def env_int(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return parsed


def parse_args() -> FraudConfig:
    parser = argparse.ArgumentParser()
    parser.add_argument("--customers", type=positive_int, default=env_int("FRAUD_GRAPH_CUSTOMERS", 6))
    parser.add_argument("--accounts", type=positive_int, default=env_int("FRAUD_GRAPH_ACCOUNTS", 8))
    parser.add_argument("--merchants", type=positive_int, default=env_int("FRAUD_GRAPH_MERCHANTS", 6))
    parser.add_argument(
        "--transactions", type=positive_int, default=env_int("FRAUD_GRAPH_TRANSACTIONS", 24)
    )
    parser.add_argument("--devices", type=positive_int, default=env_int("FRAUD_GRAPH_DEVICES", 6))
    parser.add_argument("--cities", type=positive_int, default=env_int("FRAUD_GRAPH_CITIES", 4))
    parser.add_argument("--seed", type=int, default=env_int("FRAUD_GRAPH_DATA_SEED", 19))
    parser.add_argument(
        "--batch-size",
        type=positive_int,
        default=env_int("FRAUD_GRAPH_INSERT_BATCH_SIZE", 1000),
    )
    config = FraudConfig(**vars(parser.parse_args()))
    validate_config(config)
    return config


def validate_config(config: FraudConfig) -> None:
    minimums = {
        "customers": 4,
        "accounts": 4,
        "merchants": 4,
        "transactions": 8,
        "devices": 4,
        "cities": 4,
    }
    values = config.__dict__
    too_small = [
        f"{name}>={minimum} (got {values[name]})"
        for name, minimum in minimums.items()
        if values[name] < minimum
    ]
    if too_small:
        raise ValueError(
            "The fraud graph seed queries require these minimum sizes: "
            + ", ".join(too_small)
        )


def build_schema_graph() -> SchemaGraph:
    graph = SchemaGraph(GRAPH_NAME)
    graph.add_node(
        Node(
            label="CUSTOMER",
            primary="CUSTOMER_ID",
            properties=[
                {"name": "CUSTOMER_ID", "type": "INT64"},
                {"name": "NAME", "type": "STRING"},
                {"name": "RISK_SCORE", "type": "FLOAT"},
                {"name": "SEGMENT", "type": "STRING"},
            ],
        )
    )
    graph.add_node(
        Node(
            label="ACCOUNT",
            primary="ACCOUNT_ID",
            properties=[
                {"name": "ACCOUNT_ID", "type": "INT64"},
                {"name": "ACCOUNT_TYPE", "type": "STRING"},
                {"name": "BALANCE", "type": "FLOAT"},
                {"name": "OPENED_AT", "type": "DATETIME"},
            ],
        )
    )
    graph.add_node(
        Node(
            label="MERCHANT",
            primary="MERCHANT_ID",
            properties=[
                {"name": "MERCHANT_ID", "type": "INT64"},
                {"name": "NAME", "type": "STRING"},
                {"name": "CATEGORY", "type": "STRING"},
                {"name": "COUNTRY", "type": "STRING"},
            ],
        )
    )
    graph.add_node(
        Node(
            label="TRANSACTION",
            primary="TRANSACTION_ID",
            properties=[
                {"name": "TRANSACTION_ID", "type": "INT64"},
                {"name": "AMOUNT", "type": "FLOAT"},
                {"name": "STATUS", "type": "STRING"},
                {"name": "EVENT_TIME", "type": "DATETIME"},
                {"name": "CHANNEL", "type": "STRING"},
                {"name": "FRAUD_FLAG", "type": "BOOL"},
            ],
        )
    )
    graph.add_node(
        Node(
            label="DEVICE",
            primary="DEVICE_ID",
            properties=[
                {"name": "DEVICE_ID", "type": "INT64"},
                {"name": "DEVICE_TYPE", "type": "STRING"},
                {"name": "TRUSTED", "type": "BOOL"},
            ],
        )
    )
    graph.add_node(
        Node(
            label="CITY",
            primary="CITY_ID",
            properties=[
                {"name": "CITY_ID", "type": "INT64"},
                {"name": "NAME", "type": "STRING"},
                {"name": "COUNTRY", "type": "STRING"},
            ],
        )
    )
    graph.add_edge(
        Edge(
            label="OWNS",
            src_dst_list=[["CUSTOMER", "ACCOUNT"]],
            properties=[
                {"name": "OWNERSHIP_TYPE", "type": "STRING"},
                {"name": "SINCE", "type": "DATETIME"},
            ],
        )
    )
    graph.add_edge(
        Edge(
            label="INITIATED",
            src_dst_list=[["ACCOUNT", "TRANSACTION"]],
            properties=[
                {"name": "IP_ADDRESS", "type": "STRING"},
                {"name": "AUTH_METHOD", "type": "STRING"},
            ],
        )
    )
    graph.add_edge(
        Edge(
            label="PAID",
            src_dst_list=[["TRANSACTION", "MERCHANT"]],
            properties=[
                {"name": "PAYMENT_METHOD", "type": "STRING"},
                {"name": "APPROVAL_CODE", "type": "STRING"},
            ],
        )
    )
    graph.add_edge(
        Edge(
            label="USED_DEVICE",
            src_dst_list=[["TRANSACTION", "DEVICE"]],
            properties=[{"name": "DEVICE_CONFIDENCE", "type": "FLOAT"}],
        )
    )
    graph.add_edge(
        Edge(
            label="LIVES_IN",
            src_dst_list=[["CUSTOMER", "CITY"]],
            properties=[{"name": "SINCE", "type": "DATETIME"}],
        )
    )
    graph.add_edge(
        Edge(
            label="LOCATED_IN",
            src_dst_list=[["MERCHANT", "CITY"]],
            properties=[{"name": "ACTIVE", "type": "BOOL"}],
        )
    )
    return graph


def build_manifest() -> dict[str, Any]:
    return OracleSqlPgqSchemaParser(db_id=GRAPH_NAME).build_manifest(
        build_schema_graph(),
        graph_name=GRAPH_NAME,
    )


def write_artifacts(manifest: dict[str, Any]) -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    (ARTIFACT_DIR / f"{BASE_NAME}_oracle_schema.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (ARTIFACT_DIR / f"{BASE_NAME}_oracle_tables.sql").write_text(
        manifest["table_ddl"],
        encoding="utf-8",
    )
    (ARTIFACT_DIR / f"{BASE_NAME}_oracle_property_graph.sql").write_text(
        manifest["property_graph_ddl"],
        encoding="utf-8",
    )


def safe_execute(client: OracleDBClient, sql: str, ignore_errors: tuple[str, ...] = ()) -> None:
    result = client.execute_query(sql)
    if result.status_code == QueryStatus.SUCCESS:
        return
    if result.error and any(token in result.error for token in ignore_errors):
        return
    raise RuntimeError(f"Failed SQL:\n{sql}\n\nError:\n{result.error}")


def run_script(client: OracleDBClient, script: str) -> None:
    for result in client.execute_script(script):
        if result.status_code != QueryStatus.SUCCESS:
            raise RuntimeError(result.error)


def reset_objects(client: OracleDBClient, manifest: dict[str, Any]) -> None:
    safe_execute(
        client,
        f'DROP PROPERTY GRAPH "{GRAPH_NAME}"',
        ignore_errors=("ORA-42421", "ORA-04043", "ORA-00942"),
    )
    for table_name in reversed(manifest["load_order"]):
        safe_execute(
            client,
            f'DROP TABLE "{table_name}" CASCADE CONSTRAINTS PURGE',
            ignore_errors=("ORA-00942",),
        )


def insert_rows(
    client: OracleDBClient,
    statement: str,
    rows: list[Row],
    label: str,
    batch_size: int,
) -> None:
    for start in range(0, len(rows), batch_size):
        result = client.executemany(statement, rows[start : start + batch_size])
        if result.status_code != QueryStatus.SUCCESS:
            raise RuntimeError(f"Failed loading {label}: {result.error}")
    print(f"Loaded {len(rows)} rows into {label}")


def dt(days: int, hour: int = 9) -> datetime:
    return datetime(2025, 1, 1, hour, 0, 0) + timedelta(days=days)


def generate_rows(config: FraudConfig) -> dict[str, list[Row]]:
    rng = random.Random(config.seed)
    customer_names = ["Alice", "Bob", "Carol", "Daniel", "Eve", "Fatima", "Omar", "Lina"]
    segments = ["retail", "premium", "small_business", "student"]
    customers = []
    for index in range(config.customers):
        risk = [0.82, 0.35, 0.64, 0.91][index] if index < 4 else round(rng.random(), 3)
        name = customer_names[index] if index < len(customer_names) else f"Customer {index + 1}"
        customers.append((1 + index, name, risk, segments[index % len(segments)]))

    account_types = ["checking", "savings", "business", "wallet"]
    accounts = []
    owns = []
    for index in range(config.accounts):
        account_id = 1000 + index
        customer_id = 1 + index % config.customers
        accounts.append(
            (
                account_id,
                account_types[index % len(account_types)],
                round(250 + rng.random() * 25000, 2),
                dt(index, hour=8),
            )
        )
        owns.append((customer_id, account_id, "primary" if index % 3 else "joint", dt(index)))

    base_merchants = [
        ("ElectroHub", "Electronics", "US"),
        ("GroceryMart", "Grocery", "US"),
        ("TravelNow", "Travel", "FR"),
        ("CryptoX", "Crypto", "MA"),
        ("BookBarn", "Books", "UK"),
        ("HealthPlus", "Healthcare", "US"),
    ]
    merchants = []
    for index in range(config.merchants):
        if index < len(base_merchants):
            name, category, country = base_merchants[index]
        else:
            name, category, country = f"Merchant {index + 1}", "General", "US"
        merchants.append((2000 + index, name, category, country))

    device_types = ["mobile", "desktop", "tablet", "pos_terminal"]
    devices = []
    for index in range(config.devices):
        trusted = 0 if index in {1, 4} else 1
        devices.append((3000 + index, device_types[index % len(device_types)], trusted))

    base_cities = [
        ("Casablanca", "MA"),
        ("New York", "US"),
        ("Paris", "FR"),
        ("London", "UK"),
    ]
    cities = []
    for index in range(config.cities):
        if index < len(base_cities):
            name, country = base_cities[index]
        else:
            name, country = f"City {index + 1}", "US"
        cities.append((4000 + index, name, country))

    customer_cities = [
        (1 + index, 4000 + index % config.cities, dt(index + 30))
        for index in range(config.customers)
    ]
    merchant_cities = [
        (2000 + index, 4000 + index % config.cities, 1)
        for index in range(config.merchants)
    ]

    amount_cycle = [1299.99, 42.50, 860.00, 2200.00, 120.25, 510.75, 75.00, 1450.30]
    status_cycle = ["APPROVED", "APPROVED", "DECLINED", "APPROVED"]
    channel_cycle = ["online", "card", "mobile", "branch"]
    transactions = []
    initiated = []
    paid = []
    used_device = []
    for index in range(config.transactions):
        transaction_id = 5000 + index
        amount = amount_cycle[index % len(amount_cycle)]
        fraud_flag = 1 if index % 7 in {0, 3} else 0
        account_id = 1000 + index % config.accounts
        merchant_id = 2000 + index % config.merchants
        device_id = 3000 + index % config.devices
        event_time = dt(index, hour=10 + index % 10)
        channel = channel_cycle[index % len(channel_cycle)]
        transactions.append(
            (
                transaction_id,
                amount,
                status_cycle[index % len(status_cycle)],
                event_time,
                channel,
                fraud_flag,
            )
        )
        initiated.append(
            (
                account_id,
                transaction_id,
                f"10.0.{index % 255}.{(index * 17) % 255}",
                "otp" if index % 3 else "password",
            )
        )
        paid.append(
            (
                transaction_id,
                merchant_id,
                "card" if index % 2 else "wallet",
                f"APP{transaction_id}",
            )
        )
        used_device.append(
            (
                transaction_id,
                device_id,
                round(0.35 + rng.random() * 0.64, 3),
            )
        )

    return {
        "CUSTOMER": customers,
        "ACCOUNT": accounts,
        "MERCHANT": merchants,
        "TRANSACTION": transactions,
        "DEVICE": devices,
        "CITY": cities,
        "CUSTOMER_OWNS_ACCOUNT": owns,
        "ACCOUNT_INITIATED_TRANSACTION": initiated,
        "TRANSACTION_PAID_MERCHANT": paid,
        "TRANSACTION_USED_DEVICE_DEVICE": used_device,
        "CUSTOMER_LIVES_IN_CITY": customer_cities,
        "MERCHANT_LOCATED_IN_CITY": merchant_cities,
    }


def load_data(client: OracleDBClient, config: FraudConfig) -> None:
    rows = generate_rows(config)
    statements = {
        "CUSTOMER": 'INSERT INTO "CUSTOMER" ("CUSTOMER_ID", "NAME", "RISK_SCORE", "SEGMENT") VALUES (:1, :2, :3, :4)',
        "ACCOUNT": 'INSERT INTO "ACCOUNT" ("ACCOUNT_ID", "ACCOUNT_TYPE", "BALANCE", "OPENED_AT") VALUES (:1, :2, :3, :4)',
        "MERCHANT": 'INSERT INTO "MERCHANT" ("MERCHANT_ID", "NAME", "CATEGORY", "COUNTRY") VALUES (:1, :2, :3, :4)',
        "TRANSACTION": 'INSERT INTO "TRANSACTION" ("TRANSACTION_ID", "AMOUNT", "STATUS", "EVENT_TIME", "CHANNEL", "FRAUD_FLAG") VALUES (:1, :2, :3, :4, :5, :6)',
        "DEVICE": 'INSERT INTO "DEVICE" ("DEVICE_ID", "DEVICE_TYPE", "TRUSTED") VALUES (:1, :2, :3)',
        "CITY": 'INSERT INTO "CITY" ("CITY_ID", "NAME", "COUNTRY") VALUES (:1, :2, :3)',
        "CUSTOMER_OWNS_ACCOUNT": 'INSERT INTO "CUSTOMER_OWNS_ACCOUNT" ("SRC_ID", "DST_ID", "OWNERSHIP_TYPE", "SINCE") VALUES (:1, :2, :3, :4)',
        "ACCOUNT_INITIATED_TRANSACTION": 'INSERT INTO "ACCOUNT_INITIATED_TRANSACTION" ("SRC_ID", "DST_ID", "IP_ADDRESS", "AUTH_METHOD") VALUES (:1, :2, :3, :4)',
        "TRANSACTION_PAID_MERCHANT": 'INSERT INTO "TRANSACTION_PAID_MERCHANT" ("SRC_ID", "DST_ID", "PAYMENT_METHOD", "APPROVAL_CODE") VALUES (:1, :2, :3, :4)',
        "TRANSACTION_USED_DEVICE_DEVICE": 'INSERT INTO "TRANSACTION_USED_DEVICE_DEVICE" ("SRC_ID", "DST_ID", "DEVICE_CONFIDENCE") VALUES (:1, :2, :3)',
        "CUSTOMER_LIVES_IN_CITY": 'INSERT INTO "CUSTOMER_LIVES_IN_CITY" ("SRC_ID", "DST_ID", "SINCE") VALUES (:1, :2, :3)',
        "MERCHANT_LOCATED_IN_CITY": 'INSERT INTO "MERCHANT_LOCATED_IN_CITY" ("SRC_ID", "DST_ID", "ACTIVE") VALUES (:1, :2, :3)',
    }
    for table_name, statement in statements.items():
        insert_rows(client, statement, rows[table_name], table_name, config.batch_size)
    safe_execute(client, "COMMIT")


def print_config(config: FraudConfig) -> None:
    print("Fraud graph data size configuration:")
    for name, value in config.__dict__.items():
        print(f"  {name}: {value}")


def main() -> None:
    config = parse_args()
    manifest = build_manifest()
    write_artifacts(manifest)
    client = OracleDBClient(
        {
            "dsn": os.environ["ORACLE_DSN"],
            "user": os.environ["ORACLE_USER"],
            "password": os.environ["ORACLE_PASSWORD"],
        }
    )
    if not client.connection:
        raise RuntimeError("Oracle connection failed.")

    try:
        print_config(config)
        print(f"Resetting Oracle objects for {GRAPH_NAME}")
        reset_objects(client, manifest)
        print("Creating Oracle tables")
        run_script(client, manifest["table_ddl"])
        print("Inserting generated fraud sample rows")
        load_data(client, config)
        print("Creating Oracle SQL property graph")
        run_script(client, manifest["property_graph_ddl"])
        print(f"Ready: {GRAPH_NAME}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
