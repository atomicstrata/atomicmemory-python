"""Integrity of the vendored v1 contract artifacts.

The corpus is vendored (committed, immutable) so CI is deterministic; the
refresh script re-copies from a local atomicmemory-internal checkout and is
never run in CI. These tests pin the tree's internal consistency, not its
content (content correctness is the conformance harness's job).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

CONTRACT = Path(__file__).resolve().parents[2] / "contract"
V1 = CONTRACT / "v1"

REQUIRED_VENDORED_FIELDS = {
    "source_repo",
    "source_path",
    "source_sdk_version",
    "source_main_commit",
    "schema_last_modified_commit",
    "vendored_at",
}


def test_vendored_manifest_pins_the_exact_vendored_source() -> None:
    # EXACT pins, deliberately — the opposite call from the PR1 version test.
    # A package version changes on every release (a pin = pure friction), but a
    # vendored immutable artifact set has exactly ONE correct provenance; a
    # refresh is a conscious act that updates these constants in the same
    # commit as the new artifacts. Drift between the pins and the committed
    # corpus would mean the tree was edited outside the refresh script.
    vendored = json.loads((CONTRACT / "VENDORED.json").read_text())
    assert set(vendored) >= REQUIRED_VENDORED_FIELDS
    assert vendored["source_repo"] == "atomicmemory-internal"
    assert vendored["source_sdk_version"] == "1.1.0"
    assert vendored["source_main_commit"] == "2a67871"
    assert vendored["schema_last_modified_commit"] == "6fccaf4"


def test_corpus_manifest_cases_and_schemas_all_exist() -> None:
    manifest = json.loads((V1 / "conformance" / "manifest.json").read_text())
    assert manifest["version"] == 1
    # Deliberate content pin (unlike the version assertions): a refresh that
    # adds/removes corpus cases MUST fail here, because new cases need
    # conscious model/codec mappings in the harness — silent pass-through
    # would un-cover the new case.
    assert len(manifest["cases"]) == 4
    for case in manifest["cases"]:
        case_path = V1 / "conformance" / case["file"]
        assert case_path.is_file(), f"missing corpus case {case['file']}"
        body = json.loads(case_path.read_text())
        for key in ("name", "operation", "response_schema", "expected_response"):
            assert key in body, f"{case['file']} missing {key}"
        for ref in filter(None, (body.get("request_schema"), body["response_schema"])):
            schema_file = ref.split("#", 1)[0]
            assert (V1 / schema_file).is_file(), f"{case['file']} references missing schema {schema_file}"


def test_contract_doc_present() -> None:
    assert (CONTRACT / "CONTRACT.md").read_text().strip()


def test_pyproject_declares_contract_in_the_sdist() -> None:
    # Deterministic primary assertion (no build, no network): the include list
    # itself. The tarball test below is the thorough end-to-end check.
    pyproject = (CONTRACT.parent / "pyproject.toml").read_text()
    include_block = re.search(
        r"\[tool\.hatch\.build\.targets\.sdist\].*?^include\s*=\s*\[([^\]]*)\]",
        pyproject,
        re.DOTALL | re.MULTILINE,
    )
    assert include_block and '"contract"' in include_block.group(1)


def test_sdist_ships_the_contract_artifacts(tmp_path: Path) -> None:
    # The sdist ships tests/, and tests read contract/ — an sdist without the
    # fixtures would fail pytest-from-source. Build into a temp dir and inspect.
    # NOTE: `uv build` resolves the hatchling build backend (network on a cold
    # cache; cached thereafter — CI already fetches deps via uv, so no new class
    # of dependency).
    import subprocess
    import tarfile

    result = subprocess.run(
        ["uv", "build", "--sdist", "--out-dir", str(tmp_path)],
        cwd=str(CONTRACT.parent),
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(f"uv build failed:\n{result.stderr.decode(errors='replace')}")
    tarballs = list(tmp_path.glob("*.tar.gz"))
    assert len(tarballs) == 1, f"expected exactly one sdist, got: {tarballs}"
    sdist = tarballs[0]
    with tarfile.open(sdist) as tar:
        names = tar.getnames()
    assert any(n.endswith("contract/v1/conformance/manifest.json") for n in names)
    assert any(n.endswith("contract/VENDORED.json") for n in names)
