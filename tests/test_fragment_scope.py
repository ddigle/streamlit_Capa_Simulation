# Purpose: 편집기 구역 도우미(fragment_scope)의 올리는 자리 · 머리 표지 · 작은 인자 · 남의 저장 ·
# 오류 카드를 프래그먼트 회차 대역으로, 본문 앞 올리기 금지를 정적으로 검사한다.

"""편집기 구역 회차 규칙(AGENTS 9장 「구역 회차 규칙」)의 파이썬 몫을 본다.

- **출납 ack 지킴(R1)** — Components v2 부품의 상태 값(출납)을 프래그먼트 회차로 보내고, 그
  상호작용이 머리 표지를 바꿔 앱 전체로 올라갈 때 부품이 받는 ack 가 남는지 본다. 콜백
  끝(`escalates`) · 본문 뒤(`editor_scope`)는 남고, 본문 앞에서 올리면 잃는다(대조 본문이
  그 함정을 되살린다). 잃는 것은 서버 쪽이다 — 본문을 시작한 회차는 끝에서 그 회차가 그리지
  않은 프래그먼트 위젯 상태를 지운다(`ScriptRunner._on_script_finished` 의
  `remove_stale_widgets=ctx.has_script_started`).
- **머리 표지가 그대로인 칸 고치기**는 구역 회차 하나로 끝난다. **남의 저장 토큰**(R4)이 바뀌면
  본문 뒤에서 올린다. **한 번만 쓰는 인자**(R3)는 구역 회차에서 꺼진다. **본문 오류**(R6)는 코어
  화면 카드다.
- **정적** — `grade_ui.in_fragment` · `fragment_scope.editor_scope` 감싸기는 본문 앞에서 `st.rerun`
  하지 않고, `editor_scope` 를 단 본문은 `st.rerun` 을 직접 부르지 않으며, `st.fragment` 본문
  첫머리의 「조건 → 앱 전체 올리기」 는 알려진 자리(목록)뿐이다.
"""

from __future__ import annotations

import ast
import dataclasses
import inspect
import textwrap
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest
from fragment_browser import FragmentBrowser, install_fragment_browser
from streamlit.testing.v1 import AppTest

from capa_simulation.components import fragment_scope, grade_ui

ROOT = Path(__file__).resolve().parents[1]
SCOPE = "probe_scope"

# 구역 하나와 그 안 Components v2 부품(출납 `outbox` 상태 값) — 칸을 처음 고치면 머리 표지가
# 바뀐다(편집본 「저장 안 함」 이 서는 꼴). 부품은 AppTest 실행 **안에서** 등록한다(모듈을 읽을 때
# 등록한 것은 그 실행에서 「미등록」).
_PRELUDE = """
import streamlit as st
from capa_simulation.auth import grades
from capa_simulation.components import fragment_scope, grade_ui, grid_shared

SCOPE = "probe_scope"
probe = st.components.v2.component("rr_scope_probe", js="export default function () {}")
st.session_state.setdefault("applied", [])
st.session_state.setdefault("token", 1)
st.session_state["app_runs"] = st.session_state.get("app_runs", 0) + 1


def head():
    if st.session_state.get("head_explode"):
        raise OSError("머리 표지 읽기 실패")
    return (bool(st.session_state["applied"]),)


def token():
    if st.session_state.get("token_explode"):
        raise OSError("저장 토큰 읽기 실패")
    return st.session_state["token"]


def _ops():
    value = grid_shared.outbox_value("probe")
    return list(value.get("ops", [])) if isinstance(value, dict) else []


def _apply():
    done = {op["seq"] for op in st.session_state["applied"]}
    for op in _ops():
        if op.get("refuse"):
            raise grades.GradeDenied("official.publish", "manager", "viewer")
    st.session_state["applied"] = st.session_state["applied"] + [
        op for op in _ops() if op["seq"] not in done
    ]


def _draw(fresh):
    if st.session_state.get("explode"):
        raise ValueError("구역 본문 오류")
    if st.session_state.pop("refuse_body", False):
        raise grades.GradeDenied("official.publish", "manager", "viewer")
    st.session_state["seen_fresh"] = fresh
    ops = _ops()
    ack = ops[-1]["seq"] if ops else None
    probe(key="probe", data={"ack": ack}, on_outbox_change=_on_outbox)


grade_ui.emit()
st.markdown(f"head={head()[0]}")
"""

