# Schema Generator

The example of how schema generator operate is demonstrated at `examples/generate_schema.py`.

It requires two input variables, `domain`, `subdomain`, and `complexity_level` to ask LLM generate a `SchemaGraph`(`app/core/schema/schema_graph.py`), which is an IR for all type of graph schemas.

In order to generate schema or DDL file that fit the target database engine, you need to implement the `save_schema_to_file` interface of `SchemaParser(app/core/schema/schema_parser.py)`. Please see the example of `TuGraphSchemaParser(app/impl/tugraph_cypher/schema/schema_parser.py)`