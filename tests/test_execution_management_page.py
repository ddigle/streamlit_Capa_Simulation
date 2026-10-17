# Purpose: 실행관리 머리 화면이 데이터를 읽지 않고 정의와 하위 목차만 그리는지 본다.

"""실행관리 머리 — 첫 판은 데이터를 읽지 않는다(2026-10-17 사용자 결정).

화면을 단독으로 띄워 DB 연결을 막아 둔 채 그려지는지, 하위 화면 여섯이 사이드바 선언 차례 그대로
목차에 서는지, Guide 가 정의(「실행관리」)를 싣는지 본다. 앱 안에서 링크 수·사이드바 상자·DB 를 열지
않는 회차는 `tests/test_app_navigation.py` 가 본다.
"""

from pathlib import Path
from typing import Any

import duckdb
import pytest
from streamlit.testing.v1 import AppTest

from capa_simulation.components.page_guide import GUIDE_TRIGGER_KEY, load_guide
from capa_simulation.navigation import EXECUTION_MANAGEMENT, EXECUTION_MANAGEMENT_SUBPAGES

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PAGE = PROJECT_ROOT / EXECUTION_MANAGEMENT.path
# 단독 실행에는 네비게이션이 없어 `render_page_link` 가 「사이드바에서 …」 글로 물러선다.
FALLBACK = "사이드바에서 "


def _run_without_databases(monkeypatch: pytest.MonkeyPatch) -> tuple[AppTest, list[Any]]:
    opened: list[Any] = []

    def refuse(*args: Any, **kwargs: Any) -> Any:
        opened.append(args)
        raise AssertionError("실행관리 머리는 DB 를 열지 않는다")

    monkeypatch.setattr(duckdb, "connect", refuse)
    return AppTest.from_file(str(PAGE), default_timeout=60).run(), opened


def test_the_head_draws_without_opening_any_database(monkeypatch: pytest.MonkeyPatch) -> None:
    app, opened = _run_without_databases(monkeypatch)

    assert not app.exception, [element.message for element in app.exception]
    assert opened == []
    # 사이드바 상자 제목과 본문 머리가 같다. 설명 첫머리가 「실행관리」 정의다.
    assert [title.value for title in app.title] == [EXECUTION_MANAGEMENT.title]
    captions = [str(caption.value) for caption in app.caption]
    assert captions[0].startswith("실행관리: 약속된 Capa(Static)")
    # 공통 조건을 읽지 않는 화면이다 — 조건 카드도 위젯도 없고, Guide 숨은 단추만 있다.
    assert [button.key for button in app.button] == [GUIDE_TRIGGER_KEY]
    assert not app.selectbox and not app.toggle


def test_the_table_of_contents_follows_the_sidebar_declaration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """하위 화면 목차는 사이드바 선언 차례 그대로 여섯이고, 화면마다 「보는 것」 한 줄이 붙는다.
    선언에 화면이 늘었는데 한 줄을 적지 않으면 화면이 `KeyError` 로 멈춰 여기서 걸린다."""
    app, _ = _run_without_databases(monkeypatch)
    captions = [str(caption.value) for caption in app.caption]

    links = [caption[len(FALLBACK) :] for caption in captions if caption.startswith(FALLBACK)]
    # 세 영역 비교의 Static·Dynamic 「열기」 둘 + 하위 여섯.
    assert links == ["열기", "열기", *(spec.title for spec in EXECUTION_MANAGEMENT_SUBPAGES)]
    for spec in EXECUTION_MANAGEMENT_SUBPAGES:
        index = captions.index(f"{FALLBACK}{spec.title}")
        assert captions[index + 1].strip(), spec.path
    # 「부서별 Gap·A/Item」(Dynamic 머리에서 옮겨 온 뜻)과 다음 판 한 줄.
    assert any(caption.startswith("부서별 Gap · A/Item") for caption in captions)
    assert captions[-1].endswith("다음 판에서 이 화면에 이행 현황판 숫자가 들어옵니다.")


def test_the_guide_defines_the_three_areas() -> None:
    guide = load_guide("execution_management")

    assert guide.startswith("**실행관리**(실행 Management)")
    for text in (
        "Static Capa",
        "Dynamic Capa",
        "설비 일정 기준 가용대수",
        "「Dynamic」 이라는 말은 실적 Capa 에만 씁니다.",
        "확보율 보정",
        "자원운영팀",
    ):
        assert text in guide, text
    for spec in EXECUTION_MANAGEMENT_SUBPAGES:
        # 목차는 상태 접미(`(구현중)` 등)를 뗀 이름으로 적는다.
        assert spec.title.split(" (")[0].split(" 실적")[0] in guide, spec.path
