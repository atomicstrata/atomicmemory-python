"""Load the vendored v1 schemas into a jsonschema (draft 2020-12) registry.

Provides :func:`validator_for`, which builds a ``Draft202012Validator`` for a
corpus ref (``"file.schema.json"`` or ``"file.schema.json#/$defs/Name"``).
The validator resolves via the full registry so that the 26 intra-document
``#/$defs/...`` refs inside the schemas remain valid; extracting a fragment as
a standalone schema would break every one of them.

See Also:
    tests/contract/test_conformance.py: The conformance harness that uses this.
    contract/v1/*.schema.json: The vendored schema files loaded here.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

V1 = Path(__file__).resolve().parents[2] / "contract" / "v1"

# format= keywords (date-time on createdAt/observed_at/...) are ADVISORY in
# jsonschema unless a FormatChecker is supplied — without one, "not-a-date"
# validates (probe-verified). The dev dependency is jsonschema[format] so the
# rfc3339 checker is actually installed.
_FORMAT_CHECKER = FormatChecker()


def _load_registry() -> Registry:
    """Build a jsonschema Registry from all vendored *.schema.json files.

    Returns:
        A Registry with all four v1 schemas keyed by their ``$id`` URIs.
    """
    registry: Registry = Registry()
    for schema_path in sorted(V1.glob("*.schema.json")):
        schema = json.loads(schema_path.read_text())
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    return registry


_REGISTRY = _load_registry()


def validator_for(ref: str) -> Draft202012Validator:
    """Build a validator for a corpus ref like 'file.schema.json#/$defs/Name'.

    Resolution goes through the registry via a ``$ref`` wrapper so the parent
    document context is preserved — the schemas contain 26 intra-document
    ``#/$defs/...`` references, and extracting a fragment as a standalone
    schema would break every one of them.

    Args:
        ref: A schema reference in the form ``"file.schema.json"`` or
            ``"file.schema.json#/$defs/SomeName"`` relative to the v1 dir.

    Returns:
        A ``Draft202012Validator`` with the full registry and format checking.
    """
    file_part, _, fragment = ref.partition("#")
    schema: dict[str, Any] = json.loads((V1 / file_part).read_text())
    uri = schema["$id"] + (("#" + fragment) if fragment else "")
    return Draft202012Validator({"$ref": uri}, registry=_REGISTRY, format_checker=_FORMAT_CHECKER)
