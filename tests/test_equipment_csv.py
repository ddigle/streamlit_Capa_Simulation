# Purpose: equipment csv 관련 정상·예외·회귀 동작을 검증한다.

from datetime import date
from io import BytesIO

import pandas as pd
import pytest
from test_equipment_availability import _downtime, _equipment

from capa_simulation.services.equipment_contract import (
    AREA_CODES,
    ARRIVAL_STATUSES,
    BASELINE_COLUMNS,
    DOWNTIME_COLUMNS,
    EQUIPMENT_COLUMNS,
    QUAL_CONFIRMATION_STATUSES,
    empty_downtime_schedule,
    empty_equipment_baseline,
    empty_equipment_master,
)
from capa_simulation.services.equipment_csv import (
    EQUIPMENT_CHOICE_ROWS,
    SAMPLE_BASELINE_CATEGORY,
    SAMPLE_BASELINE_COUNT,
    SAMPLE_BASELINE_PROCESS,
    SAMPLE_BASELINE_TEMPLATE_NOTE,
    SAMPLE_DOWNTIME_NOTE,
    SAMPLE_EQUIPMENT_ID,
    SAMPLE_EQUIPMENT_MANAGER,
    SAMPLE_EQUIPMENT_NOTE,
    baseline_csv_bytes,
    baseline_csv_template,
    build_baseline_import_preview,
    build_downtime_import_preview,
    build_equipment_import_preview,
    downtime_csv_bytes,
    downtime_csv_template,
    equipment_csv_bytes,
    equipment_csv_template,
    merge_baseline_rows,
    merge_downtime_rows,
    merge_equipment_rows,
    read_baseline_clipboard,
    read_baseline_csv,
    read_downtime_clipboard,
    read_downtime_csv,
    read_equipment_update,
)
from capa_simulation.services.equipment_validation import (
    prepare_downtime_schedule,
    prepare_equipment_baseline,
    prepare_equipment_master,
)
from capa_simulation.services.floor_layout_profile import FloorCanvasMap
from capa_simulation.services.schedule_confirmation import schedule_confirmation_issues

BASELINE_HEADER = "\t".join(BASELINE_COLUMNS)


def _read_whole_master(
    payload: str | bytes,
    *,
    floor_canvases: FloorCanvasMap | None = None,
    notices: list[str] | None = None,
) -> pd.DataFrame:
    """설비 마스터 표 전체를 화면 입구(`read_equipment_update`)로 읽는다 — 붙여넣기는 글, CSV 는
    바이트다. 편집본이 비어 모든 행이 새 호기이므로 새 호기에 필요한 열 검사까지 함께 돈다."""
    return read_equipment_update(
        payload, empty_equipment_master(), floor_canvases=floor_canvases, notices=notices
    ).rows


def _baseline_rows() -> pd.DataFrame:
    """같은 공정에 분류가 둘인 표. 자연키가 `공정` 단독이 아님을 드러낸다."""
    return prepare_equipment_baseline(
        pd.DataFrame(
            {
                "공정": ["Process-A", "Process-A", "Process-B"],
                "분류": ["전체", "임대", "전체"],
                "기존보유대수": [2.0, 3.0, 5.0],
                "비고": [None, None, None],
            }
        )
    )


def _incoming_baseline(process: str, category: str, count: float, note: str) -> pd.DataFrame:
    return prepare_equipment_baseline(
        pd.DataFrame(
            {
                "공정": [process],
                "분류": [category],
                "기존보유대수": [count],
                "비고": [note],
            }
        )
    )


