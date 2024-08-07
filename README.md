# Awesome-Text2GQL

This is the repository for the text2GQL generator implementation.

query_generator.py
Query生成器:解析输入的query的抽象语法树AST,对AST进行扩展或剪枝,根据数据库的schemaAST扩展和剪枝后的AST实例化得到相应的query语句。

prompt_generator.py
Prompt生成器:对输入的query进行翻译,得到query对应的prompt语句，一条query可以同时产生多条prompt语句。