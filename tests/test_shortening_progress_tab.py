# Purpose: 필요 단축 일정 탭의 진척 비교(기준선 저장·고르기·두 줄 카드·CSV·지우기)를 검사한다.

"""필요 단축 일정 진척 비교(AppTest).

`test_required_shortening_tab` 의 페이지 흉내(시나리오 쪽 갈아 끼우기)를 그대로 쓴다. 샘플 fleet
에서는 기준선을 저장하지 않으므로 샘플 설비 마스터를 **저장본으로** 넣고 시작한다.
"""

from __future__ import annotations

import codecs
import io
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
import streamlit.elements.lib.policies as policies
from alert_marks import flashed
from streamlit.testing.v1 import AppTest
from streamlit.testing.v1.element_tree import Button, TextInput
from test_required_shortening_tab import _choose_level, _csv, _database, _html, _run, _run_static

from capa_simulation.components.equipment_data_workspace import BUFFER_GENERATION_KEY
from capa_simulation.components.literal_markdown import literal_markdown
from capa_simulation.components.shortening_cumulative import SCREEN_TOTAL_KEY, ScreenTotal
from capa_simulation.components.shortening_progress_panel import (
    BASELINE_SAVE_HELP,
    NO_COMPARISON,
    SHORTENING_COMPARE_KEY,
    _unit_markup,
    _units_markup,
)
from capa_simulation.components.shortening_source import SHORTENING_BASIS_KEY
from capa_simulation.components.shortening_timeline import unit_name
from capa_simulation.design import tokens
from capa_simulation.equipment_scenario_activation import SELECTION_KEY
from capa_simulation.persistence.equipment_cache import (
    clear_equipment_repository,
    clear_shortening_baseline_cache,
)
from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
from capa_simulation.services.equipment_contract import (
    empty_downtime_schedule,
    empty_equipment_baseline,
)
from capa_simulation.services.equipment_samples import sample_equipment_master
from capa_simulation.services.required_shortening import KIND_NEW, KIND_SHORTENED
from capa_simulation.services.shortening_baseline import (
    BASELINE_UNIT_COLUMNS,
    ShorteningBaselineDraft,
    normalize_baseline_units,
)
from capa_simulation.services.shortening_progress import (
    PROGRESS_EXPORT_COLUMNS,
    PROGRESS_IMPROVED,
    PROGRESS_NEW,
    PROGRESS_REBASED,
    PROGRESS_RESOLVED,
    PROGRESS_UNCHANGED,
    PROGRESS_WORSENED,
    compare_progress,
)

PROGRESS_CSV_KEY = "equipment_shortening_progress_csv"
GUIDE = Path(__file__).resolve().parents[1] / "src/capa_simulation/guides/required_shortening.md"
# 진척 비교 화면에서 걷어 Guide 「진척 비교」 로 옮긴 글 — 호기 줄 위 범례 글과 합계 칸 설명 줄
# (2026-11-20 사용자 요청을 같은 꼴 전체로).
PROGRESS_LEFT_FOR_GUIDE = (
    "호기마다 두 줄",
    "칸은 달",
    "점선은 오늘",
    "오른쪽은 기존",
    "당긴 호기의 합",
    "지금 맞댄 공정",
    "목표 110% ·",
)


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


def _notices(app: AppTest) -> str:
    """기준선 저장 · 지우기 결과 알림(알림창 표지 — 버튼 곁 원문 마크다운)을 한 글로."""
    return " ".join(item.value for item in flashed(app))


def _in_order(app: AppTest) -> list[Any]:
    """본문 요소를 화면 차례대로(블록은 그 안을 깊이 우선으로)."""
    found: list[Any] = []

    def walk(node: Any) -> None:
        for child in getattr(node, "children", {}).values():
            if hasattr(child, "children") and not hasattr(child, "value"):
                walk(child)
            else:
                found.append(child)

    walk(app.main)
    return found


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


