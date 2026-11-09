# Purpose: 공용 공정 값 칸 · 팝업 판 · 머리 칩 · 탭 표지 data · 판 트리거 · 판 JS 를 고정한다.

"""공용 공정 칸의 화면 조각(`components/process_field.py` — 2026-11-08 사용자 답 P1 · P2-5).

- 값 칸 글자 — 「전체 N공정」 · 하나면 이름 · 둘부터 한 줄 「Mold 외 n개」(풍선이 전체 목록 —
  2026-11-09 사용자 검수 g03-2). 다른 화면에서 온 값은 이름 줄에 「HOME 에서」. 이 화면에 없는 값은
  값 칸 아이콘만 바뀌고 이름 줄 배지는 없다(2026-11-09 보드 P1-6 — 이름은 머리 칩 · 탭 표지가
  말한다).
- 본문 위 칩은 없다(2026-11-09 보드 C1 (라)) — 값 칸을 그린 회차에 표지(`MARKER_ATTRIBUTE`)를 남겨
  머리 띠 칩 · 지금 탭 표지가 바로잡는다. 표지 · 머리 칩 · 탭 표지 data 는 값이 그대로면 같다.
- 팝업 본문 — 여러 개 고름 「적용」 은 이 화면에 없는 값을 남기고, 「전체」 는 지우고, 하나 고름은
  그 화면의 공정 칸을 바꾸고 공용 값을 그 하나로 보낸다(2026-11-09 보드 C2 (가)).
- 판의 트리거는 `apply` 하나다 — 결과 객체가 dict 라 `clear` 같은 이름은 `dict.clear` 와 겹쳐 연
  회차에 「전체」 가 눌린 것으로 읽혔다(2026-11-08 사본 앱 — 팝업이 열리자마자 닫혔다).
- 판 JS 의 판정 구획(`// <process-picker-core>`)은 node 로 돌린다. 브라우저 동작(누름 · 키보드 초점
  · 회차 0)은 사본 앱으로 본다.

Components v2 는 AppTest 에 없다 — 팝업 본문 시험은 판 함수(`render_process_picker_apply`)를 갈아
끼운다.
"""

from __future__ import annotations

import html
import json
import re
from dataclasses import replace
from typing import Any

import pytest
from js_runner import run_js_json
from streamlit.testing.v1 import AppTest

import capa_simulation.components.process_field as process_field
from capa_simulation import shared_process
from capa_simulation.components.process_field import (
    CONTEXT_KEY,
    DIALOG_KEY,
    FIELD_KEY,
    MARKER_ATTRIBUTE,
    PROCESS_FIELD_HTML,
    PROCESS_FIELD_JS,
    PickerResult,
    filter_help,
    filter_value,
    first_and_rest,
    origin_status,
)

OPTIONS = ["WF", "Mold", "Underfill"]


def share(app: AppTest, values: list[str], origin: str = shared_process.HOME) -> None:
    """공용 값을 세션에 직접 둔다(시험 몫 — 화면은 공개 함수만 부른다)."""
    app.session_state[shared_process._VALUES_KEY] = values
    app.session_state[shared_process._ORIGIN_KEY] = origin
    version = app.session_state[shared_process._VERSION_KEY] if _has_version(app) else 0
    app.session_state[shared_process._VERSION_KEY] = int(version) + 1


def _has_version(app: AppTest) -> bool:
    try:
        app.session_state[shared_process._VERSION_KEY]
    except KeyError:
        return False
    return True


def shared_values(app: AppTest) -> list[str]:
    try:
        return list(app.session_state[shared_process._VALUES_KEY])
    except KeyError:
        return []


# ------------------------------------------------------------------ 글자 · 표지


