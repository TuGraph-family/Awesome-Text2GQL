import random
from http import HTTPStatus
from dashscope import Generation
from llm_process.PostProcess import CorpusPostProcess
from llm_process.Status import Status
from base.Config import Config
from generate_dataset import generate_trainset
from tqdm import tqdm
import os
import copy
import sys
from transformers import AutoTokenizer, AutoModelForCausalLM
import transformers
import torch


def gen_question_directly(
    input_path, output_path, tokenizer, model, current_device
):  # generate multi questions according to input cypher
    # 1. readt files
    with open(input_path, "r") as file:
        lines = file.readlines()
    db_id = lines[0].strip()
    for i in tqdm(range(1, len(lines))):
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
        responses = call_with_messages(massages, tokenizer, model, current_device)
        if responses != "":
            questions = process_handler.process(responses)
        # 4. save to file
        save2file(db_id, cypher, questions, output_path)
    print("corpus output file:", output_path)


# deprecated
def general_question_directly(
    input_path, output_path, tokenizer, model, current_device
):  # generate multi questions according to input question
    # 1. read file
    with open(input_path, "r") as file:
        lines = file.readlines()
    db_id = lines[0].strip()
    for i in tqdm(range(1, len(lines), 2)):
        cypher = lines[i].strip()
        question = lines[i + 1].strip()
        # 2. gen massages
        massages = [
            {
                "role": "system",
                "content": "我希望你模仿一个图数据库使用者的口吻，将我给你的语句进一步泛化，不改变表达的含义，可以修改为问句或者陈述句，这是一个例子：Roy Redgrave的第二代及其所有后代有哪些？可以泛化为：怎么查询Roy Redgrave的所有后代？\n查询Roy Redgrave的所有后代。\n输出Roy Redgrave的所有后代。\nRoy Redgrave的所有后代有哪些？\n查找数据库中名叫Roy Redgrave的人的所有后代。Roy Redgrave有哪些后代？下面我将给你一些句子，请你按顺序为每条语句输出10条泛化的结果，不需要注明是对那条语句进行的泛化，结果直接按照换行符隔开，不要有空格",
            },
            {"role": "user", "content": question},
        ]
        # 3. get response
        responses = call_with_messages(massages, tokenizer, model, current_device)
        # 4. postprocess and save
        if responses != "":
            questions = process_handler.process(responses)
            save2file(db_id, cypher, questions, output_path)
    print("corpus output file:", output_path)


# recommended
def generalization(
    input_path, output_path, tokenizer, model, current_device
):  # generate multi questions according to input cypher and question
    # 1. read file
    with open(input_path, "r") as file:
        lines = file.readlines()
    db_id = lines[0].strip()
    for i in tqdm(range(1, len(lines), 2)):
        cypher = lines[i].strip()
        question = lines[i + 1].strip()
        content = "cypher:" + cypher + ",question" + question
        # 2. gen massages
        massages = [
            {
                "role": "system",
                "content": "我希望你模仿一个图数据库使用者的口吻，将我给你的question语句进一步泛化，不改变question表达的含义，并且泛化后的表达要符合我给你的cypher的含义，可以修改为问句或者陈述句，必须是中文，这是一个例子：cypher:MATCH (van:Person {name:'Vanessa Redgrave'})-[:HAS_CHILD*2..]-(n) RETURN n,question:Roy Redgrave的第二代及其所有后代有哪些？你应该给我：怎么查询Roy Redgrave的所有后代？\n查询Roy Redgrave的所有后代。\n输出Roy Redgrave的所有后代。\nRoy Redgrave的所有后代有哪些？\n查找数据库中名叫Roy Redgrave的人的所有后代。Roy Redgrave有哪些后代？下面我将给你一些句子，请你按顺序为每条语句输出10条泛化的结果，不需要注明是对那条语句进行的泛化，结果直接按照换行符隔开，不要有空格，使用中文",
            },
            {"role": "user", "content": content},
        ]
        # 3. get response
        responses = call_with_messages(massages, tokenizer, model, current_device)
        print(responses)
        # 4. postprocess and save
        if responses != "":
            questions = process_handler.process(responses)
            save2file(db_id, cypher, questions, output_path)
    print("corpus output file:", output_path)


