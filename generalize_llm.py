import random
from http import HTTPStatus
from dashscope import Generation
from llm_process.PreProcess import CorpusPreProcess
from llm_process.Status import Status
import os
from generate_dataset import generate_trainset


def gen_prompt_directly(
    input_path, output_path
):  # generate multi prompts according to input cypher
    # 1. readt files
    with open(input_path, "rb") as file:
        for line in file:
            cypher = line.strip().decode("utf-8")
            # 2. gen massages
            # massages=[{'role': 'system', 'content': "我希望你帮助我做一些cypher语句的翻译工作，我给你一个cypher语句，你给我对应的中文，下面是两个例子，提问：MATCH (u:user {login: 'Michael'})-[r:rate]->(m:movie) WHERE r.stars < 3 RETURN m.title, r.stars\n回答：Michael讨厌的电影有哪些？\n提问：MATCH (u:user {login: 'Michael'})-[r:rate]->(m:movie) WHERE r.stars < 3 RETURN m.title, r.stars\n\n回答：查找用户Michael评分低于3星的电影，返回电影的标题和评分。之后我将给你一些cypher，请你帮我翻译一下，最好可以翻译成问句\n"},
            massages = [
                {
                    "role": "system",
                    "content": "我希望你帮助我提取cypher语句的实际含义和查询意图，我给你一个cypher语句，你应该给我5条表达查询意图的中文表达，每条中文的表达方式应该有差别，可以是陈诉句或者是问句，不需要给我每个步骤的解释，每条表达不需要加粗。这是一个例子：'MATCH (p:Person)-[:LIKES]->(b:Book) WHERE p <> b\nWITH p, collect(b) as books WHERE all(x in books WHERE x.rating > 4)\nRETURN p.name AS PersonName, books ORDER BY size(books) DESC'，你应该回答：找出那些至少有一本评分大于4的书的用户，并按照他们拥有的这类书籍的数量进行排序。\n查询所有评分大于4的人以及他们最喜欢的书籍\n怎么查找那些对书籍评分大于4的人？结果按他们喜欢的书籍数量排序，返回这些人及其相关书籍。\n",
                },
                {"role": "user", "content": cypher},
            ]
            # 3. get response
            responses = call_with_messages(massages)
            if responses != "":
                prompts = process_handle.process(responses)
                # 4. save to file
                save2file(cypher, prompts, output_path)


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
                "content": "我希望你模仿一个图数据库使用者的口吻，将我给你的prompt语句进一步泛化，不改变prompt表达的含义，并且泛化后的表达要符合我给你的cypher的含义，可以修改为问句或者陈述句，这是一个例子：cypher:MATCH (van:Person {name:'Vanessa Redgrave'})-[:HAS_CHILD*2..]-(n) RETURN n,prompt:Roy Redgrave的第二代及其所有后代有哪些？你应该给我：怎么查询Roy Redgrave的所有后代？\n查询Roy Redgrave的所有后代。\n输出Roy Redgrave的所有后代。\nRoy Redgrave的所有后代有哪些？\n查找数据库中名叫Roy Redgrave的人的所有后代。Roy Redgrave有哪些后代？下面我将给你一些句子，请你按顺序为每条语句输出10条泛化的结果，不需要注明是对那条语句进行的泛化，结果直接按照换行符隔开，不要有空格",
            },
            {"role": "user", "content": content},
        ]
        # 3. get response
        responses = call_with_messages(massages)
        # 4. postprocess and save
        if responses != "":
            prompts = process_handle.process(responses)
            save2file(db_id, cypher, prompts, output_path)


# to do
def gen_prompt_with_keywords(
    input_path, output_path, cypher
):  # generate multi prompts according to input cypher and keywords
    messages_list = [
        {
            "role": "system",
            "content": "我希望你帮助我提取cypher语句的实际含义和查询意图，我给你一个cypher语句，你应该给我5条表达查询意图的中文表达，每条中文的表达方式应该有差别，不需要给我每个步骤的解释，每条表达不需要加粗。这是一个例子：'MATCH (p:Person)-[:LIKES]->(b:Book) WHERE p <> b\nWITH p, collect(b) as books WHERE all(x in books WHERE x.rating > 4)\nRETURN p.name AS PersonName, books ORDER BY size(books) DESC'，你应该回答：找出那些至少有一本评分大于4的书的用户，并按照他们拥有的这类书籍的数量进行排序。\n查询所有评分大于4的人以及他们最喜欢的书籍\n找出那些对书籍评分大于4的人，并按他们喜欢的书籍数量排序，返回这些人及其相关书籍。\n",
        },
        {"role": "user", "content": cypher},
    ]
    return messages_list