def test_the_field_value_reads_one_line_first_name_and_the_rest() -> None:
    """고른 값은 한 줄 「<첫 공정> 외 n개」 다(2026-11-09 사용자 검수 g03-2 — 「선택」 은 붙이지
    않는다, 칸 이름이 「공정」). 첫 공정은 걸린 차례(선택지 차례 — 표시순서)의 첫 이름이고, 둘
    이상이면 풍선이 전체 목록이다."""
    text = str
    assert filter_value([], OPTIONS, text) == "전체 3공정"
    assert filter_value([], OPTIONS, text, empty="공정을 선택하세요") == "공정을 선택하세요"
    assert filter_value(["Mold"], OPTIONS, text) == "Mold"
    assert filter_value(["WF", "Mold"], OPTIONS, text) == "WF 외 1개"
    assert filter_value(OPTIONS, [*OPTIONS, "AVI"], text) == "WF 외 2개"
    assert filter_value([], [], text) == "고를 공정 없음"
    assert filter_help(["Mold"], text) is None
    assert filter_help([], text) is None
    assert filter_help(["WF", "Mold", "Underfill"], text) == "WF · Mold · Underfill"
    assert first_and_rest([]) == ""
    assert first_and_rest(["Wafer Saw", "Pre B/D", "DAF Attach"]) == "Wafer Saw 외 2개"
    # 값 칸은 마크다운이다 — 물결표 이름이 지움선이 되지 않는다.
    assert filter_value(["A~B~C"], ["A~B~C"], text) == "A\\~B\\~C"
    assert filter_value(["A~B", "C"], ["A~B", "C"], text) == "A\\~B 외 1개"


def test_the_name_row_carries_only_the_origin_and_no_missing_badge() -> None:
    """이름 줄 오른쪽은 출처 글 하나다 — 없는 공정 배지를 두지 않는다(2026-11-09 보드 P1-6 — 「HB
    접합 없음」 은 뜻이 읽히지 않았다). 없는 공정은 머리 칩 「n개 이 화면 없음」 · 판 「이 화면에
    없음」 · 탭 풍선 「PMC 는 이 화면에 없음」 이 풀어 쓴다."""
    assert origin_status(None) is None
    assert origin_status("HOME") == "HOME 에서"
    assert not hasattr(process_field, "missing_badge")
    assert not hasattr(process_field, "MISSING_BADGE")
    source = process_field.__file__
    assert "orange-badge" not in open(source, encoding="utf-8").read()


def _filter_script() -> None:
    import streamlit as st

    from capa_simulation.components import process_field
    from capa_simulation.components.process_labels import ProcessLabels
    from capa_simulation.sidebar_status import begin_app_run

    run = begin_app_run()
    labels = ProcessLabels(labels=st.session_state.get("test_labels", {}))
    chosen = process_field.render_process_filter(
        st.session_state.get("test_options", ["WF", "Mold", "Underfill"]),
        screen=st.session_state.get("test_screen", "산출 결과"),
        labels=labels,
    )
    if st.session_state.get("test_twice"):
        process_field.render_process_filter(["WF"], screen="산출 결과")
    st.session_state["test_chosen"] = chosen
    run.finish()


def _field(app: AppTest) -> Any:
    return app.sidebar.button(key=FIELD_KEY)


def _captions(app: AppTest) -> list[str]:
    return [str(item.value) for item in app.sidebar.caption]


def process_marks(app: AppTest) -> list[dict[str, Any]]:
    """이 회차에 그린 공정 값 칸 표지(문서 차례)."""
    marks = []
    for element in app._tree.get("html"):
        body = getattr(getattr(element, "proto", None), "body", "")
        for found in re.finditer(rf'{MARKER_ATTRIBUTE}="([^"]*)"', str(body)):
            marks.append(json.loads(html.unescape(found.group(1))))
    return marks


def _no_body_chip(app: AppTest) -> None:
    """본문 위 칩(옛 `shared_process_chip`)이 없다."""
    assert not [
        button for button in app.button if str(button.key).startswith("shared_process_chip")
    ]


def test_without_a_shared_value_the_field_reads_all_and_nothing_is_marked() -> None:
    app = AppTest.from_function(_filter_script).run()

    assert not app.exception
    assert _field(app).label == "전체 3공정"
    assert app.session_state["test_chosen"] == []
    _no_body_chip(app)
    assert _captions(app) == ["공정"]
    (mark,) = process_marks(app)
    assert mark["here"] is None and mark["tab"] is None