def _follow_official(app: AppTest, database_path: Path) -> None:
    """세션을 지금 공식 발행으로 옮긴다(사이드바 「설비 시나리오」 에서 최신을 불러온 것과 같다).

    세션은 고른 일정 리비전을 고정해 든다(E5) — 앱 밖의 저장(다른 사용자)은 그 세션 화면을 바꾸지
    않으므로 시험이 「불러오기」 를 대신한다.
    """
    release = DuckDBEquipmentRepository(database_path).latest_equipment_release()
    assert release is not None
    app.session_state[SELECTION_KEY] = {
        "scenario_id": release.equipment_scenario_id,
        "schedule_revision_id": release.schedule_revision_id,
    }


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
    assert "기준선을 저장했습니다 — 「9월 정기」" in _notices(app)
    (stored,) = DuckDBEquipmentRepository(database_path).list_shortening_baselines()
    assert stored.name == "9월 정기" and stored.equipment_revision_no == 1
    assert stored.scenario_content_token == "shortening-test"
    picker = app.selectbox(key=SHORTENING_COMPARE_KEY)
    assert list(picker.options) == ["비교 안 함", f"{stored.saved_at:%Y-%m-%d} · 9월 정기"]
    # 저장한 뒤 이름 칸은 새 세대로 서서 오늘의 기본 이름으로 돌아온다.
    assert _name_input(app).value == f"{date.today():%Y-%m-%d} 기준선"
    assert picker.value == NO_COMPARISON

    _shift_quals(database_path, master, {faster: -5, slower: 7})
    _follow_official(app, database_path)
    app = app.selectbox(key=SHORTENING_COMPARE_KEY).set_value(stored.baseline_id).run()

    assert not app.exception, [element.message for element in app.exception]
    body = _html(app)
    assert "진척 비교 요약" in body and "단축 필요일수 합계 (목표 110%)" in body
    assert "계획 · LOB 요약" not in body
    cards = _progress_cards(app)
    assert cards, body[:400]
    assert body.count('class="shk-prog-tags"><span>과거</span><span class="now">현재</span>') >= 2
    # 호기 이름 칸은 공정 카드와 같은 꼴 — 넘치면 앞을 줄이고 끝을 남긴다(남은 물음 보드 D6 (다)).
    assert f'<div class="shk-prog-label">{unit_name(faster)}' in body
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

    # 목표를 바꾸면 그 목표의 기준선 결과와 견준다 — 다시 저장하지 않는다. 합계 칸 라벨의 목표
    # % 도 따라 바뀐다(2026-11-20 사용자 답 「나」 — 두 줄 카드에 표가 없어 이 라벨이 본문의 목표
    # 자리).
    high = _choose_level(app, 1.3)
    assert not high.exception
    assert set(_progress_csv(high)["목표 확보율(%)"]) == {"130"}
    high_body = _html(high)
    assert "단축 필요일수 합계 (목표 130%)" in high_body
    assert "단축 필요일수 합계 (목표 110%)" not in high_body
    assert len(DuckDBEquipmentRepository(database_path).list_shortening_baselines()) == 1

    # 「비교 안 함」 으로 돌아가면 진척 비교가 사라지고 계획 화면이 선다.
    plain = high.selectbox(key=SHORTENING_COMPARE_KEY).set_value(NO_COMPARISON).run()
    assert not plain.exception
    assert "shk-prog" not in _html(plain) and "계획 · LOB 요약" in _html(plain)
    assert warnings == []
    clear_equipment_repository()


