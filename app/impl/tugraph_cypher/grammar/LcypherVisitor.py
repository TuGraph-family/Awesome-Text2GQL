# Generated from /root/work_repo/antlr_python/cypher/Lcypher.g4 by ANTLR 4.13.1
from antlr4 import *

if "." in __name__:
    from .LcypherParser import LcypherParser
else:
    from LcypherParser import LcypherParser

# This class defines a complete generic visitor for a parse tree produced by LcypherParser.


class LcypherVisitor(ParseTreeVisitor):
    # Visit a parse tree produced by LcypherParser#oC_Cypher.
    def visitOC_Cypher(self, ctx: LcypherParser.OC_CypherContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_Statement.
    def visitOC_Statement(self, ctx: LcypherParser.OC_StatementContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_Query.
    def visitOC_Query(self, ctx: LcypherParser.OC_QueryContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_RegularQuery.
    def visitOC_RegularQuery(self, ctx: LcypherParser.OC_RegularQueryContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_Union.
    def visitOC_Union(self, ctx: LcypherParser.OC_UnionContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_SingleQuery.
    def visitOC_SingleQuery(self, ctx: LcypherParser.OC_SingleQueryContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_SinglePartQuery.
    def visitOC_SinglePartQuery(self, ctx: LcypherParser.OC_SinglePartQueryContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_MultiPartQuery.
    def visitOC_MultiPartQuery(self, ctx: LcypherParser.OC_MultiPartQueryContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_UpdatingClause.
    def visitOC_UpdatingClause(self, ctx: LcypherParser.OC_UpdatingClauseContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_ReadingClause.
    def visitOC_ReadingClause(self, ctx: LcypherParser.OC_ReadingClauseContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_Match.
    def visitOC_Match(self, ctx: LcypherParser.OC_MatchContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_Unwind.
    def visitOC_Unwind(self, ctx: LcypherParser.OC_UnwindContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_Merge.
    def visitOC_Merge(self, ctx: LcypherParser.OC_MergeContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_MergeAction.
    def visitOC_MergeAction(self, ctx: LcypherParser.OC_MergeActionContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_Create.
    def visitOC_Create(self, ctx: LcypherParser.OC_CreateContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_Set.
    def visitOC_Set(self, ctx: LcypherParser.OC_SetContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_SetItem.
    def visitOC_SetItem(self, ctx: LcypherParser.OC_SetItemContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_Delete.
    def visitOC_Delete(self, ctx: LcypherParser.OC_DeleteContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_Remove.
    def visitOC_Remove(self, ctx: LcypherParser.OC_RemoveContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_RemoveItem.
    def visitOC_RemoveItem(self, ctx: LcypherParser.OC_RemoveItemContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_InQueryCall.
    def visitOC_InQueryCall(self, ctx: LcypherParser.OC_InQueryCallContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_StandaloneCall.
    def visitOC_StandaloneCall(self, ctx: LcypherParser.OC_StandaloneCallContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_YieldItems.
    def visitOC_YieldItems(self, ctx: LcypherParser.OC_YieldItemsContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_YieldItem.
    def visitOC_YieldItem(self, ctx: LcypherParser.OC_YieldItemContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_With.
    def visitOC_With(self, ctx: LcypherParser.OC_WithContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_Return.
    def visitOC_Return(self, ctx: LcypherParser.OC_ReturnContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_ReturnBody.
    def visitOC_ReturnBody(self, ctx: LcypherParser.OC_ReturnBodyContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_ReturnItems.
    def visitOC_ReturnItems(self, ctx: LcypherParser.OC_ReturnItemsContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_ReturnItem.
    def visitOC_ReturnItem(self, ctx: LcypherParser.OC_ReturnItemContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_Order.
    def visitOC_Order(self, ctx: LcypherParser.OC_OrderContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_Skip.
    def visitOC_Skip(self, ctx: LcypherParser.OC_SkipContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_Limit.
    def visitOC_Limit(self, ctx: LcypherParser.OC_LimitContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_SortItem.
    def visitOC_SortItem(self, ctx: LcypherParser.OC_SortItemContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_Hint.
    def visitOC_Hint(self, ctx: LcypherParser.OC_HintContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_Where.
    def visitOC_Where(self, ctx: LcypherParser.OC_WhereContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_Pattern.
    def visitOC_Pattern(self, ctx: LcypherParser.OC_PatternContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_PatternPart.
    def visitOC_PatternPart(self, ctx: LcypherParser.OC_PatternPartContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_AnonymousPatternPart.
    def visitOC_AnonymousPatternPart(self, ctx: LcypherParser.OC_AnonymousPatternPartContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_PatternElement.
    def visitOC_PatternElement(self, ctx: LcypherParser.OC_PatternElementContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_NodePattern.
    def visitOC_NodePattern(self, ctx: LcypherParser.OC_NodePatternContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_PatternElementChain.
    def visitOC_PatternElementChain(self, ctx: LcypherParser.OC_PatternElementChainContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_RelationshipPattern.
    def visitOC_RelationshipPattern(self, ctx: LcypherParser.OC_RelationshipPatternContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_RelationshipDetail.
    def visitOC_RelationshipDetail(self, ctx: LcypherParser.OC_RelationshipDetailContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_Properties.
    def visitOC_Properties(self, ctx: LcypherParser.OC_PropertiesContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_RelationshipTypes.
    def visitOC_RelationshipTypes(self, ctx: LcypherParser.OC_RelationshipTypesContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_NodeLabels.
    def visitOC_NodeLabels(self, ctx: LcypherParser.OC_NodeLabelsContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_NodeLabel.
    def visitOC_NodeLabel(self, ctx: LcypherParser.OC_NodeLabelContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_RangeLiteral.
    def visitOC_RangeLiteral(self, ctx: LcypherParser.OC_RangeLiteralContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_LabelName.
    def visitOC_LabelName(self, ctx: LcypherParser.OC_LabelNameContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_RelTypeName.
    def visitOC_RelTypeName(self, ctx: LcypherParser.OC_RelTypeNameContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_Expression.
    def visitOC_Expression(self, ctx: LcypherParser.OC_ExpressionContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_OrExpression.
    def visitOC_OrExpression(self, ctx: LcypherParser.OC_OrExpressionContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_XorExpression.
    def visitOC_XorExpression(self, ctx: LcypherParser.OC_XorExpressionContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_AndExpression.
    def visitOC_AndExpression(self, ctx: LcypherParser.OC_AndExpressionContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_NotExpression.
    def visitOC_NotExpression(self, ctx: LcypherParser.OC_NotExpressionContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_ComparisonExpression.
    def visitOC_ComparisonExpression(self, ctx: LcypherParser.OC_ComparisonExpressionContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_AddOrSubtractExpression.
    def visitOC_AddOrSubtractExpression(self, ctx: LcypherParser.OC_AddOrSubtractExpressionContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_MultiplyDivideModuloExpression.
    def visitOC_MultiplyDivideModuloExpression(
        self, ctx: LcypherParser.OC_MultiplyDivideModuloExpressionContext
    ):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_PowerOfExpression.
    def visitOC_PowerOfExpression(self, ctx: LcypherParser.OC_PowerOfExpressionContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_UnaryAddOrSubtractExpression.
    def visitOC_UnaryAddOrSubtractExpression(
        self, ctx: LcypherParser.OC_UnaryAddOrSubtractExpressionContext
    ):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_StringListNullOperatorExpression.
    def visitOC_StringListNullOperatorExpression(
        self, ctx: LcypherParser.OC_StringListNullOperatorExpressionContext
    ):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_ListOperatorExpression.
    def visitOC_ListOperatorExpression(self, ctx: LcypherParser.OC_ListOperatorExpressionContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_StringOperatorExpression.
    def visitOC_StringOperatorExpression(
        self, ctx: LcypherParser.OC_StringOperatorExpressionContext
    ):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_NullOperatorExpression.
    def visitOC_NullOperatorExpression(self, ctx: LcypherParser.OC_NullOperatorExpressionContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_PropertyOrLabelsExpression.
    def visitOC_PropertyOrLabelsExpression(
        self, ctx: LcypherParser.OC_PropertyOrLabelsExpressionContext
    ):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_Atom.
    def visitOC_Atom(self, ctx: LcypherParser.OC_AtomContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_Literal.
    def visitOC_Literal(self, ctx: LcypherParser.OC_LiteralContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_BooleanLiteral.
    def visitOC_BooleanLiteral(self, ctx: LcypherParser.OC_BooleanLiteralContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_ListLiteral.
    def visitOC_ListLiteral(self, ctx: LcypherParser.OC_ListLiteralContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_PartialComparisonExpression.
    def visitOC_PartialComparisonExpression(
        self, ctx: LcypherParser.OC_PartialComparisonExpressionContext
    ):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_ParenthesizedExpression.
    def visitOC_ParenthesizedExpression(self, ctx: LcypherParser.OC_ParenthesizedExpressionContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_RelationshipsPattern.
    def visitOC_RelationshipsPattern(self, ctx: LcypherParser.OC_RelationshipsPatternContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_FilterExpression.
    def visitOC_FilterExpression(self, ctx: LcypherParser.OC_FilterExpressionContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_IdInColl.
    def visitOC_IdInColl(self, ctx: LcypherParser.OC_IdInCollContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_FunctionInvocation.
    def visitOC_FunctionInvocation(self, ctx: LcypherParser.OC_FunctionInvocationContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_FunctionName.
    def visitOC_FunctionName(self, ctx: LcypherParser.OC_FunctionNameContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_ExplicitProcedureInvocation.
    def visitOC_ExplicitProcedureInvocation(
        self, ctx: LcypherParser.OC_ExplicitProcedureInvocationContext
    ):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_ImplicitProcedureInvocation.
    def visitOC_ImplicitProcedureInvocation(
        self, ctx: LcypherParser.OC_ImplicitProcedureInvocationContext
    ):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_ProcedureResultField.
    def visitOC_ProcedureResultField(self, ctx: LcypherParser.OC_ProcedureResultFieldContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_ProcedureName.
    def visitOC_ProcedureName(self, ctx: LcypherParser.OC_ProcedureNameContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_Namespace.
    def visitOC_Namespace(self, ctx: LcypherParser.OC_NamespaceContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_ListComprehension.
    def visitOC_ListComprehension(self, ctx: LcypherParser.OC_ListComprehensionContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_PatternComprehension.
    def visitOC_PatternComprehension(self, ctx: LcypherParser.OC_PatternComprehensionContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_PropertyLookup.
    def visitOC_PropertyLookup(self, ctx: LcypherParser.OC_PropertyLookupContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_CaseExpression.
    def visitOC_CaseExpression(self, ctx: LcypherParser.OC_CaseExpressionContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_CaseAlternatives.
    def visitOC_CaseAlternatives(self, ctx: LcypherParser.OC_CaseAlternativesContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_Variable.
    def visitOC_Variable(self, ctx: LcypherParser.OC_VariableContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_NumberLiteral.
    def visitOC_NumberLiteral(self, ctx: LcypherParser.OC_NumberLiteralContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_MapLiteral.
    def visitOC_MapLiteral(self, ctx: LcypherParser.OC_MapLiteralContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_Parameter.
    def visitOC_Parameter(self, ctx: LcypherParser.OC_ParameterContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_PropertyExpression.
    def visitOC_PropertyExpression(self, ctx: LcypherParser.OC_PropertyExpressionContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_PropertyKeyName.
    def visitOC_PropertyKeyName(self, ctx: LcypherParser.OC_PropertyKeyNameContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_IntegerLiteral.
    def visitOC_IntegerLiteral(self, ctx: LcypherParser.OC_IntegerLiteralContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_DoubleLiteral.
    def visitOC_DoubleLiteral(self, ctx: LcypherParser.OC_DoubleLiteralContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_SchemaName.
    def visitOC_SchemaName(self, ctx: LcypherParser.OC_SchemaNameContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_SymbolicName.
    def visitOC_SymbolicName(self, ctx: LcypherParser.OC_SymbolicNameContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_ReservedWord.
    def visitOC_ReservedWord(self, ctx: LcypherParser.OC_ReservedWordContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_LeftArrowHead.
    def visitOC_LeftArrowHead(self, ctx: LcypherParser.OC_LeftArrowHeadContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_RightArrowHead.
    def visitOC_RightArrowHead(self, ctx: LcypherParser.OC_RightArrowHeadContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_Dash.
    def visitOC_Dash(self, ctx: LcypherParser.OC_DashContext):
        return self.visitChildren(ctx)


del LcypherParser
