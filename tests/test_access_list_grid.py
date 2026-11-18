# Purpose: Admin 「접속 명단」 편집 표 — 칸 · 잠금 · 새 줄 · 줄 지우기 · 등급 · 저장 차례 · 실패.

"""Admin Area 「접속 명단」 을 범용 편집 그리드의 줄 규칙 표로 바꾼 화면(2026-11-18 접속 등급 구현
확인 보드 「고칠 것」 — 사용자 답 「추가 · 지우기까지 표 안에서」).

AppTest 는 그리드 JS 를 못 돌려 대역(`tests/edit_grid_fake`)으로 출납을 보내고, 저장은 서명을
검증하는 가짜 S3(`scripts/s3_mock_store.py`)에 쓴다. 표 · 단추 · 저장 판 · 저장 차례(빼기 → 등급 →
넣기) · 잠긴 줄 · 실패 알림 꼴을 본다. 값은 모두 합성(`demo.*`)이다.
설계 규칙: UI-LAY-11 · UI-LAY-03 · UI-INP-07 · UI-NTF-03 · UI-CON-02.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from alert_marks import active_state, states
from edit_grid_fake import Calls, install_fake_edit_grid, last, send_ops, shell_frame
from streamlit.testing.v1 import AppTest
from test_sso_access import assert_absent
from test_sso_access_s3 import (
    ADMIN,
    ADMIN_SCRIPT,
    CARD_SCRIPT,
    GONE,
    OBJECT,
    OTHER,
    USER,
    _as_person,
    _flash_text,
    file_body,
    identity_of,
    mock_s3,
    problem_of,
    requests_named,
    s3_config,
    started,
)

from capa_simulation.auth import access_store, grade_store, runtime
from capa_simulation.auth.access import GRADE_ADMIN
from capa_simulation.auth.identity import IdentityProblem
from capa_simulation.components import access_list_admin, access_list_grid, sso_status
from capa_simulation.io import s3_small
from capa_simulation.services.access_list_plan import GRADE_OPTIONS
from capa_simulation.services.edit_grid import change_counts, draft_from

__all__ = ["mock_s3"]

# 가짜 S3 는 `scripts/` 에 있고 그 자리는 `test_sso_access_s3` 를 읽을 때 `sys.path` 에 든다.
from s3_mock_store import MockStore  # noqa: E402

HOST = access_list_grid.HOST
COLUMNS = ["No.", "계정", "이름", "부서", "등록일", "등록 길", "등급"]


def _grid_app(
    cfg: Any, monkeypatch: pytest.MonkeyPatch, loginid: str = ADMIN
) -> tuple[AppTest, Calls]:
    calls = install_fake_edit_grid(monkeypatch)
    _as_person(cfg, loginid, monkeypatch)
    return AppTest.from_string(ADMIN_SCRIPT, default_timeout=30).run(), calls


def _shell(calls: Calls) -> dict[str, Any]:
    return last(calls, HOST)


def _listed(calls: Calls) -> dict[str, str]:
    """표의 명단 사람 — 계정 → 등급 글(새 줄은 뺀다)."""
    frame = shell_frame(_shell(calls))
    return {
        str(row["계정"]): GRADE_OPTIONS[int(row["등급"])]
        for _, row in frame.iterrows()
        if row["계정"] is not None
    }


def _ops(app: AppTest, calls: Calls, *ops: dict[str, Any]) -> AppTest:
    app = send_ops(app, calls, *ops, host=HOST)
    assert not list(app.exception), [item.message for item in app.exception]
    return app


def _write(rows: list[str], cols: list[str], values: list[list[Any]]) -> dict[str, Any]:
    return {"op": "write", "rows": rows, "cols": cols, "values": values}


def _save(app: AppTest) -> AppTest:
    app = app.button(key=access_list_admin.SAVE_KEY).click().run()
    assert not list(app.exception), [item.message for item in app.exception]
    return app


def _draft(app: AppTest) -> tuple[int, int, int]:
    """그 앱 세션의 접속 명단 초안 수(고친 칸, 고친 줄, 오류 칸)."""
    state = app.session_state
    value = state[access_list_grid.CELLS_KEY] if access_list_grid.CELLS_KEY in state else None
    return change_counts(draft_from(value))


def _saved_people(store: MockStore) -> dict[str, dict[str, Any]]:
    saved = json.loads(store.objects[OBJECT])
    return {item["loginid"]: item for item in saved["users"]}


# ------------------------------------------------------------------ 표 · 단추


def test_the_admin_sees_the_list_as_an_edit_grid_with_new_rows(
    mock_s3: tuple[MockStore, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    store, endpoint = mock_s3
    cfg = started(store, endpoint, USER, OTHER)

    app, calls = _grid_app(cfg, monkeypatch)

    assert not list(app.exception)
    shell = _shell(calls)
    frame = shell_frame(shell)
    assert list(frame.columns) == COLUMNS
    assert shell["fmts"][-1]["options"] == ["열람", "실무자", "관리자", "개발자"]
    assert _listed(calls) == {OTHER: "열람", USER: "열람"}
    assert frame["등록 길"].tolist()[:2] == ["개발자가 넣음", "개발자가 넣음"], "옛 파일(칸 없음)"
    assert frame["No."].tolist()[:3] == ["1", "2", "새 1"]
    assert len(frame) == 2 + access_list_grid.FRESH_ROWS
    assert shell["ids"][:3] == [USER, OTHER, "+1"], "파일 차례 그대로"
    assert shell["rowOps"] is True
    assert shell["texts"]["changesButton"] == access_list_grid.CHANGES_BUTTON == "저장 전"
    assert shell["texts"]["errors"]["pattern"] == access_list_grid.ACCOUNT_PATTERN_ERROR
    kinds = shell["locks"]["rows"]
    assert kinds[:2] == [access_list_grid.LISTED] * 2
    assert set(kinds[2:]) == {access_list_grid.FRESH}
    save = app.button(key=access_list_admin.SAVE_KEY)
    assert save.disabled and save.help == access_list_admin.SAVE_LOCKED_WHY
    assert not [b for b in app.button if b.key == access_list_admin.DISCARD_KEY]
    assert not list(app.multiselect) and not list(app.get("popover")), "옛 고르기 칸 · 메뉴 없음"
    assert any("버전 1 · 명단 2 · 개발자 1(환경변수 1)" in str(item.value) for item in app.caption)


def test_an_empty_list_still_offers_new_rows(
    mock_s3: tuple[MockStore, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    store, endpoint = mock_s3
    cfg = started(store, endpoint)

    app, calls = _grid_app(cfg, monkeypatch)

    assert not list(app.exception)
    frame = shell_frame(_shell(calls))
    assert frame["No."].tolist()[0] == "새 1" and len(frame) == access_list_grid.FRESH_ROWS
    assert _listed(calls) == {}


def test_the_way_in_reads_the_same_words_as_the_recent_table_and_not_as_a_grade(
    mock_s3: tuple[MockStore, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """「등록 길」 은 바로 아래 「최근 등록 · 빼기」 의 「한 일」 과 같은 두 낱말(스스로 등록 ·
    개발자가 넣음)이고 「등급」 칸 낱말과 겹치지 않는다(E2E 보드 s-C-02)."""
    store, endpoint = mock_s3
    cfg = started(store, endpoint, USER)
    access_store.save_changes(cfg, identity_of(cfg, ADMIN), grades={USER: GRADE_ADMIN})
    access_store.register_self(cfg, "demo.self")

    app, calls = _grid_app(cfg, monkeypatch)

    frame = shell_frame(_shell(calls)).set_index("계정", drop=False)
    assert frame.loc[USER, "등록 길"] == "개발자가 넣음"
    assert _listed(calls)[USER] == "개발자", "명단 `admin` 은 등급 칸의 「개발자」"
    assert frame.loc["demo.self", "등록 길"] == "스스로 등록"
    recent = app.dataframe[0].value
    assert "스스로 등록" in recent["한 일"].tolist()
    assert {"스스로 등록", "개발자가 넣음"}.isdisjoint(GRADE_OPTIONS)


def test_a_hand_written_time_at_the_edge_does_not_stop_the_admin_screen(
    mock_s3: tuple[MockStore, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    store, endpoint = mock_s3
    for value in ("0001-01-01T00:00:00", "9999-12-31T23:59:59Z", "not a time"):
        store.put(
            OBJECT,
            json.dumps(
                {
                    "format": 1,
                    "revision": 1,
                    "users": [{"loginid": USER, "added_at": value, "added_by": ADMIN}],
                }
            ).encode(),
        )
        cfg = started(store, endpoint)

        app, calls = _grid_app(cfg, monkeypatch)

        assert not list(app.exception), [item.message for item in app.exception]
        assert list(_listed(calls)) == [USER]


def _box_children(app: AppTest) -> list[Any]:
    (box,) = [item for item in app.status if item.label == "접속 명단"]
    return list(box.children.values())


def _row_keys(app: AppTest) -> list[tuple[str, str]]:
    """작업 줄 칸 안 단추 줄의 (꼴, key) — 캡션은 꼴만."""
    actions = _box_children(app)[0]
    (row, *rest) = list(actions.children.values())
    assert getattr(row, "key", None) == access_list_admin.ACTION_ROW
    return [(item.type, str(getattr(item, "key", "") or "")) for item in row.children.values()]


def test_the_actions_stand_in_one_row_above_the_grid(
    mock_s3: tuple[MockStore, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """표 위 작업 줄은 한 줄이다(UI-LAY-11) — 저장 · (고친 것이 있으면 편집 취소) · 다시 읽기, 끝에
    버전 값. 그 뒤 형제 칸이 그리드 칸이고 그 뒤가 접힌 「최근 등록 · 빼기」 다."""
    store, endpoint = mock_s3
    cfg = started(store, endpoint, USER, OTHER)
    app, calls = _grid_app(cfg, monkeypatch)

    children = _box_children(app)
    assert [getattr(item, "key", None) for item in children[:2]] == [
        access_list_admin.ACTIONS_BOX,
        access_list_admin.GRID_BOX,
    ]
    assert [item for item in _row_keys(app) if item[0] != "caption"] == [
        ("button", access_list_admin.SAVE_KEY),
        ("button", access_list_admin.REREAD_KEY),
    ]
    assert _row_keys(app)[-1][0] == "caption"

    app = _ops(app, calls, _write([USER], ["등급"], [["실무자"]]))

    assert [item for item in _row_keys(app) if item[0] != "caption"] == [
        ("button", access_list_admin.SAVE_KEY),
        ("button", access_list_admin.DISCARD_KEY),
        ("button", access_list_admin.REREAD_KEY),
    ]
    save = app.button(key=access_list_admin.SAVE_KEY)
    assert not save.disabled and save.help == access_list_admin.SAVE_HELP


# ------------------------------------------------------------------ 저장


def test_new_rows_add_people_with_their_grade_and_hand_written_profile(
    mock_s3: tuple[MockStore, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    store, endpoint = mock_s3
    cfg = started(store, endpoint, USER)
    app, calls = _grid_app(cfg, monkeypatch)

    app = _ops(
        app,
        calls,
        _write(
            ["+1", "+2"],
            ["계정", "이름", "부서", "등급"],
            [[OTHER, "데모 나", "DEMO 팀", "실무자"], [GONE.upper(), "", "", "관리자"]],
        ),
    )
    app = _save(app)

    people = _saved_people(store)
    assert sorted(people) == [GONE, OTHER, USER], "계정은 견주는 꼴로"
    assert (people[OTHER]["name"], people[OTHER]["dept"]) == ("데모 나", "DEMO 팀")
    assert people[GONE].get("name", "") == ""
    assert grade_store.grade_of(cfg, OTHER) == "editor"
    assert grade_store.grade_of(cfg, GONE) == "manager"
    assert problem_of(cfg, GONE) is None, "재시작 없이 바로 들어온다"
    text = _flash_text(app)
    assert text.startswith("접속 명단을 저장했습니다 — 넣음 2명 · 버전 ")
    assert_absent(text, OTHER, GONE)
    assert _draft(app) == (0, 0, 0), "저장한 고침은 걷는다"
    assert _listed(calls) == {GONE: "관리자", OTHER: "실무자", USER: "열람"}


def test_a_bad_new_row_blocks_the_save_beside_the_row_and_writes_nothing(
    mock_s3: tuple[MockStore, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """틀린 계정 꼴은 빨간 칸, 머리 글 · 겹침 · 등급 빔은 저장 판의 문제 — 하나라도 있으면 아무것도
    쓰지 않고 작업 줄 바로 아래 곁 한 줄로 알린다(표에서 고칠 일 — UI-NTF-03 · UI-LAY-03)."""
    store, endpoint = mock_s3
    cfg = started(store, endpoint, USER)
    app, calls = _grid_app(cfg, monkeypatch)
    before = requests_named(store, "PUT")

    app = _ops(
        app,
        calls,
        _write(
            ["+1", "+2", "+3", "+4"],
            ["계정", "등급"],
            [["Bad Name", "실무자"], ["loginid", "실무자"], [USER, "실무자"], [OTHER, None]],
        ),
    )
    assert any("고칠 칸 1개" in str(item.value) for item in app.markdown)
    app = _save(app)

    assert requests_named(store, "PUT") == before
    (error,) = [str(item.value) for item in app.error]
    assert error.startswith(access_list_admin.PROBLEMS_LEAD)
    for part in ("고칠 칸 1개", "머리 글", "겹치는 계정 1개", "등급이 빈 줄 1개"):
        assert part in error, part
    assert_absent(error, USER, OTHER)
    assert _draft(app)[0] > 0, "고침은 남는다"
    actions = _box_children(app)[0]
    assert [item.type for item in actions.children.values()][1] in {"vertical", "flex_container"}


def test_removing_regrading_and_adding_write_in_the_narrowing_order(
    mock_s3: tuple[MockStore, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """「저장」 한 번 — 빼기(명단) → 등급 바꿈(등급 파일) → 넣기(명단 → 등급 파일) 차례다."""
    store, endpoint = mock_s3
    cfg = started(store, endpoint, USER, OTHER)
    app, calls = _grid_app(cfg, monkeypatch)
    puts_before = [path for method, path in store.requests if method == "PUT"]

    app = _ops(
        app,
        calls,
        {"op": "remove", "rows": [USER]},
        _write([OTHER], ["등급"], [["관리자"]]),
        _write(["+1"], ["계정", "등급"], [[GONE, "실무자"]]),
    )
    app = _save(app)

    assert sorted(_saved_people(store)) == [GONE, OTHER]
    assert grade_store.grade_of(cfg, OTHER) == "manager"
    assert grade_store.grade_of(cfg, GONE) == "editor"
    assert problem_of(cfg, USER) is IdentityProblem.DENIED
    puts = [path for method, path in store.requests if method == "PUT"][len(puts_before) :]
    keys = [path.split("/", 2)[2] for path in puts]
    grades_key = grade_store.object_key(cfg)
    assert [key for key in keys if key in {OBJECT, grades_key}] == [
        OBJECT,
        grades_key,
        OBJECT,
        grades_key,
    ]
    assert "뺌 1명 · 등급 1명 · 넣음 1명" in _flash_text(app)


def test_many_grades_change_at_once_by_filling_down(
    mock_s3: tuple[MockStore, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    store, endpoint = mock_s3
    cfg = started(store, endpoint, USER, OTHER, GONE)
    app, calls = _grid_app(cfg, monkeypatch)
    first, *rest = sorted([USER, OTHER, GONE])

    app = _ops(
        app,
        calls,
        _write([first], ["등급"], [["관리자"]]),
        {
            "op": "fill",
            "rows": rest,
            "cols": ["등급"],
            "src": {"rows": [first], "cols": ["등급"]},
            "dir": "down",
        },
    )
    app = _save(app)

    assert {grade_store.grade_of(cfg, key) for key in (USER, OTHER, GONE)} == {"manager"}
    assert "등급 3명" in _flash_text(app)


def test_own_and_environment_rows_are_locked_in_the_grid_and_on_the_server(
    mock_s3: tuple[MockStore, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    store, endpoint = mock_s3
    boss = "demo.boss"
    cfg = started(store, endpoint, USER, OTHER, boss, CAPA_ACCESS_ADMINS=f"{ADMIN},{boss}")
    access_store.save_changes(cfg, identity_of(cfg, ADMIN), grades={USER: GRADE_ADMIN})
    app, calls = _grid_app(cfg, monkeypatch, loginid=USER)

    shell = _shell(calls)
    kinds = dict(zip(shell["ids"], shell["locks"]["rows"], strict=True))
    assert kinds[USER] == access_list_grid.SELF and kinds[boss] == access_list_grid.ENV
    locks = shell["locks"]["kinds"]
    assert locks[access_list_grid.SELF]["remove"] == access_list_grid.SELF_WHY
    assert locks[access_list_grid.ENV]["remove"] == access_list_grid.ENV_WHY
    assert 5 in locks[access_list_grid.SELF]["cols"] and 5 in locks[access_list_grid.ENV]["cols"]

    app = _ops(
        app,
        calls,
        _write([USER, boss], ["등급"], [["열람"]]),
        {"op": "remove", "rows": [USER, boss]},
    )

    assert _draft(app) == (0, 0, 0)
    feed = last(calls, f"{HOST}-feed")
    assert "잠긴 칸 2칸은 건너뛰었습니다" in feed["toast"]["text"]
    assert "지울 수 없는 줄 2개는 건너뛰었습니다" in feed["toast"]["text"]
    assert access_store.is_admin(cfg, USER) and access_store.is_admin(cfg, boss)


def test_the_discard_button_drops_the_draft(
    mock_s3: tuple[MockStore, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    store, endpoint = mock_s3
    cfg = started(store, endpoint, USER)
    app, calls = _grid_app(cfg, monkeypatch)
    app = _ops(app, calls, _write([USER], ["등급"], [["관리자"]]))

    app = app.button(key=access_list_admin.DISCARD_KEY).click().run()

    assert _draft(app) == (0, 0, 0)
    assert app.button(key=access_list_admin.SAVE_KEY).disabled


# ------------------------------------------------------------------ 실패


def test_a_failed_save_tells_why_only_in_the_popup_and_keeps_the_draft(
    mock_s3: tuple[MockStore, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    store, endpoint = mock_s3
    cfg = started(store, endpoint)
    app, calls = _grid_app(cfg, monkeypatch)
    app = _ops(app, calls, _write(["+1"], ["계정", "등급"], [[USER, "실무자"]]))
    store.force["PUT"] = (403, "AccessDenied")

    app = _save(app)

    text = _flash_text(app)
    assert "인증 거절(HTTP 403 · AccessDenied)" in text and "명단은 그대로입니다" in text
    assert not list(app.error), [item.value for item in app.error]
    assert problem_of(cfg, USER) is IdentityProblem.DENIED
    assert _draft(app)[0] == 2, "고침은 남아 다시 저장한다"


def test_a_save_with_no_answer_tells_the_admin_to_read_again(
    mock_s3: tuple[MockStore, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    store, endpoint = mock_s3
    cfg = started(store, endpoint, USER)
    app, calls = _grid_app(cfg, monkeypatch)
    app = _ops(app, calls, _write(["+1"], ["계정", "등급"], [[OTHER, "열람"]]))
    store.answer_delay["PUT"] = 1.0
    monkeypatch.setattr(s3_small, "READ_TIMEOUT_SECONDS", 0.2)

    app = _save(app)

    text = _flash_text(app)
    assert "저장됐는지 알 수 없습니다" in text and "시간 초과" in text and "다시 읽기" in text
    assert "그대로입니다" not in text
    assert_absent(text, OTHER)


def test_a_later_step_that_fails_keeps_what_was_saved_and_says_both(
    mock_s3: tuple[MockStore, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """빼기는 남고 등급 바꿈이 막히면 남은 수와 막힌 까닭을 함께 알리고, 뺀 사람의 초안만 걷는다."""
    store, endpoint = mock_s3
    cfg = started(store, endpoint, USER, OTHER)
    app, calls = _grid_app(cfg, monkeypatch)
    app = _ops(
        app, calls, {"op": "remove", "rows": [USER]}, _write([OTHER], ["등급"], [["관리자"]])
    )

    def conflict(*_args: Any, **_kwargs: Any) -> Any:
        raise access_store.StoreConflictError

    monkeypatch.setattr(grade_store, "change_grades", conflict)
    app = _save(app)

    assert sorted(_saved_people(store)) == [OTHER]
    text = _flash_text(app)
    assert text.startswith(access_list_admin.CONFLICT_MESSAGE) and "앞서 저장: 뺌 1명" in text
    assert _draft(app)[:2] == (1, 1), "등급 고침만 남는다"


def test_a_stale_save_of_someone_who_lost_the_right_writes_nothing(
    mock_s3: tuple[MockStore, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """보인 회차에는 개발자였어도 누른 회차의 쿠키로 다시 본다 — 저장 콜백이 그 자리에서 막힌다."""
    store, endpoint = mock_s3
    cfg = started(store, endpoint, USER)
    app, calls = _grid_app(cfg, monkeypatch)
    app = _ops(app, calls, {"op": "remove", "rows": [USER]})
    _as_person(cfg, USER, monkeypatch)
    before = requests_named(store, "PUT")

    app = _save(app)

    assert requests_named(store, "PUT") == before
    assert problem_of(cfg, USER) is None
    assert "접속 명단" not in [item.label for item in app.status]
    queued = app.session_state[access_list_admin.ACCESS_LIST_FLASH_KEY]
    assert queued.message == access_list_admin.NOT_ADMIN_MESSAGE and queued.popup_only


def test_reading_again_from_the_screen(
    mock_s3: tuple[MockStore, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    store, endpoint = mock_s3
    cfg = started(store, endpoint, USER)
    app, calls = _grid_app(cfg, monkeypatch)
    store.put(OBJECT, file_body(USER, OTHER, revision=4))

    app = app.button(key=access_list_admin.REREAD_KEY).click().run()

    assert sorted(_listed(calls)) == [OTHER, USER]
    assert problem_of(cfg, OTHER) is None
    assert "명단 2 · 버전 4" in _flash_text(app)

    store.force["GET"] = (403, "AccessDenied")
    app = app.button(key=access_list_admin.REREAD_KEY).click().run()

    assert "인증 거절(HTTP 403 · AccessDenied)" in _flash_text(app)
    assert not list(app.error)
    assert sorted(_listed(calls)) == [OTHER, USER]


def test_a_list_that_shrinks_on_reading_again_drops_the_stale_draft(
    mock_s3: tuple[MockStore, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    store, endpoint = mock_s3
    cfg = started(store, endpoint, USER, OTHER)
    app, calls = _grid_app(cfg, monkeypatch)
    app = _ops(app, calls, {"op": "remove", "rows": [USER]})
    store.put(OBJECT, file_body(OTHER, revision=2))
    app = app.button(key=access_list_admin.REREAD_KEY).click().run()
    before = requests_named(store, "PUT")

    app = _save(app)

    assert list(_listed(calls)) == [OTHER]
    assert requests_named(store, "PUT") == before
    assert access_list_admin.NOTHING_CHANGED in _flash_text(app)


def test_removing_everyone_still_tells_the_result(
    mock_s3: tuple[MockStore, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    store, endpoint = mock_s3
    cfg = started(store, endpoint, USER, OTHER)
    app, calls = _grid_app(cfg, monkeypatch)
    app = _ops(app, calls, {"op": "remove", "rows": [USER, OTHER]})

    app = _save(app)

    assert _listed(calls) == {}
    assert "뺌 2명" in _flash_text(app)


def test_unread_locks_the_save_and_warns_the_admin_on_any_screen(
    mock_s3: tuple[MockStore, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """못 읽은 동안은 개발자만 들어온다 — 표는 표 없는 껍데기로 마운트만 남고 「저장」 이 잠긴다.
    개발자는 Admin 을 열기 전 어느 화면에서나 알림을 받는다(앱 정보 카드가 낸다)."""
    store, endpoint = mock_s3
    store.force["GET"] = (403, "AccessDenied")
    cfg = s3_config(store, endpoint)
    access_store.read_at_start(cfg)

    app, calls = _grid_app(cfg, monkeypatch)

    assert app.button(key=access_list_admin.SAVE_KEY).disabled
    assert any(item.value == "접속 명단 읽지 못함" for item in app.caption)
    assert _shell(calls)["table"] is None
    card = AppTest.from_string(CARD_SCRIPT, default_timeout=30).run()
    note = active_state(card, "AD-08")
    assert note is not None and "개발자만 들어옵니다" in note["short"]
    assert sso_status.ACCESS_READ_FIX_STEP in note["full"]

    store.force.clear()
    app = app.button(key=access_list_admin.REREAD_KEY).click().run()

    assert _shell(calls)["table"] == access_list_grid.TABLE
    card = AppTest.from_string(CARD_SCRIPT, default_timeout=30).run()
    assert [item["active"] for item in states(card, "AD-08")] == [False]
    assert runtime.access_source() is not None