# to do
def gen_prompt_with_template(input_path, output_path, cypher):
    messages_list = [
        {
            "role": "system",
            "content": "我希望你帮助我提取cypher语句的实际含义和查询意图，我给你一个cypher语句，你应该给我5条表达查询意图的中文表达，每条中文的表达方式应该有差别，不需要给我每个步骤的解释，每条表达不需要加粗。这是一个例子：'MATCH (p:Person)-[:LIKES]->(b:Book) WHERE p <> b\nWITH p, collect(b) as books WHERE all(x in books WHERE x.rating > 4)\nRETURN p.name AS PersonName, books ORDER BY size(books) DESC'，你应该回答：找出那些至少有一本评分大于4的书的用户，并按照他们拥有的这类书籍的数量进行排序。\n查询所有评分大于4的人以及他们最喜欢的书籍\n找出那些对书籍评分大于4的人，并按他们喜欢的书籍数量排序，返回这些人及其相关书籍。\n",
        },
        {"role": "user", "content": cypher},
    ]
    return messages_list


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


def save2file(db_id, cypher, prompts, output_path):
    if not os.path.isfile(output_path):
        with open(output_path, "w", encoding="utf-8") as file:
            file.write(db_id + "\n")
    with open(output_path, "a+", encoding="utf-8") as file:
        for prompt in prompts:
            file.write(cypher + "\n")
            file.write(prompt + "\n")
    print("corpus have been written into the file:", output_path)


def state_machine(input_path, output_path):
    if mode == Status.GEN_PROMPT_DIRECTLY.value[0]:
        gen_prompt_directly(input_path, output_path)
    elif mode == Status.GENERAL_PROMPT_DIRECTLY.value[0]:
        general_prompt_directly(input_path, output_path)
    elif mode == Status.GENERALIZATION.value[0]:
        generalization(input_path, output_path)
    elif mode == Status.GEN_PROMPT_WITH_KEYWORDS.value[0]:
        gen_prompt_with_keywords(input_path, output_path)
    elif mode == Status.GEN_PROMPT_WITH_TEMPLATE.value[0]:
        gen_prompt_with_template(input_path, output_path)


def main():
    # 0. parse dir
    if os.path.isfile(input_dir_or_path):
        input_path = input_dir_or_path
        dir, file_name = os.path.split(input_path)
        file_base, file_extension = os.path.splitext(file_name)
        output_path = os.path.join(output_dir, file_base + "_llm.txt")
        # output_path=os.path.join(dir,file_base+'_llm.txt')
        state_machine(input_path, output_path)
    elif os.path.isdir(input_dir_or_path):
        input_dir = input_dir_or_path
        for root, dirs, file_names in os.walk(input_dir):
            for file_name in file_names:
                input_path = os.path.join(root, file_name)
                file_base, file_extension = os.path.splitext(input_path)
                if file_extension != ".txt":
                    break
                file_name = file_base + "_llm" + file_extension
                output_path = os.path.join(root, file_name).replace(
                    input_dir, output_dir
                )
                state_machine(input_path, output_path)
    else:
        print("[ERROR]: input file is not exsit", input_dir_or_path)


if __name__ == "__main__":
    # input can be a dir or a file_path，if dir, process all the .txt files in batch
    input_dir_or_path = (
        "/root/work_repo/Awesome-Text2GQL/corpus/base/generate/movie.txt"
    )
    output_dir = "/root/work_repo/Awesome-Text2GQL/output"
    assert os.path.isdir(output_dir)
    mode = Status.GENERALIZATION.value[0]
    process_handle = CorpusPreProcess()
    main()

    # generate into json format, pls mak sure the input_corpus_dir_or_path in the config.json is correct!
    # config_path = "config.json"
    # generate_trainset(config_path)
