from abc import ABC, abstractmethod
from typing import List

from app.core.clauses.Clause import Clause

class QueryVisitor(ABC):

    @abstractmethod
    def get_query_pattern(self, query: str) -> List[Clause]:
        """Get pattern of the query."""