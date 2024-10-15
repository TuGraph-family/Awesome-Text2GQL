import random
from base.Schema import Schema
from base.Parse import PatternPart
import copy

class Pattern:
    def __init__(self,schema:Schema):
        self.pattern_parts=[]
        self.matched_pattern_parts_label_lists=[]
        # self.instance_matched_pattern_parts_label_lists=[]
        self.variable_label_list_dict={}
        self.schema=schema

    def clean(self):
        self.pattern_parts=[]
        self.matched_pattern_parts_label_lists=[]
        
    def add_pattern_part(self,pattern_part):
        self.pattern_parts.append(pattern_part)
    
    def set_node_dict(self,node_dict): # for with node,todo
        self.variable_label_list_dict=node_dict
    
    def find_variable_index(self,variable):
        variable_list=[]
        for pattern_part in self.pattern_parts:
            variable_list.append(pattern_part.get_chain_variable_list())
        return self.get_pre_matched_variable_index(variable,variable_list)
        
    def __get_matched_pattern_part_label_lists(self,pattern_part:PatternPart):
        # 1. generate all matched path
        label_lists=self.schema.get_matched_pattern_list_three_nodes(pattern_part)
        # 2. Remove duplicates，edge without properties
        if len(label_lists[0])>=3:
            omit_index_list=[]
            for idx in range(1, len(pattern_part.chain_list), 2):
                edge=pattern_part.chain_list[idx]
                if(edge.labels==[] and edge.properties == []):
                    omit_index_list.append(idx)
            if len(omit_index_list) >0:
                label_list_flag=label_lists[0]
                idx=1
                while(idx<len(label_lists)):
                    if not self.if_label_list_same(label_list_flag,label_lists[idx],omit_index_list):
                        label_lists.pop(idx)
                    else:
                        label_list_flag=label_lists[idx]
                        idx+=1
        return label_lists

    def if_label_list_same(self,label_list_flag,label_list,omit_index_list):
        differing_indices = []
        for index, (item1, item2) in enumerate(zip(label_list_flag, label_list)):
            if item1 != item2:
                differing_indices.append(index)
        return differing_indices==omit_index_list
    
    def get_pre_matched_variable_index(self,variable,pre_variable_lists):
        if variable!='':
            for pattern_idx,pre_variable_list in enumerate(pre_variable_lists):
                for node_idx, pre_variable in enumerate(pre_variable_list):
                    if variable==pre_variable:
                        return pattern_idx,node_idx
        return -1,-1

    def gen_matched_pattern_parts_label_lists(self):
        # MATCH (p)-[:ACTED_IN]->(x), (p)-[:MARRIED]->(y), (p)-[:HAS_CHILD]->(z) RETURN p,x,y,z
        variable_lists=[]
        mactched_pattern_parts_label_lists=[]
        for pattern_part_idx, pattern_part in enumerate(self.pattern_parts):
            # 1. find all matched patterns
            cur_pattern_part_label_lists=self.__get_matched_pattern_part_label_lists(pattern_part)
            if len(cur_pattern_part_label_lists)==0:
                print("[WARNING]: No matched pattern find in schema")
                return False
            # 2. find constrained nodes
            variable_list=pattern_part.get_chain_variable_list()
            if pattern_part_idx==0:
                mactched_pattern_parts_label_lists = [[list] for list in cur_pattern_part_label_lists]
                variable_lists.append("")
                variable_lists[-1]=copy.deepcopy(variable_list)
                continue
            matched_variable_dict={}
            for cur_node_idx,variable in enumerate(variable_list):
                pattern_idx,node_idx=self.get_pre_matched_variable_index(variable,variable_lists)
                if pattern_idx!=-1:
                    matched_variable_dict[variable]=(cur_node_idx,pattern_idx,node_idx)
            variable_lists.append("")
            variable_lists[-1]=copy.deepcopy(variable_list)
            # 3. update
            latest_matched_pattern_parts=[]
            for label_list in cur_pattern_part_label_lists:
                for mactched_pattern_parts_label_list in mactched_pattern_parts_label_lists:
                    check_success_flag=True
                    for variable,idxs in matched_variable_dict.items():
                        if label_list[idxs[0]]!=mactched_pattern_parts_label_list[idxs[1]][idxs[2]]:
                            check_success_flag=False
                    if check_success_flag:
                        latest_matched_pattern_parts_label_list=copy.deepcopy(mactched_pattern_parts_label_list)
                        latest_matched_pattern_parts_label_list.append(label_list)
                        latest_matched_pattern_parts.append(latest_matched_pattern_parts_label_list)
            mactched_pattern_parts_label_lists=latest_matched_pattern_parts
        self.matched_pattern_parts_label_lists=mactched_pattern_parts_label_lists
        return True

    def gen_pattern_part(self,parsed_pattern_part,matched_label_list,pattern_part_instance):
        query=''
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
                    node_instance = (
                        self.schema.rm_long_property_of_instance(
                            node_instance
                        )
                    )
                    query = query + "{"
                    size = max(0, min(2, len(node_instance) - 1))
                    rand = random.randint(0, size)
                    property_key = list(node_instance.keys())[rand]
                    property_text = node_instance[property_key]
                    if type(property_text) == str:
                        property_text = f'"{property_text}"'
                    query = (
                        query
                        + property_key
                        + ": "
                        + str(property_text)
                        + "}"
                    )
                query = query + ")"
            if chain_node.type == "edge":
                if chain_node.left_arrow == True:
                    query += "<-["
                else:
                    query += "-["
                if chain_node.variable != "":
                    query = query + chain_node.variable
                if chain_node.labels != []:
                    query = query + ":" + label
                if len(chain_node.properties) != 0:
                    node_instance = (
                        self.schema.rm_long_property_of_instance(
                            node_instance
                        )
                    )
                    query = query + "{"
                    size = min(3, len(node_instance))
                    assert size >= 0
                    rand = random.randint(0, size)
                    property_key = list(node_instance.keys())[rand]
                    property_text = node_instance[property_key]
                    if type(property_text) == str:
                        property_text = f'"{property_text}"'
                    query = (
                        query
                        + property_key
                        + ":"
                        + str(property_text)
                        + "}"
                    )
                if chain_node.right_arrow == True:
                    query += "]->"
                else:
                    query += "]-"
        return query
    