def test_a_typed_target_outside_the_five_is_not_compared_with_a_baseline(tmp_path: Path) -> None:
    """기준선은 다섯 목표만 얼린다 — 직접 넣은 다섯 밖 목표(115%)로 저장해도 얼린 표는 다섯이고,
    그 목표로 진척 비교를 고르면 견주지 않고 빈 결과 한 줄(까닭은 풍선)이다. 빈 기준선과 견주면 지금
    호기가 모두 「신규 필요」 로 읽힌다(2026-11-11 사용자 고칠 것 Q2-26 — 답 밖, 지금 꼴과 가까운
    쪽). 다섯 가운데 하나로 돌아가면 다시 견준다."""
    from test_required_shortening_tab import _type_level

    from capa_simulation.components.required_shortening_panel import (
        MISSING_BASELINE_LEVEL_HELP,
    )

    database_path, _ = _saved_database(tmp_path)
    app = _run(database_path)
    typed = _type_level(app, 115.0)
    assert not typed.exception
    app = _name_input(typed).set_value("115 저장").run()
    app = _save_button(app).click().run()
    assert not app.exception, [element.message for element in app.exception]
    (stored,) = DuckDBEquipmentRepository(database_path).list_shortening_baselines()
    frozen = DuckDBEquipmentRepository(database_path).load_shortening_baseline(stored.baseline_id)
    assert set(frozen.units["목표 확보율(%)"].astype(int)) <= {90, 100, 110, 120, 130}

    _follow_official(app, database_path)
    app = app.selectbox(key=SHORTENING_COMPARE_KEY).set_value(stored.baseline_id).run()
    assert not app.exception, [element.message for element in app.exception]
    body = _html(app)
    assert "진척 비교 요약" not in body and "shk-prog" not in body
    assert "계획 · LOB 요약" not in body
    (line,) = [item for item in app.caption if "결과가 없습니다" in str(item.value)]
    assert str(line.value) == "기준선에 목표 115% 결과가 없습니다."
    assert str(line.proto.help) == MISSING_BASELINE_LEVEL_HELP
    assert PROGRESS_CSV_KEY not in {str(button.key) for button in app.get("download_button")}

    back = _choose_level(app, 1.1)
    assert not back.exception
    assert "진척 비교 요약" in _html(back)
    assert not [item for item in back.caption if "결과가 없습니다" in str(item.value)]
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
    assert "같은 이름의 기준선이 이미 있습니다" in _notices(app)
    # 이름이 까닭인 거절은 고칠 입력(「기준선 이름」)이 든 팝오버 폼 위에도 선다(설계 규칙 UI-NTF-03
    # — 그 자리에서 고칠 입력이 있는 거부는 곁). 머리 밑 자리에 경고 상자를 세우지 않는다.
    assert not any("같은 이름" in str(item.value) for item in app.warning)
    (refusal,) = [item for item in app.error if "같은 이름의 기준선이 이미 있습니다" in item.value]
    drawn = [
        str(getattr(item, "label", "") or getattr(item, "value", "")) for item in _in_order(app)
    ]
    assert drawn.index(refusal.value) < drawn.index("기준선 이름")
    (stored,) = DuckDBEquipmentRepository(database_path).list_shortening_baselines()

    app = app.selectbox(key=SHORTENING_COMPARE_KEY).set_value(stored.baseline_id).run()
    app = app.button(key="equipment_shortening_baseline_delete").click().run()
    assert "「정말 지웁니다」를 체크한 뒤" in _notices(app)
    assert DuckDBEquipmentRepository(database_path).list_shortening_baselines() == (stored,)

    confirm = next(box for box in app.checkbox if box.label == "정말 지웁니다")
    app = confirm.check().run()
    app = app.button(key="equipment_shortening_baseline_delete").click().run()

    assert not app.exception
    assert "기준선을 지웠습니다 — 「같은 이름」" in _notices(app)
    assert DuckDBEquipmentRepository(database_path).list_shortening_baselines() == ()
    picker = app.selectbox(key=SHORTENING_COMPARE_KEY)
    assert picker.value == NO_COMPARISON and list(picker.options) == ["비교 안 함"]
    assert "shk-prog" not in _html(app)
    clear_equipment_repository()


def test_an_empty_name_is_refused_beside_the_name_field_and_in_the_alert_popup(
    tmp_path: Path,
) -> None:
    """빈 이름도 이름 칸이 까닭인 거절이다 — 팝오버 폼 위 오류 + 알림창(`FL-04`)이고, 고칠 입력이
    없는 거절(머리 밑 칸 · 경고 상자)로 가지 않는다."""
    database_path, _ = _saved_database(tmp_path)
    app = _run(database_path)
    app = _name_input(app).set_value("   ").run()
    app = _save_button(app).click().run()

    assert not app.exception
    assert any("기준선 이름을 적어 주세요" in item.value for item in app.error)
    assert [item.code for item in flashed(app) if "기준선 이름을 적어" in item.value] == ["FL-04"]
    assert not app.warning
    assert DuckDBEquipmentRepository(database_path).list_shortening_baselines() == ()
    clear_equipment_repository()


