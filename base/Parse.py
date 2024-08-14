import random
from base.CypherBase import CypherBase
from base.Config import Config

class Node():
    # Vertex Instance
    def __init__(self,node_id,cypherBase:CypherBase):
        self.node_id=node_id
        self.variable=''
        self.properties=[]
        self.text_properties={} ## 待定
        self.labels=[] # 每个节点有且只有一个label
        self.desc=''
        self.type='node'
        # self.random_numbers = [random.randint(0, 9) for _ in range(30)]
        self.parse_finised=False
        self.cypherBase=cypherBase
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
        # 1. (p:plan {name: "面壁计划"})
        if(len(self.labels)==1 and len(self.properties)==1):
            labelDesc=self.cypherBase.getSchemaDesc(self.labels[0])
            propertyDesc=self.cypherBase.getSchemaDesc(self.properties[0])
            rand=random.random()
            if rand<0.2:
                self.desc=labelDesc+propertyDesc+'为'+self.text_properties[self.properties[0]]+'的节点'+self.variable
            elif rand>0.2 and rand<0.4:
                self.desc=self.text_properties[self.properties[0]]
            elif rand> 0.4 and rand<0.6:
                self.desc=propertyDesc+'为'+self.text_properties[self.properties[0]]+'的'+labelDesc
            else:
                self.desc=labelDesc+'节点'+self.variable+self.text_properties[self.properties[0]]
        elif(len(self.labels)==1 and len(self.properties)==0):
            labelDesc=self.cypherBase.getSchemaDesc(self.labels[0])
            self.desc=labelDesc+'节点'+self.variable
        elif(len(self.labels)==0 and len(self.properties)==0):
            self.desc='节点'+self.variable
        return self.desc

class EdgeInstance():
    def __init__(self):
        # self.node_id=node_id
        self.variable='' 
        self.properties=[]
        self.text_properties={} # 直接用一个字典不就行了？
        self.labels=[]
        self.leftNode=''
        self.rightNode=''
        self.leftArrow=False
        self.rightArrow=False
        self.desc=''
        self.type='edge'
        self.range=['0','0']
        self.parse_finised=False
    def addVariable(self,variable):
        self.variable=variable
    def addProperty(self,property):
        self.properties.append(property)
    def addLable(self,lable):
        self.labels.append(lable)
    def addProperties(self,properties,text_properties):
        self.properties+=properties
        self.text_properties.update(text_properties)
    def addLabels(self,labels):
        self.labels+=labels
    def addLeftNode(self,left):
        self.leftNode=left
    def addRightNode(self,right):
        self.rightNode=right

