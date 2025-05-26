import random


class CypherBase:
    def __init__(self, config):
        self.rule_names = [
            "oC_Cypher",
            "oC_Statement",
            "oC_Query",
            "oC_RegularQuery",
            "oC_Union",
            "oC_SingleQuery",
            "oC_SinglePartQuery",
            "oC_MultiPartQuery",
            "oC_UpdatingClause",
            "oC_ReadingClause",
            "oC_Match",
            "oC_Unwind",
            "oC_Merge",
            "oC_MergeAction",
            "oC_Create",
            "oC_Set",
            "oC_SetItem",
            "oC_Delete",
            "oC_Remove",
            "oC_RemoveItem",
            "oC_InQueryCall",
            "oC_StandaloneCall",
            "oC_YieldItems",
            "oC_YieldItem",
            "oC_With",
            "oC_Return",
            "oC_ReturnBody",
            "oC_ReturnItems",
            "oC_ReturnItem",
            "oC_Order",
            "oC_Skip",
            "oC_Limit",
            "oC_SortItem",
            "oC_Hint",
            "oC_Where",
            "oC_Pattern",
            "oC_PatternPart",
            "oC_AnonymousPatternPart",
            "oC_PatternElement",
            "oC_NodePattern",
            "oC_PatternElementChain",
            "oC_RelationshipPattern",
            "oC_RelationshipDetail",
            "oC_Properties",
            "oC_RelationshipTypes",
            "oC_NodeLabels",
            "oC_NodeLabel",
            "oC_RangeLiteral",
            "oC_LabelName",
            "oC_RelTypeName",
            "oC_Expression",
            "oC_OrExpression",
            "oC_XorExpression",
            "oC_AndExpression",
            "oC_NotExpression",
            "oC_ComparisonExpression",
            "oC_AddOrSubtractExpression",
            "oC_MultiplyDivideModuloExpression",
            "oC_PowerOfExpression",
            "oC_UnaryAddOrSubtractExpression",
            "oC_StringListNullOperatorExpression",
            "oC_ListOperatorExpression",
            "oC_StringOperatorExpression",
            "oC_NullOperatorExpression",
            "oC_PropertyOrLabelsExpression",
            "oC_Atom",
            "oC_Literal",
            "oC_BooleanLiteral",
            "oC_ListLiteral",
            "oC_PartialComparisonExpression",
            "oC_ParenthesizedExpression",
            "oC_RelationshipsPattern",
            "oC_FilterExpression",
            "oC_IdInColl",
            "oC_FunctionInvocation",
            "oC_FunctionName",
            "oC_ExplicitProcedureInvocation",
            "oC_ImplicitProcedureInvocation",
            "oC_ProcedureResultField",
            "oC_ProcedureName",
            "oC_Namespace",
            "oC_ListComprehension",
            "oC_PatternComprehension",
            "oC_PropertyLookup",
            "oC_CaseExpression",
            "oC_CaseAlternatives",
            "oC_Variable",
            "oC_NumberLiteral",
            "oC_MapLiteral",
            "oC_Parameter",
            "oC_PropertyExpression",
            "oC_PropertyKeyName",
            "oC_IntegerLiteral",
            "oC_DoubleLiteral",
            "oC_SchemaName",
            "oC_SymbolicName",
            "oC_ReservedWord",
            "oC_LeftArrowHead",
            "oC_RightArrowHead",
            "oC_Dash",
        ]
        self.token_dict = {
            "MATCH": 0,
            "DISTINCT": 1,
            "DESC": 2,
            "ASC": 3,
            "RETURN": 4,
            "OPTIONAL": 5,
        }

        self.template = [[] for _ in range(len(self.token_dict))]
        self.template[self.token_dict["MATCH"]].extend(
            [
                "找到",
                "获得",
                "查询",
                "查找图数据库中",
                "查找数据库中",
                "从数据库中查找",
                "在图中查找",
            ]
        )
        self.template[self.token_dict["OPTIONAL"]].extend(["以可选的方式", "尝试"])
        self.template[self.token_dict["DISTINCT"]].extend(
            ["将查询结果去重", "最后将结果去重"]
        )
        self.template[self.token_dict["DESC"]].extend(["降序"])
        self.template[self.token_dict["ASC"]].extend(["升序", ""])
        self.template[self.token_dict["RETURN"]].extend(
            ["返回子图", "返回相关的节点和关系", ""]
        )
        # schema
        self.schema_dict = {}
        self.load_dict_from_file(config.get_schema_dict_path())

    def get_rule_name(self, rule_index):
        return self.rule_names[rule_index]

    def get_token_desc(self, token_index: int):
        rand = random.randint(0, len(self.template[token_index]) - 1)
        return self.template[token_index][rand]

    def get_token_desc(self, token_name: str):
        token_index = self.token_dict[token_name]
        rand = random.randint(0, len(self.template[token_index]) - 1)
        return self.template[token_index][rand]

    def merge_desc(self, desc_list):
        desc = ""
        for i in range(len(desc_list)):
            desc = desc + desc_list[i] + ","
            if desc_list[i] == "":
                desc = desc[:-1]
            elif desc_list[i][-1] == "？" or desc_list[i][-1] == "?":
                desc = desc[:-1]
        if desc != "":
            if desc[-1] == ",":
                desc = desc[:-1]
        return desc

    def merge_query(self, query_list):
        query = ""
        for i in range(len(query_list)):
            query = query + query_list[i] + ","
            if query_list[i] == "":
                query = query[:-1]
        if query[-1] == ",":
            query = query[:-1]
        return query

    def load_dict_from_file(self, file_paths):
        for file_path in file_paths:
            with open(file_path, "r") as file:
                lines = file.readlines()
            for line in lines:
                elements = line.strip().split()
                if elements:
                    key = elements[0]
                    values = elements[1:]
                    self.schema_dict[key] = values

    def get_schema_desc(self, key):
        try:
            rand = random.randint(0, len(self.schema_dict[key]) - 1)
            return self.schema_dict[key][rand]
        except KeyError:
            return key


if __name__ == "__main__":
    schema_dict_path = "/root/work_repo/Awesome-Text2GQL/base/template/schema_dict.txt"
    cypher_base = CypherBase(schema_dict_path)
    print(cypher_base.get_schema_desc("rate"))
