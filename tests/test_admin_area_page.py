# Purpose: Admin Area 페이지와 Proc Rename 탭의 렌더링·저장 흐름을 검증한다.

import json
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from alert_marks import (
    active_state,
    data_error_marks,
    flashed,
    infos,
    place_errors,
    states,
    successes,
)
from streamlit.testing.v1 import AppTest
from streamlit.testing.v1.element_tree import Dataframe, TextInput

import capa_simulation.components.write_guard as write_guard
from capa_simulation.components.literal_markdown import literal_markdown
from capa_simulation.components.process_rename_management import (
    BASE_VERSION_KEY,
    EDITOR_KEY,
    NOTE_KEY,
    PROCESS_RENAME_SAVED_MESSAGE,
    PROCESS_RENAME_UNCHANGED_MESSAGE,
)
from capa_simulation.components.table_toolbar import toolbar_room_css
from capa_simulation.persistence.cache import clear_global_process_rename_cache
from capa_simulation.persistence.repository import DuckDBScenarioRepository

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PAGE = PROJECT_ROOT / "app_pages/admin_area.py"


def _page_script(database_path: Path) -> str:
    return f"""
from pathlib import Path

import capa_simulation.settings as settings

settings.DUCKDB_PATH = Path({str(database_path)!r})

source = Path({str(PAGE)!r})
exec(
    compile(source.read_text(encoding="utf-8"), str(source), "exec"),
    {{"__name__": "__main__"}},
)
"""


def test_admin_area_renders_without_an_active_scenario(tmp_path: Path) -> None:
    """활성 시나리오도 저장된 표시명도 없는 상태가 정상이다. 화면이 멈추면 안 된다."""
    app = AppTest.from_string(_page_script(tmp_path / "scenario.duckdb")).run(timeout=120)

    assert not list(app.exception), [element.message for element in app.exception]
    assert [heading.value for heading in app.title] == ["Admin Area"]
    # 운영 관리 기능은 이미 쓰는 화면이라 `(구현중)` 배지를 달지 않는다.
    assert not any("구현중" in markdown.value for markdown in app.markdown)
    # 탭 이름 밑에 같은 글의 제목을 다시 그리지 않는다(설계 규칙 UI-TXT-07).
    assert not [subheader.value for subheader in app.subheader]
    # 표시순서 관리가 시나리오 관리 페이지에서 여기로 옮겨 왔고, 원천 품질과 HOME 에서 걷은 계산
    # 알림을 모은 「알림 모음」 이 뒤에 붙어 네 탭이다.
    assert [tab.label for tab in app.main.tabs] == [
        ":material/label: Proc Rename",
        ":material/sort: 표시순서 관리",
        ":material/fact_check: 원천 품질",
        ":material/notifications: 알림 모음",
    ]
    # 원천 품질 탭은 닫혀 있으면 그리지 않는다(위젯이 없는 읽기 전용 탭).
    assert not any("활성 시나리오가 없습니다" in info.value for info in infos(app))
    # 내려받기는 표시명 양식과 표시순서 양식 둘이다.
    assert len(app.get("download_button")) == 2
    assert len(app.get("file_uploader")) == 0
    # 붙여넣기는 작업 줄의 팝업이다 — 닫혀 있는 동안 본문을 차지하지 않는다.
    assert not any(area.label == "공정 표시명 표 붙여넣기" for area in app.text_area)
    assert app.button(key="admin_area_process_rename_open_paste")
    assert any("공용 버전 없음" in caption.value for caption in app.caption)
    # C-DEP CD 컨테이너가 남기는 시작 점검 결과가 없으면(개발·사내 PC) 그 펼침도 없다.
    assert not _start_check_expanders(app)
    # 앱 정보는 이 화면이 아니라 모든 화면 사이드바 맨 아래 카드다(2026-10-07 사용자 결정). 카드는
    # `app.py` 가 그리므로 이 화면만 돌린 여기에는 그 글이 한 줄도 없다.
    from capa_simulation.settings import APP_CONTACT_EMAIL, APP_VERSION

    assert not any(
        APP_CONTACT_EMAIL in caption.value or APP_VERSION in caption.value
        for caption in app.caption
    )

    # 활성 시나리오가 없으면 원천 품질 탭은 열어도 안내만 남긴다 — 화면을 멈추지 않는다.
    app.session_state["admin_area_active_tab"] = ":material/fact_check: 원천 품질"
    app.run(timeout=120)
    assert not list(app.exception), [element.message for element in app.exception]
    # 빈 결과는 평문 한 줄이다(설계 규칙 UI-TXT-04 — 상자 · 하는 법 꼬리 없음).
    assert "활성 시나리오가 없습니다." in [caption.value for caption in app.caption]
    assert not any("활성 시나리오가 없습니다" in info.value for info in infos(app))


def _source_quality_script(database_path: Path) -> str:
    """Admin Area 를 활성 시나리오가 있는 채로 그리되, 원천 읽기를 세는 가짜로 바꿔 둔 스크립트.

    원천 읽기 두 함수는 캐시가 없어 부를 때마다 DB 를 연다. 부른 횟수를 세션 칸에 적고, 끝나면
    클래스를 되돌린다 — AppTest 는 같은 프로세스에서 돌아 그대로 두면 다른 테스트에 샌다.
    """
    return f"""
from pathlib import Path

import pandas as pd
import streamlit as st

import capa_simulation.settings as settings
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.scenario_activation import ACTIVE_PERSISTED_SCENARIO_ID_KEY

settings.DUCKDB_PATH = Path({str(database_path)!r})
st.session_state[ACTIVE_PERSISTED_SCENARIO_ID_KEY] = "scenario-under-test"
st.session_state.setdefault("source_quality_reads", 0)


def load_source_profile(self, scenario_id):
    st.session_state["source_quality_reads"] += 1
    return pd.DataFrame(
        {{
            "column_name": ["컬럼A", "컬럼B"],
            "source_dtype": ["VARCHAR", "DOUBLE"],
            "null_count": [0, 10],
            "unique_count": [3, 0],
        }}
    )


def load_source_row_count(self, scenario_id):
    st.session_state["source_quality_reads"] += 1
    return 10


original = (
    DuckDBScenarioRepository.load_source_profile,
    DuckDBScenarioRepository.load_source_row_count,
)
DuckDBScenarioRepository.load_source_profile = load_source_profile
DuckDBScenarioRepository.load_source_row_count = load_source_row_count
try:
    source = Path({str(PAGE)!r})
    exec(
        compile(source.read_text(encoding="utf-8"), str(source), "exec"),
        {{"__name__": "__main__"}},
    )
finally:
    (
        DuckDBScenarioRepository.load_source_profile,
        DuckDBScenarioRepository.load_source_row_count,
    ) = original
"""


def _source_quality_tables(app: AppTest) -> list[object]:
    return [frame for frame in app.dataframe if "결측률" in getattr(frame.value, "columns", [])]


def test_closed_source_quality_tab_reads_nothing_and_opens_with_its_table(
    tmp_path: Path,
) -> None:
    """닫힌 원천 품질 탭은 원천을 읽지 않는다. 이 탭이 Admin 회차의 유일한 DB 읽기라, 읽으면 닫힌
    탭이 회차마다 DuckDB 인스턴스를 열고 닫는다. 탭을 열면 그 회차에 읽고 표를 그리며, 다시
    닫으면 읽지 않는다."""
    app = AppTest.from_string(_source_quality_script(tmp_path / "scenario.duckdb"))
    app.run(timeout=120)
    assert not list(app.exception), [element.message for element in app.exception]
    app.run(timeout=60)
    assert app.session_state["source_quality_reads"] == 0
    assert not _source_quality_tables(app)

    app.session_state["admin_area_active_tab"] = ":material/fact_check: 원천 품질"
    app.run(timeout=60)
    assert not list(app.exception), [element.message for element in app.exception]
    assert app.session_state["source_quality_reads"] == 2
    assert len(_source_quality_tables(app)) == 1
    assert any("2개 컬럼 중 1개" in caption.value for caption in app.caption)

    app.session_state["admin_area_active_tab"] = ":material/label: Proc Rename"
    app.run(timeout=60)
    assert app.session_state["source_quality_reads"] == 2
    assert not _source_quality_tables(app)


def _rename_component_script(database_path: Path) -> str:
    """Proc Rename 탭 한 장만 그리고, 저장 결과를 다시 읽어 마지막 줄에 적는 스크립트.

    저장 성공은 `st.rerun()` 으로 끝나 화면의 success 가 남지 않는다. 저장 경로를 실제로
    탔는지는 다시 읽은 공용 버전과 규칙 내용으로 확인한다.
    """
    return """
from pathlib import Path

import streamlit as st

from capa_simulation.components.process_rename_management import (
    render_process_rename_management,
)
from capa_simulation.persistence.cache import load_global_process_rename
from capa_simulation.persistence.repository import DuckDBScenarioRepository

database_path = Path(r"__DATABASE__")
repository = DuckDBScenarioRepository(database_path)
repository.initialize()
render_process_rename_management(repository, ["SAW", "MOLD"])
profile = load_global_process_rename(str(database_path))
st.text(
    "v%d|%s"
    % (
        profile.version,
        ";".join(
            "%s>%s" % (source, target)
            for source, target in zip(profile.rules["공정"], profile.rules["표시명"])
        ),
    )
)
""".replace("__DATABASE__", str(database_path))


