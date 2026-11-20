# Purpose: Admin 「부대공정」 의 「이 리비전 값을 새 판으로」 — 만들기 · 새 판 적용 · S3 Drive
# 쓰기(가짜 내보내기)의 씀 · 덮지 않음 · 실패와 「S3 에 다시 쓰기」 · 알림 EP-05 · EP-02 를 본다.

"""「이 리비전 값을 새 판으로」(`components/extra_process_admin.py` — 설계 3-5 · A15 · T1 2단계).

판 1 로 등록한 시나리오에서 BOND 의 202609 UPEH 를 고친 리비전 2 를 저장 · 공식 지정해 사이드바의
활성 리비전으로 둔다. 내보내기 자리(`install_sink`)는 지금 판에 꽂히지 않아 시험이 가짜를 꽂는다 —
HEAD 의 ETag · PUT 실패를 세션 칸으로 고른다. 꽂지 않으면 DB 새 판만 넣고 S3 는 건드리지 않는다.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from alert_marks import active_state, flashed, states
from auto_update_fakes import new_repository, publish_snapshot
from extra_process_fixtures import BOND
from streamlit.testing.v1 import AppTest
from test_extra_process_registration import apply_template, register

from capa_simulation.components.extra_process_admin import (
    APPLY_BUTTON_KEY,
    IMPORT_BUTTON_KEY,
    NOT_PRODUCTION_REASON,
    REVISION_APPLY_LABEL,
    REVISION_BUTTON_KEY,
    REWRITE_BUTTON_KEY,
    UNCHANGED_REVISION,
)
from capa_simulation.extra_process_intake import (
    NEW_FILE_WORD,
    OLD_VERSION_WORD,
    RemoteHead,
    SourceFailure,
    head_word,
    needs_write,
    pending_write,
    write_back,
)
from capa_simulation.persistence.models import (
    EXTRA_KIND_APPLY,
    EXTRA_KIND_OFF,
    EXTRA_KIND_RESUME,
    EXTRA_KIND_REVISION,
    EXTRA_WRITE_FAILED,
    EXTRA_WRITE_KEPT,
    EXTRA_WRITE_PLACED_REASON,
    EXTRA_WRITE_WRITTEN,
    ExtraProcessS3Write,
    ExtraProcessState,
    ExtraProcessVersion,
)
from capa_simulation.persistence.repository import REVISION_TABLES, DuckDBScenarioRepository
from capa_simulation.services.extra_process_pack import read_pack_zip

OPEN_KEY = "__rev_open__"
SINK_KEY = "__rev_sink__"
HEAD_KEY = "__rev_head__"
PUT_FAIL_KEY = "__rev_put_fail__"
PUTS_KEY = "__rev_puts__"
SOURCE_KEY = "__rev_source__"
# 가짜 원천이 받는 바이트(없으면 받기 실패)와 「받을 것이 아직 없음」(까닭, 낱말).
FETCH_KEY = "__rev_fetch__"
WAIT_KEY = "__rev_wait__"


def _script(database: Path) -> str:
    return f"""
from pathlib import Path

import streamlit as st

import capa_simulation.components.extra_process_admin as admin
import capa_simulation.settings as settings
from capa_simulation.extra_process_intake import (
    RemoteHead,
    SourceFailure,
    SourceFetch,
    SourceNotReady,
    install_sink,
    install_source,
)
from capa_simulation.persistence.cache import get_scenario_repository
from capa_simulation.scenario_activation import bootstrap_latest_official_scenario


class FakeSink:
    place = "가짜 S3"

    def head(self):
        etag = st.session_state.get({HEAD_KEY!r})
        if etag == "FAIL":
            raise SourceFailure("닿지 못함")
        return RemoteHead(etag)

    def put(self, data):
        if st.session_state.get({PUT_FAIL_KEY!r}):
            raise SourceFailure("시간 초과")
        puts = [*st.session_state.get({PUTS_KEY!r}, []), len(data)]
        st.session_state[{PUTS_KEY!r}] = puts
        etag = f'"app-{{len(puts)}}"'
        st.session_state[{HEAD_KEY!r}] = etag
        return etag