def test_the_save_popover_has_no_head_note_and_the_button_says_what_it_freezes(
    tmp_path: Path,
) -> None:
    """「기준선 저장」 팝오버 머리에 설명 글을 두지 않는다 — 무엇을 얼려 남기고 고칠 수 없다는 말은
    저장 단추 풍선이다(누르기 전에 보인다)."""
    database_path, _ = _saved_database(tmp_path)
    app = _run(database_path)

    assert not app.exception, [element.message for element in app.exception]
    assert _save_button(app).help == BASELINE_SAVE_HELP
    assert "고칠 수 없습니다" in BASELINE_SAVE_HELP
    assert not any("그대로 얼려" in str(item.value) for item in app.caption)
    clear_equipment_repository()


def _bare_tildes(text: str) -> int:
    """마크다운이 지움선으로 읽을 물결표(앞에 `\\` 가 없는 것)의 수."""
    return len(re.findall(r"(?<!\\)~", text))


def test_a_baseline_name_with_tildes_reads_as_written_in_the_notices_and_the_delete_caption(
    tmp_path: Path,
) -> None:
    """기준선 이름은 사람이 적은 글이다 — 저장 알림·같은 이름 거절·「기준선 지우기」 확인 글·지움
    알림은 마크다운(결과 알림 원문·캡션)이라 「10/01~10/07 기준~A」 의 물결표 짝이 지움선이 되지
    않게 막는다(E2E 2026-10-26). 진척 비교 선택 상자 라벨은 글자 그대로라 손대지 않는다."""
    database_path, _ = _saved_database(tmp_path)
    name = "10/01~10/07 기준~A"
    app = _run(database_path)
    app = _name_input(app).set_value(name).run()
    app = _save_button(app).click().run()
    saved = _notices(app)
    assert not app.exception
    assert "기준선을 저장했습니다" in saved and literal_markdown(name) in saved
    assert _bare_tildes(saved) == 0

    app = _name_input(app).set_value(name).run()
    app = _save_button(app).click().run()
    refused = _notices(app)
    assert "같은 이름의 기준선이 이미 있습니다" in refused and _bare_tildes(refused) == 0

    (stored,) = DuckDBEquipmentRepository(database_path).list_shortening_baselines()
    assert stored.name == name
    app = app.selectbox(key=SHORTENING_COMPARE_KEY).set_value(stored.baseline_id).run()
    (caption,) = [item.value for item in app.caption if "기준선을 지웁니다" in item.value]
    assert literal_markdown(name) in caption and _bare_tildes(caption) == 0

    confirm = next(box for box in app.checkbox if box.label == "정말 지웁니다")
    app = confirm.check().run()
    app = app.button(key="equipment_shortening_baseline_delete").click().run()
    deleted = _notices(app)
    assert not app.exception
    assert "기준선을 지웠습니다" in deleted and literal_markdown(name) in deleted
    assert _bare_tildes(deleted) == 0
    clear_equipment_repository()


@pytest.mark.parametrize(
    "name",
    ["R6B *중요* 안", "R6B **굵게** 안", "R6B [안내](http://e.com) 끝", "R6B `코드` $x$ 안"],
)
def test_the_same_name_refusal_shows_the_name_as_written(tmp_path: Path, name: str) -> None:
    """같은 이름 거절 알림은 적은 이름을 글자 그대로 싣는다 — 예외 글을
    `bootstrap_error_message`(물결표만 막는다)로만 넘기면 별표가 기울임·굵게, `[안내](…)` 가 누를
    수 있는 링크가 됐다(2026-10-27 E2E). 저장소 예외는 이름을 속성으로도 싣고 화면이
    `literal_markdown` 으로 다시 짓는다."""
    database_path, _ = _saved_database(tmp_path)
    app = _run(database_path)
    app = _name_input(app).set_value(name).run()
    app = _save_button(app).click().run()
    assert literal_markdown(name) in _notices(app)

    app = _name_input(app).set_value(name).run()
    app = _save_button(app).click().run()
    refused = _notices(app)
    assert not app.exception
    taken = f"같은 이름의 기준선이 이미 있습니다: {literal_markdown(name)}"
    assert f"기준선을 저장하지 않았습니다 — {taken}" in refused
    assert name not in refused
    assert len(DuckDBEquipmentRepository(database_path).list_shortening_baselines()) == 1
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
    _follow_official(app, database_path)
    app = app.selectbox(key=SHORTENING_COMPARE_KEY).set_value(stored.baseline_id).run()

    assert not app.exception, [element.message for element in app.exception]
    rows = _progress_csv(app).set_index("호기")
    assert rows.at[old_name, "상태"] == PROGRESS_RESOLVED
    assert rows.at[f"{old_name}-NEW", "상태"] == PROGRESS_NEW
    # 자리에는 표지(이름 바꿈 의심 공정 수)만, 이름 · 까닭은 그 줄의 풍선이다(설계 규칙 UI-TXT-01).
    (flagged,) = [item for item in app.caption if "이름 바꿈 의심 공정 1개" in str(item.value)]
    assert "이름을 바꿨다면" in flagged.proto.help and process in flagged.proto.help
    assert not any("이름을 바꿨다면" in str(item.value) for item in app.caption)
    clear_equipment_repository()


