#!/bin/bash

MODE=400
INPUT_DIR_OR_FILE='./llm_examples/gen_question_llm.txt'
OUTPUT_DIR="./output"
SUFFIX='_t'

echo "----------------Running generalize_llm.py to GEN_PROMPT_WITH_TEMPLATE----------------"
python3 generalize_llm.py "$MODE" "$INPUT_DIR_OR_FILE" "$OUTPUT_DIR" "$SUFFIX"