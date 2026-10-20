from __future__ import annotations

import html
import threading
from collections.abc import Iterator

from .backends import APIBackend, DemoBackend, TransformersBackend
from .config import BackendConfig, GenerationOptions
from .context import pack_context
from .memory import MemoryAdapter


class Runtime:
    """One trusted owner, one loaded model. No cross-user or production isolation claim."""
    def __init__(self, memory: MemoryAdapter):
        self.memory = memory
        self.backend = DemoBackend()
        self.config = BackendConfig()
        self.gate = threading.Lock()
        self.cancel_event = threading.Event()

    def configure(self, config: BackendConfig) -> str:
        config.validate()
        if not self.gate.acquire(blocking=False):
            raise ValueError("生成・読込中です。停止してから設定を変更してください。")
        try:
            self.backend.close()
            self.backend = DemoBackend()
            self.config = BackendConfig()
            note = ""
            if config.kind == "api":
                candidate = APIBackend(config)
                try:
                    note = candidate.probe()
                except Exception:
                    candidate.close()
                    raise
                self.backend = candidate
            elif config.kind == "transformers":
                self.backend = TransformersBackend(config)
            self.config = config
            return self.backend.description + (f"\n{note}" if note else "")
        finally:
            self.gate.release()

    def cancel(self) -> None:
        self.cancel_event.set()

    def stream(self, query: str, history: list[dict], options: GenerationOptions,
               system_prompt: str = "") -> Iterator[tuple[str, str]]:
        options.validate()
        if not self.gate.acquire(blocking=False):
            raise ValueError("別の生成・モデル読込が進行中です。")
        self.cancel_event.clear()
        try:
            evidence = self.memory.search(query, limit=4) if options.memory_enabled else []
            count = getattr(self.backend, "count_tokens", None)
            packed = pack_context(query, history, evidence,
                                  options.context_window - options.max_new_tokens - 256,
                                  count=count, extra_system=system_prompt)
            # An actual tokenizer is used locally; API estimates are explicitly labeled.
            units = "実トークン" if packed.exact_tokens else "UTF-8バイト基準の保守的推定値"
            lines = [f"入力: {packed.input_units:,} ({units}) · "
                     f"予算から省いた履歴: {packed.omitted_messages}件"]
            if packed.evidence:
                for i, e in enumerate(packed.evidence, 1):
                    lines.append(f"\n**[M{i}] {html.escape(e.source)}** · 文字位置 "
                                 f"{e.start_char}–{e.end_char} · `{e.id}`\n\n"
                                 f"<blockquote>{html.escape(e.text)}</blockquote>")
            else:
                lines.append("\n該当する根拠は取得されていません。")
            refs = "\n".join(lines)
            output = ""
            yield output, refs
            iterator = self.backend.stream(packed.messages, options, self.cancel_event)
            try:
                for piece in iterator:
                    if self.cancel_event.is_set():
                        break
                    output += piece
                    yield output, refs
            finally:
                iterator.close()
        finally:
            self.cancel_event.set()
            self.gate.release()
