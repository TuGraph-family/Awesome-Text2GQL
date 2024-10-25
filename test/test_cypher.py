from antlr4 import *
from cypher.LcypherLexer import LcypherLexer
from cypher.LcypherParser import LcypherParser

from utils.CypherStream import CypherStream
import liblgraph_client_python

#
# @description     test cypher line-by-line
# @created         Berry
# @date            2024.07.12
#


def test(file_path):
    with open(file_path, "rb") as file:
        for i, line in enumerate(file, start=1):
            line = line.strip()
            line_str = line.decode("utf-8")
            print(f"line {i}: {line}")
            input_stream = CypherStream(line)
            lexer = LcypherLexer(input_stream)
            tokens = CommonTokenStream(lexer)  # Tokens
            parser = LcypherParser(tokens)
            tree = parser.oC_Cypher()
            if parser.getNumberOfSyntaxErrors() > 0:
                print(f"line {i}: grammar check failed!")
                break
            # print(tree.toStringTree(recog=parser)) #AST

            client = liblgraph_client_python.client(
                "127.0.0.1:9091", "admin", "73@TuGraph"
            )
            ret, res = client.callCypher(line_str, "default")
            if ret == False:
                print(f"line {i}: tugraph execuation check failed!")
                break
            print(f"line {i}: check passed!")


if __name__ == "__main__":
    test("/root/work_repo/Awesome-Text2GQL/query.txt")
