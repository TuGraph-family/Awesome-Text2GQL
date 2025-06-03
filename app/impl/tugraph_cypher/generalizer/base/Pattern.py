import copy
import random

from app.impl.tugraph_cypher.generalizer.base.Parse import PatternPart
from app.impl.tugraph_cypher.generalizer.base.Schema import Schema


class Pattern:
    def __init__(self, schema: Schema):
        self.pattern_parts = []
        self.matched_pattern_parts_label_lists = []
        # self.instance_matched_pattern_parts_label_lists=[]
        self.variable_label_list_dict = {}
        self.schema = schema

    def clean(self):
        self.pattern_parts = []
        self.matched_pattern_parts_label_lists = []

    def add_pattern_part(self, pattern_part):
        self.pattern_parts.append(pattern_part)

    def set_node_dict(self, node_dict):  # for with node,todo
        self.variable_label_list_dict = node_dict

    def find_variable_index(self, variable):
        variable_list = []
        for pattern_part in self.pattern_parts:
            variable_list.append(pattern_part.get_chain_variable_list())
        return self.get_pre_matched_variable_index(variable, variable_list)

    def __get_matched_pattern_part_label_lists(self, pattern_part: PatternPart):
        # 1. generate all matched path
        label_lists = self.schema.get_matched_pattern_list(pattern_part)
        if label_lists == []:
            return []
        # 2. Remove duplicates，edge without properties
        if len(label_lists[0]) >= 3:
            omit_index_list = []
            for idx in range(1, len(pattern_part.chain_list), 2):
                edge = pattern_part.chain_list[idx]
                if edge.labels == [] and edge.properties == []:
                    omit_index_list.append(idx)
            if len(omit_index_list) > 0:
                no_duplicates = [label_lists[0]]
                for label_list in label_lists[1:]:
                    same_flag = False
                    for compared_label_list in no_duplicates:
                        same_flag = self.if_label_list_same(
                            compared_label_list, label_list, omit_index_list
                        )
                        if same_flag:
                            break
                    if not same_flag:
                        no_duplicates.append(label_list)
                label_lists = no_duplicates
        return label_lists

    def if_label_list_same(self, label_list_flag, label_list, omit_index_list):
        differing_indices = []
        for index, (item1, item2) in enumerate(zip(label_list_flag, label_list, strict=False)):
            if item1 != item2:
                differing_indices.append(index)
        return differing_indices == omit_index_list

    def get_pre_matched_variable_index(self, variable, pre_variable_lists):
        if variable != "":
            for pattern_idx, pre_variable_list in enumerate(pre_variable_lists):
                for node_idx, pre_variable in enumerate(pre_variable_list):
                    if variable == pre_variable:
                        return pattern_idx, node_idx
        return -1, -1

    def gen_matched_pattern_parts_label_lists(self):
        # MATCH (p)-[:ACTED_IN]->(x), (p)-[:MARRIED]->(y), (p)-[:HAS_CHILD]->(z) RETURN p,x,y,z
        variable_lists = []
        mactched_pattern_parts_label_lists = []
        for pattern_part_idx, pattern_part in enumerate(self.pattern_parts):
            # 1. find all matched patterns
            cur_pattern_part_label_lists = self.__get_matched_pattern_part_label_lists(pattern_part)
            if len(cur_pattern_part_label_lists) == 0:
                print("[WARNING]: No matched pattern find in schema")
                return False
            # 2. find constrained nodes
            variable_list = pattern_part.get_chain_variable_list()
            if pattern_part_idx == 0:
                mactched_pattern_parts_label_lists = [
                    [list] for list in cur_pattern_part_label_lists
                ]
                variable_lists.append("")
                variable_lists[-1] = copy.deepcopy(variable_list)
                continue
            matched_variable_dict = {}
            for cur_node_idx, variable in enumerate(variable_list):
                pattern_idx, node_idx = self.get_pre_matched_variable_index(
                    variable, variable_lists
                )
                if pattern_idx != -1:
                    matched_variable_dict[variable] = (
                        cur_node_idx,
                        pattern_idx,
                        node_idx,
                    )
            variable_lists.append("")
            variable_lists[-1] = copy.deepcopy(variable_list)
            # 3. update
            latest_matched_pattern_parts = []
            for label_list in cur_pattern_part_label_lists:
                for mactched_pattern_parts_label_list in mactched_pattern_parts_label_lists:
                    check_success_flag = True
                    for _, idxs in matched_variable_dict.items():
                        if (
                            label_list[idxs[0]]
                            != mactched_pattern_parts_label_list[idxs[1]][idxs[2]]
                        ):
                            check_success_flag = False
                    if check_success_flag:
                        latest_matched_pattern_parts_label_list = copy.deepcopy(
                            mactched_pattern_parts_label_list
                        )
                        latest_matched_pattern_parts_label_list.append(label_list)
                        latest_matched_pattern_parts.append(latest_matched_pattern_parts_label_list)
            mactched_pattern_parts_label_lists = latest_matched_pattern_parts
        self.matched_pattern_parts_label_lists = mactched_pattern_parts_label_lists
        return True

    def gen_pattern_part(self, parsed_pattern_part, matched_label_list, pattern_part_instance):
        query = ""
        if parsed_pattern_part.variable != "":
            query = query + parsed_pattern_part.variable + " = "
        for i in range(len(parsed_pattern_part.chain_list)):
            label = matched_label_list[i]
            chain_node = parsed_pattern_part.chain_list[i]
            node_instance = pattern_part_instance[i]
            if chain_node.type == "node":
                query = query + "("
                if chain_node.variable != "":
                    query = query + chain_node.variable
                if chain_node.labels != []:
                    query = query + ":" + label
                if len(chain_node.properties) != 0:
                    node_instance = self.schema.rm_long_property_of_instance(node_instance)
                    if len(node_instance) != 0:
                        query = query + "{"
                        size = max(0, min(2, len(node_instance) - 1))
                        rand = random.randint(0, size)
                        property_key = list(node_instance.keys())[rand]
                        property_text = node_instance[property_key]
                        if type(property_text) is str:
                            property_text = f'"{property_text}"'
                        query = query + property_key + ": " + str(property_text) + "}"
                query = query + ")"
            if chain_node.type == "edge":
                if chain_node.left_arrow:
                    query += "<-["
                else:
                    query += "-["
                if chain_node.variable != "":
                    query = query + chain_node.variable
                if chain_node.labels != []:
                    query = query + ":" + label
                if len(chain_node.properties) != 0:
                    node_instance = self.schema.rm_long_property_of_instance(node_instance)
                    query = query + "{"
                    size = min(3, len(node_instance))
                    assert size >= 0
                    rand = random.randint(0, size)
                    property_key = list(node_instance.keys())[rand]
                    property_text = node_instance[property_key]
                    if type(property_text) is str:
                        property_text = f'"{property_text}"'
                    query = query + property_key + ":" + str(property_text) + "}"
                if chain_node.right_arrow is True:
                    query += "]->"
                else:
                    query += "]-"
        return query


