import random
from http import HTTPStatus
from dashscope import Generation
from llm_process.PreProcess import CorpusPreProcess
from llm_process.Status import Status
import os
from generate_dataset import generate_trainset
import copy


def gen_prompt_directly(
    input_path, output_path
):  # generate multi prompts according to input cypher
    # 1. readt files
    with open(input_path, "r") as file:
        lines = file.readlines()
    db_id = lines[0].strip()
    for i in range(1, len(lines)):
        cypher = lines[i].strip()
        # 2. gen massages
        # massages=[{'role': 'system', 'content': "我希望你帮助我做一些cypher语句的翻译工作，我给你一个cypher语句，你给我对应的中文，下面是两个例子，提问：MATCH (u:user {login: 'Michael'})-[r:rate]->(m:movie) WHERE r.stars < 3 RETURN m.title, r.stars\n回答：Michael讨厌的电影有哪些？\n提问：MATCH (u:user {login: 'Michael'})-[r:rate]->(m:movie) WHERE r.stars < 3 RETURN m.title, r.stars\n\n回答：查找用户Michael评分低于3星的电影，返回电影的标题和评分。之后我将给你一些cypher，请你帮我翻译一下，最好可以翻译成问句\n"},
        massages = [
            {
                "role": "system",

                "content": "我希望你模仿一个图数据库使用者的口吻，将我给你的cypher语句转换为2条表示数据库使用者查询意图的中文表达，每条中文的表达方式应该有差别，可以是陈诉句或者是问句，不需要给我每个步骤的解释，每条表达不需要加粗，不需要额外的提示词，以换行分隔开就行，句子中可以有标点符号，但是尽量不要有空格。这是三个例子，例子1：MATCH (u:user {login: 'Michael'})-[r:rate]->(m:movie) WHERE r.stars < 3 RETURN m.title, r.stars\n怎样查询Michael讨厌的电影？\n例子2：MATCH (u:user {login: 'Michael'})-[r:rate]->(m:movie) WHERE r.stars < 3 RETURN m.title, r.stars\n查找用户Michael评分低于3星的电影，返回电影的标题和评分。\n例子3：MATCH (rachel:Person {name:'Rachel Kempson'})-[]->(family:Person)-[:ACTED_IN]->(film)<-[:ACTED_IN]-(richard:Person {name:'Richard Harris'}) USING JOIN ON film RETURN family.name\n查询在与Rachel Kempson相关的家庭成员中与Richard Harris共同出演过同一部电影的人有哪些？返回该家庭成员的名字。\n下面我将给你一个cypher，请你帮我翻译一下",
            },
            {"role": "user", "content": cypher},
        ]
        # 3. get response
        responses = call_with_messages(massages)
        if responses != "":
            prompts = process_handle.process(responses)
            # 4. save to file
        save2file(db_id, cypher, prompts, output_path)


# deprecated
def general_prompt_directly(
    input_path, output_path
):  # generate multi prompts according to input prompt
    # 1. read file
    with open(input_path, "r") as file:
        lines = file.readlines()
    db_id = lines[0].strip()
    for i in range(1, len(lines), 2):
        cypher = lines[i].strip()
        prompt = lines[i + 1].strip()
        # 2. gen massages
        massages = [
            {
                "role": "system",
                "content": "我希望你模仿一个图数据库使用者的口吻，将我给你的语句进一步泛化，不改变表达的含义，可以修改为问句或者陈述句，这是一个例子：Roy Redgrave的第二代及其所有后代有哪些？可以泛化为：怎么查询Roy Redgrave的所有后代？\n查询Roy Redgrave的所有后代。\n输出Roy Redgrave的所有后代。\nRoy Redgrave的所有后代有哪些？\n查找数据库中名叫Roy Redgrave的人的所有后代。Roy Redgrave有哪些后代？下面我将给你一些句子，请你按顺序为每条语句输出10条泛化的结果，不需要注明是对那条语句进行的泛化，结果直接按照换行符隔开，不要有空格",
            },
            {"role": "user", "content": prompt},
        ]
        # 3. get response
        responses = call_with_messages(massages)
        # 4. postprocess and save
        if responses != "":
            prompts = process_handle.process(responses)
            save2file(db_id, cypher, prompts, output_path)


