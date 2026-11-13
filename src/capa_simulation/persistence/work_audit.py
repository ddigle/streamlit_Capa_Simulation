# Purpose: 저장소 쓰기 함수의 감사 줄 꼴 — 대상 id · 이름표 · 상세를 값 원문 없이 짓는다.

"""두 저장소(`repository.py` · `equipment_repository.py`)의 `@audited` 가 쓰는 `describe` 들.

값 원문 · 셀 내용 · 메모 · 비고 · VOC 본문은 싣지 않는다. 대상은 id 로 적고 화면을 읽을 수 있게 하는
이름표(시나리오 · 리비전 · 설비 시나리오 이름)만 `tgt.label` 에 싣는다(60자에서 기록기가 자른다).
손입력 「저장자」 · 「만든 사람」 · VOC 작성자는 `claimed` 로 넘긴다 — 인증 신원과 다를 때만 남는다.
실패 줄에서는 결과가 `None` 이라 인자만으로 짓는다.
"""

from __future__ import annotations

from collections.abc import Mapping, Sized
from typing import Any

from capa_simulation.audit.work import Describe, WorkNote


def _get(value: Any, *path: str) -> Any:
    for name in path:
        if value is None:
            return None
        value = value.get(name) if isinstance(value, Mapping) else getattr(value, name, None)
    return value


def _text(value: Any) -> str | None:
    return None if value is None else str(value)


def _rows(value: Any) -> int | None:
    return len(value) if isinstance(value, Sized) and not isinstance(value, str) else None


def _target(kind: str, identifier: Any, label: Any = None) -> dict[str, object]:
    target: dict[str, object] = {"type": kind, "id": _text(identifier) or ""}
    if label is not None:
        target["label"] = str(label)
    return target


# ------------------------------------------------------------------ 시나리오 · 리비전 · 공식
def scenario_create(args: Mapping[str, Any], result: Any) -> WorkNote:
    metadata = args.get("metadata")
    return WorkNote(
        tgt=_target(
            "scenario", _get(result, "scenario", "scenario_id"), _get(metadata, "scenario_name")
        ),
        det={"source": _get(metadata, "source_type"), "rows": _rows(args.get("source_data"))},
    )


def scenario(args: Mapping[str, Any], result: Any) -> WorkNote:
    return WorkNote(tgt=_target("scenario", args.get("scenario_id"), args.get("scenario_name")))


def revision_save(args: Mapping[str, Any], result: Any) -> WorkNote:
    tables = args.get("revision_tables")
    return WorkNote(
        tgt=_target("revision", _get(result, "revision", "revision_id"), args.get("revision_name")),
        det={
            "scenario": _text(args.get("scenario_id")),
            "parent": _text(args.get("parent_revision_id")),
            "tables": sorted(tables) if isinstance(tables, Mapping) else None,
        },
    )


def revision_rename(args: Mapping[str, Any], result: Any) -> WorkNote:
    return WorkNote(tgt=_target("revision", args.get("revision_id"), args.get("revision_name")))


def official_publish(args: Mapping[str, Any], result: Any) -> WorkNote:
    return WorkNote(
        tgt=_target(
            "official",
            _get(result, "release_no") or args.get("scenario_id"),
            _get(result, "scenario_name"),
        ),
        det={"release_no": _get(result, "release_no"), "revision": _text(args.get("revision_id"))},
    )


def exclusions(args: Mapping[str, Any], result: Any) -> WorkNote:
    rows = args.get("exclusions")
    first = next(iter(rows), None) if isinstance(rows, list | tuple) else None
    return WorkNote(det={"run_id": _text(_get(first, "run_id")), "rows": _rows(rows)})


def profile(name: str, rows_argument: str | None = None) -> Describe:
    """공용 프로필 저장 — 프로필 이름 · 저장 뒤 판 · 출처 · 행 수."""

    def describe(args: Mapping[str, Any], result: Any) -> WorkNote:
        return WorkNote(
            tgt=_target("profile", name),
            det={
                "profile": name,
                "version_to": _get(result, "version"),
                "source": _text(args.get("source")),
                "rows": None if rows_argument is None else _rows(args.get(rows_argument)),
            },
        )

    return describe


