#!/bin/bash

MODE=200
INPUT_DIR_OR_FILE='./llm_examples/corpus.txt'
OUTPUT_DIR="./output"
SUFFIX='_general'

echo "----------------Running generalize_llm.py to GENERAL_PROMPT_DIRECTLY----------------"
python3 generalize_llm.py "$MODE" "$INPUT_DIR_OR_FILE" "$OUTPUT_DIR" "$SUFFIX"