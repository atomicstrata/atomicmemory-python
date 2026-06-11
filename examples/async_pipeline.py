"""Async ingest + search example."""

from __future__ import annotations

import asyncio

from atomicmemory import AsyncMemoryClient, Scope, SearchRequest, TextIngest

API_URL = "http://localhost:17350"


async def main() -> None:
    async with AsyncMemoryClient(providers={"atomicmemory": {"api_url": API_URL}}) as memory:
        await memory.initialize()
        await memory.ingest(TextIngest(content="The dog is named Rex.", scope=Scope(user="demo")))
        page = await memory.search(SearchRequest(query="dog name", scope=Scope(user="demo")))
        for hit in page.results:
            print(f"  {hit.score:.3f}  {hit.memory.content}")


if __name__ == "__main__":
    asyncio.run(main())
