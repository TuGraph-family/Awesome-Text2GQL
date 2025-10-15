from collections import deque
import random
import string
from typing import Dict, List, Tuple

from app.core.clauses.match_clause import EdgePattern, NodePattern, PathPattern
from app.core.clauses.return_clause import ReturnBody, ReturnItem
from app.core.clauses.where_clause import CompareExpression
from app.core.schema.edge import Edge
from app.core.schema.node import Node


class SchemaGraph:
    def __init__(self, db_id):
        self.db_id = db_id
        self.node_dict: dict[Node] = {}
        self.edge_dict: dict[Edge] = {}
        self.adjacency_list: Dict[str, List[Tuple[str, str]]] = {}
        self.reverse_adjacency_list: Dict[str, List[Tuple[str, str]]] = {}

    def add_node(self, node: Node):
        self.node_dict[node.label] = node
        self.adjacency_list[node.label] = []
        self.reverse_adjacency_list[node.label] = []

    def add_edge(self, edge: Edge):
        self.edge_dict[edge.label] = edge
        for [src, dst] in edge.src_dst_list:
            self.adjacency_list[src].append((edge.label, dst))
            self.reverse_adjacency_list[dst].append((edge.label, src))

    def gen_desc(self):
        desc = f"{self.db_id} includes\nnodes: "
        for node in self.node_dict:
            desc = desc + node + ", "
        desc = desc.strip(", ")
        desc += "\nedges: "
        for edge in self.edge_dict:
            desc = desc + edge + ", "
        desc = desc.strip(", ")
        desc += ".\n"
        for node in self.node_dict:
            if len(self.node_dict[node].properties) > 0:
                desc += f"Node {node} has properties: "
                for property in self.node_dict[node].properties:
                    desc = desc + property["name"] + ", "
                desc = desc.strip(", ")
                desc += ".\n"
        for edge in self.edge_dict:
            if len(self.edge_dict[edge].properties) > 0:
                desc += f"Edge {edge} has properties: "
                for property in self.edge_dict[edge].properties:
                    desc = desc + property["name"] + ", "
                desc = desc.strip(", ")
                desc += ".\n"
        return desc.strip("\n")

    def print_schema_graph(self):
        for node_src in self.adjacency_list:
            for [edge, node_dst] in self.adjacency_list[node_src]:
                print(f"({node_src})-[{edge}]->({node_dst})")

    def match_path_pattern(self, path_pattern: PathPattern) -> List[PathPattern]:
        # match all path with the same degree in schema graph
        path_degree = len(path_pattern.edge_pattern_list)
        path_pattern_deque: deque = deque()
        for node_label in self.node_dict:
            path_pattern_deque.append([node_label])
        while path_degree != 0:
            deque_len = len(path_pattern_deque)
            for _ in range(deque_len):
                path = path_pattern_deque.popleft()
                node_l = path[-1]
                # match all edeges start from node_l
                for edge, node_r in self.adjacency_list[node_l]:
                    path_pattern_deque.append(path + [edge, node_r])
                # match all edges end with node_l
                for edge, node_r in self.reverse_adjacency_list[node_l]:
                    if node_l != node_r:
                        path_pattern_deque.append(path + [edge, node_r])
            path_degree -= 1

        # format all found path to PathPattern
        path_pattern_list = []
        for path in path_pattern_deque:
            tmp_path_pattern = PathPattern([], [])
            for i in range(len(path)):
                if i % 2 == 0:
                    # node
                    id = (i // 2) + 1
                    node: Node = self.node_dict[path[i]]
                    node_pattern = NodePattern(
                        symbolic_name=f"n{str(id)}", label=node.label, property_maps=[]
                    )
                    tmp_path_pattern.node_pattern_list.append(node_pattern)
                else:
                    # edge
                    id = (i // 2) + 1
                    edge: Edge = self.edge_dict[path[i]]
                    direction = ""
                    if [path[i - 1], path[i + 1]] in edge.src_dst_list:
                        direction = "right"
                    if [path[i + 1], path[i - 1]] in edge.src_dst_list:
                        if direction == "":
                            direction = "left"
                        else:
                            direction = "bidirection"
                    edge_pattern = EdgePattern(
                        symbolic_name=f"e{str(id)}",
                        label=edge.label,
                        direction=direction,
                        property_maps=[],
                        hop_range=path_pattern.edge_pattern_list[id - 1].hop_range,
                    )
                    tmp_path_pattern.edge_pattern_list.append(edge_pattern)
            path_pattern_list.append(tmp_path_pattern)
        return path_pattern_list

    def match_where_expression(self, symbolic_name: str, label: str) -> CompareExpression:
        if "n" in symbolic_name:
            properties = self.node_dict[label].properties
        elif "e" in symbolic_name:
            properties = self.edge_dict[label].properties
        property = properties[random.randint(0, len(properties) - 1)]["name"]
        type = properties[random.randint(0, len(properties) - 1)]["type"]
        comparison_type = "equal"
        # randomly generate comparison value
        # TODO: support value selection from given file
        if type == "STRING":
            str_len = random.randint(0, 20)
            cmp_value = f"{''.join(random.choice(string.ascii_letters) for _ in range(str_len))}'"
        else:
            cmp_value = random.randint(0, 10000)
        return CompareExpression(
            symbolic_name=symbolic_name,
            property=property,
            comparison_type=comparison_type,
            comparison_value=cmp_value,
        )

    def match_return_body(self, item_list: list[tuple[str, str]]) -> ReturnBody:
        return_item_list: list[ReturnItem] = []
        for symbolic_name, label in item_list:
            if "n" in symbolic_name:
                properties = self.node_dict[label].properties
            elif "e" in symbolic_name:
                properties = self.edge_dict[label].properties
            property = properties[random.randint(0, len(properties) - 1)]["name"]
            return_item_list.append(
                ReturnItem(symbolic_name=symbolic_name, property=property, alias=property.upper())
            )
        return ReturnBody(return_item_list=return_item_list, sort_item_list=[])

    def validate(self) -> bool:
        print("validation not implemented.")
        return True
