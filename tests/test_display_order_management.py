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
    warnings = [element for element in app.warning if "화면 표시명을 적었습니다" in element.value]
    assert len(warnings) == 1
    assert "`거래선`" in warnings[0].value
    assert "`거래선` → `Customer`" in warnings[0].value
    assert warnings[0].icon == ":material/help:"

    app.run(timeout=30)
    assert not app.exception
    assert not app.success
    assert not any("화면 표시명을 적었습니다" in element.value for element in app.warning)


def test_a_rejected_save_is_reported_above_the_editor(tmp_path: Path) -> None:
    """거절된 저장의 오류는 표 **위**, 저장 버튼 바로 위에 선다.

    460px 표 아래에 그리면 화면 밖이라 저장을 눌러도 아무 일이 없는 것처럼 보였다(2026-10-05 E2E).
    """
    from capa_simulation.components import display_order_management

    database_path = tmp_path / "display-order-error.duckdb"
    script = f'''
from pathlib import Path

import pandas as pd

from capa_simulation.components import display_order_management
from capa_simulation.persistence.repository import DuckDBScenarioRepository

repository = DuckDBScenarioRepository(Path(r"{database_path}"))
repository.initialize()
repository.initialize_global_display_order(
    pd.DataFrame(
        {{
            "페이지 구분": ["생산 계획"],
            "탭 구분": ["환산"],
            "정렬우선순위": [1],
            "분류컬럼": ["제품정보"],
            "정렬방식": ["사용자지정"],
            "분류값": ["X"],
            "값표시순서": [1],
            "활성여부": ["Y"],
        }}
    )
)

def _reject(*_args, **_kwargs):
    raise ValueError("거절된 저장")

# 모듈 속성을 바꾸므로 그린 뒤 되돌린다 — 되돌리지 않으면 같은 프로세스의 다음 테스트 저장까지
# 이 함수가 막는다.
saving = display_order_management._save_global_display_order
display_order_management._save_global_display_order = _reject
try:
    display_order_management.render_display_order_management(repository)
finally:
    display_order_management._save_global_display_order = saving
'''
    app = AppTest.from_string(script).run(timeout=30)
    assert not app.exception
    next(button for button in app.button if button.label == "공용 표시순서 저장").click().run(
        timeout=30
    )

    assert not app.exception
    assert [element.value for element in app.error] == ["거절된 저장"]
    order = [
        "error" if type(node).__name__ == "Error" else "editor"
        for node in app.main
        if type(node).__name__ == "Error"
        or str(getattr(node, "key", None) or "").startswith(
            display_order_management.DISPLAY_ORDER_EDITOR_KEY
        )
    ]
    assert order.index("error") < order.index("editor"), order


def test_a_stored_case_clash_opens_the_tab_with_a_warning(tmp_path: Path) -> None:
    """검사 전에 저장된 `Top`·`TOP` 이 있어도 탭이 열리고, 겹친 값을 경고한다.

    탭이 저장 검증으로 열리지 않으면 그 값을 고칠 화면이 없다. 내려받기도 그대로 선다.
    """
    database_path = tmp_path / "display-order-clash.duckdb"
    script = f'''
from pathlib import Path

import pandas as pd

from capa_simulation.components.display_order_management import render_display_order_management
from capa_simulation.persistence import display_order_store
from capa_simulation.persistence._sql_helpers import connect
from capa_simulation.persistence.repository import DuckDBScenarioRepository

database = Path(r"{database_path}")
repository = DuckDBScenarioRepository(database)
repository.initialize()
if not database.with_suffix(".seeded").exists():
    with connect(database) as connection:
        display_order_store.insert_global_display_order(
            connection,
            pd.DataFrame(
                {{
                    "페이지 구분": ["부하량", "부하량"],
                    "탭 구분": ["환산", "환산"],
                    "정렬우선순위": [1, 1],
                    "분류컬럼": ["WF 구분", "WF 구분"],
                    "정렬방식": ["사용자지정", "사용자지정"],
                    "분류값": ["Top", "TOP"],
                    "값표시순서": [1, 2],
                    "활성여부": ["Y", "Y"],
                }}
            ),
            version=1,
            source="검사 전 저장본",
        )
    database.with_suffix(".seeded").write_text("1")
render_display_order_management(repository)
'''
    app = AppTest.from_string(script).run(timeout=30)

    assert not app.exception, [item.message for item in app.exception]
    assert len(app.get("download_button")) == 1
    warnings = [element.value for element in app.warning]
    assert any("부하량 › 환산 › WF 구분: `Top` · `TOP`" in value for value in warnings), warnings

    # 그대로 저장하면 막히고 겹친 값을 알린다.
    next(button for button in app.button if button.label == "공용 표시순서 저장").click().run(
        timeout=30
    )
    assert not app.exception
    assert any("`Top` · `TOP`" in element.value for element in app.error)


