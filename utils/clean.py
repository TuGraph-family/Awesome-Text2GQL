import re

input_file_path = "/root/work_repo/Awesome-Text2GQL/noise_query.txt"
output_file_path = "/root/work_repo/Awesome-Text2GQL/clean_query.txt"
output_file_path1 = "/root/work_repo/Awesome-Text2GQL/clean_query1.txt"

keywords_to_remove = [
    "提问：",
    "Cypher: ",
    "中文: ",
    "   **Translation:**",
    "**",
    "    -",
    "`",
    ". ",
]

with open(input_file_path, "r", encoding="utf-8") as input_file, open(
    output_file_path, "w", encoding="utf-8"
) as output_file:
    for line in input_file:
        # 去除关键字
        for keyword in keywords_to_remove:
            if keyword == ". ":
                # 找到". "符号的位置
                dot_index = line.find(". ")
                if dot_index != -1:  # 找到
                    line = line[dot_index + 2 :]
                    continue

            line = line.replace(keyword, "")
        # 去除行首尾的空白字符（包括空格、换行符等）
        line = line.strip()
        # 跳过空行
        if line:
            output_file.write(line + "\n")