# 콜백 끝 올리기(`escalates`) + 본문 뒤 올리기(`editor_scope`).
CALLBACK_END = (
    _PRELUDE
    + """

@fragment_scope.escalates(SCOPE)
@grade_ui.on_press
def _on_outbox():
    _apply()


@st.fragment(key=SCOPE)
@grade_ui.in_fragment
@fragment_scope.editor_scope(SCOPE, head=head, token=token, one_shot=("fresh",))
def body(*, fresh):
    _draw(fresh)


body(fresh=True)
"""
)

# 콜백은 올리지 않는다 — 본문 뒤 올리기(`editor_scope`)만.
BODY_END = (
    _PRELUDE
    + """

@grade_ui.on_press
def _on_outbox():
    _apply()


@st.fragment(key=SCOPE)
@grade_ui.in_fragment
@fragment_scope.editor_scope(SCOPE, head=head, token=token, one_shot=("fresh",))
def body(*, fresh):
    _draw(fresh)


body(fresh=True)
"""
)

# 콜백 끝 올리기 — 한 번만 쓰는 인자를 위치 인자로 넘긴다.
CALLBACK_END_POSITIONAL = (
    _PRELUDE
    + """

@fragment_scope.escalates(SCOPE)
@grade_ui.on_press
def _on_outbox():
    _apply()


@st.fragment(key=SCOPE)
@grade_ui.in_fragment
@fragment_scope.editor_scope(SCOPE, head=head, token=token, one_shot=("fresh",))
def body(fresh):
    _draw(fresh)


body(True)
"""
)

# 바깥 프래그먼트 안의 구역 — 바깥 회차는 구역을 새 인자로 부른다(한 번만 쓰는 인자를 끄지 않는다).
NESTED = (
    _PRELUDE
    + """

@fragment_scope.escalates(SCOPE)
@grade_ui.on_press
def _on_outbox():
    _apply()


@st.fragment(key=SCOPE)
@grade_ui.in_fragment
@fragment_scope.editor_scope(SCOPE, head=head, token=token, one_shot=("fresh",))
def body(*, fresh):
    _draw(fresh)


@st.fragment(key="outer_scope")
def outer():
    st.button("outer", key="outer_press")
    body(fresh=st.session_state.get("fresh_next", False))


outer()
"""
)

# 구역 인자로 표 세 짝을 넘긴다(R3 거절 — 코어 화면 카드).
BIG_ARGUMENT = """
import pandas as pd
import streamlit as st
from capa_simulation.components import fragment_scope, grade_ui

SCOPE = "probe_scope"


@st.fragment(key=SCOPE)
@grade_ui.in_fragment
@fragment_scope.editor_scope(SCOPE)
def body(frames):
    st.markdown(str(len(frames)))


frame = pd.DataFrame({"a": [1]})
body((frame, frame, frame))
"""

# 대조 — 본문 앞에서 올린다(금지된 꼴). 앱 전체 회차가 머리 표지를 찍는다.
PRE_BODY = (
    _PRELUDE
    + """

@grade_ui.on_press
def _on_outbox():
    _apply()


if not fragment_scope.fragment_only_run():
    st.session_state["stamp"] = head()


@st.fragment(key=SCOPE)
def body(*, fresh):
    if fragment_scope.fragment_only_run() and head() != st.session_state.get("stamp"):
        st.rerun(scope="app")
    _draw(fresh)


body(fresh=True)
"""
)


