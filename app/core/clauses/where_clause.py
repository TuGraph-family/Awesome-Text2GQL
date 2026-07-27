from dataclasses import dataclass
from typing import Dict, List

from app.core.clauses.clause import Clause


@dataclass
class CompareExpression:
    symbolic_name: str
    property: tuple[str, Dict]
    comparison_type: str
    comparison_value: str
    raw_expression: str = ""


class WhereClause(Clause):
    def __init__(self, compare_expression_list: List[CompareExpression]):
        self.compare_expression_list = compare_expression_list

    def to_string(self) -> str:
        where_string = (
            f"WHERE {self.compare_expression_list.symbolic_name}"
            + f".{self.compare_expression_list.property['name']}"
        )
        if self.compare_expression_list.comparison_type == "equal":
            where_string += " = "
        elif self.compare_expression_list.comparison_type == "neq":
            where_string += " <> "
        elif self.compare_expression_list.comparison_type == "less":
            where_string += " < "
        elif self.compare_expression_list.comparison_type == "greater":
            where_string += " > "
        elif self.compare_expression_list.comparison_type == "leq":
            where_string += " <= "
        elif self.compare_expression_list.comparison_type == "geq":
            where_string += " >= "

        where_string += f"{self.compare_expression_list.comparison_value}"
        return where_string

    def to_string_gql(self) -> str:
        where_string = "WHERE"
        where_string += f" {self.compare_expression_list.symbolic_name}"
        if self.compare_expression_list.property != "":
            where_string += f".{self.compare_expression_list.property}"
        if self.compare_expression_list.comparison_type == "equal":
            where_string += " = "
        elif self.compare_expression_list.comparison_type == "neq":
            where_string += " <> "
        elif self.compare_expression_list.comparison_type == "less":
            where_string += " < "
        elif self.compare_expression_list.comparison_type == "greater":
            where_string += " > "
        elif self.compare_expression_list.comparison_type == "leq":
            where_string += " <= "
        elif self.compare_expression_list.comparison_type == "geq":
            where_string += " >= "

        where_string += f"{self.compare_expression_list.comparison_value}"
        return where_string
