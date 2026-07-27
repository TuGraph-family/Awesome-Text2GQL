# Oracle SQL/PGQ Data Generation Workflow

This guide explains the complete Oracle SQL/PGQ workflow currently implemented in the repository:

1. Convert a framework/TuGraph-style schema into Oracle SQL/PGQ artifacts.
2. Create and populate local Oracle property graphs.
3. Generate deterministic Oracle SQL/PGQ query/question pairs from the Oracle manifest.
4. Translate Cypher query templates into Oracle SQL/PGQ where the current Graph-IL subset supports them.
5. Generate LLM-based Oracle SQL/PGQ corpus pairs and validate/repair them against Oracle.
6. Combine generated corpora into a normalized dataset with metadata and train/dev/test splits.

Oracle property graphs are represented by relational table DDL, `CREATE PROPERTY GRAPH` DDL, JSON manifests, and executable `GRAPH_TABLE` queries.

Run commands from the repository root.

## Prerequisites

Install the Python environment:

```bash
poetry env use python3.10
poetry install
```

If `poetry` is not on `PATH`, use the absolute executable:

```bash
/opt/homebrew/bin/poetry --version
```

If Python hits a local `pyexpat` or `libexpat` issue on macOS, export:

```bash
export DYLD_LIBRARY_PATH="/opt/homebrew/opt/expat/lib:${DYLD_LIBRARY_PATH:-}"
```

## Environment

Set Oracle connection variables:

```bash
export ORACLE_DSN="localhost:1521/FREEPDB1"
export ORACLE_USER="SYSTEM"
export ORACLE_PASSWORD="tiger"
```

Set OpenAI-compatible LLM variables. For OCI/LiteLLM-style endpoints, use:

```bash
export OPENAI_API_KEY="<your-api-key>"
export OPENAI_BASE_URL="<your-openai-base-link>"
export OPENAI_EXTRA_HEADERS='{"client":"codex-cli","client-version":"0"}'
export LLM_PLATFORM="openai"
export LLM_MODEL="<model-name>"
```

For local Ollama/OpenAI-compatible testing, use:

```bash
export NO_PROXY="localhost,127.0.0.1,::1,${NO_PROXY:-}"
export no_proxy="localhost,127.0.0.1,::1,${no_proxy:-}"
export OPENAI_BASE_URL="http://127.0.0.1:11434/v1"
export OPENAI_API_KEY="ollama"
export LLM_PLATFORM="openai"
export LLM_MODEL="gemma4:latest"
```

Check local services:

```bash
nc -vz 127.0.0.1 1521
poetry run pytest test/test_oracle_sqlpgq_live.py
```

The live test runs `SELECT 1 AS VALUE FROM dual` through the Oracle DB client.

## Core Files

Oracle implementation:

```text
app/impl/oracle_sqlpgq/schema/schema_parser.py
app/impl/oracle_sqlpgq/translator/oracle_sqlpgq_query_translator.py
app/impl/oracle_sqlpgq/ast_visitor/oracle_sqlpgq_ast_visitor.py
app/impl/oracle_sqlpgq/db_client/oracle_db_client.py
app/impl/oracle_sqlpgq/generator/template_instantiator.py
app/impl/oracle_sqlpgq/generator/query_generalizer.py
app/impl/oracle_sqlpgq/generator/corpus_combiner.py
```

Examples:

```text
examples/tugraph_to_oracle_sqlpgq.py
examples/setup_oracle_sqlpgq_example_db.py
examples/setup_oracle_sqlpgq_fraud_db.py
examples/generate_oracle_sqlpgq_template_corpus.py
examples/cypher2oracle_sqlpgq.py
examples/generalize_oracle_sqlpgq_from_cypher.py
examples/generate_corpus_oracle_sqlpgq.py
examples/generate_corpus_oracle_sqlpgq_fraud.py
examples/combine_oracle_sqlpgq_corpus.py
```

Generated outputs:

```text
examples/Oracle_SQLPGQ_Instance/
examples/generated_corpus/
```

## Step 1: Generate Oracle SQL/PGQ Artifacts

Convert a framework/TuGraph-style schema JSON into Oracle SQL/PGQ artifacts:

```bash
poetry run python examples/tugraph_to_oracle_sqlpgq.py
```

This reads:

```text
examples/generated_schemas/example_schema.json
```