class ReadPattern(Pattern):
    def __init__(self,schema):
        super().__init__(schema)
    
    def if_pattern_need_duplicates(self,pattern_part:PatternPart,compared_pattern_part:PatternPart):
        # pattern are the same, and nodes all have no properties
        need_flag=True
        if len(pattern_part.chain_list)==len(compared_pattern_part.chain_list):
            for node_idx, node in enumerate(compared_pattern_part.chain_list):
                if node.properties!=[] or compared_pattern_part.chain_list[node_idx].properties!=[]:
                    need_flag=False
                    break
                if node.type=='edge':
                    if node.left_arrow !=compared_pattern_part.chain_list[node_idx].left_arrow or node.right_arrow !=compared_pattern_part.chain_list[node_idx].right_arrow:
                        need_flag=False
                        break
        return need_flag
    
    def if_pattern_has_constrained_node(self,pattern_part:PatternPart,compared_pattern_part:PatternPart):
        variable_list=pattern_part.get_chain_variable_list()
        compared_variable_list=compared_pattern_part.get_chain_variable_list()
        for variable in enumerate(variable_list):
            pattern_idx,node_idx=self.get_pre_matched_variable_index(variable,[compared_variable_list])
            if pattern_idx!=-1:
                return True
        return False

    def gen_matched_pattern_parts_label_lists(self):
        if not super().gen_matched_pattern_parts_label_lists():
            return False
        if len(self.pattern_parts)>1:
            for part_idx,pattern_part in enumerate(self.pattern_parts):
                for compared_part_idx in range(part_idx+1,len(self.pattern_parts)):
                    if self.if_pattern_need_duplicates(pattern_part,self.pattern_parts[compared_part_idx]):
                        # duplicates if patternparts are the same
                        idxs_to_rm=[]
                        for list_idx,list in enumerate(self.matched_pattern_parts_label_lists):
                            if list[part_idx]==list[compared_part_idx]:
                                idxs_to_rm.append(list_idx)
                        idxs_to_rm.sort(reverse=True)
                        for index in idxs_to_rm:
                            if index < len(self.matched_pattern_parts_label_lists):
                                self.matched_pattern_parts_label_lists.pop(index)
        if len(self.matched_pattern_parts_label_lists)==0:
            return False
        return True

