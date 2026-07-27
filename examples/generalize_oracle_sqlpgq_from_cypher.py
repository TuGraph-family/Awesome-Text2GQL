import argparse
import json
from pathlib import Path

from app.impl.oracle_sqlpgq.generator.query_generalizer import (
    OracleSqlPgqQueryGeneralizer,
)
from app.impl.tugraph_cypher.ast_visitor.tugraph_cypher_ast_visitor import (
    TugraphCypherAstVisitor,
)
from app.impl.tugraph_cypher.translator.tugraph_cypher_query_translator import (
    TugraphCypherQueryTranslator,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Generalize a Cypher path shape over an Oracle SQL/PGQ manifest and "
            "emit Oracle GRAPH_TABLE queries."
        )
    )
    parser.add_argument(
        "--query",
        default="MATCH (a)-[e]->(b) RETURN b",
        help="Seed Cypher query whose path length/hop ranges define the pattern.",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("examples/Oracle_SQLPGQ_Instance/TEXT2GQL_GRAPH_oracle_schema.json"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("examples/generated_corpus/oracle_sqlpgq_generalized_queries.json"),
    )
    parser.add_argument("--target-size", type=int, default=25)
    args = parser.parse_args()

    cypher_translator = TugraphCypherQueryTranslator()
    if not cypher_translator.grammar_check(args.query):
        raise ValueError("Seed query does not pass the current Cypher grammar check.")

    success, query_pattern = TugraphCypherAstVisitor().get_query_pattern(args.query)
    if not success:
        raise ValueError("Seed query is outside the current Graph-IL visitor subset.")

    generalizer = OracleSqlPgqQueryGeneralizer.from_file(args.manifest)
    generated = generalizer.generalize_dicts(query_pattern, target_size=args.target_size)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as file:
        json.dump(generated, file, indent=2, ensure_ascii=False)
    print(f"Saved {len(generated)} generalized Oracle SQL/PGQ queries to {args.output}")


if __name__ == "__main__":
    main()