def gen_question_with_template(input_path, output_path, tokenizer, model, current_device):
    (
        db_id,
        tmplt_cypher_list,
        tmplt_question_list,
        cyphers_list,
    ) = load_file_gen_question_with_template(input_path)
    for index in tqdm(range(len(tmplt_cypher_list))):
        tmplt_cypher = tmplt_cypher_list[index]
        tmplt_question = tmplt_question_list[index]
        cyphers = cyphers_list[index]
        for cypher_trunk in chunk_list(cyphers):
            cypher_content = ""
            for cypher in cypher_trunk:
                cypher_content = cypher_content + cypher + "\n"
            content = (
                "template:\n"
                + tmplt_cypher
                + ","
                + tmplt_question
                + "cyphers:\n"
                + cypher_content
            )

            messages = [
                {
                    "role": "system",
                    "content": "设想你是一个图数据库的前端，用户给你一个提问，你要给出对应的cypher语句。现在需要你反过来，将我给你的cypher语句翻译为使用者可能输入的提问，要求符合图数据库使用者的口吻，尽量准确地符合cypher含义，不要遗漏cypher中关键字如DISTINCT、OPTIONAL等，可以修改为问句或者陈述句，必须是中文。我每次会给你一个跟需要翻译的cypher相同句式的template帮助你理解cypher的含义。这是一个例子：\ntempalte:\nMATCH (m:keyword{name: 'news report'})<-[:has_keyword]-(a:movie) RETURN a,m ,关键词是news report的电影有哪些？返回相应的节点。cypher:MATCH (m:movie{title: 'The Dark Knight'})<-[:write]-(a:person) RETURN a,m\nMATCH (m:user{login: 'Sherman'})<-[:is_friend]-(a:user) RETURN a,m\n你应当回答：电影The Dark Knight的作者有哪些？返回相关节点。\n在图中找到登录用户Sheman的朋友节点，返回相关的节点信息。\n下面请你对cyphers逐条cypher语句输出翻译的结果，不需要注明是对哪条语句进行的泛化，结果按照换行符隔开，注意句子应当有标点符号",
                },
                {"role": "user", "content": content},
            ]
            
            # 3. get response
            responses = call_with_messages(messages, tokenizer, model, current_device)
            print(responses)
            # 4. postprocess and save
            if responses != "":
                questions = process_handler.process(responses)
                save2file_t(db_id, cypher_trunk, questions, output_path)
    print("output file:", output_path)


def call_with_messages_online(messages):
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
        #print(content)
        return content
    else:
        if response.code == 429:  # Requests rate limit exceeded
            call_with_messages_online(messages)
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

def call_with_messages_local(messages, tokenizer, model, current_device):
    #generate content
    inputs = tokenizer.apply_chat_template(messages, tokenize=True, return_dict=True, return_tensors="pt").to(current_device)
    
    #add more args
    output = model.generate(
        **inputs,
        do_sample=True,
        temperature=0.8,
        top_p=0.8,
        top_k=50,
        pad_token_id=tokenizer.eos_token_id,
        eos_token_id=tokenizer.eos_token_id,
        max_new_tokens = 2048
    )
    
    #deal with output and return
    output = tokenizer.decode(output[0][inputs['input_ids'].shape[1]:], skip_special_tokens=True)
    
    return output

def call_with_messages(messages,tokenizer="", model="", current_device=""):
    if model_path == "":
        output = call_with_messages_online(messages)
    else:
        output = call_with_messages_local(messages, tokenizer, model, current_device)
    return output


def load_file_gen_question_with_template(input_path):
    with open(input_path, "r") as file:
        lines = file.readlines()
    db_id = lines[0].strip()
    if db_id == "template":
        print("[ERROR]: the input file format is not right, pls give schema name!")
    index = 1
    tmplt_cypher_list = []
    tmplt_question_list = []
    cyphers_list = []
    while len(lines[index:]) > 3 and lines[index].strip() == "template":
        tmplt_cypher_list.append(lines[index + 1].strip())
        tmplt_question_list.append(lines[index + 2].strip())
        if lines[index + 3].strip() != "cyphers":
            print(
                "[ERROR]: the input file format is not right as the input of GEN_QUESTION_WITH_TEMPLATE"
            )
        cyphers = []
        index = index + 4
        for line in lines[index:]:
            if lines[index].strip() == "END":
                index = index + 1
                cyphers_list.append(copy.deepcopy(cyphers))
                break
            index = index + 1
            cyphers.append(line.strip())
    return db_id, tmplt_cypher_list, tmplt_question_list, cyphers_list


def save2file(db_id, cypher, questions, output_path):
    if not os.path.isfile(output_path):
        with open(output_path, "w", encoding="utf-8") as file:
            file.write(db_id + "\n")
    with open(output_path, "a+", encoding="utf-8") as file:
        if os.path.getsize(output_path) == 0:
            file.write(db_id + "\n")
        for question in questions:
            file.write(cypher + "\n")
            file.write(question + "\n")
    # print("corpus have been written into the file:", output_path)


