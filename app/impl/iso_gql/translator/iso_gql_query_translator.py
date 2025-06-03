from typing import List, overload
from functools import singledispatchmethod
from antlr4 import CommonTokenStream, InputStream
from multipledispatch import dispatch
from app.core.clauses.clause import Clause
from app.core.clauses.match_clause import EdgePattern, MatchClause, NodePattern, PathPattern
from app.core.clauses.return_clause import ReturnBody, ReturnClause, ReturnItem, SortItem
from app.core.clauses.where_clause import CompareExpression, WhereClause
from app.core.clauses.with_clause import WithClause
from app.core.translator.query_translator import QueryTranslator
from antlr4.error.ErrorListener import ErrorListener

from app.impl.iso_gql.grammar.GQLParser import GQLParser
from app.impl.iso_gql.grammar.GQLLexer import GQLLexer


class MyErrorListener(ErrorListener):
    def syntaxError(self, recognizer, offendingSymbol, line, column, msg, e):
        raise Exception("ERROR: when parsing line %d column %d: %s\n" % (line, column, msg))


class IsoGqlQueryTranslator(QueryTranslator):
    def __init__(self):
        self.reserved_words = [
            # Rereserved words
            "ABS",
            "ACOS",
            "ALL",
            "ALL_DIFFERENT",
            "AND",
            "ANY",
            "ARRAY",
            "AS",
            "ASC",
            "ASCENDING",
            "ASIN",
            "AT",
            "ATAN",
            "AVG",
            "BIG",
            "BIGINT",
            "BINARY",
            "BOOL",
            "BOOLEAN",
            "BOTH",
            "BTRIM",
            "BY",
            "BYTE_LENGTH",
            "BYTES",
            "CALL",
            "CARDINALITY",
            "CASE",
            "CAST",
            "CEIL",
            "CEILING",
            "CHAR",
            "CHAR_LENGTH",
            "CHARACTER_LENGTH",
            "CHARACTERISTICS",
            "CLOSE",
            "COALESCE",
            "COLLECT_LIST",
            "COMMIT",
            "COPY",
            "COS",
            "COSH",
            "COT",
            "COUNT",
            "CREATE",
            "CURRENT_DATE",
            "CURRENT_GRAPH",
            "CURRENT_PROPERTY_GRAPH",
            "CURRENT_SCHEMA",
            "CURRENT_TIME",
            "CURRENT_TIMESTAMP",
            "DATE",
            "DATETIME",
            "DAY",
            "DEC",
            "DECIMAL",
            "DEGREES",
            "DELETE",
            "DESC",
            "DESCENDING",
            "DETACH",
            "DISTINCT",
            "DOUBLE",
            "DROP",
            "DURATION",
            "DURATION_BETWEEN",
            "ELEMENT_ID",
            "ELSE",
            "END",
            "EXCEPT",
            "EXISTS",
            "EXP",
            "FILTER",
            "FINISH",
            "FLOAT",
            "FLOAT16",
            "FLOAT32",
            "FLOAT64",
            "FLOAT128",
            "FLOAT256",
            "FLOOR",
            "FOR",
            "FROM",
            "GROUP",
            "HAVING",
            "HOME_GRAPH",
            "HOME_PROPERTY_GRAPH",
            "HOME_SCHEMA",
            "HOUR",
            "IF",
            "IN",
            "INSERT",
            "INT",
            "INTEGER",
            "INT8",
            "INTEGER8",
            "INT16",
            "INTEGER16",
            "INT32",
            "INTEGER32",
            "INT64",
            "INTEGER64",
            "INT128",
            "INTEGER128",
            "INT256",
            "INTEGER256",
            "INTERSECT",
            "INTERVAL",
            "IS",
            "LEADING",
            "LEFT",
            "LET",
            "LIKE",
            "LIMIT",
            "LIST",
            "LN",
            "LOCAL",
            "LOCAL_DATETIME",
            "LOCAL_TIME",
            "LOCAL_TIMESTAMP",
            "LOG",
            "LOG10",
            "LOWER",
            "LTRIM",
            "MATCH",
            "MAX",
            "MIN",
            "MINUTE",
            "MOD",
            "MONTH",
            "NEXT",
            "NODETACH",
            "NORMALIZE",
            "NOT",
            "NOTHING",
            "NULL",
            "NULLS",
            "NULLIF",
            "OCTET_LENGTH",
            "OF",
            "OFFSET",
            "OPTIONAL",
            "OR",
            "ORDER",
            "OTHERWISE",
            "PARAMETER",
            "PARAMETERS",
            "PATH",
            "PATH_LENGTH",
            "PATHS",
            "PERCENTILE_CONT",
            "PERCENTILE_DISC",
            "POWER",
            "PRECISION",
            "PROPERTY_EXISTS",
            "RADIANS",
            "REAL",
            "RECORD",
            "REMOVE",
            "REPLACE",
            "RESET",
            "RETURN",
            "RIGHT",
            "ROLLBACK",
            "RTRIM",
            "SAME",
            "SCHEMA",
            "SECOND",
            "SELECT",
            "SESSION",
            "SESSION_USER",
            "SET",
            "SIGNED",
            "SIN",
            "SINH",
            "SIZE",
            "SKIP",
            "SMALL",
            "SMALLINT",
            "SQRT",
            "START",
            "STDDEV_POP",
            "STDDEV_SAMP",
            "STRING",
            "SUM",
            "TAN",
            "TANH",
            "THEN",
            "TIME",
            "TIMESTAMP",
            "TRAILING",
            "TRIM",
            "TYPED",
            "UBIGINT",
            "UINT",
            "UINT8",
            "UINT16",
            "UINT32",
            "UINT64",
            "UINT128",
            "UINT256",
            "UNION",
            "UNSIGNED",
            "UPPER",
            "USE",
            "USMALLINT",
            "VALUE",
            "VARBINARY",
            "VARCHAR",
            "VARIABLE",
            "WHEN",
            "WHERE",
            "WITH",
            "XOR",
            "YEAR",
            "YIELD",
            "ZONED",
            "ZONED_DATETIME",
            "ZONED_TIME",
            # Prereserved words
            "ABSTRACT",
            "AGGREGATE",
            "AGGREGATES",
            "ALTER",
            "CATALOG",
            "CLEAR",
            "CLONE",
            "CONSTRAINT",
            "CURRENT_ROLE",
            "CURRENT_USER",
            "DATA",
            "DIRECTORY",
            "DRYRUN",
            "EXACT",
            "EXISTING",
            "FUNCTION",
            "GQLSTATUS",
            "GRANT",
            "INSTANT",
            "INFINITY",
            "NUMBER",
            "NUMERIC",
            "ON",
            "OPEN",
            "PARTITION",
            "PROCEDURE",
            "PRODUCT",
            "PROJECT",
            "QUERY",
            "RECORDS",
            "REFERENCE",
            "RENAME",
            "REVOKE",
            "SUBSTRING",
            "SYSTEM_USER",
            "TEMPORAL",
            "UNIQUE",
            "UNIT",
            "VALUES",
        ]

    def is_reserved(self, word: str) -> bool:
        if word.upper() in self.reserved_words:
            return True
        else:
            return False

    def grammar_check(self, query: str) -> bool:
        error_listener = MyErrorListener()
        try:
            input_stream = InputStream(query)
            lexer = GQLLexer(input_stream)
            lexer.removeErrorListeners()
            lexer.addErrorListener(error_listener)
            stream = CommonTokenStream(lexer)
            parser = GQLParser(stream)
            parser.removeErrorListeners()
            parser.addErrorListener(error_listener)
            tree = parser.gqlProgram()
        except Exception as e:
            return False

        return True

    @singledispatchmethod
    def translate(self, query_pattern: List[Clause]) -> str:
        query = ""
        for clause in query_pattern:
            query += self.translate(clause) + " "
        return query.strip()

    @translate.register
    def _(self, match_clause: MatchClause) -> str:
        match_str = "MATCH "
        match_str += self.translate(match_clause.path_pattern)

        return match_str

    @translate.register
    def _(self, path_pattern: PathPattern) -> str:
        path_pattern_str = ""
        path_degree = len(path_pattern.edge_pattern_list)
        path_pattern_str += self.translate(path_pattern.node_pattern_list[0])
        for i in range(path_degree):
            path_pattern_str += self.translate(path_pattern.edge_pattern_list[i])
            path_pattern_str += self.translate(path_pattern.node_pattern_list[i + 1])

        return path_pattern_str

    @translate.register
    def _(self, node_pattern: NodePattern) -> str:
        node_pattern_str = ""
        # check reserved word
        if self.is_reserved(node_pattern.label):
            node_pattern.label = f"`{node_pattern.label}`"
        # construct node string
        if node_pattern.symbolic_name:
            # add node symbolic
            node_pattern_str += f"{node_pattern.symbolic_name}"
        if node_pattern.label:
            # add node label
            node_pattern_str += f":{node_pattern.label}"
        if len(node_pattern.property_maps) != 0:
            # add property maps
            property_maps_str = ""
            for map in node_pattern.property_maps:
                # check reserved word
                if self.is_reserved(map[0]):
                    map[0] = f"`{map[0]}`"
                property_maps_str += f"{map[0]}:{map[1]},"
            property_maps_str = f"{{{property_maps_str.strip(',')}}}"
            node_pattern_str += f"{property_maps_str}"
        node_pattern_str = f"({node_pattern_str})"

        return node_pattern_str

    @translate.register
    def _(self, edge_pattern: EdgePattern) -> str:
        edge_pattern_str = ""
        # check reserved word
        if self.is_reserved(edge_pattern.label):
            edge_pattern.label = f"`{edge_pattern.label}`"
        # construct edge string
        if edge_pattern.symbolic_name:
            # add edge symbolic
            edge_pattern_str += f"{edge_pattern.symbolic_name}"
        if edge_pattern.label:
            # add edge label
            edge_pattern_str += f":{edge_pattern.label}"
        if len(edge_pattern.property_maps) != 0:
            # add property maps
            property_maps_str = ""
            for map in edge_pattern.property_maps:
                # check reserved word
                if self.is_reserved(map[0]):
                    map[0] = f"`{map[0]}`"
                property_maps_str += f"{map[0]}:{map[1]},"
            property_maps_str = f"{{{property_maps_str.strip(',')}}}"
            edge_pattern_str += f"{property_maps_str}"
        # add direction
        edge_pattern_str = "-[" + edge_pattern_str + "]-"
        if edge_pattern.direction == "right":
            edge_pattern_str += ">"
        elif edge_pattern.direction == "left":
            edge_pattern_str = "<" + edge_pattern_str
        # add hop range
        hop_range = edge_pattern.hop_range
        if hop_range != (-1, -1):
            if hop_range[0] == -1:
                edge_pattern_str += f"{{1,{hop_range[1]}}}"
            elif hop_range[1] == -1:
                edge_pattern_str += f"{{{hop_range[0]},}}"
            else:
                edge_pattern_str += f"{{{hop_range[0]},{hop_range[1]}}}"

        return edge_pattern_str

    @translate.register
    def _(self, with_clause: WithClause) -> str:
        with_str = "RETURN "
        if with_clause.distinct:
            with_str += "DISTINCT "
        with_str += f"{self.translate(with_clause.return_body)}"
        with_str += " NEXT"

        return with_str

    @translate.register
    def _(self, return_body: ReturnBody) -> str:
        return_body_str = ""
        # add return items
        for return_item in return_body.return_item_list:
            return_item_str = self.translate(return_item)
            return_body_str += f"{return_item_str}, "
        return_body_str = return_body_str.strip(", ")
        # add sort items
        if len(return_body.sort_item_list) != 0:
            return_body_str += " ORDER BY "
            for sort_item in return_body.sort_item_list:
                sort_item_str = self.translate(sort_item)
                return_body_str += f"{sort_item_str}, "
            return_body_str = return_body_str.strip(", ")
        # add skip
        if return_body.skip != -1:
            return_body_str += f" SKIP {return_body.skip}"
        # add limit
        if return_body.limit != -1:
            return_body_str += f" LIMIT {return_body.limit}"

        return return_body_str

    @translate.register
    def _(self, return_item: ReturnItem) -> str:
        return_item_str = ""
        # check reserved word
        if self.is_reserved(return_item.alias):
            return_item.alias = f"`{return_item.alias}`"
        if self.is_reserved(return_item.property):
            return_item.property = f"`{return_item.property}`"
        if self.is_reserved(return_item.symbolic_name):
            return_item.symbolic_name = f"`{return_item.symbolic_name}`"
        # construct string
        return_item_str += f"{return_item.symbolic_name}"
        if return_item.property:
            return_item_str += f".{return_item.property}"
        if return_item.function_name:
            return_item_str = f"{return_item.function_name}({return_item_str})"
        if return_item.alias:
            return_item_str += f" AS {return_item.alias}"

        return return_item_str

    @translate.register
    def _(self, sort_item: SortItem) -> str:
        sort_item_str = ""
        # check reserved word
        if self.is_reserved(sort_item.symbolic_name):
            sort_item.symbolic_name = f"`{sort_item.symbolic_name}`"
        if self.is_reserved(sort_item.property):
            sort_item.property = f"`{sort_item.property}`"
        sort_item_str += f"{sort_item.symbolic_name}"
        if sort_item.property:
            sort_item_str += f".{sort_item.property}"
        if sort_item.function_name:
            sort_item_str = f"{sort_item.function_name}({sort_item_str})"
        if sort_item.order:
            sort_item_str += f" {sort_item.order}"

        return sort_item_str

    @translate.register
    def _(self, return_clause: ReturnClause) -> str:
        return_str = "RETURN "
        if return_clause.distinct:
            return_str += "DISTINCT "
        return_str += f"{self.translate(return_clause.return_body)}"

        return return_str

    @translate.register
    def _(self, where_clause: WhereClause) -> str:
        where_str = "WHERE "
        where_str += f"{self.translate(where_clause.compare_expression)}"

        return where_str

    @translate.register
    def _(self, compare_expression: CompareExpression) -> str:
        compare_expression_str = ""
        # check reserved word
        if self.is_reserved(compare_expression.property):
            compare_expression.property = f"`{compare_expression.property}`"
        compare_expression_str += f"{compare_expression.symbolic_name}"
        if compare_expression.property:
            compare_expression_str += f".{compare_expression.property}"
        if compare_expression.comparison_type == "equal":
            compare_expression_str += f" = "
        elif compare_expression.comparison_type == "neq":
            compare_expression_str += f" <> "
        elif compare_expression.comparison_type == "less":
            compare_expression_str += f" < "
        elif compare_expression.comparison_type == "greater":
            compare_expression_str += f" > "
        elif compare_expression.comparison_type == "leq":
            compare_expression_str += f" <= "
        elif compare_expression.comparison_type == "geq":
            compare_expression_str += f" >= "
        compare_expression_str += f"{compare_expression.comparison_value}"

        return compare_expression_str
