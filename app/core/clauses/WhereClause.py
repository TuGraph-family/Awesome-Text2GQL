from dataclasses import dataclass
from typing import Dict
from app.core.clauses.Clause import Clause

@dataclass
class CompareExpression:
    symbolic_name: str
    property: tuple[str, Dict]
    comparison_type: str
    comparison_value: str

class WhereClause(Clause):
    def __init__(self, compare_expression: CompareExpression):
        self.compare_expression = compare_expression
    
    def to_string(self) -> str:
        where_string = f"WHERE {self.compare_expression.symbolic_name}.{self.compare_expression.property["name"]}"
        if self.compare_expression.comparison_type == "equal":
            where_string += f" = "
        elif self.compare_expression.comparison_type == "neq":
            where_string += f" <> "
        elif self.compare_expression.comparison_type == "less":
            where_string += f" < "
        elif self.compare_expression.comparison_type == "greater":
            where_string += f" > "
        elif self.compare_expression.comparison_type == "leq":
            where_string += f" <= "
        elif self.compare_expression.comparison_type == "geq":
            where_string += f" >= "
        
        where_string += f"{self.compare_expression.comparison_value}"
        return where_string
    
    def to_string_gql(self) -> str:
        where_string = "WHERE"
        where_string += f" {self.compare_expression.symbolic_name}"
        if self.compare_expression.property != "":
            where_string += f".{self.compare_expression.property}"
        if self.compare_expression.comparison_type == "equal":
            where_string += f" = "
        elif self.compare_expression.comparison_type == "neq":
            where_string += f" <> "
        elif self.compare_expression.comparison_type == "less":
            where_string += f" < "
        elif self.compare_expression.comparison_type == "greater":
            where_string += f" > "
        elif self.compare_expression.comparison_type == "leq":
            where_string += f" <= "
        elif self.compare_expression.comparison_type == "geq":
            where_string += f" >= "
        
        where_string += f"{self.compare_expression.comparison_value}"
        return where_string