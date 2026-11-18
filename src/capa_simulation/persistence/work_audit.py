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


def scenario_archive(args: Mapping[str, Any], result: Any) -> WorkNote:
    """보관 — 같은 트랜잭션에서 비운 HOME 지정(공용 비교 대상 · 주요 Case) 수를 싣는다. 보관은
    실무자부터라 관리자 몫 HOME 설정 지정을 실무자가 비울 수 있다 — 누가 비웠는지를 이 줄로 본다."""
    return WorkNote(
        tgt=_target("scenario", args.get("scenario_id")),
        det={"home_cleared": result if isinstance(result, int) else None},
    )


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


def scenario_reorder(args: Mapping[str, Any], result: Any) -> WorkNote:
    return WorkNote(det={"rows": _rows(args.get("scenario_ids"))})


def _new_names(value: Any) -> list[tuple[str, str]]:
    """(id → (본 이름, 새 이름)) → (id, 새 이름 — 저장처럼 앞뒤 공백을 뗌)."""
    if not isinstance(value, Mapping):
        return []
    named: list[tuple[str, str]] = []
    for identifier, pair in value.items():
        wanted = pair[1] if isinstance(pair, tuple | list) and len(pair) == 2 else ""
        named.append((str(identifier), str(wanted).strip()))
    return named


def scenario_list_edits(args: Mapping[str, Any], result: Any) -> list[tuple[str, WorkNote]]:
    """목록 관리 일괄 저장 — 이름을 바꾼 시나리오 · 리비전마다 한 줄, 순서를 고쳤으면 한 줄."""
    notes = [
        ("data_scenario_rename", WorkNote(tgt=_target("scenario", identifier, name or None)))
        for identifier, name in _new_names(args.get("renames"))
    ]
    notes.extend(
        ("data_revision_rename", WorkNote(tgt=_target("revision", identifier, name or None)))
        for identifier, name in _new_names(args.get("revision_renames"))
    )
    if args.get("order") is not None:
        notes.append(("data_scenario_reorder", WorkNote(det={"rows": _rows(args.get("order"))})))
    return notes


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


def _deleted(result: Any) -> dict[str, object] | None:
    """지우기 함수의 돌려준 값(참 · 거짓) — 그 사이 다른 세션이 지워 지울 것이 없었으면 거짓이다.
    실패 줄(결과 `None`)에는 싣지 않는다."""
    return None if result is None else {"deleted": bool(result)}


def voc_delete(args: Mapping[str, Any], result: Any) -> WorkNote:
    return WorkNote(tgt=_target("voc", args.get("post_id")), det=_deleted(result))


# ------------------------------------------------------------------ 설비
def _propagated_count(result: Any) -> int | None:
    """함께 넣기로 새 리비전을 받은 다른 시나리오 수(건너뛰기만 한 시나리오는 세지 않는다)."""
    rows = _get(result, "propagated")
    if not isinstance(rows, tuple | list):
        return None
    return sum(1 for row in rows if _get(row, "revision_no") is not None)


def equipment_save(args: Mapping[str, Any], result: Any) -> WorkNote:
    """설비 저장 — 이 저장이 낸 공식 발행 번호(없으면 싣지 않음)와 함께 넣은 시나리오 수도 싣는다.
    비가동만 바뀐 저장은 실무자부터라 그 사람의 저장이 공식 발행을 냈는지를 이 줄로 가른다."""
    request = args.get("request")
    return WorkNote(
        tgt=_target("equipment_scenario", _get(request, "equipment_scenario_id")),
        det={
            "source": "screen",
            "rows": _rows(_get(request, "equipment")),
            "schedule_revision": _text(_get(result, "schedule", "schedule_revision_id")),
            "release_no": _get(result, "release_no"),
            "propagated": _propagated_count(result),
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


def shortening_filter(field: str, rows_argument: str | None = None) -> Describe:
    """필요 단축 공용 기본 조회 조건 저장 — 바꾼 칸(기간 · 공정)과 공정 수만(값 없이)."""

    def describe(args: Mapping[str, Any], result: Any) -> WorkNote:
        rows = None if rows_argument is None else _rows(args.get(rows_argument))
        return WorkNote(det={"field": field, "rows": rows})

    return describe


def legacy_trace_ack(args: Mapping[str, Any], result: Any) -> WorkNote:
    """설비 「옛 배포 흔적」 이어 쓰기 — 확인한 흔적 수만."""
    return WorkNote(det={"count": args.get("expected_trace_count")})


def baseline_save(args: Mapping[str, Any], result: Any) -> WorkNote:
    return WorkNote(tgt=_target("baseline", _get(result, "baseline_id"), _get(result, "name")))


def baseline_delete(args: Mapping[str, Any], result: Any) -> WorkNote:
    return WorkNote(tgt=_target("baseline", args.get("baseline_id")), det=_deleted(result))


def drawing(args: Mapping[str, Any], result: Any) -> WorkNote:
    building, floor = args.get("building"), args.get("floor")
    place = "FAB" if building is None else f"{building} {floor}"
    marks = args.get("marks")
    return WorkNote(tgt=_target("drawing", place), det={"rows": _rows(marks)})
