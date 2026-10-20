"""Backend adapters. Importing the UI never imports torch or downloads weights."""
from __future__ import annotations

import gc
import json
import queue
import re
import threading
import time
from collections.abc import Iterator
from typing import Protocol

import httpx

from .config import BackendConfig, GenerationOptions, normalize_api_url
from .context import Message


class Backend(Protocol):
    description: str
    def stream(self, messages: list[Message], options: GenerationOptions,
               cancel: threading.Event) -> Iterator[str]: ...
    def close(self) -> None: ...


class DemoBackend:
    description = "接続確認デモ · モデル推論は未実行"

    def stream(self, messages: list[Message], options: GenerationOptions,
               cancel: threading.Event) -> Iterator[str]:
        query = messages[-1]["content"].split("\n\nUntrusted reference data", 1)[0]
        reply = ("**接続確認デモです。実際のLongBookモデルは動いていません。**\n\n"
                 f"入力を受け取りました：\n\n{query}\n\n"
                 "右側の「接続設定」でAPIまたはTransformersを選び、"
                 "「接続 / モデル読込」を押すと実モデルと会話できます。\n\n"
                 "文書を登録した場合、取得した箇所は「取得した根拠」に表示されます。")
        for start in range(0, len(reply), 10):
            if cancel.is_set():
                return
            time.sleep(0.015)
            yield reply[start:start + 10]

    def close(self) -> None:
        pass


def sse_payloads(lines: Iterator[str]) -> Iterator[str]:
    """Decode SSE records, including comments, multi-line data and an unterminated tail."""
    data: list[str] = []
    for line in lines:
        if not line:
            if data:
                yield "\n".join(data)
                data.clear()
        elif line.startswith("data:"):
            data.append(line[5:].lstrip(" "))
    if data:
        yield "\n".join(data)


class APIBackend:
    def __init__(self, config: BackendConfig, transport: httpx.BaseTransport | None = None):
        self.config = config
        self.url = normalize_api_url(config.api_url, config.allow_insecure_http)
        self.description = f"API · {config.model}"
        # Do not redirect credentials or inherit a process-wide HTTP proxy implicitly.
        self.client = httpx.Client(
            timeout=httpx.Timeout(120, connect=10), follow_redirects=False,
            trust_env=False, transport=transport,
            headers={"Authorization": f"Bearer {config.api_key}"} if config.api_key else {},
        )

    def probe(self) -> str:
        try:
            response = self.client.get(self.url + "/models")
        except httpx.RequestError as exc:
            raise ValueError("APIへ接続できません。推論サーバーの起動とURLを確認してください。") from exc
        if response.status_code in {404, 405}:
            return "モデル一覧APIなし。チャット互換性は最初の生成で確認します。"
        if response.status_code != 200:
            raise ValueError(f"API接続確認失敗（HTTP {response.status_code}）。URLと認証を確認してください。")
        try:
            ids = [item["id"] for item in response.json().get("data", [])]
        except (ValueError, KeyError, TypeError) as exc:
            raise ValueError("/modelsの応答が互換APIの形式ではありません。") from exc
        if self.config.model not in ids:
            return "接続確認済み。指定model IDは一覧にないため、サーバーの別名設定を確認してください。"
        return "接続・model IDを確認しました。生成成功はまだ検証していません。"

    def stream(self, messages: list[Message], options: GenerationOptions,
               cancel: threading.Event) -> Iterator[str]:
        payload = {"model": self.config.model, "messages": messages, "stream": True,
                   "max_tokens": options.max_new_tokens, "temperature": options.temperature}
        try:
            with self.client.stream("POST", self.url + "/chat/completions", json=payload) as r:
                if r.status_code != 200:
                    # Never echo upstream error bodies: they may contain private prompts or keys.
                    raise ValueError(f"生成APIがHTTP {r.status_code}を返しました。"
                                     "model ID・認証・コンテキスト上限を確認してください。")
                if "application/json" in r.headers.get("content-type", ""):
                    try:
                        data = json.loads(r.read())
                        content = data["choices"][0]["message"]["content"]
                        if isinstance(content, str) and content and not cancel.is_set():
                            yield content
                            return
                    except (ValueError, KeyError, IndexError, TypeError) as exc:
                        raise ValueError("生成APIのJSON応答を解釈できません。") from exc
                    raise ValueError("生成APIからテキストが返りませんでした。")
                received = False
                for record in sse_payloads(r.iter_lines()):
                    if cancel.is_set() or record.strip() == "[DONE]":
                        break
                    try:
                        obj = json.loads(record)
                        if "error" in obj:
                            raise ValueError("生成APIがストリーム内エラーを返しました。")
                        choices = obj.get("choices", [])
                        text = choices[0].get("delta", {}).get("content") if choices else None
                    except (json.JSONDecodeError, AttributeError, IndexError, TypeError) as exc:
                        raise ValueError("生成APIのSSE応答形式が不正です。") from exc
                    if isinstance(text, str) and text:
                        received = True
                        yield text
                if not received and not cancel.is_set():
                    raise ValueError("生成テキストがありません。chat/completions互換性を確認してください。")
        except httpx.TimeoutException as exc:
            raise ValueError("APIの応答がタイムアウトしました。サーバー負荷と接続を確認してください。") from exc
        except httpx.RequestError as exc:
            raise ValueError("生成APIとの通信が切れました。") from exc

    def close(self) -> None:
        self.client.close()


