from abc import ABC, abstractmethod


class Clause(ABC):
    @abstractmethod
    def to_string(self) -> str:
        """format a clause to string."""
