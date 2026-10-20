from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

# Set before importing Gradio. No analytics, remote fonts, or telemetry are needed.
os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("GRADIO_RUN_HISTORY", "False")

import gradio as gr

from .config import BackendConfig, DEFAULT_MODEL, GenerationOptions, MODEL_PRESETS, data_directory
from .context import normalize_history
from .memory import ALLOWED_SUFFIXES, SQLiteMemory
from .runtime import Runtime

BRAND = """<div class="brand"><svg width="28" height="28" viewBox="0 0 28 28"
fill="none" aria-hidden="true"><path d="M4 5.5C8 4 11 5 14 7.5C17 5 20 4 24 5.5V22
C20 20.5 17 21 14 23C11 21 8 20.5 4 22V5.5Z" stroke="currentColor" stroke-width="1.7"
stroke-linejoin="round"/><path d="M14 8V22" stroke="currentColor" stroke-width="1.7"/></svg>
<span>LongBook</span><span class="brand-caption">あなたのための、思考のワークスペース</span></div>"""
WELCOME = """<div class="welcome"><div class="welcome-mark">L.</div>
<h1>何から始めますか？</h1><p>対話する。文書から探す。考えを深める。</p>
<p class="welcome-note">最初は接続確認デモです。右上の接続設定から実モデルへ切り替えられます。</p></div>"""


