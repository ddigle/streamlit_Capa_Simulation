# Purpose: VOC 화면이 해 둔 입력·펼침·삭제 확인을 지키고 같은 쓰기를 두 번 하지 않는지 검증한다.

"""VOC 화면에서 사용자가 해 둔 것이 사라지지 않는다(2026-10-01 브라우저 점검).

- 작성자 칸은 다른 화면에 갔다 와도 남는다. Streamlit 은 그리지 않은 회차의 위젯 값을 버리므로
  `persist_state` 가 없으면 돌아왔을 때 빈 칸이고, 글을 올리면 「작성자를 입력하세요.」로 막혔다.
- 편 글은 답변을 남긴 뒤에도 편 채로다. 라벨의 「답변 N」이 바뀌면 `key` 없는 상자는 새로
  만들어져 접혔다.
- 첫 답변 앞뒤로 글 상자와 답변 칸의 자리가 그대로다. 밀리면 브라우저에 옛 상자의 회색 사본이
  남았다(2026-10-05 E2E).
- 다른 글을 처리해도 체크해 둔 「삭제 확인」 옆 「글 삭제」 단추가 남고, 빠른 두 번 누름은 같은
  쓰기를 되풀이하지 않는다(쓰기는 모두 콜백 — AGENTS 9장). 두 회차에 겹쳐 오는 더블클릭도 한 번만
  쓴다(2026-10-25 E2E).
"""

import ast
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from streamlit.runtime.scriptrunner_utils.exceptions import StopException
from streamlit.runtime.state import session_state_proxy
from streamlit.runtime.state.safe_session_state import SafeSessionState
from streamlit.testing.v1 import AppTest

from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.services.voc_board import VOC_CATEGORIES

VOC_PAGE = Path(__file__).resolve().parents[1] / "app_pages" / "voc.py"
ON_VOC = "test_on_voc"
AUTHOR_KEY = "voc_author"


def _script(database_path: Path) -> str:
    """VOC 한 화면과 「다른 화면」을 세션 칸 하나로 오간다(사이드바 페이지 이동의 대역)."""
    return f"""
from collections.abc import Callable
from pathlib import Path
from typing import Any

import streamlit as st

import capa_simulation.settings as settings

settings.DUCKDB_PATH = Path({str(database_path)!r})

if st.session_state.get({ON_VOC!r}, True):
    page = Path({str(VOC_PAGE)!r})
    exec(compile(page.read_text(encoding="utf-8"), str(page), "exec"), {{"__name__": "__main__"}})
else:
    st.write("다른 화면")
"""


def _app(database_path: Path) -> AppTest:
    app = AppTest.from_string(_script(database_path), default_timeout=60).run()
    assert not app.exception
    return app


def _post(database_path: Path) -> str:
    repository = DuckDBScenarioRepository(database_path)
    repository.initialize()
    return repository.create_voc_post(
        category=VOC_CATEGORIES[0], title="펼침 확인", body="내용", author="홍길동"
    )


def _post_box(app: AppTest, key: str) -> tuple[str, bool]:
    """`key` 로 만든 글 상자의 `(라벨, 펼침)`. 상태를 추적하는 상자는 id 끝이 그 `key` 다."""
    found = [
        (str(box.label), bool(box.proto.expanded))
        for box in app.expander
        if str(box.proto.id).endswith(f"-{key}")
    ]
    assert len(found) == 1, [box.label for box in app.expander]
    return found[0]


def test_the_author_survives_a_trip_to_another_screen(tmp_path: Path) -> None:
    app = _app(tmp_path / "scenario.duckdb")
    app.text_input(key=AUTHOR_KEY).input("검증자A").run()

    app.session_state[ON_VOC] = False
    app.run()
    app.session_state[ON_VOC] = True
    app.run()

    assert not app.exception
    assert app.text_input(key=AUTHOR_KEY).value == "검증자A"


