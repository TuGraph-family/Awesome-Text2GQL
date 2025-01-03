#!/bin/bash

MODE=100
INPUT_DIR_OR_FILE='./input_examples/query_only.txt'
OUTPUT_DIR="./output"
SUFFIX='_gen'
MODEL_PATH='../Qwen/Qwen2.5-Coder-7B-Instruct'

echo "----------------Running generalize_llm.py to GEN_PROMPT_DIRECTLY----------------"
python3 generalize_llm.py "$MODE" "$INPUT_DIR_OR_FILE" "$OUTPUT_DIR" "$SUFFIX" "$MODEL_PATH":
