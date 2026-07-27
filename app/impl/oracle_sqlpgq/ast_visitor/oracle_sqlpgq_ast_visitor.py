import re
from typing import List, Tuple

from app.core.ast_visitor.ast_visitor import AstVisitor
from app.core.clauses.clause import Clause
from app.core.clauses.match_clause import EdgePattern, MatchClause, NodePattern, PathPattern
from app.core.clauses.return_clause import ReturnBody, ReturnClause, ReturnItem, SortItem
from app.core.clauses.where_clause import CompareExpression, WhereClause
from app.impl.oracle_sqlpgq.utils.sqlpgq import validate_graph_table_query


class OracleSqlPgqAstVisitor(AstVisitor):
    """Parse the Oracle SQL/PGQ subset emitted by OracleSqlPgqQueryTranslator."""

    NODE_RE = re.compile(r"\((?P<body>[^()]*)\)", re.DOTALL)
    EDGE_RE = re.compile(
        r"(?P<left><)?-\[(?P<body>[^\]]*)\]-(?P<right>>)?(?P<hop>\{[^}]+\})?",
        re.DOTALL,
    )
    COMPARE_RE = re.compile(
        r"(?P<var>[A-Za-z_][A-Za-z0-9_]*)"
        r"(?:\.(?:\"(?P<quoted_prop>[^\"]+)\"|(?P<prop>[A-Za-z_][A-Za-z0-9_]*)))?"
        r"\s*(?P<op>=|<>|<=|>=|<|>)\s*(?P<value>.+)",
        re.DOTALL,
    )

    def get_query_pattern(self, query: str) -> Tuple[bool, List[Clause]]:
        if not validate_graph_table_query(query):
            return False, []
        try:
            body, graph_table_end = self._extract_graph_table_span(query)
            match_text, where_text, columns_text = self._extract_sections(body)
            clauses: List[Clause] = []
            for path_text in self._split_top_level(match_text):
                clauses.append(MatchClause(self._parse_path(path_text)))
            if where_text:
                clauses.append(WhereClause(self._parse_where(where_text)))
            return_items = self._parse_columns(columns_text)
            if return_items:
                sort_items, skip, limit = self._parse_outer_modifiers(query[graph_table_end:])
                clauses.append(ReturnClause(ReturnBody(return_items, sort_items, skip, limit)))
            return True, clauses
        except Exception:
            return False, []

    def _extract_graph_table_body(self, query: str) -> str:
        return self._extract_graph_table_span(query)[0]

    def _extract_graph_table_span(self, query: str) -> Tuple[str, int]:
        marker = re.search(r"GRAPH_TABLE\s*\(", query, re.IGNORECASE)
        if marker is None:
            raise ValueError("GRAPH_TABLE not found.")
        start = marker.end() - 1
        depth = 0
        in_single = False
        in_double = False
        for index in range(start, len(query)):
            char = query[index]
            if char == "'" and not in_double:
                in_single = not in_single
            elif char == '"' and not in_single:
                in_double = not in_double
            elif not in_single and not in_double:
                if char == "(":
                    depth += 1
                elif char == ")":
                    depth -= 1
                    if depth == 0:
                        return query[start + 1 : index].strip(), index + 1
        raise ValueError("GRAPH_TABLE body is not balanced.")

    def _extract_sections(self, body: str) -> Tuple[str, str, str]:
        upper = body.upper()
        match_idx = upper.index("MATCH ")
        columns_idx = upper.rindex("COLUMNS")
        before_columns = body[match_idx + len("MATCH ") : columns_idx].strip()
        where_idx = self._find_keyword(before_columns, "WHERE")
        if where_idx == -1:
            match_text = before_columns
            where_text = ""
        else:
            match_text = before_columns[:where_idx].strip()
            where_text = before_columns[where_idx + len("WHERE") :].strip()
        columns_start = body.index("(", columns_idx)
        columns_text = body[columns_start + 1 : body.rindex(")")].strip()
        return match_text, where_text, columns_text

    def _find_keyword(self, text: str, keyword: str) -> int:
        pattern = re.compile(rf"\b{keyword}\b", re.IGNORECASE)
        for match in pattern.finditer(text):
            prefix = text[: match.start()]
            if prefix.count("(") == prefix.count(")") and prefix.count("[") == prefix.count("]"):
                return match.start()
        return -1

    def _parse_path(self, text: str) -> PathPattern:
        text = text.strip()
        position = 0
        node_patterns: List[NodePattern] = []
        edge_patterns: List[EdgePattern] = []

        first_node = self.NODE_RE.match(text, position)
        if first_node is None:
            raise ValueError("Path must start with a node pattern.")
        node_patterns.append(self._parse_node(first_node.group("body")))
        position = first_node.end()

        while position < len(text):
            edge_match = self.EDGE_RE.match(text, position)
            if edge_match is None:
                break
            edge_patterns.append(self._parse_edge(edge_match))
            position = edge_match.end()
            node_match = self.NODE_RE.match(text, position)
            if node_match is None:
                raise ValueError("Edge pattern must be followed by a node pattern.")
            node_patterns.append(self._parse_node(node_match.group("body")))
            position = node_match.end()

        return PathPattern(node_patterns, edge_patterns)

    def _parse_node(self, body: str) -> NodePattern:
        variable, label = self._parse_variable_and_label(body)
        return NodePattern(variable, label, [])

    def _parse_edge(self, edge_match: re.Match) -> EdgePattern:
        variable, label = self._parse_variable_and_label(edge_match.group("body"))
        if edge_match.group("left"):
            direction = "left"
        elif edge_match.group("right"):
            direction = "right"
        else:
            direction = "bidirection"
        return EdgePattern(variable, label, [], direction, self._parse_hop(edge_match.group("hop")))

    def _parse_variable_and_label(self, body: str) -> Tuple[str, str]:
        body = body.strip()
        if " WHERE " in body.upper():
            body = re.split(r"\bWHERE\b", body, flags=re.IGNORECASE)[0].strip()
        label_pattern = (
            r"(?P<var>[A-Za-z_][A-Za-z0-9_]*)"
            r"(?:\s+IS\s+(?:\"(?P<qlabel>[^\"]+)\"|"
            r"(?P<label>[A-Za-z_][A-Za-z0-9_]*)))?"
        )
        label_match = re.match(
            label_pattern,
            body,
            re.IGNORECASE,
        )
        if label_match is None:
            return "", ""
        label = label_match.group("qlabel") or label_match.group("label") or ""
        return label_match.group("var"), label

    def _parse_hop(self, text: str | None) -> Tuple[int, int]:
        if not text:
            return (-1, -1)
        values = text.strip("{}").split(",")
        if len(values) == 1:
            value = int(values[0])
            return (value, value)
        lower = int(values[0]) if values[0] else -1
        upper = int(values[1]) if values[1] else -1
        return (lower, upper)

    def _parse_where(self, text: str) -> List[CompareExpression]:
        expressions = []
        for part in re.split(r"\s+AND\s+", text, flags=re.IGNORECASE):
            match = self.COMPARE_RE.match(part.strip())
            if match is None:
                continue
            expressions.append(
                CompareExpression(
                    symbolic_name=match.group("var"),
                    property=match.group("quoted_prop") or match.group("prop") or "",
                    comparison_type={
                        "=": "equal",
                        "<>": "neq",
                        "<": "less",
                        ">": "greater",
                        "<=": "leq",
                        ">=": "geq",
                    }[match.group("op")],
                    comparison_value=match.group("value").strip(),
                )
            )
        return expressions

    def _parse_columns(self, text: str) -> List[ReturnItem]:
        items = []
        for item in self._split_top_level(text):
            match = re.match(r"(?P<expr>.+?)\s+AS\s+(?P<alias>[A-Za-z_][A-Za-z0-9_]*)$", item)
            if match is None:
                continue
            expr = match.group("expr").strip()
            alias = match.group("alias")
            function_name = ""
            function_match = re.match(r"(?P<func>[A-Za-z_][A-Za-z0-9_]*)\((?P<inner>.+)\)", expr)
            if function_match:
                function_name = function_match.group("func")
                expr = function_match.group("inner").strip()
            prop_pattern = (
                r"(?P<var>[A-Za-z_][A-Za-z0-9_]*)"
                r"(?:\.(?:\"(?P<qprop>[^\"]+)\"|"
                r"(?P<prop>[A-Za-z_][A-Za-z0-9_]*)))?"
            )
            prop_match = re.match(
                prop_pattern,
                expr,
            )
            if prop_match:
                items.append(
                    ReturnItem(
                        symbolic_name=prop_match.group("var"),
                        property=prop_match.group("qprop") or prop_match.group("prop") or "",
                        alias=alias,
                        function_name=function_name,
                    )
                )
        return items

    def _parse_outer_modifiers(self, text: str) -> Tuple[List[SortItem], int, int]:
        sort_items: List[SortItem] = []
        skip = -1
        limit = -1

        order_match = re.search(
            r"\bORDER\s+BY\s+(?P<body>.*?)(?=\bOFFSET\b|\bFETCH\b|$)",
            text,
            re.IGNORECASE | re.DOTALL,
        )
        if order_match:
            for item in self._split_top_level(order_match.group("body").strip()):
                sort_match = re.match(
                    r"(?P<alias>[A-Za-z_][A-Za-z0-9_]*)(?:\s+(?P<order>ASC|DESC))?$",
                    item.strip(),
                    re.IGNORECASE,
                )
                if sort_match:
                    sort_items.append(
                        SortItem(
                            symbolic_name=sort_match.group("alias"),
                            property="",
                            order=(sort_match.group("order") or "").upper(),
                        )
                    )

        offset_match = re.search(r"\bOFFSET\s+(?P<value>\d+)\s+ROWS\b", text, re.IGNORECASE)
        if offset_match:
            skip = int(offset_match.group("value"))

        fetch_match = re.search(
            r"\bFETCH\s+FIRST\s+(?P<value>\d+)\s+ROWS\s+ONLY\b",
            text,
            re.IGNORECASE,
        )
        if fetch_match:
            limit = int(fetch_match.group("value"))

        return sort_items, skip, limit

    def _split_top_level(self, text: str) -> List[str]:
        parts = []
        current = []
        paren_depth = 0
        bracket_depth = 0
        in_single = False
        in_double = False
        for char in text:
            if char == "'" and not in_double:
                in_single = not in_single
            elif char == '"' and not in_single:
                in_double = not in_double
            elif not in_single and not in_double:
                if char == "(":
                    paren_depth += 1
                elif char == ")":
                    paren_depth -= 1
                elif char == "[":
                    bracket_depth += 1
                elif char == "]":
                    bracket_depth -= 1
                elif char == "," and paren_depth == 0 and bracket_depth == 0:
                    part = "".join(current).strip()
                    if part:
                        parts.append(part)
                    current = []
                    continue
            current.append(char)
        tail = "".join(current).strip()
        if tail:
            parts.append(tail)
        return parts
