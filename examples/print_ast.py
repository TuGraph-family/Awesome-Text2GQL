from antlr4 import CommonTokenStream, InputStream

from app.impl.iso_gql.grammar.GQLLexer import GQLLexer
from app.impl.iso_gql.grammar.GQLParser import GQLParser
from app.impl.tugraph_cypher.grammar.LcypherLexer import LcypherLexer
from app.impl.tugraph_cypher.grammar.LcypherParser import LcypherParser

# print a cypher AST
query_cypher = "MATCH (n)-[*3]->(m) RETURN m"

input_stream_cypher = InputStream(query_cypher)
lexer_cypher = LcypherLexer(input_stream_cypher)
token_stream_cypher = CommonTokenStream(lexer_cypher)
parser_cypher = LcypherParser(token_stream_cypher)
tree_cypher = parser_cypher.oC_Cypher()

print(f"[Cypher AST]:{tree_cypher.toStringTree(recog=parser_cypher)}")

# print a ISO-GQL AST
query_gql = "MATCH (n)-[]->{3,3}(m) RETURN m"

input_stream_gql = InputStream(query_gql)
lexer_gql = GQLLexer(input_stream_gql)
token_stream_gql = CommonTokenStream(lexer_gql)
parser_gql = GQLParser(token_stream_gql)
tree_gql = parser_gql.gqlProgram()

print(f"[ISO-GQL AST]:{tree_gql.toStringTree(recog=parser_gql)}")