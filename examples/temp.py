import pandas as pd
from app.impl.iso_gql.translator.iso_gql_query_translator import (
    IsoGqlQueryTranslator as GQLTranslator,
)
from app.impl.tugraph_cypher.ast_visitor.tugraph_cypher_query_visitor import TugraphCypherAstVisitor
from app.impl.tugraph_cypher.translator.tugraph_cypher_query_translator import (
    TugraphCypherQueryTranslator as CypherTranslator,
)

query = "MATCH (a:DOI)-[]->{3,3}(n) WHERE a.name = '10.1016/S0764-4442(00)00217-2' RETURN properties(n) AS props"

query_visitor = TugraphCypherAstVisitor()
gql_translator = GQLTranslator()
cypher_translator = CypherTranslator()

print(cypher_translator.grammar_check(query))
