# Awesome-Text2GQL

This is the repository for the text2GQL generator implementation.

## Quick Start
`query_generator.py` : 
Query生成器:解析输入的query并得到抽象语法树AST,对AST进行扩展或剪枝,根据数据库的schema对扩展和剪枝后的AST实例化得到相应的query语句。

`prompt_generator.py`: 
Prompt生成器:对输入的query进行翻译,得到query对应的prompt语句。prompt在生成时按照一定的优先级进行模板匹配，优先匹配整句模板、其次是字句模板，没有对应模板的语句按照逐项翻译得到对应的prompt语句。prompt的生成具有一定的随机性。


`test\test_cypher.py` : 
测试输入的cypher语句的正确性。对输入的cypher语句依次进行语法测试和基于tugraph-db的执行层面的测试。