def test_a_static_leftover_unit_reads_as_leftover_not_new_in_both_lanes() -> None:
    """Static 기준의 남는 호기(확보 시점 없이 당긴 「단축」 줄 — 보드 답 Q11 (가))는 진척 카드 두
    줄 모두 본문 호기 줄처럼 「필요 MM.DD 남는 호기」 다. 「신규」 는 추가N 에만 쓴다(설계 규칙
    UI-CON-02 — E2E 검수 D1: 남는 호기가 「필요 27.04.25 신규」 로 적혀 추가N 과 같은 글이었다).
    기준선에서 남는 호기였다가 지금 현재 일정을 받은 호기는 과거 줄만 「남는 호기」 다."""
    process = "PMC"
    columns = ["공정", "호기", "구분", "기존 Qual", "목표 Qual", "단축일수", "모듈 수"]

    def unit(name: str, kind: str, need: date, secure: date | None) -> dict[str, object]:
        days = None if secure is None else (secure - need).days
        return {
            "공정": process,
            "호기": name,
            "구분": kind,
            "기존 Qual": secure,
            "목표 Qual": need,
            "단축일수": days,
            "모듈 수": 1,
        }

    def frame(rows: list[dict[str, object]]) -> pd.DataFrame:
        table = pd.DataFrame(rows, columns=columns)
        for column in ("단축일수", "모듈 수"):
            table[column] = pd.to_numeric(table[column]).astype("Int64")
        return table

    need = date(2027, 4, 25)
    past = frame(
        [
            unit("DEMO-PMC-014", KIND_SHORTENED, need, None),
            unit("DEMO-PMC-016", KIND_SHORTENED, need, None),
            unit("추가1", KIND_NEW, need, None),
        ]
    )
    current = frame(
        [
            unit("DEMO-PMC-014", KIND_SHORTENED, need, None),
            unit("DEMO-PMC-016", KIND_SHORTENED, need, date(2027, 5, 5)),
            unit("추가1", KIND_NEW, need, None),
        ]
    )
    today = date(2026, 11, 20)
    rows = compare_progress(past, current, current_processes=[process], today=today)
    axis = (date(2027, 1, 1), date(2027, 7, 1))
    markup = {
        str(row["호기"]): _unit_markup(row, axis, "", today)
        for row in (
            {str(key): value for key, value in record.items()} for record in rows.to_dict("records")
        )
    }

    def results(name: str) -> tuple[str, str]:
        found = re.search(
            r'<span class="past">(.*?)</span><span class="now">(.*?)</span>', markup[name]
        )
        assert found is not None, name
        return found.group(1), found.group(2)

    def title(name: str) -> str:
        found = re.search(r'title="([^"]*)"', markup[name])
        assert found is not None, name
        return found.group(1)

    spare_line = "필요 27.04.25 <b>남는 호기</b>"
    assert results("DEMO-PMC-014") == (spare_line, spare_line)
    assert "신규" not in markup["DEMO-PMC-014"]
    assert "과거 남는 호기 — 현재 일정 없음 · 필요 Qual 2027-04-25" in title("DEMO-PMC-014")
    assert "현재 남는 호기 — 현재 일정 없음 · 필요 Qual 2027-04-25" in title("DEMO-PMC-014")

    assert results("DEMO-PMC-016") == (spare_line, "27.05.05 → 27.04.25 <b>−10일</b>")
    assert "신규" not in markup["DEMO-PMC-016"]
    # 결과 보드 여쭘-4 a — 남는 호기였다가 날짜를 받은 것은 진척이 아니라 범위 바뀜이다. 빈칸을
    # 0일로 세어 「10일 늘어남」 으로 적지 않고 「기준 바뀜」 배지, 현재 줄은 좋고 나쁨을 말하지
    # 않는 글자색.
    assert ">기준 바뀜</span>" in markup["DEMO-PMC-016"]
    assert "늘어남" not in markup["DEMO-PMC-016"]
    now_lane = markup["DEMO-PMC-016"].split('<div class="shk-prog-lane">')[2]
    assert f"background:{tokens.TEXT};" in now_lane
    assert tokens.DELTA_INCREASE not in now_lane and tokens.ACCENT not in now_lane
    assert ">변동 없음</span>" in markup["DEMO-PMC-014"]

    assert results("추가1") == ("필요 27.04.25 <b>신규</b>",) * 2
    assert "과거 신규 필요 Qual 2027-04-25" in title("추가1")
    assert "남는 호기" not in markup["추가1"]


