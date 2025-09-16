import json
import random
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
                    f"  [Warning] No valid JSON {'list' if expect_list else 'object'} "
                    "found in LLM response."
                )
                return [] if expect_list else {}
        except json.JSONDecodeError as e:
            print(f"  [Error] Failed to parse LLM response: {e}")
            print(f"  [RAW RESPONSE]:\n---\n{response}\n---")
            return [] if expect_list else {}

    def generate_questions_batch(
        self,
        schema_json: str,
        context_examples: List[Dict[str, Any]],
        questions_per_call: int = 5
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
                print(f"  Generated {len(generated_questions)} new questions.")
        except Exception as e:
            print(f"  LLM call failed during question generation: {e}")

        return list(all_questions)

    def generate_translation_batch(
        self,
        schema_json: str,
        questions: List[str],
        error_context: Dict[str, str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Translate a list of questions into Cypher queries.
        Supports retries by providing an error_context.
        """
        instruction = corpus.TRANSLATION_PROMPT_TEMPLATE.format(
            schema_json=schema_json,
            question=questions[0], # Assuming one question per call for clarity
            error_context=error_context if error_context else ""
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