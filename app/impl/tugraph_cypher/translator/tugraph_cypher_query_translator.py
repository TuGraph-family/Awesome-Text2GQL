from functools import singledispatchmethod
from typing import List
from antlr4 import CommonTokenStream, InputStream
from app.core.clauses.clause import Clause
from app.core.translator.query_translator import QueryTranslator
from antlr4.error.ErrorListener import ErrorListener

from app.impl.tugraph_cypher.grammar.LcypherLexer import LcypherLexer
from app.impl.tugraph_cypher.grammar.LcypherParser import LcypherParser


class MyErrorListener(ErrorListener):
    def syntaxError(self, recognizer, offendingSymbol, line, column, msg, e):
        raise Exception(f"ERROR: when parsing line {line} column {column}: {msg}\n")


class TugraphCypherQueryTranslator(QueryTranslator):
    def grammar_check(self, query: str) -> bool:
        error_listener = MyErrorListener()
        try:
            input_stream = InputStream(query)
            lexer = LcypherLexer(input_stream)
            lexer.removeErrorListeners()
            lexer.addErrorListener(error_listener)
            stream = CommonTokenStream(lexer)
            parser = LcypherParser(stream)
            parser.removeErrorListeners()
            parser.addErrorListener(error_listener)
            tree = parser.oC_Cypher()
        except Exception as e:
            return False

        return True

    @singledispatchmethod
    def translate(self, query_pattern: List[Clause]) -> str:
        query = ""
        for clause in query_pattern:
            query += self.translate(clause) + " "
        return query
