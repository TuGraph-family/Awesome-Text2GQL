#!/bin/bash
CONFIG_PATH='./config.json'
INPUT_DIR_OR_FILE='./input_examples/corpus.txt'

echo "----------------make dataset----------------"
python3 generate_dataset.py "$CONFIG_PATH" "$INPUT_DIR_OR_FILE"