# Purpose: 가이드 촬영 계획의 동작 · 표적 낱말을 Playwright 로 몰고 재어 상태마다 한 장 찍는다.

"""따라하기 가이드 촬영기 — `scripts/build_page_guide.py` 가 부른다.

시안 `guide/capture/capture.mjs`·`lib.mjs`(Chrome DevTools 를 손으로 몰던 Node 스크립트)의 동작과
표적 찾기를 Python Playwright 로 옮겼다. 계획은 정해진 낱말만 쓴다.

- 동작(`OPS` 와 같은 열 개): `enter_app` · `nav` · `tab` · `click` · `fill` · `key` · `scroll` ·
  `open_popup` · `grid_edit` · `wait_idle`. 모든 동작 뒤에 회차가 쉴 때까지 기다린다
  (`stApp` 의 `data-test-script-state` 가 0.75초 동안 `notRunning`).
- 표적: `key:` · `button:` · `tab:` · `nav:` · `text:` 와 `named:` 이름(`NAMED_JS`). 팝업이 열려
  있으면 글자로 찾는 표적은 팝업 안부터 찾는다. 배열은 여러 표적의 합집합 사각형이다.
- 격자(glide 데이터 편집기)는 캔버스라 칸 자리를 React 속성(열 폭 · 행 높이 · 고정 열)과 굴림
  위치(`.dvn-scroller`)로 셈한다. 고칠 칸이 표 안 보이는 곳이면 표를 굴려 들인다(사내 표는
  70행이 넘는다).

**값을 밖으로 내지 않는다.** 화면 글자는 판정에만 쓴다. 실패는 `상태.ops.<번호> <동작>` 과 예외
종류만 남긴다. 매개값(사내 시나리오 이름 등)은 페이지 함수의 인자로만 넘긴다 — JS 글에 잇지
않는다.

**가림.** 찍기 전마다 계획의 `mask`(사이드바 꼬리말 카드)와 담당 조직 · 문의처 글자
(`settings.APP_OWNER_TEAM` · `APP_CONTACT_EMAIL`)를 감춘다. 감춘 뒤에도 그 글자가 화면 글
(`innerText`)에 남으면 찍지 않고 그 상태를 실패로 둔다.
"""

from __future__ import annotations

import datetime
import json
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Protocol

import page_guide_core as core

INTRO_HOST_ID: Final = "capa-intro-host"
# 사이드바 꼬리말 카드의 key(`components/app_credits.APP_CREDITS_KEY`). 앱 모듈을 부르면 Streamlit
# 이 깨어나 값만 옮기고 시험이 같은지 본다.
APP_CREDITS_KEY: Final = "sidebar_app_credits"
INTRO_TIMEOUT_SECONDS: Final = 240.0
SETTLE_TIMEOUT_SECONDS: Final = 120.0
ACTION_TIMEOUT_MS: Final = 30_000

# 사내 PC 글꼴 흉내(Noto Sans KR → 깔린 Noto CJK)와 깜빡이는 커서 감추기. 없는 글꼴이면 그대로다.
STYLE_JS: Final = (
    'document.addEventListener("DOMContentLoaded",()=>{const st=document.createElement("style");'
    'st.textContent=\'@font-face{font-family:"Noto Sans KR";src:local("NotoSansCJKkr-Regular");'
    'font-weight:400}@font-face{font-family:"Noto Sans KR";src:local("NotoSansCJKkr-Medium");'
    'font-weight:500}@font-face{font-family:"Noto Sans KR";src:local("NotoSansCJKkr-Bold");'
    "font-weight:600 900} *{caret-color:transparent !important}';"
    "document.head.appendChild(st);});"
)

# 페이지 쪽 도우미(`window.__g`, `page_guide_helpers.js`). 한 번 심으면 남지만 evaluate 마다
# 확인한다. 긴 JS 라 따로 둔다 — 사본 트리(`git archive`)에도 같이 실린다.
HELPERS_JS: Final = Path(__file__).with_name("page_guide_helpers.js").read_text(encoding="utf-8")

