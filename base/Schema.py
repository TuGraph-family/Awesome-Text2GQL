import json

class Vertex():
    def __init__(self) -> None:
        self.label=''
        self.properties=[]
        self.srcEdge=[] # 节点作为源节点的相关边
        self.dstEdge=[] # 节点作为目标节点的相关边

class Edge():
    def __init__(self) -> None:
        self.label=''
        self.properties=[]
        self.src=''
        self.dst=''

class Schema():
    def __init__(self, dbId, filePath):
        self.vertexDict={}
        self.edgeDict={}
        self.dbId=dbId
        self.filePath=filePath
        self.parseFinished=False
        self.parseSchema()
        
    def parseSchema(self):
        try:
            with open(self.filePath, 'r') as file:
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

if __name__ == '__main__':
    schema=Schema('movie','Awesome-Text2GQL/data/schema/movie_schema.json')
    print(schema.genDesc())