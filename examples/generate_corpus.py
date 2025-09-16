import json
import logging
from pathlib import Path

from TuGraphClient import TuGraphClient

from app.core.generator.corpus_generator import CorpusGenerator
from app.core.llm.llm_client import LlmClient

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
        - num_questions_to_generate (int): The number of diverse questions to generate 
          in the initial phase. This controls the variety of questions created from the schema.
        - target_corpus_size (int): The desired total number of question-answer pairs 
          in the final corpus after iterative augmentation.
        """
        graph = "banking_financial_08181132"
        schema_file = Path(f"examples/generated_schemas/{graph}.json")
        output_path = Path(f"examples/generated_corpus/{graph}_corpus.json")
        tu_client = TuGraphClient(
            start_host_port="localhost:7070",
            username="admin",
            password="73@TuGraph73@TuGraph",
            graph=graph,
        )
        llm_client = LlmClient(model="qwen3-coder-plus-2025-07-22")
        generator = CorpusGenerator(llm_client=llm_client)
        num_questions_to_generate = 50
        target_corpus_size = 100

        with open(schema_file, encoding="utf-8") as f:
            schema_json = json.dumps(json.load(f), ensure_ascii=False)

        # 1. Generate diverse questions and save
        diverse_questions = generator.explore_questions(
            tu_client=tu_client,
            num_questions_to_generate=num_questions_to_generate,
            schema_json=schema_json,
            output_path=output_path,
        )

        if not diverse_questions:
            logger.error("Phase 1 failed: No diverse questions were generated.")
            return

        # 2. Translate questions and validate, generating seed corpus
        generator.translate_and_validate_pairs(diverse_questions)

        logger.info(
            f"Phase 2 complete. Saving {len(generator.corpus_res)} seed pairs to {output_path}..."
        )
        generator.save_corpus_res(output_path)

        # 3. Perform bootstrap iteration enhancement based on seed corpus
        generator.run_generation_loop(num_per_iteration=5, target_corpus_size=target_corpus_size)

        # Save final corpus
        generator.save_corpus_res()

    except Exception as e:
        logger.error(f"Program execution failed: {str(e)}", exc_info=True)


if __name__ == "__main__":
    main()
