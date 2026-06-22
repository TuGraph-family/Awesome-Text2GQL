# Dataset Prep

Utilities in this directory prepare the benchmark dataset for Oracle SQL/PGQ work:

- discover dataset query files and graph import configs
- translate source Cypher/GQL-like records to Oracle SQL/PGQ
- optionally validate translated SQL/PGQ against a live Oracle Database
- summarize translation/runtime failures
- compare Oracle SQL/PGQ results with Neo4j Cypher results on the same dataset

Run commands from the repository root.

## Environment

Use the Poetry environment:

```bash
poetry env use python3.10
poetry install
```

Oracle live validation and Oracle-vs-Neo4j comparison require:

```bash
export ORACLE_DSN="localhost:1521/FREEPDB1"
export ORACLE_USER="SYSTEM"
export ORACLE_PASSWORD="tiger"
```

Neo4j comparison additionally requires:

```bash
export NEO4J_URI='bolt://localhost:7687'
export NEO4J_USER='neo4j'
export NEO4J_PASSWORD='ValidationPass123'
export NEO4J_DATABASE='neo4j'
```

On macOS, if Python hits a local `pyexpat` or `libexpat` issue:

```bash
export DYLD_LIBRARY_PATH="/opt/homebrew/opt/expat/lib:${DYLD_LIBRARY_PATH:-}"
```

## Dataset Discovery

Discovery is implemented in `dataset_prep/discover.py`.

For `train`, a database unit is counted when both files exist:

```text
dataset/train/<database>/4_level_results_ek_results.json
dataset/train/<database>/cypher/*/import_config.json
```

For `dev` and `test`, a database unit is counted when both files exist:

```text
dataset/<split>/<database>/Cypher/*_cypher.json
dataset/<split>/<database>/Cypher/**/import_config.json
```

The scripts count one top-level JSON record as one query example. They do not count every language field separately.

## Preflight

The translation script runs preflight automatically. It checks imports for `antlr4`, `oracledb`, the Cypher-to-Oracle translator, and Oracle environment variables when live validation is enabled.

To exercise the same checks indirectly:

```bash
poetry run python dataset_prep/translate_validate.py \
  --splits train \
  --databases bluesky \
  --limit-queries 1 \
  --skip-live-validation
```

## Translate To Oracle SQL/PGQ

Translate all discovered dataset records and validate against Oracle:

```bash
poetry run python dataset_prep/translate_validate.py \
  --dataset-root dataset \
  --output-root output/dataset_prep \
  --splits train dev test
```

Useful development run:

```bash
poetry run python dataset_prep/translate_validate.py \
  --dataset-root dataset \
  --output-root output/dataset_prep \
  --splits train \
  --databases bluesky \
  --limit-queries 20
```

Translate without connecting to Oracle:

```bash
poetry run python dataset_prep/translate_validate.py \
  --dataset-root dataset \
  --output-root output/dataset_prep \
  --splits train dev test \
  --skip-live-validation
```

Resume completed database units:

```bash
poetry run python dataset_prep/translate_validate.py \
  --dataset-root dataset \
  --output-root output/dataset_prep \
  --splits train dev test \
  --resume
```

Main options:

- `--splits train dev test`: splits to process.
- `--databases <name...>`: only process selected database names.
- `--limit-databases N`: process only the first N discovered database units.
- `--limit-queries N`: process only the first N records per database.
- `--skip-live-validation`: translate only, no Oracle load or query execution.
- `--resume`: reuse completed per-database summaries.
- `--fail-fast`: stop on the first database-level exception.
- `--oracle-validation-timeout-ms`: per-query Oracle timeout.
- `--oracle-validation-fetch-limit`: number of rows fetched for validation.

Outputs:

```text
output/dataset_prep/global_summary.json
output/dataset_prep/unsupported_samples.jsonl
output/dataset_prep/<split>/<database>/summary.json
output/dataset_prep/<split>/<database>/oracle_sqlpgq_enriched.jsonl
```

`oracle_sqlpgq_enriched.jsonl` contains the original record plus fields such as:

- `oracle_source_query`
- `oracle_sqlpgq`
- `oracle_translation_category`
- `oracle_validation_status`
- `oracle_validation_error`
- `oracle_dataset_meta`

## Failure Analysis

Group failed translation/validation records by likely root cause:

```bash
poetry run python dataset_prep/analyze_failures.py \
  --output-root output/dataset_prep \
  --dataset-root dataset \
  --splits train dev test \
  --sample-limit 5
```

