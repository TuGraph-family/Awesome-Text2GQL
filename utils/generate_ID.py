def process_file(file_path):
    with open(file_path, 'r') as file:
        for line in file:
            # 移除行末尾的换行符，并按空格拆分
            words = line.strip().split()
            if words:
                # 检查首个字符串是否全为大写字母
                if words[0].isupper():
                    # print(f""""{words[0]}":"{words[0]}",""")
                    print(words[0],":")

# 使用示例
file_path = '/root/work_repo/antlr_python/cypher/Lcypher.g4'  # 替换为你的文件路径
process_file(file_path)
