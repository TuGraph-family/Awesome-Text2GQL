'''
Prompt templates of DataGenerator
'''

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
10. Data Consistency & Dependency Management:    - CRITICAL: Every function that generates nodes (e.g., `generate_customers`) MUST return a list of the unique IDs it generated.
    - The `main` function is responsible for orchestrating the calls. It must capture the returned ID lists from node-generation functions.
    - When a function needs IDs from another entity (e.g., `generate_accounts` needs customer IDs), these IDs MUST be passed as function arguments. Do not rely on global variables.
11.  Edge CSV File Structure (VERY IMPORTANT): This rule defines the specific format for all relationship (edge) CSV files.
    - Headers for Edges: The column headers for the source and destination nodes MUST be the `name` of the source node type and the `name` of the destination node type from the schema, respectively. They MUST NOT be `_from` or `_to`.
    - Data Values for Edges: The data values in these columns MUST be the raw node IDs ONLY (e.g., `LE0000`). They MUST NOT include the node type as a prefix (e.g., NOT `Lender/LE0000`).
    - Example: For an edge defined in the schema as `{{"name": "LENDS_TO", "source": "Lender", "destination": "Loan", "properties": [...]}}` the resulting CSV file header MUST be `Lender,Loan,...properties`.

12. Data Noise: For about 10% of records, simulate missing data by setting 1-2 non-critical, non-key fields to an empty string (`''`).
    - CRITICAL: Do NOT use Python's `None` object to represent missing values. The final representation in the CSV file for an empty field MUST be an empty string `''`, resulting in `,,` for an empty column.

CSV Formatting & Safety Rules:
13. Writing Files: Use `csv.writer` with `newline=''` and `encoding='utf-8'`.
14. Quoting Strategy (CRITICAL): You MUST set the quoting strategy to `quoting=csv.QUOTE_MINIMAL`. This is essential for compatibility with strict data importers. Do not use `QUOTE_ALL`.
15. Field Cleaning:
    - Before writing, clean all string fields: `str(field).strip().replace('\\r', '').replace('\\n', ' ')`.
    - Ensure every row has the exact same number of columns as the CSV header.
16. Sanitization Function: To ensure data integrity and prevent all common import errors, you MUST include and use the following helper function within the generated script's main class.
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
17. Mandatory Usage: Every single `writer.writerow()` call MUST be wrapped with this sanitization function.
    - Correct Usage Example: `writer.writerow(self._sanitize_for_csv([field1, field2, field3]))`
    - Incorrect Usage Example: `writer.writerow([field1, field2, field3])`
18. CSV Writer Configuration: Configure the `csv.writer` with the following parameters for maximum compatibility: `newline=''` and `quoting=csv.QUOTE_MINIMAL`.

Final Output Instructions:
    - Python Code Only: Your entire response must be ONLY the Python code, enclosed in a single ` ```python ` block. Do not add any explanation, introduction, or concluding remarks.
    - Self-Contained: The script must include all necessary imports, parameter definitions, functions, and a main execution block (`if __name__ == "__main__":`).
    - Date Handling: When using `faker.date_...` functions, use `end_date='now'`.

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

fix_instruction = """
The Python code you previously generated failed with an error. 
Please analyze the code and the error traceback, fix the bug, and provide the complete, corrected Python script.

Constraints:
    - Output ONLY the full, corrected Python code in a single ```python block.
    - Do not add any apologies or explanations outside the code.
    - Ensure all dependencies between functions are correctly handled (e.g., passing IDs as arguments or using class attributes).

    --- PREVIOUS CODE ---
    ```python
    {original_code}
    ```

    --- ERROR TRACEBACK ---
    ```
    {last_error}
    ``` 
"""


fix_system_prompt = """
You are a senior Python debugger. Your task is to fix the provided code based on the error message.
"""
