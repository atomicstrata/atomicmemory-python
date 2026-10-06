#!/usr/bin/env bash
# Verify public tools and process-restart examples from an installed wheel.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
expected_version=$(uv run --directory "$root" python -c 'import atomicmemory; print(atomicmemory.__version__)')
consumer=$(mktemp -d)
trap 'rm -rf "$consumer"' EXIT
uv build --wheel --out-dir "$consumer/dist" "$root"
cp -R "$root/tests/tools" "$consumer/tools"
mkdir -p "$consumer/tests" "$consumer/examples"
mv "$consumer/tools" "$consumer/tests/tools"
cp "$root/tests/__init__.py" "$consumer/tests/__init__.py"
cp "$root/examples/memory_tools.py" "$consumer/examples/memory_tools.py"
uv init --bare --no-workspace "$consumer"
cd "$consumer"
uv add "$consumer"/dist/*.whl
uv add --dev pytest pytest-asyncio respx
uv run python -c 'import atomicmemory; from pathlib import Path; assert "site-packages" in str(Path(atomicmemory.__file__)); import sys; assert atomicmemory.__version__ == sys.argv[1]; assert all(hasattr(atomicmemory, name) for name in atomicmemory.__all__)' "$expected_version"
uv run python -m pytest tests/tools --asyncio-mode=auto -q