def test_an_opened_post_stays_open_after_a_reply(tmp_path: Path) -> None:
    database_path = tmp_path / "scenario.duckdb"
    post_id = _post(database_path)
    box_key = f"voc_post_expander_{post_id}"
    app = _app(database_path)
    assert _post_box(app, box_key)[1] is False

    app.text_input(key=AUTHOR_KEY).input("담당자")
    app.session_state[box_key] = True  # 사용자가 글을 편다
    app.run()
    assert _post_box(app, box_key)[1] is True

    app.text_area(key=f"voc_reply_body_{post_id}").input("확인했습니다.")
    next(button for button in app.button if button.label == "답변 남기기").click().run()

    assert not app.exception
    assert "답변을 남겼습니다." in [message.value for message in app.success]
    label, expanded = _post_box(app, box_key)
    assert label.endswith("답변 1")
    assert expanded is True

    # 알림이 사라지는 다음 회차에도(목록 위 요소가 하나 빠진다) 편 채로다.
    app.run()
    assert not app.success
    assert _post_box(app, box_key)[1] is True


def test_an_opened_post_stays_open_after_a_trip_to_another_screen(tmp_path: Path) -> None:
    database_path = tmp_path / "scenario.duckdb"
    post_id = _post(database_path)
    box_key = f"voc_post_expander_{post_id}"
    app = _app(database_path)
    app.session_state[box_key] = True
    app.run()

    app.session_state[ON_VOC] = False
    app.run()
    app.session_state[ON_VOC] = True
    app.run()

    assert _post_box(app, box_key)[1] is True


def test_the_title_and_authors_show_as_typed_not_as_markdown(tmp_path: Path) -> None:
    """제목·작성자는 마크다운으로 그려지는 글 상자 라벨·답글 caption 에서도 적은 글자 그대로다.

    escape 하지 않으면 「A~B~C」의 물결표는 취소선이 되어 사라지고 「$…$」는 수식, `![x](주소)` 는
    VOC 를 연 사람마다 그 주소를 부르는 이미지, `*익명*` 은 기울임이 되었다
    (2026-10-22 브라우저 확인).
    """
    database_path = tmp_path / "scenario.duckdb"
    repository = DuckDBScenarioRepository(database_path)
    repository.initialize()
    post_id = repository.create_voc_post(
        category=VOC_CATEGORIES[0],
        title="A~B~C 단가 $1.2 ![x](http://127.0.0.1:9/a.png)",
        body="내용",
        author="*익명*",
    )
    repository.create_voc_reply(post_id=post_id, body="확인했습니다.", author="_답변_")

    app = _app(database_path)

    label = _post_box(app, f"voc_post_expander_{post_id}")[0]
    assert (
        r"A\~B\~C 단가 \$1\.2 \!\[x\]\(http\:\/\/127\.0\.0\.1\:9\/a\.png\) · \*익명\* · " in label
    ), label
    assert "![x](" not in label
    assert label.endswith("답변 1")
    captions = [str(caption.value) for caption in app.caption]
    assert any(caption.startswith(r"\_답변\_ · ") for caption in captions), captions


def _click(app: AppTest, label: str) -> AppTest:
    return next(button for button in app.button if button.label == label).click().run()


def test_a_rejected_post_keeps_what_was_typed_and_a_saved_one_clears(tmp_path: Path) -> None:
    """작성자를 빠뜨려 거절된 글은 제목·내용을 **지우지 않는다**(2026-10-05 E2E).

    `clear_on_submit` 은 거절된 제출에도 폼을 비워 4000자까지 적은 글이 사라졌다. 올리기에
    성공한 뒤에만 비운다 — 그대로 두면 한 번 더 눌러 같은 글이 또 올라간다.
    """
    app = _app(tmp_path / "scenario.duckdb")
    app.text_input(key="voc_post_title").input("제목 A")
    app.text_area(key="voc_post_body").input("길게 적은 내용")
    _click(app, "글 올리기")

    assert "작성자를 입력하세요." in [message.value for message in app.error]
    assert app.text_input(key="voc_post_title").value == "제목 A"
    assert app.text_area(key="voc_post_body").value == "길게 적은 내용"

    app.text_input(key=AUTHOR_KEY).input("검증자A")
    _click(app, "글 올리기")

    assert not app.exception
    assert "글을 올렸습니다." in [message.value for message in app.success]
    assert app.text_input(key="voc_post_title").value == ""
    assert app.text_area(key="voc_post_body").value == ""