class UpdatePattern(Pattern):
    def __init__(self,schema):
        super().__init__(schema)
    
    def gen_matched_pattern_parts_label_lists(self):
        if not super().gen_matched_pattern_parts_label_lists():
            return False
        assert(len(self.matched_pattern_parts_label_lists)!=0)
        return True

    def get_matched_pattern_parts_label_lists(self):
        return self.matched_pattern_parts_label_lists

    def gen_pattern_part(self,parsed_pattern_part,matched_label_list,pattern_part_instance):
        query=''
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
                    node_instance = (
                        self.schema.rm_long_property_of_instance(
                            node_instance
                        )
                    )
                    size = max(0, min(2, len(node_instance) - 1))
                    rand = random.randint(0, size)
                    property_keys = random.sample(list(node_instance.keys()),rand+1)
                    if len(property_keys)>0:
                        query = query + "{"
                        for property_key in property_keys:
                            property_text = node_instance[property_key]
                            if type(property_text) == str:
                                property_text = f'"{property_text}"'
                            query = (
                                query
                                + property_key
                                + ": "
                                + str(property_text)
                                + ", "
                            )
                        query=query[:-2]+"}"
                query = query + ")"
            if chain_node.type == "edge":
                if chain_node.left_arrow == True:
                    query += "<-["
                else:
                    query += "-["
                if chain_node.variable != "":
                    query = query + chain_node.variable
                if chain_node.labels != []:
                    query = query + ":" + label
                if len(chain_node.properties) != 0:
                    node_instance = (
                        self.schema.rm_long_property_of_instance(
                            node_instance
                        )
                    )
                    query = query + "{"
                    size = min(3, len(node_instance))
                    assert size >= 0
                    rand = random.randint(0, size)
                    property_key = list(node_instance.keys())[rand]
                    property_text = node_instance[property_key]
                    if type(property_text) == str:
                        property_text = f'"{property_text}"'
                    query = (
                        query
                        + property_key
                        + ":"
                        + str(property_text)
                        + "}"
                    )
                if chain_node.right_arrow == True:
                    query += "]->"
                else:
                    query += "]-"
        return query