class ReadPattern(Pattern):
    def __init__(self, schema):
        super().__init__(schema)

    def if_pattern_need_duplicates(
        self, pattern_part: PatternPart, compared_pattern_part: PatternPart
    ):
        # pattern_part are the same, and nodes all have no properties
        need_flag = True
        if len(pattern_part.chain_list) == len(compared_pattern_part.chain_list):
            for node_idx, node in enumerate(compared_pattern_part.chain_list):
                if (
                    node.properties != []
                    or compared_pattern_part.chain_list[node_idx].properties != []
                ):
                    need_flag = False
                    break
                if node.type == "edge":
                    if (
                        node.left_arrow != compared_pattern_part.chain_list[node_idx].left_arrow
                        or node.right_arrow
                        != compared_pattern_part.chain_list[node_idx].right_arrow
                    ):
                        need_flag = False
                        break
        return need_flag

    def if_pattern_has_constrained_node(
        self, pattern_part: PatternPart, compared_pattern_part: PatternPart
    ):
        variable_list = pattern_part.get_chain_variable_list()
        compared_variable_list = compared_pattern_part.get_chain_variable_list()
        for variable in enumerate(variable_list):
            pattern_idx, node_idx = self.get_pre_matched_variable_index(
                variable, [compared_variable_list]
            )
            if pattern_idx != -1:
                return True
        return False

    def gen_matched_pattern_parts_label_lists(self):
        if not super().gen_matched_pattern_parts_label_lists():
            return False
        if len(self.pattern_parts) > 1:
            for part_idx, pattern_part in enumerate(self.pattern_parts):
                for compared_part_idx in range(part_idx + 1, len(self.pattern_parts)):
                    if self.if_pattern_need_duplicates(
                        pattern_part, self.pattern_parts[compared_part_idx]
                    ):
                        # duplicates if patternparts are the same
                        idxs_to_rm = []
                        for list_idx, list in enumerate(self.matched_pattern_parts_label_lists):
                            if list[part_idx] == list[compared_part_idx]:
                                idxs_to_rm.append(list_idx)
                        idxs_to_rm.sort(reverse=True)
                        for index in idxs_to_rm:
                            if index < len(self.matched_pattern_parts_label_lists):
                                self.matched_pattern_parts_label_lists.pop(index)
        if len(self.matched_pattern_parts_label_lists) == 0:
            return False
        return True


