import json
import os
import csv
import random
from base.Parse import PatternChain, EdgeInstance, Node
from base.CypherBase import CypherBase
import copy


class Vertex:
    def __init__(self) -> None:
        self.label = ""
        self.property_type = {}
        self.src_edge = []
        self.dst_edge = []
        self.file_path = ""
        self.column_keyword = []


class Edge:
    def __init__(self) -> None:
        self.label = ""
        self.property_type = {}
        self.src = ""
        self.dst = ""
        self.file_path = ""
        self.column_keyword = []


class Schema:
    def __init__(self, db_id, schema_path):
        self.vertex_dict = {}
        self.edge_dict = {}
        self.db_id = db_id
        self.schema_path = schema_path
        self.dir_path = os.path.dirname(os.path.dirname(os.path.abspath(schema_path)))
        self.is_parse_finished = False
        self.parse_schema()

    def parse_schema(self):
        try:
            with open(self.schema_path, "r") as file:
                data = json.load(file)
                self.parse_schema_impl(data)
        except FileNotFoundError:
            print("[ERROR] schema file not found", self.schema_path)

    def parse_schema_impl(self, json):
        schema = json["schema"]
        for item in schema:
            if item["type"] == "VERTEX":
                vertex = Vertex()
                vertex.label = item["label"]
                for property in item["properties"]:
                    vertex.property_type[property["name"]] = str(property["type"])
                self.vertex_dict[vertex.label] = vertex
            elif item["type"] == "EDGE":
                edge = Edge()
                edge.label = item["label"]
                if "properties" in item:
                    for property in item["properties"]:
                        edge.property_type[property["name"]] = str(property["type"])
                self.edge_dict[edge.label] = edge
        file_path = json["files"]
        for item in file_path:
            if item["label"] in self.edge_dict:
                edge_name = item["label"]
                edge = self.edge_dict[item["label"]]
                edge.src = item["SRC_ID"]
                edge.dst = item["DST_ID"]
                edge.column_keyword = item["columns"]
                self.vertex_dict[edge.src].src_edge.append(edge_name)
                self.vertex_dict[edge.dst].dst_edge.append(edge_name)
                edge.file_path = os.path.join(self.dir_path, item["path"])
            if item["label"] in self.vertex_dict:
                node = self.vertex_dict[item["label"]]
                node.column_keyword = item["columns"]
                node.file_path = os.path.join(self.dir_path, item["path"])
        self.is_parse_finished = True

    def gen_desc(self):
        if self.is_parse_finished:
            desc = self.db_id + "包含节点"
            for vertex in self.vertex_dict:
                desc = desc + vertex + "、"
            desc = desc[:-1]
            desc += "和边"
            for edge in self.edge_dict:
                desc = desc + edge + "、"
            desc = desc[:-1]
            desc += "。"
            for vertex in self.vertex_dict:
                desc = desc + "节点" + vertex + "有属性"
                for property in self.vertex_dict[vertex].property_type.keys():
                    desc = desc + property + "、"
                desc = desc[:-1]
                desc += "。"
            for edge in self.edge_dict:
                if self.edge_dict[edge].property_type.keys() != []:
                    desc = desc + "边" + edge + "有属性"
                    for property in self.edge_dict[edge].property_type.keys():
                        desc = desc + property + "、"
                    desc = desc[:-1]
                    desc += "。"
            return desc
        return ""

    def get_instance_of_pattern_match_list(self, all_label_list):
        instance_of_pattern_match_lists = []
        for label_list in all_label_list:
            instance_of_pattern_match_list = []
            if len(label_list) == 1:
                instance_of_pattern_match_list.append(
                    self.get_instance_by_label(label_list[0], 1)[0]
                )
            for i in range(1, len(label_list), 2):
                label = label_list[i]
                edge_instance = self.get_instance_by_label(label, 1)[0]
                edge = self.edge_dict[label]
                if edge.src == label_list[i - 1]:
                    if i == 1:
                        src_vertex_instance = self.get_vertex_by_id(
                            label_list[i - 1], edge_instance["SRC_ID"]
                        )
                        instance_of_pattern_match_list.append(src_vertex_instance)
                    dst_vertex_instance = self.get_vertex_by_id(
                        label_list[i + 1], edge_instance["DST_ID"]
                    )
                    instance_of_pattern_match_list.append(edge_instance)
                    instance_of_pattern_match_list.append(dst_vertex_instance)
                elif edge.dst == label_list[i - 1]:
                    if i == 1:
                        dst_vertex_instance = self.get_vertex_by_id(
                            label_list[i - 1], edge_instance["DST_ID"]
                        )
                        instance_of_pattern_match_list.append(dst_vertex_instance)
                    src_vertex_instance = self.get_vertex_by_id(
                        label_list[i + 1], edge_instance["SRC_ID"]
                    )
                    instance_of_pattern_match_list.append(edge_instance)
                    instance_of_pattern_match_list.append(src_vertex_instance)
                else:
                    print(f"[ERROR] data not match")
            instance_of_pattern_match_lists.append(
                copy.deepcopy(instance_of_pattern_match_list)
            )
        return instance_of_pattern_match_lists

    def rm_long_property_of_instance(self, node_instance):
        rm_key_list = []
        for key, value in node_instance.items():
            if type(value) == str and len(value) > 20:
                rm_key_list.append(key)
        for key in rm_key_list:
            node_instance.pop(key)
        return node_instance

    def get_vertex_by_id(self, label, id):
        if label in self.vertex_dict:
            vertex = self.vertex_dict[label]
        else:
            print(f"[ERROR] vertex not found, vertex_label:{label}, id:{id}")
        file_path = vertex.file_path
        if os.path.exists(file_path):
            with open(file_path, newline="") as csvfile:
                reader = list(csv.reader(csvfile))
                data_from_third_row = reader[1:]
                for row in data_from_third_row:
                    instance = {}
                    if row[0] == str(id):
                        for index, item in enumerate(row):
                            keyword = vertex.column_keyword[index]
                            keyword_type = vertex.property_type[keyword]
                            if "INT" in keyword_type:
                                instance[keyword] = int(item)
                            else:
                                instance[keyword] = str(item)
                        return instance
                    else:
                        continue

    def get_instance_by_label(self, vertex_or_edge_label, count):
        type = ""
        if vertex_or_edge_label in self.vertex_dict:
            node = self.vertex_dict[vertex_or_edge_label]
            type = "vertex"
        elif vertex_or_edge_label in self.edge_dict:
            node = self.edge_dict[vertex_or_edge_label]
            type = "edge"
        else:
            print("[ERROR]: vertex or edge is not exist")
            return
        file_path = node.file_path
        if os.path.exists(file_path):
            vertex_or_edge_instance_list = []
            with open(file_path, newline="") as csvfile:
                reader = list(csv.reader(csvfile))
                data_from_third_row = reader[2:]
                count = min(count, len(data_from_third_row))
                random_rows = random.sample(data_from_third_row, count)
                for row in random_rows:
                    vertex_or_edge_instance = {}
                    for index, item in enumerate(row):
                        keyword = node.column_keyword[index]
                        if keyword in node.property_type:
                            keyword_type = node.property_type[keyword]
                            if "INT" in keyword_type:
                                vertex_or_edge_instance[keyword] = int(item)
                            else:
                                vertex_or_edge_instance[keyword] = str(item)
                        else:
                            vertex_or_edge_instance[keyword] = str(item)
                    vertex_or_edge_instance_list.append(vertex_or_edge_instance)
        return vertex_or_edge_instance_list

    def get_properties_by_lable(self, label: str):
        for key, value in self.vertex_dict.items():
            if key == label:
                return list(self.vertex_dict[key].property_type.keys())
        for key, value in self.edge_dict.items():
            if key == label:
                return list(self.edge_dict[key].property_type.keys())

    def get_pattern_match_list(self, chain_list):
        # variableList=patternChain.getChainVariableList()
        all_label_list = []
        # labelLsit=[]
        edge_count = int(len(chain_list) / 2)
        if edge_count == 0:
            for left_node_variable, left_node in self.vertex_dict.items():
                all_label_list.append([left_node_variable])
        if edge_count == 1:
            for i in range(edge_count):  # todo
                edge_index = 2 * i + 1
                for left_node_variable, left_node in self.vertex_dict.items():
                    if (
                        chain_list[edge_index].left_arrow == True
                        and chain_list[edge_index].right_arrow == False
                    ):
                        for edge in left_node.dst_edge:
                            right_node_variable = self.edge_dict[edge].src
                            all_label_list.append(
                                [left_node_variable, edge, right_node_variable]
                            )
                    elif (
                        chain_list[edge_index].left_arrow == False
                        and chain_list[edge_index].right_arrow == True
                    ):
                        for edge in self.vertex_dict[left_node_variable].src_edge:
                            right_node_variable = self.edge_dict[edge].dst
                            all_label_list.append(
                                [left_node_variable, edge, right_node_variable]
                            )
                    else:
                        for edge in self.vertex_dict[left_node_variable].dst_edge:
                            right_node_variable = self.edge_dict[edge].src
                            all_label_list.append(
                                [left_node_variable, edge, right_node_variable]
                            )
                        for edge in self.vertex_dict[left_node_variable].src_edge:
                            right_node_variable = self.edge_dict[edge].dst
                            all_label_list.append(
                                [left_node_variable, edge, right_node_variable]
                            )
        return all_label_list


if __name__ == "__main__":
    from base.Config import Config

    config = Config("config.json")
    cypher_base = CypherBase(config)
    schema = Schema(
        "movie", "/root/work_repo/Awesome-Text2GQL/db_data/schema/movie_schema.json"
    )
    # print(schema.get_instance_by_label("person", 1))
    # print(schema.get_vertex_by_id('movie',1768))
    node1 = Node(0, cypher_base)
    # MATCH (m:movie {title: 'Forrest Gump'})<-[:acted_in]-(a:person) RETURN a, m
    node1.add_ariable("m")
    node1.add_lable("movie")
    node1.add_properties(["title"], {"title": "Forrest Gump"})
    edge = EdgeInstance()
    edge.add_lable("acted_in")
    edge.add_left_node(node1)
    edge.left_arrow = True
    node2 = Node(1, cypher_base)
    node2.add_lable("person")
    edge.add_right_node(node2)
    chain = PatternChain(cypher_base)
    chain.add_node(node1)
    chain.add_edge(edge)
    chain.add_node(node2)
    lists = schema.get_pattern_match_list(chain.chain_list)
    instance = schema.get_instance_of_pattern_match_list(lists)
    print(instance)
