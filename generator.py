from antlr4 import *

from cypher.LcypherLexer import LcypherLexer
from cypher.LcypherParser import LcypherParser
from utils.CypherStream import CypherStream
from base.TransVisitor import TransVisitor
from base.Config import Config
import sys
import os


def generate(config):
    input_path = ""
    if config.gen_query == False:
        input_path = config.get_input_query_path()  # translate
        # if file exsits , the content would be cleaned
        with open(config.get_output_path(), "w", encoding="utf-8") as file:
            file.write(config.get_db_id() + "\n")
    else:
        input_path = config.get_input_query_template_path()  # generate cypher
        output_path=config.get_output_path()
        if not os.path.exists(output_path):
            with open(output_path, 'w') as file:
                pass
        with open(output_path, 'r+') as file:
            content = file.read()
            if not content:
                file.write(config.get_db_id() + "\n")

    with open(input_path, "rb") as file:
        lines = file.readlines()
        for i in range(0, len(lines), 2):
            cypher = lines[i].strip()
            prompt = lines[i + 1].strip()
            print(f"line {i+1}: {cypher.decode('utf-8')}")
            with open(config.get_output_path(), "a", encoding="utf-8") as file:
                file.write('template' + "\n")
                file.write(cypher.decode('utf-8')+'\n')
                file.write(prompt.decode('utf-8')+'\n')
            
            input_stream = CypherStream(cypher)
            lexer = LcypherLexer(input_stream)
            token_stream = CommonTokenStream(lexer)
            parser = LcypherParser(token_stream)
            tree = parser.oC_Cypher()
            if parser.getNumberOfSyntaxErrors() > 0:
                print(f"line {i+1}: grammar check failed!")
                continue
            visitor = TransVisitor(config)
            visitor.visit(tree)


if __name__ == "__main__":
    config_path = "config.json"
    if len(sys.argv) > 1:
        config_path = sys.argv[1]
        config = Config(config_path)
        config.gen_query = sys.argv[2].lower() == "true"
        config.db_id = sys.argv[3]
    else:
        config = Config(config_path)
    generate(config)