class UpdatePattern(Pattern):
    def __init__(self, schema):
        super().__init__(schema)

    def gen_matched_pattern_parts_label_lists(self):
        if not super().gen_matched_pattern_parts_label_lists():
            return False
        assert len(self.matched_pattern_parts_label_lists) != 0
        return True

    def get_matched_pattern_parts_label_lists(self):
        return self.matched_pattern_parts_label_lists

    def gen_pattern_part(self, parsed_pattern_part, matched_label_list, pattern_part_instance):
        query = ""
        if matched_label_list == []:
            return ""
        if parsed_pattern_part.variable != "":
            query = query + parsed_pattern_part.variable + "="
        for i in range(len(parsed_pattern_part.chain_list)):
            label = matched_label_list[i]
            chain_node = parsed_pattern_part.chain_list[i]
            node_instance = pattern_part_instance[i]
            if chain_node.type == "node":
                query = query + "("
                if chain_node.variable != "":
                    query = query + chain_node.variable
                if chain_node.labels != []:
                    query = query + ":" + label
                if len(chain_node.properties) != 0:
                    node_instance = self.schema.get_create_instance(label, node_instance)
                    property_keys = list(node_instance.keys())
                    if len(property_keys) > 0:
                        query = query + "{"
                        for property_key in property_keys:
                            property_text = node_instance[property_key]
                            if type(property_text) is str:
                                property_text = f'"{property_text}"'
                            query = query + property_key + ": " + str(property_text) + ", "
                        query = query[:-2] + "}"
                query = query + ")"
            if chain_node.type == "edge":
                if chain_node.left_arrow is True:
                    query += "<-["
                else:
                    query += "-["
                if chain_node.variable != "":
                    query = query + chain_node.variable
                if chain_node.labels != []:
                    query = query + ":" + label
                if len(chain_node.properties) != 0:
                    node_instance = self.schema.get_create_instance(label, node_instance)
                    property_keys = list(node_instance.keys())
                    if len(property_keys) > 0:
                        query = query + "{"
                        for property_key in property_keys:
                            property_text = node_instance[property_key]
                            if type(property_text) is str:
                                property_text = f'"{property_text}"'
                            query = query + property_key + ": " + str(property_text) + ", "
                        query = query[:-2] + "}"
                if chain_node.right_arrow:
                    query += "]->"
                else:
                    query += "]-"
        return query


