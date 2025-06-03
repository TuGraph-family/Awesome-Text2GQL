from abc import ABC, abstractmethod

from app.core.schema.schema_graph import SchemaGraph


class SchemaParser(ABC):
    @abstractmethod
    def __init__(self, name: str):
        """Init SchemaParser."""

    @abstractmethod
    def get_schema_graph(self) -> SchemaGraph:
        """get schema graph after parsing schema."""
