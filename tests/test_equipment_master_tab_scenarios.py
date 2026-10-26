# Purpose: 설비 마스터 탭(새 길)의 가정·낡은 세션 배치 판정·역할 찍기·엑셀·CSV 팝업 규칙을 본다.

"""탭 ① 「설비 마스터」 — 설비 시나리오 상태별(개편 명세 4-8·4-10·9-3, 설비 시나리오 2단계 S3).

옛 RawData 폼(개편 D 에서 걷음)을 몰던 시험 묶음이 지키던 규칙을 새 길(페이지 → 표 대역 출납 ·
「엑셀·CSV로 한꺼번에」 팝업 · 「리비전 저장」)로 다시 본다:

- 가정 세션 — 배치 칸은 그 시나리오의 배치 차이로 저장(Q2 붙여넣기 「배치 칸도 붙여넣기」 기본 끔),
  공식 층이 다른 호기를 한 묶음으로 묶는 고침은 「저장하기 전에 고칠 것」 에 오르고 저장이 막힌다,
  「공식 자리로 되돌리기」.
- 배치를 바꾸는 적용(표 출납·팝업 넣기·되돌리기)은 그때의 역할을 찍는다(설계 6-2).
- 팝업 — 낡은 세션·배치 잠금 거절, 붙여넣은 열만 바꿈, 새 방문·다시 열기 때 미리보기 거둠, CSV
  칸 상한.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from grid_fake import Calls, install_fake_grid, last, load, send, send_ops
from streamlit.testing.v1 import AppTest
from test_equipment_assumption_rawdata import _grouped_fleet, _two_scenarios
from test_equipment_pages import PROJECT_ROOT, _page_script
from test_equipment_scenario_repository import (
    _clone,
    _request,
    _scenario,
    _seeded,
    _session,
    _set,
)

from capa_simulation.components import equipment_master_grid as emg
from capa_simulation.components.equipment_data_workspace import (
    BUFFER_KEY,
    CLIPBOARD_KEY,
    CSV_UPLOAD_LIMIT_MB,
    GRID_DETAIL_KEY,
    GRID_LOADED_KEY,
    LAYOUT_ROLE_KEY,
    PASTE_LAYOUT_KEY,
    PREVIEW_BUTTON_KEY,
    PREVIEW_KEY,
    TARGET_KEY,
    ImportReview,
)
from capa_simulation.components.equipment_import_dialog import IMPORT_APPLY_BUTTON_KEY
from capa_simulation.components.equipment_master_tab import (
    SAVE_BUTTON_KEY,
    SIDE_CHANGES,
    SIDE_HISTORY,
    SIDE_KEY,
    STALE_SCENARIO_EDITS,
    TABLE_KEY,
    save_target,
)
from capa_simulation.components.equipment_save_fields import EquipmentSaveBasis
from capa_simulation.components.equipment_settings_dialog import EQUIPMENT_DIALOG_KEY
from capa_simulation.equipment_scenario_activation import SELECTION_KEY
from capa_simulation.navigation import EQUIPMENT_MASTER_TAB, EQUIPMENT_TAB_KEY
from capa_simulation.page_bootstrap import PAGE_VISIT_KEY
from capa_simulation.persistence.equipment_cache import clear_equipment_repository
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository

PAGE = PROJECT_ROOT / "app_pages" / "available_equipment_status.py"
OPERATIONS = "operations"
GROUP_REFUSAL = "가정 설비 시나리오에서는 공식 층이 다른 호기를 한 묶음으로 묶지 않습니다"


@pytest.fixture(autouse=True)
def _release_repository() -> Any:
    clear_equipment_repository()
    yield
    clear_equipment_repository()


@pytest.fixture
def grid(monkeypatch: pytest.MonkeyPatch) -> Calls:
    return install_fake_grid(monkeypatch)


def _page(
    repository: DuckDBEquipmentRepository, scenario_id: str, schedule_revision_id: str | None = None
) -> AppTest:
    """그 설비 시나리오 세션으로 연 가용설비 현황 탭 ① (표 대역)."""
    clear_equipment_repository()
    app = AppTest.from_string(_page_script(PAGE, repository.database_path), default_timeout=90)
    app.session_state[EQUIPMENT_TAB_KEY] = EQUIPMENT_MASTER_TAB
    app.session_state[SELECTION_KEY] = {
        "scenario_id": scenario_id,
        "schedule_revision_id": schedule_revision_id,
    }
    return _ok(app.run())


def _ok(app: AppTest) -> AppTest:
    assert not app.exception, [item.message for item in app.exception]
    return app


def _texts(app: AppTest, kind: str) -> list[str]:
    return [str(item.value) for item in getattr(app, kind)]


def _buffer_value(app: AppTest, name: str, column: str) -> Any:
    return app.session_state[BUFFER_KEY][1].set_index("설비명").loc[name, column]


def _load_all(app: AppTest, grid: Calls) -> None:
    load(app, [], kind="all")


def _preview(app: AppTest, text: str, *, target: str = "설비 마스터") -> AppTest:
    """팝업을 열고 붙여넣은 뒤 「변경 미리보기」."""
    app.session_state[EQUIPMENT_DIALOG_KEY] = "import"
    _ok(app.run())
    app.selectbox(key=TARGET_KEY).set_value(target)
    app.text_area(key=CLIPBOARD_KEY).set_value(text)
    app.button(key=PREVIEW_BUTTON_KEY).click()
    return _ok(app.run())


def _save(app: AppTest) -> AppTest:
    app.session_state[SIDE_KEY] = SIDE_CHANGES
    _ok(app.run())
    app.button(key=SAVE_BUTTON_KEY).click()
    return _ok(app.run())


# ------------------------------------------------------------------ 가정 세션 — 묶음 거부 줄


def test_an_assumption_group_across_official_floors_is_a_fix_first_line_without_differences(
    tmp_path: Path, grid: Calls
) -> None:
    """배치 차이가 아직 없는 가정 시나리오(갓 복제 — `official_places` 빈 dict)에서도 공식 층이 다른
    호기를 한 묶음으로 묶는 고침은 「저장하기 전에 고칠 것」 에 오르고 오류 수에 든다(리뷰 rs-b1y —
    전에는 저장을 누른 회차에야 저장소가 거부했다)."""
    repository, setup = _grouped_fleet(tmp_path)
    app = _page(repository, setup)
    _load_all(app, grid)
    send_ops(
        app,
        grid,
        {"op": "cell", "id": "s:EQ-03", "col": "Main 설비", "text": "MOD-1"},
        {"op": "cell", "id": "s:EQ-03", "col": "층", "text": "1F"},
    )
    app.session_state[SIDE_KEY] = SIDE_CHANGES
    _ok(app.run())
    changes = last(grid, emg.side_key("changes"))
    assert changes["counts"]["errors"] >= 1
    assert any(GROUP_REFUSAL in " ".join(map(str, line)) for line in changes["errors"])
    assert any("오류" in text and "고쳐야 저장됩니다" in text for text in _texts(app, "caption"))
    before = len(repository.list_revisions())
    app.button(key=SAVE_BUTTON_KEY).click()
    _ok(app.run())
    assert len(repository.list_revisions()) == before
    assert any("고쳐야 저장됩니다" in text for text in _texts(app, "error"))


# ------------------------------------------------------------------ 역할 찍기


def test_an_import_that_moves_layout_cells_stamps_the_role(tmp_path: Path, grid: Calls) -> None:
    """「편집본에 넣기」 는 저장하지 않으므로 배치 칸을 바꾼 넣기는 그때의 역할을 찍는다 — 넣은 뒤
    저장 전에 역할이 바뀌면 저장소가 대조해 막는다(설계 6-2, 리뷰 rs-b1y). 배치 칸이 아닌 넣기는
    찍지 않는다."""
    repository, _ = _two_scenarios(tmp_path)
    app = _page(repository, OPERATIONS)
    _preview(app, "설비명\t설비이력\nEQ-01\t넣은 이력")
    app.button(key=IMPORT_APPLY_BUTTON_KEY).click()
    _ok(app.run())
    assert _buffer_value(app, "EQ-01", "설비이력") == "넣은 이력"
    assert LAYOUT_ROLE_KEY not in app.session_state

    _preview(app, "설비명\tX좌표\nEQ-01\t55")
    app.button(key=IMPORT_APPLY_BUTTON_KEY).click()
    _ok(app.run())
    assert _buffer_value(app, "EQ-01", "X좌표") == 55
    assert app.session_state[LAYOUT_ROLE_KEY] == "official"


def test_an_assumption_import_with_layout_cells_saves_as_that_scenarios_difference(
    tmp_path: Path, grid: Calls
) -> None:
    """가정 세션 팝업 「배치 칸도 붙여넣기」 는 기본 끔이다(Q2) — 끄면 있던 호기 배치 칸은 지금 값,
    켜면 그 시나리오의 배치 차이로 들어가 역할 "overlay" 를 찍고, 저장하면 공식은 그대로다."""
    repository, setup = _two_scenarios(tmp_path)
    app = _page(repository, setup)
    _preview(app, "설비명\tX좌표\nEQ-01\t55")
    assert not app.checkbox(key=PASTE_LAYOUT_KEY).value
    review = app.session_state[PREVIEW_KEY]
    assert isinstance(review, ImportReview)
    assert review.candidate[1].set_index("설비명").loc["EQ-01", "X좌표"] == 10
    assert any("배치 칸은 붙여넣지 않고 지금 값을 두었습니다" in text for text in review.notices)

    app.checkbox(key=PASTE_LAYOUT_KEY).check()
    app.button(key=PREVIEW_BUTTON_KEY).click()
    _ok(app.run())
    review = app.session_state[PREVIEW_KEY]
    assert review.candidate[1].set_index("설비명").loc["EQ-01", "X좌표"] == 55
    assert any("가정 배치 1대(EQ-01)가 바뀝니다" in text for text in review.cautions)
    app.button(key=IMPORT_APPLY_BUTTON_KEY).click()
    _ok(app.run())
    assert _buffer_value(app, "EQ-01", "X좌표") == 55
    assert app.session_state[LAYOUT_ROLE_KEY] == "overlay"

    _save(app)
    scenario = _scenario(repository, setup)
    assert scenario.latest_revision_no == 2 and scenario.latest_layout_unit_count == 1
    assert _session(repository).equipment.set_index("설비명").loc["EQ-01", "X좌표"] == 10
    assert _session(repository, setup).equipment.set_index("설비명").loc["EQ-01", "X좌표"] == 55


def test_undo_that_brings_a_layout_edit_back_stamps_the_role_again(
    tmp_path: Path, grid: Calls
) -> None:
    """칸 되돌리기로 배치 편집이 사라지면 찍힘이 걷힌다(`live_layout_role`). 그 되돌리기를 한 단계
    되돌려 배치 편집이 돌아오면 다시 찍는다(리뷰 rs-b1y — 전에는 되돌리기를 찍지 않았다)."""
    repository, _ = _two_scenarios(tmp_path)
    app = _page(repository, OPERATIONS)
    _load_all(app, grid)
    send_ops(app, grid, {"op": "cell", "id": "s:EQ-01", "col": "X좌표", "text": "55"})
    assert app.session_state[LAYOUT_ROLE_KEY] == "official"
    send_ops(app, grid, {"op": "revert", "id": "s:EQ-01", "col": "X좌표"})
    assert _buffer_value(app, "EQ-01", "X좌표") == 10
    assert LAYOUT_ROLE_KEY not in app.session_state
    send_ops(app, grid, {"op": "undo"})
    assert _buffer_value(app, "EQ-01", "X좌표") == 55
    assert app.session_state[LAYOUT_ROLE_KEY] == "official"


def test_a_stamped_session_measures_layout_edits_once_per_buffer_generation(
    tmp_path: Path, grid: Calls, monkeypatch: pytest.MonkeyPatch
) -> None:
    """역할이 찍힌 세션은 회차마다 `live_layout_role` 이 편집본 배치 편집을 본다 — 편집본 세대 열쇠
    메모로 바뀐 것 없는 회차·배치에 닿지 않는 칸 고침 회차에는 편집본 전체를 다시 재지 않는다(개편
    명세 8장 예산, 리뷰 rs-b1y 측정)."""
    from capa_simulation.components import equipment_data_workspace as workspace

    repository, _ = _two_scenarios(tmp_path)
    app = _page(repository, OPERATIONS)
    _load_all(app, grid)
    send_ops(app, grid, {"op": "cell", "id": "s:EQ-01", "col": "X좌표", "text": "55"})
    assert app.session_state[LAYOUT_ROLE_KEY] == "official"
    calls: list[int] = []
    original = workspace.layout_edits

    def counted(*args: Any, **kwargs: Any) -> Any:
        calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(workspace, "layout_edits", counted)
    for _ in range(3):
        _ok(app.run())
    send_ops(app, grid, {"op": "cell", "id": "s:EQ-02", "col": "담당자", "text": "홍길동"})
    assert _buffer_value(app, "EQ-02", "담당자") == "홍길동"
    assert app.session_state[LAYOUT_ROLE_KEY] == "official"
    assert calls == []
    # 배치 칸 고침은 다시 잰다(한 번).
    send_ops(app, grid, {"op": "cell", "id": "s:EQ-02", "col": "X좌표", "text": "66"})
    assert len(calls) == 1


# ------------------------------------------------------------------ 공식 자리로 되돌리기


def test_the_official_place_revert_from_the_detail_saves_without_a_difference(
    tmp_path: Path, grid: Calls
) -> None:
    """가정 시나리오에 배치 차이가 있는 호기 — 호기 상세 「공식 자리로 되돌리기」 가 공식 일곱 칸을
    편집본에 적고(설계 13-1), 저장하면 그 시나리오의 배치 차이가 빠진다."""
    repository, setup = _two_scenarios(tmp_path)
    mine = _session(repository, setup)
    repository.save_equipment(
        _request(
            mine,
            setup,
            equipment=_set(mine.equipment, "EQ-01", "X좌표", 50.0),
            expected_layout_role="overlay",
        )
    )
    assert _scenario(repository, setup).latest_layout_unit_count == 1
    app = _page(repository, setup)
    assert _buffer_value(app, "EQ-01", "X좌표") == 50
    _load_all(app, grid)
    send(app, emg.GRID_KEY, "open", {"view": last(grid, emg.GRID_KEY)["view"], "id": "s:EQ-01"})
    detail = last(grid, emg.side_key("detail"))
    assert detail["unit"]["official"]["count"] == 1
    send_ops(app, grid, {"op": "official", "id": "s:EQ-01"}, key=emg.side_key("detail"))
    assert _buffer_value(app, "EQ-01", "X좌표") == 10
    assert last(grid, emg.side_key("detail"))["toast"]["text"].startswith(
        "공식 자리로 되돌렸습니다 — 1대"
    )
    _save(app)
    assert _scenario(repository, setup).latest_layout_unit_count == 0
    assert _session(repository).equipment.set_index("설비명").loc["EQ-01", "X좌표"] == 10


# ------------------------------------------------------------------ 엑셀·CSV 팝업


def test_the_import_dialog_pastes_only_the_pasted_columns(tmp_path: Path, grid: Calls) -> None:
    """설비 마스터 붙여넣기는 설비명과 붙인 열만 바꾼다(`read_equipment_update` — 옛 입력 탭
    그대로)."""
    repository, _ = _two_scenarios(tmp_path)
    app = _page(repository, OPERATIONS)
    before = app.session_state[BUFFER_KEY][1].copy()
    _preview(app, "설비명\t담당자\nEQ-02\t김담당")
    review = app.session_state[PREVIEW_KEY]
    assert isinstance(review, ImportReview)
    app.button(key=IMPORT_APPLY_BUTTON_KEY).click()
    _ok(app.run())
    after = app.session_state[BUFFER_KEY][1]
    assert after.set_index("설비명").loc["EQ-02", "담당자"] == "김담당"
    untouched = [column for column in before.columns if column != "담당자"]
    pd.testing.assert_frame_equal(
        before[untouched].reset_index(drop=True), after[untouched].reset_index(drop=True)
    )
    assert EQUIPMENT_DIALOG_KEY not in app.session_state


def _tsv(frame: pd.DataFrame) -> str:
    """표를 엑셀에서 복사한 꼴(탭·줄바꿈)로 — 날짜는 `YYYY-MM-DD`, 빈 칸은 빈 글."""

    def text(value: Any) -> str:
        if pd.isna(value):
            return ""
        return f"{value:%Y-%m-%d}" if isinstance(value, pd.Timestamp) else str(value)

    rows = ["\t".join(text(value) for value in row) for row in frame.itertuples(index=False)]
    return "\n".join(["\t".join(frame.columns), *rows])


def test_an_import_that_changes_nothing_leaves_no_unsaved_edit(tmp_path: Path, grid: Calls) -> None:
    """지금 값 그대로인 붙여넣기·CSV(날짜 칸 포함)를 넣어도 편집본 세대가 오르지 않는다 — 저장본
    사본의 날짜 칸은 `datetime64[us]`, 넣은 표는 `[ns]` 라 `DataFrame.equals` 가 「바뀜」 으로 읽어
    「저장 전 변경」 0건인데 「미저장 변경」·탭 점·떠나기 확인이 남았다(E2E). 비가동 일정도 같고,
    낡은 세션은 그대로인 비가동 붙여넣기를 거절하지 않는다."""
    from capa_simulation.components.equipment_data_workspace import BUFFER_GENERATION_KEY

    repository, setup = _two_scenarios(tmp_path)
    app = _page(repository, OPERATIONS)
    generation = app.session_state[BUFFER_GENERATION_KEY]
    frames = app.session_state[BUFFER_KEY]
    assert frames[1]["반입일정"].dtype == "datetime64[us]"
    _preview(app, _tsv(frames[1][["설비명", "반입일정", "Qual일정"]]))
    app.button(key=IMPORT_APPLY_BUTTON_KEY).click()
    _ok(app.run())
    assert app.session_state[BUFFER_GENERATION_KEY] == generation

    text = _tsv(frames[2])
    _preview(app, text, target="비가동 일정")
    app.button(key=IMPORT_APPLY_BUTTON_KEY).click()
    _ok(app.run())
    assert app.session_state[BUFFER_GENERATION_KEY] == generation

    pinned = _scenario(repository, setup).latest_schedule_revision_id
    theirs = _session(repository, setup)
    repository.save_equipment(
        _request(theirs, setup, equipment=_set(theirs.equipment, "EQ-02", "X좌표", 70.0))
    )
    stale = _page(repository, setup, pinned)
    _preview(stale, text, target="비가동 일정")
    assert isinstance(stale.session_state[PREVIEW_KEY], ImportReview)
    assert not any("낡은 리비전에 넣지 않습니다" in line for line in _texts(stale, "error"))


def test_a_stale_session_import_is_refused_and_a_locked_layout_paste_too(
    tmp_path: Path, grid: Calls
) -> None:
    """남이 그 시나리오에 새 리비전을 저장한 낡은 가정 세션 — 팝업은 시나리오 칸을 바꾸는 붙여넣기를
    거절하고(`stale_paste_refusal`), 배치 편집이 잠긴 회차라 있던 호기 배치 칸을 바꾸는 붙여넣기도
    미리보기 전에 막는다(`layout_paste_refusal`). 공통 칸만 바꾸는 붙여넣기는 미리본다."""
    repository, setup = _two_scenarios(tmp_path)
    pinned = _scenario(repository, setup).latest_schedule_revision_id
    theirs = _session(repository, setup)
    repository.save_equipment(
        _request(theirs, setup, equipment=_set(theirs.equipment, "EQ-02", "X좌표", 70.0))
    )
    app = _page(repository, setup, pinned)
    _preview(app, "설비명\t시나리오 메모\nEQ-01\t낡은 쪽 메모")
    assert PREVIEW_KEY not in app.session_state
    assert any(
        "일정·시나리오 메모 칸이 바뀌는 호기 1대가 있어 낡은 리비전에 넣지 않습니다" in text
        for text in _texts(app, "error")
    )

    app.text_area(key=CLIPBOARD_KEY).set_value("설비명\tX좌표\nEQ-01\t55")
    app.button(key=PREVIEW_BUTTON_KEY).click()
    _ok(app.run())
    assert PREVIEW_KEY not in app.session_state
    assert any(
        "붙여넣기가 있던 호기 1대(EQ-01)의 배치 칸을 바꿉니다" in text
        for text in _texts(app, "error")
    )

    app.text_area(key=CLIPBOARD_KEY).set_value("설비명\t설비이력\nEQ-01\t붙여넣은 이력")
    app.button(key=PREVIEW_BUTTON_KEY).click()
    _ok(app.run())
    assert isinstance(app.session_state[PREVIEW_KEY], ImportReview)


def test_an_assumption_import_grouping_across_official_floors_is_refused_before_preview(
    tmp_path: Path, grid: Calls
) -> None:
    repository, setup = _grouped_fleet(tmp_path)
    app = _page(repository, setup)
    app.session_state[EQUIPMENT_DIALOG_KEY] = "import"
    _ok(app.run())
    app.checkbox(key=PASTE_LAYOUT_KEY).check()
    app.text_area(key=CLIPBOARD_KEY).set_value("설비명\tMain 설비\t층\nEQ-03\tMOD-1\t1F")
    app.button(key=PREVIEW_BUTTON_KEY).click()
    _ok(app.run())
    assert PREVIEW_KEY not in app.session_state
    assert any(GROUP_REFUSAL in text for text in _texts(app, "error"))


def test_the_preview_is_withdrawn_on_a_new_visit_and_when_the_dialog_closes(
    tmp_path: Path, grid: Calls
) -> None:
    """미리보기는 입력 칸보다 오래 사는 세션 칸이다 — 새 화면 방문(`page_visit`)·팝업 닫기
    (`_close_dialog` — Esc·바깥 누름의 on_dismiss)·다시 열기 때 거둔다. 닫힌 회차에 입력 칸이 버려져
    다시 열면 빈 입력에 옛 미리보기만 남았다(리뷰 rs-b1y)."""
    repository, _ = _two_scenarios(tmp_path)
    app = _page(repository, OPERATIONS)
    _preview(app, "설비명\t담당자\nEQ-02\t김담당")
    assert isinstance(app.session_state[PREVIEW_KEY], ImportReview)
    visit = app.session_state[PAGE_VISIT_KEY] if PAGE_VISIT_KEY in app.session_state else 0
    app.session_state[PAGE_VISIT_KEY] = visit + 1
    _ok(app.run())
    assert PREVIEW_KEY not in app.session_state

    _preview(app, "설비명\t담당자\nEQ-02\t김담당")
    assert isinstance(app.session_state[PREVIEW_KEY], ImportReview)
    closed = AppTest.from_function(_dismiss, default_timeout=30)
    closed.session_state[PREVIEW_KEY] = app.session_state[PREVIEW_KEY]
    closed.session_state[EQUIPMENT_DIALOG_KEY] = "import"
    _ok(closed.run())
    assert PREVIEW_KEY not in closed.session_state
    assert EQUIPMENT_DIALOG_KEY not in closed.session_state

    # 다시 여는 단추(표 불러오기 줄 `dialog` 트리거)도 남은 미리보기를 거둔다 — 다른 길로 닫혀
    # 미리보기가 남았어도(열림 칸만 지움) 빈 입력에 켜진 「편집본에 넣기」 가 서지 않는다.
    del app.session_state[EQUIPMENT_DIALOG_KEY]
    _ok(app.run())
    assert isinstance(app.session_state[PREVIEW_KEY], ImportReview)
    send(app, emg.LOADER_KEY, "dialog", {"name": "import"})
    assert app.session_state[EQUIPMENT_DIALOG_KEY] == "import"
    assert PREVIEW_KEY not in app.session_state
    assert app.button(key=IMPORT_APPLY_BUTTON_KEY).disabled


def _dismiss() -> None:
    """팝업 on_dismiss(Esc·바깥 누름) 한 번 — AppTest 는 팝업 닫기를 누를 수 없어 콜백을 부른다."""
    from capa_simulation.components.equipment_import_dialog import _close_dialog

    _close_dialog()


def test_the_import_dialog_csv_box_has_its_own_limit(tmp_path: Path, grid: Calls) -> None:
    """팝업의 CSV 칸도 서버 전체 상한이 아니라 칸 고유 상한(50MB)이다(옛 입력 탭 시험을
    팝업으로)."""
    repository, _ = _two_scenarios(tmp_path)
    app = _page(repository, OPERATIONS)
    app.session_state[EQUIPMENT_DIALOG_KEY] = "import"
    _ok(app.run())
    uploaders = app.get("file_uploader")
    assert [element.proto.label for element in uploaders] == ["또는 CSV 파일 업로드"]
    assert uploaders[0].proto.max_upload_size_mb == CSV_UPLOAD_LIMIT_MB == 50


# ------------------------------------------------------------------ 낡음·남의 저장·저장 콜백(11장)


def _path_of(app: AppTest, key: str) -> tuple[int, ...]:
    """그 key 위젯의 화면 자리(블록 차례 경로) — delta 자리가 회차마다 같은지 본다."""

    def walk(node: Any, path: tuple[int, ...]) -> tuple[int, ...] | None:
        if getattr(node, "key", None) == key:
            return path
        children = getattr(node, "children", None)
        if isinstance(children, dict):
            for index, child in sorted(children.items()):
                found = walk(child, (*path, index))
                if found is not None:
                    return found
        return None

    found = walk(app._tree, ())
    assert found is not None, key
    return found


def test_a_stale_warning_that_appears_keeps_the_tab_layout_in_place(
    tmp_path: Path, grid: Calls
) -> None:
    """남이 그 설비 시나리오에 새 리비전을 저장해 세션이 낡으면 맨 위 낡음 경고와 시나리오 칸 잠금이
    선다 — 경고는 늘 서 있는 알림 칸 안이라 오른쪽 칸·표 고르기 자리가 그 회차 전후로 같다(R21 —
    CCv2 마운트 앞 요소가 생기면 마운트가 다시 선다). 표 data 의 잠금 까닭에 낡음 글이 실린다."""
    repository, setup = _two_scenarios(tmp_path)
    pinned = _scenario(repository, setup).latest_schedule_revision_id
    app = _page(repository, setup, pinned)
    _load_all(app, grid)
    before = (_path_of(app, SIDE_KEY), _path_of(app, "equipment_master_table_v1"))
    assert "stale" not in last(grid, emg.GRID_KEY)["lockReasons"]
    theirs = _session(repository, setup)
    repository.save_equipment(
        _request(theirs, setup, equipment=_set(theirs.equipment, "EQ-02", "시나리오 메모", "남의"))
    )
    clear_equipment_repository()
    _ok(app.run())
    assert any("가 더 새롭습니다" in text for text in _texts(app, "warning"))
    assert (_path_of(app, SIDE_KEY), _path_of(app, "equipment_master_table_v1")) == before
    reasons = last(grid, emg.GRID_KEY)["lockReasons"]
    assert "가 더 새롭습니다" in reasons["stale"]


def test_an_outbox_from_before_another_users_save_is_dropped_and_told(
    tmp_path: Path, grid: Calls
) -> None:
    """남이 공통을 저장해 편집본을 다시 세우면 그 전 `base` 로 보낸 출납은 반영하지 않고 토스트로
    센다(개편 명세 4-10·6-4)."""
    repository, _ = _two_scenarios(tmp_path)
    app = _page(repository, OPERATIONS)
    _load_all(app, grid)
    old_base = last(grid, emg.GRID_KEY)["base"]
    theirs = _session(repository)
    repository.save_equipment(
        _request(theirs, equipment=_set(theirs.equipment, "EQ-02", "담당자", "남의 담당"))
    )
    clear_equipment_repository()
    _ok(app.run())
    assert last(grid, emg.GRID_KEY)["base"] != old_base
    outbox = {
        "mount": "m-old",
        "ops": [
            {"seq": 1, "at": 1, "base": old_base, "op": "cell", "id": "s:EQ-01", "col": "담당자"}
            | {"text": "옛 고침"}
        ],
    }
    send(app, emg.GRID_KEY, "outbox", outbox)
    assert _buffer_value(app, "EQ-01", "담당자") != "옛 고침"
    assert "반영하지 않았습니다" in last(grid, emg.GRID_KEY)["toast"]["text"]


@pytest.mark.parametrize("assumption", [False, True], ids=["official", "assumption"])
def test_a_unit_another_user_renames_stays_loaded_and_open_under_its_new_name(
    tmp_path: Path, grid: Calls, assumption: bool
) -> None:
    """남이 공통을 저장하며 저장본 호기 이름을 바꾸면(공식 세션에서 상세 설비명 고침 → 「리비전
    저장」) 이 세션의 불러온 목록·열어 둔 상세는 호기 키로 이어 새 이름 id 로 옮는다 — 행 id 가
    `s:` + 저장본 설비명이라 옮기지 않으면 살아 있는 호기가 목록에서 말없이 빠지고 상세가 빈 안내로
    돌아갔다(E2E eq-flows — 「불러온 호기 19대 / 전체 20대」). 가정 세션(「셋업 실무」)도 같다."""
    repository, setup = _two_scenarios(tmp_path)
    app = _page(repository, setup if assumption else OPERATIONS)
    _load_all(app, grid)
    assert [row["id"] for row in last(grid, emg.GRID_KEY)["rows"]] == ["s:EQ-01", "s:EQ-02"]
    send(app, emg.GRID_KEY, "open", {"view": last(grid, emg.GRID_KEY)["view"], "id": "s:EQ-02"})
    assert last(grid, emg.side_key("detail"))["unit"]["id"] == "s:EQ-02"
    theirs = _session(repository)
    repository.save_equipment(
        _request(
            theirs,
            equipment=_set(theirs.equipment, "EQ-02", "설비명", "EQ-02R"),
            renames={"EQ-02R": "EQ-02"},
        )
    )
    clear_equipment_repository()
    _ok(app.run())
    assert app.session_state[BUFFER_KEY][1]["설비명"].tolist() == ["EQ-01", "EQ-02R"]
    assert list(app.session_state[GRID_LOADED_KEY]) == ["s:EQ-01", "s:EQ-02R"]
    assert app.session_state[GRID_DETAIL_KEY] == "s:EQ-02R"
    table = last(grid, emg.GRID_KEY)
    assert [row["id"] for row in table["rows"]] == ["s:EQ-01", "s:EQ-02R"]
    assert table["open"] == "s:EQ-02R"
    assert last(grid, emg.side_key("detail"))["unit"]["id"] == "s:EQ-02R"
    # 남이 지운 호기는 지금처럼 거른다(지운 표시 줄은 이 세션이 지운 저장본 호기만).
    theirs = _session(repository)
    repository.save_equipment(
        _request(theirs, equipment=theirs.equipment[theirs.equipment["설비명"].ne("EQ-02R")])
    )
    clear_equipment_repository()
    _ok(app.run())
    assert [row["id"] for row in last(grid, emg.GRID_KEY)["rows"]] == ["s:EQ-01"]


def test_an_outbox_and_the_save_click_in_one_rerun_are_saved_together(
    tmp_path: Path, grid: Calls
) -> None:
    """칸에서 단추로 초점이 옮겨 가며 보낸 출납과 「리비전 저장」 누름이 한 회차에 오면 저장 콜백이
    출납을 먼저 반영하고 저장한다 — 잣대는 편집본 세대가 아니라 그린 회차 `base` 다(11장 검토)."""
    from types import SimpleNamespace

    repository, _ = _two_scenarios(tmp_path)
    app = _page(repository, OPERATIONS)
    _load_all(app, grid)
    app.session_state[SIDE_KEY] = SIDE_CHANGES
    _ok(app.run())
    base = last(grid, emg.GRID_KEY)["base"]
    app.session_state[emg.GRID_KEY] = SimpleNamespace(
        outbox={
            "mount": "m-same",
            "ops": [
                {
                    "seq": 1,
                    "at": 1,
                    "base": base,
                    "op": "cell",
                    "id": "s:EQ-01",
                    "col": "담당자",
                    "text": "같은 회차",
                }
            ],
        }
    )
    app.button(key=SAVE_BUTTON_KEY).click()
    _ok(app.run())
    assert len(repository.list_revisions()) == 2
    assert _session(repository).equipment.set_index("설비명").loc["EQ-01", "담당자"] == "같은 회차"


def _old_click(database: str) -> None:
    """한 회차: 편집본을 세우고 칸 하나를 고친 뒤, 그린 회차 `base` 가 지금과 다른 저장 누름(저장
    뒤의 옛 누름)을 부른다."""
    from datetime import date

    import streamlit as st

    from capa_simulation.components import equipment_master_tab as tab
    from capa_simulation.components.equipment_data_workspace import (
        BUFFER_KEY,
        buffer_base,
        ensure_equipment_drafts,
        replace_equipment_buffer,
    )
    from capa_simulation.equipment_scenario_activation import (
        resolve_equipment_session,
        space_edit_mode,
    )
    from capa_simulation.persistence.equipment_cache import get_equipment_repository
    from capa_simulation.services.equipment_grid import GridContext

    repository = get_equipment_repository(database)
    session = resolve_equipment_session(database)
    ensure_equipment_drafts(session.snapshot)
    frames = st.session_state[BUFFER_KEY]
    master = frames[1].copy()
    master.loc[master["설비명"].eq("EQ-01"), "담당자"] = "옛 누름"
    replace_equipment_buffer((frames[0], master, frames[2]))
    tab._save_revision(
        repository,
        basis=session.save_basis(),
        context=GridContext(base=buffer_base()),
        layout=space_edit_mode(session, stamped_role=None).layout,
        floor_canvases={},
        today=date(2026, 10, 25),
        drawn_base="그린 회차의 옛 base",
    )
    st.session_state["result_written"] = tab.SAVE_RESULT_KEY in st.session_state


def test_an_old_save_click_from_before_the_last_save_is_ignored(tmp_path: Path) -> None:
    """저장 뒤의 옛 누름(그린 회차 `base` 가 지금과 다름)은 쓰지도 알리지도 않는다(4-6 다)."""
    repository, _ = _two_scenarios(tmp_path)
    app = AppTest.from_function(
        _old_click, args=(str(repository.database_path),), default_timeout=60
    )
    _ok(app.run())
    assert app.session_state["result_written"] is False
    assert len(repository.list_revisions()) == 1


GOTO_KEY = "test_master_tab_goto"


def test_fix_in_the_downtime_table_filters_that_unit_and_opens_the_table(
    tmp_path: Path, grid: Calls
) -> None:
    """호기 상세 「비가동 일정 표에서 고치기」(`goto` → `_on_goto`) — 표 고르기를 「비가동 일정」
    으로, 그 표 설비명 거르기를 그 이름으로 세워 편집표에 그 호기 비가동만 선다(4-6 가). 진짜 콜백은
    회차 맨 앞에서 돈다 — 대역은 그리는 자리에서 돌아 위젯 뒤 대입이 되므로 페이지 앞에서 부른다."""
    repository, _ = _two_scenarios(tmp_path)
    head = f"""
