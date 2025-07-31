import subprocess
import re
import time
from datetime import datetime
from typing import Tuple, List
from pathlib import Path
from app.core.llm.llm_client import LlmClient

PROMPT = """
You are a world-class Python engineer and an expert in graph database test data generation. 
Your task is to generate a single, self-contained, and executable Python script based on a given graph schema. 
The script must produce high-quality, realistic data that simulates complex real-world scenarios.
"""

INSTRUCTION_TEMPLATE = """
Graph Schema:
```json
{schema_json}
```
As a top-tier Python engineer, create a professional, high-quality Python script to generate realistic test data based on the provided graph schema.

Core Requirements:
0.  Strict Schema Adherence (TOP PRIORITY): This is the most important rule. The generated CSV headers and columns MUST STRICTLY and EXACTLY match the properties defined for the corresponding node or edge in the provided `schema_json`.
    - No Extra Columns: DO NOT add any columns that are not explicitly defined in the schema. This includes common default columns like `id`, `_id`, or `node_id`.
    - Exact Naming: If the schema defines a property `{{"name": "customer_id", "type": "string"}}`, the column header in the CSV MUST be `customer_id`.
1.  Single Script Generation: Generate a single, self-contained Python script. It must be directly executable (`python your_script.py`) without any modifications.
2.  Libraries: Use only the following standard libraries: `csv`, `faker`, `numpy`, `random`, `datetime`, and `os`.
3.  Reproducibility: Use `Faker('en_US')`, `np.random.seed(42)`, and `random.seed(42)` to ensure the generated data is reproducible.
4.  File Output:
    - Generate one CSV file for each node type and each edge type.
    - Crucially, all file paths must be relative to the location of the generated script. Use `os.path.dirname(os.path.abspath(__file__))` as the base directory.
    - Save node and edge CSV files into a `./csv_files/` subdirectory (relative to the script).
    - The script should automatically create this directory if it doesn't exist.
5.  OOP Script Generation: ...
6.  Libraries & Imports:
    - Use only `csv`, `faker`, `numpy`, `random`, `datetime`, and `os`.
    - CRITICAL IMPORT STYLE: You MUST use `from faker import Faker` to import the Faker library. Do not use `import faker`. The script should then instantiate it with `fake = Faker('en_US')`.

Data Realism & Quality Requirements:
8.  Data Volume Control: Use configurable parameters at the top of the script (e.g., `USER_COUNT`, `TRANSACTION_COUNT`) to easily control the amount of data generated.
9.  Realistic Data Distributions:
    - Implement realistic distributions for relevant properties.
    - For "hub" nodes or popular items (e.g., a few users with many transactions), use a power-law distribution. A good way to model this is with `numpy.random.zipf(a, size=...)`.
    - For values like transaction amounts, use a log-normal distribution (`numpy.random.lognormal(mean, sigma, size=...)`) or a skewed distribution to simulate a long tail (many small values, few large ones).
    - Use normal distribution (`numpy.random.normal`) for attributes like age or scores where applicable.
    - Add detailed comments in the code to explain which distribution is used for which attribute and why.
10. Data Consistency & Dependency Management:    - CRITICAL: Every function that generates nodes (e.g., `generate_customers`) MUST return a list of the unique IDs it generated.    - The `main` function is responsible for orchestrating the calls. It must capture the returned ID lists from node-generation functions.    - When a function needs IDs from another entity (e.g., `generate_accounts` needs customer IDs), these IDs MUST be passed as function arguments. Do not rely on global variables.
    - The edge CSV file must contain `_from` and `_to` columns, populated by sampling from the ID lists passed as arguments.
11. Data Noise: For about 10% of records, simulate missing data by setting 1-2 non-critical, non-key fields to an empty string (`''`).
    - CRITICAL: Do NOT use Python's `None` object to represent missing values. The final representation in the CSV file for an empty field MUST be an empty string `''`, resulting in `,,` for an empty column.

CSV Formatting & Safety Rules:
12. Writing Files: Use `csv.writer` with `newline=''` and `encoding='utf-8'`.
13. Quoting Strategy (CRITICAL): You MUST set the quoting strategy to `quoting=csv.QUOTE_MINIMAL`. This is essential for compatibility with strict data importers. Do not use `QUOTE_ALL`.
14. Field Cleaning:
     - Before writing, clean all string fields: `str(field).strip().replace('\\r', '').replace('\\n', ' ')`.
     - Ensure every row has the exact same number of columns as the CSV header.
15. Sanitization Function: To ensure data integrity and prevent all common import errors, you MUST include and use the following helper function within the generated script's main class.
    ```python
    def _sanitize_for_csv(self, row_data: list) -> list:
        \"\"\"
        Cleans a list of data just before it's written to CSV.
        - Converts None to an empty string ''.
        - Strips whitespace from strings.
        - Removes newlines and carriage returns from strings.
        \"\"\"
        cleaned_row = []
        for item in row_data:
            if item is None:
                cleaned_row.append('')  # CRITICAL: Convert None to empty string
            else:
                # Convert all items to string, then clean
                s = str(item).strip()
                s = s.replace('\r\n', ' ').replace('\n', ' ').replace('\r', ' ')
                cleaned_row.append(s)
        return cleaned_row
    ```
11. Mandatory Usage: Every single `writer.writerow()` call MUST be wrapped with this sanitization function.
    - Correct Usage Example: `writer.writerow(self._sanitize_for_csv([field1, field2, field3]))`
    - Incorrect Usage Example: `writer.writerow([field1, field2, field3])`
12. CSV Writer Configuration: Configure the `csv.writer` with the following parameters for maximum compatibility: `newline=''` and `quoting=csv.QUOTE_MINIMAL`.

Final Output Instructions:
    - Python Code Only: Your entire response must be ONLY the Python code, enclosed in a single ` ```python ` block. Do not add any explanation, introduction, or concluding remarks.    - Self-Contained: The script must include all necessary imports, parameter definitions, functions, and a main execution block (`if __name__ == "__main__":`).    - Date Handling: When using `faker.date_...` functions, use `end_date='now'`.

Reference Example Snippet (for distribution and relationship logic):
```python
# ... (inside a generation function) ...
# Store generated IDs for later use in relationships
customer_ids = [f"C{{i:06d}}" for i in range(CUSTOMER_COUNT)]
# ... (in another function) ...
# For generating relationships, sample from the existing ID list
from_id = random.choice(customer_ids)
to_id = random.choice(account_ids)
writer.writerow([from_id, to_id, ...])

# Example for power-law distribution of activities per user
# 'a=2' is a common parameter for Zipf distributions
user_activity_counts = np.random.zipf(a=2, size=USER_COUNT)
# ... use these counts to generate a realistic number of events per user ...
```
"""

