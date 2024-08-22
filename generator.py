from antlr4 import *

from cypher.LcypherLexer import LcypherLexer
from cypher.LcypherParser import LcypherParser
from utils.CypherStream import CypherStream
from base.TransVisitor import TransVisitor
from base.Config import Config
import sys

def test(config):
    inputQueryPath=''
    if config.genQuery==False:
        inputQueryPath=config.getInputQueryPath() # 翻译
        with open(config.getOutputPath(), "w", encoding="utf-8") as file:
            file.write(config.getDbId()+'\n')
    else:
        inputQueryPath=config.getInputQueryTemplatePath() #生成query

    with open(inputQueryPath, 'rb') as file:
        for i, line in enumerate(file, start=1):
            line=line.strip()
            print(f"行 {i}: {line.decode('utf-8')}")
            input_stream = CypherStream(line)
            lexer = LcypherLexer(input_stream)
            token_stream = CommonTokenStream(lexer)
            parser = LcypherParser(token_stream)
            tree = parser.oC_Cypher()

            if parser.getNumberOfSyntaxErrors() > 0: # 判错接口
                print(f"行 {i}: grammar check failed!")
                continue
            visitor = TransVisitor(config)
            visitor.visit(tree)


if __name__ == '__main__':
    config_path='/root/work_repo/Awesome-Text2GQL/config.json'
    if len(sys.argv)>1:
        config_path=sys.argv[1]
        config=Config(config_path)
        config.genQuery=sys.argv[2].lower()=='true'
        config.db_id=sys.argv[3]
    else:
        config=Config(config_path)
    test(config)