import json
from base.Schema import Schema

def main(input_path,output_path,db_id,schema_path):
    schema=Schema(db_id,schema_path)
    schemaDesc=schema.genDesc()
    instruction_beginning="我希望你像一个Tugraph数据库前端一样工作，你只需要返回给我cypher语句。下面是一条描述任务的指令，写一条正确的response来完成这个请求.\n\"\n##Instruction:\n"
    instruction_end="\n\n"
    instruction=instruction_beginning+schemaDesc+instruction_end
    dataSize=0
    with open(input_path, 'r') as file:
        dataSize = sum(1 for line in file)/2

    dataList= [{
        "db_id": db_id,
        "instruction":instruction,
        "input": '',
        "output": '',
        "history": []
    } for i in range(int(dataSize))]
    
    with open(input_path, 'rb') as file:
        for i, line in enumerate(file, start=1):
            line=line.strip()
            if (i%2==0):
                data_temp={'input':str(line.decode('utf-8'))}
                dataList[int(i/2-1)].update(data_temp)
            else:
                data_temp={'output':line.decode('utf-8')}
                dataList[int(i/2-1)].update(data_temp)
    json_data = json.dumps(dataList, ensure_ascii=False,indent=4)
    with open(output_path, 'w') as file:
        file.write(json_data)
    print("JSON数据已写入文件。")
    
if __name__=='__main__':
    input_path='/root/work_repo/Awesome-Text2GQL/data/raw_query.txt'
    output_path='/root/work_repo/Awesome-Text2GQL/data/text2gql_train.json'
    db_id='movie'
    schema_path='Awesome-Text2GQL/data/schema/movie_schema.json'
    main(input_path,output_path,db_id,schema_path)