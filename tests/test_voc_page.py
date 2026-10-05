# Purpose: VOC 화면이 작성자 이름과 편 글을 화면 이동·답변 뒤에도 지키는지 검증한다.

"""VOC 화면에서 사용자가 해 둔 것이 사라지지 않는다(2026-10-01 브라우저 점검).

- 작성자 칸은 다른 화면에 갔다 와도 남는다. Streamlit 은 그리지 않은 회차의 위젯 값을 버리므로
  `persist_state` 가 없으면 돌아왔을 때 빈 칸이고, 글을 올리면 「작성자를 입력하세요.」로 막혔다.
- 편 글은 답변을 남긴 뒤에도 편 채로다. 라벨의 「답변 N」이 바뀌면 `key` 없는 상자는 새로
  만들어져 접혔다.
- 첫 답변 앞뒤로 글 상자와 답변 칸의 자리가 그대로다. 밀리면 브라우저에 옛 상자의 회색 사본이
  남았다(2026-10-05 E2E).
"""

from collections.abc import Callable
from pathlib import Path
from typing import Any

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

    답변 회차는 알림 없이 `st.rerun()` 으로 끊기고, 다음 회차는 맨 위 알림과 첫 답글을 더 그린다.
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