class FakeSource:
    label = "가짜 원천에서 가져오기"
    place = "가짜 S3"

    def fetch(self):
        waiting = st.session_state.get({WAIT_KEY!r})
        if waiting:
            raise SourceNotReady(*waiting)
        data = st.session_state.get({FETCH_KEY!r})
        if data is None:
            raise SourceFailure("닿지 못함")
        return SourceFetch(
            data=data,
            place="가짜 S3",
            key="extra_process/",
            etag=st.session_state.get({HEAD_KEY!r}),
        )

    def head(self):
        etag = st.session_state.get({HEAD_KEY!r})
        if etag == "FAIL":
            raise SourceFailure("닿지 못함")
        return RemoteHead(etag)


original_path = settings.DUCKDB_PATH
original_lock = admin.write_lock_reason
settings.DUCKDB_PATH = Path({str(database)!r})
if st.session_state.get({OPEN_KEY!r}):
    admin.write_lock_reason = lambda: None
if st.session_state.get({SINK_KEY!r}):
    install_sink(FakeSink())
if st.session_state.get({SOURCE_KEY!r}):
    install_source(FakeSource())
try:
    bootstrap_latest_official_scenario(str(settings.DUCKDB_PATH))
    repository = get_scenario_repository(str(settings.DUCKDB_PATH))
    admin.render_extra_process_admin(repository, alert_tab="부대공정")
finally:
    install_sink(None)
    install_source(None)
    admin.write_lock_reason = original_lock
    settings.DUCKDB_PATH = original_path
