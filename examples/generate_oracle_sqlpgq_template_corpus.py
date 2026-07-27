import argparse
import json
from pathlib import Path

from app.impl.oracle_sqlpgq.generator.template_instantiator import (
    OracleSqlPgqTemplateInstantiator,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate deterministic Oracle SQL/PGQ corpus pairs from a schema manifest."
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("examples/Oracle_SQLPGQ_Instance/TEXT2GQL_GRAPH_oracle_schema.json"),
        help="Oracle SQL/PGQ schema manifest JSON.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("examples/generated_corpus/oracle_sqlpgq_template_corpus.json"),
        help="Output JSON file.",
    )
    parser.add_argument("--target-size", type=int, default=50)
    parser.add_argument(
        "--without-metadata",
        action="store_true",
        help="Write only question/query fields.",
    )
    args = parser.parse_args()

    instantiator = OracleSqlPgqTemplateInstantiator.from_file(args.manifest)
    pairs = instantiator.generate_dicts(
        target_size=args.target_size,
        include_metadata=not args.without_metadata,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as file:
        json.dump(pairs, file, indent=2, ensure_ascii=False)
    print(f"Saved {len(pairs)} Oracle SQL/PGQ template pairs to {args.output}")


if __name__ == "__main__":
    main()

