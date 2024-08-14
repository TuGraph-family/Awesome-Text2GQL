import json

class Config:
    def __init__(self, filepath):
        self.filepath = filepath
        self.config_data = self.load_config()
        self.workMode=self.config_data.get('work_mode') # 默认是translate-翻译生成prompt，还可以设置为genQuery
        assert(self.workMode!='translate' or self.workMode!='genQuery')

    def load_config(self):
        with open(self.filepath, 'r') as file:
            return json.load(file)

    def getInputQueryPath(self):
        return self.config_data.get('input_query_path')
    
    def getInputQueryTemplatePath(self):
        return self.config_data.get('input_query_template_path')
     
    def getschemaDictPath(self):
        return self.config_data.get("schema_dict_path")
    
    # def get_database_config(self):
    #     return self.config_data.get('database', {})

    # def get_api_config(self):
    #     return self.config_data.get('api', {})
    

# # 使用Config类
# config = Config('config.json')

# # 获取数据库配置信息
# database_config = config.get_database_config()
# print(f"Database Host: {database_config.get('host')}")
# print(f"Database Port: {database_config.get('port')}")

# # 获取API配置信息
# api_config = config.get_api_config()
# print(f"API URL: {api_config.get('url')}")
# print(f"API Token: {api_config.get('token')}")