def test_equipment_csv_template_round_trips_with_38_columns() -> None:
    result = _read_whole_master(equipment_csv_template())

    assert len(result.columns) == 38
    assert "사업부" not in result.columns
    assert "투자기준" not in result.columns
    assert "설비가동현황" not in result.columns
    assert result.columns.tolist() == list(EQUIPMENT_COLUMNS)
    assert len(result) == 1
    assert result.loc[0, "설비명"] == SAMPLE_EQUIPMENT_ID
    assert result.loc[0, "담당자"] == SAMPLE_EQUIPMENT_MANAGER
    assert result.loc[0, "설비이력"] == SAMPLE_EQUIPMENT_NOTE
    assert result.loc[0, "투자Capa"] == "299K"
    assert result.loc[0, "Area Code"] == "Main"
    assert result.loc[0, "반입실적"] == pd.Timestamp("2026-09-05")
    assert result.loc[0, "반입상태"] == "완료"
    assert result.loc[0, "Qual실적"] == pd.Timestamp("2026-09-16")
    assert result.loc[0, "Qual상태"] == "완료"
    assert result.loc[0, "환산비"] == 1.0


def test_equipment_csv_template_lists_choice_rows_without_equipment_id() -> None:
    raw = pd.read_csv(BytesIO(equipment_csv_template()), dtype="object")

    assert len(raw) == 1 + len(EQUIPMENT_CHOICE_ROWS)
    choices = raw.loc[raw["설비명"].isna()]
    assert len(choices) == len(EQUIPMENT_CHOICE_ROWS)
    assert choices["투자구분"].tolist() == ["WLP", "2.5D", "HCB"]
    # 안내 행의 예시 값이 계약에 없는 이름으로 적혀 조용히 사라지지 않았다.
    assert choices["투자Capa"].dropna().tolist() == ["322K"]
    # Area Code 는 Main·MI·부대 셋을 안내한다.
    assert choices["Area Code"].tolist() == list(AREA_CODES)
    # 예시 행과 안내 행을 합치면 두 상태 칸의 허용값이 모두 보인다.
    assert set(raw["Qual상태"]) == set(QUAL_CONFIRMATION_STATUSES)
    assert set(raw["반입상태"]) == set(ARRIVAL_STATUSES)


def test_the_template_example_row_is_a_finished_unit_with_no_confirmation_warning() -> None:
    """양식의 예시 행을 그대로 따라 쓴 호기에 일정 확인 알림이 뜨지 않는다 — 끝난 단계는 실적과
    「완료」를 함께 적은 꼴이다."""
    example = _read_whole_master(equipment_csv_template())

    assert schedule_confirmation_issues(example, today=date(2026, 10, 16)).empty


def test_downtime_csv_template_has_no_id_and_round_trips() -> None:
    equipment = _read_whole_master(equipment_csv_template())
    result = read_downtime_csv(downtime_csv_template(), equipment=equipment)

    assert len(downtime_csv_template().decode("utf-8-sig").splitlines()) == 2
    assert "비가동ID" not in result.columns
    assert result.loc[0, "설비명"] == SAMPLE_EQUIPMENT_ID
    assert result.loc[0, "비고"] == SAMPLE_DOWNTIME_NOTE


def test_equipment_templates_round_trip_through_excel_clipboard() -> None:
    equipment_text = pd.read_csv(BytesIO(equipment_csv_template())).to_csv(
        index=False,
        sep="\t",
    )
    equipment = _read_whole_master(equipment_text)
    downtime_text = pd.read_csv(BytesIO(downtime_csv_template())).to_csv(
        index=False,
        sep="\t",
    )
    downtime = read_downtime_clipboard(downtime_text, equipment=equipment)

    assert len(equipment) == 1
    assert equipment.loc[0, "설비명"] == SAMPLE_EQUIPMENT_ID
    assert equipment.loc[0, "담당자"] == SAMPLE_EQUIPMENT_MANAGER
    assert downtime.loc[0, "설비명"] == SAMPLE_EQUIPMENT_ID


def test_equipment_csv_merge_and_preview_replace_by_equipment_id() -> None:
    current = _equipment()
    incoming = current.iloc[[0]].copy()
    incoming.loc[incoming.index[0], "공정소분류"] = "Changed"

    preview = build_equipment_import_preview(current, incoming)
    result = merge_equipment_rows(current, incoming)

    assert preview.loc[0, "Import구분"] == "대체"
    assert "공정소분류" in preview.loc[0, "변경컬럼"]
    assert "Process-A → Changed" in preview.loc[0, "변경내용"]
    assert len(result) == 2
    assert result.loc[result["설비명"].eq("EQ-01"), "공정소분류"].item() == "Changed"