def test_the_sample_fleet_cannot_be_saved_as_a_baseline(tmp_path: Path) -> None:
    """샘플 fleet 은 합성값이라 공용 기록으로 남기지 않는다 — 팝오버에는 표지 한 마디와 꺼진 단추만
    두고 까닭은 그 단추 풍선이다(검수표 11/02 equip-44 와 같은 꼴)."""
    app = _run(_database(tmp_path))

    assert not app.exception
    assert not any(widget.label == "기준선 이름" for widget in app.text_input)
    assert not any("기준선을 저장하지 않습니다" in str(item.value) for item in app.info)
    blocked = next(
        button for button in app.button if button.label == "기준선 저장" and button.disabled
    )
    assert "샘플 데이터를 보는 중이라 기준선을 저장하지 않습니다" in str(blocked.help)
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


def test_a_baseline_keeps_its_basis_and_is_compared_on_that_basis(tmp_path: Path) -> None:
    """보드 답 Q14 (가) — 기준선은 그때 현재 일정 기준(처음 Static)을 남기고, 전환을 설비 마스터로
    바꿔도 진척 비교는 그 기준선과 같은 기준(Static)의 계획과 견준다. 요약 기준선 칸에 기준 한 마디,
    기준 값 글도 보이는 계획의 기준이다."""
    database_path, _ = _saved_database(tmp_path)
    app = _run_static(database_path)
    assert app.session_state[SHORTENING_BASIS_KEY] == "Static"
    app = _name_input(app).set_value("Static 기준선").run()
    app = _save_button(app).click().run()
    assert not app.exception, [element.message for element in app.exception]
    (stored,) = DuckDBEquipmentRepository(database_path).list_shortening_baselines()
    assert stored.schedule_basis == "Static"

    app = app.sidebar.button_group(key=SHORTENING_BASIS_KEY).set_value("설비 마스터").run()
    app = app.selectbox(key=SHORTENING_COMPARE_KEY).set_value(stored.baseline_id).run()
    assert not app.exception, [element.message for element in app.exception]
    body = _html(app)
    assert "현재 일정 기준 Static — 이 기준으로 견줌(전환은 설비 마스터)" in body
    captions = [str(item.value) for item in app.caption]
    assert any("Static 역산 가용(환산) · 오늘" in caption for caption in captions)
    # 같은 기준이면 견줄 것이 없다 — 합계 변화 칸이 「변동 없음」 이고 악화 · 신규 · 해소가 0 이다.
    # 「변동 없음 n」 세는 칸은 늘 서므로 그 글만으로는 아무것도 막지 못한다 — 다른 기준(설비
    # 마스터)의 계획과 견주면 이 표본에서 합계 변화 칸이 바뀌어 아래 단언이 깨진다.
    assert re.search(r'class="shk-prog-change"[^>]*>변동 없음</span>', body)
    for label in ("개선", "악화", "신규", "해소"):
        assert f"<b>{label} 0</b>" in body, label


