# Purpose: 편집기가 만든 부대공정 판이 받은 판 상자를 지나 「앱 입력」 새 판으로 들어가는 길, 그
# 판의 S3 Drive 경계(쓸 몫 아님 · 놓인 파일 같음 적기)와 세 길 공용 「뺀 공정」 확인 칸을 본다.

"""편집기 판의 받은 판 상자 · 적용 · S3 Drive 경계(`extra_process_intake.stage_editor_pack` ·
`components/extra_process_admin.py` — 편집기 화면은 다음 단계라, 시험이 그 셈을 대신해 받은 판
자리에 판을 둔다).

편집기 화면이 할 셈은 `_stage_from_editor` 하나다 — 펼친 판(활성 판, 끈 동안 마지막 내용 판)을
모형으로 펴서 고치고(`with_lines` · `with_cells`) 접어(`fold`) 정규 바이트로 만든 뒤(`canonical`)
펼친 때의 차례 · sha · 접은 줄을 든 `EditorOrigin` 으로 싣는다. 견본 판(판 1 — 두 공정 모두 통째
옮김)에 합성 새 공정 `DEMO_New_Sort` 를 더하는 고침을 쓴다. 「뺀 공정」 확인 칸은 받은 판 상자
공용이라 가져온 판 · 리비전 판 · 편집기 판 셋 모두에서 본다.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from alert_marks import active_state, flashed, states
from auto_update_fakes import new_repository
from extra_process_fixtures import AOI, bump_version, edited, template_files, zip_files
from streamlit.testing.v1 import AppTest
from test_extra_process_admin import PACK_KEY, _app
from test_extra_process_editor import NEW_NAME, YEAR_2026, _fill, _new_line_fields
from test_extra_process_registration import apply_template
from test_extra_process_revision_admin import (
    FETCH_KEY,
    _placed_from_download,
    _row,
)
from test_extra_process_revision_admin import _app as _drive_app
from test_extra_process_revision_admin import _click as _drive_click

from capa_simulation.audit import recorder
from capa_simulation.components.extra_process_admin import (
    APPLY_BUTTON_KEY,
    EDITOR_APPLY_HELP,
    EDITOR_PROBLEM_COLUMNS,
    IMPORT_BUTTON_KEY,
    REMOVED_CONFIRM_KEY,
    REMOVED_CONFIRM_LABEL,
    REVISION_APPLY_LABEL,
    REWRITE_BUTTON_KEY,
    TURNS_ON_PART,
    UNCONFIRMED_REMOVED_REASON,
    history_frame,
)
from capa_simulation.components.literal_markdown import literal_markdown
from capa_simulation.extra_process_intake import (
    OLD_VERSION_WORD,
    SAME_WORD,
    EditorOrigin,
    RevisionOrigin,
    SourceFetch,
    StagedPack,
    head_word,
    needs_write,
    pending_write,
    placed_matches,
    stage_editor_pack,
    stage_pack,
    unplaced,
)
from capa_simulation.persistence.models import (
    EXTRA_EDITOR_PLACE,
    EXTRA_KIND_APPLY,
    EXTRA_KIND_OFF,
    EXTRA_KIND_RESUME,
    EXTRA_KIND_REVISION,
    EXTRA_REVISION_PLACE,
    EXTRA_WRITE_PLACED_REASON,
    EXTRA_WRITE_WRITTEN,
    ExtraProcessS3Write,
    ExtraProcessState,
    ExtraProcessVersion,
)
from capa_simulation.persistence.repository import DuckDBScenarioRepository
from capa_simulation.services.extra_process_editor import (
    PRODUCTIVITY,
    UPEH_COLUMN,
    EditorModel,
    canonical,
    fold,
    model_from_pack,
    with_cells,
    with_lines,
)
from capa_simulation.services.extra_process_pack import (
    BOTH_CLASSES,
    FORMAT_VERSION,
    JUDGE_APPLY,
    JUDGE_UNCHANGED,
    MASS,
    PackChanges,
    PackInfo,
    PackJudgement,
    bundle_pack_files,
    pack_sha256,
    read_pack_zip,
)

NOW = datetime(2026, 11, 27, 9, 0)
WRITTEN_AT = "2026-11-27T09:00:00+09:00"


@pytest.fixture
def database(tmp_path: Path) -> Path:
    return tmp_path / "editor_box.duckdb"


def _stage_from_editor(
    repository: DuckDBScenarioRepository, edit: Callable[[EditorModel], EditorModel]
) -> StagedPack:
    """편집기 화면이 할 셈 — 펼친 판을 고쳐 다음 판(마지막 내용 판 + 1)으로 접고 받은 판 자리에
    싣는다."""
    state = repository.load_extra_process_state()
    opened = state.active or state.latest_content
    base = (
        None
        if opened is None or opened.sha256 is None
        else read_pack_zip(repository.load_extra_process_content(opened.sha256)).pack
    )
    latest = state.latest_content
    version_no = (0 if latest is None else latest.version_no or 0) + 1
    folded = fold(
        edit(model_from_pack(base)),
        PackInfo(FORMAT_VERSION, version_no, WRITTEN_AT, "", "앱 입력 시험"),
    )
    origin = EditorOrigin(state.last_seq, None if opened is None else opened.sha256, folded)
    return stage_editor_pack(canonical(folded.rows), origin, now=NOW, base=base)


def _add_new_process(upeh: float = 30000.0) -> Callable[[EditorModel], EditorModel]:
    """펼친 줄은 그대로 두고 새 공정 한 줄(2026 한 해 값)을 더하는 고침."""

    def edit(model: EditorModel) -> EditorModel:
        rows = [(line.line_id, line.fields) for line in model.lines]
        added = with_lines(model, [*rows, ("n1", _new_line_fields())])
        values = {"upeh": upeh, "owned": 5.0, "rate": 0.8, "vital": 1.1}
        return with_cells(added, _fill("n1", YEAR_2026, values))

    return edit


def _captions(app: AppTest) -> list[str]:
    return [str(item.value) for item in app.caption]


def _value_line(app: AppTest) -> str:
    return next(text for text in _captions(app) if text.startswith("더한 공정 "))


def _history(app: AppTest) -> pd.DataFrame:
    return next(frame.value for frame in app.dataframe if "S3 쓰기" in frame.value)


def _audit_lines(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    lines: list[dict[str, Any]] = []

    def capture(event: str, **fields: Any) -> None:
        lines.append({"ev": event, **fields})

    monkeypatch.setattr(recorder, "record", capture)
    return lines


# --------------------------------------------------------------------------- 받은 판 상자 · 적용


def test_an_editor_pack_rides_the_staged_box_and_applies_as_app_input(
    database: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """편집기 판은 받은 판 상자의 머리 「앱에서 만든 판」 · 값 줄 · 「새 판 적용」 을 그대로
    지나고, 적용하면 갈래 「새 판」 · 원천 자리 「앱 입력」 · 바탕 칸 빈 줄이 되어 판 이력에 「앱
    입력」 으로 보인다. 내보내기가 꽂혀 있어도 S3 Drive 는 쓰지 않는다(가짜 내보내기의 PUT 은
    부르면 실패한다)."""
    repository = new_repository(database)
    apply_template(repository)
    staged = _stage_from_editor(repository, _add_new_process())
    assert staged.judgement is not None and staged.judgement.verdict == JUDGE_APPLY
    assert staged.seen_seq == 1 and staged.fetch.place == EXTRA_EDITOR_PLACE
    lines = _audit_lines(monkeypatch)

    app = _app(database, open_place=True, staged=staged, drive_etag='"판1-파일"')

    assert any(
        str(item.value).startswith("**앱에서 만든 판** · 새 판 2 · sha ") for item in app.markdown
    )
    line = _value_line(app)
    assert line.startswith("더한 공정 1 · 뺀 공정 0 · ") and TURNS_ON_PART not in line
    apply = app.button(key=APPLY_BUTTON_KEY)
    assert apply.label == REVISION_APPLY_LABEL and apply.help == EDITOR_APPLY_HELP
    assert not apply.disabled

    apply.click().run()
    assert not app.exception, [item.message for item in app.exception]

    state = repository.load_extra_process_state()
    active = state.active
    assert active is not None and active.kind == EXTRA_KIND_REVISION and active.editor_made
    assert active.version_no == 2 and active.process_count == 3
    assert (active.base_scenario_ref, active.base_revision_ref) == (None, None)
    assert state.writes == ()
    assert active_state(app, "EP-05") is None
    assert any("부대공정 판 2 적용 — 앱 입력" in str(note.value) for note in flashed(app))
    assert not [button for button in app.button if button.key == APPLY_BUTTON_KEY]
    history = _history(app)
    assert list(history["갈래"]) == ["앱 입력", "적용"] and list(history["바탕"]) == ["", ""]
    assert [line["ev"] for line in lines if line["ev"].startswith("admin_extra")] == [
        "admin_extra_process_editor"
    ]


def test_an_editor_pack_opened_before_another_write_is_refused(database: Path) -> None:
    """적용은 펼친 때의 차례와 대조한다 — 펼친 뒤 다른 쓰기(남의 끄기)가 끼었으면 쓰지 않고 「그
    사이 바뀜」 오류 하나만 낸다(누른 때의 차례를 쓰면 남이 끈 판을 말없이 다시 켠다). 펼친 뒤
    다른 판이 들어왔으면 판 번호 검사가 먼저 막는다."""
    repository = new_repository(database)
    apply_template(repository)
    staged = _stage_from_editor(repository, _add_new_process())
    repository.turn_off_extra_process(expected_seq=1, applied_by=None)

    app = _app(database, open_place=True, staged=staged)
    app.button(key=APPLY_BUTTON_KEY).click().run()
    assert not app.exception, [item.message for item in app.exception]

    state = repository.load_extra_process_state()
    assert state.last_seq == 2 and state.off
    assert any("그 사이 바뀌었습니다" in str(note.value) for note in flashed(app, "error"))

    apply_template(repository, expected_seq=2, files=bump_version(template_files(), 2))
    app = _app(database, open_place=True, staged=staged)
    app.button(key=APPLY_BUTTON_KEY).click().run()
    assert repository.load_extra_process_state().last_seq == 3
    assert any("보다 커야 합니다" in str(note.value) for note in flashed(app, "error"))


def test_a_rejected_editor_pack_points_each_row_at_the_editor_place(database: Path) -> None:
    """관문이 거절한 편집기 판은 거절 표 앞에 편집기 자리(공정 · 표 · 양산구분 · 칸 · 기간 · 옮긴
    줄)를 싣고 「적용」 을 세우지 않는다."""
    repository = new_repository(database)
    apply_template(repository)

    def zero_upeh(model: EditorModel) -> EditorModel:
        added = _add_new_process()(model)
        return with_cells(
            added, {**added.cells, (("n1", PRODUCTIVITY, MASS, UPEH_COLUMN), 202603): 0.0}
        )

    staged = _stage_from_editor(repository, zero_upeh)
    assert staged.judgement is None and not staged.reading.accepted

    app = _app(database, open_place=True, staged=staged)

    assert any(str(item.value).startswith("**앱에서 만든 판** · 거절 · ") for item in app.markdown)
    table = next(frame.value for frame in app.dataframe if "옮긴 줄" in frame.value)
    assert tuple(table.columns) == EDITOR_PROBLEM_COLUMNS
    placed = table[table["공정"] == NEW_NAME]
    assert not placed.empty
    first = placed.iloc[0]
    # 바탕 없는 새 공정의 ER 은 양산을 따라 한 줄(`모두`)로 접힌다.
    assert (first["표"], first["양산구분"], first["칸"]) == (
        PRODUCTIVITY,
        BOTH_CLASSES,
        UPEH_COLUMN,
    )
    assert first["기간"] == "26.03" and not first["옮긴 줄"]
    assert first["파일"] == "03_productivity.csv"
    assert not [button for button in app.button if button.key == APPLY_BUTTON_KEY]


def test_an_editor_pack_while_off_says_applying_turns_it_on(database: Path) -> None:
    """끈 동안 편집기는 마지막 내용 판을 펼치고, 그 판의 값 줄 끝에 「적용하면 켜짐」 이 붙는다 —
    적용하면 그 판으로 다시 켜진다. 차이는 펼친 판과 견준다."""
    repository = new_repository(database)
    apply_template(repository)
    repository.turn_off_extra_process(expected_seq=1, applied_by=None)
    staged = _stage_from_editor(repository, _add_new_process())

    app = _app(database, open_place=True, staged=staged)

    line = _value_line(app)
    assert line.startswith("더한 공정 1 · 뺀 공정 0 · ") and line.endswith(TURNS_ON_PART)
    app.button(key=APPLY_BUTTON_KEY).click().run()
    assert not app.exception, [item.message for item in app.exception]
    state = repository.load_extra_process_state()
    assert not state.off and state.active is not None and state.active.version_no == 2


def test_the_history_shows_an_editor_version_as_app_input_without_a_base() -> None:
    def version(seq: int, kind: str, place: str | None, ref: str | None) -> ExtraProcessVersion:
        return ExtraProcessVersion(
            seq=seq,
            kind=kind,
            version_no=seq,
            sha256=str(seq) * 64,
            created_at=NOW,
            source_place=place,
            base_scenario_ref=ref,
            base_revision_ref=ref,
        )

    state = ExtraProcessState(
        (
            version(1, EXTRA_KIND_APPLY, "S3 Drive", None),
            version(2, EXTRA_KIND_REVISION, EXTRA_REVISION_PLACE, "rev-2"),
            version(3, EXTRA_KIND_REVISION, EXTRA_EDITOR_PLACE, None),
        )
    )

    frame = history_frame(state, {"rev-2": "DEMO 시나리오 r2"})

    assert list(frame["갈래"]) == ["앱 입력", "새 판", "적용"]
    assert list(frame["바탕"]) == ["", "DEMO 시나리오 r2", ""]


# --------------------------------------------------------------------------- S3 Drive 경계


def _editor_state(*, written: bool = False) -> tuple[ExtraProcessState, bytes]:
    """판 1(가져와 적용 — ETag 있음) 위에 편집기 판 2 가 활성인 합성 판 이력과 판 2 바이트."""
    first = bundle_pack_files(template_files())
    second = bundle_pack_files(bump_version(template_files(), 2))
    applied = _row(1, EXTRA_KIND_APPLY, pack_sha256(first), '"set-v1"')
    editor = _row(2, EXTRA_KIND_REVISION, pack_sha256(second), source_place=EXTRA_EDITOR_PLACE)
    writes = (
        (
            ExtraProcessS3Write(
                seq=1,
                version_seq=2,
                result=EXTRA_WRITE_WRITTEN,
                created_at=NOW,
                etag='"사람이-놓은-판2"',
                reason=EXTRA_WRITE_PLACED_REASON,
            ),
        )
        if written
        else ()
    )
    return ExtraProcessState((applied, editor), writes), second


def test_an_editor_version_owes_the_drive_nothing_but_a_placed_copy_is_noted() -> None:
    """경계2 — 편집기 판은 S3 Drive 에 쓸 몫이 아니라(`EP-05` · `EP-06` · 「S3 에 다시 쓰기」 밖)
    활성이어도 쓰기 대기가 없다. 다만 사람이 그 판 양식을 그대로 놓아 가져오면 「놓인 파일 같음」
    은 적을 거리다 — 적으면 그 ETag 가 기준이 되어 「같음」 이고, 다시 가져와도 더 적지 않는다.
    「새 판으로」 판은 지금처럼 쓸 몫이다."""
    state, second = _editor_state()
    assert pending_write(state) is False and not needs_write(state)
    assert unplaced(state)
    # 기준은 아직 판 1 파일 — 활성 판(판 2 내용)에는 「옛 판」 이다.
    assert head_word('"set-v1"', state, {}) == OLD_VERSION_WORD

    fetched = SourceFetch(
        data=second, place="S3 Drive", key="extra_process/", etag='"사람이-놓은-판2"'
    )
    staged = stage_pack(state, fetched, now=NOW)
    assert staged.judgement is not None and staged.judgement.verdict == JUDGE_UNCHANGED
    assert placed_matches(state, staged)

    noted, _ = _editor_state(written=True)
    assert noted.baseline == ('"사람이-놓은-판2"', 2)
    assert head_word('"사람이-놓은-판2"', noted, {}) == SAME_WORD
    assert not unplaced(noted) and not placed_matches(noted, staged)

    # 끄고 단추로 다시 켜도 같은 내용이라 쓸 몫이 아니다.
    off = _row(3, EXTRA_KIND_OFF, None)
    resumed = _row(4, EXTRA_KIND_RESUME, state.history[1].sha256, source_place=EXTRA_EDITOR_PLACE)
    again = ExtraProcessState((*state.history, off, resumed))
    assert pending_write(again) is False and unplaced(again)

    revised = _row(2, EXTRA_KIND_REVISION, state.history[1].sha256)
    assert needs_write(ExtraProcessState((state.history[0], revised)))


def _apply_editor_version(repository: DuckDBScenarioRepository) -> ExtraProcessVersion:
    """판 1 을 적용하고 그 위에 편집기 판 2 를 넣는다(저장소 메서드 — 화면 셈은 위 시험이 본다)."""
    apply_template(repository)
    staged = _stage_from_editor(repository, _add_new_process())
    pack = staged.reading.pack
    assert pack is not None
    repository.apply_editor_extra_process(
        staged.fetch.data,
        sha256=staged.reading.sha256,
        version_no=pack.info.version_no,
        expected_seq=staged.seen_seq,
        applied_by=None,
        process_count=len(pack.processes),
        row_counts="{}",
    )
    active = repository.load_extra_process_state().active
    assert active is not None and active.editor_made
    return active


def test_with_a_sink_an_editor_version_raises_no_write_alert_and_no_rewrite(database: Path) -> None:
    """내보내기가 꽂혀 있어도 편집기 판은 쓰지 못함(`EP-05`) · 「S3 에 다시 쓰기」 거리가 아니다."""
    _apply_editor_version(new_repository(database))

    app = _drive_app(database, sink=True, head='"판1-파일"')

    assert active_state(app, "EP-05") is None and states(app, "EP-05")
    assert not [button for button in app.button if button.key == REWRITE_BUTTON_KEY]


def test_with_a_source_a_placed_editor_version_moves_the_baseline_without_drift(
    database: Path,
) -> None:
    """원천만 꽂힌 C-DEP — 편집기 판 뒤에 판 어긋남(`EP-06`)이 서지 않는다. 사람이 그 판 양식을
    그대로 놓으면 처음엔 「새 파일」(`EP-02`)이고, 가져오면 「놓인 파일 같음」 이 적혀 기준이
    옮겨진다 — 다른 세션도 그 파일을 「같음」 으로 본다(적지 않으면 기준이 판 1 파일에 머물러
    `EP-02` 가 남는다)."""
    repository = new_repository(database)
    active = _apply_editor_version(repository)
    placed = _placed_from_download(repository, str(active.sha256))
    app = _drive_app(database, source=True, head='"사람이-놓은-판2"')
    assert active_state(app, "EP-06") is None and states(app, "EP-06")
    assert active_state(app, "EP-02") is not None

    app.session_state[FETCH_KEY] = placed
    _drive_click(app, IMPORT_BUTTON_KEY)

    state = repository.load_extra_process_state()
    (noted,) = state.writes
    assert noted.placed and noted.version_seq == active.seq
    assert state.baseline == ('"사람이-놓은-판2"', active.seq)
    notes = [str(note.value) for note in flashed(app)]
    assert any("활성 판 2 내용과 같습니다" in text for text in notes)
    assert not any("판 어긋남" in text for text in notes)
    assert active_state(app, "EP-02") is None and active_state(app, "EP-06") is None

    other = _drive_app(database, source=True, head='"사람이-놓은-판2"')
    assert active_state(other, "EP-02") is None
    assert any(f"가짜 S3 {SAME_WORD}" in str(item.value) for item in other.caption)

    other.session_state[FETCH_KEY] = placed
    _drive_click(other, IMPORT_BUTTON_KEY)
    assert len(repository.load_extra_process_state().writes) == 1
    assert any("바뀐 것 없음" in str(note.value) for note in flashed(other, "info"))


# ----------------------------------------------------------------- 뺀 공정 확인(세 길 공용)


def _without_aoi(version: int) -> bytes:
    """견본에서 `DEMO_New_AOI` 를 모든 장에서 지운 판(판 번호 `version`)."""
    files = bump_version(template_files(), version)
    for name in sorted(files)[1:]:
        files = edited(
            files, name, lambda rows: [rows[0], *(row for row in rows[1:] if row[0] != AOI)]
        )
    return zip_files(files)


def _drop_aoi(model: EditorModel) -> EditorModel:
    return with_lines(
        model, [(line.line_id, line.fields) for line in model.lines if line.base_name != AOI]
    )


def _assert_removed_gate(app: AppTest, count: int) -> None:
    """뺀 공정 확인 칸이 서고 비어 있어 「적용」 이 잠겨 있다."""
    box = app.checkbox(key=REMOVED_CONFIRM_KEY)
    assert box.label == REMOVED_CONFIRM_LABEL.format(n=count) and not box.value
    assert literal_markdown(AOI) in str(box.help)
    apply = app.button(key=APPLY_BUTTON_KEY)
    assert apply.disabled and apply.help == UNCONFIRMED_REMOVED_REASON


def test_an_editor_pack_that_drops_a_process_needs_the_removed_check(database: Path) -> None:
    """편집기에서 공정 줄을 지운 판 — 값 줄 「뺀 공정 1」 과 확인 칸이 서고, 채워야 「새 판 적용」
    이 열린다."""
    repository = new_repository(database)
    apply_template(repository)
    staged = _stage_from_editor(repository, _drop_aoi)

    app = _app(database, open_place=True, staged=staged)

    assert _value_line(app).startswith("더한 공정 0 · 뺀 공정 1 · ")
    _assert_removed_gate(app, 1)
    app.checkbox(key=REMOVED_CONFIRM_KEY).check().run()
    assert not app.button(key=APPLY_BUTTON_KEY).disabled
    app.button(key=APPLY_BUTTON_KEY).click().run()
    assert not app.exception, [item.message for item in app.exception]
    active = repository.load_extra_process_state().active
    assert active is not None and active.editor_made and active.process_count == 1


def test_an_imported_pack_that_drops_a_process_needs_the_check_and_a_new_pack_clears_it(
    database: Path,
) -> None:
    """가져온 판도 같다 — 채운 확인은 다음에 받은 판으로 이어지지 않는다(확인 칸은 key 만으로 같은
    위젯이라 받은 판을 새로 둘 때 비운다)."""
    apply_template(new_repository(database))
    app = _app(database, open_place=True, pack=_without_aoi(2))

    app.button(key=IMPORT_BUTTON_KEY).click().run()
    _assert_removed_gate(app, 1)
    app.checkbox(key=REMOVED_CONFIRM_KEY).check().run()
    assert not app.button(key=APPLY_BUTTON_KEY).disabled

    app.session_state[PACK_KEY] = _without_aoi(3)
    app.button(key=IMPORT_BUTTON_KEY).click().run()
    assert not app.exception, [item.message for item in app.exception]
    assert any("적용 전 판 3" in text for text in _captions(app))
    _assert_removed_gate(app, 1)


def test_while_off_an_imported_pack_counts_drops_against_the_last_pack(database: Path) -> None:
    """끈 동안 가져온 판은 마지막 내용 판과 견준다 — 적용하면 그 자리에서 다시 켜지므로 빠지는
    공정을 확인해야 하고, 값 줄 끝에 「적용하면 켜짐」 이 붙는다."""
    repository = new_repository(database)
    apply_template(repository)
    repository.turn_off_extra_process(expected_seq=1, applied_by=None)
    app = _app(database, open_place=True, pack=_without_aoi(2))

    app.button(key=IMPORT_BUTTON_KEY).click().run()

    line = _value_line(app)
    assert line.startswith("더한 공정 0 · 뺀 공정 1 · ") and line.endswith(TURNS_ON_PART)
    _assert_removed_gate(app, 1)


def test_a_revision_pack_that_drops_a_process_needs_the_same_check(database: Path) -> None:
    """리비전에서 만든 판도 같은 받은 판 상자의 확인 칸을 지난다(빼는 공정이 생기는 꼴을 합성으로
    둔다 — 「새 판으로」 는 보통 공정을 빼지 않는다)."""
    repository = new_repository(database)
    apply_template(repository)
    data = _without_aoi(2)
    reading = read_pack_zip(data)
    staged = StagedPack(
        fetch=SourceFetch(data=data, place=EXTRA_REVISION_PLACE),
        reading=reading,
        judgement=PackJudgement(JUDGE_APPLY, "새 판 2"),
        seen_seq=1,
        staged_at=NOW,
        changes=PackChanges(removed=(AOI,)),
        revision=RevisionOrigin("demo-scenario", "demo-revision", "DEMO 시나리오 r2"),
    )

    app = _app(database, open_place=True, staged=staged)

    _assert_removed_gate(app, 1)
