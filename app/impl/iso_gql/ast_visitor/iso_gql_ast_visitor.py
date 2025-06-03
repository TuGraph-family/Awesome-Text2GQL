from typing import List

from antlr4 import CommonTokenStream, InputStream

from app.core.ast_visitor.ast_visitor import AstVisitor
from app.impl.iso_gql.grammar.GQLLexer import GQLLexer
from app.impl.iso_gql.grammar.GQLParser import GQLParser
from app.impl.iso_gql.grammar.GQLVisitor import GQLVisitor


class IsoGqlAstVisitor(GQLVisitor, AstVisitor):
    def get_query_pattern(self, query: str) -> List:
        input_stream = InputStream(query)
        lexer = GQLLexer(input_stream)
        token_stream = CommonTokenStream(lexer)
        parser = GQLParser(token_stream)
        tree = parser.gqlProgram()
        print(tree.toStringTree(recog=parser))
        querry_pattern = self.visit(tree)
        return querry_pattern

    def visitSimpleMatchStatement(self, ctx: GQLParser.SimpleMatchStatementContext):
        clause_list = []
        # get where clause and get path pattern
        path_pattern, where_clause = self.visitGraphPatternBindingTable(
            ctx.graphPatternBindingTable()
        )
        if where_clause != None:
            clause_list.append(where_clause)
        # add match clause
        clause_list.append("MATCH")
        return clause_list

    def visitGraphPattern(self, ctx: GQLParser.GraphPatternContext):
        path_pattern = None
        where_clause = None

        # add where clause
        if ctx.graphPatternWhereClause() != None:
            where_clause = self.visitGraphPatternWhereClause(ctx.graphPatternWhereClause())
        return path_pattern, where_clause

    def visitGraphPatternWhereClause(self, ctx: GQLParser.GraphPatternWhereClauseContext):
        return "WHERE"

    def visitReturnStatement(self, ctx: GQLParser.ReturnStatementContext):
        return ["RETURN"]

    def aggregateResult(self, aggregate, nextResult):
        result = []
        if aggregate != None:
            result += aggregate
        if nextResult != None:
            result += nextResult
        return result


if __name__ == "__main__":
    query_visitor = IsoGqlAstVisitor()
    # query = "MATCH (s:Supplier)-[:SUPPLIES]->(p:Product) WITH s, avg(p.unitPrice) AS avgUnitPrice ORDER BY avgUnitPrice DESC LIMIT 5 RETURN s.companyName AS Supplier, avgUnitPrice AS AverageUnitPrice"
    query = "MATCH (n:Topic) WHERE n.label = 'P' RETURN DISTINCT n.label AS label, n.description AS description"
    query_pattern = query_visitor.get_query_pattern(query)
    print(query_pattern)