@pytest.mark.parametrize(("static", "dated_first"), [(3.0, False), (7.0, True)])
def test_a_unit_whose_static_spare_side_changed_since_the_baseline_reads_as_a_basis_change(
    tmp_path: Path, static: float, dated_first: bool
) -> None:
    """결과 보드 여쭘-4 a — 기준선과 지금 사이에 한 시점만 Static 기준의 남는 호기(현재 일정 없음)인
    호기는 진척이 아니라 범위 바뀜이다. 카드 배지 「기준 바뀜」, 요약 호기 변동 「기준 바뀜 1」 과
    합계 칸 「기준 바뀜 1대(현재 n일) 빼고 견줌」 이고, 합계 · 증감 · 개선/악화는 그 호기를 빼고
    견준다(나머지는 같은 계획이라 「변동 없음」). 「이번 주 값 넣기」 의 화면 합계는 진척 비교와
    상관없이 그대로다.

    기준선은 앱이 얼린 Static 기준선에서 목표 110% 의 당긴 호기 한 줄만 반대 꼴로 바꿔 새로 저장한
    것이다 — 지금 날짜를 받은 호기면 현재 일정 · 단축일수를 비워 남는 호기로(남는 → 날짜), 지금 남는
    호기면 9일 늦은 현재 일정을 줘(날짜 → 남는). Static 가용 3.0 은 남는 호기가, 7.0 은 날짜를 받은
    호기가 서는 표본이라 그 꼴의 줄만 고른다 — 7.0 은 남는 → 날짜(지금 n일 > 0)라 요약 지금 합계가
    그 몫을 뺐는지까지 본다. 표본은 오늘 기준 상대 날짜라 그 꼴이 서지 않는 날에는 다른 꼴로
    넘어가지 않고 그 방향을 분명히 건너뛴다 — 넘어가면 그 단언이 「화면 합계 − 0」 으로
    약해진다(방향마다 고정한 시험은 `test_shortening_progress`)."""
    database_path, _ = _saved_database(tmp_path)
    app = _run_static(database_path, static=static)
    assert not app.exception, [element.message for element in app.exception]
    plain_total = app.session_state[SCREEN_TOTAL_KEY]
    assert isinstance(plain_total, ScreenTotal) and plain_total.basis == "Static"
    app = _name_input(app).set_value("Static 기준선").run()
    app = _save_button(app).click().run()
    assert not app.exception, [element.message for element in app.exception]
    repository = DuckDBEquipmentRepository(database_path)
    (frozen,) = repository.list_shortening_baselines()
    baseline = repository.load_shortening_baseline(frozen.baseline_id)
    units = baseline.units.copy()
    pulled = units.loc[units["목표 확보율(%)"].eq(110) & units["구분"].eq(KIND_SHORTENED)]
    wanted = pulled.loc[pulled["기존 Qual"].notna() == dated_first]
    if wanted.empty:
        clear_equipment_repository()
        shape = "날짜를 받은" if dated_first else "남는"
        pytest.skip(f"오늘 표본(Static 가용 {static})에는 110% 의 {shape} 당긴 호기가 없다")
    index = wanted.index[0]
    unit = str(units.at[index, "호기"])
    target = units.at[index, "목표 Qual"]
    assert isinstance(target, date)
    if dated_first:
        now_days = int(str(units.at[index, "단축일수"]))
        assert now_days > 0, "남는 → 날짜 방향은 요약 지금 합계가 그 몫을 뺐는지까지 본다"
        units.at[index, "기존 Qual"] = None
        units.at[index, "단축일수"] = pd.NA
    else:
        now_days = 0
        units.at[index, "기존 Qual"] = target + timedelta(days=9)
        units.at[index, "단축일수"] = 9
    stored = repository.save_shortening_baseline(
        ShorteningBaselineDraft(
            name="남는 호기 기준선",
            plan_today=frozen.plan_today,
            start_month=frozen.start_month,
            end_month=frozen.end_month,
            processes=baseline.processes,
            cutoff_days=baseline.cutoff_days,
            units=normalize_baseline_units(units),
            schedule_basis="Static",
        )
    )
    clear_shortening_baseline_cache()

    app = _run_static(database_path, static=static)
    assert app.session_state[SCREEN_TOTAL_KEY] == plain_total
    app = app.selectbox(key=SHORTENING_COMPARE_KEY).set_value(stored.baseline_id).run()
    assert not app.exception, [element.message for element in app.exception]

    rows = _progress_csv(app).set_index("호기")
    assert rows.at[unit, "상태"] == PROGRESS_REBASED
    assert rows.at[unit, "단축일수 증감"] == ""
    others = rows.drop(index=unit)
    assert set(others.loc[others["구분"].eq(KIND_SHORTENED), "상태"]) == {PROGRESS_UNCHANGED}
    body = _html(app)
    assert ">기준 바뀜</span>" in body
    assert re.search(r">기준 바뀜 1</b>", body)
    assert f"기준 바뀜 1대(현재 {now_days:,}일) 빼고 견줌" in body
    assert re.search(r'class="shk-prog-change"[^>]*>변동 없음</span>', body)
    for label in ("개선", "악화", "신규", "해소"):
        assert f"<b>{label} 0</b>" in body, label
    # 요약의 지금 합계는 그 호기를 뺀 몫이고, 「이번 주 값 넣기」 합계는 그대로다.
    assert f'<span class="shk-kpi-value">{plain_total.days - now_days:,}일</span>' in body
    assert app.session_state[SCREEN_TOTAL_KEY] == plain_total
    clear_equipment_repository()


