from dataclasses import dataclass
from typing import Dict, List


@dataclass
class Node:
    label: str
    properties: List[Dict[str, str]]