def _op(seq: int, **extra: Any) -> dict[str, Any]:
    """부품 상태 값 — 출납 `outbox` 하나(마운트 · 보낼 op)."""
    return {"outbox": {"mount": "m1", "ops": [{"op": "cell", "seq": seq, "id": "U1", **extra}]}}


def _ops(*seqs: int) -> dict[str, Any]:
    ops = [{"op": "cell", "seq": seq, "id": "U1"} for seq in seqs]
    return {"outbox": {"mount": "m1", "ops": ops}}


def _start(monkeypatch: pytest.MonkeyPatch, script: str) -> tuple[AppTest, FragmentBrowser, str]:
    browser = install_fragment_browser(monkeypatch)
    app = AppTest.from_string(script).run(timeout=60)
    assert not list(app.exception), [element.message for element in app.exception]
    return app, browser, browser.fragment_keyed(SCOPE)


def _heads(app: AppTest) -> list[str]:
    return [str(item.value) for item in app.markdown if str(item.value).startswith("head=")]


def _block_keys(browser: FragmentBrowser) -> list[str]:
    """보낸 델타의 칸(블록) key — 코어 화면 카드 칸(`page_failure_card.CARD_KEY`)이 섰는지 본다."""
    return [
        message.delta.add_block.id
        for message in browser.emitted
        if message.WhichOneof("type") == "delta" and message.delta.WhichOneof("type") == "add_block"
    ]


@pytest.mark.parametrize("script", [CALLBACK_END, BODY_END], ids=["callback-end", "body-end"])
def test_a_first_edit_rises_to_the_app_run_and_keeps_the_outbox_ack(
    monkeypatch: pytest.MonkeyPatch, script: str
) -> None:
    """첫 칸 고치기는 머리 표지(저장 안 함 있음)를 바꿔 앱 전체 회차로 올라간다 — 콜백 끝에서
    올리든 본문 뒤에서 올리든 그 회차의 부품은 보낸 op 의 ack 를 받는다(출납이 쌓이지 않는다). 구역
    밖 머리도 새 값이다."""
    app, browser, scope = _start(monkeypatch, script)

    browser.send_state(app, "probe", _op(1))

    assert not list(app.exception), [element.message for element in app.exception]
    assert browser.started == [[scope], []], "구역 회차로 시작해 앱 전체 회차로 올라간다"
    assert browser.bidi_data("probe") == {"ack": 1}
    assert _heads(app) == ["head=True"]
    assert [op["seq"] for op in app.session_state["applied"]] == [1]


def test_a_pre_body_rise_loses_the_ack_of_the_edit_that_raised_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """대조 — 본문 앞에서 `st.rerun(scope="app")` 으로 올리면 그 회차가 다시 그리지 않은 부품의
    상태 값(출납)을 회차 끝 정리가 지워, 올라간 앱 전체 회차의 부품은 ack 없이 그려진다.
    op 는 콜백이 이미 반영했으므로 브라우저는 반영된 op 를 다시 보내게 된다."""
    app, browser, scope = _start(monkeypatch, PRE_BODY)

    browser.send_state(app, "probe", _op(1))

    assert browser.started == [[scope], []]
    assert [op["seq"] for op in app.session_state["applied"]] == [1]
    assert browser.bidi_data("probe") == {"ack": None}


@pytest.mark.parametrize(
    "script", [CALLBACK_END, CALLBACK_END_POSITIONAL], ids=["keyword", "positional"]
)
def test_an_edit_that_keeps_the_head_marks_stays_a_scope_run(
    monkeypatch: pytest.MonkeyPatch, script: str
) -> None:
    """머리 표지가 그대로인 칸 고치기(두 번째 칸)는 구역 회차 하나로 끝난다 — 앱 전체 회차가 없다.
    한 번만 쓰는 인자(`one_shot`)는 키워드로 넘기든 위치로 넘기든 구역 회차에서 꺼진다(R3)."""
    app, browser, scope = _start(monkeypatch, script)
    browser.send_state(app, "probe", _op(1))
    assert app.session_state["seen_fresh"] is True, "앱 전체 회차는 넘긴 값 그대로"
    runs = app.session_state["app_runs"]

    browser.send_state(app, "probe", _ops(1, 2))

    assert browser.started == [[scope]]
    assert app.session_state["app_runs"] == runs
    assert browser.bidi_data("probe") == {"ack": 2}
    assert app.session_state["seen_fresh"] is False


