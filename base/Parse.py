import random
from base.CypherBase import CypherBase
from base.Config import Config


class Node:
    # Vertex Instance
    def __init__(self, node_id, cypher_base: CypherBase):
        self.node_id = node_id
        self.variable = ""
        self.properties = []
        self.text_properties = {}
        self.labels = []
        self.desc = ""
        self.type = "node"
        self.type_desc = "节点"
        # self.random_numbers = [random.randint(0, 9) for _ in range(30)]
        self.parse_finised = False
        self.cypher_base = cypher_base

    def add_ariable(self, variable):
        self.variable = variable

    def add_property(self, property):
        self.properties.append(property)

    def addLable(self, lable):
        self.labels.append(lable)

    def add_properties(self, properties, text_properties):
        self.properties += properties
        self.text_properties.update(text_properties)

    def add_labels(self, labels):
        self.labels += labels

    def get_desc(self):
        # 1. (p:plan {name: "面壁计划"})
        if len(self.labels) == 1:
            label_desc = self.cypher_base.get_schema_desc(self.labels[0])
            if len(self.properties) == 1:
                property_desc = self.cypher_base.get_schema_desc(self.properties[0])
                rand = random.random()
                if rand < 0.15:
                    self.desc = (
                        label_desc
                        + property_desc
                        + "为"
                        + self.text_properties[self.properties[0]]
                        + "的节点"
                        + self.variable
                    )
                elif rand > 0.15 and rand < 0.2:
                    self.desc = self.text_properties[self.properties[0]]
                elif rand > 0.2 and rand < 0.95:
                    self.desc = (
                        property_desc
                        + "为"
                        + self.text_properties[self.properties[0]]
                        + "的"
                        + label_desc
                        + self.variable
                    )
                else:
                    self.desc = (
                        "节点"
                        + self.variable
                        + label_desc
                        + self.text_properties[self.properties[0]]
                    )
            elif (self.properties) == 0:
                self.desc = label_desc + "节点" + self.variable
            else:
                self.desc = ""
                for property in self.properties:
                    property_desc = self.cypher_base.get_schema_desc(property)
                    self.desc = (
                        self.desc
                        + property_desc
                        + "为"
                        + self.text_properties[property]
                        + ","
                    )
                self.desc = self.desc[:-1]
                self.desc = self.desc + "的" + label_desc + self.variable
        elif len(self.labels) == 0 and len(self.properties) == 0:
            self.desc = "节点" + self.variable

        return self.desc


class EdgeInstance:
    def __init__(self):
        # self.node_id=node_id
        self.variable = ""
        self.properties = []
        self.text_properties = {}
        self.labels = []
        self.left_node = ""
        self.right_node = ""
        self.left_arrow = False
        self.right_arrow = False
        self.desc = ""
        self.type = "edge"
        self.range = ["0", "0"]
        self.parse_finised = False
        self.type_desc = "边"

    def add_ariable(self, variable):
        self.variable = variable

    def add_property(self, property):
        self.properties.append(property)

    def add_lable(self, lable):
        self.labels.append(lable)

    def add_properties(self, properties, text_properties):
        self.properties += properties
        self.text_properties.update(text_properties)

    def add_labels(self, labels):
        self.labels += labels

    def add_left_node(self, left):
        self.left_node = left

    def add_right_node(self, right):
        self.right_node = right


