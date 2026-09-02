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
            "페이지 구분": ["부하량", "부하량"],
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
    assert len(app.get("file_uploader")) == 1
    assert len(app.dataframe) == 1
    assert any("공용 버전 v1" in caption.value for caption in app.caption)
