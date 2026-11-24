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
- 판 JS 의 판정 구획(`// <process-picker-core>`)은 node 로 돌린다. 마운트 함수(`export default` —
  타일 · 「적용」 · 「전체」 누름, 「적용」 잠금, data 셋이 이어지는 자리, 보일 때만 찾기 칸 초점)는
  자산 HTML 로 세운 가짜 DOM 에서 node 로 돌린다. 방향키 초점 옮김 · 회차 0 은 사본 앱으로 본다.

Components v2 는 AppTest 에 없다 — 팝업 본문 시험은 판 함수(`render_process_picker_apply`)를 갈아
끼운다.
"""

from __future__ import annotations

import html
import json
import re
from dataclasses import replace
from pathlib import Path
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
from capa_simulation.components.process_labels import ProcessLabels

OPTIONS = ["WF", "Mold", "Underfill"]
# 시험마다 빈 프로필로 갈아 끼우기 전의 진짜 읽기(DB 파일 판정 시험 몫).
REAL_SHARED_DISPLAY_NAMES = process_field._shared_display_names


@pytest.fixture(autouse=True)
def _no_shared_display_names(monkeypatch: pytest.MonkeyPatch) -> None:
    """머리 칩 · 탭 풍선이 읽는 공용 표시명 프로필(`process_field._shared_display_names`)은 빈
    프로필이다 — 그 읽기가 저장소 DB 를 열지 않게(프로필을 보는 시험은 따로 갈아 끼운다)."""
    monkeypatch.setattr(process_field, "_shared_display_names", ProcessLabels)


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


def test_the_marks_tab_title_reads_this_screens_letters() -> None:
    """값 칸을 그린 회차의 탭 표지(`tab` — 회차 끝에 지금 탭 풍선을 바로잡는다)도 그 화면 글자다
    (2차 보드 Q2-17) — 다른 화면이 보낸 표시명이 있어도 Space 는 원본으로 적는다."""
    app = AppTest.from_function(_filter_script)
    app.session_state["test_screen"] = "Space"
    app.run()
    app.session_state[shared_process._LABELS_KEY] = {"Mold": "몰드"}
    share(app, ["Mold", "HB 접합"], origin="산출 결과")
    app.run()

    assert not app.exception
    assert _field(app).label == "Mold"
    (mark,) = process_marks(app)
    assert mark["tab"]["title"] == "공정 Mold — 산출 결과 에서\nHB 접합 은 이 화면에 없음"


def test_the_mark_is_the_same_while_the_value_stays() -> None:
    """표지 · 머리 칩 data 는 값이 그대로면 회차마다 같다(시각 · 카운터 없음) — JS 가 다시 불리지
    않는다."""
    app = AppTest.from_function(_filter_script).run()
    share(app, ["Mold"])
    app.run()
    first = process_marks(app)
    app.run()
    assert process_marks(app) == first


def _chip_script() -> None:
    import streamlit as st

    from capa_simulation.components import process_field

    st.session_state["chips"] = {
        name: process_field.header_chip(path)
        for name, path in (
            ("space", "app_pages/space_status.py"),
            ("result", "app_pages/calculation_result.py"),
            ("home", None),
        )
    }


def test_the_header_chip_reads_original_names_on_space_and_sent_labels_elsewhere() -> None:
    """머리 칩 · 판의 글자는 그 화면 글자다 — Space(원본 이름으로 그리는 화면)에서는 원본,
    표시명으로 그리는 화면과 따라가지 않는 화면(HOME)은 표시명(2026-11-10 보드 Q-3 — 한 화면 한
    이름). 공용 표시명 프로필이 비었으면(이 시험 — DB 파일이 아직 없음 · 읽지 못함) 보낸 화면이
    실은 글자다. 값(원본)과 차례는 같다."""
    app = AppTest.from_function(_chip_script)
    app.session_state[shared_process._VALUES_KEY] = ["WF", "Mold"]
    app.session_state[shared_process._ORIGIN_KEY] = "산출 결과"
    app.session_state[shared_process._LABELS_KEY] = {"WF": "WF 입고검사", "Mold": "몰드"}
    app.session_state[shared_process._VERSION_KEY] = 1
    app.run()

    assert not app.exception
    chips = app.session_state["chips"]
    assert [chips[name]["values"] for name in ("space", "result", "home")] == [["WF", "Mold"]] * 3
    assert (chips["space"]["labels"], chips["space"]["top"]) == (["WF", "Mold"], "WF 외 1개")
    assert (chips["result"]["labels"], chips["result"]["top"]) == (
        ["WF 입고검사", "몰드"],
        "WF 입고검사 외 1개",
    )
    assert chips["home"]["labels"] == ["WF 입고검사", "몰드"]
    assert chips["space"]["origin"] == chips["result"]["origin"] == "산출 결과"


def test_the_header_chip_reads_the_shared_display_names_before_the_sent_letters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """표시명 화면(산출 결과 — 아직 그리지 않음)과 따라가지 않는 화면(HOME)의 칩 · 판은 지금 공용
    표시명 프로필로 적는다(2차 보드 Q2-18 — 칩 · 판 · 풍선은 늘 그 화면 글자). Space(원본 이름으로
    그리는 화면)에서 고른 값처럼 보낸 글자가 없어도, 보낸 글자가 옛 표시명이어도(같은 세션에 Admin
    Proc Rename 으로 바뀜) 그 화면 표시명이고, 프로필에서 지운 표시명(보낸 글자에만 남음)은
    원본이다. Space 는 원본 그대로다(Q-3)."""
    monkeypatch.setattr(
        process_field,
        "_shared_display_names",
        lambda: ProcessLabels(labels={"WF": "WF 입고검사", "Mold": "새 몰드"}),
    )
    app = AppTest.from_function(_chip_script)
    app.session_state[shared_process._VALUES_KEY] = ["WF", "Mold", "PMC"]
    app.session_state[shared_process._ORIGIN_KEY] = "Space"
    app.session_state[shared_process._LABELS_KEY] = {"Mold": "옛 몰드", "PMC": "피엠씨"}
    app.session_state[shared_process._VERSION_KEY] = 1
    app.run()

    assert not app.exception
    chips = app.session_state["chips"]
    assert (chips["space"]["labels"], chips["space"]["top"]) == (
        ["WF", "Mold", "PMC"],
        "WF 외 2개",
    )
    assert (chips["result"]["labels"], chips["result"]["top"]) == (
        ["WF 입고검사", "새 몰드", "PMC"],
        "WF 입고검사 외 2개",
    )
    assert chips["home"]["labels"] == ["WF 입고검사", "새 몰드", "PMC"]


def test_the_marks_tab_title_on_a_display_screen_reads_its_display_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Space 에서 고른 값(표시명 없음)이 걸린 표시명 화면의 회차 표지 탭 풍선도 그 화면 표시명이다
    — 값 칸 글자와 같다(2차 보드 Q2-18)."""
    monkeypatch.setattr(
        process_field,
        "_shared_display_names",
        lambda: ProcessLabels(labels={"WF": "WF 입고검사"}),
    )
    app = AppTest.from_function(_filter_script)
    app.session_state["test_labels"] = {"WF": "WF 입고검사"}
    app.run()
    share(app, ["WF", "Mold"], origin="Space")
    app.run()

    assert not app.exception
    assert _field(app).label == "WF 입고검사 외 1개"
    (mark,) = process_marks(app)
    assert mark["tab"]["title"] == "공정 WF 입고검사 · Mold — Space 에서"


