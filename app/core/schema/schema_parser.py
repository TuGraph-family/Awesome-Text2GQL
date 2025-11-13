from abc import ABC, abstractmethod

from app.core.schema.schema_graph import SchemaGraph


class SchemaParser(ABC):
    @abstractmethod
    def __init__(self, name: str):
        """Init SchemaParser."""

    @abstractmethod
    def get_schema_graph(self) -> SchemaGraph:
        """get schema graph after parsing schema."""

    @abstractmethod
    def save_schema_to_file(
        self, output_dir, schema_graph: SchemaGraph, domain: str, subdomain: str
    ):
        """serialize schema graph to target schema file format."""
