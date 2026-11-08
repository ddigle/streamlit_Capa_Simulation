# Purpose: 화면들이 같이 쓰는 공용 공정 값의 읽기 · 쓰기 규칙(P2 다섯)과 모듈 경계를 고정한다.

"""공용 공정 칸(`shared_process.py` — 2026-11-08 사용자 답 P1 · P2).

- 값은 원본 공정명이고, 화면은 그 화면 목록 안 것만 읽는다. 없는 공정은 지우지 않는다.
- HOME 은 보내기만(`publish_from_home`), 여러 개 따라감 화면의 「적용」 은 이 화면에 없는 값을
  남긴다. 둘 다 모두 켜면 그 화면 몫은 전체다.
- 하나 고름 화면은 받기만 — 값이 바뀐 뒤 처음이고 하나일 때만 따라 열고, 들어온 길이 이긴다.
- 사용자 메모(모니터링 · 원복 검토)에 맞춰 세션 키는 이 모듈 밖에서 만지지 않는다.

세션은 AppTest 한 벌로 가둔다 — 스크립트가 세션의 `ops` 차례대로 공개 함수를 부르고 결과를 쌓는다.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from streamlit.testing.v1 import AppTest

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _runner() -> None:
    import streamlit as st

    from capa_simulation import shared_process

    results = st.session_state.setdefault("results", [])
    for name, args, kwargs in st.session_state.pop("ops", []):
        results.append(getattr(shared_process, name)(*args, **kwargs))


def _app() -> AppTest:
    return AppTest.from_function(_runner).run()


def _call(app: AppTest, *ops: tuple[str, tuple[Any, ...], dict[str, Any]]) -> list[Any]:
    app.session_state["results"] = []
    app.session_state["ops"] = list(ops)
    app.run()
    assert not app.exception, [item.message for item in app.exception]
    return list(app.session_state["results"])


def op(name: str, *args: Any, **kwargs: Any) -> tuple[str, tuple[Any, ...], dict[str, Any]]:
    return (name, args, kwargs)


def test_publish_keeps_original_names_in_order_and_bumps_the_version_only_on_change() -> None:
    app = _app()
    out = _call(
        app,
        op("publish", [" Mold ", "Underfill", "Mold", "", None], "HOME"),
        op("values"),
        op("origin"),
        op("version"),
        op("publish", ["Mold", "Underfill"], "HOME"),
        op("version"),
        op("publish", ["Mold", "Underfill"], "기준 정보"),
        op("origin"),
        op("version"),
    )
    assert out[1] == ("Mold", "Underfill")
    assert out[2] == "HOME"
    assert out[3] == 1
    # 같은 화면이 같은 값을 다시 적으면 판이 오르지 않는다 — 하나 고름 화면이 다시 따라 열지 않는다.
    assert out[5] == 1
    assert (out[7], out[8]) == ("기준 정보", 2)


def test_clear_empties_the_value_and_its_origin() -> None:
    app = _app()
    out = _call(
        app, op("publish", ["Mold"], "HOME"), op("clear"), op("values"), op("origin"), op("clear")
    )
    assert out[2:4] == [(), ""]
    assert _call(app, op("version")) == [2]


def test_home_sends_only_what_it_narrowed_and_clears_when_everything_is_on() -> None:
    """P2-1 — HOME 「선택 공정 적용」 은 이번 선택지 안에서 켠 공정만 복사한다. 모두 켰으면
    지운다."""
    app = _app()
    options = ["WF", "Mold", "Underfill"]
    out = _call(
        app,
        op("publish_from_home", ["Underfill", "Mold", "Hidden"], options),
        op("values"),
        op("origin"),
        op("publish_from_home", options, options),
        op("values"),
    )
    assert out[1] == ("Mold", "Underfill")
    assert out[2] == "HOME"
    assert out[4] == ()


def test_a_screen_reads_only_its_own_processes_and_keeps_the_others() -> None:
    app = _app()
    out = _call(
        app,
        op("publish", ["HB 접합", "Mold", "Underfill"], "HOME"),
        op("applied", ["Underfill", "Mold", "WF"]),
        op("missing", ["Underfill", "Mold", "WF"]),
        op("applied", ["WF"]),
        op("values"),
    )
    # 차례는 화면 목록 차례 · 없는 것은 고른 차례.
    assert out[1] == ["Underfill", "Mold"]
    assert out[2] == ["HB 접합"]
    # 걸리는 것이 없으면 빈 목록(= 전체) — 빈 화면을 만들지 않고 값도 지우지 않는다.
    assert out[3] == []
    assert out[4] == ("HB 접합", "Mold", "Underfill")


def test_applying_on_a_screen_keeps_the_values_that_screen_could_not_touch() -> None:
    app = _app()
    out = _call(
        app,
        op("publish", ["HB 접합", "Mold"], "HOME"),
        op("apply_from_screen", ["Underfill", "Ghost"], ["Underfill", "Mold"], "가용설비"),
        op("values"),
        op("origin"),
        op("apply_from_screen", [], ["Underfill", "Mold"], "가용설비"),
        op("values"),
    )
    assert out[2] == ("Underfill", "HB 접합")
    assert out[3] == "가용설비"
    assert out[5] == ("HB 접합",)


def test_turning_every_process_on_a_screen_is_the_same_as_choosing_none() -> None:
    """모두 켜고 「적용」 하면 이 화면 몫은 전체다 — HOME 「적용」 처럼 모두 켠 목록을 값으로 남기지
    않는다(남으면 리비전을 바꿔 새로 들어온 공정이 따라가는 화면마다 걸러진다). 이 화면에 없는 값은
    그대로 남는다."""
    app = _app()
    options = ["WF", "Mold", "Underfill"]
    out = _call(
        app,
        op("publish", ["Mold"], "HOME"),
        op("apply_from_screen", ["Underfill", "WF", "Mold"], options, "산출 결과"),
        op("values"),
        op("origin"),
        op("publish", ["HB 접합", "Mold"], "HOME"),
        op("apply_from_screen", options, options, "산출 결과"),
        op("values"),
        op("applied", options),
    )
    assert out[2:4] == [(), ""]
    assert out[6] == ("HB 접합",)
    assert out[7] == []


def test_the_origin_is_named_only_on_other_screens() -> None:
    app = _app()
    out = _call(
        app,
        op("origin_for", "산출 결과"),
        op("publish", ["Mold"], "HOME"),
        op("origin_for", "산출 결과"),
        op("origin_for", "HOME"),
    )
    assert out[0] is None
    assert out[2] == "HOME"
    assert out[3] is None


def test_a_single_screen_follows_once_and_only_when_the_value_is_one_process() -> None:
    """P2-2 — 값이 바뀐 뒤 처음 그리는 회차에 공용 값이 하나이고 목록에 있으면 그 공정을 연다.
    값이 여럿이면(이 화면에 걸리는 것이 하나뿐이어도) 보던 공정을 둔다."""
    app = _app()
    options = ["WF", "Mold", "Underfill"]
    out = _call(
        app,
        op("follow_single", "공정 Capa 상세", options, entered=False),
        op("publish", ["Mold", "HB 접합"], "HOME"),
        op("follow_single", "공정 Capa 상세", options, entered=False),
        op("publish", ["Mold"], "HOME"),
        op("follow_single", "공정 Capa 상세", options, entered=False),
        op("follow_single", "공정 Capa 상세", options, entered=False),
        op("single_applied", "공정 Capa 상세", "Mold"),
        op("single_applied", "공정 Capa 상세", "WF"),
        op("follow_single", "제약 시뮬레이션", ["Mold"], entered=False),
    )
    assert out[0] is None
    assert out[2] is None
    assert out[4] == "Mold"
    assert out[5] is None
    assert out[6:8] == [True, False]
    # 화면마다 따로 본다.
    assert out[8] == "Mold"


def test_a_single_value_missing_from_the_list_opens_once_the_list_brings_it_back() -> None:
    """하나인데 목록에 없으면(리비전을 바꿔 사라진 공정) 본 것으로 치지 않는다 — 돌아오면 그때
    연다."""
    app = _app()
    out = _call(
        app,
        op("publish", ["Mold"], "HOME"),
        op("follow_single", "공정 Capa 상세", ["WF"], entered=False),
        op("follow_single", "공정 Capa 상세", ["WF", "Mold"], entered=False),
    )
    assert out[1:] == [None, "Mold"]


def test_an_entered_route_wins_and_the_value_counts_as_seen() -> None:
    """HOME 그림 칸 · 카드 링크 · 주소로 들어온 회차에는 따르지 않고, 다음 회차에도 덮지 않는다."""
    app = _app()
    out = _call(
        app,
        op("publish", ["Mold"], "HOME"),
        op("follow_single", "공정 Capa 상세", ["WF", "Mold"], entered=True),
        op("follow_single", "공정 Capa 상세", ["WF", "Mold"], entered=False),
        op("single_applied", "공정 Capa 상세", "Mold"),
        op("publish", ["WF"], "산출 결과"),
        op("follow_single", "공정 Capa 상세", ["WF", "Mold"], entered=False),
    )
    assert out[1:4] == [None, None, False]
    assert out[5] == "WF"


def test_a_followed_process_stops_counting_once_the_value_moves_away() -> None:
    app = _app()
    out = _call(
        app,
        op("publish", ["Mold"], "HOME"),
        op("follow_single", "공정 Capa 상세", ["Mold"], entered=False),
        op("single_applied", "공정 Capa 상세", "Mold"),
        op("clear"),
        op("single_applied", "공정 Capa 상세", "Mold"),
        op("single_applied", "공정 Capa 상세", None),
    )
    assert out[1:3] == ["Mold", True]
    assert out[4:6] == [False, False]


def test_drafts_hidden_by_the_shared_value_are_counted() -> None:
    """기준 정보 「거름 밖 n개」 의 셈 — 걸린 값이 없으면 0 이다."""
    app = _app()
    out = _call(
        app,
        op("count_outside", ["Mold", "WF"], ["Mold", "WF"]),
        op("publish", ["Mold"], "HOME"),
        op("count_outside", ["Mold", "WF", "Underfill", "WF"], ["Mold", "WF", "Underfill"]),
        op("count_outside", ["WF"], ["WF"]),
    )
    assert out[0] == 0
    assert out[2] == 2
    assert out[3] == 0


def test_only_the_shared_process_module_touches_its_session_keys() -> None:
    """되돌릴 때 이 모듈과 부르는 줄만 걷게 — 화면 · 부품 소스에 공용 값의 세션 키 글자가 없다."""
    pattern = re.compile(r"shared_process_(values|origin|version|seen|followed)")
    sources = [
        *PROJECT_ROOT.joinpath("src").rglob("*.py"),
        *PROJECT_ROOT.joinpath("app_pages").rglob("*.py"),
        PROJECT_ROOT / "app.py",
    ]
    offenders = [
        path.relative_to(PROJECT_ROOT).as_posix()
        for path in sources
        if path.name != "shared_process.py" and pattern.search(path.read_text(encoding="utf-8"))
    ]
    assert offenders == []
