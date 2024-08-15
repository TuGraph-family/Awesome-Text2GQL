import json

class Config:
    def __init__(self, filepath):
        self.filepath = filepath
        self.config_data = self.load_config()
        self.genQuery=self.config_data.get('genQuery') # 默认是translate翻译生成prompt，还可以设置为genQuery

    def load_config(self):
        with open(self.filepath, 'r') as file:
            return json.load(file)

    def getInputQueryPath(self):
        return self.config_data.get('input_query_path')
    
    def getInputQueryTemplatePath(self):
        return self.config_data.get('input_query_template_path')

    def getschemaDictPath(self):
        return self.config_data.get("schema_dict_path")
    
    def getOutputPath(self):
        if self.genQuery:
            return self.config_data.get("output_query_path")
        else:
            return self.config_data.get("output_prompt_path")
    
    def getDbId(self):
        return self.config_data.get("db_id")
    
    def getSchemaPath(self,db_id):
        schema_dict=self.config_data.get("db_schema_path")
        return schema_dict[db_id]