class PatternChain():
    def __init__(self,cypherBase:CypherBase):
        # self.chainDict={}
        self.variable=''
        self.chainList=[]
        self.desc=''
        self.random_numbers = [random.randint(0, 9) for _ in range(30)]
        self.cypherBase=cypherBase
        self.matchType=0
        self.parse_finised=False
    
    def clean(self):
        self.chainList=[]
        self.desc=''
        self.matchType=0
        self.parse_finised=False
        
    def addNode(self,node:Node):
        # self.chainDict[node.variable]=node
        self.chainList.append(node)
    def addEdge(self,edge:EdgeInstance):
        # self.chainDict[edge.variable]=edge
        self.chainList.append(edge)
    def addItem(self,item):
        # item：variable,property,text_property
        for chainNode in self.chainList:
            if chainNode.variable==item[0]:
                propertyText=item[2]
                propertyDict={}
                propertyDict[item[1]]=propertyText
                chainNode.addProperties([item[1]],propertyDict)

    def patternMatch(self):
        if(len(self.chainList)==3):
            if(len(self.chainList[0].labels)==0 and len(self.chainList[1].labels)==1 and len(self.chainList[2].labels)==0):
                # MATCH (n)-[e:person_person]-(m) RETURN n,e,m 查询
                self.matchType=1
            elif(len(self.chainList[0].properties)!=0 and len(self.chainList[1].labels)==0 and len(self.chainList[2].labels)==1):
                if(self.chainList[1].type=='edge' and self.chainList[1].leftArrow==False and self.chainList[1].rightArrow==False):
                    # MATCH (p:plan {name: "面壁计划"})-[e]-(neighbor:person) RETURN neighbor,p,e # 与面壁计划有关的人有哪些？
                    self.matchType=2
                elif(self.chainList[1].type=='edge' and self.chainList[1].leftArrow==True):
                    # MATCH (m:movie {title: 'Forrest Gump'})<-[:acted_in]-(a:person) RETURN a, m  # 参演了Forrest Gump电影的演员有哪些？
                    self.matchType=3
                else:
                    self.matchType=0
            elif(len(self.chainList[0].properties)!=0 and len(self.chainList[1].properties)!=0 and len(self.chainList[2].labels)==1):
                # # MATCH (u:user {login: 'Michael'})-[r:rate]->(m:movie) WHERE r.stars < 3 RETURN m.title, r.stars
                self.matchType=4
        return self.matchType
        
    def getDesc(self,returnGen=False):
        matchType=self.patternMatch()
        if(matchType==1):
            # MATCH (n)-[e:person_person]-(m) RETURN n,e,m 查询
            if returnGen:
                if(self.random_numbers.pop()<5):
                    self.desc='返回图中所有通过'+self.chainList[1].labels[0]+'关系相连的节点和关系。'
                else:
                    self.desc='所有通过'+self.chainList[1].labels[0]+'类型关系连接的节点对'+self.chainList[0]+'和'+self.chainList[2]+'，并返回这些节点对以及它们之间的person_person关系。'
            else:
                self.desc='所有通过'+self.chainList[1].labels[0]+'类型关系连接的节点对'+self.chainList[0]+'和'+self.chainList[2]
        elif(matchType==2):
            # MATCH (p:plan {name: "面壁计划"})-[e]-(neighbor:person) RETURN neighbor,p,e # 与面壁计划有关的人有哪些？
            nodeDesc=self.chainList[0].getDesc()
            self.desc='与'+nodeDesc+'有关的'+self.cypherBase.getSchemaDesc(self.chainList[2].labels[0])+'有哪些'
        elif(matchType==3):
            # MATCH (m:movie {title: 'Forrest Gump'})<-[:acted_in]-(a:person) RETURN a, m  # 参演了Forrest Gump电影的演员有哪些？
            nodeDesc=self.chainList[0].getDesc()
            self.desc=self.cypherBase.getSchemaDesc(self.chainList[1].labels[0])+nodeDesc+'的'+self.cypherBase.getSchemaDesc(self.chainList[2].labels[0])+'有哪些'
        elif(matchType==4):
            # MATCH (u:user {login: 'Michael'})-[r:rate]->(m:movie) WHERE r.stars < 3 RETURN m.title, r.stars
            return "pattern Match failed"
        else:
            return "pattern Match failed"
        return self.desc
        # MATCH (a:person {name: "叶文洁"})-[e1:person_person]->(n)<-[e2:person_person]-(b:person {name: "汪淼"}) RETURN a,b,n,e1,e2
        # 查询叶文洁和汪淼这两个人之间的的共同关联的人物都有谁。
        # 查询与叶文洁关联的人物有关的人物，返回子图。