INTRO_STATE_JS: Final = (
    f"(()=>{{const h=document.getElementById({json.dumps(INTRO_HOST_ID)});if(!h)return'none';"
    "if(getComputedStyle(h).display==='none')return'hidden';"
    "const d=h.shadowRoot&&h.shadowRoot.querySelector('.btn.detail');"
    "return d&&!d.disabled?'ready':'waiting'})()"
)
INTRO_CLICK_JS: Final = (
    f"(()=>{{const h=document.getElementById({json.dumps(INTRO_HOST_ID)});"
    "const d=h&&h.shadowRoot&&h.shadowRoot.querySelector('.btn.detail');"
    "if(d){d.click(); return true} return false})()"
)
APP_STATE_JS: Final = (
    "({nav: __g.navs().length, error: !!document.querySelector("
    '\'[data-testid="stMain"] [data-testid="stAlertContentError"]\')})'
)


def _q(text: str) -> str:
    """JS 글자 따옴표 — 한글을 그대로 둔다(계획 · 뼈대 글자만 여기 잇는다. 매개값은 인자로)."""
    return json.dumps(text, ensure_ascii=False)


@dataclass(frozen=True)
class LastEdit:
    """가장 최근 `grid_edit` 이 고친 칸 — `EDIT_CELL` · `EDIT_ROW` 가 찍을 때 다시 잰다."""

    grid: str
    col: int
    row: int


def _named(name: str, arg: str | None, last_edit: LastEdit | None) -> str:
    plain: dict[str, str] = {
        "SIDEBAR_SCEN": "__g.sidebarScen()",
        "SIDEBAR_BADGE": "__g.sidebarBadge()",
        "SIDEBAR_PENDING": "__g.sidebarPending()",
        "SIDEBAR_FOOTER": f"__g.key({_q(APP_CREDITS_KEY)})",
        "HEADER_BAND": "__g.headerBand()",
        "PAGE_TITLE": "__g.pageTitle()",
        "DIALOG": "__g.dialog()",
        "DIALOG_SECTIONS": (
            "(__g.dialog() && __g.dialog().querySelector('[data-testid=\"stButtonGroup\"]'))"
        ),
        "GRID": "__g.grid()",
        "LAST_GRID": "__g.lastGrid()",
        "LOB_CHART": "__g.lobChart()",
        "LOB_BN_BARS": "__g.lobBnBars()",
        "KEY_PROCESS_GRID": "__g.keyProcessGrid()",
        "DETAIL_BN": "__g.detailBn()",
        "BN_CELL": "__g.bnCell()",
        "PROC_HEAD": "__g.procHead()",
        "PROC_MONTH_CANVAS": "__g.procMonthCanvas()",
        "PF_TILES": "__g.pfTiles()",
    }
    if name in plain:
        return plain[name]
    if name in ("EDIT_CELL", "EDIT_ROW"):
        if last_edit is None:
            return "null"
        grid = target_expr(last_edit.grid, None)
        if name == "EDIT_CELL":
            return f"__g.cellRect({grid}, {last_edit.col}, {last_edit.row})"
        return f"__g.editRow({grid}, {last_edit.row})"
    assert arg is not None
    with_arg: dict[str, Callable[[str], str]] = {
        "MAIN_LINK": lambda a: f"__g.mainLink({_q(a)})",
        "MAIN_ALERT": lambda a: f"__g.mainAlert({_q(a)})",
        "HEAD_BOX": lambda a: f"__g.headBox({_q(a)})",
        "WIDGET": lambda a: f"__g.fillWidget({_q(a)})",
        "FORM_OF": lambda a: f"__g.formOf({_q(a)})",
        "EXPANDER": lambda a: f"__g.expander({_q(a)})",
        "KEY_BUTTON": lambda a: f"__g.keyButton({_q(a)})",
        "GRID_COLUMN": lambda a: f"__g.gridColumn(__g.grid(), {_q(a)})",
        "LOB_LABEL": lambda a: f"__g.lobLabel({_q(a)})",
        "LOB_ROW": lambda a: f"__g.lobRow({_q(a)})",
    }
    return with_arg[name](arg)


