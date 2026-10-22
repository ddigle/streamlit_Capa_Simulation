# Purpose: 필요 단축 일정 탭의 진척 비교(기준선 저장·고르기·두 줄 카드·CSV·지우기)를 검사한다.

"""필요 단축 일정 진척 비교(AppTest).

`test_required_shortening_tab` 의 페이지 흉내(시나리오 쪽 갈아 끼우기)를 그대로 쓴다. 샘플 fleet
에서는 기준선을 저장하지 않으므로 샘플 설비 마스터를 **저장본으로** 넣고 시작한다.
"""

from __future__ import annotations

import codecs
import io
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest
import streamlit.elements.lib.policies as policies
from streamlit.testing.v1 import AppTest
from streamlit.testing.v1.element_tree import Button, TextInput
from test_required_shortening_tab import _csv, _database, _html, _run

from capa_simulation.components.equipment_data_workspace import BUFFER_GENERATION_KEY
from capa_simulation.components.required_shortening_panel import SHORTENING_LEVEL_KEY
from capa_simulation.components.shortening_progress_panel import (
    NO_COMPARISON,
    SHORTENING_COMPARE_KEY,
)
from capa_simulation.persistence.equipment_cache import clear_equipment_repository
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
from capa_simulation.services.equipment_contract import (
    empty_downtime_schedule,
    empty_equipment_baseline,
)
from capa_simulation.services.equipment_samples import sample_equipment_master
from capa_simulation.services.required_shortening import KIND_SHORTENED
from capa_simulation.services.shortening_baseline import (
    BASELINE_UNIT_COLUMNS,
    ShorteningBaselineDraft,
    normalize_baseline_units,
)
from capa_simulation.services.shortening_progress import (
    PROGRESS_EXPORT_COLUMNS,
    PROGRESS_IMPROVED,
    PROGRESS_NEW,
    PROGRESS_RESOLVED,
    PROGRESS_WORSENED,
)

PROGRESS_CSV_KEY = "equipment_shortening_progress_csv"


def _saved_database(tmp_path: Path) -> tuple[Path, pd.DataFrame]:
    """샘플 설비 마스터를 저장본(r1)으로 넣은 설비 DB."""
    database_path = _database(tmp_path)
    master = sample_equipment_master()
    DuckDBEquipmentRepository(database_path).save_snapshot(
        empty_equipment_baseline(), master, empty_downtime_schedule(), note="진척 비교 시험"
    )
    return database_path, master


def _save_button(app: AppTest) -> Button:
    return next(button for button in app.button if button.label == "기준선 저장")


def _name_input(app: AppTest) -> TextInput:
    return next(widget for widget in app.text_input if widget.label == "기준선 이름")


def _progress_cards(app: AppTest) -> list[str]:
    body = _html(app)
    return [
        chunk.split('"', 1)[0]
        for chunk in body.split('<section class="shk-card shk-prog" aria-label="진척 ')[1:]
    ]


def _toasts(app: AppTest) -> str:
    return " ".join(str(item.value) for item in app.toast)


def _progress_csv(app: AppTest) -> pd.DataFrame:
    data = app.session_state["captured_downloads"][PROGRESS_CSV_KEY]["data"]
    assert isinstance(data, bytes) and data.startswith(codecs.BOM_UTF8)
    return pd.read_csv(io.StringIO(data.decode("utf-8-sig")), dtype=str, keep_default_na=False)


def _shift_quals(database_path: Path, master: pd.DataFrame, moves: dict[str, int]) -> pd.DataFrame:
    """고른 호기의 Qual 을 며칠씩 옮겨 새 리비전으로 저장한다(설비 마스터 RawData 편집과 같다)."""
    changed = master.copy()
    for name, days in moves.items():
        rows = changed["설비명"].eq(name)
        assert rows.sum() == 1, name
        changed.loc[rows, "Qual일정"] = (
            pd.to_datetime(changed.loc[rows, "Qual일정"]) + timedelta(days=days)
        ).dt.date
    DuckDBEquipmentRepository(database_path).save_snapshot(
        empty_equipment_baseline(), changed, empty_downtime_schedule(), note="Qual 이동"
    )
    return changed


