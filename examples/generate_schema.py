import logging
from pathlib import Path

from app.core.generator.schema_generator import SchemaGenerator
from app.impl.tugraph_cypher.schema.schema_parser import TuGraphSchemaParser

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

def main():
    try:
        domain = "game"
        subdomain = "card_games"
        complexity_level = 5  # complexity_level(1-5)

        schema_gen = SchemaGenerator()
        
        logger.info("Generating Schema...")
        schema_graph = schema_gen.generate_schema(domain, subdomain, complexity_level)
        
        # validate SchemaGraph
        if schema_graph.validate():
            logger.info("Schema generated successfully")

            tugraph_schema_parser = TuGraphSchemaParser()
            output_dir = Path("examples/generated_schemas/")

            saved_path = tugraph_schema_parser.save_schema_to_file(output_dir, schema_graph, domain, subdomain)
            
            logger.info(f"Schema json file saved to: {saved_path}")
            
            # Print schema describe
            schema_desc = schema_graph.gen_desc()
            print("=== Schema describe ===")
            print(schema_desc)
        else:
            logger.info("Schema validation failed!")

    except Exception as e:
        logger.error(f"Failed: {str(e)}", exc_info=True)

if __name__ == "__main__":
    main()