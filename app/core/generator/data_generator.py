import json
import subprocess
import re
import time
from datetime import datetime
from typing import Tuple, List
from pathlib import Path

from app.core.llm.llm_client import LlmClient
from app.core.prompt import data


class DataGenerator:
    """High-quality data generator based on Schema"""

    def __init__(self):
        self.llm_client = LlmClient(model="qwen3-coder-plus-2025-07-22")
        self.schema_json = None


    def _extract_python_code(self, response: str) -> str:
        """Robustly extract Python code from LLM response using regex."""
        # Match ```python ... ``` or ``` ... ``` blocks
        code_block_match = re.search(r'```(?:python)?\s*\n(.*?)\n```', response, re.DOTALL)
        if code_block_match:
            return code_block_match.group(1).strip()
        # If no code block found, return entire response as fallback (assuming it's all code)
        return response.strip()

    def generate_data_script(self) -> str:
        """Call LLM to generate data generation Python script."""
        
        data.INSTRUCTION_TEMPLATE = data.INSTRUCTION_TEMPLATE.format(schema_json=self.schema_json)
        message = [
            {"role": "system", "content": data.PROMPT},
            {"role": "user", "content": data.INSTRUCTION_TEMPLATE}
        ]
        
        response = self.llm_client.call_with_messages(message)
        
        # Robust code extraction
        code = self._extract_python_code(response)

        if not code:
            raise ValueError("LLM did not return any code.")
            
        # Optional core checks: e.g., check for if __name__ == "__main__":
        if 'if __name__ == "__main__":' not in code:
            print("Warning: Generated code is missing the main execution block.")

        return code
    
    def _sanitize_code(self, code: str) -> str:
        """
        Apply fixes for known high-frequency errors in generated code.
        This is a more reliable safety measure than relying solely on prompts.
        """
        # 1. Fix Faker import issues
        if 'from faker import Faker' not in code:
            if 'import faker' in code:
                code = code.replace('import faker', 'from faker import Faker', 1)
            else:
                code = 'from faker import Faker\n' + code

        # 2. Ensure Faker instance is created
        if not re.search(r"fake\s*=\s*Faker\(.*\)", code):
            last_import_pos = -1
            for match in re.finditer(r"^import .*", code, re.MULTILINE):
                last_import_pos = match.end()
            for match in re.finditer(r"^from .*", code, re.MULTILINE):
                last_import_pos = max(last_import_pos, match.end())

            if last_import_pos != -1:
                code = code[:last_import_pos] + "\n\n# Initialize Faker\nfake = Faker('en_US')\n" + code[last_import_pos:]
            else:
                code = "# Initialize Faker\nfake = Faker('en_US')\n" + code

        return code
    
    def generate_data(self, schema_file, output_base: str = "examples/generated_data", max_retries: int = 2) -> Tuple[str, List[Path]]:
        """Generate, save, and execute data generation script with automatic retry/fix logic."""
        with open(schema_file, 'r', encoding='utf-8') as f:
            self.schema_json = json.dumps(json.load(f), ensure_ascii=False)
        
        self.output_base = Path(output_base)
        
        # Script will create ./csv_files/ subdir, but ensure root exists
        self.script_dir = self.output_base / "scripts"
        self.script_dir.mkdir(parents=True, exist_ok=True)
        self.csv_dir = self.script_dir / "csv_files"

        last_error = "" # Error Traceback info
        original_code = ""

        for attempt in range(max_retries + 1):
            if attempt > 0:
                print(f"--- Attempt {attempt + 1}/{max_retries + 1}: Asking LLM to fix the previous error ---")
                fix_instruction = data.fix_instruction.format(
                    last_error = last_error,
                    original_code = original_code
                )
                fix_system_prompt = data.fix_system_prompt
                message = [
                    {"role": "system", "content": fix_system_prompt},
                    {"role": "user", "content": fix_instruction}
                ]
                response = self.llm_client.call_with_messages(message)
                code = self._extract_python_code(response)
            else:
                print("--- Attempt 1: Generating initial script ---")
                code = self.generate_data_script()

            if not code:
                last_error = "LLM returned empty code."
                continue
            
            original_code = code

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            script_name = f"data_generator_{timestamp}_attempt{attempt+1}.py"
            script_path = self.script_dir / script_name
            
            with open(script_path, 'w', encoding='utf-8') as f:
                f.write(code)
            
            try:
                result = subprocess.run(
                    ["python", str(script_path.name)],
                    cwd=str(self.script_dir),
                    capture_output=True, text=True, encoding='utf-8', timeout=600
                )
                
                if result.returncode == 0:
                    print(f"--- Script executed successfully on attempt {attempt + 1}! ---")
                    csv_files = list((self.script_dir / "csv_files").glob("*.csv"))
                    if not csv_files:
                        raise FileNotFoundError(f"Script ran but produced no CSV files. Output:\n{result.stdout}\n{result.stderr}")
                    return str(script_path), csv_files
                else:
                    last_error = f"STDOUT:\n{result.stdout}\n\nSTDERR:\n{result.stderr}"
                    print(f"Script failed on attempt {attempt + 1}. Error:\n{last_error}")

            except subprocess.TimeoutExpired as e:
                last_error = f"Script execution timed out: {e}"
                print(last_error)
            except Exception as e:
                last_error = f"An unexpected error occurred: {e}"
                print(last_error)

            time.sleep(2) # Avoid excessive API calls

        raise RuntimeError(f"Failed to generate a working script after {max_retries + 1} attempts. Last error:\n{last_error}")