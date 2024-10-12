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
        label_lists=self.schema.get_matched_pattern_list(pattern_part)
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

    def get_matched_pattern_parts_label_lists(self):
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

    def get_matched_pattern_parts_label_lists(self):              
        if not super().get_matched_pattern_parts_label_lists():
            return False
        if len(self.pattern_parts)>1:
            for part_idx,pattern_part in enumerate(self.pattern_parts):
                for compared_part_idx in range(part_idx+1,len(self.pattern_parts)):
                    if self.if_pattern_need_duplicates(pattern_part,self.pattern_parts[compared_part_idx]):
                        # duplicates
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
    
    def get_matched_pattern_parts_label_lists(self):
        if not super().get_matched_pattern_parts_label_lists():
            return False
        if len(self.matched_pattern_parts_label_lists)==0:
            return False
        return True

class CurrentPattern():
# oC_MultiPartQuery : ( ( oC_ReadingClause SP? )* ( oC_UpdatingClause SP? )* oC_With SP? )+ oC_SinglePartQuery ;
    # MATCH (n:Person {name:'A'}),(m:Person {name:'C'}) WITH n,m MATCH (n)-[r]->(m) DELETE r
    def __init__(self,schema:Schema):
        self.read_pattern=ReadPattern(schema)
        self.update_pattern=UpdatePattern(schema)
        self.with_node_dict={}
        self.cur_parse_type=''
        self.__matched_pattern_parts_label_lists=[]

    def get_read_pattern(self):
        return self.read_pattern
    
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
    
    def get_matched_pattern_parts_label_lists(self):
        # todo,只考虑了match字句，没有考虑update
        self.__matched_pattern_parts_label_lists=[[list] for list in self.read_pattern.matched_pattern_parts_label_lists]
        return self.__matched_pattern_parts_label_lists
        
    # def get_label_by_index(self,index):
    #     pass

    # def get_label_by_variable(self,variable):
    #     pass

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
