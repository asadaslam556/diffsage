import asyncio

from app.vectorstore.embeddings import HashingEmbedder, chunk_text
from app.vectorstore.store import MemoryVectorStore


def test_chunks_respect_size_and_overlap():
    text = "\n".join(f"rule {i}: keep functions short and named clearly" for i in range(100))
    chunks = chunk_text(text, size=300, overlap=60)
    assert len(chunks) > 5
    assert all(len(c) <= 360 for c in chunks)
    assert chunks[0][-30:] in chunks[1]  # overlap carries over


def test_one_giant_line_is_split():
    chunks = chunk_text("x" * 2500, size=900, overlap=100)
    assert len(chunks) == 3 and all(len(c) <= 900 for c in chunks)


def test_hashing_embedder_is_deterministic_and_normalised():
    async def go():
        emb = HashingEmbedder(128)
        a, b = await emb.embed(["use snake_case for functions", "use snake_case for functions"])
        assert a == b
        assert abs(sum(v * v for v in a) - 1.0) < 1e-9

    asyncio.run(go())


def test_search_prefers_the_related_chunk_and_isolates_users():
    async def go():
        emb = HashingEmbedder(256)
        store = MemoryVectorStore()
        docs = ["python functions use snake_case naming", "sql migrations must be reversible"]
        await store.upsert("alice", "d1", "style.md", docs, await emb.embed(docs))
        await store.upsert("bob", "d2", "bob.md", ["python snake_case naming"], await emb.embed(["python snake_case naming"]))
        [query] = await emb.embed(["what naming do python functions use"])
        hits = await store.search("alice", query, 2)
        assert hits[0].text == docs[0]
        assert all(h.filename == "style.md" for h in hits)  # never bob's

    asyncio.run(go())
