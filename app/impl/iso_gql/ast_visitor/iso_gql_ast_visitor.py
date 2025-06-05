from typing import List, Tuple

from antlr4 import CommonTokenStream, InputStream

from app.core.ast_visitor.ast_visitor import AstVisitor
from app.core.clauses.clause import Clause
from app.impl.iso_gql.grammar.GQLLexer import GQLLexer
from app.impl.iso_gql.grammar.GQLParser import GQLParser
from app.impl.iso_gql.grammar.GQLVisitor import GQLVisitor


class IsoGqlAstVisitor(GQLVisitor, AstVisitor):
    def get_query_pattern(self, query: str) -> Tuple[bool, List[Clause]]:
        input_stream = InputStream(query)
        lexer = GQLLexer(input_stream)
        token_stream = CommonTokenStream(lexer)
        parser = GQLParser(token_stream)
        tree = parser.gqlProgram()
        try:
            querry_pattern = self.visit(tree)
            return True, querry_pattern
        except Exception:
            return False, []

    def visitSimpleMatchStatement(self, ctx: GQLParser.SimpleMatchStatementContext):
        clause_list = []
        # get where clause and get path pattern
        path_pattern, where_clause = self.visitGraphPatternBindingTable(
            ctx.graphPatternBindingTable()
        )
        if where_clause is not None:
            clause_list.append(where_clause)
        # add match clause
        clause_list.append("MATCH")
        return clause_list

    def visitGraphPattern(self, ctx: GQLParser.GraphPatternContext):
        path_pattern = None
        where_clause = None

        # add where clause
        if ctx.graphPatternWhereClause() is not None:
            where_clause = self.visitGraphPatternWhereClause(ctx.graphPatternWhereClause())
        return path_pattern, where_clause

    def visitGraphPatternWhereClause(self, ctx: GQLParser.GraphPatternWhereClauseContext):
        return "WHERE"

    def visitReturnStatement(self, ctx: GQLParser.ReturnStatementContext):
        return ["RETURN"]

    def aggregateResult(self, aggregate, nextResult):
        result = []
        if aggregate is not None:
            result += aggregate
        if nextResult is not None:
            result += nextResult
        return result