def test_an_outer_fragment_run_keeps_the_one_shot_argument_it_passes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """바깥 프래그먼트 회차가 안쪽 구역을 부르면 그 인자는 앞 앱 전체 회차 값이 아니라 새 값이다 —
    한 번만 쓰는 인자를 끄지 않는다. 구역 자신의 회차에서만 끈다(`own_fragment_run`)."""
    app, browser, scope = _start(monkeypatch, NESTED)
    outer = browser.fragment_keyed("outer_scope")
    assert app.session_state["seen_fresh"] is False

    app.session_state["fresh_next"] = True
    browser.fragment_queue = [outer]
    app.button(key="outer_press").click().run(timeout=60)

    assert browser.started == [[outer]]
    assert app.session_state["seen_fresh"] is True

    browser.send_state(app, "probe", _op(1))
    browser.send_state(app, "probe", _ops(1, 2))
    assert browser.started == [[scope]]
    assert app.session_state["seen_fresh"] is False


def test_one_shot_names_must_be_arguments_of_the_scope_body() -> None:
    """한 번만 쓰는 인자 이름이 본문 함수 인자에 없으면 단 순간 `TypeError` 다(조용히 지나가면 끄지
    못한다)."""

    def body(fresh: bool) -> None:
        del fresh

    with pytest.raises(TypeError, match="one_shot"):
        fragment_scope.editor_scope("probe_unknown", one_shot=("stale",))(body)


def test_a_save_by_someone_else_rises_after_the_body(monkeypatch: pytest.MonkeyPatch) -> None:
    """남의 저장(R4) — 구역 회차 본문 머리가 다시 읽은 토큰이 앱 전체 회차에 찍은 값과 다르면 본문
    뒤에서 앱 전체로 올린다. 올라간 회차가 새 토큰을 찍어 다음 칸은 다시 구역 회차다."""
    app, browser, scope = _start(monkeypatch, CALLBACK_END)
    browser.send_state(app, "probe", _op(1))

    app.session_state["token"] = 2
    browser.send_state(app, "probe", _ops(1, 2))
    assert browser.started == [[scope], []]
    assert browser.bidi_data("probe") == {"ack": 2}

    browser.send_state(app, "probe", _ops(1, 2, 3))
    assert browser.started == [[scope]]


