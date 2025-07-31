from abc import ABC, abstractmethod
import json
from typing import Dict, List
from venv import logger
from app.core.llm.llm_client import LlmClient
from app.core.schema.edge import Edge
from app.core.schema.node import Node
from app.core.schema.schema_graph import SchemaGraph

PROMPT = """
You are an expert graph database architect with 15+ years of experience designing schemas for complex domains.
Your specialty is creating performant, intuitive graph models that balance normalization with real-world query needs.
Design a comprehensive graph schema for my target domain. Follow this thinking framework:
"""

INSTRUCTION_TEMPLATE = """
Schema Description:
{schema_description}

You are a top-tier graph database architect. Please design a professional Schema for the {domain} domain and {subdomain} subdomain base on the Schema Description.

# Critical Format Requirements
1. For VERTEX nodes:
   - "primary" MUST be defined at the SAME LEVEL as "properties", NOT inside properties array
   - Primary key specification format:
     {{
       "label": "Example",
       "type": "VERTEX",
       "properties": [{{ "name": "id", ... }}],  // No primary keys here
       "primary": "id"  // CORRECT: Top-level field
     }}

2. For EDGE relationships:
   - Only ONE entry per relationship type
   - Multiple constraints MUST be consolidated into SINGLE "constraints" array
   - Correct constraints format:
     "constraints": [
       ["StartLabel", "EndLabel"],
       ["AltStart", "AltEnd"]
     ]

# Task Requirements
1. Include {min_nodes}-{max_nodes} node types
2. Include {min_rels}-{max_rels} relationship types
3. Strict schema format compliance:
    schema (array)
    label (required, string)
    type (required: only VERTEX/EDGE)
    properties (array, required for vertices)
      name (required, string)
      type (required: BOOL,INT8,INT16,INT32,INT64,DATE,DATETIME,FLOAT,DOUBLE,STRING,BLOB)
      optional (optional)
      index (optional)
      unique (optional)
      pair_unique (optional)
    primary (VERTEX ONLY, REQUIRED, TOP-LEVEL FIELD)
    temporal (EDGE ONLY, optional)
    temporal_field_order (EDGE ONLY, optional, default "ASC")
    constraints (EDGE ONLY, optional, array of label pairs)
    detach_property (optional, default false)

# Prohibited Patterns
NEVER include "primary" inside properties array
NEVER create multiple entries for same edge type
NEVER combine unique/pair_unique in same property

# Output Example
{example_json}

# Compliance Verification
Before final output, self-check:
1. Every VERTEX has top-level "primary"
   - Each node type must have EXACTLY ONE primary key property
   - Primary key must be specified as a SINGLE property name (no comma-separated values)
   - Format: "primary": "<single_property_name>"
   - Multi-property keys are PROHIBITED in this context
2. Every EDGE has SINGLE entry with consolidated constraints
3. ZERO "primary" in properties arrays
4. Naming Consistency Requirement:
   - Use UPPER_SNAKE_CASE for ALL node labels (e.g., MEDIA_OUTLET)
   - Use PascalCase for relationship types (e.g., PublishedBy)
   - Maintain EXACT case consistency across all schema elements
5. Case-Sensitive Enforcement:
   - If a node is defined as A_NODE, it must ALWAYS be referenced as A_NODE (not Anode or a_node)
   - Apply the same naming convention to all related elements
6. Validation Protocol:
   - Before finalizing, verify all node label references match their original definitions exactly
   - Cross-check every relationship's source/target nodes against defined node labels
"""

class SchemaConfig:
    """Schema生成配置参数"""
    def __init__(self, 
                 complexity_level: int = 3, 
                 enable_cross_domain: bool = True):
        """
        :param complexity_level: 复杂度等级 (1-5)
        :param enable_cross_domain: 是否启用跨领域链接
        """
        self.complexity_level = complexity_level
        self.enable_cross_domain = True

