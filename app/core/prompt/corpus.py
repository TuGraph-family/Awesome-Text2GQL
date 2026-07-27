"""
Prompt templates of CorpusGenerator
"""

SYSTEM_PROMPT = """
You are an expert in graph databases and the Cypher query language. Your task is to generate new, high-quality, and diverse "natural language question-Cypher query" data pairs based on the provided graph schema and some validated query examples.
Please ensure that the Cypher queries you generate are syntactically correct and compatible with the provided graph schema.
Your output must be in strict JSON format, use English, as a list containing multiple objects.
"""  # noqa: E501

SQLPGQ_SYSTEM_PROMPT = """
You are an Oracle SQL/PGQ expert generating executable training data.
SQL/PGQ extends SQL with property-graph pattern matching through GRAPH_TABLE.

Core rules:
- Use only the supplied graph name, labels, edge labels, and properties. Do not invent schema.
- Use property graph comments or validated examples as semantic guidance when present.
- Return exactly the JSON shape requested by the user prompt. Do not add explanations.
- Every graph access must use GRAPH_TABLE. The final SQL may be a direct GRAPH_TABLE query,
  a CTE/subquery around GRAPH_TABLE, a join between GRAPH_TABLE and relational tables, or a
  UNION ALL that combines graph results with normal SQL results.
- MATCH vertices with (v IS "LABEL") or (v); match edges with -[e IS "EDGE"]->, <-[e IS "EDGE"]-, or -[e IS "EDGE"]-.
- Declare variables for every vertex and edge that is referenced in WHERE, COLUMNS, SELECT, ORDER BY, GROUP BY, or HAVING.
- Never use Cypher or PGQL syntax: no (v:LABEL), no {{prop: value}}, no [:EDGE], no RETURN.
- Use double quotes for graph, label, and property identifiers; use single quotes only for string literals.
- Access properties inside GRAPH_TABLE as v."PROPERTY" or e."PROPERTY".
- Add graph WHERE predicates only when the question asks for a filter or the filter is required. Do not invent arbitrary literals.
- COLUMNS must not be empty. Alias every projected expression. Outside GRAPH_TABLE, refer to COLUMNS aliases, not graph variables.
- Project graph elements as VERTEX_ID(v) or EDGE_ID(e), not as raw vertex or edge variables.
- Put outer SQL operations such as ORDER BY, GROUP BY, HAVING, OFFSET, and FETCH outside GRAPH_TABLE.
- For aggregation, project needed values in COLUMNS and aggregate in outer SQL unless using path aggregates inside a quantified path.
- Use VERTEX_EQUAL(v1, v2) to compare vertices; do not compare vertices with v1 = v2.
- Avoid reserved words as variable names; use suffixes such as start_vertex or end_vertex.
- Keep parentheses balanced and avoid unsupported quantifiers such as *? or +?.

Advanced SQL/PGQ patterns to generate when they fit the schema and examples:
- Mixed SQL plus SQL/PGQ: WITH clauses, inline views, joins to base tables, EXISTS/NOT EXISTS,
  UNION ALL branches with compatible column counts and types, CASE expressions, analytic
  functions such as ROW_NUMBER(), and outer GROUP BY/HAVING/ORDER BY/FETCH.
- Bounded recursive paths: use supported quantifiers such as *, +, ?, {n}, {n,}, and {n,m}
  only where Oracle SQL/PGQ accepts them. Prefer bounded forms such as {1,3} for validation.
- ONE ROW PER MATCH, ONE ROW PER VERTEX (v), and ONE ROW PER STEP (src, edge, dst) when
  path unnesting is requested. Iterator variables must be unique, must not appear in MATCH or
  graph WHERE, and may be referenced only in COLUMNS.
- MATCHNUM(), PATH_NAME(), and ELEMENT_NUMBER(iterator) may be used in COLUMNS with
  ONE ROW PER queries.
- LISTAGG, JSON_ARRAYAGG, MIN, MAX, AVG, SUM, and COUNT may be used in COLUMNS for path
  aggregates when the variable is grouped by a quantified path; otherwise aggregate outside
  GRAPH_TABLE.
- VERTEX_ID, EDGE_ID, VERTEX_EQUAL, EDGE_EQUAL, and IS SOURCE/DESTINATION OF predicates are
  valid SQL/PGQ tools when the question asks for element identity or edge direction checks.

Shortest-path caution:
- For Oracle database SQL property graph queries, do not generate PGQL-only path search goals
  such as KEEP SHORTEST, ANY SHORTEST, ALL SHORTEST, ANY CHEAPEST, COST, TOTAL_COST, or
  MATCH path_variable = (...) unless a validated example in the prompt uses that exact syntax.
  Prefer a bounded path query with ORDER BY/FETCH or ONE ROW PER STEP for live DB validation.
"""  # noqa: E501


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
"""  # noqa: E501

SQLPGQ_INSTRUCTION_TEMPLATE = """
# Command
Generate {num_per_iteration} new "question-query" data pairs based on the following information.

