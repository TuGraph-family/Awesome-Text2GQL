from enum import Enum


class Status(Enum):
    GEN_PROMPT_DIRECTLY = (
        100,
        "gen_prompt_directly",
        "generate multi prompts according to input cypher",
    )
    GENERAL_PROMPT_DIRECTLY = (
        200,
        "geneal_prompt_directly",
        "generate multi prompts according to input prompt",
    )
    GENERALIZATION = (
        300,
        "generalization",
        "generate multi prompts according to input cypher and prompt",
    )
    GEN_PROMPT_WITH_KEYWORDS = (
        400,
        "gen_prompt_with_keywords",
        "generate multi prompts according to input cypher and keywords",
    )
    GEN_PROMPT_WITH_TEMPLATE = (
        500,
        "gen_prompt_with_template",
        "# generate multi prompts according to input cypher, tempelate cypher and template prompt",
    )
