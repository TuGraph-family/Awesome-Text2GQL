from antlr4.InputStream import InputStream
import codecs

class CypherStream(InputStream):
    def __init__(self, line:str, encoding:str='ascii', errors:str='strict'):
        super().__init__(self.readDataFrom(line, encoding, errors))
        self.line = line

    def readDataFrom(self, line:str, encoding:str, errors:str='strict'):
        return codecs.decode(line, encoding, errors)