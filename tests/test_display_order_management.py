# Purpose: display order management 관련 정상·예외·회귀 동작을 검증한다.

from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_display_order_management_renders_global_profile(tmp_path: Path) -> None:
    database_path = tmp_path / "display-order.duckdb"
    script = f'''
from pathlib import Path

import pandas as pd

from capa_simulation.components.display_order_management import render_display_order_management
from capa_simulation.persistence.repository import DuckDBScenarioRepository

repository = DuckDBScenarioRepository(Path(r"{database_path}"))
repository.initialize()
repository.initialize_global_display_order(
    pd.DataFrame(
        {{
            "페이지 구분": ["생산 계획", "생산 계획"],
            "탭 구분": ["환산", "환산"],
            "정렬우선순위": [1, 1],
            "분류컬럼": ["양산구분", "양산구분"],
            "정렬방식": ["사용자지정", "사용자지정"],
            "분류값": ["양산", "ER"],
            "값표시순서": [1, 2],
            "활성여부": ["Y", "Y"],
        }}
    )
)
render_display_order_management(repository)
'''

    app = AppTest.from_string(script).run(timeout=30)

    assert not app.exception
    assert len(app.get("download_button")) == 1
    assert len(app.get("file_uploader")) == 0
    # 붙여넣기는 작업 줄의 팝업이다.
    assert not any(widget.label == "표시순서 표 붙여넣기" for widget in app.text_area)
    app.button(key="display_order_open_paste").click().run(timeout=30)
    assert not app.exception
    assert any(widget.label == "표시순서 표 붙여넣기" for widget in app.text_area)
    assert len(app.dataframe) == 1
    assert any("공용 버전 v1" in caption.value for caption in app.caption)


def test_display_label_warning_survives_the_rerun_after_saving(tmp_path: Path) -> None:
    """저장 성공은 곧바로 `st.rerun()` 한다. 그 회차에 그린 경고는 화면에 닿지 않으므로
    다음 회차에 성공 문구와 함께 한 번 그리고, 그다음 회차에는 지운다."""
    database_path = tmp_path / "display-order-label.duckdb"
    script = f'''
from pathlib import Path

import pandas as pd

from capa_simulation.components.display_order_management import render_display_order_management
from capa_simulation.persistence.repository import DuckDBScenarioRepository

repository = DuckDBScenarioRepository(Path(r"{database_path}"))
repository.initialize()
repository.initialize_global_display_order(
    pd.DataFrame(
        {{
            "페이지 구분": ["생산 계획"],
            "탭 구분": ["환산"],
            "정렬우선순위": [1],
            "분류컬럼": ["거래선"],
            "정렬방식": ["사용자지정"],
            "분류값": ["X"],
            "값표시순서": [1],
            "활성여부": ["Y"],
        }}
    )
)
render_display_order_management(repository)
'''

    app = AppTest.from_string(script).run(timeout=30)
    assert not app.exception
    assert not app.warning

    save = [button for button in app.button if button.label == "공용 표시순서 저장"]
    assert len(save) == 1
    save[0].click().run(timeout=30)

    assert not app.exception
    assert [element.value for element in app.success] == [
        "표시순서를 모든 시나리오의 공용 설정으로 저장했습니다."
    ]
    warnings = [element for element in app.warning if "화면 표시명입니다" in element.value]
    assert len(warnings) == 1
    assert "`거래선`" in warnings[0].value
    assert "`Customer`" in warnings[0].value
    assert warnings[0].icon == ":material/help:"

    app.run(timeout=30)
    assert not app.exception
    assert not app.success
    assert not any("화면 표시명입니다" in element.value for element in app.warning)
