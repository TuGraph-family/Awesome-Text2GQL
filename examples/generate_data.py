import logging
from pathlib import Path

from app.core.generator.data_generator import DataGenerator

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger("DataGenerator")

def main():
    try:
        schema_file = Path("examples/generated_schemas/geography_5_csv_files_08051006.json")

        logger.info("Creating DataGenerator...")
        data_gen = DataGenerator()
        
        logger.info("Call LLM to generate high-quality data...")
        script_path, csv_files = data_gen.generate_data(schema_file, output_base="examples/generated_data")
        
        logger.info(f"Data generation script saved to: {script_path}")
        logger.info(f"Generated {len(csv_files)} CSV files")
        
        # Print file list
        logger.info("Generated Data Files:")
        for file in csv_files:
            print(f"- {file.name}")
        
        # Display sample data
        for sample_file in csv_files:
            print(f"\nSample data of '{sample_file.name}':")
            with open(sample_file, 'r', encoding='utf-8') as f:
                for i, line in enumerate(f):
                    if i < 5:  # Display first 5 lines
                        print(line.strip())
                    else:
                        break
        
        logger.info("Data generation completed!")
    
    except Exception as e:
        logger.error(f"Program execution failed: {str(e)}", exc_info=True)

if __name__ == "__main__":
    main()