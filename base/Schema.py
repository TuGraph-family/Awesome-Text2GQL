import json
import os
import csv
import random

class Vertex():
    def __init__(self) -> None:
        self.label=''
        self.properties=[]
        self.srcEdge=[] # 节点作为源节点的相关边
        self.dstEdge=[] # 节点作为目标节点的相关边
        self.filePath=''

class Edge():
    def __init__(self) -> None:
        self.label=''
        self.properties=[]
        self.src=''
        self.dst=''
        self.filePath=''

class Schema():
    def __init__(self, dbId, schemaPath):
        self.vertexDict={}
        self.edgeDict={}
        self.dbId=dbId
        self.schemaPath=schemaPath
        self.dirPath=os.path.dirname(os.path.dirname(os.path.abspath(schemaPath))) #上上级文件夹
        self.parseFinished=False
        self.parseSchema()

    def parseSchema(self):
        try:
            with open(self.schemaPath, 'r') as file:
                data = json.load(file)
                self.parseSchemaImpl(data)
        except FileNotFoundError:
            print("schema文件未找到")
            
    def parseSchemaImpl(self,json):
        schema = json['schema']
        for item in schema:
            if item['type']=='VERTEX':
                vertex=Vertex()
                vertex.label=item['label']
                for property in item['properties']:
                    vertex.properties.append(property['name'])
                self.vertexDict[vertex.label]=vertex
            elif item['type']=='EDGE':
                edge=Edge()
                edge.label=item['label']
                if 'properties' in item:
                    for property in item['properties']:
                        edge.properties.append(property['name'])         
                self.edgeDict[edge.label]=edge
        
        vertex_path=json['files']
        for item in vertex_path:
            if item['label'] in self.edgeDict:
                edgeName=item['label']
                edge=self.edgeDict[item['label']]
                edge.src=item['SRC_ID']
                edge.dst=item['DST_ID']
                self.vertexDict[edge.src].srcEdge.append(edgeName)
                self.vertexDict[edge.dst].dstEdge.append(edgeName)
                edge.filePath=os.path.join(self.dirPath, item['path'])
            if item['label'] in self.vertexDict:
                self.vertexDict[item['label']].filePath=os.path.join(self.dirPath, item['path'])
        self.parseFinished=True

    def genDesc(self):
        if self.parseFinished:
            desc=self.dbId+'包含节点'
            for vertex in self.vertexDict:
                desc=desc+vertex+'、'
            desc=desc[:-1]
            desc+='和边'
            for edge in self.edgeDict:
                desc=desc+edge+'、'
            desc=desc[:-1]
            desc+='。'
            for vertex in self.vertexDict:
                desc=desc+'节点'+vertex+'有属性'
                for property in self.vertexDict[vertex].properties:
                    desc=desc+property+'、'
                desc=desc[:-1]
                desc+='。'
            for edge in self.edgeDict:
                if self.edgeDict[edge].properties!=[]:
                    desc=desc+'边'+edge+'有属性'
                    for property in self.edgeDict[edge].properties:
                        desc=desc+property+'、'
                    desc=desc[:-1]
                    desc+='。'
            return desc
        return ''
    
    def getItemFromDb(self,vertexOrEdge,count):
        filePath=''
        if vertexOrEdge in self.vertexDict:
            filePath=self.vertexDict[vertexOrEdge].filePath
        elif vertexOrEdge in self.edgeDict:
            filePath=self.edgeDict[vertexOrEdge].filePath
        else:
            print("[ERROR]: vertexOrEdge is not exist")
            return
        if os.path.exists(filePath):
            keywordList=[]
            vertexOrEdgeInstanceList=[]
        with open(filePath, newline='') as csvfile:
            reader = list(csv.reader(csvfile))
            second_row = reader[1]
            for item in second_row:
                itemList=item.split(':')
                keywordList.append(itemList[0])
                # 获取第3行到末尾行的数据
            data_from_third_row = reader[2:]
            count=min(count,len(data_from_third_row))
            random_rows = random.sample(data_from_third_row, count)
            for row in random_rows:
                vertexOrEdgeInstance={}
                for index, item in enumerate(row):
                    keyword=keywordList[index]
                    vertexOrEdgeInstance[keyword]=item
                vertexOrEdgeInstanceList.append(vertexOrEdgeInstance)
            

if __name__ == '__main__':
    schema=Schema('movie','Awesome-Text2GQL/data/schema/movie_schema.json')
    print(schema.getItemFromDb('person',10))