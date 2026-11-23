# Purpose: Admin 「부대공정」 탭의 잠금 · 상태 줄 · 가져오기(가짜 원천) · 미리보기 · 적용 · 끄기 /
# 다시 켜기와 이력 표를 본다.

"""Admin 「부대공정」(`components/extra_process_admin.py` · `extra_process_intake.py` — 설계 A7).

1단계에는 가져오기 원천이 꽂히지 않는다 — 시험은 가짜 원천을 꽂고(`install_source`), C-DEP · 개발자
판정(`write_lock_reason`)은 갈아 끼워 연다. 꺼진 곳(사외 `app.py` 꼴)에서는 쓰는 단추가 모두 잠긴다.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest
from alert_marks import active_state, data_error_marks, flashed
from extra_process_fixtures import BOND, bump_version, edited, set_cell, template_files, zip_files
from percent_display import column_formats, shown_texts
from streamlit.testing.v1 import AppTest

from capa_simulation.components.data_error_mark import EMPTY_CLASS
from capa_simulation.components.extra_process_admin import (
    APPLY_BUTTON_KEY,
    APPLY_CONFIRM_KEY,
    DOWNLOAD_BUTTON_KEY,
    IMPORT_BUTTON_KEY,
    NOT_PRODUCTION_REASON,
    PREVIEW_BUTTON_KEY,
    TOGGLE_BUTTON_KEY,
    UNCONFIRMED_REASON,
    history_frame,
    status_line,
    write_lock_reason,
)
from capa_simulation.components.percent_cells import percent_cell_text
from capa_simulation.extra_process_intake import SAME_WORD, SourceFetch, stage_pack
from capa_simulation.persistence.models import (
    EXTRA_KIND_APPLY,
    EXTRA_KIND_OFF,
    ExtraProcessState,
    ExtraProcessVersion,
)
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.services.extra_process_pack import (
    JUDGE_APPLY,
    JUDGE_BACKWARD,
    JUDGE_RESUME,
    JUDGE_UNCHANGED,
    pack_sha256,
    read_pack_zip,
    template_zip,
)

OPEN_KEY = "__extra_open__"
PACK_KEY = "__extra_pack__"
NO_SCENARIO_KEY = "__extra_no_scenario__"
# 가짜 S3 Drive 자리(내보내기 꽂이)의 HEAD ETag — 있으면 꽂고, 가짜 원천도 같은 ETag 로 받는다.
DRIVE_ETAG_KEY = "__extra_drive_etag__"
# 가짜 원천이 ETag 를 따로 받지 않은 시험의 ETag(받기 · 머리 보기가 같다).
PACK_ETAG = '"가짜-판"'


def _script(database: Path) -> str:
    return f"""
from pathlib import Path

import streamlit as st

import capa_simulation.components.extra_process_admin as admin
import capa_simulation.settings as settings
from capa_simulation.extra_process_intake import (
    RemoteHead,
    SourceFetch,
    install_sink,
    install_source,
)
from capa_simulation.persistence.cache import get_scenario_repository
from capa_simulation.scenario_activation import bootstrap_latest_official_scenario


class FakeSource:
    label = "가짜 원천에서 가져오기"
    place = "가짜"

    def fetch(self):
        data = st.session_state[{PACK_KEY!r}]
        return SourceFetch(
            data=data,
            place="가짜",
            key="extra_process/current.zip",
            etag=st.session_state.get({DRIVE_ETAG_KEY!r}) or {PACK_ETAG!r},
        )

    def head(self):
        # 받기와 같은 ETag — 놓인 파일을 받기와 머리 보기가 같게 본다.
        return RemoteHead(st.session_state.get({DRIVE_ETAG_KEY!r}) or {PACK_ETAG!r})


class FakeSink:
    place = "가짜"

    def head(self):
        return RemoteHead(st.session_state.get({DRIVE_ETAG_KEY!r}))

    def put(self, data):
        raise AssertionError("쓰지 않는 시험")


original_path = settings.DUCKDB_PATH
original_lock = admin.write_lock_reason
settings.DUCKDB_PATH = Path({str(database)!r})
if st.session_state.get({OPEN_KEY!r}):
    admin.write_lock_reason = lambda: None
if st.session_state.get({PACK_KEY!r}) is not None:
    install_source(FakeSource())
if st.session_state.get({DRIVE_ETAG_KEY!r}) is not None:
    install_sink(FakeSink())