def test_a_rejected_reply_keeps_its_text_and_a_saved_one_clears(tmp_path: Path) -> None:
    database_path = tmp_path / "scenario.duckdb"
    post_id = _post(database_path)
    reply_key = f"voc_reply_body_{post_id}"
    app = _app(database_path)
    app.text_area(key=reply_key).input("확인했습니다.")
    _click(app, "답변 남기기")

    assert "작성자를 입력하세요." in [message.value for message in app.error]
    assert app.text_area(key=reply_key).value == "확인했습니다."

    app.text_input(key=AUTHOR_KEY).input("담당자")
    _click(app, "답변 남기기")

    assert "답변을 남겼습니다." in [message.value for message in app.success]
    assert app.text_area(key=reply_key).value == ""


def _path_of(app: AppTest, matches: Callable[[Any], bool]) -> tuple[int, ...]:
    """`matches` 에 맞는 노드 하나의 델타 경로(본문 기준 자식 번호 차례)."""
    found: list[tuple[int, ...]] = []

    def walk(node: Any, path: tuple[int, ...]) -> None:
        if matches(node):
            found.append(path)
        for index, child in getattr(node, "children", {}).items():
            walk(child, (*path, index))

    walk(app.main, ())
    assert len(found) == 1, found
    return found[0]


def test_a_first_reply_keeps_the_post_box_and_reply_form_in_place(tmp_path: Path) -> None:
    """첫 답변 앞뒤로 key 있는 글 상자와 답변 칸의 자리가 그대로다(2026-10-05 E2E).

    답변 앞 회차에는 알림·답글이 없고, 답변 회차는 맨 위 알림과 첫 답글을 더 그린다.
    그 사이 글 상자·답변 칸이 한 칸이라도 밀리면 브라우저에 옛 상자가 적은 답변을 든 회색 사본으로
    남아 새로고침 전까지 다른 페이지까지 따라왔다. 브라우저의 회색 사본은 여기서 볼 수 없으므로
    그 원인인 **자리 밀림**을 잰다.
    """
    database_path = tmp_path / "scenario.duckdb"
    post_id = _post(database_path)
    box_key = f"voc_post_expander_{post_id}"
    reply_key = f"voc_reply_body_{post_id}"
    app = _app(database_path)
    app.text_input(key=AUTHOR_KEY).input("담당자")
    app.session_state[box_key] = True
    app.run()

    def box_path() -> tuple[int, ...]:
        return _path_of(
            app,
            lambda node: node.type == "expander" and str(node.proto.id).endswith(f"-{box_key}"),
        )

    def reply_path() -> tuple[int, ...]:
        return _path_of(app, lambda node: getattr(node, "key", None) == reply_key)

    before = (box_path(), reply_path())
    app.text_area(key=reply_key).input("첫 답변")
    _click(app, "답변 남기기")

    assert not app.exception
    assert "답변을 남겼습니다." in [message.value for message in app.success]
    assert _post_box(app, box_key)[0].endswith("답변 1")
    assert (box_path(), reply_path()) == before

    app.run()  # 알림이 사라지는 다음 회차
    assert not app.success
    assert (box_path(), reply_path()) == before


def _two_posts(database_path: Path) -> tuple[str, str]:
    """글 둘을 남기고 `(위 글, 아래 글)` 을 돌려준다. 화면은 목록 차례대로 그린다."""
    repository = DuckDBScenarioRepository(database_path)
    repository.initialize()
    for title in ("아래 글", "위 글"):
        repository.create_voc_post(
            category=VOC_CATEGORIES[0], title=title, body="내용", author="홍길동"
        )
    upper, lower = (str(post_id) for post_id in repository.list_voc_posts()["post_id"])
    return upper, lower


