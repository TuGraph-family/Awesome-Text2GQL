from antlr4 import *
from cypher.LcypherParser import LcypherParser
from cypher.LcypherVisitor import LcypherVisitor
from base.Parse import Node, ReturnBody, PatternPart, EdgeInstance
from base.CypherBase import CypherBase
from base.Schema import Schema
from base.Pattern import ReadPattern, UpdatePattern, CurrentPattern
from base.Expr import ExprTree,ExprLeaf
from base import Config
import copy
import random


class TransVisitor(LcypherVisitor):
    def __init__(self, config: Config):
        self.prompt = ""
        self.current_node_id = 0
        self.config = config
        self.cypher_base = CypherBase(self.config)
        self.return_body = ReturnBody(self.cypher_base, self.config)
        self.cur_pattern_part = PatternPart(self.cypher_base)
        self.if_gen_query = self.config.gen_query
        self.db_id = config.get_db_id()
        schema_path = self.config.get_schema_path(self.db_id)
        self.schema = Schema(self.db_id, schema_path)
        # queryGen
        self.current_pattern = CurrentPattern(self.schema)
        self.gen_query_list = []
        self.gen_optional=True
        self.optional_probability=0.1

    def save2file(self):
        if self.if_gen_query:
            with open(self.config.get_output_path(), "a", encoding="utf-8") as file:
                file.write("cyphers" + "\n")
                for query in self.gen_query_list:
                    file.write(query + "\n")
                file.write("END" + "\n")
            # print("querys have been written into the file:", self.config.get_output_path())
        else:
            with open(self.config.get_output_path(), "a", encoding="utf-8") as file:
                file.write(self.query + "\n")
                file.write(self.prompt + "\n")
            # print("questions have been written into the file:", self.config.get_output_path())

    def visitOC_Cypher(self, ctx: LcypherParser.OC_CypherContext):
        # oC_Cypher : SP? oC_Statement ( SP? ';' )? SP? EOF ;
        self.visitChildren(ctx)

    def visitOC_Statement(self, ctx: LcypherParser.OC_StatementContext):
        self.prompt = str(self.visitChildren(ctx))
        self.query = ctx.getText()
        self.save2file()

    def visitOC_Query(self, ctx: LcypherParser.OC_QueryContext):
        desc = self.visitChildren(ctx)
        return desc

    def visitOC_RegularQuery(self, ctx: LcypherParser.OC_RegularQueryContext):
        desc = self.visitChildren(ctx)
        return desc

    def visitOC_Union(self, ctx: LcypherParser.OC_UnionContext):
        desc = self.visitChildren(ctx)
        return desc

    def visitOC_SingleQuery(self, ctx: LcypherParser.OC_SingleQueryContext):
        desc = self.visitChildren(ctx)
        return desc

    def visitOC_SinglePartQuery(self, ctx: LcypherParser.OC_SinglePartQueryContext):
        # oC_SinglePartQuery : ( ( oC_ReadingClause SP? )* oC_Return )
        #            | ( ( oC_ReadingClause SP? )* oC_UpdatingClause ( SP? oC_UpdatingClause )* ( SP? oC_Return )? )
        desc_list = []
        reading_desc = ""
        update_desc = ""
        return_desc = ""
        for child in ctx.getChildren():
            # if isinstance(child, LcypherParser.OC_ReadingClauseContext): # LcypherParser is not defined???
            #     return self.visit(ctx.oC_ReadingClause())
            if isinstance(child, ParserRuleContext):
                rule_index = child.getRuleIndex()
                rule_name = self.cypher_base.get_rule_name(rule_index)
                if rule_name == "oC_ReadingClause":
                    # readingDesc+=self.visit(ctx.oC_ReadingClause())
                    reading_desc += self.visitOC_ReadingClause(child)
                if rule_name == "oC_UpdatingClause":
                    self.gen_optional=False
                    update_desc += self.visitOC_UpdatingClause(child)
                if rule_name == "oC_Return":
                    return_desc += self.visitOC_Return(child)
        if self.if_gen_query and self.gen_optional:
            for query in self.gen_query_list:
                if random.random() < self.optional_probability:
                    query='OPTIONAL '+query
        desc_list.append(reading_desc)
        desc_list.append(update_desc)
        desc_list.append(return_desc)
        desc = self.cypher_base.merge_desc(desc_list)
        return desc

    # Visit a parse tree produced by LcypherParser#oC_MultiPartQuery.
    def visitOC_MultiPartQuery(self, ctx: LcypherParser.OC_MultiPartQueryContext):
        # oC_MultiPartQuery : ( ( oC_ReadingClause SP? )* ( oC_UpdatingClause SP? )* oC_With SP? )+ oC_SinglePartQuery ;
        # MATCH (n:Person {name:'A'}),(m:Person {name:'C'}) WITH n,m MATCH (n)-[r]->(m) DELETE r
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_UpdatingClause.
    def visitOC_UpdatingClause(self, ctx: LcypherParser.OC_UpdatingClauseContext):
        # oC_UpdatingClause : oC_Create| oC_Merge| oC_Delete | oC_Set| oC_Remove
        self.visitChildren(ctx)
        return ""

    # Visit a parse tree produced by LcypherParser#oC_ReadingClause.
    def visitOC_ReadingClause(self, ctx: LcypherParser.OC_ReadingClauseContext):
        # oC_ReadingClause : oC_Match | oC_Unwind | oC_InQueryCall
        return self.visitChildren(ctx)

    def visit_GenOC_Where(where_tree):
        if where_tree != None:
            pass
        # 生成where语句，深度优先遍历

    def visitGenOC_Match(self, ctx: LcypherParser.OC_MatchContext,where_tree:ExprTree):
        match_pattern = self.current_pattern.get_read_pattern()
        if self.current_pattern.get_matched_label_lists() == ([], []):
            return
        
        # 1. delete those not match
        query2rm_list=where_tree.pre_gen_where(match_pattern.matched_pattern_parts_label_lists)
        self.current_pattern.cur_parse_type == "where"
        self.current_pattern.rm_query_by_index(query2rm_list)
        self.current_pattern.cur_parse_type == "match"
        
        # 2. generate match clause
        for child in ctx.getChildren():
            if isinstance(child, ParserRuleContext):
                rule_index = child.getRuleIndex()
                rule_name = self.cypher_base.get_rule_name(rule_index)
                if rule_name == "oC_Pattern":
                    query_list = []
                    for index, matched_pattern_parts_label_list in enumerate(
                        match_pattern.matched_pattern_parts_label_lists
                    ):
                        query = ""
                        for part_idx, part in enumerate(match_pattern.pattern_parts):
                            label_list = matched_pattern_parts_label_list[part_idx]
                            pattern_part_instance = (
                                self.schema.get_instance_of_matched_label_list(
                                    label_list
                                )
                            )
                            # instantiate & combine
                            query = (
                                query
                                + match_pattern.gen_pattern_part(
                                    part, label_list, pattern_part_instance
                                )
                                + ","
                            )
                        query = "MATCH " + query
                        query = query[:-1]
                        query_list.append(query)
                if rule_name == "oC_Hint":
                    pass
                if rule_name == "oC_Where":
                    # 3. generate where clause
                    self.visit_GenOC_Where(where_tree)
        self.gen_query_list = query_list

    # Visit a parse tree produced by LcypherParser#oC_Match.
    def visitOC_Match(self, ctx: LcypherParser.OC_MatchContext):
        # oC_Match : ( OPTIONAL_ SP )? MATCH SP? oC_Pattern ( SP? oC_Hint )* ( SP? oC_Where )? ;
        self.current_pattern.cur_parse_type = "match"
        desc = ""
        if ctx.OPTIONAL_():
            self.optional_probability = 1
            desc = self.cypher_base.get_token_desc("OPTIONAL")
        match_desc = self.cypher_base.get_token_desc("MATCH")
        # todo support OC_Hint、OC_WHERE
        desc = desc + match_desc
        where_tree=None
        for child in ctx.getChildren():
            if isinstance(child, ParserRuleContext):
                rule_index = child.getRuleIndex()
                rule_name = self.cypher_base.get_rule_name(rule_index)
                if rule_name == "oC_Pattern":
                    pattern_desc = self.visitOC_Pattern(child)
                    desc += pattern_desc
                if rule_name == "oC_Hint":
                    self.visitOC_Hint(child)
                if rule_name == "oC_Where":
                    where_tree=self.visitOC_Where(child)
        if self.if_gen_query:
            self.visitGenOC_Match(ctx,where_tree)
        self.current_pattern.cur_parse_type = ""
        return desc

    # Visit a parse tree produced by LcypherParser#oC_Unwind.
    def visitOC_Unwind(self, ctx: LcypherParser.OC_UnwindContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_Merge.
    def visitOC_Merge(self, ctx: LcypherParser.OC_MergeContext):
        # oC_Merge : MERGE SP? oC_PatternPart ( SP oC_MergeAction )* ;
        self.current_pattern.cur_parse_type = "merge"
        for child in ctx.getChildren():
            if isinstance(child, ParserRuleContext):
                rule_index = child.getRuleIndex()
                rule_name = self.cypher_base.get_rule_name(rule_index)
                if rule_name == "oC_PatternPart":
                    self.visitOC_PatternPart(child)
                    self.cur_pattern_part.parse_finised = True
                    pattern_part = copy.deepcopy(self.cur_pattern_part)
                    self.cur_pattern_part.clean()
                    self.current_pattern.add_pattern_part(pattern_part)
                    if self.if_gen_query:
                        self.visitGenOC_Create_and_Merge(ctx, type="MERGE")
                if rule_name == "oC_MergeAction":
                    self.visitOC_MergeAction(child)
        self.current_pattern.add_update_pattern()
        self.current_pattern.cur_parse_type = ""

    # Visit a parse tree produced by LcypherParser#oC_MergeAction.
    def visitOC_MergeAction(self, ctx: LcypherParser.OC_MergeActionContext):
        # oC_MergeAction : ( ON SP MATCH SP oC_Set )
        #                | ( ON SP CREATE SP oC_Set )
        if ctx.MATCH():
            for list_idx in range(len(self.gen_query_list)):
                self.gen_query_list[list_idx] = (
                    self.gen_query_list[list_idx] + " ON MATCH"
                )
        if ctx.CREATE():
            for list_idx in range(len(self.gen_query_list)):
                self.gen_query_list[list_idx] = (
                    self.gen_query_list[list_idx] + " ON CREATE"
                )
        for child in ctx.getChildren():
            if isinstance(child, ParserRuleContext):
                self.visitOC_Set(child)

    def visitGenOC_Create_and_Merge(self, ctx, type="CREATE"):
        (
            matched_label_lists,
            self.gen_query_list,
        ) = self.current_pattern.get_matched_label_lists(self.gen_query_list)
        update_pattern = self.current_pattern.get_cur_update_pattern()
        if matched_label_lists == []:
            return
        for list_idx, matched_pattern_parts_label_list in enumerate(
            update_pattern.matched_pattern_parts_label_lists
        ):
            query = ""
            for idx, part in enumerate(update_pattern.pattern_parts):
                label_list = matched_pattern_parts_label_list[idx]
                # get_instance(label_list)
                pattern_part_instance = self.schema.get_instance_of_matched_label_list(
                    label_list
                )
                # instantiate & combine
                query = (
                    query
                    + update_pattern.gen_pattern_part(
                        part, label_list, pattern_part_instance
                    )
                    + ", "
                )
            query = query[:-2]
            if type == "CREATE":
                if list_idx > len(self.gen_query_list) - 1:  # only create without match
                    self.gen_query_list.append("CREATE " + query)
                else:
                    self.gen_query_list[list_idx] = (
                        self.gen_query_list[list_idx] + " CREATE " + query
                    )
            elif type == "MERGE":
                if list_idx > len(self.gen_query_list) - 1:
                    self.gen_query_list.append("MERGE " + query)
                else:
                    self.gen_query_list[list_idx] = (
                        self.gen_query_list[list_idx] + " MERGE " + query
                    )

    def visitOC_Create(self, ctx: LcypherParser.OC_CreateContext):
        self.current_pattern.cur_parse_type = "create"
        # oC_Create : CREATE SP? oC_Pattern ;
        self.visitChildren(ctx)
        if self.if_gen_query:
            self.visitGenOC_Create_and_Merge(ctx, type="CREATE")
        self.current_pattern.add_update_pattern()
        self.current_pattern.cur_parse_type = ""

    def visitOC_Set(self, ctx: LcypherParser.OC_SetContext):
        # oC_Set : SET SP? oC_SetItem ( SP? ',' SP? oC_SetItem )* ;
        self.current_pattern.cur_parse_type='set'
        for list_idx in range(len(self.gen_query_list)):
            self.gen_query_list[list_idx] = self.gen_query_list[list_idx] + " SET"
        for child in ctx.getChildren():
            if isinstance(child, ParserRuleContext):
                self.visitOC_SetItem(child)
        for list_idx in range(len(self.gen_query_list)):
            self.gen_query_list[list_idx] = self.gen_query_list[list_idx][:-2]
        self.current_pattern.cur_parse_type=''
        return ""

    def visitOC_SetItem(self, ctx: LcypherParser.OC_SetItemContext):
        # oC_SetItem : ( oC_PropertyExpression SP? '=' SP? oC_Expression ) √
        #            | ( oC_Variable SP? '=' SP? oC_Expression ) √ e.g.: SET r=NULL,SET n=m,SET m = {age: 33},SET m.age = id(n)
        #            | ( oC_Variable SP? '+=' SP? oC_Expression ) e.g:  expression: n.tile
        #            | ( oC_Variable SP? oC_NodeLabels ) e.g.: SET a :MyLabel
        for child in ctx.getChildren():
            if isinstance(child, ParserRuleContext):
                rule_index = child.getRuleIndex()
                rule_name = self.cypher_base.get_rule_name(rule_index)
                variable = ""
                if rule_name == "oC_PropertyExpression":
                    variable, property = self.visitOC_PropertyExpression(child)
                    (
                        clause_idx,
                        part_idx,
                        node_idx,
                    ) = self.current_pattern.find_variable_index(variable)
                    (
                        lable_lists,
                        query_lists,
                    ) = self.current_pattern.get_matched_label_lists()
                    for idx, query in enumerate(self.gen_query_list):
                        label = lable_lists[idx][clause_idx][part_idx][node_idx]
                        node_instance = self.schema.get_instance_by_label(label, 1)[0]
                        if len(node_instance) != 0:
                            property_key, property_value = random.choice(
                                list(node_instance.items())
                            )
                            if type(property_value) == str:
                                property_value = f'"{property_value}"'
                            query = (
                                query
                                + " "
                                + str(variable)
                                + "."
                                + str(property_key)
                                + "="
                                + str(property_value)
                                + ", "
                            )
                            self.gen_query_list[idx] = query
                if rule_name == "oC_Variable":
                    variable = self.visitOC_Variable(child)
                if rule_name == "oC_Expression":
                    expr = self.visitOC_Expression(child)
                if rule_name == "oC_NodeLables":
                    self.visitOC_NodeLabels(
                        child
                    )  # set node label , unnassary, do not supprt now

    # Visit a parse tree produced by LcypherParser#oC_Delete.
    def visitOC_Delete(self, ctx: LcypherParser.OC_DeleteContext):
        delete_text = ctx.getText()
        for list_idx, query in enumerate(self.gen_query_list):
            self.gen_query_list[list_idx] = query + " " + delete_text

    def visitOC_Remove(self, ctx: LcypherParser.OC_RemoveContext):
        # oC_Remove : REMOVE SP oC_RemoveItem ( SP? ',' SP? oC_RemoveItem )* ;
        for list_idx in range(len(self.gen_query_list)):
            self.gen_query_list[list_idx] = self.gen_query_list[list_idx] + " REMOVE"
        for child in ctx.getChildren():
            if isinstance(child, ParserRuleContext):
                self.visitOC_RemoveItem(child)
        for list_idx in range(len(self.gen_query_list)):
            self.gen_query_list[list_idx] = self.gen_query_list[list_idx][:-2]

    def visitOC_RemoveItem(self, ctx: LcypherParser.OC_RemoveItemContext):
        # oC_RemoveItem : ( oC_Variable oC_NodeLabels )
        #               | oC_PropertyExpression
        for child in ctx.getChildren():
            if isinstance(child, ParserRuleContext):
                rule_index = child.getRuleIndex()
                rule_name = self.cypher_base.get_rule_name(rule_index)
                variable = ""
                if rule_name == "oC_PropertyExpression":
                    variable, property = self.visitOC_PropertyExpression(child)
                    (
                        clause_idx,
                        part_idx,
                        node_idx,
                    ) = self.current_pattern.find_variable_index(variable)
                    (
                        lable_lists,
                        query_lists,
                    ) = self.current_pattern.get_matched_label_lists()
                    for idx, query in enumerate(self.gen_query_list):
                        label = lable_lists[idx][clause_idx][part_idx][node_idx]
                        properties = self.schema.get_properties_by_lable(label)
                        if len(properties) != 0:
                            property_key = random.choice(properties)
                            query = (
                                query
                                + " "
                                + str(variable)
                                + "."
                                + str(property_key)
                                + ", "
                            )
                            self.gen_query_list[idx] = query
                if rule_name == "oC_Variable":
                    variable = self.visitOC_Variable(child)
                if rule_name == "oC_NodeLables":
                    self.visitOC_NodeLabels(child)

    def visitOC_InQueryCall(self, ctx: LcypherParser.OC_InQueryCallContext):
        return self.visitChildren(ctx)

    def visitOC_StandaloneCall(self, ctx: LcypherParser.OC_StandaloneCallContext):
        return self.visitChildren(ctx)

    def visitOC_YieldItems(self, ctx: LcypherParser.OC_YieldItemsContext):
        return self.visitChildren(ctx)

    def visitOC_YieldItem(self, ctx: LcypherParser.OC_YieldItemContext):
        return self.visitChildren(ctx)

    def visitOC_With(self, ctx: LcypherParser.OC_WithContext):
        return self.visitChildren(ctx)

    def visitGenOC_Return(self, ctx: LcypherParser.OC_ReturnContext):
        if self.if_gen_query:
            for query_index, query in enumerate(self.gen_query_list):
                property_list = []
                if random.random() > 0.9:
                    query = query + " RETURN DISTINCT "
                else:
                    query = query + " RETURN "
                for item in self.return_body.return_items:
                    tmp_variable = item[0]
                    tmp_property = item[1]
                    (
                        type_idx,
                        part_idx,
                        node_idx,
                    ) = self.current_pattern.find_variable_index(tmp_variable)
                    if type_idx != -1:
                        (
                            matched_pattern_parts_label_lists,
                            query_lists,
                        ) = self.current_pattern.get_matched_label_lists()
                        label = matched_pattern_parts_label_lists[query_index][
                            type_idx
                        ][part_idx][node_idx]
                        if len(item) == 2 and tmp_property == 0:
                            query = query + tmp_variable + ","
                        elif len(item) == 2 and tmp_property != 0:
                            properties = self.schema.get_properties_by_lable(label)
                            size = min(3, len(properties)) - 1
                            if size <= 0:
                                query = query + tmp_variable + ","
                            else:
                                rand = random.randint(0, size)
                                property = properties[rand]
                                query = query + tmp_variable + "." + property + ","
                            property_list.append((label, property))
                        # elif(len(item)==3 and item[1]==0):
                        #     query=query+variable+"AS"+variable+","
                        elif len(item) == 3 and tmp_property != 0:
                            properties = self.schema.get_properties_by_lable(label)
                            size = min(3, len(properties)) - 1
                            if size <= 0:
                                query = query + tmp_variable + ","
                            else:
                                rand = random.randint(0, size)
                                property = properties[rand]
                                query = (
                                    query
                                    + tmp_variable
                                    + "."
                                    + property
                                    + " AS "
                                    + property
                                    + ","
                                )
                            property_list.append((label, property))
                    elif type_idx == -1:
                        query = query + tmp_variable + ","  # RETURN p
                query = query[:-1]
                # orderby
                if self.return_body.order_by != []:
                    query = query + " ORDER BY "
                    rand_nums = random.sample(
                        range(0, len(property_list)), len(self.return_body.order_by)
                    )
                    for i in range(len(self.return_body.order_by)):
                        tmp_variable = self.return_body.order_by[i][0]
                        property = property_list[rand_nums[i]]  # (label,property)
                        query = query + tmp_variable + "." + property[1]
                        if random.random() > 0.8:
                            query = query + " DESC"
                        elif random.random() > 0.9:
                            query = query + " ASC"
                        query = query + ","
                    query = query[:-1]
                # skip
                if random.random() > 0.95:
                    query = query + " SKIP " + str(random.randint(1, 10))
                # limit
                if random.random() > 0.95:
                    query = query + " LIMIT " + str(random.randint(1, 1000))
                self.gen_query_list[query_index] = copy.deepcopy(query)

    # Visit a parse tree produced by LcypherParser#oC_Return.
    def visitOC_Return(self, ctx: LcypherParser.OC_ReturnContext):
        # oC_Return : RETURN ( SP? DISTINCT )? SP oC_ReturnBody ;
        for child in ctx.getChildren():
            if isinstance(child, ParserRuleContext):
                self.visitOC_ReturnBody(child)
        if ctx.DISTINCT():
            self.return_body.distinct = True
        self.visitGenOC_Return(ctx)
        if self.if_gen_query:
            return ""
        return self.return_body.get_desc(
            self.current_pattern.read_pattern.pattern_parts
        )

    # Visit a parse tree produced by LcypherParser#oC_ReturnBody.
    def visitOC_ReturnBody(self, ctx: LcypherParser.OC_ReturnBodyContext):
        # oC_ReturnBody : oC_ReturnItems ( SP oC_Order )? ( SP oC_Skip )? ( SP oC_Limit )? ;
        for child in ctx.getChildren():
            if isinstance(child, ParserRuleContext):
                rule_index = child.getRuleIndex()
                rule_name = self.cypher_base.get_rule_name(rule_index)
                if rule_name == "oC_ReturnItems":
                    self.return_body.return_items = self.visitOC_ReturnItems(child)
                if rule_name == "oC_Order":
                    self.return_body.order_by = self.visitOC_Order(child)
                if rule_name == "oC_Skip":
                    self.return_body.skip = str(self.visitOC_Skip(child))
                if rule_name == "oC_Limit":
                    self.return_body.limit = str(self.visitOC_Limit(child))

    # Visit a parse tree produced by LcypherParser#oC_ReturnItems.
    def visitOC_ReturnItems(self, ctx: LcypherParser.OC_ReturnItemsContext):
        # oC_ReturnItems : ( '*' ( SP? ',' SP? oC_ReturnItem )* )
        #                | ( oC_ReturnItem ( SP? ',' SP? oC_ReturnItem )* )
        #                ;
        return_items = []
        for child in ctx.getChildren():
            if isinstance(child, ParserRuleContext):
                return_items.append(self.visitOC_ReturnItem(child))
        return return_items

    # Visit a parse tree produced by LcypherParser#oC_ReturnItem.
    def visitOC_ReturnItem(self, ctx: LcypherParser.OC_ReturnItemContext):
        # oC_ReturnItem : ( oC_Expression SP AS SP oC_Variable )
        #               | oC_Expression
        return_item = ()
        for child in ctx.getChildren():
            if isinstance(child, ParserRuleContext):
                rule_index = child.getRuleIndex()
                rule_name = self.cypher_base.get_rule_name(rule_index)
                if rule_name == "oC_Expression":
                    return_item = self.visitOC_Expression(child)
                if rule_name == "oC_Variable":
                    return_item = return_item + (self.visitOC_Variable(child),)
        return return_item

    # Visit a parse tree produced by LcypherParser#oC_Order.
    def visitOC_Order(self, ctx: LcypherParser.OC_OrderContext):
        # oC_Order : ORDER SP BY SP oC_SortItem ( ',' SP? oC_SortItem )* ;
        order_by = []
        for child in ctx.getChildren():
            if isinstance(child, ParserRuleContext):
                order_by.append(self.visitOC_SortItem(child))  # return tuple
        return order_by

    # Visit a parse tree produced by LcypherParser#oC_Skip.
    def visitOC_Skip(self, ctx: LcypherParser.OC_SkipContext):
        # oC_Skip : L_SKIP SP oC_Expression ;
        for child in ctx.getChildren():
            if isinstance(child, ParserRuleContext):
                ret = self.visitOC_Expression(child)
                return ret[0]
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_Limit.
    def visitOC_Limit(self, ctx: LcypherParser.OC_LimitContext):
        # oC_Limit : LIMIT SP oC_Expression ;
        for child in ctx.getChildren():
            if isinstance(child, ParserRuleContext):
                ret = self.visitOC_Expression(child)
                return ret[0]
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_SortItem.
    def visitOC_SortItem(self, ctx: LcypherParser.OC_SortItemContext):
        # oC_SortItem : oC_Expression ( SP? ( ASCENDING | ASC | DESCENDING | DESC ) )? ;
        sort_item = ()
        for child in ctx.getChildren():
            if isinstance(child, ParserRuleContext):
                sort_item = self.visitOC_Expression(child)
        if ctx.DESC():
            sort_item += ("DESC",)
        elif ctx.DESCENDING():
            sort_item += ("DESC",)
        else:
            sort_item += ("ASC",)
        return sort_item

    def visitOC_Hint(self, ctx: LcypherParser.OC_HintContext):
        return self.visitChildren(ctx)

    def visitOC_Where(self, ctx: LcypherParser.OC_WhereContext):
        # oC_Where : WHERE SP oC_Expression ;
        self.current_pattern.cur_parse_type='where'
        for child in ctx.getChildren():
            if isinstance(child, ParserRuleContext):
                rule_index = child.getRuleIndex()
                rule_name = self.cypher_base.get_rule_name(rule_index)
                if rule_name == "oC_Expression":
                    root = self.visitOC_Expression(child)
        self.current_pattern.cur_parse_type='match'
        return root

    def visitOC_Pattern(self, ctx: LcypherParser.OC_PatternContext):
        # oC_Pattern : oC_PatternPart ( SP? ',' SP? oC_PatternPart )* ;
        # MATCH (n:person), (m:movie)
        merge_list = []
        for child in ctx.getChildren():
            if isinstance(child, ParserRuleContext):
                rule_index = child.getRuleIndex()
                rule_name = self.cypher_base.get_rule_name(rule_index)
                if rule_name == "oC_PatternPart":
                    pattern_desc = self.visitOC_PatternPart(child)
                    merge_list.append(pattern_desc)
                    self.cur_pattern_part.parse_finised = True
                    pattern_part = copy.deepcopy(self.cur_pattern_part)
                    self.cur_pattern_part.clean()
                    self.current_pattern.add_pattern_part(pattern_part)
        desc = self.cypher_base.merge_desc(merge_list)
        return desc

    def visitOC_PatternPart(self, ctx: LcypherParser.OC_PatternPartContext):
        # oC_PatternPart : ( oC_Variable SP? '=' SP? oC_AnonymousPatternPart )
        #    | oC_AnonymousPatternPart
        desc = ""
        for child in ctx.getChildren():
            if isinstance(child, ParserRuleContext):
                rule_index = child.getRuleIndex()
                rule_name = self.cypher_base.get_rule_name(rule_index)
                if rule_name == "oC_Variable":
                    self.cur_pattern_part.variable = self.visitOC_Variable(child)
                if rule_name == "oC_AnonymousPatternPart":
                    desc = self.visitOC_AnonymousPatternPart(child)
        return desc

    # Visit a parse tree produced by LcypherParser#oC_AnonymousPatternPart.
    def visitOC_AnonymousPatternPart(
        self, ctx: LcypherParser.OC_AnonymousPatternPartContext
    ):
        # oC_AnonymousPatternPart : oC_PatternElement ;
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser #oC_PatternElement.
    def visitOC_PatternElement(self, ctx: LcypherParser.OC_PatternElementContext):
        # oC_PatternElement : ( oC_NodePattern ( SP? oC_PatternElementChain )* )
        #   | ( '(' oC_PatternElement ')' );
        n = ctx.getChildCount()
        desc = ""
        self.cur_pattern_part.text = ctx.getText()
        is_only_one_node = True
        last_node = Node(self.cypher_base)
        for i in range(n):
            c = ctx.getChild(i)
            if isinstance(c, ParserRuleContext):
                rule_index = c.getRuleIndex()
                rule_name = self.cypher_base.get_rule_name(rule_index)
                if rule_name == "oC_NodePattern":
                    first_node = self.visitOC_NodePattern(c)
                    desc = first_node.get_desc()
                    self.cur_pattern_part.add_node(first_node)
                    last_node = first_node
                if rule_name == "oC_PatternElementChain":
                    is_only_one_node = False
                    edge, node = self.visitOC_PatternElementChain(c)
                    edge.add_left_node(last_node)
                    edge.add_right_node(node)
                    edge.parse_finised = True
                    last_node = node
                    self.cur_pattern_part.add_edge(edge)
                    self.cur_pattern_part.add_node(node)
                if rule_name == "oC_PatternElement":
                    return self.visitOC_PatternElement(c)
        if is_only_one_node:
            return desc
        return self.cur_pattern_part.get_desc()

    # Visit a parse tree produced by LcypherParser#oC_NodePattern.
    def visitOC_NodePattern(self, ctx: LcypherParser.OC_NodePatternContext):
        # oC_NodePattern : '(' SP? ( oC_Variable SP? )? ( oC_NodeLabels SP? )? ( oC_Properties SP? )? ')' ;
        node_instance = Node(self.cypher_base)
        n = ctx.getChildCount()
        for i in range(n):
            c = ctx.getChild(i)
            if isinstance(c, ParserRuleContext):
                rule_index = c.getRuleIndex()
                rule_name = self.cypher_base.get_rule_name(rule_index)
                if rule_name == "oC_Variable":
                    variable = str(self.visit(ctx.oC_Variable()))
                    node_instance.add_ariable(variable)
                if rule_name == "oC_NodeLabels":
                    labels = self.visit(ctx.oC_NodeLabels())
                    node_instance.add_labels(labels)
                if rule_name == "oC_Properties":
                    properties, text_properties = self.visit(ctx.oC_Properties())
                    node_instance.add_properties(properties, text_properties)
        node_instance.parse_finised = True
        return node_instance

    # Visit a parse tree produced by LcypherParser#oC_PatternElementChain.
    def visitOC_PatternElementChain(
        self, ctx: LcypherParser.OC_PatternElementChainContext
    ):
        # oC_PatternElementChain : oC_RelationshipPattern SP? oC_NodePattern ;
        n = ctx.getChildCount()
        for i in range(n):
            c = ctx.getChild(i)
            if isinstance(c, ParserRuleContext):
                rule_index = c.getRuleIndex()
                rule_name = self.cypher_base.get_rule_name(rule_index)
                if rule_name == "oC_NodePattern":
                    node = self.visitOC_NodePattern(c)
                if rule_name == "oC_RelationshipPattern":
                    edge = self.visitOC_RelationshipPattern(c)
        return edge, node

    # Visit a parse tree produced by LcypherParser#oC_RelationshipPattern.
    def visitOC_RelationshipPattern(
        self, ctx: LcypherParser.OC_RelationshipPatternContext
    ):
        # oC_RelationshipPattern : ( oC_LeftArrowHead SP? oC_Dash SP? oC_RelationshipDetail? SP? oC_Dash SP? oC_RightArrowHead )
        #                        | ( oC_LeftArrowHead SP? oC_Dash SP? oC_RelationshipDetail? SP? oC_Dash )
        #                        | ( oC_Dash SP? oC_RelationshipDetail? SP? oC_Dash SP? oC_RightArrowHead )
        #                        | ( oC_Dash SP? oC_RelationshipDetail? SP? oC_Dash )
        edge = EdgeInstance()
        n = ctx.getChildCount()
        for i in range(n):
            c = ctx.getChild(i)
            if isinstance(c, ParserRuleContext):
                rule_index = c.getRuleIndex()
                rule_name = self.cypher_base.get_rule_name(rule_index)
                if rule_name == "oC_RelationshipDetail":
                    edge = self.visitOC_RelationshipDetail(c)
        if ctx.oC_LeftArrowHead():
            edge.left_arrow = True
        if ctx.oC_RightArrowHead():
            edge.right_arrow = True
        return edge

    # Visit a parse tree produced by LcypherParser#oC_RelationshipDetail.
    def visitOC_RelationshipDetail(
        self, ctx: LcypherParser.OC_RelationshipDetailContext
    ):
        # oC_RelationshipDetail : '[' SP? ( oC_Variable SP? )? ( oC_RelationshipTypes SP? )? oC_RangeLiteral? ( oC_Properties SP? )? ']' ;
        edge = EdgeInstance()
        n = ctx.getChildCount()
        for i in range(n):
            c = ctx.getChild(i)
            if isinstance(c, ParserRuleContext):
                rule_index = c.getRuleIndex()
                rule_name = self.cypher_base.get_rule_name(rule_index)
                if rule_name == "oC_Variable":
                    edge.variable = self.visitOC_Variable(c)
                if rule_name == "oC_RelationshipTypes":
                    edge.add_lable(self.visitOC_RelationshipTypes(c))
                if rule_name == "oC_RangeLiteral":
                    edge.range = self.visitOC_RangeLiteral(c)
                if rule_name == "oC_Properties":
                    properties, text_properties = self.visit(ctx.oC_Properties())
                    edge.add_properties(properties, text_properties)
        return edge

    # Visit a parse tree produced by LcypherParser#oC_Properties.
    def visitOC_Properties(self, ctx: LcypherParser.OC_PropertiesContext):
        # oC_Properties : oC_MapLiteral
        #       | oC_Parameter
        for child in ctx.getChildren():
            if isinstance(child, ParserRuleContext):
                rule_index = child.getRuleIndex()
                rule_name = self.cypher_base.get_rule_name(rule_index)
                if rule_name == "oC_MapLiteral":
                    return self.visitOC_MapLiteral(child)
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_RelationshipTypes.
    def visitOC_RelationshipTypes(self, ctx: LcypherParser.OC_RelationshipTypesContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_NodeLabels.
    def visitOC_NodeLabels(self, ctx: LcypherParser.OC_NodeLabelsContext):
        # oC_NodeLabels : oC_NodeLabel ( SP? oC_NodeLabel )* ;
        labels = []
        self.visitChildren(ctx)
        n = ctx.getChildCount()
        for i in range(n):
            c = ctx.getChild(i)
            if isinstance(c, ParserRuleContext):
                label = str(self.visitOC_NodeLabel(c))
                labels.append(str(label))
        return labels

    # Visit a parse tree produced by LcypherParser#oC_NodeLabel.
    def visitOC_NodeLabel(self, ctx: LcypherParser.OC_NodeLabelContext):
        # oC_NodeLabel : ':' SP? oC_LabelName ;
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_RangeLiteral.
    def visitOC_RangeLiteral(self, ctx: LcypherParser.OC_RangeLiteralContext):
        # oC_RangeLiteral : '*' SP? ( oC_IntegerLiteral SP? )? ( '..' SP? ( oC_IntegerLiteral SP? )? )? ;
        text = ctx.getText()
        int_list = []
        str = text.replace("*", "").replace(" ", "")
        items = str.split("..")
        position = str.find("..")
        # 1
        if position != 0:
            int_list.append(items[0])
        else:
            int_list.append(str(0))
        # 2
        if len(items) == 2:
            int_list.append(items[1])
        elif position == 0 and len(items) == 1:
            int_list.append(items[0])
        else:
            int_list.append(str(0))
        return int_list

    # Visit a parse tree produced by LcypherParser#oC_LabelName.
    def visitOC_LabelName(self, ctx: LcypherParser.OC_LabelNameContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_RelTypeName.
    def visitOC_RelTypeName(self, ctx: LcypherParser.OC_RelTypeNameContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_Expression.
    def visitOC_Expression(self, ctx: LcypherParser.OC_ExpressionContext):
        # oC_Expression : oC_OrExpression ;
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_OrExpression.
    def visitOC_OrExpression(self, ctx: LcypherParser.OC_OrExpressionContext):
    # oC_OrExpression : oC_XorExpression ( SP OR SP oC_XorExpression )* ;
        if self.current_pattern.cur_parse_type=='where':
            text='OR'
            for child in ctx.getChildren():
                if isinstance(child, ParserRuleContext):
                    if text in ctx.OR():
                        root=ExprTree('OR')
                        root.add_leaf(self.visitOC_OrExpression(child))
                        return root
                    else:
                        return self.visitOC_OrExpression(child)
        else:
            return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_XorExpression.
    def visitOC_XorExpression(self, ctx: LcypherParser.OC_XorExpressionContext):
    # oC_XorExpression : oC_AndExpression ( SP XOR SP oC_AndExpression )* ;
        if self.current_pattern.cur_parse_type=='where':
            text='XOR'
            for child in ctx.getChildren():
                if isinstance(child, ParserRuleContext):
                    if text in ctx.XOR():
                        root=ExprTree('XOR')
                        root.add_leaf(self.visitOC_AndExpression(child))
                        return root
                    else:
                        return self.visitOC_AndExpression(child)
        else:
            return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_AndExpression.
    def visitOC_AndExpression(self, ctx: LcypherParser.OC_AndExpressionContext):
        # oC_AndExpression : oC_NotExpression ( SP AND SP oC_NotExpression )* ;
        # And > Xor > Or
        if self.current_pattern.cur_parse_type=='where':
            text='AND'
            for child in ctx.getChildren():
                if isinstance(child, ParserRuleContext):
                    if text in ctx.AND():
                        root=ExprTree('AND')
                        root.add_leaf(self.visitOC_NotExpression(child))
                        return root
                    else:
                        return self.visitOC_NotExpression(child)
        else:
            return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_NotExpression.
    def visitOC_NotExpression(self, ctx: LcypherParser.OC_NotExpressionContext):
        # oC_NotExpression : ( NOT SP? )* oC_ComparisonExpression ;
        if self.current_pattern.cur_parse_type=='where':
            text='NOT'
            for child in ctx.getChildren():
                if isinstance(child, ParserRuleContext):
                    if text in ctx.NOT():
                        root=ExprTree('NOT')
                        root.add_leaf(self.visitOC_ComparisonExpression(child))
                        return root
                    else:
                        return self.visitOC_ComparisonExpression(child)
        else:
            return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_ComparisonExpression.
    def visitOC_ComparisonExpression(
        self, ctx: LcypherParser.OC_ComparisonExpressionContext
    ):
        # oC_ComparisonExpression : oC_AddOrSubtractExpression ( SP? oC_PartialComparisonExpression )* ;
        symbol = ""
        for child in ctx.getChildren():
            if isinstance(child, ParserRuleContext):
                rule_index = child.getRuleIndex()
                rule_name = self.cypher_base.get_rule_name(rule_index)
                if rule_name == "oC_AddOrSubtractExpression":
                    left_expr = self.visitOC_AddOrSubtractExpression(child)
                if rule_name == "oC_PartialComparisonExpression":
                    symbol, right_expr = self.visitOC_PartialComparisonExpression(child)
                    # todo ，support multi oC_PartialComparisonExpression ?
        if symbol != "":
            leaf = ExprLeaf(left_expr, symbol, right_expr)
            return leaf
        return left_expr

    # Visit a parse tree produced by LcypherParser#oC_AddOrSubtractExpression.
    def visitOC_AddOrSubtractExpression(
        self, ctx: LcypherParser.OC_AddOrSubtractExpressionContext
    ):
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
    def visitOC_ListOperatorExpression(
        self, ctx: LcypherParser.OC_ListOperatorExpressionContext
    ):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_StringOperatorExpression.
    def visitOC_StringOperatorExpression(
        self, ctx: LcypherParser.OC_StringOperatorExpressionContext
    ):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_NullOperatorExpression.
    def visitOC_NullOperatorExpression(
        self, ctx: LcypherParser.OC_NullOperatorExpressionContext
    ):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_PropertyOrLabelsExpression.
    def visitOC_PropertyOrLabelsExpression(
        self, ctx: LcypherParser.OC_PropertyOrLabelsExpressionContext
    ):
        # oC_PropertyOrLabelsExpression : oC_Atom ( SP? oC_PropertyLookup )* ( SP? oC_NodeLabels )? ;
        property=''
        for child in ctx.getChildren():
            if isinstance(child, ParserRuleContext):
                rule_index = child.getRuleIndex()
                rule_name = self.cypher_base.get_rule_name(rule_index)
                if rule_name == "oC_Atom":
                    variable=str(self.visitOC_Atom(child))
                if rule_name == "oC_PropertyLookup":
                    property=str(self.visitOC_PropertyLookup(child))
                if rule_name == "oC_NodeLabels":
                    self.visitOC_NodeLabels(child)
        if property == '':
            return (variable, 0)
        else:
            return (variable, property)

    # Visit a parse tree produced by LcypherParser#oC_Atom.
    def visitOC_Atom(self, ctx: LcypherParser.OC_AtomContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_Literal.
    def visitOC_Literal(self, ctx: LcypherParser.OC_LiteralContext):
        # oC_Literal : oC_NumberLiteral
        #    | StringLiteral
        #    | oC_BooleanLiteral
        #    | NULL_
        #    | oC_MapLiteral
        #    | oC_ListLiteral
        #    ;
        if ctx.StringLiteral():
            ret = str(ctx.StringLiteral()).replace("'", "")
            return ret
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
        # oC_PartialComparisonExpression : ( '=' SP? oC_AddOrSubtractExpression )
        #                            | ( '<>' SP? oC_AddOrSubtractExpression )
        #                            | ( '<' SP? oC_AddOrSubtractExpression )
        #                            | ( '>' SP? oC_AddOrSubtractExpression )
        #                            | ( '<=' SP? oC_AddOrSubtractExpression )
        #                            | ( '>=' SP? oC_AddOrSubtractExpression )
        text = ctx.getText()
        symbol = text[:2]
        if symbol != "<>" and symbol != "<=" or symbol != ">=":
            symbol = symbol[:1]
        for child in ctx.getChildren():
            if isinstance(child, ParserRuleContext):
                rule_index = child.getRuleIndex()
                rule_name = self.cypher_base.get_rule_name(rule_index)
                if rule_name == "oC_AddOrSubtractExpression":
                    add_Or_sub_expr = self.visitOC_AddOrSubtractExpression(child)
        return symbol, add_Or_sub_expr

    # Visit a parse tree produced by LcypherParser#oC_ParenthesizedExpression.
    def visitOC_ParenthesizedExpression(
        self, ctx: LcypherParser.OC_ParenthesizedExpressionContext
    ):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_RelationshipsPattern.
    def visitOC_RelationshipsPattern(
        self, ctx: LcypherParser.OC_RelationshipsPatternContext
    ):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_FilterExpression.
    def visitOC_FilterExpression(self, ctx: LcypherParser.OC_FilterExpressionContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_IdInColl.
    def visitOC_IdInColl(self, ctx: LcypherParser.OC_IdInCollContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_FunctionInvocation.
    def visitOC_FunctionInvocation(
        self, ctx: LcypherParser.OC_FunctionInvocationContext
    ):
# oC_FunctionInvocation : oC_FunctionName SP? '(' SP? ( DISTINCT SP? )? ( oC_Expression SP? ( ',' SP? oC_Expression SP? )* )? ')' ;
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
    def visitOC_ProcedureResultField(
        self, ctx: LcypherParser.OC_ProcedureResultFieldContext
    ):
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
    def visitOC_PatternComprehension(
        self, ctx: LcypherParser.OC_PatternComprehensionContext
    ):
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
        # oC_MapLiteral : '{' SP? ( oC_PropertyKeyName SP? ':' SP? oC_Expression SP? ( ',' SP? oC_PropertyKeyName SP? ':' SP? oC_Expression SP? )* )? '}' ;
        n = ctx.getChildCount()
        properties = []
        text_properties = {}  # dict
        for i in range(n):
            c = ctx.getChild(i)
            if isinstance(c, ParserRuleContext):
                rule_index = c.getRuleIndex()
                rule_name = self.cypher_base.get_rule_name(rule_index)
                if rule_name == "oC_PropertyKeyName":
                    properties.append(str(self.visitOC_PropertyKeyName(c)))
                if rule_name == "oC_Expression":
                    expression = self.visitOC_Expression(c)
                    text_properties[properties[-1]] = str(expression[0])
        return properties, text_properties

    # Visit a parse tree produced by LcypherParser#oC_Parameter.
    def visitOC_Parameter(self, ctx: LcypherParser.OC_ParameterContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_PropertyExpression.
    def visitOC_PropertyExpression(
        self, ctx: LcypherParser.OC_PropertyExpressionContext
    ):
        # oC_PropertyExpression : oC_Atom ( SP? oC_PropertyLookup )+ ;
        tokens = []
        for child in ctx.getChildren():
            if isinstance(child, ParserRuleContext):
                rule_index = child.getRuleIndex()
                rule_name = self.cypher_base.get_rule_name(rule_index)
                if rule_name == "oC_Atom":
                    tokens.append(str(self.visitOC_Atom(child)))
                if rule_name == "oC_PropertyLookup":
                    tokens.append(str(self.visitOC_PropertyLookup(child)))
        if len(tokens) == 1:
            return (tokens[0], 0)
        elif len(tokens) == 2:
            return (tokens[0], tokens[1])
        else:
            print("[ERROR]: cannot parse the property expression")
            return (0, 0)

    # Visit a parse tree produced by LcypherParser#oC_PropertyKeyName.
    def visitOC_PropertyKeyName(self, ctx: LcypherParser.OC_PropertyKeyNameContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_IntegerLiteral.
    def visitOC_IntegerLiteral(self, ctx: LcypherParser.OC_IntegerLiteralContext):
        # # oC_IntegerLiteral : HexInteger
        #           | OctalInteger
        #           | DecimalInteger
        if ctx.DecimalInteger():
            return str(ctx.DecimalInteger())
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_DoubleLiteral.
    def visitOC_DoubleLiteral(self, ctx: LcypherParser.OC_DoubleLiteralContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_SchemaName.
    def visitOC_SchemaName(self, ctx: LcypherParser.OC_SchemaNameContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by LcypherParser#oC_SymbolicName.
    def visitOC_SymbolicName(self, ctx: LcypherParser.OC_SymbolicNameContext):
        return ctx.getText()
        # return ctx.INT().getText()

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