And writes:

```text
examples/Oracle_SQLPGQ_Instance/TEXT2GQL_GRAPH_oracle_schema.json
examples/Oracle_SQLPGQ_Instance/TEXT2GQL_GRAPH_oracle_tables.sql
examples/Oracle_SQLPGQ_Instance/TEXT2GQL_GRAPH_oracle_property_graph.sql
examples/Oracle_SQLPGQ_Instance/TEXT2GQL_GRAPH_oracle_loader.py
```

How it works:

- `OracleSqlPgqSchemaParser` converts `SchemaGraph` nodes into relational vertex tables.
- It converts graph edges into relational edge tables with `SRC_ID`, `DST_ID`, primary keys, and foreign keys.
- It emits `CREATE OR REPLACE PROPERTY GRAPH ... VERTEX TABLES ... EDGE TABLES`.
- It writes a JSON manifest used by deterministic generation and validation workflows.

Why it matters:

- Oracle SQL/PGQ property graphs are metadata over relational tables.
- The manifest becomes the source of truth for schema-aware corpus generation.

## Step 2: Create and Populate the Movie Graph

Create the default local movie-style Oracle graph:

```bash
poetry run python examples/setup_oracle_sqlpgq_example_db.py
```

This script:

1. Drops `TEXT2GQL_GRAPH` if it exists.
2. Drops/recreates the example graph tables.
3. Inserts deterministic generated rows.
4. Creates the Oracle SQL property graph.

The script is destructive only for the example graph objects in the configured Oracle schema.

Use a larger dataset when generating bigger corpora:

```bash
poetry run python examples/setup_oracle_sqlpgq_example_db.py \
  --users 100 \
  --movies 500 \
  --genres 20 \
  --tags 200 \
  --ratings 2000 \
  --genre-edges 800 \
  --tag-edges 1000 \
  --friend-edges 500 \
  --similarity-edges 1000 \
  --seed 42 \
  --batch-size 1000
```

Equivalent environment variable form:

```bash
export ORACLE_SQLPGQ_USERS=100
export ORACLE_SQLPGQ_MOVIES=500
export ORACLE_SQLPGQ_GENRES=20
export ORACLE_SQLPGQ_TAGS=200
export ORACLE_SQLPGQ_RATINGS=2000
export ORACLE_SQLPGQ_GENRE_EDGES=800
export ORACLE_SQLPGQ_TAG_EDGES=1000
export ORACLE_SQLPGQ_FRIEND_EDGES=500
export ORACLE_SQLPGQ_SIMILARITY_EDGES=1000
export ORACLE_SQLPGQ_DATA_SEED=42
export ORACLE_SQLPGQ_INSERT_BATCH_SIZE=1000

poetry run python examples/setup_oracle_sqlpgq_example_db.py
```

Minimum sizes are enforced because the seed validation queries depend on known values:

```text
users >= 4
movies >= 4
genres >= 4
tags >= 6
ratings >= 4
genre_edges >= 5
tag_edges >= 6
friend_edges >= 3
similarity_edges >= 3
```

Sanity check the graph:

```bash
poetry run python -c 'from app.impl.oracle_sqlpgq.db_client.oracle_db_client import OracleDBClient; import os; c=OracleDBClient({"dsn":os.environ["ORACLE_DSN"],"user":os.environ["ORACLE_USER"],"password":os.environ["ORACLE_PASSWORD"]}); q="SELECT * FROM GRAPH_TABLE (\"TEXT2GQL_GRAPH\" MATCH (m IS \"MOVIE\") COLUMNS (m.\"title\" AS title)) gt FETCH FIRST 3 ROWS ONLY"; r=c.execute_query(q); print(r.status_code); print(r.data or r.error); c.close()'
```

Expected status:

```text
200
```

## Step 3: Generate Deterministic Template Corpus

Generate schema-derived Oracle SQL/PGQ pairs without using an LLM:

```bash
poetry run python examples/generate_oracle_sqlpgq_template_corpus.py \
  --manifest examples/Oracle_SQLPGQ_Instance/TEXT2GQL_GRAPH_oracle_schema.json \
  --target-size 50 \
  --output examples/generated_corpus/oracle_sqlpgq_template_corpus.json
```

How it works:

