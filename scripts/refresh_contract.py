"""Refresh the vendored v1 contract artifacts from a local TS-SDK checkout.

Run MANUALLY when the TS contract revs — never in CI. The committed copy
under contract/ is the source of truth for this repo's tests; this script
exists so refreshes are mechanical and the provenance manifest can't drift
from what was actually copied.

Usage:
    uv run python scripts/refresh_contract.py /path/to/atomicmemory-internal
"""

from __future__ import annotations

import datetime as _dt
import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT = REPO_ROOT / "contract"
SOURCE_SUBPATHS = ("packages/sdk/schema/v1", "packages/sdk/CONTRACT.md")


def _git(source_repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(source_repo), *args], text=True).strip()


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    source = Path(sys.argv[1]).resolve()
    schema_dir = source / "packages/sdk/schema/v1"
    contract_md = source / "packages/sdk/CONTRACT.md"
    if not schema_dir.is_dir() or not contract_md.is_file():
        print(f"refresh_contract: {source} does not look like an atomicmemory-internal checkout")
        return 2

    shutil.rmtree(CONTRACT / "v1", ignore_errors=True)
    shutil.copytree(schema_dir, CONTRACT / "v1")
    shutil.copyfile(contract_md, CONTRACT / "CONTRACT.md")

    sdk_pkg = json.loads((source / "packages/sdk/package.json").read_text())
    vendored = {
        "source_repo": "atomicmemory-internal",
        "source_path": " + ".join(SOURCE_SUBPATHS),
        "source_sdk_version": sdk_pkg["version"],
        "source_main_commit": _git(source, "rev-parse", "--short", "HEAD"),
        "schema_last_modified_commit": _git(source, "log", "-1", "--format=%h", "--", *SOURCE_SUBPATHS),
        "vendored_at": _dt.date.today().isoformat(),
    }
    if not vendored["schema_last_modified_commit"]:
        print(
            "refresh_contract: git log found no commits for the source paths; is this a shallow clone?",
            file=sys.stderr,
        )
        return 1
    (CONTRACT / "VENDORED.json").write_text(json.dumps(vendored, indent=2) + "\n")
    print(f"refresh_contract: vendored {vendored['source_sdk_version']} @ {vendored['source_main_commit']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
