# Purpose: 코어 화면 머리에 설명 줄이 없고 걷은 소개 말이 그 화면 Guide 에 남았는지 본다.

"""화면 머리말 걷기(검수 물음 head-desc, 답 「머리말을 모두 걷는다」 · 메모 「꼭 필요한 소개 문구는
guide에 포함.」).

화면 소개는 그 화면 Guide 가 맡는다(설계 규칙 UI-TXT-01 · UI-TXT-02). 설명 인자를 넘기는 코어
화면은 없다 — 마지막 둘 가운데 필요 단축 일정은 머리말을 Guide 로 옮겼고(2026-11-08 그림 메모 g03),
모듈 공개 창구(`module_api.page_header`)는 창구 1.1 부터 그 인자를 받기만 하고 그리지 않는다(답 d1).
문장 그물(`tests/test_place_sentence_sites.py`)은 `description=` 을 훑지 않아 여기서 호출 자리를
맞댄다.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from capa_simulation.components.page_guide import GUIDE_TRIGGER_KEY, load_guide
from capa_simulation.components.page_header import render_page_header_with_status

ROOT = Path(__file__).resolve().parents[1]
HEADER_CALLS = {"render_page_header", "_render_page_header", "render_page_header_with_status"}
# 설명 인자를 넘겨도 되는 자리 — 없다. 모듈 창구(`module_api.page_header`)는 1.1 부터 받기만 한다.
DESCRIPTION_SITES: set[str] = set()
# 머리말에서 옮긴 말 — (화면 파일, Guide 에 남아야 할 글).
MOVED_WORDS = (
    ("actual_efficiency", "생산이력의 공정·제품별 효율 실적을 Capa 효율 기준정보와 비교"),
    ("actual_efficiency", "개선 우선순위와 조치 진행상태를 관리"),
    ("actual_upeh", "생산이력의 공정·제품별 UPEH 실적을 Capa UPEH 기준정보와 비교"),
    ("actual_upeh", "개선 우선순위와 조치 진행상태를 관리"),
    ("yield_actual", "공정·제품별 수율 실적을 Capa 기준정보(RQ_YLD)의 수율과 비교"),
    ("yield_actual", "개선 우선순위와 조치 진행상태를 관리"),
    ("wip_status", "공정·제품·STEP별 보유 재공, 유입과 Flow를 일 표준 가능량과 비교"),
    ("capa_chatbot", "데이터 조회, 부족 공정 파악과 원인 탐색을 지원하는 대화형 분석 화면"),
    ("reference_integrity", "표준 Capa 가 실제로 얼마나 실현됐는지 다시 계산"),
    ("reference_integrity", "설비 성능(효율·UPEH)과 가용 Capa 활용(Rundown·재공부족)"),
    ("internal_modules", "동료가 만든 화면입니다 — 아직 코어 계산과 이어지지 않습니다."),
    ("process_capa_detail", "어느 화면에서든 공정 하나를 눌러 바로 깊게 보는 목적지"),
    ("process_capa_detail", "산출 근거 → 부족한 달"),
    ("process_capa_detail", "단축이 필요한 공정 전부의 진척은 `필요 단축 일정`"),
    ("constraint_simulation", "제약 제품에 먼저 떼어 준 뒤 기존 제품 확보율이 언제부터 얼마나"),
    ("execution_management", "유관부서에 이행을 요청"),
    ("execution_management", "Static 기준정보에 반영되도록"),
    ("required_shortening", "단축이 필요한 공정 전부의 진척 관리 한 페이지"),
    ("required_shortening", "공정 진척 보드·기한 임박·이행 지연"),
    ("required_shortening", "공정 하나를 깊이 보려면 카드의 「공정 Capa 상세에서 근거 보기」"),
)


def _sources() -> list[Path]:
    return [
        *sorted((ROOT / "app_pages").glob("*.py")),
        *sorted((ROOT / "src" / "capa_simulation").rglob("*.py")),
    ]


def _passes_description(path: Path) -> bool:
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Call):
            name = getattr(node.func, "id", getattr(node.func, "attr", None))
            if name in HEADER_CALLS and any(kw.arg == "description" for kw in node.keywords):
                return True
    return False


def _guide_text(page: str) -> str:
    return " ".join(load_guide(page).replace("**", "").split())


def test_no_core_screen_passes_a_description() -> None:
    sites = {path.relative_to(ROOT).as_posix() for path in _sources() if _passes_description(path)}
    assert sites == DESCRIPTION_SITES


def test_the_status_header_takes_no_description() -> None:
    assert "description" not in inspect.signature(render_page_header_with_status).parameters


@pytest.mark.parametrize(("page", "words"), MOVED_WORDS)
def test_the_moved_words_live_in_that_page_guide(page: str, words: str) -> None:
    assert words in _guide_text(page)
    assert f'render_page_guide("{page}"' in (ROOT / "app_pages" / f"{page}.py").read_text(
        encoding="utf-8"
    )


def test_a_page_that_had_no_guide_now_opens_one_and_keeps_its_header_bare() -> None:
    """DB 없이 서는 모듈 색인으로 본다 — 머리 설명 줄이 없고 Guide 단추가 그 말을 연다."""
    page = str(ROOT / "app_pages" / "internal_modules.py")
    app = AppTest.from_file(page, default_timeout=60).run()

    assert not app.exception, [element.message for element in app.exception]
    assert not any("동료가 만든" in str(caption.value) for caption in app.caption)
    opened = app.button(key=GUIDE_TRIGGER_KEY).click().run()
    assert not opened.exception, [element.message for element in opened.exception]
    assert any("동료가 만든 화면" in str(item.value) for item in opened.markdown)