- `OracleSqlPgqTemplateInstantiator` reads the Oracle manifest.
- It creates query/question pairs for:
  - one-hop traversals
  - graph element identifiers with `VERTEX_ID` and `EDGE_ID`
  - aggregate counts
  - two-hop traversals
  - bounded path queries for recursive/self edges
- It avoids literal predicates by default, so generated queries are schema-driven and portable across instances of the same graph.

Why it matters:

- This path is deterministic and reproducible.
- It gives high-validity Oracle SQL/PGQ coverage without depending on an LLM.
- It is useful as seed/context data for later LLM generation.

Live-validate generated template queries:

```bash
poetry run python -c 'import json, os; from pathlib import Path; from app.core.validator.db_client import QueryStatus; from app.impl.oracle_sqlpgq.db_client.oracle_db_client import OracleDBClient; path=Path("examples/generated_corpus/oracle_sqlpgq_template_corpus.json"); data=json.loads(path.read_text()); c=OracleDBClient({"dsn":os.environ["ORACLE_DSN"],"user":os.environ["ORACLE_USER"],"password":os.environ["ORACLE_PASSWORD"]}); ok=0; bad=[]; 
for i,item in enumerate(data):
    r=c.execute_query(item["query"])
    ok += r.status_code == QueryStatus.SUCCESS
    bad.append((i, r.error)) if r.status_code != QueryStatus.SUCCESS else None
print(f"{ok}/{len(data)} passed")
print(bad[:5])
c.close()'
```

## Step 4: Translate Cypher Queries to Oracle SQL/PGQ

Translate one supported Cypher query:

```bash
poetry run python examples/cypher2oracle_sqlpgq.py \
  --query "MATCH (p:PERSON)-[a:ACTED_IN]->(m:MOVIE) RETURN m.title AS movie_title" \
  --graph-name TEXT2GQL_GRAPH
```

Translate the Cypher template file:

```bash
poetry run python examples/cypher2oracle_sqlpgq.py \
  --input examples/corpus_templates/corpus_templates.json \
  --output examples/generated_corpus/cypher_templates_to_oracle_sqlpgq.json \
  --graph-name TEXT2GQL_GRAPH
```

How it works:

```text
Cypher query -> Cypher grammar check -> Cypher AST visitor -> Graph-IL -> Oracle SQL/PGQ translator
```

The output category explains what happened:

- `Graph-IL Translatable`: translated successfully.
- `Not Comply with OpenCypher`: the source query failed the current Cypher grammar check.
- `Graph-IL Not Support`: the query parsed as Cypher but is outside the current visitor/IR subset.
- `No Related Oracle SQL/PGQ Standard`: translation completed but failed the current SQL/PGQ structural validator.

Current supported subset:

- basic `MATCH` paths
- labels and relationship labels
- simple property comparisons
- `RETURN` items and aliases
- aggregates supported by current Graph-IL extraction
- `ORDER BY`, `SKIP`, `LIMIT`
- `DISTINCT`
- relationship hop ranges

Unsupported or partially supported examples include `OPTIONAL MATCH`, `shortestPath`, unions, complex boolean logic, `IN`, `STARTS WITH`, `CONTAINS`, and some path-return forms.

Why it matters:

- Existing Cypher corpora can be triaged into Oracle-translatable and unsupported categories.
- The translated subset can be validated against Oracle and included in Oracle SQL/PGQ datasets.

## Step 5: Generalize Oracle SQL/PGQ Queries From a Seed Shape

Generate Oracle queries by taking a seed Cypher path shape and matching it over the Oracle manifest:

```bash
poetry run python examples/generalize_oracle_sqlpgq_from_cypher.py \
  --query "MATCH (a)-[e]->(b) RETURN b" \
  --manifest examples/Oracle_SQLPGQ_Instance/TEXT2GQL_GRAPH_oracle_schema.json \
  --target-size 25 \
  --output examples/generated_corpus/oracle_sqlpgq_generalized_queries.json
```

How it works:

- The seed Cypher query is parsed into Graph-IL.
- `OracleSqlPgqQueryGeneralizer` reads the Oracle manifest.
- It finds schema paths with the same path length/hop shape.
- It emits Oracle `GRAPH_TABLE` queries through `OracleSqlPgqQueryTranslator`.

Why it matters:

- A small number of seed query shapes can produce many Oracle-specific query variants.
- This increases query diversity while staying schema-aware.