def _drawn_chip_script() -> None:
    """앱 차례 — 머리 칩(알림 칸)을 페이지보다 먼저 만들고, 그 뒤 페이지가 값 칸을 그린다."""
    import streamlit as st

    from capa_simulation.components import process_field
    from capa_simulation.components.process_labels import ProcessLabels
    from capa_simulation.sidebar_status import begin_app_run

    run = begin_app_run()
    st.session_state["chip"] = process_field.header_chip("app_pages/calculation_result.py")
    st.session_state["home_chip"] = process_field.header_chip(None)
    process_field.render_process_filter(
        st.session_state.get("test_options", ["WF", "Mold", "Underfill"]),
        screen="산출 결과",
        labels=ProcessLabels(labels=st.session_state.get("test_labels", {})),
    )
    run.finish()


def _profile(monkeypatch: pytest.MonkeyPatch, app: AppTest, labels: dict[str, str]) -> None:
    """공용 표시명 프로필과 그 화면이 값 칸에 넘기는 표시명을 같이 둔다(앱에서는 둘 다
    `get_process_labels`)."""
    monkeypatch.setattr(
        process_field, "_shared_display_names", lambda: ProcessLabels(labels=dict(labels))
    )
    app.session_state["test_labels"] = dict(labels)


def test_a_drawn_display_screen_reads_the_renamed_display_name_not_the_old_sent_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """표시명 화면에서 고른 뒤 같은 세션에 표시명이 바뀌면(Admin Proc Rename) 그 화면의 머리 칩 · 판
    · 탭 풍선도 값 칸처럼 새 이름이다 — 보낸 글자(옛 표시명)가 남아 한 화면에 두 이름이 서지
    않는다(2차 보드 Q2-18 · 검토 지적)."""
    app = AppTest.from_function(_drawn_chip_script)
    _profile(monkeypatch, app, {"WF": "새 WF 이름"})
    app.run()
    share(app, ["WF", "Mold"], origin="산출 결과")
    app.session_state[shared_process._LABELS_KEY] = {"WF": "옛 WF 이름"}
    app.run()

    assert not app.exception
    assert _field(app).label == "새 WF 이름 외 1개"
    chip = app.session_state["chip"]
    assert (chip["labels"], chip["top"]) == (["새 WF 이름", "Mold"], "새 WF 이름 외 1개")
    (mark,) = process_marks(app)
    assert mark["labels"] == {"WF": "새 WF 이름", "Mold": "Mold"}
    assert mark["tab"]["title"] == "공정 새 WF 이름 · Mold — 산출 결과 에서"


