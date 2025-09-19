import json
import logging
from pathlib import Path

from app.core.generator.corpus_generator_new import CorpusGenerator
from app.core.llm.llm_client import LlmClient
from app.core.validator.validator import CorpusValidator

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("CorpusGeneratorScript")


def main():
    try:
        """
        Initializes the CorpusGenerator and generates a diverse question-answer corpus based on 
        the given schema file.
        - graph (str): The name of the graph database to use (e.g., "example").
        - schema_file (Path): The path to the schema file 
          (e.g., "examples/generated_schemas/example.json").
        - output_path (Path): The path where the generated corpus will be saved 
          (e.g., "examples/generated_corpus/example_corpus.json").
        - tu_client (TuGraphClient): The graph database client used for querying 
          and schema exploration.
        - llm_client (LlmClient): The language model client used for question generation 
          and translation (e.g., "qwen3-coder-plus-2025-07-22").
          in the initial phase. This controls the variety of questions created from the schema.
        - strong_corpus_size (int): The desired total number of question-answer pairs 
          in the final corpus after iterative augmentation.
        """
        # --- 1. Configuration and Initialization ---
        logger.info("Starting corpus generation process...")
        graph = "healthcare_donor_20250805_171303"
        seed_from_json = "examples/generated_corpus/healthcare_donor_20250805_171303_corpus_seeds.json"
        schema_file = Path(f"examples/generated_schemas/{graph}.json")
        output_path = Path(f"examples/generated_corpus/{graph}_corpus.json")
        
        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Store client parameters in a dictionary
        tu_client_params = {
            "start_host_port": "localhost:7070",
            "username": "admin",
            "password": "73@TuGraph73@TuGraph",
            "graph": graph,
        }
        explor_query = [
                {"question": "Seed 1", "query": "MATCH (n) RETURN n LIMIT 5"},
                {"question": "Seed 2", "query": "MATCH p=()-[r]->() RETURN p LIMIT 5"},
            ]

        llm_client = LlmClient(model="qwen3-coder-plus-2025-07-22")
        
        # Initialize the generator and validator with their respective clients
        generator = CorpusGenerator(llm_client=llm_client)
        # Pass the parameters to the validator
        validator = CorpusValidator(tu_client_params=tu_client_params)

        strong_corpus_size = 100
        target_seeds_size = 10
        questions_per_call = 3
        seeds_corpus = []

        with open(schema_file, encoding="utf-8") as f:
            schema_json = json.dumps(json.load(f), ensure_ascii=False)
        
        # Perpare seeds context for seeds generation
        if seed_from_json:
            path_of_seeds_file = Path(seed_from_json)
            with open(path_of_seeds_file, encoding="utf-8") as f:
                seeds_json = json.load(f)
            if len(seeds_json) >= target_seeds_size:
                seeds_corpus = validator.validate_and_filter_pairs(seeds_json)
                # TODO:when validator failed, seeds_corpus will be empty!
            else:
                print("Seeds json is empty!")
        else:
            seed_context = validator.validate_and_filter_pairs(explor_query)
            # Generate seeds corpus
            while(len(seeds_corpus) < target_seeds_size):
                # 1. Generate seeds corpus
                tmp_seeds_corpus = generator.generate_seeds_corpus(
                    seed_context, 
                    target_seeds_size, 
                    schema_json, 
                    questions_per_call
                    )
                # 2. Validate each seed
                seeds_corpus = seeds_corpus + validator.validate_and_filter_pairs(tmp_seeds_corpus)

        # Save progress periodically
        seeds_path = output_path.parent / (output_path.stem + "_seeds" + output_path.suffix)
        with open(seeds_path, "w", encoding="utf-8") as f:
            json.dump(seeds_corpus, f, indent=4, ensure_ascii=False)
        print(f"Saved {len(seeds_corpus)} pairs to {seeds_path}")

        # ---Now, we have target_seeds_size seeds corpus---
    
        # 3. Run generation loop to generate strong corpus base on seeds corpus
        strong_corpus = []
        while(len(strong_corpus) < strong_corpus_size):
            strong_corpus = generator.run_generation_loop(
            schema_json=schema_json,
            seeds_corpus=seeds_corpus,
            strong_corpus_size=strong_corpus_size,
            )
            # TODO: Validate strong corpus 
            print(strong_corpus)

        logger.info(f"\nCorpus generation complete! Final size: {len(strong_corpus)}")


    except Exception as e:
        logger.error(f"Program execution failed: {str(e)}", exc_info=True)


if __name__ == "__main__":
    main()