Live-validate generated generalized queries:

```bash
poetry run python -c 'import json, os; from pathlib import Path; from app.core.validator.db_client import QueryStatus; from app.impl.oracle_sqlpgq.db_client.oracle_db_client import OracleDBClient; path=Path("examples/generated_corpus/oracle_sqlpgq_generalized_queries.json"); data=json.loads(path.read_text()); c=OracleDBClient({"dsn":os.environ["ORACLE_DSN"],"user":os.environ["ORACLE_USER"],"password":os.environ["ORACLE_PASSWORD"]}); ok=0; bad=[]; 
for i,item in enumerate(data):
    r=c.execute_query(item["query"])
    ok += r.status_code == QueryStatus.SUCCESS
    bad.append((i, r.error)) if r.status_code != QueryStatus.SUCCESS else None
print(f"{ok}/{len(data)} passed")
print(bad[:5])
c.close()'
```

## Step 6: Generate LLM Corpus and Validate/Repair

Run a small test generation:

```bash
ORACLE_SQLPGQ_CORPUS_SIZE=3 \
ORACLE_SQLPGQ_NUM_PER_ITERATION=1 \
ORACLE_SQLPGQ_REPAIR_ATTEMPTS=1 \
poetry run python examples/generate_corpus_oracle_sqlpgq.py
```

Run a larger generation:

```bash
ORACLE_SQLPGQ_CORPUS_SIZE=50 \
ORACLE_SQLPGQ_NUM_PER_ITERATION=5 \
ORACLE_SQLPGQ_REPAIR_ATTEMPTS=2 \
poetry run python examples/generate_corpus_oracle_sqlpgq.py
```

How it works:

1. Hardcoded seed queries in `examples/generate_corpus_oracle_sqlpgq.py` are executed against Oracle.
2. Successful seed pairs are saved with result summaries.
3. Seed pairs and result summaries are passed to the LLM as examples.
4. The LLM generates new natural-language questions and Oracle SQL/PGQ queries.
5. Raw candidates are saved before validation.
6. Each generated query is executed against Oracle.
7. Failed queries are sent back to the LLM with the Oracle error for repair.
8. Valid and rejected pairs are saved separately.

Outputs:

```text
examples/generated_corpus/oracle_sqlpgq_example_corpus_raw.json
examples/generated_corpus/oracle_sqlpgq_example_corpus.json
examples/generated_corpus/oracle_sqlpgq_example_corpus_validated_with_results.json
examples/generated_corpus/oracle_sqlpgq_example_corpus_seed_validated_with_results.json
examples/generated_corpus/oracle_sqlpgq_example_corpus_rejected.json
```

Why it matters:

- The model sees real Oracle SQL/PGQ examples and real result summaries.
- Live validation prevents invalid SQL/PGQ from entering the final corpus.
- Repair loops improve final yield.

## Step 7: Combine Corpus Files

Combine deterministic, generalized, and LLM-generated corpora:

```bash
poetry run python examples/combine_oracle_sqlpgq_corpus.py \
  --input \
    examples/generated_corpus/oracle_sqlpgq_template_corpus.json \
    examples/generated_corpus/oracle_sqlpgq_generalized_queries.json \
    examples/generated_corpus/oracle_sqlpgq_example_corpus.json \
  --output examples/generated_corpus/oracle_sqlpgq_combined_corpus.json \
  --split
```

Combine and live-validate every final query against Oracle:

```bash
poetry run python examples/combine_oracle_sqlpgq_corpus.py \
  --input \
    examples/generated_corpus/oracle_sqlpgq_template_corpus.json \
    examples/generated_corpus/oracle_sqlpgq_generalized_queries.json \
    examples/generated_corpus/oracle_sqlpgq_example_corpus.json \
  --output examples/generated_corpus/oracle_sqlpgq_combined_corpus_validated.json \
  --split \
  --validate-live
```

How it works:

- `OracleSqlPgqCorpusCombiner` reads multiple JSON files.
- It normalizes fields into a common format.
- It deduplicates repeated question/query pairs.
- It preserves source file, source index, category, labels, result summaries, and validation metadata.
- With `--split`, it assigns train/dev/test splits.
- With `--validate-live`, it executes each final query against Oracle and writes:
  - `validation`: `passed` or `failed`
  - `validation_status_code`
  - `result` preview for passed queries
  - `validation_error` preview for failed queries

