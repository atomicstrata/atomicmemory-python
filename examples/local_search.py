"""Local-only semantic search — no atomicmemory-core required.

Demonstrates the in-memory store + cosine search using a hand-built
embedding function (e.g. trivial bag-of-words) so the example runs
without the optional embeddings extra.
"""

from __future__ import annotations

from atomicmemory.search import SemanticSearch, StoredContext


def fake_embed(text: str) -> list[float]:
    """Toy embedding: word frequencies on a fixed vocabulary."""
    vocab = ["alpha", "beta", "gamma", "delta", "epsilon"]
    return [text.lower().count(word) for word in vocab]


def main() -> None:
    contexts = [
        StoredContext(id="c1", content="alpha beta beta", embedding=fake_embed("alpha beta beta")),
        StoredContext(id="c2", content="gamma gamma delta", embedding=fake_embed("gamma gamma delta")),
        StoredContext(id="c3", content="epsilon", embedding=fake_embed("epsilon")),
    ]
    search = SemanticSearch(embed_fn=fake_embed)
    for hit in search.search("beta", contexts, top_k=2):
        print(f"  {hit.score:.3f}  {hit.context.content}")


if __name__ == "__main__":
    main()