# recommended
def generalization(
    input_path, output_path
):  # generate multi prompts according to input cypher and prompt
    # 1. read file
    with open(input_path, "r") as file:
        lines = file.readlines()
    db_id = lines[0].strip()
    for i in range(1, len(lines), 2):
        cypher = lines[i].strip()
        prompt = lines[i + 1].strip()
        content = "cypher:" + cypher + ",prompt" + prompt
        # 2. gen massages
        massages = [
            {
                "role": "system",
                "content": "我希望你模仿一个图数据库使用者的口吻，将我给你的prompt语句进一步泛化，不改变prompt表达的含义，并且泛化后的表达要符合我给你的cypher的含义，可以修改为问句或者陈述句，必须是中文，这是一个例子：cypher:MATCH (van:Person {name:'Vanessa Redgrave'})-[:HAS_CHILD*2..]-(n) RETURN n,prompt:Roy Redgrave的第二代及其所有后代有哪些？你应该给我：怎么查询Roy Redgrave的所有后代？\n查询Roy Redgrave的所有后代。\n输出Roy Redgrave的所有后代。\nRoy Redgrave的所有后代有哪些？\n查找数据库中名叫Roy Redgrave的人的所有后代。Roy Redgrave有哪些后代？下面我将给你一些句子，请你按顺序为每条语句输出10条泛化的结果，不需要注明是对那条语句进行的泛化，结果直接按照换行符隔开，不要有空格，使用中文",
            },
            {"role": "user", "content": content},
        ]
        # 3. get response
        responses = call_with_messages(massages)
        # 4. postprocess and save
        if responses != "":
            prompts = process_handle.process(responses)
            save2file(db_id, cypher, prompts, output_path)


def gen_prompt_with_template(input_path, output_path):
    db_id,tmplt_cypher_list,tmplt_prompt_list,cyphers_list=load_file_gen_prompt_with_template(input_path)
    for index, tmplt_cypher in enumerate(tmplt_cypher_list):
        tmplt_prompt=tmplt_prompt_list[index]
        cyphers=cyphers_list[index]
        for cypher_trunk in chunk_list(cyphers):
            cypher_content=''
            for cypher in cypher_trunk:
                cypher_content=cypher_content+cypher+'\n'
            content='template:\n'+tmplt_cypher+','+tmplt_prompt+'cyphers:\n'+cypher_content
            massages = [
                {
                    "role": "system",
                    "content": "设想你是一个图数据库的前端，用户给你一个提问，你要给出对应的cypher语句。现在需要你反过来，将我给你的cypher语句翻译为使用者可能输入的提问，要求符合图数据库使用者的口吻，尽量准确地符合cypher含义，不要遗漏cypher中关键字如DISTINCT、OPTIONAL等，可以修改为问句或者陈述句，必须是中文。我每次会给你一个跟需要翻译的cypher相同句式的template帮助你理解cypher的含义。这是一个例子：\ntempalte:\nMATCH (m:keyword{name: 'news report'})<-[:has_keyword]-(a:movie) RETURN a,m ,关键词是news report的电影有哪些？返回相应的节点。cypher:MATCH (m:movie{title: 'The Dark Knight'})<-[:write]-(a:person) RETURN a,m\nMATCH (m:user{login: 'Sherman'})<-[:is_friend]-(a:user) RETURN a,m\n你应当回答：电影The Dark Knight的作者有哪些？返回相关节点。\n在图中找到登录用户Sheman的朋友节点，返回相关的节点信息。\n下面请你对cyphers逐条cypher语句输出翻译的结果，不需要注明是对哪条语句进行的泛化，结果按照换行符隔开，注意句子应当有标点符号",
                },
                {"role": "user", "content": content},
            ]
            # 3. get response
            responses = call_with_messages(massages)
            # 4. postprocess and save
            if responses != "":
                prompts = process_handle.process(responses)
                save2file_t(db_id, cypher_trunk, prompts, output_path)
    print("corpus have been written into the file:", output_path)


