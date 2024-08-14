from antlr4 import *

from cypher.LcypherLexer import LcypherLexer
from cypher.LcypherParser import LcypherParser
from utils.CypherStream import CypherStream
from base.TransVisitor import TransVisitor
from base.Config import Config

def test(config):
    with open(config.getInputQueryPath(), 'rb') as file:
        for i, line in enumerate(file, start=1):
            line=line.strip()
            print(f"行 {i}: {line.decode('utf-8')}")
            input_stream = CypherStream(line)
            lexer = LcypherLexer(input_stream)
            token_stream = CommonTokenStream(lexer)
            parser = LcypherParser(token_stream)
            tree = parser.oC_Cypher()
            visitor = TransVisitor(config)
            visitor.visit(tree)

if __name__ == '__main__':
    config_path='/root/work_repo/Awesome-Text2GQL/config.json'
    config=Config(config_path)
    test(config)