class ReturnBody():
    def __init__(self,cypherBase:CypherBase,config:Config):
        self.cypherBase=cypherBase
        self.config=config
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
        self.matchType=0
    
    def patternMatch(self,patternChainList):
        matchSuccess=True
        if(len(patternChainList)==1):
            # type 1
            patternChain=patternChainList[0]
            if(len(patternChain.chainList)==len(self.returnItems)):
                for index,item in enumerate(self.returnItems):
                    if (len(item)==2 and item[0]==patternChain.chainList[index].variable and item[1]==0):
                        continue
                    else:
                        matchSuccess=False
                        break
            else:
                matchSuccess=False
            if(matchSuccess):
                self.returnDesc='返回子图'
                
            # type 2 待完善
            # RETURN n.name, n.age, n.belt ORDER BY n.name
            # 返回这些节点n的name、age和belt属性，同时按照节点的name属性排序。
        elif(len(patternChainList)==2):
            # 待完善MATCH (n:person), (m:movie)
            matchSuccess=False
        else:
            matchSuccess=False
        return matchSuccess
        
    def getDesc(self,patternChainList):
        mergeList=[]
        assert(len(self.returnItems)!=0)
        # 模板1，返回子图
        # self.returnDesc=self.patternMatch(matchPattern)
        if(self.patternMatch(patternChainList)==False):
            # 逐项翻译:
            returnDescList=[]
            self.returnDesc='返回'
            for item in self.returnItems:
                if(len(item)==3 and item[1]!=0):
                    if(self.random_numbers.pop()<5):
                        returnDescList.append(item[0]+'节点的'+item[1]+'属性值,并将该值重命名为'+item[2])
                    else:
                        returnDescList.append('节点'+item[0]+'的'+item[1]+'属性值,并将该值重命名为'+item[2])
                elif(len(item)==3 and item[1]==0):
                    returnDescList.append('将该节点重命名为'+item[2])
                elif(len(item)==2 and item[1]==0):
                    returnDescList.append(item[0]+'节点')
                else:
                    returnDescList.append(item[0]+'节点的'+item[1]+'属性值')
            self.returnDesc+=self.cypherBase.mergeDesc(returnDescList)
        mergeList.append(self.returnDesc)
        
        # orderby
        if(len(self.orderBy)==1 and self.DISTINCT==False):
            if(self.random_numbers.pop()<5):
                self.orderDesc='同时按照节点的'+self.orderBy[0][1]+'属性'+self.cypherBase.getTokenDesc(self.orderBy[0][2])+'排序'
            else:
                self.orderDesc='按照节点的'+self.orderBy[0][1]+'属性'+self.cypherBase.getTokenDesc(self.orderBy[0][2])+'排列返回的结果'
        elif(len(self.orderBy)==2 and self.DISTINCT==False):
            #  ORDER BY n.property1 DESC, n.property2 ASC
            self.orderDesc='返回结果首先按照'+self.orderBy[0][0]+'.'+self.orderBy[0][1]+'的值'+self.cypherBase.getTokenDesc(self.orderBy[0][2])+'排列，然后在'+self.orderBy[0][0]+'.'+self.orderBy[0][1]+'的值相同的情况下，按照'+self.orderBy[1][0]+'.'+self.orderBy[1][1]+'的值'+self.cypherBase.getTokenDesc(self.orderBy[1][2])+'排列'
        else:
            pass #多条sort的情况
            # 待完善
        mergeList.append(self.orderDesc)
        
        if(self.skip!=0 and self.limit!=0):
            desc='保留去除前'+str(self.skip)+'条数据后的'+str(self.limit)+'条数据'
            mergeList.append(desc)
        else:
            if(self.skip!=0):
                if(self.skip=='1'):
                    self.skipDesc='跳过第一条数据'
                else:
                    self.skipDesc='跳过前'+str(self.skip)+'条数据'
                mergeList.append(self.skipDesc)
            if(self.limit!=0):
                if(self.random_numbers.pop()<5):
                    self.limitDesc='返回'+str(self.limit)+'条数据'
                else:
                    self.limitDesc='保留前'+str(self.limit)+'条数据'
                mergeList.append(self.limitDesc)
        
        self.desc=self.cypherBase.mergeDesc(mergeList)
        if(self.DISTINCT==True):
            self.desc=self.desc+','+self.cypherBase.getTokenDesc('DISTINCT')
        return self.desc

class Where():
    def __init__(self,whereExpr):
        self.whereExpr=whereExpr
        self.desc=''