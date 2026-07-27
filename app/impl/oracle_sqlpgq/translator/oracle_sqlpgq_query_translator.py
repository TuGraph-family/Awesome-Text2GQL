from collections import Counter
import re
from typing import Dict, Iterable, List, Tuple

from app.core.clauses.clause import Clause
from app.core.clauses.match_clause import EdgePattern, MatchClause, NodePattern, PathPattern
from app.core.clauses.return_clause import ReturnBody, ReturnClause, ReturnItem, SortItem
from app.core.clauses.where_clause import CompareExpression, WhereClause
from app.core.clauses.with_clause import WithClause
from app.core.translator.query_translator import QueryTranslator
from app.impl.oracle_sqlpgq.utils.sqlpgq import (
    OracleNameSanitizer,
    validate_graph_table_query,
    validate_property_graph_ddl,
)


class OracleSqlPgqQueryTranslator(QueryTranslator):
    """Translate the framework's graph-query IR into Oracle SQL/PGQ."""

    AGGREGATE_FUNCTIONS = {"COUNT", "AVG", "SUM", "MIN", "MAX"}

    def __init__(
        self,
        graph_name: str = "GRAPH",
        node_label_map: Dict[str, List[str]] | None = None,
        edge_label_map: Dict[str, List[str]] | None = None,
        property_type_map: Dict[str, Dict[str, str]] | None = None,
        node_primary_key_map: Dict[str, str] | None = None,
        edge_primary_key_map: Dict[str, str] | None = None,
        strict_property_validation: bool = False,
    ):
        self.graph_name = graph_name
        self.node_label_map = self._normalize_label_map(node_label_map or {})
        self.edge_label_map = self._normalize_label_map(edge_label_map or {})
        self.property_type_map = property_type_map or {}
        self.node_primary_key_map = node_primary_key_map or {}
        self.edge_primary_key_map = edge_primary_key_map or {}
        self.strict_property_validation = strict_property_validation
        self._var_kinds: Dict[str, str] = {}
        self._var_sql_names: Dict[str, str] = {}
        self._var_labels: Dict[str, str] = {}
        self._path_variables: Dict[str, List[Tuple[str, str]]] = {}
        self._path_variable_has_quantifier: Dict[str, bool] = {}
        self._path_variable_quantified_edges: Dict[str, set[str]] = {}
        self._var_property_redirects: Dict[Tuple[str, str], str] = {}
        self._reserved_variables: set[str] = set()
        self._pattern_where_expressions: List[str] = []
        self._auto_node_index = 0
        self._auto_edge_index = 0

    def _normalize_label_map(self, label_map: Dict[str, List[str]]) -> Dict[str, List[str]]:
        normalized: Dict[str, List[str]] = {}
        for source, targets in label_map.items():
            values = list(targets or [])
            normalized[source] = values
            normalized.setdefault(str(source).lower(), values)
            clean_source = OracleNameSanitizer.clean(source)
            normalized.setdefault(clean_source, values)
            normalized.setdefault(clean_source.lower(), values)
        return normalized

    def grammar_check(self, query: str) -> bool:
        normalized = " ".join(str(query or "").strip().split()).upper()
        if "CREATE" in normalized and "PROPERTY GRAPH" in normalized:
            return validate_property_graph_ddl(query)
        return validate_graph_table_query(query)

    def translate(self, query_pattern: List[Clause]) -> str:
        self._reset()
        if any(isinstance(clause, MatchClause) and clause.optional for clause in query_pattern):
            return self._translate_optional_match(query_pattern)
        if any(isinstance(clause, WithClause) for clause in query_pattern):
            return self._translate_supported_with(query_pattern)
        match_clauses: List[MatchClause] = []
        where_expressions: List[CompareExpression] = []
        return_body: ReturnBody | None = None
        distinct = False

        for clause in query_pattern:
            if isinstance(clause, MatchClause):
                match_clauses.append(clause)
            elif isinstance(clause, WhereClause):
                where_expressions.extend(self._as_compare_list(clause.compare_expression_list))
            elif isinstance(clause, ReturnClause):
                return_body = clause.return_body
                distinct = clause.distinct
            elif isinstance(clause, WithClause):
                if return_body is None:
                    return_body = clause.return_body
                where_expressions.extend(self._as_compare_list(clause.compare_expression_list))

        if not match_clauses:
            raise ValueError("Oracle SQL/PGQ translation requires at least one MatchClause.")

        match_parts = [self._translate_match_clause(clause) for clause in match_clauses]
        pattern_predicates, where_expressions = self._extract_pattern_predicates(where_expressions)
        return_pattern_predicates = self._return_pattern_predicates(return_body)
        if return_pattern_predicates:
            return self._translate_return_pattern_predicate_cte(
                match_parts,
                where_expressions,
                return_body,
                distinct,
                return_pattern_predicates,
            )
        if pattern_predicates:
            return self._translate_pattern_predicate_cte(
                match_parts,
                where_expressions,
                return_body,
                distinct,
                pattern_predicates,
            )
        graph_table_parts = [
            OracleNameSanitizer.quote(self.graph_name, fallback="GRAPH"),
            "MATCH " + ", ".join(match_parts),
        ]

        where_parts = self._where_parts(where_expressions)
        if where_parts:
            graph_table_parts.append("WHERE " + " AND ".join(where_parts))

        aggregate_query = self._has_aggregate(return_body)
        hidden_sort_aliases = self._hidden_sort_aliases(return_body, aggregate_query)
        graph_table_parts.append(
            f"COLUMNS ({self._translate_columns(return_body, aggregate_query)})"
        )

        if return_body is not None and distinct and hidden_sort_aliases and not aggregate_query:
            visible_aliases = [
                OracleNameSanitizer.alias(alias)
                for alias in self._resolved_return_aliases(return_body)
            ]
            hidden_aliases = [OracleNameSanitizer.alias(alias) for alias in hidden_sort_aliases]
            inner_select = (
                "SELECT DISTINCT " + ", ".join([*visible_aliases, *hidden_aliases]) + "\n"
                f"FROM GRAPH_TABLE (\n  {' '.join(graph_table_parts)}\n) gt"
            )
            query = (
                "SELECT "
                + ", ".join(visible_aliases)
                + "\nFROM (\n"
                + self._indent_sql(inner_select)
                + "\n) distinct_rows"
            )
            query += self._outer_group_order_and_paging(return_body, aggregate_query)
            return query

        select_keyword = self._outer_select(
            return_body,
            distinct,
            aggregate_query,
            hidden_sort_aliases,
        )
        query = f"{select_keyword}\nFROM GRAPH_TABLE (\n  {' '.join(graph_table_parts)}\n) gt"

        if return_body is not None:
            query += self._outer_group_order_and_paging(return_body, aggregate_query)

        return query

    def _extract_pattern_predicates(
        self,
        where_expressions: List[CompareExpression],
    ) -> Tuple[List[Tuple[bool, str]], List[CompareExpression]]:
        predicates: List[Tuple[bool, str]] = []
        residual: List[CompareExpression] = []
        for expression in where_expressions:
            raw_expression = getattr(expression, "raw_expression", "")
            raw_predicates, raw_residual = self._extract_raw_path_predicate_parts(
                raw_expression or "",
            )
            if raw_predicates:
                predicates.extend(raw_predicates)
                if raw_residual:
                    residual.append(CompareExpression("", "", "raw", "", raw_residual))
                continue
            match = re.fullmatch(
                r"\s*(?P<not>NOT\s+)?EXISTS\s*\(\s*(?P<pattern>\(.+\))\s*\)\s*",
                raw_expression or "",
                flags=re.IGNORECASE | re.DOTALL,
            )
            if match:
                predicates.append((bool(match.group("not")), match.group("pattern")))
                continue
            residual.append(expression)
        return predicates, residual

    def _extract_raw_path_predicate_parts(
        self,
        raw_expression: str,
    ) -> Tuple[List[Tuple[bool, str]], str]:
        if not raw_expression:
            return [], ""
        predicates: List[Tuple[bool, str]] = []
        residual_parts: List[str] = []
        for part in self._split_top_level_and(raw_expression):
            exists_match = re.fullmatch(
                r"\s*(?P<not>NOT\s+)?EXISTS\s*\(\s*(?P<pattern>\(.+\))\s*\)\s*",
                part,
                flags=re.IGNORECASE | re.DOTALL,
            )
            if exists_match:
                predicates.append((bool(exists_match.group("not")), exists_match.group("pattern")))
                continue
            match = re.fullmatch(
                r"\s*(?P<not>NOT\s+)?(?P<pattern>"
                r"\([^()]*\)\s*"
                r"(?:(?:<-\[[^\]]*\]-)|(?:-\[[^\]]*\]->)|(?:-\[[^\]]*\]-))\s*"
                r"\([^()]*\)"
                r"(?:\s*(?:(?:<-\[[^\]]*\]-)|(?:-\[[^\]]*\]->)|(?:-\[[^\]]*\]-))\s*"
                r"\([^()]*\))*"
                r")\s*",
                part,
                flags=re.IGNORECASE | re.DOTALL,
            )
            if match:
                predicates.append((bool(match.group("not")), match.group("pattern")))
            else:
                residual_parts.append(part)
        return predicates, " AND ".join(residual_parts)

    def _split_top_level_and(self, expression: str) -> List[str]:
        parts: List[str] = []
        start = 0
        depth = 0
        in_single = False
        in_double = False
        index = 0
        while index < len(expression):
            char = expression[index]
            if char == "'" and not in_double:
                in_single = not in_single
                index += 1
                continue
            if char == '"' and not in_single:
                in_double = not in_double
                index += 1
                continue
            if in_single or in_double:
                index += 1
                continue
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
            elif (
                depth == 0
                and expression[index : index + 3].upper() == "AND"
                and (index == 0 or not expression[index - 1].isalnum())
                and (index + 3 == len(expression) or not expression[index + 3].isalnum())
            ):
                parts.append(expression[start:index].strip())
                start = index + 3
                index += 3
                continue
            index += 1
        tail = expression[start:].strip()
        if tail:
            parts.append(tail)
        return parts

    def _return_pattern_predicates(
        self,
        return_body: ReturnBody | None,
    ) -> Dict[int, Tuple[bool, str]]:
        if return_body is None:
            return {}
        predicates: Dict[int, Tuple[bool, str]] = {}
        for index, item in enumerate(return_body.return_item_list):
            match = re.fullmatch(
                r"\s*(?P<not>NOT\s+)?EXISTS\s*\(\s*(?P<pattern>\(.+\))\s*\)\s*",
                item.expression or "",
                flags=re.IGNORECASE | re.DOTALL,
            )
            if match:
                predicates[index] = (bool(match.group("not")), match.group("pattern"))
        return predicates

    def _translate_optional_match(self, query_pattern: List[Clause]) -> str:
        optional_indexes = [
            index
            for index, clause in enumerate(query_pattern)
            if isinstance(clause, MatchClause) and clause.optional
        ]
        if len(optional_indexes) != 1:
            raise ValueError("Only one OPTIONAL MATCH clause is supported.")

        optional_index = optional_indexes[0]
        if optional_index == 0:
            raise ValueError("Standalone OPTIONAL MATCH is not supported by Graph IR translation.")

        if any(isinstance(clause, MatchClause) for clause in query_pattern[optional_index + 1 :]):
            raise ValueError("OPTIONAL MATCH must be the final MATCH stage.")

        before_optional = query_pattern[:optional_index]
        if not any(isinstance(clause, MatchClause) for clause in before_optional):
            raise ValueError("OPTIONAL MATCH requires a preceding MATCH.")

        if any(isinstance(clause, WithClause) for clause in before_optional):
            return self._translate_supported_with(query_pattern)

        carried_variables = sorted(
            self._declared_variables_in_match_clauses(
                [clause for clause in before_optional if isinstance(clause, MatchClause)]
            )
        )
        if not carried_variables:
            raise ValueError("OPTIONAL MATCH requires named variables to carry forward.")

        synthetic_with = WithClause(
            ReturnBody(
                [
                    ReturnItem(
                        symbolic_name=variable,
                        property="",
                        alias="",
                        function_name="",
                        expression=variable,
                    )
                    for variable in carried_variables
                ],
                [],
            ),
            [],
            False,
        )
        return self._translate_supported_with(
            [*before_optional, synthetic_with, *query_pattern[optional_index:]]
        )

    def _translate_return_pattern_predicate_cte(
        self,
        match_parts: List[str],
        where_expressions: List[CompareExpression],
        return_body: ReturnBody,
        distinct: bool,
        return_pattern_predicates: Dict[int, Tuple[bool, str]],
    ) -> str:
        if self._has_aggregate(return_body):
            raise ValueError("Aggregate RETURN pattern predicates are not supported.")
        outer_variables = set(self._var_kinds)
        parsed_predicates = {}
        correlated_variables = set()
        for index, (negated, pattern) in return_pattern_predicates.items():
            path = self._parse_pattern_predicate_path(pattern)
            variables = self._path_pattern_variables(path) & outer_variables
            if not variables:
                raise ValueError("RETURN pattern predicate requires outer correlation.")
            correlated_variables.update(variables)
            parsed_predicates[index] = (negated, path, variables)

        visible_items = [
            item
            for index, item in enumerate(return_body.return_item_list)
            if index not in return_pattern_predicates
        ]
        base_return_body = self._return_body_with_join_variables(
            ReturnBody(
                visible_items, return_body.sort_item_list, return_body.skip, return_body.limit
            ),
            sorted(correlated_variables),
        )
        graph_table_parts = [
            OracleNameSanitizer.quote(self.graph_name, fallback="GRAPH"),
            "MATCH " + ", ".join(match_parts),
        ]
        where_parts = self._where_parts(where_expressions)
        if where_parts:
            graph_table_parts.append("WHERE " + " AND ".join(where_parts))
        graph_table_parts.append(f"COLUMNS ({self._translate_columns(base_return_body)})")
        base_query = f"SELECT *\nFROM GRAPH_TABLE (\n  {' '.join(graph_table_parts)}\n) gt"

        select_items = []
        for index, item in enumerate(return_body.return_item_list):
            alias = OracleNameSanitizer.alias(
                item.alias
                or item.property
                or self._default_expression_alias(item.symbolic_name, item.expression)
            )
            if index in parsed_predicates:
                negated, path, variables = parsed_predicates[index]
                predicate = self._pattern_predicate_sql(negated, path, variables)
                select_items.append(f"CASE WHEN {predicate} THEN 1 ELSE 0 END AS {alias}")
            else:
                select_items.append(OracleNameSanitizer.alias(alias))
        keyword = "SELECT DISTINCT" if distinct else "SELECT"
        query = (
            "WITH base AS (\n"
            f"{self._indent_sql(base_query)}\n"
            ")\n"
            f"{keyword} " + ", ".join(select_items) + "\n"
            "FROM base"
        )
        query += self._outer_order_and_paging_for_with(return_body, include_group_by=False)
        return query

    def _translate_pattern_predicate_cte(
        self,
        match_parts: List[str],
        where_expressions: List[CompareExpression],
        return_body: ReturnBody | None,
        distinct: bool,
        pattern_predicates: List[Tuple[bool, str]],
    ) -> str:
        outer_variables = set(self._var_kinds)
        correlated_variables = set()
        parsed_predicates = []
        for negated, pattern in pattern_predicates:
            path = self._parse_pattern_predicate_path(pattern)
            variables = self._path_pattern_variables(path) & outer_variables
            if not variables:
                raise ValueError("Pattern predicate requires correlation to the outer MATCH.")
            correlated_variables.update(variables)
            parsed_predicates.append((negated, path, variables))

        aggregate_query = self._has_aggregate(return_body)
        base_return_body = self._return_body_with_join_variables(
            return_body or ReturnBody([], []),
            sorted(correlated_variables),
        )
        graph_table_parts = [
            OracleNameSanitizer.quote(self.graph_name, fallback="GRAPH"),
            "MATCH " + ", ".join(match_parts),
        ]
        where_parts = self._where_parts(where_expressions)
        if where_parts:
            graph_table_parts.append("WHERE " + " AND ".join(where_parts))
        graph_table_parts.append(
            f"COLUMNS ({self._translate_columns(base_return_body, aggregate_query)})"
        )
        base_query = f"SELECT *\nFROM GRAPH_TABLE (\n  {' '.join(graph_table_parts)}\n) gt"

        final_select = (
            self._outer_select(return_body, distinct, aggregate_query)
            if aggregate_query
            else self._visible_outer_select(return_body, distinct)
        )
        query = f"WITH base AS (\n{self._indent_sql(base_query)}\n)\n{final_select}\nFROM base"
        filters = [
            self._pattern_predicate_sql(negated, path, variables)
            for negated, path, variables in parsed_predicates
        ]
        if filters:
            query += "\nWHERE " + " AND ".join(filters)
        if return_body is not None:
            query += self._outer_group_order_and_paging(return_body, aggregate_query)
        return query

    def _visible_outer_select(
        self,
        return_body: ReturnBody | None,
        distinct: bool,
    ) -> str:
        if return_body is None or not return_body.return_item_list:
            return "SELECT DISTINCT *" if distinct else "SELECT *"
        keyword = "SELECT DISTINCT" if distinct else "SELECT"
        return f"{keyword} " + ", ".join(
            OracleNameSanitizer.alias(alias) for alias in self._resolved_return_aliases(return_body)
        )

    def _pattern_predicate_sql(
        self,
        negated: bool,
        path: PathPattern,
        variables: set[str],
    ) -> str:
        translator = OracleSqlPgqQueryTranslator(
            graph_name=self.graph_name,
            node_label_map=self.node_label_map,
            edge_label_map=self.edge_label_map,
            property_type_map=self.property_type_map,
            node_primary_key_map=self.node_primary_key_map,
            edge_primary_key_map=self.edge_primary_key_map,
            strict_property_validation=self.strict_property_validation,
        )
        match_part = translator._translate_path_pattern(path)
        inline_where = ""
        if translator._pattern_where_expressions:
            inline_where = "WHERE " + " AND ".join(translator._pattern_where_expressions) + " "
        return_body = ReturnBody(
            [
                ReturnItem(
                    symbolic_name=variable,
                    property="",
                    alias=translator._element_projection_alias(variable),
                    function_name="",
                    expression=variable,
                )
                for variable in sorted(variables)
            ],
            [],
        )
        subquery = (
            "SELECT 1\n"
            "FROM GRAPH_TABLE (\n"
            f"  {OracleNameSanitizer.quote(self.graph_name, fallback='GRAPH')} "
            f"MATCH {match_part} "
            f"{inline_where}"
            f"COLUMNS ({translator._translate_columns(return_body)})\n"
            ") pp\n"
            "WHERE "
            + " AND ".join(
                f"pp.{translator._element_projection_alias(variable)} = "
                f"base.{self._element_projection_alias(variable)}"
                for variable in sorted(variables)
            )
        )
        operator = "NOT EXISTS" if negated else "EXISTS"
        return f"{operator} (\n{self._indent_sql(subquery)}\n)"

    def _pattern_predicate_relation_sql(
        self,
        path: PathPattern,
        variables: set[str],
    ) -> str:
        translator = OracleSqlPgqQueryTranslator(
            graph_name=self.graph_name,
            node_label_map=self.node_label_map,
            edge_label_map=self.edge_label_map,
            property_type_map=self.property_type_map,
            node_primary_key_map=self.node_primary_key_map,
            edge_primary_key_map=self.edge_primary_key_map,
            strict_property_validation=self.strict_property_validation,
        )
        match_part = translator._translate_path_pattern(path)
        inline_where = ""
        if translator._pattern_where_expressions:
            inline_where = "WHERE " + " AND ".join(translator._pattern_where_expressions) + " "
        return_body = ReturnBody(
            [
                ReturnItem(
                    symbolic_name=variable,
                    property="",
                    alias=translator._element_projection_alias(variable),
                    function_name="",
                    expression=variable,
                )
                for variable in sorted(variables)
            ],
            [],
        )
        return (
            "SELECT DISTINCT *\n"
            "FROM GRAPH_TABLE (\n"
            f"  {OracleNameSanitizer.quote(self.graph_name, fallback='GRAPH')} "
            f"MATCH {match_part} "
            f"{inline_where}"
            f"COLUMNS ({translator._translate_columns(return_body)})\n"
            ") pp"
        )

    def _parse_pattern_predicate_path(self, pattern: str) -> PathPattern:
        text = self._unwrap_pattern_predicate_path(pattern)
        index = 0
        nodes: List[NodePattern] = []
        edges: List[EdgePattern] = []
        node, index = self._parse_pattern_predicate_node(text, index)
        nodes.append(node)
        while index < len(text):
            edge, index = self._parse_pattern_predicate_edge(text, index)
            edges.append(edge)
            node, index = self._parse_pattern_predicate_node(text, index)
            nodes.append(node)
        return PathPattern(nodes, edges, "")

    def _unwrap_pattern_predicate_path(self, pattern: str) -> str:
        text = str(pattern or "").strip()
        if not (text.startswith("((") and text.endswith("))")):
            return text
        inner = text[1:-1].strip()
        if re.match(
            r"^\([^()]*\)\s*(?:<-\[[^\]]*\]-|-\[[^\]]*\]->|-\[[^\]]*\]-)",
            inner,
            flags=re.DOTALL,
        ):
            return inner
        return text

    def _parse_pattern_predicate_node(
        self,
        text: str,
        index: int,
    ) -> Tuple[NodePattern, int]:
        index = self._skip_spaces(text, index)
        if index >= len(text) or text[index] != "(":
            raise ValueError("Pattern predicate expected a node pattern.")
        end = text.find(")", index)
        if end == -1:
            raise ValueError("Pattern predicate node is missing a closing parenthesis.")
        body = text[index + 1 : end].strip()
        variable, label, property_maps = self._parse_pattern_predicate_body(body)
        return (
            NodePattern(
                variable,
                label,
                property_maps,
            ),
            self._skip_spaces(text, end + 1),
        )

    def _parse_pattern_predicate_edge(
        self,
        text: str,
        index: int,
    ) -> Tuple[EdgePattern, int]:
        index = self._skip_spaces(text, index)
        direction = "both"
        if text.startswith("<-[", index):
            direction = "left"
            body_start = index + 3
            close = text.find("]-", body_start)
            next_index = close + 2
        elif text.startswith("-[", index):
            body_start = index + 2
            close = text.find("]", body_start)
            if close == -1:
                raise ValueError("Pattern predicate edge is missing a closing bracket.")
            if text.startswith("->", close + 1):
                direction = "right"
                next_index = close + 3
            elif text.startswith("-", close + 1):
                next_index = close + 2
            else:
                raise ValueError("Pattern predicate edge is missing a direction suffix.")
        else:
            raise ValueError("Pattern predicate expected an edge pattern.")
        if close == -1:
            raise ValueError("Pattern predicate edge is missing a closing bracket.")
        body = text[body_start:close].strip()
        variable, label, property_maps = self._parse_pattern_predicate_body(body)
        return (
            EdgePattern(
                variable,
                label,
                property_maps,
                direction,
                (-1, -1),
            ),
            self._skip_spaces(text, next_index),
        )

    def _parse_pattern_predicate_body(
        self,
        body: str,
    ) -> Tuple[str, str, List[Tuple[str, str]]]:
        body, property_maps = self._extract_pattern_predicate_property_map(body)
        variable = ""
        label = ""
        if ":" in body:
            variable, label = body.split(":", 1)
        else:
            variable = body
        return (
            self._clean_pattern_identifier(variable),
            self._clean_pattern_identifier(label),
            property_maps,
        )

    def _extract_pattern_predicate_property_map(
        self,
        body: str,
    ) -> Tuple[str, List[Tuple[str, str]]]:
        start = str(body or "").find("{")
        if start == -1:
            return body, []
        end = self._matching_brace_index(body, start)
        if end == -1:
            return body, []
        map_body = body[start + 1 : end]
        property_maps = []
        for item in self._split_top_level_commas(map_body):
            if ":" not in item:
                continue
            property_name, property_value = item.split(":", 1)
            property_maps.append(
                (
                    self._clean_pattern_identifier(property_name),
                    property_value.strip(),
                )
            )
        return (body[:start] + body[end + 1 :]).strip(), property_maps

    def _matching_brace_index(self, text: str, start: int) -> int:
        depth = 0
        in_single = False
        in_double = False
        index = start
        while index < len(text):
            char = text[index]
            if char == "'" and not in_double:
                in_single = not in_single
                index += 1
                continue
            if char == '"' and not in_single:
                in_double = not in_double
                index += 1
                continue
            if in_single or in_double:
                index += 1
                continue
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return index
            index += 1
        return -1

    def _split_top_level_commas(self, text: str) -> List[str]:
        parts: List[str] = []
        start = 0
        depth = 0
        in_single = False
        in_double = False
        index = 0
        while index < len(text):
            char = text[index]
            if char == "'" and not in_double:
                in_single = not in_single
                index += 1
                continue
            if char == '"' and not in_single:
                in_double = not in_double
                index += 1
                continue
            if in_single or in_double:
                index += 1
                continue
            if char in "({[":
                depth += 1
            elif char in ")}]":
                depth = max(depth - 1, 0)
            elif char == "," and depth == 0:
                parts.append(text[start:index].strip())
                start = index + 1
            index += 1
        tail = text[start:].strip()
        if tail:
            parts.append(tail)
        return parts

    def _path_pattern_variables(self, path: PathPattern) -> set[str]:
        variables = set()
        for node in path.node_pattern_list:
            if node.symbolic_name:
                variables.add(node.symbolic_name)
        for edge in path.edge_pattern_list:
            if edge.symbolic_name:
                variables.add(edge.symbolic_name)
        return variables

    def _clean_pattern_identifier(self, value: str) -> str:
        return str(value or "").strip().strip("`").strip('"')

    def _skip_spaces(self, text: str, index: int) -> int:
        while index < len(text) and text[index].isspace():
            index += 1
        return index

    def _translate_supported_with(self, query_pattern: List[Clause]) -> str:
        with_indexes = [
            index for index, clause in enumerate(query_pattern) if isinstance(clause, WithClause)
        ]
        if len(with_indexes) == 2:
            if any(
                isinstance(clause, MatchClause)
                for clause in query_pattern[with_indexes[0] + 1 : with_indexes[1]]
            ):
                return self._translate_with_match_then_with_cte(
                    query_pattern,
                    with_indexes,
                )
            return self._translate_two_stage_with_cte(query_pattern, with_indexes)
        if len(with_indexes) != 1:
            raise ValueError("Only one-stage WITH pipelines are supported.")

        with_index = with_indexes[0]
        before_with = query_pattern[:with_index]
        after_with = query_pattern[with_index + 1 :]
        with_clause = query_pattern[with_index]
        assert isinstance(with_clause, WithClause)

        if any(isinstance(clause, (MatchClause, WhereClause)) for clause in after_with):
            return self._translate_with_match_cte(before_with, with_clause, after_with)
        return_clauses = [clause for clause in after_with if isinstance(clause, ReturnClause)]
        if len(return_clauses) != 1:
            raise ValueError("WITH pipeline requires one final RETURN clause.")

        match_clauses = [clause for clause in before_with if isinstance(clause, MatchClause)]
        where_expressions: List[CompareExpression] = []
        for clause in before_with:
            if isinstance(clause, WhereClause):
                where_expressions.extend(self._as_compare_list(clause.compare_expression_list))
        if not match_clauses:
            raise ValueError("WITH translation requires a preceding MATCH.")

        if (
            self._has_aggregate(with_clause.return_body)
            or any(item.function_name for item in with_clause.return_body.return_item_list)
            or with_clause.return_body.sort_item_list
            or with_clause.return_body.skip != -1
            or with_clause.return_body.limit != -1
            or with_clause.compare_expression_list
            or self._with_passthrough_variable_names(with_clause.return_body)
        ):
            return self._translate_with_cte(
                match_clauses,
                where_expressions,
                with_clause,
                return_clauses[0],
            )

        self._reset()
        match_parts = [self._translate_match_clause(clause) for clause in match_clauses]
        graph_table_parts = [
            OracleNameSanitizer.quote(self.graph_name, fallback="GRAPH"),
            "MATCH " + ", ".join(match_parts),
        ]
        where_parts = self._where_parts(where_expressions)
        if where_parts:
            graph_table_parts.append("WHERE " + " AND ".join(where_parts))
        graph_table_parts.append(
            f"COLUMNS ({self._translate_with_projection_columns(with_clause)})"
        )

        return_clause = return_clauses[0]
        select_keyword = self._outer_select_for_with(
            return_clause.return_body,
            return_clause.distinct,
        )
        query = f"{select_keyword}\nFROM GRAPH_TABLE (\n  {' '.join(graph_table_parts)}\n) gt"
        query += self._outer_order_and_paging_for_with(return_clause.return_body)
        return query

    def _translate_with_cte(
        self,
        match_clauses: List[MatchClause],
        where_expressions: List[CompareExpression],
        with_clause: WithClause,
        return_clause: ReturnClause,
    ) -> str:
        self._reset()
        match_parts = [self._translate_match_clause(clause) for clause in match_clauses]
        pattern_predicates, where_expressions = self._extract_pattern_predicates(where_expressions)
        if pattern_predicates:
            return self._translate_with_cte_pattern_predicates(
                match_parts,
                where_expressions,
                with_clause,
                return_clause,
                pattern_predicates,
            )
        graph_table_parts = [
            OracleNameSanitizer.quote(self.graph_name, fallback="GRAPH"),
            "MATCH " + ", ".join(match_parts),
        ]
        where_parts = self._where_parts(where_expressions)
        if where_parts:
            graph_table_parts.append("WHERE " + " AND ".join(where_parts))

        stage_return_body = self._with_stage_return_body(
            with_clause.return_body,
            return_clause.return_body,
            with_clause,
        )
        aggregate_query = self._has_aggregate(stage_return_body)
        graph_table_parts.append(
            f"COLUMNS ({self._translate_columns(stage_return_body, aggregate_query)})"
        )
        stage_select = self._outer_select(
            stage_return_body,
            with_clause.distinct,
            aggregate_query,
        )
        stage_query = f"{stage_select}\nFROM GRAPH_TABLE (\n  {' '.join(graph_table_parts)}\n) gt"
        stage_query += self._outer_group_order_and_paging(stage_return_body, aggregate_query)

        carried_variables = self._with_carried_variables(with_clause.return_body)
        final_select = self._outer_select_for_with_stage(
            return_clause.return_body,
            return_clause.distinct,
            carried_variables,
        )
        query = (
            f"WITH stage_1 AS (\n{self._indent_sql(stage_query)}\n)\n{final_select}\nFROM stage_1"
        )
        filters = self._with_filters(with_clause, carried_variables)
        if filters:
            query += "\nWHERE " + " AND ".join(filters)
        query += self._outer_group_order_and_paging_for_with_stage(
            return_clause.return_body,
            carried_variables,
        )
        return query

    def _translate_with_cte_pattern_predicates(
        self,
        match_parts: List[str],
        where_expressions: List[CompareExpression],
        with_clause: WithClause,
        return_clause: ReturnClause,
        pattern_predicates: List[Tuple[bool, str]],
    ) -> str:
        outer_variables = set(self._var_kinds)
        correlated_variables = set()
        parsed_predicates = []
        for negated, pattern in pattern_predicates:
            path = self._parse_pattern_predicate_path(pattern)
            variables = self._path_pattern_variables(path) & outer_variables
            if not variables:
                raise ValueError("Pattern predicate requires correlation to the outer MATCH.")
            correlated_variables.update(variables)
            parsed_predicates.append((negated, path, variables))

        graph_table_parts = [
            OracleNameSanitizer.quote(self.graph_name, fallback="GRAPH"),
            "MATCH " + ", ".join(match_parts),
        ]
        where_parts = self._where_parts(where_expressions)
        if where_parts:
            graph_table_parts.append("WHERE " + " AND ".join(where_parts))

        stage_return_body = self._with_stage_return_body(
            with_clause.return_body,
            return_clause.return_body,
            with_clause,
        )
        aggregate_query = self._has_aggregate(stage_return_body)
        base_return_body = self._return_body_with_join_variables(
            stage_return_body,
            sorted(correlated_variables),
        )
        graph_table_parts.append(
            f"COLUMNS ({self._translate_columns(base_return_body, aggregate_query)})"
        )
        base_query = f"SELECT *\nFROM GRAPH_TABLE (\n  {' '.join(graph_table_parts)}\n) gt"

        predicate_ctes: List[Tuple[str, str, set[str]]] = []
        if parsed_predicates and all(
            not negated for negated, _path, _variables in parsed_predicates
        ):
            predicate_ctes = [
                (
                    f"predicate_{index}",
                    self._pattern_predicate_relation_sql(path, variables),
                    variables,
                )
                for index, (_negated, path, variables) in enumerate(parsed_predicates, start=1)
            ]

        stage_query = (
            f"{self._outer_select(stage_return_body, with_clause.distinct, aggregate_query)}\n"
            "FROM base"
        )
        if predicate_ctes:
            for cte_name, _cte_sql, variables in predicate_ctes:
                join_conditions = [
                    f"{cte_name}.{self._element_projection_alias(variable)} = "
                    f"base.{self._element_projection_alias(variable)}"
                    for variable in sorted(variables)
                ]
                stage_query += "\nJOIN " + cte_name + " ON " + " AND ".join(join_conditions)
        else:
            filters = [
                self._pattern_predicate_sql(negated, path, variables)
                for negated, path, variables in parsed_predicates
            ]
            if filters:
                stage_query += "\nWHERE " + " AND ".join(filters)
        stage_query += self._outer_group_order_and_paging(stage_return_body, aggregate_query)

        carried_variables = self._with_carried_variables(with_clause.return_body)
        final_select = self._outer_select_for_with_stage(
            return_clause.return_body,
            return_clause.distinct,
            carried_variables,
        )
        cte_parts = [
            ("base", base_query),
            *[(name, sql) for name, sql, _variables in predicate_ctes],
        ]
        cte_parts.append(("stage_1", stage_query))
        query = "WITH " + ",\n".join(
            f"{name} AS (\n{self._indent_sql(sql)}\n)" for name, sql in cte_parts
        )
        query += f"\n{final_select}\nFROM stage_1"
        with_filters = self._with_filters(with_clause, carried_variables)
        if with_filters:
            query += "\nWHERE " + " AND ".join(with_filters)
        query += self._outer_group_order_and_paging_for_with_stage(
            return_clause.return_body,
            carried_variables,
        )
        return query

    def _translate_two_stage_with_cte(
        self,
        query_pattern: List[Clause],
        with_indexes: List[int],
    ) -> str:
        first_with_index, second_with_index = with_indexes
        first_with = query_pattern[first_with_index]
        second_with = query_pattern[second_with_index]
        assert isinstance(first_with, WithClause)
        assert isinstance(second_with, WithClause)

        before_first_with = query_pattern[:first_with_index]
        between_withs = query_pattern[first_with_index + 1 : second_with_index]
        after_second_with = query_pattern[second_with_index + 1 :]
        if any(isinstance(clause, (MatchClause, ReturnClause)) for clause in between_withs):
            raise ValueError("Two-stage WITH only supports adjacent SQL stages.")
        if any(
            isinstance(clause, (MatchClause, WhereClause, WithClause))
            for clause in after_second_with
        ):
            raise ValueError("Two-stage WITH only supports a final RETURN clause.")
        return_clauses = [
            clause for clause in after_second_with if isinstance(clause, ReturnClause)
        ]
        if len(return_clauses) != 1:
            raise ValueError("Two-stage WITH pipeline requires one final RETURN clause.")

        match_clauses = [clause for clause in before_first_with if isinstance(clause, MatchClause)]
        where_expressions: List[CompareExpression] = []
        for clause in before_first_with:
            if isinstance(clause, WhereClause):
                where_expressions.extend(self._as_compare_list(clause.compare_expression_list))
        for clause in between_withs:
            if isinstance(clause, WhereClause):
                first_with.compare_expression_list = self._as_compare_list(
                    first_with.compare_expression_list
                ) + self._as_compare_list(clause.compare_expression_list)
        if not match_clauses:
            raise ValueError("Two-stage WITH translation requires a preceding MATCH.")

        return_clause = return_clauses[0]
        second_stage_body = self._sql_stage_return_body(
            second_with.return_body,
            return_clause.return_body,
        )
        stage_1_query = self._first_with_stage_query(
            match_clauses,
            where_expressions,
            first_with,
            second_stage_body,
        )
        stage_1_aliases = {
            OracleNameSanitizer.alias(alias)
            for alias in self._resolved_return_aliases(
                self._with_stage_return_body(
                    first_with.return_body,
                    second_stage_body,
                    first_with,
                )
            )
        }
        stage_2_query = self._sql_with_stage_query(
            second_stage_body,
            second_with.distinct,
            "stage_1",
            stage_1_aliases,
        )
        second_filters = self._sql_stage_filters(second_with)
        if second_filters:
            stage_2_query = (
                "SELECT *\n"
                "FROM (\n"
                f"{self._indent_sql(stage_2_query)}\n"
                ") stage_2_raw\n"
                "WHERE " + " AND ".join(second_filters)
            )

        stage_2_aliases = set(self._resolved_sql_stage_aliases(second_stage_body))
        final_select = self._sql_stage_final_select(
            return_clause.return_body,
            return_clause.distinct,
            stage_2_aliases,
        )
        query = (
            "WITH stage_1 AS (\n"
            f"{self._indent_sql(stage_1_query)}\n"
            "),\n"
            "stage_2 AS (\n"
            f"{self._indent_sql(stage_2_query)}\n"
            ")\n"
            f"{final_select}\n"
            "FROM stage_2"
        )
        query += self._sql_stage_final_group_order_and_paging(
            return_clause.return_body,
            stage_2_aliases,
        )
        return query

    def _translate_with_match_then_with_cte(
        self,
        query_pattern: List[Clause],
        with_indexes: List[int],
    ) -> str:
        first_with_index, second_with_index = with_indexes
        first_with = query_pattern[first_with_index]
        second_with = query_pattern[second_with_index]
        assert isinstance(first_with, WithClause)
        assert isinstance(second_with, WithClause)

        before_first_with = query_pattern[:first_with_index]
        between_withs = query_pattern[first_with_index + 1 : second_with_index]
        after_second_with = query_pattern[second_with_index + 1 :]
        if any(isinstance(clause, WithClause) for clause in between_withs):
            raise ValueError("Nested WITH stages are not supported.")
        if any(
            isinstance(clause, (MatchClause, WhereClause, WithClause))
            for clause in after_second_with
        ):
            raise ValueError("WITH MATCH WITH only supports a final RETURN clause.")
        return_clauses = [
            clause for clause in after_second_with if isinstance(clause, ReturnClause)
        ]
        if len(return_clauses) != 1:
            raise ValueError("WITH MATCH WITH pipeline requires one final RETURN clause.")
        return_clause = return_clauses[0]

        intermediate_body = self._sql_stage_return_body(
            second_with.return_body,
            return_clause.return_body,
        )
        intermediate_return = ReturnClause(intermediate_body, second_with.distinct)
        intermediate_query = self._translate_with_match_cte(
            before_first_with,
            first_with,
            [*between_withs, intermediate_return],
        )
        available_aliases = set(self._resolved_sql_stage_aliases(intermediate_body))
        final_select = self._sql_stage_final_select(
            return_clause.return_body,
            return_clause.distinct,
            available_aliases,
        )
        cte_prefix, intermediate_select = self._split_with_cte_final_select(intermediate_query)
        query = (
            f"{cte_prefix},\n"
            "stage_3 AS (\n"
            f"{self._indent_sql(intermediate_select)}\n"
            ")\n"
            f"{final_select}\n"
            "FROM stage_3"
        )
        filters = self._sql_stage_filters(second_with)
        if filters:
            query += "\nWHERE " + " AND ".join(filters)
        query += self._sql_stage_final_group_order_and_paging(
            return_clause.return_body,
            available_aliases,
        )
        return query

    def _split_with_cte_final_select(self, query: str) -> Tuple[str, str]:
        marker = "\nSELECT "
        index = query.rfind(marker)
        if not query.startswith("WITH ") or index == -1:
            raise ValueError("Expected WITH CTE query with a final SELECT.")
        return query[:index], query[index + 1 :]

    def _first_with_stage_query(
        self,
        match_clauses: List[MatchClause],
        where_expressions: List[CompareExpression],
        with_clause: WithClause,
        next_with_body: ReturnBody,
    ) -> str:
        self._reset()
        match_parts = [self._translate_match_clause(clause) for clause in match_clauses]
        graph_table_parts = [
            OracleNameSanitizer.quote(self.graph_name, fallback="GRAPH"),
            "MATCH " + ", ".join(match_parts),
        ]
        where_parts = self._where_parts(where_expressions)
        if where_parts:
            graph_table_parts.append("WHERE " + " AND ".join(where_parts))

        stage_return_body = self._with_stage_return_body(
            with_clause.return_body,
            next_with_body,
            with_clause,
        )
        aggregate_query = self._has_aggregate(stage_return_body)
        graph_table_parts.append(
            f"COLUMNS ({self._translate_columns(stage_return_body, aggregate_query)})"
        )
        stage_query = (
            f"{self._outer_select(stage_return_body, with_clause.distinct, aggregate_query)}\n"
            f"FROM GRAPH_TABLE (\n  {' '.join(graph_table_parts)}\n) gt"
        )
        stage_query += self._outer_group_order_and_paging(stage_return_body, aggregate_query)

        carried_variables = self._with_carried_variables(with_clause.return_body)
        filters = self._with_filters(with_clause, carried_variables)
        if filters:
            stage_query = (
                "SELECT *\n"
                "FROM (\n"
                f"{self._indent_sql(stage_query)}\n"
                ") stage_1_raw\n"
                "WHERE " + " AND ".join(filters)
            )
        return stage_query

    def _sql_with_stage_query(
        self,
        return_body: ReturnBody,
        distinct: bool,
        from_name: str,
        available_aliases: set[str],
    ) -> str:
        aggregate_query = self._has_aggregate(return_body)
        select_items = []
        return_aliases = self._resolved_sql_stage_aliases(return_body)
        for item, alias in zip(return_body.return_item_list, return_aliases, strict=True):
            if self._is_complex_aggregate_item(item):
                expression = self._translate_sql_expression(item.expression)
            elif self._is_aggregate_item(item):
                expression = self._sql_stage_aggregate_expression(item, available_aliases)
            else:
                expression = self._sql_stage_item_expression(item, available_aliases)
            select_items.append(f"{expression} AS {OracleNameSanitizer.alias(alias)}")
        keyword = "SELECT DISTINCT" if distinct else "SELECT"
        query = f"{keyword} " + ", ".join(select_items) + f"\nFROM {from_name}"
        if aggregate_query:
            group_aliases = [
                self._sql_stage_item_expression(item, available_aliases)
                for item in return_body.return_item_list
                if not self._is_aggregate_item(item)
            ]
            if group_aliases:
                query += "\nGROUP BY " + ", ".join(dict.fromkeys(group_aliases))
        query += self._outer_order_and_paging_for_with(return_body, include_group_by=False)
        return query

    def _sql_stage_return_body(
        self,
        stage_body: ReturnBody,
        final_body: ReturnBody,
    ) -> ReturnBody:
        items = list(stage_body.return_item_list)
        carried_variables = {
            item.symbolic_name
            for item in items
            if (
                not item.property
                and not item.function_name
                and (not item.expression or item.expression == item.symbolic_name)
            )
        }
        existing_aliases = set(self._resolved_sql_stage_aliases(stage_body))
        for variable, property_name in self._return_body_property_references(final_body):
            if variable not in carried_variables:
                continue
            property_name = self._canonical_property_name(variable, property_name)
            alias = self._with_property_stage_alias(variable, property_name)
            if alias in existing_aliases:
                continue
            items.append(
                ReturnItem(
                    symbolic_name=variable,
                    property=property_name,
                    alias=alias,
                    function_name="",
                    expression=f"{variable}.{property_name}",
                )
            )
            existing_aliases.add(alias)
        return ReturnBody(
            items,
            stage_body.sort_item_list,
            stage_body.skip,
            stage_body.limit,
        )

    def _return_body_property_references(
        self,
        return_body: ReturnBody,
    ) -> List[Tuple[str, str]]:
        references: List[Tuple[str, str]] = []
        for item in return_body.return_item_list:
            if item.property:
                references.append((item.symbolic_name, item.property))
            references.extend(self._all_property_references(item.expression))
        for sort_item in return_body.sort_item_list:
            if sort_item.property:
                references.append((sort_item.symbolic_name, sort_item.property))
            references.extend(self._all_property_references(sort_item.expression))
        return list(dict.fromkeys(references))

    def _all_property_references(self, expression: str) -> List[Tuple[str, str]]:
        protected, _ = self._protect_string_literals(expression or "")
        references: List[Tuple[str, str]] = []
        for match in re.finditer(
            r"\b(?P<variable>[A-Za-z_][A-Za-z0-9_]*)\."
            r"(?:\"(?P<quoted_property>[^\"]+)\"|"
            r"(?P<property>[A-Za-z_][A-Za-z0-9_$#-]*)\b)",
            protected,
        ):
            references.append(
                (
                    match.group("variable"),
                    match.group("quoted_property") or match.group("property"),
                )
            )
        return references

    def _sql_stage_final_select(
        self,
        return_body: ReturnBody,
        distinct: bool,
        available_aliases: set[str],
    ) -> str:
        select_items = []
        for item, alias in zip(
            return_body.return_item_list,
            self._resolved_sql_stage_aliases(return_body),
            strict=True,
        ):
            if self._is_complex_aggregate_item(item):
                expression = self._translate_sql_expression(item.expression)
            elif self._is_aggregate_item(item):
                expression = self._sql_stage_aggregate_expression(item, available_aliases)
            else:
                expression = self._sql_stage_item_expression(item, available_aliases)
            select_items.append(f"{expression} AS {OracleNameSanitizer.alias(alias)}")
        keyword = "SELECT DISTINCT" if distinct else "SELECT"
        return f"{keyword} " + ", ".join(select_items)

    def _sql_stage_final_group_order_and_paging(
        self,
        return_body: ReturnBody,
        available_aliases: set[str],
    ) -> str:
        suffix = ""
        if self._has_aggregate(return_body):
            group_aliases = [
                self._sql_stage_item_expression(item, available_aliases)
                for item in return_body.return_item_list
                if not self._is_aggregate_item(item)
            ]
            if group_aliases:
                suffix += "\nGROUP BY " + ", ".join(dict.fromkeys(group_aliases))
        if return_body.sort_item_list:
            suffix += "\nORDER BY " + ", ".join(
                self._translate_sort_item(item, return_body) for item in return_body.sort_item_list
            )
        if return_body.skip != -1:
            suffix += f"\nOFFSET {return_body.skip} ROWS"
        if return_body.limit != -1:
            suffix += f"\nFETCH FIRST {return_body.limit} ROWS ONLY"
        return suffix

    def _translate_sort_item_for_with_match(
        self,
        sort_item: SortItem,
        return_body: ReturnBody,
    ) -> str:
        if sort_item.property and sort_item.symbolic_name:
            alias = self._with_property_stage_alias(
                sort_item.symbolic_name,
                self._canonical_property_name(sort_item.symbolic_name, sort_item.property),
            )
            alias = f"stage_2.{OracleNameSanitizer.alias(alias)}"
        else:
            alias = OracleNameSanitizer.alias(self._sort_alias(sort_item, return_body))
        return f"{alias}{self._sql_sort_order(sort_item.order)}"

    def _resolved_sql_stage_aliases(self, return_body: ReturnBody) -> List[str]:
        aliases = []
        for item in return_body.return_item_list:
            alias = (
                item.alias
                or item.property
                or self._default_expression_alias(
                    item.symbolic_name,
                    item.expression or item.symbolic_name,
                )
            )
            aliases.append(OracleNameSanitizer.alias(alias))
        return aliases

    def _sql_stage_item_expression(
        self,
        item: ReturnItem | SortItem,
        available_aliases: set[str],
    ) -> str:
        if item.property:
            property_alias = self._with_property_stage_alias(
                item.symbolic_name,
                self._canonical_property_name(item.symbolic_name, item.property),
            )
            if property_alias in available_aliases:
                return property_alias
        if item.expression and (
            item.expression != item.symbolic_name
            or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", item.expression)
        ):
            return self._sql_stage_expression(item.expression, available_aliases)
        alias = OracleNameSanitizer.alias(item.alias or item.property or item.symbolic_name)
        if alias in available_aliases:
            return alias
        element_alias = self._element_projection_alias(item.symbolic_name)
        if element_alias in available_aliases:
            return element_alias
        return OracleNameSanitizer.alias(item.symbolic_name)

    def _sql_stage_expression(self, expression: str, available_aliases: set[str]) -> str:
        translated = self._translate_sql_expression(expression)
        for variable, property_name in self._property_references(expression):
            property_name = self._canonical_property_name(variable, property_name)
            sql_variable = self._var_sql_names.get(variable, variable)
            property_ref = OracleNameSanitizer.quote(property_name, fallback="PROP")
            property_alias = self._with_property_stage_alias(variable, property_name)
            if property_alias not in available_aliases:
                continue
            translated = translated.replace(f"{sql_variable}.{property_ref}", property_alias)
            translated = re.sub(
                rf"\b{re.escape(variable)}\.{re.escape(property_name)}\b",
                property_alias,
                translated,
            )
        return translated

    def _sql_stage_aggregate_expression(
        self,
        item: ReturnItem | SortItem,
        available_aliases: set[str],
    ) -> str:
        function_name = item.function_name.upper()
        if function_name == "COUNT" and item.symbolic_name == "*":
            return "COUNT(*)"
        symbolic_name = self._strip_distinct_prefix(item.symbolic_name)
        expression = self._aggregate_argument_expression_text(item, symbolic_name)
        expression = self._translate_sql_expression(expression)
        element_alias = self._element_projection_alias(symbolic_name)
        if element_alias in available_aliases:
            expression = element_alias
        distinct = "DISTINCT " if self._has_distinct_prefix(item.symbolic_name) else ""
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_$#]*", expression):
            expression = OracleNameSanitizer.alias(expression)
        return self._aggregate_sql_call(function_name, distinct, expression)

    def _sql_stage_filters(self, with_clause: WithClause) -> List[str]:
        filters = []
        for expr in self._as_compare_list(with_clause.compare_expression_list):
            if getattr(expr, "raw_expression", ""):
                filters.append(self._translate_sql_expression(expr.raw_expression))
            else:
                filters.append(self._translate_compare_expression(expr))
        return filters

    def _translate_with_match_cte(
        self,
        before_with: List[Clause],
        with_clause: WithClause,
        after_with: List[Clause],
    ) -> str:
        first_match_clauses = [clause for clause in before_with if isinstance(clause, MatchClause)]
        first_where_expressions: List[CompareExpression] = []
        for clause in before_with:
            if isinstance(clause, WhereClause):
                first_where_expressions.extend(
                    self._as_compare_list(clause.compare_expression_list)
                )
        second_match_clauses = [clause for clause in after_with if isinstance(clause, MatchClause)]
        optional_second_stage = any(clause.optional for clause in second_match_clauses)
        if optional_second_stage and not all(clause.optional for clause in second_match_clauses):
            raise ValueError("OPTIONAL MATCH cannot be mixed with regular MATCH in one stage.")
        second_where_expressions: List[CompareExpression] = []
        return_clauses = []
        for clause in after_with:
            if isinstance(clause, WhereClause):
                second_where_expressions.extend(
                    self._as_compare_list(clause.compare_expression_list)
                )
            elif isinstance(clause, ReturnClause):
                return_clauses.append(clause)
            elif isinstance(clause, WithClause):
                raise ValueError("Multiple WITH stages are not supported.")
        if not first_match_clauses or not second_match_clauses or len(return_clauses) != 1:
            raise ValueError("WITH MATCH pipeline requires MATCH ... WITH ... MATCH ... RETURN.")

        carried_variables = self._with_passthrough_variable_names(with_clause.return_body)
        scalar_aliases = self._with_scalar_aliases(with_clause.return_body)
        self._assign_with_match_property_map_correlation_variables(
            second_match_clauses,
            scalar_aliases,
        )
        second_declared_variables = self._declared_variables_in_match_clauses(second_match_clauses)
        (
            correlations,
            scalar_correlations,
            expression_scalar_correlations,
            stage_expression_correlations,
            element_correlations,
            stage_one_filters,
            residual_second_where,
        ) = self._with_match_correlations(
            second_where_expressions,
            carried_variables,
            second_declared_variables,
            scalar_aliases,
        )
        property_map_scalar_correlations = self._extract_with_match_property_map_correlations(
            second_match_clauses,
            second_declared_variables,
            scalar_aliases,
        )
        scalar_correlations.extend(property_map_scalar_correlations)
        if (
            not carried_variables
            and not scalar_correlations
            and not expression_scalar_correlations
            and not stage_expression_correlations
        ):
            raise ValueError(
                "WITH MATCH pipeline requires carried graph variables or scalar correlations."
            )

        self._reset()
        first_match_parts = [self._translate_match_clause(clause) for clause in first_match_clauses]
        first_join_variables = {
            variable for variable in carried_variables if variable in self._var_kinds
        }
        if (
            not first_join_variables
            and not scalar_correlations
            and not expression_scalar_correlations
            and not stage_expression_correlations
        ):
            raise ValueError("WITH MATCH pipeline has no declared carried variables.")
        first_graph_table_parts = [
            OracleNameSanitizer.quote(self.graph_name, fallback="GRAPH"),
            "MATCH " + ", ".join(first_match_parts),
        ]
        first_where_parts = self._where_parts(first_where_expressions)
        if first_where_parts:
            first_graph_table_parts.append("WHERE " + " AND ".join(first_where_parts))
        return_clause = return_clauses[0]
        staged_with = (
            self._has_aggregate(with_clause.return_body)
            or bool(with_clause.compare_expression_list)
            or bool(scalar_correlations)
            or bool(expression_scalar_correlations)
            or bool(stage_expression_correlations)
        )
        stage_one_aliases: set[str] = set()
        nonstaged_stage_one_aliases: set[str] = set()
        first_join_aliases: Dict[str, str] = {}
        if staged_with:
            stage_return_body = self._with_stage_return_body(
                with_clause.return_body,
                return_clause.return_body,
                with_clause,
            )
            stage_return_body = self._return_body_with_property_projections(
                stage_return_body,
                [
                    (first_variable, first_property)
                    for (
                        _second_variable,
                        _second_property,
                        first_variable,
                        first_property,
                    ) in correlations
                ],
            )
            first_join_aliases = {
                variable: self._element_projection_alias(variable)
                for variable in sorted(first_join_variables)
            }
            stage_one_aliases = {
                OracleNameSanitizer.alias(alias)
                for alias in self._resolved_return_aliases(stage_return_body)
            }
            aggregate_with_query = self._has_aggregate(stage_return_body)
            first_graph_table_parts.append(
                f"COLUMNS ({self._translate_columns(stage_return_body, aggregate_with_query)})"
            )
            first_select = self._outer_select(
                stage_return_body,
                with_clause.distinct,
                aggregate_with_query,
            )
            first_stage_query = (
                f"{first_select}\nFROM GRAPH_TABLE (\n  {' '.join(first_graph_table_parts)}\n) gt"
            )
            first_stage_query += self._outer_group_order_and_paging(
                stage_return_body,
                aggregate_with_query,
            )
            filters = self._with_filters(with_clause, first_join_variables)
            if filters:
                first_stage_query = (
                    "SELECT *\n"
                    "FROM (\n"
                    f"{self._indent_sql(first_stage_query)}\n"
                    ") stage_1_raw\n"
                    "WHERE " + " AND ".join(filters)
                )
        else:
            first_join_aliases = {
                variable: self._stage_one_join_alias(variable)
                for variable in sorted(first_join_variables)
            }
            first_stage_columns = [
                (f"{self._element_id_expression(variable)} AS {first_join_aliases[variable]}")
                for variable in sorted(first_join_variables)
            ]
            first_stage_columns.extend(
                self._stage_one_return_projections(
                    return_clause.return_body,
                    first_join_variables,
                    second_declared_variables,
                )
            )
            first_stage_columns.extend(
                self._stage_one_with_scalar_projections(with_clause.return_body)
            )
            first_stage_columns.extend(self._stage_one_sort_projections(with_clause.return_body))
            first_stage_columns.extend(
                self._stage_one_property_projections(
                    [
                        (first_variable, first_property)
                        for (
                            _second_variable,
                            _second_property,
                            first_variable,
                            first_property,
                        ) in correlations
                    ]
                )
            )
            first_stage_columns.extend(
                self._stage_one_property_projections(
                    self._stage_one_aggregate_property_references(
                        return_clause.return_body,
                        first_join_variables,
                    )
                )
            )
            first_graph_table_parts.append(
                "COLUMNS (" + ", ".join(dict.fromkeys(first_stage_columns)) + ")"
            )
            nonstaged_stage_one_aliases = {
                OracleNameSanitizer.alias(match.group(1))
                for projection in first_stage_columns
                if (
                    match := re.search(
                        r"\bAS\s+([A-Za-z_][A-Za-z0-9_]*)\s*$",
                        projection,
                        flags=re.IGNORECASE,
                    )
                )
            }
            first_select = "SELECT DISTINCT *" if with_clause.distinct else "SELECT *"
            first_stage_query = (
                f"{first_select}\nFROM GRAPH_TABLE (\n  {' '.join(first_graph_table_parts)}\n) gt"
            )
            first_stage_query += self._outer_order_and_paging_for_with(with_clause.return_body)

        self._reset()
        second_match_parts = [
            self._translate_match_clause(clause) for clause in second_match_clauses
        ]
        join_variables = [
            variable
            for variable in sorted(first_join_variables)
            if variable in second_declared_variables and variable in self._var_kinds
        ]
        second_graph_table_parts = [
            OracleNameSanitizer.quote(self.graph_name, fallback="GRAPH"),
            "MATCH " + ", ".join(second_match_parts),
        ]
        second_where_parts = self._where_parts(residual_second_where)
        if second_where_parts:
            second_graph_table_parts.append("WHERE " + " AND ".join(second_where_parts))

        aggregate_query = self._has_aggregate(return_clause.return_body)
        if not stage_one_aliases:
            stage_one_aliases = nonstaged_stage_one_aliases
        stage_one_filter_sql = [
            self._with_match_stage_one_filter_sql(filter_expression, stage_one_aliases)
            for filter_expression in stage_one_filters
        ]
        cross_join = (
            not join_variables
            and not correlations
            and not scalar_correlations
            and not expression_scalar_correlations
            and not stage_expression_correlations
            and not element_correlations
            and self._with_match_allows_cross_join(
                return_clause.return_body,
                aggregate_query,
                second_declared_variables,
            )
        )
        if (
            not join_variables
            and not correlations
            and not scalar_correlations
            and not expression_scalar_correlations
            and not stage_expression_correlations
            and not element_correlations
            and not cross_join
        ):
            raise ValueError("WITH MATCH pipeline has no carried variables in second MATCH.")
        if optional_second_stage and cross_join:
            raise ValueError("OPTIONAL MATCH requires correlation to prior bindings.")
        second_return_body = self._return_body_for_second_match_stage(
            return_clause.return_body,
            join_variables,
            second_declared_variables,
            first_join_variables,
            stage_one_aliases,
            correlations,
            scalar_correlations,
            expression_scalar_correlations,
            stage_expression_correlations,
            element_correlations,
        )
        if cross_join and not second_return_body.return_item_list:
            second_return_body = ReturnBody(
                [
                    ReturnItem(
                        symbolic_name="",
                        property="",
                        alias="dummy_value",
                        function_name="",
                        expression="1",
                    )
                ],
                [],
            )
        second_graph_table_parts.append(
            f"COLUMNS ({self._translate_columns(second_return_body, aggregate_query)})"
        )
        second_stage_query = (
            f"SELECT *\nFROM GRAPH_TABLE (\n  {' '.join(second_graph_table_parts)}\n) gt"
        )

        join_conditions = [
            f"stage_2.{self._element_projection_alias(variable)} = "
            f"stage_1.{first_join_aliases[variable]}"
            for variable in join_variables
        ]
        join_conditions.extend(
            f"stage_2.{self._with_property_stage_alias(second_variable, second_property)} = "
            f"stage_1.{self._with_property_stage_alias(first_variable, first_property)}"
            for second_variable, second_property, first_variable, first_property in correlations
        )
        join_conditions.extend(
            f"stage_2.{self._with_property_stage_alias(second_variable, second_property)} "
            f"{operator} stage_1.{stage_alias}"
            for second_variable, second_property, operator, stage_alias in scalar_correlations
        )
        join_conditions.extend(
            f"stage_2.{expression_alias} {operator} stage_1.{stage_alias}"
            for (
                _expression,
                expression_alias,
                operator,
                stage_alias,
            ) in expression_scalar_correlations
        )
        join_conditions.extend(
            f"stage_2.{self._with_property_stage_alias(second_variable, second_property)} "
            f"{operator} "
            f"{self._with_match_stage_expression_sql(stage_expression, stage_one_aliases)}"
            for (
                second_variable,
                second_property,
                operator,
                stage_expression,
            ) in stage_expression_correlations
        )
        join_conditions.extend(
            f"stage_2.{self._element_projection_alias(second_variable)} "
            f"{operator} stage_1.{first_join_aliases[first_variable]}"
            for second_variable, operator, first_variable in element_correlations
        )
        final_select = self._outer_select_for_with_match(
            return_clause.return_body,
            return_clause.distinct,
            aggregate_query,
            stage_one_aliases,
            first_join_variables,
            second_return_body,
        )
        query = (
            "WITH stage_1 AS (\n"
            f"{self._indent_sql(first_stage_query)}\n"
            "),\n"
            "stage_2 AS (\n"
            f"{self._indent_sql(second_stage_query)}\n"
            ")\n"
            f"{final_select}\n"
            + (
                "FROM stage_1\nLEFT JOIN stage_2 ON " + " AND ".join(join_conditions)
                if optional_second_stage
                else "FROM stage_2\n"
                + (
                    "CROSS JOIN stage_1"
                    if cross_join
                    else "JOIN stage_1 ON " + " AND ".join(join_conditions)
                )
            )
        )
        if stage_one_filter_sql:
            query += "\nWHERE " + " AND ".join(stage_one_filter_sql)
        query += self._outer_group_order_and_paging_for_with_match(
            return_clause.return_body,
            aggregate_query,
            stage_one_aliases,
            first_join_variables,
            second_return_body,
        )
        return query

    def _with_match_allows_cross_join(
        self,
        return_body: ReturnBody,
        aggregate_query: bool,
        second_declared_variables: set[str],
    ) -> bool:
        for item in return_body.return_item_list:
            if aggregate_query and not self._is_aggregate_item(item):
                return False
            symbolic_name = self._strip_distinct_prefix(item.symbolic_name)
            if symbolic_name in second_declared_variables:
                return False
            if any(
                variable in second_declared_variables
                for variable, _property_name in self._property_references(item.expression)
            ):
                return False
        for sort_item in return_body.sort_item_list:
            symbolic_name = self._strip_distinct_prefix(sort_item.symbolic_name)
            if symbolic_name in second_declared_variables:
                return False
            if any(
                variable in second_declared_variables
                for variable, _property_name in self._property_references(sort_item.expression)
            ):
                return False
        return True

    def _outer_group_order_and_paging_for_with_match(
        self,
        return_body: ReturnBody,
        aggregate_query: bool,
        stage_one_aliases: set[str],
        first_join_variables: set[str],
        second_return_body: ReturnBody | None = None,
    ) -> str:
        suffix = ""
        if aggregate_query:
            group_aliases = []
            return_aliases = self._resolved_return_aliases(return_body)
            stage_two_aliases = self._stage_two_aliases_by_return_item(second_return_body)
            for item, resolved_alias in zip(
                return_body.return_item_list,
                return_aliases,
                strict=True,
            ):
                if self._is_aggregate_item(item):
                    continue
                stage_alias = self._stage_alias_for_return_item(
                    item,
                    first_join_variables,
                    stage_one_aliases,
                )
                if stage_alias in stage_one_aliases:
                    group_aliases.append(f"stage_1.{stage_alias}")
                elif OracleNameSanitizer.alias(resolved_alias) in stage_one_aliases:
                    group_aliases.append(f"stage_1.{OracleNameSanitizer.alias(resolved_alias)}")
                else:
                    stage_two_alias = stage_two_aliases.get(
                        id(item),
                        OracleNameSanitizer.alias(resolved_alias),
                    )
                    group_aliases.append(f"stage_2.{stage_two_alias}")
            for item in return_body.return_item_list:
                if not self._is_complex_aggregate_item(item):
                    continue
                for variable, property_name in self._property_references(item.expression):
                    property_name = self._canonical_property_name(variable, property_name)
                    property_alias = self._with_property_stage_alias(variable, property_name)
                    if property_alias in stage_one_aliases:
                        group_aliases.append(f"stage_1.{property_alias}")
            if group_aliases:
                suffix += "\nGROUP BY " + ", ".join(dict.fromkeys(group_aliases))
        if return_body.sort_item_list:
            suffix += "\nORDER BY " + ", ".join(
                self._translate_sort_item_for_with_match(item, return_body)
                for item in return_body.sort_item_list
            )
        if return_body.skip != -1:
            suffix += f"\nOFFSET {return_body.skip} ROWS"
        if return_body.limit != -1:
            suffix += f"\nFETCH FIRST {return_body.limit} ROWS ONLY"
        return suffix

    def _return_body_with_join_variables(
        self,
        return_body: ReturnBody,
        join_variables: List[str],
    ) -> ReturnBody:
        items = list(return_body.return_item_list)
        existing_aliases = {
            OracleNameSanitizer.alias(self._return_alias(item, self._return_expression(item)))
            for item in items
        }
        for variable in join_variables:
            alias = self._element_projection_alias(variable)
            if alias in existing_aliases:
                continue
            items.append(
                ReturnItem(
                    symbolic_name=variable,
                    property="",
                    alias=alias,
                    function_name="",
                    expression=variable,
                )
            )
            existing_aliases.add(alias)
        return ReturnBody(
            items,
            return_body.sort_item_list,
            return_body.skip,
            return_body.limit,
        )

    def _return_body_for_second_match_stage(
        self,
        return_body: ReturnBody,
        join_variables: List[str],
        second_declared_variables: set[str],
        first_join_variables: set[str],
        stage_one_aliases: set[str],
        correlations: List[Tuple[str, str, str, str]] | None = None,
        scalar_correlations: List[Tuple[str, str, str, str]] | None = None,
        expression_scalar_correlations: List[Tuple[str, str, str, str]] | None = None,
        stage_expression_correlations: List[Tuple[str, str, str, str]] | None = None,
        element_correlations: List[Tuple[str, str, str]] | None = None,
    ) -> ReturnBody:
        correlations = correlations or []
        scalar_correlations = scalar_correlations or []
        expression_scalar_correlations = expression_scalar_correlations or []
        stage_expression_correlations = stage_expression_correlations or []
        element_correlations = element_correlations or []
        items = [
            item
            for item in return_body.return_item_list
            if self._return_item_can_project_from_second_match(
                item,
                second_declared_variables,
                first_join_variables,
                stage_one_aliases,
            )
        ]
        sort_items = [
            item
            for item in return_body.sort_item_list
            if self._return_item_can_project_from_second_match(
                item,
                second_declared_variables,
                first_join_variables,
                stage_one_aliases,
            )
        ]
        stage_body = ReturnBody(
            items,
            sort_items,
            return_body.skip,
            return_body.limit,
        )
        stage_body = self._return_body_with_join_variables(stage_body, join_variables)
        aggregate_element_references = []
        for item in return_body.return_item_list:
            aggregate_element_references.extend(
                variable
                for variable in self._aggregate_element_references(item.expression)
                if variable in second_declared_variables
            )
        for sort_item in return_body.sort_item_list:
            aggregate_element_references.extend(
                variable
                for variable in self._aggregate_element_references(sort_item.expression)
                if variable in second_declared_variables
            )
        stage_body = self._return_body_with_join_variables(
            stage_body,
            list(dict.fromkeys(aggregate_element_references)),
        )
        stage_body = self._return_body_with_join_variables(
            stage_body,
            [
                second_variable
                for second_variable, _operator, _first_variable in element_correlations
            ],
        )
        stage_body = self._return_body_with_property_projections(
            stage_body,
            [
                (second_variable, second_property)
                for (
                    second_variable,
                    second_property,
                    _first_variable,
                    _first_property,
                ) in correlations
            ]
            + [
                (second_variable, second_property)
                for second_variable, second_property, _operator, _stage_alias in scalar_correlations
            ]
            + [
                (second_variable, second_property)
                for (
                    second_variable,
                    second_property,
                    _operator,
                    _stage_expression,
                ) in stage_expression_correlations
            ]
            + [
                (item.symbolic_name, item.property)
                for item in return_body.return_item_list
                if item.symbolic_name in second_declared_variables and item.property
            ]
            + [
                (variable, property_name)
                for item in return_body.return_item_list
                for variable, property_name in self._property_references(item.expression)
                if variable in second_declared_variables
            ]
            + [
                (sort_item.symbolic_name, sort_item.property)
                for sort_item in return_body.sort_item_list
                if sort_item.symbolic_name in second_declared_variables and sort_item.property
            ],
        )
        return self._return_body_with_expression_projections(
            stage_body,
            [
                (expression, expression_alias)
                for (
                    expression,
                    expression_alias,
                    _operator,
                    _stage_alias,
                ) in expression_scalar_correlations
            ],
        )

    def _return_item_can_project_from_second_match(
        self,
        item: ReturnItem | SortItem,
        second_declared_variables: set[str],
        first_join_variables: set[str],
        stage_one_aliases: set[str],
    ) -> bool:
        if self._stage_alias_for_return_item(
            item
        ) in stage_one_aliases and not self._is_aggregate_item(item):
            return False
        if (
            item.expression
            and not self._is_aggregate_item(item)
            and self._expression_uses_stage_one_alias(item.expression, stage_one_aliases)
        ):
            return False
        if (
            item.property
            and item.symbolic_name in first_join_variables
            and not self._is_aggregate_item(item)
        ):
            return False
        symbolic_name = self._strip_distinct_prefix(item.symbolic_name)
        if symbolic_name in second_declared_variables:
            return True
        references = self._property_references(item.expression)
        if not references:
            return False
        return all(variable in second_declared_variables for variable, _property_name in references)

    def _expression_uses_stage_one_alias(
        self,
        expression: str,
        stage_one_aliases: set[str],
    ) -> bool:
        if not expression:
            return False
        for variable, property_name in self._property_references(expression):
            property_name = self._canonical_property_name(variable, property_name)
            if self._with_property_stage_alias(variable, property_name) in stage_one_aliases:
                return True
        return any(re.search(rf"\b{re.escape(alias)}\b", expression) for alias in stage_one_aliases)

    def _outer_select_for_with_match(
        self,
        return_body: ReturnBody,
        distinct: bool,
        aggregate_query: bool,
        stage_one_aliases: set[str],
        first_join_variables: set[str],
        second_return_body: ReturnBody | None = None,
    ) -> str:
        if not stage_one_aliases:
            return self._outer_select(return_body, distinct, aggregate_query, ["__join__"])
        select_items = []
        return_aliases = self._resolved_return_aliases(return_body)
        stage_two_aliases = self._stage_two_aliases_by_return_item(second_return_body)
        for item, resolved_alias in zip(return_body.return_item_list, return_aliases, strict=True):
            if self._is_complex_aggregate_item(item):
                expression = self._outer_complex_aggregate_expression_for_with_match(
                    item.expression,
                    stage_one_aliases,
                )
                alias = self._return_alias(item, expression)
                select_items.append(f"{expression} AS {OracleNameSanitizer.alias(alias)}")
            elif self._is_aggregate_item(item):
                expression = self._outer_aggregate_expression_for_with_match(
                    item,
                    stage_one_aliases,
                    second_return_body,
                )
                alias = self._return_alias(item, expression)
                select_items.append(f"{expression} AS {OracleNameSanitizer.alias(alias)}")
            elif item.property:
                stage_alias = self._stage_alias_for_return_item(
                    item,
                    first_join_variables,
                    stage_one_aliases,
                )
                resolved_sql_alias = OracleNameSanitizer.alias(resolved_alias)
                if stage_alias in stage_one_aliases:
                    expression = f"stage_1.{stage_alias}"
                elif resolved_sql_alias in stage_one_aliases:
                    expression = f"stage_1.{resolved_sql_alias}"
                else:
                    stage_two_alias = stage_two_aliases.get(
                        id(item),
                    ) or self._stage_two_property_alias(
                        second_return_body,
                        item.symbolic_name,
                        item.property,
                    )
                    expression = f"stage_2.{stage_two_alias or stage_alias}"
                select_items.append(f"{expression} AS {resolved_sql_alias}")
            elif item.expression and (
                item.expression != item.symbolic_name
                or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", item.expression)
            ):
                if self._expression_uses_stage_one_alias(item.expression, stage_one_aliases):
                    expression = self._outer_expression_for_with_match(
                        item.expression,
                        stage_one_aliases,
                    )
                else:
                    expression = f"stage_2.{OracleNameSanitizer.alias(resolved_alias)}"
                select_items.append(f"{expression} AS {OracleNameSanitizer.alias(resolved_alias)}")
            else:
                stage_alias = self._stage_alias_for_return_item(
                    item,
                    first_join_variables,
                    stage_one_aliases,
                )
                resolved_sql_alias = OracleNameSanitizer.alias(resolved_alias)
                if stage_alias in stage_one_aliases:
                    expression = f"stage_1.{stage_alias}"
                else:
                    expression = f"stage_2.{stage_two_aliases.get(id(item), stage_alias)}"
                select_items.append(f"{expression} AS {resolved_sql_alias}")
        keyword = "SELECT DISTINCT" if distinct else "SELECT"
        return f"{keyword} " + ", ".join(select_items)

    def _stage_two_aliases_by_return_item(
        self,
        second_return_body: ReturnBody | None,
    ) -> Dict[int, str]:
        if second_return_body is None:
            return {}
        return {
            id(item): OracleNameSanitizer.alias(alias)
            for item, alias in zip(
                second_return_body.return_item_list,
                self._resolved_return_aliases(second_return_body),
                strict=True,
            )
        }

    def _stage_two_property_alias(
        self,
        second_return_body: ReturnBody | None,
        variable: str,
        property_name: str,
    ) -> str:
        if second_return_body is None:
            return ""
        property_name = self._canonical_property_name(variable, property_name)
        for item, alias in zip(
            second_return_body.return_item_list,
            self._resolved_return_aliases(second_return_body),
            strict=True,
        ):
            if (
                item.symbolic_name == variable
                and item.property
                and not self._is_aggregate_item(item)
            ):
                item_property = self._canonical_property_name(variable, item.property)
                if item_property == property_name:
                    return OracleNameSanitizer.alias(alias)
            for expr_variable, expr_property in self._property_references(item.expression):
                if self._is_aggregate_item(item):
                    continue
                if expr_variable != variable:
                    continue
                expr_property = self._canonical_property_name(variable, expr_property)
                if expr_property == property_name:
                    return OracleNameSanitizer.alias(alias)
        return ""

    def _outer_complex_aggregate_expression_for_with_match(
        self,
        expression: str,
        stage_one_aliases: set[str],
    ) -> str:
        translated = self._translate_sql_expression(expression)
        translated = self._outer_expression_for_with_match(translated, stage_one_aliases)
        for variable in self._aggregate_element_reference_names(expression):
            stage_one_element_alias = self._stage_one_join_alias(variable)
            element_alias = self._element_projection_alias(variable)
            if stage_one_element_alias in stage_one_aliases:
                qualified = f"stage_1.{stage_one_element_alias}"
            elif element_alias in stage_one_aliases:
                qualified = f"stage_1.{element_alias}"
            else:
                qualified = f"stage_2.{element_alias}"
            translated = re.sub(
                rf"\b(COUNT)\s*\(\s*DISTINCT\s+{re.escape(variable)}\s*\)",
                rf"\1(DISTINCT {qualified})",
                translated,
                flags=re.IGNORECASE,
            )
            translated = re.sub(
                rf"\b(COUNT|MIN|MAX)\s*\(\s*{re.escape(variable)}\s*\)",
                rf"\1({qualified})",
                translated,
                flags=re.IGNORECASE,
            )
        return self._coalesce_sum_calls(translated)

    def _outer_expression_for_with_match(
        self,
        expression: str,
        stage_one_aliases: set[str],
    ) -> str:
        translated = self._translate_sql_expression(expression)
        for variable, property_name in self._property_references(expression):
            property_name = self._canonical_property_name(variable, property_name)
            property_alias = self._with_property_stage_alias(variable, property_name)
            if property_alias not in stage_one_aliases:
                continue
            sql_variable = self._var_sql_names.get(variable, variable)
            property_ref = OracleNameSanitizer.quote(property_name, fallback="PROP")
            translated = translated.replace(
                f"{sql_variable}.{property_ref}",
                f"stage_1.{property_alias}",
            )
            translated = re.sub(
                rf"\b{re.escape(variable)}\.{re.escape(property_name)}\b",
                f"stage_1.{property_alias}",
                translated,
            )
        for alias in sorted(stage_one_aliases, key=len, reverse=True):
            translated = re.sub(
                rf"(?<![.\"])\b{re.escape(alias)}\b(?!\")",
                f"stage_1.{alias}",
                translated,
            )
        return translated

    def _outer_aggregate_expression_for_with_match(
        self,
        item: ReturnItem | SortItem,
        stage_one_aliases: set[str],
        second_return_body: ReturnBody | None = None,
    ) -> str:
        function_name = item.function_name.upper()
        if function_name == "COUNT" and item.symbolic_name == "*":
            return "COUNT(*)"
        symbolic_name = self._strip_distinct_prefix(item.symbolic_name)
        argument = self._aggregate_argument_expression_text(item, symbolic_name)
        if item.property:
            property_name = self._canonical_property_name(symbolic_name, item.property)
            property_alias = self._with_property_stage_alias(symbolic_name, property_name)
            if property_alias in stage_one_aliases:
                distinct = "DISTINCT " if self._has_distinct_prefix(item.symbolic_name) else ""
                return self._aggregate_sql_call(
                    function_name,
                    distinct,
                    f"stage_1.{property_alias}",
                )
            stage_two_alias = self._stage_two_property_alias(
                second_return_body,
                symbolic_name,
                property_name,
            )
            if stage_two_alias:
                distinct = "DISTINCT " if self._has_distinct_prefix(item.symbolic_name) else ""
                return self._aggregate_sql_call(
                    function_name,
                    distinct,
                    f"stage_2.{stage_two_alias}",
                )
        stage_one_element_alias = self._stage_one_join_alias(symbolic_name)
        if (
            not item.property
            and "." not in argument
            and stage_one_element_alias in stage_one_aliases
        ):
            distinct = "DISTINCT " if self._has_distinct_prefix(item.symbolic_name) else ""
            return self._aggregate_sql_call(
                function_name,
                distinct,
                f"stage_1.{stage_one_element_alias}",
            )
        if symbolic_name in self._var_kinds and not item.property and "." not in argument:
            distinct = "DISTINCT " if self._has_distinct_prefix(item.symbolic_name) else ""
            return (
                f"{function_name}({distinct}"
                f"stage_2.{self._element_projection_alias(symbolic_name)})"
            )
        argument = self._translate_sql_expression(argument)
        argument_alias = OracleNameSanitizer.alias(argument)
        if argument_alias in stage_one_aliases:
            distinct = "DISTINCT " if self._has_distinct_prefix(item.symbolic_name) else ""
            return self._aggregate_sql_call(
                function_name,
                distinct,
                f"stage_1.{argument_alias}",
            )
        return self._outer_aggregate_expression(item)

    def _stage_alias_for_return_item(
        self,
        item: ReturnItem | SortItem,
        first_join_variables: set[str] | None = None,
        stage_one_aliases: set[str] | None = None,
    ) -> str:
        if item.property and first_join_variables and item.symbolic_name in first_join_variables:
            property_name = self._canonical_property_name(item.symbolic_name, item.property)
            property_alias = self._with_property_stage_alias(item.symbolic_name, property_name)
            if not stage_one_aliases or property_alias in stage_one_aliases:
                return property_alias
        if not item.property and stage_one_aliases:
            element_alias = self._element_projection_alias(item.symbolic_name)
            if element_alias in stage_one_aliases:
                return element_alias
            stage_one_element_alias = self._stage_one_join_alias(item.symbolic_name)
            if stage_one_element_alias in stage_one_aliases:
                return stage_one_element_alias
        return OracleNameSanitizer.alias(
            getattr(item, "alias", "")
            or item.property
            or self._default_expression_alias(item.symbolic_name, item.expression)
        )

    def _stage_one_return_projections(
        self,
        return_body: ReturnBody,
        first_join_variables: set[str],
        second_declared_variables: set[str],
    ) -> List[str]:
        projections = []
        return_aliases = self._resolved_return_aliases(return_body)
        for item, alias in zip(return_body.return_item_list, return_aliases, strict=True):
            if self._is_aggregate_item(item):
                continue
            if item.symbolic_name not in first_join_variables:
                continue
            if not item.property and item.symbolic_name in second_declared_variables:
                continue
            projections.append(self._translate_return_item(item, alias))
        return projections

    def _stage_one_with_scalar_projections(self, return_body: ReturnBody) -> List[str]:
        projections = []
        for item in return_body.return_item_list:
            if self._is_aggregate_item(item):
                continue
            if (
                not item.property
                and not item.function_name
                and (not item.expression or item.expression == item.symbolic_name)
                and item.symbolic_name in self._var_kinds
            ):
                continue
            alias = item.alias or item.property or item.symbolic_name
            if not alias:
                continue
            projections.append(
                f"{self._return_expression(item)} AS {OracleNameSanitizer.alias(alias)}"
            )
        return projections

    def _stage_one_sort_projections(self, return_body: ReturnBody) -> List[str]:
        projections = []
        projected_aliases = {
            self._element_projection_alias(item.symbolic_name)
            for item in return_body.return_item_list
            if (
                not item.property
                and not item.function_name
                and item.symbolic_name in self._var_kinds
            )
        }
        projected_aliases.update(
            OracleNameSanitizer.alias(item.alias or item.property or item.symbolic_name)
            for item in return_body.return_item_list
            if (item.alias or item.property or item.symbolic_name)
        )
        for sort_item in return_body.sort_item_list:
            alias = OracleNameSanitizer.alias(self._sort_alias(sort_item, return_body))
            if alias in projected_aliases:
                continue
            if sort_item.expression:
                expression = self._translate_sql_expression(sort_item.expression)
            else:
                expression = self._value_expression(sort_item.symbolic_name, sort_item.property)
            projections.append(f"{expression} AS {alias}")
            projected_aliases.add(alias)
        return projections

    def _stage_one_property_projections(
        self,
        references: List[Tuple[str, str]],
    ) -> List[str]:
        projections = []
        for variable, property_name in references:
            property_name = self._canonical_property_name(variable, property_name)
            sql_variable = self._var_sql_names.get(variable, variable)
            property_ref = OracleNameSanitizer.quote(property_name, fallback="PROP")
            alias = self._with_property_stage_alias(variable, property_name)
            projections.append(f"{sql_variable}.{property_ref} AS {alias}")
        return projections

    def _stage_one_aggregate_property_references(
        self,
        return_body: ReturnBody,
        first_join_variables: set[str],
    ) -> List[Tuple[str, str]]:
        references: List[Tuple[str, str]] = []
        for item in return_body.return_item_list:
            if not self._is_aggregate_item(item):
                continue
            symbolic_name = self._strip_distinct_prefix(item.symbolic_name)
            if item.property and symbolic_name in first_join_variables:
                references.append((symbolic_name, item.property))
            for variable, property_name in self._property_references(item.expression):
                if variable in first_join_variables:
                    references.append((variable, property_name))
        unique: List[Tuple[str, str]] = []
        for variable, property_name in references:
            property_name = self._canonical_property_name(variable, property_name)
            if (variable, property_name) not in unique:
                unique.append((variable, property_name))
        return unique

    def _return_body_with_property_projections(
        self,
        return_body: ReturnBody,
        references: List[Tuple[str, str]],
    ) -> ReturnBody:
        if not references:
            return return_body
        items = list(return_body.return_item_list)
        existing_aliases = {
            OracleNameSanitizer.alias(self._return_alias(item, self._return_expression(item)))
            for item in items
        }
        for variable, property_name in references:
            property_name = self._canonical_property_name(variable, property_name)
            alias = self._with_property_stage_alias(variable, property_name)
            if alias in existing_aliases:
                continue
            items.append(
                ReturnItem(
                    symbolic_name=variable,
                    property=property_name,
                    alias=alias,
                    function_name="",
                    expression=f"{variable}.{property_name}",
                )
            )
            existing_aliases.add(alias)
        return ReturnBody(
            items,
            return_body.sort_item_list,
            return_body.skip,
            return_body.limit,
        )

    def _return_body_with_expression_projections(
        self,
        return_body: ReturnBody,
        references: List[Tuple[str, str]],
    ) -> ReturnBody:
        if not references:
            return return_body
        items = list(return_body.return_item_list)
        existing_aliases = {
            OracleNameSanitizer.alias(self._return_alias(item, self._return_expression(item)))
            for item in items
        }
        for expression, alias in references:
            alias = OracleNameSanitizer.alias(alias)
            if alias in existing_aliases:
                continue
            items.append(
                ReturnItem(
                    symbolic_name="",
                    property="",
                    alias=alias,
                    function_name="",
                    expression=expression,
                )
            )
            existing_aliases.add(alias)
        return ReturnBody(
            items,
            return_body.sort_item_list,
            return_body.skip,
            return_body.limit,
        )

    def _with_match_correlations(
        self,
        where_expressions: List[CompareExpression],
        carried_variables: set[str],
        second_declared_variables: set[str],
        scalar_aliases: set[str],
    ) -> Tuple[
        List[Tuple[str, str, str, str]],
        List[Tuple[str, str, str, str]],
        List[Tuple[str, str, str, str]],
        List[Tuple[str, str, str, str]],
        List[Tuple[str, str, str]],
        List[str],
        List[CompareExpression],
    ]:
        correlations: List[Tuple[str, str, str, str]] = []
        scalar_correlations: List[Tuple[str, str, str, str]] = []
        expression_scalar_correlations: List[Tuple[str, str, str, str]] = []
        stage_expression_correlations: List[Tuple[str, str, str, str]] = []
        element_correlations: List[Tuple[str, str, str]] = []
        stage_one_filters: List[str] = []
        residual: List[CompareExpression] = []
        for expression in where_expressions:
            raw_expression = getattr(expression, "raw_expression", "")
            if self._is_with_match_stage_one_filter(
                raw_expression or "",
                second_declared_variables,
                scalar_aliases,
            ):
                stage_one_filters.append(raw_expression)
                continue
            element_match = re.fullmatch(
                r"\s*(?P<left>[A-Za-z_][A-Za-z0-9_]*)\s*"
                r"(?P<operator>=|<>)\s*"
                r"(?P<right>[A-Za-z_][A-Za-z0-9_]*)\s*",
                raw_expression or "",
            )
            if element_match:
                left = element_match.group("left")
                right = element_match.group("right")
                operator = element_match.group("operator")
                if left in second_declared_variables and right in carried_variables:
                    element_correlations.append((left, operator, right))
                    continue
                if right in second_declared_variables and left in carried_variables:
                    element_correlations.append((right, operator, left))
                    continue
            cast_expression_scalar = self._with_match_cast_expression_scalar_correlation(
                raw_expression or "",
                second_declared_variables,
                scalar_aliases,
            )
            if cast_expression_scalar:
                expression_scalar_correlations.append(cast_expression_scalar)
                continue
            cast_scalar = self._with_match_cast_scalar_correlation(
                raw_expression or "",
                second_declared_variables,
                scalar_aliases,
            )
            if cast_scalar:
                scalar_correlations.append(cast_scalar)
                continue
            expression_scalar = self._with_match_expression_scalar_correlation(
                raw_expression or "",
                second_declared_variables,
                scalar_aliases,
            )
            if expression_scalar:
                expression_scalar_correlations.append(expression_scalar)
                continue
            stage_expression = self._with_match_stage_expression_correlation(
                raw_expression or "",
                second_declared_variables,
                scalar_aliases,
            )
            if stage_expression:
                stage_expression_correlations.append(stage_expression)
                continue
            match = re.fullmatch(
                r"\s*(?P<left_var>[A-Za-z_][A-Za-z0-9_]*)\."
                r"(?P<left_prop>[A-Za-z_][A-Za-z0-9_$#-]*)\s*"
                r"(?P<operator>=|<>|<=|>=|<|>)\s*"
                r"(?:(?P<right_var>[A-Za-z_][A-Za-z0-9_]*)\."
                r"(?P<right_prop>[A-Za-z_][A-Za-z0-9_$#-]*)|"
                r"(?P<right_alias>[A-Za-z_][A-Za-z0-9_]*))\s*",
                raw_expression or "",
            )
            if not match:
                reverse_match = re.fullmatch(
                    r"\s*(?P<left_alias>[A-Za-z_][A-Za-z0-9_]*)\s*"
                    r"(?P<operator>=|<>|<=|>=|<|>)\s*"
                    r"(?P<right_var>[A-Za-z_][A-Za-z0-9_]*)\."
                    r"(?P<right_prop>[A-Za-z_][A-Za-z0-9_$#-]*)\s*",
                    raw_expression or "",
                )
                if (
                    reverse_match
                    and reverse_match.group("left_alias") in scalar_aliases
                    and reverse_match.group("right_var") in second_declared_variables
                ):
                    scalar_correlations.append(
                        (
                            reverse_match.group("right_var"),
                            reverse_match.group("right_prop"),
                            self._reverse_operator(reverse_match.group("operator")),
                            OracleNameSanitizer.alias(reverse_match.group("left_alias")),
                        )
                    )
                else:
                    residual.append(expression)
                continue
            left_var = match.group("left_var")
            left_prop = match.group("left_prop")
            operator = match.group("operator")
            right_var = match.group("right_var")
            right_prop = match.group("right_prop")
            right_alias = match.group("right_alias")
            if (
                left_var in second_declared_variables
                and right_alias
                and right_alias in scalar_aliases
            ):
                scalar_correlations.append(
                    (left_var, left_prop, operator, OracleNameSanitizer.alias(right_alias))
                )
            elif left_var in second_declared_variables and right_var in carried_variables:
                if operator == "=":
                    correlations.append((left_var, left_prop, right_var, right_prop))
                else:
                    scalar_correlations.append(
                        (
                            left_var,
                            left_prop,
                            operator,
                            self._with_property_stage_alias(right_var, right_prop),
                        )
                    )
            elif right_var in second_declared_variables and left_var in carried_variables:
                if operator == "=":
                    correlations.append((right_var, right_prop, left_var, left_prop))
                else:
                    scalar_correlations.append(
                        (
                            right_var,
                            right_prop,
                            self._reverse_operator(operator),
                            self._with_property_stage_alias(left_var, left_prop),
                        )
                    )
            else:
                residual.append(expression)
        return (
            correlations,
            scalar_correlations,
            expression_scalar_correlations,
            stage_expression_correlations,
            element_correlations,
            stage_one_filters,
            residual,
        )

    def _is_with_match_stage_one_filter(
        self,
        expression: str,
        second_declared_variables: set[str],
        scalar_aliases: set[str],
    ) -> bool:
        if not expression:
            return False
        protected, _ = self._protect_string_literals(expression)
        if not any(
            re.search(rf"\b{re.escape(alias)}\b", protected) for alias in scalar_aliases if alias
        ):
            return False
        for variable, _property_name in self._property_references(protected):
            if variable in second_declared_variables:
                return False
        words = set(re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", protected))
        ignored = {
            "AND",
            "OR",
            "NOT",
            "NULL",
            "IS",
            "TRUE",
            "FALSE",
            "TOFLOAT",
            "TOINTEGER",
            "TOSTRING",
            "DATE",
            "DATETIME",
            "SIZE",
            "SPLIT",
            "REPLACE",
            "LEFT",
            "SUBSTRING",
        }
        return not any(word in second_declared_variables for word in words - ignored)

    def _with_match_stage_one_filter_sql(
        self,
        expression: str,
        stage_one_aliases: set[str],
    ) -> str:
        translated = self._translate_sql_expression(expression)
        for alias in sorted(stage_one_aliases, key=len, reverse=True):
            translated = re.sub(
                rf"(?<![.\"])\b{re.escape(alias)}\b(?!\")",
                f"stage_1.{alias}",
                translated,
            )
        return translated

    def _with_match_stage_expression_sql(
        self,
        expression: str,
        stage_one_aliases: set[str],
    ) -> str:
        translated = self._translate_sql_expression(expression)
        for alias in sorted(stage_one_aliases, key=len, reverse=True):
            translated = re.sub(
                rf"(?<![.\"])\b{re.escape(alias)}\b(?!\")",
                f"stage_1.{alias}",
                translated,
            )
        return translated

    def _with_match_stage_expression_correlation(
        self,
        expression: str,
        second_declared_variables: set[str],
        scalar_aliases: set[str],
    ) -> Tuple[str, str, str, str] | None:
        property_ref = (
            r"(?P<{prefix}_var>[A-Za-z_][A-Za-z0-9_]*)\."
            r"(?P<{prefix}_prop>[A-Za-z_][A-Za-z0-9_$#-]*)"
        )
        left_property = re.fullmatch(
            property_ref.format(prefix="left")
            + r"\s*(?P<operator>=|<>|<=|>=|<|>)\s*"
            + r"(?P<right_expr>.+?)\s*",
            expression,
            flags=re.IGNORECASE,
        )
        if (
            left_property
            and left_property.group("left_var") in second_declared_variables
            and self._is_stage_one_scalar_expression(
                left_property.group("right_expr"),
                scalar_aliases,
            )
        ):
            return (
                left_property.group("left_var"),
                left_property.group("left_prop"),
                left_property.group("operator"),
                left_property.group("right_expr").strip(),
            )
        right_property = re.fullmatch(
            r"\s*(?P<left_expr>.+?)\s*"
            + r"(?P<operator>=|<>|<=|>=|<|>)\s*"
            + property_ref.format(prefix="right")
            + r"\s*",
            expression,
            flags=re.IGNORECASE,
        )
        if (
            right_property
            and right_property.group("right_var") in second_declared_variables
            and self._is_stage_one_scalar_expression(
                right_property.group("left_expr"),
                scalar_aliases,
            )
        ):
            return (
                right_property.group("right_var"),
                right_property.group("right_prop"),
                self._reverse_operator(right_property.group("operator")),
                right_property.group("left_expr").strip(),
            )
        return None

    def _is_stage_one_scalar_expression(
        self,
        expression: str,
        scalar_aliases: set[str],
    ) -> bool:
        if not expression:
            return False
        protected, _ = self._protect_string_literals(expression)
        if not any(
            re.search(rf"\b{re.escape(alias)}\b", protected) for alias in scalar_aliases if alias
        ):
            return False
        stripped = protected
        for alias in sorted(scalar_aliases, key=len, reverse=True):
            stripped = re.sub(rf"\b{re.escape(alias)}\b", "", stripped)
        return bool(re.fullmatch(r"[\s\d.+\-*/%()]+", stripped))

    def _with_match_expression_scalar_correlation(
        self,
        expression: str,
        second_declared_variables: set[str],
        scalar_aliases: set[str],
    ) -> Tuple[str, str, str, str] | None:
        property_expr = (
            r"size\s*\(\s*"
            r"(?P<{prefix}_var>[A-Za-z_][A-Za-z0-9_]*)\."
            r"(?P<{prefix}_prop>[A-Za-z_][A-Za-z0-9_$#-]*)"
            r"\s*\)"
        )
        alias_ref = r"(?P<{prefix}_alias>[A-Za-z_][A-Za-z0-9_]*)"
        left_property = re.fullmatch(
            property_expr.format(prefix="left")
            + r"\s*(?P<operator>=|<>|<=|>=|<|>)\s*"
            + alias_ref.format(prefix="right")
            + r"\s*",
            expression,
            flags=re.IGNORECASE,
        )
        if (
            left_property
            and left_property.group("left_var") in second_declared_variables
            and left_property.group("right_alias") in scalar_aliases
        ):
            variable = left_property.group("left_var")
            property_name = left_property.group("left_prop")
            return (
                f"size({variable}.{property_name})",
                self._with_expression_stage_alias(variable, property_name, "size"),
                left_property.group("operator"),
                OracleNameSanitizer.alias(left_property.group("right_alias")),
            )
        right_property = re.fullmatch(
            alias_ref.format(prefix="left")
            + r"\s*(?P<operator>=|<>|<=|>=|<|>)\s*"
            + property_expr.format(prefix="right")
            + r"\s*",
            expression,
            flags=re.IGNORECASE,
        )
        if (
            right_property
            and right_property.group("right_var") in second_declared_variables
            and right_property.group("left_alias") in scalar_aliases
        ):
            variable = right_property.group("right_var")
            property_name = right_property.group("right_prop")
            return (
                f"size({variable}.{property_name})",
                self._with_expression_stage_alias(variable, property_name, "size"),
                self._reverse_operator(right_property.group("operator")),
                OracleNameSanitizer.alias(right_property.group("left_alias")),
            )
        return None

    def _with_expression_stage_alias(
        self,
        variable: str,
        property_name: str,
        function_name: str,
    ) -> str:
        return OracleNameSanitizer.alias(f"{variable}_{property_name}_{function_name}")

    def _with_match_cast_scalar_correlation(
        self,
        expression: str,
        second_declared_variables: set[str],
        scalar_aliases: set[str],
    ) -> Tuple[str, str, str, str] | None:
        property_ref = (
            r"(?:(?:toFloat|toInteger)\s*\(\s*)?"
            r"(?P<{prefix}_var>[A-Za-z_][A-Za-z0-9_]*)\."
            r"(?P<{prefix}_prop>[A-Za-z_][A-Za-z0-9_$#-]*)"
            r"\s*\)?"
        )
        alias_ref = r"(?P<{prefix}_alias>[A-Za-z_][A-Za-z0-9_]*)"
        left_property = re.fullmatch(
            property_ref.format(prefix="left")
            + r"\s*(?P<operator>=|<>|<=|>=|<|>)\s*"
            + alias_ref.format(prefix="right")
            + r"\s*",
            expression,
            flags=re.IGNORECASE,
        )
        if (
            left_property
            and left_property.group("left_var") in second_declared_variables
            and left_property.group("right_alias") in scalar_aliases
        ):
            return (
                left_property.group("left_var"),
                left_property.group("left_prop"),
                left_property.group("operator"),
                OracleNameSanitizer.alias(left_property.group("right_alias")),
            )
        right_property = re.fullmatch(
            alias_ref.format(prefix="left")
            + r"\s*(?P<operator>=|<>|<=|>=|<|>)\s*"
            + property_ref.format(prefix="right")
            + r"\s*",
            expression,
            flags=re.IGNORECASE,
        )
        if (
            right_property
            and right_property.group("right_var") in second_declared_variables
            and right_property.group("left_alias") in scalar_aliases
        ):
            return (
                right_property.group("right_var"),
                right_property.group("right_prop"),
                self._reverse_operator(right_property.group("operator")),
                OracleNameSanitizer.alias(right_property.group("left_alias")),
            )
        return None

    def _with_match_cast_expression_scalar_correlation(
        self,
        expression: str,
        second_declared_variables: set[str],
        scalar_aliases: set[str],
    ) -> Tuple[str, str, str, str] | None:
        property_ref = (
            r"(?P<{prefix}_func>toFloat|toInteger)\s*\(\s*"
            r"(?P<{prefix}_var>[A-Za-z_][A-Za-z0-9_]*)\."
            r"(?P<{prefix}_prop>[A-Za-z_][A-Za-z0-9_$#-]*)"
            r"\s*\)"
        )
        alias_ref = r"(?P<{prefix}_alias>[A-Za-z_][A-Za-z0-9_]*)"
        left_property = re.fullmatch(
            property_ref.format(prefix="left")
            + r"\s*(?P<operator>=|<>|<=|>=|<|>)\s*"
            + alias_ref.format(prefix="right")
            + r"\s*",
            expression,
            flags=re.IGNORECASE,
        )
        if (
            left_property
            and left_property.group("left_var") in second_declared_variables
            and left_property.group("right_alias") in scalar_aliases
        ):
            variable = left_property.group("left_var")
            property_name = left_property.group("left_prop")
            function_name = left_property.group("left_func")
            return (
                f"{function_name}({variable}.{property_name})",
                self._with_expression_stage_alias(variable, property_name, function_name),
                left_property.group("operator"),
                OracleNameSanitizer.alias(left_property.group("right_alias")),
            )
        right_property = re.fullmatch(
            alias_ref.format(prefix="left")
            + r"\s*(?P<operator>=|<>|<=|>=|<|>)\s*"
            + property_ref.format(prefix="right")
            + r"\s*",
            expression,
            flags=re.IGNORECASE,
        )
        if (
            right_property
            and right_property.group("right_var") in second_declared_variables
            and right_property.group("left_alias") in scalar_aliases
        ):
            variable = right_property.group("right_var")
            property_name = right_property.group("right_prop")
            function_name = right_property.group("right_func")
            return (
                f"{function_name}({variable}.{property_name})",
                self._with_expression_stage_alias(variable, property_name, function_name),
                self._reverse_operator(right_property.group("operator")),
                OracleNameSanitizer.alias(right_property.group("left_alias")),
            )
        return None

    def _extract_with_match_property_map_correlations(
        self,
        match_clauses: List[MatchClause],
        second_declared_variables: set[str],
        scalar_aliases: set[str],
    ) -> List[Tuple[str, str, str, str]]:
        correlations: List[Tuple[str, str, str, str]] = []
        for clause in match_clauses:
            patterns = (
                clause.path_pattern
                if isinstance(clause.path_pattern, list)
                else [clause.path_pattern]
            )
            for path in patterns:
                for node in path.node_pattern_list:
                    correlations.extend(
                        self._extract_property_map_scalar_correlations(
                            node.symbolic_name,
                            node.property_maps,
                            second_declared_variables,
                            scalar_aliases,
                        )
                    )
                for edge in path.edge_pattern_list:
                    correlations.extend(
                        self._extract_property_map_scalar_correlations(
                            edge.symbolic_name,
                            edge.property_maps,
                            second_declared_variables,
                            scalar_aliases,
                        )
                    )
        return correlations

    def _assign_with_match_property_map_correlation_variables(
        self,
        match_clauses: List[MatchClause],
        scalar_aliases: set[str],
    ) -> None:
        if not scalar_aliases:
            return
        used_variables = self._declared_variables_in_match_clauses(match_clauses)
        node_index = 0
        edge_index = 0

        def has_scalar_map(property_maps: List[Tuple[str, str]]) -> bool:
            return any(
                OracleNameSanitizer.alias(str(value or "").strip()) in scalar_aliases
                for _property_name, value in property_maps
            )

        def next_variable(prefix: str, current_index: int) -> tuple[str, int]:
            while True:
                current_index += 1
                variable = f"{prefix}{current_index}"
                if variable not in used_variables:
                    used_variables.add(variable)
                    return variable, current_index

        for clause in match_clauses:
            patterns = (
                clause.path_pattern
                if isinstance(clause.path_pattern, list)
                else [clause.path_pattern]
            )
            for path in patterns:
                for node in path.node_pattern_list:
                    if not node.symbolic_name and has_scalar_map(node.property_maps):
                        node.symbolic_name, node_index = next_variable("with_corr_n", node_index)
                for edge in path.edge_pattern_list:
                    if not edge.symbolic_name and has_scalar_map(edge.property_maps):
                        edge.symbolic_name, edge_index = next_variable("with_corr_e", edge_index)

    def _extract_property_map_scalar_correlations(
        self,
        variable: str,
        property_maps: List[Tuple[str, str]],
        second_declared_variables: set[str],
        scalar_aliases: set[str],
    ) -> List[Tuple[str, str, str, str]]:
        if variable not in second_declared_variables:
            return []
        correlations: List[Tuple[str, str, str, str]] = []
        retained: List[Tuple[str, str]] = []
        for property_name, property_value in property_maps:
            alias = OracleNameSanitizer.alias(str(property_value or "").strip())
            if alias in scalar_aliases:
                correlations.append((variable, property_name, "=", alias))
            else:
                retained.append((property_name, property_value))
        property_maps[:] = retained
        return correlations

    def _reverse_operator(self, operator: str) -> str:
        return {
            "<": ">",
            ">": "<",
            "<=": ">=",
            ">=": "<=",
        }.get(operator, operator)

    def _declared_variables_in_match_clauses(
        self,
        match_clauses: List[MatchClause],
    ) -> set[str]:
        variables = set()
        for clause in match_clauses:
            paths = (
                clause.path_pattern
                if isinstance(clause.path_pattern, list)
                else [clause.path_pattern]
            )
            for path in paths:
                for node in path.node_pattern_list:
                    if node.symbolic_name:
                        variables.add(node.symbolic_name)
                for edge in path.edge_pattern_list:
                    if edge.symbolic_name:
                        variables.add(edge.symbolic_name)
        return variables

    def _stage_one_join_alias(self, variable: str) -> str:
        return OracleNameSanitizer.alias(f"stage_1_{self._element_projection_alias(variable)}")

    def _with_stage_return_body(
        self,
        with_body: ReturnBody,
        final_body: ReturnBody,
        with_clause: WithClause,
    ) -> ReturnBody:
        carried_variables = self._with_carried_variables(with_body)
        items = list(with_body.return_item_list)
        existing_aliases = {
            OracleNameSanitizer.alias(self._return_alias(item, self._return_expression(item)))
            for item in items
        }
        for variable, property_name in self._with_stage_needed_properties(final_body, with_clause):
            if variable not in carried_variables:
                continue
            alias = self._with_property_stage_alias(variable, property_name)
            if alias in existing_aliases:
                continue
            items.append(
                ReturnItem(
                    symbolic_name=variable,
                    property=property_name,
                    alias=alias,
                    function_name="",
                    expression=f"{variable}.{property_name}",
                )
            )
            existing_aliases.add(alias)
        graph_aliases = self._with_graph_aliases(with_body)
        aliased_property_references: List[Tuple[str, str]] = []
        for item in final_body.return_item_list:
            if item.property:
                aliased_property_references.append((item.symbolic_name, item.property))
            aliased_property_references.extend(self._all_property_references(item.expression))
        for sort_item in final_body.sort_item_list:
            if sort_item.property:
                aliased_property_references.append((sort_item.symbolic_name, sort_item.property))
            aliased_property_references.extend(self._all_property_references(sort_item.expression))
        for alias_variable, property_name in dict.fromkeys(aliased_property_references):
            source_variable = graph_aliases.get(alias_variable)
            if not source_variable or source_variable not in carried_variables:
                continue
            property_name = self._canonical_property_name(source_variable, property_name)
            alias = self._with_property_stage_alias(alias_variable, property_name)
            if alias in existing_aliases:
                continue
            items.append(
                ReturnItem(
                    symbolic_name=source_variable,
                    property=property_name,
                    alias=alias,
                    function_name="",
                    expression=f"{source_variable}.{property_name}",
                )
            )
            existing_aliases.add(alias)
        return ReturnBody(
            items,
            with_body.sort_item_list,
            with_body.skip,
            with_body.limit,
        )

    def _with_graph_aliases(self, with_body: ReturnBody) -> Dict[str, str]:
        aliases: Dict[str, str] = {}
        for item in with_body.return_item_list:
            if (
                item.alias
                and not item.property
                and not item.function_name
                and (not item.expression or item.expression == item.symbolic_name)
                and item.symbolic_name in self._var_kinds
            ):
                aliases[item.alias] = item.symbolic_name
        return aliases

    def _with_stage_needed_properties(
        self,
        final_body: ReturnBody,
        with_clause: WithClause,
    ) -> List[Tuple[str, str]]:
        references = self._final_property_references(final_body)
        for expr in self._as_compare_list(with_clause.compare_expression_list):
            if getattr(expr, "raw_expression", ""):
                references.extend(self._property_references(expr.raw_expression))
            elif expr.property:
                references.append((expr.symbolic_name, expr.property))
        unique: List[Tuple[str, str]] = []
        for variable, property_name in references:
            if (variable, property_name) not in unique:
                unique.append((variable, property_name))
        return unique

    def _with_carried_variables(self, with_body: ReturnBody) -> set[str]:
        carried = set()
        for item in with_body.return_item_list:
            if (
                not item.property
                and not item.function_name
                and (not item.expression or item.expression == item.symbolic_name)
                and item.symbolic_name in self._var_kinds
            ):
                carried.add(item.symbolic_name)
        return carried

    def _with_passthrough_variable_names(self, with_body: ReturnBody) -> set[str]:
        carried = set()
        for item in with_body.return_item_list:
            if (
                not item.property
                and not item.function_name
                and (not item.expression or item.expression == item.symbolic_name)
                and item.symbolic_name
            ):
                carried.add(item.symbolic_name)
        return carried

    def _with_scalar_aliases(self, with_body: ReturnBody) -> set[str]:
        aliases = set()
        for item in with_body.return_item_list:
            if (
                not item.property
                and not item.function_name
                and (
                    not item.expression
                    or (
                        item.expression == item.symbolic_name
                        and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", item.symbolic_name or "")
                    )
                )
            ):
                continue
            alias = item.alias or item.property or item.symbolic_name
            if alias:
                aliases.add(OracleNameSanitizer.alias(alias))
                aliases.add(alias)
        return aliases

    def _final_property_references(self, return_body: ReturnBody) -> List[Tuple[str, str]]:
        references: List[Tuple[str, str]] = []
        for item in return_body.return_item_list:
            if item.property:
                references.append((item.symbolic_name, item.property))
            references.extend(self._property_references(item.expression))
        for sort_item in return_body.sort_item_list:
            if sort_item.property:
                references.append((sort_item.symbolic_name, sort_item.property))
            references.extend(self._property_references(sort_item.expression))
        unique: List[Tuple[str, str]] = []
        for variable, property_name in references:
            if variable in self._var_kinds and (variable, property_name) not in unique:
                unique.append((variable, property_name))
        return unique

    def _with_property_stage_alias(self, variable: str, property_name: str) -> str:
        alias = OracleNameSanitizer.alias(f"{variable}_{property_name}")
        if alias.upper() == self._element_projection_alias(variable).upper():
            return OracleNameSanitizer.alias(f"{variable}_{property_name}_PROP")
        return alias

    def _outer_select_for_with_stage(
        self,
        return_body: ReturnBody,
        distinct: bool,
        carried_variables: set[str],
    ) -> str:
        select_items = []
        return_aliases = self._resolved_return_aliases(return_body)
        for item, resolved_alias in zip(
            return_body.return_item_list,
            return_aliases,
            strict=True,
        ):
            if self._is_complex_aggregate_item(item):
                expression = self._with_stage_aggregate_sql_expression(
                    item.expression,
                    carried_variables,
                )
            elif self._is_aggregate_item(item):
                expression = self._with_stage_aggregate_item_expression(
                    item,
                    carried_variables,
                )
            elif item.property and item.symbolic_name in carried_variables:
                expression = self._with_property_stage_alias(item.symbolic_name, item.property)
            elif item.property:
                expression = self._with_property_stage_alias(item.symbolic_name, item.property)
            elif not item.property and item.symbolic_name in carried_variables:
                expression = self._element_projection_alias(item.symbolic_name)
            elif item.expression and (
                item.expression != item.symbolic_name
                or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", item.expression)
            ):
                expression = self._with_stage_expression(
                    self._translate_sql_expression(item.expression),
                    carried_variables,
                )
            else:
                expression = OracleNameSanitizer.alias(item.symbolic_name)
                if item.function_name:
                    expression = f"{item.function_name.upper()}({expression})"
            select_items.append(f"{expression} AS {OracleNameSanitizer.alias(resolved_alias)}")
        keyword = "SELECT DISTINCT" if distinct else "SELECT"
        return f"{keyword} " + ", ".join(select_items)

    def _with_stage_aggregate_item_expression(
        self,
        item: ReturnItem | SortItem,
        carried_variables: set[str],
    ) -> str:
        function_name = item.function_name.upper()
        if function_name == "COUNT" and item.symbolic_name == "*":
            return "COUNT(*)"
        self._reject_temporal_numeric_aggregate(item)
        symbolic_name = self._strip_distinct_prefix(item.symbolic_name)
        expression = self._aggregate_argument_expression_text(
            item,
            symbolic_name,
        )
        expression = self._translate_sql_expression(expression)
        expression = self._with_stage_expression(expression, carried_variables)
        if expression in carried_variables:
            expression = self._element_projection_alias(expression)
        distinct = "DISTINCT " if self._has_distinct_prefix(item.symbolic_name) else ""
        return self._aggregate_sql_call(function_name, distinct, expression)

    def _with_stage_aggregate_sql_expression(
        self,
        expression: str,
        carried_variables: set[str],
    ) -> str:
        translated = self._translate_sql_expression(expression)
        return self._coalesce_sum_calls(self._with_stage_expression(translated, carried_variables))

    def _with_stage_expression(self, expression: str, carried_variables: set[str]) -> str:
        for variable, property_name in self._property_references(expression):
            if variable not in carried_variables:
                continue
            property_name = self._canonical_property_name(variable, property_name)
            sql_variable = self._var_sql_names.get(variable, variable)
            property_ref = OracleNameSanitizer.quote(property_name, fallback="PROP")
            expression = expression.replace(
                f"{sql_variable}.{property_ref}",
                self._with_property_stage_alias(variable, property_name),
            )
            expression = re.sub(
                rf"\b{re.escape(variable)}\.{re.escape(property_name)}\b",
                self._with_property_stage_alias(variable, property_name),
                expression,
            )
        for variable in carried_variables:
            element_alias = self._element_projection_alias(variable)
            expression = re.sub(
                rf"\b(VERTEX_ID|EDGE_ID)\s*\(\s*{re.escape(variable)}\s*\)",
                element_alias,
                expression,
                flags=re.IGNORECASE,
            )
            expression = re.sub(
                rf"\b(COUNT)\s*\(\s*DISTINCT\s+{re.escape(variable)}\s*\)",
                rf"\1(DISTINCT {element_alias})",
                expression,
                flags=re.IGNORECASE,
            )
            expression = re.sub(
                rf"\b(COUNT|MIN|MAX)\s*\(\s*{re.escape(variable)}\s*\)",
                rf"\1({element_alias})",
                expression,
                flags=re.IGNORECASE,
            )
        variables = sorted(carried_variables, key=len, reverse=True)
        for left in variables:
            for right in variables:
                comparison = (
                    f"{self._element_projection_alias(left)} = "
                    f"{self._element_projection_alias(right)}"
                )
                expression = re.sub(
                    rf"\bNOT\s+VERTEX_EQUAL\s*\(\s*{re.escape(left)}\s*,\s*{re.escape(right)}\s*\)",
                    (
                        f"{self._element_projection_alias(left)} <> "
                        f"{self._element_projection_alias(right)}"
                    ),
                    expression,
                    flags=re.IGNORECASE,
                )
                expression = re.sub(
                    rf"\bNOT\s+EDGE_EQUAL\s*\(\s*{re.escape(left)}\s*,\s*{re.escape(right)}\s*\)",
                    (
                        f"{self._element_projection_alias(left)} <> "
                        f"{self._element_projection_alias(right)}"
                    ),
                    expression,
                    flags=re.IGNORECASE,
                )
                expression = re.sub(
                    rf"\bVERTEX_EQUAL\s*\(\s*{re.escape(left)}\s*,\s*{re.escape(right)}\s*\)",
                    comparison,
                    expression,
                    flags=re.IGNORECASE,
                )
                expression = re.sub(
                    rf"\bEDGE_EQUAL\s*\(\s*{re.escape(left)}\s*,\s*{re.escape(right)}\s*\)",
                    comparison,
                    expression,
                    flags=re.IGNORECASE,
                )
        return expression

    def _with_filters(self, with_clause: WithClause, carried_variables: set[str]) -> List[str]:
        for expr in self._as_compare_list(with_clause.compare_expression_list):
            raw_expression = getattr(expr, "raw_expression", "")
            if raw_expression and re.search(
                r"\b(?:AVG|SUM|COUNT|MIN|MAX)\s*\(",
                raw_expression,
                flags=re.IGNORECASE,
            ):
                raise ValueError("WITH WHERE aggregate filters must be projected first.")
        return [
            self._with_stage_expression(
                self._translate_sql_expression(expr.raw_expression),
                carried_variables,
            )
            if getattr(expr, "raw_expression", "")
            else self._translate_compare_expression(expr)
            for expr in self._as_compare_list(with_clause.compare_expression_list)
        ]

    def _outer_group_order_and_paging_for_with_stage(
        self,
        return_body: ReturnBody,
        carried_variables: set[str],
    ) -> str:
        suffix = ""
        if self._has_aggregate(return_body):
            group_aliases = []
            for item in return_body.return_item_list:
                if self._is_aggregate_item(item):
                    continue
                if item.property and item.symbolic_name in carried_variables:
                    group_aliases.append(
                        self._with_property_stage_alias(item.symbolic_name, item.property)
                    )
                elif not item.property and item.symbolic_name in carried_variables:
                    group_aliases.append(self._element_projection_alias(item.symbolic_name))
                else:
                    group_aliases.append(OracleNameSanitizer.alias(item.symbolic_name))
            if group_aliases:
                suffix += "\nGROUP BY " + ", ".join(dict.fromkeys(group_aliases))
        if return_body.sort_item_list:
            suffix += "\nORDER BY " + ", ".join(
                self._translate_sort_item_for_with_stage(
                    item,
                    return_body,
                    carried_variables,
                )
                for item in return_body.sort_item_list
            )
        if return_body.skip != -1:
            suffix += f"\nOFFSET {return_body.skip} ROWS"
        if return_body.limit != -1:
            suffix += f"\nFETCH FIRST {return_body.limit} ROWS ONLY"
        return suffix

    def _indent_sql(self, sql: str) -> str:
        return "\n".join("  " + line for line in sql.splitlines())

    def _translate_with_projection_columns(self, with_clause: WithClause) -> str:
        projections = []
        for item in with_clause.return_body.return_item_list:
            if not item.alias:
                raise ValueError("WITH projection requires aliases for Oracle SQL output.")
            if item.function_name:
                raise ValueError("Aggregate WITH projection requires staged SQL CTE support.")
            projections.append(
                f"{self._return_expression(item)} AS {OracleNameSanitizer.alias(item.alias)}"
            )
        if not projections:
            raise ValueError("WITH projection cannot be empty.")
        return ", ".join(projections)

    def _outer_select_for_with(self, return_body: ReturnBody, distinct: bool) -> str:
        select_items = []
        return_aliases = self._resolved_return_aliases(return_body)
        for item, resolved_alias in zip(
            return_body.return_item_list,
            return_aliases,
            strict=True,
        ):
            expression = OracleNameSanitizer.alias(item.symbolic_name)
            if item.function_name:
                expression = self._aggregate_sql_call(
                    item.function_name.upper(),
                    "",
                    expression,
                )
            select_items.append(f"{expression} AS {OracleNameSanitizer.alias(resolved_alias)}")
        keyword = "SELECT DISTINCT" if distinct else "SELECT"
        return f"{keyword} " + ", ".join(select_items)

    def _outer_order_and_paging_for_with(
        self,
        return_body: ReturnBody,
        include_group_by: bool = True,
    ) -> str:
        suffix = ""
        if include_group_by and self._has_aggregate(return_body):
            return_aliases = self._resolved_return_aliases(return_body)
            group_aliases = [
                OracleNameSanitizer.alias(alias)
                for item, alias in zip(
                    return_body.return_item_list,
                    return_aliases,
                    strict=True,
                )
                if not self._is_aggregate_item(item)
            ]
            if group_aliases:
                suffix += "\nGROUP BY " + ", ".join(dict.fromkeys(group_aliases))
        if return_body.sort_item_list:
            suffix += "\nORDER BY " + ", ".join(
                self._translate_sort_item(item, return_body) for item in return_body.sort_item_list
            )
        if return_body.skip != -1:
            suffix += f"\nOFFSET {return_body.skip} ROWS"
        if return_body.limit != -1:
            suffix += f"\nFETCH FIRST {return_body.limit} ROWS ONLY"
        return suffix

    def _reset(self) -> None:
        self._var_kinds = {}
        self._var_sql_names = {}
        self._var_labels = {}
        self._path_variables = {}
        self._path_variable_has_quantifier = {}
        self._path_variable_quantified_edges = {}
        self._var_property_redirects = {}
        self._reserved_variables = set()
        self._pattern_where_expressions = []
        self._auto_node_index = 0
        self._auto_edge_index = 0

    def _as_compare_list(self, value) -> List[CompareExpression]:
        if value is None:
            return []
        if isinstance(value, list):
            return [item for item in value if isinstance(item, CompareExpression)]
        if isinstance(value, CompareExpression):
            return [value]
        return []

    def _translate_match_clause(self, match_clause: MatchClause) -> str:
        path_pattern = match_clause.path_pattern
        if isinstance(path_pattern, list):
            return ", ".join(self._translate_path_pattern(item) for item in path_pattern)
        return self._translate_path_pattern(path_pattern)

    def _translate_path_pattern(self, path_pattern: PathPattern) -> str:
        self._reserved_variables.update(
            node.symbolic_name for node in path_pattern.node_pattern_list if node.symbolic_name
        )
        self._reserved_variables.update(
            edge.symbolic_name for edge in path_pattern.edge_pattern_list if edge.symbolic_name
        )
        if path_pattern.edge_pattern_list and all(
            edge.direction == "left" for edge in path_pattern.edge_pattern_list
        ):
            return self._translate_reversed_left_path(path_pattern)
        parts: List[str] = []
        if not path_pattern.node_pattern_list:
            raise ValueError("PathPattern must include at least one node pattern.")
        parts.append(self._translate_node_pattern(path_pattern.node_pattern_list[0]))
        for index, edge in enumerate(path_pattern.edge_pattern_list):
            parts.append(self._translate_edge_pattern(edge))
            parts.append(self._translate_node_pattern(path_pattern.node_pattern_list[index + 1]))
        self._infer_node_labels_from_edge_labels(path_pattern)
        self._register_adjacent_edge_property_redirects(path_pattern)
        self._register_path_variable(path_pattern)
        return "".join(parts)

    def _translate_reversed_left_path(self, path_pattern: PathPattern) -> str:
        parts: List[str] = []
        reversed_nodes = list(reversed(path_pattern.node_pattern_list))
        reversed_edges = list(reversed(path_pattern.edge_pattern_list))
        parts.append(self._translate_node_pattern(reversed_nodes[0]))
        translated_edges: List[EdgePattern] = []
        for index, edge in enumerate(reversed_edges):
            translated_edge = EdgePattern(
                edge.symbolic_name,
                edge.label,
                edge.property_maps,
                "right",
                edge.hop_range,
            )
            parts.append(self._translate_edge_pattern(translated_edge))
            translated_edges.append(translated_edge)
            parts.append(self._translate_node_pattern(reversed_nodes[index + 1]))
        translated_path = PathPattern(reversed_nodes, translated_edges, path_pattern.path_variable)
        self._infer_node_labels_from_edge_labels(translated_path)
        self._register_adjacent_edge_property_redirects(translated_path)
        self._register_path_variable(path_pattern)
        return "".join(parts)

    def _infer_node_labels_from_edge_labels(self, path_pattern: PathPattern) -> None:
        if not self.edge_label_map:
            return
        inferred: Dict[str, set[str]] = {}
        for index, edge in enumerate(path_pattern.edge_pattern_list):
            if edge.direction not in {"left", "right"} or not edge.label:
                continue
            endpoint_labels = self._edge_endpoint_labels(edge.label)
            if not endpoint_labels:
                continue
            src_label, dst_label = endpoint_labels
            if edge.direction == "right":
                src_node = path_pattern.node_pattern_list[index]
                dst_node = path_pattern.node_pattern_list[index + 1]
            else:
                src_node = path_pattern.node_pattern_list[index + 1]
                dst_node = path_pattern.node_pattern_list[index]
            for node, label in ((src_node, src_label), (dst_node, dst_label)):
                if node.symbolic_name and not self._var_labels.get(node.symbolic_name):
                    inferred.setdefault(node.symbolic_name, set()).add(
                        self._source_label_for_graph_label(label)
                    )
        for variable, labels in inferred.items():
            if len(labels) == 1:
                self._var_labels[variable] = next(iter(labels))

    def _source_label_for_graph_label(self, graph_label: str) -> str:
        source_by_lower = {
            str(source).lower(): source
            for source, targets in self.node_label_map.items()
            if graph_label in targets and str(source).lower() != str(graph_label).lower()
        }
        if len(source_by_lower) == 1:
            return next(iter(source_by_lower.values()))
        return graph_label

    def _edge_endpoint_labels(self, edge_label: str) -> Tuple[str, str] | None:
        relation = OracleNameSanitizer.clean(edge_label)
        marker = f"_{relation}_"
        endpoints: set[Tuple[str, str]] = set()
        for graph_label in self._label_map_targets(edge_label, self.edge_label_map):
            if marker not in graph_label:
                continue
            src_label, dst_label = graph_label.split(marker, 1)
            if src_label and dst_label:
                endpoints.add((src_label, dst_label))
        if len(endpoints) == 1:
            return next(iter(endpoints))
        return None

    def _register_adjacent_edge_property_redirects(self, path_pattern: PathPattern) -> None:
        if not self.property_type_map:
            return
        candidates: Dict[Tuple[str, str], set[str]] = {}
        for index, edge in enumerate(path_pattern.edge_pattern_list):
            edge_variable = edge.symbolic_name
            if not edge_variable:
                continue
            edge_properties = set()
            for edge_label in self._possible_graph_labels(edge_variable):
                edge_properties.update(self.property_type_map.get(edge_label, {}))
            if not edge_properties:
                continue
            for node in (
                path_pattern.node_pattern_list[index],
                path_pattern.node_pattern_list[index + 1],
            ):
                node_variable = node.symbolic_name
                if not node_variable:
                    continue
                for property_name in edge_properties:
                    if self._property_type_on_variable(node_variable, property_name):
                        continue
                    candidates.setdefault((node_variable, property_name.lower()), set()).add(
                        edge_variable
                    )
        for key, edge_variables in candidates.items():
            if len(edge_variables) == 1:
                self._var_property_redirects[key] = next(iter(edge_variables))

    def _register_path_variable(self, path_pattern: PathPattern) -> None:
        if not path_pattern.path_variable:
            return
        elements: List[Tuple[str, str]] = []
        for index, node in enumerate(path_pattern.node_pattern_list):
            if node.symbolic_name:
                elements.append(("node", node.symbolic_name))
            if index < len(path_pattern.edge_pattern_list):
                edge = path_pattern.edge_pattern_list[index]
                if edge.symbolic_name:
                    elements.append(("edge", edge.symbolic_name))
        self._path_variables[path_pattern.path_variable] = elements
        self._path_variable_has_quantifier[path_pattern.path_variable] = any(
            edge.hop_range != (-1, -1) for edge in path_pattern.edge_pattern_list
        )
        self._path_variable_quantified_edges[path_pattern.path_variable] = {
            edge.symbolic_name
            for edge in path_pattern.edge_pattern_list
            if edge.symbolic_name and edge.hop_range != (-1, -1)
        }

    def _translate_node_pattern(self, node_pattern: NodePattern) -> str:
        variable = node_pattern.symbolic_name or self._next_node_var()
        node_pattern.symbolic_name = variable
        sql_variable = self._declare_variable(variable, "node", node_pattern.label)
        body = sql_variable
        if node_pattern.label:
            body += f" IS {self._label_expression(node_pattern.label, self.node_label_map, 'NODE')}"
        inline_where = self._property_maps_to_where(sql_variable, node_pattern.property_maps)
        if inline_where:
            self._pattern_where_expressions.append(inline_where)
        return f"({body})"

    def _translate_edge_pattern(self, edge_pattern: EdgePattern) -> str:
        variable = edge_pattern.symbolic_name or self._next_edge_var()
        edge_pattern.symbolic_name = variable
        if edge_pattern.hop_range != (-1, -1) and edge_pattern.property_maps:
            raise ValueError(
                "Property maps on quantified relationships are not supported by Oracle SQL/PGQ."
            )
        sql_variable = self._declare_variable(variable, "edge", edge_pattern.label)
        body = sql_variable
        if edge_pattern.label and self._should_emit_label(
            edge_pattern.label,
            self.edge_label_map,
        ):
            body += f" IS {self._label_expression(edge_pattern.label, self.edge_label_map, 'EDGE')}"
        inline_where = self._property_maps_to_where(sql_variable, edge_pattern.property_maps)
        if inline_where:
            self._pattern_where_expressions.append(inline_where)
        edge = f"[{body}]"
        if edge_pattern.direction == "left":
            edge = f"<-{edge}-"
        elif edge_pattern.direction == "right":
            edge = f"-{edge}->"
        else:
            edge = f"-{edge}-"
        if edge_pattern.hop_range != (-1, -1):
            edge += self._hop_quantifier(edge_pattern.hop_range)
        return edge

    def _should_emit_label(self, source_label: str, label_map: Dict[str, List[str]]) -> bool:
        if not source_label:
            return False
        if not self.strict_property_validation:
            return True
        return any(
            self._label_map_targets(source_part.strip(), label_map)
            != [OracleNameSanitizer.clean(source_part.strip())]
            for source_part in source_label.split("|")
            if source_part.strip()
        )

    def _property_maps_to_where(
        self, variable: str, property_maps: Iterable[Tuple[str, str]]
    ) -> str:
        expressions = []
        for property_name, property_value in property_maps:
            property_name = self._canonical_property_name(variable, property_name)
            property_ref = OracleNameSanitizer.quote(property_name, fallback="PROP")
            map_comparison = self._property_map_comparison(
                variable,
                property_name,
                property_value,
            )
            if map_comparison:
                operator, comparison_value = map_comparison
                expressions.append(f"{variable}.{property_ref} {operator} {comparison_value}")
                continue
            property_value = self._coerce_literal_for_property(
                variable,
                property_name,
                property_value,
            )
            expressions.append(f"{variable}.{property_ref} = {property_value}")
        return " AND ".join(expressions)

    def _property_map_comparison(
        self,
        variable: str,
        property_name: str,
        value: str,
    ) -> Tuple[str, str] | None:
        match = re.fullmatch(
            r"\{\s*(?P<operator>lt|lte|gt|gte|eq|neq)\s*:\s*(?P<value>.+?)\s*\}",
            str(value or "").strip(),
            flags=re.IGNORECASE,
        )
        if not match:
            return None
        operator = {
            "lt": "<",
            "lte": "<=",
            "gt": ">",
            "gte": ">=",
            "eq": "=",
            "neq": "<>",
        }[match.group("operator").lower()]
        comparison_value = self._coerce_literal_for_property(
            variable,
            property_name,
            match.group("value"),
        )
        return operator, comparison_value

    def _coerce_literal_for_property(
        self,
        variable: str,
        property_name: str,
        value: str,
    ) -> str:
        property_type = self._property_type(variable, property_name)
        raw_value = str(value).strip()
        if self._is_string_type(property_type) and raw_value.lower() in {"true", "false"}:
            return f"'{raw_value.lower()}'"
        value = self._translate_sql_expression(raw_value)
        if not self._is_string_type(property_type):
            return value
        if re.fullmatch(r"-?\d+(?:\.\d+)?", value):
            return f"'{value}'"
        date_match = re.fullmatch(r"DATE\s+('[^']*')", value, flags=re.IGNORECASE)
        if date_match:
            return date_match.group(1)
        return value

    def _property_type(self, variable: str, property_name: str) -> str:
        redirect_variable = self._property_redirect_target(variable, property_name)
        if redirect_variable:
            return self._property_type_on_variable(redirect_variable, property_name)
        return self._property_type_on_variable(variable, property_name)

    def _property_type_on_variable(self, variable: str, property_name: str) -> str:
        source_variable = self._source_variable(variable)
        for label in self._possible_graph_labels(source_variable):
            properties = self.property_type_map.get(label, {})
            if property_name in properties:
                return properties[property_name]
            clean_property = OracleNameSanitizer.clean(property_name)
            if clean_property in properties:
                return properties[clean_property]
            snake_property = self._camel_to_snake(property_name)
            if snake_property in properties:
                return properties[snake_property]
            for candidate, property_type in properties.items():
                if candidate.lower() in {
                    property_name.lower(),
                    clean_property.lower(),
                    snake_property.lower(),
                }:
                    return property_type
        return ""

    def _property_redirect_target(self, variable: str, property_name: str) -> str:
        source_variable = self._source_variable(variable)
        clean_property = OracleNameSanitizer.clean(property_name)
        return (
            self._var_property_redirects.get((source_variable, property_name.lower()))
            or self._var_property_redirects.get((source_variable, clean_property.lower()))
            or ""
        )

    def _property_exists_for_variable_kind(self, variable: str, property_name: str) -> bool:
        kind = self._var_kinds.get(self._source_variable(variable))
        if not kind or not self.property_type_map:
            return True
        clean_property = OracleNameSanitizer.clean(property_name)
        candidate_labels = self._property_labels_for_kind(kind)
        for label in candidate_labels:
            properties = self.property_type_map.get(label, {})
            snake_property = self._camel_to_snake(property_name)
            if (
                property_name in properties
                or clean_property in properties
                or snake_property in properties
            ):
                return True
            if any(
                candidate.lower()
                in {property_name.lower(), clean_property.lower(), snake_property.lower()}
                for candidate in properties
            ):
                return True
        return False

    def _property_labels_for_kind(self, kind: str) -> set[str]:
        label_map = self.edge_label_map if kind == "edge" else self.node_label_map
        if label_map:
            labels = set(label_map)
            for targets in label_map.values():
                labels.update(targets)
            return labels & set(self.property_type_map)
        if kind == "edge":
            edge_labels = {label for labels in self.edge_label_map.values() for label in labels}
            return edge_labels & set(self.property_type_map)
        edge_labels = {label for labels in self.edge_label_map.values() for label in labels}
        return set(self.property_type_map) - edge_labels

    def _canonical_property_name(self, variable: str, property_name: str) -> str:
        resolved = self._resolve_pseudo_property(variable, property_name)
        if resolved:
            return resolved
        if (
            self.strict_property_validation
            and self.property_type_map
            and property_name.lower() in {"identity", "id"}
            and not self._property_type(variable, property_name)
        ):
            raise ValueError(f'Cannot resolve pseudo-property "{property_name}" for "{variable}".')
        redirect_variable = self._property_redirect_target(variable, property_name)
        if redirect_variable:
            variable = redirect_variable
        if not self.property_type_map:
            return property_name
        possible_labels = self._possible_graph_labels(variable)
        for label in possible_labels:
            properties = self.property_type_map.get(label, {})
            if property_name in properties:
                return property_name
            clean_property = OracleNameSanitizer.clean(property_name)
            if clean_property in properties:
                return clean_property
            snake_property = self._camel_to_snake(property_name)
            if snake_property in properties:
                return snake_property
            for candidate in properties:
                if candidate.lower() in {
                    property_name.lower(),
                    clean_property.lower(),
                    snake_property.lower(),
                }:
                    return candidate
        if self.strict_property_validation and self._possible_graph_labels(variable):
            raise ValueError(
                f'Property "{property_name}" is not defined for variable "{variable}".'
            )
        if self.strict_property_validation and self._var_labels.get(
            self._source_variable(variable)
        ):
            raise ValueError(
                f'Label for variable "{variable}" is not mapped to an Oracle graph label.'
            )
        if (
            self.strict_property_validation
            and self._var_kinds.get(self._source_variable(variable))
            and not possible_labels
            and not property_name.lower().endswith("_id")
            and property_name.lower() not in {"id", "identity"}
            and not self._property_exists_for_variable_kind(variable, property_name)
        ):
            raise ValueError(
                f'Property "{property_name}" is not defined for variable "{variable}".'
            )
        return property_name

    def _camel_to_snake(self, value: str) -> str:
        return re.sub(r"(?<!^)(?=[A-Z])", "_", str(value or "")).lower()

    def _resolve_pseudo_property(self, variable: str, property_name: str) -> str:
        if not self.property_type_map:
            return ""
        source_variable = self._source_variable(variable)
        source_label = self._var_labels.get(source_variable, "")
        clean_label = OracleNameSanitizer.clean(source_label)
        property_lower = property_name.lower()
        pseudo_names = {"identity", "id"}
        if source_label:
            pseudo_names.add(f"{source_label}_id".lower())
            pseudo_names.add(f"{clean_label}_id".lower())
        if property_lower not in pseudo_names:
            return ""
        primary_key = self._primary_key_for_variable(variable)
        if not primary_key:
            return ""
        if self._property_type(variable, property_name):
            return ""
        return primary_key

    def _primary_key_for_variable(self, variable: str) -> str:
        source_variable = self._source_variable(variable)
        label = self._var_labels.get(source_variable, "")
        if not label:
            return ""
        key_map = (
            self.edge_primary_key_map
            if self._var_kinds.get(source_variable) == "edge"
            else self.node_primary_key_map
        )
        for candidate in [label, *self._possible_graph_labels(source_variable)]:
            if candidate in key_map:
                return key_map[candidate]
            for key_label, primary_key in key_map.items():
                if key_label.lower() == candidate.lower():
                    return primary_key
        properties_by_label = [
            self.property_type_map.get(candidate, {})
            for candidate in self._possible_graph_labels(source_variable)
        ]
        for properties in properties_by_label:
            for property_name in properties:
                if property_name.lower() in {
                    f"{label}_id".lower(),
                    f"{OracleNameSanitizer.clean(label)}_id".lower(),
                }:
                    return property_name
        for properties in properties_by_label:
            id_like = [name for name in properties if name.lower().endswith("_id")]
            if len(id_like) == 1:
                return id_like[0]
        return ""

    def _possible_graph_labels(self, variable: str) -> List[str]:
        source_variable = self._source_variable(variable)
        label = self._var_labels.get(source_variable, "")
        if not label:
            return []
        label_map = (
            self.edge_label_map
            if self._var_kinds.get(source_variable) == "edge"
            else self.node_label_map
        )
        labels: List[str] = []
        for source_part in label.split("|"):
            source_part = source_part.strip()
            if (
                self.strict_property_validation
                and label_map
                and not self._label_map_has_explicit_target(source_part, label_map)
            ):
                continue
            labels.extend(self._label_map_targets(source_part, label_map))
        return list(dict.fromkeys(labels))

    def _label_map_targets(self, source_label: str, label_map: Dict[str, List[str]]) -> List[str]:
        clean_label = OracleNameSanitizer.clean(source_label)
        return (
            label_map.get(source_label)
            or label_map.get(source_label.lower())
            or label_map.get(clean_label)
            or label_map.get(clean_label.lower())
            or [clean_label]
        )

    def _label_map_has_explicit_target(
        self,
        source_label: str,
        label_map: Dict[str, List[str]],
    ) -> bool:
        clean_label = OracleNameSanitizer.clean(source_label)
        target_labels = {target for targets in label_map.values() for target in targets}
        return (
            any(
                key in label_map
                for key in (
                    source_label,
                    source_label.lower(),
                    clean_label,
                    clean_label.lower(),
                )
            )
            or source_label in target_labels
            or clean_label in target_labels
        )

    def _is_string_type(self, property_type: str) -> bool:
        normalized = str(property_type or "").upper()
        return "CHAR" in normalized or "CLOB" in normalized or normalized == "STRING"

    def _is_temporal_type(self, property_type: str) -> bool:
        normalized = str(property_type or "").upper()
        return "DATE" in normalized or "TIMESTAMP" in normalized

    def _source_variable(self, variable: str) -> str:
        for source, sql_name in self._var_sql_names.items():
            if variable in (source, sql_name):
                return source
        return variable

    def _hop_quantifier(self, hop_range: Tuple[int, int]) -> str:
        lower, upper = hop_range
        if lower == upper:
            return f"{{{lower}}}"
        if lower == -1:
            return f"{{1,{upper}}}"
        if upper == -1:
            raise ValueError(
                "Open-ended variable-length paths are not supported by Oracle SQL/PGQ."
            )
        return f"{{{lower},{upper}}}"

    def _label_expression(
        self,
        source_label: str,
        label_map: Dict[str, List[str]],
        fallback: str,
    ) -> str:
        labels: List[str] = []
        for source_part in source_label.split("|"):
            source_part = source_part.strip()
            if not source_part:
                continue
            labels.extend(self._label_map_targets(source_part, label_map))
        if not labels:
            labels = [source_label]
        return " | ".join(OracleNameSanitizer.quote(label, fallback=fallback) for label in labels)

    def _declare_variable(self, variable: str, kind: str, label: str = "") -> str:
        self._var_kinds[variable] = kind
        if label:
            self._var_labels[variable] = label
        self._var_sql_names.setdefault(variable, self._sql_variable_name(variable))
        return self._var_sql_names[variable]

    def _sql_variable_name(self, variable: str) -> str:
        if str(variable or "").upper() == "USER":
            return "user_var"
        return OracleNameSanitizer.alias(variable)

    def _where_parts(self, where_expressions: List[CompareExpression]) -> List[str]:
        for expression in where_expressions:
            raw_expression = getattr(expression, "raw_expression", "")
            if self._contains_aggregate_function(raw_expression):
                raise ValueError("Aggregate functions in MATCH WHERE are not supported.")
        return self._pattern_where_expressions + [
            self._translate_compare_expression(expr) for expr in where_expressions
        ]

    def _translate_columns(
        self,
        return_body: ReturnBody | None,
        aggregate_query: bool = False,
    ) -> str:
        if return_body is None or not return_body.return_item_list:
            variables = [var for var, kind in self._var_kinds.items() if kind == "node"]
            if not variables:
                variables = list(self._var_kinds.keys())
            return ", ".join(
                f"{self._element_id_expression(var)} AS {OracleNameSanitizer.alias(var + '_ID')}"
                for var in variables
            )

        if aggregate_query:
            return self._translate_aggregate_columns(return_body)

        return_aliases = self._resolved_return_aliases(return_body)
        projections = []
        for item, alias in zip(return_body.return_item_list, return_aliases, strict=True):
            if item.symbolic_name in self._path_variables and not item.property:
                projections.extend(self._translate_path_return_item(item, alias))
            else:
                projections.append(self._translate_return_item(item, alias))
        projected_aliases = {OracleNameSanitizer.alias(alias) for alias in return_aliases}
        for sort_item in return_body.sort_item_list:
            if self._is_aggregate_sort(sort_item):
                continue
            alias = OracleNameSanitizer.alias(self._sort_alias(sort_item, return_body))
            if alias in projected_aliases:
                continue
            if sort_item.expression:
                projections.append(
                    f"{self._translate_sql_expression(sort_item.expression)} AS {alias}"
                )
                projected_aliases.add(alias)
        return ", ".join(projections)

    def _translate_path_return_item(self, return_item: ReturnItem, alias: str) -> List[str]:
        projections = []
        alias_prefix = OracleNameSanitizer.alias(alias or return_item.symbolic_name)
        quantified_edges = self._path_variable_quantified_edges.get(
            return_item.symbolic_name,
            set(),
        )
        for kind, variable in self._path_variables.get(return_item.symbolic_name, []):
            sql_variable = self._var_sql_names.get(variable, variable)
            if kind == "edge" and variable in quantified_edges:
                projection_alias = OracleNameSanitizer.alias(f"{alias_prefix}_{variable}_IDS")
                projections.append(f"JSON_ARRAYAGG(EDGE_ID({sql_variable})) AS {projection_alias}")
            else:
                expression = "EDGE_ID" if kind == "edge" else "VERTEX_ID"
                projection_alias = OracleNameSanitizer.alias(f"{alias_prefix}_{variable}_ID")
                projections.append(f"{expression}({sql_variable}) AS {projection_alias}")
        if not projections:
            raise ValueError(f"Path variable {return_item.symbolic_name} is not declared.")
        return projections

    def _translate_return_item(
        self,
        return_item: ReturnItem,
        alias: str | None = None,
    ) -> str:
        expression = self._return_expression(return_item)
        if return_item.function_name.upper() in self.AGGREGATE_FUNCTIONS:
            expression = self._aggregate_sql_call(
                return_item.function_name.upper(),
                "",
                expression,
            )
        alias = alias or self._return_alias(return_item, expression)
        return f"{expression} AS {OracleNameSanitizer.alias(alias)}"

    def _translate_aggregate_columns(self, return_body: ReturnBody) -> str:
        projections: List[Tuple[str, str]] = []
        return_aliases = self._resolved_return_aliases(return_body)
        for item, alias in zip(return_body.return_item_list, return_aliases, strict=True):
            if self._is_complex_aggregate_item(item):
                for expression, expression_alias in self._aggregate_expression_projections(
                    item.expression
                ):
                    projections.append((expression, expression_alias))
            elif self._is_aggregate_item(item):
                argument_expression, argument_alias = self._aggregate_argument_projection(item)
                if argument_expression:
                    projections.append((argument_expression, argument_alias))
            else:
                expression = self._return_expression(item)
                projections.append((expression, alias))

        outer_aliases = {OracleNameSanitizer.alias(alias) for alias in return_aliases}
        for sort_item in return_body.sort_item_list:
            sort_alias = OracleNameSanitizer.alias(self._sort_alias(sort_item, return_body))
            if sort_alias in outer_aliases:
                continue
            if self._is_complex_aggregate_item(sort_item):
                for expression, expression_alias in self._aggregate_expression_projections(
                    sort_item.expression
                ):
                    projections.append((expression, expression_alias))
            elif self._is_aggregate_sort(sort_item):
                argument_expression, argument_alias = self._aggregate_argument_projection(sort_item)
                if argument_expression:
                    projections.append((argument_expression, argument_alias))
            elif sort_item.expression:
                if self._sort_expression_uses_return_aliases(sort_item, return_body):
                    continue
                projections.append(
                    (
                        self._translate_sql_expression(sort_item.expression),
                        self._sort_alias(sort_item, return_body),
                    )
                )

        unique: Dict[str, str] = {}
        for expression, alias in projections:
            unique.setdefault(OracleNameSanitizer.alias(alias), expression)
        if not unique:
            unique["dummy_value"] = "1"
        return ", ".join(f"{expression} AS {alias}" for alias, expression in unique.items())

    def _outer_select(
        self,
        return_body: ReturnBody | None,
        distinct: bool,
        aggregate_query: bool,
        hidden_sort_aliases: List[str] | None = None,
    ) -> str:
        hidden_sort_aliases = hidden_sort_aliases or []
        if return_body is None or not aggregate_query:
            if hidden_sort_aliases and return_body is not None:
                select_items = []
                for alias in self._resolved_return_aliases(return_body):
                    select_items.append(OracleNameSanitizer.alias(alias))
                keyword = "SELECT DISTINCT" if distinct else "SELECT"
                return f"{keyword} " + ", ".join(select_items)
            return "SELECT DISTINCT *" if distinct else "SELECT *"
        select_items = []
        return_aliases = self._resolved_return_aliases(return_body)
        for item, resolved_alias in zip(return_body.return_item_list, return_aliases, strict=True):
            if self._is_complex_aggregate_item(item):
                expression = self._outer_aggregate_sql_expression(item.expression)
                alias = self._return_alias(item, expression)
                select_items.append(f"{expression} AS {OracleNameSanitizer.alias(alias)}")
            elif self._is_aggregate_item(item):
                expression = self._outer_aggregate_expression(item)
                alias = self._return_alias(item, expression)
                select_items.append(f"{expression} AS {OracleNameSanitizer.alias(alias)}")
            else:
                select_items.append(OracleNameSanitizer.alias(resolved_alias))
        keyword = "SELECT DISTINCT" if distinct else "SELECT"
        return f"{keyword} " + ", ".join(select_items)

    def _outer_aggregate_expression(self, item: ReturnItem | SortItem) -> str:
        function_name = item.function_name.upper()
        if function_name == "COUNT" and item.symbolic_name == "*":
            return "COUNT(*)"
        self._reject_temporal_numeric_aggregate(item)
        _, argument_alias = self._aggregate_argument_projection(item)
        distinct = ""
        if self._has_distinct_prefix(item.symbolic_name):
            distinct = "DISTINCT "
        return self._aggregate_sql_call(
            function_name,
            distinct,
            OracleNameSanitizer.alias(argument_alias),
        )

    def _aggregate_sql_call(self, function_name: str, distinct: str, expression: str) -> str:
        aggregate = f"{function_name}({distinct}{expression})"
        if function_name.upper() == "SUM":
            return f"COALESCE({aggregate}, 0)"
        return aggregate

    def _coalesce_sum_calls(self, expression: str) -> str:
        result: List[str] = []
        index = 0
        while index < len(expression):
            match = re.search(r"\bSUM\s*\(", expression[index:], flags=re.IGNORECASE)
            if not match:
                result.append(expression[index:])
                break
            start = index + match.start()
            open_paren = index + match.end() - 1
            if self._inside_coalesce_call(expression, start):
                result.append(expression[index : open_paren + 1])
                index = open_paren + 1
                continue
            close_paren = self._matching_paren_index(expression, open_paren)
            if close_paren == -1:
                result.append(expression[index:])
                break
            result.append(expression[index:start])
            result.append(f"COALESCE({expression[start : close_paren + 1]}, 0)")
            index = close_paren + 1
        return "".join(result)

    def _inside_coalesce_call(self, expression: str, start: int) -> bool:
        prefix = expression[max(0, start - 20) : start]
        return bool(re.search(r"COALESCE\s*\(\s*$", prefix, flags=re.IGNORECASE))

    def _matching_paren_index(self, expression: str, open_paren: int) -> int:
        depth = 0
        in_single = False
        for index in range(open_paren, len(expression)):
            char = expression[index]
            if char == "'":
                in_single = not in_single
                continue
            if in_single:
                continue
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    return index
        return -1

    def _aggregate_argument_projection(self, item: ReturnItem | SortItem) -> Tuple[str, str]:
        if item.function_name.upper() == "COUNT" and item.symbolic_name == "*":
            return "", "dummy_value"
        self._reject_temporal_numeric_aggregate(item)
        self._reject_temporal_numeric_aggregate_expression(item.expression)
        symbolic_name = self._strip_distinct_prefix(item.symbolic_name)
        argument = ReturnItem(
            symbolic_name=symbolic_name,
            property=item.property,
            alias="",
            function_name="",
            expression=self._aggregate_argument_expression_text(item, symbolic_name),
        )
        expression = self._return_expression(argument)
        return (
            expression,
            item.property or self._default_expression_alias(symbolic_name, expression),
        )

    def _reject_temporal_numeric_aggregate(self, item: ReturnItem | SortItem) -> None:
        if item.function_name.upper() not in {"AVG", "SUM"}:
            return
        if not item.property:
            return
        property_type = self._property_type(item.symbolic_name, item.property)
        if self._is_temporal_type(property_type):
            raise ValueError(
                f"{item.function_name.upper()} over temporal property "
                f"{item.symbolic_name}.{item.property} requires explicit numeric conversion."
            )
        if self._is_string_type(property_type):
            raise ValueError(
                f"{item.function_name.upper()} over string property "
                f"{item.symbolic_name}.{item.property} requires explicit numeric conversion."
            )

    def _aggregate_expression_projections(self, expression: str) -> List[Tuple[str, str]]:
        self._reject_temporal_numeric_aggregate_expression(expression)
        expression = self._translate_collect_size_aggregate_expression(expression)
        projections: List[Tuple[str, str]] = []
        seen = set()
        property_aliases = self._aggregate_property_aliases(expression)
        for variable, property_name in self._property_references(expression):
            property_name = self._canonical_property_name(variable, property_name)
            alias = property_aliases[(variable, property_name)]
            if alias in seen:
                continue
            seen.add(alias)
            property_ref = OracleNameSanitizer.quote(property_name, fallback="PROP")
            sql_variable = self._var_sql_names.get(variable, variable)
            projections.append((f"{sql_variable}.{property_ref}", alias))
        for variable in self._aggregate_element_references(expression):
            alias = self._element_projection_alias(variable)
            if alias in seen:
                continue
            seen.add(alias)
            projections.append((self._element_id_expression(variable), alias))
        if not projections:
            projections.append(("1", "dummy_value"))
        return projections

    def _outer_aggregate_sql_expression(self, expression: str) -> str:
        self._reject_temporal_numeric_aggregate_expression(expression)
        expression = self._translate_collect_size_aggregate_expression(expression)
        translated = self._translate_sql_expression(expression)
        property_aliases = self._aggregate_property_aliases(expression)
        for variable, property_name in self._property_references(expression):
            property_name = self._canonical_property_name(variable, property_name)
            sql_variable = self._var_sql_names.get(variable, variable)
            property_ref = OracleNameSanitizer.quote(property_name, fallback="PROP")
            alias = OracleNameSanitizer.alias(property_aliases[(variable, property_name)])
            translated = translated.replace(f"{sql_variable}.{property_ref}", alias)
        for variable in self._aggregate_element_references(expression):
            alias = OracleNameSanitizer.alias(self._element_projection_alias(variable))
            translated = re.sub(
                rf"\b(COUNT)\s*\(\s*DISTINCT\s+{re.escape(variable)}\s*\)",
                rf"\1(DISTINCT {alias})",
                translated,
                flags=re.IGNORECASE,
            )
            translated = re.sub(
                rf"\b(COUNT|MIN|MAX)\s*\(\s*{re.escape(variable)}\s*\)",
                rf"\1({alias})",
                translated,
                flags=re.IGNORECASE,
            )
        return self._coalesce_sum_calls(translated)

    def _reject_temporal_numeric_aggregate_expression(self, expression: str) -> None:
        expression = expression or ""
        if not self._contains_aggregate_function(expression):
            return
        if re.search(r"\bduration\s*\.\s*between\s*\(", expression, flags=re.IGNORECASE):
            raise ValueError("duration.between aggregate requires explicit numeric conversion.")
        lowered = expression.lower()
        if "date(" in lowered or "tofloat(" in lowered or "tointeger(" in lowered:
            return
        if "-" not in expression:
            return
        for variable, property_name in self._property_references(expression):
            property_type = self._property_type(variable, property_name)
            if self._is_temporal_type(property_type):
                raise ValueError(
                    "Temporal arithmetic aggregate requires explicit numeric conversion."
                )

    def _translate_collect_size_aggregate_expression(self, expression: str) -> str:
        expression = re.sub(
            r"\bsize\s*\(\s*apoc\.coll\.toSet\s*\(\s*collect\s*\(\s*"
            r"(?P<body>[^()]+?)\s*\)\s*\)\s*\)",
            lambda match: f"COUNT(DISTINCT {match.group('body').strip()})",
            expression or "",
            flags=re.IGNORECASE,
        )
        return re.sub(
            r"\bsize\s*\(\s*collect\s*\(\s*(?P<distinct>distinct\s+)?"
            r"(?P<body>[^()]+?)\s*\)\s*\)",
            lambda match: (
                "COUNT("
                + ("DISTINCT " if match.group("distinct") else "")
                + match.group("body").strip()
                + ")"
            ),
            expression or "",
            flags=re.IGNORECASE,
        )

    def _aggregate_property_aliases(self, expression: str) -> Dict[Tuple[str, str], str]:
        references = [
            (variable, self._canonical_property_name(variable, property_name))
            for variable, property_name in self._property_references(expression)
        ]
        aliases: Dict[Tuple[str, str], str] = {}
        for variable, property_name in references:
            aliases[(variable, property_name)] = f"{variable}_{property_name}"
        return aliases

    def _aggregate_element_references(self, expression: str) -> List[str]:
        return [
            variable
            for variable in self._aggregate_element_reference_names(expression)
            if variable in self._var_kinds
        ]

    def _aggregate_element_reference_names(self, expression: str) -> List[str]:
        protected, _ = self._protect_string_literals(expression or "")
        variables: List[str] = []
        for match in re.finditer(
            r"\b(?:COUNT|MIN|MAX)\s*\(\s*(?:DISTINCT\s+)?"
            r"(?P<variable>[A-Za-z_][A-Za-z0-9_]*)\s*\)",
            protected,
            flags=re.IGNORECASE,
        ):
            variables.append(match.group("variable"))
        return list(dict.fromkeys(variables))

    def _element_projection_alias(self, variable: str) -> str:
        return f"{variable}_VALUE"

    def _property_references(self, expression: str) -> List[Tuple[str, str]]:
        protected, _ = self._protect_string_literals(expression or "")
        references: List[Tuple[str, str]] = []
        for match in re.finditer(
            r"\b(?P<variable>[A-Za-z_][A-Za-z0-9_]*)\."
            r"(?:\"(?P<quoted_property>[^\"]+)\"|"
            r"(?P<property>[A-Za-z_][A-Za-z0-9_$#-]*)\b)",
            protected,
        ):
            variable = match.group("variable")
            property_name = match.group("quoted_property") or match.group("property")
            if variable in self._var_kinds:
                references.append((variable, property_name))
        return references

    def _property_projection_alias(self, variable: str, property_name: str) -> str:
        return property_name

    def _aggregate_argument_expression_text(
        self,
        item: ReturnItem | SortItem,
        symbolic_name: str,
    ) -> str:
        if not item.expression:
            return symbolic_name
        expression = item.expression.strip()
        if expression.upper().startswith(f"{item.function_name.upper()}(") and expression.endswith(
            ")"
        ):
            expression = expression[len(item.function_name) + 1 : -1].strip()
        return self._strip_distinct_prefix(expression)

    def _translate_sort_item(self, sort_item: SortItem, return_body: ReturnBody) -> str:
        if sort_item.expression and self._sort_expression_uses_return_aliases(
            sort_item,
            return_body,
        ):
            expression = self._translate_sql_expression(sort_item.expression)
            return f"{expression}{self._sql_sort_order(sort_item.order)}"
        alias = self._sort_alias(sort_item, return_body)
        order = self._sql_sort_order(sort_item.order)
        return f"{OracleNameSanitizer.alias(alias)}{order}"

    def _translate_sort_item_for_with_stage(
        self,
        sort_item: SortItem,
        return_body: ReturnBody,
        carried_variables: set[str],
    ) -> str:
        if sort_item.expression:
            alias = self._with_stage_expression(
                self._translate_sql_expression(sort_item.expression),
                carried_variables,
            )
            return f"{alias}{self._sql_sort_order(sort_item.order)}"
        if sort_item.property and sort_item.symbolic_name in carried_variables:
            alias = self._with_property_stage_alias(
                sort_item.symbolic_name,
                self._canonical_property_name(sort_item.symbolic_name, sort_item.property),
            )
        else:
            alias = self._sort_alias(sort_item, return_body)
        return f"{OracleNameSanitizer.alias(alias)}{self._sql_sort_order(sort_item.order)}"

    def _sql_sort_order(self, order: str) -> str:
        normalized = str(order or "").upper()
        if normalized == "DESCENDING":
            normalized = "DESC"
        elif normalized == "ASCENDING":
            normalized = "ASC"
        return f" {normalized}" if normalized else ""

    def _sort_expression_uses_return_aliases(
        self,
        sort_item: SortItem,
        return_body: ReturnBody,
    ) -> bool:
        expression = sort_item.expression or ""
        if not expression:
            return False
        if self._property_references(expression):
            return False
        aliases = {
            OracleNameSanitizer.alias(alias) for alias in self._resolved_return_aliases(return_body)
        }
        if not aliases:
            return False
        protected, _ = self._protect_string_literals(expression)
        return any(re.search(rf"\b{re.escape(alias)}\b", protected) for alias in aliases)

    def _sort_alias(self, sort_item: SortItem, return_body: ReturnBody) -> str:
        for return_item in return_body.return_item_list:
            if (
                return_item.symbolic_name == sort_item.symbolic_name
                and return_item.property == sort_item.property
                and return_item.function_name == sort_item.function_name
            ):
                return self._return_alias(
                    return_item,
                    return_item.expression or return_item.symbolic_name,
                )
            if sort_item.expression and sort_item.expression == return_item.alias:
                return return_item.alias
            if sort_item.expression and sort_item.expression == return_item.expression:
                return (
                    return_item.alias
                    or return_item.property
                    or self._default_expression_alias(
                        return_item.symbolic_name,
                        sort_item.expression,
                    )
                )
        alias = sort_item.property or sort_item.symbolic_name
        if sort_item.function_name:
            alias = f"{sort_item.function_name}_{alias}"
        return alias

    def _return_alias(self, return_item: ReturnItem, expression: str) -> str:
        return (
            return_item.alias
            or return_item.property
            or self._default_expression_alias(
                return_item.symbolic_name,
                return_item.expression or expression,
            )
        )

    def _return_expression(self, return_item: ReturnItem) -> str:
        if return_item.expression:
            expression = return_item.expression.strip()
            if (
                expression == return_item.symbolic_name
                and return_item.symbolic_name
                and return_item.symbolic_name in self._var_kinds
            ):
                return self._element_id_expression(return_item.symbolic_name)
            if return_item.function_name:
                if return_item.function_name.upper() not in self.AGGREGATE_FUNCTIONS:
                    return self._translate_sql_expression(expression)
                return self._value_expression(return_item.symbolic_name, return_item.property)
            return self._translate_sql_expression(expression)
        return self._value_expression(return_item.symbolic_name, return_item.property)

    def _value_expression(self, symbolic_name: str, property_name: str) -> str:
        symbolic_name = self._strip_distinct_prefix(symbolic_name)
        if symbolic_name == "*":
            return "*"
        sql_symbolic_name = self._var_sql_names.get(symbolic_name, symbolic_name)
        if property_name:
            if property_name.lower() == "label" and not self._property_type(
                symbolic_name, property_name
            ):
                return self._label_value_expression(symbolic_name)
            if self._is_edge_identity_property(symbolic_name, property_name):
                return f"EDGE_ID({sql_symbolic_name})"
            redirect_variable = self._property_redirect_target(symbolic_name, property_name)
            property_name = self._canonical_property_name(symbolic_name, property_name)
            property_ref = OracleNameSanitizer.quote(property_name, fallback="PROP")
            if redirect_variable:
                sql_symbolic_name = self._var_sql_names.get(redirect_variable, redirect_variable)
            return f"{sql_symbolic_name}.{property_ref}"
        return self._element_id_expression(symbolic_name)

    def _is_edge_identity_property(self, variable: str, property_name: str) -> bool:
        source_variable = self._source_variable(variable)
        if self._var_kinds.get(source_variable) != "edge":
            return False
        if property_name.lower() not in {"identity", "id"}:
            return False
        return self._primary_key_for_variable(source_variable).upper() == "EDGE_ID"

    def _label_value_expression(self, variable: str) -> str:
        labels = self._possible_graph_labels(variable)
        sql_variable = self._var_sql_names.get(variable, variable)
        if not labels:
            raise ValueError(f'Cannot resolve pseudo-property "label" for "{variable}".')
        if len(labels) == 1:
            return f"'{labels[0]}'"
        branches = [
            f"WHEN {sql_variable} IS LABELED {OracleNameSanitizer.quote(label, fallback='LABEL')} "
            f"THEN '{self._sql_string_value(label)}'"
            for label in labels
        ]
        return "CASE " + " ".join(branches) + " END"

    def _sql_string_value(self, value: str) -> str:
        return str(value).replace("'", "''")

    def _element_id_expression(self, variable: str) -> str:
        sql_variable = self._var_sql_names.get(variable, variable)
        if self._var_kinds.get(variable) == "edge":
            return f"EDGE_ID({sql_variable})"
        return f"VERTEX_ID({sql_variable})"

    def _translate_compare_expression(self, compare_expression: CompareExpression) -> str:
        raw_expression = getattr(compare_expression, "raw_expression", "")
        if raw_expression:
            return self._translate_sql_expression(raw_expression)
        prop = ""
        if compare_expression.property:
            property_name = self._canonical_property_name(
                compare_expression.symbolic_name,
                compare_expression.property,
            )
            prop = f".{OracleNameSanitizer.quote(property_name, fallback='PROP')}"
        operator = {
            "equal": "=",
            "neq": "<>",
            "less": "<",
            "greater": ">",
            "leq": "<=",
            "geq": ">=",
        }.get(compare_expression.comparison_type, "=")
        sql_symbolic_name = self._var_sql_names.get(
            compare_expression.symbolic_name,
            compare_expression.symbolic_name,
        )
        return f"{sql_symbolic_name}{prop} {operator} {compare_expression.comparison_value}"

    def _translate_sql_expression(self, expression: str) -> str:
        protected, literals = self._protect_string_literals(expression)
        protected = re.sub(
            r"\bdate\s*\(\s*__SQL_LITERAL_(\d+)__\s*\)",
            lambda match: f"DATE __SQL_LITERAL_{match.group(1)}__",
            protected,
            flags=re.IGNORECASE,
        )
        protected = re.sub(
            r"\bdate\s*\(\s*\)",
            "TRUNC(CURRENT_DATE)",
            protected,
            flags=re.IGNORECASE,
        )
        if re.search(r"\b(?:NOT\s+)?EXISTS\s*\(\s*\(", protected, flags=re.IGNORECASE):
            raise ValueError("Cypher pattern predicates require SQL CTE rewrite support.")
        protected = self._translate_date_property_extractors(protected)
        protected = self._translate_property_extractors(protected)
        protected = self._translate_label_predicates(protected)
        protected = self._translate_date_function_property_calls(protected)
        protected = re.sub(
            r"\b([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_$#-]*)\b",
            self._translate_property_reference_match,
            protected,
        )
        protected = self._translate_chained_comparisons(protected)
        protected = self._translate_string_predicates(protected)
        protected = re.sub(
            r"\bdate\s*\(([^()]+)\)",
            r"CAST(\1 AS DATE)",
            protected,
            flags=re.IGNORECASE,
        )
        protected = self._coerce_typed_property_comparisons(protected)
        protected = self._coerce_date_function_property_comparisons(protected)
        protected = self._translate_element_id_comparisons(protected)
        protected = self._translate_id_function_calls(protected)
        protected = self._translate_element_comparisons(protected)
        protected = self._translate_split_size(protected, literals)
        protected = self._translate_modulo(protected)
        protected = re.sub(r"(?<!')\btrue\b(?!')", "1", protected, flags=re.IGNORECASE)
        protected = re.sub(r"(?<!')\bfalse\b(?!')", "0", protected, flags=re.IGNORECASE)
        protected = re.sub(r"\bsize\s*\(", "LENGTH(", protected, flags=re.IGNORECASE)
        protected = re.sub(r"\btoFloat\s*\(", "TO_NUMBER(", protected, flags=re.IGNORECASE)
        protected = re.sub(r"\btoString\s*\(", "TO_CHAR(", protected, flags=re.IGNORECASE)
        protected = self._translate_to_integer(protected)
        protected = self._translate_substring(protected)
        protected = self._translate_left_function(protected)
        protected = self._guard_numeric_division(protected)
        protected = self._translate_string_concatenation(protected)
        protected = self._translate_modulo(protected)
        protected = re.sub(r"\bCOUNT\s*\(\s*\)", "COUNT(*)", protected, flags=re.IGNORECASE)
        protected = self._restore_string_literals(protected, literals)
        return protected

    def _translate_chained_comparisons(self, expression: str) -> str:
        operand = (
            r'(?:[A-Za-z_][A-Za-z0-9_]*\."[^"]+"|'
            r"DATE\s+__SQL_LITERAL_\d+__|"
            r"__SQL_LITERAL_\d+__|"
            r"-?\d+(?:\.\d+)?)"
        )
        return re.sub(
            rf"(?P<left>{operand})\s*(?P<left_op><=|<|>=|>)\s*"
            rf"(?P<middle>{operand})\s*(?P<right_op><=|<|>=|>)\s*"
            rf"(?P<right>{operand})",
            lambda match: (
                f"({match.group('left')} {match.group('left_op')} {match.group('middle')} "
                f"AND {match.group('middle')} {match.group('right_op')} {match.group('right')})"
            ),
            expression,
        )

    def _translate_property_reference_match(self, match: re.Match) -> str:
        variable = match.group(1)
        property_name = match.group(2)
        if variable not in self._var_kinds:
            return match.group(0)
        if property_name.lower() == "label" and not self._property_type(variable, property_name):
            return self._label_value_expression(variable)
        if self._is_edge_identity_property(variable, property_name):
            return f"EDGE_ID({self._var_sql_names.get(variable, variable)})"
        redirect_variable = self._property_redirect_target(variable, property_name)
        property_name = self._canonical_property_name(variable, property_name)
        if redirect_variable:
            variable = redirect_variable
        return (
            f"{self._var_sql_names.get(variable, variable)}."
            f"{OracleNameSanitizer.quote(property_name, fallback='PROP')}"
        )

    def _translate_label_predicates(self, expression: str) -> str:
        def replace(match: re.Match) -> str:
            variable = match.group("variable")
            label = match.group("label")
            if variable not in self._var_kinds:
                return match.group(0)
            label_map = (
                self.edge_label_map
                if self._var_kinds.get(variable) == "edge"
                else self.node_label_map
            )
            labels = self._label_map_targets(label, label_map)
            declared_labels = self._possible_graph_labels(variable)
            if declared_labels and not (set(labels) & set(declared_labels)):
                return "(1 = 0)"
            sql_variable = self._var_sql_names.get(variable, variable)
            predicates = [
                f"{sql_variable} IS LABELED {OracleNameSanitizer.quote(item, fallback='LABEL')}"
                for item in labels
            ]
            return "(" + " OR ".join(predicates) + ")"

        return re.sub(
            r"(?<![A-Za-z0-9_.$#])(?P<variable>[A-Za-z_][A-Za-z0-9_]*)\s*:"
            r"\s*`?(?P<label>[A-Za-z_][A-Za-z0-9_$#-]*)`?",
            replace,
            expression,
        )

    def _translate_date_function_property_calls(self, expression: str) -> str:
        def replace(match: re.Match) -> str:
            variable = match.group("variable")
            property_name = self._canonical_property_name(variable, match.group("property"))
            property_ref = (
                f"{self._var_sql_names.get(variable, variable)}."
                f"{OracleNameSanitizer.quote(property_name, fallback='PROP')}"
            )
            if self._is_string_type(self._property_type(variable, property_name)):
                return self._to_date_expression(property_ref)
            return f"CAST({property_ref} AS DATE)"

        return re.sub(
            r"\bdate\s*\(\s*(?P<variable>[A-Za-z_][A-Za-z0-9_]*)\."
            r"(?P<property>[A-Za-z_][A-Za-z0-9_$#-]*)\s*\)",
            replace,
            expression,
            flags=re.IGNORECASE,
        )

    def _to_date_expression(self, expression: str) -> str:
        return f"TO_DATE({expression} DEFAULT NULL ON CONVERSION ERROR, 'YYYY-MM-DD')"

    def _translate_string_predicates(self, expression: str) -> str:
        operand = (
            r'(?:[A-Za-z_][A-Za-z0-9_]*\."[^"]+"|'
            r"[A-Za-z_][A-Za-z0-9_]*|"
            r"TO_DATE\([^)]+\)|"
            r"LOWER\([^)]+\)|"
            r"UPPER\([^)]+\))"
        )
        literal = r"(?:__SQL_LITERAL_\d+__|'[^']*')"
        expression = re.sub(
            rf"(?P<left>{operand})\s+STARTS\s+WITH\s+(?P<right>{literal})",
            lambda match: f"{match.group('left')} LIKE {match.group('right')} || '%'",
            expression,
            flags=re.IGNORECASE,
        )
        expression = re.sub(
            rf"(?P<left>{operand})\s+ENDS\s+WITH\s+(?P<right>{literal})",
            lambda match: f"{match.group('left')} LIKE '%' || {match.group('right')}",
            expression,
            flags=re.IGNORECASE,
        )
        return re.sub(
            rf"(?P<left>{operand})\s+CONTAINS\s+(?P<right>{literal})",
            lambda match: f"INSTR({match.group('left')}, {match.group('right')}) > 0",
            expression,
            flags=re.IGNORECASE,
        )

    def _translate_to_integer(self, expression: str) -> str:
        pattern = re.compile(r"\btoInteger\s*\(", flags=re.IGNORECASE)
        while True:
            match = pattern.search(expression)
            if not match:
                return expression
            body_start = match.end()
            body_end = self._matching_paren_index(expression, body_start - 1)
            if body_end == -1:
                return expression
            body = expression[body_start:body_end]
            replacement = f"CAST({body} AS INTEGER)"
            expression = expression[: match.start()] + replacement + expression[body_end + 1 :]

    def _translate_substring(self, expression: str) -> str:
        def replace(match: re.Match) -> str:
            start = match.group("start")
            if re.fullmatch(r"-?\d+", start):
                start = str(int(start) + 1)
            else:
                start = f"({start}) + 1"
            length = match.group("length")
            return f"SUBSTR({match.group('value')}, {start}, {length})"

        return re.sub(
            r"\bsubstring\s*\(\s*(?P<value>[^,]+)\s*,\s*"
            r"(?P<start>[^,]+)\s*,\s*(?P<length>[^()]+)\)",
            replace,
            expression,
            flags=re.IGNORECASE,
        )

    def _translate_left_function(self, expression: str) -> str:
        def replace(match: re.Match) -> str:
            return f"SUBSTR({match.group('value')}, 1, {match.group('length')})"

        return re.sub(
            r"\bleft\s*\(\s*(?P<value>[^,]+)\s*,\s*(?P<length>[^()]+)\)",
            replace,
            expression,
            flags=re.IGNORECASE,
        )

    def _guard_numeric_division(self, expression: str) -> str:
        return re.sub(
            r"/\s*(TO_NUMBER\([^)]+\))",
            lambda match: f"/ NULLIF({match.group(1)}, 0)",
            expression,
            flags=re.IGNORECASE,
        )

    def _translate_string_concatenation(self, expression: str) -> str:
        operand = r"(?:__SQL_LITERAL_\d+__|TO_CHAR\([^)]+\)|[A-Za-z_][A-Za-z0-9_]*)"
        previous = None
        while previous != expression:
            previous = expression
            expression = re.sub(
                rf"(?P<left>{operand})\s*\+\s*(?P<right>{operand})",
                lambda match: (
                    f"{match.group('left')} || {match.group('right')}"
                    if (
                        match.group("left").startswith("__SQL_LITERAL_")
                        or match.group("right").startswith("__SQL_LITERAL_")
                        or match.group("left").upper().startswith("TO_CHAR(")
                        or match.group("right").upper().startswith("TO_CHAR(")
                    )
                    else match.group(0)
                ),
                expression,
                flags=re.IGNORECASE,
            )
        return expression

    def _matching_paren_index(self, expression: str, open_index: int) -> int:
        depth = 0
        index = open_index
        while index < len(expression):
            char = expression[index]
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    return index
            index += 1
        return -1

    def _translate_date_property_extractors(self, expression: str) -> str:
        def replace(match: re.Match) -> str:
            variable = match.group("variable")
            property_name = match.group("property")
            raw_field = match.group("field")
            field = raw_field.upper()
            property_ref = (
                f"{self._var_sql_names.get(variable, variable)}."
                f"{OracleNameSanitizer.quote(property_name, fallback='PROP')}"
            )
            if self._is_string_type(self._property_type(variable, property_name)):
                property_ref = self._to_date_expression(property_ref)
            if raw_field.lower() == "weekday":
                return f"(TRUNC({property_ref}) - TRUNC({property_ref}, 'IW'))"
            if raw_field.lower() == "dayofweek":
                return f"(TRUNC({property_ref}) - TRUNC({property_ref}, 'IW') + 1)"
            return f"EXTRACT({field} FROM {property_ref})"

        return re.sub(
            r"\bdate\s*\(\s*(?P<variable>[A-Za-z_][A-Za-z0-9_]*)\."
            r"(?P<property>[A-Za-z_][A-Za-z0-9_$#-]*)\s*\)\."
            r"(?P<field>year|month|day|weekday|dayOfWeek)\b",
            replace,
            expression,
            flags=re.IGNORECASE,
        )

    def _translate_property_extractors(self, expression: str) -> str:
        def replace(match: re.Match) -> str:
            variable = match.group("variable")
            property_name = match.group("property")
            field = match.group("field").upper()
            property_ref = (
                f"{self._var_sql_names.get(variable, variable)}."
                f"{OracleNameSanitizer.quote(property_name, fallback='PROP')}"
            )
            if field in {"YEAR", "MONTH", "DAY"}:
                if self._is_string_type(self._property_type(variable, property_name)):
                    property_ref = self._to_date_expression(property_ref)
                return f"EXTRACT({field} FROM {property_ref})"
            return match.group(0)

        return re.sub(
            r"\b(?P<variable>[A-Za-z_][A-Za-z0-9_]*)\."
            r"(?P<property>[A-Za-z_][A-Za-z0-9_$#-]*)\."
            r"(?P<field>year|month|day)\b",
            replace,
            expression,
            flags=re.IGNORECASE,
        )

    def _translate_split_size(self, expression: str, literals: List[str] | None = None) -> str:
        literals = literals or []

        def replace(match: re.Match) -> str:
            body = match.group("body").strip()
            literal_index = int(match.group("literal_index"))
            delimiter = ""
            if literal_index < len(literals):
                delimiter = literals[literal_index].strip("'")
            if delimiter == ",":
                return (
                    f"CASE WHEN {body} IS NULL OR {body} = '' THEN 0 "
                    f"ELSE REGEXP_COUNT({body}, ',') + 1 END"
                )
            return f"REGEXP_COUNT({body}, '\\S+')"

        return re.sub(
            r"\bsize\s*\(\s*split\s*\((?P<body>[^,]+),\s*"
            r"__SQL_LITERAL_(?P<literal_index>\d+)__\s*\)\s*\)",
            replace,
            expression,
            flags=re.IGNORECASE,
        )

    def _translate_modulo(self, expression: str) -> str:
        expression = re.sub(
            r"(?P<left>CAST\([^)]+\s+AS\s+INTEGER\))\s*%\s*"
            r"(?P<right>-?\d+(?:\.\d+)?)",
            lambda match: f"MOD({match.group('left')}, {match.group('right')})",
            expression,
            flags=re.IGNORECASE,
        )
        expression = re.sub(
            r"(?P<left>EXTRACT\(.+\))\s*%\s*(?P<right>-?\d+(?:\.\d+)?)",
            lambda match: f"MOD({match.group('left')}, {match.group('right')})",
            expression,
        )
        return re.sub(
            r"(?P<left>[A-Za-z_][A-Za-z0-9_.$#\"]*)\s*%\s*"
            r"(?P<right>-?\d+(?:\.\d+)?)",
            lambda match: f"MOD({match.group('left')}, {match.group('right')})",
            expression,
        )

    def _coerce_typed_property_comparisons(self, expression: str) -> str:
        def replace_date(match: re.Match) -> str:
            variable = match.group("variable")
            property_name = match.group("property")
            if self._is_string_type(self._property_type(variable, property_name)):
                return (
                    f'{variable}."{property_name}" {match.group("operator")} '
                    f"__SQL_LITERAL_{match.group('literal')}__"
                )
            return match.group(0)

        expression = re.sub(
            r'\b(?P<variable>[A-Za-z_][A-Za-z0-9_]*)\."(?P<property>[^"]+)"\s*'
            r"(?P<operator><=|>=|<>|=|<|>)\s*DATE\s+__SQL_LITERAL_(?P<literal>\d+)__",
            replace_date,
            expression,
            flags=re.IGNORECASE,
        )

        def replace_boolean(match: re.Match) -> str:
            variable = match.group("variable")
            property_name = match.group("property")
            boolean = match.group("boolean").lower()
            if self._is_string_type(self._property_type(variable, property_name)):
                return f"{variable}.\"{property_name}\" {match.group('operator')} '{boolean}'"
            return match.group(0)

        expression = re.sub(
            r'\b(?P<variable>[A-Za-z_][A-Za-z0-9_]*)\."(?P<property>[^"]+)"\s*'
            r"(?P<operator><=|>=|<>|=|<|>)\s*(?P<boolean>true|false)\b",
            replace_boolean,
            expression,
            flags=re.IGNORECASE,
        )

        def replace_number(match: re.Match) -> str:
            variable = match.group("variable")
            property_name = match.group("property")
            if self._is_string_type(self._property_type(variable, property_name)):
                return (
                    f'{variable}."{property_name}" {match.group("operator")} '
                    f"'{match.group('number')}'"
                )
            return match.group(0)

        return re.sub(
            r'\b(?P<variable>[A-Za-z_][A-Za-z0-9_]*)\."(?P<property>[^"]+)"\s*'
            r"(?P<operator><=|>=|<>|=|<|>)\s*(?P<number>-?\d+(?:\.\d+)?)\b",
            replace_number,
            expression,
        )

    def _coerce_date_function_property_comparisons(self, expression: str) -> str:
        date_expr = (
            r"TO_DATE\([A-Za-z_][A-Za-z0-9_]*\.\"[^\"]+\" "
            r"DEFAULT NULL ON CONVERSION ERROR, 'YYYY-MM-DD'\)"
        )
        property_ref = (
            r"(?P<{prefix}_variable>[A-Za-z_][A-Za-z0-9_]*)"
            r"\.\"(?P<{prefix}_property>[^\"]+)\""
        )

        def property_type(match: re.Match, prefix: str) -> str:
            return self._property_type(
                match.group(f"{prefix}_variable"),
                match.group(f"{prefix}_property"),
            )

        def replace_right(match: re.Match) -> str:
            right = match.group("right")
            if self._is_string_type(property_type(match, "right")):
                right = self._to_date_expression(right)
            return f"{match.group('left')} {match.group('operator')} {right}"

        expression = re.sub(
            rf"(?P<left>{date_expr})\s*(?P<operator><=|>=|<>|=|<|>)\s*"
            rf"(?P<right>{property_ref.format(prefix='right')})",
            replace_right,
            expression,
        )

        def replace_left(match: re.Match) -> str:
            left = match.group("left")
            if self._is_string_type(property_type(match, "left")):
                left = self._to_date_expression(left)
            return f"{left} {match.group('operator')} {match.group('right')}"

        return re.sub(
            rf"(?P<left>{property_ref.format(prefix='left')})\s*"
            rf"(?P<operator><=|>=|<>|=|<|>)\s*(?P<right>{date_expr})",
            replace_left,
            expression,
        )

    def _translate_element_comparisons(self, expression: str) -> str:
        def replace(match: re.Match) -> str:
            left = match.group("left")
            right = match.group("right")
            operator = match.group("operator")
            left_source = self._source_variable(left)
            right_source = self._source_variable(right)
            if left_source not in self._var_kinds or right_source not in self._var_kinds:
                return match.group(0)
            if self._var_kinds[left_source] != self._var_kinds[right_source]:
                return match.group(0)
            function_name = (
                "EDGE_EQUAL" if self._var_kinds[left_source] == "edge" else "VERTEX_EQUAL"
            )
            comparison = f"{function_name}({left}, {right})"
            return comparison if operator == "=" else f"NOT {comparison}"

        return re.sub(
            r"\b(?P<left>[A-Za-z_][A-Za-z0-9_]*)\s*(?P<operator>=|<>)\s*"
            r"(?P<right>[A-Za-z_][A-Za-z0-9_]*)\b",
            replace,
            expression,
        )

    def _translate_element_id_comparisons(self, expression: str) -> str:
        def replace(match: re.Match) -> str:
            left = match.group("left")
            right = match.group("right")
            operator = match.group("operator")
            left_source = self._source_variable(left)
            right_source = self._source_variable(right)
            if left_source not in self._var_kinds or right_source not in self._var_kinds:
                return match.group(0)
            if self._var_kinds[left_source] != self._var_kinds[right_source]:
                return match.group(0)
            function_name = (
                "EDGE_EQUAL" if self._var_kinds[left_source] == "edge" else "VERTEX_EQUAL"
            )
            comparison = f"{function_name}({left}, {right})"
            return comparison if operator == "=" else f"NOT {comparison}"

        return re.sub(
            r"\bid\s*\(\s*(?P<left>[A-Za-z_][A-Za-z0-9_]*)\s*\)\s*"
            r"(?P<operator>=|<>)\s*"
            r"id\s*\(\s*(?P<right>[A-Za-z_][A-Za-z0-9_]*)\s*\)",
            replace,
            expression,
            flags=re.IGNORECASE,
        )

    def _translate_id_function_calls(self, expression: str) -> str:
        def replace(match: re.Match) -> str:
            variable = match.group("variable")
            if variable not in self._var_kinds:
                return match.group(0)
            return self._element_id_expression(variable)

        return re.sub(
            r"\bid\s*\(\s*(?P<variable>[A-Za-z_][A-Za-z0-9_]*)\s*\)",
            replace,
            expression,
            flags=re.IGNORECASE,
        )

    def _protect_string_literals(self, expression: str) -> tuple[str, List[str]]:
        literals: List[str] = []
        result: List[str] = []
        i = 0
        while i < len(expression):
            if expression[i] != "'":
                result.append(expression[i])
                i += 1
                continue
            start = i
            i += 1
            while i < len(expression):
                if expression[i] == "\\" and i + 1 < len(expression) and expression[i + 1] == "'":
                    i += 2
                    continue
                if expression[i] == "'" and i + 1 < len(expression) and expression[i + 1] == "'":
                    i += 2
                    continue
                if expression[i] == "'":
                    i += 1
                    break
                i += 1
            placeholder = f"__SQL_LITERAL_{len(literals)}__"
            literals.append(expression[start:i].replace("\\'", "''"))
            result.append(placeholder)
        return "".join(result), literals

    def _restore_string_literals(self, expression: str, literals: List[str]) -> str:
        for index, literal in enumerate(literals):
            expression = expression.replace(f"__SQL_LITERAL_{index}__", literal)
        return expression

    def _default_expression_alias(self, symbolic_name: str, expression: str) -> str:
        if symbolic_name == "*":
            return "COUNT_VALUE"
        if symbolic_name in self._path_variables:
            return symbolic_name
        if self._has_distinct_prefix(symbolic_name):
            symbolic_name = self._strip_distinct_prefix(symbolic_name)
        if symbolic_name in self._var_kinds and expression.strip() in (
            symbolic_name,
            self._element_id_expression(symbolic_name),
        ):
            return f"{symbolic_name}_VALUE"
        compact = re.sub(r"[^A-Za-z0-9_]+", "_", symbolic_name or expression).strip("_")
        return compact or "VALUE"

    def _outer_group_order_and_paging(
        self,
        return_body: ReturnBody,
        aggregate_query: bool = False,
    ) -> str:
        suffix = ""
        if aggregate_query:
            group_aliases = []
            return_aliases = self._resolved_return_aliases(return_body)
            projected_aliases = {OracleNameSanitizer.alias(alias) for alias in return_aliases}
            for item, resolved_alias in zip(
                return_body.return_item_list,
                return_aliases,
                strict=True,
            ):
                if not self._is_aggregate_item(item):
                    group_aliases.append(OracleNameSanitizer.alias(resolved_alias))
            for sort_item in return_body.sort_item_list:
                sort_alias = OracleNameSanitizer.alias(self._sort_alias(sort_item, return_body))
                if (
                    sort_alias in projected_aliases
                    or self._is_aggregate_sort(sort_item)
                    or self._sort_expression_uses_return_aliases(sort_item, return_body)
                ):
                    continue
                group_aliases.append(sort_alias)
            if group_aliases:
                suffix += "\nGROUP BY " + ", ".join(dict.fromkeys(group_aliases))
        if return_body.sort_item_list:
            suffix += "\nORDER BY " + ", ".join(
                self._translate_sort_item(item, return_body) for item in return_body.sort_item_list
            )
        if return_body.skip != -1:
            suffix += f"\nOFFSET {return_body.skip} ROWS"
        if return_body.limit != -1:
            suffix += f"\nFETCH FIRST {return_body.limit} ROWS ONLY"
        return suffix

    def _has_distinct_prefix(self, value: str) -> bool:
        return bool(re.match(r"^\s*DISTINCT\s+", value or "", flags=re.IGNORECASE))

    def _strip_distinct_prefix(self, value: str) -> str:
        return re.sub(
            r"^\s*DISTINCT\s+",
            "",
            value or "",
            count=1,
            flags=re.IGNORECASE,
        )

    def _hidden_sort_aliases(
        self,
        return_body: ReturnBody | None,
        aggregate_query: bool,
    ) -> List[str]:
        if return_body is None or aggregate_query:
            return []
        projected_aliases = set(self._resolved_return_aliases(return_body))
        hidden_aliases = []
        for sort_item in return_body.sort_item_list:
            alias = OracleNameSanitizer.alias(self._sort_alias(sort_item, return_body))
            if alias not in projected_aliases:
                hidden_aliases.append(alias)
        return hidden_aliases

    def _resolved_return_aliases(self, return_body: ReturnBody) -> List[str]:
        raw_aliases = [
            self._return_alias(item, self._return_expression(item))
            for item in return_body.return_item_list
        ]
        alias_counts = Counter(OracleNameSanitizer.alias(alias) for alias in raw_aliases)
        seen: Dict[str, int] = {}
        resolved = []
        for item, raw_alias in zip(return_body.return_item_list, raw_aliases, strict=True):
            alias = OracleNameSanitizer.alias(raw_alias)
            if alias_counts[alias] == 1:
                resolved.append(alias)
                continue
            expression = self._return_expression(item)
            base = OracleNameSanitizer.alias(
                self._default_expression_alias(item.symbolic_name, expression)
            )
            index = seen.get(base, 0)
            seen[base] = index + 1
            resolved.append(base if index == 0 else f"{base}_{index + 1}")
        return resolved

    def _has_aggregate(self, return_body: ReturnBody | None) -> bool:
        if return_body is None:
            return False
        return any(self._is_aggregate_item(item) for item in return_body.return_item_list)

    def _is_aggregate_item(self, item: ReturnItem | SortItem) -> bool:
        return (
            item.function_name.upper() in self.AGGREGATE_FUNCTIONS
            or self._is_complex_aggregate_item(item)
        )

    def _is_complex_aggregate_item(self, item: ReturnItem | SortItem) -> bool:
        return (
            bool(item.expression)
            and self._contains_aggregate_function(item.expression)
            and not self._is_simple_aggregate_expression(item)
        )

    def _is_aggregate_sort(self, item: SortItem) -> bool:
        return self._is_aggregate_item(item)

    def _contains_aggregate_function(self, expression: str) -> bool:
        return bool(
            re.search(
                r"\b(?:COUNT|AVG|SUM|MIN|MAX|COLLECT)\s*\(",
                expression or "",
                flags=re.IGNORECASE,
            )
        )

    def _is_simple_aggregate_expression(self, item: ReturnItem | SortItem) -> bool:
        if item.function_name.upper() not in self.AGGREGATE_FUNCTIONS:
            return False
        expression = (item.expression or "").strip()
        if not re.fullmatch(
            rf"\s*{re.escape(item.function_name)}\s*\(.+\)\s*",
            expression,
            flags=re.IGNORECASE | re.DOTALL,
        ):
            return False
        open_paren = expression.find("(")
        if self._matching_paren_index(expression, open_paren) != len(expression) - 1:
            return False
        argument = expression[open_paren + 1 : -1].strip()
        argument = self._strip_distinct_prefix(argument)
        return bool(
            re.fullmatch(
                r"\*|[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_$#-]*)?",
                argument,
            )
        )

    def _next_node_var(self) -> str:
        while True:
            self._auto_node_index += 1
            variable = f"n{self._auto_node_index}"
            if variable not in self._var_kinds and variable not in self._reserved_variables:
                return variable

    def _next_edge_var(self) -> str:
        while True:
            self._auto_edge_index += 1
            variable = f"e{self._auto_edge_index}"
            if variable not in self._var_kinds and variable not in self._reserved_variables:
                return variable
