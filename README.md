# Awesome-Text2GQL

This is the repository for the text2GQL generator implementation. Awesome-Text2GQL aims to generate cyphers/gqls and corresponding prompts as training corpus for fine-tuning of large language models (LLMs). Based on TuGraph-DB, the training corpus helps to train the Text2GQL and Text2Cypher models that are suitable for TuGraph-DB query engine capabilities.
![框架示意图](./images/框架示意图.jpg)


## Quick Start

Just run ./run.sh

```
pip install -r requirements.txt
sh ./run.sh
```

Change `GEN_QUERY` in the `run.sh` to make sure the generator works at the proper mode you want.

`GEN_QUERY=true` means generating cyphers according to cypher templates in batch.

`GEN_QUERY=false` means generating prompts with the cyphers generated in the last step.

## Attention

This project is under development, suggestions or issues are welcome.