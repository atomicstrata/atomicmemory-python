"""AtomicMemoryLessons — lessons category.

Port of the lessons section of
`atomicmemory-sdk/src/memory/atomicmemory-provider/handle-impl.ts:895-993`.
All routes are user-scoped.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from urllib.parse import quote

import httpx

from atomicmemory.providers.atomicmemory.handle import (
    Lesson,
    LessonSeverity,
    LessonsListResult,
    LessonStats,
    ReportLessonResult,
)
from atomicmemory.providers.atomicmemory.http import (
    HttpOptions,
    afetch_json,
    afetch_void,
    fetch_json,
    fetch_void,
)

Route = Callable[[str], str]

# `Lessons.list` shadows the `list` builtin inside the class body, so
# `list[str]` annotations there refer to the method. Module-level alias.
_StrList = list[str]


class AtomicMemoryLessons:
    """Lesson list / report / delete operations for a user."""

    def __init__(self, client: httpx.Client, http: HttpOptions, route: Route) -> None:
        self._client = client
        self._http = http
        self._route = route

    def list(self, user_id: str) -> LessonsListResult:
        path = self._route(f"/memories/lessons?user_id={quote(user_id, safe='')}")
        raw = fetch_json(self._client, self._http, path)
        return LessonsListResult.model_validate(
            {
                "lessons": [Lesson.model_validate(row) for row in raw.get("lessons", [])],
                "count": raw.get("count", 0),
            }
        )

    def stats(self, user_id: str) -> LessonStats:
        path = self._route(f"/memories/lessons/stats?user_id={quote(user_id, safe='')}")
        raw = fetch_json(self._client, self._http, path)
        return LessonStats.model_validate(raw)

    def report(
        self,
        user_id: str,
        pattern: str,
        sources: _StrList | None = None,
        severity: LessonSeverity | None = None,
    ) -> ReportLessonResult:
        body: dict[str, Any] = {"user_id": user_id, "pattern": pattern}
        if sources:
            body["source_memory_ids"] = sources
        if severity is not None:
            body["severity"] = severity
        raw = fetch_json(
            self._client,
            self._http,
            self._route("/memories/lessons/report"),
            method="POST",
            json=body,
        )
        return ReportLessonResult.model_validate(raw)

    def delete(self, lesson_id: str, user_id: str) -> None:
        path = self._route(f"/memories/lessons/{quote(lesson_id, safe='')}?user_id={quote(user_id, safe='')}")
        fetch_void(self._client, self._http, path, method="DELETE")


class AsyncAtomicMemoryLessons:
    """Async counterpart of :class:`AtomicMemoryLessons`."""

    def __init__(self, client: httpx.AsyncClient, http: HttpOptions, route: Route) -> None:
        self._client = client
        self._http = http
        self._route = route

    async def list(self, user_id: str) -> LessonsListResult:
        path = self._route(f"/memories/lessons?user_id={quote(user_id, safe='')}")
        raw = await afetch_json(self._client, self._http, path)
        return LessonsListResult.model_validate(
            {
                "lessons": [Lesson.model_validate(row) for row in raw.get("lessons", [])],
                "count": raw.get("count", 0),
            }
        )

    async def stats(self, user_id: str) -> LessonStats:
        path = self._route(f"/memories/lessons/stats?user_id={quote(user_id, safe='')}")
        raw = await afetch_json(self._client, self._http, path)
        return LessonStats.model_validate(raw)

    async def report(
        self,
        user_id: str,
        pattern: str,
        sources: _StrList | None = None,
        severity: LessonSeverity | None = None,
    ) -> ReportLessonResult:
        body: dict[str, Any] = {"user_id": user_id, "pattern": pattern}
        if sources:
            body["source_memory_ids"] = sources
        if severity is not None:
            body["severity"] = severity
        raw = await afetch_json(
            self._client,
            self._http,
            self._route("/memories/lessons/report"),
            method="POST",
            json=body,
        )
        return ReportLessonResult.model_validate(raw)

    async def delete(self, lesson_id: str, user_id: str) -> None:
        path = self._route(f"/memories/lessons/{quote(lesson_id, safe='')}?user_id={quote(user_id, safe='')}")
        await afetch_void(self._client, self._http, path, method="DELETE")