"""


@pytest.fixture
def database(tmp_path: Path) -> Path:
    return tmp_path / "revision_admin.duckdb"


def _edited_revision(database: Path, *, upeh: float | None = 60000.0) -> DuckDBScenarioRepository:
    """판 1 로 등록한 시나리오에 BOND 202609 UPEH 를 고친 리비전 2 를 저장하고 공식으로 둔다
    (`upeh` 가 None 이면 고치지 않은 리비전 1 을 공식으로 둔다)."""
    repository = new_repository(database)
    apply_template(repository)
    snapshot, _memo = register(repository)
    if upeh is None:
        publish_snapshot(repository, snapshot)
        return repository
    tables = {name: snapshot.tables[name].copy() for name in REVISION_TABLES}
    frame = tables["RQ_UPEH"]
    frame.loc[frame["공정"].eq(BOND) & frame["생산계획년월"].eq(202609), "UPEH"] = upeh
    edited = repository.save_revision(
        snapshot.scenario.scenario_id,
        tables,
        snapshot.preset,
        revision_name="BOND UPEH 고침",
        parent_revision_id=snapshot.revision.revision_id,
    )
    publish_snapshot(repository, edited)
    return repository


def _app(
    database: Path,
    *,
    open_place: bool = True,
    sink: bool = False,
    head: str | None = None,
    source: bool = False,
) -> AppTest:
    app = AppTest.from_string(_script(database), default_timeout=120)
    app.session_state[OPEN_KEY] = open_place
    app.session_state[SINK_KEY] = sink
    app.session_state[HEAD_KEY] = head
    app.session_state[PUT_FAIL_KEY] = False
    app.session_state[SOURCE_KEY] = source
    app.session_state[FETCH_KEY] = None
    app.session_state[WAIT_KEY] = None
    app.run()
    assert not app.exception, [item.message for item in app.exception]
    return app


def _click(app: AppTest, key: str) -> AppTest:
    app.button(key=key).click().run()
    assert not app.exception, [item.message for item in app.exception]
    return app


def _captions(app: AppTest) -> list[str]:
    return [str(item.value) for item in app.caption]


def _history(app: AppTest) -> pd.DataFrame:
    return next(frame.value for frame in app.dataframe if "S3 쓰기" in frame.value)


def test_off_the_production_server_the_revision_button_is_locked(database: Path) -> None:
    _edited_revision(database)

    app = _app(database, open_place=False)

    button = app.button(key=REVISION_BUTTON_KEY)
    assert button.disabled and button.help == NOT_PRODUCTION_REASON


def test_without_any_version_the_lock_says_there_is_none_not_that_it_is_off(
    database: Path,
) -> None:
    """판 이력이 아예 없으면(가져오기 원천이 꽂히기 전의 운영) 상태 줄은 「판 없음」 이고
    「새 판으로」 의 풍선도 「판 없음」 을 말한다 — 「다시 켜기」 를 시키지 않는다(그 단추는
    끈 판에만 선다)."""
    repository = new_repository(database)
    snapshot, _memo = register(repository)
    publish_snapshot(repository, snapshot)

    app = _app(database)

    assert repository.load_extra_process_state().history == ()
    assert any(caption.endswith("판 없음") for caption in _captions(app))
    button = app.button(key=REVISION_BUTTON_KEY)
    assert button.disabled and button.help == "적용한 부대공정 판이 없습니다"
    assert not [item for item in app.button if "다시 켜기" in str(item.label)]


def test_an_unedited_revision_has_nothing_to_carry(database: Path) -> None:
    _edited_revision(database, upeh=None)
    app = _app(database)

    _click(app, REVISION_BUTTON_KEY)

    assert any(UNCHANGED_REVISION in str(note.value) for note in flashed(app))
    assert not [button for button in app.button if button.key == APPLY_BUTTON_KEY]


def test_without_a_sink_the_new_version_goes_to_the_database_only(database: Path) -> None:
    repository = _edited_revision(database)
    app = _app(database)

    _click(app, REVISION_BUTTON_KEY)
    assert any(text.startswith("**리비전에서 만든 판**") for text in _markdowns(app))
    assert any(
        "옮긴 공정 2 · 옮기지 못한 공정 0 · 경로가 판과 다름 0" in text for text in _captions(app)
    )
    apply = app.button(key=APPLY_BUTTON_KEY)
    assert apply.label == REVISION_APPLY_LABEL
    _click(app, APPLY_BUTTON_KEY)

    state = repository.load_extra_process_state()
    active = state.active
    assert active is not None and active.kind == EXTRA_KIND_REVISION and active.version_no == 2
    assert active.base_revision_ref is not None and state.writes == ()
    pack = read_pack_zip(repository.load_extra_process_content(str(active.sha256))).pack
    assert pack is not None and pack.info.memo.startswith("앱 — ")
    assert 60000.0 in {row.upeh for row in pack.productivity if row.process == BOND}
    assert any("부대공정 판 2 적용 — 리비전에서" in str(note.value) for note in flashed(app))
    assert active_state(app, "EP-05") is None
    assert not [button for button in app.button if button.key == REWRITE_BUTTON_KEY]
    history = _history(app)
    assert history.loc[0, "갈래"] == "새 판" and str(history.loc[0, "바탕"]).endswith("r2")
    # 같은 리비전으로 다시 누를 수 없다 — 리비전의 판(1)이 활성 판(2)과 다르다.
    again = app.button(key=REVISION_BUTTON_KEY)
    assert again.disabled and "판 1로 만든 리비전" in str(again.help)


def test_a_sink_with_no_file_is_overwritten_and_recorded(database: Path) -> None:
    repository = _edited_revision(database)
    app = _app(database, sink=True)

    _click(app, REVISION_BUTTON_KEY)
    _click(app, APPLY_BUTTON_KEY)

    state = repository.load_extra_process_state()
    assert [item.result for item in state.writes] == [EXTRA_WRITE_WRITTEN]
    assert state.baseline == ('"app-1"', state.last_seq)
    assert any("앱이 덮음 · 판 2" in str(note.value) for note in flashed(app))
    assert str(_history(app).loc[0, "S3 쓰기"]).startswith("앱이 덮음")
    assert any("가짜 S3 같음 — 앱이 씀" in text for text in _captions(app))
    assert active_state(app, "EP-05") is None


def test_an_unapplied_file_is_kept_then_rewritten_after_it_is_cleared(database: Path) -> None:
    repository = _edited_revision(database)
    app = _app(database, sink=True, head='"사람이 놓은 파일"')

    _click(app, REVISION_BUTTON_KEY)
    _click(app, APPLY_BUTTON_KEY)

    state = repository.load_extra_process_state()
    assert [item.result for item in state.writes] == [EXTRA_WRITE_KEPT]
    assert any("덮지 않았습니다" in str(note.value) for note in flashed(app, "warning"))
    pending = active_state(app, "EP-05")
    assert pending is not None and "덮지 않음" in pending["short"]
    # 덮지 않았다 — PUT 이 한 번도 불리지 않았다.
    assert PUTS_KEY not in app.session_state

    # 사람이 그 파일을 치우면(파일 없음) 「S3 에 다시 쓰기」 가 덮는다.
    app.session_state[HEAD_KEY] = None
    _click(app, REWRITE_BUTTON_KEY)

    state = repository.load_extra_process_state()
    assert [item.result for item in state.writes] == [EXTRA_WRITE_KEPT, EXTRA_WRITE_WRITTEN]
    assert active_state(app, "EP-05") is None
    assert not [button for button in app.button if button.key == REWRITE_BUTTON_KEY]


def test_a_failed_put_leaves_the_rewrite_button(database: Path) -> None:
    repository = _edited_revision(database)
    app = _app(database, sink=True)
    app.session_state[PUT_FAIL_KEY] = True

    _click(app, REVISION_BUTTON_KEY)
    _click(app, APPLY_BUTTON_KEY)

    last = repository.load_extra_process_state().writes[-1]
    assert (last.result, last.stage, last.reason) == (EXTRA_WRITE_FAILED, "PUT", "시간 초과")
    assert any("쓰지 못했습니다" in str(note.value) for note in flashed(app, "error"))
    assert active_state(app, "EP-05") is not None
    # DB 는 이미 새 판이다 — 다음 등록은 판 2 로 돈다.
    active = repository.load_extra_process_state().active
    assert active is not None and active.version_no == 2

    app.session_state[PUT_FAIL_KEY] = False
    _click(app, REWRITE_BUTTON_KEY)
    assert repository.load_extra_process_state().writes[-1].result == EXTRA_WRITE_WRITTEN


def test_a_new_file_on_the_drive_raises_ep02_only_with_a_source(database: Path) -> None:
    _edited_revision(database)

    without_source = _app(database, sink=True, head='"새 파일"')
    assert active_state(without_source, "EP-02") is None
    assert states(without_source, "EP-02")

    app = _app(database, sink=True, head='"새 파일"', source=True)
    assert active_state(app, "EP-02") is not None
    assert any(f"가짜 S3 {NEW_FILE_WORD}" in text for text in _captions(app))


def test_with_a_source_and_no_sink_a_new_version_raises_the_drift_alert_until_placed(
    database: Path,
) -> None:
    """원천만 꽂힌 C-DEP(내보내기 없음) — 「새 판 적용」 뒤에는 `EP-05` 대신 판 어긋남 `EP-06`
    하나가 선다(2026-11-19 보드 답 m19-extra2-newfile (가)). 사람이 양식 내려받기로 받은 새 판을
    그대로 놓고 가져오면 「놓인 파일 같음」 이 적히고 알림이 풀린다 — 그 파일의 ETag 가 기준이다."""
    repository = _edited_revision(database)
    app = _app(database, source=True, head='"판1-파일"')
    assert active_state(app, "EP-06") is None
    assert states(app, "EP-06")

    _click(app, REVISION_BUTTON_KEY)
    _click(app, APPLY_BUTTON_KEY)

    state = repository.load_extra_process_state()
    active = state.active
    assert active is not None and active.kind == EXTRA_KIND_REVISION and state.writes == ()
    drift = active_state(app, "EP-06")
    assert drift is not None and "양식 내려받기로 새 판을 받아 놓으세요" in drift["short"]
    assert active_state(app, "EP-05") is None
    assert not [button for button in app.button if button.key == REWRITE_BUTTON_KEY]

    # 양식 내려받기 → 풀어 그대로 놓은 여섯 장 = 활성 판과 같은 바이트(묶개가 같다).
    app.session_state[FETCH_KEY] = repository.load_extra_process_content(str(active.sha256))
    app.session_state[HEAD_KEY] = '"사람이-놓은-새-판"'
    _click(app, IMPORT_BUTTON_KEY)

    state = repository.load_extra_process_state()
    (placed,) = state.writes
    assert placed.placed and placed.result_label == EXTRA_WRITE_PLACED_REASON
    assert state.baseline == ('"사람이-놓은-새-판"', active.seq)
    assert state.last_seq == active.seq
    assert any("판 어긋남을 풉니다" in str(note.value) for note in flashed(app))
    assert active_state(app, "EP-06") is None
    assert active_state(app, "EP-02") is None
    assert str(_history(app).loc[0, "S3 쓰기"]).startswith(EXTRA_WRITE_PLACED_REASON)
    assert any("가짜 S3 같음" in text for text in _captions(app)), _captions(app)

    # 같은 파일을 다시 가져오면 「바뀐 것 없음」 이고 더 적지 않는다.
    _click(app, IMPORT_BUTTON_KEY)
    assert len(repository.load_extra_process_state().writes) == 1
    assert any("바뀐 것 없음" in str(note.value) for note in flashed(app, "info"))


def test_nothing_to_fetch_yet_is_a_note_not_a_failure(database: Path) -> None:
    """원천이 받을 것이 아직 없다고 하면(여섯 다 없음 · 놓는 중) 알림창 안내 하나와 상태 줄
    낱말이다 — 가져오기 실패 `EP-01` 을 세우지 않는다."""
    _edited_revision(database)
    app = _app(database, source=True, head='"판1-파일"')
    app.session_state[WAIT_KEY] = ("S3 Drive 에 부대공정 파일을 놓는 중입니다", "놓는 중")

    _click(app, IMPORT_BUTTON_KEY)

    assert any("놓는 중입니다" in str(note.value) for note in flashed(app, "info"))
    assert not flashed(app, "error")
    assert any("가짜 S3 놓는 중" in text for text in _captions(app)), _captions(app)


def _markdowns(app: AppTest) -> list[str]:
    return [str(item.value) for item in app.markdown]


class _Sink:
    place = "가짜"

    def __init__(self, etag: str | None, *, head_fails: bool = False, put_fails: bool = False):
        self.etag = etag
        self.head_fails = head_fails
        self.put_fails = put_fails
        self.puts = 0

    def head(self) -> RemoteHead:
        if self.head_fails:
            raise SourceFailure("인증 거절")
        return RemoteHead(self.etag)

    def put(self, data: bytes) -> str:
        del data
        if self.put_fails:
            raise SourceFailure("닿지 못함")
        self.puts += 1
        return f'"w{self.puts}"'


def test_write_back_branches_follow_the_baseline() -> None:
    from datetime import datetime

    now = datetime(2026, 11, 19, 1, 2)
    same = write_back(_Sink('"base"'), b"x", baseline='"base"', now=now)
    assert (same.result, same.etag, same.word) == (
        EXTRA_WRITE_WRITTEN,
        '"w1"',
        "같음 — 앱이 씀 01:02",
    )
    empty = write_back(_Sink(None), b"x", baseline='"base"', now=now)
    assert empty.result == EXTRA_WRITE_WRITTEN
    staged = write_back(
        _Sink('"staged"'), b"x", baseline='"base"', now=now, known={'"staged"': "적용 전 판 3"}
    )
    assert (staged.result, staged.seen_etag, staged.word) == (
        EXTRA_WRITE_KEPT,
        '"staged"',
        "적용 전 판 3",
    )
    other = write_back(_Sink('"other"'), b"x", baseline='"base"', now=now)
    assert (other.result, other.word) == (EXTRA_WRITE_KEPT, NEW_FILE_WORD)
    head_failed = write_back(_Sink(None, head_fails=True), b"x", baseline=None, now=now)
    assert (head_failed.result, head_failed.stage, head_failed.word) == (
        EXTRA_WRITE_FAILED,
        "HEAD",
        "읽지 못함(인증 거절)",
    )
    put_old = write_back(_Sink('"base"', put_fails=True), b"x", baseline='"base"', now=now)
    assert (put_old.stage, put_old.word) == ("PUT", OLD_VERSION_WORD)
    put_none = write_back(_Sink(None, put_fails=True), b"x", baseline='"base"', now=now)
    assert put_none.word == "없음"


class _BrokenSink(_Sink):
    """`SourceFailure` 로 감싸지 못한 실패 · 빈 ETag 를 돌려주는 꽂이(꽂을 실물이 그럴 수 있다)."""

    def __init__(self, etag: str | None, *, head_error: bool = False, put_etag: str | None = None):
        super().__init__(etag)
        self.head_error = head_error
        self.put_etag = put_etag

    def head(self) -> RemoteHead:
        if self.head_error:
            raise RuntimeError("https://bucket.example/extra_process/current.zip?X-Amz-Signature=x")
        return super().head()

    def put(self, data: bytes) -> str:
        if self.put_etag is None:
            raise KeyError("ETag")
        return self.put_etag


def test_write_back_records_any_sink_failure_and_an_empty_etag_as_failed() -> None:
    """꽂이가 `SourceFailure` 밖의 예외를 내거나 PUT 이 빈 ETag 를 돌려줘도 쓰기는 「실패」 기록으로
    끝난다 — DB 에 새 판을 넣은 뒤라 새면 기록 없이 화면 오류가 되고, 빈 ETag 의 「씀」 은 기록이
    거절한다. 까닭에는 예외 종류 이름만 싣는다(글에 주소 · 서명이 섞일 수 있다)."""
    from datetime import datetime

    from capa_simulation.extra_process_intake import ETAG_MISSING

    now = datetime(2026, 11, 19, 1, 2)
    head = write_back(_BrokenSink(None, head_error=True), b"x", baseline=None, now=now)
    assert (head.result, head.stage, head.reason) == (
        EXTRA_WRITE_FAILED,
        "HEAD",
        "예상하지 못한 오류(RuntimeError)",
    )
    assert "Signature" not in head.word and "https" not in head.word
    put = write_back(_BrokenSink(None), b"x", baseline=None, now=now)
    assert (put.result, put.stage, put.reason, put.word) == (
        EXTRA_WRITE_FAILED,
        "PUT",
        "예상하지 못한 오류(KeyError)",
        "없음",
    )
    for empty in ("", "  "):
        blank = write_back(_BrokenSink('"base"', put_etag=empty), b"x", baseline='"base"', now=now)
        assert (blank.result, blank.stage, blank.reason, blank.etag, blank.word) == (
            EXTRA_WRITE_FAILED,
            "PUT",
            ETAG_MISSING,
            None,
            OLD_VERSION_WORD,
        )


def test_an_empty_etag_write_is_recorded_and_leaves_the_rewrite_button(database: Path) -> None:
    """빈 ETag 의 쓰기도 기록이 거절되지 않고 「실패」 로 남아 「S3 에 다시 쓰기」 가 선다."""
    repository = _edited_revision(database)
    app = _app(database)
    _click(app, REVISION_BUTTON_KEY)
    _click(app, APPLY_BUTTON_KEY)
    from datetime import datetime

    from capa_simulation.extra_process_intake import ETAG_MISSING

    state = repository.load_extra_process_state()
    active = state.active
    assert active is not None and active.sha256 is not None and needs_write(state)
    data = repository.load_extra_process_content(active.sha256)

    outcome = write_back(
        _BrokenSink(None, put_etag=""), data, baseline=state.baseline[0], now=datetime(2026, 11, 19)
    )
    repository.record_extra_process_write(
        version_seq=active.seq,
        result=outcome.result,
        written_by=None,
        etag=outcome.etag,
        seen_etag=outcome.seen_etag,
        stage=outcome.stage,
        reason=outcome.reason,
    )
    after = repository.load_extra_process_state()
    last = pending_write(after)
    assert isinstance(last, ExtraProcessS3Write) and last.reason == ETAG_MISSING
    assert needs_write(after)


def test_head_word_tells_same_from_old_version(database: Path) -> None:
    repository = _edited_revision(database)
    state = repository.load_extra_process_state()
    # 판 1 은 S3 메타 없이 적용했다 — 기준 ETag 가 없다.
    assert state.baseline == (None, None)
    assert head_word(None, state, {}) == "없음"
    assert head_word('"x"', state, {'"x"': "거절"}) == "거절"
    assert head_word('"y"', state, {}) == NEW_FILE_WORD


def _row(seq: int, kind: str, sha: str | None, etag: str | None = None) -> ExtraProcessVersion:
    from datetime import datetime

    return ExtraProcessVersion(
        seq=seq,
        kind=kind,
        version_no=None if sha is None else seq,
        sha256=sha,
        created_at=datetime(2026, 11, 19, 1, 0),
        s3_etag=etag,
    )


def _write(seq: int, version_seq: int, result: str, etag: str | None = None) -> ExtraProcessS3Write:
    from datetime import datetime

    return ExtraProcessS3Write(
        seq=seq,
        version_seq=version_seq,
        result=result,
        created_at=datetime(2026, 11, 19, 1, 0),
        etag=etag,
        stage="PUT" if result == EXTRA_WRITE_FAILED else None,
    )


def test_off_and_resume_keep_the_written_new_version_the_same() -> None:
    """끄기 → 단추 「다시 켜기」 뒤에도 같은 내용(sha)이다 — 앱이 쓴 파일의 ETag 는 「같음」 이고,
    아직 쓰지 못한 「새 판」 은 다시 켠 뒤에도 `EP-05` · 「S3 에 다시 쓰기」 거리다."""
    applied = _row(1, EXTRA_KIND_APPLY, "a" * 64, '"etag-1"')
    revised = _row(2, EXTRA_KIND_REVISION, "b" * 64)
    off = _row(3, EXTRA_KIND_OFF, None)
    resumed = _row(4, EXTRA_KIND_RESUME, "b" * 64)

    written = ExtraProcessState(
        (applied, revised, off, resumed), (_write(1, 2, EXTRA_WRITE_WRITTEN, '"etag-2"'),)
    )
    assert head_word('"etag-2"', written, {}) == "같음"
    assert not needs_write(written)

    kept = ExtraProcessState((applied, revised, off, resumed), (_write(1, 2, EXTRA_WRITE_KEPT),))
    assert needs_write(kept)
    pending = pending_write(kept)
    assert isinstance(pending, ExtraProcessS3Write) and pending.result == EXTRA_WRITE_KEPT
    # 기준은 아직 판 1 파일 — 그 ETag 는 활성 판(판 2 내용)에는 「옛 판」 이다.
    assert head_word('"etag-1"', kept, {}) == OLD_VERSION_WORD
    assert not needs_write(ExtraProcessState((applied,)))


def test_with_a_source_too_the_written_word_survives_the_next_round(database: Path) -> None:
    """원천 · 내보내기가 둘 다 꽂힌 꼴(운영이 될 꼴) — 쓴 뒤 다음 회차의 새 파일 감지 HEAD 가
    「같음 — 앱이 씀」 을 덮지 않고, 앱이 쓴 파일을 새 파일로 보지 않는다."""
    _edited_revision(database)
    app = _app(database, sink=True, source=True)

    _click(app, REVISION_BUTTON_KEY)
    _click(app, APPLY_BUTTON_KEY)
    app.run()

    assert any("가짜 S3 같음 — 앱이 씀" in text for text in _captions(app))
    assert active_state(app, "EP-02") is None
    assert active_state(app, "EP-05") is None


@pytest.mark.parametrize(
    ("version_no", "short", "full"),
    [
        (1, "부대공정 판 1을 S3 Drive 에", ("만든 판 1이 S3 Drive", "DB 의 판 1로 돕니다")),
        (2, "부대공정 판 2를 S3 Drive 에", ("만든 판 2가 S3 Drive", "DB 의 판 2로 돕니다")),
        (3, "부대공정 판 3을 S3 Drive 에", ("만든 판 3이 S3 Drive", "DB 의 판 3으로 돕니다")),
        (6, "부대공정 판 6을 S3 Drive 에", ("만든 판 6이 S3 Drive", "DB 의 판 6으로 돕니다")),
        (10, "부대공정 판 10을 S3 Drive 에", ("만든 판 10이 S3 Drive", "DB 의 판 10으로 돕니다")),
    ],
)
def test_the_unwritten_version_alert_picks_particles_by_the_number(
    monkeypatch: pytest.MonkeyPatch, version_no: int, short: str, full: tuple[str, str]
) -> None:
    """`EP-05` 글의 판 번호 뒤 조사(을/를 · 이/가 · (으)로)는 번호의 끝소리로 고른다."""
    from types import SimpleNamespace

    import capa_simulation.components.extra_process_admin as admin
    from capa_simulation import alerts

    sent: dict[str, dict[str, object]] = {}
    monkeypatch.setattr(admin, "installed_sink", lambda: object())
    monkeypatch.setattr(admin, "pending_write", lambda state: None)
    monkeypatch.setattr(admin, "_new_file_word", lambda state: None)
    monkeypatch.setattr(alerts, "state", lambda code, **kwargs: sent.update({code: kwargs}))
    state = SimpleNamespace(active=SimpleNamespace(version_no=version_no))

    admin._report_remote_state(state, "부대공정")  # type: ignore[arg-type]

    note = sent["EP-05"]
    assert note["active"] is True
    assert str(note["text"]).startswith(short), note["text"]
    assert all(part in str(note["full"]) for part in full), note["full"]
