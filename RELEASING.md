# Releasing `atomicmemory` to PyPI

Publishing uses **OIDC Trusted Publishing** — no API tokens. The package is
published from the public mirror (`atomicstrata/atomicmemory-python`), which is
the clean release surface; development happens here in the private repo and
reaches the mirror via a manual snapshot sync.

## One-time setup (already done unless this is a fresh project)

1. **PyPI Trusted Publisher** — on the `atomicmemory` project at
   <https://pypi.org/manage/project/atomicmemory/settings/publishing/>, add a
   GitHub publisher:
   - Owner: `atomicstrata`
   - Repository: `atomicmemory-python`
   - Workflow filename: `publish-pypi.yml`
   - Environment name: `pypi-release`
2. **GitHub environment** — on `atomicstrata/atomicmemory-python`, create an
   environment named `pypi-release`. Add the release approver as a required
   reviewer to gate each publish behind a one-click approval.

## Releasing a version

1. Land the version bump + changelog on this repo's `main` (the `[Unreleased]`
   CHANGELOG section becomes `[X.Y.Z] - <date>` at release time).
2. Snapshot-sync `main` to `atomicstrata/atomicmemory-python` (single curated PR;
   merge after its CI is green).
3. On the mirror, run the **Publish to PyPI** workflow
   (Actions → Publish to PyPI → Run workflow) with the exact version as input.
   It verifies the version matches `pyproject.toml` and is not already on PyPI,
   builds the sdist + wheel with `uv build`, and publishes via OIDC with PEP 740
   attestations. The `pypi-release` environment prompts for approval first.
4. Verify: `pip install atomicmemory==X.Y.Z` from a clean environment.

The workflow is `workflow_dispatch`-only and guarded to run solely on the public
mirror, so a routine snapshot sync never triggers a publish.
