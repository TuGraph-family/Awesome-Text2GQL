from http import HTTPStatus
import random

from dashscope import Generation
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer


class LlmClient:
    def __init__(self, model="", model_path=""):
        self.model = model
        self.model_path = model_path
        self.current_device = None
        self.tokenizer = None
        if model_path != "":
            # check current device
            self.current_device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
            # load tokenizer
            self.tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
            # load model
            self.model = AutoModelForCausalLM.from_pretrained(
                model_path, torch_dtype=torch.float16
            ).to(current_device)

    def call_with_messages(self, messages):
        if self.model_path == "":
            output = self.call_with_messages_online(messages)
        else:
            output = self.call_with_messages_local(messages)
        return output

    def call_with_messages_online(self, messages):
        response = Generation.call(
            model=self.model,
            messages=messages,
            seed=random.randint(1, 10000),
            temperature=0.8,
            top_p=0.8,
            top_k=50,
            result_format="message",
        )
        if response.status_code == HTTPStatus.OK:
            content = response.output.choices[0].message.content
            return content
        else:
            if response.code == 429:  # Requests rate limit exceeded
                self.call_with_messages_online(messages)
            else:
                print(
                    "Request id: %s, Status code: %s, error code: %s, error message: %s"
                    % (
                        response.request_id,
                        response.status_code,
                        response.code,
                        response.message,
                    )
                )
                print("Failed!", messages[1]["content"])
                return ""

    def call_with_messages_local(self, messages):
        # generate content
        inputs = self.tokenizer.apply_chat_template(
            messages, tokenize=True, return_dict=True, return_tensors="pt"
        ).to(self.current_device)

        # add more args
        output = self.model.generate(
            **inputs,
            do_sample=True,
            temperature=0.8,
            top_p=0.8,
            top_k=50,
            pad_token_id=self.tokenizer.eos_token_id,
            eos_token_id=self.tokenizer.eos_token_id,
            max_new_tokens=2048,
        )

        # deal with output and return
        output = self.tokenizer.decode(
            output[0][inputs["input_ids"].shape[1] :], skip_special_tokens=True
        )

        return output


if __name__ == "__main__":
    llm_client = LlmClient(model="qwen-plus-0723")
    messages = [
        {
            "role": "system",
            "content": "",
        },
        {"role": "user", "content": ""},
    ]
    print(llm_client.call_with_messages(messages))
