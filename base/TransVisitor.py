# Generated from /root/work_repo/antlr_python/cypher/Lcypher.g4 by ANTLR 4.13.1
from antlr4 import *
from cypher.LcypherParser import LcypherParser
from cypher.LcypherVisitor import LcypherVisitor
from base.Parse import Node,ReturnBody
from base.CypherBase import CypherBase

# This class defines a complete generic visitor for a parse tree produced by LcypherParser.

class TransVisitor(LcypherVisitor):
    def __init__(self):
        self.prompt = ''
        self.nodeList=[]
        self.currentNodeId=0
        self.cypherBase=CypherBase()
        self.returnBody=ReturnBody()
    
    def printPrompt(self):
        print(self.prompt)

    # Visit a parse tree produced by LcypherParser#oC_Cypher.
    def visitOC_Cypher(self, ctx:LcypherParser.OC_CypherContext):
        # oC_Cypher : SP? oC_Statement ( SP? ';' )? SP? EOF ;
        self.visitChildren(ctx)


    # Visit a parse tree produced by LcypherParser#oC_Statement.
    def visitOC_Statement(self, ctx:LcypherParser.OC_StatementContext):
        self.prompt= str(self.visitChildren(ctx))


    # Visit a parse tree produced by LcypherParser#oC_Query.
    def visitOC_Query(self, ctx:LcypherParser.OC_QueryContext):
        desc= self.visitChildren(ctx)
        return desc


    # Visit a parse tree produced by LcypherParser#oC_RegularQuery.
    def visitOC_RegularQuery(self, ctx:LcypherParser.OC_RegularQueryContext):
        desc= self.visitChildren(ctx)
        return desc


    # Visit a parse tree produced by LcypherParser#oC_Union.
    def visitOC_Union(self, ctx:LcypherParser.OC_UnionContext):
        desc= self.visitChildren(ctx)
        return desc


    # Visit a parse tree produced by LcypherParser#oC_SingleQuery.
    def visitOC_SingleQuery(self, ctx:LcypherParser.OC_SingleQueryContext):
        desc= self.visitChildren(ctx)
        return desc
    
    # Visit a parse tree produced by LcypherParser#oC_SinglePartQuery.
    def visitOC_SinglePartQuery(self, ctx:LcypherParser.OC_SinglePartQueryContext):
        # oC_SinglePartQuery : ( ( oC_ReadingClause SP? )* oC_Return )
        #            | ( ( oC_ReadingClause SP? )* oC_UpdatingClause ( SP? oC_UpdatingClause )* ( SP? oC_Return )? )
        descList=[]
        readingDesc=''
        updateDesc=''
        returnDesc=''
        for child in ctx.getChildren():
            # if isinstance(child, LcypherParser.OC_ReadingClauseContext): # LcypherParser is not defined???
            #     return self.visit(ctx.oC_ReadingClause())
            if isinstance(child, ParserRuleContext): # LcypherParser is not defined???
                ruleIndex=child.getRuleIndex()
                ruleName = self.cypherBase.getRuleName(ruleIndex)
                if (ruleName=='oC_ReadingClause'):
                    # readingDesc+=self.visit(ctx.oC_ReadingClause()) # 报错 list没有accept方法 易错点
                    readingDesc += self.visitOC_ReadingClause(child) #0次或多次
                    # readingDesc+=','
                if (ruleName=='oC_UpdatingClause'):
                    updateDesc+=self.visitOC_UpdatingClause(child)
                    # updateDesc+=','
                if (ruleName=='oC_Return'):
                    returnDesc+=self.visit(ctx.oC_Return())
        descList.append(readingDesc)
        descList.append(updateDesc)
        descList.append(returnDesc)
        desc=self.cypherBase.mergeDesc(descList)
        return desc


    # Visit a parse tree produced by LcypherParser#oC_MultiPartQuery.
    def visitOC_MultiPartQuery(self, ctx:LcypherParser.OC_MultiPartQueryContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by LcypherParser#oC_UpdatingClause.
    def visitOC_UpdatingClause(self, ctx:LcypherParser.OC_UpdatingClauseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by LcypherParser#oC_ReadingClause.
    def visitOC_ReadingClause(self, ctx:LcypherParser.OC_ReadingClauseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by LcypherParser#oC_Match.
    def visitOC_Match(self, ctx:LcypherParser.OC_MatchContext):
        # oC_Match : ( OPTIONAL_ SP )? MATCH SP? oC_Pattern ( SP? oC_Hint )* ( SP? oC_Where )? ;
        matchDesc=self.cypherBase.getTokenDesc('MATCH')
        for child in ctx.getChildren():
            if isinstance(child,ParserRuleContext):
                ruleIndex=child.getRuleIndex()
                ruleName = self.cypherBase.getRuleName(ruleIndex)
                if (ruleName=='oC_Pattern'):
                    desc=matchDesc+self.visitOC_Pattern(child)
                    return desc
            # 未完成
        return self.visitChildren(ctx)


    # Visit a parse tree produced by LcypherParser#oC_Unwind.
    def visitOC_Unwind(self, ctx:LcypherParser.OC_UnwindContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by LcypherParser#oC_Merge.
    def visitOC_Merge(self, ctx:LcypherParser.OC_MergeContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by LcypherParser#oC_MergeAction.
    def visitOC_MergeAction(self, ctx:LcypherParser.OC_MergeActionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by LcypherParser#oC_Create.
    def visitOC_Create(self, ctx:LcypherParser.OC_CreateContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by LcypherParser#oC_Set.
    def visitOC_Set(self, ctx:LcypherParser.OC_SetContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by LcypherParser#oC_SetItem.
    def visitOC_SetItem(self, ctx:LcypherParser.OC_SetItemContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by LcypherParser#oC_Delete.
    def visitOC_Delete(self, ctx:LcypherParser.OC_DeleteContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by LcypherParser#oC_Remove.
    def visitOC_Remove(self, ctx:LcypherParser.OC_RemoveContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by LcypherParser#oC_RemoveItem.
    def visitOC_RemoveItem(self, ctx:LcypherParser.OC_RemoveItemContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by LcypherParser#oC_InQueryCall.
    def visitOC_InQueryCall(self, ctx:LcypherParser.OC_InQueryCallContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by LcypherParser#oC_StandaloneCall.
    def visitOC_StandaloneCall(self, ctx:LcypherParser.OC_StandaloneCallContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by LcypherParser#oC_YieldItems.
    def visitOC_YieldItems(self, ctx:LcypherParser.OC_YieldItemsContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by LcypherParser#oC_YieldItem.
    def visitOC_YieldItem(self, ctx:LcypherParser.OC_YieldItemContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by LcypherParser#oC_With.
    def visitOC_With(self, ctx:LcypherParser.OC_WithContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by LcypherParser#oC_Return.
    def visitOC_Return(self, ctx:LcypherParser.OC_ReturnContext):
        #oC_Return : RETURN ( SP? DISTINCT )? SP oC_ReturnBody ;
        for child in ctx.getChildren():
            if isinstance(child,ParserRuleContext):
                self.visitOC_ReturnBody(child)
        if ctx.DISTINCT():
            self.returnBody.distinct=True
        return self.returnBody.getDesc()


    # Visit a parse tree produced by LcypherParser#oC_ReturnBody.
    def visitOC_ReturnBody(self, ctx:LcypherParser.OC_ReturnBodyContext):
        # oC_ReturnBody : oC_ReturnItems ( SP oC_Order )? ( SP oC_Skip )? ( SP oC_Limit )? ;
        for child in ctx.getChildren():
            if isinstance(child,ParserRuleContext):
                ruleIndex=child.getRuleIndex()
                ruleName = self.cypherBase.getRuleName(ruleIndex)
                if (ruleName=='oC_ReturnItems'):
                    self.returnBody.returnItems=self.visitOC_ReturnItems(child)
                if (ruleName=='oC_Order'):
                    self.returnBody.orderBy=self.visitOC_Order(child)
                if (ruleName=='oC_Skip'):
                    self.returnBody.skip=str(self.visitOC_Skip(child))
                if (ruleName=='oC_Limit'):
                    self.returnBody.limit=str(self.visitOC_Limit(child))


    # Visit a parse tree produced by LcypherParser#oC_ReturnItems.
    def visitOC_ReturnItems(self, ctx:LcypherParser.OC_ReturnItemsContext):
        # oC_ReturnItems : ( '*' ( SP? ',' SP? oC_ReturnItem )* )
        #                | ( oC_ReturnItem ( SP? ',' SP? oC_ReturnItem )* )
        #                ;
        returnItems=[]
        for child in ctx.getChildren():
            if isinstance(child,ParserRuleContext):
                returnItems.append(self.visitOC_ReturnItem(child))
        return returnItems

    # Visit a parse tree produced by LcypherParser#oC_ReturnItem.
    def visitOC_ReturnItem(self, ctx:LcypherParser.OC_ReturnItemContext):
        # oC_ReturnItem : ( oC_Expression SP AS SP oC_Variable )
        #               | oC_Expression
        #               ;
        returnItem=()
        for child in ctx.getChildren():
            if isinstance(child,ParserRuleContext):
                ruleIndex=child.getRuleIndex()
                ruleName = self.cypherBase.getRuleName(ruleIndex)
                if (ruleName=='oC_Expression'):
                    returnItem=self.visitOC_Expression(child)
                if (ruleName=='oC_Variable'):
                    returnItem=returnItem+(self.visitOC_Variable(child),)
        return returnItem


    # Visit a parse tree produced by LcypherParser#oC_Order.
    def visitOC_Order(self, ctx:LcypherParser.OC_OrderContext):
        # oC_Order : ORDER SP BY SP oC_SortItem ( ',' SP? oC_SortItem )* ;
        orderBy=[]
        for child in ctx.getChildren():
            if isinstance(child,ParserRuleContext):
                orderBy.append(self.visitOC_SortItem(child)) # 会返回一个元组
        return orderBy


    # Visit a parse tree produced by LcypherParser#oC_Skip.
    def visitOC_Skip(self, ctx:LcypherParser.OC_SkipContext):
        # oC_Skip : L_SKIP SP oC_Expression ;
        for child in ctx.getChildren():
            if isinstance(child,ParserRuleContext):
                ret=self.visitOC_Expression(child)
                return ret[0]
        return self.visitChildren(ctx)


    # Visit a parse tree produced by LcypherParser#oC_Limit.
    def visitOC_Limit(self, ctx:LcypherParser.OC_LimitContext):
        # oC_Limit : LIMIT SP oC_Expression ;
        for child in ctx.getChildren():
            if isinstance(child,ParserRuleContext):
                ret=self.visitOC_Expression(child)
                return ret[0]
        return self.visitChildren(ctx)


    # Visit a parse tree produced by LcypherParser#oC_SortItem.
    def visitOC_SortItem(self, ctx:LcypherParser.OC_SortItemContext):
# oC_SortItem : oC_Expression ( SP? ( ASCENDING | ASC | DESCENDING | DESC ) )? ;
        sortItem=()
        for child in ctx.getChildren():
            if isinstance(child,ParserRuleContext):
                sortItem=self.visitOC_Expression(child)
        if (ctx.DESC()):
            sortItem+=('DESC',)
        elif(ctx.DESCENDING()):
            sortItem+=('DESC',)
        else:
            sortItem+=('ASC',)
        return sortItem

    # Visit a parse tree produced by LcypherParser#oC_Hint.
    def visitOC_Hint(self, ctx:LcypherParser.OC_HintContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by LcypherParser#oC_Where.
    def visitOC_Where(self, ctx:LcypherParser.OC_WhereContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by LcypherParser#oC_Pattern.
    def visitOC_Pattern(self, ctx:LcypherParser.OC_PatternContext):
        # oC_Pattern : oC_PatternPart ( SP? ',' SP? oC_PatternPart )* ;
        return self.visitChildren(ctx)


    # Visit a parse tree produced by LcypherParser#oC_PatternPart.
    def visitOC_PatternPart(self, ctx:LcypherParser.OC_PatternPartContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by LcypherParser#oC_AnonymousPatternPart.
    def visitOC_AnonymousPatternPart(self, ctx:LcypherParser.OC_AnonymousPatternPartContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by LcypherParser#oC_PatternElement.
    def visitOC_PatternElement(self, ctx:LcypherParser.OC_PatternElementContext):
        result=self.visitChildren(ctx)
        return result


    # Visit a parse tree produced by LcypherParser#oC_NodePattern.
    def visitOC_NodePattern(self, ctx:LcypherParser.OC_NodePatternContext):
        # oC_NodePattern : '(' SP? ( oC_Variable SP? )? ( oC_NodeLabels SP? )? ( oC_Properties SP? )? ')' ;
        node_instance=Node(len(self.nodeList))
        self.nodeList.append(node_instance)
        n = ctx.getChildCount()
        for i in range(n):
            c = ctx.getChild(i)
            if isinstance(c,ParserRuleContext):
                ruleIndex=c.getRuleIndex()
                ruleName = self.cypherBase.getRuleName(ruleIndex)
                if (ruleName=='oC_Variable'):
                    variable=str(self.visit(ctx.oC_Variable()))
                    self.nodeList[-1].addVariable(variable)
                if (ruleName=='oC_NodeLabels'):
                    labels=self.visit(ctx.oC_NodeLabels())
                    self.nodeList[-1].addLabels(labels)
                if (ruleName=='oC_Properties'):
                    properties,text_properties=self.visit(ctx.oC_Properties())
                    self.nodeList[-1].addProperties(properties,text_properties)
        self.nodeList[-1].parse_finised=True
        return self.nodeList[-1].getDesc()

    # Visit a parse tree produced by LcypherParser#oC_PatternElementChain.
    def visitOC_PatternElementChain(self, ctx:LcypherParser.OC_PatternElementChainContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by LcypherParser#oC_RelationshipPattern.
    def visitOC_RelationshipPattern(self, ctx:LcypherParser.OC_RelationshipPatternContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by LcypherParser#oC_RelationshipDetail.
    def visitOC_RelationshipDetail(self, ctx:LcypherParser.OC_RelationshipDetailContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by LcypherParser#oC_Properties.
    def visitOC_Properties(self, ctx:LcypherParser.OC_PropertiesContext):
        # oC_Properties : oC_MapLiteral
        #       | oC_Parameter
        for child in ctx.getChildren():
            if isinstance(child,ParserRuleContext):
                ruleIndex=child.getRuleIndex()
                ruleName = self.cypherBase.getRuleName(ruleIndex)
                if (ruleName=='oC_MapLiteral'):
                    return self.visitOC_MapLiteral(child)
        return self.visitChildren(ctx)


    # Visit a parse tree produced by LcypherParser#oC_RelationshipTypes.
    def visitOC_RelationshipTypes(self, ctx:LcypherParser.OC_RelationshipTypesContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by LcypherParser#oC_NodeLabels.
    def visitOC_NodeLabels(self, ctx:LcypherParser.OC_NodeLabelsContext):
        # oC_NodeLabels : oC_NodeLabel ( SP? oC_NodeLabel )* ;
        labels=[]
        self.visitChildren(ctx)
        n = ctx.getChildCount()
        for i in range(n):
            c = ctx.getChild(i)
            if isinstance(c,ParserRuleContext):
                label=str(self.visitOC_NodeLabel(c))
                labels.append(str(label))
        return labels


    # Visit a parse tree produced by LcypherParser#oC_NodeLabel.
    def visitOC_NodeLabel(self, ctx:LcypherParser.OC_NodeLabelContext):
        # oC_NodeLabel : ':' SP? oC_LabelName ;
        return self.visitChildren(ctx)


    # Visit a parse tree produced by LcypherParser#oC_RangeLiteral.
    def visitOC_RangeLiteral(self, ctx:LcypherParser.OC_RangeLiteralContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by LcypherParser#oC_LabelName.
    def visitOC_LabelName(self, ctx:LcypherParser.OC_LabelNameContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by LcypherParser#oC_RelTypeName.
    def visitOC_RelTypeName(self, ctx:LcypherParser.OC_RelTypeNameContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by LcypherParser#oC_Expression.
    def visitOC_Expression(self, ctx:LcypherParser.OC_ExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by LcypherParser#oC_OrExpression.
    def visitOC_OrExpression(self, ctx:LcypherParser.OC_OrExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by LcypherParser#oC_XorExpression.
    def visitOC_XorExpression(self, ctx:LcypherParser.OC_XorExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by LcypherParser#oC_AndExpression.
    def visitOC_AndExpression(self, ctx:LcypherParser.OC_AndExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by LcypherParser#oC_NotExpression.
    def visitOC_NotExpression(self, ctx:LcypherParser.OC_NotExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by LcypherParser#oC_ComparisonExpression.
    def visitOC_ComparisonExpression(self, ctx:LcypherParser.OC_ComparisonExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by LcypherParser#oC_AddOrSubtractExpression.
    def visitOC_AddOrSubtractExpression(self, ctx:LcypherParser.OC_AddOrSubtractExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by LcypherParser#oC_MultiplyDivideModuloExpression.
    def visitOC_MultiplyDivideModuloExpression(self, ctx:LcypherParser.OC_MultiplyDivideModuloExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by LcypherParser#oC_PowerOfExpression.
    def visitOC_PowerOfExpression(self, ctx:LcypherParser.OC_PowerOfExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by LcypherParser#oC_UnaryAddOrSubtractExpression.
    def visitOC_UnaryAddOrSubtractExpression(self, ctx:LcypherParser.OC_UnaryAddOrSubtractExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by LcypherParser#oC_StringListNullOperatorExpression.
    def visitOC_StringListNullOperatorExpression(self, ctx:LcypherParser.OC_StringListNullOperatorExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by LcypherParser#oC_ListOperatorExpression.
    def visitOC_ListOperatorExpression(self, ctx:LcypherParser.OC_ListOperatorExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by LcypherParser#oC_StringOperatorExpression.
    def visitOC_StringOperatorExpression(self, ctx:LcypherParser.OC_StringOperatorExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by LcypherParser#oC_NullOperatorExpression.
    def visitOC_NullOperatorExpression(self, ctx:LcypherParser.OC_NullOperatorExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by LcypherParser#oC_PropertyOrLabelsExpression.
    def visitOC_PropertyOrLabelsExpression(self, ctx:LcypherParser.OC_PropertyOrLabelsExpressionContext):
        #oC_PropertyOrLabelsExpression : oC_Atom ( SP? oC_PropertyLookup )* ( SP? oC_NodeLabels )? ;
        tokens=[]
        for child in ctx.getChildren():
            if isinstance(child,ParserRuleContext):
                ruleIndex=child.getRuleIndex()
                ruleName = self.cypherBase.getRuleName(ruleIndex)
                if (ruleName=='oC_Atom'):
                    tokens.append(str(self.visitOC_Atom(child)))
                if (ruleName=='oC_PropertyLookup'):
                    tokens.append(str(self.visitOC_PropertyLookup(child)))
                if (ruleName=='oC_NodeLabels'): ## ？？？什么含义？
                    self.visitOC_NodeLabels(child)
        if(len(tokens)==1):
            return (tokens[0],0)
        elif(len(tokens)==2):
            return (tokens[0],tokens[1])


    # Visit a parse tree produced by LcypherParser#oC_Atom.
    def visitOC_Atom(self, ctx:LcypherParser.OC_AtomContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by LcypherParser#oC_Literal.
    def visitOC_Literal(self, ctx:LcypherParser.OC_LiteralContext):
        # oC_Literal : oC_NumberLiteral
        #    | StringLiteral
        #    | oC_BooleanLiteral
        #    | NULL_
        #    | oC_MapLiteral
        #    | oC_ListLiteral
        #    ;
        if ctx.StringLiteral():
            ret = str(ctx.StringLiteral()).replace("'", "")
            return ret # 叶子节点,返回属性的值，Tom Hanks
        #// 处理其他分支...
        return self.visitChildren(ctx)


    # Visit a parse tree produced by LcypherParser#oC_BooleanLiteral.
    def visitOC_BooleanLiteral(self, ctx:LcypherParser.OC_BooleanLiteralContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by LcypherParser#oC_ListLiteral.
    def visitOC_ListLiteral(self, ctx:LcypherParser.OC_ListLiteralContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by LcypherParser#oC_PartialComparisonExpression.
    def visitOC_PartialComparisonExpression(self, ctx:LcypherParser.OC_PartialComparisonExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by LcypherParser#oC_ParenthesizedExpression.
    def visitOC_ParenthesizedExpression(self, ctx:LcypherParser.OC_ParenthesizedExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by LcypherParser#oC_RelationshipsPattern.
    def visitOC_RelationshipsPattern(self, ctx:LcypherParser.OC_RelationshipsPatternContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by LcypherParser#oC_FilterExpression.
    def visitOC_FilterExpression(self, ctx:LcypherParser.OC_FilterExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by LcypherParser#oC_IdInColl.
    def visitOC_IdInColl(self, ctx:LcypherParser.OC_IdInCollContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by LcypherParser#oC_FunctionInvocation.
    def visitOC_FunctionInvocation(self, ctx:LcypherParser.OC_FunctionInvocationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by LcypherParser#oC_FunctionName.
    def visitOC_FunctionName(self, ctx:LcypherParser.OC_FunctionNameContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by LcypherParser#oC_ExplicitProcedureInvocation.
    def visitOC_ExplicitProcedureInvocation(self, ctx:LcypherParser.OC_ExplicitProcedureInvocationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by LcypherParser#oC_ImplicitProcedureInvocation.
    def visitOC_ImplicitProcedureInvocation(self, ctx:LcypherParser.OC_ImplicitProcedureInvocationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by LcypherParser#oC_ProcedureResultField.
    def visitOC_ProcedureResultField(self, ctx:LcypherParser.OC_ProcedureResultFieldContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by LcypherParser#oC_ProcedureName.
    def visitOC_ProcedureName(self, ctx:LcypherParser.OC_ProcedureNameContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by LcypherParser#oC_Namespace.
    def visitOC_Namespace(self, ctx:LcypherParser.OC_NamespaceContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by LcypherParser#oC_ListComprehension.
    def visitOC_ListComprehension(self, ctx:LcypherParser.OC_ListComprehensionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by LcypherParser#oC_PatternComprehension.
    def visitOC_PatternComprehension(self, ctx:LcypherParser.OC_PatternComprehensionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by LcypherParser#oC_PropertyLookup.
    def visitOC_PropertyLookup(self, ctx:LcypherParser.OC_PropertyLookupContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by LcypherParser#oC_CaseExpression.
    def visitOC_CaseExpression(self, ctx:LcypherParser.OC_CaseExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by LcypherParser#oC_CaseAlternatives.
    def visitOC_CaseAlternatives(self, ctx:LcypherParser.OC_CaseAlternativesContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by LcypherParser#oC_Variable.
    def visitOC_Variable(self, ctx:LcypherParser.OC_VariableContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by LcypherParser#oC_NumberLiteral.
    def visitOC_NumberLiteral(self, ctx:LcypherParser.OC_NumberLiteralContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by LcypherParser#oC_MapLiteral.
    def visitOC_MapLiteral(self, ctx:LcypherParser.OC_MapLiteralContext):
        #oC_MapLiteral : '{' SP? ( oC_PropertyKeyName SP? ':' SP? oC_Expression SP? ( ',' SP? oC_PropertyKeyName SP? ':' SP? oC_Expression SP? )* )? '}' ;
        n = ctx.getChildCount()
        properties=[]
        text_properties={} # dict
        for i in range(n):
            c = ctx.getChild(i)
            if isinstance(c,ParserRuleContext):
                ruleIndex=c.getRuleIndex()
                ruleName = self.cypherBase.getRuleName(ruleIndex)
                if (ruleName=='oC_PropertyKeyName'):
                    properties.append(str(self.visitOC_PropertyKeyName(c)))
                if (ruleName=='oC_Expression'):
                    expression=self.visitOC_Expression(c)
                    text_properties[properties[-1]]=str(expression[0])
        return properties,text_properties


    # Visit a parse tree produced by LcypherParser#oC_Parameter.
    def visitOC_Parameter(self, ctx:LcypherParser.OC_ParameterContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by LcypherParser#oC_PropertyExpression.
    def visitOC_PropertyExpression(self, ctx:LcypherParser.OC_PropertyExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by LcypherParser#oC_PropertyKeyName.
    def visitOC_PropertyKeyName(self, ctx:LcypherParser.OC_PropertyKeyNameContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by LcypherParser#oC_IntegerLiteral.
    def visitOC_IntegerLiteral(self, ctx:LcypherParser.OC_IntegerLiteralContext):
        # # oC_IntegerLiteral : HexInteger
        #           | OctalInteger # 八进制
        #           | DecimalInteger #十进制
        #           ; # 三种词法
        if ctx.DecimalInteger():
            return str(ctx.DecimalInteger()) # 叶子节点
        return self.visitChildren(ctx)


    # Visit a parse tree produced by LcypherParser#oC_DoubleLiteral.
    def visitOC_DoubleLiteral(self, ctx:LcypherParser.OC_DoubleLiteralContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by LcypherParser#oC_SchemaName.
    def visitOC_SchemaName(self, ctx:LcypherParser.OC_SchemaNameContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by LcypherParser#oC_SymbolicName.
    def visitOC_SymbolicName(self, ctx:LcypherParser.OC_SymbolicNameContext):
        return ctx.getText()
        # return ctx.INT().getText() # 获取叶子节点的值


    # Visit a parse tree produced by LcypherParser#oC_ReservedWord.
    def visitOC_ReservedWord(self, ctx:LcypherParser.OC_ReservedWordContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by LcypherParser#oC_LeftArrowHead.
    def visitOC_LeftArrowHead(self, ctx:LcypherParser.OC_LeftArrowHeadContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by LcypherParser#oC_RightArrowHead.
    def visitOC_RightArrowHead(self, ctx:LcypherParser.OC_RightArrowHeadContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by LcypherParser#oC_Dash.
    def visitOC_Dash(self, ctx:LcypherParser.OC_DashContext):
        return self.visitChildren(ctx)

del LcypherParser