# 생성기가 구현하는 `named:` 이름 — `page_guide_core.NAMED_TARGETS` 와 같아야 한다(시험이 본다).
IMPLEMENTED_NAMED: Final = frozenset(core.NAMED_TARGETS)


def split_target(word: str) -> tuple[str, str, str | None]:
    """`종류:글자` → (종류, 이름 또는 글자, 괄호 안 글자)."""
    kind, _, rest = word.partition(":")
    if kind != "named":
        return kind, rest, None
    name, paren, tail = rest.partition("(")
    return kind, name, (tail[:-1] if paren and tail.endswith(")") else None)


def target_expr(word: str | Sequence[str], last_edit: LastEdit | None) -> str:
    """표적 낱말 → 요소나 사각형(배열)을 돌려주는 JS 식. 배열은 합집합 사각형이다."""
    if not isinstance(word, str):
        return "__g.union([" + ", ".join(target_expr(item, last_edit) for item in word) + "])"
    kind, text, arg = split_target(word)
    if kind == "key":
        return f"__g.key({_q(text)})"
    if kind == "button":
        return f"__g.dialogFirst(s=>__g.btn({_q(text)}, s))"
    if kind == "tab":
        return f"__g.dialogFirst(s=>__g.tab({_q(text)}, s))"
    if kind == "nav":
        return f"__g.nav({_q(text)})"
    if kind == "text":
        return f"__g.textBox({_q(text)})"
    if kind == "named" and text in core.NAMED_TARGETS:
        return _named(text, arg, last_edit)
    raise ValueError(f"모르는 표적 낱말 종류: {kind}")


class CaptureError(RuntimeError):
    """동작 · 표적이 서지 않았다. 문구는 고정 글자만 — 화면 글자 · 매개값을 담지 않는다."""


class AppProblem(RuntimeError):
    """앱이 오류 화면(부트스트랩 실패)이다 — 상태를 더 돌지 않는다."""


def _number_text(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:.6g}"