def _guide_item(section: str, heading: str) -> str:
    """Guide 원고의 `section` 머리(####) 아래에서 굵은 머리 `heading` 항목 하나(다음 첫 단계
    항목 앞까지)."""
    text = GUIDE.read_text(encoding="utf-8")
    start = text.index(f"#### {section}")
    part = text[start : text.index("\n#### ", start + 1)]
    item = part.index(f"- **{heading}**")
    return part[item : part.index("\n- ", item + 1)]


def test_the_progress_view_has_no_unit_legend_or_total_note_and_the_guide_says_them(
    tmp_path: Path,
) -> None:
    """2026-11-20 사용자 요청(요약 값 아래 회색 설명 줄 · 공정 카드 범례 줄을 Guide 로)을 같은 꼴
    전체로 — 진척 비교의 합계 칸은 라벨 · 값 · 막대와 합계에서 뺀 몫 줄(있을 때만)만이고, 두 줄
    카드의 호기 줄 위 범례 글도 없다(호기가 없는 카드의 빈 글 위 포함). 걷은 뜻은 Guide
    「진척 비교」 의 요약 · 카드 줄이 말한다(설계 규칙 UI-TXT-01 · UI-TXT-02 · PRC-01). 기준선
    칸의 출처 줄은 값이라 그대로다."""
    database_path, _ = _saved_database(tmp_path)
    app = _run(database_path)
    app = _save_button(app).click().run()
    assert not app.exception, [element.message for element in app.exception]
    (stored,) = DuckDBEquipmentRepository(database_path).list_shortening_baselines()
    app = app.selectbox(key=SHORTENING_COMPARE_KEY).set_value(stored.baseline_id).run()
    assert not app.exception, [element.message for element in app.exception]

    body = _html(app)
    assert "진척 비교 요약" in body and _progress_cards(app)
    assert 'class="shk-prog-unit"' in body
    total = re.search(
        r'<div class="shk-prog-total-figure"><span class="shk-kpi-label">'
        r"단축 필요일수 합계 \(목표 110%\)</span>"
        r'<span class="shk-kpi-value">[^<]+</span>'
        r'((?:<span class="shk-kpi-note">[^<]*</span>)*)</div>',
        body,
    )
    assert total is not None
    notes = re.findall(r'<span class="shk-kpi-note">([^<]*)</span>', total.group(1))
    assert all(note.endswith(" 빼고 견줌") for note in notes), notes
    assert "shk-units-legend" not in body
    for phrase in PROGRESS_LEFT_FOR_GUIDE:
        assert phrase not in body, phrase
    assert "현재 일정 기준 " in body and "그날 오늘 " in body
    empty = _units_markup(pd.DataFrame(), [202601, 202602], today=date(2026, 1, 1))
    assert 'class="shk-empty"' in empty and "shk-units-legend" not in empty
    assert "호기마다 두 줄" not in empty
    clear_equipment_repository()

    summary = _guide_item("진척 비교", "요약")
    for words in (
        "단축 필요일수 합계 (목표 n%)",
        "당긴 호기의 단축일수",
        "고른 목표",
        "지금 맞댄 공정",
        "뺀 몫",
        "기준 바뀜",
    ):
        assert words in summary, words
    card = _guide_item("진척 비교", "카드")
    for words in (
        "◀ 필요 시점 ── ○ 확보 시점",
        "◀ ━━ ●",
        "칸은 달",
        "점선은 오늘",
        "범례 글이 없습니다",
        "기존 → 필요 −N일",
        "점선 원",
    ):
        assert words in card, words
