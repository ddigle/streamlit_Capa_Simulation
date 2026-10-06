# Purpose: 헤더 툴바 iframe 내용이 회차마다 같고 테마 키 규칙이 앱 키 하나를 따르는지 고정한다.

import re

import pytest
from streamlit.elements.html import _html_only_style_tags

from capa_simulation.components import intro_summary, page_guide, print_button, theme_toggle
from capa_simulation.components.intro_summary import summary_label_script
from capa_simulation.components.page_guide import guide_toolbar_script
from capa_simulation.components.print_button import print_toolbar_script
from capa_simulation.design import theme


def _render(monkeypatch: pytest.MonkeyPatch) -> tuple[list[str], list[object], list[str]]:
    """`st.iframe`·`st.html` 호출을 가로채 내용·높이·스타일을 모은다."""
    frames: list[str] = []
    heights: list[object] = []
    styles: list[str] = []

    def fake_iframe(src: str, **kwargs: object) -> None:
        frames.append(src)
        heights.append(kwargs.get("height"))

    monkeypatch.setattr(theme_toggle.st, "iframe", fake_iframe)
    monkeypatch.setattr(theme_toggle.st, "html", lambda body, **_kwargs: styles.append(body))
    return frames, heights, styles


def test_toolbar_iframe_is_identical_whatever_theme_python_resolved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """내용이 바뀌면 Streamlit 이 iframe 을 새로 만들고, 옛 iframe 이 만든 테마·Guide 버튼의
    `onclick` 은 떨어져 나간 문서의 함수라 브라우저가 부르지 않는다(2026-10-01 브라우저 실측).
    파이썬이 푼 테마는 화면 이동 뒤 조회 인자가 빠지면 바뀔 수 있으므로 내용에 싣지 않는다.
    """
    # 테마는 스레드에 담긴다. 끝나면 되돌려 뒤 테스트의 색이 어두워지지 않게 한다.
    monkeypatch.setattr(theme._LOCAL, "mode", "light", raising=False)
    frames, _, _ = _render(monkeypatch)

    for mode in ("light", "dark"):
        monkeypatch.setattr(theme, "_read_client_mode", lambda mode=mode: mode)
        theme.begin_run()
        theme_toggle.render_theme_toggle(
            extra_scripts=(guide_toolbar_script(), summary_label_script(), print_toolbar_script())
        )

    assert len(frames) == 2
    assert frames[0] == frames[1]


