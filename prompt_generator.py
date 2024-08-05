import sys
from antlr4 import *

from cypher.LcypherLexer import LcypherLexer
from cypher.LcypherParser import LcypherParser
from utils.CypherStream import CypherStream
from base.TransVisitor import TransVisitor

def test(file_path):
    with open(file_path, 'rb') as file:
        for i, line in enumerate(file, start=1):
            line=line.strip()
            print(f"行 {i}: {line}")
            input_stream = CypherStream(line)
            lexer = LcypherLexer(input_stream)
            token_stream = CommonTokenStream(lexer)
            parser = LcypherParser(token_stream)
            tree = parser.oC_Cypher()
            
            # print(tree.toStringTree(recog=parser)) #AST
            ruleNames = parser.ruleNames
            # listener = TransListener(parser)
            # walker = ParseTreeWalker()
            # walker.walk(listener, tree)
            visitor = TransVisitor()
            visitor.visit(tree)
            visitor.printPrompt()

if __name__ == '__main__':
    test('/root/work_repo/Awesome-Text2GQL/query.txt')