def test_preview_reads_blank_cells_the_same_after_the_scalar_fast_path() -> None:
    """빈 칸 판정을 `pd.Series([x]).isna()` 에서 `pd.isna(x)` 로 바꿨다.

    미리보기가 칸마다 Series 를 하나씩 만들고 있었다 — 31열이라 실측 100행 944ms ·
    500행 4.7초 · 2,000행 19초였고, 세션 키가 살아 있는 동안 **매 rerun** 다시 계산된다.
    빠르게 만드는 것보다 **판정이 한 칸도 달라지지 않는 것**이 중요하므로 세 경우를 못박는다.
    """
    current = _equipment()
    # EQ-02 는 설비이력이 차 있고 Area Code 는 비어 있다. 두 칸을 한 행에서 함께 본다.
    incoming = current.loc[current["설비명"].eq("EQ-02")].copy()
    incoming.loc[incoming.index[0], "설비이력"] = pd.NA
    incoming.loc[incoming.index[0], "Area Code"] = pd.NA

    preview = build_equipment_import_preview(current, incoming)

    # 값이 있던 칸이 비었다 → 변경으로 잡히고 "(빈 값)" 으로 적힌다.
    assert preview.loc[0, "Import구분"] == "대체"
    assert "설비이력" in preview.loc[0, "변경컬럼"]
    assert "(빈 값)" in preview.loc[0, "변경내용"]
    # 원래도 비어 있던 칸은 변경이 아니다 — 양쪽 결측은 같은 값으로 본다.
    assert "Area Code" not in str(preview.loc[0, "변경컬럼"]).split(", ")


def test_preview_does_not_depend_on_the_incoming_index() -> None:
    """판정 세 칸은 행 순서로 쌓는데 `insert` 는 **인덱스로 맞춰** 넣는다.

    `incoming` 의 인덱스가 0 부터가 아니면(필터로 고른 행, 이어 붙인 프레임) 전부 어긋나
    Import구분·변경컬럼·변경내용이 통째로 `<NA>` 가 된다. 지금 호출부가 우연히 0 기반이라
    드러나지 않았을 뿐이라 여기서 못박는다.
    """
    current = _equipment()
    shifted = current.iloc[[1]].copy()  # 인덱스가 [1] 이다
    shifted.loc[shifted.index[0], "공정소분류"] = "Changed"

    preview = build_equipment_import_preview(current, shifted)

    assert preview.loc[0, "Import구분"] == "대체"
    assert "공정소분류" in preview.loc[0, "변경컬럼"]


def test_downtime_merge_and_preview_use_natural_key() -> None:
    current = _downtime()
    incoming = current.copy()
    incoming.loc[0, "상세사유"] = "교체 사유 변경"

    preview = build_downtime_import_preview(current, incoming)
    result = merge_downtime_rows(current, incoming, equipment=_equipment())

    assert preview.loc[0, "Import구분"] == "대체"
    assert preview.loc[0, "변경컬럼"] == "상세사유"
    assert len(result) == 1
    assert result.loc[0, "상세사유"] == "교체 사유 변경"


def test_import_preview_marks_new_rows() -> None:
    incoming = _equipment().iloc[[0]].copy()
    incoming.loc[incoming.index[0], "설비명"] = "EQ-NEW"

    preview = build_equipment_import_preview(_equipment(), incoming)

    assert preview["Import구분"].tolist() == ["신규"]
    assert preview["변경컬럼"].tolist() == ["-"]


def test_baseline_csv_template_round_trips_with_the_contract_columns() -> None:
    raw = pd.read_csv(BytesIO(baseline_csv_template()), dtype="object")
    result = read_baseline_csv(baseline_csv_template())

    assert raw.columns.tolist() == list(BASELINE_COLUMNS)
    assert len(result) == 1
    assert result.loc[0, "공정"] == SAMPLE_BASELINE_PROCESS
    assert result.loc[0, "분류"] == SAMPLE_BASELINE_CATEGORY
    assert result.loc[0, "기존보유대수"] == float(SAMPLE_BASELINE_COUNT)
    assert result.loc[0, "비고"] == SAMPLE_BASELINE_TEMPLATE_NOTE