def test_a_refused_callback_in_a_scope_run_rises_at_the_callback_end(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """구역 회차 콜백의 등급 거절은 `on_press` 가 콜백 끝에서 앱 전체 회차로 올린다 — 그 회차의
    `emit` 이 알림을 내고 표지를 걷는다. 본문을 시작하기 전이라 부품 상태 값이 남는다."""
    app, browser, scope = _start(monkeypatch, BODY_END)
    browser.send_state(app, "probe", _op(1))

    browser.send_state(app, "probe", _op(2, refuse=True))

    assert not list(app.exception), [element.message for element in app.exception]
    assert browser.started == [[scope], []]
    assert grade_ui.PENDING_KEY not in app.session_state
    assert browser.bidi_data("probe") == {"ack": 2}


def test_a_refusal_in_the_body_before_the_component_loses_its_ack_and_seq_filtering_heals_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """한계 — 구역 본문이 부품을 그리기 **전에** 등급 거절을 내면 그 회차는 부품 상태 값(출납)을
    다시 그리지 못한 채 끝난다. `in_fragment` 가 올리든 그냥 끝내든 회차 끝 정리(`st.stop` 밖의 모든
    끝)가 그 상태 값을 지워, 올라간 앱 전체 회차의 부품은 ack 없이 그려진다. 그래서 거절될 수 있는
    쓰기는 콜백(`on_press` — 콜백 끝 올리기는 상태 값이 남는다)에 두고, 편집기는 마운트별 seq 로
    겹침을 거른다 — 브라우저가 반영된 op 를 다시 보내도 한 번만 들어가고 그 회차가 ack 를 싣는다."""
    app, browser, scope = _start(monkeypatch, CALLBACK_END)
    browser.send_state(app, "probe", _op(1))
    app.session_state["refuse_body"] = True

    browser.send_state(app, "probe", _ops(1, 2))

    assert not list(app.exception), [element.message for element in app.exception]
    assert browser.started == [[scope], []]
    assert [op["seq"] for op in app.session_state["applied"]] == [1, 2]
    assert browser.bidi_data("probe") == {"ack": None}

    browser.send_state(app, "probe", _ops(1, 2))

    assert [op["seq"] for op in app.session_state["applied"]] == [1, 2]
    assert browser.bidi_data("probe") == {"ack": 2}


def test_a_scope_body_failure_is_the_core_page_card_not_the_default_box(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """구역 회차의 본문 오류(R6)는 Streamlit 기본 오류 상자가 아니라 코어 화면 카드로 그 구역
    자리에 서고, 회차는 멈춤으로 끝난다(카드 칸 key `page_failure_card.CARD_KEY`)."""
    from capa_simulation.components.page_failure_card import CARD_KEY

    app, browser, scope = _start(monkeypatch, CALLBACK_END)
    browser.send_state(app, "probe", _op(1))
    app.session_state["explode"] = True

    browser.send_state(app, "probe", _ops(1, 2))

    assert browser.started == [[scope]]
    assert not list(app.exception), "기본 오류 상자가 아니다"
    keys = _block_keys(browser)
    assert any(CARD_KEY in key for key in keys), keys


@pytest.mark.parametrize("flag", ["token_explode", "head_explode"], ids=["token", "head"])
def test_a_failing_token_or_head_read_in_a_scope_run_is_the_core_page_card(
    monkeypatch: pytest.MonkeyPatch, flag: str
) -> None:
    """구역 회차 본문 머리의 저장 토큰 읽기(R4 — DuckDB 를 읽을 수 있다)와 본문 뒤 머리 표지
    견주기(R2)가 던져도 본문 오류처럼 코어 화면 카드로 그 구역 자리에 선다(R6) — Streamlit 기본 오류
    상자가 아니다. 콜백이 머리 표지를 읽지 않는 대본(본문 뒤 올리기)으로 본다."""
    from capa_simulation.components.page_failure_card import CARD_KEY

    app, browser, scope = _start(monkeypatch, BODY_END)
    browser.send_state(app, "probe", _op(1))
    app.session_state[flag] = True

    browser.send_state(app, "probe", _ops(1, 2))

    assert browser.started == [[scope]]
    assert not list(app.exception), [element.message for element in app.exception]
    keys = _block_keys(browser)
    assert any(CARD_KEY in key for key in keys), keys


# ------------------------------------------------------------------ 작은 인자(R3)


@dataclasses.dataclass(frozen=True)
class _Snapshot:
    name: str
    frame: pd.DataFrame


@dataclasses.dataclass(frozen=True)
class _Small:
    name: str
    count: int


def test_scope_arguments_must_be_small_values() -> None:
    """구역 인자는 작은 값만 — 표 · 표를 든 dataclass · 표를 든 모음(표 세 짝 튜플 · 목록 · 사전) ·
    긴 목록은 거절하고, 글 · 수 · 0차원 스칼라(`np.int64` · `pd.Timestamp`) · 짧은 튜플 · 표 없는
    dataclass 는 지나간다. 크기를 재지 않고 꼴만 본다."""
    frame = pd.DataFrame({"a": [1]})
    fragment_scope.check_small_args(("표",), {"n": 3, "pair": ("a", 1), "small": _Small("x", 1)})
    fragment_scope.check_small_args((), {"long_text": "가" * 10_000})
    fragment_scope.check_small_args(
        (np.int64(3), np.float64(0.5), pd.Timestamp("2026-01-01"), pd.NaT, np.dtype("int64")),
        {"mixed": ("a", np.int64(2), {"k": pd.Timedelta("1D")}), "nested": [(_Small("y", 2),)]},
    )
    for args, kwargs in (
        ((frame,), {}),
        ((), {"snapshot": _Snapshot("s", frame)}),
        ((), {"ids": list(range(fragment_scope.SMALL_ITEMS + 1))}),
        ((), {"series": frame["a"]}),
        ((), {"frames": (frame, frame, frame)}),
        (([frame],), {}),
        ((), {"by_name": {"a": frame}}),
        ((), {"deep": [(_Snapshot("s", frame),)]}),
        ((), {"array": np.array([1, 2])}),
    ):
        with pytest.raises(TypeError, match="작은 값"):
            fragment_scope.check_small_args(args, kwargs)


def test_a_big_scope_argument_is_the_core_page_card(monkeypatch: pytest.MonkeyPatch) -> None:
    """작은 인자 검사에 걸린 구역은 본문 오류처럼 코어 화면 카드로 선다(R6) — Streamlit 기본 오류
    상자가 아니다."""
    from capa_simulation.components.page_failure_card import CARD_KEY

    browser = install_fragment_browser(monkeypatch)
    app = AppTest.from_string(BIG_ARGUMENT).run(timeout=60)

    assert not list(app.exception), "기본 오류 상자가 아니다"
    keys = _block_keys(browser)
    assert any(CARD_KEY in key for key in keys), keys


def test_the_scope_box_key_and_the_run_style_share_one_prefix() -> None:
    """구역 칸 key 접두는 스타일의 계약이다 — 구역 칸 안 낡음 흐림만 덮는다."""
    assert fragment_scope.box_key("equipment") == "capa_scope_equipment"
    assert f'[class*="st-key-{fragment_scope.SCOPE_BOX_PREFIX}"]' in fragment_scope.SCOPE_RUN_STYLE


# ------------------------------------------------------------------ 정적 — 본문 앞 올리기 금지


def _is_rerun(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "rerun"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "st"
    )


# 앱 전체로 올리는 도우미 — 이름으로 불러도(`escalate(…)`) 모듈로
# 불러도(`fragment_scope.escalate(…)`) 올리기다.
_RISE_HELPERS = frozenset({"escalate", "escalate_if_moved"})


def _is_rise(node: ast.AST) -> bool:
    """`st.rerun(…)` 또는 올리기 도우미 호출."""
    if _is_rerun(node):
        return True
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name):
        return func.id in _RISE_HELPERS
    return isinstance(func, ast.Attribute) and func.attr in _RISE_HELPERS


def _calls_name(node: ast.AST, name: str) -> bool:
    return any(
        isinstance(inner, ast.Call) and isinstance(inner.func, ast.Name) and inner.func.id == name
        for inner in ast.walk(node)
    )


def _inner_function(source: str) -> ast.FunctionDef:
    tree = ast.parse(textwrap.dedent(source))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "inner":
            return node
    raise AssertionError("감싸기 안쪽 함수(inner)가 없다")


@pytest.mark.parametrize(
    ("wrapper", "body_call"),
    [(grade_ui.in_fragment, "fn"), (fragment_scope.editor_scope, "_run_guarded")],
    ids=["grade_ui.in_fragment", "fragment_scope.editor_scope"],
)
def test_scope_wrappers_never_rise_before_the_body(wrapper: Any, body_call: str) -> None:
    """감싸기는 본문(`fn` · `_run_guarded`)을 부르는 문장 **앞**에서 올리지 않는다(`st.rerun` 도,
    올리기 도우미 `escalate` · `escalate_if_moved` 도). 본문
    가운데서 난 거절을 받은 `except` 칸만 예외다 — 본문이 이미 멈춰, 어떻게 끝내도(올리기 · 그냥
    끝냄) 그 회차가 아직 그리지 못한 위젯 상태 값은 회차 끝 정리가 지운다(한계 —
    `test_a_refusal_in_the_body_before_the_component_loses_its_ack_and_seq_filtering_heals_it`)."""
    inner = _inner_function(inspect.getsource(wrapper))
    seen_body = False
    for statement in inner.body:
        if _calls_name(statement, body_call):
            seen_body = True
            if isinstance(statement, ast.Try):
                for part in [*statement.body, *statement.orelse, *statement.finalbody]:
                    assert not any(_is_rise(node) for node in ast.walk(part)), "본문과 같은 칸"
            continue
        if not seen_body:
            assert not any(_is_rise(node) for node in ast.walk(statement)), ast.unparse(statement)
    assert seen_body


def _source_files() -> list[Path]:
    return sorted(
        [*(ROOT / "src").rglob("*.py"), *(ROOT / "app_pages").glob("*.py"), ROOT / "app.py"]
    )


def _decorator_names(function: ast.FunctionDef) -> list[str]:
    names: list[str] = []
    for decorator in function.decorator_list:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        if isinstance(target, ast.Attribute):
            names.append(target.attr)
        elif isinstance(target, ast.Name):
            names.append(target.id)
    return names


def _functions_in(tree: ast.Module, rel: str) -> list[tuple[str, ast.FunctionDef]]:
    return [(rel, node) for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]


def _functions() -> list[tuple[str, ast.FunctionDef]]:
    found: list[tuple[str, ast.FunctionDef]] = []
    for path in _source_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        found.extend(_functions_in(tree, path.relative_to(ROOT).as_posix()))
    return found


def _direct_rises(functions: list[tuple[str, ast.FunctionDef]]) -> list[tuple[str, str]]:
    """`editor_scope` 를 단 본문 가운데 `st.rerun` 을 직접 부르는 것."""
    return [
        (rel, function.name)
        for rel, function in functions
        if "editor_scope" in _decorator_names(function)
        and any(_is_rerun(node) for node in ast.walk(function))
    ]


# 그물 대조 — 직접 `st.rerun` 하는 구역 본문(잡혀야 한다)과 도우미로 올리는 구역 본문.
_DIRECT_RISE_CONTROL = """
@st.fragment(key="bad")
@grade_ui.in_fragment
@fragment_scope.editor_scope("bad")
def bad():
    draw()
    st.rerun(scope="app")


@st.fragment(key="good")
@grade_ui.in_fragment
@fragment_scope.editor_scope("good")
def good():
    draw()
    fragment_scope.escalate()
"""


def test_editor_scope_bodies_rise_only_through_the_helpers() -> None:
    """`editor_scope` 를 단 구역 본문은 `st.rerun` 을 직접 부르지 않는다 — 올리기는 콜백
    끝(`escalates`) · 본문 뒤(`editor_scope` 스스로) · `fragment_scope.escalate`(본문을 다 그린
    뒤)로만 한다(R1). 그물이 헛돌지 않는지 대조 본문으로 먼저 본다."""
    control = _functions_in(ast.parse(_DIRECT_RISE_CONTROL), "control")
    assert _direct_rises(control) == [("control", "bad")]

    offenders = _direct_rises(_functions())
    assert not offenders, offenders


# 본문을 그리기 전에 「조건 → 앱 전체 올리기」 를 하는 알려진 프래그먼트 · 팝업 — 안에 Components
# v2 상태 값 부품이 없어 ack 를 잃을 것이 없다. 새로 더하지 않는다 — 편집기 구역은
# `fragment_scope` 로 올린다.
KNOWN_PRE_BODY_RISES = {
    # 기준선 저장 · 지우기 표지(`consume_baseline_write`)와 직전 계획에 없는 목표 — 필요 단축 일정
    # 본문.
    ("src/capa_simulation/components/required_shortening_panel.py", "_render_view"),
    # 확인할 공지가 없으면 팝업을 닫는다 — 안에는 단추 둘뿐이다(공지 관리 확인 팝업).
    ("src/capa_simulation/components/notice_admin.py", "_confirm_dialog"),
    # 그린 때의 판정 배지 · 올리기 잠금이 바뀌었으면 앱 회차로 돌아간다 — 안에는 글 · 복사
    # 단추뿐이다(DB 동기화 펼침의 되풀이 구역).
    ("src/capa_simulation/components/object_sync_status.py", "_render_live_body"),
}
# 그리지 않는 `st.` 부름 — 본문 첫머리에서 이것들만 지난 뒤의 올리기도 「그리기 전」 이다.
_QUIET_ST = frozenset(
    {"session_state", "query_params", "rerun", "secrets", "context", "cache_data", "cache_resource"}
)


def _dotted(node: ast.AST) -> tuple[str, ...]:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return tuple(reversed(parts))


def _draws(statement: ast.stmt) -> bool:
    """이 문장이 무언가를 그릴 수 있는가 — `with` · 되풀이 · `try` · 돌려주기, 올리기가 아닌 홀로 선
    호출, 그리지 않는 것 밖의 `st.` 부름."""
    if isinstance(statement, (ast.With, ast.For, ast.While, ast.Try, ast.Return)):
        return True
    if isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Call):
        return not _is_rise(statement.value)
    return any(
        isinstance(node, ast.Call)
        and len(dotted := _dotted(node.func)) > 1
        and dotted[0] == "st"
        and dotted[1] not in _QUIET_ST
        for node in ast.walk(statement)
    )