class CurrentPattern:
    def __init__(self, schema: Schema):
        self.read_pattern = ReadPattern(schema)
        self.cur_update_pattern = UpdatePattern(schema)
        self.update_patterns = []
        self.with_node_dict = {}
        self.cur_parse_type = ""
        self.__matched_label_lists = []
        self.schema = schema
        self.list_idx_to_rm = []
        self.if_extend_list = False

    def set_cur_parse_type(self, type):
        self.cur_parse_type = type

    def get_read_pattern(self):
        return self.read_pattern

    def get_update_pattern(self, pattern_idx=None):
        assert self.update_patterns != []
        if pattern_idx is None:
            return self.update_patterns[-1]
        self.update_patterns[pattern_idx - 1]

    def get_cur_update_pattern(self):
        return self.cur_update_pattern

    def add_update_pattern(self):
        self.update_patterns.append(copy.deepcopy(self.cur_update_pattern))
        self.cur_update_pattern.clean()

    def add_pattern_part(self, pattern_part):
        if self.cur_parse_type == "match":
            self.read_pattern.add_pattern_part(pattern_part)
        elif self.cur_parse_type == "create" or self.cur_parse_type == "merge":
            self.cur_update_pattern.add_pattern_part(pattern_part)
        else:
            print("[ERROR]: no valid cur_parse_type")

    def find_variable_index(self, variable):
        # find corordinate of the variable
        part_idx, node_idx = self.read_pattern.find_variable_index(variable)
        pattern_idx = 0
        while part_idx == -1 and node_idx == -1 and pattern_idx < len(self.update_patterns):
            part_idx, node_idx = self.update_patterns[pattern_idx].find_variable_index(variable)
            pattern_idx += 1
            if part_idx != -1 and node_idx != -1:
                return pattern_idx, part_idx, node_idx
        if part_idx == -1 and node_idx == -1:
            return -1, -1, -1
        return 0, part_idx, node_idx

    def get_label_by_idxs(self, list_idx, pattern_idx, part_idx, node_idx):
        if pattern_idx != -1 and part_idx != -1 and node_idx != -1:
            return self.__matched_label_lists[list_idx][pattern_idx][part_idx][node_idx]
        return ""

    def rm_query_by_index(self, list_idx_to_rm, query_list):
        latest_query_lists = [
            item for index, item in enumerate(query_list) if index not in list_idx_to_rm
        ]
        latest_matched_label_lists = [
            item
            for index, item in enumerate(self.__matched_label_lists)
            if index not in list_idx_to_rm
        ]
        self.read_pattern.matched_pattern_parts_label_lists = [
            item
            for index, item in enumerate(self.read_pattern.matched_pattern_parts_label_lists)
            if index not in list_idx_to_rm
        ]
        for update_pattern in self.update_patterns:
            update_pattern.matched_pattern_parts_label_lists = [
                item
                for index, item in enumerate(update_pattern.matched_pattern_parts_label_lists)
                if index not in list_idx_to_rm
            ]
        self.cur_update_pattern.matched_pattern_parts_label_lists = [
            item
            for index, item in enumerate(self.cur_update_pattern.matched_pattern_parts_label_lists)
            if index not in list_idx_to_rm
        ]
        query_list = latest_query_lists
        self.__matched_label_lists = latest_matched_label_lists
        self.list_idx_to_rm = []
        if len(query_list) == 0:
            return [], []
        return self.__matched_label_lists, query_list

    def get_matched_label_lists(self, query_list=None):
        if (
            self.cur_parse_type == ""
            or self.cur_parse_type == "where"
            or self.cur_parse_type == "set"
        ):
            return self.__matched_label_lists, query_list
        if (
            self.__gen_matched_pattern_parts_label_lists()
        ):  # find if the matched_label_lists need to been changed
            if (
                self.list_idx_to_rm != [] and query_list is not None and query_list != []
            ):  # delete not match
                return self.rm_query_by_index(self.list_idx_to_rm, query_list)
            if (
                self.if_extend_list and query_list is not None
            ):  # extend, if no match pattern or other situations
                multiplier = len(self.__matched_label_lists) / len(query_list)
                query_list = [element for _ in range(int(multiplier)) for element in query_list]
                self.read_pattern.matched_pattern_parts_label_lists = [
                    element
                    for _ in range(int(multiplier))
                    for element in self.read_pattern.matched_pattern_parts_label_lists
                ]
                for update_pattern in self.update_patterns:
                    update_pattern.matched_pattern_parts_label_lists = [
                        element
                        for _ in range(int(multiplier))
                        for element in update_pattern.matched_pattern_parts_label_lists
                    ]
                self.cur_update_pattern.matched_pattern_parts_label_lists = [
                    element
                    for element in self.cur_update_pattern.matched_pattern_parts_label_lists
                    for _ in range(int(multiplier))
                ]
                self.if_extend_list = False
            return self.__matched_label_lists, query_list
            # todo control the max size
        else:
            return [], []

    def __gen_matched_pattern_parts_label_lists(self):
        if self.cur_parse_type == "match":  # macth
            self.read_pattern.gen_matched_pattern_parts_label_lists()
            self.__matched_label_lists = [
                [list] for list in self.read_pattern.matched_pattern_parts_label_lists
            ]
            return True
        else:  # create or merge
            # no match, the first create or merge
            if (
                len(self.read_pattern.matched_pattern_parts_label_lists) == 0
                and self.__matched_label_lists == []
            ):
                if self.cur_update_pattern.gen_matched_pattern_parts_label_lists():
                    self.__matched_label_lists = [
                        [[], list]
                        for list in self.cur_update_pattern.matched_pattern_parts_label_lists
                    ]
                    return True
                return False
            elif len(self.cur_update_pattern.pattern_parts[0].chain_list) == 1:  # create a vertex
                # todo: deal with the constraints, support the template above
                if len(self.__matched_label_lists) < 10:
                    self.if_extend_list = True
                if self.if_extend_list:
                    if self.cur_update_pattern.gen_matched_pattern_parts_label_lists():
                        latest_matched_label_lists = []
                        for (
                            update_label_list
                        ) in self.cur_update_pattern.matched_pattern_parts_label_lists:
                            for pre_label_list in self.__matched_label_lists:
                                temp_label_list = copy.deepcopy(pre_label_list)
                                temp_label_list.append(update_label_list)
                                latest_matched_label_lists.append(copy.deepcopy(temp_label_list))
                        self.__matched_label_lists = latest_matched_label_lists
                        return True
                else:
                    if self.cur_update_pattern.gen_matched_pattern_parts_label_lists():
                        for list_idx, pre_label_list in enumerate(self.__matched_label_lists):
                            pre_label_list.append(
                                random.choice(
                                    self.cur_update_pattern.matched_pattern_parts_label_lists
                                )
                            )
                            self.__matched_label_lists[list_idx] = copy.deepcopy(pre_label_list)
                        return True
                return False
            else:  # create an edge, will not change the matched_lists size
                # 1. find label_list
                cur_update_parts_matched_label_lists = []
                for pattern_part in self.cur_update_pattern.pattern_parts:
                    left_node_variable = pattern_part.chain_list[0].variable
                    right_node_variable = pattern_part.chain_list[2].variable
                    (
                        pattern_idx_of_left,
                        part_idx_of_left,
                        node_idx_of_left,
                    ) = self.find_variable_index(left_node_variable)
                    (
                        pattern_idx_of_right,
                        part_idx_of_right,
                        node_idx_of_right,
                    ) = self.find_variable_index(right_node_variable)
                    update_matched_label_list = []
                    for list_idx in range(len(self.__matched_label_lists)):
                        left_label = self.get_label_by_idxs(
                            list_idx,
                            pattern_idx_of_left,
                            part_idx_of_left,
                            node_idx_of_left,
                        )
                        right_label = self.get_label_by_idxs(
                            list_idx,
                            pattern_idx_of_right,
                            part_idx_of_right,
                            node_idx_of_right,
                        )
                        update_matched_label_lists = (
                            self.schema.get_matched_pattern_list_create_edge(
                                pattern_part, left_label, right_label
                            )
                        )
                        if len(update_matched_label_lists) == 0:
                            self.list_idx_to_rm.append(list_idx)
                            update_matched_label_list.append([])
                            continue
                        update_matched_label = random.choice(
                            update_matched_label_lists
                        )  # no extend
                        update_matched_label_list.append(update_matched_label)
                    cur_update_parts_matched_label_lists.append(
                        copy.deepcopy(update_matched_label_list)
                    )
                # 2. update label_list
                assert self.cur_update_pattern.matched_pattern_parts_label_lists == []
                for list_idx in range(len(self.__matched_label_lists)):
                    pattern_lable_list = []
                    for (
                        cur_update_part_matched_label_lists
                    ) in cur_update_parts_matched_label_lists:  # pattern_part
                        pattern_lable_list.append(cur_update_part_matched_label_lists[list_idx])
                    self.cur_update_pattern.matched_pattern_parts_label_lists.append(
                        pattern_lable_list
                    )
                    self.__matched_label_lists[list_idx].append(pattern_lable_list)
        return True

    # todo
    def add_with_node(self, variable, label_list):
        self.with_node_dict[variable] = label_list

    def update_read_pattern(self, read_pattern, with_node_dict):
        self.read_pattern = read_pattern
        self.read_pattern.set_node_dict(with_node_dict)

    def clean(self):
        self.read_pattern.clean()
        self.cur_update_pattern.clean()
        self.update_patterns = []
        self.with_node_dict = {}
