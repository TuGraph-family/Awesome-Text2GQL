from abc import ABC, abstractmethod
from typing import List, Tuple

from app.core.clauses.clause import Clause


class AstVisitor(ABC):
    @abstractmethod
    def get_query_pattern(self, query: str) -> Tuple[bool, List[Clause]]:
        """Get pattern of the query."""