def test_a_shared_value_from_another_screen_narrows_marks_and_names_its_origin() -> None:
    app = AppTest.from_function(_filter_script)
    app.session_state["test_labels"] = {"Mold": "몰드"}
    app.run()
    share(app, ["Underfill", "Mold"])
    app.run()

    assert not app.exception
    assert app.session_state["test_chosen"] == ["Mold", "Underfill"]
    assert _field(app).label == "몰드 외 1개"
    assert _field(app).help == "몰드 · Underfill"
    assert _captions(app) == ["공정", "HOME 에서"]
    _no_body_chip(app)
    (mark,) = process_marks(app)
    # 걸린 공정은 이 화면 선택지 차례다 — 머리 칩이 이 차례로 첫 이름을 적는다(값 칸과 같다).
    assert mark["here"] == {
        "on": True,
        "follows": True,
        "inside": ["Mold", "Underfill"],
        "missing": [],
    }
    assert mark["tab"]["miss"] is False


def test_a_value_chosen_on_this_screen_carries_no_origin() -> None:
    app = AppTest.from_function(_filter_script).run()
    share(app, ["Mold"], origin="산출 결과")
    app.run()

    assert _captions(app) == ["공정"]
    _no_body_chip(app)


def test_a_process_this_screen_lacks_shows_everything_and_the_mark_names_it() -> None:
    """사내는 설비 쪽 공정 이름이 달라 자주 뜬다 — 값은 지우지 않고 전체를 보인다. 이름 줄에는
    배지를 달지 않고(P1-6) 표지가 없는 공정을 실어 머리 칩 「1개 이 화면 없음」 · 탭 표지 주황이
    말한다."""
    app = AppTest.from_function(_filter_script).run()
    share(app, ["Mold", "HB 접합"])
    app.run()

    assert app.session_state["test_chosen"] == ["Mold"]
    assert _captions(app) == ["공정", "HOME 에서"]
    (mark,) = process_marks(app)
    assert mark["here"] == {
        "on": True,
        "follows": True,
        "inside": ["Mold"],
        "missing": ["HB 접합"],
    }
    assert mark["tab"] == {
        "miss": True,
        "title": "공정 Mold — HOME 에서\nHB 접합 은 이 화면에 없음",
    }

    share(app, ["HB 접합"])
    app.run()
    assert app.session_state["test_chosen"] == []
    assert _field(app).label == "전체 3공정"
    assert _captions(app) == ["공정"]
    (mark,) = process_marks(app)
    assert mark["here"] == {"on": False, "follows": True, "inside": [], "missing": ["HB 접합"]}
    assert mark["tab"]["title"] == "공정 1개 — HOME 에서\nHB 접합 은 이 화면에 없음"
    assert shared_values(app) == ["HB 접합"]


def test_the_mark_is_the_same_while_the_value_stays() -> None:
    """표지 · 머리 칩 data 는 값이 그대로면 회차마다 같다(시각 · 카운터 없음) — JS 가 다시 불리지
    않는다."""
    app = AppTest.from_function(_filter_script).run()
    share(app, ["Mold"])
    app.run()
    first = process_marks(app)
    app.run()
    assert process_marks(app) == first


def test_the_field_is_drawn_once_per_run() -> None:
    """같은 전체 회차에 두 번 불러도 값 칸은 하나다(같은 key 의 위젯이 둘이면 멈춘다)."""
    app = AppTest.from_function(_filter_script)
    app.session_state["test_twice"] = True
    app.run()

    assert not app.exception
    assert [button.key for button in app.sidebar.button].count(FIELD_KEY) == 1