class PatternChain:
    def __init__(self, cypher_base: CypherBase):
        # self.chainDict={}
        self.variable = ""
        self.chain_list = []
        self.desc = ""
        self.random_numbers = [random.randint(0, 9) for _ in range(30)]
        self.cypher_base = cypher_base
        self.match_type = 0
        self.parse_finised = False
        self.type = "patterncChain"
        self.type_desc = "匹配的链路"
        self.text = ""

    def clean(self):
        self.chain_list = []
        self.desc = ""
        self.match_type = 0
        self.parse_finised = False

    def get_chain_variable_list(self):
        variable_list = []
        for chain_node in self.chain_list:
            variable_list.append(chain_node.variable)
        return variable_list

    def get_variable_type(self, variable):
        for chain_node in self.chain_list:
            if chain_node.variable == variable:
                return chain_node.type
        if variable == self.variable:
            return self.type
        print("[ERROR]: getVariableType failed!")

    def get_variable_type_desc(self, variable):
        for chain_node in self.chain_list:
            if chain_node.variable == variable:
                return chain_node.type_desc
        if variable == self.variable:
            return self.type_desc
        print("[ERROR]: get_variable_type_desc failed!")

    def find_variable_index(self, variable):
        for index, chain_node in enumerate(self.chain_list):
            if chain_node.variable == variable:
                return index
        if variable == self.variable:
            return -1
        print("[ERROR]: do not support generate only return part without match")

    def get_variable_label(self, variable):
        for chain_node in self.chain_list:
            if chain_node.variable == variable and chain_node.labels != []:
                return chain_node.labels[0]
        return ""

    def add_node(self, node: Node):
        # self.chainDict[node.variable]=node
        self.chain_list.append(node)

    def add_edge(self, edge: EdgeInstance):
        # self.chainDict[edge.variable]=edge
        self.chain_list.append(edge)

    def add_item(self, item):
        # item：variable,property,text_property
        for chain_node in self.chain_list:
            if chain_node.variable == item[0]:
                property_text = item[2]
                property_dict = {}
                property_dict[item[1]] = property_text
                chain_node.add_properties([item[1]], property_dict)

    def get_text(self):
        return self.text

    def pattern_match(self):
        if len(self.chain_list) == 3:
            if (
                len(self.chain_list[0].labels) == 0
                and len(self.chain_list[1].labels) == 1
                and len(self.chain_list[2].labels) == 0
            ):
                # MATCH (n)-[e:person_person]-(m) RETURN n,e,m
                if (
                    self.chain_list[0].variable != ""
                    and self.chain_list[1].variable != ""
                    and self.chain_list[2].variable != ""
                ):
                    self.match_type = 1
            elif (
                len(self.chain_list[0].properties) != 0
                and len(self.chain_list[1].labels) == 0
                and len(self.chain_list[2].labels) == 1
            ):
                if (
                    self.chain_list[1].type == "edge"
                    and self.chain_list[1].left_arrow == False
                    and self.chain_list[1].right_arrow == False
                ):
                    # MATCH (p:plan {name: "面壁计划"})-[e]-(neighbor:person) RETURN neighbor,p,e # 与面壁计划有关的人有哪些？
                    self.match_type = 2
            elif (
                self.chain_list[1].type == "edge" and self.chain_list[1].left_arrow == True
            ):
                # MATCH (m:movie {title: 'Forrest Gump'})<-[:acted_in]-(a:person) RETURN a, m  # 参演了Forrest Gump电影的演员有哪些？
                self.match_type = 3
            elif (
                len(self.chain_list[0].properties) != 0
                and self.chain_list[1].right_arrow == True
                and len(self.chain_list[2].labels) == 1
            ):
                # # MATCH (u:user {login: 'Michael'})-[r:rate]->(m:movie) WHERE r.stars < 3 RETURN m.title, r.stars
                self.match_type = 4
        return self.match_type

    def get_desc(self, gen_return=False):
        match_type = self.pattern_match()
        if match_type == 1:
            # MATCH (n)-[e:person_person]-(m) RETURN n,e,m
            if gen_return:
                if self.random_numbers.pop() < 5:
                    self.desc = "返回图中所有通过" + self.chain_list[1].labels[0] + "关系相连的节点和关系。"
                else:
                    self.desc = (
                        "所有通过"
                        + self.chain_list[1].labels[0]
                        + "类型关系连接的节点对"
                        + self.chain_list[0].variable
                        + "和"
                        + self.chain_list[2].variable
                        + "，并返回这些节点对以及它们之间的person_person关系。"
                    )
            else:
                self.desc = (
                    "所有通过"
                    + self.chain_list[1].labels[0]
                    + "类型关系连接的节点对"
                    + self.chain_list[0].variable
                    + "和"
                    + self.chain_list[2].variable
                )
        elif match_type == 2:
            # MATCH (p:plan {name: "面壁计划"})-[e]-(neighbor:person) RETURN neighbor,p,e # 与面壁计划有关的人有哪些？
            node_desc = self.chain_list[0].get_desc()
            self.desc = (
                "与"
                + node_desc
                + "有关的"
                + self.cypher_base.get_schema_desc(self.chain_list[2].labels[0])
                + "有哪些?"
            )
        elif match_type == 3:
            # MATCH (m:movie {title: 'Forrest Gump'})<-[:acted_in]-(a:person) RETURN a, m  # 参演了Forrest Gump电影的演员有哪些？
            node_desc = self.chain_list[0].get_desc()
            self.desc = (
                self.cypher_base.get_schema_desc(self.chain_list[1].labels[0])
                + node_desc
                + "的"
                + self.cypher_base.get_schema_desc(self.chain_list[2].labels[0])
                + "有哪些?"
            )
        elif match_type == 4:
            # MATCH (u:user {login: 'Michael'})-[r:rate]->(m:movie) WHERE r.stars < 3 RETURN m.title, r.stars
            node_desc = self.chain_list[0].get_desc()
            self.desc = (
                node_desc
                + self.cypher_base.get_schema_desc(self.chain_list[1].labels[0])
                + "的"
                + self.cypher_base.get_schema_desc(self.chain_list[2].labels[0])
                + "有哪些?"
            )
        else:
            if random.random() < 0.99999:
                self.desc = "符合" + self.get_text() + "模式的节点和关系"
            else:
                pass
            # MATCH p=(node{id:"579"})-[]->() RETURN p
            # 从id为579的node节点到其他节点的所有直接相连的路径。
            # []任何关系
            # ()任何节点，所有节点，节点
            # 找到一个节点，然后查找该节点通过任何关系指向的节点。->
        if self.variable != "" and random.random() > 0.5:
            self.desc = self.desc + ",将匹配到的路径赋值给变量" + self.variable
        return self.desc
        # MATCH (a:person {name: "叶文洁"})-[e1:person_person]->(n)<-[e2:person_person]-(b:person {name: "汪淼"}) RETURN a,b,n,e1,e2
        # 查询叶文洁和汪淼这两个人之间的的共同关联的人物都有谁。
        # 查询与叶文洁关联的人物有关的人物，返回子图。

    def gen_query(self, return_type: int = 0):
        query_list = []
        return_query = "RETURN "
        if return_type == 1:
            merge_list = []
            for chain_node in self.chain_list:
                merge_list.append(chain_node.variable) 
            return_query += self.cypher_base.merge_query(merge_list)
            for query in query_list:
                query = query + " " + return_query
        return query_list
        # return type 2


