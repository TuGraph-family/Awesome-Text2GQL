import json
import os
import sys
import liblgraph_client_python
import re

ROOT_PATH = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(ROOT_PATH)

from typing import Any, Dict, Optional
from dbgpt_hub_gql.llm_base.chat_model import ChatModel
import logging


def logger():
    logger = logging.getLogger("my_logger")
    logger.setLevel(logging.DEBUG)
    file_handler = logging.FileHandler("app.log")
    file_handler.setLevel(logging.DEBUG)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    formatter = logging.Formatter("%(message)s")
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    logging.getLogger("ChatModel").setLevel(logging.WARNING)
    return logger


def inference(model: ChatModel, predict_data: str, **input_kwargs):
    instruction = '我希望你像一个Tugraph数据库前端一样工作，你只需要返回给我cypher语句。下面是一条描述任务的指令，写一条正确的response来完成这个请求.\n"\n##Instruction:\nmovie包含节点person、genre、keyword、movie、user和边acted_in、rate、directed、is_friend、has_genre、has_keyword、produce、write。边acted_in有属性role。边rate有属性stars。\n\n'
    response, _ = model.chat(query=instruction + predict_data, history=[], **input_kwargs)
    return response


def start_predict(model: ChatModel, predict_data):
    result = inference(model, predict_data)
    logger.info(result)
    return result


def print_res(res):
    res = res.replace("{", "\n{")
    res = re.sub(r"\n", "", res, count=1)
    logger.info(f"{res}")


def main():
    cypher = start_predict(model, "")
    logger.info(
        "╔════════════════════════════════════════════════════════════════════════════════════════════════════════════╗ "
    )
    logger.info(
        "║                                 Welocome to TuGraph-DB ChatBot!                                            ║"
    )
    logger.info(
        "║ -----------------------------------------------------------------------------------------------------------║"
    )
    logger.info(
        "║  ████████    ██████                    ██       ████   ████   █████ ██                  ████               ║"
    )
    logger.info(
        "║     ██       ██                        ██       ██  █  █  █   ██    ██             ██   █  █         ██    ║"
    )
    logger.info(
        "║     ██  █  █ ██  ██  ███  █████ ██████ █████    ██   █ █████  ██    █████  █████ ██████ █████ ████ ██████  ║"
    )
    logger.info(
        "║     ██  █  █ ██   ██ █   █   ██ ██   █ █  ██ ██ ██   █ █   █  ██    █  ██ █   ██   ██   █   █ █  █   ██    ║"
    )
    logger.info(
        "║     ██   ██  ██████  █    ███ █ ██████ █  ██    █████  █████  █████ █  ██  ███ █   ███  █████ ████   ███   ║"
    )
    logger.info(
        "║                                 ██                                                                         ║"
    )
    logger.info(
        "║                                 ██                                                                         ║"
    )
    logger.info(
        "║ -----------------------------------------------------------------------------------------------------------║"
    )
    logger.info(
        "║  Hello! I'm ChatBot of Tugraph-DB. I'm so glad to help you ~                                               ║"
    )
    logger.info(
        "║  You can give me a question or an instruction to describe how you want to interact with Tugraph-DB,        ║"
    )
    logger.info(
        "║  and I'll give you the corresponding cypher!                                                               ║"
    )
    logger.info(
        "╚════════════════════════════════════════════════════════════════════════════════════════════════════════════╝"
    )

    while True:
        logger.info("please input your question or instruction：")
        user_input = input()
        cypher = start_predict(model, user_input.lower())
        logger.info("Do you want to execute the cypher now?")
        logger.info("[y/n] :")
        user_input = input()
        if user_input.lower() == "y":
            ret, res = client.callCypher(cypher, "default")
            print_res(res)
        elif user_input.lower() == "exit":
            sys.exit()
        else:
            continue


if __name__ == "__main__":
    client = liblgraph_client_python.client("127.0.0.1:9090", "admin", "73@TuGraph")
    logger = logger()
    model = ChatModel()
    main()
