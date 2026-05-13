"""Basic round-trip example against a local atomicmemory-core instance.

Prereq:
  cd ../atomicmemory-core
  npm run dev  # starts core on http://localhost:3050

Then:
  uv run python examples/basic_ingest_search.py
"""

from __future__ import annotations

from atomicmemory import MemoryClient, MemoryRef, Scope, SearchRequest, TextIngest

API_URL = "http://localhost:3050"


def main() -> None:
    with MemoryClient(providers={"atomicmemory": {"api_url": API_URL}}) as client:
        client.initialize()
        ingest = client.ingest(TextIngest(content="I prefer aisle seats on flights.", scope=Scope(user="demo")))
        print(f"Ingested: created={ingest.created} updated={ingest.updated}")

        page = client.search(SearchRequest(query="seat preference", scope=Scope(user="demo")))
        for hit in page.results:
            print(f"  {hit.score:.3f}  {hit.memory.content}")

        for created_id in ingest.created:
            client.delete(MemoryRef(id=created_id, scope=Scope(user="demo")))


if __name__ == "__main__":
    main()