def _submit_clipboard(app: AppTest, pasted: str) -> AppTest:
    """작업 줄의 「Excel 붙여넣기」 팝업을 열고, 붙여넣고, 전체 교체를 확인해 적용한다."""
    app.button(key="admin_area_process_rename_open_paste").click().run(timeout=60)
    app.text_area("admin_area_process_rename_clipboard").set_value(pasted)
    app.checkbox("admin_area_process_rename_clipboard_confirm").check()
    next(button for button in app.button if button.label == "붙여넣기 표시명 적용").click()
    return app.run(timeout=60)


def test_proc_rename_tab_saves_and_reloads_the_shared_profile(tmp_path: Path) -> None:
    """붙여넣기 → 전체교체 확인 → submit 이 실제로 공용 프로필을 올린다."""
    app = AppTest.from_string(_rename_component_script(tmp_path / "rename-roundtrip.duckdb")).run(
        timeout=60
    )

    assert not list(app.exception), [element.message for element in app.exception]
    assert app.text[-1].value == "v0|"

    app = _submit_clipboard(app, "공정\t표시명\nSAW\t절단\nMOLD\t성형")

    assert not list(app.exception), [element.message for element in app.exception]
    assert not list(app.error)
    assert app.text[-1].value == "v1|SAW>절단;MOLD>성형"
    assert any("공용 버전 v1" in caption.value for caption in app.caption)


def test_proc_rename_tab_reports_a_duplicated_display_name_as_an_error(
    tmp_path: Path,
) -> None:
    """표시명 중복은 1:1 위반이다. 저장하지 않고 화면 오류로 알린다."""
    app = AppTest.from_string(_rename_component_script(tmp_path / "rename-duplicate.duckdb")).run(
        timeout=60
    )

    app = _submit_clipboard(app, "공정\t표시명\nSAW\t같은이름\nMOLD\t같은이름")

    assert not list(app.exception), [element.message for element in app.exception]
    assert any("중복" in error.value for error in flashed(app, "error"))
    assert not place_errors(app)
    assert app.text[-1].value == "v0|"


def test_a_duplicated_display_name_with_markdown_marks_is_shown_literally(
    tmp_path: Path,
) -> None:
    """1:1 위반 오류는 겹친 이름을 글자 그대로 싣는다 — 예외 글 그대로면 물결표만 막혀
    「~x~ *y*」 의 별표가 기울임이 되었다(2026-10-26 E2E)."""
    app = AppTest.from_string(_rename_component_script(tmp_path / "rename-marks.duckdb")).run(
        timeout=60
    )

    app = _submit_clipboard(app, "공정\t표시명\nAAA\t~x~ *y*\nBBB\t~x~ *y*")

    assert not list(app.exception), [element.message for element in app.exception]
    errors = [str(error.value) for error in flashed(app, "error")]
    assert errors == [
        f"표시명이 중복되었습니다: {literal_markdown('~x~ *y*')}. "
        "원본 공정과 표시명은 항상 1:1이어야 합니다."
    ], errors
    assert app.text[-1].value == "v0|"


def test_proc_rename_notices_list_the_names_literally(tmp_path: Path) -> None:
    """「보유하지 않은 공정」 안내와 「원본명과 같은 표시명」 경고가 늘어놓는 이름은 사람 글이라
    막아 적는다 — 「ZZ~9~9 *q*」 가 「ZZ<del>9</del>9 <em>q</em>」 로 그려졌다(2026-10-26 E2E)."""
    database_path = tmp_path / "rename-notice-marks.duckdb"
    unowned = "ZZ~9~9 *q*"
    owned = "MO~L*D*"
    script = f'''
from pathlib import Path

import pandas as pd

from capa_simulation.components.process_rename_management import (
    render_process_rename_management,
)
from capa_simulation.persistence.repository import DuckDBScenarioRepository

repository = DuckDBScenarioRepository(Path(r"{database_path}"))
repository.initialize()
repository.replace_global_process_rename(
    pd.DataFrame([({unowned!r}, "ZQ"), ("SAW", {owned!r})], columns=["공정", "표시명"]),
    source="테스트",
)
render_process_rename_management(repository, ["SAW", {owned!r}])
'''

    app = AppTest.from_string(script).run(timeout=60)

    assert not list(app.exception), [element.message for element in app.exception]
    # 「보유 공정 밖 표시명」 은 표 머리 표지이고 이름은 그 풍선에 싣는다(설계 규칙 UI-TXT-04).
    [marker] = [item for item in app.caption if "보유 공정 밖 표시명" in item.value]
    assert literal_markdown(unowned) in marker.proto.help, marker.proto.help
    assert unowned not in marker.proto.help, marker.proto.help
    # 「원본명과 같은 표시명」 은 상태 알림(`AD-06`)이다 — 알림창 · 패널은 평문(`textContent`)이라
    # 이름을 글자 그대로 싣고, 자리에는 경고 상자를 그리지 않는다(2026-11-03 D2).
    assert not list(app.warning)
    collision = active_state(app, "AD-06")
    assert collision is not None and owned in collision["full"], states(app, "AD-06")
    clear_global_process_rename_cache()


def test_display_name_equal_to_another_owned_process_warns_but_still_saves(
    tmp_path: Path,
) -> None:
    """매핑 밖 공정의 원본명과 겹치는 표시명은 오류가 아니라 경고다.

    보유 공정 목록은 시나리오마다 달라 저장을 막으면 안 된다. 값은 원본이라 조인도
    그대로지만 화면에는 두 공정이 같은 이름으로 나오므로 건수를 알린다.
    """
    app = AppTest.from_string(_rename_component_script(tmp_path / "rename-collision.duckdb")).run(
        timeout=60
    )

    app = _submit_clipboard(app, "공정\t표시명\nSAW\tMOLD")

    assert not list(app.error)
    assert app.text[-1].value == "v1|SAW>MOLD"
    # 경고 상자가 아니라 상태 알림(`AD-06` — 알림창 · Alarm, 2026-11-03 D2)이다.
    assert not list(app.warning)
    note = active_state(app, "AD-06")
    assert note is not None and "보유 공정의 원본명과 같은 표시명 1건" in note["short"], note
    collision = note["full"]
    # 선택 상자·표에서 어떻게 보이는지와 검사 범위(설비 마스터는 보지 않는다)를 사실대로 적는다.
    assert "「표시명 (원본)」" in collision and "표·그림·버튼에서는 같은 글자" in collision
    # 모든 화면의 공정 상자가 글자를 가른다 — 「다른 공정이 잡힐 수 있다」 는 이제 사실이 아니다.
    assert "다른 공정이 잡힐" not in collision
    assert "설비 마스터에만 있는 공정은 여기서 검사하지 않습니다" in collision


