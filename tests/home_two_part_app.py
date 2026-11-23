# Purpose: 두 부품 공식버전을 발행한 DB 로 HOME 을 돌리는 AppTest 대본과 그 DB 준비를 낸다.

"""두 부품 HOME 진입 도우미 — 제품별 비중 · 계획 세부수량 갈라 보임 시험이 함께 쓴다.

- `publish_two_part_revision` — 내장 시드를 부트스트랩한 DB 에
  `custom_key_tables.two_part_tables` 를 새 공식버전으로 발행한다.
- `home_script` — app.py 의 전역 준비만 재현하고 HOME 을 돌리는 대본. 그린 Plotly 그림을 key 마다
  `st.session_state["spy_figures"]` 에 남긴다. Components v2 가로 스크롤바는 AppTest 인스턴스마다
  등록이 남지 않아 빈 스텁으로 둔다.
"""

from __future__ import annotations

from pathlib import Path

from custom_key_tables import two_part_tables

HOME_PAGE = Path(__file__).resolve().parents[1] / "app_pages" / "home.py"


def home_script(database_path: Path) -> str:
    """HOME 을 돌리는 AppTest 대본 — 그린 그림을 key 로 남긴다."""
    return f"""
from pathlib import Path

import streamlit as st

import capa_simulation.components.horizontal_scrollbar as horizontal_scrollbar
import capa_simulation.settings as settings

settings.DUCKDB_PATH = Path({str(database_path)!r})

from capa_simulation.scenario_activation import bootstrap_latest_official_scenario
from capa_simulation.scenario_preset_state import apply_pending_scenario_preset

bootstrap_latest_official_scenario(str(settings.DUCKDB_PATH))
apply_pending_scenario_preset()

st.session_state["spy_figures"] = {{}}
_original_plotly_chart = st.plotly_chart


def _spy_plotly_chart(figure, *args, **kwargs):
    st.session_state["spy_figures"] = {{
        **st.session_state["spy_figures"],
        kwargs.get("key"): figure,
    }}
    return _original_plotly_chart(figure, *args, **kwargs)


st.plotly_chart = _spy_plotly_chart
_original_scrollbar = horizontal_scrollbar.render_horizontal_scrollbar
horizontal_scrollbar.render_horizontal_scrollbar = lambda *_args, **_kwargs: None
try:
    page_source = Path({str(HOME_PAGE)!r}).read_text(encoding="utf-8")
    exec(compile(page_source, {str(HOME_PAGE)!r}, "exec"), {{"__name__": "__main__"}})
finally:
    st.plotly_chart = _original_plotly_chart
    horizontal_scrollbar.render_horizontal_scrollbar = _original_scrollbar
"""


def publish_two_part_revision(database_path: Path) -> None:
    """내장 시드를 부트스트랩한 DB 에 두 부품 표를 새 공식버전으로 발행한다.

    시드는 `ensure_initial_scenario` 로 바로 세운다 — `bootstrap_latest_official_scenario` 는 세션
    칸을 보고 건너뛰는데, 앱 밖에서는 그 칸이 프로세스에 하나라 같은 프로세스에서 이 도우미를 두
    번째 부르는 시험은 새 DB 를 세우지 않는다.
    """
    from capa_simulation.application_bootstrap import ensure_initial_scenario
    from capa_simulation.persistence.cache import get_scenario_repository, load_scenario_snapshot
    from capa_simulation.persistence.models import ScenarioCreate

    repository = get_scenario_repository(str(database_path))
    ensure_initial_scenario(repository)
    official = repository.latest_official_release()
    assert official is not None
    snapshot = load_scenario_snapshot(str(database_path), official.revision_id)
    tables = dict(snapshot.tables)
    split = two_part_tables()
    tables.update({name: split[name] for name in tables if name in split})
    created = repository.create_scenario(
        ScenarioCreate(
            scenario_name="두 부품 계획",
            source_simulation_code="DEMO-TWO-PART",
            source_simulation_name="두 부품 계획",
            source_type="DUCKDB_SCENARIO_CLONE",
            pipeline_version="duckdb-rq-snapshot-v3",
        ),
        tables,
        snapshot.preset,
    )
    repository.publish_official_revision(
        str(created.scenario.scenario_id),
        str(created.revision.revision_id),
        release_name="두 부품 계획",
    )
