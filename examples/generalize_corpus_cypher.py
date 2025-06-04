import json
import os

from app.core.generalizer.query_generalizer import QueryGeneralizer
from app.core.generalizer.question_generalizer import QuestionGeneralizer
from app.core.llm.llm_client import LlmClient
from app.core.translator.question_translator import QuestionTranslator
from app.impl.tugraph_cypher.ast_visitor.tugraph_cypher_query_visitor import TugraphCypherAstVisitor

INSTRUCTION_TEMPLATE = """
I want you to work like a Graph database expert,
translate my question into a excutable query, and return only the query to me.
Below is an description about the graph database' schema to help you with your work.
Schema Description:
{schema_description}
"""

query_template = "MATCH (n {name: 'Carrie-Anne Moss'}) RETURN n.born AS born"
question_template = "Find the birth year of Carrie-Anne Moss."

db_id = "movie"
instance_path = (
    f"{os.path.dirname(__file__)}"
    + "/../app/impl/tugraph_cypher/generalizer/base/db_instance/movie"
)
output_path = "./example_dataset.json"
llm_client = LlmClient(model="qwen-plus-0723")

# generate instruction
query_generalizer = QueryGeneralizer(db_id, instance_path)
schema_description = query_generalizer.schema_graph.gen_desc()
instruction = INSTRUCTION_TEMPLATE.format(schema_description=schema_description)

# generalize query
query_visitor = TugraphCypherAstVisitor()
query_list = query_generalizer.generalize_from_cypher(query_template=query_template)

# translate query into question
question_translator = QuestionTranslator(llm_client=llm_client, chunk_size=5)
question_list = question_translator.translate(
    query_template=query_template, question_template=question_template, query_list=query_list
)

# contruct corpus pair
corpus_pair_list = []
for i in range(len(query_list)):
    corpus_pair_list.append((query_list[i], question_list[i]))

# generalize question
generalized_corpus_pair_list = []
question_generalizer = QuestionGeneralizer(llm_client)
for corpus_pair in corpus_pair_list:
    query = corpus_pair[0]
    question = corpus_pair[1]
    generalized_question_list = question_generalizer.generalize(query=query, question=question)
    for generalized_question in generalized_question_list:
        generalized_corpus_pair_list.append((query, generalized_question))
    generalized_corpus_pair_list.append((query, question))

# store generalized corpus dataset into json file
data_list = [
    {
        "db_id": db_id,
        "instruction": instruction,
        "input": "",
        "output": "",
        "history": [],
    }
    for i in range(len(generalized_corpus_pair_list))
]
for i in range(len(generalized_corpus_pair_list)):
    corpus_pair = generalized_corpus_pair_list[i]
    temp_data = {"output": corpus_pair[0], "input": corpus_pair[1]}
    data_list[i].update(temp_data)
json_data = json.dumps(data_list, ensure_ascii=False, indent=4)
with open(output_path, "w") as file:
    file.write(json_data)
