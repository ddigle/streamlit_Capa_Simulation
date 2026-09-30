# Purpose: 산출 결과 확보율 탭의 히트맵 상자가 탭을 오가도 편 채로 남는지 검증한다.

"""편 히트맵은 다른 탭에 갔다 와도 편 채다(2026-10-01 브라우저 점검).

산출 결과는 열린 탭의 본문만 그린다. `key` 없는 확장 패널은 떠난 동안 그려지지 않아 돌아올 때
새로 만들어지고 기본값(접힘)으로 섰다. 같은 탭의 `히트맵 주요 공정` 선택은 `persist_state` 라
남는데 상자만 접혀, 보던 히트맵을 다시 펴야 했다.
"""

from streamlit.testing.v1 import AppTest
from test_reference_data_page import (
    CALC_TAB_KEY,
    REQUIRED_TAB,
    SECUREMENT_TAB,
    TWO_PROCESS_RESULT_SCRIPT,
)

HEATMAP_EXPANDER_KEY = "securement_heatmap_expander"


def _heatmap_boxes(app: AppTest) -> list[bool]:
    """히트맵 상자의 펼침. 상태를 추적하는 상자는 id 끝이 그 `key` 다."""
    return [
        bool(box.proto.expanded)
        for box in app.expander
        if str(box.proto.id).endswith(f"-{HEATMAP_EXPANDER_KEY}")
    ]


def _open(app: AppTest, tab: str) -> AppTest:
    app.session_state[CALC_TAB_KEY] = tab
    app.run()
    assert not app.exception
    return app


def test_an_opened_heatmap_stays_open_after_a_trip_to_another_tab() -> None:
    app = _open(AppTest.from_string(TWO_PROCESS_RESULT_SCRIPT, default_timeout=60), SECUREMENT_TAB)
    assert _heatmap_boxes(app) == [False]

    app.session_state[HEATMAP_EXPANDER_KEY] = True  # 사용자가 상자를 편다
    app.run()
    assert _heatmap_boxes(app) == [True]

    _open(app, REQUIRED_TAB)
    assert _heatmap_boxes(app) == []
    _open(app, SECUREMENT_TAB)

    assert _heatmap_boxes(app) == [True]