def test_a_display_name_clashing_with_another_process_reads_like_the_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """표시명이 그 화면 다른 공정의 원본과 같으면(Shipping Inspection → 「AVI」, AVI 는 따로 있는
    공정) 칩 · 판 · 탭 풍선도 값 칸처럼 「AVI (Shipping Inspection)」 으로 가른다 — 맨 「AVI」 는
    다른 공정으로 읽힌다(검토 지적). Space 에서 고른 값(보낸 글자 없음)도 같다. 그 화면을 처음 그린
    회차는 페이지보다 먼저 만든 칩이 선택지를 모르므로 회차 표지의 `labels` 가 그 글자를 실어
    알림 칸 JS 가 바로잡고, 다음 회차부터는 칩도 그 글자다. 따라가지 않는 화면(HOME)은 공용 값과
    그린 화면 선택지를 합친 목록으로 가른다 — 산출 결과를 그린 뒤라 같은 글자다."""
    app = AppTest.from_function(_drawn_chip_script)
    app.session_state["test_options"] = ["AVI", "Shipping Inspection", "Mold"]
    _profile(monkeypatch, app, {"Shipping Inspection": "AVI"})
    share(app, ["Shipping Inspection"], origin="Space")
    app.run()

    assert not app.exception
    assert _field(app).label == "AVI \\(Shipping Inspection\\)"
    (mark,) = process_marks(app)
    assert mark["labels"] == {"Shipping Inspection": "AVI (Shipping Inspection)"}
    assert mark["tab"]["title"] == "공정 AVI (Shipping Inspection) — Space 에서"

    app.run()
    chip = app.session_state["chip"]
    assert (chip["labels"], chip["top"]) == (
        ["AVI (Shipping Inspection)"],
        "AVI (Shipping Inspection)",
    )
    assert app.session_state["home_chip"]["labels"] == ["AVI (Shipping Inspection)"]