class ReturnBody:
    def __init__(self, cypher_base: CypherBase, config: Config):
        self.cypher_base = cypher_base
        self.config = config
        self.DISTINCT = False
        self.skip = 0
        self.limit = 0
        self.order_by = []  # tuple list，variable and its label/property
        self.return_items = []  # tuple list，len=2 Expreesion，len=3 means AS
        self.desc = ""
        self.order_desc = ""
        self.return_desc = ""
        self.skip_desc = ""
        self.limit_desc = ""
        self.random_numbers = [random.randint(0, 9) for _ in range(30)]
        self.match_type = 0

    def pattern_match(self, pattern_chain_list):
        match_success = True
        if len(pattern_chain_list) == 1:
            # type 1
            pattern_chain = pattern_chain_list[0]
            if len(pattern_chain.chain_list) == len(self.return_items):
                for index, item in enumerate(self.return_items):
                    if (
                        len(item) == 2
                        and item[0] == pattern_chain.chain_list[index].variable
                        and item[1] == 0
                    ):
                        continue
                    else:
                        match_success = False
                        break
            else:
                match_success = False
            if match_success:
                rand = random.random()
                if rand < 0.3:
                    self.return_desc = "返回子图"
                elif rand < 0.7:
                    self.return_desc = "返回相应的节点和关系"
                else:
                    self.return_desc = "返回对应的"
                    merge_list = []
                    for item in self.return_items:
                        variable = item[0]
                        label = ""
                        for patternc_chain in pattern_chain_list:
                            label = patternc_chain.get_variable_label(variable)
                            if label != "":
                                break
                        if label == "":
                            label = variable
                        merge_list.append(self.cypher_base.get_schema_desc(label))
                    self.return_desc = self.return_desc + self.cypher_base.merge_desc(
                        merge_list
                    )

            # type 2 todo
            # RETURN n.name, n.age, n.belt ORDER BY n.name
        elif len(pattern_chain_list) == 2:
            # todo :MATCH (n:person), (m:movie)
            match_success = False
        else:
            match_success = False
        return match_success

    def get_desc(self, pattern_chain_list):
        merge_list = []
        assert len(self.return_items) != 0
        # self.returnDesc=self.patternMatch(matchPattern)
        if self.pattern_match(pattern_chain_list) == False:
            return_desc_list = []
            self.return_desc = "返回"
            for item in self.return_items:
                type_desc = pattern_chain_list[0].get_variable_type_desc(
                    item[0]
                )  # todo ，only support one patternchain
                if len(item) == 3 and item[1] != 0:
                    if self.random_numbers.pop() < 5:
                        return_desc_list.append(
                            item[0]
                            + type_desc
                            + "的"
                            + item[1]
                            + "属性值,并将该值重命名为"
                            + item[2]
                        )
                    else:
                        return_desc_list.append(
                            type_desc
                            + item[0]
                            + "的"
                            + item[1]
                            + "属性值,并将该值重命名为"
                            + item[2]
                        )
                elif len(item) == 3 and item[1] == 0:
                    return_desc_list.append("将该" + type_desc + "重命名为" + item[2])
                elif len(item) == 2 and item[1] == 0:
                    return_desc_list.append(type_desc + item[0])
                else:
                    return_desc_list.append(item[0] + type_desc + "的" + item[1] + "属性值")
            self.return_desc += self.cypher_base.merge_desc(return_desc_list)
        merge_list.append(self.return_desc)

        # orderby
        if len(self.order_by) == 1 and self.DISTINCT == False:
            if self.random_numbers.pop() < 5:
                self.order_desc = (
                    "同时按照"
                    + type_desc
                    + "的"
                    + self.order_by[0][1]
                    + "属性"
                    + self.cypher_base.get_token_desc(self.order_by[0][2])
                    + "排序"
                )
            else:
                self.order_desc = (
                    "按照"
                    + type_desc
                    + "的"
                    + self.order_by[0][1]
                    + "属性"
                    + self.cypher_base.get_token_desc(self.order_by[0][2])
                    + "排列返回的结果"
                )
        elif len(self.order_by) == 2 and self.DISTINCT == False:
            #  ORDER BY n.property1 DESC, n.property2 ASC
            self.order_desc = (
                "返回结果首先按照"
                + self.order_by[0][0]
                + "."
                + self.order_by[0][1]
                + "的值"
                + self.cypher_base.get_token_desc(self.order_by[0][2])
                + "排列，然后在"
                + self.order_by[0][0]
                + "."
                + self.order_by[0][1]
                + "的值相同的情况下，按照"
                + self.order_by[1][0]
                + "."
                + self.order_by[1][1]
                + "的值"
                + self.cypher_base.get_token_desc(self.order_by[1][2])
                + "排列"
            )
        else:
            pass
            # todo : multi sort
        merge_list.append(self.order_desc)

        if self.skip != 0 and self.limit != 0:
            desc = "保留去除前" + str(self.skip) + "条数据后的" + str(self.limit) + "条数据"
            merge_list.append(desc)
        else:
            if self.skip != 0:
                if self.skip == "1":
                    self.skip_desc = "跳过第一条数据"
                else:
                    self.skip_desc = "跳过前" + str(self.skip) + "条数据"
                merge_list.append(self.skip_desc)
            if self.limit != 0:
                if self.random_numbers.pop() < 5:
                    self.limit_desc = "返回" + str(self.limit) + "条数据"
                else:
                    self.limit_desc = "保留前" + str(self.limit) + "条数据"
                merge_list.append(self.limit_desc)

        self.desc = self.cypher_base.merge_desc(merge_list)
        if self.DISTINCT == True:
            self.desc = self.desc + "," + self.cypher_base.get_token_desc("DISTINCT")
        return self.desc


class Where:
    def __init__(self, where_expr):
        self.where_expr = where_expr
        self.desc = ""
