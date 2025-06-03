# generate .dot file for visulization.

from antlr4.Token import Token
from antlr4.Utils import escapeWhitespace
from antlr4.tree.Tree import RuleNode, ErrorNode, TerminalNode, Tree, ParseTree
from antlr4 import *
from cypher.LcypherLexer import LcypherLexer
from cypher.LcypherParser import LcypherParser
from utils.CypherStream import CypherStream
from graphviz import Digraph

# need forward declaration
Parser = None


class Cypher2Dot(object):
    def __init__(cls):
        cls.node_cnt = 0
        cls.root_list = []
        cls.dot = Digraph()

    # @classmethod
    def Cypher2Dot(cls, t: Tree, ruleNames: list = None, recog: Parser = None):
        if recog is not None:
            ruleNames = recog.ruleNames
        s = escapeWhitespace(cls.getNodeText(t, ruleNames), False)
        if t.getChildCount() == 0:
            if s != " ":
                cls.dot.node(str(cls.node_cnt), label=s)
            return s

        cls.root_list.append(cls.node_cnt)
        cls.dot.node(str(cls.node_cnt), label=s)
        for i in range(0, t.getChildCount()):
            cls.node_cnt += 1
            cls.dot.edge(str(cls.root_list[-1]), str(cls.node_cnt))
            cls.Cypher2Dot(t.getChild(i), ruleNames)

        cls.root_list.pop()

    # @classmethod
    def getNodeText(cls, t: Tree, ruleNames: list = None, recog: Parser = None):
        if recog is not None:
            ruleNames = recog.ruleNames
        if ruleNames is not None:
            if isinstance(t, RuleNode):
                if t.getAltNumber() != 0:  # should use ATN.INVALID_ALT_NUMBER but won't compile
                    return ruleNames[t.getRuleIndex()] + ":" + str(t.getAltNumber())
                return ruleNames[t.getRuleIndex()]
            elif isinstance(t, ErrorNode):
                return str(t)
            elif isinstance(t, TerminalNode):
                if t.symbol is not None:
                    return t.symbol.text  ## MATCH
        # no recog for rule names
        payload = t.getPayload()
        if isinstance(payload, Token):
            return payload.text
        return str(t.getPayload())

    # Return ordered list of all children of this node
    # @classmethod
    def getChildren(cls, t: Tree):
        return [t.getChild(i) for i in range(0, t.getChildCount())]

    def save_dot_file(cls, file_path="/root/work_repo/antlr_python/output/ast"):
        # cls.dot.render(file_path, format='png', view=True)
        cls.dot.render(file_path, view=True)


def test_from_file(input_path):
    with open(input_path, "rb") as file:
        for i, line in enumerate(file, start=1):
            line = line.strip()
            print(f"line {i}: {line}")
            input_stream = CypherStream(line)
            lexer = LcypherLexer(input_stream)
            tokens = CommonTokenStream(lexer)  # Tokens
            parser = LcypherParser(tokens)
            tree = parser.oC_Cypher()
            if parser.getNumberOfSyntaxErrors() > 0:
                print("syntax errors")
                break
            print(tree.toStringTree(recog=parser))  # AST
            handler = Cypher2Dot()
            handler.Cypher2Dot(tree, recog=parser)
            handler.save_dot_file()


if __name__ == "__main__":
    test_from_file("/root/work_repo/antlr_python/query.txt")