def call_with_messages(messages):
    response = Generation.call(
        model="qwen-plus-0723",
        messages=messages,
        seed=random.randint(1, 10000),
        temperature=0.8,
        top_p=0.8,
        top_k=50,
        result_format="message",
    )
    if response.status_code == HTTPStatus.OK:
        content = response.output.choices[0].message.content
        print(content)
        return content
    else:
        print(
            "Request id: %s, Status code: %s, error code: %s, error message: %s"
            % (
                response.request_id,
                response.status_code,
                response.code,
                response.message,
            )
        )
        print("Failed!", messages[1]["content"])
        return ""

def load_file_gen_prompt_with_template(input_path):
    with open(input_path, "r") as file:
        lines = file.readlines()
    db_id = lines[0].strip()
    index=1
    tmplt_cypher_list=[]
    tmplt_prompt_list=[]
    cyphers_list=[]
    while(len(lines[index:])>3 and lines[index].strip()=='template'):
        tmplt_cypher_list.append(lines[index+1].strip())
        tmplt_prompt_list.append(lines[index+2].strip())
        if lines[index+3].strip()!='cyphers':
            print('[ERROR]: the input file format is not right as the input of GEN_PROMPT_WITH_TEMPLATE')
        cyphers=[]
        index=index+4
        for line in lines[index:]:
            if lines[index].strip()=='END':
                index=index+1
                cyphers_list.append(copy.deepcopy(cyphers))
                break
            index=index+1
            cyphers.append(line.strip())
    return db_id,tmplt_cypher_list,tmplt_prompt_list,cyphers_list
    

def save2file(db_id, cypher, prompts, output_path):
    if not os.path.isfile(output_path):
        with open(output_path, "w", encoding="utf-8") as file:
            file.write(db_id + "\n")
    with open(output_path, "a+", encoding="utf-8") as file:
        for prompt in prompts:
            file.write(cypher + "\n")
            file.write(prompt + "\n")
    print("corpus have been written into the file:", output_path)

def save2file_t(db_id, cyphers, prompts, output_path):
    if not os.path.isfile(output_path):
        with open(output_path, "w", encoding="utf-8") as file:
            file.write(db_id + "\n")
    with open(output_path, "a+", encoding="utf-8") as file:
        for index,prompt in enumerate(prompts):
            file.write(cyphers[index] + "\n")
            file.write(prompt + "\n")
    
def chunk_list(lst, chunk_size=5):
    for i in range(0, len(lst), chunk_size):
        yield lst[i:i + chunk_size]

def state_machine(input_path, output_path):
    if mode == Status.GEN_PROMPT_DIRECTLY.value[0]:
        gen_prompt_directly(input_path, output_path)
    elif mode == Status.GENERAL_PROMPT_DIRECTLY.value[0]:
        general_prompt_directly(input_path, output_path) # deprecated
    elif mode == Status.GENERALIZATION.value[0]:
        generalization(input_path, output_path) # recommended
    elif mode == Status.GEN_PROMPT_WITH_TEMPLATE.value[0]:
        gen_prompt_with_template(input_path, output_path)


def main():
    # 0. parse dir
    if os.path.isfile(input_dir_or_path):
        input_path = input_dir_or_path
        dir, file_name = os.path.split(input_path)
        file_base, file_extension = os.path.splitext(file_name)
        output_path = os.path.join(output_dir, file_base + suffix + ".txt")
        state_machine(input_path, output_path)
    elif os.path.isdir(input_dir_or_path):
        input_dir = input_dir_or_path
        for root, dirs, file_names in os.walk(input_dir):
            for file_name in file_names:
                input_path = os.path.join(root, file_name)
                file_base, file_extension = os.path.splitext(input_path)
                if file_extension != ".txt":
                    break
                file_name = file_base + suffix + file_extension
                output_path = os.path.join(root, file_name).replace(
                    input_dir, output_dir
                )
                state_machine(input_path, output_path)
    else:
        print("[ERROR]: input file is not exsit", input_dir_or_path)


if __name__ == "__main__":
    # input can be a dir or a file_path，if dir, process all the .txt files in batch
    input_dir_or_path = (
        "./test_input.txt"
    )
    output_dir = "./output"
    suffix='_t'
    assert os.path.isdir(output_dir)
    mode = Status.GEN_PROMPT_WITH_TEMPLATE.value[0]
    process_handle = CorpusPreProcess()
    main()

    # generate into json format, pls mak sure the input_corpus_dir_or_path in the config.json is correct!
    # config_path = "config.json"
    # generate_trainset(config_path)
