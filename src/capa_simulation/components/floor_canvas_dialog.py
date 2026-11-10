# Purpose: Space 층·FAB 전체 도면의 캔버스 폭·높이를 고치는 「캔버스 편집」 팝업을 렌더링한다.

"""Space 층·FAB 전체 도면의 캔버스 폭·높이를 고치는 UI를 렌더링한다.

가끔 하는 쓰기라 본문을 차지하지 않고 `캔버스 편집` **팝업**이다(2026-09-29 사용자 결정). 단추는
사이드바 「Space 도면」 상자에 서고(2026-11-03 사용자 요청) 팝업은 본문 끝의 호스트가 연다 — 둘을
가른다. 호스트는 화면 팝업 호스트 프래그먼트(`components/dialog_host.py` — 2026-11-08 사용자 결정
U5)라 열기 · 닫기는 페이지를 다시 계산하지 않고 그 호스트만 돈다(설계 규칙 UI-PRF-01). 저장이
성공하면 팝업 칸을 비우고 앱 전체를 다시 돌려(`DialogHost.finish`) 레이아웃이 새 캔버스로 다시
그려진다. 호스트만 도는 회차의 인자(저장된 설비 마스터)는 직전 앱 전체 회차의 것이라, 그 사이 설비
DB 가 바뀌었으면 팝업 본문이 앱 전체 회차로 물러나 새로 읽는다.

층과 FAB 전체 도면이 **같은 팝업**을 범위(`_CanvasTarget`)만 바꿔 쓴다. 다른 것은 저장 자리(층 표 /
FAB 표), 기본 캔버스(100 × 60 / `FAB_CANVAS`), 캔버스 밖 검사의 대상(층은 저장된 설비 마스터의 그 층
호기 전부와 저장된 도면 요소, FAB 는 지금 그리는 요소 — 저장된 것이 없으면 기본 배치)과 저장 뒤
정리할 대기분이다.

밖으로 나가는 것의 목록 · 까닭은 팝업 자리에 쓰지 않고 상태 알림(`CANVAS_OUTSIDE_ALERT`)으로 낸다
(설계 규칙 UI-NTF-02). 자리에는 저장을 막는 조건만 남는다 — 도면 요소가 밖이면 잠긴 저장 단추와 짧은
풍선, 호기가 밖이면 확인 칸 하나(체크 전까지 같은 잠금). 호기는 저장소가 막지 않고 다음 설비 저장이
막히므로 알고 줄이는 길을 남긴다.

층 캔버스를 줄이는 저장은 가정 설비 시나리오의 배치도 본다(설비 시나리오 2단계 S4 — 설계 6-4).
캔버스를 바꾸는 저장이 보는 리비전(ACTIVE 시나리오 최신·최신 공식 발행)의 그 층 차이 요소가 밖이면
저장소가 막으므로 공식 요소처럼 단추를 끄고, 차이 호기가 밖이면 공식 호기처럼 확인 칸으로 받는다(그
시나리오의 다음 저장만 막힌다). 재료는 `load_layout_overlay_extent` 하나다.

옛 판이 올린 도면 그림은 그리지도 읽지도 않고 지우지도 않는다(설비 DB `image_*` 칸 — 표는 그대로다).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from functools import partial
from pathlib import Path
from typing import Final, Protocol

import pandas as pd
import streamlit as st

from capa_simulation import alerts
from capa_simulation.components.dialog_host import DialogBody, DialogHost
from capa_simulation.components.equipment_data_workspace import (
    rebase_fab_canvas,
    rebase_floor_canvas,
    stage_floor_canvas,
)
from capa_simulation.page_bootstrap import (
    BOOTSTRAP_ERRORS,
    PAGE_DIALOG_SUFFIX,
    bootstrap_error_message,
)
from capa_simulation.persistence.equipment_cache import (
    DatabaseStamp,
    clear_floor_layout_cache,
    database_stamp,
    get_equipment_repository,
    load_fab_layout,
    load_floor_layout_marks,
    load_floor_layout_profile,
    load_layout_overlay_extent,
)
from capa_simulation.persistence.equipment_repository import LayoutOverlayExtent
from capa_simulation.services.equipment_validation import floor_equipment_outside_canvas
from capa_simulation.services.fab_layout import FAB_CANVAS, effective_fab_layout
from capa_simulation.services.floor_layout_mark import marks_extent
from capa_simulation.services.floor_layout_profile import (
    DEFAULT_CANVAS_HEIGHT,
    DEFAULT_CANVAS_WIDTH,
    MAX_CANVAS_EXTENT,
    MIN_CANVAS_EXTENT,
    CanvasSize,
    FloorKey,
    normalize_canvas_size,
)
from capa_simulation.services.korean_particle import with_subject_particle
from capa_simulation.sidebar_status import keeps_app_run_open

# 이 화면의 위젯 키는 모두 이 접두에서 파생한다. 리터럴 접두를 자리마다 다시
# 적으면 다른 모듈과 겹쳐도 `test_session_key_collisions` 가 볼 축이 없다.
FLOOR_CANVAS_WIDGET_KEY: Final = "space_floor_layout"
# 지금 열린 캔버스 팝업의 범위 — 층은 `동|층`, FAB 는 `FAB`. 페이지를 떠나면
# `forget_page_dialogs` 가 비운다.
FLOOR_CANVAS_DIALOG_KEY: Final = f"space{PAGE_DIALOG_SUFFIX}"
# 팝업의 호스트 프래그먼트 — 열기 · 닫기가 앱 전체 대신 이 호스트만 돈다(U5 · 설계 규칙 UI-PRF-01).
CANVAS_DIALOG_HOST: Final = DialogHost("space_canvas_dialog_host", FLOOR_CANVAS_DIALOG_KEY)
FAB_DIALOG_SCOPE: Final = "FAB"
# 고치는 크기 밖으로 나가는 호기 · 도면 요소(등록부 `alerts.SPECS`).
CANVAS_OUTSIDE_ALERT = "EQ-16"
# 팝업 본문이 밖 알림을 조건 있음(`active`)으로 낸 채인가 — 닫는 회차를 가른다(`_dismiss`).
OUTSIDE_SHOWN_KEY: Final = f"{FLOOR_CANVAS_WIDGET_KEY}_outside_shown"
SAMPLE_CANVAS_LOCK: Final = "샘플 데이터를 보는 중에는 FAB 캔버스를 고치지 않습니다."


class _CanvasProfile(Protocol):
    """팝업이 보는 저장된 캔버스 — 층(`FloorLayoutProfile`)과 FAB(`FabLayoutProfile`)가 함께
    맞는다."""

    @property
    def canvas_size(self) -> CanvasSize: ...

    @property
    def updated_at(self) -> datetime: ...


@dataclass(frozen=True)
class _CanvasTarget:
    """팝업의 범위. `floor` 가 None 이면 FAB 전체 도면이다."""

    floor: FloorKey | None

    @property
    def scope(self) -> str:
        return FAB_DIALOG_SCOPE if self.floor is None else f"{self.floor[0]}|{self.floor[1]}"

    @property
    def key(self) -> str:
        """위젯 키 꼬리 — 층은 `C1_1F`, FAB 는 `FAB`."""
        return FAB_DIALOG_SCOPE if self.floor is None else f"{self.floor[0]}_{self.floor[1]}"

    @property
    def title(self) -> str:
        return "S.PKG FAB 전체" if self.floor is None else f"{self.floor[0]} {self.floor[1]}"

    @property
    def default_canvas(self) -> CanvasSize:
        return FAB_CANVAS if self.floor is None else (DEFAULT_CANVAS_WIDTH, DEFAULT_CANVAS_HEIGHT)


@dataclass(frozen=True)
class _CanvasOutside:
    """고치는 크기 밖으로 나가는 것. `mark_extent` 는 캔버스를 이보다 줄일 수 없는 요소 범위다."""

    units: tuple[str, ...]
    overlay_units: tuple[tuple[str, int], ...]
    overlay_marks: tuple[str, ...]
    mark_extent: CanvasSize
    marks_outside: bool

    @property
    def unit_count(self) -> int:
        return len(self.units) + sum(count for _, count in self.overlay_units)


def render_floor_canvas_button(
    *, floor: FloorKey | None, disabled: bool = False, reason: str | None = None
) -> None:
    """`캔버스 편집` 단추 — 누르면 그 범위(층, `floor` 가 None 이면 FAB 전체 도면)의 팝업 열림 칸을
    적는다. 팝업은 그리지 않는다 — 본문 호스트(`render_floor_canvas_dialog_host`)가 연다.

    단추는 사이드바 「Space 도면」 상자에 선다(2026-11-03 사용자 요청 — 레이아웃 위 작업 줄을
    사이드바로). 팝업 함수를 사이드바 `with` 안에서 부르지 않으려고 단추와 팝업을 가른다. `disabled`
    면 단추를 끄고 `reason` 을 풍선으로 둔다 — 층 캔버스는 공용 값이라 가정 설비 시나리오에서
    잠그고(G5 와 같은 까닭 — 설계 8-4), FAB 은 설비 샘플 화면(합성 fleet 을 보는 중)·가정 설비
    시나리오에서 잠근다. 아이콘은 없다 — 상자 제목이 같은 지도 아이콘이고, 사이드바 폭(245px
    상자)에서 「배치 편집」 토글과 한 줄에 들어야 한다(아이콘을 달면 둘째 줄로 감겼다).
    """
    target = _CanvasTarget(floor)
    button_key = f"{FLOOR_CANVAS_WIDGET_KEY}_open_{target.key}"
    st.button(
        "캔버스 편집",
        key=button_key,
        on_click=CANVAS_DIALOG_HOST.open,
        args=(target.scope, button_key),
        disabled=disabled,
        help=(reason or SAMPLE_CANVAS_LOCK) if disabled else None,
    )


def render_floor_canvas_dialog_host(
    *,
    database_path: str,
    floor: FloorKey | None,
    saved_equipment: pd.DataFrame,
    disabled: bool = False,
    others: Mapping[str, tuple[DialogBody, tuple[str, ...]]] | None = None,
) -> None:
    """캔버스 팝업의 본문 호스트. 그 범위의 열림 칸이 서 있고 잠기지 않았으면 팝업을 연다.

    Space 화면의 팝업 호스트는 이것 하나다(`DialogHost` 쓰는 법 — 화면당 호스트 하나). 같은 화면의
    다른 팝업(필요 단축 보기의 목표 확보율 — `space_shortening_view.LEVEL_DIALOGS`)은 `others`
    (열림 값 → (팝업, 입력 위젯 key))로 받아 함께 연다 — 캔버스 잠금(`disabled`)과 상관없다.

    `saved_equipment` 는 층이면 **저장된 설비 마스터 전체**다(필터 전, 레이아웃표시 무관) — 캔버스를
    줄일 때 그 층 호기가 밖으로 나가는지 저장 검증과 같은 행으로 잰다. 설비 저장본이 없으면(샘플
    화면) 빈 표를 넘긴다 — 저장을 막을 호기가 없다. FAB 은 빈 표다(호기가 없다). `disabled` 는
    단추와 같은 잠금이다 — 잠긴 회차에 남은 열림 칸으로 팝업이 서지 않게 두 겹으로 막는다.

    팝업을 닫은 회차는 고치던 크기가 사라졌으니 밖 알림을 해소한다 — 열렸든 닫혔든 이벤트 칸에
    정확히 한 자리다(팝업 블록 또는 표지 — 호스트의 `idle`).

    **매 앱 전체 회차 빠짐없이** 부른다(본문 끝) — 이번 회차에 등록되지 않은 호스트는 단추의 여는
    콜백도 팝업 닫기도 겨눌 수 없다(`DialogHost.render`). 닫기(X · 바깥 · Esc)는 팝업의 입력 위젯
    (폭 · 높이 · 이탈 호기 확인) 값을 함께 지워 다시 열면 저장값으로 선다. 밖 알림이 선 채 닫으면
    그 닫기만 앱 전체 회차다(`_dismiss`).
    """
    target = _CanvasTarget(floor)
    seen = database_stamp(database_path)

    extra = dict(others or {})

    def pick(value: object) -> DialogBody | None:
        if isinstance(value, str) and value in extra:
            return extra[value][0]
        if disabled or value != target.scope:
            return None
        return partial(
            _floor_canvas_dialog,
            database_path=database_path,
            target=target,
            saved_equipment=saved_equipment,
            seen_stamp=seen,
        )

    def widget_keys(value: object) -> tuple[str, ...]:
        if isinstance(value, str) and value in extra:
            return extra[value][1]
        return _widget_keys(target)

    CANVAS_DIALOG_HOST.render(
        pick,
        widget_keys=widget_keys,
        idle=partial(
            alerts.state, CANVAS_OUTSIDE_ALERT, scope=target.scope, content=None, active=False
        ),
    )


def _widget_keys(target: _CanvasTarget) -> tuple[str, ...]:
    """그 범위 팝업의 입력 위젯 key 와 밖 알림 표지 칸 — 닫으면 지운다(`DialogHost` 지키는 것 5)."""
    return (
        *(
            f"{FLOOR_CANVAS_WIDGET_KEY}_{name}_{target.key}"
            for name in ("width", "height", "shrink")
        ),
        OUTSIDE_SHOWN_KEY,
    )


def _dismiss() -> None:
    """닫기(X · 바깥 · Esc). 보통은 호스트만 돈다(`DialogHost.close`). 밖 알림이 조건 있음으로 선
    채 닫으면 앱 전체 회차로 닫는다(`close_to_app`) — 그 회차의 해소 표지(호스트 `idle`)를 알림
    칸이 그 회차에 읽게. 호스트만 도는 짧은 회차는 앱 뿌리의 회차 표지를 움직이지 않아, 알림 칸이
    해소를 다음 회차까지 못 읽었다(2026-11-08 사본 실측 — 알림 칸은 회차 표지가 바뀔 때만 문서를
    훑는다)."""
    shown = bool(st.session_state.get(OUTSIDE_SHOWN_KEY))
    if shown:
        CANVAS_DIALOG_HOST.close_to_app()
    else:
        CANVAS_DIALOG_HOST.close()


def _load_profile(database_path: str, target: _CanvasTarget) -> _CanvasProfile | None:
    if target.floor is None:
        return load_fab_layout(database_path)[0]
    return load_floor_layout_profile(database_path, *target.floor)


def _marks_extent(
    database_path: str, target: _CanvasTarget, overlay: LayoutOverlayExtent
) -> CanvasSize:
    """캔버스를 이보다 줄일 수 없는 요소 범위 — 층은 공식 요소와 가정 배치 차이 요소(`overlay`) 둘
    다. FAB 는 지금 그리는 요소(저장된 것이 없으면 기본 배치 — 가정이 없다)."""
    if target.floor is None:
        _, marks = effective_fab_layout(None, load_fab_layout(database_path)[1])
        return marks_extent(marks)
    right, top = marks_extent(load_floor_layout_marks(database_path, *target.floor))
    overlay_right, overlay_top = overlay.mark_extent()
    return max(right, overlay_right), max(top, overlay_top)


def _outside_of(
    database_path: str,
    target: _CanvasTarget,
    saved_equipment: pd.DataFrame,
    canvas: CanvasSize,
) -> _CanvasOutside:
    """`canvas` 밖으로 나가는 것을 잰다. 호기 이탈은 **저장된 설비 마스터의 그 층 호기 전부**로
    잰다 — 저장 검증과 같은 행이다. 층 화면에 그린 호기(레이아웃표시 Y·조건 카드 필터를 지난 것)만
    보면 안 보이는 호기를 놓쳐, 알림 없이 줄인 뒤 다음 설비 저장이 전부 막힌다. 가정 설비 시나리오
    배치(설비 0031)의 이 층 차이 요소·호기도 본다 — FAB 는 가정이 없다."""
    overlay = (
        load_layout_overlay_extent(database_path, *target.floor)
        if target.floor is not None
        else LayoutOverlayExtent()
    )
    right, top = _marks_extent(database_path, target, overlay)
    return _CanvasOutside(
        units=(
            tuple(floor_equipment_outside_canvas(saved_equipment, target.floor, canvas))
            if target.floor is not None
            else ()
        ),
        overlay_units=overlay.units_outside(canvas) if target.floor is not None else (),
        overlay_marks=overlay.marks_outside(canvas) if target.floor is not None else (),
        mark_extent=(right, top),
        marks_outside=right > canvas[0] + 1e-9 or top > canvas[1] + 1e-9,
    )


def overlay_unit_words(outside: tuple[tuple[str, int], ...]) -> str:
    """「가정 배치 「셋업 실무」 호기 2대 · 「배치안」 호기 1대」 — 캔버스 밖 가정 차이 호기(알림
    전문의 평문)."""
    return " · ".join(f"가정 배치 「{name}」 호기 {count:,}대" for name, count in outside)


def overlay_mark_words(names: tuple[str, ...]) -> str:
    """「(가정 배치 「셋업 실무」 의 요소도 밖입니다 …)」 — 없으면 빈 글(알림 전문의 평문)."""
    if not names:
        return ""
    shown = ", ".join(f"「{name}」" for name in names)
    return f" 가정 배치 {shown} 의 요소도 밖입니다 — 그 설비 시나리오의 Space 에서 옮기세요."


def _unit_names(names: tuple[str, ...], limit: int = 5) -> str:
    """`DEMO-EQ01, DEMO-EQ02 외 3대(5대)` — 알림 전문에 실을 이탈 호기(평문)."""
    more = f" 외 {len(names) - limit}대" if len(names) > limit else ""
    return f"{', '.join(names[:limit])}{more}({len(names)}대)"


def _outside_full(target: _CanvasTarget, canvas: CanvasSize, outside: _CanvasOutside) -> str:
    """밖 알림의 전문 — 무엇이 밖인지 · 저장하면 어떻게 되나 · 어디서 고치나."""
    lines = [f"{target.title} 캔버스 {canvas[0]:g} × {canvas[1]:g}"]
    if outside.units:
        lines.append(
            f"호기 {with_subject_particle(_unit_names(outside.units))} 범위를 벗어납니다. 이대로 "
            "저장하면 가용설비 현황의 설비 마스터 저장이 전부 막힙니다 — 저장은 마스터 전체를 한 "
            "번에 검증하므로 다른 동·층만 고쳐도 같은 오류가 납니다. 레이아웃표시 N 이거나 조건 "
            "카드로 걸러 층 도면에 안 보이는 호기도 셉니다. 가용설비 현황에서 이 층 좌표를 먼저 "
            "고치세요."
        )
    if outside.overlay_units:
        lines.append(
            f"{with_subject_particle(overlay_unit_words(outside.overlay_units))} 범위를 "
            "벗어납니다 — 공식 배치는 그대로 저장되지만 그 설비 시나리오의 다음 저장이 막힙니다. "
            "그 시나리오의 Space 에서 먼저 옮기세요."
        )
    if outside.marks_outside:
        right, top = outside.mark_extent
        lines.append(
            f"도면 요소가 범위를 벗어나 저장할 수 없습니다(필요한 크기 {right:g} × {top:g}). Space "
            "배치 편집에서 요소를 옮기세요." + overlay_mark_words(outside.overlay_marks)
        )
    return "\n".join(lines)


def _outside_short(target: _CanvasTarget, canvas: CanvasSize, outside: _CanvasOutside) -> str:
    """밖 알림의 짧은 글 — 어디 캔버스에서 무엇이 밖인가."""
    parts = []
    if outside.unit_count:
        parts.append(f"호기 {outside.unit_count:,}대")
    if outside.marks_outside:
        parts.append("도면 요소")
    return (
        f"{target.title} 캔버스 {canvas[0]:g} × {canvas[1]:g} 밖 — {' · '.join(parts)}"
        if parts
        else ""
    )


def _report_outside(target: _CanvasTarget, canvas: CanvasSize, outside: _CanvasOutside) -> None:
    """고치는 크기 밖으로 나가는 것을 상태 알림으로 낸다 — 팝업 회차마다 같은 자리에서 한 번
    (없으면 `active=False`). 지문은 밖인 호기 · 요소 범위라 같은 것이 밖인 동안 칸을 더 눌러도 다시
    뜨지 않는다(팝업 안에서는 이벤트 칸을 쓰지 않는다 — `alerts.emit`)."""
    active = bool(outside.unit_count or outside.marks_outside)
    st.session_state[OUTSIDE_SHOWN_KEY] = active
    alerts.state(
        CANVAS_OUTSIDE_ALERT,
        scope=target.scope,
        content={
            "units": outside.units,
            "overlay": outside.overlay_units,
            "overlay_marks": outside.overlay_marks,
            "marks": outside.mark_extent if outside.marks_outside else None,
        },
        active=active,
        text=_outside_short(target, canvas, outside) if active else None,
        full=_outside_full(target, canvas, outside) if active else None,
        scope_label=target.title,
    )


def _save_lock(outside: _CanvasOutside, *, units_confirmed: bool) -> str | None:
    """저장을 막는 까닭 한 줄(잠긴 단추 풍선). 막을 것이 없으면 None."""
    if outside.marks_outside:
        right, top = outside.mark_extent
        return f"도면 요소가 캔버스 밖입니다 — 필요한 크기 {right:g} × {top:g}"
    if not units_confirmed:
        return "이탈 호기를 확인해 체크해야 저장합니다"
    return None


def _saved_line(
    target: _CanvasTarget, profile: _CanvasProfile | None, default_canvas: CanvasSize
) -> str:
    """지금 값 줄 하나(설계 규칙 UI-TXT-04) — 「**C1 1F** · 100 × 60 · 저장 시각」, 저장한 적이
    없으면 「기본값 폭 × 높이」."""
    if profile is None:
        return f"**{target.title}** · 기본값 {default_canvas[0]:g} × {default_canvas[1]:g}"
    width, height = profile.canvas_size
    return f"**{target.title}** · {width:g} × {height:g} · {profile.updated_at:%Y-%m-%d %H:%M}"


@st.dialog("캔버스 편집", on_dismiss=_dismiss)
@keeps_app_run_open
def _floor_canvas_dialog(
    *,
    database_path: str,
    target: _CanvasTarget,
    saved_equipment: pd.DataFrame,
    seen_stamp: DatabaseStamp,
) -> None:
    """한 범위(층·FAB)의 캔버스 폭·높이를 고친다. 설비 리비전과 무관한 단일 저장값이다.

    저장된 캔버스 · 도면 요소 · 가정 배치 차이는 본문에서 다시 읽는다(캐시). `saved_equipment` 는
    직전 앱 전체 회차가 넘긴 것이라 그 뒤 설비 DB 가 바뀌었으면(`seen_stamp` — 남의 저장) 앱 전체
    회차로 물러나 새 마스터로 다시 연다(`DialogHost` 쓰는 쪽이 지키는 것 1 — 열림 칸은 그대로다).
    """
    if database_stamp(database_path) != seen_stamp:
        st.rerun()
    profile = _load_profile(database_path, target)
    key = target.key
    saved = profile.canvas_size if profile is not None else target.default_canvas
    st.markdown(_saved_line(target, profile, target.default_canvas))
    with st.container(horizontal=True, gap="small"):
        width = st.number_input(
            "캔버스 폭",
            min_value=MIN_CANVAS_EXTENT,
            max_value=MAX_CANVAS_EXTENT,
            value=saved[0],
            step=1.0,
            key=f"{FLOOR_CANVAS_WIDGET_KEY}_width_{key}",
            width=160,
        )
        height = st.number_input(
            "캔버스 높이",
            min_value=MIN_CANVAS_EXTENT,
            max_value=MAX_CANVAS_EXTENT,
            value=saved[1],
            step=1.0,
            key=f"{FLOOR_CANVAS_WIDGET_KEY}_height_{key}",
            width=160,
        )
    canvas = (float(width), float(height))
    outside = _outside_of(database_path, target, saved_equipment, canvas)
    _report_outside(target, canvas, outside)
    units_confirmed = True
    if outside.unit_count:
        units_confirmed = st.checkbox(
            f"이탈 호기 {outside.unit_count:,}대 알고 저장",
            value=False,
            key=f"{FLOOR_CANVAS_WIDGET_KEY}_shrink_{key}",
        )
    lock = _save_lock(outside, units_confirmed=units_confirmed)
    save_clicked = st.button(
        "캔버스 저장",
        icon=":material/save:",
        type="primary",
        disabled=lock is not None,
        help=lock,
        key=f"{FLOOR_CANVAS_WIDGET_KEY}_save_{key}",
    )
    if not save_clicked or lock is not None:
        return
    if not _save(database_path=database_path, target=target, canvas=canvas):
        return
    # 저장소가 맞춘 값과 같은 정밀도로(대기분 기준값과 견줄 때 어긋나지 않게).
    written = normalize_canvas_size(*canvas)
    # 이 범위의 Space 미저장 캔버스는 버린다. 남겨 두면 팝업이 저장한 값을 가리고, 다음 저장이 옛
    # 대기값으로 되돌린다. 미저장 호기 좌표·도면 요소는 그대로 둔다 — 다음 저장이 새 캔버스로 다시
    # 검증해 밖이면 막는다. 이 세션의 대기분이 본 캔버스도 방금 쓴 값으로 바꾼다(남의 변경으로
    # 오인하지 않게).
    if target.floor is None:
        rebase_fab_canvas(written)
    else:
        rebase_floor_canvas(target.floor, written)
        stage_floor_canvas(target.floor, None)
    _queue_saved_alert(target, written, outside)
    CANVAS_DIALOG_HOST.finish()


def _queue_saved_alert(target: _CanvasTarget, written: CanvasSize, outside: _CanvasOutside) -> None:
    """저장 결과 알림 — 호기를 밖에 둔 채 저장했으면 그 뒤 막히는 것까지 말한다."""
    done = f"{target.title} 캔버스 {written[0]:g} × {written[1]:g} 저장"
    if outside.unit_count:
        alerts.event(
            "FL-03",
            text=f"{done} — 호기 {outside.unit_count:,}대가 밖이라 설비 저장이 막힙니다",
            full=_outside_full(target, written, outside),
        )
    else:
        alerts.event("FL-01", text=done)


def _save(*, database_path: str, target: _CanvasTarget, canvas: CanvasSize) -> bool:
    """저장하고 성공 여부를 돌려준다. 막히면 그 까닭을 팝업 안에 쓴다."""
    repository = get_equipment_repository(database_path)
    try:
        if target.floor is None:
            repository.save_fab_layout_canvas(*canvas)
        else:
            repository.save_floor_layout_canvas(*target.floor, *canvas)
    except BOOTSTRAP_ERRORS as exc:
        st.error(bootstrap_error_message(exc, database_paths=(Path(database_path),)))
        return False
    clear_floor_layout_cache()
    return True
