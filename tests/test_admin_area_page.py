# Purpose: Admin Area 페이지와 Proc Rename 탭의 렌더링·저장 흐름을 검증한다.

from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest

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
    assert any("Proc Rename" in subheader.value for subheader in app.subheader)
    # 표시순서 관리가 시나리오 관리 페이지에서 여기로 옮겨 왔고, 원천 품질과 HOME 에서 걷은 계산
    # 알림을 모은 「알림 모음」 이 뒤에 붙어 네 탭이다.
    assert [tab.label for tab in app.main.tabs] == [
        ":material/label: Proc Rename",
        ":material/sort: 표시순서 관리",
        ":material/fact_check: 원천 품질",
        ":material/notifications: 알림 모음",
    ]
    # 원천 품질 탭은 닫혀 있으면 그리지 않는다(위젯이 없는 읽기 전용 탭).
    assert not any("활성 시나리오가 없습니다" in info.value for info in app.info)
    # 내려받기는 표시명 양식과 표시순서 양식 둘이다.
    assert len(app.get("download_button")) == 2
    assert len(app.get("file_uploader")) == 0
    # 붙여넣기는 작업 줄의 팝업이다 — 닫혀 있는 동안 본문을 차지하지 않는다.
    assert not any(area.label == "공정 표시명 표 붙여넣기" for area in app.text_area)
    assert app.button(key="admin_area_process_rename_open_paste")
    assert any("공용 버전 없음" in caption.value for caption in app.caption)
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
    assert any("활성 시나리오가 없습니다" in info.value for info in app.info)


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
    assert any("2개 컬럼 중 1개" in warning.value for warning in app.warning)

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
    assert any("중복" in error.value for error in app.error)
    assert app.text[-1].value == "v0|"


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
    collision = next(
        warning.value
        for warning in app.warning
        if "보유 공정의 원본명과 같은 표시명 1건" in warning.value
    )
    # 선택 상자·표에서 어떻게 보이는지와 검사 범위(설비 마스터는 보지 않는다)를 사실대로 적는다.
    assert "「표시명 (원본)」" in collision and "표·그림·버튼에서는 같은 글자" in collision
    # 모든 화면의 공정 상자가 글자를 가른다 — 「다른 공정이 잡힐 수 있다」 는 이제 사실이 아니다.
    assert "다른 공정이 잡힐" not in collision
    assert "설비 마스터에만 있는 공정은 여기서 검사하지 않습니다" in collision


def test_direct_edit_save_refuses_to_overwrite_a_newer_shared_profile(tmp_path: Path) -> None:
    """A 가 직접 편집 표를 연 뒤 B 가 표시명을 저장했다. A 의 저장은 막히고 B 의 저장본이 남는다
    (판정 기준과 같은 버전 대조). 그 회차가 그린 최신 저장본에서 다시 누르면 저장된다."""
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
    assert app.text[-1].value == "v2|SAW>절단;MOLD>성형"

    next(button for button in app.button if button.label == "공용 공정 표시명 저장").click()
    app.run(timeout=60)
    assert not list(app.error), [str(error.value) for error in app.error]
    assert app.text[-1].value == "v3|SAW>절단;MOLD>성형"
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


def test_unowned_display_name_is_reported_as_ignored_not_as_an_error(tmp_path: Path) -> None:
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
    assert any("무시합니다" in info.value for info in app.info)
