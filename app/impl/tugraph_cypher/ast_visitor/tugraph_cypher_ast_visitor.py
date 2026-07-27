import re
import traceback
from typing import List, Tuple

from antlr4 import CommonTokenStream, InputStream

from app.core.ast_visitor.ast_visitor import AstVisitor
from app.core.clauses.clause import Clause
from app.core.clauses.match_clause import EdgePattern, MatchClause, NodePattern, PathPattern
from app.core.clauses.return_clause import ReturnBody, ReturnClause, ReturnItem, SortItem
from app.core.clauses.where_clause import CompareExpression, WhereClause
from app.core.clauses.with_clause import WithClause
from app.impl.tugraph_cypher.grammar.LcypherLexer import LcypherLexer
from app.impl.tugraph_cypher.grammar.LcypherParser import LcypherParser
from app.impl.tugraph_cypher.grammar.LcypherVisitor import LcypherVisitor


class TugraphCypherAstVisitor(LcypherVisitor, AstVisitor):
    def get_query_pattern(self, query: str) -> Tuple[bool, List[Clause]]:
        input_stream = InputStream(query)
        lexer = LcypherLexer(input_stream)
        token_stream = CommonTokenStream(lexer)
        parser = LcypherParser(token_stream)
        tree = parser.oC_Cypher()
        try:
            querry_pattern = self.visit(tree)
            return True, querry_pattern
        except Exception as e:
            print("发生未知错误:", e)
            traceback.print_exc()
            return False, []

    def visitOC_SinglePartQuery(self, ctx: LcypherParser.OC_SinglePartQueryContext):
        clause_list = []
        # add clause list from reading clause
        for context in ctx.oC_ReadingClause():
            clause_list += self.visitOC_ReadingClause(context)
        # add return clause
        clause_list.append(self.visitOC_Return(ctx.oC_Return()))
        # return clause list
        return clause_list

    def visitOC_MultiPartQuery(self, ctx: LcypherParser.OC_MultiPartQueryContext):
        clause_list = []
        for child_ctx in ctx.getChildren():
            # add clause list from reading clause
            if isinstance(child_ctx, LcypherParser.OC_ReadingClauseContext):
                clause_list += self.visitOC_ReadingClause(child_ctx)
            # add with clause
            if isinstance(child_ctx, LcypherParser.OC_WithContext):
                clause_list.append(self.visitOC_With(child_ctx))
            # add clause list from single part query
            if isinstance(child_ctx, LcypherParser.OC_SinglePartQueryContext):
                clause_list += self.visitOC_SinglePartQuery(child_ctx)
        # return clause list
        return clause_list

    def visitOC_Unwind(self, ctx: LcypherParser.OC_UnwindContext):
        return []

    def visitOC_Match(self, ctx: LcypherParser.OC_MatchContext):
        clause_list = []
        # add match clause
        path_pattern_list = self.visitOC_Pattern(ctx.oC_Pattern())
        # only use the first path pattern
        match_clause = MatchClause(path_pattern_list, optional=ctx.OPTIONAL_() is not None)
        # add match clause to clause list
        clause_list.append(match_clause)
        # add where clause to clause list
        if ctx.oC_Where() is not None:
            clause_list.append(self.visitOC_Where(ctx.oC_Where()))
        return clause_list

    def visitOC_Pattern(self, ctx: LcypherParser.OC_PatternContext):
        path_patterns = []
        for pattern_part in ctx.oC_PatternPart():
            path_patterns.extend(self.visitOC_PatternPart(pattern_part))
        return path_patterns

    def visitOC_PatternPart(self, ctx: LcypherParser.OC_PatternPartContext):
        path_patterns = self.visitOC_AnonymousPatternPart(ctx.oC_AnonymousPatternPart())
        if ctx.oC_Variable():
            path_variable = self._symbolic_name(ctx.oC_Variable().oC_SymbolicName())
            for path_pattern in path_patterns:
                path_pattern.path_variable = path_variable
        return path_patterns

    def visitOC_AnonymousPatternPart(
        self, ctx: LcypherParser.OC_AnonymousPatternPartContext
    ):
        return self.visitOC_PatternElement(ctx.oC_PatternElement())

    def visitOC_PatternElement(self, ctx: LcypherParser.OC_PatternElementContext):
        node_pattern_list = []
        edge_pattern_list = []
        node_pattern_list.append(self.visitOC_NodePattern(ctx.oC_NodePattern()))
        for chain_ctx in ctx.oC_PatternElementChain():
            edge_pattern_list.append(
                self.visitOC_RelationshipPattern(chain_ctx.oC_RelationshipPattern())
            )
            node_pattern_list.append(self.visitOC_NodePattern(chain_ctx.oC_NodePattern()))
        return [PathPattern(node_pattern_list, edge_pattern_list)]

    def visitOC_NodePattern(self, ctx: LcypherParser.OC_NodePatternContext):
        symbolic_name = ""
        label = ""
        property_maps = []
        if ctx.oC_Variable():
            symbolic_name = self._symbolic_name(ctx.oC_Variable().oC_SymbolicName())
        if ctx.oC_NodeLabels():
            # only get the first node label for now
            # TODO: support getting node label list
            label = self._symbolic_name(
                ctx.oC_NodeLabels().oC_NodeLabel(0).oC_LabelName().oC_SchemaName().oC_SymbolicName()
            )
        if ctx.oC_Properties():
            property_maps = self.visitOC_Properties(ctx.oC_Properties())
        return NodePattern(symbolic_name, label, property_maps)

    def visitOC_RelationshipPattern(self, ctx: LcypherParser.OC_RelationshipPatternContext):
        symbolic_name = ""
        label = ""
        property_maps = []
        direction = ""
        hop_range = (-1, -1)
        # get symbloic_name, label, and hop_range
        if ctx.oC_RelationshipDetail():
            rel_det_ctx = ctx.oC_RelationshipDetail()
            if rel_det_ctx.oC_Variable():
                symbolic_name = self._symbolic_name(rel_det_ctx.oC_Variable().oC_SymbolicName())
            if rel_det_ctx.oC_RelationshipTypes():
                label = "|".join(
                    self._symbolic_name(
                        rel_type.oC_SchemaName().oC_SymbolicName()
                    )
                    for rel_type in rel_det_ctx.oC_RelationshipTypes().oC_RelTypeName()
                )
            if rel_det_ctx.oC_RangeLiteral():
                range_ctx = rel_det_ctx.oC_RangeLiteral()
                if len(range_ctx.oC_IntegerLiteral()) == 0:
                    # no lower bound and upper bound
                    hop_range = (1, -1)
                elif len(range_ctx.oC_IntegerLiteral()) == 2:
                    # lower bound and upper bound
                    lower_bound = int(range_ctx.oC_IntegerLiteral(0).getText())
                    upper_bound = int(range_ctx.oC_IntegerLiteral(1).getText())
                    hop_range = (lower_bound, upper_bound)
                else:
                    if ".." in range_ctx.getText():
                        # lower bound or upper bound
                        bound_index = 0
                        dot_index = 0
                        for i in range(range_ctx.getChildCount()):
                            child = range_ctx.getChild(i)
                            if child.getText() == "..":
                                dot_index = i
                            if isinstance(child, LcypherParser.OC_IntegerLiteralContext):
                                bound_index = i
                        if bound_index < dot_index:
                            # lower bound
                            lower_bound = int(range_ctx.oC_IntegerLiteral(0).getText())
                            hop_range = (lower_bound, -1)
                        else:
                            # upper bound
                            upper_bound = int(range_ctx.oC_IntegerLiteral(0).getText())
                            hop_range = (1, upper_bound)
                    else:
                        # lower bound and upper bound are same
                        lower_bound = int(range_ctx.oC_IntegerLiteral(0).getText())
                        hop_range = (lower_bound, lower_bound)
            if rel_det_ctx.oC_Properties():
                property_maps = self.visitOC_Properties(rel_det_ctx.oC_Properties())
        # get direction
        if ctx.oC_LeftArrowHead() and ctx.oC_RightArrowHead():
            direction = "bidirection"
        else:
            if ctx.oC_LeftArrowHead():
                direction = "left"
            elif ctx.oC_RightArrowHead():
                direction = "right"
            else:
                direction = "bidirection"
        return EdgePattern(symbolic_name, label, property_maps, direction, hop_range)

    def visitOC_MapLiteral(self, ctx: LcypherParser.OC_MapLiteralContext):
        property_maps = []
        count = len(ctx.oC_PropertyKeyName())
        for i in range(count):
            property_name = self._symbolic_name(
                ctx.oC_PropertyKeyName(i).oC_SchemaName().oC_SymbolicName()
            )
            value = self._expression_text(ctx.oC_Expression(i))
            property_maps.append([property_name, value])
        return property_maps

    def visitOC_Where(self, ctx: LcypherParser.OC_WhereContext):
        return WhereClause(
            CompareExpression(
                symbolic_name="",
                property="",
                comparison_type="raw",
                comparison_value="",
                raw_expression=self._expression_text(ctx.oC_Expression()),
            )
        )

    def visitOC_ComparisonExpression(self, ctx: LcypherParser.OC_ComparisonExpressionContext):
        # print(self.visitOC_AddOrSubtractExpression(ctx.oC_AddOrSubtractExpression()))
        [symbolic_name, property, function_name] = self.visitOC_AddOrSubtractExpression(
            ctx.oC_AddOrSubtractExpression()
        )[:3]
        if len(ctx.oC_PartialComparisonExpression()) != 0:
            [comparison_type, comparison_value] = self.visitOC_PartialComparisonExpression(
                ctx.oC_PartialComparisonExpression(0)
            )
            return [CompareExpression(symbolic_name, property, comparison_type, comparison_value)]
        else:
            return [symbolic_name, property, function_name]

    def visitOC_PartialComparisonExpression(
        self, ctx: LcypherParser.OC_PartialComparisonExpressionContext
    ):
        [compare_value, *_] = self.visitOC_AddOrSubtractExpression(ctx.oC_AddOrSubtractExpression())
        compare_type = ""
        compare_symbol = ctx.getChild(0).getText()
        if compare_symbol == "=":
            compare_type = "equal"
        elif compare_symbol == "<>":
            compare_type = "neq"
        elif compare_symbol == "<":
            compare_type = "less"
        elif compare_symbol == ">":
            compare_type = "greater"
        elif compare_symbol == "<=":
            compare_type = "leq"
        elif compare_symbol == ">=":
            compare_type = "geq"

        return [compare_type, compare_value]

    def visitOC_With(self, ctx: LcypherParser.OC_WithContext):
        return_body = self.visitOC_ReturnBody(ctx.oC_ReturnBody())
        where_expression = None
        if ctx.oC_Where():
            where_expression = CompareExpression(
                symbolic_name="",
                property="",
                comparison_type="raw",
                comparison_value="",
                raw_expression=self._expression_text(ctx.oC_Where().oC_Expression()),
            )
        distinct = ctx.DISTINCT() is not None
        return WithClause(return_body, where_expression, distinct)

    def visitOC_Return(self, ctx: LcypherParser.OC_ReturnContext):
        return_body = self.visitOC_ReturnBody(ctx.oC_ReturnBody())
        distinct = ctx.DISTINCT() is not None
        return_clause = ReturnClause(return_body, distinct)
        return return_clause

    def visitOC_ReturnBody(self, ctx: LcypherParser.OC_ReturnBodyContext):
        return_item_list = []
        sort_item_list = []
        skip = -1
        limit = -1

        return_item_list = self.visitOC_ReturnItems(ctx.oC_ReturnItems())
        if ctx.oC_Order() is not None:
            sort_item_list = self.visitOC_Order(ctx.oC_Order())
        if ctx.oC_Skip():
            skip = int(ctx.oC_Skip().oC_Expression().getText())
        if ctx.oC_Limit():
            limit = int(ctx.oC_Limit().oC_Expression().getText())
        return ReturnBody(return_item_list, sort_item_list, skip, limit)

    def visitOC_ReturnItems(self, ctx: LcypherParser.OC_ReturnItemsContext):
        return_item_list = []
        for item_ctx in ctx.oC_ReturnItem():
            return_item = self.visitOC_ReturnItem(item_ctx)
            return_item_list.append(return_item)
        return return_item_list

    def visitOC_ReturnItem(self, ctx: LcypherParser.OC_ReturnItemContext):
        symbolic_name = ""
        property = ""
        alias = ""
        if ctx.oC_Variable():
            alias = self._symbolic_name(ctx.oC_Variable().oC_SymbolicName())
        expression = self._expression_text(ctx.oC_Expression())
        symbolic_name, property, function_name = self._parse_value_expression(expression)
        return ReturnItem(symbolic_name, property, alias, function_name, expression)

    def visitOC_PropertyOrLabelsExpression(
        self, ctx: LcypherParser.OC_PropertyOrLabelsExpressionContext
    ):
        if ctx.oC_Atom().oC_Variable():
            # return symbolic name and property
            symbolic_name = self._symbolic_name(ctx.oC_Atom().oC_Variable().oC_SymbolicName())
            property = ""
            if len(ctx.oC_PropertyLookup()) != 0:
                property = self._symbolic_name(
                    ctx.oC_PropertyLookup(0).oC_PropertyKeyName().oC_SchemaName().oC_SymbolicName()
                )
            return [symbolic_name, property, ""]
        if ctx.oC_Atom().oC_FunctionInvocation():
            function_name = ctx.oC_Atom().oC_FunctionInvocation().oC_FunctionName().getText()
            [symbolic_name, property, _] = self.visitOC_Expression(
                ctx.oC_Atom().oC_FunctionInvocation().oC_Expression(0)
            )
            # TODO: move this part into translation
            if ctx.oC_Atom().oC_FunctionInvocation().DISTINCT():
                symbolic_name = f"DISTINCT {symbolic_name}"
            return [symbolic_name, property, function_name]
        if ctx.oC_Atom().oC_Literal():
            # return comparison value
            comparison_value = ctx.oC_Atom().oC_Literal().getText()
            return [comparison_value]

    def visitOC_Order(self, ctx: LcypherParser.OC_OrderContext):
        sort_item_list = []
        for item_ctx in ctx.oC_SortItem():
            sort_item = self.visitOC_SortItem(item_ctx)
            sort_item_list.append(sort_item)
        return sort_item_list

    def visitOC_SortItem(self, ctx: LcypherParser.OC_SortItemContext):
        order = ""
        count = ctx.getChildCount()
        if count > 1:
            order = ctx.getChild(count - 1).getText()
        expression = self._expression_text(ctx.oC_Expression())
        symbolic_name, property, function_name = self._parse_value_expression(expression)
        return SortItem(symbolic_name, property, order, function_name, expression)

    def _symbolic_name(self, ctx) -> str:
        text = ctx.getText() if ctx is not None else ""
        if len(text) >= 2 and text[0] == "`" and text[-1] == "`":
            return text[1:-1].replace("``", "`")
        return text

    def _expression_text(self, ctx) -> str:
        text = self._normalize_backtick_identifiers(ctx.getText() if ctx is not None else "")
        return self._normalize_string_literals(text)

    def _normalize_backtick_identifiers(self, text: str) -> str:
        return re.sub(r"`([^`]*)`", lambda match: match.group(1), text)

    def _normalize_string_literals(self, text: str) -> str:
        result = []
        index = 0
        while index < len(text):
            char = text[index]
            if char == "'":
                start = index
                index += 1
                while index < len(text):
                    if text[index] == "\\":
                        index += 2
                        continue
                    if text[index] == "'":
                        index += 1
                        break
                    index += 1
                result.append(text[start:index])
                continue
            if char != '"':
                result.append(char)
                index += 1
                continue

            index += 1
            literal = []
            while index < len(text):
                if text[index] == "\\" and index + 1 < len(text):
                    literal.append(text[index + 1])
                    index += 2
                    continue
                if text[index] == '"':
                    index += 1
                    break
                literal.append(text[index])
                index += 1
            result.append("'" + "".join(literal).replace("'", "''") + "'")
        return "".join(result)

    def _parse_value_expression(self, expression: str) -> tuple[str, str, str]:
        expression = expression.strip()
        function_match = re.fullmatch(
            r"(?P<function>[A-Za-z_][A-Za-z0-9_]*)\((?P<body>.*)\)",
            expression,
            flags=re.DOTALL,
        )
        if function_match:
            body = function_match.group("body").strip()
            if body.upper().startswith("DISTINCT "):
                body = "DISTINCT " + body[9:].strip()
            symbolic_name, property_name, _ = self._parse_value_expression(body)
            return symbolic_name, property_name, function_match.group("function")
        if expression == "*":
            return "*", "", ""
        property_match = re.fullmatch(
            r"(?P<symbolic>[A-Za-z_][A-Za-z0-9_]*)"
            r"(?:\.(?P<property>[A-Za-z_][A-Za-z0-9_$#-]*))?",
            expression,
        )
        if property_match:
            return (
                property_match.group("symbolic"),
                property_match.group("property") or "",
                "",
            )
        return expression, "", ""

    def aggregateResult(self, aggregate, nextResult):
        result = []
        if aggregate is not None:
            result += aggregate
        if nextResult is not None:
            result += nextResult
        return result
