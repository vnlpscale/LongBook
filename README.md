# LongBook

**モデルは記憶を捨てたAI。記憶は外へ、思考を自由に。**

LongBook Seriesを、Colab・Windows・Linuxから同じチャットUIで使うための個人用ハーネスです。左側の会話履歴、ストリーミング回答、停止、右側のモデル設定、文書検索メモリを備えます。Node.js・Docker・GPUは、デモ/APIクライアントとして使う場合は不要です。

> **v0.1.0 / research preview**
> ハーネスの可搬性とモデルの実行可能性は別です。独自アーキテクチャを持つLongBookの実機生成、Windows実機、Colab共有リンク、ブラウザー操作は、この初版作成環境では未検証です。デモを実モデルの回答と誤認しないよう、初期画面と回答に明示します。
>
> これは10B〜1Tトークンの研究用分散メモリエンジンの完成版ではありません。同梱するメモリは200文書・原本合計50 MiBまでのSQLite実装です。

[Colabで開く](https://colab.research.google.com/github/vnlpscale/LongBook/blob/feat/portable-chat-harness/notebooks/LongBook_Colab.ipynb) · [モデルコレクション](https://huggingface.co/collections/summerMC/longbook-series) · [詳細設計](docs/ARCHITECTURE.md) · [セキュリティ](SECURITY.md)

## 最短で起動

最初に、このブランチをZIPでダウンロードして展開します。Gitがある場合は次の方法も使えます。

```bash
git clone --branch feat/portable-chat-harness https://github.com/vnlpscale/LongBook.git
cd LongBook
```

### Windows

展開したフォルダーの **`start.bat` をダブルクリック**します。必要に応じてuvとPython 3.11をユーザー領域に導入し、`.venv`を作ってブラウザーを開きます。管理者権限やシステムPythonの変更を前提にしません。

初回はネット接続とダウンロード先への書き込み権限が必要です。組織の実行ポリシーがスクリプトを禁止している場合は、ポリシーを変更せず、管理者に確認するか下の手動インストールを使ってください。

ローカルモデルの依存も導入する場合：

```powershell
.\start.bat -Local
# CUDA 4bitを使用する場合（実機互換性は要確認）
.\start.bat -Quantized
# 診断のみ
.\start.bat -Doctor
```

### Linux

```bash
bash start.sh
# ローカル推論用の依存を追加
bash start.sh --local
# CUDA 4bitの依存も追加
bash start.sh --quantized
# 診断のみ
bash start.sh --doctor
```

Python環境はuvが管理します。初回だけuv公式インストーラーを取得・実行します。事前に内容を確認したい場合は [uv公式インストール手順](https://docs.astral.sh/uv/getting-started/installation/) を参照してください。

### Colab（Webだけで利用）

上の「Colabで開く」から、ノートブックの「1. インストール」「2. UIを起動」を実行します。認証付き共有URLとランダムパスワードが表示されます。ユーザー名は `longbook` です。

初期設定は軽量なデモ/API向けです。Colab内でLongBookを動かす場合はGPUランタイムを選び、`INSTALL_LOCAL=True`、4bitには `INSTALL_4BIT=True` を指定してインストールし直します。モデル重みのダウンロードと読込はUIで明示的に実行します。

**GPUの割当や9B/27Bモデルが収まることは保証しません。** メモリ不足・独自カーネル非互換の場合は、別GPUサーバーのAPIへ接続してください。Colabセッション終了時にはサーバーと一時文書が消えます。メモリのバックアップ用セルを同梱しています。

### 既存のPythonでインストール

Python 3.11〜3.13向けです。PyPIには公開していないため、このソースフォルダーからインストールしてください。

```bash
python -m venv .venv
# Linux: source .venv/bin/activate
# Windows PowerShell: .\.venv\Scripts\Activate.ps1
python -m pip install .
longbook ui
# 必要になった段階でローカル推論の依存を追加
python -m pip install ".[local]"
```

## 実モデルに接続する

右上の **接続設定** → 実行方式を選択 → **接続 / モデル読込**。

| 実行方式 | 動作 | 必要なもの |
|---|---|---|
| 接続確認デモ | 固定の説明をストリーミング表示。AI推論はしない | UIを起動できる環境 |
| API接続 | `/v1/chat/completions`互換サーバーに接続 | 推論サーバーのURL、model名、必要なら認証キー |
| Transformers | `AutoModelForCausalLM`でローカル実行 | ローカル依存、十分なRAM/VRAM、モデル側の互換性 |

### API接続：軽量PC・Windows・GGUF向け

Base URLには、たとえば `http://127.0.0.1:8080/v1` を入力します。`model` は**サーバーが公開するmodel ID/別名**です。Hugging FaceのモデルIDと同じとは限りません。

LongBook GGUFをロードできる `llama-server` 等を別途起動して接続する構成です。**このパッケージはGGUF推論エンジン自体をインストールせず、LongBookの独自構造が任意のllama.cpp版で動くとも保証しません。** 実際のサーバー側でロードと生成を確認してください。

外部サーバーにはHTTPSを使います。信頼するLAN内のHTTPを使用するときだけ、UIの許可チェックを有効にしてください。APIモードでは質問・選択された履歴・取得した文書の抜粋が、そのAPIサーバーへ送信されます。

APIキーは接続時のメモリに保持します。環境変数 `LONGBOOK_API_KEY` も使用できます。`.env.example`は記入例で、通常のランチャーは`.env`を自動読込しません。

### Transformers：独自モデルコードの明示的な許可

LongBookの一部は独自のPythonコードや依存を必要とします。通常のAutoModelでロードできないモデルを勝手に安全だと判断しない設計です。

「ローカルモデルの詳細」でモデルIDを指定し、「revision確認」を押してcommit SHAを取得します。モデルのFilesタブのコードを確認した後に「外部Pythonコードの実行を許可」を有効にしてください。**許可する場合は40文字のcommit SHAを必須**とし、モデルとコードのrevisionに渡します。モデルがさらに外部コードを読み込む可能性もあるため、SHA固定はサンドボックスの代わりにはなりません。

ローカル推論は現在テキストのみです。VLモデルの画像入力、音声、ツール実行、Flash Attentionや独自カーネルの自動ビルドは含みません。

## データの保存場所

会話履歴はブラウザーのローカルストレージに保存します。別ブラウザーや別の共有URLへは自動同期されません。「診断・保存」から会話をJSON出力できます。

文書メモリはSQLiteに原本と索引を保存します。標準パスはLinuxが `~/.local/share/longbook`、Windowsが `%LOCALAPPDATA%\longbook` です。`LONGBOOK_DATA_DIR`または `--data-dir`で変更できます。ブラウザー履歴とサーバー文書メモリは別の保存場所です。

取り込めるのはUTF-8のtxt/md/csv/json/log/pyです。1文書2 MiB、200文書、原本合計50 MiBまで。索引・SQLiteの付加容量は別です。PDF/OCR/画像取込は未実装です。登録した記憶は質問ごとに最大4チャンクを検索し、原本の文字位置と識別子を表示します。**検索したことは内容を検証したことではありません。**

## 起動オプション

```bash
longbook ui --port 7861
longbook ui --data-dir /path/to/private/data
longbook ui --share             # 認証付きGradio共有リンク
longbook ui --host 0.0.0.0      # LAN向け。認証を自動的に必須化
longbook doctor
```

非ループバックで起動するとき、`LONGBOOK_PASSWORD`が未指定ならランダムなパスワードを生成してターミナルに表示します。指定する場合は12文字以上です。CLI引数でパスワードを受け取らず、プロセス一覧に載りにくくしています。インスタンスは**信頼する所有者1人用**です。認証を追加しただけでマルチテナントサービスにはなりません。

## Docker（任意）

```bash
docker compose up --build
```

ローカルの7860番で開き、ログに表示された認証情報を使います。Dockerは必須ではありません。このイメージにはGPU用の依存は含みません。

コンテナ内の `127.0.0.1` はホストPCではありません。ホスト上の推論サーバーへ接続する場合はDockerのホスト到達用アドレスを設定してください。ネットワーク越しのHTTPにはUIで明示的な許可も必要です。

## テストと現在の検証範囲

```bash
python -m pip install ".[dev]"
python -m pytest -q
python -m build
```

自動テストは文書検索・原本保持・削除・入力上限・コンテキスト選択・SSE・APIエラー秘匿・認証・実HTTP経由のGradioチャットを対象にします。LongBookモデルをダウンロードするテストや、学習・モデル精度のテストではありません。

初版はLinux / Python 3.13 / Gradio 6.5.1で実行確認しました。ブラウザーを用いた見た目と操作の検証は実行環境のURL遮断ポリシーで実施できていません。Windows / Python 3.11〜3.13用のCI定義を追加しましたが、実際のCI結果を確認するまで実機動作確認済みとは扱いません。

依存には互換範囲を指定しています。全推移依存を固定したロックファイルではなく、別環境で解決された依存の検証は必要です。

## ライセンス

ハーネスは既存リポジトリと同じMITライセンスです。モデル重み・モデルの独自コード・外部依存には、それぞれのライセンスが適用されます。モデル重みは配布物に含めません。
