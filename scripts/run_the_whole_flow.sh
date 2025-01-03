#!/bin/bash

OUTPUT_DIR="./output"
if [ ! -d "$OUTPUT_DIR" ]; then
    mkdir -p "$OUTPUT_DIR"
    echo "create output dir: $OUTPUT_DIR"
fi

CONFIG_PATH='./config.json'
GEN_QUERY=true
DB_ID='movie'
#For online model service calling
MODEL_PATH=''
#For local model calling
#Using relative model path or HuggingFace model id
#MODEL_PATH='../Qwen/Qwen2.5-Coder-7B-Instruct'
echo "----------------Running generator.py to generate cyphers----------------"
python3 generator.py "$CONFIG_PATH" "$GEN_QUERY" "$DB_ID"

MODE=400
INPUT_DIR_OR_FILE="./output/output_query.txt"
SUFFIX='_t'
echo "----------------Running generalize_llm.py to GEN_QUESTION_WITH_TEMPLATE----------------"
python3 generalize_llm.py "$MODE" "$INPUT_DIR_OR_FILE" "$OUTPUT_DIR" "$SUFFIX" "$MODEL_PATH"

MODE=300
INPUT_DIR_OR_FILE="./output/output_query_t.txt"
SUFFIX='_general'
echo "----------------Running generalize_llm.py to GENERALIZE with query----------------"
python3 generalize_llm.py "$MODE" "$INPUT_DIR_OR_FILE" "$OUTPUT_DIR" "$SUFFIX" "$MODEL_PATH"

CONFIG_PATH='./config.json'
INPUT_DIR_OR_FILE="./output/output_query_t_general.txt"
echo "----------------make dataset----------------"
python3 generate_dataset.py "$CONFIG_PATH" "$INPUT_DIR_OR_FILE"