def test_the_picker_remembers_this_screens_options_and_visible_texts() -> None:
    app = AppTest.from_function(_filter_script)
    app.session_state["test_labels"] = {"WF": "Mold"}
    app.run()

    context = app.session_state[CONTEXT_KEY]
    assert context.mode == process_field.MULTI
    assert context.screen == "산출 결과"
    assert context.options == ("WF", "Mold", "Underfill")
    # 표시명이 다른 공정의 원본과 겹치면 「표시명 (원본)」 으로 가른다.
    assert context.texts == ("Mold (WF)", "Mold", "Underfill")


# ------------------------------------------------------------------ 팝업 본문


def _dialog_script() -> None:
    import streamlit as st

    from capa_simulation.components import process_field
    from capa_simulation.sidebar_status import begin_app_run

    run = begin_app_run()
    if st.session_state.get("test_no_field"):
        pass
    elif st.session_state.get("test_single"):
        st.session_state.setdefault("test_detail_process", "WF")
        process_field.render_process_choice(
            ["WF", "Mold", "Underfill"], screen="공정 Capa 상세", key="test_detail_process"
        )
    else:
        process_field.render_process_filter(["WF", "Mold", "Underfill"], screen="가용설비")
    if st.session_state.get("test_body"):
        process_field.render_process_dialog_body()
    run.finish()


