"""Unit tests for content_class forwarding on ingest (every mode).

A core running the default ``RAW_CONTENT_POLICY=reject`` refuses content that is
``"raw"`` or carries no ``content_class`` at all — regardless of ingest mode
(``text``/``messages`` extraction or ``verbatim``). The SDK exposes
``content_class`` on every ingest input and forwards the caller's choice verbatim;
it never infers one, so omitting it leaves the field off the wire and a
reject-policy core fails the ingest closed rather than the SDK mislabeling raw
content as safe.
"""

from __future__ import annotations

from atomicmemory.memory.types import MessageIngest, Scope, TextIngest, VerbatimIngest
from atomicmemory.providers.atomicmemory.provider import _build_ingest_body

_SCOPE = Scope(user="u")
_MSGS = [{"role": "user", "content": "I prefer dark mode"}]


def test_forwards_stamped_content_class() -> None:
    body = _build_ingest_body(VerbatimIngest(scope=_SCOPE, content="distilled summary", content_class="summary"))
    assert body["content_class"] == "summary"
    assert body["skip_extraction"] is True


def test_forwards_explicit_raw_choice_unchanged() -> None:
    body = _build_ingest_body(VerbatimIngest(scope=_SCOPE, content="transcript", content_class="raw"))
    assert body["content_class"] == "raw"


def test_omits_content_class_when_unstamped() -> None:
    body = _build_ingest_body(VerbatimIngest(scope=_SCOPE, content="unclassified"))
    assert "content_class" not in body


def test_forwards_content_class_on_messages_extraction() -> None:
    body = _build_ingest_body(MessageIngest(scope=_SCOPE, messages=_MSGS, content_class="summary"))
    assert body["content_class"] == "summary"
    assert "skip_extraction" not in body  # extraction mode, not verbatim


def test_forwards_content_class_on_text_extraction() -> None:
    body = _build_ingest_body(TextIngest(scope=_SCOPE, content="a note", content_class="redacted"))
    assert body["content_class"] == "redacted"


def test_omits_content_class_on_messages_when_unstamped() -> None:
    body = _build_ingest_body(MessageIngest(scope=_SCOPE, messages=_MSGS))
    assert "content_class" not in body
