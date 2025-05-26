import json
from app.core.generalizer.QueryGeneralizer import QueryGeneralizer
from app.core.generalizer.QuestionGeneralizer import QuestionGeneralizer
from app.core.llm.llm_client import LlmClient
from app.core.translator.QuestionTranslator import QuestionTranslator
from app.impl.iso_gql.translator.GraphQueryTranslator import GraphQueryTranslator as GQLTranslator
from app.impl.tugraph_cypher.query_visitor.GraphQueryVisitor import GraphQueryVisitor
from app.impl.tugraph_cypher.translator.GraphQueryTranslator import GraphQueryTranslator as CypherTranslator

INSTRUCTION_TEMPLATE = """
I want you to work like a Graph database expert, translate my question into a excutable query, and return only the query to me.
Below is an description about the graph database' schema to help you with your work.
Schema Description:
{schema_description}
"""

query_template="MATCH (n:Person)-[:HAS_CHILD*1]->(n) WHERE n.name = 'Vanessa Redgrave' RETURN n"
question_template="Who are Roy Redgrave's second generations?"

db_id = "movie"
instance_path = "../app/impl/tugraph_cypher/generalizer/base/db_instance/movie"
output_path = "./example_dataset.json"
llm_client = LlmClient(model="qwen-plus-0723")

# generate instruction
query_generalizer = QueryGeneralizer(db_id, instance_path)
schema_description=query_generalizer.schema_graph.gen_desc()
instruction = INSTRUCTION_TEMPLATE.format(schema_description=schema_description)

# generalize query
query_visitor = GraphQueryVisitor()
gql_translator = GQLTranslator()
query_list = []
success, query_pattern = query_visitor.get_query_pattern(query_template)
if success:
    query_pattern_list = query_generalizer.generalize(query_pattern=query_pattern)
    for query_pattern in query_pattern_list:
        query = gql_translator.translate(query_pattern)
        query_list.append(query)

# translate query into question
question_translator = QuestionTranslator(llm_client, 5)
question_list = question_translator.translate(
    query_template=query_template,
    question_template=question_template,
    query_list = query_list
)

corpus_pair_list = []
for i in range(len(query_list)):
    corpus_pair_list.append((query_list[i], question_list[i]))
corpus_pair_list.append((query_template, question_template))

# generalize question
generalized_corpus_pair_list = []
question_generalizer = QuestionGeneralizer(llm_client)
for corpus_pair in corpus_pair_list:
    query = corpus_pair[0]
    question = corpus_pair[1]
    generalized_question_list = question_generalizer.generalize(
        query=query,
        question=question
    )
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