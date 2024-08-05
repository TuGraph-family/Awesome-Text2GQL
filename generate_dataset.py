import json

def main(input_path,output_path,db_id):
    # 定义三个值
    value2 = ''
    value3 = ''

    #     {
    #         "db_id": "department_management",
    #         "instruction": "I want you to act as a SQL terminal in front of an example database, you need only to return the sql command to me.Below is an instruction that describes a task, Write a response that appropriately completes the request.\n\"\n##Instruction:\ndepartment_management contains tables such as department, head, management. Table department has columns such as Department_ID, Name, Creation, Ranking, Budget_in_Billions, Num_Employees. Department_ID is the primary key.\nTable head has columns such as head_ID, name, born_state, age. head_ID is the primary key.\nTable management has columns such as department_ID, head_ID, temporary_acting. department_ID is the primary key.\nThe head_ID of management is the foreign key of head_ID of head.\nThe department_ID of management is the foreign key of Department_ID of department.\n\n",
    #         "input": "###Input:\nHow many heads of the departments are older than 56 ?\n\n###Response:",
    #         "output": "SELECT count(*) FROM head WHERE age  >  56",
    #         "history": []
    #     },
    
    dataSize=0
    with open(input_path, 'r') as file:
        dataSize = sum(1 for line in file)/2
        
    dataList= [{
        "db_id": db_id,
        "instruction": value2,
        "input": value3,
        "output": value3,
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
    db_id=''
    main(input_path,output_path,db_id)
