import random
from http import HTTPStatus
from dashscope import Generation
from llm_process.PreProcess import CorpusPreProcess
from llm_process.Status import Status

def gen_prompt_directly(): # generate multi prompts according to input cypher
    # 1. read files
    with open(input_path, "rb") as file:
        for line in file:
            cypher=line.strip().decode('utf-8')
            # 2. gen massages
            # massages=[{'role': 'system', 'content': "我希望你帮助我做一些cypher语句的翻译工作，我给你一个cypher语句，你给我对应的中文，下面是两个例子，提问：MATCH (u:user {login: 'Michael'})-[r:rate]->(m:movie) WHERE r.stars < 3 RETURN m.title, r.stars\n回答：Michael讨厌的电影有哪些？\n提问：MATCH (u:user {login: 'Michael'})-[r:rate]->(m:movie) WHERE r.stars < 3 RETURN m.title, r.stars\n\n回答：查找用户Michael评分低于3星的电影，返回电影的标题和评分。之后我将给你一些cypher，请你帮我翻译一下，最好可以翻译成问句\n"},
            massages=[{'role': 'system', 'content': "我希望你帮助我提取cypher语句的实际含义和查询意图，我给你一个cypher语句，你应该给我5条表达查询意图的中文表达，每条中文的表达方式应该有差别，可以是陈诉句或者是问句，不需要给我每个步骤的解释，每条表达不需要加粗。这是一个例子：'MATCH (p:Person)-[:LIKES]->(b:Book) WHERE p <> b\nWITH p, collect(b) as books WHERE all(x in books WHERE x.rating > 4)\nRETURN p.name AS PersonName, books ORDER BY size(books) DESC'，你应该回答：找出那些至少有一本评分大于4的书的用户，并按照他们拥有的这类书籍的数量进行排序。\n查询所有评分大于4的人以及他们最喜欢的书籍\n怎么查找那些对书籍评分大于4的人？结果按他们喜欢的书籍数量排序，返回这些人及其相关书籍。\n"},
                        {'role': 'user', 'content': cypher}]
            # 3. get response
            responses=call_with_messages(massages)
            if responses!='':
                prompts=process_handle.process(cypher,responses)
                # 4. save to file
                save2file(cypher,prompts)

# to do
def generalization(cypher,prompt): # generate multi prompts according to input cypher and prompt
    messages_list = [{'role': 'system', 'content': "我希望你帮助我提取cypher语句的实际含义和查询意图，我给你一个cypher语句，你应该给我5条表达查询意图的中文表达，每条中文的表达方式应该有差别，不需要给我每个步骤的解释，每条表达不需要加粗。这是一个例子：'MATCH (p:Person)-[:LIKES]->(b:Book) WHERE p <> b\nWITH p, collect(b) as books WHERE all(x in books WHERE x.rating > 4)\nRETURN p.name AS PersonName, books ORDER BY size(books) DESC'，你应该回答：找出那些至少有一本评分大于4的书的用户，并按照他们拥有的这类书籍的数量进行排序。\n查询所有评分大于4的人以及他们最喜欢的书籍\n找出那些对书籍评分大于4的人，并按他们喜欢的书籍数量排序，返回这些人及其相关书籍。\n"},
                {'role': 'user', 'content': cypher}]
    return messages_list

def gen_prompt_with_keywords(cypher,keywords): # generate multi prompts according to input cypher and keywords
    messages_list = [{'role': 'system', 'content': "我希望你帮助我提取cypher语句的实际含义和查询意图，我给你一个cypher语句，你应该给我5条表达查询意图的中文表达，每条中文的表达方式应该有差别，不需要给我每个步骤的解释，每条表达不需要加粗。这是一个例子：'MATCH (p:Person)-[:LIKES]->(b:Book) WHERE p <> b\nWITH p, collect(b) as books WHERE all(x in books WHERE x.rating > 4)\nRETURN p.name AS PersonName, books ORDER BY size(books) DESC'，你应该回答：找出那些至少有一本评分大于4的书的用户，并按照他们拥有的这类书籍的数量进行排序。\n查询所有评分大于4的人以及他们最喜欢的书籍\n找出那些对书籍评分大于4的人，并按他们喜欢的书籍数量排序，返回这些人及其相关书籍。\n"},
                {'role': 'user', 'content': cypher}]
    return messages_list

# to do
def gen_prompt_with_template(cypher):
    messages_list = [{'role': 'system', 'content': "我希望你帮助我提取cypher语句的实际含义和查询意图，我给你一个cypher语句，你应该给我5条表达查询意图的中文表达，每条中文的表达方式应该有差别，不需要给我每个步骤的解释，每条表达不需要加粗。这是一个例子：'MATCH (p:Person)-[:LIKES]->(b:Book) WHERE p <> b\nWITH p, collect(b) as books WHERE all(x in books WHERE x.rating > 4)\nRETURN p.name AS PersonName, books ORDER BY size(books) DESC'，你应该回答：找出那些至少有一本评分大于4的书的用户，并按照他们拥有的这类书籍的数量进行排序。\n查询所有评分大于4的人以及他们最喜欢的书籍\n找出那些对书籍评分大于4的人，并按他们喜欢的书籍数量排序，返回这些人及其相关书籍。\n"},
                {'role': 'user', 'content': cypher}]
    return messages_list
        
def call_with_messages(messages):
    response = Generation.call(model="qwen-turbo",
                               messages=messages, 
                               seed=random.randint(1, 10000),
                               temperature=0.8,
                               top_p=0.8,
                               top_k=50,
                               result_format='message')
    if response.status_code == HTTPStatus.OK:
        content=response.output.choices[0].message.content
        print(content)
        return content
    else:
        print('Request id: %s, Status code: %s, error code: %s, error message: %s' % (
            response.request_id, response.status_code,
            response.code, response.message
        ))
        print('Failed!',messages[1]['content'])
        return ''

def save2file(cypher,prompts):
    with open(output_path, "a+", encoding="utf-8") as file:
        for prompt in prompts:
            file.write(cypher + "\n")
            file.write(prompt + "\n")
    
def main():
    if mode==Status.GEN_PROMPT_DIRECTLY.value[0]:
        gen_prompt_directly()
    elif mode==Status.GENERALIZATION.value[0]:
        generalization()
    elif mode==Status.GEN_PROMPT_WITH_KEYWORDS.value[0]:
        gen_prompt_with_keywords()
    elif mode==Status.GEN_PROMPT_WITH_TEMPLATE.value[0]:
        gen_prompt_with_template()
        
if __name__ == '__main__':
    input_path='/root/work_repo/Awesome-Text2GQL/test_input.txt'
    output_path='/root/work_repo/Awesome-Text2GQL/test_output.txt'
    mode=100
    process_handle=CorpusPreProcess()
    main()