from typing import List, Tuple

from app.core.llm.llm_client import LlmClient

CONTENT_TEMPLATE = """
Original Query: {query}
Original Question: {question}
"""

PROMPT = """
I hope you can imitate the tone of a graph database user to further generalize the question statements I provide without changing their original meaning. The generalized expressions should align with the meaning of the provided query and can be reformulated as questions or statements. Here is an example:
Original Query: MATCH (n:Person {name:'Vanessa Redgrave'})-[:HAS_CHILD*1..]-(n) RETURN n
Original Question: Who are Roy Redgrave's second generation and all their descendants?
You should provide:
How to find all descendants of Roy Redgrave?
Find all descendants of Roy Redgrave.
Output all descendants of Roy Redgrave.
Who are all descendants of Roy Redgrave?
Find all descendants of a person named Roy Redgrave in the database.
Who are the descendants of Roy Redgrave?

Below, I will provide some sentences. For each statement, please generate 10 generalized results in sequence. Do not indicate which original statement they correspond to. Results should be separated by line breaks without spaces.
"""


class QuestionGeneralizer:
    def __init__(self, llm_client: LlmClient):
        self.llm_client = llm_client
        self.keywords_to_remove = [
            "Cypher: ",
            "   **Translation:**",
            "**",
            "    -",
            "`",
            ". ",
        ]

    def generalize(self, query: str, question: str) -> List[str]:
        content = CONTENT_TEMPLATE.format(query=query, question=question)
        # 2. gen massages
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
            generalized_question_list = self.post_process(response)
            return generalized_question_list
        else:
            return []

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
    question_generalizer = QuestionGeneralizer(llm_client)
    generalized_question_list = question_generalizer.generalize(
        query="MATCH (n {name: 'Carrie-Anne Moss'}) RETURN n.born AS born",
        question="Find the birth year of Carrie-Anne Moss.",
    )
    print(generalized_question_list)
