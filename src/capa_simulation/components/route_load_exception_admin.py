# Purpose: Admin Area 「부하 예외」 탭 — 공정별 부하 산출 예외 선언의 상태 줄 · 산식마다 공정 고르기
# · 저장 · 판 이력 표를 그린다.

"""Admin 「부하 예외」(공정별 부하 산출 예외 선언 — AGENTS 6장 「공정별 부하 산출 예외」 (i)).

**보이는 것.** 상태 줄 값 한 줄(「부하 예외 · 판 3 · 공정 2 · 11-23 09:12」 — 한 번도 저장하지
않았으면 「부하 예외 · 선언 없음」), 산식(`ROUTE_LOAD_FORMULAS`)마다 공정 다중 선택 하나, 「저장」
단추, 열린 탭이면 맨 아래 판 이력 표(판 · 언제 · 누가 — 앞 두 글자 · 공정 — 표시명 · 산식). 설명
글은 세우지 않는다 — 고르기 · 단추의 뜻은 풍선, 범위 · 하는 법은 Guide 다(설계 규칙 UI-TXT-01 ·
UI-TXT-02).

**고르는 공정.** 선택지는 활성 리비전 소요기준(`RQ_REQB`)의 원본 공정명이고 화면 글자는 표시명이
있으면 「표시명 (원본)」 이다(UI-DAT-10 — 저장값은 원본). 이번 데이터에 없는 선언 공정(과 고른
공정)도 선택지에 남기고 「(이번 데이터에 없음)」 을 붙인다 — 선택지에서 빠지면 다음 저장이 그 선언을
말없이 지운다(AGENTS 5장 26). 같은 공정인지는 계산과 같은 견줌 키(앞뒤 공백 · 대소문자)로 본다.

**본 판.** 고르기 칸은 지금 선언으로 채우고 그때의 판(`SEEDED`)을 함께 둔다 — 그 판이 저장의
「화면이 본 판」 이다(UI-STA-05). 남이 새 판을 저장하면 고친 것이 없는 칸은 다음 회차에 새 판으로
다시 채우고, 고친 칸은 그대로 둔다 — 그 칸으로 누른 저장은 본 판이 지난 판이라 쓰지
않고(`RouteLoadExceptionMoved`) 새 판을 다시 채운 뒤 알린다. 같은 단추의 빠른 두 번 누름은 제 저장
짝(`write_guard.save_remembered`)으로 가려 「남이 먼저 저장」 이라 하지 않고 칸을 저장된 판으로 다시
채운다. 거부를 보기 전에 닿은 같은 단추의 둘째 누름(옛 화면의 고른 값 · 다시 채운 본 판)은 거부
표지(`write_guard.held_profile_conflict`)로 쓰지 않고 그 거부를 다시 알린다. 지금 선언과 같은 저장은
새 판을 만들지 않는다(UI-STA-01). 모두 빼고 저장하면 선언 없음 판 한 줄이다 — 그 한 줄로 되돌릴 수
있어 확인 창은 두지 않는다(UI-STA-02).

**잠금.** 저장은 C-DEP 운영 자리의 실제 개발자에게만 열린다 — 「부대공정」 과 같은 판정
`sso_identity.production_write_lock_reason` 하나다. 잠긴 동안 고르기 · 단추를 잠그고 풍선에 까닭을
단다(UI-INP-07). 누른 회차에도 다시 판정하고, 저장소 쓰기는 `admin.area` 벽 뒤다. 쓰기는 본문에서
한다(콜백 아님).

**저장 뒤.** 공용 프로필을 비우고(`clear_global_route_load_exceptions_cache`) 이 세션의 입장 Summary
확인을 잊게 한 뒤(`forget_intro_summary_check`) 알림창 하나로 알린다(UI-NTF-03). 다른 세션은 다음
회차에 `PageContext` 가 새 판을 읽어 계산 토큰이 바뀌고 새 칸을 짓는다(AGENTS 5장 44 · 45).

**닫힌 탭도 그린다**(`app_pages/admin_area.py`) — 고르기 칸이 있어 건너뛰면 Streamlit 이 그 값을
버린다. 닫힌 회차는 공용 프로필 캐시(쓰기 세대 키)만 읽고 판 이력 표는 열린 회차에만 읽는다.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Final

import pandas as pd
import streamlit as st

from capa_simulation.components import sso_identity, write_guard
from capa_simulation.components.data_error_mark import render_data_error
from capa_simulation.components.flash import queue_flash, render_flash
from capa_simulation.components.intro_summary import forget_intro_summary_check
from capa_simulation.components.process_labels import ProcessLabels, get_process_labels
from capa_simulation.components.state_alerts import tab_name
from capa_simulation.navigation import ADMIN_AREA_ROUTE_EXCEPTION_TAB
from capa_simulation.page_bootstrap import BOOTSTRAP_ERRORS, bootstrap_error_message
from capa_simulation.persistence.cache import (
    clear_global_route_load_exceptions_cache,
    load_global_route_load_exceptions,
)
from capa_simulation.persistence.models import (
    RouteLoadExceptionEntries,
    RouteLoadExceptionProfile,
    RouteLoadExceptionState,
)
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.persistence.route_load_exception_store import (
    RouteLoadExceptionMoved,
    RouteLoadExceptionUnchanged,
)
from capa_simulation.services.frame_contracts import scalar_match_key
from capa_simulation.services.route_load_exceptions import ROUTE_LOAD_FORMULAS
from capa_simulation.session_slot import SessionSlot

TAB_LABEL: Final = ADMIN_AREA_ROUTE_EXCEPTION_TAB
FLASH_KEY: Final = "admin_route_exception_flash"
SAVE_BUTTON_KEY: Final = "admin_route_exception_save"
# 산식마다 고르기 칸 key 의 앞머리 — 칸은 `<앞머리>__<산식 id>`.
PICK_KEY: Final = "admin_route_exception_pick"
# 고르기 칸을 채운 선언의 (판, 항목) — 저장의 「화면이 본 판」.
SEEDED_KEY: Final = "admin_route_exception_seeded"
# 제 저장 짝의 저장 이름(`write_guard`).
SAVE_NAME: Final = "admin_route_exception"
# 판 이력 `source_place` — 어느 화면에서 저장했나.
SOURCE_PLACE: Final = "Admin Area"

STATUS_HEAD: Final = "부하 예외"
NO_DECLARATION: Final = "선언 없음"
SAVE_LABEL: Final = "저장"
MISSING_MARK: Final = "(이번 데이터에 없음)"
PICK_HELP: Final = (
    "고른 공정의 Wafer 경로 부하를 이 산식으로 냅니다 — 저장하면 모든 시나리오(공식 포함)의 "
    "소요대수 · 확보율에 곧바로 듭니다."
)
SAVE_HELP: Final = (
    "고른 공정을 새 판으로 저장합니다 — 모든 시나리오(공식 포함)의 소요대수 · 확보율에 곧바로 "
    "듭니다. 모두 빼고 저장하면 선언 없음 판입니다."
)
SAVED_MESSAGE: Final = (
    "부하 예외 판 {seq} 저장 — 모든 시나리오(공식 포함) 소요대수 · 확보율에 곧바로 듭니다"
)
UNCHANGED_MESSAGE: Final = (
    "바뀐 것이 없습니다 — 지금 부하 예외 선언 그대로라 새 판을 만들지 않았습니다."
)
MOVED_MESSAGE: Final = (
    "부하 예외 선언이 그 사이 바뀌어(지금 판 {seq}) 저장하지 않았습니다 — 바뀐 선언을 다시 "
    "불러왔으니 확인한 뒤 다시 저장하세요."
)
TWO_FORMULAS_MESSAGE: Final = "한 공정은 산식 하나에만 고를 수 있습니다 — 저장하지 않았습니다."
HISTORY_COLUMNS: Final = ("판", "언제", "누가", "공정", "산식")

# 세션 칸(AGENTS 5장 42 — 창구로만). 채운 판은 「있거나 없음」.
SEEDED: Final = SessionSlot(SEEDED_KEY, tuple)


def write_lock_reason() -> str | None:
    """저장을 잠그는 까닭 — 열려 있으면 None. 화면과 누른 회차가 함께 부른다. 판정은 「부대공정」 과
    같은 `sso_identity.production_write_lock_reason` 하나이고, 이 이름은 시험이 바꿔 끼우는
    자리다."""
    return sso_identity.production_write_lock_reason()


def pick_slot(formula: str) -> SessionSlot[list[str]]:
    """그 산식의 고르기 칸(원본 공정명 목록) — 위젯 key 칸이라 위젯을 만들기 전에만 쓴다."""
    return SessionSlot(f"{PICK_KEY}__{formula}", list, list)


def status_line(profile: RouteLoadExceptionProfile) -> str:
    """상태 줄 값 한 줄 — 판 · 공정 수 · 저장 시각만 싣고 공정 이름은 싣지 않는다(리뷰 압축본
    꼴)."""
    if profile.seq <= 0 or profile.created_at is None:
        return f"{STATUS_HEAD} · {NO_DECLARATION}"
    return " · ".join(
        (
            STATUS_HEAD,
            f"판 {profile.seq}",
            f"공정 {profile.process_count}",
            f"{profile.created_at:%m-%d %H:%M}",
        )
    )


def option_names(present: Sequence[str], extra: Sequence[str]) -> tuple[list[str], frozenset[str]]:
    """고르기 칸의 선택지(원본 공정명)와 이번 데이터에 있는 견줌 키.

    `present` 는 활성 리비전 소요기준 공정(견줌 키가 같은 것은 처음 표기 하나), `extra` 는 선언 ·
    고른 공정이다 — 견줌 키가 이번 데이터에 없으면 그 표기를 뒤에 더한다(빠지면 다음 저장이 지운다).
    """
    names: list[str] = []
    keys: set[str] = set()
    for name in present:
        key = scalar_match_key(name)
        if key and key not in keys:
            keys.add(key)
            names.append(name)
    present_keys = frozenset(keys)
    for name in extra:
        key = scalar_match_key(name)
        if key and key not in keys:
            keys.add(key)
            names.append(name)
    return names, present_keys


def option_texts(
    names: Sequence[str], *, labels: ProcessLabels, present_keys: frozenset[str]
) -> dict[str, str]:
    """선택지마다 보이는 글자 — 표시명이 있으면 「표시명 (원본)」, 이번 데이터에 없으면 끝에 표지.

    Streamlit 다중 선택은 값을 보이는 글자로 주고받는다 — 글자가 겹치면 다른 공정이 돌아오므로 겹친
    글자에는 「 (2)」 · 「 (3)」 을 붙인다(`ProcessLabels.unique_format_func` 와 같은 까닭).
    """
    texts: dict[str, str] = {}
    for name in names:
        shown = labels.label(name)
        text = name if shown == name else f"{shown} ({name})"
        if scalar_match_key(name) not in present_keys:
            text = f"{text} {MISSING_MARK}"
        texts[name] = text
    counts = Counter(texts.values())
    numbered: Counter[str] = Counter()
    for name in sorted(texts, key=lambda item: (texts[item], item)):
        text = texts[name]
        if counts[text] > 1:
            numbered[text] += 1
            if numbered[text] > 1:
                texts[name] = f"{text} ({numbered[text]})"
    return texts


def _grouped(entries: RouteLoadExceptionEntries) -> dict[str, frozenset[str]]:
    """항목을 산식마다 공정 견줌 키 묶음으로."""
    grouped: dict[str, set[str]] = {formula: set() for formula in ROUTE_LOAD_FORMULAS}
    for process, formula in entries:
        grouped.setdefault(formula, set()).add(scalar_match_key(process))
    return {formula: frozenset(keys) for formula, keys in grouped.items()}


def _picked() -> dict[str, frozenset[str]]:
    """지금 고르기 칸을 산식마다 공정 견줌 키 묶음으로."""
    return {
        formula: frozenset(scalar_match_key(name) for name in pick_slot(formula).get())
        for formula in ROUTE_LOAD_FORMULAS
    }


def _canonical(names: Sequence[str], present: Mapping[str, str]) -> list[str]:
    """견줌 키가 이번 데이터에 있으면 그 표기로, 견줌 키가 같은 둘은 처음 하나로 — 같은 공정이
    선택지에 두 번 서지 않고, 고른 값이 늘 선택지 안이게(`option_names` 와 같은 거름)."""
    kept: dict[str, str] = {}
    for name in names:
        key = scalar_match_key(name)
        kept.setdefault(key, present.get(key, name))
    return list(kept.values())


def _seed(profile: RouteLoadExceptionProfile, present: Mapping[str, str]) -> None:
    """고르기 칸을 지금 선언으로 채우고 그 판을 본 판으로 둔다."""
    for formula in ROUTE_LOAD_FORMULAS:
        declared = [process for process, chosen in profile.entries if chosen == formula]
        pick_slot(formula).set(_canonical(declared, present))
    SEEDED.set((profile.seq, profile.entries))


def _seeded_state() -> tuple[int, RouteLoadExceptionEntries] | None:
    held = SEEDED.peek()
    if (
        not isinstance(held, tuple)
        or len(held) != 2
        or not isinstance(held[0], int)
        or not isinstance(held[1], tuple)
    ):
        return None
    return held[0], held[1]


def _ensure_seeded(
    profile: RouteLoadExceptionProfile, present: Mapping[str, str]
) -> tuple[int, RouteLoadExceptionEntries]:
    """처음 회차 · 남이 새 판을 저장했고 고친 것이 없는 회차면 지금 선언으로 다시 채운다."""
    seeded = _seeded_state()
    if seeded is None or (seeded[0] != profile.seq and _picked() == _grouped(seeded[1])):
        _seed(profile, present)
        return profile.seq, profile.entries
    return seeded


def _masked(name: str | None) -> str:
    """저장한 사람은 앞 두 글자만(값 원문을 넓게 펴지 않는다 — 「부대공정」 판 이력과 같다)."""
    if not name:
        return ""
    return name[:2] + "…" if len(name) > 2 else name


def history_frame(state: RouteLoadExceptionState, labels: ProcessLabels) -> pd.DataFrame:
    """판 이력 표(새 판이 위) — 판 · 언제 · 누가(가림) · 공정(표시명) · 산식. 판마다 공정 한
    줄씩이고, 선언 없음 판은 공정 · 산식이 빈 한 줄이다."""
    rows = []
    for item in reversed(state.history):
        head = {
            "판": str(item.seq),
            "언제": f"{item.created_at:%Y-%m-%d %H:%M}",
            "누가": _masked(item.applied_by),
        }
        if not item.entries:
            rows.append({**head, "공정": "", "산식": ""})
            continue
        for process, formula in item.entries:
            rows.append(
                {
                    **head,
                    "공정": labels.label(process),
                    "산식": ROUTE_LOAD_FORMULAS.get(formula, formula),
                }
            )
    return pd.DataFrame(rows, columns=list(HISTORY_COLUMNS))


def render_route_load_exception_admin(
    repository: DuckDBScenarioRepository,
    processes: Sequence[str],
    *,
    database_path: str,
    alert_tab: str | None,
) -> None:
    """탭 본문. `processes` 는 활성 리비전 소요기준 공정(원본 — 못 읽으면 빈 목록), `alert_tab` 은
    이 탭 이름(열린 탭)이고 None 이면 닫힌 탭이다 — 닫힌 탭은 위젯만 세우고 판 이력 표를
    건너뛴다."""
    render_flash(FLASH_KEY)
    try:
        profile = load_global_route_load_exceptions(database_path)
    except BOOTSTRAP_ERRORS as exc:
        if alert_tab is not None:
            render_data_error(
                bootstrap_error_message(exc),
                code="AD-07",
                tab=tab_name(TAB_LABEL),
                text="부하 예외 선언을 읽지 못했습니다",
            )
        return
    labels = get_process_labels()
    present = {scalar_match_key(name): name for name in reversed(processes)}
    seeded = _ensure_seeded(profile, present)
    lock = write_lock_reason()
    st.caption(status_line(profile))
    picks: dict[str, list[str]] = {}
    for formula, formula_label in ROUTE_LOAD_FORMULAS.items():
        slot = pick_slot(formula)
        chosen = slot.get()
        declared = [process for process, kind in seeded[1] if kind == formula]
        canonical = _canonical(chosen, present)
        if canonical != chosen:
            slot.set(canonical)
        names, present_keys = option_names(processes, [*declared, *canonical])
        texts = option_texts(names, labels=labels, present_keys=present_keys)
        picks[formula] = list(
            st.multiselect(
                formula_label,
                names,
                key=slot.key,
                format_func=texts.__getitem__,
                disabled=lock is not None,
                help=lock or PICK_HELP,
                placeholder="",
            )
        )
    pressed = st.button(
        SAVE_LABEL,
        key=SAVE_BUTTON_KEY,
        icon=":material/save:",
        disabled=lock is not None,
        help=lock or SAVE_HELP,
    )
    if pressed:
        _save(repository, picks, seeded_seq=seeded[0])
    if alert_tab is not None:
        _render_history(repository, labels)


def _who() -> str | None:
    identity = sso_identity.verified_identity()
    return None if identity is None else identity.loginid


def _entries(picks: Mapping[str, Sequence[str]]) -> dict[str, str]:
    """고르기 칸을 선언(원본 공정명 → 산식 id)으로. 한 공정을 두 산식에 고르면 `ValueError`."""
    entries: dict[str, str] = {}
    seen: set[str] = set()
    for formula, names in picks.items():
        for name in names:
            key = scalar_match_key(name)
            if key in seen:
                raise ValueError(TWO_FORMULAS_MESSAGE)
            seen.add(key)
            entries[name] = formula
    return entries


def _after_save(seq: int, entries: Mapping[str, str] | None) -> None:
    """저장(또는 같은 누름의 첫 저장)을 마친 뒤 — 공용 프로필 비우기 · 입장 Summary 확인 잊기 · 본
    판 옮기기 · 알림. `entries` 가 None 이면(겹친 둘째 누름 — 이 누름의 고른 값이 저장된 값이라고
    말할 수 없다) 본 판을 비워 다음 회차가 저장된 판으로 칸을 다시 채운다."""
    clear_global_route_load_exceptions_cache()
    forget_intro_summary_check()
    if entries is None:
        SEEDED.clear()
    else:
        SEEDED.set((seq, tuple(entries.items())))
    queue_flash(FLASH_KEY, SAVED_MESSAGE.format(seq=seq))


def _save(
    repository: DuckDBScenarioRepository,
    picks: Mapping[str, Sequence[str]],
    *,
    seeded_seq: int,
) -> None:
    again = write_lock_reason()
    if again is not None:
        queue_flash(FLASH_KEY, again, kind="error", icon=":material/block:")
        st.rerun()
    try:
        entries = _entries(picks)
    except ValueError as exc:
        queue_flash(FLASH_KEY, bootstrap_error_message(exc), kind="error", icon=":material/error:")
        st.rerun()
    who = _who()
    # 표지 dict 는 쓰기 전에 받아 둔다 — 쓰기 뒤 세션 칸 접근은 둘째 누름의 회차에 끊길 수 있다.
    marks = write_guard.own_save_marks()
    conflicts = write_guard.profile_conflict_marks()
    held = write_guard.held_profile_conflict(conflicts, SAVE_NAME)
    if held is not None:
        # 남의 저장에 거부된 누름의 둘째 누름이다 — 거부 뒤 다시 채운 본 판을 들었지만 고른 값은 옛
        # 화면 것이라 쓰지 않고 그 거부를 다시 알린다(write_guard). 다음 회차가 새 판으로 다시
        # 채운다.
        SEEDED.clear()
        queue_flash(FLASH_KEY, held, kind="error", icon=":material/error:")
        st.rerun()
    try:
        saved = write_guard.save_remembered(
            SAVE_NAME,
            seeded_seq,
            lambda: repository.append_route_load_exceptions(
                expected_seq=seeded_seq,
                entries=entries,
                applied_by=who,
                source_place=SOURCE_PLACE,
            ),
            stored=lambda state: state.seq,
            marks=marks,
        )
    except RouteLoadExceptionUnchanged:
        queue_flash(FLASH_KEY, UNCHANGED_MESSAGE, kind="info", icon=":material/info:")
    except RouteLoadExceptionMoved as exc:
        if write_guard.is_own_save(SAVE_NAME, exc.expected, exc.current, marks):
            # 같은 단추의 빠른 두 번 누름이다 — 첫 누름이 이미 저장했다(write_guard).
            _after_save(exc.current, None)
        else:
            # 남이 먼저 새 판을 저장했다 — 쓰지 않고, 다음 회차가 새 판으로 고르기 칸을 다시 채운다.
            # 거부 표지는 곧바로 적는다 — 거부를 보기 전에 닿은 둘째 누름이 옛 고른 값으로 쓰지
            # 않게.
            message = MOVED_MESSAGE.format(seq=exc.current)
            write_guard.note_profile_conflict(conflicts, SAVE_NAME, message)
            clear_global_route_load_exceptions_cache()
            SEEDED.clear()
            queue_flash(FLASH_KEY, message, kind="error", icon=":material/error:")
    except (ValueError, *BOOTSTRAP_ERRORS) as exc:
        queue_flash(FLASH_KEY, bootstrap_error_message(exc), kind="error", icon=":material/error:")
    else:
        _after_save(saved.seq, entries)
    st.rerun()


def _render_history(repository: DuckDBScenarioRepository, labels: ProcessLabels) -> None:
    try:
        state = repository.load_route_load_exceptions()
    except (RuntimeError, *BOOTSTRAP_ERRORS) as exc:
        render_data_error(
            bootstrap_error_message(exc),
            code="AD-07",
            tab=tab_name(TAB_LABEL),
            text="부하 예외 판 이력을 읽지 못했습니다",
        )
        return
    if not state.history:
        return
    st.dataframe(
        history_frame(state, labels),
        hide_index=True,
        width="stretch",
        placeholder="",
    )
