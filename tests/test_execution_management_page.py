# Purpose: 실행 관리 머리 화면이 데이터를 읽지 않고 정의와 하위 목차만 그리는지 본다.

"""실행 관리 머리 — 첫 판은 데이터를 읽지 않는다(2026-10-17 사용자 결정).

화면을 단독으로 띄워 DB 연결을 막아 둔 채 그려지는지, 하위 화면(여덟)이 사이드바 선언 차례 그대로
목차에 서는지, Guide 가 정의(「실행 관리」)를 싣는지 본다. 앱 안에서 링크 수·사이드바 상자·DB 를
열지 않는 회차는 `tests/test_app_navigation.py` 가 본다.
"""

from pathlib import Path
from typing import Any

import duckdb
import pytest
from streamlit.testing.v1 import AppTest

from capa_simulation.components.page_guide import GUIDE_TRIGGER_KEY, load_guide
from capa_simulation.navigation import (
    DYNAMIC_CAPA,
    EXECUTION_MANAGEMENT,
    EXECUTION_MANAGEMENT_SUBPAGES,
    STATIC_CAPA,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PAGE = PROJECT_ROOT / EXECUTION_MANAGEMENT.path
# 단독 실행에는 네비게이션이 없어 `render_page_link` 가 「사이드바에서 …」 글로 물러선다.
FALLBACK = "사이드바에서 "


def _run_without_databases(monkeypatch: pytest.MonkeyPatch) -> tuple[AppTest, list[Any]]:
    opened: list[Any] = []

    def refuse(*args: Any, **kwargs: Any) -> Any:
        opened.append(args)
        raise AssertionError("실행 관리 머리는 DB 를 열지 않는다")

    monkeypatch.setattr(duckdb, "connect", refuse)
    return AppTest.from_file(str(PAGE), default_timeout=60).run(), opened


def test_the_head_draws_without_opening_any_database(monkeypatch: pytest.MonkeyPatch) -> None:
    app, opened = _run_without_databases(monkeypatch)

    assert not app.exception, [element.message for element in app.exception]
    assert opened == []
    # 사이드바 상자 제목과 본문 머리가 같다. 「실행 관리」 정의는 머리가 아니라 Guide 가 말한다.
    assert [title.value for title in app.title] == [EXECUTION_MANAGEMENT.title]
    captions = [str(caption.value) for caption in app.caption]
    assert not any(caption.startswith("실행 관리:") for caption in captions)
    # 공통 조건을 읽지 않는 화면이다 — 조건 카드도 위젯도 없고, Guide 숨은 단추만 있다.
    assert [button.key for button in app.button] == [GUIDE_TRIGGER_KEY]
    assert not app.selectbox and not app.toggle


def test_the_table_of_contents_follows_the_sidebar_declaration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """하위 화면 목차는 사이드바 선언 차례 그대로(지금 여덟 — 제약 시뮬레이션까지)이고, 화면마다
    「보는 것」 한 줄이 붙는다. 선언에 화면이 늘었는데 한 줄을 적지 않으면 화면이 `KeyError` 로 멈춰
    여기서 걸린다."""
    app, _ = _run_without_databases(monkeypatch)
    captions = [str(caption.value) for caption in app.caption]

    links = [caption[len(FALLBACK) :] for caption in captions if caption.startswith(FALLBACK)]
    # 세 영역 비교의 Static·Dynamic 「열기」 둘 + 하위 화면 전부(선언 차례).
    assert links == ["열기", "열기", *(spec.title for spec in EXECUTION_MANAGEMENT_SUBPAGES)]
    for spec in EXECUTION_MANAGEMENT_SUBPAGES:
        index = captions.index(f"{FALLBACK}{spec.title}")
        summary = captions[index + 1]
        assert summary.strip(), spec.path
        # 목차 글은 화면 이름으로 말한다 — 내부 표 이름이 보이지 않는다.
        assert "RQ_" not in summary, spec.path
    # 「부서별 Gap·A/Item」(Dynamic 머리에서 옮겨 온 뜻).
    assert any(caption.startswith("부서별 Gap · A/Item") for caption in captions)


def test_explanations_ride_tooltips_and_the_next_release_is_a_dashed_slot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """영역 뜻풀이 · 목차 차례는 자리 글이 아니라 풍선이고(설계 규칙 UI-TXT-01 · 02), 다음 판에
    숫자가 들어올 칸은 점선 자리 하나다(UI-LAY-10 — 제목 · 표지 한 줄, 문장 없음)."""
    app, _ = _run_without_databases(monkeypatch)
    captions = [str(caption.value) for caption in app.caption]

    # 닫힌 로드맵 상자(눌러야 보인다) 밖의 캡션은 링크 물러섬 · 목차 「보는 것」 한 줄 · 「지금
    # 여기」 다 — 머리 설명 줄과 영역 뜻풀이(「…입니다.」), 차례 · 다음 판 문장은 자리에 없다.
    for caption in captions:
        if caption.startswith("부서별 Gap"):
            continue
        assert "합니다." not in caption and "입니다." not in caption, caption
    assert not any("다음 판에서" in caption for caption in captions)
    helps = {str(item.value): item.help for item in app.markdown}
    for spec, word in (
        (STATIC_CAPA, "약속"),
        (EXECUTION_MANAGEMENT, "이행"),
        (DYNAMIC_CAPA, "실적"),
    ):
        assert helps[f"**{spec.title}** · {word}"], spec.title
    assert "사이드바 차례 그대로" in str(helps["#### :material/list_alt: 이 영역의 화면"])
    slots = [
        str(element.proto.body)
        for element in app.get("html")
        if "em-dashboard-slot" in str(element.proto.body)
    ]
    assert len(slots) == 1
    assert "<strong>이행 현황판 자리</strong>" in slots[0]
    assert "<span>부서별 Gap · A/Item 숫자 · 다음 판</span>" in slots[0]
    assert "border:2px dashed" in slots[0]


def test_the_guide_defines_the_three_areas() -> None:
    guide = load_guide("execution_management")

    assert guide.startswith("**실행 관리**")
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