def _posts(database_path: Path) -> list[tuple[str, bool]]:
    posts = DuckDBScenarioRepository(database_path).list_voc_posts()
    return [(str(row["title"]), bool(row["resolved"])) for _, row in posts.iterrows()]


def _delete_ready(app: AppTest, post_id: str) -> tuple[bool, int]:
    """그 글의 `(삭제 확인 체크, 「글 삭제」 단추 수)`."""
    checked = bool(app.checkbox(key=f"voc_delete_confirm_{post_id}").value)
    return checked, sum(1 for button in app.button if button.key == f"voc_delete_{post_id}")


def _reply_button(app: AppTest, post_id: str) -> Any:
    """그 글 답변 폼의 「답변 남기기」. 글마다 같은 라벨이라 폼으로 가른다."""
    return next(
        button
        for button in app.button
        if button.label == "답변 남기기"
        and str(button.proto.form_id).startswith(f"voc_reply_form_{post_id}")
    )


def test_a_checked_delete_confirm_keeps_its_button_after_acting_on_another_post(
    tmp_path: Path,
) -> None:
    """위 글에서 무엇을 해도 아래 글에 체크해 둔 「삭제 확인」 옆 「글 삭제」 단추가 남는다.

    처리를 본문에서 하고 `st.rerun()` 하면 끊긴 회차가 아직 그리지 않은 아래 글의 체크 칸 값을
    버린다 — 브라우저는 체크된 칸을 그대로 보이는데 단추가 사라졌다(AGENTS 9장 「세션 상태를 바꾸는
    조작은 콜백으로 한다」). 「답변 완료로 표시」·「답변 남기기」·「글 올리기」 셋 다 그랬다.
    """
    database_path = tmp_path / "scenario.duckdb"
    upper, lower = _two_posts(database_path)
    app = _app(database_path)
    app.text_input(key=AUTHOR_KEY).input("담당자")
    app.checkbox(key=f"voc_delete_confirm_{lower}").check().run()
    assert _delete_ready(app, lower) == (True, 1)

    app.button(key=f"voc_resolve_{upper}").click().run()

    assert not app.exception
    assert _posts(database_path) == [("위 글", True), ("아래 글", False)]
    assert _delete_ready(app, lower) == (True, 1)

    app.text_area(key=f"voc_reply_body_{upper}").input("확인했습니다.")
    _reply_button(app, upper).click().run()

    assert not app.exception
    assert "답변을 남겼습니다." in [message.value for message in app.success]
    assert app.text_area(key=f"voc_reply_body_{upper}").value == ""
    assert _delete_ready(app, lower) == (True, 1)

    app.text_input(key="voc_post_title").input("새 글")
    app.text_area(key="voc_post_body").input("새 내용")
    _click(app, "글 올리기")

    assert not app.exception
    assert "글을 올렸습니다." in [message.value for message in app.success]
    assert app.text_input(key="voc_post_title").value == ""
    assert app.text_area(key="voc_post_body").value == ""
    assert [title for title, _ in _posts(database_path)] == ["새 글", "위 글", "아래 글"]
    assert _delete_ready(app, lower) == (True, 1)


def test_the_page_never_reruns_from_its_body() -> None:
    """VOC 의 쓰기는 모두 콜백이다 — 본문 `st.rerun()` 은 위 결함을 되살린다."""
    tree = ast.parse(VOC_PAGE.read_text(encoding="utf-8"))
    reruns = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and node.attr == "rerun"
    ]
    assert reruns == []


