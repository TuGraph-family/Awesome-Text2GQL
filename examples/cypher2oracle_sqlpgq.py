import argparse
import contextlib
import io
import json
from pathlib import Path
import re

from app.impl.oracle_sqlpgq.translator.oracle_sqlpgq_query_translator import (
    OracleSqlPgqQueryTranslator,
)
from app.impl.tugraph_cypher.ast_visitor.tugraph_cypher_ast_visitor import (
    TugraphCypherAstVisitor,
)
from app.impl.tugraph_cypher.translator.tugraph_cypher_query_translator import (
    TugraphCypherQueryTranslator as CypherTranslator,
)

SUPPORTED_SCOPE = (
    "Graph-IL subset: basic MATCH paths, simple property comparisons, RETURN items, "
    "aliases, aggregates, ORDER BY, SKIP, LIMIT, DISTINCT, and relationship hop ranges."
)


def cypher2oracle_sqlpgq(
    query: str,
    graph_name: str = "GRAPH",
    node_label_map: dict[str, list[str]] | None = None,
    edge_label_map: dict[str, list[str]] | None = None,
    property_type_map: dict[str, dict[str, str]] | None = None,
    node_primary_key_map: dict[str, str] | None = None,
    edge_primary_key_map: dict[str, str] | None = None,
    strict_property_validation: bool = False,
) -> tuple[str, str]:
    """Translate a supported Cypher query into Oracle SQL/PGQ GRAPH_TABLE syntax."""

    if _starts_with_optional_match(query):
        optional_query = _translate_standalone_optional_match(
            query,
            graph_name=graph_name,
            node_label_map=node_label_map,
            edge_label_map=edge_label_map,
            property_type_map=property_type_map,
            node_primary_key_map=node_primary_key_map,
            edge_primary_key_map=edge_primary_key_map,
            strict_property_validation=strict_property_validation,
        )
        if optional_query is not None:
            return optional_query
        return "Unable to Translate to Oracle SQL/PGQ", "Graph-IL Not Support"

    optional_null_query = _translate_optional_null_antijoin(
        query,
        graph_name=graph_name,
        node_label_map=node_label_map,
        edge_label_map=edge_label_map,
        property_type_map=property_type_map,
        node_primary_key_map=node_primary_key_map,
        edge_primary_key_map=edge_primary_key_map,
        strict_property_validation=strict_property_validation,
    )
    if optional_null_query is not None:
        return optional_null_query

    match_optional_with_query = _translate_match_optional_with(
        query,
        graph_name=graph_name,
        node_label_map=node_label_map,
        edge_label_map=edge_label_map,
        property_type_map=property_type_map,
        node_primary_key_map=node_primary_key_map,
        edge_primary_key_map=edge_primary_key_map,
        strict_property_validation=strict_property_validation,
    )
    if match_optional_with_query is not None:
        return match_optional_with_query

    union_query = _translate_union_query(
        query,
        graph_name=graph_name,
        node_label_map=node_label_map,
        edge_label_map=edge_label_map,
        property_type_map=property_type_map,
        node_primary_key_map=node_primary_key_map,
        edge_primary_key_map=edge_primary_key_map,
        strict_property_validation=strict_property_validation,
    )
    if union_query is not None:
        return union_query

    query_visitor = TugraphCypherAstVisitor()
    cypher_translator = CypherTranslator()
    oracle_translator = OracleSqlPgqQueryTranslator(
        graph_name=graph_name,
        node_label_map=node_label_map,
        edge_label_map=edge_label_map,
        property_type_map=property_type_map,
        node_primary_key_map=node_primary_key_map,
        edge_primary_key_map=edge_primary_key_map,
        strict_property_validation=strict_property_validation,
    )

    if not cypher_translator.grammar_check(query):
        return "Unable to Translate to Oracle SQL/PGQ", "Not Comply with OpenCypher"

    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        success, query_pattern = query_visitor.get_query_pattern(query)
    if not success:
        return "Unable to Translate to Oracle SQL/PGQ", "Graph-IL Not Support"

    try:
        sqlpgq_query = oracle_translator.translate(query_pattern)
    except Exception:
        return "Unable to Translate to Oracle SQL/PGQ", "Graph-IL Not Support"

    if oracle_translator.grammar_check(sqlpgq_query):
        return sqlpgq_query, "Graph-IL Translatable"

    return "Unable to Translate to Oracle SQL/PGQ", "No Related Oracle SQL/PGQ Standard"