def test_baseline_csv_template_carries_no_choice_rows() -> None:
    """공정·분류·기존보유대수 중 하나만 채워도 행이 남으므로 안내 행을 둘 수 없다."""
    assert len(baseline_csv_template().decode("utf-8-sig").splitlines()) == 2

    with pytest.raises(ValueError, match="기존 보유대수의 공정에 누락값이 있습니다."):
        read_baseline_clipboard(f"{BASELINE_HEADER}\n\t전체\t\t\n")


def test_baseline_template_round_trips_through_excel_clipboard() -> None:
    text = pd.read_csv(BytesIO(baseline_csv_template())).to_csv(index=False, sep="\t")

    result = read_baseline_clipboard(text)

    assert result.loc[0, "공정"] == SAMPLE_BASELINE_PROCESS
    assert result["기존보유대수"].dtype == "float64"


def test_baseline_merge_and_preview_replace_by_process_and_category() -> None:
    current = _baseline_rows()
    incoming = _incoming_baseline("Process-A", "전체", 9.0, "증설 반영")

    preview = build_baseline_import_preview(current, incoming)
    result = merge_baseline_rows(current, incoming)

    assert preview.loc[0, "Import구분"] == "대체"
    assert "기존보유대수" in preview.loc[0, "변경컬럼"]
    assert "2.0 → 9.0" in preview.loc[0, "변경내용"]
    assert len(result) == 3
    replaced = result.loc[result["공정"].eq("Process-A") & result["분류"].eq("전체")]
    assert replaced["기존보유대수"].item() == 9.0
    # 같은 공정의 다른 분류는 Import 대상이 아니므로 그대로 남아야 한다.
    kept = result.loc[result["공정"].eq("Process-A") & result["분류"].eq("임대")]
    assert kept["기존보유대수"].item() == 3.0


def test_baseline_import_preview_marks_a_new_category_as_new() -> None:
    current = _baseline_rows()
    incoming = _incoming_baseline("Process-B", "임대", 4.0, "신규 임대")

    preview = build_baseline_import_preview(current, incoming)
    result = merge_baseline_rows(current, incoming)

    assert preview["Import구분"].tolist() == ["신규"]
    assert preview["변경컬럼"].tolist() == ["-"]
    assert preview["변경내용"].tolist() == ["-"]
    assert len(result) == 4


def test_baseline_clipboard_takes_the_same_number_rule_as_the_editor() -> None:
    result = read_baseline_clipboard(f"{BASELINE_HEADER}\nProcess-A\t전체\t1.5\t\n")

    assert result.loc[0, "기존보유대수"] == 1.5
    assert pd.isna(result.loc[0, "비고"])

    with pytest.raises(ValueError, match="기존보유대수는 0 이상의 숫자여야 합니다"):
        read_baseline_clipboard(f"{BASELINE_HEADER}\nProcess-A\t전체\t1,200\t\n")
    with pytest.raises(ValueError, match="기존보유대수는 0 이상의 숫자여야 합니다"):
        read_baseline_clipboard(f"{BASELINE_HEADER}\nProcess-A\t전체\t-1\t\n")


def test_baseline_count_error_names_the_failing_rows_by_process_and_category() -> None:
    """어느 행이 틀렸는지 공정·분류로 알린다(최대 다섯). 맞는 행은 적지 않는다."""
    bad = "".join(f"Process-{index}\t분류{index}\t-{index}\t\n" for index in range(1, 8))
    content = f"{BASELINE_HEADER}\nProcess-OK\t전체\t2.25\t\n{bad}"

    with pytest.raises(ValueError) as caught:
        read_baseline_clipboard(content)

    message = str(caught.value)
    assert message.startswith("기존보유대수는 0 이상의 숫자여야 합니다: ")
    assert "Process-1 / 분류1" in message and "Process-5 / 분류5" in message
    assert "Process-6" not in message and "Process-OK" not in message


