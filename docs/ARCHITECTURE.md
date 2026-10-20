# LongBook portable harness v0.1

## Execution boundary

```text
Browser: ChatInterface + local conversation history
    |
Gradio: login + streaming event queue + settings
    |
Runtime: one-owner lock + cancellation + context budgeting
    |                         |
Backend protocol              MemoryAdapter.search()
    |                         |
Demo / HTTP API / Transformers SQLite raw evidence + FTS5
```

The UI is authored in Python and ships its CSS as package data. It requires neither a Node.js
build toolchain nor a browser extension. Gradio's built-in conversation UI supplies new-chat,
streaming, stop, retry/edit controls, local history and Markdown rendering. Our sidebar supplies
backend configuration, evidence import, deletion, diagnostics and conversation JSON export.
No custom generated images, bundled fonts, or external CDN assets are required.

## Backend contracts

`stream(messages, options, cancel)` yields **text deltas**. The runtime aggregates them for the UI.
`close()` must release resources or explicitly reject release while generation is still active.
One process hosts one loaded model and one owner. Runtime locks prevent switching/unloading a
model during generation. Local workers check a cancellation event between generation steps and
have a 600-second wall limit; a long GPU kernel cannot be forcibly interrupted safely.

The API adapter speaks the chat/completions wire format over HTTP using httpx, without requiring
a specific commercial SDK. It supports SSE records, keepalive comments, UTF-8, done sentinels and
JSON fallbacks. API error bodies are deliberately not shown. A /models check confirms connectivity,
not successful LongBook inference.

The Transformers adapter imports heavy dependencies only on explicit model load. It uses
AutoTokenizer, AutoModelForCausalLM, apply_chat_template and TextIteratorStreamer. It chooses
CPU float32 or CUDA bf16/fp16; the optional 4bit path uses bitsandbytes on CUDA. It does not implement
LongBook-specific GDN kernels or alter checkpoint weights. Compatibility must be checked against
the selected checkpoint and its revision. Images for VL checkpoints are not implemented.

## Context budget

Let C be the user-configured total context budget, O the output reservation, and H=256 the
additional safety margin. We enforce a packed input budget B=C-O-H using the model's actual
chat-template tokenizer for local generation. The API path uses a conservative UTF-8 byte-based
estimate, not a guaranteed tokenizer-independent upper bound.

The latest question is retained in full or rejected. Evidence is added in retrieval order while
it fits. Recent user-led conversation turns are then added; old turns are omitted whole, never
silently chopped mid-message. The UI reports the estimated/exact input count and omitted-message
count. Changing C does not change the underlying model or server's actual context capability.

## Evidence memory

Each source is retained as original UTF-8 bytes, keyed by SHA-256. Search passages use 1,200-character
windows with a 160-character overlap. Offsets are character offsets in decoded text, not token
or byte offsets. Source identity and exact original bytes are distinct from the derived search text.

FTS5 indexes normalized English words and Japanese bigrams. Query terms are bounded and escaped;
SQL inputs are parameterized. Deleting a source transactionally deletes its chunks and FTS rows.
The preview caps raw data at 50 MiB and 200 documents with 2 MiB per file. This is intentionally a
small, dependency-light retrieval implementation, not state-of-the-art semantic retrieval.

Only explicitly uploaded documents are indexed. Assistant answers and conversation summaries
are not automatically accepted as facts. The UI displays **retrieved** evidence, not verified truth.

## Research extension boundary

`MemoryAdapter` in memory.py defines the read-side boundary for a future LEM service. At 10B–1T
scale replace SQLite retrieval with a remotely managed memory service, along with a separate
bulk-ingestion system. Add immutable evidence storage, temporal/provenance metadata, hierarchical
and hybrid indices, snapshot consistency, authorization, learned retrieval policies and evaluation.
Those features are **not implemented** by this preview. The local upload form is not a distributed
bulk-ingestion client and should not be represented as one.

## Packaging and environments

The source distribution contains Windows batch/PowerShell and Linux bash launchers. These bootstrap
uv and managed Python 3.11, then launch the package in an isolated local environment. Local model
and quantization dependencies are opt-in. The Colab notebook installs from an explicit branch/tag/
commit ref and uses Gradio's authenticated share link. Docker is an optional CPU/API-client image.

## Verification boundaries

Automated tests cover Python contracts and live HTTP serving, not rendered browser fidelity or
real checkpoint accuracy. A browser UI test was attempted on Chromium but all navigation was
blocked by the execution environment's administrator URL policy. No policy changes or bypasses
were made, and no screenshot-based verification claim is made.

Primary implementation references:

- https://www.gradio.app/docs/gradio/chatinterface
- https://www.gradio.app/docs/gradio/blocks
- https://docs.astral.sh/uv/getting-started/installation/
- https://huggingface.co/docs/transformers/main/en/internal/generation_utils
- https://huggingface.co/collections/summerMC/longbook-series

The Gradio code path was tested with 6.5.1. Dependencies are range-bounded, not a full environment
lock. Windows/Colab/GPU/checkpoint compatibility and current patch-release dependencies must be
validated separately before a stable release.