import streamlit as st
from capa_simulation.components.equipment_master_tab import _on_goto
goto = st.session_state.pop({GOTO_KEY!r}, None)
if goto:
    _on_goto(*goto)
"""
    clear_equipment_repository()
    app = AppTest.from_string(
        head + _page_script(PAGE, repository.database_path), default_timeout=90
    )
    app.session_state[EQUIPMENT_TAB_KEY] = EQUIPMENT_MASTER_TAB
    _ok(app.run())
    assert app.session_state["equipment_master_table_v1"] == "설비 마스터"
    app.session_state[GOTO_KEY] = ("비가동 일정", "EQ-01")
    _ok(app.run())
    assert app.session_state["equipment_master_table_v1"] == "비가동 일정"
    assert app.session_state["equipment_downtime_view_filter_설비명"] == ["EQ-01"]
    assert app.multiselect(key="equipment_downtime_view_filter_설비명").value == ["EQ-01"]
    editors = [
        node
        for node in app._tree
        if "-equipment_downtime_editor_v3" in str(getattr(getattr(node, "proto", None), "id", ""))
    ]
    assert editors


def test_an_assumption_counts_schedule_alerts_by_the_official_schedule(
    tmp_path: Path, grid: Calls
) -> None:
    """가정 설비 시나리오의 「일정 확인 필요」 는 공식 일정 기준이다(4-1·4-10) — 그 시나리오 일정을
    모두 뒤로 미뤄도 공식 일정에서 미확인인 호기가 불러오기 줄 수에 든다."""
    repository, setup = _two_scenarios(tmp_path)
    _page(repository, OPERATIONS)
    official_alerts = list(last(grid, emg.LOADER_KEY)["alertIds"])
    assert official_alerts
    mine = _session(repository, setup)
    moved = mine.equipment.copy()
    for column in ("제진대일정", "물류일정", "반입일정", "Qual일정"):
        moved[column] = pd.to_datetime(moved[column]) + pd.DateOffset(years=5)
    repository.save_equipment(_request(mine, setup, equipment=moved))
    grid.clear()
    _page(repository, setup)
    assert list(last(grid, emg.LOADER_KEY)["alertIds"]) == official_alerts


def test_scenario_cells_edited_before_the_session_went_stale_block_the_save_with_a_way_out(
    tmp_path: Path, grid: Calls
) -> None:
    """가정 세션에서 시나리오 칸과 공통 칸을 고친 뒤 남이 그 시나리오에 저장해 낡은 세션이 됐다 —
    일정이 바뀐 저장은 저장소가 늘 거부하므로 「저장하기 전에 고칠 것」 에 그 칸 수와 되돌리는 길을
    싣고 저장을 막는다(예전에는 저장을 눌러야 「다른 사용자가 먼저 …」 로 공통 칸까지 거부되고 고칠
    것 표시가 없었다). 시나리오 칸을 되돌리면 공통 칸은 저장된다."""
    repository, setup = _two_scenarios(tmp_path)
    app = _page(repository, setup)
    _load_all(app, grid)
    send_ops(
        app,
        grid,
        {"op": "cell", "id": "s:EQ-01", "col": "시나리오 메모", "text": "낡기 전 메모"},
        {"op": "cell", "id": "s:EQ-01", "col": "설비이력", "text": "공통 이력"},
    )
    theirs = _session(repository, setup)
    repository.save_equipment(
        _request(theirs, setup, equipment=_set(theirs.equipment, "EQ-02", "X좌표", 70.0))
    )
    app.session_state[SIDE_KEY] = SIDE_CHANGES
    _ok(app.run())

    line = STALE_SCENARIO_EDITS.format(cells=1, units=1)
    changes = last(grid, emg.side_key("changes"))
    assert any(line in " ".join(map(str, item)) for item in changes["errors"])
    assert any("「저장 전 변경」 에서 되돌려야" in text for text in _texts(app, "warning"))
    before = len(repository.list_revisions())
    app.button(key=SAVE_BUTTON_KEY).click()
    _ok(app.run())
    assert len(repository.list_revisions()) == before
    assert any("고쳐야 저장됩니다" in text for text in _texts(app, "error"))

    send_ops(app, grid, {"op": "revert", "id": "s:EQ-01", "col": "시나리오 메모"})
    changes = last(grid, emg.side_key("changes"))
    assert not any(line in " ".join(map(str, item)) for item in changes["errors"])
    _save(app)
    assert len(repository.list_revisions()) == before + 1
    assert _buffer_value(app, "EQ-01", "설비이력") == "공통 이력"


def test_a_tilde_scenario_name_keeps_its_tildes_in_every_markdown_spot_of_the_tab(
    tmp_path: Path, grid: Calls
) -> None:
    """설비 시나리오 이름 「E2E~가정~A」 — 탭 맨 위 알약·낡은 세션 경고·비가동 「선택 행 삭제」
    풍선·저장 이력 머리가 물결표를 `\\~` 로 막아 취소선(「E2E<del>가정</del>A」)이 되지 않는다."""
    repository = _seeded(tmp_path)
    setup = _clone(repository, "E2E~가정~A").equipment_scenario_id
    pinned = _scenario(repository, setup).latest_schedule_revision_id
    theirs = _session(repository, setup)
    repository.save_equipment(
        _request(theirs, setup, equipment=_set(theirs.equipment, "EQ-02", "X좌표", 70.0))
    )
    app = _page(repository, setup, pinned)
    app.session_state[SIDE_KEY] = SIDE_HISTORY
    app.session_state[TABLE_KEY] = "비가동 일정"
    _ok(app.run())

    escaped = "E2E\\~가정\\~A"
    texts = [
        *_texts(app, "markdown"),
        *_texts(app, "caption"),
        *_texts(app, "warning"),
        *(str(button.help) for button in app.button if button.help),
    ]
    named = [text for text in texts if "가정" in text and "E2E" in text]
    assert named
    assert all(escaped in text for text in named), named
    assert any("가 더 새롭습니다" in text and escaped in text for text in _texts(app, "warning"))
    assert any("의 일정 리비전" in text and escaped in text for text in _texts(app, "caption"))
    assert any("설비 시나리오 ·" in text and escaped in text for text in _texts(app, "markdown")), (
        _texts(app, "markdown")
    )


@pytest.mark.parametrize(
    ("target", "text", "shown"),
    [
        (
            "비가동 일정",
            "설비명\t비가동유형\t시작일\t종료일\t상세사유\t비고\n없는~호기~X\t고장\t2026-11-01\t\t\t",
            "없는\\~호기\\~X",
        ),
        ("설비 마스터", "설비명\t담당자\nEQ-01\t김담당\nNEW~01~\t새 담당", "NEW\\~01\\~"),
    ],
)
def test_import_refusals_keep_the_tildes_of_a_pasted_name(
    tmp_path: Path, grid: Calls, target: str, text: str, shown: str
) -> None:
    """「엑셀·CSV로 한꺼번에」 거부 문구가 붙여넣은 설비명을 그대로 실어도 물결표가 취소선이 되지
    않는다(`markdown_safe_tildes`) — 「없는~호기~X」·「NEW~01~」 글자 그대로."""
    repository, setup = _two_scenarios(tmp_path)
    app = _page(repository, setup)
    _preview(app, text, target=target)

    errors = _texts(app, "error")
    assert any(shown in error for error in errors), errors


def test_the_save_hint_names_the_scenario_in_brackets_even_without_a_basis() -> None:
    """저장 안내 「시나리오 칸은 「…」 에 새 리비전으로」 — 이름은 막고, 출발점이 없어도 낫표는
    남는다."""
    assert save_target(EquipmentSaveBasis("s1", "셋업~가정~A")) == "「셋업\\~가정\\~A」"
    assert save_target(None) == "「이 설비 시나리오」"