class DataGenerator:
    """基于Schema的高质量测试数据生成器"""

    def __init__(self, schema_json: str, output_base: str = "examples/generated_data"):
        self.schema_json = schema_json
        self.llm_client = LlmClient(model="qwen-plus-0723")
        self.output_base = Path(output_base)
        
        # 脚本将自行创建 ./csv_files/ 子目录，但我们可以确保根目录存在
        self.script_dir = self.output_base / "scripts"
        self.script_dir.mkdir(parents=True, exist_ok=True)
        # csv_dir 将由生成的脚本在执行时创建，路径相对于脚本本身
        self.csv_dir = self.script_dir / "csv_files" # 用于最后收集文件

    def _extract_python_code(self, response: str) -> str:
        """使用正则表达式从LLM响应中稳健地提取Python代码。"""
        # 匹配 ```python ... ``` 或 ``` ... ``` 块
        code_block_match = re.search(r'```(?:python)?\s*\n(.*?)\n```', response, re.DOTALL)
        if code_block_match:
            return code_block_match.group(1).strip()
        # 如果没有找到代码块，作为备选方案，返回整个响应（假设它全是代码）
        return response.strip()

    def generate_data_script(self) -> str:
        """调用LLM生成数据生成Python代码。"""
        instruction = INSTRUCTION_TEMPLATE.format(schema_json=self.schema_json)
        message = [
            {"role": "system", "content": PROMPT},
            {"role": "user", "content": instruction}
        ]
        
        response = self.llm_client.call_with_messages(message)
        
        # 使用更稳健的方式提取代码
        code = self._extract_python_code(response)

        # 温和的后处理：只添加最关键、最不可能被LLM生成的元信息
        # 更好的Prompt使得复杂的 _sanitize_generated_code 不再必要
        if not code:
            raise ValueError("LLM did not return any code.")
            
        # 我们可以选择性地保留一些非常核心的检查，但目标是让Prompt解决问题
        # 例如，检查 if __name__ == "__main__":
        if 'if __name__ == "__main__":' not in code:
            # 可以尝试找到main函数并添加调用，但这也很复杂
            # 更好的做法是在Prompt中强调这一点，如果还是出错就认为是LLM生成失败
            print("Warning: Generated code is missing the main execution block.")

        return code
    
    def _sanitize_code(self, code: str) -> str:
        """
        对生成的代码执行一些已知的、高频错误的修正。
        这是一个比完全依赖Prompt更可靠的保险措施。
        """
        # 1. 修正 Faker 导入问题
        # 如果代码中没有 'from faker import Faker'
        if 'from faker import Faker' not in code:
            # 但却有 'import faker'，则进行替换
            if 'import faker' in code:
                code = code.replace('import faker', 'from faker import Faker', 1)
            # 如果两种都没有，则在顶部添加
            else:
                code = 'from faker import Faker\n' + code

        # 2. 确保 Faker 实例被创建
        # 使用正则表达式检查 fake = Faker(...) 是否存在
        if not re.search(r"fake\s*=\s*Faker\(.*\)", code):
            # 插入到 import 语句之后
            # 找到最后一个 import 语句
            last_import_pos = -1
            for match in re.finditer(r"^import .*", code, re.MULTILINE):
                last_import_pos = match.end()
            for match in re.finditer(r"^from .*", code, re.MULTILINE):
                last_import_pos = max(last_import_pos, match.end())

            if last_import_pos != -1:
                code = code[:last_import_pos] + "\n\n# Initialize Faker\nfake = Faker('en_US')\n" + code[last_import_pos:]
            else:
                # 如果没有 import 语句，就加在最前面
                code = "# Initialize Faker\nfake = Faker('en_US')\n" + code

        return code
    
    def generate_test_data(self, max_retries: int = 2) -> Tuple[str, List[Path]]:
        """生成、保存并执行数据生成脚本，带有自动重试修复逻辑。"""
        
        last_error = ""
        original_code = ""

        for attempt in range(max_retries + 1):
            if attempt > 0:
                print(f"--- Attempt {attempt + 1}/{max_retries + 1}: Asking LLM to fix the previous error ---")
                # 构建修复Prompt
                fix_instruction = (
                    "The Python code you previously generated failed with an error. "
                    "Please analyze the code and the error traceback, fix the bug, and provide the complete, corrected Python script.\n\n"
                    "Constraints:\n"
                    "- Output ONLY the full, corrected Python code in a single ```python block.\n"
                    "- Do not add any apologies or explanations outside the code.\n"
                    "- Ensure all dependencies between functions are correctly handled (e.g., passing IDs as arguments or using class attributes).\n\n"
                    "--- PREVIOUS CODE ---\n"
                    f"```python\n{original_code}\n```\n\n"
                    "--- ERROR TRACEBACK ---\n"
                    f"```\n{last_error}\n```"
                )
                
                # 使用一个简化的System Prompt进行修复
                fix_system_prompt = "You are a senior Python debugger. Your task is to fix the provided code based on the error message."
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

            original_code = code # 保存当前代码，以备修复时使用
            
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

            time.sleep(2) # 避免过于频繁的API调用

        raise RuntimeError(f"Failed to generate a working script after {max_retries + 1} attempts. Last error:\n{last_error}")