@pytest.fixture
def picker(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """판 대역 — 다음 회차에 돌려줄 결과(`result`)와 받은 인자(`calls`)."""
    box: dict[str, Any] = {"result": None, "calls": []}

    def fake(**kwargs: Any) -> PickerResult | None:
        box["calls"].append(kwargs)
        result, box["result"] = box["result"], None
        assert result is None or isinstance(result, PickerResult)
        return result

    monkeypatch.setattr(process_field, "render_process_picker_apply", fake)
    return box


def _open_body(app: AppTest) -> None:
    app.session_state[DIALOG_KEY] = True
    app.session_state["test_body"] = True


def test_applying_on_a_screen_keeps_values_it_lacks_and_closes(picker: dict[str, Any]) -> None:
    app = AppTest.from_function(_dialog_script).run()
    share(app, ["HB 접합", "Mold"])
    _open_body(app)
    app.run()
    assert picker["calls"][-1]["selected"] == ("Mold",)
    assert picker["calls"][-1]["has_shared"] is True

    picker["result"] = PickerResult(values=("WF", "Underfill"))
    app.run()

    assert not app.exception
    assert shared_values(app) == ["WF", "Underfill", "HB 접합"]
    assert app.session_state[shared_process._ORIGIN_KEY] == "가용설비"
    assert DIALOG_KEY not in app.session_state


def test_the_all_button_clears_every_value(picker: dict[str, Any]) -> None:
    app = AppTest.from_function(_dialog_script).run()
    share(app, ["HB 접합", "Mold"])
    _open_body(app)
    app.run()
    picker["result"] = PickerResult(clear=True)
    app.run()

    assert shared_values(app) == []
    assert DIALOG_KEY not in app.session_state


def test_a_single_screen_sends_the_process_picked_in_its_field(picker: dict[str, Any]) -> None:
    """2026-11-09 보드 C2 (가) — 공정 하나만 보는 화면도 사이드바 공정 칸에서 사용자가 직접 고른
    공정은 공용 값을 그 하나로 바꾼다(출처 = 그 화면). 그 화면은 같은 공정을 다시 「따라 열지」 않고
    값 칸이 강조된다(출처 글은 자기 화면이라 없다)."""
    app = AppTest.from_function(_dialog_script)
    app.session_state["test_single"] = True
    app.run()
    share(app, ["Mold", "Underfill"])
    _open_body(app)
    app.run()
    assert picker["calls"][-1]["mode"] == process_field.SINGLE
    assert picker["calls"][-1]["selected"] == ("WF",)

    picker["result"] = PickerResult(values=("Underfill",))
    app.run()

    assert not app.exception
    assert app.session_state["test_detail_process"] == "Underfill"
    assert shared_values(app) == ["Underfill"]
    assert app.session_state[shared_process._ORIGIN_KEY] == "공정 Capa 상세"
    assert DIALOG_KEY not in app.session_state

    app.session_state["test_body"] = False
    app.run()
    assert app.session_state[shared_process._FOLLOWED_KEY] == {"공정 Capa 상세": "Underfill"}
    assert app.session_state[shared_process._SEEN_KEY] == {
        "공정 Capa 상세": app.session_state[shared_process._VERSION_KEY]
    }
    assert _captions(app) == ["공정"]
    (mark,) = process_marks(app)
    assert mark["here"] == {"on": True, "follows": True, "inside": ["Underfill"], "missing": []}


def test_a_dialog_on_another_page_has_nothing_to_pick(picker: dict[str, Any]) -> None:
    """팝업은 지금 페이지가 적은 선택지만 쓴다 — 다른 페이지의 선택지로 판을 세우지 않는다."""
    app = AppTest.from_function(_dialog_script).run()
    context = app.session_state[CONTEXT_KEY]
    app.session_state[CONTEXT_KEY] = replace(context, page="다른 페이지")
    app.session_state["test_no_field"] = True
    _open_body(app)
    app.run()

    assert not app.exception
    assert picker["calls"] == []
    assert "고를 공정 없음" in [str(item.value) for item in app.caption]


# ------------------------------------------------------------------ 판 트리거 해석


class _Result(dict[str, Any]):
    """Components v2 결과처럼 속성으로도 읽히는 dict — `clear` 는 dict 의 메서드다."""

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc


def _parse(monkeypatch: pytest.MonkeyPatch, result: _Result, mode: str = "multi") -> Any:
    monkeypatch.setattr(process_field, "_PROCESS_PICKER", lambda **_kwargs: result)
    return process_field.render_process_picker_apply(
        mode=mode,
        options=OPTIONS,
        texts=OPTIONS,
        selected=(),
        has_shared=False,
        key="test_picker",
    )


def test_a_mounted_picker_without_a_trigger_returns_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """결과 dict 의 `clear` 메서드를 「전체」 로 읽지 않는다 — 연 회차에 팝업이 닫히던 결함."""
    assert _parse(monkeypatch, _Result()) is None
    assert _parse(monkeypatch, _Result(apply=None)) is None


def test_the_apply_trigger_keeps_known_values_in_option_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    out = _parse(monkeypatch, _Result(apply={"values": ["Underfill", "Ghost", "WF"]}))
    assert out == PickerResult(values=("WF", "Underfill"))
    assert _parse(monkeypatch, _Result(apply={"clear": True})) == PickerResult(clear=True)
    assert _parse(monkeypatch, _Result(apply={"values": "WF"})) is None
    single = _Result(apply={"values": ["WF", "Mold"]})
    assert _parse(monkeypatch, single, mode="single") is None
    assert _parse(monkeypatch, _Result(apply={"values": ["Mold"]}), mode="single") == PickerResult(
        values=("Mold",)
    )


def test_the_picker_sends_a_single_trigger_name() -> None:
    names = set(re.findall(r"setTriggerValue\('([a-z_]+)'", PROCESS_FIELD_JS))
    assert names == {"apply"}
    for part in ("capa-proc-search", "capa-proc-apply", "capa-proc-all", "capa-proc-grid"):
        assert part in PROCESS_FIELD_HTML


def test_apply_sits_right_before_the_tiles_in_tab_order() -> None:
    """Tab 차례는 찾기 → 「전체」 → 「적용」 → 판이다. 판에서 Shift+Tab 한 번이 「적용」 이라,
    공용 값이 있을 때 그 자리 Enter 가 「전체」(모든 화면의 공정 거름 지움)가 되지 않는다."""
    spots = [
        PROCESS_FIELD_HTML.index(f'class="{name}"')
        for name in ("capa-proc-search", "capa-proc-all", "capa-proc-apply", "capa-proc-grid")
    ]
    assert spots == sorted(spots)
    between = PROCESS_FIELD_HTML[spots[2] : spots[3]]
    assert "<button" not in between.split("</button>", 1)[1]
    assert "<input" not in between
    assert "tabindex" not in PROCESS_FIELD_HTML.lower()


# ------------------------------------------------------------------ 판 JS 구획


def _node(runner: str) -> Any:
    match = re.search(
        r"// <process-picker-core>\n(?P<body>.*?)\n// </process-picker-core>",
        PROCESS_FIELD_JS,
        re.S,
    )
    assert match, "process_field.js 에 // <process-picker-core> 구획이 없습니다"
    return run_js_json(match.group("body") + "\n" + runner, what="공정 판 JS 구획 시험")


def test_toggling_keeps_option_order_and_the_apply_state_follows_the_draft() -> None:
    out = _node(
        """
const order = ['WF', 'Mold', 'Underfill']
const one = toggleDraft([], 'Underfill', order)
const two = toggleDraft(one, 'WF', order)
const back = toggleDraft(two, 'Underfill', order)
process.stdout.write(JSON.stringify({
  one, two, back,
  same: applyState('multi', ['Mold', 'WF'], ['WF', 'Mold'], 3),
  ready: applyState('multi', ['WF'], ['WF', 'Mold'], 3),
  single: applyState('single', [], ['WF'], 3),
  allIsNone: applyState('multi', order, [], 3),
  allClearsOne: applyState('multi', order, ['Mold'], 3),
  allStaysAll: applyState('multi', order, ['Underfill', 'Mold', 'WF'], 3),
  noneOfAll: applyState('multi', [], order, 3),
  multiCount: countLabel('multi', 2, 24),
  singleCount: countLabel('single', 0, 24),
}))
"""
    )
    assert out["one"] == ["Underfill"]
    assert out["two"] == ["WF", "Underfill"]
    assert out["back"] == ["WF"]
    assert (out["same"], out["ready"], out["single"]) == ("same", "ready", "none")
    # 모두 켠 초안은 고르지 않은 것(이 화면 몫은 전체)과 같다 — 서버 `apply_from_screen` 과 같다.
    assert (out["allIsNone"], out["allClearsOne"]) == ("same", "ready")
    assert (out["allStaysAll"], out["noneOfAll"]) == ("same", "same")
    assert (out["multiCount"], out["singleCount"]) == ("선택 2 / 24", "24개 공정")


def test_searching_matches_the_visible_text_or_the_original_name() -> None:
    out = _node(
        """
const option = { value: 'Pre B/D', label: '선다이싱' }
process.stdout.write(JSON.stringify([
  matchesNeedle(option, ''), matchesNeedle(option, ' pre '), matchesNeedle(option, '다이싱'),
  matchesNeedle(option, 'mold'),
]))
"""
    )
    assert out == [True, True, True, False]


def test_arrow_keys_move_within_the_visible_tiles_and_stop_at_the_ends() -> None:
    out = _node(
        """
process.stdout.write(JSON.stringify([
  stepIndex(0, 'ArrowLeft', 10, 4), stepIndex(1, 'ArrowRight', 10, 4),
  stepIndex(1, 'ArrowDown', 10, 4), stepIndex(9, 'ArrowDown', 10, 4),
  stepIndex(5, 'ArrowUp', 10, 4), stepIndex(5, 'Home', 10, 4), stepIndex(5, 'End', 10, 4),
  stepIndex(5, 'Enter', 10, 4), stepIndex(0, 'ArrowRight', 0, 4),
]))
"""
    )
    assert out == [0, 2, 5, 9, 1, 0, 9, None, None]


def test_options_are_cleaned_of_blanks_and_duplicates() -> None:
    out = _node(
        """
process.stdout.write(JSON.stringify(cleanOptions([
  { value: 'WF', label: '웨이퍼' }, { value: '', label: 'x' }, { value: 'WF', label: 'y' },
  { value: 'Mold' }, null,
])))
"""
    )
    assert out == [{"value": "WF", "label": "웨이퍼"}, {"value": "Mold", "label": "Mold"}]