def create_app(data_dir: Path | None = None):
    data_dir = data_dir or data_directory()
    memory = SQLiteMemory(data_dir / "memory.sqlite3")
    runtime = Runtime(memory)

    def configure(kind, model, url, key, revision, trust, quantization, device, insecure):
        config = BackendConfig(
            kind=kind, model=model.strip(), api_url=url,
            api_key=key or os.getenv("LONGBOOK_API_KEY", ""),
            revision=revision.strip() or "main", trust_remote_code=trust,
            quantization=quantization, device=device, allow_insecure_http=insecure,
        )
        try:
            note = runtime.configure(config)
            return note, "**" + runtime.backend.description + "**"
        except Exception as exc:
            # Keep the status accurate after a failed model switch; never echo a key.
            message = str(exc)
            for secret in (key, os.getenv("LONGBOOK_API_KEY", "")):
                if secret:
                    message = message.replace(secret, "[redacted]")
            return "設定失敗: " + message, "**" + runtime.backend.description + "**"

    def unload():
        try:
            note = runtime.configure(BackendConfig())
            return note, "**" + note + "**"
        except ValueError as exc:
            raise gr.Error(str(exc)) from exc

    def resolve_revision(model, revision):
        from huggingface_hub import HfApi
        try:
            info = HfApi().model_info(model.strip(), revision=revision.strip() or "main")
            return info.sha, "取得したSHAを固定します。Filesタブでコードを確認してから外部コードを許可してください。"
        except Exception as exc:
            raise gr.Error("revisionを取得できません。モデルID・公開状態・ネット接続を確認してください。") from exc

    def generate(message, history, max_tokens, temperature, window, use_memory, system):
        try:
            options = GenerationOptions(int(max_tokens), float(temperature), int(window), use_memory)
            yield from runtime.stream(message, history, options, system)
        except Exception as exc:
            error = str(exc)
            if runtime.config.api_key:
                error = error.replace(runtime.config.api_key, "[redacted]")
            raise gr.Error(error) from exc

    def ingest(files):
        messages = []
        for file in (files or [])[:20]:
            try:
                _, created = memory.add_file(file)
                messages.append(f"{Path(file).name}: {'登録しました' if created else '登録済みです'}")
            except ValueError as exc:
                messages.append(f"{Path(file).name}: {exc}")
        stats = memory.stats()
        messages.append(f"合計 {stats['documents']}文書 / {stats['chunks']}チャンク")
        return "\n".join(messages), gr.Dropdown(choices=memory.list_documents(), value=None)

    def delete_document(document_id):
        if document_id:
            memory.delete(document_id)
        return "選択文書を削除しました。", gr.Dropdown(choices=memory.list_documents(), value=None)

    def export_chat(history):
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".json",
                                         prefix="longbook-chat-", delete=False) as f:
            json.dump({"format": "longbook-chat-v1", "messages": normalize_history(history)},
                      f, ensure_ascii=False, indent=2)
        return gr.File(value=f.name, visible=True)

    with gr.Blocks(title="LongBook", fill_height=True, fill_width=True,
                   analytics_enabled=False, delete_cache=(3600, 3600)) as demo:
        with gr.Row(elem_id="app-header"):
            gr.HTML(BRAND, scale=8, min_width=230)
            open_settings = gr.Button("接続設定", scale=0, min_width=110, elem_id="open-settings")
        live_status = gr.Markdown("**接続確認デモ · モデル推論は未実行**", elem_id="live-status")

        with gr.Sidebar(label="設定", position="right", open=False, width=360) as sidebar:
            gr.Markdown("## ワークスペース設定")
            with gr.Tabs():
                with gr.Tab("モデル"):
                    kind = gr.Dropdown(
                        [("接続確認デモ（モデルなし）", "demo"),
                         ("API接続（GGUFサーバーなど）", "api"),
                         ("Transformers（ローカル・実験）", "transformers")],
                        value=os.getenv("LONGBOOK_BACKEND", "demo"), label="実行方式")
                    model = gr.Dropdown(MODEL_PRESETS, value=os.getenv("LONGBOOK_MODEL", DEFAULT_MODEL),
                                        allow_custom_value=True, label="モデルID / サーバーのmodel名")
                    url = gr.Textbox(value=os.getenv("LONGBOOK_API_URL", "http://127.0.0.1:8080/v1"),
                                     label="API Base URL")
                    key = gr.Textbox(type="password", label="APIキー（必要な場合のみ）",
                                     placeholder="未入力ならサーバー環境変数を使用")
                    insecure = gr.Checkbox(False, label="LANのHTTPを許可（通信は暗号化されません）")
                    with gr.Accordion("ローカルモデルの詳細", open=False):
                        revision = gr.Textbox(value="main", label="Hugging Face revision / commit SHA")
                        resolve_btn = gr.Button("revision確認（コードは実行しません）")
                        revision_note = gr.Textbox(label="revision情報", interactive=False)
                        trust = gr.Checkbox(False, label="確認した外部Pythonコードの実行を許可")
                        gr.Markdown("独自コードを実行する場合は**40文字のcommit SHA固定**が必要です。"
                                    "チェックだけで安全性が保証されるわけではありません。")
                        device = gr.Dropdown(["auto", "cpu", "cuda"], value="auto", label="デバイス")
                        quantization = gr.Dropdown([("非量子化", "none"), ("4bit / CUDA", "4bit")],
                                                   value="none", label="量子化")
                    connect = gr.Button("接続 / モデル読込", variant="primary")
                    unload_btn = gr.Button("モデルを解放してデモへ戻る")
                    connection_note = gr.Textbox(value="モデルはまだダウンロードしていません。",
                                                 label="接続結果", interactive=False, lines=3)
                    with gr.Accordion("生成パラメータ", open=False):
                        max_tokens = gr.Slider(128, 4096, value=512, step=128, label="最大出力トークン")
                        temperature = gr.Slider(0, 2, value=0.6, step=0.05, label="Temperature")
                        window = gr.Dropdown([2048, 4096, 8192, 16384, 32768, 65536, 131072],
                                             value=8192, label="モデルの入力＋出力予算")
                        system = gr.Textbox(label="追加システム指示", lines=3,
                                            placeholder="例：日本語で、数式と具体例を交えて説明してください。")
                        gr.Markdown("API側ではトークン数を保守的に推定します。"
                                    "予算を増やしてもモデル自体の上限は増えません。")
                with gr.Tab("メモリ"):
                    use_memory = gr.Checkbox(True, label="登録文書から根拠を検索する")
                    gr.Markdown("**完全外部メモリの小規模実装**\n\n"
                                "原本と索引をローカルSQLiteに保存します。"
                                "1T規模の研究アルゴリズムではありません。"
                                "生成回答を自動で事実として保存しません。")
                    uploads = gr.File(label="文書を追加（UTF-8 / 各2 MiB）", file_count="multiple",
                                      type="filepath", file_types=sorted(ALLOWED_SUFFIXES))
                    memory_status = gr.Textbox(label="取り込み状態", interactive=False,
                                               value=f"{memory.stats()['documents']}文書登録済み")
                    documents = gr.Dropdown(memory.list_documents(), label="登録文書")
                    delete_btn = gr.Button("選択した文書を削除", variant="stop")
                    gr.Markdown("メモリはこのサーバーの所有者用です。共有リンクのログイン情報を"
                                "他人へ配布しないでください。")
                with gr.Tab("診断・保存"):
                    doctor_btn = gr.Button("環境を診断する")
                    diagnostics = gr.JSON(label="診断結果")
                    export_btn = gr.Button("表示中の会話をJSONに保存")
                    export_file = gr.File(label="ダウンロード", visible=False)
                    gr.Markdown("会話履歴は**このブラウザー**に保存されます。"
                                "別ブラウザーや別のColab共有URLには自動同期されません。"
                                "ブラウザーデータを消す前にエクスポートしてください。")

        chatbot = gr.Chatbot(show_label=False, height="min(61vh, 760px)", min_height=280,
                             elem_id="conversation", placeholder=WELCOME, layout="bubble",
                             buttons=["copy"], sanitize_html=True, allow_tags=False,
                             allow_file_downloads=False, render=False)
        textbox = gr.Textbox(placeholder="LongBookにメッセージを送る…", lines=1, max_lines=6,
                             submit_btn="送信", stop_btn="停止", autofocus=False,
                             elem_id="composer", render=False)
        references = gr.Markdown("関連文書はまだ取得されていません。", render=False)
        chat = gr.ChatInterface(
            generate, chatbot=chatbot, textbox=textbox,
            additional_inputs=[max_tokens, temperature, window, use_memory, system],
            additional_outputs=[references], save_history=True, editable=True,
            flagging_mode="never", analytics_enabled=False, concurrency_limit=1,
            api_name="chat", api_visibility="undocumented", fill_height=True, fill_width=True,
        )
        chat.new_chat_button.value = "新しいチャット"
        chat.new_chat_button.elem_id = "new-chat"
        chat.chat_history_dataset.elem_id = "conversation-list"
        with gr.Accordion("取得した根拠とコンテキスト使用量", open=False, elem_id="evidence-panel"):
            references.render()
        gr.Markdown("LongBookは誤ることがあります。重要な情報は原文で確認してください。",
                    elem_id="disclaimer")

        open_settings.click(lambda: gr.Sidebar(open=True), outputs=sidebar, queue=False,
                            api_visibility="private")
        connect.click(configure, inputs=[kind, model, url, key, revision, trust, quantization,
                                        device, insecure], outputs=[connection_note, live_status],
                      api_visibility="private")
        unload_btn.click(unload, outputs=[connection_note, live_status], api_visibility="private")
        resolve_btn.click(resolve_revision, [model, revision], [revision, revision_note],
                          api_visibility="private")
        textbox.stop(runtime.cancel, queue=False, api_visibility="private")
        uploads.upload(ingest, uploads, [memory_status, documents], api_visibility="private")
        delete_btn.click(delete_document, documents, [memory_status, documents],
                         api_visibility="private")
        from .doctor import diagnose
        doctor_btn.click(diagnose, outputs=diagnostics, api_visibility="private")
        export_btn.click(export_chat, chatbot, export_file, api_visibility="private")
    demo.queue(max_size=8, default_concurrency_limit=1)
    return demo, runtime


def theme():
    # System fonts keep cold/offline startup independent of Google Fonts.
    return gr.themes.Base(primary_hue="teal", secondary_hue="slate", neutral_hue="slate",
                          font=["system-ui", "sans-serif"], font_mono=["monospace"]).set(
        button_primary_background_fill="#153f35", button_primary_text_color="#ffffff",
        button_primary_background_fill_hover="#235a4a", border_color_primary="#e6e8e7",
        block_radius="12px", button_large_radius="10px", input_radius="10px",
    )