Why it matters:

- The final file is benchmark/training friendly.
- Records keep provenance, so you can trace whether a pair came from templates, generalization, or LLM generation.
- Live validation on the combined output is the strongest final check because it runs after deduplication and normalization.

## Step 8: Create the Fraud/Payments Graph

The repo includes a second scalable Oracle SQL/PGQ domain:

```text
TEXT2GQL_FRAUD_GRAPH
```

Default size:

```bash
poetry run python examples/setup_oracle_sqlpgq_fraud_db.py
```

Scaled size:

```bash
poetry run python examples/setup_oracle_sqlpgq_fraud_db.py \
  --customers 100 \
  --accounts 200 \
  --merchants 80 \
  --transactions 5000 \
  --devices 300 \
  --cities 25 \
  --seed 19 \
  --batch-size 1000
```

Environment variable form:

```bash
export FRAUD_GRAPH_CUSTOMERS=100
export FRAUD_GRAPH_ACCOUNTS=200
export FRAUD_GRAPH_MERCHANTS=80
export FRAUD_GRAPH_TRANSACTIONS=5000
export FRAUD_GRAPH_DEVICES=300
export FRAUD_GRAPH_CITIES=25
export FRAUD_GRAPH_DATA_SEED=19
export FRAUD_GRAPH_INSERT_BATCH_SIZE=1000

poetry run python examples/setup_oracle_sqlpgq_fraud_db.py
```

Generated artifacts:

```text
examples/Oracle_SQLPGQ_Instance/TEXT2GQL_FRAUD_GRAPH_oracle_schema.json
examples/Oracle_SQLPGQ_Instance/TEXT2GQL_FRAUD_GRAPH_oracle_tables.sql
examples/Oracle_SQLPGQ_Instance/TEXT2GQL_FRAUD_GRAPH_oracle_property_graph.sql
```

Generate and validate fraud corpus:

```bash
FRAUD_ORACLE_SQLPGQ_CORPUS_SIZE=50 \
FRAUD_ORACLE_SQLPGQ_NUM_PER_ITERATION=5 \
FRAUD_ORACLE_SQLPGQ_REPAIR_ATTEMPTS=2 \
poetry run python examples/generate_corpus_oracle_sqlpgq_fraud.py
```

Outputs:

```text
examples/generated_corpus/oracle_sqlpgq_fraud_corpus_raw.json
examples/generated_corpus/oracle_sqlpgq_fraud_corpus.json
examples/generated_corpus/oracle_sqlpgq_fraud_corpus_validated_with_results.json
examples/generated_corpus/oracle_sqlpgq_fraud_corpus_seed_validated_with_results.json
examples/generated_corpus/oracle_sqlpgq_fraud_corpus_rejected.json
```

## Step 9: Run Tests

Offline Oracle unit tests:

```bash
poetry run pytest \
  test/test_oracle_sqlpgq.py \
  test/test_cypher2oracle_sqlpgq.py \
  test/test_oracle_sqlpgq_template_instantiator.py \
  test/test_oracle_sqlpgq_query_generalizer.py \
  test/test_oracle_sqlpgq_corpus_combiner.py
```

Live Oracle smoke test:

```bash
poetry run pytest test/test_oracle_sqlpgq_live.py
```

## Current Capabilities

Implemented:

- Oracle SQL/PGQ schema artifact generation.
- Movie graph setup and data population.
- Fraud graph setup and data population.
- Oracle DB client and live validation.
- Graph-IL to Oracle SQL/PGQ translation.
- Cypher to Oracle SQL/PGQ translation for the supported subset.
- Deterministic Oracle SQL/PGQ template corpus generation.
- Oracle query generalization from seed Graph-IL/Cypher shapes.
- LLM corpus generation with live validation and repair.
- Corpus combination with metadata, deduplication, and splits.

Still limited:

- Oracle SQL/PGQ parsing is subset-based, not a full ANTLR-backed Oracle SQL/PGQ grammar.
- Deterministic templates currently avoid literal filters. Value-aware template instantiation can be added by sampling real values from Oracle.
- Generic synthetic row generation for arbitrary new schemas is not complete. New domains still need domain-specific setup scripts, CSV loading, or a future generic data synthesizer.
