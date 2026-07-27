"""
Convert a framework/TuGraph-style schema JSON into Oracle SQL/PGQ artifacts.

Generated files:
- *_oracle_tables.sql
- *_oracle_property_graph.sql
- *_oracle_schema.json
- *_oracle_loader.py
"""

import logging
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.impl.oracle_sqlpgq.schema.schema_parser import OracleSqlPgqSchemaParser

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def convert_schema_to_oracle_sqlpgq(
    input_json_path: str,
    output_dir: str,
    graph_name: str = "TEXT2GQL_GRAPH",
) -> str:
    input_path = Path(input_json_path)
    if not input_path.exists():
        raise FileNotFoundError(f"Input schema file not found: {input_path}")

    parser = OracleSqlPgqSchemaParser(db_id=graph_name, instance_path=str(input_path))
    schema_graph = parser.get_schema_graph()
    output_path = Path(output_dir)
    saved_manifest = parser.save_schema_to_file(
        output_path,
        schema_graph,
        domain=graph_name,
        subdomain="",
    )
    logger.info("Generated Oracle SQL/PGQ artifacts under %s", output_path)
    logger.info("Manifest: %s", saved_manifest)
    return saved_manifest


if __name__ == "__main__":
    convert_schema_to_oracle_sqlpgq(
        input_json_path="examples/generated_schemas/example_schema.json",
        output_dir="examples/Oracle_SQLPGQ_Instance",
        graph_name="TEXT2GQL_GRAPH",
    )