class ISchemaGenerator(ABC):
    """Schema生成器抽象基类"""
    @abstractmethod
    def generate_schema(self, domain: str, subdomain: str, config: SchemaConfig = None) -> SchemaGraph:
        """
        生成指定领域的图数据库Schema
        :param domain: 领域描述 (e.g., "金融风控", "社交网络")
        :param subdomain: 子领域描述
        :param config: Schema配置参数
        :return: 生成的Schema图对象
        """
        pass

class BaseSchemaGenerator(ISchemaGenerator):
    """基于LLM的基础Schema生成器"""
    def __init__(self, schema_description: str = ""):
        self._llm_client = LlmClient(model="qwen-plus-0723")
        self._schema_description = schema_description  # 存储描述，稍后使用
    
    def _calc_node_range(self, complexity: int) -> tuple:
        """根据复杂度计算节点数量范围"""
        return {
            1: (3, 5),
            2: (5, 8),
            3: (8, 12),
            4: (12, 18),
            5: (18, 25)
        }.get(complexity, (5, 10))
    
    def _calc_relationship_range(self, complexity: int) -> tuple:
        """根据复杂度计算关系数量范围"""
        return {
            1: (2, 4),
            2: (4, 7),
            3: (7, 12),
            4: (12, 20),
            5: (20, 35)
        }.get(complexity, (4, 8))

    def generate_schema(self, domain: str, subdomain: str, config: SchemaConfig = None) -> SchemaGraph:
        config = config or SchemaConfig()
        
        node_range = self._calc_node_range(config.complexity_level)
        rel_range = self._calc_relationship_range(config.complexity_level)
        
        EXAMPLE_JSON = """
        [
            {
                "label": "Customer",
                "type": "VERTEX",
                "properties": [
                    {
                        "name": "id",
                        "type": "STRING",
                        "optional": false,
                        "unique": true,
                        "index": true
                    },
                    {
                        "name": "name",
                        "type": "STRING",
                        "optional": false
                    },
                    ...
                ],
                "primary": "id"
            },
            {
                "label": "Account",
                "type": "VERTEX",
                "properties": [
                    {
                        "name": "account_id",
                        "type": "STRING",
                        "optional": false,
                        "unique": true,
                        "index": true
                    },
                    ...
                ],
                "primary": "account_id"
            },
            ...
            {
                "label": "OWNS",
                "type": "EDGE",
                "properties": [
                    {
                        "name": "ownership_percent",
                        "type": "FLOAT",
                        "optional": false
                    }
                ],
                "constraints": [
                    [
                        "Customer",
                        "Account"
                    ]
                ]
            },
            ...
        ]
        """

        # 一次性替换所有占位符
        INSTRUCTION = INSTRUCTION_TEMPLATE.format(
            schema_description=self._schema_description,
            domain=domain,
            subdomain=subdomain,
            example_json=EXAMPLE_JSON,
            min_nodes=node_range[0],
            max_nodes=node_range[1],
            min_rels=rel_range[0],
            max_rels=rel_range[1]
        )
        
        logger.debug(f"生成的提示词:\n{INSTRUCTION}")
        messages = [
            {
                "role": "system",
                "content": PROMPT,
            },
            {"role": "user", "content": INSTRUCTION},
        ]
        response = self._llm_client.call_with_messages(messages)
        logger.debug(f"LLM原始响应:\n{response}")
        print(f"LLM原始响应:\n{response}")
        
        schema_json = self._parse_llm_response(response)
        
        # 创建SchemaGraph实例并填充数据
        return self._build_schema_graph(domain, schema_json)
    
    def _parse_llm_response(self, response: str) -> list:
        """提取并解析LLM返回的JSON数据"""
        try:
            # 尝试直接解析整个响应
            return json.loads(response)
        except json.JSONDecodeError:
            try:
                # 尝试提取代码块中的JSON
                start_idx = response.find('[')
                end_idx = response.rfind(']') + 1
                json_str = response[start_idx:end_idx]
                return json.loads(json_str)
            except (ValueError, IndexError, json.JSONDecodeError) as e:
                logger.error(f"LLM响应解析失败: {e}\n响应内容: {response[:500]}...")
                raise SchemaParseError("无法解析LLM返回的Schema数据") from e

    def _build_schema_graph(self, domain: str, schema_data: List[Dict]) -> SchemaGraph:
        """将LLM生成的JSON数据转换为SchemaGraph实例"""
        schema_graph = SchemaGraph(db_id=domain)
        
        # 先处理所有节点
        node_map = {}
        for item in schema_data:
            if item["type"] == "VERTEX":
                node = Node(
                    label=item["label"],
                    properties=item["properties"],
                    # 添加Primary属性
                    primary=item["primary"]
                )
                schema_graph.add_node(node)
                node_map[item["label"]] = node
        
        # 再处理所有边
        for item in schema_data:
            if item["type"] == "EDGE":
                # 提取源和目标节点标签
                src_dst_list = []
                for constraint in item.get("constraints", []):
                    if len(constraint) == 2:
                        src_label, dst_label = constraint
                        src_dst_list.append([src_label, dst_label])
                
                edge = Edge(
                    label=item["label"],
                    src_dst_list=src_dst_list,
                    properties=item.get("properties", [])
                )
                schema_graph.add_edge(edge)
        
        return schema_graph

