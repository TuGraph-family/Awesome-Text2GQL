import json
from base.Schema import Schema
from base.Config import Config
import sys
import os
from utils.GrammarCheck import grammar_check


def generate(config, input_path, output_path):
    with open(input_path, "rb") as file:
        for line in file:
            db_id = line.decode("utf-8")
            db_id = db_id.strip()
            break
    schema_path = config.get_schema_path(db_id)
    if db_id == "common":
        schema_desc = ""
    else:
        schema = Schema(db_id, schema_path)
        schema_desc = schema.gen_desc()
    instruction_beginning = '我希望你像一个Tugraph数据库前端一样工作，你只需要返回给我cypher语句。下面是一条描述任务的指令，写一条正确的response来完成这个请求.\n"\n##Instruction:\n'
    instruction_end = "\n\n"
    instruction = instruction_beginning + schema_desc + instruction_end
    data_size = 0
    with open(input_path, "r") as file:
        data_size = sum(1 for line in file) / 2

    data_list = [
        {
            "db_id": db_id,
            "instruction": instruction,
            "input": "",
            "output": "",
            "history": [],
        }
        for i in range(int(data_size))
    ]

    with open(input_path, "rb") as file:
        for i, line in enumerate(file, start=0):
            if i != 0:
                index = i - 1
                line = line.strip()
                if index % 2 == 0:
                    data_temp = {"output": line.decode("utf-8")}
                    data_list[int(index / 2)].update(data_temp)
                else:
                    data_temp = {"input": str(line.decode("utf-8"))}
                    data_list[int(index / 2)].update(data_temp)
    cnt = len(data_list)
    json_data = json.dumps(data_list, ensure_ascii=False, indent=4)
    with open(output_path, "a+") as file:
        file.write(json_data)
    print(
        f"prompt and query have been written into JSON file: {output_path}, cnt:{cnt}"
    )

    with open(output_path, "r") as file:
        content = file.read()
    modified_content = content.replace("][", ",")
    with open(output_path, "w") as file:
        file.write(modified_content)


def generate_trainset(config_path, input_dir_or_file=""):
    config = Config(config_path)
    configs = config.get_config("generate_dataset")
    output_path = configs["output_corpus_path"]
    if input_dir_or_file == "":
        input_dir_or_file = configs["input_corpus_dir_or_file"]
    # grammar check
    if os.path.isdir(input_dir_or_file):
        for root, dirs, file_names in os.walk(input_dir_or_file):
            for file_name in file_names:
                input_path = os.path.join(root, file_name)
                file_base, file_extension = os.path.splitext(input_path)
                if file_extension != ".txt":
                    break
                if not grammar_check(input_path):
                    sys.exit()
    elif os.path.isfile(input_dir_or_file):
        if not grammar_check(input_dir_or_file):
            sys.exit()
    else:
        print("[ERROR]: input file is not exsit", input_dir_or_file)
    # generate dataset
    if os.path.isdir(input_dir_or_file):
        for root, dirs, file_names in os.walk(input_dir_or_file):
            for file_name in file_names:
                input_path = os.path.join(root, file_name)
                file_base, file_extension = os.path.splitext(input_path)
                if file_extension != ".txt":
                    break
                generate(config, input_path, output_path)
    elif os.path.isfile(input_dir_or_file):
        generate(config, input_dir_or_file, output_path)


if __name__ == "__main__":
    current_working_directory = os.getcwd()
    config_path = "config.json"
    input_dir_or_file = ""
    if len(sys.argv) > 1:
        config_path = sys.argv[1]
        if len(sys.argv) > 2:
            input_dir_or_file = sys.argv[2]
    generate_trainset(config_path, input_dir_or_file)
