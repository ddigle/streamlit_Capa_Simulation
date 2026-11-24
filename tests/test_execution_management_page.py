# Purpose: 실행 관리 머리 화면이 데이터를 읽지 않고 정의와 하위 목차만 그리는지 본다.

"""실행 관리 머리 — 첫 판은 데이터를 읽지 않는다(2026-10-17 사용자 결정).

화면을 단독으로 띄워 DB 연결을 막아 둔 채 그려지는지, 하위 화면(여덟)이 사이드바 선언 차례 그대로
목차에 서는지, Guide 가 정의(「실행 관리」)를 싣는지 본다. 운영 서버(통합인증 켜짐)의 개발자가 아닌
회차에는 구현 중 화면 카드 · 이행 현황판 자리가 빠지는지도 본다(2026-11-24 정식판 마감 2-A — 등급은
`grade_support` 의 합성 계정). 앱 안에서 링크 수·사이드바 상자·DB 를 열지 않는 회차는
`tests/test_app_navigation.py` 가 본다.
"""

import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import duckdb
import pytest
from grade_support import as_grade
from streamlit.testing.v1 import AppTest

from capa_simulation.auth import grades
from capa_simulation.components import sso_identity
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
SCREENS_HEADING = "#### 이 영역의 화면"


def _guide_screen_names(guide: str) -> list[str]:
    """Guide 「이 영역의 화면」 절의 `- **이름**` 줄 이름(적힌 차례). 실적 셋은 묶음 줄
    하나(`- **효율 · UPEH · 수율 실적**`)가 맡아 「효율 실적」 · 「UPEH 실적」 · 「수율 실적」
    으로 편다."""
    section = guide[guide.index(SCREENS_HEADING) + len(SCREENS_HEADING) :]
    section = section.split("\n#### ", 1)[0]
    names: list[str] = []
    for name in re.findall(r"^- \*\*([^*]+)\*\*", section, flags=re.MULTILINE):
        if name.endswith(" 실적"):
            names.extend(f"{part} 실적" for part in name.removesuffix(" 실적").split(" · "))
        else:
            names.append(name)
    return names


def _subpage_names(titles: Sequence[str]) -> list[str]:
    """선언의 하위 화면 제목에서 상태 접미(`(구현중)` 등)를 뗀 이름."""
    return [title.split(" (")[0] for title in titles]


def _run_without_databases(monkeypatch: pytest.MonkeyPatch) -> tuple[AppTest, list[Any]]:
    opened: list[Any] = []

    def refuse(*args: Any, **kwargs: Any) -> Any:
        opened.append(args)
        raise AssertionError("실행 관리 머리는 DB 를 열지 않는다")

    monkeypatch.setattr(duckdb, "connect", refuse)
    return AppTest.from_file(str(PAGE), default_timeout=60).run(), opened


def _dashboard_slots(app: AppTest) -> list[str]:
    """이행 현황판 점선 자리(`em-dashboard-slot`)의 HTML 본문."""
    return [
        str(element.proto.body)
        for element in app.get("html")
        if "em-dashboard-slot" in str(element.proto.body)
    ]


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
    """하위 화면 목차는 사이드바 선언 차례 그대로(지금 여덟 — 제약 시뮬레이션까지)이고, 카드는
    화면 이름 링크 하나다 — 그 화면이 보는 것은 카드 밑 회색 줄이 아니라 Guide 「이 영역의 화면」
    이다(설계 규칙 UI-TXT-01 · 02 — 규칙집 6-39)."""
    app, _ = _run_without_databases(monkeypatch)
    captions = [str(caption.value) for caption in app.caption]

    links = [caption[len(FALLBACK) :] for caption in captions if caption.startswith(FALLBACK)]
    # 세 영역 비교의 Static·Dynamic 「열기」 둘 + 하위 화면 전부(선언 차례).
    assert links == ["열기", "열기", *(spec.title for spec in EXECUTION_MANAGEMENT_SUBPAGES)]
    # 캡션은 링크 물러섬과 「지금 여기」 뿐이다 — 카드 밑 「보는 것」 줄이 없다.
    others = [caption for caption in captions if not caption.startswith(FALLBACK)]
    assert others == [":material/my_location: 지금 여기"], others
    # 「부서별 Gap · A/Item」 · 로드맵은 본문 머리 접힘이 아니라 Guide 첫 단락이다(2026-11-09 사용자
    # 규칙 「상단 여백 · 문구 최소화」, 설계 규칙 UI-LAY-08 · UI-TXT-01).
    assert not any("부서별 Gap · A/Item —" in caption for caption in captions)
    assert not app.expander and not app.status


