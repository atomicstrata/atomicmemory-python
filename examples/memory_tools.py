"""Run one operation per process to check persistent memory with sync or async tools.

Set ATOMICMEMORY_API_KEY and ATOMICMEMORY_USER in the application environment.
ATOMICMEMORY_API_URL defaults to Cloud; local endpoints use explicit configuration.
This example does not call a model, retry writes, or claim terminal correction receipts.
"""

from __future__ import annotations

import argparse
import asyncio
import os

from atomicmemory import AsyncMemoryClient, MemoryClient, async_memory_tools, memory_tools


def arguments() -> argparse.Namespace:
    """Read application configuration and the selected single operation."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["ingest", "search"])
    parser.add_argument("text")
    parser.add_argument("--async", dest="use_async", action="store_true")
    parsed = parser.parse_args()
    parsed.user = os.environ["ATOMICMEMORY_USER"]
    parsed.providers = {
        "atomicmemory": {
            "api_url": os.environ.get("ATOMICMEMORY_API_URL", "https://api.atomicstrata.ai"),
            "api_key": os.environ["ATOMICMEMORY_API_KEY"],
        }
    }
    return parsed


def run_sync(args: argparse.Namespace) -> None:
    """Initialize once and invoke one sync tool with model-shaped arguments."""
    with MemoryClient(providers=args.providers) as client:
        client.initialize()
        tools = memory_tools(client=client, user=args.user)
        if args.operation == "ingest":
            result = tools["memory_ingest"].execute({"content": args.text})
            if not (result.created or result.updated or result.unchanged):
                raise RuntimeError("Saving was not confirmed; do not retry automatically.")
            print(result.model_dump_json(exclude_none=True))
        else:
            print(tools["memory_search"].execute({"query": args.text}).model_dump_json(exclude_none=True))


async def run_async(args: argparse.Namespace) -> None:
    """Initialize once and invoke the equivalent async tool."""
    async with AsyncMemoryClient(providers=args.providers) as client:
        await client.initialize()
        tools = async_memory_tools(client=client, user=args.user)
        if args.operation == "ingest":
            result = await tools["memory_ingest"].execute({"content": args.text})
            if not (result.created or result.updated or result.unchanged):
                raise RuntimeError("Saving was not confirmed; do not retry automatically.")
            print(result.model_dump_json(exclude_none=True))
        else:
            result_page = await tools["memory_search"].execute({"query": args.text})
            print(result_page.model_dump_json(exclude_none=True))


if __name__ == "__main__":
    args = arguments()
    if args.use_async:
        asyncio.run(run_async(args))
    else:
        run_sync(args)
