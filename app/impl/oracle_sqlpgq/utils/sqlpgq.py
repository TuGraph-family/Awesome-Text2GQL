import re
from typing import Any, Dict, Iterable, List, Tuple

RESERVED_WORDS = {
    "ACCESS",
    "ADD",
    "ALL",
    "ALTER",
    "AND",
    "AS",
    "ASC",
    "BY",
    "CHECK",
    "COLUMN",
    "COMMENT",
    "CREATE",
    "DATE",
    "DELETE",
    "DESC",
    "DISTINCT",
    "DROP",
    "EDGE",
    "ENFORCED",
    "FETCH",
    "FROM",
    "GRAPH",
    "GROUP",
    "KEY",
    "LABEL",
    "MATCH",
    "NODE",
    "NOT",
    "NULL",
    "OFFSET",
    "OR",
    "ORDER",
    "PRIMARY",
    "PROPERTY",
    "REFERENCES",
    "RESOURCE",
    "SELECT",
    "SIZE",
    "TABLE",
    "USER",
    "VERTEX",
    "WHERE",
}


class OracleNameSanitizer:
    """Normalize framework labels/properties into Oracle-safe SQL identifiers."""

    _invalid = re.compile(r"[^A-Za-z0-9_$#]")

    @classmethod
    def clean(cls, name: str, fallback: str = "X") -> str:
        value = str(name or "").strip()
        value = cls._invalid.sub("_", value)
        value = re.sub(r"_+", "_", value)
        if not value:
            value = fallback
        if value[0].isdigit():
            value = f"{fallback}_{value}"
        return value[:128]

    @classmethod
    def quote(cls, name: str, fallback: str = "X") -> str:
        value = cls.clean(name, fallback=fallback).replace('"', '""')
        return f'"{value}"'

    @classmethod
    def alias(cls, name: str, fallback: str = "COL") -> str:
        value = cls.clean(name, fallback=fallback)
        if value.upper() in RESERVED_WORDS:
            value = f"{value}_VALUE"
        return value[:128]


class OracleTypeMapper:
    """Map framework/TuGraph-like scalar types to Oracle SQL column types."""

    TYPE_MAP = {
        "BOOL": "NUMBER(1)",
        "BOOLEAN": "NUMBER(1)",
        "INT8": "NUMBER(3)",
        "INT16": "NUMBER(5)",
        "INT32": "NUMBER(10)",
        "INT64": "NUMBER(19)",
        "INTEGER": "NUMBER(10)",
        "LONG": "NUMBER(19)",
        "FLOAT": "BINARY_FLOAT",
        "DOUBLE": "BINARY_DOUBLE",
        "DATE": "DATE",
        "DATETIME": "TIMESTAMP",
        "TIMESTAMP": "TIMESTAMP",
        "STRING": "VARCHAR2(4000)",
        "TEXT": "CLOB",
        "BLOB": "BLOB",
    }

    @classmethod
    def to_oracle(cls, type_name: str) -> str:
        return cls.TYPE_MAP.get(str(type_name or "STRING").upper(), "VARCHAR2(4000)")


def split_sql_statements(script: str) -> List[str]:
    """Split a simple SQL script on semicolons outside single/double quoted strings."""

    statements: List[str] = []
    current: List[str] = []
    in_single = False
    in_double = False
    i = 0
    while i < len(script):
        ch = script[i]
        current.append(ch)
        if ch == "'" and not in_double:
            if i + 1 < len(script) and script[i + 1] == "'":
                current.append(script[i + 1])
                i += 1
            else:
                in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == ";" and not in_single and not in_double:
            statement = "".join(current).strip().rstrip(";").strip()
            if statement:
                statements.append(statement)
            current = []
        i += 1

    tail = "".join(current).strip()
    if tail:
        statements.append(tail)
    return statements


def is_balanced_sql(text: str) -> bool:
    depth = 0
    in_single = False
    in_double = False
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "'" and not in_double:
            if i + 1 < len(text) and text[i + 1] == "'":
                i += 2
                continue
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif not in_single and not in_double:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth < 0:
                    return False
        i += 1
    return depth == 0 and not in_single and not in_double


def validate_graph_table_query(query: str) -> bool:
    normalized = " ".join(str(query or "").strip().split()).upper()
    if not (normalized.startswith("SELECT ") or normalized.startswith("WITH ")):
        return False
    required_tokens = ["FROM GRAPH_TABLE", " MATCH ", " COLUMNS "]
    return all(token in normalized for token in required_tokens) and is_balanced_sql(query)


def validate_property_graph_ddl(ddl: str) -> bool:
    normalized = " ".join(str(ddl or "").strip().split()).upper()
    required_tokens = [
        "CREATE",
        "PROPERTY GRAPH",
        "VERTEX TABLES",
        "EDGE TABLES",
    ]
    return all(token in normalized for token in required_tokens) and is_balanced_sql(ddl)


def property_list(properties: Iterable[Dict[str, Any]]) -> List[Tuple[str, str]]:
    return [(str(item.get("name", "")), str(item.get("type", "STRING"))) for item in properties]
