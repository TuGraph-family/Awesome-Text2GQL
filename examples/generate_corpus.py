import json
import logging
from pathlib import Path

from app.core.generator.corpus_generator import CorpusGenerator
from app.core.llm.llm_client import LlmClient
from app.core.validator.validator import CorpusValidator

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("CorpusGeneratorScript")


def save_corpus_without_results(data: list, file_path: Path) -> None:
    """
    Save corpus data to JSON file, keeping only 'question' and 'query' fields.
    """
    # Filter out only question and query fields
    filtered_data = [
        {"question": item.get("question", ""), "query": item.get("query", "")} for item in data
    ]

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(filtered_data, f, indent=4, ensure_ascii=False)
    logger.info(f"Successfully saved {len(filtered_data)} pairs to {file_path}")


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
        - seeds_json_path (str): Optional path to load existing seeds, or empty to generate new ones
        - tu_client_params (dict): TuGraph database connection parameters 
          (host, username, password, graph name)
        - llm_client (LlmClient): The language model client used for question generation
          and translation (e.g., "qwen3-coder-plus-2025-07-22").
        - target_seeds_size (int): Target number of seed question-query pairs for initial corpus
        - iteration_times (int): Number of iterative augmentation rounds to run
        - corpus_size_per_iteration (int): Number of complex corpus entries to generate 
          per iteration
        """
        # --- 1. Configuration and Initialization ---
        logger.info("Starting corpus generation process...")

        # Graph database name
        graph = "example_schema"

        # Set to a path to load seeds, or empty string "" to generate new seeds.
        # Example: seeds_json_path = "examples/generated_corpus/example_corpus_seeds.json"
        seeds_json_path = ""

        schema_file = Path(f"examples/generated_schemas/{graph}.json")
        output_path = Path(f"examples/generated_corpus/{graph}_corpus.json")
        seeds_path = output_path.parent / (output_path.stem + "_seeds" + output_path.suffix)

        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # TuGraph client parameters
        tu_client_params = {
            "start_host_port": "localhost:7070",
            "username": "admin",
            "password": "73@TuGraph73@TuGraph",
            "graph": graph,
        }

        # Initial exploration queries for seed generation
        explor_query = [
            {"question": "Seed 1", "query": "MATCH p = ()-[]-() RETURN p LIMIT 5"},
            {"question": "Seed 2", "query": "MATCH p = ()-[]-()-[]-() RETURN p LIMIT 5"},
        ]

        llm_client = LlmClient(model="qwen3-coder-plus-2025-07-22")

        # Initialize the generator and validator with their respective clients
        generator = CorpusGenerator(llm_client=llm_client)
        validator = CorpusValidator(tu_client_params=tu_client_params)

        target_seeds_size = 30
        questions_per_call = 3
        seeds_corpus = []

        # Load schema file
        with open(schema_file, encoding="utf-8") as f:
            schema_json = json.dumps(json.load(f), ensure_ascii=False)

        # --- 2. Seeds Preparation: Generate new or load existing ---

        # Generate seeds from scratch if no path is provided
        if not seeds_json_path:
            logger.info("`seeds_json_path` is empty. Generating new seeds from scratch...")
            seed_context = validator.execute_and_get_context(explor_query)

            # Generation loop for seeds
            while len(seeds_corpus) < target_seeds_size:
                logger.info(
                    f"Current seeds count: {len(seeds_corpus)}. "
                    f"Target: {target_seeds_size}. Generating more..."
                )
                # 1. Generate a batch of seeds
                seed_context = seed_context + seeds_corpus
                tmp_seeds_corpus = generator.generate_seeds_corpus(
                    seed_context,
                    target_seeds_size,
                    schema_json,
                    questions_per_call,
                )
                # 2. Validate the batch and add valid pairs to the main list
                validated_seeds = validator.validate_and_filter_pairs(tmp_seeds_corpus)
                validated_seeds_with_context = validator.execute_and_get_context(validated_seeds)
                seeds_corpus.extend(validated_seeds_with_context)
                logger.info(f"Added {len(validated_seeds_with_context)} new valid seeds.")

            # Save the newly generated seeds corpus
            save_corpus_without_results(seeds_corpus, seeds_path)

        else:
            # Load seeds from the specified JSON file
            logger.info(f"Loading seeds from provided path: {seeds_json_path}")
            path_of_seeds_file = Path(seeds_json_path)

            if path_of_seeds_file.exists():
                with open(path_of_seeds_file, encoding="utf-8") as f:
                    loaded_seeds = json.load(f)
                logger.info(f"Loaded {len(loaded_seeds)} pairs from file. Validating...")
                validated_seeds = validator.validate_and_filter_pairs(loaded_seeds)
                validated_seeds_with_context = validator.execute_and_get_context(validated_seeds)
                seeds_corpus = validated_seeds_with_context
                logger.info(f"After validation, {len(seeds_corpus)} seed pairs are ready to use.")
            else:
                logger.error(f"Seeds file not found at {seeds_json_path}. Cannot proceed.")
                return  # Exit if the file doesn't exist

        # Check if we have enough seeds to proceed
        if not seeds_corpus or len(seeds_corpus) == 0:
            logger.error("No valid seeds available. Aborting complexity corpus generation.")
            return

        logger.info(f"Proceeding to generate complexity corpus using {len(seeds_corpus)} seeds.")

        # --- 3. Generate Complexity Corpus based on the prepared seeds ---
        logger.info("Starting iterative generation of complexity corpus...")

        # Iteration parameters
        corpus_size_per_iteration = 30  # Number of complex corpus entries to generate per iteration
        iteration_times = 4  # Total number of iterations to run
        num_per_llm_call = 5  # Number of candidate questions to generate per LLM call

        current_seeds = seeds_corpus  # Start with the initially validated seeds

        for batch_number in range(iteration_times):
            logger.info(f"--- Starting Iteration Batch {batch_number + 1}/{iteration_times} ---")
            iteration_pairs = []

            # Inner while loop to ensure enough corpus is generated for the current batch
            while len(iteration_pairs) < corpus_size_per_iteration:
                remaining_needed = corpus_size_per_iteration - len(iteration_pairs)
                logger.info(
                    f"Batch {batch_number + 1}: "
                    f"Generated {len(iteration_pairs)}/{corpus_size_per_iteration}. "
                    f"Need {remaining_needed} more."
                )

                # Generate a new batch of raw question-answer pairs based on the current seeds
                raw_corpus = generator.run_generation_loop(
                    schema_json=schema_json,
                    seeds_corpus_with_context=current_seeds,
                    complexity_corpus_size=num_per_llm_call,
                )

                # 1. Validate the raw corpus
                validated_corpus = validator.validate_and_filter_pairs(raw_corpus)

                # 2. Execute query and get context (assuming this function exists)
                pairs_with_context = validator.execute_and_get_context(validated_corpus)

                iteration_pairs.extend(pairs_with_context)

            # Save the corpus of this batch to a separate file
            batch_file_path = (
                output_path.parent / f"{output_path.stem}_{batch_number:02d}{output_path.suffix}"
            )
            save_corpus_without_results(iteration_pairs, batch_file_path)

            logger.info(
                f"--- Iteration {batch_number + 1} complete. "
                f"Saved {len(iteration_pairs)} pairs. ---"
            )

            # The output of this iteration becomes the seeds for the next one
            current_seeds = iteration_pairs

            # If an iteration produces no valid pairs, stop the generation early
            if not current_seeds:
                logger.warning(
                    f"Iteration {batch_number + 1} produced no valid pairs. "
                    "Stopping generation early."
                )
                break

        logger.info("Corpus generation complete! Individual batch files have been saved.")

    except Exception as e:
        logger.error(f"Program execution failed: {str(e)}", exc_info=True)


if __name__ == "__main__":
    main()
