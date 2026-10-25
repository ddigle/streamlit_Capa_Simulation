# Purpose: Space 층 도면 요소·Main 설비명 위치를 세션 배치 차이로 합치고 견주기 재료를 낸다.

"""Space 현황의 층 도면 요소·Main 설비명 위치 한 곳(설비 시나리오 2단계 S3 — 설계 7-2·8-1).

- **그림 = 공식 층 현행값(쓰기 세대 캐시) ⊕ 세션 설비 시나리오 일정 리비전의 배치 차이**(설비 0031 —
  일정 id 하나를 키로 한 불변 칸 `load_schedule_layout_overlay`). 공식 세션·차이 없는 리비전은 공식
  현행값 그대로다(차이를 질의하지 않는다).
- 합치기는 회차마다 한다(층 하나·수십 요소 — 캐시하지 않는다). 그래서 이 모듈에는 캐시 데코레이터가
  없다 — 캐시 경계는 `persistence/equipment_cache.py` 그대로다.
- Space 의 요소·이름표 읽기는 **모두 이것을 지난다**(뷰어·편집기·저장 안 한 상자의 겹침 경고) —
  하나라도 공식 현행값을 직접 읽으면 가정 회차의 경고가 공식 요소로 판정되고 편집 기준 지문이
  어긋난다(검토 F15·M7). `app_pages/space_status.py` 에는 공식 층 요소 직접 읽기가 없다(시험이
  본다).
- 「공식과 견주기」(S4 — 설계 8-3) 재료도 여기서 낸다 — 층 상세 뷰어 payload(`compare_payload`)와
  FAB 층 목록 「공식과 다름」 칸·블록 풍선의 층별 셈(`floor_unit_differences`). 둘 다 그리는 세션
  스냅샷의 합친 본문(`layout_official_places`)과 마스터만 읽는다 — 공식 스냅샷을 따로 읽지 않는다.
"""

from __future__ import annotations

from collections.abc import Collection
from typing import Any

from capa_simulation.equipment_scenario_activation import EquipmentSession
from capa_simulation.persistence.equipment_cache import (
    load_floor_group_labels,
    load_floor_layout_marks,
    load_schedule_layout_overlay,
)
from capa_simulation.services.floor_layout_mark import FloorLayoutMark
from capa_simulation.services.floor_layout_profile import FloorKey
from capa_simulation.services.korean_particle import subject_particle
from capa_simulation.services.layout_overlay import (
    EMPTY_LAYOUT_DIGEST,
    LayoutOverlay,
    effective_floor_marks,
    effective_group_labels,
    label_changes,
    layout_compare,
    layout_counts_words,
    layout_difference,
    mark_changes,
    unit_differences_by_floor,
)


def session_layout_overlay(database_path: str, session: EquipmentSession) -> LayoutOverlay:
    """세션이 든 일정 리비전의 도면 요소·Main 설비명 위치 차이(호기 칸은 비어 있다 — 합친 본문에
    이미 얹혀 있다). 차이가 없거나 일정 없이 열었으면 빈 차이다(질의하지 않는다)."""
    snapshot = session.snapshot
    schedule = snapshot.schedule if snapshot is not None and not session.unmerged else None
    if schedule is None or schedule.layout_digest == EMPTY_LAYOUT_DIGEST:
        return LayoutOverlay()
    return load_schedule_layout_overlay(database_path, schedule.schedule_revision_id)


def effective_floor_layout(
    database_path: str, key: FloorKey, session: EquipmentSession
) -> tuple[tuple[FloorLayoutMark, ...], dict[str, str]]:
    """그 층의 (도면 요소, Main 설비명 위치) — 공식 층 현행값에 세션 리비전의 차이를 얹은 것."""
    official_marks = load_floor_layout_marks(database_path, *key)
    official_labels = load_floor_group_labels(database_path, *key)
    overlay = session_layout_overlay(database_path, session)
    if not overlay:
        return tuple(official_marks), dict(official_labels)
    return (
        effective_floor_marks(official_marks, overlay.marks_for(key)),
        effective_group_labels(official_labels, overlay.labels_for(key)),
    )


def floor_layout_differences(database_path: str, session: EquipmentSession) -> tuple[int, int]:
    """세션 리비전의 도면 요소·Main 설비명 위치 차이 가운데 지금 공식 층 현행값과 실제로 다른 수
    (실효 — 공식과 같아진 차이는 다음 저장 때 지워진다). 머리 알림 재료(설계 8-2)."""
    overlay = session_layout_overlay(database_path, session)
    if not overlay:
        return 0, 0
    marks = labels = 0
    for key in overlay.floors:
        official_marks = load_floor_layout_marks(database_path, *key)
        official_labels = load_floor_group_labels(database_path, *key)
        if overlay.marks_for(key):
            marks += len(
                mark_changes(
                    effective_floor_marks(official_marks, overlay.marks_for(key)), official_marks
                )
            )
        if overlay.labels_for(key):
            labels += len(
                label_changes(
                    effective_group_labels(official_labels, overlay.labels_for(key)),
                    official_labels,
                )
            )
    return marks, labels


