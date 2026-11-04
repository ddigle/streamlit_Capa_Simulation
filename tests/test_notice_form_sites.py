# Purpose: 토스트 · 초록 결과 상자를 직접 그리는 자리(st.toast · st.success)를 허용 목록과 맞댄다.

"""알림 꼴 그물(설계 규칙 UI-NTF-01 · 03 — `docs/design_rules.md` 5-1).

앱의 알림은 오른쪽 아래 알림창 한 꼴 · 한 길이다(UI-NTF-01). 동작 결과(저장 · 적용 · 불러옴 · 발행 ·
삭제)는 `flash.queue_flash` 로 알림창에만 내고(UI-NTF-03 — 성공은 버튼 곁에 그리지 않는다), 목록
구획의 빈 결과 · 점검 결론은 평문 한 줄(`st.caption`)이다(AMB-02 (가) — 초록 상자를 쓰지 않는다).
그래서 화면 코드(`app.py` · `app_pages/` · `src/capa_simulation/`, 알림의 한 길인 `flash.py` ·
`alerts.py` 밖)에서 Streamlit 토스트(`st.toast(`)와 초록 결과 상자(`st.success(` · 칸`.success(`)를
직접 부르는 자리를 (파일, 맨 바깥 함수) 마다 세어 허용 목록과 **정확히** 맞댄다.

- 토스트 자리는 없다(`ALLOWED_TOASTS` 는 비어 있다 — 필요 단축 일정 기준선 결과가 마지막이었다).
- 초록 상자 자리는 모두 미정리다 — 값 줄 · 점검 결론 · 빈 결과를 초록 상자로 그린 기존 자리라
  다음 판에 평문 한 줄(`st.caption`)이나 값 줄로 바꿔 이 목록을 줄인다. 새 자리는 들이지 않는다
  (`ALLOWED_SUCCESS` 의 까닭은 미정리 하나뿐이다).
- 새 자리가 생기면 실패한다 — 동작 결과면 `queue_flash`, 빈 결과 · 점검 결론이면 `st.caption`,
  값이면 「**라벨** · 값」 줄로 그린다.
- 자리가 줄면 실패한다 — 목록의 그 칸도 줄인다.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from source_sites import (
    LOGGERS,
    PROJECT_ROOT,
    UNSETTLED,
    method,
    receiver,
    screen_calls,
    screen_files,
)

# 알림의 한 길 — 버튼 곁 결과 알림이 거부 · 실패를 그 칸에 그린다(`flash._draw`).
OWNERS = ("src/capa_simulation/components/flash.py", "src/capa_simulation/alerts.py")

ALLOWED_TOASTS: dict[tuple[str, str], tuple[str, ...]] = {}
# (파일, 맨 바깥 함수) → 초록 상자 부름마다 까닭(문서 차례).
ALLOWED_SUCCESS: dict[tuple[str, str], tuple[str, ...]] = {
    # 「저장된 도면: … · 캔버스 …」 — Space 도면 팝업의 지금 값(Space 화면 갈래가 맡아 다음 판에 값
    # 줄로 옮긴다).
    ("src/capa_simulation/components/floor_layout_upload.py", "_render_current_state"): (
        UNSETTLED,
    ),
}


def direct_calls(
    name: str, paths: list[Path] | None = None, root: Path = PROJECT_ROOT
) -> dict[tuple[str, str], list[int]]:
    """(파일, 맨 바깥 함수) 마다 `.{name}(` 부름의 줄 번호(로거 · `OWNERS` 밖)."""
    found: dict[tuple[str, str], list[int]] = {}
    files = paths or screen_files(exclude=OWNERS)
    for relative, outer, _path, _scope, call in screen_calls(files, root):
        if method(call) == name and receiver(call) not in LOGGERS:
            found.setdefault((relative, outer), []).append(call.lineno)
    return found


def _listing(sites: Mapping[tuple[str, str], object]) -> str:
    return "\n".join(f"{file} {func or '(본문)'}: {value}" for (file, func), value in sites.items())


def _mismatch(
    found: dict[tuple[str, str], list[int]], allowed: dict[tuple[str, str], tuple[str, ...]]
) -> dict[tuple[str, str], tuple[int, int]]:
    return {
        site: (len(allowed.get(site, ())), len(found.get(site, [])))
        for site in {*found, *allowed}
        if len(found.get(site, [])) != len(allowed.get(site, ()))
    }


def test_no_place_draws_a_toast() -> None:
    """토스트는 알림창이 아닌 다른 꼴이다 — 결과는 `queue_flash` 로 낸다."""
    stale = _mismatch(direct_calls("toast"), ALLOWED_TOASTS)
    assert not stale, (
        "st.toast 자리가 허용 목록과 다릅니다(목록 수, 지금 수) — 동작 결과는"
        " flash.queue_flash 로 알림창 · Alarm 에 냅니다:\n" + _listing(stale)
    )


def test_success_boxes_match_the_list() -> None:
    """새 초록 상자 자리는 들이지 않고, 옮긴 자리는 목록에서 지운다."""
    stale = _mismatch(direct_calls("success"), ALLOWED_SUCCESS)
    assert not stale, (
        "초록 결과 상자(st.success) 자리가 허용 목록과 다릅니다(목록 수, 지금 수) — 동작 결과는"
        " flash.queue_flash, 빈 결과 · 점검 결론은 st.caption 평문 한 줄, 값은 「**라벨** · 값」"
        " 줄로 그리고, 옮겼으면 tests/test_notice_form_sites.py 목록도 줄이세요:\n"
        + _listing(stale)
    )


def test_remaining_success_boxes_are_all_unsettled() -> None:
    """초록 상자로 자리에 남을 까닭은 없다 — 남은 자리는 모두 다음 판에 줄일 미정리다."""
    assert all(reasons and set(reasons) == {UNSETTLED} for reasons in ALLOWED_SUCCESS.values())
    assert not ALLOWED_TOASTS


SAMPLE_PAGE = """
import logging

import streamlit as st

logger = logging.getLogger(__name__)


def render(slot) -> None:
    st.toast("저장했습니다.")
    st.success("저장했습니다.")
    slot.success("반영했습니다.")
    st.sidebar.success("불러왔습니다.")
    st.caption("저장했습니다.")
    logger.success("남김")
"""


def test_the_net_counts_toasts_and_success_boxes_on_any_container(tmp_path: Path) -> None:
    page = tmp_path / "page.py"
    page.write_text(SAMPLE_PAGE, encoding="utf-8")

    assert {
        site: len(lines) for site, lines in direct_calls("toast", [page], tmp_path).items()
    } == {("page.py", "render"): 1}
    assert {
        site: len(lines) for site, lines in direct_calls("success", [page], tmp_path).items()
    } == {("page.py", "render"): 3}
