import json
import logging
import datetime
from pathlib import Path
from app.core.generator.schema_generator import (
    BaseSchemaGenerator, 
    SchemaConfig,
    SchemaDescGenerator
)
from app.core.schema.schema_graph import SchemaGraph

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def save_schema_to_file(schema_graph: SchemaGraph, domain: str):
    """将SchemaGraph保存到JSON文件"""
    # 创建输出目录
    output_dir = Path("examples/generated_schemas/")
    output_dir.mkdir(exist_ok=True)
    
    # 文件名
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{domain.replace(' ', '_')}_{timestamp}.json"
    file_path = output_dir / filename
    
    schema_data = []
    
    # 添加节点
    for label, node in schema_graph.node_dict.items():
        node_data = {
            "type": "VERTEX",
            "label": label,
            "properties": node.properties,
            "primary":node.primary
        }
        schema_data.append(node_data)
    
    # 添加边
    for label, edge in schema_graph.edge_dict.items():
        edge_data = {
            "type": "EDGE",
            "label": label,
            "properties": edge.properties,
            "constraints": edge.src_dst_list
        }
        schema_data.append(edge_data)
    
    # 保存到文件
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(schema_data, f, ensure_ascii=False, indent=2)
    
    logger.info(f"Schema已保存到: {file_path}")
    return str(file_path)

def main():
    try:
        domain = "sport"
        subdomain = "hockey"
        schema_desc = SchemaDescGenerator()

        # 调用LLM生成domain_description
        schema_description = schema_desc.generate_schema_description(domain,subdomain)

        # 初始化BaseSchemaGenerator
        generator = BaseSchemaGenerator(
            schema_description = schema_description
        )
        
        # 创建配置类
        config = SchemaConfig(
            complexity_level = 3,  # 复杂度等级(1-5)
            enable_cross_domain = True
        )
        
        # 生成目标domain的Schema
        logger.info("开始生成Schema...")
        schema_graph = generator.generate_schema(domain, subdomain, config)

        logger.info("Schema生成成功！")
        
        
        # 根据SchemaGraph类实现验证逻辑
        try:
            # 假设SchemaGraph有validate方法
            if hasattr(schema_graph, 'validate') and callable(schema_graph.validate):
                if schema_graph.validate():
                    logger.info("Schema验证通过")
                else:
                    logger.warning("Schema验证失败")
            else:
                logger.info("SchemaGraph未实现验证方法，跳过验证")
        except Exception as e:
            logger.warning(f"Schema验证过程中出错: {str(e)}")
        
        # 保存Schema到文件
        # examples\generated_schemas
        saved_path = save_schema_to_file(schema_graph, domain)
        print(f"\nSchema文件路径: {saved_path}")
        
        # 输出Schema信息到控制台
        if hasattr(schema_graph, 'gen_desc') and callable(schema_graph.gen_desc):
            schema_desc = schema_graph.gen_desc()
            print("\n=== Schema describe ===")
            print(schema_desc)
            
    except Exception as e:
        logger.error(f"Filed: {str(e)}", exc_info=True)

if __name__ == "__main__":
    main()