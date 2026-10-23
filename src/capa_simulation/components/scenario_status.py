# Purpose: 사이드바 시나리오 필드와 리비전 불러오기·새 리비전 저장·편집 되돌리기 팝업을 그린다.

"""사이드바 「조회 조건」 패널의 시나리오 줄과 그 팝업(2026-10-10 사용자 결정).

**필드는 세션만 읽는다.** 패널은 모든 화면·모든 회차에 서므로, 회차마다 저장소를 세 번 읽던
접히는 상자(시나리오 목록·최신 공식버전·리비전 목록)를 걷고 머리 띠와 같은 세션 값만 본다 —
활성 이름표(`active_scenario_label`)·최신 공식버전(`latest_official_revision`)·미저장 여부.
저장소는 **팝업을 연 동안에만** 읽는다.

**팝업은 세션 키로 연다**(`SCENARIO_DIALOG_KEY`). 열림 키가 있는 동안 `app.py` 의 호스트 프래그먼트
(`sidebar_status.CONDITION_DIALOG_FRAGMENT_KEY`)가 매 회차 팝업을 부른다 — 팝업 안 조작은 팝업
(프래그먼트)만 다시 돌리고, 페이지가 다시 도는 회차에도 팝업이 닫히지 않는다. 값 칸을 누를 때와
닫을 때는 그 호스트만 다시 돌아 페이지를 다시 계산하지 않는다(여는 콜백의 마지막 줄 · 팝업이 호스트
안에서 만들어져 `on_dismiss` 가 호스트를 겨눈다). 키는 `PAGE_DIALOG_SUFFIX` 로 끝나 페이지를 옮기면
`forget_page_dialogs` 가 버린다. 한 실행에 팝업은 하나뿐이라 여는 콜백이 다른 팝업 칸부터 비운다.
닫기(X·바깥 클릭·Esc)는 `on_dismiss` 콜백이, 성공한 불러오기·저장·되돌리기는 `st.rerun()` 앞에서
직접 키를 지운다(`st.rerun()` 은 `on_dismiss` 를 거치지 않는다) — 이 셋은 원본을 바꾸므로 앱 전체를
다시 돌린다.

**팝업 안의 「불러오기」는 프래그먼트 실행이다.** 전에는 사이드바 버튼이 앱 전체 실행 한가운데서
`st.rerun()` 을 불러 그 회차에 그리지 않은 페이지 위젯 값(필터·탭)이 버려졌다. 프래그먼트 실행은
페이지 위젯을 건드리지 않아 그 값이 그대로 남는다. 편집표는 원본 토큰이 바뀌어 다음 회차에 페이지가
비운다(`scenario_edit_bar.reset_editors_on_source_change`). HOME 토글의 기본값 쓰기는 토글을 그리지
않는 이 실행에서 하므로 다음 회차 위젯에 새 값으로 닿는다(브라우저 실측).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

import streamlit as st

# 테스트가 `settings.DUCKDB_PATH` 를 갈아끼운다. 이름을 직접 import 하면 여기서 잡은
# 바인딩이 교체를 무시하므로 호출 시점에 모듈에서 찾는다.
import capa_simulation.settings as settings
from capa_simulation.components.capacity_gate import revision_save_verdict
from capa_simulation.components.condition_field import condition_field
from capa_simulation.components.intro_summary import latest_official_revision
from capa_simulation.components.literal_markdown import literal_markdown
from capa_simulation.components.page_link import render_page_link
from capa_simulation.components.revision_label import revision_label
from capa_simulation.components.scenario_edit_bar import (
    forget_pending_edits,
    pending_edit_labels,
)
from capa_simulation.components.scenario_management import (
    revision_tables_for_save,
    revision_virtual_product_rows,
    virtual_product_save_notice,
)
from capa_simulation.io.reference_cache import (
    get_effective_reference_tables,
    get_effective_reference_version,
)
from capa_simulation.navigation import SCENARIO_MANAGEMENT
from capa_simulation.page_bootstrap import (
    BOOTSTRAP_ERRORS,
    PAGE_DIALOG_SUFFIX,
    bootstrap_error_message,
    forget_page_dialogs,
    prune_choice,
)
from capa_simulation.persistence._sql_helpers import pinned_connections
from capa_simulation.persistence.cache import (
    get_scenario_repository,
    load_scenario_snapshot,
)
from capa_simulation.persistence.models import RevisionSummary, ScenarioSummary
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.scenario_activation import (
    activate_persisted_snapshot,
    activate_saved_revision,
    active_persisted_revision_id,
    active_persisted_scenario_id,
    active_scenario_label,
    discard_unsaved_scenario_changes,
    has_unsaved_scenario_changes,
)
from capa_simulation.scenario_preset_state import capture_scenario_preset
from capa_simulation.scenario_state import ensure_active_scenario
from capa_simulation.services.korean_particle import object_particle
from capa_simulation.services.revision_compatibility import revision_block_reason
from capa_simulation.sidebar_status import (
    CONDITION_DIALOG_FRAGMENT_KEY,
    keeps_app_run_open,
    rerun_fragment_if_alone,
)

# 팝업 안 시나리오·리비전 **초안**. 팝업을 열 때마다 올라와 있는 값으로 다시 적는다 — 닫힌 뒤에
# 「골랐지만 불러오지 않은 선택」이 남지 않는다. 그래서 `persist_state` 를 주지 않는다.
SIDEBAR_SCENARIO_KEY = "sidebar_scenario_id"
SIDEBAR_REVISION_KEY = "sidebar_revision_id"
SIDEBAR_FLASH_KEY = "sidebar_scenario_flash"
# 성공 알림과 함께 띄울 경고. 저장은 됐지만 남은 계산 오류가 있을 때 쓴다.
SIDEBAR_FLASH_WARNING_KEY = "sidebar_scenario_flash_warning"
# 저장 구획의 리비전명·메모 칸의 key 와 그 세대. 세대는 **저장에 성공한 회차**에만 올라 다음
# 회차에 두 칸이 새 빈 위젯으로 선다(`save_field_key`). 거절된 저장(적용 전 편집 미확인·계산
# 검사·저장 오류)은 세대를 그대로 두어 적은 글이 남는다.
SAVE_REVISION_NAME_KEY = "sidebar_revision_name"
SAVE_REVISION_NOTE_KEY = "sidebar_revision_note"
SAVE_FORM_GENERATION_KEY = "sidebar_revision_save_generation"
# 패널의 시나리오 값 칸. 누르면 팝업이 열린다.
SCENARIO_FIELD_KEY = "sidebar_scenario_field"
SCENARIO_FIELD_LABEL = "시나리오"
SCENARIO_DIALOG_TITLE = "시나리오·리비전"
# 팝업 열림 칸. `PAGE_DIALOG_SUFFIX` 로 끝나 페이지를 떠나면 비워진다.
SCENARIO_DIALOG_KEY = f"sidebar_scenario{PAGE_DIALOG_SUFFIX}"
# 팝업의 구획(불러오기 | 새 리비전 저장). 여는 콜백이 정한다 — 미저장이면 저장 구획으로 연다.
SCENARIO_DIALOG_MODE_KEY = "sidebar_scenario_dialog_mode"
LOAD_MODE = "불러오기"
SAVE_MODE = "새 리비전 저장"
# `시나리오 관리` 페이지가 `:material/database:` 를 쓴다. 사이드바에 같은 아이콘이 둘
# 나란히 서면 어느 것이 페이지이고 어느 것이 컨트롤인지 갈리지 않는다. `database` 는
# 저장소(관리 페이지)를 뜻하고, 여기는 **지금 보고 있는 한 겹**이라 `layers` 다.
SCENARIO_FIELD_ICON = ":material/layers:"
# 리비전 메모를 선택지 캡션에 붙일 때 자르는 길이. 캡션은 한 줄 정보다.
_NOTE_PREVIEW_LIMIT = 40


def render_scenario_field(*, pending_edits: Sequence[str] = ()) -> None:
    """패널의 시나리오 줄. **세션만 읽는다** — 회차마다 저장소를 보지 않는다.

    이름 줄 오른쪽에 상태 배지 하나(공식 vN / 저장된 리비전 / 미저장 변경), 값 칸에
    「시나리오명 · rN」. 저장하지 않은 편집이 있으면 값 칸 왼쪽에 주황 띠가 서고 팝업이 저장
    구획으로 열린다. 불러오기·저장 알림은 다음 회차에 한 번, 값 칸 바로 아래에 선다.

    `pending_edits` 는 이 화면에 적용하지 않은 편집이다. 패널 맨 위 주황 한 줄이 이미 말하므로
    여기서는 읽지 않는다 — 팝업이 누른 회차에 다시 센다(`render_scenario_dialog_body`).
    """
    del pending_edits
    flash = st.session_state.pop(SIDEBAR_FLASH_KEY, None)
    warning = st.session_state.pop(SIDEBAR_FLASH_WARNING_KEY, None)
    label = active_scenario_label()
    unsaved = has_unsaved_scenario_changes()
    # 값 칸은 버튼 라벨이라 마크다운으로 그려진다 — 사람이 적은 시나리오명은 글자 그대로 싣는다
    # (「*별*」 이 기울임이 되어 별표가 빠졌다). 말줄임 풍선도 그려진 글자를 쓴다.
    value = (
        f"{literal_markdown(label.scenario_name)} · r{label.revision_no}"
        if label is not None
        else "올라온 리비전 없음"
    )
    condition_field(
        scenario_name_label(label.revision_no if label is not None else None),
        value,
        slug="scenario",
        key=SCENARIO_FIELD_KEY,
        icon=SCENARIO_FIELD_ICON,
        status=scenario_status_badge(
            active_revision_id=active_persisted_revision_id(),
            official=latest_official_revision(),
            unsaved=unsaved,
        ),
        pending=unsaved,
        on_click=open_scenario_dialog,
    )
    # 알림은 **늘 서 있는 한 칸** 안에 그린다. 알림이 생기고 사라질 때 아래 줄(조회기간·페이지
    # 칸)의 자리가 밀려 새 요소로 다시 서지 않게 한다(AGENTS 9장 — 수가 바뀌는 알림). 빈 칸은
    # 높이가 없다.
    with st.container():
        if isinstance(flash, str):
            st.success(flash)
        if isinstance(warning, str):
            st.warning(warning, icon=":material/warning:")


def scenario_name_label(revision_no: int | None) -> str:
    """시나리오 이름 줄 왼쪽 글 — 「시나리오 · r12」.

    값 칸은 「시나리오명 · rN」(2026-10-10 사용자 결정 D3)인데, 시나리오명이 길면 칸 끝의
    「· rN」 이 늘 말줄임에 잘려 같은 시나리오 안에서 리비전을 바꿔도 칸으로는 갈리지 않았다
    (2026-10-11 병합 전 리뷰). 값 칸 글자 차례는 그대로 두고 리비전 번호를 이름 줄에도 적어 늘
    보이게 한다.
    """
    if revision_no is None:
        return SCENARIO_FIELD_LABEL
    return f"{SCENARIO_FIELD_LABEL} · r{revision_no}"


def scenario_status_badge(
    *,
    active_revision_id: str | None,
    official: tuple[str, int] | None,
    unsaved: bool,
) -> str:
    """시나리오 이름 줄의 배지 하나. 미저장이 먼저다 — 머리 띠(`header_lines`)와 같은 차례.

    `official` 은 이 세션이 마지막으로 확인한 최신 공식버전(리비전 id, 번호)이다. 머리 띠와 같은
    값이라 신선도도 같다(30초에 한 번, 이 세션에서 공식버전을 지정하면 곧바로).
    """
    if unsaved:
        return ":orange-badge[미저장 변경]"
    if active_revision_id is None:
        return ""
    if official is not None and official[0] == active_revision_id:
        return f":green-badge[공식 v{official[1]}]"
    return ":gray-badge[저장된 리비전]"


def open_scenario_dialog() -> None:
    """값 칸의 콜백. 다른 팝업 칸을 비우고, 초안을 올라와 있는 값으로 적고, 팝업을 연다.

    콜백은 스크립트보다 먼저 돌아 팝업 안 위젯이 만들어지기 **전**에 초안을 적는다. 미저장
    편집이 있으면 저장 구획으로 연다 — 그 편집을 남기려는 사람이 먼저 할 일이 저장이다.

    **마지막 줄**에서 팝업 호스트 프래그먼트만 다시 돌린다 — 여는 회차에 바뀌는 것은 열림 키와
    초안뿐이라 페이지를 다시 계산할 까닭이 없다. 판정을 못 넘으면(직전 실행이 끝나지 않음·다른
    위젯도 바뀜) 앱 전체를 다시 돌린다(`sidebar_status.rerun_fragment_if_alone`).
    """
    _open_dialog(
        active_persisted_scenario_id(),
        active_persisted_revision_id(),
        mode=SAVE_MODE if has_unsaved_scenario_changes() else LOAD_MODE,
    )
    rerun_fragment_if_alone(CONDITION_DIALOG_FRAGMENT_KEY, SCENARIO_FIELD_KEY)


def open_scenario_dialog_on(scenario_id: str, revision_id: str) -> None:
    """팝업을 「불러오기」 구획으로, 초안을 그 시나리오·리비전으로 미리 골라 연다.

    HOME 주요 Case 칩(`home_main_case_chips`)이 저장하지 않은 편집·적용 전 편집이 있을 때 쓴다 —
    사이드바에서 다른 리비전을 불러올 때와 **같은 확인**(「변경을 버리고 불러오기」 확인 칸과
    「불러오기」 단추)을 이 팝업 그대로 거친다. 칩의 콜백에서 부르고, 뒤이은 앱 전체 회차의 호스트
    프래그먼트가 팝업을 그린다 — 그래서 값 칸의 콜백과 달리 프래그먼트만 다시 돌리지 않는다.
    """
    _open_dialog(scenario_id, revision_id, mode=LOAD_MODE)


def _open_dialog(scenario_id: str | None, revision_id: str | None, *, mode: str) -> None:
    """다른 팝업 칸을 비우고, 초안 둘과 구획을 적고, 열림 키를 단다. 콜백에서만 부른다."""
    forget_page_dialogs()
    for key, value in ((SIDEBAR_SCENARIO_KEY, scenario_id), (SIDEBAR_REVISION_KEY, revision_id)):
        # 닫힌 팝업 안 위젯은 브라우저에 없으니 지워도 되돌아올 옛 값이 없다.
        if value is None:
            st.session_state.pop(key, None)
        else:
            st.session_state[key] = value
    st.session_state[SCENARIO_DIALOG_MODE_KEY] = mode
    st.session_state[SCENARIO_DIALOG_KEY] = True


def close_scenario_dialog() -> None:
    """팝업을 닫는다 — X·바깥 클릭·Esc(`on_dismiss`)와 성공한 동작이 부른다."""
    st.session_state.pop(SCENARIO_DIALOG_KEY, None)


def _finish(flash: str) -> None:
    """원본을 바꾼 동작(불러오기·저장·되돌리기)의 끝. 알림을 남기고 팝업을 닫고 앱을 다시 돌린다."""
    _settle(flash)
    st.rerun()


def _settle(flash: str) -> None:
    """원본을 바꾼 뒤의 세션 정리 — 알림을 남기고 팝업을 닫는다. 다시 돌리기는 부르는 쪽 몫이다.

    적용하지 않은 편집 목록도 비운다 — 다음 회차에 페이지가 그 편집을 버리기 전에 사이드바가 먼저
    「적용 전 편집」으로 세지 않게(`scenario_edit_bar.forget_pending_edits`).
    """
    st.session_state[SIDEBAR_FLASH_KEY] = flash
    forget_pending_edits()
    close_scenario_dialog()


def load_saved_revision(database_path: str, revision_id: str) -> str | None:
    """저장된 리비전 하나를 이 세션의 활성 시나리오로 올린다. 못 올렸으면 그 까닭 한 줄을 돌려준다.

    팝업의 「불러오기」와 HOME 주요 Case 칩(`home_main_case_chips`)이 함께 쓰는 **한 길**이다 —
    칩은 사이드바에서 그 리비전을 불러온 것과 똑같아야 한다(2026-10-23 사용자 결정). 활성화
    **전에** 옛 리비전 호환을 본다(시나리오 관리 화면의 불러오기와 같은 검사) — 활성화한 뒤에
    계산이 죽으면 활성 시나리오가 이미 바뀐 뒤라 화면에서 되돌릴 방법이 없다. 올렸으면 필드 아래
    알림을 남기고 적용 전 편집 목록을 비우고 팝업을 닫는다(`_settle`). 앱 전체를 다시 돌리는 것은
    부르는 쪽 몫이다 — 팝업은 `st.rerun()` 하고, 칩은 콜백이라 뒤이은 회차가 곧 새 시나리오의
    회차다. 못 올렸으면 활성 시나리오는 그대로다. DB 핀(`pinned_connections`)은 부르는 쪽이 잡는다.
    """
    try:
        snapshot = load_scenario_snapshot(database_path, revision_id)
        blocked = revision_block_reason(snapshot.tables)
        if blocked is not None:
            return blocked
        activate_persisted_snapshot(snapshot)
    except BOOTSTRAP_ERRORS as exc:
        return f"리비전을 불러오지 못했습니다: {bootstrap_error_message(exc)}"
    _settle(
        f"{literal_markdown(snapshot.scenario.scenario_name)} "
        f"r{snapshot.revision.revision_no}"
        f"{object_particle(str(snapshot.revision.revision_no))} 불러왔습니다."
    )
    return None


def scenario_dialog_is_open() -> bool:
    return SCENARIO_DIALOG_KEY in st.session_state


@st.dialog(
    SCENARIO_DIALOG_TITLE,
    width="medium",
    icon=SCENARIO_FIELD_ICON,
    on_dismiss=close_scenario_dialog,
)
def show_scenario_dialog(page_file: str | None) -> None:
    """팝업 껍데기. 열림 키가 있는 동안 `app.py` 의 호스트 프래그먼트가 매 회차 부른다. 본문은 아래
    함수다."""
    render_scenario_dialog_body(page_file=page_file)


@keeps_app_run_open
def render_scenario_dialog_body(
    database_path: Path | None = None, *, page_file: str | None
) -> None:
    """팝업 본문. 사이드바(`st.sidebar`)를 쓰지 않아 팝업 밖 테스트에서도 그대로 돈다.

    `database_path` 를 주지 않으면 **부를 때의** `settings.DUCKDB_PATH` 를 쓴다. 팝업 안 조작은
    `app.py` 의 실행 핀(`pinned_connections`) 밖에서 도는 프래그먼트라 여기서 다시 잡는다.

    본문이 도는 동안은 실행 표지를 「끝나지 않음」으로 내려 둔다(`keeps_app_run_open`) — 불러오기·
    저장·되돌리기가 앱 전체 재실행 전에 끊겨도 그 사이 누른 사이드바 클릭이 앱 전체를 다시 돌린다.

    적용하지 않은 편집은 **이 회차에** 센다(`page_file` 은 지금 화면의 파일 이름). 그 편집은
    시나리오에 들어 있지 않아 저장에 실리지 않고, 저장·불러오기가 원본을 바꾸는 순간 사라진다 —
    그래서 둘 다 한 번 더 묻는다(2026-09-29 2차 리뷰).
    """
    resolved = (settings.DUCKDB_PATH if database_path is None else database_path).resolve()
    with pinned_connections(resolved):
        _render_dialog_body(
            str(resolved),
            pending_edit_labels(page_file),
            on_management_page=page_file == Path(SCENARIO_MANAGEMENT.path).name,
        )


def _render_dialog_body(
    database_path: str, pending_edits: Sequence[str], *, on_management_page: bool = False
) -> None:
    active_scenario_id = active_persisted_scenario_id()
    active_revision_id = active_persisted_revision_id()
    unsaved = has_unsaved_scenario_changes()
    try:
        repository = get_scenario_repository(database_path)
        scenarios = repository.list_scenarios()
        official = repository.latest_official_release()
    except BOOTSTRAP_ERRORS as exc:
        st.error(f"시나리오 저장소를 읽지 못했습니다: {bootstrap_error_message(exc)}")
        return

    _render_dialog_header(
        active_revision_id=active_revision_id,
        official=(official.revision_id, official.release_no) if official is not None else None,
        unsaved=unsaved,
    )
    if not scenarios:
        st.info("저장된 시나리오가 없습니다.")
        st.caption("시나리오 관리 페이지에서 신규 시나리오를 등록하세요.")
        return
    if st.session_state.get(SCENARIO_DIALOG_MODE_KEY) not in (LOAD_MODE, SAVE_MODE):
        st.session_state[SCENARIO_DIALOG_MODE_KEY] = LOAD_MODE
    mode = st.segmented_control(
        "구획",
        options=[LOAD_MODE, SAVE_MODE],
        required=True,
        key=SCENARIO_DIALOG_MODE_KEY,
        label_visibility="collapsed",
    )
    scenario_by_id = {scenario.scenario_id: scenario for scenario in scenarios}
    if mode == SAVE_MODE:
        _render_revision_save(
            repository,
            scenario_by_id,
            active_scenario_id=active_scenario_id,
            active_revision_id=active_revision_id,
            pending_edits=pending_edits,
        )
        return
    _render_load(
        database_path,
        repository,
        scenario_by_id,
        official_revision_id=official.revision_id if official is not None else None,
        official_release_no=official.release_no if official is not None else None,
        active_scenario_id=active_scenario_id,
        active_revision_id=active_revision_id,
        unsaved=unsaved,
        pending_edits=pending_edits,
    )
    _render_rename_route(on_management_page=on_management_page)


def _render_rename_route(*, on_management_page: bool) -> None:
    """이름 바꾸는 곳으로 가는 한 줄(2026-10-22 결정 S7). 이름 변경은 시나리오 관리 페이지 몫이다.

    그 페이지에서 연 팝업이면 링크 대신 그 화면의 어디서 고치는지만 적는다 — 같은 페이지로 가는
    링크는 팝업을 닫지 않는다.
    """
    if on_management_page:
        st.caption("이름은 이 화면 「목록 관리」의 표에서 바로 고칩니다.")
        return
    render_page_link(
        SCENARIO_MANAGEMENT.path, label="시나리오 관리에서 이름 바꾸기", icon=":material/edit:"
    )


def _render_dialog_header(
    *, active_revision_id: str | None, official: tuple[str, int] | None, unsaved: bool
) -> None:
    """지금 올라와 있는 것 한 줄과 그 상태 배지. 이 팝업이 무엇을 바꾸는지의 기준점이다."""
    label = active_scenario_label()
    badge = scenario_status_badge(
        active_revision_id=active_revision_id, official=official, unsaved=unsaved
    )
    if label is None:
        st.caption("올라와 있는 리비전이 없습니다. 아래에서 불러오세요.")
        return
    st.caption(
        f"올라와 있음 · {literal_markdown(label.scenario_name)} · r{label.revision_no} "
        f"{literal_markdown(label.revision_name)}" + (f" {badge}" if badge else "")
    )


def _render_load(
    database_path: str,
    repository: DuckDBScenarioRepository,
    scenario_by_id: dict[str, ScenarioSummary],
    *,
    official_revision_id: str | None,
    official_release_no: int | None,
    active_scenario_id: str | None,
    active_revision_id: str | None,
    unsaved: bool,
    pending_edits: Sequence[str],
) -> None:
    """불러오기 구획. 작업 줄이 목록 **위**다 — 공정 필터 팝업과 같은 문법이다.

    시나리오 상자·리비전 radio 의 고른 값은 위젯 앞에서 **매 회차** 다시 적는다. 두 선택지 글자에
    든 시나리오명·리비전명은 다른 세션이 바꿀 수 있고, 팝업이 열린 동안 브라우저는 옛 글자를
    되보낸다. 적지 않으면 Streamlit 1.63 이 그 글자를 선택지에서 못 찾아 첫 항목으로 조용히
    되돌려 다음 「불러오기」가 고른 것과 다른 리비전에 걸린다(AGENTS 9장 「글자가 바뀌는 것을 피할
    수 없는 상자」).
    """
    selected_scenario_id = prune_choice(
        SIDEBAR_SCENARIO_KEY,
        list(scenario_by_id),
        default=(
            active_scenario_id
            if active_scenario_id is not None and active_scenario_id in scenario_by_id
            else next(iter(scenario_by_id))
        ),
    )
    try:
        revisions = repository.list_revisions(selected_scenario_id)
    except BOOTSTRAP_ERRORS as exc:
        st.error(f"리비전 목록을 읽지 못했습니다: {bootstrap_error_message(exc)}")
        return
    revision_by_id = {revision.revision_id: revision for revision in revisions}
    _ensure_revision_selection(
        scenario_by_id[selected_scenario_id],
        revision_by_id,
        active_scenario_id=active_scenario_id,
        active_revision_id=active_revision_id,
    )

    discard_changes = True
    if pending_edits:
        st.caption(_pending_edits_notice(pending_edits))
    if unsaved or pending_edits:
        # 미저장 배지는 머리 줄이 이미 단다. 여기서는 버린다는 확인만 받는다.
        discard_changes = st.checkbox(
            "변경을 버리고 불러오기",
            key="sidebar_discard_unsaved_changes",
        )
    with st.container(horizontal=True, gap="small"):
        load_clicked = st.button(
            "불러오기",
            icon=":material/download:",
            type="primary",
            disabled=not discard_changes or not revision_by_id,
            key="sidebar_load_revision",
        )
        # 저장하지 않은 편집을 버리고 올라와 있는 리비전으로 되돌린다. **모든 화면의 편집**을
        # 버리는 시나리오 단위 동작이라 불러오기 곁이 제자리다(2026-09-29 사용자 결정). 버릴
        # 것이 있을 때만 선다.
        reset_clicked = unsaved and st.button(
            "편집 되돌리기",
            icon=":material/restart_alt:",
            key="sidebar_reset_active_scenario",
            help="저장하지 않은 모든 화면의 편집을 버리고 올라와 있는 리비전으로 되돌립니다.",
        )

    st.selectbox(
        "시나리오",
        options=list(scenario_by_id),
        format_func=lambda value: _scenario_label(scenario_by_id[value]),
        key=SIDEBAR_SCENARIO_KEY,
    )
    if not revision_by_id:
        st.info("선택한 시나리오에 저장된 리비전이 없습니다.")
    else:
        options = list(revision_by_id)
        # 공식·올라와 있음처럼 회차마다 바뀌는 상태는 라벨이 아니라 캡션에 둔다 — 라벨이 바뀌면
        # 브라우저가 옛 라벨을 되보낸다(AGENTS 9장). 라벨의 리비전명도 이름 바꾸기로 바뀔 수 있어
        # `_ensure_revision_selection` 이 고른 값을 매 회차 되쓴다. radio 선택지는 마크다운으로
        # 그려져 사람이 적은 이름을 `literal_markdown` 으로 싣는다.
        st.radio(
            "리비전",
            options=options,
            format_func=lambda value: literal_markdown(revision_label(revision_by_id[value])),
            captions=[
                _revision_caption(
                    revision_by_id[revision_id],
                    official_revision_id=official_revision_id,
                    official_release_no=official_release_no,
                    active_revision_id=active_revision_id,
                )
                for revision_id in options
            ],
            key=SIDEBAR_REVISION_KEY,
        )

    if reset_clicked:
        discard_unsaved_scenario_changes(
            get_effective_reference_tables(), get_effective_reference_version()
        )
        _finish("저장하지 않은 편집을 버렸습니다.")
    if load_clicked:
        failure = load_saved_revision(database_path, str(st.session_state[SIDEBAR_REVISION_KEY]))
        if failure is not None:
            st.error(failure)
            return
        st.rerun()


def _pending_edits_notice(pending_edits: Sequence[str]) -> str:
    """적용하지 않은 편집이 어디에 남았고 저장·불러오기가 그것을 어떻게 하는지 한 줄로."""
    return (
        ":orange-badge[적용 전 편집] "
        + ", ".join(pending_edits)
        + " 의 적용하지 않은 편집은 저장에 들어가지 않고, 저장·불러오기를 하면 사라집니다."
    )


def _pending_save_refusal(pending_edits: Sequence[str]) -> str:
    """적용 전 편집을 버린다는 확인 없이 누른 저장을 막았을 때의 알림. 무엇을 하면 되는지까지."""
    return (
        "신규 리비전을 저장하지 않았습니다. "
        + ", ".join(pending_edits)
        + " 에 적용하지 않은 편집이 있습니다 — 먼저 「변경사항 적용」을 누르거나, 그 편집을 버려도"
        " 되면 「적용하지 않은 편집을 버리고 저장」을 체크한 뒤 다시 저장하세요."
    )


def _render_revision_save(
    repository: DuckDBScenarioRepository,
    scenario_by_id: Mapping[str, ScenarioSummary],
    *,
    active_scenario_id: str | None,
    active_revision_id: str | None,
    pending_edits: Sequence[str] = (),
) -> None:
    """새 리비전 저장 구획. 저장 대상은 **늘 올라와 있는 시나리오**다.

    막힌 저장의 까닭은 이 구획 안에 적는다. 팝업은 프래그먼트 재실행으로 닫히지 않으므로 팝업
    밖에 한 번 더 적던 장치(접히는 상자 시절의 popover 우회)가 필요 없다.
    """
    if active_scenario_id is None or active_revision_id is None:
        st.info("먼저 저장된 리비전을 불러오세요.")
        return
    active_summary = scenario_by_id.get(active_scenario_id)
    if active_summary is None:
        st.warning("올라와 있는 시나리오 정보를 찾지 못했습니다.")
        return
    # 공정 필터·조회기간은 리비전 프리셋이 담는다. 편집이 없어도 저장할 것이 있다는 사실을 남긴다.
    st.caption(
        f"「{literal_markdown(active_summary.scenario_name)}」에 새 리비전으로 저장합니다. "
        "지금 화면의 편집과 함께 조회기간·공정 필터도 담깁니다."
    )
    # 적용하지 않은 편집은 저장에 실리지 않고 저장하는 순간 사라진다. 그래서 그 편집을 버린다는
    # 확인 칸을 체크해야 저장한다. 확인 칸은 폼 **밖**이라 체크가 곧바로 세션에 남는다.
    dropping_confirmed = True
    if pending_edits:
        st.warning(_pending_edits_notice(pending_edits) + " 먼저 「변경사항 적용」을 누르세요.")
        dropping_confirmed = st.checkbox(
            "적용하지 않은 편집을 버리고 저장",
            key="sidebar_save_discards_pending_edits",
        )
    # `clear_on_submit` 을 쓰지 않는다. 그것은 **거절된 저장**에도 리비전명·메모를 지워, 막힌
    # 까닭을 고친 뒤 처음부터 다시 적어야 했다. 성공한 회차에만 칸의 key 세대를 올려 새 빈
    # 위젯으로 세운다(`save_field_key`).
    with st.form("sidebar_revision_save_form"):
        revision_name = st.text_input(
            "새 리비전명",
            placeholder="예: 공정 조건 변경안",
            key=save_field_key(SAVE_REVISION_NAME_KEY),
        )
        note = st.text_area(
            "변경 메모",
            height=80,
            key=save_field_key(SAVE_REVISION_NOTE_KEY),
        )
        # **저장 버튼은 잠그지 않는다**(2026-10-01 브라우저 E2E). 잠긴 버튼으로 온 제출은
        # Streamlit 이 서버에서 버려 `submitted` 가 그냥 False 가 된다. 누른 회차의 목록으로
        # 판정해 막고 알린다.
        submitted = st.form_submit_button(
            "신규 리비전 저장",
            icon=":material/save_as:",
            type="primary",
        )
    if not submitted:
        return
    if not dropping_confirmed:
        st.warning(_pending_save_refusal(pending_edits), icon=":material/block:")
        return

    try:
        # `REVISION_TABLES` 14개를 통째로 새 리비전으로 적는다(표시순서·모듈수는
        # 시나리오에 종속되지 않는 공용 프로필이라 빠진다). 표가 크면 몇 초가 걸린다.
        with st.spinner("현재 편집본을 새 리비전으로 저장하는 중입니다..."):
            reference_version = get_effective_reference_version()
            reference_tables = get_effective_reference_tables()
            active_scenario = ensure_active_scenario(reference_tables, reference_version)
            verdict = revision_save_verdict(reference_version, active_scenario, reference_tables)
            if not verdict.allowed:
                st.error(verdict.message)
                return
            revision_tables = revision_tables_for_save(active_scenario, reference_tables)
            # 활성화가 세션의 가상 제품 목록을 비우므로 그 전에 읽는다. 불러온 리비전의
            # 이력도 함께 물려준다.
            virtual_products = revision_virtual_product_rows(
                repository, active_revision_id, revision_tables
            )
            snapshot = repository.save_revision(
                active_scenario_id,
                revision_tables,
                capture_scenario_preset(
                    {**reference_tables, "RQ_REQB": revision_tables["RQ_REQB"]}
                ),
                revision_name=revision_name,
                parent_revision_id=active_revision_id,
                note=note.strip() or None,
                virtual_products=virtual_products,
            )
            # 방금 보던 내용을 그대로 적은 리비전이라 HOME 토글은 켜 둔 채 둔다.
            activate_saved_revision(snapshot)
    except BOOTSTRAP_ERRORS as exc:
        st.error(f"신규 리비전을 저장하지 못했습니다: {bootstrap_error_message(exc)}")
        return
    if verdict.message:
        st.session_state[SIDEBAR_FLASH_WARNING_KEY] = verdict.message
    st.session_state[SAVE_FORM_GENERATION_KEY] = save_form_generation() + 1
    _finish(
        f"신규 리비전 r{snapshot.revision.revision_no}"
        f"{object_particle(str(snapshot.revision.revision_no))} 저장했습니다."
        + virtual_product_save_notice(len(virtual_products))
    )


def save_form_generation() -> int:
    """저장 구획 두 칸의 key 세대. 저장에 성공할 때마다 하나씩 오른다."""
    value = st.session_state.get(SAVE_FORM_GENERATION_KEY, 0)
    return value if isinstance(value, int) else 0


def save_field_key(base: str) -> str:
    """저장 구획 한 칸(`SAVE_REVISION_NAME_KEY`·`SAVE_REVISION_NOTE_KEY`)의 지금 위젯 key.

    **세션 칸에 빈 값을 적는 것으로는 비워지지 않는다**(2026-10-08 안정화 점검). 두 칸은 닫힌
    팝업 안이라 저장에 성공한 다음 회차에 브라우저에 마운트되어 있지 않고, 서버가 보낸 새 값을
    받지 못한 채 옛 값을 들고 있다가 다음 조작에 되보냈다. key 세대를 바꾸면 브라우저에게는 처음
    보는 위젯이라 빈 칸으로 서고, 옛 key 의 값은 다음 회차에 그려지지 않아 버려진다(시나리오
    관리 복제 폼의 `clone_field_key` 와 같은 방식). 첫 세대는 바탕 key 그대로다.
    """
    generation = save_form_generation()
    return base if generation == 0 else f"{base}__g{generation}"


def _ensure_revision_selection(
    scenario: ScenarioSummary,
    revision_by_id: Mapping[str, object],
    *,
    active_scenario_id: str | None,
    active_revision_id: str | None,
) -> None:
    """리비전 초안을 위젯 앞에서 **매 회차 다시 적는다**(지우지 않는다).

    목록에 있으면 그 값 그대로 — 리비전명이 바뀌어도 브라우저가 새 글자를 받게 한다. 고른 시나리오가
    바뀌어 목록에 없으면 같은 시나리오는 올라와 있는 리비전, 다른 시나리오는 그 시나리오의 최신
    리비전이다. 위젯을 만들기 전에 부른다.
    """
    if not revision_by_id:
        return
    preferred = (
        active_revision_id
        if scenario.scenario_id == active_scenario_id
        else scenario.active_revision_id
    )
    prune_choice(
        SIDEBAR_REVISION_KEY,
        list(revision_by_id),
        default=(
            preferred
            if preferred is not None and preferred in revision_by_id
            else next(iter(revision_by_id))
        ),
    )


def _scenario_label(summary: ScenarioSummary) -> str:
    return f"{summary.scenario_name} · {summary.source_simulation_code}"


def _revision_caption(
    revision: RevisionSummary,
    *,
    official_revision_id: str | None,
    official_release_no: int | None,
    active_revision_id: str | None,
) -> str:
    """리비전 선택지 아래 한 줄 — 저장일 · 공식 여부 · 올라와 있음 · 메모."""
    parts = [f"{revision.created_at:%y.%m.%d} 저장"]
    if official_release_no is not None and revision.revision_id == official_revision_id:
        parts.append(f"공식 v{official_release_no}")
    if revision.revision_id == active_revision_id:
        parts.append("올라와 있음")
    note = (revision.note or "").strip().replace("\n", " ")
    if note:
        # 캡션은 마크다운으로 그려진다. 메모(사람·시스템이 적은 글)는 글자 그대로 싣는다.
        shown = note if len(note) <= _NOTE_PREVIEW_LIMIT else note[:_NOTE_PREVIEW_LIMIT] + "…"
        parts.append(literal_markdown(shown))
    return " · ".join(parts)