def test_toolbar_iframe_is_collapsed_to_zero_without_the_deprecated_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`st.iframe` 은 높이 0 을 오류로 막는다 — 1px 로 띄우고 CSS 로 접는다.

    폐기 예고가 회차마다 터미널에 찍히던 `components.v1.html` 로 돌아가지 않는다. 접는 규칙은
    스타일만 든 `st.html` 이라 본문 자리를 먹지 않고, iframe 내용에 든 버튼 id 로 그 iframe 만
    고른다 — id 를 바꾸고 규칙을 놓치면 본문이 1px 내려간다.
    """
    frames, heights, styles = _render(monkeypatch)

    theme_toggle.render_theme_toggle(extra_scripts=(guide_toolbar_script(),))

    assert heights == [theme_toggle._FRAME_HEIGHT_PX]
    assert isinstance(heights[0], int) and heights[0] > 0
    assert styles == [theme_toggle._COLLAPSE_STYLE]
    assert _html_only_style_tags(styles[0])
    assert f'srcdoc*="{theme_toggle.THEME_BUTTON_ID}"' in styles[0]
    assert theme_toggle.THEME_BUTTON_ID in frames[0]
    assert "components" not in vars(theme_toggle)


def _function_body(js: str, name: str) -> str:
    start = js.index(f"function {name}(")
    end = js.index("\n  }\n", start)
    return js[start:end]


def test_the_key_rule_is_the_first_script_and_keeps_one_app_wide_choice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """고른 테마의 정본은 앱 키 하나다. Streamlit 키는 경로마다 따로라 그것만 보면 한 페이지에서
    고른 테마가 다른 페이지에 닿지 않는다(하위 페이지 Dark 가 두 번 새로고침하고 밝게 끝났다).

    규칙은 iframe 맨 앞 스크립트 한 벌이고, 버튼·Guide·사이드바 라벨·Print 스크립트가 모두 그것을
    부른다.
    """
    frames, _, _ = _render(monkeypatch)
    theme_toggle.render_theme_toggle(
        extra_scripts=(guide_toolbar_script(), summary_label_script(), print_toolbar_script())
    )
    frame = frames[0]
    rule = theme_toggle.THEME_RULE_SCRIPT

    assert frame.startswith(f"<script>{rule}</script>")
    assert frame.index(rule) < frame.index(theme_toggle.THEME_BUTTON_ID)
    for constant in (
        theme_toggle.THEME_APP_KEY,
        theme_toggle.THEME_SYNC_PREFIX,
        theme_toggle.THEME_RELOAD_GUARD_PREFIX,
        theme_toggle.THEME_STORAGE_PREFIX,
        theme_toggle.THEME_STORAGE_SUFFIX,
    ):
        assert f'"{constant}"' in rule, constant
    assert "%(" not in rule
    assert theme_toggle.THEME_APP_KEY != theme_toggle.THEME_SYNC_PREFIX
    assert not theme_toggle.THEME_APP_KEY.startswith(theme_toggle.THEME_STORAGE_PREFIX)
    # 처음이면 밝게(2026-10-01 결정) — 앱 키도 경로 키도 없을 때의 마지막 값이다.
    assert '|| here || "Light";' in rule
    # 고른 값은 Light·Dark 뿐이다. ⋮ 메뉴(감췄지만 남긴 안전망)의 "System" 은 고른 값이 아니다.
    assert 'value === "Dark" || value === "Light"' in rule


def test_the_storage_key_is_computed_from_the_path_at_the_moment_of_use() -> None:
    """이 iframe 은 앱 안에서 페이지를 옮겨도 남는다. 처음 실행 때 경로로 키를 만들어 두면 다른
    페이지에서 누른 버튼이 엉뚱한 경로의 키에 적는다 — 경로는 쓰는 순간 `location.pathname` 으로
    읽는다.
    """
    rule = theme_toggle.THEME_RULE_SCRIPT
    # 규칙의 바깥(모듈 첫머리)에는 경로가 없다. 경로를 읽는 것은 창을 받는 함수 안뿐이다.
    preamble = rule[: rule.index("function ")]
    assert "pathname" not in preamble
    for name in ("resolve", "write", "sync", "choose"):
        assert "win.location.pathname" in _function_body(rule, name), name
    assert "location.pathname" not in theme_toggle._SCRIPT
    assert not re.search(r"var\s+KEY\s*=", theme_toggle._SCRIPT)
    # 열릴 때는 맞춰 적고(sync), 누를 때는 그 순간 창으로 적는다(choose).
    place = _function_body(theme_toggle._SCRIPT, "place")
    assert "capaTheme.sync(parentWindow)" in place
    assert "capaTheme.choose(parentWindow, next)" in place
    # 지금 경로의 Streamlit 키를 고쳐 적었거나 조회 인자가 다르면 **한 번** 새로고침한다.
    assert "if (state.stale || paramChanged) {" in place
    # 못 적었으면 새로고침하지 않는다 — 쓰기 실패가 새로고침 반복이 되지 않게.
    assert "state.stale = false" in _function_body(rule, "sync")


def test_menu_choices_are_adopted_only_against_our_own_sync_mark() -> None:
    """⋮ 메뉴는 지금 경로의 Streamlit 키만 고친다. 그 키가 우리가 마지막으로 적은 표지와 다를 때만
    사람이 바꾼 것으로 보고 앱 키로 받아들인다 — 표지가 없는 옛 경로 값은 받아들이지 않는다.

    메뉴는 CSS 로 감춘다(`app_header.py`). 이 규칙은 판올림으로 그 감춤이 풀려 메뉴가 다시 보일 때를
    위한 안전망으로 남긴다.
    """
    rule = theme_toggle.THEME_RULE_SCRIPT
    menu = _function_body(rule, "menuChoice")
    assert "SYNC_PREFIX + paths[index]" in menu
    assert "if (mark && value && value !== mark) return value;" in menu
    # 메뉴로 바꾼 값이 앱 키보다 앞선다(앱 키는 그보다 오래된 선택이다).
    assert "menuChoice(storage, state.paths) || pick(storage.getItem(APP_KEY))" in rule
    # 적을 때는 표지도 함께 적는다.
    assert "storage.setItem(SYNC_PREFIX + paths[index], choice);" in _function_body(rule, "write")


def test_only_paths_carrying_our_sync_mark_are_touched() -> None:
    """다른 경로는 우리 표지가 있는 것만 고른다. Streamlit 테마 키 전부를 훑으면 한 출처의 다른
    Streamlit 앱(`/proxy/<포트>/`)의 키를 덮어쓰고, 그 앱의 ⋮ 메뉴 선택을 앱 키로 받아들인다.
    """
    known = _function_body(theme_toggle.THEME_RULE_SCRIPT, "knownPaths")
    assert "var paths = [current];" in known
    assert "key.indexOf(SYNC_PREFIX) !== 0" in known
    assert "key.slice(SYNC_PREFIX.length)" in known
    assert "indexOf(PREFIX)" not in known
    assert "SUFFIX" not in known


def test_a_key_driven_reload_happens_at_most_once_per_tab() -> None:
    """Streamlit 은 문서가 열릴 때마다 지금 경로의 키를 제 값으로 다시 적는다. 그 값이 우리가 적은
    것과 어긋나기 시작하면(판올림·`[theme.dark]` 없는 설정) 「어긋나면 새로고침」은 끝없이 돈다.
    새로고침 전에 탭 표지를 남기고, 표지가 있으면 다시 새로고침하지 않는다. `resolve` 가 표지를
    보므로 입장 화면의 예측도 같다.
    """
    rule = theme_toggle.THEME_RULE_SCRIPT
    assert "win.sessionStorage.getItem(GUARD_PREFIX + path) !== null" in _function_body(
        rule, "reloadedOnce"
    )
    assert "state.stale = state.mismatch && !reloadedOnce(win, path);" in _function_body(
        rule, "resolve"
    )
    sync = _function_body(rule, "sync")
    assert "var guard = GUARD_PREFIX + win.location.pathname;" in sync
    # 새로고침할 때 표지를 남기고, 못 남기면 새로고침하지 않는다. 키가 맞으면 지운다.
    assert 'if (state.stale) win.sessionStorage.setItem(guard, "1");' in sync
    assert "else if (!state.mismatch) win.sessionStorage.removeItem(guard);" in sync
    # 쓰기 실패와 표지 실패 둘 다 새로고침을 거둔다.
    assert sync.count("} catch (error) { state.stale = false; }") == 2
    # 표지는 탭 단위(`sessionStorage`)다 — `localStorage` 에 두면 다른 탭의 새로고침을 막는다.
    assert "localStorage" not in _function_body(rule, "reloadedOnce")
    assert theme_toggle.THEME_RELOAD_GUARD_PREFIX not in (
        theme_toggle.THEME_APP_KEY,
        theme_toggle.THEME_SYNC_PREFIX,
    )


def test_toolbar_readers_use_the_shared_rule_instead_of_their_own_key() -> None:
    """Guide·Print 단추와 사이드바 라벨의 색도 같은 규칙으로 고른다. 저장 키를 따로 두면 규칙이
    갈라진다."""
    for script in (
        guide_toolbar_script(),
        summary_label_script(),
        print_toolbar_script(),
        page_guide._SCRIPT,
    ):
        assert theme_toggle.THEME_STORAGE_PREFIX not in script
        assert "localStorage" not in script
        assert "capaTheme.resolve(parentWindow)" in script
    assert "THEME_STORAGE_PREFIX" not in vars(intro_summary)
    assert "THEME_STORAGE_PREFIX" not in vars(print_button)


def test_toolbar_scripts_take_the_slot_and_button_id_from_one_place() -> None:
    """툴바 슬롯·사이드바 머리칸·테마 버튼 id 는 `theme_toggle` 한 곳에 있다. Guide·Print·사이드바
    라벨 원문이 값을 직접 적으면 판올림에서 한 곳만 고쳐 다른 단추가 조용히 사라진다."""
    templates = (page_guide._SCRIPT, intro_summary._LABEL_SCRIPT, print_button._SCRIPT)
    for template in templates:
        assert theme_toggle.TOOLBAR_SLOT not in template
        assert theme_toggle.SIDEBAR_HEADER_SLOT not in template
        assert theme_toggle.THEME_BUTTON_ID not in template
        assert "querySelector('%(slot)s')" in template
    assert 'getElementById("%(theme)s")' in page_guide._SCRIPT
    assert 'getElementById("%(theme)s")' in print_button._SCRIPT
    for script in (guide_toolbar_script(), print_toolbar_script()):
        assert f"querySelector('{theme_toggle.TOOLBAR_SLOT}')" in script
        assert f'getElementById("{theme_toggle.THEME_BUTTON_ID}")' in script
    # 사이드바 라벨은 툴바가 아니라 사이드바 머리칸에 선다.
    label = summary_label_script()
    assert f"querySelector('{theme_toggle.SIDEBAR_HEADER_SLOT}')" in label
    assert theme_toggle.TOOLBAR_SLOT not in label


def test_the_theme_button_asks_before_a_reload_drops_unsaved_edits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """테마 전환은 새로고침(새 세션)이라 적용만 하고 저장하지 않은 편집이 말없이 사라졌다
    (2026-10-05 E2E). 표지가 있으면 누른 순간 먼저 묻는다.

    표지는 iframe 이 아니라 늘 그리는 스타일 끝의 CSS 변수다 — iframe 내용은 회차마다 같아야
    한다(위 검사). 표지만 든 스타일은 본문 자리를 먹지 않는다.
    """
    frames, _, _ = _render(monkeypatch)
    theme_toggle.render_theme_toggle()

    script = frames[0]
    variable = theme_toggle.UNSAVED_EDITS_CSS_VARIABLE
    click = script[script.index("button.onclick") :]
    assert click.index("confirm(") < click.index("capaTheme.choose(")
    assert variable in click
    assert theme_toggle.UNSAVED_EDITS_CONFIRM in click

    marker = theme_toggle.unsaved_edits_marker(True)
    assert f"{variable}:1" in marker
    assert _html_only_style_tags(marker)
    assert theme_toggle.unsaved_edits_marker(False) == ""


def test_the_print_button_sits_right_of_the_theme_button_and_waits_for_an_idle_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """⋮ 메뉴를 감추며 그 안의 Print 를 툴바 단추로 옮겼다(2026-10-05 사용자 결정). Streamlit 메뉴의
    Print 처럼 스크립트가 도는 동안은 500ms 마다 다시 보고, 멈췄을 때 앱 창의 `print()` 를 부른다 —
    반쯤 그려진 화면을 찍지 않는다. 같은 iframe 에 실려도 내용은 회차마다 같아야 한다.
    """
    script = print_toolbar_script()
    assert "%(" not in script
    assert f'button.id = "{print_button.BUTTON_ID}";' in script
    assert 'button.setAttribute("aria-label", "인쇄");' in script
    assert 'button.textContent = "Print";' in script
    # 실행 상태를 읽어 도는 중이면 500ms 뒤에 다시 본다. 다 돌았을 때만 인쇄한다.
    wait = _function_body(script, "printWhenIdle")
    assert ".stApp[data-test-script-state]" in wait
    assert 'getAttribute("data-test-script-state")' in wait
    assert 'state === "running"' in wait
    assert "parentWindow.setTimeout(printWhenIdle, 500);" in wait
    assert wait.index("setTimeout(printWhenIdle") < wait.index("parentWindow.print()")
    # 테마 버튼 바로 오른쪽에 선다. 테마 버튼이 서기 전이면 기다려 차례가 뒤집히지 않게 한다.
    place = _function_body(script, "place")
    assert "if (!theme) return false;" in place
    assert "slot.insertBefore(button, theme.nextSibling);" in place
    # Guide 와 같은 윤곽 단추다.
    assert '"font-size:13px", "font-weight:600"' in place
    assert '"border-radius:8px"' in place
    assert '"background:transparent"' in place

    frames, _, _ = _render(monkeypatch)
    for _ in range(2):
        theme_toggle.render_theme_toggle(extra_scripts=(print_toolbar_script(),))
    assert frames[0] == frames[1]
    assert f"<script>{script}</script>" in frames[0]


def test_the_print_button_asks_first_in_the_dark_theme_and_prints_at_once_in_light() -> None:
    """인쇄는 화면 색 그대로라 어두운 테마는 검은 바탕까지 찍힌다. 어두운 테마에서 Print 를 누르면
    테마 버튼의 미저장 확인과 같은 네이티브 `confirm` 으로 먼저 묻고, 취소면 아무것도 하지 않는다
    (2026-10-06 사용자 결정). 테마는 툴바 단추들과 같은 키 규칙(`capaTheme.resolve`)으로 단추를
    세울 때 읽은 값이다 — 누르는 순간 저장소를 다시 읽으면 다른 탭에서 바꾼 테마를 이 탭 화면의
    테마로 착각한다. 밝은 테마는 묻지 않고 곧바로 기다림-인쇄로 간다.
    """
    script = print_toolbar_script()
    click = script[script.index("button.onclick") :]
    click = click[: click.index("\n    };")]

    # 어두운 테마인지는 색이 아니라 같은 키 규칙으로, 단추를 세울 때(단추 색과 같은 값) 판단한다.
    assert 'capaTheme.resolve(parentWindow).choice === "Dark"' in _function_body(script, "dark")
    assert "var isDark = dark();" in script[: script.index("button.onclick")]
    assert "dark()" not in click
    # 기다리는 중이면 다시 묻지도 않는다. 묻는 것은 어두운 테마일 때뿐이고, 취소면 그대로 끝난다.
    assert "if (waiting) return;" in click
    guard = f'if (isDark && !parentWindow.confirm("{print_button.DARK_PRINT_CONFIRM}")) return;'
    assert guard in click
    assert (
        click.index("if (waiting) return;") < click.index(guard) < click.index("printWhenIdle();")
    )
    # 확인을 거친 뒤에야 기다림 → print() 경로로 들어간다. 클릭이 print() 를 바로 부르지 않는다.
    assert "parentWindow.print()" not in click
    assert click.count("confirm(") == 1
    # 문구는 JS 문자열 안에 그대로 들어간다 — 따옴표·역슬래시·줄바꿈이 없어야 한다.
    for unsafe in ('"', "\\", "\n", "\r"):
        assert unsafe not in print_button.DARK_PRINT_CONFIRM
    assert "Light" in print_button.DARK_PRINT_CONFIRM