def _translate_optional_null_antijoin(
    query: str,
    graph_name: str,
    node_label_map: dict[str, list[str]] | None,
    edge_label_map: dict[str, list[str]] | None,
    property_type_map: dict[str, dict[str, str]] | None,
    node_primary_key_map: dict[str, str] | None,
    edge_primary_key_map: dict[str, str] | None,
    strict_property_validation: bool,
) -> tuple[str, str] | None:
    match = re.fullmatch(
        r"\s*(?P<base>MATCH\b.+?)\s+OPTIONAL\s+MATCH\s+"
        r"(?P<optional>.+?)\s+WHERE\s+"
        r"(?P<null_var>[A-Za-z_][A-Za-z0-9_]*)\s+IS\s+NULL\s+"
        r"(?P<tail>RETURN\b.+)\s*",
        query,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return None
    optional_pattern = match.group("optional").strip()
    transformed = (
        f"{match.group('base').strip()} "
        f"WHERE NOT EXISTS({optional_pattern}) "
        f"{match.group('tail').strip()}"
    )
    return cypher2oracle_sqlpgq(
        transformed,
        graph_name=graph_name,
        node_label_map=node_label_map,
        edge_label_map=edge_label_map,
        property_type_map=property_type_map,
        node_primary_key_map=node_primary_key_map,
        edge_primary_key_map=edge_primary_key_map,
        strict_property_validation=strict_property_validation,
    )


def _translate_match_optional_with(
    query: str,
    graph_name: str,
    node_label_map: dict[str, list[str]] | None,
    edge_label_map: dict[str, list[str]] | None,
    property_type_map: dict[str, dict[str, str]] | None,
    node_primary_key_map: dict[str, str] | None,
    edge_primary_key_map: dict[str, str] | None,
    strict_property_validation: bool,
) -> tuple[str, str] | None:
    if not _is_supported_match_optional_with(query):
        return None
    optional_match = re.search(r"\bOPTIONAL\s+MATCH\b", query, flags=re.IGNORECASE)
    if not optional_match:
        return None
    base_part = query[: optional_match.start()].strip()
    optional_part = query[optional_match.start() :].strip()
    with_match = re.search(r"\bWITH\b", optional_part, flags=re.IGNORECASE)
    if not with_match:
        return None
    optional_pattern = optional_part[: with_match.start()]
    base_variables = _declared_cypher_variables(base_part)
    optional_variables = _declared_cypher_variables(optional_pattern)
    join_variables = [var for var in base_variables if var in optional_variables]
    if not join_variables:
        return "Unable to Translate to Oracle SQL/PGQ", "Graph-IL Not Support"

    transformed = f"{base_part} WITH {', '.join(base_variables)} {optional_part}"
    match_query = re.sub(
        r"\bOPTIONAL\s+MATCH\b",
        "MATCH",
        transformed,
        count=1,
        flags=re.IGNORECASE,
    )
    translated, category = cypher2oracle_sqlpgq(
        match_query,
        graph_name=graph_name,
        node_label_map=node_label_map,
        edge_label_map=edge_label_map,
        property_type_map=property_type_map,
        node_primary_key_map=node_primary_key_map,
        edge_primary_key_map=edge_primary_key_map,
        strict_property_validation=strict_property_validation,
    )
    if category != "Graph-IL Translatable":
        return "Unable to Translate to Oracle SQL/PGQ", category
    rewritten = _rewrite_optional_with_left_join(translated, join_variables)
    if rewritten is None:
        return "Unable to Translate to Oracle SQL/PGQ", "Graph-IL Not Support"
    if OracleSqlPgqQueryTranslator(graph_name=graph_name).grammar_check(rewritten):
        return rewritten, "Graph-IL Translatable"
    return "Unable to Translate to Oracle SQL/PGQ", "No Related Oracle SQL/PGQ Standard"


def _is_supported_match_optional_with(query: str) -> bool:
    normalized = " ".join(str(query or "").split())
    if _starts_with_optional_match(normalized):
        return False
    if len(re.findall(r"\bOPTIONAL\s+MATCH\b", normalized, flags=re.IGNORECASE)) != 1:
        return False
    if len(re.findall(r"\bWITH\b", normalized, flags=re.IGNORECASE)) != 1:
        return False
    return bool(
        re.search(
            r"^\s*MATCH\b.+\bOPTIONAL\s+MATCH\b.+\bWITH\b.+\bRETURN\b",
            normalized,
            flags=re.IGNORECASE,
        )
    )


def _declared_cypher_variables(fragment: str) -> list[str]:
    variables: list[str] = []
    for pattern in (
        r"\(\s*(?P<var>[A-Za-z_][A-Za-z0-9_]*)\s*(?::|[){])",
        r"\[\s*(?P<var>[A-Za-z_][A-Za-z0-9_]*)\s*(?::|[\]{])",
    ):
        for match in re.finditer(pattern, fragment or ""):
            variable = match.group("var")
            if variable not in variables:
                variables.append(variable)
    return variables


def _rewrite_optional_with_left_join(
    translated: str,
    carried_variables: list[str],
) -> str | None:
    rewritten = re.sub(
        r"(?P<indent>[ \t]*)FROM stage_2\n(?P=indent)JOIN stage_1 ON (?P<condition>[^\n]+)",
        r"\g<indent>FROM stage_1\n\g<indent>LEFT JOIN stage_2 ON \g<condition>",
        translated,
        count=1,
        flags=re.IGNORECASE,
    )
    if rewritten == translated:
        return None
    for variable in carried_variables:
        stage_2_alias = f"{variable}_VALUE"
        stage_1_alias = f"stage_1_{variable}_VALUE"
        rewritten = re.sub(
            rf"(?P<select>\bSELECT\s+){re.escape(stage_2_alias)}(?P<tail>\s*,)",
            rf"\g<select>stage_1.{stage_1_alias} AS {stage_2_alias}\g<tail>",
            rewritten,
            count=1,
            flags=re.IGNORECASE,
        )
        rewritten = _replace_group_by_token(
            rewritten,
            stage_2_alias,
            f"stage_1.{stage_1_alias}",
        )
    return rewritten


def _replace_group_by_token(sql: str, token: str, replacement: str) -> str:
    def replace_line(match: re.Match) -> str:
        body = match.group("body")
        parts = _split_top_level_commas(body)
        parts = [replacement if part.strip() == token else part.strip() for part in parts]
        return f"GROUP BY {', '.join(parts)}"

    return re.sub(
        r"GROUP BY (?P<body>[^\n]+)",
        replace_line,
        sql,
        flags=re.IGNORECASE,
    )


def _translate_optional_after_with_match(
    query: str,
    graph_name: str,
    node_label_map: dict[str, list[str]] | None,
    edge_label_map: dict[str, list[str]] | None,
    property_type_map: dict[str, dict[str, str]] | None,
    node_primary_key_map: dict[str, str] | None,
    edge_primary_key_map: dict[str, str] | None,
    strict_property_validation: bool,
) -> tuple[str, str] | None:
    if not _is_supported_optional_after_with_match(query):
        return None

    match_query = re.sub(
        r"\bOPTIONAL\s+MATCH\b",
        "MATCH",
        query,
        count=1,
        flags=re.IGNORECASE,
    )
    translated, category = cypher2oracle_sqlpgq(
        match_query,
        graph_name=graph_name,
        node_label_map=node_label_map,
        edge_label_map=edge_label_map,
        property_type_map=property_type_map,
        node_primary_key_map=node_primary_key_map,
        edge_primary_key_map=edge_primary_key_map,
        strict_property_validation=strict_property_validation,
    )
    if category != "Graph-IL Translatable":
        return "Unable to Translate to Oracle SQL/PGQ", category

    rewritten = re.sub(
        r"\nFROM stage_2\nJOIN stage_1 ON (?P<condition>[^\n]+)",
        r"\nFROM stage_1\nLEFT JOIN stage_2 ON \g<condition>",
        translated,
        count=1,
        flags=re.IGNORECASE,
    )
    if rewritten == translated:
        return "Unable to Translate to Oracle SQL/PGQ", "Graph-IL Not Support"
    if OracleSqlPgqQueryTranslator(graph_name=graph_name).grammar_check(rewritten):
        return rewritten, "Graph-IL Translatable"
    return "Unable to Translate to Oracle SQL/PGQ", "No Related Oracle SQL/PGQ Standard"


def _is_supported_optional_after_with_match(query: str) -> bool:
    normalized = " ".join(str(query or "").split())
    if _starts_with_optional_match(normalized):
        return False
    if len(re.findall(r"\bOPTIONAL\s+MATCH\b", normalized, flags=re.IGNORECASE)) != 1:
        return False
    if len(re.findall(r"\bWITH\b", normalized, flags=re.IGNORECASE)) != 1:
        return False
    if re.search(r"\bRETURN\s+count\s*\(\s*\*\s*\)", normalized, flags=re.IGNORECASE):
        return False
    return bool(
        re.search(
            r"\bMATCH\b.+\bWITH\b.+\bOPTIONAL\s+MATCH\b.+\bRETURN\b",
            normalized,
            flags=re.IGNORECASE,
        )
    )


def _translate_standalone_optional_match(
    query: str,
    graph_name: str,
    node_label_map: dict[str, list[str]] | None,
    edge_label_map: dict[str, list[str]] | None,
    property_type_map: dict[str, dict[str, str]] | None,
    node_primary_key_map: dict[str, str] | None,
    edge_primary_key_map: dict[str, str] | None,
    strict_property_validation: bool,
) -> tuple[str, str] | None:
    if not _is_supported_standalone_optional_match(query):
        return None

    match_query = re.sub(
        r"^\s*OPTIONAL\s+MATCH\b",
        "MATCH",
        query,
        count=1,
        flags=re.IGNORECASE,
    )
    translated, category = cypher2oracle_sqlpgq(
        match_query,
        graph_name=graph_name,
        node_label_map=node_label_map,
        edge_label_map=edge_label_map,
        property_type_map=property_type_map,
        node_primary_key_map=node_primary_key_map,
        edge_primary_key_map=edge_primary_key_map,
        strict_property_validation=strict_property_validation,
    )
    if category != "Graph-IL Translatable":
        return "Unable to Translate to Oracle SQL/PGQ", category

    wrapped = _wrap_standalone_optional_sql(translated)
    if wrapped is None:
        return "Unable to Translate to Oracle SQL/PGQ", "Graph-IL Not Support"
    if OracleSqlPgqQueryTranslator(graph_name=graph_name).grammar_check(wrapped):
        return wrapped, "Graph-IL Translatable"
    return "Unable to Translate to Oracle SQL/PGQ", "No Related Oracle SQL/PGQ Standard"


def _is_supported_standalone_optional_match(query: str) -> bool:
    normalized = " ".join(str(query or "").split())
    if not _starts_with_optional_match(normalized):
        return False
    if len(re.findall(r"\bOPTIONAL\s+MATCH\b", normalized, flags=re.IGNORECASE)) != 1:
        return False
    if re.search(r"\bWITH\b", normalized, flags=re.IGNORECASE):
        return False
    if re.search(r"\bRETURN\s+count\s*\(\s*\*\s*\)", normalized, flags=re.IGNORECASE):
        return False
    return True


def _starts_with_optional_match(query: str) -> bool:
    return bool(
        re.match(
            r"^\s*OPTIONAL\s+MATCH\b",
            str(query or ""),
            flags=re.IGNORECASE,
        )
    )


def _contains_optional_match(query: str) -> bool:
    return bool(
        re.search(
            r"\bOPTIONAL\s+MATCH\b",
            str(query or ""),
            flags=re.IGNORECASE,
        )
    )


def _wrap_standalone_optional_sql(translated: str) -> str | None:
    body, tail = _split_trailing_order_and_paging(translated)
    select_items = _top_level_select_items(body)
    if not select_items:
        return None

    output_aliases: list[str] = []
    fallback_items: list[str] = []
    if len(select_items) == 1 and select_items[0] == "*":
        output_aliases = _graph_table_column_aliases(body)
        fallback_items = [f"NULL AS {alias}" for alias in output_aliases]
        if not output_aliases:
            return None
    else:
        for item in select_items:
            alias = _select_item_alias(item)
            if alias is None:
                return None
            expression = _select_item_expression(item)
            if re.fullmatch(r"COUNT\s*\(\s*\*\s*\)", expression, flags=re.IGNORECASE):
                return None
            fallback_value = (
                "0" if re.match(r"COUNT\s*\(", expression, flags=re.IGNORECASE) else "NULL"
            )
            output_aliases.append(alias)
            fallback_items.append(f"{fallback_value} AS {alias}")

    final_projection = ", ".join(output_aliases)
    fallback_projection = ", ".join(fallback_items)
    return (
        "WITH optional_rows AS (\n"
        f"{_indent_sql(body)}\n"
        "),\n"
        "optional_result AS (\n"
        f"  SELECT {final_projection}\n"
        "  FROM optional_rows\n"
        "  UNION ALL\n"
        f"  SELECT {fallback_projection}\n"
        "  FROM DUAL\n"
        "  WHERE NOT EXISTS (SELECT 1 FROM optional_rows)\n"
        ")\n"
        f"SELECT {final_projection}\n"
        "FROM optional_result"
        f"{tail}"
    )


def _split_trailing_order_and_paging(sql: str) -> tuple[str, str]:
    indexes = [
        match.start()
        for pattern in (r"\nORDER\s+BY\b", r"\nOFFSET\b", r"\nFETCH\b")
        if (match := re.search(pattern, sql, flags=re.IGNORECASE))
    ]
    if not indexes:
        return sql.rstrip(), ""
    index = min(indexes)
    return sql[:index].rstrip(), sql[index:]


def _top_level_select_items(sql: str) -> list[str]:
    match = re.match(r"\s*SELECT\s+(?:DISTINCT\s+)?", sql, flags=re.IGNORECASE)
    if not match:
        return []
    from_match = re.search(r"\nFROM\b", sql[match.end() :], flags=re.IGNORECASE)
    if not from_match:
        return []
    select_body = sql[match.end() : match.end() + from_match.start()]
    return _split_top_level_commas(select_body)


def _select_item_alias(item: str) -> str | None:
    match = re.search(
        r"\bAS\s+([A-Za-z_][A-Za-z0-9_$#]*)\s*$",
        item,
        flags=re.IGNORECASE,
    )
    if match:
        return match.group(1)
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_$#]*", item.strip()):
        return item.strip()
    return None


def _select_item_expression(item: str) -> str:
    match = re.search(r"\bAS\b", item, flags=re.IGNORECASE)
    if not match:
        return item.strip()
    return item[: match.start()].strip()


def _translate_union_query(
    query: str,
    graph_name: str,
    node_label_map: dict[str, list[str]] | None,
    edge_label_map: dict[str, list[str]] | None,
    property_type_map: dict[str, dict[str, str]] | None,
    node_primary_key_map: dict[str, str] | None,
    edge_primary_key_map: dict[str, str] | None,
    strict_property_validation: bool,
) -> tuple[str, str] | None:
    branches, operators = _split_top_level_unions(query)
    if len(branches) == 1:
        return None

    translated_branches: list[str] = []
    branch_aliases: list[list[str]] = []
    for branch in branches:
        translated, category = cypher2oracle_sqlpgq(
            branch,
            graph_name=graph_name,
            node_label_map=node_label_map,
            edge_label_map=edge_label_map,
            property_type_map=property_type_map,
            node_primary_key_map=node_primary_key_map,
            edge_primary_key_map=edge_primary_key_map,
            strict_property_validation=strict_property_validation,
        )
        if category != "Graph-IL Translatable":
            return "Unable to Translate to Oracle SQL/PGQ", category
        aliases = _graph_table_column_aliases(translated)
        if not aliases:
            return "Unable to Translate to Oracle SQL/PGQ", "Graph-IL Not Support"
        translated_branches.append(translated)
        branch_aliases.append(aliases)

    output_aliases: list[str] = []
    for aliases in branch_aliases:
        for alias in aliases:
            if alias not in output_aliases:
                output_aliases.append(alias)

    sql_branches = [
        _wrap_union_branch(translated, aliases, output_aliases, index)
        for index, (translated, aliases) in enumerate(
            zip(translated_branches, branch_aliases, strict=True),
            start=1,
        )
    ]
    union_sql = sql_branches[0]
    for operator, branch_sql in zip(operators, sql_branches[1:], strict=True):
        union_sql += f"\n{operator}\n{branch_sql}"

    if OracleSqlPgqQueryTranslator(graph_name=graph_name).grammar_check(union_sql):
        return union_sql, "Graph-IL Translatable"
    return "Unable to Translate to Oracle SQL/PGQ", "No Related Oracle SQL/PGQ Standard"


def _wrap_union_branch(
    translated: str,
    branch_aliases: list[str],
    output_aliases: list[str],
    index: int,
) -> str:
    select_items = [
        alias if alias in branch_aliases else f"NULL AS {alias}" for alias in output_aliases
    ]
    return (
        "SELECT "
        + ", ".join(select_items)
        + f"\nFROM (\n{_indent_sql(translated)}\n) union_branch_{index}"
    )


def _indent_sql(sql: str) -> str:
    return "\n".join("  " + line for line in sql.splitlines())


def _graph_table_column_aliases(sql: str) -> list[str]:
    start = re.search(r"\bCOLUMNS\s*\(", sql, flags=re.IGNORECASE)
    if not start:
        return []
    index = start.end()
    depth = 1
    in_single = False
    in_double = False
    body_start = index
    while index < len(sql):
        char = sql[index]
        if char == "'" and not in_double:
            if index + 1 < len(sql) and sql[index + 1] == "'":
                index += 2
                continue
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double
        elif not in_single and not in_double:
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    return _projection_aliases(sql[body_start:index])
        index += 1
    return []


def _projection_aliases(columns_body: str) -> list[str]:
    projections = _split_top_level_commas(columns_body)
    aliases = []
    for projection in projections:
        match = re.search(
            r"\bAS\s+([A-Za-z_][A-Za-z0-9_$#]*)\s*$",
            projection.strip(),
            flags=re.IGNORECASE,
        )
        if not match:
            return []
        aliases.append(match.group(1))
    return aliases


def _split_top_level_commas(text: str) -> list[str]:
    parts: list[str] = []
    start = 0
    depth = 0
    in_single = False
    in_double = False
    index = 0
    while index < len(text):
        char = text[index]
        if char == "'" and not in_double:
            if index + 1 < len(text) and text[index + 1] == "'":
                index += 2
                continue
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double
        elif not in_single and not in_double:
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
            elif char == "," and depth == 0:
                parts.append(text[start:index].strip())
                start = index + 1
        index += 1
    tail = text[start:].strip()
    if tail:
        parts.append(tail)
    return parts


def _split_top_level_unions(query: str) -> tuple[list[str], list[str]]:
    branches: list[str] = []
    operators: list[str] = []
    start = 0
    index = 0
    depth = 0
    in_single = False
    in_double = False
    in_backtick = False
    while index < len(query):
        char = query[index]
        if char == "`" and not in_single and not in_double:
            in_backtick = not in_backtick
            index += 1
            continue
        if char == "'" and not in_double and not in_backtick:
            if index + 1 < len(query) and query[index + 1] == "'":
                index += 2
                continue
            in_single = not in_single
            index += 1
            continue
        if char == '"' and not in_single and not in_backtick:
            in_double = not in_double
            index += 1
            continue
        if in_single or in_double or in_backtick:
            index += 1
            continue
        if char in "([{":
            depth += 1
            index += 1
            continue
        if char in ")]}":
            depth -= 1
            index += 1
            continue
        if depth == 0 and _keyword_at(query, index, "UNION"):
            operator, end = _union_operator_at(query, index)
            branches.append(query[start:index].strip())
            operators.append(operator)
            start = end
            index = end
            continue
        index += 1
    if not operators:
        return [query], []
    branches.append(query[start:].strip())
    if any(not branch for branch in branches):
        return [query], []
    return branches, operators


def _union_operator_at(query: str, index: int) -> tuple[str, int]:
    end = index + len("UNION")
    while end < len(query) and query[end].isspace():
        end += 1
    if _keyword_at(query, end, "ALL"):
        return "UNION ALL", end + len("ALL")
    return "UNION", end


def _keyword_at(text: str, index: int, keyword: str) -> bool:
    end = index + len(keyword)
    if text[index:end].upper() != keyword:
        return False
    before = text[index - 1] if index > 0 else ""
    after = text[end] if end < len(text) else ""
    return not (_is_identifier_char(before) or _is_identifier_char(after))


def _is_identifier_char(char: str) -> bool:
    return bool(char and (char.isalnum() or char in "_$#"))


def _translate_queries(queries: list[str], graph_name: str) -> list[dict[str, str]]:
    output_query_list = []
    for query in queries:
        translated_query, category = cypher2oracle_sqlpgq(query, graph_name=graph_name)
        output_query_list.append(
            {
                "cypher": query,
                "oracle_sqlpgq": translated_query,
                "category": category,
            }
        )
    return output_query_list


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Translate supported Cypher queries into Oracle SQL/PGQ GRAPH_TABLE syntax. "
            f"Supported scope: {SUPPORTED_SCOPE}"
        )
    )
    parser.add_argument("--query", help="Single Cypher query to translate.")
    parser.add_argument("--input", type=Path, help="JSON file containing a list of Cypher queries.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("test_oracle_sqlpgq_query.json"),
        help="Output JSON file when --input is used.",
    )
    parser.add_argument("--graph-name", default="GRAPH", help="Oracle property graph name.")
    args = parser.parse_args()

    if args.query:
        translated_query, category = cypher2oracle_sqlpgq(args.query, graph_name=args.graph_name)
        print(json.dumps({"query": translated_query, "category": category}, indent=2))
        return

    if not args.input:
        parser.error("Provide either --query or --input.")

    with open(args.input, encoding="utf-8") as file:
        query_list = json.load(file)

    output_query_list = _translate_queries(query_list, graph_name=args.graph_name)
    with open(args.output, "w", encoding="utf-8") as file:
        json.dump(output_query_list, file, ensure_ascii=False, indent=4)


if __name__ == "__main__":
    main()
