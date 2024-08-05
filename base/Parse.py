import random
from base.CypherBase import CypherBase

# 一定是跟schema强相关的。暂时只做movie的。
class Node():
    def __init__(self,node_id):
        self.node_id=node_id
        self.variable=''
        self.properties=[]
        self.text_properties={} ## 待定
        self.labels=[] # 每个节点有且只有一个label
        self.desc=''
        self.random_numbers = [random.randint(0, 9) for _ in range(30)]
        self.parse_finised=False
    def addVariable(self,variable):
        self.variable=variable
    def addProperty(self,property):
        self.properties.append(property)
    def addLable(self,lable):
        self.labels.append(lable)
    def addProperties(self,properties,text_properties):
        self.properties+=properties
        self.text_properties.update(text_properties) # 不能有两个相同属性！！
    def addLabels(self,labels):
        self.labels+=labels
    def getDesc(self):
        # self.desc+='节点'
        nodeFlag=False
        if(self.variable!=''):
            pass
            # self.desc=self.variable
        for lable in self.labels:
            if(lable=='movie'): # 有且只有一个label
                self.desc+='电影'
                nodeFlag=True
        for property in self.properties:
            rand=self.random_numbers.pop()
            if(property=='name'):
                if(rand<3):
                    self.desc=self.desc+'姓名为'+self.text_properties['name']
                else:
                    self.desc=self.desc+self.text_properties['name']
            elif(property=='tile'):
                if(rand<3):
                    self.desc=self.desc+'标题是'+self.text_properties['title']
                else:
                    self.desc=self.desc+self.text_properties['title']
            else:
                self.desc+=self.text_properties[property]
            if(rand<3 and nodeFlag==False):
                self.desc+='的节点'+self.variable # 的电影,node 默认的label是节点
        return self.desc
    
class ReturnBody(CypherBase):
    def __init__(self):
        super().__init__()
        self.DISTINCT=False
        self.skip=0
        self.limit=0
        self.orderBy=[] # 元组列表，variable及其label/property
        self.returnItems=[] # 元组列表，元组len=2即Expreesion，len=3即含AS
        self.desc=''
        self.orderDesc=''
        self.returnDesc=''
        self.skipDesc=''
        self.limitDesc=''
        self.random_numbers = [random.randint(0, 9) for _ in range(30)]
        
    def getDesc(self):
        # RETURN n.name, n.age, n.belt ORDER BY n.name
        # 返回这些节点n的name、age和belt属性，同时按照节点的name属性排序。
        # 预制模板
        
        # 逐项翻译:
        assert(len(self.returnItems)!=0)
        # 逐项翻译:
        mergeList=[]
        for item in self.returnItems:
            if(len(item)==3 and item[1]!=0):
                if(self.random_numbers.pop()<5):
                    self.returnDesc='返回'+item[0]+'节点的'+item[1]+'属性值,并将该值重命名为'+item[2]
                else:
                    self.returnDesc='返回节点'+item[0]+'的'+item[1]+'属性值,并将该值重命名为'+item[2]
            elif(len(item)==3 and item[1]==0):
                self.returnDesc='将该节点重命名为'+item[2]
            elif(len(item)==2 and item[1]==0):
                self.returnDesc='返回'+item[0]+'节点'
            else:
                self.returnDesc='返回'+item[0]+'节点的'+item[1]+'属性值'
        mergeList.append(self.returnDesc)
        # orderby
        if(len(self.orderBy)==1 and self.DISTINCT==False):
            if(self.random_numbers.pop()<5):
                self.orderDesc='同时按照节点的'+self.orderBy[0][1]+'属性'+self.getTokenDesc(self.orderBy[0][2])+'排序'
            else:
                self.orderDesc='按照节点的'+self.orderBy[0][1]+'属性'+self.getTokenDesc(self.orderBy[0][2])+'排列返回的结果'
        elif(len(self.orderBy)==2 and self.DISTINCT==False):
            #  ORDER BY n.property1 DESC, n.property2 ASC
            self.orderDesc='返回结果首先按照'+self.orderBy[0][0]+'.'+self.orderBy[0][1]+'的值'+self.getTokenDesc(self.orderBy[0][2])+'排列，然后在'+self.orderBy[0][0]+'.'+self.orderBy[0][1]+'的值相同的情况下，按照'+self.orderBy[1][0]+'.'+self.orderBy[1][1]+'的值'+self.getTokenDesc(self.orderBy[1][2])+'排列'
        else:
            pass #多条sort的情况
        mergeList.append(self.orderDesc)
        
        if(self.skip!=0):
            if(self.skip=='1'):
                self.skipDesc='跳过第一条数据'
            else:
                self.skipDesc='跳过前'+str(self.skip)+'条数据'
            mergeList.append(self.skipDesc)
            
        if(self.limit!=0):
            self.limitDesc='返回'+str(self.limit)+'条数据'
            mergeList.append(self.limitDesc)
        
        self.desc=self.mergeDesc(mergeList)
        if(self.DISTINCT==True):
            self.desc=self.desc+','+self.getTokenDesc('DISTINCT')
        return self.desc