def test_without_a_baseline_the_tab_is_the_plain_view_with_a_save_entry(tmp_path: Path) -> None:
    """「비교 안 함」 이 기본이고 그때는 진척 비교를 하나도 그리지 않는다 — 기존 화면 그대로."""
    database_path, _ = _saved_database(tmp_path)

    app = _run(database_path)

    assert not app.exception, [element.message for element in app.exception]
    picker = app.selectbox(key=SHORTENING_COMPARE_KEY)
    assert picker.label == "진척 비교"
    assert picker.value == NO_COMPARISON and list(picker.options) == ["비교 안 함"]
    body = _html(app)
    assert "shk-prog" not in body and "진척 비교 요약" not in body
    assert "부족 공정" in body and "계획 · LOB 요약" in body
    assert PROGRESS_CSV_KEY not in {str(button.key) for button in app.get("download_button")}
    # 「기준선 저장」 팝오버의 폼은 그대로 서 있다(기본 이름은 오늘 날짜).
    assert _name_input(app).value == f"{date.today():%Y-%m-%d} 기준선"
    clear_equipment_repository()


def test_a_saved_baseline_is_listed_and_compares_two_lanes_per_unit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """기준선 저장 → 목록에 뜸 → Qual 을 당기고 늦춘 저장 → 고르면 두 줄 카드·요약·CSV."""
    database_path, master = _saved_database(tmp_path)
    warnings: list[object] = []
    monkeypatch.setattr(policies, "_shown_default_value_warning", False)
    monkeypatch.setattr(policies._LOGGER, "warning", lambda *args, **_kwargs: warnings.append(args))
    app = _run(database_path)
    _, units = _csv(app, "equipment_shortening_units_csv")
    singles = units.loc[units["구분"].eq(KIND_SHORTENED) & units["모듈 수"].eq("1")]
    assert len(singles) >= 2, "샘플 fleet 의 110% 에 당길 단일 호기가 둘 있어야 한다"
    faster, slower = str(singles["호기"].iloc[0]), str(singles["호기"].iloc[1])

    app = _name_input(app).set_value("  9월 정기  ").run()
    app = _save_button(app).click().run()

    assert not app.exception, [element.message for element in app.exception]
    assert "기준선을 저장했습니다 — 「9월 정기」" in _toasts(app)
    (stored,) = DuckDBEquipmentRepository(database_path).list_shortening_baselines()
    assert stored.name == "9월 정기" and stored.equipment_revision_no == 1
    assert stored.scenario_content_token == "shortening-test"
    picker = app.selectbox(key=SHORTENING_COMPARE_KEY)
    assert list(picker.options) == ["비교 안 함", f"9월 정기 · {stored.saved_at:%Y-%m-%d}"]
    # 저장한 뒤 이름 칸은 새 세대로 서서 오늘의 기본 이름으로 돌아온다.
    assert _name_input(app).value == f"{date.today():%Y-%m-%d} 기준선"
    assert picker.value == NO_COMPARISON

    _shift_quals(database_path, master, {faster: -5, slower: 7})
    app = app.selectbox(key=SHORTENING_COMPARE_KEY).set_value(stored.baseline_id).run()

    assert not app.exception, [element.message for element in app.exception]
    body = _html(app)
    assert "진척 비교 요약" in body and "단축 필요일수 합계" in body
    assert "계획 · LOB 요약" not in body
    cards = _progress_cards(app)
    assert cards, body[:400]
    assert body.count('class="shk-prog-tags"><span>과거</span><span class="now">현재</span>') >= 2
    frame = _progress_csv(app)
    assert list(frame.columns) == list(PROGRESS_EXPORT_COLUMNS)
    rows = frame.set_index("호기")
    # 확보 시점(기존 Qual)은 옮긴 날수만큼 움직인다 — 당기면 단축일수가 줄고 늦추면 는다.
    assert rows.at[faster, "확보 시점 이동(일)"] == "-5"
    assert rows.at[slower, "확보 시점 이동(일)"] == "7"
    assert rows.at[faster, "상태"] == PROGRESS_IMPROVED
    assert rows.at[slower, "상태"] == PROGRESS_WORSENED
    assert "일 줄임</span>" in body and "일 늘어남</span>" in body
    assert "확보 −5일" in body and "확보 +7일" in body

    # 목표를 바꾸면 그 목표의 기준선 결과와 견준다 — 다시 저장하지 않는다.
    high = app.selectbox(key=SHORTENING_LEVEL_KEY).set_value(1.3).run()
    assert not high.exception
    assert set(_progress_csv(high)["목표 확보율(%)"]) == {"130"}
    assert len(DuckDBEquipmentRepository(database_path).list_shortening_baselines()) == 1

    # 「비교 안 함」 으로 돌아가면 진척 비교가 사라지고 계획 화면이 선다.
    plain = high.selectbox(key=SHORTENING_COMPARE_KEY).set_value(NO_COMPARISON).run()
    assert not plain.exception
    assert "shk-prog" not in _html(plain) and "계획 · LOB 요약" in _html(plain)
    assert warnings == []
    clear_equipment_repository()


