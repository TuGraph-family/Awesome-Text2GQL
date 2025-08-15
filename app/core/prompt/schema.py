'''
Prompt templates of SchemaGenerator
'''

PROMPT = """
You are an expert graph database architect with 15+ years of experience designing schemas for complex domains.
Your specialty is creating performant, intuitive graph models that balance normalization with real-world query needs.
Design a comprehensive graph schema for my target domain. Follow this thinking framework:
"""

INSTRUCTION = """
Schema Description:
{schema_description}

You are a top-tier graph database architect. Please design a professional Schema for the {domain} domain and {subdomain} subdomain base on the Schema Description.

# Critical Format Requirements
1. For VERTEX nodes:
   - Every VERTEX MUST have a dedicated ID property named using the format: `[LABEL]_id` (case-sensitive)
   - "primary" MUST be defined at the SAME LEVEL as "properties", NOT inside properties array
   - Primary key specification format:
     {{
       "label": "Example",
       "type": "VERTEX",
       "properties": [{{ "name": "Example_id", ... }}],  // No primary keys here
       "primary": "Example_id"  // CORRECT: Top-level field
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

Generate_des_prompt = """
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

Generate_des_instruction_template = """
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