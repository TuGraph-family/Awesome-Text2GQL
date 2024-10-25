from antlr4 import *

from cypher.LcypherLexer import LcypherLexer
from cypher.LcypherParser import LcypherParser
from utils.CypherStream import CypherStream
from base.TransVisitor import TransVisitor
from base.Config import Config
from tqdm import tqdm
import sys
import os
import copy


def generate(config: Config):
    input_path = ""
    if config.gen_query == False:
        input_path = config.get_input_query_path()  # translate
        # if file exsits , the content would be cleaned
        with open(config.get_output_path(), "w", encoding="utf-8") as file:
            file.write(config.get_db_id() + "\n")
        generate_question(input_path)
    else:
        input_path = config.get_input_query_template_path()  # generate cypher
        output_path = config.get_output_path()
        if not os.path.exists(output_path):
            with open(output_path, "w") as file:
                pass
        with open(output_path, "r+") as file:
            content = file.read()
            if not content:
                file.write(config.get_db_id() + "\n")
        generate_query(input_path)


def generate_query(input_path):
    with open(input_path, "rb") as file:
        lines = file.readlines()
        for i in tqdm(range(0, len(lines), 2)):
            cypher = lines[i].strip()
            prompt = lines[i + 1].strip()
            # print(f"line {i+1}: {cypher.decode('utf-8')}")
            with open(config.get_output_path(), "a", encoding="utf-8") as file:
                file.write("template" + "\n")
                file.write(cypher.decode("utf-8") + "\n")
                file.write(prompt.decode("utf-8") + "\n")

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
        print("output file:", config.get_output_path())


def generate_question(input_path):
    with open(input_path, "rb") as file:
        lines = file.readlines()
    db_id = lines[0].decode("utf-8").strip()
    config.db_id = db_id
    if db_id == "template":
        print("[ERROR]: the input file format is not right, pls give schema name!")
    index = 1
    cyphers = []
    while len(lines[index:]) > 3 and lines[index].decode("utf-8").strip() == "template":
        if lines[index + 3].decode("utf-8").strip() != "cyphers":
            print(
                "[ERROR]: the input file format is not right as the input of generate_question"
            )
        index = index + 4
        for line in lines[index:]:
            if lines[index].decode("utf-8").strip() == "END":
                index = index + 1
                break
            index = index + 1
            cyphers.append(line.strip())
    if cyphers == []:
        print("[WARNING]: the input file format is not right as there is no cyphers")

    for i in tqdm(range(len(cyphers))):
        # print(f"line {i+1}: {cypher.decode('utf-8')}")
        input_stream = CypherStream(cyphers[i])
        lexer = LcypherLexer(input_stream)
        token_stream = CommonTokenStream(lexer)
        parser = LcypherParser(token_stream)
        tree = parser.oC_Cypher()
        if parser.getNumberOfSyntaxErrors() > 0:
            print(f"line {i+1}: grammar check failed!")
            continue
        visitor = TransVisitor(config)
        visitor.visit(tree)
    print("output file:", config.get_output_path())


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