def _leading_rise(function: ast.FunctionDef) -> bool:
    """본문을 그리기 전(설명 글 · 그리지 않는 대입 뒤, 그리는 첫 문장 앞)의 `if …: <올리기>` 나
    홀로 선 올리기."""
    for statement in function.body:
        if isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Constant):
            continue
        if isinstance(statement, ast.If) and any(_is_rise(node) for node in ast.walk(statement)):
            return True
        if isinstance(statement, ast.Expr) and _is_rise(statement.value):
            return True
        if _draws(statement):
            return False
    return False


def _pre_body_rises(functions: list[tuple[str, ast.FunctionDef]]) -> set[tuple[str, str]]:
    return {
        (rel, function.name)
        for rel, function in functions
        if {"fragment", "dialog"} & set(_decorator_names(function)) and _leading_rise(function)
    }


# 그물 대조 — 대입 뒤 올리기 · 팝업 본문 · 도우미 올리기는 잡히고, 그린 뒤 올리기는 잡히지 않는다.
_PRE_BODY_CONTROL = """
@st.fragment
def after_assign():
    token = st.session_state.get("token")
    if token != seen():
        st.rerun(scope="app")
    draw()


@st.dialog("편집")
def dialog_rise():
    if moved():
        st.rerun()
    draw()


@st.fragment
def helper_rise():
    fragment_scope.escalate()
    draw()


@st.fragment
def drawn_first():
    st.markdown("본문")
    if moved():
        st.rerun(scope="app")
"""


def test_fragments_do_not_rise_before_drawing_their_body() -> None:
    """`st.fragment` · `st.dialog` 본문에서 무언가를 그리기 전에 앱 전체로 올리는 자리는 알려진
    목록뿐이다(R1 — 본문 앞 올리기 금지). 그물이 헛돌지 않는지 대조 본문으로 먼저 본다."""
    control = _functions_in(ast.parse(_PRE_BODY_CONTROL), "control")
    assert _pre_body_rises(control) == {
        ("control", "after_assign"),
        ("control", "dialog_rise"),
        ("control", "helper_rise"),
    }

    assert _pre_body_rises(_functions()) == KNOWN_PRE_BODY_RISES