def test_direct_edit_save_refuses_to_overwrite_a_newer_shared_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A 가 직접 편집 표를 연 뒤 B 가 표시명을 저장했다. A 의 저장은 막히고 B 의 저장본이 남는다
    (판정 기준과 같은 버전 대조). 그 회차가 그린 최신 저장본에서 고쳐 다시 누르면 저장된다 — 고치지
    않고 누르면 대조는 지나지만 바뀐 것이 없어 새 버전을 만들지 않는다(2026-11-01 개선 I5)."""
    database_path = tmp_path / "rename-conflict.duckdb"
    repository = DuckDBScenarioRepository(database_path)
    repository.initialize()
    repository.replace_global_process_rename(
        pd.DataFrame([("SAW", "절단")], columns=["공정", "표시명"]), source="A 가 본 것"
    )
    clear_global_process_rename_cache()
    app = AppTest.from_string(_rename_component_script(database_path)).run(timeout=60)
    assert app.text[-1].value == "v1|SAW>절단"

    repository.replace_global_process_rename(
        pd.DataFrame([("SAW", "절단"), ("MOLD", "성형")], columns=["공정", "표시명"]),
        source="B 의 저장",
    )
    clear_global_process_rename_cache()
    next(button for button in app.button if button.label == "공용 공정 표시명 저장").click()
    app.run(timeout=60)

    assert not list(app.exception), [element.message for element in app.exception]
    errors = [str(error.value) for error in app.error]
    assert any("다른 사용자가 먼저" in text for text in errors), errors
    # 거부는 저장 단추가 든 폼 바로 위 칸에 선다 — 표 밑이면 단추에서 표 높이만큼 떨어진다(설계 규칙
    # UI-LAY-03, 표시순서 관리와 같은 꼴).
    kinds = _kinds_in_order(app.main)
    assert kinds.index("error") < kinds.index("form"), kinds
    assert app.text[-1].value == "v2|SAW>절단;MOLD>성형"

    # 새 화면을 보고 다시 누른 저장이다 — 거부 직후 둘째 누름의 창(`TRAILING_PRESS_SECONDS`)이
    # 지났다. AppTest 의 회차 사이는 그 창보다 짧아 창은 시험이 정한다.
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 0.0)
    next(button for button in app.button if button.label == "공용 공정 표시명 저장").click()
    app.run(timeout=60)
    assert not list(app.error), [str(error.value) for error in app.error]
    assert [str(item.value) for item in infos(app)] == [PROCESS_RENAME_UNCHANGED_MESSAGE]
    assert app.text[-1].value == "v2|SAW>절단;MOLD>성형"

    _edit_display_name(app, 1, "몰드")
    next(button for button in app.button if button.label == "공용 공정 표시명 저장").click()
    app.run(timeout=60)
    assert not list(app.error), [str(error.value) for error in app.error]
    assert app.text[-1].value == "v3|SAW>절단;MOLD>몰드"
    clear_global_process_rename_cache()


def _kinds_in_order(node: Any) -> list[str]:
    """요소 나무를 문서 차례로 훑은 요소 종류(칸 · 폼 같은 묶음도 그 자리에 든다)."""
    kinds: list[str] = []
    children = getattr(node, "children", {})
    for index in sorted(children):
        child = children[index]
        kinds.append(str(getattr(child, "type", "")))
        kinds.extend(_kinds_in_order(child))
    return kinds


def _edit_display_name(app: AppTest, row: int, name: str) -> None:
    """직접 편집 표 `row` 행의 표시명을 고친 것처럼 편집표 칸을 채운다(다음 회차가 그 편집을
    보낸다)."""
    app.session_state[EDITOR_KEY] = {
        "edited_rows": {row: {"표시명": name}},
        "added_rows": [],
        "deleted_rows": [],
    }


def _rename_memo(app: AppTest) -> TextInput:
    """직접 편집 변경 메모 칸 — 저장에 성공해도 key 가 그대로다."""
    return app.text_input(key=NOTE_KEY)


def _press_rename_save(app: AppTest) -> AppTest:
    next(button for button in app.button if button.label == "공용 공정 표시명 저장").click()
    app.run(timeout=60)
    assert not list(app.exception), [element.message for element in app.exception]
    return app


def test_a_direct_edit_save_without_changes_makes_no_new_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """바꾼 것 없는 「공용 공정 표시명 저장」 은 새 버전을 만들지 않고 「바뀐 것이 없습니다」 를
    알린다(2026-11-01 개선 I5 — E2E #41: v4→v5 로 올라가며 「저장했습니다」 를 띄웠다). 변경 메모만
    적은 저장도 같다. 고친 칸이 있으면 평소대로 저장한다."""
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 0.0)
    database_path = tmp_path / "rename-unchanged.duckdb"
    repository = DuckDBScenarioRepository(database_path)
    repository.initialize()
    repository.replace_global_process_rename(
        pd.DataFrame([("SAW", "절단")], columns=["공정", "표시명"]), source="처음 저장"
    )
    clear_global_process_rename_cache()
    app = AppTest.from_string(_rename_component_script(database_path)).run(timeout=60)
    assert app.text[-1].value == "v1|SAW>절단"

    kinds_before = _kinds_in_order(app.main)
    app = _press_rename_save(app)
    assert [str(item.value) for item in infos(app)] == [PROCESS_RENAME_UNCHANGED_MESSAGE]
    assert not successes(app) and not place_errors(app)
    assert app.text[-1].value == "v1|SAW>절단"
    # 글은 폼 안 저장 줄 바로 아래 칸이다 — 칸이 늘 서 있어 그 밖의 요소 차례는 그대로다(g8-16).
    kinds = _kinds_in_order(app.main)
    assert kinds.index("form") < kinds.index("text_input") < kinds.index("info")
    assert kinds.index("info") < len(kinds) - kinds[::-1].index("dataframe") - 1
    assert [kind for kind in kinds if kind != "info"] == kinds_before

    app.text_input(key=NOTE_KEY).set_value("메모만 적음")
    app = _press_rename_save(app)
    assert [str(item.value) for item in infos(app)] == [PROCESS_RENAME_UNCHANGED_MESSAGE]
    assert _rename_memo(app).value == "메모만 적음"
    profile = repository.load_global_process_rename()
    assert (profile.version, profile.source) == (1, "처음 저장")

    _edit_display_name(app, 0, "자르기")
    app = _press_rename_save(app)
    assert not infos(app) and not place_errors(app)
    assert [str(item.value) for item in successes(app)] == [PROCESS_RENAME_SAVED_MESSAGE]
    assert app.text[-1].value == "v2|SAW>자르기"
    clear_global_process_rename_cache()


def test_a_saved_direct_edit_note_is_not_carried_into_the_next_save(tmp_path: Path) -> None:
    """저장에 성공하면 변경 메모 칸이 빈다 — 다시 적지 않은 메모가 값만 고친 다음 저장의 기록에
    실렸다(2026-11-08 점검 u3-m2)."""
    database_path = tmp_path / "rename-note.duckdb"
    repository = DuckDBScenarioRepository(database_path)
    repository.initialize()
    repository.replace_global_process_rename(
        pd.DataFrame([("SAW", "절단")], columns=["공정", "표시명"]), source="처음 저장"
    )
    clear_global_process_rename_cache()
    app = AppTest.from_string(_rename_component_script(database_path)).run(timeout=60)

    _edit_display_name(app, 0, "자르기")
    _rename_memo(app).set_value("첫 메모")
    app = _press_rename_save(app)
    assert _rename_memo(app).value == ""
    profile = repository.load_global_process_rename()
    assert (profile.version, profile.source) == (2, "첫 메모")

    _edit_display_name(app, 0, "절삭")
    app = _press_rename_save(app)
    assert _rename_memo(app).value == ""
    profile = repository.load_global_process_rename()
    assert (profile.version, profile.source) == (3, "웹 직접 편집")
    clear_global_process_rename_cache()


def test_a_refused_direct_edit_save_keeps_the_typed_note(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """거절된 저장(1:1 위반 · 남의 저장)은 적은 메모를 지우지 않는다."""
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 0.0)
    database_path = tmp_path / "rename-note-refused.duckdb"
    repository = DuckDBScenarioRepository(database_path)
    repository.initialize()
    repository.replace_global_process_rename(
        pd.DataFrame([("SAW", "절단"), ("MOLD", "성형")], columns=["공정", "표시명"]),
        source="처음 저장",
    )
    clear_global_process_rename_cache()
    app = AppTest.from_string(_rename_component_script(database_path)).run(timeout=60)

    _edit_display_name(app, 1, "절단")
    _rename_memo(app).set_value("거절될 메모")
    app = _press_rename_save(app)
    assert list(app.error), "1:1 위반은 저장하지 않고 알린다"
    assert _rename_memo(app).value == "거절될 메모"

    repository.replace_global_process_rename(
        pd.DataFrame([("SAW", "절단")], columns=["공정", "표시명"]), source="B 의 저장"
    )
    clear_global_process_rename_cache()
    _edit_display_name(app, 0, "자르기")
    app = _press_rename_save(app)
    assert any("다른 사용자가 먼저" in str(error.value) for error in app.error)
    assert _rename_memo(app).value == "거절될 메모"
    clear_global_process_rename_cache()


def test_a_double_press_that_cut_the_first_run_still_empties_the_direct_edit_note(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """둘째 누름이 첫 저장의 뒷정리를 끊으면 칸을 비울 표지가 없다 — 제 저장임을 알아본 둘째 회차가
    칸을 비운다. AppTest 는 두 요청을 겹칠 수 없어 누른 화면의 위젯 값과 끊긴 회차가 남긴 본
    version 을 되살려 한 번 더 보낸다."""
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 0.0)
    database_path = tmp_path / "rename-note-double.duckdb"
    repository = DuckDBScenarioRepository(database_path)
    repository.initialize()
    repository.replace_global_process_rename(
        pd.DataFrame([("SAW", "절단")], columns=["공정", "표시명"]), source="처음 저장"
    )
    clear_global_process_rename_cache()
    app = AppTest.from_string(_rename_component_script(database_path)).run(timeout=60)
    _edit_display_name(app, 0, "자르기")
    _rename_memo(app).set_value("첫 메모")
    next(button for button in app.button if button.label == "공용 공정 표시명 저장").click()
    pressed = app._tree.get_widget_states()
    app.run(timeout=60)
    assert repository.load_global_process_rename().version == 2

    app.session_state[BASE_VERSION_KEY] = 1
    app._run(widget_state=pressed)

    assert not list(app.exception), [element.message for element in app.exception]
    assert [str(item.value) for item in successes(app)] == [PROCESS_RENAME_SAVED_MESSAGE]
    assert _rename_memo(app).value == ""
    profile = repository.load_global_process_rename()
    assert (profile.version, profile.source) == (2, "첫 메모")
    clear_global_process_rename_cache()


def test_a_second_press_of_the_direct_edit_save_keeps_the_note_it_did_not_save(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """앞 회차가 끝나기 전에 온 다른 메모의 둘째 누름은 제 저장으로 판정되어 쓰이지 않는다 — 그
    메모는 칸에 남긴다(판정 기준과 같은 꼴)."""
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 0.0)
    database_path = tmp_path / "rename-note-second.duckdb"
    repository = DuckDBScenarioRepository(database_path)
    repository.initialize()
    repository.replace_global_process_rename(
        pd.DataFrame([("SAW", "절단")], columns=["공정", "표시명"]), source="처음 저장"
    )
    clear_global_process_rename_cache()
    app = AppTest.from_string(_rename_component_script(database_path)).run(timeout=60)
    _edit_display_name(app, 0, "자르기")
    _rename_memo(app).set_value("첫 메모")
    app = _press_rename_save(app)
    assert _rename_memo(app).value == ""

    app.session_state[BASE_VERSION_KEY] = 1
    _edit_display_name(app, 0, "절삭")
    _rename_memo(app).set_value("둘째 메모")
    app = _press_rename_save(app)

    assert [str(item.value) for item in successes(app)] == [PROCESS_RENAME_SAVED_MESSAGE]
    assert _rename_memo(app).value == "둘째 메모"
    profile = repository.load_global_process_rename()
    assert (profile.version, profile.source) == (2, "첫 메모")
    clear_global_process_rename_cache()


def test_a_slow_second_press_of_the_direct_edit_save_repeats_the_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """느린 두 번 누름(둘째 누름이 첫 저장 뒤 새로 그린 표에 닿는다 — 같은 표라 바뀐 것이 없다)은
    「바뀐 것이 없습니다」 로 방금 성공을 덮지 않는다(write_guard.held_notice 창 안)."""
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 3600.0)
    database_path = tmp_path / "rename-slow-double.duckdb"
    repository = DuckDBScenarioRepository(database_path)
    repository.initialize()
    repository.replace_global_process_rename(
        pd.DataFrame([("SAW", "절단")], columns=["공정", "표시명"]), source="처음 저장"
    )
    clear_global_process_rename_cache()
    app = AppTest.from_string(_rename_component_script(database_path)).run(timeout=60)
    _edit_display_name(app, 0, "자르기")
    app = _press_rename_save(app)
    assert app.text[-1].value == "v2|SAW>자르기"

    app = _press_rename_save(app)

    assert not infos(app) and not place_errors(app), [str(item.value) for item in infos(app)]
    assert [str(item.value) for item in successes(app)] == [PROCESS_RENAME_SAVED_MESSAGE]
    assert app.text[-1].value == "v2|SAW>자르기"
    clear_global_process_rename_cache()


def test_a_double_press_after_a_newer_shared_profile_keeps_the_refusal(tmp_path: Path) -> None:
    """B 가 먼저 저장한 뒤 A 가 옛 화면에서 「공용 공정 표시명 저장」을 빠르게 두 번 누른다
    (2026-10-26 E2E). 첫 누름은 거부되고 그 회차가 출발점을 지운다. 둘째 누름은 옛 화면의 표를
    든 채 최신 version 으로 대조를 지나 저장했고, 거부 알림 대신 성공만 남았다. 거부 직후의 둘째
    누름은 저장하지 않고 그 거부를 다시 알린다. AppTest 는 두 요청을 겹칠 수 없어 누른 화면의 위젯
    값을 한 번 더 보낸다.
    """
    database_path = tmp_path / "rename-conflict-double.duckdb"
    repository = DuckDBScenarioRepository(database_path)
    repository.initialize()
    repository.replace_global_process_rename(
        pd.DataFrame([("SAW", "절단")], columns=["공정", "표시명"]), source="A 가 본 것"
    )
    clear_global_process_rename_cache()
    app = AppTest.from_string(_rename_component_script(database_path)).run(timeout=60)
    assert app.text[-1].value == "v1|SAW>절단"
    repository.replace_global_process_rename(
        pd.DataFrame([("SAW", "절단"), ("MOLD", "성형")], columns=["공정", "표시명"]),
        source="B 의 저장",
    )
    clear_global_process_rename_cache()
    next(button for button in app.button if button.label == "공용 공정 표시명 저장").click()
    pressed = app._tree.get_widget_states()
    app.run(timeout=60)
    assert any("다른 사용자가 먼저" in str(error.value) for error in app.error)

    app._run(widget_state=pressed)

    assert not list(app.exception), [element.message for element in app.exception]
    errors = [str(error.value) for error in app.error]
    assert len(errors) == 1 and "다른 사용자가 먼저" in errors[0], errors
    assert not successes(app)
    assert app.text[-1].value == "v2|SAW>절단;MOLD>성형"
    assert repository.load_global_process_rename().source == "B 의 저장"
    clear_global_process_rename_cache()


def test_a_single_press_after_a_held_double_press_saves_the_process_rename(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """남의 저장 뒤 옛 화면 두 번 누름이 둘 다 거부된 다음, 최신 화면을 보고 한 번 누른 저장은
    저장된다(2026-10-27 E2E — 판정 기준·확보율 보정과 같은 꼴). 둘째 누름이 거부 뒤 회차(제출
    아님 — 본 version 을 적는 자리)를 끊고 거부 표지에 걸려 끝나면, 그 회차가 그린 최신 version 을
    본 값으로 적어야 한다 — 적지 않으면 캡션은 「공용 버전 v2」 인데 창 뒤의 한 번 누름이 「편집
    시작 v1 · 지금 v2」 로 또 거부됐다. 끊긴 회차는 본 version 을 옛 값으로 되살려 흉내 낸다."""
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 3600.0)
    database_path = tmp_path / "rename-conflict-held.duckdb"
    repository = DuckDBScenarioRepository(database_path)
    repository.initialize()
    repository.replace_global_process_rename(
        pd.DataFrame([("SAW", "절단")], columns=["공정", "표시명"]), source="A 가 본 것"
    )
    clear_global_process_rename_cache()
    app = AppTest.from_string(_rename_component_script(database_path)).run(timeout=60)
    repository.replace_global_process_rename(
        pd.DataFrame([("SAW", "절단"), ("MOLD", "성형")], columns=["공정", "표시명"]),
        source="B 의 저장",
    )
    clear_global_process_rename_cache()
    next(button for button in app.button if button.label == "공용 공정 표시명 저장").click()
    pressed = app._tree.get_widget_states()
    app.run(timeout=60)
    assert any("다른 사용자가 먼저" in str(error.value) for error in app.error)

    app.session_state["admin_area_process_rename_base_version"] = 1
    app._run(widget_state=pressed)
    assert any("다른 사용자가 먼저" in str(error.value) for error in app.error)
    assert repository.load_global_process_rename().version == 2

    # 거부 표지의 창이 지났다 — 최신 화면을 보고 고쳐 다시 누른 저장이다(고치지 않으면 바뀐 것이
    # 없어 쓰지 않는다 — 개선 I5).
    monkeypatch.setattr(write_guard, "TRAILING_PRESS_SECONDS", 0.0)
    _edit_display_name(app, 1, "몰드")
    next(button for button in app.button if button.label == "공용 공정 표시명 저장").click()
    app.run(timeout=60)

    assert not list(app.exception), [element.message for element in app.exception]
    assert not list(app.error), [str(error.value) for error in app.error]
    assert app.text[-1].value == "v3|SAW>절단;MOLD>몰드"
    clear_global_process_rename_cache()


def test_a_double_press_of_the_direct_edit_save_reports_no_conflict(tmp_path: Path) -> None:
    """「공용 공정 표시명 저장」 빠른 두 번 누름 — 둘째 누름이 첫 저장 전의 편집 시작 version 을
    들고 와도 방금 한 제 저장을 「다른 사용자가 먼저 저장」이라 알리지 않는다(2026-10-26 E2E)."""
    database_path = tmp_path / "rename-double.duckdb"
    clear_global_process_rename_cache()
    app = AppTest.from_string(_rename_component_script(database_path)).run(timeout=60)
    assert app.text[-1].value == "v0|"
    next(button for button in app.button if button.label == "공용 공정 표시명 저장").click()
    pressed = app._tree.get_widget_states()
    app.run(timeout=60)
    assert app.text[-1].value == "v1|"

    app.session_state["admin_area_process_rename_base_version"] = 0
    app._run(widget_state=pressed)

    assert not list(app.exception), [element.message for element in app.exception]
    assert not list(app.error), [str(error.value) for error in app.error]
    assert app.text[-1].value == "v1|"
    clear_global_process_rename_cache()


def test_proc_rename_tab_shows_the_saved_shared_profile(tmp_path: Path) -> None:
    database_path = tmp_path / "rename.duckdb"
    script = f'''
from pathlib import Path

from capa_simulation.components.process_rename_management import (
    render_process_rename_management,
)
from capa_simulation.persistence.repository import DuckDBScenarioRepository

repository = DuckDBScenarioRepository(Path(r"{database_path}"))
repository.initialize()
repository.replace_global_process_rename(
    __import__("pandas").DataFrame([("SAW", "절단")], columns=["공정", "표시명"]),
    source="테스트 초기값",
)
render_process_rename_management(repository, ["SAW", "MOLD"])
'''

    app = AppTest.from_string(script).run(timeout=60)

    assert not list(app.exception), [element.message for element in app.exception]
    assert any("공용 버전 v1" in caption.value for caption in app.caption)
    assert any("테스트 초기값" in caption.value for caption in app.caption)
    # 공용 버전 줄은 「직접 편집」 제목 바로 옆 한 칸이다(2026-11-08 사용자 그림 메모 g18) —
    # 내려받기 · 붙여넣기 줄에는 단추만 남는다.
    heading = _path_of(
        app,
        lambda node: (
            getattr(node, "type", "") == "markdown"
            and "직접 편집" in str(getattr(node, "value", ""))
        ),
    )
    version = _path_of(
        app,
        lambda node: (
            getattr(node, "type", "") == "caption"
            and "공용 버전 v1" in str(getattr(node, "value", ""))
        ),
    )
    download = _path_of(
        app, lambda node: getattr(node, "key", "") == "admin_area_process_rename_download"
    )
    assert heading[:-1] == version[:-1] and heading[-1] < version[-1]
    # 내려받기 · 붙여넣기 단추와 「보유 공정 n개」 팝오버는 그 제목 줄 오른쪽 끝 한 칸이다 — 단추
    # 줄 · 접힘 줄을 따로 세우지 않는다(2026-11-09 사용자 보드 T3 · T7).
    assert download[:-2] == heading[:-3]
    toolbar: Any = app.main
    for index in download[:-1]:
        toolbar = toolbar.children[index]
    kinds = [type(child).__name__ for child in toolbar.children.values()]
    assert kinds[-2:] == ["DownloadButton", "Button"] and len(kinds) == 3, kinds
    assert not [item.label for item in app.expander if "보유 공정" in item.label]


def test_a_long_change_memo_folds_beside_the_heading_and_keeps_the_buttons_whole(
    tmp_path: Path,
) -> None:
    """버전 줄은 사람이 적은 변경 메모를 싣는다. 메모가 길어도 오른쪽 끝 단추 칸(보유 공정 · CSV ·
    Excel)이 눌려 단추가 세로로 쌓이거나 이름이 잘리지 않게, 서식이 단추 칸을 줄지 않는 한 덩이로
    두고 제목 칸이 남은 폭에서 버전 줄을 제목 곁에 접는다. 줄이 제목 칸 바닥과 단추 칸을 못 담으면
    단추 칸이 통째로 다음 줄로 내려간다(2026-11-09 독립 검토, 설계 규칙 UI-LAY-11 · UI-ACC-02). 실제
    줄 수는 브라우저 배치라 서식의 꼴과 칸 차례만 본다. 저장 줄 변경 메모 칸은 이름 줄 없이 안내
    글이 이름을 말한다(접근성 이름은 남는다)."""
    from capa_simulation.components import process_rename_management as prm
    from capa_simulation.components.profile_caption import HEADING_KEY_PREFIX

    memo = "검토용 긴 변경 메모 — 제목 줄이 긴 버전 글을 접는지 보려고 일부러 길게 적었습니다 " * 2
    database_path = tmp_path / "rename-fold.duckdb"
    script = f'''
from pathlib import Path

from capa_simulation.components.process_rename_management import (
    render_process_rename_management,
)
from capa_simulation.persistence.repository import DuckDBScenarioRepository

repository = DuckDBScenarioRepository(Path(r"{database_path}"))
repository.initialize()
repository.replace_global_process_rename(
    __import__("pandas").DataFrame(
        [("SAW", "절단"), ("없는공정", "유령")], columns=["공정", "표시명"]
    ),
    source={memo!r},
)
render_process_rename_management(repository, ["SAW", "MOLD"])
'''

    app = AppTest.from_string(script).run(timeout=60)
    assert not list(app.exception), [element.message for element in app.exception]

    def key_is(key: str) -> Any:
        return lambda node: getattr(node, "key", "") == key

    row = _path_of(app, key_is(prm.HEADING_ROW_KEY))
    box = _path_of(app, key_is(prm.HEADING_BOX_KEY))
    tools = _path_of(app, key_is(prm.HEADING_TOOLS_KEY))
    line = _path_of(app, key_is(f"{HEADING_KEY_PREFIX}{prm.HEADING_PROFILE_KEY}"))
    download = _path_of(app, key_is("admin_area_process_rename_download"))
    assert box[:-1] == row == tools[:-1] and box[-1] < tools[-1]
    assert line[: len(box)] == box and download[:-1] == tools
    # 버전 줄은 제목 줄의 둘째 칸이다 — 서식이 그 칸만 접는다(셋째 칸은 보유 공정 밖 표지).
    heading_line: Any = app.main
    for index in line:
        heading_line = heading_line.children[index]
    cells = [heading_line.children[index] for index in sorted(heading_line.children)]
    assert len(cells) == 3
    assert cells[1].type == "caption" and "공용 버전 v1" in str(cells[1].value)
    assert cells[2].type == "caption" and cells[2].value == "보유 공정 밖 표시명 1건"

    marked = prm.heading_row_css(marked=True)
    # 제목 줄 서식과 저장 줄 표 도구 막대 자리 서식은 `st.html` 하나로 간다 — 서식만 든 `st.html` 은
    # 이벤트 칸으로 가므로 한 덩이로 묶는다(표시순서 관리 `DIRECT_EDITOR_STYLE` 과 같은 결).
    styles = [str(element.proto.body) for element in app.get("html")]
    assert prm.direct_editor_style(marked=True) in styles
    assert [body for body in styles if prm.SAVE_ROW_KEY in body] == [
        prm.direct_editor_style(marked=True)
    ]
    assert marked in prm.direct_editor_style(marked=True)
    assert toolbar_room_css(prm.SAVE_ROW_KEY) in prm.direct_editor_style(marked=True)
    floor = prm.HEADING_MIN_WIDTH + prm.HEADING_MARK_ROOM
    assert f"min-width: min({floor}px, 100%);" in marked
    assert f"min-width: min({prm.HEADING_MIN_WIDTH}px, 100%);" in prm.heading_row_css(marked=False)
    assert f".st-key-{prm.HEADING_ROW_KEY} {{ container-type: inline-size; }}" in marked
    assert f":has(> .st-key-{prm.HEADING_BOX_KEY}) {{\n  flex: 1 1 0%;" in marked
    assert (
        f":has(> .st-key-{prm.HEADING_TOOLS_KEY}) {{\n  flex: 0 0 auto;\n  width: auto;\n"
        "  margin-left: auto;" in marked
    )
    assert (
        f".st-key-{HEADING_KEY_PREFIX}{prm.HEADING_PROFILE_KEY} {{ flex-wrap: nowrap; }}" in marked
    )
    assert '[data-testid="stElementContainer"]:nth-child(2) { flex-shrink: 1; min-width: 0; }' in (
        marked
    )
    assert f"@container (max-width: {floor}px)" in marked

    note = _rename_memo(app)
    assert note.label == "변경 메모"
    assert note.proto.label_visibility.value == note.proto.label_visibility.COLLAPSED
    assert note.placeholder == prm.NOTE_PLACEHOLDER
    assert prm.NOTE_PLACEHOLDER.startswith("변경 메모 · 예: ")


def _path_of(app: AppTest, matches: Any) -> tuple[int, ...]:
    """`matches` 에 맞는 노드 하나의 델타 경로(본문 기준 자식 번호 차례)."""
    found: list[tuple[int, ...]] = []

    def walk(node: Any, path: tuple[int, ...]) -> None:
        if matches(node):
            found.append(path)
        for index, child in getattr(node, "children", {}).items():
            walk(child, (*path, index))

    walk(app.main, ())
    assert len(found) == 1, found
    return found[0]


def test_unowned_display_name_is_reported_as_a_note_not_as_an_error(tmp_path: Path) -> None:
    """보유 공정에 없는 원본의 표시명은 오류가 아니라 안내다. 「무시합니다」 라고 하지 않는다 —
    시나리오 밖 공정을 그리는 Dynamic Capa·Chatbot 에는 그 표시명이 나온다(2026-10-26 E2E —
    「Wafer Sorter → WS 정렬」 을 「무시합니다」 라 하고 Dynamic 축·Chatbot 근거 표에는 「WS 정렬」
    이 섰다)."""
    database_path = tmp_path / "rename-unowned.duckdb"
    script = f'''
from pathlib import Path

from capa_simulation.components.process_rename_management import (
    render_process_rename_management,
)
from capa_simulation.persistence.repository import DuckDBScenarioRepository

repository = DuckDBScenarioRepository(Path(r"{database_path}"))
repository.initialize()
repository.replace_global_process_rename(
    __import__("pandas").DataFrame([("없는공정", "유령")], columns=["공정", "표시명"]),
    source="테스트",
)
render_process_rename_management(repository, ["SAW", "MOLD"])
'''

    app = AppTest.from_string(script).run(timeout=60)

    assert not list(app.exception), [element.message for element in app.exception]
    assert not list(app.error)
    # 표에 있지만 이 시나리오의 계산 화면에는 그리지 않는 항목이라 표 머리 표지 + 풍선이다 — 파란
    # 안내 상자로 늘 띄우지 않는다(설계 규칙 UI-TXT-01 · 04).
    assert not [str(info.value) for info in app.info], [str(info.value) for info in app.info]
    [marker] = [item for item in app.caption if "보유 공정 밖 표시명" in item.value]
    assert marker.value == "보유 공정 밖 표시명 1건"
    assert "없는공정" in marker.proto.help and "그대로 적용됩니다" in marker.proto.help
    assert "무시합니다" not in marker.proto.help


def _start_check_expanders(app: AppTest) -> list[str]:
    """「서버 시작 점검」 펼침의 제목. 아이콘이 달린 펼침을 AppTest 는 `status` 로 센다."""
    labels = [item.label for item in app.expander] + [item.label for item in app.status]
    return [label for label in labels if "서버 시작 점검" in label]


def _start_check_script(database_path: Path, report_path: Path) -> str:
    return f"""
from pathlib import Path

import capa_simulation.settings as settings

settings.DUCKDB_PATH = Path({str(database_path)!r})
settings.CONTAINER_START_REPORT_PATH = Path({str(report_path)!r})

source = Path({str(PAGE)!r})
exec(
    compile(source.read_text(encoding="utf-8"), str(source), "exec"),
    {{"__name__": "__main__"}},
)
"""


def test_the_server_start_check_shows_the_container_report(tmp_path: Path) -> None:
    """CD 서버에는 셸도 로그도 없어 시작 스크립트의 결과를 화면에서 읽는다. 결과 파일이 있을 때만
    펼침 하나가 탭 위에 서고, 단계 표·남은 환경변수·pip 출력 끝을 싣는다. 탭은 그대로다."""
    report = tmp_path / "container_start.json"
    report.write_text(
        json.dumps(
            {
                "version": 1,
                "written_at": "2026-10-24T09:00:00+09:00",
                "steps": {
                    "install": {"status": "failed", "reason": "설치 시도 실패 — pip 종료 코드 1"},
                    "token": {"status": "ok", "reason": "토큰 파일을 씀"},
                    "user_name": {"status": "ok", "reason": "있음"},
                },
                "bigdataquery_version": None,
                "token_file": {"exists": True, "modified_at": "2026-10-24T09:00:00+09:00"},
                "user_name": {"present": True, "masked": "fa***"},
                "missing_environment": [],
                "pip_tail": ["ERROR: No matching distribution found for bigdataquery==9.9.9"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    app = AppTest.from_string(_start_check_script(tmp_path / "scenario.duckdb", report))
    app.run(timeout=120)

    assert not list(app.exception), [element.message for element in app.exception]
    [expander] = _start_check_expanders(app)
    assert "실패" in expander
    [steps] = [frame for frame in app.dataframe if "단계" in getattr(frame.value, "columns", [])]
    # 넷째 줄 「통합인증」 은 결과 파일이 아니라 지금 설정에서 판정한다(시험 환경은 꺼짐).
    assert steps.value["결과"].tolist() == ["실패", "정상", "정상", "건너뜀"]
    assert steps.value["단계"].iloc[3] == "통합인증"
    # 까닭 칸은 잘리지 않게 넓고 세 칸 합은 창 1283 의 표 폭(샘플 관측 918px) 안이다(g8-21).
    widths = {
        name: column["width"]
        for name, column in json.loads(steps.proto.columns).items()
        if name in {"단계", "결과", "까닭"}
    }
    assert widths["까닭"] > widths["단계"] + widths["결과"]
    assert sum(widths.values()) <= 918
    assert steps.value["까닭"].iloc[3] == "ADFS_CLIENT_ID 없음"
    assert "pip 종료 코드 1" in steps.value["까닭"].iloc[0]
    # 옛 결과 파일에는 통합인증 칸이 없어 그 캡션도 없다.
    assert not [c.value for c in app.caption if "시작 때 있던 통합인증" in c.value]
    assert any("No matching distribution" in block.value for block in app.code)
    assert any("fa\\*\\*\\*" in caption.value for caption in app.caption)
    assert [tab.label for tab in app.main.tabs] == [
        ":material/label: Proc Rename",
        ":material/sort: 표시순서 관리",
        ":material/fact_check: 원천 품질",
        ":material/notifications: 알림 모음",
    ]


def test_the_server_start_check_adds_the_sync_lines_when_the_server_has_them(
    tmp_path: Path,
) -> None:
    """S3 키나 `managed` 가 있는 서버는 동기화 줄이 표에 더해지고 값이 캡션에 선다. 옛 파일은
    `test_the_server_start_check_shows_the_container_report` 가 본다."""
    ok = {"status": "ok", "reason": "정상"}
    report = tmp_path / "container_start.json"
    report.write_text(
        json.dumps(
            {
                "version": 1,
                "written_at": "2026-11-07T09:00:00+09:00",
                "steps": {"install": ok, "token": ok, "user_name": ok},
                "sync": {
                    "steps": {
                        "aws_profile": {"status": "ok", "reason": "씀"},
                        "aws_cli": {"status": "failed", "reason": "판 다름 2.36.8"},
                        "ecs": {"status": "ok", "reason": "HTTP 403 닿음"},
                        "bucket": ok,
                        "boot_pull": {"status": "ok", "reason": "세대 7 · 받음"},
                    },
                    "started_at_utc": "2026-11-07T00:00:00Z",
                    "disk_free_bytes": 42949672960,
                    "disk_total_bytes": 107374182400,
                    "pod": "demo-pod-0",
                    "memory_limit_bytes": 1073741824,
                    "cpu_limit": 2.0,
                    "logical_cores": 8,
                    "duckdb_memory_limit": "800.0 MiB",
                    "duckdb_threads": "2",
                    "pull_seconds": 2.5,
                    "previous_upload_utc": "2026-11-06T23:59:00Z",
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (tmp_path / "container_app_ready.json").write_text(
        json.dumps({"ready_at_utc": "2026-11-07T00:00:45Z"}), encoding="utf-8"
    )
    app = AppTest.from_string(_start_check_script(tmp_path / "scenario.duckdb", report))
    app.run(timeout=120)

    assert not list(app.exception), [element.message for element in app.exception]
    [expander] = _start_check_expanders(app)
    assert "실패" in expander
    [steps] = [frame for frame in app.dataframe if "단계" in getattr(frame.value, "columns", [])]
    assert steps.value["단계"].tolist()[3:] == [
        "통합인증",
        "AWS 프로필",
        "aws CLI",
        "ECS 연결",
        "버킷 목록",
        "DB 받기",
    ]
    assert steps.value["까닭"].iloc[5] == "판 다름 2.36.8"
    captions = "\n".join(caption.value for caption in app.caption)
    assert "**/project 디스크** · 여유 40.0 GiB · 전체 100.0 GiB" in captions
    assert "**한도** · 메모리 1.0 GiB · CPU 2 · 논리 코어 8" in captions
    assert "받기 2.5초 · 앱 응답까지 45초" in captions
    assert "**앞 pod 마지막 올림 → 이번 앱 준비** · 105초" in captions


def test_a_cd_server_without_a_start_report_says_the_script_did_not_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CD 가 이미지 `CMD` 를 덮어써 시작 스크립트가 돌지 않으면 결과 파일이 없어 화면이 개발 PC
    와 같아진다. 스크립트가 앱에 넘기지 않는 비밀값 key 가 앱에 있으면 「결과 없음」 펼침으로
    알린다."""
    monkeypatch.setenv("CAPA_BDQ_TOKEN", "FAKE-bdq-login-token-0000")
    app = AppTest.from_string(
        _start_check_script(tmp_path / "scenario.duckdb", tmp_path / "없음.json")
    )
    app.run(timeout=120)

    assert not list(app.exception), [element.message for element in app.exception]
    [expander] = _start_check_expanders(app)
    assert "결과 없음" in expander
    # 까닭은 펼침 안 캡션이고 알릴 조건은 상태 알림(`AD-01`)이다(2026-11-03 D2).
    assert not list(app.warning)
    captions = [caption.value for caption in app.caption]
    assert any("돌지 않은 것으로" in text for text in captions), captions
    note = active_state(app, "AD-01")
    assert note is not None and "돌지 않은 것으로" in note["full"], states(app, "AD-01")
    # 알림 전문은 Guide 를 열지 않아도 다음 할 일이 있고, 평문이다(코드 표시 기호 없음).
    assert note["full"].endswith("이 문구를 그대로 알려 주세요.") and "`" not in note["full"]
    assert not any("그대로 알려 주세요" in text for text in captions), captions
    assert "FAKE-bdq-login-token-0000" not in str(note)
    assert not any("FAKE-bdq-login-token-0000" in text for text in captions)


@pytest.mark.parametrize(
    "body", ["", "{깨진 JSON", json.dumps({"version": 1, "steps": {"install": "x"}})]
)
def test_a_broken_start_report_is_told_apart_from_a_missing_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, body: str
) -> None:
    """결과 파일이 있는데 깨졌으면(빈 파일·JSON 아님·모르는 꼴) 스크립트는 돌았다 — 「결과 없음 —
    돌지 않은 것으로 보입니다」 가 아니라 「결과 파일을 읽지 못함(꼴이 다름)」 이다(E2E r2). CD
    환경변수가 있어도 그렇다."""
    monkeypatch.setenv("CAPA_ARTIFACTORY_USER", "FAKE-art-user")
    report = tmp_path / "container_start.json"
    report.write_text(body, encoding="utf-8")
    app = AppTest.from_string(_start_check_script(tmp_path / "scenario.duckdb", report))
    app.run(timeout=120)

    assert not list(app.exception), [element.message for element in app.exception]
    [expander] = _start_check_expanders(app)
    assert expander.endswith("결과 파일을 읽지 못함")
    captions = [caption.value for caption in app.caption]
    assert any("읽지 못했습니다(꼴이 다름)" in text for text in captions), captions
    assert not any("결과 파일이 없습니다" in text for text in captions)
    # 펼침 자리 글은 결론까지 — 그다음 할 일은 Guide 와 알림 전문이 말한다(설계 규칙 UI-TXT-04).
    assert not any("CI/CD" in text for text in captions), captions
    note = active_state(app, "AD-01")
    assert note is not None and "결과 파일을 읽지 못함" in note["short"], states(app, "AD-01")
    assert "CI/CD 를 다시 돌리고" in note["full"] and "`" not in note["full"]