class Camera:
    """브라우저 세션 하나를 계획의 낱말로 몬다. 상태마다 `capture` 가 한 장을 찍는다."""

    def __init__(
        self,
        browser: Any,
        base_url: str,
        *,
        viewport: tuple[int, int],
        scale: float,
        mask: Sequence[str],
        needles: Sequence[str],
    ) -> None:
        self.browser = browser
        self.base_url = base_url
        self.viewport = viewport
        self.scale = scale
        self.mask_words = list(mask)
        self.needles = [needle for needle in needles if needle]
        self.context: Any = None
        self.page: Any = None
        self.last_edit: LastEdit | None = None
        self.where = ""
        self.checked_app = False

    # -- 세션

    def open_session(self) -> None:
        """새 세션(새 브라우저 문맥) — 세션 상태 · 열린 팝업 · 편집이 모두 비워진다."""
        self.close()
        self.context = self.browser.new_context(
            viewport={"width": self.viewport[0], "height": self.viewport[1]},
            device_scale_factor=self.scale,
            locale="ko-KR",
            color_scheme="light",
            reduced_motion="reduce",
        )
        self.context.set_default_timeout(ACTION_TIMEOUT_MS)
        self.context.add_init_script(STYLE_JS)
        self.context.add_init_script(HELPERS_JS)
        self.page = self.context.new_page()
        self.last_edit = None

    def close(self) -> None:
        if self.context is not None:
            try:
                self.context.close()
            except Exception:  # noqa: BLE001 — 닫기 실패는 다음 문맥에 영향이 없다
                pass
        self.context = None
        self.page = None

    # -- 페이지 쪽

    def js(self, expression: str, arg: Any = None) -> Any:
        return self.page.evaluate(f"(arg) => {{ {HELPERS_JS}; return ({expression}); }}", arg)

    def safe(self, expression: str, arg: Any = None) -> Any:
        """다시 읽는 중(첫 방문 테마 새로고침)에 끊긴 evaluate 는 None 으로."""
        try:
            return self.js(expression, arg)
        except Exception:  # noqa: BLE001 — 다음 회차에 다시 읽는다
            return None

    def wait_for(
        self, read: Callable[[], Any], accept: Callable[[Any], bool], timeout: float, what: str
    ) -> Any:
        deadline = time.monotonic() + timeout
        value = read()
        while not accept(value):
            if time.monotonic() > deadline:
                raise CaptureError(f"기다림 넘음 — {what}")
            time.sleep(0.25)
            value = read()
        return value

    def settle(self, timeout: float = SETTLE_TIMEOUT_SECONDS) -> None:
        """회차가 쉴 때까지 — 연속 세 번(약 0.75초) `notRunning` 이면 쉼으로 본다."""
        time.sleep(0.35)
        deadline = time.monotonic() + timeout
        quiet = 0
        while time.monotonic() < deadline:
            quiet = quiet + 1 if self.safe("__g.idle()") == "notRunning" else 0
            if quiet >= 3:
                time.sleep(0.6)
                return
            time.sleep(0.25)
        raise CaptureError("앱이 계속 도는 중")

    def click_at(self, rect: Sequence[float]) -> None:
        x, y = rect[0] + rect[2] / 2, rect[1] + rect[3] / 2
        self.page.mouse.move(x, y)
        self.page.mouse.click(x, y)

    def click(self, expression: str) -> None:
        """표적을 화면 안으로 굴려 넣고(굴림이 멈출 때까지 기다려) 가운데를 누른다."""
        rect = self.js(f"__g.prepClick({expression})")
        if rect is None:
            raise CaptureError("누를 표적 없음")
        for _ in range(20):
            time.sleep(0.12)
            now = self.js(f"__g.rectNow({expression})")
            if now == rect:
                break
            rect = now if now is not None else rect
        self.click_at(rect)

    def park(self) -> None:
        self.page.mouse.move(self.viewport[0] - 4, self.viewport[1] - 4)

    def expr(self, word: str | Sequence[str]) -> str:
        return target_expr(word, self.last_edit)

    # -- 동작

    def run_ops(self, state_id: str, ops: Sequence[Mapping[str, Any]]) -> None:
        handlers: dict[str, Callable[[Mapping[str, Any]], None]] = {
            "enter_app": self._enter_app,
            "nav": self._nav,
            "tab": self._tab,
            "click": self._click,
            "fill": self._fill,
            "key": self._key,
            "scroll": self._scroll,
            "open_popup": self._open_popup,
            "grid_edit": self._grid_edit,
            "wait_idle": self._wait_idle,
        }
        for index, op in enumerate(ops):
            self.where = f"{state_id}.ops.{index} {op['op']}"
            handlers[str(op["op"])](op)

    def _enter_app(self, op: Mapping[str, Any]) -> None:
        try:
            self.page.goto(
                self.base_url, wait_until="domcontentloaded", timeout=INTRO_TIMEOUT_SECONDS * 1000
            )
        except Exception:  # noqa: BLE001 — 첫 방문 새로고침이 이동을 끊을 수 있다. 아래가 기다린다
            pass
        state = self.wait_for(
            lambda: self.safe(INTRO_STATE_JS),
            lambda value: value in ("ready", "hidden"),
            INTRO_TIMEOUT_SECONDS,
            "입장 화면",
        )
        if state == "hidden":
            # 숨은 채 생겨 곧 서는 호스트와 가르려고 잠깐 더 본다.
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline and state != "ready":
                time.sleep(0.25)
                state = self.safe(INTRO_STATE_JS)
        if state == "ready":
            self.js(INTRO_CLICK_JS)
        self.wait_for(
            lambda: self.safe(INTRO_STATE_JS),
            lambda value: value in ("hidden", "none"),
            30,
            "입장 화면 걷힘",
        )
        self.settle()
        time.sleep(2.0)
        if not self.checked_app:
            facts = self.wait_for(
                lambda: self.safe(APP_STATE_JS) or {"nav": 0, "error": False},
                lambda value: value["nav"] > 0 or value["error"],
                15,
                "사이드바 메뉴",
            )
            if facts["nav"] == 0:
                raise AppProblem("앱 오류 화면")
            self.checked_app = True

    def _nav(self, op: Mapping[str, Any]) -> None:
        link = f"__g.nav({_q(str(op['text']))})"
        for _ in range(3):
            self.js("__g.navIntoView(arg)", str(op["text"]))
            time.sleep(0.2)
            if self.js(f"__g.hit({link})") == "ok":
                break
            summary = self.js("__g.openGroupOf(arg)", str(op["text"]))
            if not summary:
                break
            self.click_at(summary)
            self.settle()
            time.sleep(0.6)
        self.click(link)
        self.settle()
        time.sleep(0.8)

    def _tab(self, op: Mapping[str, Any]) -> None:
        scopes = {
            "main": "__g.main()",
            "sidebar": "document.querySelector('[data-testid=\"stSidebar\"]')",
            "dialog": "__g.dialog()",
        }
        scope = scopes.get(str(op.get("scope", "")), "null")
        tab = f"__g.tab({_q(str(op['text']))}, {scope})"
        for _ in range(3):
            if self.js(f"__g.hit({tab})") != "ok":
                self.js("__g.mainTop()")
                time.sleep(0.3)
            self.click(tab)
            self.settle()
            if (
                self.js(
                    f"(()=>{{const t={tab}; return t ? t.getAttribute('aria-selected') : null}})()"
                )
                == "true"
            ):
                time.sleep(0.6)
                return
            time.sleep(0.5)
        raise CaptureError("탭이 골라지지 않음")

    def _click(self, op: Mapping[str, Any]) -> None:
        target = self.expr(op["target"])
        if self.js(f"__g.rectNow({target})") is None:
            if op.get("optional"):
                return
            raise CaptureError("누를 표적 없음")
        self.click(target)
        self.settle()
        time.sleep(0.5)

    def _leave_input(self) -> None:
        """입력칸에서 빠져 회차가 값을 받게 한다. 팝업은 포커스를 가두므로 팝업 안 글을 누른다."""
        if self.js("!!__g.dialogQuiet()"):
            self.click("__g.dialogQuiet()")
        else:
            self.js("__g.blur()")

    def _fill(self, op: Mapping[str, Any]) -> None:
        label = str(op["label"])
        value = str(op["value"])
        kind = self.js("__g.widgetKind(arg)", label)
        if kind is None:
            raise CaptureError("입력칸 없음")
        self.click(f"__g.fillInput({_q(label)})")
        time.sleep(0.2)
        keyboard = self.page.keyboard
        if op.get("clear"):
            keyboard.press("Control+a")
            keyboard.press("Backspace")
        keyboard.insert_text(value)
        if kind in ("stSelectbox", "stMultiSelect"):
            time.sleep(0.8)
            option = self.js("__g.optionFor(arg)", value)
            if option is None:
                keyboard.press("Escape")
                raise CaptureError("고를 값 없음")
            self.click_at(option)
        else:
            time.sleep(0.2)
            self._leave_input()
        self.settle()
        time.sleep(0.4)

    def _key(self, op: Mapping[str, Any]) -> None:
        self.page.keyboard.press(str(op["key"]))
        time.sleep(0.3)
        if not self.js("!!__g.dialog()"):
            self.js("__g.blur()")
        self.settle()

    def _scroll(self, op: Mapping[str, Any]) -> None:
        if op.get("to") == "top":
            self.js("__g.mainTop()")
        else:
            options = {"block": op.get("block", "center"), "offset": int(op.get("offset", 0))}
            if not self.js(f"__g.scrollTo({self.expr(op['target'])}, arg)", options):
                raise CaptureError("굴릴 표적 없음")
        time.sleep(0.6)

    def _open_popup(self, op: Mapping[str, Any]) -> None:
        self.click(f"__g.popupButton({self.expr(op['target'])})")
        self.wait_for(lambda: self.safe("!!__g.dialog()"), lambda v: v is True, 20, "팝업")
        self.settle()
        time.sleep(0.8)
        section = op.get("section")
        if section is None:
            return
        state = self.js("__g.sectionState(arg)", str(section))
        if state is None:
            raise CaptureError("팝업 구획 없음")
        if state != "active":
            # 구획 고르기는 필수 선택(required)이라 이미 고른 것을 눌러도 풀리지 않는다.
            self.click(f"__g.sectionButton({_q(str(section))})")
            self.settle()
            time.sleep(0.6)

    def _wait_idle(self, op: Mapping[str, Any]) -> None:
        self.settle(timeout=float(op.get("seconds", SETTLE_TIMEOUT_SECONDS)))

    def _grid_edit(self, op: Mapping[str, Any]) -> None:
        grid_word = op["grid"]
        grid = self.expr(grid_word)
        spec = {"row": op["row"], "rowColumn": op.get("row_column"), "column": op["column"]}
        cell = self.js(f"__g.locateCell({grid}, arg)", spec)
        if cell is None:
            raise CaptureError("고칠 칸 없음")
        if self.js(f"__g.revealCell({grid}, arg.col, arg.row)", cell):
            time.sleep(0.6)
        rect = self.js(f"__g.cellRect({grid}, arg.col, arg.row)", cell)
        if rect is None:
            raise CaptureError("고칠 칸 없음")
        if not self.js("__g.inView(arg)", rect):
            self.js(
                f"(()=>{{const e={grid}; if(e) e.scrollIntoView({{block:'center'}}); return 1}})()"
            )
            time.sleep(0.6)
            rect = self.js(f"__g.cellRect({grid}, arg.col, arg.row)", cell)
        if isinstance(grid_word, str):
            self.last_edit = LastEdit(grid_word, int(cell["col"]), int(cell["row"]))
        if isinstance(op.get("value"), bool):
            self._toggle_cell(grid, cell, rect, bool(op["value"]))
            return
        if "delta" in op:
            current = self.js(f"__g.cellText({grid}, arg.col, arg.row)", cell)
            try:
                number = float(str(current).replace(",", ""))
            except ValueError:
                raise CaptureError("숫자 칸이 아님") from None
            new_text = _number_text(number + float(op["delta"]))
        else:
            new_text = str(op["value"])
        x, y = rect[0] + rect[2] / 2, rect[1] + rect[3] / 2
        self.click_at(rect)
        time.sleep(0.4)
        self.page.mouse.dblclick(x, y)
        time.sleep(0.6)
        active = self.js("(()=>{const a=document.activeElement; return a ? a.tagName : ''})()")
        keyboard = self.page.keyboard
        if active in ("INPUT", "TEXTAREA"):
            keyboard.press("Control+a")
            keyboard.insert_text(new_text)
        else:
            self.click_at(rect)
            time.sleep(0.3)
            keyboard.type(new_text)
        time.sleep(0.3)
        keyboard.press("Enter")
        self.settle()
        time.sleep(0.8)

    def _toggle_cell(
        self, grid: str, cell: Mapping[str, Any], rect: Sequence[float], wanted: bool
    ) -> None:
        for attempt in range(3):
            if attempt < 2:
                self.click_at(rect)
            else:
                self.page.keyboard.press("Space")
            self.settle()
            time.sleep(1.0)
            if self.js(f"__g.cellData({grid}, arg.col, arg.row)", cell) is wanted:
                return
        raise CaptureError("체크 칸이 바뀌지 않음")

    # -- 찍기

    def measure(self, word: str | Sequence[str]) -> list[float] | None:
        try:
            rect = self.js(f"__g.asRect({self.expr(word)})")
        except Exception:  # noqa: BLE001 — 못 찾은 표적이다
            return None
        return [float(value) for value in rect] if rect else None

    def mask(self) -> None:
        """가릴 것을 감추고, 감춘 뒤에도 담당 조직 · 문의처 글이 보이면 찍지 않는다."""
        words = ", ".join(self.expr(word) for word in self.mask_words)
        self.js(f"__g.hideAll([{words}], arg)", self.needles)
        if self.needles and self.js("__g.shows(arg)", self.needles):
            raise CaptureError("가림 실패 — 꼬리말 글이 남음")

    def capture(self, state: Mapping[str, Any], folder: Path) -> core.ShotState:
        state_id = str(state["id"])
        self.where = f"{state_id} 찍기"
        self.settle()
        time.sleep(0.8)
        self.mask()
        self.park()
        time.sleep(0.35)
        targets: dict[str, list[float]] = {}
        missing: list[str] = []
        for name, word in state["targets"].items():
            rect = self.measure(word)
            if rect and rect[2] > 0 and rect[3] > 0:
                targets[str(name)] = rect
            else:
                missing.append(str(name))
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{state_id}.png"
        self.page.screenshot(path=str(path), type="png")
        return core.ShotState(
            id=state_id,
            image=path,
            targets=targets,
            missing=missing,
            date=datetime.date.today().isoformat(),
            scale=self.scale,
        )