def test_a_second_submit_of_a_posted_form_neither_posts_nor_refills(tmp_path: Path) -> None:
    """빠른 두 번 누름 — 올린 폼의 제출이 한 번 더 들어와도 같은 글을 또 올리지 않는다.

    AppTest 는 같은 순간의 두 요청을 합칠 수 없어, 누른 화면의 위젯 값을 붙잡아 두었다가 올린 뒤에
    한 번 더 보낸다(브라우저에 남은 옛 화면의 누름과 같다). 옛 화면은 올린 제목·내용을 함께 보내지만
    폼은 빈 채로 둔다.
    """
    database_path = tmp_path / "scenario.duckdb"
    app = _app(database_path)
    app.text_input(key=AUTHOR_KEY).input("검증자A")
    app.text_input(key="voc_post_title").input("제목 A")
    app.text_area(key="voc_post_body").input("내용 A")
    next(button for button in app.button if button.label == "글 올리기").click()
    pressed = app._tree.get_widget_states()
    app.run()
    assert "글을 올렸습니다." in [message.value for message in app.success]

    app._run(widget_state=pressed)

    assert not app.exception
    assert _posts(database_path) == [("제목 A", False)]
    assert not app.error
    assert app.text_input(key="voc_post_title").value == ""
    assert app.text_area(key="voc_post_body").value == ""


def test_a_second_press_of_resolve_or_reply_does_not_repeat_it(tmp_path: Path) -> None:
    """「답변 완료로 표시」를 빠르게 두 번 눌러도 되돌아가지 않고, 답변도 한 번만 남는다."""
    database_path = tmp_path / "scenario.duckdb"
    post_id = _post(database_path)
    app = _app(database_path)
    app.text_input(key=AUTHOR_KEY).input("담당자").run()
    app.button(key=f"voc_resolve_{post_id}").click()
    pressed = app._tree.get_widget_states()
    app.run()
    assert _posts(database_path) == [("펼침 확인", True)]

    app._run(widget_state=pressed)

    assert not app.exception
    assert _posts(database_path) == [("펼침 확인", True)]

    app.text_area(key=f"voc_reply_body_{post_id}").input("확인했습니다.")
    _reply_button(app, post_id).click()
    pressed = app._tree.get_widget_states()
    app.run()
    assert "답변을 남겼습니다." in [message.value for message in app.success]

    app._run(widget_state=pressed)

    assert not app.exception
    assert len(DuckDBScenarioRepository(database_path).list_voc_replies()) == 1
    assert app.text_area(key=f"voc_reply_body_{post_id}").value == ""


def test_a_second_press_of_a_finished_delete_neither_writes_nor_notifies(
    tmp_path: Path,
) -> None:
    """지우기를 끝낸 글의 누름이 한 번 더 들어와도 「글을 지웠습니다.」를 다시 알리지 않는다."""
    database_path = tmp_path / "scenario.duckdb"
    upper, lower = _two_posts(database_path)
    app = _app(database_path)
    app.checkbox(key=f"voc_delete_confirm_{upper}").check().run()
    app.button(key=f"voc_delete_{upper}").click()
    pressed = app._tree.get_widget_states()
    app.run()
    assert "글을 지웠습니다." in [message.value for message in app.success]
    assert _posts(database_path) == [("아래 글", False)]

    app._run(widget_state=pressed)

    assert not app.exception
    assert not app.success
    assert _posts(database_path) == [("아래 글", False)]
    assert _delete_ready(app, lower) == (False, 0)


