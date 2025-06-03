from typing import Dict, List, Tuple
from dataclasses import dataclass
from app.core.clauses.clause import Clause
from app.core.clauses.return_clause import ReturnBody
from app.core.clauses.where_clause import CompareExpression


class WithClause(Clause):
    def __init__(
        self, return_body: ReturnBody, where_expression: CompareExpression, distinct: bool
    ):
        self.return_body: ReturnBody = return_body
        self.where_expression = where_expression
        self.distinct = distinct

    def to_string(self) -> str:
        with_string = "WITH "
        for return_item in self.return_body.return_item_list:
            with_string += f" {return_item.symbolic_name}.{return_item.property}"
            if return_item.alias != "":
                with_string += f" AS {return_item.alias}"
            with_string += ","

        return with_string.strip(",")

    def to_string_cypher(self) -> str:
        with_string = "WITH "
        for return_item in self.return_body.return_item_list:
            with_string += f" {return_item.symbolic_name}.{return_item.property}"
            if return_item.alias != "":
                with_string += f" AS {return_item.alias}"
            with_string += ","

        return with_string.strip(",")

    def to_string_gql(self) -> str:
        with_string = "RETURN"
        if self.distinct:
            with_string += " DISTINCT"
        # add return items
        for return_item in self.return_body.return_item_list:
            item_string = f"{return_item.symbolic_name}"
            if return_item.property != "":
                item_string += f".{return_item.property}"
            if return_item.function_name != "":
                item_string = f"{return_item.function_name}({item_string})"
            if return_item.alias != "":
                item_string += f" AS {return_item.alias}"
            with_string += f" {item_string},"
        with_string = with_string.strip(",")
        # add order list
        if len(self.return_body.sort_item_list) != 0:
            with_string += " ORDER BY"
            for sort_item in self.return_body.sort_item_list:
                item_string = f"{sort_item.symbolic_name}"
                if sort_item.property != "":
                    item_string += f".{sort_item.property}"
                if sort_item.function_name != "":
                    item_string = f"{sort_item.function_name}({item_string})"
                if sort_item.order != "":
                    item_string += f" {sort_item.order}"
                with_string += f" {item_string},"
            with_string = with_string.strip(",")
        # add skip
        if self.return_body.skip != -1:
            with_string += f" SKIP {self.return_body.skip}"
        # add limit
        if self.return_body.limit != -1:
            with_string += f" LIMIT {self.return_body.limit}"
        with_string += " NEXT"

        return with_string
