import hashlib
import pytest
from longbook_harness.memory import SQLiteMemory, MAX_DOCUMENT_BYTES, index_terms

@pytest.fixture
def memory(tmp_path):
    return SQLiteMemory(tmp_path / "memory.sqlite3")

def test_japanese_search(memory):
    memory.add_bytes("設計.md", "認証にはJWTを使い、データベースにはPostgreSQLを採用する。".encode())
    hits = memory.search("データベースは何ですか")
    assert len(hits) == 1 and "PostgreSQL" in hits[0].text

def test_english_search(memory):
    memory.add_bytes("memo.txt", b"Use PostgreSQL for durable memory storage.")
    assert memory.search("durable storage")[0].source == "memo.txt"

def test_raw_bytes_retained_and_deduplicated(memory):
    raw = b"\xef\xbb\xbfhello world\r\n"
    ident, created = memory.add_bytes("a.txt", raw)
    assert ident == hashlib.sha256(raw).hexdigest() and created
    assert memory.add_bytes("other.txt", raw) == (ident, False)
    with memory._db() as db:
        assert db.execute("SELECT raw FROM documents").fetchone()[0] == raw
    assert memory.stats()["documents"] == 1

def test_delete_removes_fts(memory):
    ident, _ = memory.add_bytes("a.md", b"needle inside document")
    assert memory.search("needle")
    memory.delete(ident)
    assert memory.search("needle") == []
    assert memory.stats() == {"documents": 0, "bytes": 0, "chunks": 0}

@pytest.mark.parametrize("name,raw", [("a.pdf", b"hello"), ("a.txt", b""),
                                      ("a.md", b"\xff"), ("a.txt", b"\x00")])
def test_invalid_files(memory, name, raw):
    with pytest.raises(ValueError):
        memory.add_bytes(name, raw)
    assert memory.stats()["documents"] == 0

def test_document_size_limit(memory):
    with pytest.raises(ValueError):
        memory.add_bytes("big.txt", b"x" * (MAX_DOCUMENT_BYTES + 1))

def test_safe_queries(memory):
    memory.add_bytes("memo.txt", b"alpha beta")
    assert memory.search('" OR * - NOT \'); DROP TABLE chunks; --') == []
    assert memory.search("alpha")

def test_filename_is_display_only(memory):
    memory.add_bytes("../../outside.txt", b"sample")
    assert memory.list_documents()[0][0].startswith("outside.txt")

def test_terms():
    assert "ab" in index_terms("ＡＢ")
    assert "記憶" in index_terms("記憶機構")

def test_overlapping_offsets(memory):
    text = "a" * 2000
    memory.add_bytes("large.txt", text.encode())
    with memory._db() as db:
        rows = db.execute("SELECT start_char,end_char,text FROM chunks ORDER BY id").fetchall()
    for r in rows:
        assert text[r[0]:r[1]] == r[2]
