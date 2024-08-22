from antlr4 import *

from cypher.LcypherLexer import LcypherLexer
from cypher.LcypherParser import LcypherParser
from utils.CypherStream import CypherStream
from base.TransVisitor import TransVisitor
from base.Config import Config
import sys


def test(config):
    input_path = ""
    if config.gen_query == False:
        input_path = config.get_input_query_path()  # 翻译
        with open(config.get_output_path(), "w", encoding="utf-8") as file:
            file.write(config.get_db_id() + "\n")
    else:
        input_path = config.get_input_query_template_path()  # 生成cypher

    with open(input_path, "rb") as file:
        for i, line in enumerate(file, start=1):
            line = line.strip()
            print(f"行 {i}: {line.decode('utf-8')}")
            input_stream = CypherStream(line)
            lexer = LcypherLexer(input_stream)
            token_stream = CommonTokenStream(lexer)
            parser = LcypherParser(token_stream)
            tree = parser.oC_Cypher()

            if parser.getNumberOfSyntaxErrors() > 0:  # 判错接口
                print(f"行 {i}: grammar check failed!")
                continue
            visitor = TransVisitor(config)
            visitor.visit(tree)


if __name__ == "__main__":
    config_path = "/root/work_repo/Awesome-Text2GQL/config.json"
    if len(sys.argv) > 1:
        config_path = sys.argv[1]
        config = Config(config_path)
        config.gen_query = sys.argv[2].lower() == "true"
        config.db_id = sys.argv[3]
    else:
        config = Config(config_path)
    test(config)
