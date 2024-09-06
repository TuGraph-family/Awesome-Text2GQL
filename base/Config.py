import json


class Config:
    def __init__(self, file_path):
        self.file_path = file_path
        self.config_data = self.load_config()
        self.gen_query = self.config_data.get(
            "genQuery"
        )  # default translate，can be set as genQuery
        self.db_id = ""

    def load_config(self):
        with open(self.file_path, "r") as file:
            return json.load(file)

    def get_input_query_path(self):
        return self.config_data.get("input_query_path")

    def get_input_query_template_path(self):
        return self.config_data.get("input_query_template_path")

    def get_input_corpus_dir_or_path(self):
        return self.config_data.get("input_corpus_dir_or_path")

    def get_output_path(self):
        if self.gen_query:
            return self.config_data.get("output_query_path")
        else:
            return self.config_data.get("output_prompt_path")

    def get_output_corpus(self):
        return self.config_data.get("output_corpus_path")

    def get_schema_dict_path(self):
        return self.config_data.get("schema_dict_path")

    def get_db_id(self):
        return self.db_id

    def get_schema_path(self, db_id):
        schema_dict = self.config_data.get("db_schema_path")
        return schema_dict[db_id]  # todo error check
