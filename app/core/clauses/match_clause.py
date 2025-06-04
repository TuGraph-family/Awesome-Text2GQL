from dataclasses import dataclass
from typing import List, Tuple

from app.core.clauses.clause import Clause


@dataclass
class NodePattern:
    symbolic_name: str
    label: str
    property_maps: List[Tuple[str, str]]


@dataclass
class EdgePattern:
    symbolic_name: str
    label: str
    property_maps: List[Tuple[str, str]]
    direction: str
    hop_range: tuple[int, int] = (-1, -1)


@dataclass
class PathPattern:
    node_pattern_list: List[NodePattern]
    edge_pattern_list: List[EdgePattern]


class MatchClause(Clause):
    def __init__(self, path_pattern: PathPattern):
        self.path_pattern = path_pattern

    def to_string(self) -> str:
        match_string = "MATCH "
        path_degree = len(self.path_pattern.edge_pattern_list)
        # add first node
        node_pattern = self.path_pattern.node_pattern_list[0]
        match_string += f"({node_pattern.symbolic_name}:{node_pattern.label})"
        for i in range(path_degree):
            # add edge
            edge_pattern = self.path_pattern.edge_pattern_list[i]
            if edge_pattern.direction == "right":
                match_string += f"-[{edge_pattern.symbolic_name}:{edge_pattern.label}]->"
            elif edge_pattern.direction == "left":
                match_string += f"<-[{edge_pattern.symbolic_name}:{edge_pattern.label}]-"
            elif edge_pattern.direction == "bidirection":
                match_string += f"-[{edge_pattern.symbolic_name}:{edge_pattern.label}]-"
            # add node
            node_pattern = self.path_pattern.node_pattern_list[i + 1]
            match_string += f"({node_pattern.symbolic_name}:{node_pattern.label})"
        return match_string

    def to_string_cypher(self) -> str:
        match_string = "MATCH "
        path_degree = len(self.path_pattern.edge_pattern_list)
        # add first node
        node_pattern = self.path_pattern.node_pattern_list[0]
        match_string += f"({node_pattern.symbolic_name}:{node_pattern.label})"
        for i in range(path_degree):
            # add edge
            edge_pattern = self.path_pattern.edge_pattern_list[i]
            egde_string = f"{edge_pattern.symbolic_name}:{edge_pattern.label}"
            hop_range = edge_pattern.hop_range
            if hop_range != (-1, -1):
                if hop_range[0] == hop_range[1]:
                    egde_string += f"*{hop_range[1]}"
                if hop_range[0] == -1:
                    egde_string += f"*..{hop_range[1]}"
                elif hop_range[1] == -1:
                    egde_string += f"*{hop_range[0]}.."
                else:
                    egde_string += f"*{hop_range[0]}..{hop_range[1]}"
            edge_string = "-[" + egde_string + "]-"
            if edge_pattern.direction == "right":
                edge_string += ">"
            elif edge_pattern.direction == "left":
                edge_string = "<" + edge_string
            match_string += edge_string
            # add node
            node_pattern = self.path_pattern.node_pattern_list[i + 1]
            match_string += f"({node_pattern.symbolic_name}:{node_pattern.label})"
        return match_string

    def to_string_gql(self) -> str:
        match_string = "MATCH "
        path_degree = len(self.path_pattern.edge_pattern_list)
        # add first node
        node_pattern = self.path_pattern.node_pattern_list[0]
        if node_pattern.symbolic_name:
            if node_pattern.label != "":
                property_maps_str = ""
                if len(node_pattern.property_maps) != 0:
                    for map in node_pattern.property_maps:
                        property_maps_str += f"{map[0]}:{map[1]},"
                    property_maps_str = f"{{{property_maps_str.strip(',')}}}"
                match_string += (
                    f"({node_pattern.symbolic_name}:{node_pattern.label}{property_maps_str})"
                )
            else:
                match_string += f"({node_pattern.symbolic_name})"
        else:
            if node_pattern.label != "":
                match_string += f"(:{node_pattern.label})"
            else:
                match_string += "()"
        for i in range(path_degree):
            # add edge
            edge_pattern = self.path_pattern.edge_pattern_list[i]
            edge_string = ""
            if edge_pattern.symbolic_name:
                if edge_pattern.label:
                    edge_string = f"{edge_pattern.symbolic_name}:{edge_pattern.label}"
                    property_maps_str = ""
                    if len(edge_pattern.property_maps) != 0:
                        for map in edge_pattern.property_maps:
                            property_maps_str += f"{map[0]}:{map[1]},"
                        property_maps_str = f"{{{property_maps_str.strip(',')}}}"
                    match_string += (
                        f"({edge_pattern.symbolic_name}:{edge_pattern.label}{property_maps_str})"
                    )
                else:
                    edge_string = f"{edge_pattern.symbolic_name}"
            else:
                if edge_pattern.label:
                    edge_string = f":{edge_pattern.label}"
            hop_range = edge_pattern.hop_range
            edge_string = "-[" + edge_string + "]-"
            if edge_pattern.direction == "right":
                edge_string += ">"
            elif edge_pattern.direction == "left":
                edge_string = "<" + edge_string
            if hop_range != (-1, -1):
                if hop_range[0] == -1:
                    edge_string += f"{{1,{hop_range[1]}}}"
                elif hop_range[1] == -1:
                    edge_string += f"{{{hop_range[0]},}}"
                else:
                    edge_string += f"{{{hop_range[0]},{hop_range[1]}}}"
            match_string += edge_string
            # add node
            node_pattern = self.path_pattern.node_pattern_list[i + 1]
            if node_pattern.symbolic_name:
                if node_pattern.label != "":
                    property_maps_str = ""
                    if len(node_pattern.property_maps) != 0:
                        for map in node_pattern.property_maps:
                            property_maps_str += f"{map[0]}:{map[1]},"
                        property_maps_str = f"{{{property_maps_str.strip(',')}}}"
                    match_string += (
                        f"({node_pattern.symbolic_name}:{node_pattern.label}{property_maps_str})"
                    )
                else:
                    match_string += f"({node_pattern.symbolic_name})"
            else:
                if node_pattern.label != "":
                    match_string += f"(:{node_pattern.label})"
                else:
                    match_string += "()"
        return match_string