class TransformersBackend:
    """Text-only, standard AutoModelForCausalLM contract; custom kernels are not bundled."""
    def __init__(self, config: BackendConfig):
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
        except ImportError as exc:
            raise ValueError("ローカル用依存が未導入です。start.sh --local / start.bat -Local、"
                             "または pip install '.[local]' を実行してください。") from exc
        self.torch = torch
        self.worker: threading.Thread | None = None
        self.model = None
        self.tokenizer = None
        self.resolved_revision = config.revision
        if config.trust_remote_code and not re.fullmatch(r"[0-9a-fA-F]{40}", config.revision):
            raise ValueError("外部モデルコードを許可する場合は40文字のcommit SHAが必要です。"
                             "「revision確認」で取得し、コードを確認してから許可してください。")
        cuda = config.device != "cpu" and torch.cuda.is_available()
        if config.device == "cuda" and not cuda:
            raise ValueError("CUDA対応GPUを検出できませんでした。CPUかAPI接続を選択してください。")
        if config.quantization == "4bit" and not cuda:
            raise ValueError("このハーネスの4bit経路はCUDA専用です。API接続か非量子化を選択してください。")
        dtype = (torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16) if cuda else torch.float32
        common = {"revision": config.revision, "trust_remote_code": config.trust_remote_code}
        if config.trust_remote_code:
            common["code_revision"] = config.revision
        kwargs = dict(common, torch_dtype=dtype, low_cpu_mem_usage=True,
                      device_map="auto" if cuda else "cpu")
        if config.quantization == "4bit":
            kwargs["quantization_config"] = BitsAndBytesConfig(
                load_in_4bit=True, bnb_4bit_compute_dtype=dtype,
                bnb_4bit_quant_type="nf4", bnb_4bit_use_double_quant=True,
            )
        try:
            self.tokenizer = AutoTokenizer.from_pretrained(config.model, **common)
            self.model = AutoModelForCausalLM.from_pretrained(config.model, **kwargs).eval()
            if not self.tokenizer.chat_template:
                raise ValueError("このモデルにchat_templateがありません。モデル側の対応が必要です。")
        except Exception as exc:
            self.close()
            raise ValueError("モデル読込失敗。モデルカードの依存・custom code対応・revision・"
                             f"空きRAM/VRAMを確認してください（{type(exc).__name__}）。") from exc
        self.description = f"Transformers · {config.model} · {'CUDA' if cuda else 'CPU'}"

    @property
    def busy(self) -> bool:
        return self.worker is not None and self.worker.is_alive()

    def count_tokens(self, messages: list[Message]) -> int:
        return len(self.tokenizer.apply_chat_template(messages, tokenize=True,
                                                     add_generation_prompt=True))

    def stream(self, messages: list[Message], options: GenerationOptions,
               cancel: threading.Event) -> Iterator[str]:
        from transformers import StoppingCriteria, StoppingCriteriaList, TextIteratorStreamer
        if self.busy:
            raise ValueError("前のGPU処理がまだ終了していません。終了後に再試行してください。")
        torch = self.torch

        class StopOnCancel(StoppingCriteria):
            def __call__(self, input_ids, scores, **kwargs):
                return cancel.is_set()

        ids = self.tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True)
        device = self.model.get_input_embeddings().weight.device
        input_ids = torch.tensor([ids], dtype=torch.long, device=device)
        streamer = TextIteratorStreamer(self.tokenizer, skip_prompt=True, skip_special_tokens=True,
                                        timeout=1.0)
        errors: list[Exception] = []
        done = threading.Event()
        kwargs = {"input_ids": input_ids, "attention_mask": torch.ones_like(input_ids),
                  "max_new_tokens": options.max_new_tokens,
                  "do_sample": options.temperature > 0, "streamer": streamer,
                  "stopping_criteria": StoppingCriteriaList([StopOnCancel()])}
        if options.temperature > 0:
            kwargs["temperature"] = options.temperature
        pad_id = self.tokenizer.pad_token_id
        if pad_id is None:
            pad_id = self.tokenizer.eos_token_id
        if pad_id is not None:
            kwargs["pad_token_id"] = pad_id

        def generate() -> None:
            try:
                with torch.inference_mode():
                    self.model.generate(**kwargs)
            except Exception as exc:
                errors.append(exc)
                streamer.end()
            finally:
                done.set()

        self.worker = threading.Thread(target=generate, daemon=True, name="longbook-generation")
        self.worker.start()
        started = time.monotonic()
        try:
            while not cancel.is_set():
                if time.monotonic() - started > 600:
                    raise ValueError("生成の上限600秒に達しました。入力長・出力長を減らしてください。")
                try:
                    token = next(streamer)
                    if token:
                        yield token
                except queue.Empty:
                    if done.is_set():
                        break
                    continue
                except StopIteration:
                    break
            if errors:
                raise ValueError("モデル生成失敗。VRAM不足または独自カーネルの非互換の可能性があります"
                                 f"（{type(errors[0]).__name__}）。") from errors[0]
        finally:
            cancel.set()
            self.worker.join(timeout=2)

    def close(self) -> None:
        if self.busy:
            raise ValueError("生成処理中のモデルは解放できません。先に停止してください。")
        self.model = None
        self.tokenizer = None
        gc.collect()
        if self.torch.cuda.is_available():
            self.torch.cuda.empty_cache()
