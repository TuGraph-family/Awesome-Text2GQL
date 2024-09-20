#!/bin/bash

CONFIG_PATH='./config.json'
GEN_QUERY=false
DB_ID='movie'

echo "----------------Running generator.py to generate cyphers----------------"
python3 generator.py "$CONFIG_PATH" "$GEN_QUERY" "$DB_ID"