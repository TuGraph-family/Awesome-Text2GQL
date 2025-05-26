from typing import List
from dataclasses import dataclass
from app.core.clauses.Clause import Clause

@dataclass
class ReturnItem:

    symbolic_name: str
    property: str
    alias: str
    function_name: str = ""

@dataclass
class SortItem:

    symbolic_name: str
    property: str
    order: str
    function_name: str = ""

@dataclass
class ReturnBody:

    return_item_list: List[ReturnItem]
    sort_item_list: List[SortItem]
    skip: int = -1
    limit: int = -1

class ReturnClause(Clause):
    def __init__(self, return_body: ReturnBody, distinct: bool = False):
        self.return_body: ReturnBody = return_body
        self.distinct = distinct
    
    def to_string(self) -> str:
        return_string = f"RETURN"
        # add return items
        for return_item in self.return_body.return_item_list:
            item_string += f"{return_item.symbolic_name}"
            if return_item.property != "":
                item_string += f".{return_item.property}"
            if return_item.function_name != "":
                item_string = f"{return_item.function_name}({item_string})"
            if return_item.alias != "":
                item_string += f" AS {return_item.alias}"
            return_string += f" {item_string},"
        return_string = return_string.strip(",")
        # add order list
        if len(self.return_body.sort_item_list) != 0:
            return_string += " ORDER BY" 
            for sort_item in self.return_body.sort_item_list:
                item_string += f"{sort_item.symbolic_name}"
                if sort_item.property != "":
                    item_string += f".{sort_item.property}"
                if sort_item.function_name != "":
                    item_string = f"{sort_item.function_name}({item_string})"
                if sort_item.order != "":
                    item_string += f" {sort_item.order}"
                retun_string += f" {item_string},"
                # if sort_item.property != "":
                #     return_string += f".{sort_item.property}"
                # if sort_item.order != "":
                #     return_string += f" {sort_item.order}"
                # return_string += ","
            return_string = return_string.strip(",")
        # add skip
        if self.return_body.skip != -1:
            return_string += f" SKIP {self.return_body.skip}"
        # add limit
        if self.return_body.limit != -1:
            return_string += f" LIMIT {self.return_body.limit}"

        return return_string

    def to_string_gql(self) -> str:
        return_string = f"RETURN"
        if self.distinct:
            return_string += " DISTINCT"
        # add return items
        for return_item in self.return_body.return_item_list:
            item_string = f"{return_item.symbolic_name}"
            if return_item.property != "":
                item_string += f".{return_item.property}"
            if return_item.function_name != "":
                item_string = f"{return_item.function_name}({item_string})"
            if return_item.alias != "":
                item_string += f" AS {return_item.alias}"
            return_string += f" {item_string},"
        return_string = return_string.strip(",")
        # add order list
        if len(self.return_body.sort_item_list) != 0:
            return_string += " ORDER BY" 
            for sort_item in self.return_body.sort_item_list:
                item_string = f"{sort_item.symbolic_name}"
                if sort_item.property != "":
                    item_string += f".{sort_item.property}"
                if sort_item.function_name != "":
                    item_string = f"{sort_item.function_name}({item_string})"
                if sort_item.order != "":
                    item_string += f" {sort_item.order}"
                return_string += f" {item_string},"
            return_string = return_string.strip(",")
        # add skip
        if self.return_body.skip != -1:
            return_string += f" SKIP {self.return_body.skip}"
        # add limit
        if self.return_body.limit != -1:
            return_string += f" LIMIT {self.return_body.limit}"

        return return_string