def test_a_duplicate_name_is_refused_and_a_baseline_is_deleted_only_when_confirmed(
    tmp_path: Path,
) -> None:
    database_path, _ = _saved_database(tmp_path)
    app = _run(database_path)
    app = _name_input(app).set_value("같은 이름").run()
    app = _save_button(app).click().run()
    app = _name_input(app).set_value("같은 이름").run()
    app = _save_button(app).click().run()

    assert not app.exception
    assert "같은 이름의 기준선이 이미 있습니다" in _toasts(app)
    (stored,) = DuckDBEquipmentRepository(database_path).list_shortening_baselines()

    app = app.selectbox(key=SHORTENING_COMPARE_KEY).set_value(stored.baseline_id).run()
    app = app.button(key="equipment_shortening_baseline_delete").click().run()
    assert "「정말 지웁니다」를 체크한 뒤" in _toasts(app)
    assert DuckDBEquipmentRepository(database_path).list_shortening_baselines() == (stored,)

    confirm = next(box for box in app.checkbox if box.label == "정말 지웁니다")
    app = confirm.check().run()
    app = app.button(key="equipment_shortening_baseline_delete").click().run()

    assert not app.exception
    assert "기준선을 지웠습니다 — 「같은 이름」" in _toasts(app)
    assert DuckDBEquipmentRepository(database_path).list_shortening_baselines() == ()
    picker = app.selectbox(key=SHORTENING_COMPARE_KEY)
    assert picker.value == NO_COMPARISON and list(picker.options) == ["비교 안 함"]
    assert "shk-prog" not in _html(app)
    clear_equipment_repository()


def test_a_unit_renamed_after_the_baseline_is_flagged_as_a_possible_rename(
    tmp_path: Path,
) -> None:
    """기준선을 저장한 뒤 당긴 호기 하나의 설비명을 바꿨다. 짝짓기는 이름으로만 하므로 옛 이름 줄은
    「해소」, 새 이름 줄은 「신규 필요」로 갈린다 — 진척 비교가 그 가능성을 한 줄로 알려야 한다
    (근본 처리인 이름 이력 매핑은 사용자 결정)."""
    database_path, master = _saved_database(tmp_path)
    app = _run(database_path)
    _, units = _csv(app, "equipment_shortening_units_csv")
    singles = units.loc[units["구분"].eq(KIND_SHORTENED) & units["모듈 수"].eq("1")]
    old_name = str(singles["호기"].iloc[0])
    process = str(singles["공정"].iloc[0])
    app = _save_button(app).click().run()
    (stored,) = DuckDBEquipmentRepository(database_path).list_shortening_baselines()

    renamed = master.copy()
    renamed.loc[renamed["설비명"].eq(old_name), "설비명"] = f"{old_name}-NEW"
    DuckDBEquipmentRepository(database_path).save_snapshot(
        empty_equipment_baseline(), renamed, empty_downtime_schedule(), note="이름 바꿈"
    )
    app = app.selectbox(key=SHORTENING_COMPARE_KEY).set_value(stored.baseline_id).run()

    assert not app.exception, [element.message for element in app.exception]
    rows = _progress_csv(app).set_index("호기")
    assert rows.at[old_name, "상태"] == PROGRESS_RESOLVED
    assert rows.at[f"{old_name}-NEW", "상태"] == PROGRESS_NEW
    captions = [str(item.value) for item in app.caption]
    flagged = [text for text in captions if "이름을 바꿨다면" in text]
    assert flagged and process in flagged[0], captions
    clear_equipment_repository()