# 1. Graph Schema
This is the Schema definition of the Oracle SQL property graph:
```json
{schema_json}
```

Graph name to use in every GRAPH_TABLE call:
```text
{graph_name}
```

2. Verified Query Examples (Context)
Here are some verified "question-query-result" examples that execute successfully.
```json
{examples_json}
```

3. Your Task
Generate {num_per_iteration} new, meaningful Oracle SQL/PGQ "question-query" data pairs.

Basic direct GRAPH_TABLE shape:
```sql
SELECT *
FROM GRAPH_TABLE (
  "{graph_name}"
  MATCH (n IS "LABEL")-[e IS "EDGE"]->(m IS "LABEL")
  WHERE n."property" = 'value'
  COLUMNS (m."property" AS property_alias)
) gt
```

Guidelines:
- Use "{graph_name}" as the graph name in every query.
- Use only schema labels, edge labels, and property names.
- Use concrete literal values from verified examples/results when filtering.
- If no known literal value is available, generate a broader query without that literal.
- Do not add a WHERE clause unless the question requires a filter.
- Always give every projected expression in COLUMNS an AS alias.
- Use COLUMNS aliases in outer SELECT, JOIN, ORDER BY, GROUP BY, HAVING, OFFSET, and FETCH clauses.
- For counts, averages, and grouping, project required values in COLUMNS and aggregate outside GRAPH_TABLE unless the query is a path aggregate.
- Project identifiers with VERTEX_ID(v) or EDGE_ID(e) when the question asks for vertices, edges, or IDs.
- Generate a diverse mix. Include at least one advanced SQL/PGQ pattern when the schema supports it:
  CTEs around GRAPH_TABLE, joins to base tables, UNION ALL with normal SQL, analytic functions,
  outer GROUP BY/HAVING, bounded path traversal, one-row-per-step path expansion, or element IDs.
- For UNION ALL, every branch must return the same number of columns with compatible data types.
- For joins to base tables, join using primary-key values projected from GRAPH_TABLE COLUMNS.
- For ONE ROW PER STEP, use unique iterator variables and project them only in COLUMNS; if unsure,
  prefer a bounded multi-hop query that can be validated by Oracle.
- Do not generate KEEP SHORTEST, ANY SHORTEST, ALL SHORTEST, COST, or PGQL path-variable syntax
  unless the verified examples include a working query using that exact form.
- Do not output Cypher, PGQL, placeholders, comments, explanations, or result fields.
- Return a strict JSON list of objects with "question" and "query" keys only. Do not include result fields.

Valid example:
```json
[
  {{
    "question": "Which movies belong to the Science Fiction genre?",
    "query": "SELECT * FROM GRAPH_TABLE (\"{graph_name}\" MATCH (m IS \"MOVIE\")-[b IS \"BELONGS_TO\"]->(g IS \"GENRE\") WHERE g.\"name\" = 'Science Fiction' COLUMNS (m.\"title\" AS movie_title, g.\"name\" AS genre_name)) gt"
  }},
  {{
    "question": "Which graph-derived movies can also be checked against the base movie table?",
    "query": "WITH graph_movies AS (SELECT gt.movie_id, gt.movie_title FROM GRAPH_TABLE (\"{graph_name}\" MATCH (m IS \"MOVIE\")-[b IS \"BELONGS_TO\"]->(g IS \"GENRE\") COLUMNS (m.\"MOVIE_id\" AS movie_id, m.\"title\" AS movie_title)) gt) SELECT gm.movie_title FROM graph_movies gm JOIN \"MOVIE\" m ON m.\"MOVIE_id\" = gm.movie_id"
  }}
]
```
"""  # noqa: E501

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
"""  # noqa: E501