def save2file_t(db_id, cyphers, questions, output_path):
    if not os.path.isfile(output_path):
        with open(output_path, "w", encoding="utf-8") as file:
            file.write(db_id + "\n")
    with open(output_path, "a+", encoding="utf-8") as file:
        if os.path.getsize(output_path) == 0:
            file.write(db_id + "\n")
        #for index, question in enumerate(questions):
        #    file.write(cyphers[index] + "\n")
        #    file.write(question + "\n")
        for index,cypher in enumerate(cyphers):
            file.write(cypher + "\n")
            file.write(questions[index] + "\n")


def chunk_list(lst, chunk_size=5):
    for i in range(0, len(lst), chunk_size):
        yield lst[i : i + chunk_size]


def state_machine(input_path, output_path, tokenizer, model, current_device):
    if mode == Status.GEN_QUESTION_DIRECTLY.value[0]:  # 100
        gen_question_directly(input_path, output_path, tokenizer, model, current_device)
    elif mode == Status.GENERAL_QUESTION_DIRECTLY.value[0]:  # 200
        general_question_directly(input_path, output_path, tokenizer, model, current_device)  # deprecated # 300
    elif mode == Status.GENERALIZATION.value[0]:
        generalization(input_path, output_path, tokenizer, model, current_device)  # recommended # 400
    elif mode == Status.GEN_QUESTION_WITH_TEMPLATE.value[0]:
        gen_question_with_template(input_path, output_path, tokenizer, model, current_device)
    else:
        print("[ERROR]: work_mode is not proper, current work_mode is:", mode)


def main():
    # 0. parse dir
    if os.path.isfile(input_dir_or_file):
        input_path = input_dir_or_file
        dir, file_name = os.path.split(input_path)
        file_base, file_extension = os.path.splitext(file_name)
        output_path = os.path.join(output_dir, file_base + suffix + ".txt")

        #load local model 
        if model_path != "":
            #0. check current device
            current_device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
            print("model running on %s"%current_device)
            print("the model path is %s"%model_path) 
    
            #1.load tokenizer
            tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
    
            #2.load model
            model = AutoModelForCausalLM.from_pretrained(model_path, torch_dtype=torch.float16).to(current_device)

            #3.call
            state_machine(input_path, output_path, tokenizer, model, current_device)
        else:
            tokenizer = ""
            model = ""
            current_device = ""
            state_machine(input_path, output_path, tokenizer, model, current_device)

    elif os.path.isdir(input_dir_or_file):
        #load local model
        if model_path != "":
            #0. check current device
            current_device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
            print("model running on %s"%current_device)
            print("the model path is %s"%model_path)

            #1.load tokenizer
            tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)

            #2.load model
            model = AutoModelForCausalLM.from_pretrained(model_path, torch_dtype=torch.float16).to(current_device)

        else:
            tokenizer = ""
            model = ""
            current_device = ""
            state_machine(input_path, output_path, tokenizer, model, current_device)
        
        input_dir = input_dir_or_file
        for root, dirs, file_names in os.walk(input_dir):
            for file_name in file_names:
                input_path = os.path.join(root, file_name)
                file_base, file_extension = os.path.splitext(
                    os.path.basename(input_path)
                )
                if file_extension != ".txt":
                    break
                file_name = file_base + suffix + file_extension
                output_path = os.path.join(root, file_name).replace(
                    input_dir, output_dir
                )
                state_machine(input_path, output_path, tokenizer, model, current_device)
    else:
        print("[ERROR]: input file is not exsit", input_dir_or_file)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        # input can be a dir or a file_path，if dir, process all the .txt files in batch
        mode = int(sys.argv[1])
        input_dir_or_file = sys.argv[2]
        output_dir = sys.argv[3]
        suffix = sys.argv[4]
        model_path = sys.argv[5]
        print(model_path)
        if not os.path.isdir(output_dir):
            print("[ERROR]: output_dir do not exsit!")
            sys.exit()
    else:
        config_path = "config.json"
        config = Config(config_path)
        configs = config.get_config("generalizer")
        mode = int(configs["work_mode"])
        input_dir_or_file = configs["input_dir_or_file"]
        output_dir = configs["output_dir"]
        suffix = configs["suffix"]
        model_path = configs["model_path"]
        if not os.path.isdir(output_dir):
            print("[ERROR]: output_dir do not exsit!")
            sys.exit()
    process_handler = CorpusPostProcess()
    main()