def test_an_opened_server_start_check_stays_open_after_a_trip_to_another_screen(
    tmp_path: Path,
) -> None:
    """진단을 읽다 다른 화면(VOC 등)에 다녀오면 그리지 않은 회차에 펼침 상태가 버려져
    접혔다(E2E r1). 기억 칸(`remembered_expander`)이 편 상태를 지킨다 — 다른 화면 회차는 이
    펼침을 그리지 않는 회차로 흉내 낸다."""
    report = tmp_path / "container_start.json"
    report.write_text(
        json.dumps(
            {
                "version": 1,
                "written_at": "2026-10-24T09:00:00+09:00",
                "steps": {
                    step: {"status": "ok", "reason": "정상"}
                    for step in ("install", "token", "user_name")
                },
            }
        ),
        encoding="utf-8",
    )
    script = f"""
from pathlib import Path

import streamlit as st

import capa_simulation.settings as settings
from capa_simulation.components.container_start_check import render_container_start_check

settings.CONTAINER_START_REPORT_PATH = Path({str(report)!r})
if st.session_state.get("on_admin", True):
    render_container_start_check()
"""
    app = AppTest.from_string(script).run(timeout=60)
    key = "admin_area_container_start_check"

    def opened() -> list[bool]:
        boxes = [*app.expander, *app.status]
        return [bool(box.proto.expanded) for box in boxes if str(box.proto.id).endswith(key)]

    assert opened() == [False]
    app.session_state[key] = True  # 사용자가 펼친다
    app.run(timeout=60)
    assert opened() == [True]

    app.session_state["on_admin"] = False  # 다른 화면으로
    app.run(timeout=60)
    assert opened() == []
    app.session_state["on_admin"] = True  # 돌아온다
    app.run(timeout=60)

    assert opened() == [True]


