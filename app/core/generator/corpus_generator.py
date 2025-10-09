import json
import random
import time
from typing import Any, Dict, List

from app.core.llm.llm_client import LlmClient
from app.core.prompt import corpus


class CorpusGenerator:
    def __init__(self, llm_client: LlmClient):
        self.llm_client = llm_client

    def _extract_json_from_response(self, response: str, expect_list: bool = True):
        """Extract JSON from LLM response."""
        try:
            start_char, end_char = ("[", "]") if expect_list else ("{", "}")
            json_start = response.find(start_char)
            json_end = response.rfind(end_char) + 1
            if json_start != -1 and json_end != 0:
                json_str = response[json_start:json_end]
                return json.loads(json_str)
            else:
                print(
                    f" [Warning] No valid JSON {'list' if expect_list else 'object'} "
                    "found in LLM response."
                )
                return [] if expect_list else {}
        except json.JSONDecodeError as e:
            print(f" [Error] Failed to parse LLM response: {e}")
            print(f" [RAW RESPONSE]:\n---\n{response}\n---")
            return [] if expect_list else {}

    def generate_questions_batch(
        self, schema_json: str, context_examples: List[Dict[str, Any]], questions_per_call: int
    ) -> List[str]:
        """
        Generate a batch of diverse questions based on schema and context.
        """
        all_questions = set()

        # Randomly select a query intent archetype to guide generation
        archetype = random.choice(corpus.QUERY_ARCHETYPES)
        print(f"Brainstorming questions with intent: '{archetype.split(':')[0]}'")

        instruction = corpus.EXPLORATION_PROMPT_TEMPLATE.format(
            schema_json=schema_json,
            archetype=archetype,
            examples_json=json.dumps(context_examples, indent=2, ensure_ascii=False),
            num_to_generate=questions_per_call,
        )
        message = [
            {"role": "system", "content": corpus.SYSTEM_PROMPT},
            {"role": "user", "content": instruction},
        ]

        try:
            response = self.llm_client.call_with_messages(message)
            generated_questions = self._extract_json_from_response(response, expect_list=True)
            if generated_questions:
                all_questions.update(generated_questions)
                print(f" Generated {len(generated_questions)} new questions.")
        except Exception as e:
            print(f" LLM call failed during question generation: {e}")

        return list(all_questions)

    def generate_translation_batch(
        self, schema_json: str, questions: List[str], error_context: Dict[str, str] = None
    ) -> List[Dict[str, Any]]:
        """
        Translate a list of questions into Cypher queries.
        Supports retries by providing an error_context.
        """
        instruction = corpus.TRANSLATION_PROMPT_TEMPLATE.format(
            schema_json=schema_json,
            question=questions[0],  # Assuming one question per call for clarity
            error_context=error_context if error_context else "",
        )
        message = [
            {"role": "system", "content": corpus.SYSTEM_PROMPT},
            {"role": "user", "content": instruction},
        ]

        try:
            response = self.llm_client.call_with_messages(message)
            query_obj = self._extract_json_from_response(response, expect_list=False)
            query = query_obj.get("query")

            if not query:
                print("LLM response was empty or malformed.")
                return []

            return [{"question": questions[0], "query": query}]

        except Exception as e:
            print(f"LLM call failed during translation: {e}")
            return []

    def generate_seeds_corpus(
        self, seed_context, target_seeds_size, schema_json, questions_per_call
    ) -> List[Dict[str, Any]]:
        """
        Generate target size seeds corpus base on seed context
        """
        # Initialize an empty list for the corpus and a small set of seed queries for context
        seed_corpus = []

        # ---  Iterative Generation and Validation Loop ---
        print(f"Targeting a final corpus size of {target_seeds_size} pairs.")
        iteration = 0
        while len(seed_corpus) < target_seeds_size:
            iteration += 1
            print(f"\n--- Iteration {iteration} ---")

            # Use a mix of seed context and existing corpus context
            current_context = seed_context + seed_corpus

            # --- Phase A: Generate a batch of questions ---
            questions_batch = self.generate_questions_batch(
                schema_json=schema_json,
                context_examples=current_context,
                questions_per_call=questions_per_call,
            )

            if not questions_batch:
                print("No new questions were generated. Stopping iteration.")
                time.sleep(2)
                continue

            # --- Phase B: Translate and Validate questions ---
            newly_added_count = 0
            for question in questions_batch:
                print(f"Translating: '{question}'")

                # Call LLM to translate a single question
                translation_attempt = self.generate_translation_batch(
                    schema_json=schema_json, questions=[question]
                )

                if translation_attempt:
                    seed_corpus.append(translation_attempt[0])
                    newly_added_count += 1
                    print(
                        "--> Successfully translated a new pair. "
                        f"Current there are {len(seed_corpus)} seed corpus pairs"
                    )
                else:
                    print(f"--> Failed to validate query for '{question}'.")

                time.sleep(1)  # Pause to control API rate limits
                if len(seed_corpus) >= target_seeds_size:
                    break  # Exit inner loop if target is reached

            print(f"Iteration {iteration} summary: Added {newly_added_count} new translated pairs.")

        return seed_corpus

    def run_generation_loop(
        self,
        schema_json: str,
        seeds_corpus_with_context: List[Dict[str, Any]],
        num_per_iteration: int = 5,
        complexity_corpus_size: int = 30,
    ) -> List[Dict[str, Any]]:
        """
        Run the main generation loop,
        using existing seed corpus as foundation for bootstrap generation.
        Args:
            num_per_iteration: Number of Q&A pairs to generate per iteration
            complexity_corpus_size: Target strong corpus size
        """
        print(f"Starting iterative generation loop. Target corpus size: {complexity_corpus_size}")
        print(f"Starting with {len(seeds_corpus_with_context)} initial pairs")
        complexity_corpus = []
        iteration_count = 0

        try:
            # Start iterative generation
            while len(complexity_corpus) < complexity_corpus_size:
                iteration_count += 1
                print(f"\n--- Iteration {iteration_count} ---")
                print(f"Current Corpus Size: {len(complexity_corpus)} pairs")
                print(
                    f"Remaining to target: {complexity_corpus_size - len(complexity_corpus)} pairs"
                )

                # Randomly select 3/10 of existing corpus as examples (at least 3, maximum 10)
                example_count = int(3 + (7 - 3) * random.random())
                random_examples = random.sample(
                    seeds_corpus_with_context, min(example_count, len(seeds_corpus_with_context))
                )
                selected_contexts = random_examples

                # 1. Build Prompt
                instruction = corpus.INSTRUCTION_TEMPLATE.format(
                    schema_json=schema_json,
                    examples_json=json.dumps(selected_contexts, indent=2, ensure_ascii=False),
                    num_per_iteration=num_per_iteration,
                )
                message = [
                    {"role": "system", "content": corpus.SYSTEM_PROMPT},
                    {"role": "user", "content": instruction},
                ]

                # 2. Call LLM
                print(f"  Calling LLM to generate {num_per_iteration} new pairs...")
                print(f"  Using {len(selected_contexts)} randomly selected examples as context")
                try:
                    response = self.llm_client.call_with_messages(message)
                    new_pairs = self._extract_json_from_response(response)
                    if not new_pairs:
                        print("  LLM did not return valid pairs. Skipping iteration.")
                        time.sleep(2)
                        continue
                    else:
                        # add new pairs to strong corpus
                        complexity_corpus.extend(new_pairs)
                    print(f"  LLM returned {len(new_pairs)} new pairs.")
                except Exception as e:
                    print(f"  LLM call failed: {e}")
                    time.sleep(2)
                    continue

                # Exit loop if target reached
                if len(complexity_corpus) >= complexity_corpus_size:
                    print(f"\nTarget corpus size of {complexity_corpus_size} reached!")
                    break

                # Control API call frequency
                time.sleep(2)

        except KeyboardInterrupt:
            print("\nKeyboardInterrupt detected! Saving corpus before exit...")
            return complexity_corpus
        except Exception as e:
            print(f"Iteration failed execution: {e}")

        # Final corpus save
        return complexity_corpus
