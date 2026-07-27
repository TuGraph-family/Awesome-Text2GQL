import argparse
import os
from pathlib import Path

from app.core.validator.validator import CorpusValidator
from app.impl.oracle_sqlpgq.generator.corpus_combiner import OracleSqlPgqCorpusCombiner


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Combine Oracle SQL/PGQ corpus files with metadata and deduplication."
    )
    parser.add_argument(
        "--input",
        type=Path,
        nargs="+",
        default=[
            Path("examples/generated_corpus/oracle_sqlpgq_template_corpus.json"),
            Path("examples/generated_corpus/oracle_sqlpgq_generalized_queries.json"),
            Path("examples/generated_corpus/oracle_sqlpgq_example_corpus.json"),
        ],
        help="Input JSON corpus files.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("examples/generated_corpus/oracle_sqlpgq_combined_corpus.json"),
    )
    parser.add_argument("--split", action="store_true", help="Assign train/dev/test splits.")
    parser.add_argument(
        "--validate-live",
        action="store_true",
        help="Execute each combined query against Oracle and mark validation status.",
    )
    parser.add_argument(
        "--result-preview-chars",
        type=int,
        default=500,
        help="Maximum number of characters to keep from result/error previews.",
    )
    args = parser.parse_args()

    validator = None
    if args.validate_live:
        validator = CorpusValidator(
            backend="oracle_sqlpgq",
            db_client_params={
                "dsn": os.environ["ORACLE_DSN"],
                "user": os.environ["ORACLE_USER"],
                "password": os.environ["ORACLE_PASSWORD"],
            },
        )

    records = OracleSqlPgqCorpusCombiner().write_combined(
        args.input,
        args.output,
        split=args.split,
        validator=validator,
        result_preview_chars=args.result_preview_chars,
    )
    print(f"Saved {len(records)} combined Oracle SQL/PGQ records to {args.output}")
    if args.validate_live:
        passed = sum(1 for record in records if record.get("validation") == "passed")
        failed = sum(1 for record in records if record.get("validation") == "failed")
        print(f"Live validation: {passed} passed, {failed} failed")


if __name__ == "__main__":
    main()
