from base.Parse import Node,ReturnBody,PatternChain,EdgeInstance

class GenQuery():
    def __init__(self,patternChain:PatternChain,returnBody:ReturnBody):
        self.patternChain=patternChain
        self.returnBody=returnBody
        self.queryList=[]
    
    def GenQueryByExactAST(self):
        # 一对一生成
        # 查询所有符合条件的schema并生成
        pass
    
    def GenQuery(self):
        # 带有剪枝和扩展的方法
        pass
        
    def GenQueryBySchema(self):
        # 只根据Schema进行生成,生成各种类型的句子。
        # MATCH
        
        # CREATE 很适合！！！
        pass