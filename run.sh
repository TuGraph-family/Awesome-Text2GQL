#!/bin/bash

# CONFIG_PATH='/root/work_repo/Awesome-Text2GQL/config.json'
CONFIG_PATH='./config.json'
GEN_QUERY=true
DB_ID='movie'

echo "----------------Running generator.py to generate cyphers----------------"
python3 generator.py "$CONFIG_PATH" "$GEN_QUERY" "$DB_ID"

GEN_QUERY=false
echo "----------------Running generator.py to generate prompts----------------"
python3 generator.py "$CONFIG_PATH" "$GEN_QUERY" "$DB_ID"

echo "----------------make dataset----------------"
python3 generate_dataset.py "$CONFIG_PATH"