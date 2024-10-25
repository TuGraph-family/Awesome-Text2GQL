from enum import Enum


class Status(Enum):
    GEN_QUESTION_DIRECTLY = (
        100,
        "gen_question_directly",
        "generate multi questions according to input cypher",
    )
    GENERAL_QUESTION_DIRECTLY = (
        200,
        "geneal_question_directly",
        "generate multi questions according to input question",
    )
    GENERALIZATION = (
        300,
        "generalization",
        "generate multi questions according to input cypher and question",
    )
    GEN_QUESTION_WITH_TEMPLATE = (
        400,
        "gen_question_with_template",
        "generate multi questions according to input cypher, tempelate cypher and template question",
    )