def test_baseline_count_keeps_two_decimals_through_paste_and_export() -> None:
    """모듈 단위 기존 보유(0.25대)가 붙여넣기·내보내기에서 첫째 자리로 잘리지 않는다."""
    pasted = read_baseline_clipboard(f"{BASELINE_HEADER}\nProcess-A\t전체\t0.25\t\n")

    assert pasted.loc[0, "기존보유대수"] == 0.25
    assert ",0.25," in baseline_csv_bytes(pasted).decode("utf-8-sig")


def test_baseline_clipboard_names_the_missing_contract_column() -> None:
    with pytest.raises(ValueError, match="기존 보유대수 필수 컬럼이 없습니다: 기존보유대수"):
        read_baseline_clipboard("공정\t분류\t비고\nProcess-A\t전체\t\n")


def test_baseline_clipboard_rejects_a_duplicated_natural_key() -> None:
    with pytest.raises(ValueError, match="기존 보유대수의 공정·분류가 중복되었습니다"):
        read_baseline_clipboard(f"{BASELINE_HEADER}\nProcess-A\t전체\t1\t\nProcess-A\t전체\t2\t\n")


def test_out_of_canvas_coordinates_are_rejected_at_paste_and_import_time() -> None:
    """붙여넣기·CSV·병합 세 경로가 층 캔버스 상한을 그 자리에서 막는다."""
    # C1 1F 를 폭 40 으로 줄이면 EQ-02(30+12=42)가 캔버스를 벗어난다.
    canvases = {("C1", "1F"): (40.0, 60.0)}
    clipboard = _equipment().to_csv(index=False, sep="	")
    payload = _equipment().to_csv(index=False).encode("utf-8-sig")

    # 상한을 넘기지 않으면 예전처럼 통과한다. 과거 리비전이 계속 열려야 하기 때문이다.
    assert len(_read_whole_master(clipboard)) == 2

    with pytest.raises(ValueError, match="층 캔버스"):
        _read_whole_master(clipboard, floor_canvases=canvases)
    with pytest.raises(ValueError, match="층 캔버스"):
        _read_whole_master(payload, floor_canvases=canvases)
    with pytest.raises(ValueError, match="층 캔버스"):
        merge_equipment_rows(
            _equipment().iloc[:1],
            _equipment().iloc[1:],
            floor_canvases=canvases,
        )


# ------------------------------------------------------------- 현재 데이터 내보내기
#
# 합격선은 **왕복**이다. 내보낸 파일을 고치지 않고 그대로 다시 읽으면 같은 표가 나와야
# 하고, 그러려면 컬럼 이름·차례가 읽는 쪽 계약과 같아야 한다.


def _assert_same_table(left: pd.DataFrame, right: pd.DataFrame) -> None:
    """값이 같은지만 본다. Excel 을 거치면 `8.0` 이 `8` 로 돌아와 dtype 이 int 로 갈리는데
    그것은 이 앱이 붙여넣기에서 늘 받아 온 모양이라 같은 표로 친다."""
    pd.testing.assert_frame_equal(
        left.reset_index(drop=True), right.reset_index(drop=True), check_dtype=False
    )


def test_exported_equipment_csv_round_trips_unchanged() -> None:
    equipment = prepare_equipment_master(_equipment())

    payload = equipment_csv_bytes(equipment)
    header = payload.decode("utf-8-sig").splitlines()[0]

    assert header.split(",") == list(EQUIPMENT_COLUMNS)
    _assert_same_table(_read_whole_master(payload), equipment)


def test_exported_downtime_csv_round_trips_unchanged() -> None:
    equipment = prepare_equipment_master(_equipment())
    downtime = prepare_downtime_schedule(_downtime(), equipment=equipment)

    payload = downtime_csv_bytes(downtime)
    header = payload.decode("utf-8-sig").splitlines()[0]

    assert header.split(",") == list(DOWNTIME_COLUMNS)
    _assert_same_table(read_downtime_csv(payload, equipment=equipment), downtime)


