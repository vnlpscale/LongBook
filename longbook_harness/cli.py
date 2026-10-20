from __future__ import annotations

import argparse
import json
import os
import secrets
from pathlib import Path


def launch_ui(*, host="127.0.0.1", port=7860, share=False, inbrowser=True,
              data_dir=None, prevent_thread_lock=False):
    from .app import create_app, theme
    from .config import data_directory

    root = Path(data_dir).expanduser().resolve() if data_dir else data_directory()
    root.mkdir(parents=True, exist_ok=True)
    public = share or host not in {"127.0.0.1", "localhost", "::1"}
    password = os.getenv("LONGBOOK_PASSWORD", "")
    if public and not password:
        password = secrets.token_urlsafe(24)
        print("\nPersonal-use login. Do not distribute these credentials.")
        print(f"Username: longbook\nPassword: {password}\n", flush=True)
    if password and len(password) < 12:
        raise ValueError("LONGBOOK_PASSWORDは12文字以上にしてください。")
    auth = ("longbook", password) if password else None
    demo, runtime = create_app(root)
    try:
        demo.launch(
            server_name=host, server_port=port, share=share, inbrowser=inbrowser,
            auth=auth, auth_message="LongBook · 個人用ワークスペース",
            prevent_thread_lock=prevent_thread_lock, show_error=False, ssr_mode=False,
            enable_monitoring=False, strict_cors=True, max_file_size=2 * 1024 * 1024,
            blocked_paths=[str(root)], footer_links=[], theme=theme(),
            css_paths=Path(__file__).with_name("style.css"),
        )
    except Exception:
        runtime.cancel()
        raise
    return demo, runtime


def main():
    parser = argparse.ArgumentParser(prog="longbook", description="Portable personal LongBook harness")
    commands = parser.add_subparsers(dest="command")
    ui = commands.add_parser("ui", help="Launch the web chat UI")
    ui.add_argument("--host", default="127.0.0.1")
    ui.add_argument("--port", type=int, default=7860)
    ui.add_argument("--share", action="store_true", help="Create an authenticated Gradio share link")
    ui.add_argument("--no-browser", action="store_true")
    ui.add_argument("--data-dir", type=Path)
    commands.add_parser("doctor", help="Print diagnostics without loading model weights")
    args = parser.parse_args()
    if args.command == "doctor":
        from .doctor import diagnose
        print(json.dumps(diagnose(), ensure_ascii=False, indent=2))
    elif args.command == "ui":
        launch_ui(host=args.host, port=args.port, share=args.share, inbrowser=not args.no_browser,
                  data_dir=args.data_dir)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