class Shooter(Protocol):
    """`run_states` 가 쓰는 만큼의 촬영기 — `Camera` 이고, 시험은 가짜를 넣는다."""

    where: str

    def open_session(self) -> None: ...

    def run_ops(self, state_id: str, ops: Sequence[Mapping[str, Any]]) -> None: ...

    def capture(self, state: Mapping[str, Any], folder: Path) -> core.ShotState: ...


@dataclass
class StateOutcome:
    state_id: str
    result: str  # captured | failed | skipped | left
    found: int = 0
    total: int = 0
    seconds: float = 0.0
    failure: str | None = None


def run_states(
    camera: Shooter,
    skeleton: core.Skeleton,
    params: Mapping[str, str | int],
    *,
    wanted: Sequence[str],
    skip: Sequence[str],
    deadline: float,
    folder: Path,
    on_state: Callable[[StateOutcome, core.ShotState | None], None],
) -> None:
    """계획 차례대로 상태를 연다. 앞 상태가 바로 앞에 찍은 상태가 아니면 새 세션을 열고 사슬을
    뿌리부터 다시 돈다. `skip` 은 건너뛰고(쓰기 등급), 예산을 넘으면 남은 상태는 `left` 다."""
    previous: str | None = None
    for state in skeleton.states:
        state_id = str(state["id"])
        if state_id not in wanted:
            continue
        total = len(state["targets"])
        if state_id in skip:
            on_state(StateOutcome(state_id, "skipped", total=total), None)
            continue
        if time.monotonic() > deadline:
            on_state(StateOutcome(state_id, "left", total=total), None)
            continue
        began = time.monotonic()
        try:
            if previous is not None and state.get("from") == previous:
                camera.run_ops(state_id, core.bind_params(state["ops"], params))
            else:
                camera.open_session()
                for link in skeleton.chain(state_id):
                    camera.run_ops(link, core.bind_params(skeleton.state(link)["ops"], params))
            shot = camera.capture(state, folder)
        except AppProblem:
            raise
        except Exception as exc:  # noqa: BLE001 — 상태 하나가 끊겨도 나머지는 돈다. 종류만 남긴다
            failure = f"{camera.where} {type(exc).__name__}"
            shot = core.ShotState(id=state_id, image=None, targets={}, failed=failure)
            previous = None
            on_state(
                StateOutcome(
                    state_id,
                    "failed",
                    total=total,
                    seconds=time.monotonic() - began,
                    failure=failure,
                ),
                shot,
            )
            continue
        previous = state_id
        on_state(
            StateOutcome(
                state_id,
                "captured",
                found=len(shot.targets),
                total=total,
                seconds=time.monotonic() - began,
            ),
            shot,
        )
