import json


class Config:
    def __init__(self, file_path):
        self.file_path = file_path
        self.config_data = self.load_config()
        self.genQuery = self.config_data.get(
            "genQuery"
        )  # 默认是translate翻译生成prompt，还可以设置为genQuery
        self.db_id = ""

    def load_config(self):
        with open(self.file_path, "r") as file:
            return json.load(file)

    def getInputQueryPath(self):
        return self.config_data.get("input_query_path")

    def getInputQueryTemplatePath(self):
        return self.config_data.get("input_query_template_path")

    def get_input_corpus_list(self):
        return self.config_data.get("input_corpus_path_list")

    def getOutputPath(self):
        if self.genQuery:
            return self.config_data.get("output_query_path")
        else:
            return self.config_data.get("output_prompt_path")

    def get_output_corpus(self):
        return self.config_data.get("output_corpus_path")

    def getschemaDictPath(self):
        return self.config_data.get("schema_dict_path")

    def getDbId(self):
        return self.db_id

    def getSchemaPath(self, db_id):
        schema_dict = self.config_data.get("db_schema_path")
        return schema_dict[db_id]  # 待完善，判错