Outputs:

```text
output/dataset_prep/failure_analysis.json
output/dataset_prep/failure_analysis.md
```

The report groups records whose `oracle_validation_status` is one of:

```text
syntax_error
runtime_error
unsupported
load_error
```

It also lists databases that were expected from discovery but do not have completed output.

## Oracle SQL/PGQ Vs Neo4j Result Validation

Use this after `translate_validate.py` has produced `oracle_sqlpgq_enriched.jsonl` files.

Run all splits:

```bash
poetry run python dataset_prep/compare_oracle_neo4j_results.py \
  --neo4j-uri bolt://localhost:7687 \
  --neo4j-user neo4j \
  --neo4j-password 'ValidationPass123' \
  --splits train dev test
```

Small smoke test:

```bash
poetry run python dataset_prep/compare_oracle_neo4j_results.py \
  --neo4j-uri bolt://localhost:7687 \
  --neo4j-user neo4j \
  --neo4j-password 'ValidationPass123' \
  --splits train \
  --databases bluesky \
  --limit-queries 20
```

Main options:

- `--dataset-output-root`: where translated Oracle JSONL files are read from.
- `--output-root`: where comparison reports are written.
- `--oracle-statuses success no_record`: which prior Oracle validation statuses are eligible.
- `--include-all-translatable`: compare every translatable record even if prior Oracle validation did not succeed.
- `--neo4j-batch-size`: CSV import and batched clear size.
- `--keep-loaded`: leave the last loaded Oracle and Neo4j graph in place for debugging.

Outputs:

```text
output/oracle_neo4j_compare/summary.json
output/oracle_neo4j_compare/mismatched_or_failed_queries.jsonl
output/oracle_neo4j_compare/<split>/<database>/summary.json
```

The comparison script:

- loads the same CSV graph into Oracle and Neo4j
- runs `oracle_sqlpgq` against Oracle
- runs `oracle_source_query` against Neo4j
- normalizes values before comparison, including dates, datetimes, booleans, decimals, floats, lists, maps, nodes, and relationships
- records failed executions and result mismatches in JSONL

Neo4j is cleared between databases in batches to avoid transaction memory errors from a single large `DETACH DELETE`.

## Export Validated Oracle SQL/PGQ Dataset

Use this after `translate_validate.py` has produced enriched records. The exporter loads each graph into Oracle and Neo4j, reruns the Oracle-vs-Neo4j comparison, and writes only records whose source Cypher and translated SQL/PGQ results match.

```bash
poetry run python dataset_prep/export_validated_dataset.py \
  --dataset-root dataset \
  --dataset-output-root output/dataset_prep \
  --output-root output/oracle_sqlpgq_dataset \
  --splits train dev test
```

The output mirrors the source `dataset/` layout. Query JSON files are filtered to matched records and each exported record gets:

```text
initial_sql_pgq
```

By default, the exporter strips internal `oracle_*` enrichment fields and copies the dataset assets beside the filtered query files. Useful options:

- `--sql-pgq-field <name>`: use a different field name for the SQL/PGQ query.
- `--include-oracle-metadata`: keep the internal `oracle_*` enrichment fields.
- `--no-copy-assets`: write only filtered query JSON files.
- `--overwrite`: replace an existing non-empty output directory.
- `--reuse-loaded`: validate against already-loaded Oracle and Neo4j graphs for a focused run.

## Common Workflows

Full Oracle translation and validation:

```bash
poetry run python dataset_prep/translate_validate.py --splits train dev test
poetry run python dataset_prep/analyze_failures.py
```

Full Oracle-vs-Neo4j validation:

```bash
poetry run python dataset_prep/translate_validate.py --splits train dev test --resume
poetry run python dataset_prep/compare_oracle_neo4j_results.py \
  --neo4j-uri bolt://localhost:7687 \
  --neo4j-user neo4j \
  --neo4j-password 'ValidationPass123' \
  --splits train dev test
```

Focused database debugging:

```bash
poetry run python dataset_prep/translate_validate.py \
  --splits dev \
  --databases Address \
  --limit-queries 50 \
  --fail-fast

poetry run python dataset_prep/compare_oracle_neo4j_results.py \
  --splits dev \
  --databases Address \
  --limit-queries 50 \
  --neo4j-uri bolt://localhost:7687 \
  --neo4j-user neo4j \
  --neo4j-password 'ValidationPass123' \
  --keep-loaded
```
