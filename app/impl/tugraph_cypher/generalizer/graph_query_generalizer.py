import os
from typing import List

from antlr4 import CommonTokenStream, InputStream

from app.impl.tugraph_cypher.generalizer.base.Config import Config
from app.impl.tugraph_cypher.generalizer.base.TransVisitor import TransVisitor
from app.impl.tugraph_cypher.grammar.LcypherLexer import LcypherLexer
from app.impl.tugraph_cypher.grammar.LcypherParser import LcypherParser
from app.impl.tugraph_cypher.translator.tugraph_cypher_query_translator import (
    TugraphCypherQueryTranslator,
)

CURRENT_PATH = f"{os.path.dirname(__file__)}"


class GraphQueryGeneralizer:
    def __init__(self, db_id, instance_path):
        self.translator = TugraphCypherQueryTranslator()
        self.config = Config(f"{CURRENT_PATH}/base/config.json")
        self.config.gen_query = True
        self.config.db_id = db_id
        self.config.instance_path = instance_path

    def generalize(self, query_template: str) -> List[str]:
        if not self.translator.grammar_check(query_template):
            return []
        input_stream = InputStream(query_template)
        lexer = LcypherLexer(input_stream)
        token_stream = CommonTokenStream(lexer)
        parser = LcypherParser(token_stream)
        tree = parser.oC_Cypher()
        visitor = TransVisitor(self.config)
        query_list = visitor.visit(tree)
        return query_list


if __name__ == "__main__":
    query_generalizer = GraphQueryGeneralizer("movie", f"{CURRENT_PATH}/base/db_instance/movie")
    query_list = query_generalizer.generalize(
        "MATCH (n {name: 'Carrie-Anne Moss'}) RETURN n.born AS born"
    )
    print(query_list)
