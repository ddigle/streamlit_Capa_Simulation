# Purpose: Admin Area 페이지와 Proc Rename 탭의 렌더링·저장 흐름을 검증한다.

from pathlib import Path

from streamlit.testing.v1 import AppTest

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
    # 표시순서 관리가 시나리오 관리 페이지에서 여기로 옮겨 왔고, 원천 품질이 뒤에 붙어 세 탭이다.
    assert [tab.label for tab in app.main.tabs] == [
        ":material/label: Proc Rename",
        ":material/sort: 표시순서 관리",
        ":material/fact_check: 원천 품질",
    ]
    # 활성 시나리오가 없으면 원천 품질 탭은 안내만 남긴다 — 화면을 멈추지 않는다.
    assert any("활성 시나리오가 없습니다" in info.value for info in app.info)
    # 내려받기는 표시명 양식과 표시순서 양식 둘이다.
    assert len(app.get("download_button")) == 2
    assert len(app.get("file_uploader")) == 0
    # 붙여넣기는 작업 줄의 팝업이다 — 닫혀 있는 동안 본문을 차지하지 않는다.
    assert not any(area.label == "공정 표시명 표 붙여넣기" for area in app.text_area)
    assert app.button(key="admin_area_process_rename_open_paste")
    assert any("공용 버전 없음" in caption.value for caption in app.caption)


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
    assert any("보유 공정의 원본명과 같은 표시명 1건" in warning.value for warning in app.warning)


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
