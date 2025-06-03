from typing import List, Tuple
from app.core.llm.llm_client import LlmClient

CONTENT_TEMPLATE = """
Original Query: {query_template}
Translated Question: {question_template}

Queries to translate:
{query_chunk_str}
"""

PROMPT = """
Imagine you are the frontend of a graph database, where users ask questions and you generate corresponding queries.
Now, I need you to reverse this process: translate the queries I provide into natural language questions that a graph database user might input.
The translation must:
1. Match the phrasing style of graph database users.
2. Accurately reflect the query semantics.
3. Preserve all keywords like DISTINCT, OPTIONAL, etc.
4.Convert to either questions or statements as needed.

For each query, I will provide a template with the same structure as the target query to help you understand its meaning. Here's an example:

Original Query: MATCH (m:keyword{name: 'news report'})<-[:has_keyword]-(a:movie) RETURN a,m
Translated Question: "What movies have the keyword 'news report'? Return the corresponding nodes."

Queries to translate:
MATCH (m:movie{title: 'The Dark Knight'})<-[:write]-(a:person) RETURN a,m
MATCH (m:user{login: 'Sherman'})<-[:is_friend]-(a:user) RETURN a,m

You should respond with:
"Who are the authors of the movie 'The Dark Knight'? Return the relevant nodes.
"Find the friend nodes of the logged-in user Sherman in the graph, returning the relevant node information."

Now, translate each of the following queries one by one. Do not indicate which query you're translating from.
Separate results with newline characters and ensure sentences include proper punctuation marks.
"""


class QuestionTranslator:
    def __init__(self, llm_client: LlmClient, chunk_size):
        self.llm_client = llm_client
        self.chunk_size = chunk_size
        self.keywords_to_remove = [
            "Cypher: ",
            "   **Translation:**",
            "**",
            "    -",
            "`",
            ". ",
        ]

    def translate(
        self, query_template: str, question_template: str, query_list: List[str]
    ) -> List[Tuple[str, str]]:
        question_list = []
        chunk_size = self.chunk_size
        query_chunk_list = [
            query_list[i : i + chunk_size] for i in range(0, len(query_list), chunk_size)
        ]
        for query_chunk in query_chunk_list:
            query_chunk_str = ""
            for query in query_chunk:
                query_chunk_str = query_chunk_str + query + "\n"
            content = CONTENT_TEMPLATE.format(
                query_template=query_template,
                question_template=question_template,
                query_chunk_str=query_chunk_str,
            )

            messages = [
                {
                    "role": "system",
                    "content": PROMPT,
                },
                {"role": "user", "content": content},
            ]

            # 3. get response
            response = self.llm_client.call_with_messages(messages)

            # 4. postprocess and save
            if response != "":
                translated_question_list = self.post_process(response)

                # deal with unexpected questions length
                chunk_size = len(query_chunk)
                questions_size = len(translated_question_list)

                if questions_size > chunk_size:
                    translated_question_list = translated_question_list[0:chunk_size]
                elif questions_size < chunk_size:
                    filled_questions = ["Question translation failed."] * (
                        chunk_size - questions_size
                    )
                    translated_question_list = translated_question_list + filled_questions
                else:
                    pass
            else:
                translated_question_list = ["Question translation failed."] * (chunk_size)

            question_list += translated_question_list

        return question_list

    def post_process(self, response):
        lines = response.split("\n")
        generalized_question_list = []
        for line in lines:
            # remove keywords
            for keyword in self.keywords_to_remove:
                if keyword == ". ":  # remove "1."
                    dot_index = line.find(". ")
                    if dot_index != -1:
                        line = line[dot_index + 2 :]
                        continue
                line = line.replace(keyword, "")
            # remove white space
            line = line.strip()
            if line:
                generalized_question_list.append(line)
        return generalized_question_list


if __name__ == "__main__":
    llm_client = LlmClient(model="qwen-plus-0723")
    question_translator = QuestionTranslator(llm_client, 5)
    translated_question_list = question_translator.translate(
        query_template="MATCH (n {name: 'Carrie-Anne Moss'}) RETURN n.born AS born",
        question_template="Find the birth year of Carrie-Anne Moss.",
        query_list=[
            "MATCH (n{born: 1965}) RETURN n.id AS id",
            "MATCH (n{id: 526}) RETURN n.name AS name",
            'MATCH (n{name: "hand to hand combat"}) RETURN n.name AS name',
            'MATCH (n{summary: "placeholder text"}) RETURN n.title AS title',
            'MATCH (n{login: "Matthew"}) RETURN n.login AS login',
        ],
    )
    print(translated_question_list)