def test_exported_baseline_csv_round_trips_unchanged() -> None:
    baseline = _baseline_rows()

    payload = baseline_csv_bytes(baseline)
    header = payload.decode("utf-8-sig").splitlines()[0]

    assert header.split(",") == list(BASELINE_COLUMNS)
    _assert_same_table(read_baseline_csv(payload), baseline)


def test_exported_dates_are_plain_days_not_timestamps() -> None:
    """준비된 프레임의 날짜는 `datetime64` 다. 시각까지 붙어 나가면 Excel 이 날짜로 안 읽는다."""
    equipment = prepare_equipment_master(_equipment())

    text = equipment_csv_bytes(equipment).decode("utf-8-sig")

    assert "00:00:00" not in text
    assert "2026-" in text


# 날짜 칸의 꼴이 섞여도 연도가 앞인 값은 뜻이 하나다. pandas 는 칸의 첫 값으로 꼴을 정해 칸 전체에
# 쓰므로, 막히느냐가 행 차례에 달리지 않는지를 첫 행·끝 행 양쪽에서 본다.


@pytest.mark.parametrize(("row", "separator"), [(0, "/"), (-1, "/"), (-1, ".")])
def test_equipment_csv_reads_a_date_written_in_another_form_in_the_same_column(
    row: int, separator: str
) -> None:
    equipment = prepare_equipment_master(_equipment())
    frame = pd.read_csv(BytesIO(equipment_csv_bytes(equipment)), dtype=str)
    target = frame.index[row]
    frame.loc[target, "반입일정"] = frame.loc[target, "반입일정"].replace("-", separator)

    result = _read_whole_master(frame.to_csv(index=False).encode("utf-8-sig"))

    _assert_same_table(result, equipment)


def _downtime_paste(start_dates: list[str]) -> str:
    rows = [
        f"EQ-01\t고장\t{start}\t\t부품 교체\t메모 {number}"
        for number, start in enumerate(start_dates)
    ]
    return "\n".join(["\t".join(DOWNTIME_COLUMNS), *rows])


def test_downtime_paste_reads_year_first_dates_written_in_mixed_forms() -> None:
    equipment = prepare_equipment_master(_equipment())
    starts = [
        "2026-10-01",
        "2026/10/05",
        "2026.10.07",
        "2026-10-09 00:00:00",
        "2026-10-11 8:30",
        "2026-10-13T08:00:00",
        "2026. 10. 15.",
    ]

    result = read_downtime_clipboard(_downtime_paste(starts), equipment=equipment)

    assert result["시작일"].tolist() == [
        pd.Timestamp(2026, 10, day) for day in (1, 5, 7, 9, 11, 13, 15)
    ]


@pytest.mark.parametrize(
    ("first", "value"),
    [
        ("2026-10-01", "05/10/2026"),
        ("2026-10-01", "다음 주"),
        ("2026-10-01", "2026/02/30"),
        ("2026-10-01", "2026-10/05"),
        ("2026-10-01", "1000/01/01"),
        ("2026-10-01", "2026-10-11 25:00"),
        ("2026-10-01", "2026/10/11 23:75"),
        ("2026-10-01", "2026-10-11 24:00:00"),
        ("2026-10-01T00:00:00+09:00", "2026/10/05"),
    ],
)
def test_downtime_paste_still_rejects_ambiguous_or_impossible_dates(first: str, value: str) -> None:
    """연도가 앞이 아닌 꼴(일·월 차례가 갈린다)·날짜가 아닌 글자·없는 날·구분자가 섞인 값·
    없는 시각은 첫 값이 멀쩡해도 지금처럼 막는다. `24:00` 은 다음 날 0시라 같은 날로 읽으면
    안 된다. 시간대가 붙은 칸도 다른 오류로 새지 않고 같은 문구로 막힌다."""
    equipment = prepare_equipment_master(_equipment())

    with pytest.raises(ValueError, match="시작일은 날짜 형식이어야 합니다"):
        read_downtime_clipboard(_downtime_paste([first, value]), equipment=equipment)