def test_a_value_this_screen_lacks_reads_the_display_name_without_a_hidden_mark(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """그 화면 선택지에 없는 값(「n개 이 화면 없음」)은 프로필의 표시명이다 — 선택지로 가른 글자
    함수는 선택지 밖 값에 보이지 않는 U+2060 을 붙이므로 그 함수로 적지 않는다."""
    app = AppTest.from_function(_drawn_chip_script)
    _profile(monkeypatch, app, {"WF": "WF 입고검사", "PMC": "피엠씨"})
    app.run()
    share(app, ["WF", "PMC"])
    app.run()

    assert not app.exception
    chip = app.session_state["chip"]
    (mark,) = process_marks(app)
    assert chip["labels"] == ["WF 입고검사", "피엠씨"]
    assert mark["labels"] == {"WF": "WF 입고검사", "PMC": "피엠씨"}
    assert mark["tab"]["title"] == "공정 WF 입고검사 — HOME 에서\n피엠씨 는 이 화면에 없음"
    assert "\u2060" not in json.dumps([chip, mark], ensure_ascii=False)


def test_the_shared_profile_is_read_only_when_the_database_file_exists(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """머리 칩 · 탭 줄은 DB 를 새로 만들지 않는다 — 파일이 없으면 프로필도 없는 것(원본)이고, 있으면
    공용 표시명 프로필(`get_process_labels`)을 읽는다."""
    from capa_simulation import settings

    profile = ProcessLabels(version=3, labels={"WF": "WF 입고검사"})
    monkeypatch.setattr(process_field, "get_process_labels", lambda: profile)
    absent = tmp_path / "absent.duckdb"
    monkeypatch.setattr(settings, "DUCKDB_PATH", absent)
    assert REAL_SHARED_DISPLAY_NAMES() == ProcessLabels()
    assert not absent.exists()

    present = tmp_path / "present.duckdb"
    present.write_bytes(b"")
    monkeypatch.setattr(settings, "DUCKDB_PATH", present)
    assert REAL_SHARED_DISPLAY_NAMES() is profile


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


def test_a_board_that_keeps_pick_order_and_does_not_read_all_as_none() -> None:
    """판을 쓰는 다른 칸(필요 단축 일정 조건 카드 「공정」 — `pickOrder` · `wholeIsAll: false`)은
    누른 차례로 쌓고(끄면 빼고 다시 켜면 끝), 모두 켬을 고르지 않음과 같이 보지 않는다 — 판은 그때
    공정 수 0 을 넘겨 `applyState` 가 둘을 가른다. 차례를 지키는 판(`ordered`)은 차례만 바뀐 초안도
    지금 값과 다르게 본다 — 저장소도 차례를 남긴다. 차례를 보지 않는 판(공용 공정 팝업)은 그대로
    같다."""
    out = _node(
        """
const order = ['WF', 'Mold', 'Underfill']
const one = togglePicked([], 'Underfill')
const two = togglePicked(one, 'WF')
const back = togglePicked(togglePicked(two, 'Underfill'), 'Underfill')
process.stdout.write(JSON.stringify({
  one, two, back,
  allFromNone: applyState('multi', order, [], 0, true),
  noneFromAll: applyState('multi', [], order, 0, true),
  reordered: applyState('multi', ['Mold', 'WF'], ['WF', 'Mold'], 0, true),
  sameOrder: applyState('multi', ['WF', 'Mold'], ['WF', 'Mold'], 0, true),
  anyOrder: applyState('multi', ['Mold', 'WF'], ['WF', 'Mold'], 0),
  emptyFromOne: applyState('multi', [], ['Mold'], 0, true),
}))
"""
    )
    assert out["one"] == ["Underfill"]
    assert out["two"] == ["Underfill", "WF"]
    assert out["back"] == ["WF", "Underfill"]
    assert (out["allFromNone"], out["noneFromAll"]) == ("ready", "ready")
    assert (out["reordered"], out["sameOrder"], out["anyOrder"]) == ("ready", "same", "same")
    assert out["emptyFromOne"] == "ready"


def test_the_board_flags_default_to_the_shared_dialog_board() -> None:
    """판 data 의 넷(`wholeIsAll` · `pickOrder` · `clearDraft` · `clearLabel`)은 주지 않으면 공용
    공정 팝업 판 그대로다 — 그 팝업 data 에는 실리지 않는다. 다른 칸이 줄 때만 실린다. 판 JS 가 넷을
    읽어 누름 · 「적용」 잠금 · 비우기 · 단추 글로 잇는 자리는 아래 마운트 시험(가짜 DOM)이 돈다."""
    shared = process_field._board_data(
        mode=process_field.MULTI, options=OPTIONS, texts=OPTIONS, selected=(), has_shared=True
    )
    assert set(shared) == {"mode", "options", "selected", "hasShared"}
    other = process_field._board_data(
        mode=process_field.MULTI,
        options=OPTIONS,
        texts=OPTIONS,
        selected=("Mold", "WF"),
        has_shared=True,
        whole_is_all=False,
        pick_order=True,
        clear_draft=True,
        clear_label="선택 해제",
    )
    assert (
        other["wholeIsAll"],
        other["pickOrder"],
        other["clearDraft"],
        other["clearLabel"],
    ) == (False, True, True, "선택 해제")
    assert other["selected"] == ["Mold", "WF"]


def test_an_apply_in_pick_order_keeps_the_sent_order_without_strangers_or_repeats() -> None:
    picked = process_field.parse_board_apply(
        {"values": ["Underfill", "Ghost", "WF", "Underfill"]}, OPTIONS, pick_order=True
    )
    assert picked == PickerResult(values=("Underfill", "WF"))
    assert process_field.parse_board_apply(
        {"values": ["Underfill", "WF"]}, OPTIONS
    ) == PickerResult(values=("WF", "Underfill"))
    assert process_field.parse_board_apply({"clear": True}, OPTIONS) == PickerResult(clear=True)
    assert process_field.parse_board_apply(None, OPTIONS) is None
    assert process_field.parse_board_apply({"values": "WF"}, OPTIONS, pick_order=True) is None


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


# ------------------------------------------------------------------ 판 JS 마운트(가짜 DOM)

_MOUNT_HEAD = "export default function (component) {"

# 판 자산 HTML 을 그대로 세운 가짜 DOM 에서 마운트 함수를 돌린다. 단계(`steps`)는 마운트(서버 회차 —
# 같은 뿌리 요소라 회차를 넘는 초안이 남는다) · 타일 · 「적용」 · 「전체」 누름 · 보임 바꾸기 · 그림
# 차례(`requestAnimationFrame`) 돌리기다. 잠긴 단추에는 click 이 가지 않는다(브라우저와
# 같다). `snap` 이름을 준 단계 뒤에는 단추 상태 · 글 · 초점 기록을 남긴다.
_BOARD_DOM_RUNNER = r"""
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'))
globalThis.Node = { ELEMENT_NODE: 1, TEXT_NODE: 3 }
const frames = []
globalThis.requestAnimationFrame = (fn) => {
  frames.push(fn)
  return frames.length
}
const focusCalls = []
let shown = true
// 창 처리기 대역 — capture 로 단 keydown 처리기를 모은다. 판을 둔 팝오버(`st.popover`)는 열린 동안
// 문서의 keydown 을 capture 단계에서 받아 Esc 면 닫는다 — 창 capture 처리기가 멈추지 않은 Esc 는
// 그 팝오버가 받아 닫는 것으로 센다(`closed`).
const windowListeners = []
globalThis.window = {
  addEventListener: (type, fn, capture) => {
    windowListeners.push({ type, fn, capture: Boolean(capture) })
  },
}
let closed = 0

class FakeText {
  constructor(value) {
    this.nodeType = 3
    this.nodeValue = String(value)
    this.parentNode = null
  }
  get textContent() { return this.nodeValue }
}

class FakeElement {
  constructor(tag) {
    this.nodeType = 1
    this.tagName = String(tag).toUpperCase()
    this.childNodes = []
    this.parentNode = null
    this.attributes = {}
    this.dataset = {}
    this.className = ''
    this.hidden = false
    this.disabled = false
    this.tabIndex = -1
    this.value = ''
    this.offsetTop = 0
  }
  get children() { return this.childNodes.filter((node) => node.nodeType === 1) }
  append(...nodes) {
    for (const node of nodes) {
      node.parentNode = this
      this.childNodes.push(node)
    }
  }
  replaceChildren(...nodes) {
    this.childNodes = []
    this.append(...nodes)
  }
  get textContent() { return this.childNodes.map((node) => node.textContent).join('') }
  set textContent(value) { this.replaceChildren(new FakeText(value)) }
  setAttribute(name, value) {
    this.attributes[name] = String(value)
    if (name === 'class') this.className = String(value)
    if (name === 'hidden') this.hidden = true
  }
  getAttribute(name) { return name in this.attributes ? this.attributes[name] : null }
  matches(selector) { return this.className.split(/\s+/).includes(selector.replace(/^\./, '')) }
  querySelectorAll(selector) {
    const found = []
    const walk = (node) => {
      for (const child of node.children) {
        if (child.matches(selector)) found.push(child)
        walk(child)
      }
    }
    walk(this)
    return found
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null }
  closest(selector) {
    for (let node = this; node && node.nodeType === 1; node = node.parentNode) {
      if (node.matches(selector)) return node
    }
    return null
  }
  focus() { focusCalls.push(this.className) }
  getClientRects() { return shown ? [{ width: 1, height: 1 }] : [] }
}

globalThis.document = { createElement: (tag) => new FakeElement(tag) }

// 자산 HTML 을 태그 · 속성 · 글 마디로 세운다 — 읽지 못한 글자가 남으면 실패다.
const VOID_TAGS = new Set(['input'])
function buildTree(html) {
  const top = new FakeElement('div')
  const stack = [top]
  const token = /<\/([a-z]+)\s*>|<([a-z]+)((?:\s+[a-z][a-z0-9-]*(?:="[^"]*")?)*)\s*>|([^<]+)/g
  let read = 0
  for (const match of html.matchAll(token)) {
    if (match.index !== read) {
      throw new Error('HTML 을 읽지 못한 자리: ' + html.slice(read, read + 40))
    }
    read = match.index + match[0].length
    const here = stack[stack.length - 1]
    if (match[1]) {
      const closed = stack.pop()
      if (stack.length === 0 || closed.tagName !== match[1].toUpperCase()) {
        throw new Error('닫는 태그가 어긋남: ' + match[1])
      }
      continue
    }
    if (match[2]) {
      const element = new FakeElement(match[2])
      for (const attr of match[3].matchAll(/([a-z][a-z0-9-]*)(?:="([^"]*)")?/g)) {
        element.setAttribute(attr[1], attr[2] ?? '')
      }
      here.append(element)
      if (!VOID_TAGS.has(match[2])) stack.push(element)
      continue
    }
    here.append(new FakeText(match[4]))
  }
  if (read !== html.length || stack.length !== 1) throw new Error('HTML 이 끝까지 닫히지 않음')
  return top
}

const parent = buildTree(input.html)
const root = parent.querySelector('.capa-proc-root')
const part = (name) => root.querySelector('.capa-proc-' + name)
const triggers = []
const snaps = {}
let data = null

function click(target) {
  const button = ['.capa-proc-tile', '.capa-proc-apply', '.capa-proc-all']
    .map((selector) => target.closest(selector))
    .find(Boolean)
  if (button && button.disabled) return
  root.onclick({ target, preventDefault() {}, stopPropagation() {} })
}

for (const step of input.steps) {
  if (step.op === 'mount') {
    data = step.data
    __mount({
      data,
      parentElement: parent,
      setTriggerValue: (name, value) => triggers.push({ name, value }),
    })
  } else if (step.op === 'tile') {
    const index = data.options.findIndex((option) => option.value === step.value)
    const tile = part('grid').querySelectorAll('.capa-proc-tile')[index]
    click(tile.querySelector('.capa-proc-name'))
  } else if (step.op === 'apply') {
    click(part('apply').querySelector('.capa-proc-icon'))
  } else if (step.op === 'clear') {
    click(part('all'))
  } else if (step.op === 'shown') {
    shown = step.on
  } else if (step.op === 'type') {
    part('search').value = step.text
    root.oninput({ target: part('search') })
  } else if (step.op === 'key') {
    const event = {
      key: step.key,
      target: part('search'),
      isComposing: Boolean(step.composing),
      ctrlKey: false,
      metaKey: false,
      stopped: false,
      preventDefault() {},
      stopPropagation() { this.stopped = true },
    }
    for (const listener of windowListeners) {
      if (listener.type === 'keydown' && listener.capture && !event.stopped) listener.fn(event)
    }
    if (!event.stopped && event.key === 'Escape') closed += 1
    else if (!event.stopped) root.onkeydown(event)
  } else if (step.op === 'frames') {
    for (const fn of frames.splice(0)) fn()
  } else {
    throw new Error('모르는 단계: ' + step.op)
  }
  if (step.snap) {
    const clearAll = part('all')
    snaps[step.snap] = {
      apply: part('apply').disabled ? 'locked' : 'open',
      clear: clearAll.disabled ? 'locked' : 'open',
      clearText: clearAll.childNodes
        .filter((node) => node.nodeType === 3)
        .map((node) => node.nodeValue)
        .join(''),
      clearIcon: clearAll.querySelector('.capa-proc-icon').textContent,
      state: root.dataset.state,
      count: part('count').textContent,
      tiles: part('grid').querySelectorAll('.capa-proc-tile').length,
      shownTiles: part('grid')
        .querySelectorAll('.capa-proc-tile')
        .filter((tile) => !tile.hidden).length,
      search: part('search').value,
      focus: focusCalls.slice(),
      closed,
      windowKeydown: windowListeners.filter((listener) => listener.type === 'keydown').length,
    }
  }
}
process.stdout.write(JSON.stringify({ snaps, triggers }))
"""


def _mount(*steps: dict[str, Any]) -> Any:
    """판 JS 의 마운트 함수(`export default`)를 자산 HTML 로 세운 가짜 DOM 에서 `steps` 대로
    돌린다 — 돌려주는 것은 `snaps`(이름별 단추 상태 · 글 · 초점)와 `triggers`(보낸 트리거 차례)."""
    assert PROCESS_FIELD_JS.count(_MOUNT_HEAD) == 1
    source = PROCESS_FIELD_JS.replace(_MOUNT_HEAD, "globalThis.__mount = function (component) {")
    return run_js_json(
        source + "\n" + _BOARD_DOM_RUNNER,
        what="공정 판 JS 마운트 시험",
        stdin=json.dumps({"html": PROCESS_FIELD_HTML, "steps": list(steps)}, ensure_ascii=False),
    )


def _board(
    selected: tuple[str, ...] = (), *, has_shared: bool = False, shortening: bool = True
) -> dict[str, Any]:
    """서버가 판에 보내는 data(`_board_data`) — `shortening` 이면 필요 단축 일정 조건 카드
    「공정」 판의 넷(`whole_is_all=False` · `pick_order` · `clear_draft` · 「선택 해제」), 아니면
    공용 공정 팝업 판."""
    flags: dict[str, Any] = {}
    if shortening:
        flags = {
            "whole_is_all": False,
            "pick_order": True,
            "clear_draft": True,
            "clear_label": "선택 해제",
        }
    return process_field._board_data(
        mode=process_field.MULTI,
        options=OPTIONS,
        texts=["웨이퍼", "몰드", "언더필"],
        selected=selected,
        has_shared=has_shared,
        **flags,
    )


def test_the_mounted_shortening_board_keeps_pick_order_and_applies_every_process() -> None:
    """필요 단축 일정 「공정」 판(data 넷을 준 판)은 누른 차례로 쌓아 보내고, 모두 켬을 고르지
    않음과 같이 보지 않아 「적용」 이 열리며, 「전체」 자리 글이 「선택 해제」 다(아이콘은 그대로).
    다음 회차의 지금 값 차례가 첫 초안이다."""
    out = _mount(
        {"op": "mount", "data": _board(), "snap": "start"},
        {"op": "tile", "value": "Underfill"},
        {"op": "tile", "value": "WF", "snap": "two"},
        {"op": "tile", "value": "Mold", "snap": "every"},
        {"op": "apply"},
        {"op": "mount", "data": _board(("Mold", "WF"), has_shared=True), "snap": "seeded"},
        {"op": "tile", "value": "Underfill"},
        {"op": "apply"},
    )
    start, two, every, seeded = (out["snaps"][name] for name in ("start", "two", "every", "seeded"))
    assert start["tiles"] == len(OPTIONS)
    assert (start["clearText"], start["clearIcon"]) == ("선택 해제", "filter_alt_off")
    assert (start["apply"], start["clear"], start["state"]) == ("locked", "locked", "same")
    assert (two["apply"], two["clear"], two["count"]) == ("open", "open", "선택 2 / 3")
    assert (every["apply"], every["state"], every["count"]) == ("open", "ready", "선택 3 / 3")
    assert (seeded["apply"], seeded["clear"], seeded["count"]) == ("locked", "open", "선택 2 / 3")
    assert out["triggers"] == [
        {"name": "apply", "value": {"values": ["Underfill", "WF", "Mold"]}},
        {"name": "apply", "value": {"values": ["Mold", "WF", "Underfill"]}},
    ]


def test_the_shortening_boards_clear_button_only_empties_the_draft_and_apply_sends_it() -> None:
    """필요 단축 일정 판의 「선택 해제」(`clearDraft`)는 다른 화면의 같은 이름 단추처럼 고름만
    푼다 — 서버에 아무것도 보내지 않고 판에 켠 타일만 끈다. 켠 타일이 있을 때만 켜지고(적용한
    값이 없어도), 누르면 잠기므로 초점이 찾기 칸으로 간다 — 「적용」 이 열려도 그리로 가지 않는다
    (누르고 있던 Enter 의 되풀이가 공용 설정을 쓰지 않게). 비운 초안은 「적용」 이 빈 목록으로
    보낸다(「목표 미달 공정 전체」)."""
    out = _mount(
        {"op": "mount", "data": _board()},
        {"op": "tile", "value": "WF"},
        {"op": "tile", "value": "Mold", "snap": "picked"},
        {"op": "clear", "snap": "unpicked"},
        {"op": "mount", "data": _board(("Mold", "WF"), has_shared=True), "snap": "seeded"},
        {"op": "clear", "snap": "emptied"},
        {"op": "apply"},
    )
    picked, unpicked, seeded, emptied = (
        out["snaps"][name] for name in ("picked", "unpicked", "seeded", "emptied")
    )
    assert (picked["clear"], picked["apply"]) == ("open", "open")
    assert (unpicked["clear"], unpicked["apply"], unpicked["count"]) == (
        "locked",
        "locked",
        "선택 0 / 3",
    )
    assert unpicked["focus"][-1] == "capa-proc-search"
    assert (seeded["clear"], seeded["apply"]) == ("open", "locked")
    assert (emptied["clear"], emptied["apply"], emptied["count"]) == (
        "locked",
        "open",
        "선택 0 / 3",
    )
    assert emptied["focus"][-1] == "capa-proc-search"
    assert out["triggers"] == [{"name": "apply", "value": {"values": []}}]


def test_a_reordered_pick_of_the_same_processes_can_be_applied() -> None:
    """같은 공정을 차례만 바꿔 고른 초안(처음 고른 공정을 바꿈)은 「적용」 이 열려 그 차례로
    보낸다 — 저장소 · 한 줄 칸이 차례를 쓴다. 공용 공정 팝업 판은 차례를 보지 않아 그대로 잠긴다."""
    out = _mount(
        {"op": "mount", "data": _board(("WF", "Mold"), has_shared=True), "snap": "seeded"},
        {"op": "tile", "value": "WF"},
        {"op": "tile", "value": "WF", "snap": "reordered"},
        {"op": "apply"},
    )
    seeded, reordered = out["snaps"]["seeded"], out["snaps"]["reordered"]
    assert seeded["apply"] == "locked"
    assert (reordered["apply"], reordered["state"], reordered["count"]) == (
        "open",
        "ready",
        "선택 2 / 3",
    )
    assert out["triggers"] == [{"name": "apply", "value": {"values": ["Mold", "WF"]}}]

    shared = _mount(
        {"op": "mount", "data": _board(("WF", "Mold"), has_shared=True, shortening=False)},
        {"op": "tile", "value": "WF"},
        {"op": "tile", "value": "WF", "snap": "reordered"},
        {"op": "apply"},
    )
    assert shared["snaps"]["reordered"]["apply"] == "locked"
    assert shared["triggers"] == []


@pytest.mark.parametrize("shortening", [True, False])
def test_escape_with_a_search_text_clears_only_the_text_even_inside_a_popover(
    shortening: bool,
) -> None:
    """찾기 칸에 글이 있을 때 Esc 는 글만 지우고 판을 둔 팝오버 · 팝업은 닫지 않는다 — 팝오버는
    문서의 keydown 을 capture 단계에서 받아 닫으므로 판은 그보다 앞인 창 capture 단계에서 받는다.
    한글을 치는 중의 Esc 는 글을 지우지 않고 팝오버에도 보내지 않는다(조합은 입력기 몫). 글이 없는
    Esc 는 손대지 않아 팝오버가 닫힌다. 창 처리기는 판을 몇 번 다시 세워도 하나다(R7)."""
    out = _mount(
        {"op": "mount", "data": _board(shortening=shortening)},
        {"op": "tile", "value": "WF"},
        {"op": "type", "text": "mo", "snap": "typed"},
        {"op": "key", "key": "Escape", "composing": True, "snap": "composing"},
        {"op": "key", "key": "Escape", "snap": "cleared"},
        {"op": "mount", "data": _board(shortening=shortening)},
        {"op": "mount", "data": _board(shortening=shortening)},
        {"op": "key", "key": "Escape", "snap": "empty"},
    )
    typed, composing, cleared, empty = (
        out["snaps"][name] for name in ("typed", "composing", "cleared", "empty")
    )
    assert (typed["search"], typed["shownTiles"]) == ("mo", 1)
    assert (composing["search"], composing["closed"]) == ("mo", 0)
    assert (cleared["search"], cleared["shownTiles"], cleared["closed"]) == ("", len(OPTIONS), 0)
    assert cleared["count"] == "선택 1 / 3"
    assert (empty["closed"], empty["windowKeydown"]) == (1, 1)


def test_the_mounted_shared_dialog_board_keeps_option_order_and_locks_every_process() -> None:
    """data 셋을 주지 않은 판(공용 공정 팝업)은 선택지 차례로 보내고, 모두 켬을 고르지 않음과 같이
    보아 「적용」 을 잠근다(잠긴 단추는 누르지 못한다) — 「전체」 글 그대로다."""
    out = _mount(
        {"op": "mount", "data": _board(shortening=False), "snap": "start"},
        {"op": "tile", "value": "Underfill"},
        {"op": "tile", "value": "WF"},
        {"op": "tile", "value": "Mold", "snap": "every"},
        {"op": "apply"},
        {"op": "tile", "value": "Mold", "snap": "two"},
        {"op": "apply"},
    )
    start, every, two = (out["snaps"][name] for name in ("start", "every", "two"))
    assert (start["clearText"], start["clearIcon"]) == ("전체", "filter_alt_off")
    assert (every["apply"], every["state"]) == ("locked", "same")
    assert (two["apply"], two["state"]) == ("open", "ready")
    assert out["triggers"] == [{"name": "apply", "value": {"values": ["WF", "Underfill"]}}]


def test_the_mounted_board_takes_the_search_focus_only_once_it_is_visible() -> None:
    """보이지 않는 판(닫힌 팝오버 안에 미리 선 판)은 찾기 칸 초점을 가져가지 않는다 — 화면의 다른
    칸에서 초점을 뺏지 않게. 보이는 회차에 한 번만 가져간다."""
    out = _mount(
        {"op": "shown", "on": False},
        {"op": "mount", "data": _board()},
        {"op": "frames", "snap": "hidden"},
        {"op": "shown", "on": True},
        {"op": "mount", "data": _board()},
        {"op": "frames", "snap": "visible"},
        {"op": "mount", "data": _board()},
        {"op": "frames", "snap": "again"},
    )
    snaps = out["snaps"]
    assert snaps["hidden"]["focus"] == []
    assert snaps["visible"]["focus"] == ["capa-proc-search"]
    assert snaps["again"]["focus"] == ["capa-proc-search"]
