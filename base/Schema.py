import json
import os
import csv
import random
from base.Parse import PatternChain
import copy


class Vertex:
    def __init__(self) -> None:
        self.label = ""
        self.properties = []
        self.src_edge = []
        self.dst_edge = []
        self.file_path = ""


class Edge:
    def __init__(self) -> None:
        self.label = ""
        self.properties = []
        self.src = ""
        self.dst = ""
        self.file_path = ""


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
                    vertex.properties.append(property["name"])
                self.vertex_dict[vertex.label] = vertex
            elif item["type"] == "EDGE":
                edge = Edge()
                edge.label = item["label"]
                if "properties" in item:
                    for property in item["properties"]:
                        edge.properties.append(property["name"])
                self.edge_dict[edge.label] = edge

        vertex_path = json["files"]
        for item in vertex_path:
            if item["label"] in self.edge_dict:
                edge_name = item["label"]
                edge = self.edge_dict[item["label"]]
                edge.src = item["SRC_ID"]
                edge.dst = item["DST_ID"]
                self.vertex_dict[edge.src].src_edge.append(edge_name)
                self.vertex_dict[edge.dst].dst_edge.append(edge_name)
                edge.file_path = os.path.join(self.dir_path, item["path"])
            if item["label"] in self.vertex_dict:
                self.vertex_dict[item["label"]].file_path = os.path.join(
                    self.dir_path, item["path"]
                )
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
                for property in self.vertex_dict[vertex].properties:
                    desc = desc + property + "、"
                desc = desc[:-1]
                desc += "。"
            for edge in self.edge_dict:
                if self.edge_dict[edge].properties != []:
                    desc = desc + "边" + edge + "有属性"
                    for property in self.edge_dict[edge].properties:
                        desc = desc + property + "、"
                    desc = desc[:-1]
                    desc += "。"
            return desc
        return ""

    def get_instance_from_db(self, vertex_or_edge, count):
        file_path = ""
        if vertex_or_edge in self.vertex_dict:
            file_path = self.vertex_dict[vertex_or_edge].file_path
        elif vertex_or_edge in self.edge_dict:
            file_path = self.edge_dict[vertex_or_edge].file_path
        else:
            print("[ERROR]: vertexOrEdge is not exist")
            return
        if os.path.exists(file_path):
            keyword_list = []
            vertex_or_edge_instance_list = []
        with open(file_path, newline="") as csvfile:
            reader = list(csv.reader(csvfile))
            second_row = reader[1]
            for item in second_row:
                item_list = item.split(":")
                keyword_list.append(item_list[0])
            data_from_third_row = reader[2:]
            count = min(count, len(data_from_third_row))
            random_rows = random.sample(data_from_third_row, count)
            for row in random_rows:
                vertex_or_edge_instance = {}
                for index, item in enumerate(row):
                    keyword = keyword_list[index]
                    vertex_or_edge_instance[keyword] = item
                vertex_or_edge_instance_list.append(vertex_or_edge_instance)
        return vertex_or_edge_instance_list

    def get_properties_by_lable(self, label: str):
        for key, value in self.vertex_dict.items():
            if key == label:
                return self.vertex_dict[key].properties
        for key, value in self.edge_dict.items():
            if key == label:
                return self.edge_dict[key].properties

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
    schema = Schema("movie", "Awesome-Text2GQL/data/schema/movie_schema.json")
    print(schema.get_instance_from_db("person", 10))
