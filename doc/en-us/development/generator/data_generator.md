# Data Generator

The example of how data generator operate is demonstrated at `examples/generate_data.py`.

It requires three input variables, `schema_file`, and `output_base` to ask LLM to generate a python script,then the script will generate synthesis data in csv format on the given schema. The ultimate goal is to create an importable data folder.

The current data generator requires the input file to be JSON format, might need some modification to be comopatible with SQL DDL format.

In the TuGraph case, it requires an import.config file to import data into database engine, which contains schema information and projections between nodes/edges to the specific CSV files. We add a `generate_import_config` function to do this in the example. The situation for Oracle or other relational databases might be different and requires modification.