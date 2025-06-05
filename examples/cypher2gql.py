import pandas as pd

from app.impl.iso_gql.translator.iso_gql_query_translator import (
    IsoGqlQueryTranslator as GQLTranslator,
)
from app.impl.tugraph_cypher.ast_visitor.tugraph_cypher_ast_visitor import TugraphCypherAstVisitor
from app.impl.tugraph_cypher.translator.tugraph_cypher_query_translator import (
    TugraphCypherQueryTranslator as CypherTranslator,
)

# Login using e.g. `huggingface-cli login` to access this dataset
splits = {"train": "data/train-00000-of-00001.parquet", "test": "data/test-00000-of-00001.parquet"}
df = pd.read_parquet("hf://datasets/neo4j/text2cypher-2024v1/" + splits["test"])
cols = df.columns.values.copy()
cols[2] = "gql"
new_df = pd.DataFrame(columns=cols)

query_visitor = TugraphCypherAstVisitor()
gql_translator = GQLTranslator()
cypher_translator = CypherTranslator()
for _, row in df.iterrows():
    query = row["cypher"]
    if cypher_translator.grammar_check(query):
        if not gql_translator.grammar_check(query):
            success, query_pattern = query_visitor.get_query_pattern(query)
            if success:
                query = gql_translator.translate(query_pattern)
            else:
                continue
        new_row = row.copy()
        new_row["cypher"] = query
        new_row_series = pd.Series(new_row.to_list(), index=cols)
        new_df = pd.concat([new_df, new_row_series.to_frame().T], ignore_index=True)

new_df.to_parquet("./test.parquet")
