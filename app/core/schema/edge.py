from dataclasses import dataclass
from typing import Dict, List, Tuple

@dataclass
class Edge:

    label: str
    properties: List[Dict[str, str]]
    src_dst_list: list[Tuple[str, str]]