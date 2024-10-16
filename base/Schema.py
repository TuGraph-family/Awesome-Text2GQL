import json
import os
import csv
import random
from base.Parse import PatternPart, EdgeInstance, Node
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
                if len(self.edge_dict[edge].property_type) > 0:
                    desc = desc + "节点" + vertex + "有属性"
                    for property in self.vertex_dict[vertex].property_type.keys():
                        desc = desc + property + "、"
                    desc = desc[:-1]
                    desc += "。"
            for edge in self.edge_dict:
                if self.edge_dict[edge].property_type.keys() != []:
                    if len(self.edge_dict[edge].property_type) > 0:
                        desc = desc + "边" + edge + "有属性"
                        for property in self.edge_dict[edge].property_type.keys():
                            desc = desc + property + "、"
                        desc = desc[:-1]
                        desc += "。"
            return desc
        return ""

    def get_instance_of_matched_ptn_prts_label_list(
        self, matched_pattern_parts_label_list
    ):
        instance = []
        for part in matched_pattern_parts_label_list:
            instance.append(self.get_instance_of_matched_label_lists(part))
        return instance

    def get_instance_of_matched_label_lists(self, all_label_list):
        instance_of_pattern_match_lists = []
        for label_list in all_label_list:
            # instance_of_pattern_match_list=self.get_instance_of_matched_label_list(label_list)
            instance_of_pattern_match_lists.append(
                copy.deepcopy(self.get_instance_of_matched_label_list(label_list))
            )
        return instance_of_pattern_match_lists

    def get_instance_of_matched_label_list(self, label_list):
        instance_of_pattern_match_list = []
        if len(label_list) == 1:
            instance_of_pattern_match_list.append(
                self.__get_instance_by_label(label_list[0], 1)[0]
            )
        for i in range(1, len(label_list), 2):
            label = label_list[i]
            edge_instance = self.__get_instance_by_label(label, 1)[0]
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
                print(f"[ERROR] no matched data")
        return instance_of_pattern_match_list

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

    def __get_instance_by_label(self, vertex_or_edge_label, count):
        # instance includes 'SRC_ID' and 'DST_ID'
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

    def get_instance_by_label(self, vertex_or_edge_label, count):
        # instance excludes 'SRC_ID' and 'DST_ID'
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
                        if keyword == "SRC_ID" or keyword == "DST_ID":
                            continue
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

    def get_matched_pattern_list(self, pattern_part: PatternPart):  # three nodes
        chain_list = pattern_part.chain_list
        if len(chain_list) <= 3:
            self.get_matched_pattern_list_three_nodes(pattern_part)

    def get_matched_pattern_list_three_nodes(
        self, pattern_part: PatternPart
    ):  # three nodes
        chain_list = pattern_part.chain_list
        all_label_list = []
        edge_count = int(len(chain_list) / 2)
        if edge_count == 0:
            for left_node_label, left_node in self.vertex_dict.items():
                all_label_list.append([left_node_label])
        if edge_count == 1:
            for i in range(edge_count):  # todo
                edge_index = 2 * i + 1
                for left_node_label, left_node in self.vertex_dict.items():
                    if (
                        chain_list[edge_index].left_arrow == True
                        and chain_list[edge_index].right_arrow == False
                    ):
                        for edge in left_node.dst_edge:
                            right_node_label = self.edge_dict[edge].src
                            all_label_list.append(
                                [left_node_label, edge, right_node_label]
                            )
                    elif (
                        chain_list[edge_index].left_arrow == False
                        and chain_list[edge_index].right_arrow == True
                    ):
                        for edge in self.vertex_dict[left_node_label].src_edge:
                            right_node_label = self.edge_dict[edge].dst
                            all_label_list.append(
                                [left_node_label, edge, right_node_label]
                            )
                    else:
                        for edge in self.vertex_dict[left_node_label].dst_edge:
                            right_node_label = self.edge_dict[edge].src
                            all_label_list.append(
                                [left_node_label, edge, right_node_label]
                            )
                        for edge in self.vertex_dict[left_node_label].src_edge:
                            right_node_label = self.edge_dict[edge].dst
                            all_label_list.append(
                                [left_node_label, edge, right_node_label]
                            )
        return all_label_list

    def get_matched_pattern_list_create_edge(
        self, pattern_part: PatternPart, left_label, right_label
    ):
        # ()-[]->()，given one or two node's label, find all the matched edge
        chain_list = pattern_part.chain_list
        all_label_list = []
        edge_index = 1
        for left_node_label, left_node in self.vertex_dict.items():
            if left_node_label == left_label or left_label == "":
                if (
                    chain_list[edge_index].left_arrow == True
                    and chain_list[edge_index].right_arrow == False
                ):
                    for edge in left_node.dst_edge:
                        right_node_label = self.edge_dict[edge].src
                        if right_node_label == right_label:
                            all_label_list.append(
                                [left_node_label, edge, right_node_label]
                            )
                elif (
                    chain_list[edge_index].left_arrow == False
                    and chain_list[edge_index].right_arrow == True
                ):
                    for edge in self.vertex_dict[left_node_label].src_edge:
                        right_node_label = self.edge_dict[edge].dst
                        if right_node_label == right_label or right_label == "":
                            all_label_list.append(
                                [left_node_label, edge, right_node_label]
                            )
                else:
                    for edge in self.vertex_dict[left_node_label].dst_edge:
                        right_node_label = self.edge_dict[edge].src
                        if right_node_label == right_label or right_label == "":
                            all_label_list.append(
                                [left_node_label, edge, right_node_label]
                            )
                    for edge in self.vertex_dict[left_node_label].src_edge:
                        right_node_label = self.edge_dict[edge].dst
                        if right_node_label == right_label or right_label == "":
                            all_label_list.append(
                                [left_node_label, edge, right_node_label]
                            )
        return all_label_list


if __name__ == "__main__":
    from base.Config import Config

    config = Config("config.json")
    cypher_base = CypherBase(config)
    schema = Schema(
        "movie", "/root/work_repo/Awesome-Text2GQL/db_data/schema/movie_schema.json"
    )

    print(schema.gen_desc())
