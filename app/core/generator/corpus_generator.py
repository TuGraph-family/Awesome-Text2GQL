import json
import time
import random
from typing import Any, Dict, List
from pathlib import Path
import httpx


from TuGraphClient import TuGraphClient
from app.core.llm.llm_client import LlmClient
from app.core.prompt import corpus

class CorpusGenerator:
    def __init__(self, llm_client: LlmClient):
        self.llm_client = llm_client
        self.corpus_res: List[Dict[str, str]] = []
        self.context_examples = []

    def _extract_json_from_response(self, response: str, expect_list: bool = True):
        """Extract JSON from LLM response."""
        try:
            start_char, end_char = ('[', ']') if expect_list else ('{', '}')
            json_start = response.find(start_char)
            json_end = response.rfind(end_char) + 1
            if json_start != -1 and json_end != 0:
                json_str = response[json_start:json_end]
                return json.loads(json_str)
            else:
                print(f"  [Warning] No valid JSON {'list' if expect_list else 'object'} found in LLM response.")
                return [] if expect_list else {}
        except json.JSONDecodeError as e:
            print(f"  [Error] Failed to parse LLM response: {e}")
            print(f"  [RAW RESPONSE]:\n---\n{response}\n---")
            return [] if expect_list else {}

    def seed_context(self):
        """Populate context with initial Cypher queries as startup seeds for LLM."""
        print("[Phase 1] Seeding context with initial queries...")
        seed_cyphers = [
            "MATCH (n) RETURN n LIMIT 5",
            "MATCH p = ()-[]->() RETURN p LIMIT 5",
            "MATCH p = ()-[]->()-[]->() RETURN p LIMIT 5"
        ]
        
        for i, cypher in enumerate(seed_cyphers):
            print(f"  Executing seed query {i+1}/{len(seed_cyphers)}: {cypher}")
            try:
                res = self.tu_client.call_cypher(cypher, timeout=30)
                # Truncate results to avoid overly long prompts
                res_summary = str(res)[:500] + '...' if len(str(res)) > 500 else str(res)
                
                self.context_examples.append({
                    "question": f"A seed query for exploring the graph with path length {i}.",
                    "query": cypher,
                    "result": res_summary
                })
                print("  Seed query successful.")
            except Exception as e:
                print(f"  Seed query failed: {e}")
        print("Context seeded.\n")

    def explore_questions(self, tu_client: TuGraphClient, schema_json: str, output_path: Path, num_questions_to_generate: int = 50, questions_per_call: int = 5,  ) -> List[str]:
        """
        Phase 1: Explore and generate a large number of diverse questions.
        """
        self.tu_client = tu_client
        self.schema_json = schema_json
        self.output_path = output_path

        print("\n--- [Phase 1: Question Exploration] ---")
        all_questions = set() # Use set for automatic deduplication
        self.seed_context() # Initialize query seeds
        
        num_calls = (num_questions_to_generate) // questions_per_call
        
        for i in range(num_calls):
            # Randomly select a query intent archetype to guide generation
            archetype = random.choice(corpus.QUERY_ARCHETYPES)
            print(f"\n[Iteration {i+1}/{num_calls}] Brainstorming with intent: '{archetype.split(':')[0]}'")

            instruction = corpus.EXPLORATION_PROMPT_TEMPLATE.format(
                schema_json=self.schema_json,
                archetype=archetype,
                examples_json=json.dumps(self.context_examples, indent=2, ensure_ascii=False),
                num_to_generate=questions_per_call
            )
            message = [
                {"role": "system", "content": corpus.SYSTEM_PROMPT},
                {"role": "user", "content": instruction}
            ]

            try:
                response = self.llm_client.call_with_messages(message)
                generated_questions = self._extract_json_from_response(response, expect_list=True)
                if generated_questions:
                    all_questions.update(generated_questions)
                    print(f"  Generated {len(generated_questions)} new questions. Total unique questions: {len(all_questions)}")
            except Exception as e:
                print(f"  LLM call failed during question exploration: {e}")
            
            time.sleep(2) # Control API call frequency

        question_list = list(all_questions)
        self._save_questions(question_list)
        return question_list

    def _is_db_alive(self) -> bool:
        """Execute a simple query to check if the database is responsive."""
        try:
            # Use a very lightweight, guaranteed-success query
            self.tu_client.call_cypher("MATCH (n) RETURN count(n) LIMIT 1", timeout=5)
            return True
        except (httpx.ReadError, httpx.ConnectError, httpx.TimeoutException):
            return False
        except Exception:
            # Other exceptions may also indicate unhealthy service
            return False

    def translate_and_validate_pairs(self, questions: List[str], max_retries: int = 3):
        """Phase 2: Translate questions into queries and validate, with database crash recovery mechanism and stricter success criteria."""
        print("\n--- [Phase 2: Translation and Validation] ---")
        
        for question in questions:
            is_successful = False
            last_failed_query = ""
            last_error_message = ""

            for attempt in range(max_retries):
                error_context = ""
                if attempt > 0:
                    print(f"\n  Attempt {attempt + 1}/{max_retries} for question: '{question}'")
                    error_context = (
                        f"\n# Last attempt failed, please correct\n\n"
                        f"Your last generated query was:\n```cypher\n{last_failed_query}\n```\n"
                        f"It produced the following error during execution:\n```\n{last_error_message}\n```\n"
                        f"Please carefully analyze the error reason and generate a corrected, valid query."
                    )

                instruction = corpus.TRANSLATION_PROMPT_TEMPLATE.format(
                    schema_json=self.schema_json, question=question, error_context=error_context)
                message = [{"role": "system", "content": corpus.SYSTEM_PROMPT}, {"role": "user", "content": instruction}]

                try:
                    response = self.llm_client.call_with_messages(message)
                    query_obj = self._extract_json_from_response(response, expect_list=False)
                    query = query_obj.get("query")

                    if not query:
                        last_error_message, last_failed_query = "LLM response was empty or malformed.", ""
                        continue

                    # 1. Prepare validation query, only call database once
                    validation_query = query + " LIMIT 1" if "LIMIT" not in query.upper() else query
                    
                    # 2. Execute query
                    res = self.tu_client.call_cypher(validation_query, timeout=30)
                    res_str = str(res)

                    # 3. Use 'elapsed' as the sole criterion for success
                    if 'elapsed' in res_str:
                        print(f"\n    --> Success! Query for '{question}' is valid.")
                        print(f"      Response: {res_str[:100]}...")
                        self.corpus_res.append({"question": question, "query": query})
                        is_successful = True
                        break # Success, break out of retry loop
                    else:
                        # Database returned error string, consider as failure and trigger retry
                        print(f"\n    --> Attempt Failed! DB returned an error message.")
                        last_error_message = res_str # The entire return result is the error message
                        last_failed_query = query
                        # No exception thrown here, loop will automatically continue to next attempt
                
                except (httpx.ReadError, httpx.ConnectError) as net_err:
                    # Catch HTTP exceptions, but currently not effective
                    # TODO: Fix
                    poison_query = query if 'query' in locals() else "N/A"
                    print(f"\n  [FATAL] Database connection lost! Suspected crash caused by query:\n    {poison_query}")
                    print("  Entering recovery mode. Pausing generation and waiting for DB to restart...")
                    
                    recovery_interval = 15
                    while not self._is_db_alive():
                        print(f"  DB is still down. Retrying in {recovery_interval} seconds...")
                        time.sleep(recovery_interval)
                    
                    print("  [RECOVERED] Database is back online! Resuming generation process.")
                    is_successful = False
                    break

                except Exception as e:
                    # Handle other unexpected Python exceptions
                    print(f"\n    --> Attempt Failed! An unexpected Python exception occurred: {e}")
                    last_error_message = str(e)
                    last_failed_query = query if 'query' in locals() else "N/A"

            if not is_successful:
                print(f"\n  --> Failed to generate a valid query for question after all attempts: '{question}'")
            
            time.sleep(2)
        
        # For all queries in self.corpus_res, execute each query and delete those whose result is an empty list ([]).
        print("\n--- [Phase 3: Corpus Validation] ---")
        valid_corpus = []
        for item in self.corpus_res:
            query = item.get("query")
            try:
                res = self.tu_client.call_cypher(query, timeout=30)
                # Skip if result is empty
                if not res.get('result'):
                    print(f"  Removing query (empty result): {query}")
                    continue
                valid_corpus.append(item)
            except Exception as e:
                print(f"  Error executing query during corpus validation: {e}")
                continue
        self.corpus_res = valid_corpus

        # self.save_corpus_res()


    def run_generation_loop(self, num_per_iteration: int = 5, target_corpus_size: int = 100):
        """Run the main generation-validation loop, using existing corpus as foundation for bootstrap generation.
        
        Args:
            num_per_iteration: Number of Q&A pairs to generate per iteration
            target_corpus_size: Target corpus size
        """
        print(f"[Phase 3] Starting iterative generation loop. Target corpus size: {target_corpus_size}")
        print(f"Starting with {len(self.corpus_res)} initial pairs")
        iteration_count = 0

        try:
            # Start iterative generation
            while len(self.corpus_res) < target_corpus_size:
                iteration_count += 1
                print(f"\n--- Iteration {iteration_count} ---")
                print(f"Current Corpus Size: {len(self.corpus_res)} pairs")
                print(f"Remaining to target: {target_corpus_size - len(self.corpus_res)} pairs")
                
                # Randomly select 3/10 of existing corpus as examples (at least 3, maximum 10)
                example_count = max(3, min(10, len(self.corpus_res) * 3 // 10))

                if self.corpus_res:
                    random_examples = random.sample(self.corpus_res, min(example_count, len(self.corpus_res)))
                    # et complete context information for these random examples
                    selected_contexts = []
                    for example in random_examples:
                        question = example.get("question")
                        # Find matching complete context in context_examples
                        for ctx in self.context_examples:
                            if ctx.get("question") == question:
                                selected_contexts.append(ctx)
                                break
                else:
                    selected_contexts = self.context_examples  # If no corpus, use all context
                
                # 1. Build Prompt
                instruction = corpus.INSTRUCTION_TEMPLATE.format(
                    schema_json=self.schema_json,
                    examples_json=json.dumps(selected_contexts, indent=2, ensure_ascii=False),
                    num_to_generate=num_per_iteration
                )
                message = [
                    {"role": "system", "content": corpus.SYSTEM_PROMPT},
                    {"role": "user", "content": instruction}
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
                    print(f"  LLM returned {len(new_pairs)} new pairs. Validating now...")
                except Exception as e:
                    print(f"  LLM call failed: {e}")
                    time.sleep(2)
                    continue

                # 3. Validate and filter
                newly_added_count = 0
                for pair in new_pairs:
                    question = pair.get("question")
                    query = pair.get("query")
                    
                    if not question or not query:
                        print(f"  - Invalid pair found (missing keys): {pair}")
                        continue
                    
                    # Check if question already exists
                    if any(q.get("question") == question for q in self.corpus_res):
                        print(f"  - Skipping duplicate question: {question}")
                        continue
                    
                    print(f"  - Validating: [Q] {question}")
                    try:
                        # Use limit 1 to quickly validate query validity, avoid returning large amounts of data
                        validation_query = query + " LIMIT 1" if "LIMIT" not in query.upper() else query
                        res = self.tu_client.call_cypher(validation_query, timeout=30)
                        
                        res_str = str(res)
                        # Check if returned string contains key information
                        if res.get('result'):
                            print("    Query is valid and response format is correct.")
                            self.corpus_res.append(pair)
                            
                            # Update context for next iteration
                            res_summary = res_str[:500] + '...' if len(res_str) > 500 else res_str
                            new_context = {
                                "question": question,
                                "query": query,
                                "result": res_summary
                            }
                            self.context_examples.append(new_context)
                            newly_added_count += 1
                        else:
                            # Query executed but return format doesn't meet requirements
                            print(f"    Query failed validation: Response missing 'elapsed' or 'size'.")
                            
                    except Exception as e:
                        # Query execution itself failed
                        print(f"    Query failed execution: {e}")
                
                print(f"\n  --- Iteration {iteration_count} Summary ---")
                print(f"  Added {newly_added_count} new valid pairs to the corpus.")
                print(f"  Total pairs: {len(self.corpus_res)}")
                
                # Exit loop if target reached
                if len(self.corpus_res) >= target_corpus_size:
                    print(f"\nTarget corpus size of {target_corpus_size} reached!")
                    break
                    
                # Control API call frequency
                time.sleep(2)

        except KeyboardInterrupt:
            print("\nKeyboardInterrupt detected! Saving corpus before exit...")
            self.save_corpus_res()
            raise
        except Exception as e:
            print(f"Iteration failed execution: {e}")
            
        # Final corpus save
        self.save_corpus_res()


    def _execute_and_get_context_item(self, item: Dict[str, str]) -> Dict[str, Any]:
        """Execute a query and format it as a context entry, provided the result is not empty."""
        try:
            res = self.tu_client.call_cypher(item['query'], timeout=60)
            if res and res.get('result'):
                res_summary = str(res)[:500] + '...' if len(str(res)) > 500 else str(res)
                return {
                    "question": item['question'],
                    "query": item['query'],
                    "result": res_summary
                }
        except Exception:
            pass # Execution failed or result format incorrect
        return None


    def _save_questions(self, questions: List[str]):
        """Save the generated question list separately."""
        if not questions:
            return
        question_path = self.output_path.with_name(self.output_path.stem + "_questions.json")
        question_path.parent.mkdir(parents=True, exist_ok=True)
        print(f"\nSaving {len(questions)} unique questions to {question_path}...")
        try:
            with open(question_path, 'w', encoding='utf-8') as f:
                json.dump(questions, f, indent=4, ensure_ascii=False)
            print("  Questions saved successfully.")
        except Exception as e:
            print(f"  Failed to save questions: {e}")
            

    def save_corpus_res(self, output_path: Path = None):
        """
        Save the generated corpus to a file.
        If output_path parameter is provided, save to specified path, otherwise use default path defined during class initialization.
        """
        # Determine final save path
        path_to_save = output_path if output_path else self.output_path

        if not self.corpus_res:
            print(f"\nNo valid pairs in corpus. Nothing to save to {path_to_save}.")
            return

        # Ensure parent directory exists
        path_to_save.parent.mkdir(parents=True, exist_ok=True)
        print(f"\nSaving {len(self.corpus_res)} pairs to {path_to_save}...")
        try:
            with open(path_to_save, 'w', encoding='utf-8') as f:
                json.dump(self.corpus_res, f, indent=4, ensure_ascii=False)
            print(f"  Corpus saved successfully to {path_to_save}.")
        except Exception as e:
            print(f"  Failed to save corpus: {e}")
