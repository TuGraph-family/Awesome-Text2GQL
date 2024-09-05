class CorpusPreProcess():
    def __init__(self) -> None:
        self.keywords_to_remove = [
            "提问：",
            "Cypher: ",
            "中文: ",
            "   **Translation:**",
            "**",
            "    -",
            "`",
            ". ",
        ]
        # self.input_path=input_path
        # self.output_path=output_path

    def remove_process(self,raw_prompts):
        prompts = raw_prompts.split('\n')
        output=[]
        for prompt in prompts:
            # remove keywords
            for keyword in self.keywords_to_remove:
                if keyword == ". ": # remove "1."
                    dot_index = prompt.find(". ")
                    if dot_index != -1:
                        prompt = prompt[dot_index + 2 :]
                        continue
                prompt = prompt.replace(keyword, "")
            # remove white space
            prompt = prompt.strip()
            if prompt:
                output.append(prompt)
        return output

    def process(self,raw_prompts):
        prompts=self.remove_process(raw_prompts)
        return prompts