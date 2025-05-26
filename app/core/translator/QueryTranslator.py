from abc import ABC, abstractmethod
from typing import List

from app.core.clauses.Clause import Clause

class QueryTranslator(ABC):

    @abstractmethod
    def translate(query_pattern: List[Clause]) -> str:
        """translate query pattern into corresponding query."""