try:
    if not st.session_state.get({NO_SCENARIO_KEY!r}):
        bootstrap_latest_official_scenario(str(settings.DUCKDB_PATH))
    repository = get_scenario_repository(str(settings.DUCKDB_PATH))
    admin.render_extra_process_admin(repository, alert_tab="부대공정")
finally:
    install_source(None)
    install_sink(None)
    admin.write_lock_reason = original_lock
    settings.DUCKDB_PATH = original_path
"""


@pytest.fixture
def database(tmp_path: Path) -> Path:
    return tmp_path / "admin_extra.duckdb"


def _app(
    database: Path,
    *,
    open_place: bool = False,
    pack: bytes | None = None,
    no_scenario: bool = False,
    drive_etag: str | None = None,
) -> AppTest:
    app = AppTest.from_string(_script(database), default_timeout=120)
    app.session_state[OPEN_KEY] = open_place
    app.session_state[PACK_KEY] = pack
    app.session_state[NO_SCENARIO_KEY] = no_scenario
    app.session_state[DRIVE_ETAG_KEY] = drive_etag
    app.run()
    assert not app.exception, [item.message for item in app.exception]
    return app


def _repository(database: Path) -> DuckDBScenarioRepository:
    return DuckDBScenarioRepository(database)


def _captions(app: AppTest) -> list[str]:
    return [str(item.value) for item in app.caption]


def test_off_the_production_server_every_writing_button_is_locked(database: Path) -> None:
    app = _app(database)

    assert any(text == "부대공정 · 판 없음" for text in _captions(app))
    # 1단계는 원천이 꽂히지 않아 가져오기 단추가 서지 않는다.
    assert not [button for button in app.button if button.key == IMPORT_BUTTON_KEY]
    toggle = app.button(key=TOGGLE_BUTTON_KEY)
    assert toggle.disabled and toggle.help == NOT_PRODUCTION_REASON
    downloads = [item for item in app.get("download_button") if item.key == DOWNLOAD_BUTTON_KEY]
    assert len(downloads) == 1


def test_write_lock_is_closed_without_a_managed_server() -> None:
    assert write_lock_reason() == NOT_PRODUCTION_REASON


def test_a_fake_source_imports_previews_and_applies_a_pack(database: Path) -> None:
    pack = zip_files(template_files())
    app = _app(database, open_place=True, pack=pack)

    app.button(key=IMPORT_BUTTON_KEY).click().run()
    assert not app.exception, [item.message for item in app.exception]
    assert any("가짜 적용 전 판 1" in text for text in _captions(app))
    assert any("측정률 빈칸 → 1.0 2칸 · 0 → 1.0 으로 셈 0칸" in text for text in _captions(app))
    # 지금 판과의 차이 · 되돌리는 칸은 시험 계산 없이 「적용」 위 값 줄에 선다(설계 3-4 의 5 · 6).
    assert any(
        text.startswith("더한 공정 2 · 뺀 공정 0 · 바뀐 칸 ")
        and "앞 판 값으로 되돌리는 칸 0" in text
        for text in _captions(app)
    )
    assert not [box for box in app.checkbox if box.key == APPLY_CONFIRM_KEY]

    app.button(key=PREVIEW_BUTTON_KEY).click().run()
    assert not app.exception, [item.message for item in app.exception]
    outcome = next(frame.value for frame in app.dataframe if "결과" in frame.value)
    assert list(outcome["결과"]) == ["합침", "합침"]
    rate_frame = next(frame for frame in app.dataframe if "확보율" in frame.value)
    rates = rate_frame.value
    assert {BOND, "DEMO_New_AOI"} == set(rates["공정"])
    # 확보율은 비율 값 그대로 싣고 글만 %(다른 화면의 % 표 칸과 같은 소수 둘째 자리 고정 —
    # 2026-11-19 보드 m19-e2e-percent) — 비율(6.3903)로 보였고(2026-11-18 E2E), 끝 0 을 지워 줄마다
    # 자릿수가 달랐다(605.3% · 639.03%).
    assert column_formats(rate_frame)["확보율"] is None
    texts = shown_texts(rate_frame, "확보율")
    assert texts and all(text.endswith("%") and text[-4] == "." for text in texts), texts
    assert texts == [percent_cell_text(value) for value in rates["확보율"]]
    # 같은 표의 대수 칸은 Streamlit 기본 꼴 글(소수 넷째 자리까지 · 끝 0 걷음)이다 — Styler 6자리
    # 글이 새지 않는다.
    assert all(len(text.partition(".")[2]) <= 4 for text in shown_texts(rate_frame, "소요대수"))

    app.button(key=APPLY_BUTTON_KEY).click().run()
    assert not app.exception, [item.message for item in app.exception]
    state = _repository(database).load_extra_process_state()
    assert state.active is not None and state.active.version_no == 1
    assert state.active.s3_key == "extra_process/current.zip"
    assert any(text.startswith("부대공정 · 판 1 · 공정 2 · 적용 ") for text in _captions(app))

    # 같은 파일을 다시 가져오면 「바뀐 것 없음」 이고 아무것도 쓰지 않는다(쓰기 기록도 없음 —
    # 「놓인 파일 같음」 은 S3 Drive 에 쓰지 못한 「새 판」 일 때만).
    app.button(key=IMPORT_BUTTON_KEY).click().run()
    assert any("바뀐 것 없음" in str(note.value) for note in flashed(app))
    after = _repository(database).load_extra_process_state()
    assert after.last_seq == 1 and after.writes == ()


def test_the_new_file_alert_clears_once_that_file_is_imported_and_applied(database: Path) -> None:
    """S3 Drive 에 사람이 놓은 새 파일(`EP-02`)을 같은 세션이 가져와 적용하면 그 회차에 알림이
    걷히고 상태 줄도 그 파일 낱말로 바뀐다(2026-11-19 E2E e3-D2 — HEAD 를 5분 띄워 보는 메모가
    가져오기 · 적용 뒤에도 「새 파일」 을 이어 적용 뒤 5분 동안 「가져오지 않은 파일」 이
    남았다)."""
    pack = zip_files(template_files())
    app = _app(database, open_place=True, pack=pack, drive_etag='"사람-1"')
    assert active_state(app, "EP-02") is not None

    app.button(key=IMPORT_BUTTON_KEY).click().run()
    assert not app.exception, [item.message for item in app.exception]
    assert active_state(app, "EP-02") is None
    assert any("가짜 적용 전 판 1" in text for text in _captions(app))

    app.button(key=APPLY_BUTTON_KEY).click().run()
    assert not app.exception, [item.message for item in app.exception]
    state = _repository(database).load_extra_process_state()
    assert state.active is not None and state.active.s3_etag == '"사람-1"'
    assert active_state(app, "EP-02") is None
    assert any(f"가짜 {SAME_WORD}" in text for text in _captions(app)), _captions(app)


def test_a_zero_ratio_pack_is_accepted_with_its_cell_count(database: Path) -> None:
    files = edited(
        template_files(),
        "03_productivity.csv",
        lambda rows: set_cell(
            rows, lambda row: row[0] == BOND and row[7] == "202607", "WF측정률", "0"
        ),
    )
    app = _app(database, open_place=True, pack=zip_files(files))

    app.button(key=IMPORT_BUTTON_KEY).click().run()

    assert any("0 → 1.0 으로 셈 1칸" in text for text in _captions(app))
    assert not app.button(key=APPLY_BUTTON_KEY).disabled


def test_a_rejected_pack_shows_the_rejection_table_without_apply(database: Path) -> None:
    files = edited(
        template_files(),
        "01_process.csv",
        lambda rows: set_cell(rows, lambda row: row[0] == BOND, "소요기준", ""),
    )
    app = _app(database, open_place=True, pack=zip_files(files))

    app.button(key=IMPORT_BUTTON_KEY).click().run()

    table = next(
        frame.value for frame in app.dataframe if "규칙" in frame.value and "파일" in frame.value
    )
    assert list(table["규칙"]) == ["V-03"]
    assert not [button for button in app.button if button.key == APPLY_BUTTON_KEY]


def test_a_pack_that_brings_back_older_values_needs_a_check_before_apply(database: Path) -> None:
    """G12 — 판 2 위에 판 1 사본의 판 번호만 3 으로 올린 판을 받으면 값 줄에 되돌리는 칸이 서고,
    확인 칸을 채워야 「적용」 이 열린다(UI-NTF-09)."""
    from auto_update_fakes import new_repository
    from test_extra_process_registration import apply_template

    repository = new_repository(database)
    apply_template(repository)
    second = edited(
        bump_version(template_files(), 2),
        "03_productivity.csv",
        lambda rows: set_cell(
            rows, lambda row: row[0] == BOND and row[7] == "202607", "UPEH", "60000"
        ),
    )
    apply_template(repository, expected_seq=1, files=second)
    app = _app(database, open_place=True, pack=zip_files(bump_version(template_files(), 3)))

    app.button(key=IMPORT_BUTTON_KEY).click().run()

    line = next(text for text in _captions(app) if text.startswith("더한 공정 0 · 뺀 공정 0"))
    assert "앞 판 값으로 되돌리는 칸 0" not in line
    apply = app.button(key=APPLY_BUTTON_KEY)
    assert apply.disabled and apply.help == UNCONFIRMED_REASON
    app.checkbox(key=APPLY_CONFIRM_KEY).check().run()
    assert not app.button(key=APPLY_BUTTON_KEY).disabled


def test_the_trial_button_place_shows_a_data_error_when_no_scenario_is_loaded(
    database: Path,
) -> None:
    """시험 계산에 쓸 시나리오를 못 읽으면 단추가 까닭 없이 사라지지 않고 그 자리에 「데이터
    Error」 마크가 선다(UI-NTF-08 — 불러온 시나리오가 없는 것은 마크 대신 회색 빈 상태 한 줄).
    「적용」 은 그대로 선다."""
    app = _app(database, open_place=True, pack=zip_files(template_files()), no_scenario=True)

    app.button(key=IMPORT_BUTTON_KEY).click().run()

    assert not app.exception, [item.message for item in app.exception]
    assert not [button for button in app.button if button.key == PREVIEW_BUTTON_KEY]
    bodies = [str(element.proto.body) for element in app.get("html")]
    assert data_error_marks(app) + sum(EMPTY_CLASS in body for body in bodies) == 1
    assert not app.button(key=APPLY_BUTTON_KEY).disabled


def test_off_and_resume_toggle_on_the_same_button(database: Path) -> None:
    app = _app(database, open_place=True, pack=zip_files(template_files()))
    app.button(key=IMPORT_BUTTON_KEY).click().run()
    app.button(key=APPLY_BUTTON_KEY).click().run()

    assert app.button(key=TOGGLE_BUTTON_KEY).label == "끄기"
    app.button(key=TOGGLE_BUTTON_KEY).click().run()
    assert _repository(database).load_extra_process_state().off
    assert app.button(key=TOGGLE_BUTTON_KEY).label == "다시 켜기"
    assert any(text.startswith("부대공정 · 꺼짐 · 마지막 판 1") for text in _captions(app))

    app.button(key=TOGGLE_BUTTON_KEY).click().run()
    state = _repository(database).load_extra_process_state()
    assert state.active is not None and state.active.version_no == 1
    assert app.button(key=TOGGLE_BUTTON_KEY).label == "끄기"


def _version(seq: int, kind: str, version_no: int | None, sha: str | None) -> ExtraProcessVersion:
    return ExtraProcessVersion(
        seq=seq,
        kind=kind,
        version_no=version_no,
        sha256=sha,
        created_at=datetime(2026, 11, 13, 9, 12),
        applied_by="dev01",
        process_count=2 if sha else None,
        row_counts=json.dumps({"01_process.csv": 2, "02_route.csv": 3}) if sha else None,
    )


def test_status_line_and_history_carry_values_only() -> None:
    sha = "a" * 64
    on = ExtraProcessState((_version(1, EXTRA_KIND_APPLY, 3, sha),))
    off = ExtraProcessState((*on.history, _version(2, EXTRA_KIND_OFF, None, None)))

    assert status_line(ExtraProcessState()) == "부대공정 · 판 없음"
    assert status_line(on) == "부대공정 · 판 3 · 공정 2 · 적용 11-13 09:12"
    assert status_line(off) == "부대공정 · 꺼짐 · 마지막 판 3"
    frame = history_frame(off)
    assert list(frame["갈래"]) == ["끄기", "적용"]
    assert list(frame["판"]) == ["", "3"]
    assert list(frame["적용한 사람"]) == ["de…", "de…"]
    assert list(frame["sha"]) == ["", "aaaaaaaa"]
    assert list(frame["행 수"]) == ["", "5"]


def test_stage_pack_judges_against_the_history() -> None:
    one = zip_files(template_files())
    sha = pack_sha256(one)
    now = datetime(2026, 11, 18, 9, 0)

    empty = stage_pack(ExtraProcessState(), SourceFetch(one, "가짜"), now=now)
    assert (
        empty.applicable and empty.judgement is not None and empty.judgement.verdict == JUDGE_APPLY
    )

    on = ExtraProcessState((_version(1, EXTRA_KIND_APPLY, 1, sha),))
    same = stage_pack(on, SourceFetch(one, "가짜"), now=now)
    assert same.judgement is not None and same.judgement.verdict == JUDGE_UNCHANGED
    assert not same.applicable

    off = ExtraProcessState((*on.history, _version(2, EXTRA_KIND_OFF, None, None)))
    resumed = stage_pack(off, SourceFetch(one, "가짜"), now=now)
    assert resumed.judgement is not None and resumed.judgement.verdict == JUDGE_RESUME
    assert resumed.seen_seq == 2

    changed = edited(
        template_files(),
        "03_productivity.csv",
        lambda rows: set_cell(
            rows, lambda row: row[0] == BOND and row[7] == "202607", "UPEH", "59000"
        ),
    )
    backward = stage_pack(on, SourceFetch(zip_files(changed), "가짜"), now=now)
    assert backward.judgement is not None and backward.judgement.verdict == JUDGE_BACKWARD
    assert not backward.applicable
    forward = stage_pack(on, SourceFetch(zip_files(bump_version(changed, 2)), "가짜"), now=now)
    assert forward.applicable
    assert read_pack_zip(template_zip()).accepted is False


def test_the_open_tab_raises_a_state_alert_for_extras_dropped_from_the_official_version(
    database: Path,
) -> None:
    """자동 갱신(화면 없음)이 뺀 부대공정도 최신 공식버전 출처 표로 잡는다 — `EP-03` 상태 알림."""
    from auto_update_fakes import new_repository, publish_snapshot
    from test_extra_process_registration import apply_template, register

    repository = new_repository(database)
    files = edited(
        template_files(),
        "02_route.csv",
        lambda rows: set_cell(rows, lambda row: row[0] == BOND, "참조공정", "DEMO_Nowhere"),
    )
    apply_template(repository, files=files)
    snapshot, memo = register(repository)
    assert memo == "부대공정 판 1 · 1 합침 · 1 뺌"
    publish_snapshot(repository, snapshot)

    app = _app(database)

    dropped = active_state(app, "EP-03")
    assert dropped is not None and dropped["short"] == "공식 v1 에서 뺀 부대공정 1개"
    assert BOND in dropped["full"]
    assert active_state(app, "EP-04") is None


def test_a_saved_route_exception_declaration_misses_the_preview_memo(database: Path) -> None:
    """시험 계산 메모는 (sha, 계산 토큰)마다 하나다 — 부하 예외 선언을 저장하면(공용 프로필 비우기
    뒤) 메모가 빗나가 옛 판의 결과를 다시 보이지 않고, 다시 누르면 새 판으로 접은 키로 센다."""
    from before_custom_copy import seed_route_declaration

    from capa_simulation.components.extra_process_admin import PREVIEW_KEY
    from capa_simulation.persistence.cache import (
        clear_global_route_load_exceptions_cache,
        get_scenario_repository,
    )
    from capa_simulation.services.simulation_cache import calculation_token

    clear_global_route_load_exceptions_cache()
    pack = zip_files(template_files())
    app = _app(database, open_place=True, pack=pack)
    app.button(key=IMPORT_BUTTON_KEY).click().run()
    app.button(key=PREVIEW_BUTTON_KEY).click().run()
    assert not app.exception, [item.message for item in app.exception]
    sha, plain_token = app.session_state[PREVIEW_KEY][0]
    assert any("결과" in frame.value for frame in app.dataframe)

    declaration = seed_route_declaration()
    get_scenario_repository(str(database)).append_route_load_exceptions(
        expected_seq=0, entries=declaration, applied_by=None, source_place="test"
    )
    clear_global_route_load_exceptions_cache()
    app.run()
    assert not app.exception, [item.message for item in app.exception]
    assert not any("결과" in frame.value for frame in app.dataframe)

    app.button(key=PREVIEW_BUTTON_KEY).click().run()
    assert not app.exception, [item.message for item in app.exception]
    assert app.session_state[PREVIEW_KEY][0] == (sha, calculation_token(plain_token, declaration))
    clear_global_route_load_exceptions_cache()
