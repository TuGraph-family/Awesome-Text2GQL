import json
import os
import csv
import random
from app.impl.tugraph_cypher.generalizer.base.Parse import Node
from app.core.schema.node import Node
from app.core.schema.edge import Edge
from app.core.schema.schema_graph import SchemaGraph
from app.core.schema.schema_parser import SchemaParser


class TuGraphVertex:
    def __init__(self) -> None:
        self.label = ""
        self.property_type = {}
        self.required = []
        self.src_edge = []
        self.dst_edge = []
        self.file_path = ""
        self.header = 0
        self.column_keyword = []


class TuGraphEdge:
    def __init__(self) -> None:
        self.label = ""
        self.property_type = {}
        self.required = []
        self.src = ""
        self.dst = ""
        self.file_path = ""
        self.header = 0
        self.column_keyword = []


class TuGraphSchemaParser(SchemaParser):
    def __init__(self, db_id, instance_path):
        self.vertex_dict = {}
        self.edge_dict = {}
        self.db_id = db_id
        self.schema_path = f"{instance_path}/schema.json"
        self.dir_path = f"{instance_path}/"
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
                vertex = TuGraphVertex()
                vertex.label = item["label"]
                for property in item["properties"]:
                    vertex.property_type[property["name"]] = str(property["type"])
                    if "optional" in property:
                        if bool(property["optional"]) == False:
                            vertex.required.append(property["name"])
                    else:
                        vertex.required.append(property["name"])
                self.vertex_dict[vertex.label] = vertex
            elif item["type"] == "EDGE":
                edge = TuGraphEdge()
                edge.label = item["label"]
                if "properties" in item:
                    for property in item["properties"]:
                        edge.property_type[property["name"]] = str(property["type"])
                    if "optional" in property:
                        if bool(property["optional"]) == False:
                            edge.required.append(property["name"])
                    else:
                        edge.required.append(property["name"])
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
                if "header" in item:
                    edge.header = int(item["header"])
            if item["label"] in self.vertex_dict:
                node = self.vertex_dict[item["label"]]
                node.column_keyword = item["columns"]
                node.file_path = os.path.join(self.dir_path, item["path"])
                if "header" in item:
                    node.header = int(item["header"])
        self.is_parse_finished = True

    def get_schema_graph(self):
        schema_graph = SchemaGraph(self.db_id)
        for vertex_label in self.vertex_dict:
            tugraph_vertex = self.vertex_dict[vertex_label]
            properties = []
            for property_name in tugraph_vertex.property_type:
                property_dict = {}
                property_dict["name"] = property_name
                property_dict["type"] = tugraph_vertex.property_type[property_name]
                properties.append(property_dict)
            node = Node(vertex_label, properties)
            schema_graph.add_node(node)
        for edge_label in self.edge_dict:
            tugraph_edge = self.edge_dict[edge_label]
            properties = []
            for property_name in tugraph_edge.property_type:
                property_dict = {}
                property_dict["name"] = property_name
                property_dict["type"] = tugraph_edge.property_type[property_name]
                properties.append(property_dict)
            src_dst_list = [[tugraph_edge.src, tugraph_edge.dst]]
            edge = Edge(edge_label, properties, src_dst_list)
            schema_graph.add_edge(edge)

        return schema_graph

    def get_vertex_instance_by_id(self, label, id):
        if label in self.vertex_dict:
            vertex = self.vertex_dict[label]
        else:
            print(f"[ERROR] vertex not found, vertex_label:{label}, id:{id}")
        file_path = vertex.file_path
        header = vertex.header
        if os.path.exists(file_path):
            with open(file_path, newline="") as csvfile:
                reader = list(csv.reader(csvfile))
                data = reader[header:]
                for row in data:
                    instance = {}
                    if row[0] == str(id):
                        for index, item in enumerate(row):
                            keyword = vertex.column_keyword[index]
                            keyword_type = vertex.property_type[keyword]
                            if "INT" in keyword_type:
                                instance[keyword] = int(item)
                            elif keyword_type == "STRING":
                                instance[keyword] = str(item)
                            else:
                                instance[keyword] = float(item)
                        return instance
        # print(f"[WARNING] vertex_instance not found, vertex_label:{label}, vertex_id:{id}")
        return {}

    def get_edge_instance_by_src_id(self, edge_label, src_id):
        # instance includes 'SRC_ID' and 'DST_ID'
        if edge_label in self.edge_dict:
            edge = self.edge_dict[edge_label]
        else:
            print(f"[ERROR] edge not found, edge_label:{edge_label}")
        file_path = edge.file_path
        header = edge.header
        src_idx = edge.column_keyword.index("SRC_ID")
        if os.path.exists(file_path):
            with open(file_path, newline="") as csvfile:
                reader = list(csv.reader(csvfile))
                data_from_third_row = reader[header:]
                for row in data_from_third_row:
                    instance = {}
                    if row[src_idx] == str(src_id):
                        for index, item in enumerate(row):
                            keyword = edge.column_keyword[index]
                            if keyword in edge.property_type:
                                keyword_type = edge.property_type[keyword]
                                if "INT" in keyword_type:
                                    instance[keyword] = int(item)
                                elif keyword_type == "STRING":
                                    instance[keyword] = str(item)
                                else:
                                    instance[keyword] = float(item)
                            else:
                                instance[keyword] = str(item)
                        return instance
        return {}

    def get_edge_instance_by_dst_id(self, edge_label, dst_id):
        # instance includes 'SRC_ID' and 'DST_ID'
        if edge_label in self.edge_dict:
            edge = self.edge_dict[edge_label]
        else:
            print(f"[ERROR] edge not found, edge_label:{edge_label}")
        file_path = edge.file_path
        header = edge.header
        dst_idx = edge.column_keyword.index("DST_ID")
        if os.path.exists(file_path):
            with open(file_path, newline="") as csvfile:
                reader = list(csv.reader(csvfile))
                data_from_third_row = reader[header:]
                for row in data_from_third_row:
                    instance = {}
                    if row[dst_idx] == str(dst_id):
                        for index, item in enumerate(row):
                            keyword = edge.column_keyword[index]
                            if keyword in edge.property_type:
                                keyword_type = edge.property_type[keyword]
                                if "INT" in keyword_type:
                                    instance[keyword] = int(item)
                                elif keyword_type == "STRING":
                                    instance[keyword] = str(item)
                                else:
                                    instance[keyword] = float(item)
                            else:
                                instance[keyword] = str(item)
                        return instance
        # print("[WARNING]: the edge instance cannot been found, dst_id is {dst_id}")
        return {}

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
        header = node.header
        if os.path.exists(file_path):
            vertex_or_edge_instance_list = []
            with open(file_path, newline="") as csvfile:
                reader = list(csv.reader(csvfile))
                data_from_third_row = reader[header:]
                count = min(count, len(data_from_third_row))
                if count == 1:
                    random_rows = random.sample(data_from_third_row, count)
                else:
                    random_rows = data_from_third_row[:count]
                    random.shuffle(random_rows)
                for row in random_rows:
                    vertex_or_edge_instance = {}
                    for index, item in enumerate(row):
                        keyword = node.column_keyword[index]
                        if keyword in node.property_type:
                            keyword_type = node.property_type[keyword]
                            if "INT" in keyword_type:
                                vertex_or_edge_instance[keyword] = int(item)
                            elif keyword_type == "STRING":
                                vertex_or_edge_instance[keyword] = str(item)
                            else:
                                vertex_or_edge_instance[keyword] = float(item)
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
        header = node.header
        if os.path.exists(file_path):
            vertex_or_edge_instance_list = []
            with open(file_path, newline="") as csvfile:
                reader = list(csv.reader(csvfile))
                data_from_third_row = reader[header:]
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
                            elif keyword_type == "STRING":
                                vertex_or_edge_instance[keyword] = str(item)
                            else:
                                vertex_or_edge_instance[keyword] = float(item)
                        else:
                            vertex_or_edge_instance[keyword] = str(item)
                    vertex_or_edge_instance_list.append(vertex_or_edge_instance)
        return vertex_or_edge_instance_list
