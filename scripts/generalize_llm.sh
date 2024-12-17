#!/bin/bash

MODE=300
INPUT_DIR_OR_FILE='./input_examples/corpus.txt'
OUTPUT_DIR="./output"
SUFFIX='_general'
MODEL_PATH='../Qwen__Qwen2.5-Coder-14B-Instruct'

echo "----------------Running generalize_llm.py to GENERALIZE with query----------------"
python3 generalize_llm.py "$MODE" "$INPUT_DIR_OR_FILE" "$OUTPUT_DIR" "$SUFFIX" "$MODEL_PATH"