class SchemaParseError(Exception):
    """自定义异常：用于Schema解析错误"""
    pass

class SchemaDescGenerator():
    def __init__(self):
        self._llm_client = LlmClient(model="qwen-plus-0723")
        self._PROMPT = """
You are a business domain modeling specialist with expertise in graph-based knowledge representation. Your task is to create detailed documentation for graph schemas that accurately model real-world subdomains. For each request:

1. Provide comprehensive analysis of the business context
2. Design semantically meaningful node and relationship types
3. Explain interaction patterns and business significance
4. Include real-world usage scenarios
5. Maintain technical accuracy while being accessible to both business and technical stakeholders

Structure your response with these sections:
1. Subdomain Introduction
2. Core Node Types (Entities)
3. Relationship Types (Connections)
4. Schema Diagram (using Mermaid syntax)
5. Business Rules & Constraints
6. Example Usage Scenarios
"""
        self._INSTRUCTION_TEMPLATE = """
Generate a complete graph schema documentation for:

Domain: {domain}
Subdomain: {subdomain}
Key Business Requirements:
1. [Critical business objective #1]
2. [Important operational constraint #2]
3. [Key data interaction pattern #3]

**Specific Context Details**:
- Industry: [e.g., Healthcare, FinTech]
- Scale: [e.g., 100K daily transactions]
- Critical Relationships: [e.g., Regulatory dependencies]
- Special Constraints: [e.g., Privacy compliance needs]

**Output Requirements**:
- Use business-friendly terminology
- Include 4-6 core node types
- Define 3-5 relationship types with clear semantics
- Provide Mermaid diagram for visualization
- Explain how schema supports business requirements
"""

    def generate_schema_description(self,domain:str, subdomain:str) -> str:

        INSTRUCTION = self._INSTRUCTION_TEMPLATE.format(
            domain=domain,
            subdomain=subdomain
        )
        messages = [
            {
                "role": "system",
                "content": self._PROMPT,
            },
            {"role": "user", "content": INSTRUCTION},
        ]
        response = self._llm_client.call_with_messages(messages)
        return response

class NodeType:
    def __init__(self, name, properties=None):
        self.name = name
        self.properties = properties or []

    @classmethod
    def from_dict(cls, data):
        return cls(
            name=data.get("name"),
            properties=[Property.from_dict(p) for p in data.get("properties", [])]
        )

class RelationshipType:
    def __init__(self, name, source, target, properties=None, cardinality="MANY_TO_MANY"):
        self.name = name
        self.source = source
        self.target = target
        self.properties = properties or []
        self.cardinality = cardinality

class Property:
    def __init__(self, name, type_, constraints=None):
        self.name = name
        self.type = type_
        self.constraints = constraints or []

    @classmethod
    def from_dict(cls, data):
        return cls(
            name=data.get("name"),
            type_=data.get("type"),
            constraints=data.get("constraints", [])
        )