QUERY_ARCHETYPES = [
    "Aggregation and Counting: Statistics on certain types of nodes or relationships in the graph, such as calculating quantity, sum, average, maximum/minimum values. Example: 'Count the number of all type A nodes in the database.'",  # noqa: E501
    "Filtering and Sorting: Filter nodes that meet conditions based on one or more attribute values, and sort the results. Example: 'Find type A nodes where attribute X is greater than [some value] and attribute Y is [some string], sorted by attribute X in descending order.'",  # noqa: E501
    "Relationship Reachability Query: Query which other nodes can be reached from a specific node through specified relationships. Example: 'Which type B nodes have [R-type relationship] with the type A node named [instance name]?'",  # noqa: E501
    "Multi-hop Path Query: Query complex paths spanning two or more relationships. Example: 'Which type A nodes can connect to the type C node named [instance name] through type B nodes? (A->B->C)'",  # noqa: E501
    "Common Neighbors and Association Analysis: Find whether two or more nodes are connected through the same intermediate node, often used to discover indirect connections. Example: 'Which type A nodes and another type A node named [instance name] are both connected to the same type B node? (A1->B<-A2)'",  # noqa: E501
    "Existence and Boolean Checks: Check whether nodes or patterns that meet specific conditions exist in the graph, typically returning yes or no. Example: 'Does the database contain a type A node whose attribute X value is [some specific value]?'",  # noqa: E501
    "Attribute Comparison Query: Filter other nodes based on comparisons between different nodes or based on a node's attributes. Example: 'Find all other type A nodes whose attribute X value is greater than that of the type A node named [instance name].'",  # noqa: E501
    "Path Analysis and Traversal: Focus on analysis of paths themselves, such as finding the shortest path or all possible paths. Example: 'Find the shortest path between the type A node named [instance A] and the type B node named [instance B].'",  # noqa: E501
]

SQLPGQ_QUERY_ARCHETYPES = [
    "Direct Graph Pattern Query: Answer a question with one GRAPH_TABLE MATCH pattern, projected aliases, and optional graph WHERE filters.",  # noqa: E501
    "Mixed SQL and SQL/PGQ Join: Use GRAPH_TABLE in a CTE or inline view, then join projected graph IDs or properties to normal relational tables.",  # noqa: E501
    "UNION ALL Hybrid Query: Combine a normal SQL branch with a GRAPH_TABLE branch using compatible output columns and data types.",  # noqa: E501
    "Outer SQL Aggregation: Project graph values in COLUMNS, then use COUNT, AVG, SUM, MIN, MAX, GROUP BY, HAVING, ORDER BY, or FETCH outside GRAPH_TABLE.",  # noqa: E501
    "Analytic SQL Over Graph Results: Use ROW_NUMBER, RANK, DENSE_RANK, or partitioned aggregates over a GRAPH_TABLE result set.",  # noqa: E501
    "Bounded Path Traversal: Use multi-hop or bounded quantified path patterns to ask reachability or chain questions while avoiding unsupported shortest-path goals.",  # noqa: E501
    "One Row Per Path Expansion: Ask for path steps or path elements and generate ONE ROW PER STEP or ONE ROW PER VERTEX queries when supported by the validated examples.",  # noqa: E501
    "Element Identity Query: Project VERTEX_ID or EDGE_ID, or compare graph elements with VERTEX_EQUAL/EDGE_EQUAL when identity matters.",  # noqa: E501
]



QUERY_TEMPLATE_INSTRUCTION = """
    You are a Cypher query generator expert for TuGraph.

    I have run some exploration queries on a Graph Database and got the following RAW RESULT DATA. 
    
    --- RAW DATA START ---
    {raw_data_str}
    --- RAW DATA END ---

    I also have a list of CYPHER TEMPLATES. 
    Your task is to generate {current_batch_size} new (Question, Query) pairs by filling these templates using the REAL DATA extracted from the RAW DATA above.

    --- TEMPLATES ---
    {selected_templates}

    --- CRITICAL RULES (Follow these or query will fail) ---
    1. **Correct Syntax**: NEVER put a `WHERE` clause inside the node parentheses. 
    - WRONG: `MATCH (n:Person WHERE n.age > 10)`
    - RIGHT: `MATCH (n:Person) WHERE n.age > 10`
    2. **Distinguish Node vs Edge**: 
    - Look closely at the RAW DATA. 
    - 'src' and 'dst' fields indicate an EDGE. 
    - 'identity' without 'src/dst' indicates a NODE.
    - Do NOT use a Node label as an Edge type (e.g. if 'GENRE' is a node, do not write `-[r:GENRE]-`).
    3. **Data Types**:
    - If a value is a string in RAW DATA, put quotes around it in Cypher (e.g. `name = "John"`).
    - If a value is a number, do not use quotes (e.g. `age = 40`).
    4. **JSON Output**: Output MUST be a strict JSON list of objects: [{{"question": "...", "query": "..."}}]
    """  # noqa: E501


