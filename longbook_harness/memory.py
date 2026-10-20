"""Small-corpus evidence adapter; NOT a 10B–1T distributed memory implementation.

Original UTF-8 bytes are retained in SQLite. An FTS5 index stores normalized
English words and Japanese bigrams. No model output is automatically promoted
into a fact. Evidence retrieval is not factual verification.
"""
from __future__ import annotations

import hashlib
import re
import sqlite3
import unicodedata
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Protocol

MAX_DOCUMENT_BYTES = 2 * 1024 * 1024
MAX_TOTAL_BYTES = 50 * 1024 * 1024
MAX_DOCUMENTS = 200
ALLOWED_SUFFIXES = {".txt", ".md", ".csv", ".json", ".log", ".py"}


def index_terms(text: str, limit: int | None = None) -> list[str]:
    text = unicodedata.normalize("NFKC", text).lower()
    parts = re.findall(r"[a-z0-9_]+|[\u3040-\u30ff\u3400-\u9fff]+", text)
    result: list[str] = []
    for part in parts:
        if part.isascii():
            result.append(part)
        elif len(part) == 1:
            result.append(part)
        else:
            result.extend(part[i:i + 2] for i in range(len(part) - 1))
        if limit and len(result) >= limit:
            return list(dict.fromkeys(result))[:limit]
    return list(dict.fromkeys(result))


@dataclass(frozen=True)
class Evidence:
    id: str
    document_id: str
    source: str
    start_char: int
    end_char: int
    text: str


class MemoryAdapter(Protocol):
    """Replace this boundary with a distributed LEM service at research scale."""
    def search(self, query: str, limit: int = 4) -> list[Evidence]: ...


class SQLiteMemory:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL,
                    raw BLOB NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS chunks (
                    id INTEGER PRIMARY KEY, document_id TEXT NOT NULL,
                    start_char INTEGER NOT NULL, end_char INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE
                );
                CREATE VIRTUAL TABLE IF NOT EXISTS chunk_search USING fts5(terms);
            """)

    @contextmanager
    def _db(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def add_bytes(self, name: str, raw: bytes) -> tuple[str, bool]:
        # A displayed filename never becomes a filesystem destination.
        name = Path(name.replace("\\", "/")).name[:200]
        if Path(name).suffix.lower() not in ALLOWED_SUFFIXES:
            raise ValueError("UTF-8のtxt/md/csv/json/log/pyだけを取り込めます。")
        if not raw or len(raw) > MAX_DOCUMENT_BYTES:
            raise ValueError("1文書の上限は2 MiBです。空ファイルは登録できません。")
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValueError("UTF-8形式で保存し直してください。") from exc
        if "\x00" in text or not text.strip():
            raise ValueError("空文書またはバイナリデータは登録できません。")
        digest = hashlib.sha256(raw).hexdigest()
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM documents WHERE id=?", (digest,)).fetchone():
                return digest, False
            total, count = db.execute(
                "SELECT COALESCE(SUM(length(raw)),0), COUNT(*) FROM documents"
            ).fetchone()
            if total + len(raw) > MAX_TOTAL_BYTES or count >= MAX_DOCUMENTS:
                raise ValueError("初版の上限は200文書・原本合計50 MiBです。不要な文書を削除してください。")
            db.execute("INSERT INTO documents(id,name,raw) VALUES(?,?,?)", (digest, name, raw))
            # Character offsets, deliberately not mislabeled as token offsets.
            for start in range(0, len(text), 1040):
                end = min(start + 1200, len(text))
                passage = text[start:end]
                cur = db.execute(
                    "INSERT INTO chunks(document_id,start_char,end_char,text) VALUES(?,?,?,?)",
                    (digest, start, end, passage),
                )
                db.execute("INSERT INTO chunk_search(rowid,terms) VALUES(?,?)",
                           (cur.lastrowid, " ".join(index_terms(passage))))
                if end == len(text):
                    break
        return digest, True

    def add_file(self, path: str) -> tuple[str, bool]:
        source = Path(path)
        with source.open("rb") as f:
            raw = f.read(MAX_DOCUMENT_BYTES + 1)
        return self.add_bytes(source.name, raw)

    def search(self, query: str, limit: int = 4) -> list[Evidence]:
        terms = index_terms(query[:8000], limit=48)
        if not terms:
            return []
        # Terms come from a restricted tokenizer, but still quote defensively.
        match = " OR ".join('"' + term.replace('"', '""') + '"' for term in terms)
        with self._db() as db:
            rows = db.execute("""
                SELECT c.*, d.name FROM chunk_search f
                JOIN chunks c ON c.id=f.rowid JOIN documents d ON d.id=c.document_id
                WHERE chunk_search MATCH ? ORDER BY bm25(chunk_search), c.id LIMIT ?
            """, (match, min(max(limit, 1), 20))).fetchall()
        return [Evidence(f"{r['document_id'][:12]}:{r['start_char']}", r["document_id"],
                         r["name"], r["start_char"], r["end_char"], r["text"]) for r in rows]

    def list_documents(self) -> list[tuple[str, str]]:
        with self._db() as db:
            return [(f"{r['name']} · {r['id'][:8]}", r["id"]) for r in db.execute(
                "SELECT id,name FROM documents ORDER BY created_at DESC, id"
            )]

    def delete(self, document_id: str) -> None:
        with self._db() as db:
            db.execute("DELETE FROM chunk_search WHERE rowid IN "
                       "(SELECT id FROM chunks WHERE document_id=?)", (document_id,))
            db.execute("DELETE FROM documents WHERE id=?", (document_id,))

    def stats(self) -> dict[str, int]:
        with self._db() as db:
            documents, total = db.execute(
                "SELECT COUNT(*),COALESCE(SUM(length(raw)),0) FROM documents"
            ).fetchone()
            chunks = db.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        return {"documents": documents, "bytes": total, "chunks": chunks}