def test_the_sample_fleet_cannot_be_saved_as_a_baseline(tmp_path: Path) -> None:
    """샘플 fleet 은 합성값이라 공용 기록으로 남기지 않는다 — 팝오버에 까닭만 적는다."""
    app = _run(_database(tmp_path))

    assert not app.exception
    assert not any(widget.label == "기준선 이름" for widget in app.text_input)
    infos = " ".join(str(item.value) for item in app.info)
    assert "샘플 데이터를 보는 중이라 기준선을 저장하지 않습니다" in infos
    clear_equipment_repository()


def test_an_unsaved_equipment_edit_does_not_block_saving_a_baseline(tmp_path: Path) -> None:
    """RawData 제출·Space 배치 대기는 편집본(buffer)에만 쌓이고 계산은 저장본 사본만 읽는다 — 화면의
    계획이 그대로이니 기준선 저장도 막지 않는다(막으면 원치 않는 공용 리비전을 강요한다)."""
    database_path, _ = _saved_database(tmp_path)
    app = _run(database_path)
    assert not app.exception
    before = app.session_state["captured_downloads"]["equipment_shortening_units_csv"]["data"]

    # RawData 제출·Space 캔버스 대기가 하는 일 — 편집본 세대만 올린다.
    app.session_state[BUFFER_GENERATION_KEY] = int(app.session_state[BUFFER_GENERATION_KEY]) + 1
    app = app.run()

    assert not app.exception
    after = app.session_state["captured_downloads"]["equipment_shortening_units_csv"]["data"]
    assert after == before
    assert any(widget.label == "기준선 이름" for widget in app.text_input)
    assert not any("설비 편집" in str(item.value) for item in app.info)
    clear_equipment_repository()


def test_a_past_baseline_target_without_a_finished_qual_is_flagged_as_delayed(
    tmp_path: Path,
) -> None:
    """이행 지연 — 기준선의 목표 Qual 이 지났는데 설비 마스터 Qual 이 끝나지 않은 당긴 호기. 진척
    보드 아래 목록, 보드의 「이행 지연」 칸, 그 진척 카드 머리·호기 줄의 「지연」 표지가 선다.
    담당자는 줄 옆 글과 풍선이다."""
    database_path, master = _saved_database(tmp_path)
    app = _run(database_path)
    _, units = _csv(app, "equipment_shortening_units_csv")
    singles = units.loc[units["구분"].eq(KIND_SHORTENED) & units["모듈 수"].eq("1")]
    unit, process = str(singles["호기"].iloc[0]), str(singles["공정"].iloc[0])
    qual = pd.Timestamp(master.loc[master["설비명"].eq(unit), "Qual일정"].iloc[0]).date()
    today = date.today()
    target = today - timedelta(days=5)
    row = dict.fromkeys(BASELINE_UNIT_COLUMNS)
    row.update(
        {
            "목표 확보율(%)": 110,
            "공정": process,
            "호기": unit,
            "구분": KIND_SHORTENED,
            "설비명": unit,
            "모듈 수": 1,
            "환산비": 1.0,
            "기존 Qual": qual,
            "목표 Qual": target,
            "단축일수": max((qual - target).days, 1),
            "늘어난 환산대수": 0.5,
            "대상 월": target.year * 100 + target.month,
            "해소 기여 월": "",
        }
    )
    stored = DuckDBEquipmentRepository(database_path).save_shortening_baseline(
        ShorteningBaselineDraft(
            name="지난 기준선",
            plan_today=today - timedelta(days=30),
            start_month=target.year * 100 + target.month,
            end_month=target.year * 100 + target.month,
            processes=(process,),
            cutoff_days={process: 10},
            units=normalize_baseline_units(pd.DataFrame([row])),
        )
    )
    clear_equipment_repository()

    app = _run(database_path)
    app = app.selectbox(key=SHORTENING_COMPARE_KEY).set_value(stored.baseline_id).run()

    assert not app.exception, [element.message for element in app.exception]
    labels = [str(box.label) for box in app.status]
    assert "이행 지연 1대 — 기준선 목표 Qual 이 지났는데 Qual 미완료" in labels, labels
    body = _html(app)
    assert ">지연 1대</span>" in body and ">지연</span>" in body
    assert "담당 샘플 담당자" in body
    board = next(
        frame.value
        for frame in app.dataframe
        if "equipment_shortening_board_" in str(frame.proto.id)
    )
    assert "기준선 대비" in board.columns and "이행 지연" in board.columns
    assert int(board["이행 지연"].sum()) == 1
    clear_equipment_repository()