def test_explanations_ride_tooltips_and_the_next_release_is_a_dashed_slot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """영역 뜻풀이 · 목차 차례는 자리 글이 아니라 풍선이고(설계 규칙 UI-TXT-01 · 02), 다음 판에
    숫자가 들어올 칸은 점선 자리 하나다(UI-LAY-10 — 제목 · 표지 한 줄, 문장 없음)."""
    app, _ = _run_without_databases(monkeypatch)
    captions = [str(caption.value) for caption in app.caption]

    # 캡션은 링크 물러섬 · 「지금 여기」 다 — 머리 설명 줄과 영역 뜻풀이(「…입니다.」), 차례 ·
    # 다음 판 문장, 목차 「보는 것」 줄은 자리에 없다.
    for caption in captions:
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
    slots = _dashboard_slots(app)
    assert len(slots) == 1
    assert "<strong>이행 현황판 자리</strong>" in slots[0]
    assert "<span>부서별 Gap · A/Item 숫자 · 다음 판</span>" in slots[0]
    assert "border:2px dashed" in slots[0]


def test_draft_cards_and_the_dashboard_slot_are_developer_only_on_the_operational_server(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """운영 서버(통합인증 켜짐)의 실무자에게는 목차에 구현 중 화면(실적 셋) 카드가 없어 다섯이고, 맨
    아래 이행 현황판 점선 자리도 없다. 세 영역의 Dynamic Capa 는 카드 · 이름 · 풍선이 그대로이고
    「열기」 만 없다(설계 규칙 UI-INP-07 예외 — 숨긴 자리가 값을 보이던 곳이면 값만). 같은 서버의
    개발자는 지금처럼 여덟 · 「열기」 둘 · 자리 하나다(UI-LAY-10 예외 — 2026-11-24 정식판 마감 2-A).
    판정은 사이드바와 같은 `sso_identity.unfinished_hidden` 하나다."""
    for grade in (grades.EDITOR, grades.DEVELOPER):
        as_grade(monkeypatch, grade)
        developer = grade == grades.DEVELOPER
        assert sso_identity.unfinished_hidden() is (not developer)
        app, opened = _run_without_databases(monkeypatch)

        assert not app.exception, [element.message for element in app.exception]
        assert opened == []
        captions = [str(caption.value) for caption in app.caption]
        links = [caption[len(FALLBACK) :] for caption in captions if caption.startswith(FALLBACK)]
        shown = [
            spec.title for spec in EXECUTION_MANAGEMENT_SUBPAGES if developer or not spec.unfinished
        ]
        assert len(shown) == (8 if developer else 5)
        opens = ["열기", "열기"] if developer else ["열기"]
        assert links == [*opens, *shown], grade
        assert len(_dashboard_slots(app)) == (1 if developer else 0), grade
        helps = {str(item.value): item.help for item in app.markdown}
        for spec, word in (
            (STATIC_CAPA, "약속"),
            (EXECUTION_MANAGEMENT, "이행"),
            (DYNAMIC_CAPA, "실적"),
        ):
            assert helps[f"**{spec.title}** · {word}"], (grade, spec.title)
        others = [caption for caption in captions if not caption.startswith(FALLBACK)]
        assert others == [":material/my_location: 지금 여기"], (grade, others)
    assert DYNAMIC_CAPA.unfinished and not STATIC_CAPA.unfinished


def test_the_guide_defines_the_three_areas() -> None:
    guide = load_guide("execution_management")

    assert guide.startswith("**실행 관리**")
    # 업무 활용 목적 · 부서별 Action Item · 로드맵은 첫 단락이다 — 첫 소제목(「세 영역」) 앞.
    opening = guide.split("#### ", 1)[0]
    for text in (
        "부서별 Gap · A/Item",
        "기술팀 · 설비 일정",
        "기술팀 · 설비 성능",
        "자원운영팀 · 투자",
        "로드맵 — 약속 대비 Gap 확인 → 부서별 A/Item · 이행 요청 → 진척 관리",
    ):
        assert text in opening, text
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


def test_the_guide_says_what_each_subpage_looks_at() -> None:
    """목차 카드 밑에 서던 「보는 것」 줄의 뜻은 Guide 「이 영역의 화면」 목록이 말한다 — 화면마다
    한 줄이고 카드에 화면 이름만 있다는 것도 그 절 머리가 말한다(설계 규칙 UI-TXT-02)."""
    guide = " ".join(load_guide("execution_management").replace("**", "").split())
    section = guide[guide.index("#### 이 영역의 화면") : guide.index("#### 가용대수를 부르는 말")]
    assert "목차 카드에는 화면 이름만 있고 누르면 그 화면이 열립니다." in section
    for text in (
        "어느 화면에서든 공정 하나를 눌러 바로 깊게 보는 목적지",
        "그 달을 메울 호기·기간",
        "단축이 필요한 공정 전부의 진척 관리 한 페이지",
        "기한 임박·이행 지연",
        "공정 하나에 미래 제약(제약 제품 전용 설비)이 생기면",
        "개조 비가동",
        "설비 일정 기준 가용대수",
        "Static 대비 일정",
        "입력 비가동대수",
        "셋업 이행을 공간·호기로 봅니다(반입 전·지연·미확인 표식)",
        "기준정보 대비 실적 Gap 과 개선 우선순위",
        "실적 DB 연결 전 — 합성 샘플, 운영 서버에서는 개발자에게만 보입니다",
    ):
        assert text in section, text


def test_the_guide_reads_true_for_every_viewer() -> None:
    """Guide 는 보는 사람마다 다를 수 없다 — 운영 서버의 개발자가 아니면 맨 아래 점선 자리가
    없으므로 그 자리를 가리키지 않고 「아직 들어오지 않았습니다」 로 말하며, 운영 서버에서
    개발자에게만 서는 실적 셋 · Dynamic Capa 는 그렇다고 적는다(2026-11-24 정식판 마감 2-A —
    설계 규칙 UI-TXT-01 — 화면 자리에는 설명 글을 더하지 않는다)."""
    raw = load_guide("execution_management")
    guide = " ".join(raw.replace("**", "").split())

    assert "이행 현황판 숫자(부서별 Gap · A/Item)는 아직 들어오지 않았습니다." in guide
    assert "다음 판에서" not in guide
    assert "맨 아래 점선" not in guide
    (dynamic_row,) = [
        line for line in raw.splitlines() if line.startswith(f"| **{DYNAMIC_CAPA.title}** · 실적 |")
    ]
    assert "운영 서버에서는 개발자에게만 보입니다" in dynamic_row


def test_every_subpage_has_its_own_line_in_the_guide_screen_list() -> None:
    """목차 카드는 화면 이름뿐이라 화면이 무엇을 보는지는 Guide 「이 영역의 화면」 목록 한 줄만
    말한다 — 선언(`EXECUTION_MANAGEMENT_SUBPAGES`)의 하위 화면마다 `- **이름**` 줄이 사이드바
    차례대로 있어야 한다(실적 셋은 묶음 줄 하나). 선언에 화면이 늘고 Guide 를 고치지 않으면
    이름이 Guide 다른 단락에 있어도 여기서 깨진다(설계 규칙 UI-TXT-02 — 규칙집 6-39)."""
    guide = load_guide("execution_management")
    declared = _subpage_names([spec.title for spec in EXECUTION_MANAGEMENT_SUBPAGES])

    assert _guide_screen_names(guide) == declared
    # 그물이 비지 않음 — 목록에서 화면 줄 하나의 굵은 이름이 빠지거나 실적 묶음 줄에서 하나가
    # 빠진 Guide 는 선언과 어긋난다. 이름이 Guide 다른 단락에만 있으면(머리 단락의 「설비
    # 일정」 처럼) 목록 줄로 치지 않는다.
    assert _guide_screen_names(guide.replace("- **Space 현황**", "- Space 현황")) != declared
    assert (
        _guide_screen_names(guide.replace("효율 · UPEH · 수율 실적", "효율 · 수율 실적"))
        != declared
    )
    assert "설비 일정" in guide and "설비 일정" not in _guide_screen_names(guide)
