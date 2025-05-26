import sys
import os.path
import antlr4
from antlr4 import *
from antlr4.error.ErrorListener import ErrorListener
from GQLLexer import GQLLexer
from GQLParser import GQLParser

input_stream = InputStream("MATCH (a:Article{title:'Maslov class and minimality in Calabi-Yau manifolds'})-[]->{1,3}(n) RETURN n")
lexer = GQLLexer(input_stream)
stream = CommonTokenStream(lexer)
parser = GQLParser(stream)
tree = parser.gqlProgram()
print(tree.toStringTree(recog=parser))