# ------------------------------------------------------------------ 모듈 상태


# Admin 안쪽 탭 묶음을 담는 칸(`app_pages/admin_area.TABS_BOX_KEY` — 페이지 파일은 들여올 수 없어
# 글자로 맞댄다).
TABS_BOX_KEY = "admin_area_tabs_box"


def _module_status_labels(app: AppTest) -> list[str]:
    labels = [item.label for item in app.expander] + [item.label for item in app.status]
    popovers = [str(item.proto.popover.label) for item in app.get("popover")]
    return [label for label in labels + popovers if "모듈 상태" in label]


def test_the_module_run_time_is_whole_milliseconds_with_the_unit_in_the_column(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """가벼운 모듈도 서로 갈린다 — 2.4ms · 3.6ms 가 「0.00」 둘이 아니라 2 · 4 다. 칸은 정수 숫자
    칸이라 정렬이 값 차례다(글 칸이면 「12,346」 < 「2」 < 「4」 글자 차례 — 반박 검토
    2026-11-02)."""
    from capa_simulation import module_failures, module_registry
    from capa_simulation.components import module_status

    monkeypatch.delenv(module_registry.DISABLED_ENV_VAR, raising=False)
    scan = module_registry.scan_modules(PROJECT_ROOT / "tests" / "fixtures" / "modules")
    module_failures.note_run_seconds("demo_ok", 0.0024)
    module_failures.note_run_seconds("demo_keys", 0.0036)
    module_failures.note_run_seconds("demo_crash", 12.3456)

    table = module_status.build_status_table(scan)
    times = dict(zip(table["모듈"], table["마지막 회차 시간(ms)"], strict=True))

    assert "마지막 회차 시간" not in table.columns
    assert pd.api.types.is_integer_dtype(table["마지막 회차 시간(ms)"])
    assert (times["demo_ok"], times["demo_keys"], times["demo_crash"]) == (2, 4, 12346)
    assert pd.isna(times["demo_off"])
    ordered = table.sort_values("마지막 회차 시간(ms)", ascending=False, na_position="last")
    assert ordered["모듈"].tolist()[:3] == ["demo_crash", "demo_keys", "demo_ok"]
    assert module_status.run_time_ms(0.0004) == 0
    assert module_status.run_time_ms(0.0006) == 1


def test_the_module_status_is_a_popover_at_the_tab_row_only_with_modules(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """모듈 폴더가 있으면(사내) 안쪽 탭 줄 오른쪽 끝 팝오버에 상태·까닭·회차 시간이 선다 — 수는
    닫힌 단추 글, 표는 팝오버 안(2026-11-10 보드 Q-6). 탭 위에 펼침 줄이 없다. 없으면(사외) 없다."""
    from capa_simulation import module_failures, module_registry
    from capa_simulation.components import module_status

    script = _page_script(tmp_path / "scenario.duckdb")
    app = AppTest.from_string(script).run(timeout=120)
    assert not list(app.exception), [element.message for element in app.exception]
    assert _module_status_labels(app) == []

    monkeypatch.setenv(
        module_registry.ROOT_ENV_VAR, str(PROJECT_ROOT / "tests" / "fixtures" / "modules")
    )
    module_failures.record_failure("demo_crash", page="main", kind="RuntimeError", where="page")
    module_failures.note_run_seconds("demo_ok", 0.123)
    app = AppTest.from_string(script).run(timeout=120)
    assert not list(app.exception), [element.message for element in app.exception]

    assert _module_status_labels(app) == ["모듈 상태 · 켜짐 3 · 꺼짐 1 · 실패 2"]
    # 탭 위 펼침 줄은 없다 — 팝오버는 탭 묶음과 같은 칸 안 맨 앞이고 서식이 그 칸 오른쪽 위에
    # 얹는다.
    expanders = [item.label for item in app.expander] + [item.label for item in app.status]
    assert not [label for label in expanders if "모듈 상태" in label]
    (popover,) = [item for item in app.get("popover") if "모듈 상태" in item.proto.popover.label]
    assert popover.proto.id.endswith(module_status.POPOVER_KEY)
    (frame,) = popover.get("dataframe")
    assert isinstance(frame, Dataframe)
    table = frame.value
    rows = {row["모듈"]: row for row in table.to_dict("records")}
    # 회차 시간은 단위를 칸 이름에 적고 ms 정수로 싣는다(초 소수 둘째 자리면 가벼운 모듈이 0.00).
    assert rows["demo_ok"]["상태"] == "켜짐" and rows["demo_ok"]["마지막 회차 시간(ms)"] == 123
    assert pd.isna(rows["demo_off"]["마지막 회차 시간(ms)"])
    assert rows["demo_off"]["까닭"] == "module.json enabled=false"
    assert rows["demo_bad_manifest"]["상태"] == "실패"
    assert rows["demo_future_api"]["API"] == "99.0"
    # 「빠진 화면」 은 「화면」 곁이다 — 끝 칸이면 가로 스크롤 뒤로 숨는다(g8-21).
    columns = table.columns.tolist()
    assert columns.index("빠진 화면") == columns.index("화면") + 1
    assert rows["demo_crash"]["마지막 오류"].endswith("RuntimeError · page · main")
    # `module.json` 의 name 은 「모듈 이름」 이다 — 같은 줄 까닭의 「화면 이름 겹침」
    # (pages[].title)과 가른다. 까닭 · 마지막 오류는 기본 폭에서 잘리므로 넓힌 칸으로 싣는다.
    assert "화면 이름" not in table.columns
    assert rows["demo_ok"]["모듈 이름"] == "데모 모듈"
    widths = {
        name: config.get("width")
        for name, config in json.loads(app.dataframe[0].proto.columns).items()
    }
    assert widths["까닭"] == "large" and widths["마지막 오류"] == "medium"
    # 회차 시간은 숫자 칸(오른쪽 맞춤 · 값 차례 정렬)에 천 단위 쉼표 꼴이다.
    run_time = json.loads(app.dataframe[0].proto.columns)["마지막 회차 시간(ms)"]
    assert run_time["type_config"] == {"type": "number", "format": "localized"}
    # 재시작 안내는 환경변수 줄의 풍선이다 — 자리 캡션으로 늘 띄우지 않는다(설계 규칙 UI-TXT-01).
    assert not any("앱을 다시 띄운 뒤" in caption.value for caption in app.caption)
    [environment] = [
        caption for caption in app.caption if module_registry.DISABLED_ENV_VAR in caption.value
    ]
    assert "앱을 다시 띄운 뒤" in environment.proto.help
    # 탭은 그대로 넷이다.
    assert len(app.main.tabs) == 4
    # 팝오버 단추 칸과 네 탭은 같은 칸(`TABS_BOX_KEY`) 안이고 단추 칸이 앞이다 — 서식이 그 칸 오른쪽
    # 위(탭 줄 높이)에 단추 칸을 얹으므로, 둘이 갈라지면 단추가 탭 위 한 줄로 되돌아간다.
    (box,) = _keyed_blocks(app.main, TABS_BOX_KEY)
    tools, tabs = list(box.children.values())
    assert str(tools.proto.id).endswith(f"-{module_status.TOOLS_KEY}")
    assert tabs.type == "tab_container" and len(tabs.children) == 4

    monkeypatch.setenv(module_registry.ROOT_ENV_VAR, "off")
    app = AppTest.from_string(script).run(timeout=120)
    assert _module_status_labels(app) == []
    # 모듈이 없으면 그 칸에는 탭만 있다(사외 화면 그대로).
    (box,) = _keyed_blocks(app.main, TABS_BOX_KEY)
    assert [child.type for child in box.children.values()] == ["tab_container"]


def _keyed_blocks(node: Any, key: str) -> list[Any]:
    """key 를 단 칸(`st.container(key=…)`) — AppTest 블록 id 는 `…-<key>` 로 끝난다."""
    found = []
    for child in getattr(node, "children", {}).values():
        if child.type == "flex_container" and str(child.proto.id).endswith(f"-{key}"):
            found.append(child)
        found.extend(_keyed_blocks(child, key))
    return found


def test_the_module_status_places_its_button_on_the_tab_row_only_inside_the_box() -> None:
    """단추 칸 서식 — 탭 묶음 칸의 key 를 받으면 단추 칸을 그 칸 오른쪽 위에 절대 위치로 얹고 탭
    줄의 오른쪽을 비운다. 탭 묶음은 칸 바로 밑 자식으로 고른다(`:has(> …)` — 칸 자신을 `:has()`
    안에 다시 적는 꼴은 브라우저가 맞추지 않았다, 2026-11-10 사본 앱 측정). key 가 없으면 흐름 안
    한 줄이다."""
    from capa_simulation.components import module_status

    loose = module_status.tools_style(None)
    assert "position: absolute" not in loose and "tablist" not in loose
    placed = module_status.tools_style(TABS_BOX_KEY)
    box = f'.st-key-{TABS_BOX_KEY}:has(> [data-testid="stTabs"])'
    assert f"{box} {{ position: relative; }}" in placed
    assert (
        f'{box} > [data-testid="stLayoutWrapper"]:has(> .st-key-{module_status.TOOLS_KEY}) '
        "{ position: absolute; top: 0; right: 0;"
    ) in placed
    assert (
        f'{box} > [data-testid="stTabs"] > div > [role="tablist"] '
        f"{{ padding-right: {module_status.TAB_ROW_RESERVE_REM}rem; }}"
    ) in placed
    assert f":has(.st-key-{TABS_BOX_KEY}" not in placed


def test_the_module_status_stands_in_the_flow_when_the_database_stops_the_page(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DB 를 못 열어 멈추는 회차(`AD-07`)에도 모듈 상태 팝오버와 `MO-01` 은 선다 — 탭 묶음 칸을
    DB 를 열기 전에 세워 그 안에 먼저 그린다. 그 칸에 탭이 없어 단추는 흐름 안 한 줄이다(서식의
    `:has(> stTabs)` 가 맞지 않는다)."""
    from capa_simulation import module_registry

    monkeypatch.setenv(
        module_registry.ROOT_ENV_VAR, str(PROJECT_ROOT / "tests" / "fixtures" / "modules")
    )
    # DB 자리가 폴더라 열리지 않는다.
    app = AppTest.from_string(_page_script(tmp_path)).run(timeout=120)
    assert not list(app.exception), [element.message for element in app.exception]

    assert not app.main.tabs
    assert _module_status_labels(app) == ["모듈 상태 · 켜짐 3 · 꺼짐 1 · 실패 2"]
    (box,) = _keyed_blocks(app.main, TABS_BOX_KEY)
    assert [child.type for child in box.children.values()] == ["flex_container"]
    assert data_error_marks(app) == 1
    assert [item["active"] for item in states(app, "MO-01")] == [False]


def _alert_tab_script(database_path: Path) -> str:
    """활성 시나리오(내장 합성 시드의 공식)를 세운 뒤 Admin Area 를 돌리는 스크립트. 전체 기간
    계산은 세션 칸 `alert_mode` 대로 갈아 끼운다 — `stopped` 는 계산 멈춤 한 칸(오류),
    `warned` 는 경고 두 칸, `broken` 은 알림 모음을 읽지 못함(`AD-07`)이다. 회차 끝에 원래
    함수로 되돌린다 — AppTest 는 같은 프로세스에서 돌아 그대로 두면 다른 시험에 샌다."""
    return f"""
from pathlib import Path

import streamlit as st

import capa_simulation.settings as settings

settings.DUCKDB_PATH = Path({str(database_path)!r})

from capa_simulation.components import alert_board
from capa_simulation.scenario_activation import bootstrap_latest_official_scenario
from capa_simulation.services.simulation_cache import CapacityOutcome

bootstrap_latest_official_scenario(str(settings.DUCKDB_PATH))
mode = st.session_state.get("alert_mode", "stopped")


def _outcome(*_args, **_kwargs):
    if mode == "broken":
        raise ValueError("시험 — 알림 모음을 읽지 못함")
    if mode == "warned":
        return CapacityOutcome(unit_capacity=None, required_equipment=None, error="")
    return CapacityOutcome(unit_capacity=None, required_equipment=None, error="시험 — UPEH 없음")


def _alerts(outcome, density):
    if mode != "warned":
        return original_collect(outcome, density)
    return [
        alert_board.Alert("계산 멈춤", "ok", "없음"),
        alert_board.Alert("소요대수에 들지 않은 수요", "warning", "시험 경고"),
        alert_board.Alert("측정률 가정", "warning", "시험 경고"),
    ]


original_outcome = alert_board.get_full_capacity_outcome
original_collect = alert_board.collect_alerts
alert_board.get_full_capacity_outcome = _outcome
alert_board.collect_alerts = _alerts
try:
    source = Path({str(PAGE)!r})
    exec(
        compile(source.read_text(encoding="utf-8"), str(source), "exec"),
        {{"__name__": "__main__"}},
    )
finally:
    alert_board.get_full_capacity_outcome = original_outcome
    alert_board.collect_alerts = original_collect
"""


ALERT_TAB_LABEL = ":material/notifications: 알림 모음"
ALERT_TAB_MARK = (
    '.st-key-admin_area_active_tab [data-testid="stTab"]:nth-child(4)'
    ':not(.st-key-admin_area_active_tab [data-testid="stTabPanel"] *)::after'
)


def _count_mark(app: AppTest) -> str:
    """탭 이름 곁 수 표지의 서식 — 매 회차 한 자리(찍을 것이 없으면 빈 규칙)."""
    bodies = [str(element.proto.body) for element in app.get("html")]
    marks = [body for body in bodies if "stTab" in body and "content:" in body]
    empty = [body for body in bodies if body == "<style></style>"]
    assert len(marks) + len(empty) >= 1, bodies
    assert len(marks) <= 1, marks
    return marks[0] if marks else ""


def test_the_alert_count_rides_the_fourth_tab_and_follows_the_scenario(tmp_path: Path) -> None:
    """「알림 모음」 수 표지의 배선 — 탭을 연 회차에 그 계산 키로 센 수가 넷째 탭(이름 상수
    `ALERT_TAB_NAME`) 이름 곁에 선다. 계산 멈춤이면 오류색에 「!」 를 붙여 글자로도 가르고(설계 규칙
    UI-ACC-03), 경고만이면 확인 필요색 수다. 다른 탭으로 옮겨도 남고, 시나리오 내용이 바뀌면(내용
    토큰) 사라지며, 알림 모음을 계산하지 못한 회차에도 사라진다(설계 규칙 UI-DAT-11)."""
    from capa_simulation.design import tokens
    from capa_simulation.scenario_state import ACTIVE_SCENARIO_KEY

    app = AppTest.from_string(_alert_tab_script(tmp_path / "scenario.duckdb"))
    app.run(timeout=180)
    assert not list(app.exception), [element.message for element in app.exception]
    assert [tab.label for tab in app.main.tabs][3] == ALERT_TAB_LABEL
    # 닫힌 탭에서는 전체 기간 계산을 돌리지 않아 아직 셀 수 없다 — 표지가 없다.
    assert _count_mark(app) == ""

    app.session_state["admin_area_active_tab"] = ALERT_TAB_LABEL
    app.run(timeout=180)
    assert not list(app.exception), [element.message for element in app.exception]
    mark = _count_mark(app)
    assert ALERT_TAB_MARK in mark
    assert f'{ALERT_TAB_MARK} {{ content: "! 1"; }}' in mark
    assert f"color: {tokens.ALERT_ERROR};" in mark
    assert not any("알림 1건" in str(item.value) for item in app.markdown)

    app.session_state["admin_area_active_tab"] = ":material/label: Proc Rename"
    app.run(timeout=180)
    assert f'{ALERT_TAB_MARK} {{ content: "! 1"; }}' in _count_mark(app)

    app.session_state["alert_mode"] = "warned"
    app.session_state["admin_area_active_tab"] = ALERT_TAB_LABEL
    app.run(timeout=180)
    mark = _count_mark(app)
    assert f'{ALERT_TAB_MARK} {{ content: "2"; }}' in mark
    assert f"color: {tokens.ALERT_CHECK};" in mark

    app.session_state["alert_mode"] = "broken"
    app.run(timeout=180)
    assert _count_mark(app) == ""

    app.session_state["alert_mode"] = "warned"
    app.run(timeout=180)
    assert f'{ALERT_TAB_MARK} {{ content: "2"; }}' in _count_mark(app)
    app.session_state["admin_area_active_tab"] = ":material/label: Proc Rename"
    active = dict(app.session_state[ACTIVE_SCENARIO_KEY])
    active["content_token"] = "edited-content"
    app.session_state[ACTIVE_SCENARIO_KEY] = active
    app.run(timeout=180)
    assert _count_mark(app) == ""
