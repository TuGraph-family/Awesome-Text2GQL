from antlr4 import InputStream, CommonTokenStream
from app.impl.tugraph_cypher.grammar.LcypherLexer import LcypherLexer
from app.impl.tugraph_cypher.grammar.LcypherParser import LcypherParser

#
# @description     test cypher line-by-line
# @created         Berry
# @date            2024.07.12
#


def grammar_check(file_path):
    with open(file_path, "rb") as file:
        next(file)
        line = []
        for idx, line in enumerate(file, start=2):
            line_str = line.decode("utf-8").rstrip("\n")
            if int(idx % 2) == 0:
                if not grammar_check_line(line_str, idx, file_path):
                    return False
    return True


def grammar_check_line(line_str, idx, file_path):
    input_stream = InputStream(line_str)
    lexer = LcypherLexer(input_stream)
    tokens = CommonTokenStream(lexer)  # Tokens
    parser = LcypherParser(tokens)
    if parser.getNumberOfSyntaxErrors() > 0:
        print(f"[ERROR]: grammar check failed in file: {file_path} line {idx}")
        print(f"line {idx}: {line_str}")
        return False
    return True


if __name__ == "__main__":
    grammar_check("/root/work_repo/Awesome-Text2GQL/output/generate/movie.txt")
