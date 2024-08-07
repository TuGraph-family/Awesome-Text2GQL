import random

class CypherBase():
    def __init__(self,schemaDictPath):
        self.ruleNames=['oC_Cypher', 'oC_Statement', 'oC_Query', 'oC_RegularQuery', 'oC_Union', 'oC_SingleQuery', 
                        'oC_SinglePartQuery', 'oC_MultiPartQuery', 'oC_UpdatingClause', 'oC_ReadingClause', 'oC_Match',
                        'oC_Unwind', 'oC_Merge', 'oC_MergeAction', 'oC_Create', 'oC_Set', 'oC_SetItem', 'oC_Delete', 
                        'oC_Remove', 'oC_RemoveItem', 'oC_InQueryCall', 'oC_StandaloneCall', 'oC_YieldItems', 
                        'oC_YieldItem', 'oC_With', 'oC_Return', 'oC_ReturnBody', 'oC_ReturnItems', 'oC_ReturnItem', 
                        'oC_Order', 'oC_Skip', 'oC_Limit', 'oC_SortItem', 'oC_Hint', 'oC_Where', 'oC_Pattern', 'oC_PatternPart', 
                        'oC_AnonymousPatternPart', 'oC_PatternElement', 'oC_NodePattern', 'oC_PatternElementChain', 
                        'oC_RelationshipPattern', 'oC_RelationshipDetail', 'oC_Properties', 'oC_RelationshipTypes', 
                        'oC_NodeLabels', 'oC_NodeLabel', 'oC_RangeLiteral', 'oC_LabelName', 'oC_RelTypeName', 
                        'oC_Expression', 'oC_OrExpression', 'oC_XorExpression', 'oC_AndExpression', 'oC_NotExpression',
                        'oC_ComparisonExpression', 'oC_AddOrSubtractExpression', 'oC_MultiplyDivideModuloExpression', 
                        'oC_PowerOfExpression', 'oC_UnaryAddOrSubtractExpression', 'oC_StringListNullOperatorExpression',
                        'oC_ListOperatorExpression', 'oC_StringOperatorExpression', 'oC_NullOperatorExpression', 
                        'oC_PropertyOrLabelsExpression', 'oC_Atom', 'oC_Literal', 'oC_BooleanLiteral', 'oC_ListLiteral',
                        'oC_PartialComparisonExpression', 'oC_ParenthesizedExpression', 'oC_RelationshipsPattern', 
                        'oC_FilterExpression', 'oC_IdInColl', 'oC_FunctionInvocation', 'oC_FunctionName', 
                        'oC_ExplicitProcedureInvocation', 'oC_ImplicitProcedureInvocation', 'oC_ProcedureResultField',
                        'oC_ProcedureName', 'oC_Namespace', 'oC_ListComprehension', 'oC_PatternComprehension', 
                        'oC_PropertyLookup', 'oC_CaseExpression', 'oC_CaseAlternatives', 'oC_Variable', 'oC_NumberLiteral', 
                        'oC_MapLiteral', 'oC_Parameter', 'oC_PropertyExpression', 'oC_PropertyKeyName', 'oC_IntegerLiteral',
                        'oC_DoubleLiteral', 'oC_SchemaName', 'oC_SymbolicName', 'oC_ReservedWord', 'oC_LeftArrowHead',
                        'oC_RightArrowHead', 'oC_Dash']
        self.tokenDict={'MATCH': 0, 'DISTINCT': 1,'DESC':2,'ASC':3}
        
        # 关键字模板
        self.template = [[] for _ in range(len(self.tokenDict))]
        self.template[self.tokenDict['MATCH']].extend(['找到','获得','查询','查找图数据库中','查找数据库中','从数据库中查找'])
        self.template[self.tokenDict['DISTINCT']].extend(['将查询结果去重','最后将结果去重'])
        self.template[self.tokenDict['DESC']].extend(['降序'])
        self.template[self.tokenDict['ASC']].extend(['升序',''])
        # schema相关的关键字模板
        self.schemaDict={}
        self.loadDictFromFile(schemaDictPath)
        
    def getRuleName(self,ruleIndex):
        return self.ruleNames[ruleIndex]
    
    def getTokenDesc(self,tokenIndex:int):
        rand=random.randint(0, len(self.template[tokenIndex])-1)
        return self.template[tokenIndex][rand]
    
    def getTokenDesc(self,tokenName:str):
        tokenIndex=self.tokenDict[tokenName]
        rand=random.randint(0, len(self.template[tokenIndex])-1)
        return self.template[tokenIndex][rand]
    
    def mergeDesc(self,descList):
        desc=''
        for i in range(len(descList)):
            desc=desc+descList[i]+','
            if(descList[i]==''):
                desc = desc[:-1]
        desc = desc[:-1]
        return desc
    
    def loadDictFromFile(self,filePath):
        with open(filePath, 'r') as file:
            lines = file.readlines()
        for line in lines:
            elements = line.strip().split()
            if elements:
                key = elements[0]
                values = elements[1:]
                self.schemaDict[key] = values
                
    def getSchemaDesc(self,key):
        rand=random.randint(0, len(self.schemaDict[key])-1)
        return self.schemaDict[key][rand]

if __name__ == '__main__':
    schemaDictPath='/root/work_repo/Awesome-Text2GQL/base/template/schema_dict.txt'
    cpherBase=CypherBase(schemaDictPath)
    print(cpherBase.getSchemaDesc('rate'))