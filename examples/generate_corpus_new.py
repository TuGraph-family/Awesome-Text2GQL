import json
import logging
from pathlib import Path
import time

from TuGraphClient import TuGraphClient

from app.core.generator.corpus_generator_new import CorpusGenerator
from app.core.llm.llm_client import LlmClient
from app.core.validator.corpus_validator import CorpusValidator

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

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
        - target_corpus_size (int): The desired total number of question-answer pairs 
          in the final corpus after iterative augmentation.
        """
        # --- 1. Configuration and Initialization ---
        logger.info("Starting corpus generation process...")
        graph = "healthcare_donor_20250805_171303"
        schema_file = Path(f"examples/generated_schemas/{graph}.json")
        output_path = Path(f"examples/generated_corpus/{graph}_corpus.json")
        
        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        tu_client = TuGraphClient(
            start_host_port="localhost:7070",
            username="admin",
            password="73@TuGraph73@TuGraph",
            graph=graph,
        )
        llm_client = LlmClient(model="qwen3-coder-plus-2025-07-22")
        
        # Initialize the generator and validator with their respective clients
        generator = CorpusGenerator(llm_client=llm_client)
        validator = CorpusValidator(tu_client=tu_client)

        target_corpus_size = 100
        questions_per_call = 5
        
        with open(schema_file, encoding="utf-8") as f:
            schema_json = json.dumps(json.load(f), ensure_ascii=False)
            
        # Initialize an empty list for the corpus and a small set of seed queries for context
        corpus_res = []
        seed_context = validator.execute_and_get_context(
            [
                {"question": "Seed 1", "query": "MATCH (n) RETURN n LIMIT 5"},
                {"question": "Seed 2", "query": "MATCH p=()-[r]->() RETURN p LIMIT 5"},
            ]
        )
        
        # --- 2. Iterative Generation and Validation Loop ---
        logger.info(f"Targeting a final corpus size of {target_corpus_size} pairs.")
        iteration = 0
        while len(corpus_res) < target_corpus_size:
            iteration += 1
            logger.info(f"\n--- Iteration {iteration} ---")
            
            # Use a mix of seed context and existing corpus context
            current_context = seed_context + validator.execute_and_get_context(corpus_res)
            
            # --- Phase A: Generate a batch of questions ---
            questions_batch = generator.generate_questions_batch(
                schema_json=schema_json,
                context_examples=current_context,
                questions_per_call=questions_per_call
            )
            
            if not questions_batch:
                logger.warning("No new questions were generated. Stopping iteration.")
                time.sleep(2)
                continue
                
            # --- Phase B: Translate and Validate questions ---
            newly_added_count = 0
            for question in questions_batch:
                logger.info(f"Translating and validating: '{question}'")
                
                # Call LLM to translate a single question
                translation_attempt = generator.generate_translation_batch(
                    schema_json=schema_json,
                    questions=[question]
                )
                
                # Use the validator to check the generated query against the DB
                if translation_attempt:
                    valid_pairs = validator.validate_and_filter_pairs(translation_attempt)
                    
                    if valid_pairs:
                        corpus_res.append(valid_pairs[0])
                        newly_added_count += 1
                        logger.info("--> Successfully added a new pair. "
                                    f"Total pairs: {len(corpus_res)}")
                    else:
                        logger.warning(f"--> Failed to validate query for '{question}'.")
                
                time.sleep(1) # Pause to control API rate limits
                if len(corpus_res) >= target_corpus_size:
                    break # Exit inner loop if target is reached
            
            logger.info(f"Iteration {iteration} summary: Added {newly_added_count} new pairs.")
            
            # Save progress periodically
            if iteration % 5 == 0 or len(corpus_res) >= target_corpus_size:
                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump(corpus_res, f, indent=4, ensure_ascii=False)
                logger.info(f"Saved {len(corpus_res)} pairs to {output_path}")

        logger.info(f"\nCorpus generation complete! Final size: {len(corpus_res)}")


    except Exception as e:
        logger.error(f"Program execution failed: {str(e)}", exc_info=True)


if __name__ == "__main__":
    main()
