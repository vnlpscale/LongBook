from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

DEFAULT_MODEL = "summerMC/Qwen3.5-9B-Longbook9-GDN32-x2"
MODEL_PRESETS = [
    DEFAULT_MODEL,
    "summerMC/Qwen3.8-27B-Longbook27-VL-GDN64",
]
GGUF_REPO = "summerMC/Qwen3.8-27B-Longbook27-VL-GDN64-GGUF"


def data_directory() -> Path:
    if value := os.getenv("LONGBOOK_DATA_DIR"):
        return Path(value).expanduser().resolve()
    if os.name == "nt":
        base = Path(os.getenv("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
    else:
        base = Path(os.getenv("XDG_DATA_HOME", str(Path.home() / ".local" / "share")))
    return base / "longbook"


def normalize_api_url(value: str, allow_insecure: bool = False) -> str:
    """Accept a base URL, not credentials, query strings, or completion routes."""
    p = urlsplit(value.strip())
    if p.scheme not in {"http", "https"} or not p.hostname:
        raise ValueError("API URL は http(s)://host:port/v1 の形式にしてください。")
    if p.username or p.password or p.query or p.fragment:
        raise ValueError("API URL に認証情報・クエリ・フラグメントは指定できません。")
    if p.scheme == "http" and p.hostname not in {"127.0.0.1", "localhost", "::1"}:
        if not allow_insecure:
            raise ValueError("リモートAPIにはHTTPSが必要です。LAN HTTPは明示的に許可してください。")
    path = p.path.rstrip("/")
    if path.endswith("/chat/completions"):
        path = path.removesuffix("/chat/completions")
    if not path:
        path = "/v1"
    return urlunsplit((p.scheme, p.netloc, path, "", ""))


@dataclass(frozen=True)
class BackendConfig:
    kind: str = "demo"
    model: str = DEFAULT_MODEL
    api_url: str = "http://127.0.0.1:8080/v1"
    api_key: str = field(default="", repr=False)
    revision: str = "main"
    trust_remote_code: bool = False
    quantization: str = "none"
    device: str = "auto"
    allow_insecure_http: bool = False

    def validate(self) -> None:
        if self.kind not in {"demo", "api", "transformers"}:
            raise ValueError("不明なバックエンドです。")
        if not self.model.strip() or len(self.model) > 256:
            raise ValueError("モデルIDを入力してください（最大256文字）。")
        if self.kind == "api":
            normalize_api_url(self.api_url, self.allow_insecure_http)
        if self.quantization not in {"none", "4bit"}:
            raise ValueError("量子化は none または 4bit です。")
        if self.device not in {"auto", "cpu", "cuda"}:
            raise ValueError("deviceはauto/cpu/cudaです。")


@dataclass(frozen=True)
class GenerationOptions:
    max_new_tokens: int = 512
    temperature: float = 0.6
    context_window: int = 8192
    memory_enabled: bool = True

    def validate(self) -> None:
        if not 1 <= self.max_new_tokens <= 4096:
            raise ValueError("最大出力は1〜4096トークンです。")
        if not 0 <= self.temperature <= 2:
            raise ValueError("temperatureは0〜2です。")
        if not 2048 <= self.context_window <= 131072:
            raise ValueError("コンテキスト予算は2048〜131072です。")
        if self.max_new_tokens + 512 >= self.context_window:
            raise ValueError("出力予約が大きすぎます。入力用に512以上残してください。")