def space_layout_notices(
    session: EquipmentSession, floor_differences: tuple[int, int]
) -> list[tuple[str, str]]:
    """Space 머리 알림 칸의 배치 줄 — (글, 꼴 "info"|"caption") 차례(설계 8-2). 역할이 아니라
    **그리는 스냅샷**으로 정한다 — 합친 본문 캐시는 역할을 키에 못 담아, 공식 시나리오의 가정이던
    때 리비전도 그 차이가 그대로 그려진다(검토 M8). `floor_differences` 는 도면 요소·Main 설비명
    위치 실효 수(`floor_layout_differences`)다."""
    snapshot = session.snapshot
    if snapshot is None or session.unmerged:
        return []
    difference = layout_difference(
        snapshot.equipment,
        snapshot.unit_key_pairs,
        snapshot.layout_official_places,
        snapshot.unscheduled_units,
        LayoutOverlay(),
    )
    marks, labels = floor_differences
    stored_units, stored_marks, stored_labels = session.stored_layout_rows
    has_rows = bool(stored_units or stored_marks or stored_labels)
    if not has_rows and not session.is_assumption:
        return []
    parts = []
    if difference.units:
        parts.append(f"공식과 다른 호기 {difference.units:,}대")
    if marks:
        parts.append(f"도면 요소 {marks:,}개")
    if labels:
        parts.append(f"Main 설비명 위치 {labels:,}개")
    tail = ""
    if (stored_units and not difference.units) or stored_marks > marks or stored_labels > labels:
        stored = layout_counts_words(stored_units, stored_marks, stored_labels)
        tail = f"(저장된 차이 {stored} — 공식과 같아진 것은 다음 저장·발행 때 정리됩니다)"
    lines: list[tuple[str, str]] = []
    name = f"「{session.scenario_name}」" if session.scenario_name else "이 설비 시나리오"
    if not session.is_assumption:
        # 공식 설비 시나리오의 옛 리비전 — 그 시나리오가 가정이던 때 저장한 배치안이다.
        lines.append(
            (
                f"이 리비전은 공식과 다른 배치({' · '.join(parts) or '저장된 차이'})를 담고 "
                f"있습니다 — {name}{subject_particle(name)} 가정이던 때의 배치안입니다.{tail}",
                "info",
            )
        )
    elif parts:
        lines.append((f"가정 배치 · {' · '.join(parts)}{tail}", "info"))
    else:
        lines.append((f"가정 설비 시나리오 · 배치는 공식과 같습니다{tail}", "caption"))
    if snapshot.layout_regrouped:
        lines.append(
            (
                f"공식에서 모듈 구성이 바뀐 묶음 {len(snapshot.layout_regrouped):,}개"
                f"({', '.join(snapshot.layout_regrouped[:3])}"
                f"{' 외' if len(snapshot.layout_regrouped) > 3 else ''}) — 가정 배치에서 그 "
                "모듈은 자리 없이 트레이에 있습니다. 배치 편집에서 다시 놓으세요.",
                "caption",
            )
        )
    if snapshot.layout_orphans:
        lines.append(
            (
                f"공통 대장에서 지운 호기의 배치 차이 {snapshot.layout_orphans:,}행은 버렸습니다 "
                "— 다음 저장 때 빠집니다.",
                "caption",
            )
        )
    return lines


def compare_payload(
    session: EquipmentSession, key: FloorKey, *, shown: Collection[str]
) -> dict[str, Any] | None:
    """층 상세 뷰어의 「공식과 견주기」 재료(`space_layout_editor.render_space_layout_viewer` 의
    `compare`) — 공식 자리 점선 상자(`ghosts`)와 다른 층에서 온 호기 꼬리표(`arrivals`). `shown` 은
    지금 화면이 그리는 설비명(공정 필터·일정 없음을 지난 것)이다. 차이가 없거나 일정 없이 열었으면
    None."""
    snapshot = session.snapshot
    if snapshot is None or session.unmerged or not snapshot.layout_official_places:
        return None
    compare = layout_compare(
        snapshot.equipment,
        snapshot.unit_key_pairs,
        snapshot.layout_official_places,
        key,
        shown=shown,
    )
    if not compare:
        return None
    return {
        "ghosts": [
            {
                "id": ghost.name,
                "x": ghost.x,
                "y": ghost.y,
                "w": ghost.w,
                "h": ghost.h,
                "tag": ghost.tag,
            }
            for ghost in compare.ghosts
        ],
        "arrivals": [{"id": arrival.name, "tag": arrival.tag} for arrival in compare.arrivals],
    }


def floor_unit_differences(session: EquipmentSession) -> dict[FloorKey, int]:
    """층마다 공식과 자리가 다른 설비 수(나간·들어온·그 층 안에서 옮긴 호기 — 묶음은 1대, 일정 없는
    호기 제외). FAB 층 목록 「공식과 다름」 칸·블록 풍선 재료(설계 8-3)."""
    snapshot = session.snapshot
    if snapshot is None or session.unmerged or not snapshot.layout_official_places:
        return {}
    return unit_differences_by_floor(
        snapshot.equipment,
        snapshot.unit_key_pairs,
        snapshot.layout_official_places,
        snapshot.unscheduled_units,
    )