class CurrentPattern():
# oC_MultiPartQuery : ( ( oC_ReadingClause SP? )* ( oC_UpdatingClause SP? )* oC_With SP? )+ oC_SinglePartQuery ;
    # MATCH (n:Person {name:'A'}),(m:Person {name:'C'}) WITH n,m MATCH (n)-[r]->(m) DELETE r
    def __init__(self,schema:Schema):
        self.read_pattern=ReadPattern(schema)
        self.update_pattern=UpdatePattern(schema) # todo support multi CREATE clause
        self.with_node_dict={}
        self.cur_parse_type=''
        self.__matched_label_lists=[]
        self.schema=schema
        self.list_idx_to_rm=[]

    def get_read_pattern(self):
        return self.read_pattern
    
    def get_update_pattern(self):
        return self.update_pattern

    def add_pattern_part(self,pattern_part):
        if self.cur_parse_type=='match':
            self.read_pattern.add_pattern_part(pattern_part)
        elif self.cur_parse_type=='update':
            self.update_pattern.add_pattern_part(pattern_part)
        else:
            print('[ERROR]: no valid cur_parse_type')

    def find_variable_index(self,variable):
        # find corordinate of the variable
        part_idx,node_idx=self.read_pattern.find_variable_index(variable)
        if part_idx==-1 and node_idx==-1:
            part_idx,node_idx=self.update_pattern.find_variable_index(variable)
            if part_idx==-1 and node_idx==-1:
                return -1,-1,-1
            return 1,part_idx,node_idx
        return 0,part_idx,node_idx

    def get_matched_label_lists(self,query_list=None):
        if self.__gen_matched_pattern_parts_label_lists():
            if self.list_idx_to_rm!=[] and query_list!=None and query_list!=[]:
                latest_query_lists=[item for index, item in enumerate(query_list) if index not in self.list_idx_to_rm]
                latest_matched_label_lists=[item for index, item in enumerate(self.__matched_label_lists) if index not in self.list_idx_to_rm]
                self.read_pattern.matched_pattern_parts_label_lists=[item for index, item in enumerate(self.read_pattern.matched_pattern_parts_label_lists) if index not in self.list_idx_to_rm]
                self.update_pattern.matched_pattern_parts_label_lists=[item for index, item in enumerate(self.update_pattern.matched_pattern_parts_label_lists) if index not in self.list_idx_to_rm]
                query_list=latest_query_lists
                self.__matched_label_lists=latest_matched_label_lists
                self.list_idx_to_rm=[]
                if len(query_list)==0:
                    return [],[]
            return self.__matched_label_lists,query_list
        else:
            return [],[]

    def __gen_matched_pattern_parts_label_lists(self):
        # self.__matched_label_lists=[[list] for list in self.read_pattern.matched_pattern_parts_label_lists]
        if len(self.read_pattern.matched_pattern_parts_label_lists)==0:
            if self.update_pattern.gen_matched_pattern_parts_label_lists(): # no match
                self.__matched_label_lists=[[[],list] for list in self.update_pattern.matched_pattern_parts_label_lists]
                return True
            return False
        else:
            if len(self.update_pattern.pattern_parts)==0: # no create
                self.__matched_label_lists=[[list] for list in self.read_pattern.matched_pattern_parts_label_lists]
                return True
            elif len(self.update_pattern.pattern_parts[0].chain_list)==1: # create a vertex
                # MATCH (a {name:'Passerby A'}) CREATE (:Person {name:'Passerby E', birthyear:a.birthyear})
                # todo: deal with the constraints, support the template above
                if self.update_pattern.gen_matched_pattern_parts_label_lists():
                    self.__matched_label_lists = [[a, b] for a, b in zip(self.read_pattern.matched_pattern_parts_label_lists,self.update_pattern.matched_pattern_parts_label_lists)]
                    return True
                return False
            else: # create an edge, will not change the matched_lists size
                # 1. find label_list
                update_part_matched_label_lists=[]
                for pattern_part in self.update_pattern.pattern_parts:
                    left_node_variable=pattern_part.chain_list[0].variable
                    right_node_variable=pattern_part.chain_list[2].variable
                    part_idx_of_left,node_idx_of_left=self.read_pattern.find_variable_index(left_node_variable)
                    part_idx_of_right,node_idx_of_right=self.read_pattern.find_variable_index(right_node_variable)
                    update_matched_label_list=[]
                    for list_idx,read_label_list in enumerate(self.read_pattern.matched_pattern_parts_label_lists):
                        left_label=read_label_list[part_idx_of_left][node_idx_of_left]
                        right_label=read_label_list[part_idx_of_right][node_idx_of_right]
                        update_matched_label_lists=self.schema.get_matched_pattern_list_create_edge(pattern_part,left_label,right_label)
                        if len(update_matched_label_lists)==0:
                            self.list_idx_to_rm.append(list_idx)
                            update_matched_label_list.append([])
                            continue
                        update_matched_label=random.choice(update_matched_label_lists)
                        update_matched_label_list.append(update_matched_label)
                    update_part_matched_label_lists.append(copy.deepcopy(update_matched_label_list))
                # 2. update label_list
                assert(self.update_pattern.matched_pattern_parts_label_lists==[])
                for list_idx,read_label_list in enumerate(self.read_pattern.matched_pattern_parts_label_lists):
                    update_label_list=[]
                    for update_part_label_list in update_part_matched_label_lists: # pattern_part
                        update_label_list.append(copy.deepcopy(update_part_label_list[list_idx]))
                    self.__matched_label_lists.append([read_label_list,update_label_list])
                    self.update_pattern.matched_pattern_parts_label_lists.append(update_label_list)
        return True

    # todo
    def add_with_node(self, variable,label_list):
        self.with_node_dict[variable]=label_list

    def update_read_pattern(self, read_pattern,with_node_dict):
        self.read_pattern=read_pattern
        self.read_pattern.set_node_dict(with_node_dict)

    def clean(self):
        self.read_pattern.clean()
        self.update_pattern.clean()
        self.with_node_dict={}
