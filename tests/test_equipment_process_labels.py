# Purpose: 가용설비 현황 페이지가 공용 공정 표시명을 조회 탭의 보이는 글자에만 넘기는지 검사한다.

"""가용설비 현황 페이지의 공정 표시명 배선(AppTest, 2026-10-10 사용자 결정).

화면에 보이는 글자만 표시명이고 입력 칸의 값은 원본이다. 탭마다 자세한 자리는 컴포넌트 테스트
(`test_equipment_explorer`·`test_availability_gap_panel`)가 보고, 여기서는 페이지가 **실제 공용
프로필**(시뮬레이션 DB)을 읽어 Main·Static 대비 일정·Preference 에 넘기는지, Admin 저장처럼 프로필을
갈고 캐시를 비우면 다음 회차에 따라 바뀌는지, 표시명이 없으면 화면이 그대로인지를 본다.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest
from test_equipment_pages import _open_tab, _page_script
from widget_browser import BrowserChoice

from capa_simulation.components.availability_gap_panel import PROCESS_FILTER_KEY
from capa_simulation.components.equipment_explorer import SMALL_PROCESS_KEY
from capa_simulation.persistence.cache import clear_global_process_rename_cache
from capa_simulation.persistence.equipment_cache import clear_equipment_repository
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.services.equipment_samples import (
    sample_equipment_baseline,
    sample_equipment_master,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PAGE = PROJECT_ROOT / "app_pages" / "available_equipment_status.py"
CUTOFF_FILTER_KEY = "equipment_cutoff_view_v1_filter_공정"


def _processes() -> list[str]:
    return sorted(set(sample_equipment_master()["공정소분류"]))


def _database(tmp_path: Path) -> Path:
    """빈 설비 DB(샘플 fleet 이 보인다)에 **첫 공정만 빼고** Cut-off 를 적는다."""
    database_path = tmp_path / "availability.duckdb"
    repository = DuckDBEquipmentRepository(database_path)
    repository.initialize()
    processes = _processes()[1:]
    repository.save_process_cutoff(
        pd.DataFrame(
            {
                "공정": processes,
                "Cutoff일수": [10.0] * len(processes),
                "비고": [None] * len(processes),
            }
        )
    )
    return database_path


def _save_labels(database_path: Path, labels: dict[str, str]) -> None:
    """Admin `Proc Rename` 저장과 같은 길 — 공용 프로필을 갈고 그 프로필 캐시만 비운다."""
    simulation_path = database_path.with_name(f"{database_path.stem}_simulation.duckdb")
    DuckDBScenarioRepository(simulation_path).replace_global_process_rename(
        pd.DataFrame({"공정": list(labels), "표시명": list(labels.values())}),
        source="가용설비 현황 표시명 검증",
    )
    clear_global_process_rename_cache()


def _main_options(app: AppTest) -> list[str]:
    return list(app.multiselect(key=SMALL_PROCESS_KEY).options)


def test_without_display_names_the_page_keeps_the_original_names(tmp_path: Path) -> None:
    """표시명을 정한 공정이 없으면 지금과 글자까지 같다 — 선택지는 원본 공정명의 가나다순이다."""
    app = AppTest.from_string(_page_script(PAGE, _database(tmp_path)), default_timeout=120).run()

    assert not app.exception, [item.message for item in app.exception]
    expected = sorted(
        set(sample_equipment_master()["공정소분류"].dropna().astype(str))
        | set(sample_equipment_baseline()["공정"].dropna().astype(str))
    )
    assert _main_options(app) == expected
    clear_equipment_repository()


def test_the_page_labels_every_viewing_tab_and_follows_a_changed_profile(tmp_path: Path) -> None:
    database_path = _database(tmp_path)
    first, second = _processes()[:2]
    app = AppTest.from_string(_page_script(PAGE, database_path), default_timeout=120).run()
    assert not app.exception, [item.message for item in app.exception]
    assert first in _main_options(app)

    _save_labels(database_path, {first: "표시-첫공정", second: "표시-둘째공정"})
    app.run()

    # Main — `공정소분류` 선택지는 표시명, 값은 원본이다.
    assert not app.exception, [item.message for item in app.exception]
    options = _main_options(app)
    assert {"표시-첫공정", "표시-둘째공정"} <= set(options)
    assert first not in options and second not in options
    app.multiselect(key=SMALL_PROCESS_KEY).set_value([second]).run()
    assert app.session_state[SMALL_PROCESS_KEY] == [second]

    # Preference — 편집표의 `공정` 칸과 「Cut-off 를 적지 않은 공정」 경고는 원본(새 행에 그 이름을
    # 적어야 맞댄다), `표 보기 설정` 의 공정 필터 선택지만 표시명이다.
    app = _open_tab(app, "Preference")
    assert not app.exception
    warnings = " ".join(str(item.value) for item in app.warning)
    assert first in warnings and "표시-첫공정" not in warnings
    cutoff_filter = app.multiselect(key=CUTOFF_FILTER_KEY)
    assert "표시-둘째공정" in cutoff_filter.options and second not in cutoff_filter.options
    editors = [
        frame.value for frame in app.dataframe if {"공정", "Cutoff일수"} <= set(frame.value.columns)
    ]
    assert editors, "Cut-off 편집표를 찾지 못했습니다"
    assert second in set(editors[0]["공정"])
    assert not any(str(value).startswith("표시-") for value in editors[0]["공정"])

    # Static 대비 일정 — `공정` 선택지는 표시명, 값은 원본이다.
    app = _open_tab(app, "Static 대비 일정")
    assert not app.exception, [item.message for item in app.exception]
    # 이 상자는 브라우저처럼 다룬다 — 브라우저는 고른 **글자**를 들고 있다가 다음 조작마다 되보낸다
    # (일반 AppTest 는 회차마다 세션 값으로 글자를 다시 만들어 이 차이를 못 본다).
    browser = BrowserChoice(app, "selectbox", PROCESS_FILTER_KEY)
    browser.sync()
    assert "표시-둘째공정" in browser.options() and second not in browser.options()
    browser.pick("표시-둘째공정")
    browser.run()
    assert app.session_state[PROCESS_FILTER_KEY] == second

    # 표시명을 고치면(Admin 저장) 다음 회차에 그대로 따라온다 — 표시명은 캐시 결과의 복사본에만
    # 입히므로 계산 캐시를 비우지 않아도 된다(Admin 저장이 비우는 것은 표시명 프로필 캐시 하나다).
    # 브라우저는 옛 글자 「표시-둘째공정」 을 들고 있다. 페이지가 잡은 값을 매 회차 세션에 다시 적어
    # 새 글자를 보내므로 다음 조작에도 선택이 빠지지 않는다(2026-10-10 재검증 — 적지 않으면 한 조작
    # 뒤 `전체 합계` 로 돌아갔다).
    _save_labels(database_path, {second: "표시-고친공정"})
    for _ in range(2):
        browser.run()
        assert not app.exception
        assert app.session_state[PROCESS_FILTER_KEY] == second
    assert "표시-고친공정" in browser.options() and "표시-둘째공정" not in browser.options()
    assert browser.wire == "표시-고친공정"
    clear_equipment_repository()