SQLPGQ_QUERY_TEMPLATE_INSTRUCTION = """
    You are an Oracle SQL/PGQ query generator.

    I have run exploration queries on an Oracle SQL property graph and got the following RAW RESULT DATA.

    --- RAW DATA START ---
    {raw_data_str}
    --- RAW DATA END ---

    I also have a list of Oracle SQL/PGQ templates.
    Generate {current_batch_size} new (Question, Query) pairs by filling these templates using REAL DATA extracted from the RAW DATA above.

    --- TEMPLATES ---
    {selected_templates}

    --- CRITICAL RULES ---
    1. Use Oracle SQL/PGQ only: every graph access must use GRAPH_TABLE (... MATCH ... COLUMNS (...)).
    2. Use IS label syntax: (v IS "LABEL") and -[e IS "EDGE"]->.
    3. Never output Cypher syntax such as (v:LABEL), {{prop: value}}, [:EDGE], or RETURN.
    4. Use only labels, edge labels, properties, and literal values supported by the raw data/templates.
    5. Put graph filters in GRAPH_TABLE WHERE only when needed.
    6. Alias every COLUMNS expression and use those aliases in outer SQL.
    7. Mixed SQL is allowed: CTEs, joins with base tables, UNION ALL, analytic functions,
       GROUP BY/HAVING, ORDER BY/FETCH, and bounded path patterns are valid when templates show them.
    8. Do not generate KEEP SHORTEST or PGQL path-variable syntax unless templates show a validated example.
    9. Output MUST be a strict JSON list of objects: [{{"question": "...", "query": "..."}}]
    """  # noqa: E501


EXPLORATION_PROMPT_TEMPLATE = """
# Command
Your task is to brainstorm and generate diverse natural language questions. Focus on the breadth and depth of questions, without writing the graph query yet.

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

"""  # noqa: E501

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
"""  # noqa: E501

SQLPGQ_TRANSLATION_PROMPT_TEMPLATE = """
Command
Your task as an Oracle SQL/PGQ expert is to accurately translate the given natural language question into an executable Oracle SQL property graph query.

1. Graph Schema
```JSON
{schema_json}
```

Graph name to use in GRAPH_TABLE:
```text
{graph_name}
```

2. Question to be Translated
```json
{question}
```

3. Important Rules
- Use Oracle SQL/PGQ only, not Cypher and not PGQL.
- Every graph access must use GRAPH_TABLE ("{graph_name}" MATCH ... COLUMNS (...)).
- The final query may be direct GRAPH_TABLE SQL, or SQL wrapped with CTEs/subqueries, joins to
  relational tables, UNION ALL, GROUP BY/HAVING, analytic functions, ORDER BY, OFFSET, or FETCH.
- Use labels, edge labels, and property names exactly as defined by the schema.
- Use "{graph_name}" as the graph name.
- Put graph-pattern predicates inside GRAPH_TABLE WHERE only when required by the question.
- Do not invent filter literals or placeholder predicates.
- Put projected values inside COLUMNS, and always give every projected value an AS alias.
- Use COLUMNS aliases in outer SELECT, JOIN, ORDER BY, GROUP BY, HAVING, OFFSET, and FETCH clauses.
- For aggregation, project the required value in COLUMNS and aggregate outside GRAPH_TABLE unless using a path aggregate.
- If the question asks for vertices or edges, project VERTEX_ID(v) or EDGE_ID(e).
- Never use Cypher forms such as (p:PERSON), {{NAME: 'Tom Hanks'}}, [:ACTED_IN], RETURN, or m.TITLE.
- Use Oracle SQL/PGQ forms such as (p IS "PERSON"), [a IS "ACTED_IN"], p."NAME", m."TITLE", and a."ROLE".
- COLUMNS must look like COLUMNS (m."TITLE" AS movie_title, a."ROLE" AS role), not COLUMNS (m."TITLE", a."ROLE").
- For UNION ALL, each branch must return the same number of columns with compatible data types.
- For mixed SQL and SQL/PGQ joins, project graph IDs/properties in COLUMNS and join outside GRAPH_TABLE.
- For ONE ROW PER STEP, use unique iterator variables and reference them only in COLUMNS.
- Do not generate KEEP SHORTEST, ANY SHORTEST, ALL SHORTEST, COST, or PGQL path-variable syntax unless the error context or verified examples prove the target database accepts that exact form.
- Ensure every variable referenced in WHERE/COLUMNS is declared in MATCH.
- Ensure all parentheses are balanced.

Correct Oracle SQL/PGQ example:
{{
"query": "SELECT * FROM GRAPH_TABLE (\"{graph_name}\" MATCH (p IS \"PERSON\")-[a IS \"ACTED_IN\"]->(m IS \"MOVIE\") WHERE p.\"NAME\" = 'Tom Hanks' COLUMNS (m.\"TITLE\" AS movie_title, a.\"ROLE\" AS role)) gt"
}}

Invalid Cypher-style example:
{{
"query": "SELECT m.TITLE, e.ROLE FROM GRAPH_TABLE (MATCH (p:PERSON {{NAME: 'Tom Hanks'}})-[:ACTED_IN]->(m:MOVIE)) gt"
}}

{error_context}

4. Output Format
Return a JSON object containing only the "query" key.
{{
"query": "SELECT ... FROM GRAPH_TABLE (...) gt"
}}
"""  # noqa: E501
