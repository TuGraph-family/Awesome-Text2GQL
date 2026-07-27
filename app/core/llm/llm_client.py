from http import HTTPStatus
import json
import os
import random
import time

from dashscope import Generation
import openai
from openai import OpenAI, OpenAIError
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer


class LlmClient:
    def __init__(self, model="", model_path="", platform=""):
        self.model = model
        self.model_path = model_path
        self.current_device = None
        self.tokenizer = None

        platform_form_env = os.getenv("LLM_PLATFORM")
        if platform != "":
            self.platform = platform
        elif platform_form_env is not None:
            self.platform = platform_form_env
        else:
            self.platform = "dashscope"
        if model_path != "":
            # check current device
            self.current_device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
            # load tokenizer
            self.tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
            # load model
            self.model = AutoModelForCausalLM.from_pretrained(
                model_path, torch_dtype=torch.float16
            ).to(self.current_device)

    def call_with_messages(self, messages):
        if self.model_path == "":
            output = self.call_with_messages_online(messages)
        else:
            output = self.call_with_messages_local(messages)
        return output

    def call_with_messages_online(self, messages):
        if self.platform == "openai":
            return self.call_with_messages_online_for_openai(messages)
        elif self.platform == "dashscope":
            return self.call_with_messages_online_for_dashscope(messages)
        else:
            print(f"Unsupposed platform:{self.platform}")
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

    def call_with_messages_online_for_openai(self, messages):
        try:
            client_kwargs = {
                "api_key": os.getenv("OPENAI_API_KEY"),
                "base_url": os.getenv("OPENAI_BASE_URL"),
            }
            default_headers = self._openai_default_headers()
            if default_headers:
                client_kwargs["default_headers"] = default_headers

            openai_client = OpenAI(**client_kwargs)
            response = openai_client.chat.completions.create(
                model=self.model, messages=messages, temperature=0
            )
            return self._extract_openai_chat_content(response)
        except openai.RateLimitError:
            print("there are too many request,ready to retry in 1 second")
            time.sleep(1)
            print("begin to retry")
            return self.call_with_messages_online_for_openai(messages)
        except OpenAIError as exc:
            print(
                "OpenAI-compatible LLM call failed: "
                f"{type(exc).__name__}: {exc}"
            )
            return ""

    def _extract_openai_chat_content(self, response) -> str:
        if isinstance(response, str):
            stream_content = self._extract_openai_sse_content(response)
            if stream_content:
                return stream_content
            try:
                response = json.loads(response)
            except json.JSONDecodeError:
                preview = response[:500].replace("\n", "\\n")
                print(
                    "OpenAI-compatible LLM returned a raw string instead of a "
                    f"chat completion object: {preview}"
                )
                return response

        if isinstance(response, dict):
            choices = response.get("choices") or []
            if choices:
                message = choices[0].get("message") or {}
                content = message.get("content")
                if content is not None:
                    return content
            preview = json.dumps(response, default=str)[:500]
            print(f"OpenAI-compatible LLM returned unexpected JSON: {preview}")
            return ""

        try:
            return response.choices[0].message.content or ""
        except (AttributeError, IndexError, KeyError, TypeError) as exc:
            preview = repr(response)[:500]
            print(
                "OpenAI-compatible LLM returned an unexpected response type "
                f"({type(response).__name__}): {preview}; parse error: {exc}"
            )
            return ""

    def _extract_openai_sse_content(self, response_text: str) -> str:
        if not response_text.lstrip().startswith("data:"):
            return ""

        content_parts: list[str] = []
        for line in response_text.splitlines():
            line = line.strip()
            if not line.startswith("data:"):
                continue

            payload = line.removeprefix("data:").strip()
            if not payload or payload == "[DONE]":
                continue

            try:
                event = json.loads(payload)
            except json.JSONDecodeError:
                continue

            for choice in event.get("choices", []):
                delta = choice.get("delta") or {}
                if delta.get("content"):
                    content_parts.append(delta["content"])

                message = choice.get("message") or {}
                if message.get("content"):
                    content_parts.append(message["content"])

                if choice.get("text"):
                    content_parts.append(choice["text"])

        if not content_parts:
            preview = response_text[:500].replace("\n", "\\n")
            print(f"OpenAI-compatible LLM returned an empty SSE stream: {preview}")
            return ""
        return "".join(content_parts)

    def _openai_default_headers(self) -> dict[str, str]:
        raw_headers = os.getenv("OPENAI_EXTRA_HEADERS") or os.getenv("OPENAI_HTTP_HEADERS")
        if not raw_headers:
            return {}
        try:
            parsed = json.loads(raw_headers)
        except json.JSONDecodeError as exc:
            print(f"Invalid OPENAI_EXTRA_HEADERS JSON: {exc}")
            return {}
        if not isinstance(parsed, dict):
            print("OPENAI_EXTRA_HEADERS must be a JSON object.")
            return {}
        return {str(key): str(value) for key, value in parsed.items()}

    def call_with_messages_online_for_dashscope(self, messages):
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
                print(
                    f"Request id: {response.request_id}, Status code: {response.status_code}"
                    + f", error code: {response.code}, error message: {response.message}"
                    + "too many request,ready to retry in 1 second "
                )
                time.sleep(1)
                print(f"Request id: {response.request_id}, begin to retry")
                return self.call_with_messages_online_for_dashscope(messages)
            else:
                print(
                    f"Request id: {response.request_id}, Status code: {response.status_code}"
                    + f", error code: {response.code}, error message: {response.message}"
                )
                print("Failed!", messages[1]["content"])
                return ""


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