def _race(
    app: AppTest,
    monkeypatch: pytest.MonkeyPatch,
    *,
    callback: str,
    write: str,
) -> None:
    """누른 화면의 같은 누름 둘이 **두 회차에서 겹쳐** 온다 — 더블클릭(2026-10-25 E2E).

    Streamlit 1.63 은 둘째 누름이 닿으면(`runner.fastReruns`) 돌던 회차에 멈춤을 걸고
    새 회차를 세운다. 두 회차는 스레드가 다르고 같은 세션 칸을 회차마다 따로 잠근다
    (`SafeSessionState`). 첫 회차의 콜백(`callback` 이름의 위젯 콜백)은 여기서 그 회차의
    세션 칸으로 바로 부른다. 그 콜백이 DB 에 쓰려는 순간(`write` 저장소 메서드) 둘째
    누름이 닿는다 — 첫 회차에 멈춤을 걸고 둘째 회차(`app._run`)를 다른 스레드에서 세워
    1초 기다린 뒤 쓴다. 멈춤을 받은 첫 콜백은 다음 세션 칸 접근에서 `StopException` 으로
    끊긴다(브라우저에서 잰 모양 그대로).
    """
    pressed = app._tree.get_widget_states()
    shared = app.session_state._state
    metadata = next(
        meta
        for meta in shared._new_widget_state.widget_metadata.values()
        if getattr(meta.callback, "__name__", None) == callback
    )
    pressed_callback = metadata.callback
    assert pressed_callback is not None
    callback_args = metadata.callback_args or ()
    stopped = threading.Event()

    def first_yield() -> None:
        if stopped.is_set():
            raise StopException()

    first_state = SafeSessionState(shared, first_yield)
    local = threading.local()
    original_state = session_state_proxy.get_session_state

    def thread_state() -> SafeSessionState:
        state = getattr(local, "state", None)
        return state if isinstance(state, SafeSessionState) else original_state()

    monkeypatch.setattr(session_state_proxy, "get_session_state", thread_state)
    second = threading.Thread(target=lambda: app._run(widget_state=pressed))
    original_write = getattr(DuckDBScenarioRepository, write)
    arrived: list[int] = []

    def racing(self: DuckDBScenarioRepository, *args: Any, **kwargs: Any) -> Any:
        if not arrived:
            arrived.append(1)
            stopped.set()
            second.start()
            second.join(timeout=1.0)
        return original_write(self, *args, **kwargs)

    monkeypatch.setattr(DuckDBScenarioRepository, write, racing)
    local.state = first_state
    try:
        pressed_callback(*callback_args)
    except StopException:
        pass
    finally:
        del local.state
    second.join(timeout=60)
    assert arrived and not second.is_alive()


def test_a_double_click_on_two_runs_posts_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """더블클릭은 두 회차의 콜백이 수 ms 차이로 같은 세대 0 을 보아 같은 글이 두 건 올랐다.

    세대 비교와 쓰기는 한 잠금 안이고, 끊긴 첫 콜백이 쓴 세대는 둘째 콜백이 쓰지 않고 뒷정리만 한다.
    """
    database_path = tmp_path / "scenario.duckdb"
    app = _app(database_path)
    app.text_input(key=AUTHOR_KEY).input("검증자A")
    app.text_input(key="voc_post_title").input("제목 A")
    app.text_area(key="voc_post_body").input("내용 A")
    app.run()
    next(button for button in app.button if button.label == "글 올리기").click()

    _race(app, monkeypatch, callback="_submit_post", write="create_voc_post")

    assert not app.exception
    assert _posts(database_path) == [("제목 A", False)]
    assert "글을 올렸습니다." in [message.value for message in app.success]
    assert app.text_input(key="voc_post_title").value == ""
    assert app.text_area(key="voc_post_body").value == ""


def test_a_double_click_of_a_reply_on_two_runs_replies_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path = tmp_path / "scenario.duckdb"
    post_id = _post(database_path)
    app = _app(database_path)
    app.text_input(key=AUTHOR_KEY).input("담당자")
    app.text_area(key=f"voc_reply_body_{post_id}").input("확인했습니다.")
    app.run()
    _reply_button(app, post_id).click()

    _race(app, monkeypatch, callback="_submit_reply", write="create_voc_reply")

    assert not app.exception
    replies = DuckDBScenarioRepository(database_path).list_voc_replies()
    assert replies["body"].tolist() == ["확인했습니다."]
    assert "답변을 남겼습니다." in [message.value for message in app.success]
    assert app.text_area(key=f"voc_reply_body_{post_id}").value == ""
