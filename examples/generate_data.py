import json
import logging
from pathlib import Path
from app.core.generator.data_generator import DataGenerator

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger("DataGeneratorDemo")

def load_schema_json(schema_file: str) -> str:
    """从文件加载Schema JSON"""
    logger.info(f"加载Schema文件: {schema_file}")
    with open(schema_file, 'r', encoding='utf-8') as f:
        return json.dumps(json.load(f), ensure_ascii=False)

def main():
    try:
        # 列出可用Schema文件
        schema_dir = Path("examples/generated_schemas/")
        if not schema_dir.exists():
            logger.error("没有找到Schema目录，请先生成Schema")
            return
            
        files = list(schema_dir.glob("*.json"))
        if not files:
            logger.error("没有找到Schema文件，请先生成Schema")
            return
            
        print("\n可用的Schema文件:")
        for i, file in enumerate(files, 1):
            print(f"{i}. {file.name}")
            
        choice = int(input("请选择Schema文件编号: ").strip())
            
        schema_file = str(files[choice-1])
        schema_json = load_schema_json(schema_file)

        # 创建数据生成器
        logger.info("创建数据生成器...")
        data_gen = DataGenerator(schema_json, output_base="examples/generated_data")
        
        # 使用LLM生成高质量测试数据
        logger.info("使用LLM生成高质量测试数据...")
        script_path, csv_files = data_gen.generate_test_data()
        
        logger.info(f"数据生成脚本已保存到: {script_path}")
        logger.info(f"生成的CSV文件: {len(csv_files)}个")
        
        # 打印文件列表
        print("\n=== 生成的数据文件 ===")
        for file in csv_files:
            print(f"- {file.name}")
        
        # 显示部分数据
        if csv_files:
            sample_file = csv_files[0]
            print(f"\n文件 '{sample_file.name}' 示例数据:")
            with open(sample_file, 'r', encoding='utf-8') as f:
                for i, line in enumerate(f):
                    if i < 5:  # 显示前5行
                        print(line.strip())
                    else:
                        break
        
        logger.info("数据生成完成！")
    
    except Exception as e:
        logger.error(f"程序执行失败: {str(e)}", exc_info=True)

if __name__ == "__main__":
    main()