# ------------------------------------------------------------------ VOC
def voc_post(args: Mapping[str, Any], result: Any) -> WorkNote:
    return WorkNote(tgt=_target("voc", result), claimed=_text(args.get("author")))


def voc_reply(args: Mapping[str, Any], result: Any) -> WorkNote:
    return WorkNote(tgt=_target("voc", args.get("post_id")), claimed=_text(args.get("author")))


def voc_resolve(args: Mapping[str, Any], result: Any) -> WorkNote:
    return WorkNote(
        tgt=_target("voc", args.get("post_id")), det={"resolved": bool(args.get("resolved"))}
    )


def voc_delete(args: Mapping[str, Any], result: Any) -> WorkNote:
    return WorkNote(tgt=_target("voc", args.get("post_id")))


# ------------------------------------------------------------------ 설비
def equipment_save(args: Mapping[str, Any], result: Any) -> WorkNote:
    request = args.get("request")
    return WorkNote(
        tgt=_target("equipment_scenario", _get(request, "equipment_scenario_id")),
        det={
            "source": "screen",
            "rows": _rows(_get(request, "equipment")),
            "schedule_revision": _text(_get(result, "schedule", "schedule_revision_id")),
        },
        claimed=_text(_get(request, "saved_by")),
    )


def equipment_wrapper(args: Mapping[str, Any], result: Any) -> WorkNote:
    return WorkNote(
        tgt=_target("equipment_scenario", "official"),
        det={"source": "wrapper", "rows": _rows(args.get("equipment"))},
    )


def equipment_clone(args: Mapping[str, Any], result: Any) -> WorkNote:
    return WorkNote(
        tgt=_target(
            "equipment_scenario",
            _get(result, "equipment_scenario_id"),
            _get(result, "scenario_name") or args.get("name"),
        ),
        det={"source": _text(args.get("source_schedule_revision_id"))},
        claimed=_text(args.get("created_by")),
    )


def equipment_rename(args: Mapping[str, Any], result: Any) -> WorkNote:
    return WorkNote(
        tgt=_target("equipment_scenario", args.get("equipment_scenario_id"), args.get("name"))
    )


def equipment_publish(args: Mapping[str, Any], result: Any) -> WorkNote:
    return WorkNote(
        tgt=_target("equipment_release", _get(result, "release_no") or ""),
        det={"schedule_revision": _text(args.get("schedule_revision_id"))},
        claimed=_text(args.get("released_by")),
    )


def schedule_rename(args: Mapping[str, Any], result: Any) -> WorkNote:
    return WorkNote(
        tgt=_target("schedule_revision", args.get("schedule_revision_id"), args.get("name"))
    )


def schedule_restore(args: Mapping[str, Any], result: Any) -> WorkNote:
    return WorkNote(
        tgt=_target("schedule_revision", args.get("schedule_revision_id")),
        det={"schedule_revision": _text(_get(result, "schedule", "schedule_revision_id"))},
        claimed=_text(args.get("saved_by")),
    )


def overlay_clear(args: Mapping[str, Any], result: Any) -> WorkNote:
    return WorkNote(
        tgt=_target("equipment_scenario", args.get("equipment_scenario_id")),
        claimed=_text(args.get("saved_by")),
    )


def rows_of(argument: str, *, claimed: str | None = None) -> Describe:
    """운영 값 저장 — 행 수만(값 없이)."""

    def describe(args: Mapping[str, Any], result: Any) -> WorkNote:
        return WorkNote(
            det={"rows": _rows(args.get(argument))},
            claimed=None if claimed is None else _text(args.get(claimed)),
        )

    return describe


def baseline_save(args: Mapping[str, Any], result: Any) -> WorkNote:
    return WorkNote(tgt=_target("baseline", _get(result, "baseline_id"), _get(result, "name")))


def baseline_delete(args: Mapping[str, Any], result: Any) -> WorkNote:
    return WorkNote(tgt=_target("baseline", args.get("baseline_id")))


def drawing(args: Mapping[str, Any], result: Any) -> WorkNote:
    building, floor = args.get("building"), args.get("floor")
    place = "FAB" if building is None else f"{building} {floor}"
    marks = args.get("marks")
    return WorkNote(tgt=_target("drawing", place), det={"rows": _rows(marks)})