def test_the_direct_editor_fixes_one_clashing_scope_while_another_remains(tmp_path: Path) -> None:
    """두 범위에 예전 겹침이 있을 때 직접 편집으로 한 범위를 고쳐 저장하면 저장된다(리뷰 재현).

    화면의 저장 사슬(`_save_global_display_order` → Repository)이 다른 범위의 겹침을 넘기지 않으면
    어느 범위를 고쳐도 막혔다. AppTest 는 편집표 칸을 고칠 수 없어, 이 스크립트 안에서만
    `st.data_editor` 가 「고친 표」(고른 범위의 첫 줄만 남긴 것)를 돌려주게 한다.
    """
    database_path = tmp_path / "display-order-two-clashes.duckdb"
    script = f'''
from pathlib import Path

import pandas as pd
import streamlit as st

from capa_simulation.components.display_order_management import render_display_order_management
from capa_simulation.persistence import display_order_store
from capa_simulation.persistence._sql_helpers import connect
from capa_simulation.persistence.repository import DuckDBScenarioRepository

database = Path(r"{database_path}")
repository = DuckDBScenarioRepository(database)
repository.initialize()
if not database.with_suffix(".seeded").exists():
    rows = []
    for tab in ("계획", "환산"):
        for order, value in enumerate(("Top", "TOP"), start=1):
            rows.append(
                {{
                    "페이지 구분": "부하량",
                    "탭 구분": tab,
                    "정렬우선순위": 1,
                    "분류컬럼": "WF 구분",
                    "정렬방식": "사용자지정",
                    "분류값": value,
                    "값표시순서": order,
                    "활성여부": "Y",
                }}
            )
    with connect(database) as connection:
        display_order_store.insert_global_display_order(
            connection, pd.DataFrame(rows), version=1, source="검사 전 저장본"
        )
    database.with_suffix(".seeded").write_text("1")

original_editor = st.data_editor


def _fixed_editor(frame, **kwargs):
    original_editor(frame, **kwargs)
    return frame.iloc[[0]].reset_index(drop=True)


st.data_editor = _fixed_editor
try:
    render_display_order_management(repository)
finally:
    st.data_editor = original_editor
'''
    app = AppTest.from_string(script).run(timeout=30)
    assert not app.exception, [item.message for item in app.exception]
    warning = " ".join(element.value for element in app.warning)
    assert "부하량 › 계획" in warning and "부하량 › 환산" in warning
    assert "범위마다 따로 고칠 수 있습니다" in warning
    assert app.selectbox(key="display_order_tab").value == "계획"

    next(button for button in app.button if button.label == "공용 표시순서 저장").click().run(
        timeout=30
    )

    assert not app.exception, [item.message for item in app.exception]
    assert not app.error, [element.value for element in app.error]
    assert any("공용 설정으로 저장했습니다" in element.value for element in app.success)
    # 고친 범위는 사라지고 남은 범위만 경고한다.
    warning = " ".join(element.value for element in app.warning)
    assert "부하량 › 환산" in warning and "부하량 › 계획" not in warning
