'''
Prompt templates of CorpusGenerator
'''

SYSTEM_PROMPT = """
You are an expert in graph databases and the Cypher query language. Your task is to generate new, high-quality, and diverse "natural language question-Cypher query" data pairs based on the provided graph schema and some validated query examples.
Please ensure that the Cypher queries you generate are syntactically correct and compatible with the provided graph schema.
Your output must be in strict JSON format, use English, as a list containing multiple objects.
"""# noqa: E501


INSTRUCTION_TEMPLATE = """
# Command
Generate {num_per_iteration} new "question-query" data pairs based on the following information.

# 1. Graph Schema
This is the Schema definition of the graph you'll be working with:
```json
{schema_json}
```

2. Verified Query Examples (Context)
Here are some verified "question-query-result" examples that execute successfully. Use these as reference to understand the data patterns and query style in the graph. The result field shows partial data for reference.
```json
{examples_json}
```

3. Your Task
Now, based on the above Schema and examples, generate {num_per_iteration} new, more interesting, and potentially more complex "question-query" data pairs.
Please follow these guidelines:
Diversity: Create different types of queries, such as aggregations (COUNT, SUM, AVG), filtering (WHERE), multi-hop queries (MATCH (a)-[]->(b)-[]->(c)), optional matching (OPTIONAL MATCH), etc.
Increasing Complexity: Try to generate queries more complex than the examples, but ensure they are logically meaningful.
No Repetition: Do not generate items identical to the questions or queries in the examples above.
Strict Output Format: Your response must be a JSON list where each object contains both "question" and "query" keys. Do not add any explanations or comments outside the JSON content.

For example:
[
    {{
        "question": "(New natural language question 1)",
        "query": "(Corresponding Cypher query 1)"
    }},
    {{
        "question": "(New natural language question 2)",
        "query": "(Corresponding Cypher query 2)"
    }}
]
"""# noqa: E501

ENHANCEMENT_PROMPT_TEMPLATE = """
# Command
Your task as a senior Cypher expert is to create more complex and insightful new "question-query" pairs based on existing queries.

# 1. Graph Schema
```json
{schema_json}
```
2. Verified Query Examples (Context)
Here are some verified, high-quality "question-query-result" pairs. They are your source of inspiration.

```json
{examples_json}
```

3. Your Task
Now, based on the above Schema and examples, generate {num_to_generate} new, more complex "question-query" data pairs.
Please follow these guidelines to increase complexity:

Combination Patterns: Combine query patterns from multiple examples. For instance, combine a filtering query with a multi-hop path query.

Increase Depth: Extend existing path queries by adding more hops (e.g., from A->B to A->B->C->D).

Use Advanced Functions: Introduce aggregation functions (COUNT, SUM, AVG, COLLECT), or use more complex logic in WHERE clauses (OR, NOT, IN).

Ask Deeper Questions: Move from "what" type questions to more analytical questions like "why", "how many types", "compare", etc.

No Repetition: Ensure newly generated questions and queries are significantly different from the examples.

4. Output Format
Return in JSON list format where each object contains both "question" and "query" keys.
For example:
[
    {{
        "question": "(New natural language question 1)",
        "query": "(Corresponding Cypher query 1)"
    }},
    {{
        "question": "(New natural language question 2)",
        "query": "(Corresponding Cypher query 2)"
    }}
]
"""# noqa: E501


QUERY_ARCHETYPES = [
    "Aggregation and Counting: Statistics on certain types of nodes or relationships in the graph, such as calculating quantity, sum, average, maximum/minimum values. Example: 'Count the number of all type A nodes in the database.'", # noqa: E501
    "Filtering and Sorting: Filter nodes that meet conditions based on one or more attribute values, and sort the results. Example: 'Find type A nodes where attribute X is greater than [some value] and attribute Y is [some string], sorted by attribute X in descending order.'",# noqa: E501
    "Relationship Reachability Query: Query which other nodes can be reached from a specific node through specified relationships. Example: 'Which type B nodes have [R-type relationship] with the type A node named [instance name]?'",# noqa: E501
    "Multi-hop Path Query: Query complex paths spanning two or more relationships. Example: 'Which type A nodes can connect to the type C node named [instance name] through type B nodes? (A->B->C)'",# noqa: E501
    "Common Neighbors and Association Analysis: Find whether two or more nodes are connected through the same intermediate node, often used to discover indirect connections. Example: 'Which type A nodes and another type A node named [instance name] are both connected to the same type B node? (A1->B<-A2)'",# noqa: E501
    "Existence and Boolean Checks: Check whether nodes or patterns that meet specific conditions exist in the graph, typically returning yes or no. Example: 'Does the database contain a type A node whose attribute X value is [some specific value]?'",# noqa: E501
    "Attribute Comparison Query: Filter other nodes based on comparisons between different nodes or based on a node's attributes. Example: 'Find all other type A nodes whose attribute X value is greater than that of the type A node named [instance name].'",# noqa: E501
    "Path Analysis and Traversal: Focus on analysis of paths themselves, such as finding the shortest path or all possible paths. Example: 'Find the shortest path between the type A node named [instance A] and the type B node named [instance B].'"# noqa: E501
]


EXPLORATION_PROMPT_TEMPLATE = """
# Command
Your task is to brainstorm and generate diverse natural language questions. Focus on the breadth and depth of questions, without considering how to write Cypher queries for now.

# 1. Graph Schema
```json
{schema_json}
```

2. Verified Query Examples (Context)
Here are some verified "question-query-result" examples that execute successfully. Use these as reference to understand the data patterns and query style in the graph. The result field shows partial data for reference.
```json
{examples_json}
```

3. Task Guidance
Please generate {num_to_generate} different, meaningful natural language questions around the following "query intent". These questions should fully utilize various nodes, relationships, and attributes defined in the Schema.
"Query Intent": {archetype}

4. Output Format
Return in JSON list format, where each element is a string (question).
For example:
[
"Question 1...",
"Question 2..."
]

"""# noqa: E501

TRANSLATION_PROMPT_TEMPLATE = """
Command
Your task as a Cypher expert is to accurately translate the given natural language question into a Cypher query statement.

1. Graph Schema
This is the Schema of the graph the query is based on:
```JSON
{schema_json}
```

2. Question to be Translated
```json
{question}
```

3. !!! Important Rules !!!
Rule 1: Attribute Ownership: When specifying an attribute for a node (e.g., (n:Label)) in a WHERE clause, you must ensure the attribute clearly belongs to the Label node in the Schema definition.

Rule 2: Strict Prohibition of Confusion: Absolutely do not use attributes of relationships (EDGE) on nodes (VERTEX). For example, if compliance_status is an attribute of a relationship, then WHERE n.compliance_status = 'compliant' is a fatal error. The correct usage is to access it through the relationship variable, e.g., -[r:HAS_STATUS]-> and WHERE r.compliance_status = 'compliant'.

Rule 3: Faithfulness to Schema: Only use Schema

Rule 4: Use '%Y-%m-%d %H:%M:%S' format for time representation

{error_context}

3. Output Format
Return in JSON object format containing only the "query" key. Do not add any additional explanations.
For example:
{{
"query": "MATCH (m:Movie) WHERE m.title = 'some movie' RETURN m"
}}
"""# noqa: E501