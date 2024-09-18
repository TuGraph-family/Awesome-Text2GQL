# Awesome-Text2GQL

This is the repository for the text2GQL generator implementation. Awesome-Text2GQL aims to generate cyphers/gqls and corresponding prompts as training corpus for fine-tuning of large language models (LLMs). Based on TuGraph-DB, the training corpus helps to train the Text2GQL and Text2Cypher models that are suitable for TuGraph-DB query engine capabilities.

![image](./images/overview.jpg)


## Quick Start

### Preparation

#### Environment

For Linux, it is recommended to use miniconda to manage your python environment while other tools may also work.

```
git clone https://github.com/TuGraph-contrib/Awesome-Text2GQL
cd Awesome-Text2GQL
mkdir output
conda create --name text2gql python=3.10 
conda activate text2gql
```

Install related python dependency packages

```
python setup.py install -v
sh ./run.sh
```

#### Setup for LLMs

To run generating qusetions and generalization functions based on LLMs，apply API-KEY before you run the whole flow.

1. Apply API-KEY

We build the corpus generalization module based on the Qwen Inference Service served by Aliyvn, you can refer to [Aliyvn](https://help.aliyun.com/zh/dashscope/create-and-authorize-a-ram-user?spm=a2c4g.11186623.0.0.4a514bb0RnwdnK) to apply the API-KEY.

2. Set API-KEY via environment variables (recommended)

```
# replace YOUR_DASHSCOPE_API_KEY with your API-KEY
echo "export DASHSCOPE_API_KEY='YOUR_DASHSCOPE_API_KEY'" >> ~/.bashrc
source ~/.bashrc
echo $DASHSCOPE_API_KEY
```

### Run

#### The whole flow

Make sure you have done the preparations above. To experience the whole flow recommended, you can run as below：

```
sh ./scripts/run_the_whole_flow.sh
```

The following steps will be exexcted in sequence:

- generate cyphers by generation module based on Antlr4 with templates as input.
- generate questions by generalization module based on LLMs with the cyphers generated in the last step as input.
- generalize the questions generated in the last step by generalization module based on LLMs.
- transform the corpus generated above into model training format.

#### Run parts seperately

##### Cypher generation

```
sh ./scripts/gen_query.sh
```

The corpus generation module can be run in two modes, that is generating querys by instantiator and generating questions by translator.

Set `GEN_QUERY=true` to generate querys according to templates in batch.

##### Question generation

1. generate questions based on LLMs with template as additional input(recommened)

```
sh ./scripts/gen_question_with_template_llm.sh
```

2. generate questions based on LLMs without template as input. It helps to generate questions which don't have corresponding template initially.

```
sh ./scripts/gen_question_directly_llm.sh
```

3. generate questions based on Antlr4(deprecated)

Set `GEN_QUERY=false`  to generate questions using translator of the generation module based on Antlr4.

```
sh ./scripts/gen_question.sh
```

##### Corpus generalization

1. generalize corpus with query and question as input(recommened)

```
sh ./scripts/generalize_llm.sh
```

2. generalize question without querys as input(deprecated)

```
sh ./scripts/general_questions_directly_llm.sh
```

##### Transform

transform the corpus generated above into model training format.

```
sh ./scripts/generate_dataset.sh
```


## Attention

This project is still under development, suggestions or issues are welcome.