import re
from base.CypherBase import CypherBase
from base.Config import Config

input_file_path = "/root/work_repo/Awesome-Text2GQL/noise_query.txt"
output_file_path = "/root/work_repo/Awesome-Text2GQL/clean_query.txt"
output_file_path1 = "/root/work_repo/Awesome-Text2GQL/clean_query1.txt"
# def extract_and_save_strings(input_path, output_path):
#     with open(input_path, 'r', encoding='utf-8') as input_file, \
#          open(output_path, 'w', encoding='utf-8') as output_file:
#         for line in input_file:
#             # Find the first and last occurrence of double quotes
#             first_quote_index = line.find('"')
#             last_quote_index = line.rfind('"')

#             # If both quotes are found, extract the substring
#             if first_quote_index != -1 and last_quote_index != -1:
#                 extracted_string = line[first_quote_index + 1:last_quote_index]
#                 output_file.write(f"{extracted_string}\n")

# # Using the same sample content and file paths as before
# extract_and_save_strings(input_file_path, output_file_path)
# 指定要去除的关键字
keywords_to_remove = ["有哪些？", "是什么？", "是谁？"]
config = Config("/root/work_repo/Awesome-Text2GQL/config.json")
cypher = CypherBase(config)

with open(output_file_path, "r", encoding="utf-8") as input_file, open(
    output_file_path1, "w", encoding="utf-8"
) as output_file:
    lines = input_file.readlines()
    for index, line in enumerate(lines):
        # 去除关键字
        for keyword in keywords_to_remove:
            if keyword in line:
                match = cypher.get_token_desc("MATCH")
                line = match + line
                line = line.replace(keyword, "。")
                output_file.write(lines[index - 1])
                output_file.write(line)