@pytest.mark.parametrize("value", ["2026-10-11 99:99", "2026/10/11 23:75", "2026-10-11 24:00"])
def test_downtime_paste_rejects_an_impossible_time_written_alone(value: str) -> None:
    """꼴이 섞이지 않은 값 하나여도 첫 읽기에서 못 읽은 값은 다시 읽는 길로 간다. 그 길이
    없는 시각을 떼어 내고 날짜만 받지 않는지 본다."""
    equipment = prepare_equipment_master(_equipment())

    with pytest.raises(ValueError, match="시작일은 날짜 형식이어야 합니다"):
        read_downtime_clipboard(_downtime_paste([value]), equipment=equipment)


def test_export_guards_identifier_values_excel_would_rewrite_and_reading_strips_them() -> None:
    """`0123` 같은 설비명은 Excel 이 `123` 으로 바꾼다. 식별 컬럼만 `="…"` 로 묶어 내보내고,
    고치지 않고 그대로 되돌린 파일은 읽는 쪽이 껍데기를 벗겨 같은 값으로 읽는다."""
    equipment = prepare_equipment_master(_equipment())
    equipment.loc[equipment.index[0], "설비명"] = "0123"

    payload = equipment_csv_bytes(equipment)
    text = payload.decode("utf-8-sig")

    # CSV 안에서는 큰따옴표가 겹쳐 `"=""0123"""` 로 적힌다. Excel 은 그것을 문자열을 돌려주는
    # 수식으로 읽어 `0123` 을 보여 주고, pandas 는 껍데기 `="0123"` 으로 되돌린다.
    assert '"=""0123"""' in text
    # 숫자·날짜 컬럼은 묶지 않는다 — 숫자로 읽히는 것이 맞고 날짜는 Excel 이 그대로 돌려준다.
    assert text.count('=""') == 1
    assert _read_whole_master(payload)["설비명"].iloc[0] == "0123"
    _assert_same_table(_read_whole_master(payload), equipment)


def test_exporting_an_empty_table_gives_a_header_only_file_that_reads_back_empty() -> None:
    """빈 표는 버튼을 막지 않는다. 헤더만 든 파일이 곧 정확한 컬럼 차례의 양식이다."""
    equipment = prepare_equipment_master(empty_equipment_master())

    for payload, columns, back in (
        (equipment_csv_bytes(equipment), EQUIPMENT_COLUMNS, _read_whole_master),
        (baseline_csv_bytes(empty_equipment_baseline()), BASELINE_COLUMNS, read_baseline_csv),
        (
            downtime_csv_bytes(empty_downtime_schedule()),
            DOWNTIME_COLUMNS,
            lambda data: read_downtime_csv(data, equipment=equipment),
        ),
    ):
        lines = payload.decode("utf-8-sig").splitlines()
        assert lines == [",".join(columns)]
        assert back(payload).empty


def test_the_master_csv_lists_units_by_process_then_name() -> None:
    """설비 마스터 CSV 는 `공정소분류` → `설비명` 오름차순이다(2026-10-08 사용자 요청). 글자 속
    숫자는 수로 견주고(`EQ2` 가 `EQ10` 앞) 대소문자는 가리지 않으며, 빈 공정은 맨 뒤다."""
    equipment = pd.DataFrame(
        {
            "설비명": ["EQ10", "EQ2", "ab-1", "EQ1", "Z9", "EQ3"],
            "공정소분류": ["Die Attach", "Die Attach", "AWB", "Die Attach", None, "awb"],
        }
    )

    text = equipment_csv_bytes(equipment).decode("utf-8-sig")
    names = [line.split(",")[EQUIPMENT_COLUMNS.index("설비명")] for line in text.splitlines()[1:]]

    assert names == ["ab-1", "EQ3", "EQ1", "EQ2", "EQ10", "Z9"]
