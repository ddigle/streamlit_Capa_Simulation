# Purpose: 가용설비 화면의 CSV·붙여넣기 Import 왕복을 화면과 서비스 계층 양쪽에서 고정한다.

"""양식 내려받기부터 저장까지 한 번에 도는 길을 끝에서 끝까지 묶어 둔다.

이 파일은 두 층을 함께 본다.

* **화면 왕복(AppTest)** — 빈 설비 DB 로 `app_pages/available_equipment_status.py` 를 실제로
  실행해 `양식 → 붙여넣기(칸을 벗어나면 자동 검사) → 편집본 적용 → 저장`을 누른다. 양식의
  예시 한 줄을 그대로 저장하려 하면 막히고, 값을 고치면 새 리비전이 생긴다.
* **서비스 계층** — 화면에서 재기 어려운 세 가지를 직접 잰다. 미리보기 비용의 상한,
  인덱스가 0 부터가 아닌 프레임의 판정, 그리고 CSV 와 붙여넣기의 빈 칸 판정 동등성.

세 가지를 화면 대신 서비스 계층에서 보는 이유는 각각 다르다. 성능은 페이지 렌더 비용이
측정에 섞이면 상한이 뜻을 잃고, 0 이 아닌 인덱스는 `prepare_*` 가 전부 `reset_index` 를 하는
탓에 지금 화면 경로로는 만들 수 없으며(공개 함수의 계약으로만 고정된다), CSV 읽기 경로는
아직 어느 화면도 호출하지 않는 대기 중 API 다. 셋 다 화면이 아니라 함수가 계약의 주인이다.
"""

from __future__ import annotations

import time
from io import BytesIO
from pathlib import Path

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal
from streamlit.testing.v1 import AppTest

from capa_simulation.components.table_toolbar import CSV_TEMPLATE_LABEL
from capa_simulation.services.clipboard_table import TEXT_TABLE_READ_OPTIONS
from capa_simulation.services.equipment_contract import (
    BASELINE_COLUMNS,
    empty_downtime_schedule,
    empty_equipment_master,
)
from capa_simulation.services.equipment_csv import (
    SAMPLE_BASELINE_CATEGORY,
    SAMPLE_BASELINE_COUNT,
    SAMPLE_BASELINE_PROCESS,
    SAMPLE_BASELINE_TEMPLATE_NOTE,
    SAMPLE_EQUIPMENT_ID,
    baseline_csv_template,
    build_baseline_import_preview,
    build_equipment_import_preview,
    downtime_csv_template,
    equipment_csv_template,
    read_baseline_clipboard,
    read_baseline_csv,
    read_equipment_clipboard,
    read_equipment_csv,
)
from capa_simulation.services.equipment_validation import (
    prepare_equipment_baseline,
    prepare_equipment_master,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EQUIPMENT_PAGE = PROJECT_ROOT / "app_pages" / "available_equipment_status.py"

BASELINE_CLIPBOARD_KEY = "equipment_baseline_clipboard_v4"
BASELINE_CONFIRM_KEY = "confirm_baseline_import_v3"
BASELINE_TEMPLATE_DOWNLOAD_KEY = "equipment_baseline_template_download_v3"
BASELINE_DRAFT_KEY = "equipment_baseline_draft_v3"
MASTER_CLIPBOARD_KEY = "equipment_master_clipboard_v4"
MASTER_CONFIRM_KEY = "confirm_equipment_import_v3"
MASTER_DRAFT_KEY = "equipment_master_draft_v3"
DOWNTIME_CLIPBOARD_KEY = "equipment_downtime_clipboard_v4"
DOWNTIME_CONFIRM_KEY = "confirm_downtime_import_v3"
DOWNTIME_DRAFT_KEY = "equipment_downtime_draft_v3"
DRAFT_REVISION_KEY = "equipment_draft_revision_v4"
SAVE_BUTTON_LABEL = "설비 데이터 저장"
# 업로드 변환 결과를 실어 두는 칸. 위젯 키가 아니라 이 파일이 만든 이름이다.
UPLOAD_PROBE_KEY = "_test_upload_probe"

# 미리보기 한 번의 상한. 붙여넣기 미리보기는 세션 키가 살아 있는 동안 **매 rerun 다시**
# 계산되므로, 사용자가 옆 위젯을 건드릴 때마다 이 시간을 다시 기다린다. 칸마다 1원소
# Series 를 만들어 결측을 재던 구현은 31열 기준 행당 수 ms 가 들어 200행이 1초를 넘었다.
# 상한은 지금 구현(행당 1ms 미만)에 한참 여유를 두면서도 그 구현은 반드시 넘도록 잡는다.
PREVIEW_BUDGET_PER_200_ROWS_SECONDS = 1.0


def _page_script(database_path: Path) -> str:
    """설비 DB 경로만 갈아끼워 화면을 그대로 실행하는 AppTest 스크립트.

    `tests/conftest.py` 가 테스트마다 `settings` 의 경로를 되돌리므로 여기서는 덮어쓰기만
    한다. 다른 테스트 파일에서 같은 도우미를 가져오지 않는다 — 이 파일 혼자 성립해야 한다.
    """
    return f"""
from pathlib import Path
import capa_simulation.settings as settings

settings.EQUIPMENT_DUCKDB_PATH = Path({str(database_path)!r})
page_source = Path({str(EQUIPMENT_PAGE)!r}).read_text(encoding="utf-8")
exec(compile(page_source, {str(EQUIPMENT_PAGE)!r}, "exec"), {{"__name__": "__main__"}})
"""


def _upload_probe_script(database_path: Path) -> str:
    """화면을 그대로 실행하고 **업로드 변환 함수의 결과**를 세션에 실어 둔다.

    `AppTest` 는 `st.file_uploader` 에 파일을 얹을 수 없고(업로더의 키는 세션에 쓸 수도
    없다), `app_pages` 는 패키지가 아니라 함수를 import 할 수도 없다. 같은 프로세스에서
    도는 스크립트 안에서 `exec` 한 이름공간을 위젯이 아닌 세션 칸에 두면 테스트가 그
    함수를 부른 결과를 그대로 받는다. 업로드 콜백이 이 변환 말고 더 하는 일은 붙여넣기 칸에
    넣고 `_scan_clipboard` 를 부르는 것뿐이라, 그 뒤는 붙여넣기 경로와 같은 길이다.
    """
    return f"""
from pathlib import Path
import streamlit as st
import capa_simulation.settings as settings

settings.EQUIPMENT_DUCKDB_PATH = Path({str(database_path)!r})
page_source = Path({str(EQUIPMENT_PAGE)!r}).read_text(encoding="utf-8")
page = {{"__name__": "__main__"}}
exec(compile(page_source, {str(EQUIPMENT_PAGE)!r}, "exec"), page)
convert = page["_csv_bytes_to_clipboard"]
st.session_state[{UPLOAD_PROBE_KEY!r}] = {{
    "baseline": convert(page["baseline_csv_template"]()),
    "equipment": convert(page["equipment_csv_template"]()),
    "downtime": convert(page["downtime_csv_template"]()),
}}
"""


def _as_clipboard_text(csv_payload: bytes) -> str:
    """내려받은 CSV 양식을 Excel 에서 열어 헤더째 복사한 것과 같은 탭 구분 텍스트."""
    frame = pd.read_csv(BytesIO(csv_payload), **TEXT_TABLE_READ_OPTIONS)
    return str(frame.to_csv(sep="\t", index=False).strip("\r\n"))


def _tab_text(rows: list[list[str]]) -> str:
    return "\n".join("\t".join(row) for row in rows)


def _csv_bytes(rows: list[list[str]]) -> bytes:
    return "\n".join(",".join(row) for row in rows).encode("utf-8-sig")


def _user_baseline() -> pd.DataFrame:
    """사용자가 이미 샘플을 지우고 자기 값으로 채워 둔 편집본."""
    return prepare_equipment_baseline(
        pd.DataFrame(
            {
                "공정": ["사내공정-A", "사내공정-B"],
                "분류": ["전체", "전체"],
                "기존보유대수": [11.0, 4.0],
                "비고": ["", ""],
            }
        )
    )


def _seed_user_drafts(app: AppTest) -> None:
    """샘플 30행 대신 사용자 값이 들어 있는 상태에서 화면을 연다.

    빈 DB 로 그냥 열면 화면이 `sample_equipment_baseline()` 30행을 채워 주고, 저장 가드가
    그 30행까지 함께 잡아 건수만 봐서는 **양식 예시 한 줄이 잡혔는지** 알 수 없다. 저장본이
    없을 때의 리비전 표식은 `"empty"` 라, 그 값을 미리 넣어 두면 씨뿌리기가 건너뛴다.
    """
    app.session_state[DRAFT_REVISION_KEY] = "empty"
    app.session_state[BASELINE_DRAFT_KEY] = _user_baseline()
    app.session_state[MASTER_DRAFT_KEY] = empty_equipment_master()
    app.session_state["equipment_downtime_draft_v3"] = empty_downtime_schedule()


def _paste_and_apply(
    app: AppTest,
    clipboard: str,
    *,
    text_area_key: str = BASELINE_CLIPBOARD_KEY,
    confirm_key: str = BASELINE_CONFIRM_KEY,
) -> None:
    """붙여넣기 → 확인 후 편집본에 적용까지 화면이 요구하는 순서 그대로.

    **「미리보기」 버튼이 없어졌다.** 붙여넣고 칸을 벗어나면 `on_change` 가 그 자리에서
    검사하고 미리보기를 세운다 — `set_value().run()` 이 브라우저의 blur 와 같은 자리에서
    그 콜백을 부른다. 이 왕복이 고정하는 것(미리보기를 거쳐야 편집본에 닿는다)은 그대로다.
    """
    app.text_area(text_area_key).set_value(clipboard)
    app.run()
    assert not app.exception
    app.button(confirm_key).click().run()
    assert not app.exception


def _save(app: AppTest) -> None:
    """폼 제출 버튼에는 `key` 가 없어 라벨로 찾는다."""
    buttons = [button for button in app.button if button.label == SAVE_BUTTON_LABEL]
    assert len(buttons) == 1, f"저장 버튼을 하나로 특정하지 못했습니다: {len(buttons)}개"
    buttons[0].click().run()


def _template_row(count: str) -> str:
    return "\t".join(
        [
            SAMPLE_BASELINE_PROCESS,
            SAMPLE_BASELINE_CATEGORY,
            count,
            SAMPLE_BASELINE_TEMPLATE_NOTE,
        ]
    )


# ---------------------------------------------------------------------------
# 1. 화면 왕복 — 양식을 그대로 저장하면 막히고, 값을 고치면 저장된다
# ---------------------------------------------------------------------------


def test_the_untouched_template_row_reaches_the_editor_but_not_the_revision(
    tmp_path: Path,
) -> None:
    """양식을 열어 아무것도 고치지 않고 붙여넣으면 편집본까지는 들어가고 저장에서 막힌다.

    예시 행은 네 컬럼이 다 차 있어 `prepare_equipment_baseline` 을 그냥 통과한다. 그래서
    붙여넣기·미리보기·적용은 전부 정상으로 보이고, 마지막 저장 한 번만이 이것을 걸러낸다.
    리비전은 불변이라 한 번 들어가면 지울 수 없다 — 막는 자리가 여기뿐이다.
    """
    app = AppTest.from_string(_page_script(tmp_path / "template_guard.duckdb"), default_timeout=90)
    _seed_user_drafts(app)
    app.run()

    assert not app.exception
    # 사용자가 실제로 내려받는 버튼이 이 화면에 있다는 것까지 함께 묶어 둔다.
    # 없는 키를 찾으면 `KeyError` 라, 이 한 줄이 곧 존재 검사다.
    assert app.download_button(BASELINE_TEMPLATE_DOWNLOAD_KEY).label == CSV_TEMPLATE_LABEL

    _paste_and_apply(app, _as_clipboard_text(baseline_csv_template()))

    draft = app.session_state[BASELINE_DRAFT_KEY]
    assert SAMPLE_BASELINE_PROCESS in draft["공정"].tolist()

    _save(app)

    assert not app.exception
    assert any("예시 행이 1건" in element.value for element in app.error)
    assert not any("설비 운영 데이터 r" in element.value for element in app.success)


def test_an_edited_count_turns_the_template_row_into_a_saved_revision(tmp_path: Path) -> None:
    """한 칸만 고치면 그 행은 사용자의 것이 되어 저장이 끝까지 간다.

    가드가 네 컬럼 전부 일치를 요구하는 이유가 여기다. 예시와 같은 공정명을 쓰는 것이 실제로
    맞는 현장이라면 저장 자체가 불가능해서는 안 된다.
    """
    app = AppTest.from_string(_page_script(tmp_path / "template_fix.duckdb"), default_timeout=90)
    _seed_user_drafts(app)
    app.run()

    _paste_and_apply(app, _as_clipboard_text(baseline_csv_template()))
    _save(app)
    assert any("예시 행이" in element.value for element in app.error)

    # Excel 에서 대수만 고쳐 다시 복사한다. 자연키(공정 + 분류)가 같아 그 행을 대체한다.
    header = "\t".join(BASELINE_COLUMNS)
    corrected = str(SAMPLE_BASELINE_COUNT + 5)
    _paste_and_apply(app, f"{header}\n{_template_row(corrected)}")

    draft = app.session_state[BASELINE_DRAFT_KEY]
    assert len(draft) == len(_user_baseline()) + 1
    assert draft.loc[draft["공정"].eq(SAMPLE_BASELINE_PROCESS), "기존보유대수"].tolist() == [
        float(corrected)
    ]

    _save(app)

    assert not app.exception
    assert not app.error
    assert any("설비 운영 데이터 r1" in element.value for element in app.success)
    # 저장 뒤에는 화면이 더 이상 「샘플을 유지한다」고 말하지 않고 리비전을 편집한다고 말한다.
    assert any("최근 저장본 r1" in element.value for element in app.caption)


def test_a_paste_that_only_repeats_the_template_process_name_is_still_the_user_s_row(
    tmp_path: Path,
) -> None:
    """공정명만 양식과 같고 나머지가 다르면 막지 않는다.

    양식의 공정명은 합성 표본에서 온 문자열일 뿐이라 실제 공정명과 겹칠 수 있다. 공정명
    하나로 막으면 그 현장은 이 화면을 쓸 수 없다.
    """
    app = AppTest.from_string(_page_script(tmp_path / "same_process.duckdb"), default_timeout=90)
    _seed_user_drafts(app)
    app.run()

    header = "\t".join(BASELINE_COLUMNS)
    row = "\t".join([SAMPLE_BASELINE_PROCESS, "임대", str(SAMPLE_BASELINE_COUNT), "실제 집계"])
    _paste_and_apply(app, f"{header}\n{row}")
    _save(app)

    assert not app.exception
    assert not app.error
    assert any("설비 운영 데이터 r1" in element.value for element in app.success)


@pytest.mark.xfail(
    reason=(
        "양식 예시 가드가 기존 보유대수에만 있다. 호기 마스터 양식의 예시 호기 SAM01 은 "
        "그대로 붙여넣어도 저장까지 간다 — 같은 위험인데 한 표만 막혀 있다. 고칠지 말지는 "
        "사람이 정한다. 가드가 생기면 이 표시를 떼어라."
    ),
)
def test_the_untouched_master_template_row_is_stopped_at_save(tmp_path: Path) -> None:
    """호기 마스터 양식의 예시 한 줄도 기존 보유대수와 같은 자리에서 막혀야 한다.

    `SAM01` 은 담당자 「홍길동」까지 붙은 표본 값인데 네 일정과 확정상태가 다 차 있어
    `prepare_equipment_master` 를 그냥 통과한다. 저장되면 호기 마스터에만 있고 현장에는 없는
    호기 하나가 그 리비전의 총대수·가용대수에 남는다. 기존 보유대수 쪽이 오늘 막힌 것과
    출처도 결과도 같다.

    비가동 일정 양식은 같은 `SAM01` 을 참조하는데, 호기 마스터에 없으면 붙여넣기 단계에서
    이미 막히므로 이 구멍은 호기 마스터 한 곳이다.
    """
    app = AppTest.from_string(_page_script(tmp_path / "master_guard.duckdb"), default_timeout=90)
    _seed_user_drafts(app)
    app.run()

    _paste_and_apply(
        app,
        _as_clipboard_text(equipment_csv_template()),
        text_area_key=MASTER_CLIPBOARD_KEY,
        confirm_key=MASTER_CONFIRM_KEY,
    )

    assert app.session_state[MASTER_DRAFT_KEY]["호기"].tolist() == [SAMPLE_EQUIPMENT_ID]

    _save(app)

    assert not app.exception
    assert any("예시 행이" in element.value for element in app.error)
    assert not any("설비 운영 데이터 r" in element.value for element in app.success)


# ---------------------------------------------------------------------------
# 2. 미리보기 비용 — 행 수가 늘어도 선형에 가깝게
# ---------------------------------------------------------------------------


def _wide_preview_pair(rows: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """31열 호기 마스터에서 **키를 뺀 모든 글자 컬럼이 달라진** 최악에 가까운 한 쌍.

    미리보기는 바뀐 컬럼을 찾느라 행마다 30번 비교하고, 바뀐 칸마다 한 번 더 문자열로
    바꾼다. 편집한 마스터를 통째로 다시 붙여넣는 것이 실제로 이 모양이라, 상한은 이 경로에서
    재야 뜻이 있다.
    """
    template = read_equipment_csv(equipment_csv_template())
    repeated = pd.concat([template] * rows, ignore_index=True)
    repeated["호기"] = [f"EQ{index:05d}" for index in range(len(repeated))]
    incoming = prepare_equipment_master(repeated)
    current = incoming.copy()
    for column in current.columns:
        if column == "호기":
            continue
        if current[column].dtype == "object" or str(current[column].dtype) == "string":
            current[column] = "이전값"
    return current, incoming


def _fastest_preview_seconds(rows: int, *, repeats: int = 3) -> float:
    """가장 빠른 한 번을 쓴다. 같은 PC 에서 다른 작업이 함께 도는 것을 가정한다."""
    current, incoming = _wide_preview_pair(rows)
    build_equipment_import_preview(current.head(5), incoming.head(5))  # 예열
    durations: list[float] = []
    for _ in range(repeats):
        started = time.perf_counter()
        preview = build_equipment_import_preview(current, incoming)
        durations.append(time.perf_counter() - started)
        assert len(preview) == rows
    return min(durations)


def test_a_200_row_preview_finishes_inside_the_budget() -> None:
    """200행 미리보기 한 번이 상한 안에 끝난다."""
    elapsed = _fastest_preview_seconds(200)

    assert elapsed < PREVIEW_BUDGET_PER_200_ROWS_SECONDS, (
        f"200행 미리보기가 {elapsed:.3f}초 걸렸습니다. 상한 {PREVIEW_BUDGET_PER_200_ROWS_SECONDS}초"
    )


def test_the_preview_budget_holds_per_row_as_the_table_grows() -> None:
    """행당 비용이 유지된다 — 800행은 200행 상한의 네 배 안에 끝난다."""
    elapsed = _fastest_preview_seconds(800)
    budget = PREVIEW_BUDGET_PER_200_ROWS_SECONDS * 4

    assert elapsed < budget, f"800행 미리보기가 {elapsed:.3f}초 걸렸습니다. 상한 {budget}초"


def test_the_preview_cost_does_not_bend_upward_with_row_count() -> None:
    """네 배 큰 표가 열 배 넘게 걸리면 행당 비용이 아니라 모양이 틀어진 것이다.

    배수를 넉넉히(선형이면 4배인 자리에 10배) 둔다. 재는 시간이 100ms 안팎이라 배수를
    조이면 기계 사정에 흔들린다. 여기서 보려는 것은 제곱으로 휘는 모양뿐이다.
    """
    small = _fastest_preview_seconds(200)
    large = _fastest_preview_seconds(800)

    assert large < small * 10, f"200행 {small:.3f}초 대비 800행 {large:.3f}초"


# ---------------------------------------------------------------------------
# 3. 인덱스가 0 부터가 아닌 프레임
# ---------------------------------------------------------------------------


def test_the_preview_verdict_survives_a_frame_that_does_not_start_at_zero() -> None:
    """판정 세 컬럼은 행 순서대로 쌓고 `insert` 는 인덱스로 맞춘다 — 그 둘을 맞춰 둔다.

    `prepare_*` 가 모두 `reset_index` 를 하므로 지금 화면 경로로는 0 이 아닌 인덱스가 오지
    않는다. 그러나 `build_*_import_preview` 는 공개 함수이고, 걸러 낸 일부만 넘기거나 두 표를
    이어 붙여 넘기는 순간 판정이 통째로 `<NA>` 가 된다. 조용히 틀리는 쪽이라 여기서 고정한다.
    """
    current = prepare_equipment_baseline(
        pd.DataFrame(
            {
                "공정": ["사내공정-A", "사내공정-B"],
                "분류": ["전체", "전체"],
                "기존보유대수": [3.0, 9.0],
                "비고": ["이전메모", None],
            }
        )
    )
    incoming = prepare_equipment_baseline(
        pd.DataFrame(
            {
                "공정": ["사내공정-A", "사내공정-C", "사내공정-B"],
                "분류": ["전체", "전체", "전체"],
                "기존보유대수": [12.0, 5.0, 9.0],
                "비고": ["새메모", "신규", None],
            }
        )
    )
    incoming.index = pd.Index([10, 20, 30])

    preview = build_baseline_import_preview(current, incoming)

    assert preview["Import구분"].tolist() == ["대체", "신규", "대체"]
    assert preview.loc[:, ["Import구분", "변경컬럼", "변경내용"]].notna().all().all()
    assert preview["변경컬럼"].tolist() == ["기존보유대수, 비고", "-", "변경 없음"]
    assert preview.index.tolist() == [0, 1, 2]
    # 붙인 세 컬럼이 원래 행과 같은 줄에 있어야 한다.
    assert preview["공정"].tolist() == ["사내공정-A", "사내공정-C", "사내공정-B"]


# ---------------------------------------------------------------------------
# 4. 빈 칸 판정이 CSV 경로와 붙여넣기 경로에서 같다
# ---------------------------------------------------------------------------


# 빈 비고, 업무 값으로서의 `NA`, 그리고 통째로 빈 줄을 한 표에 담는다. `NA` 는 pandas 가
# 기본으로 결측 취급하는 문자열이라, 한쪽 경로만 그 기본값을 쓰면 같은 표가 전송 방식에
# 따라 다르게 읽힌다.
_PARITY_ROWS: list[list[str]] = [
    list(BASELINE_COLUMNS),
    ["사내공정-A", "전체", "12", ""],
    ["사내공정-NA", "NA", "7", "NA"],
    ["", "", "", ""],
    ["사내공정-B", "전체", "5", "증설"],
]


def _parity_current() -> pd.DataFrame:
    return prepare_equipment_baseline(
        pd.DataFrame(
            {
                "공정": ["사내공정-A", "사내공정-NA"],
                "분류": ["전체", "NA"],
                "기존보유대수": [3.0, 7.0],
                "비고": ["이전메모", ""],
            }
        )
    )


def test_the_csv_and_paste_paths_read_the_same_table_the_same_way() -> None:
    """같은 표를 파일로 올리든 붙여넣든 결과 프레임이 한 글자도 다르지 않아야 한다."""
    from_csv = read_baseline_csv(_csv_bytes(_PARITY_ROWS))
    from_clipboard = read_baseline_clipboard(_tab_text(_PARITY_ROWS))

    assert_frame_equal(from_csv, from_clipboard)
    # 빈 줄은 양쪽 모두 버린다. 남는 것은 값이 있는 세 줄이다.
    assert len(from_csv) == 3


def test_a_business_value_named_na_is_not_a_blank_cell_on_either_path() -> None:
    """`NA` 는 결측이 아니라 값이다. 결측으로 읽히면 그 행의 식별이 통째로 사라진다."""
    for frame in (
        read_baseline_csv(_csv_bytes(_PARITY_ROWS)),
        read_baseline_clipboard(_tab_text(_PARITY_ROWS)),
    ):
        na_row = frame.loc[frame["공정"].eq("사내공정-NA")]

        assert na_row["분류"].tolist() == ["NA"]
        assert na_row["비고"].tolist() == ["NA"]


def test_the_preview_marks_the_same_cells_blank_on_both_paths() -> None:
    """미리보기가 「(빈 값)」이라고 적는 자리가 두 경로에서 같아야 한다."""
    current = _parity_current()
    csv_preview = build_baseline_import_preview(
        current, read_baseline_csv(_csv_bytes(_PARITY_ROWS))
    )
    paste_preview = build_baseline_import_preview(
        current, read_baseline_clipboard(_tab_text(_PARITY_ROWS))
    )

    assert csv_preview["변경내용"].tolist() == paste_preview["변경내용"].tolist()
    assert csv_preview["Import구분"].tolist() == ["대체", "대체", "신규"]
    # 값이 있던 비고를 지우면 「→ (빈 값)」, 비어 있던 자리에 `NA` 를 넣으면 「(빈 값) →」다.
    assert "비고: 이전메모 → (빈 값)" in csv_preview.loc[0, "변경내용"]
    assert csv_preview.loc[1, "변경내용"] == "비고: (빈 값) → NA"


def test_the_31_column_master_reads_the_same_on_both_paths() -> None:
    """네 컬럼짜리 표뿐 아니라 날짜·숫자가 섞인 31열에서도 두 경로가 같아야 한다.

    빈 칸이 날짜면 `NaT`, 좌표면 `NaN` 이 되고 글자면 `<NA>` 가 된다. 결측 판정이 경로마다
    다르면 이 셋이 전부 갈라지므로, 폭이 넓은 표에서 한 번 더 묶어 둔다.
    """
    template = pd.read_csv(BytesIO(equipment_csv_template()), **TEXT_TABLE_READ_OPTIONS)
    edited = template.iloc[[0]].fillna("").astype(str).copy()
    # 업무 값으로서의 `NA` 하나와, 비워 둔 날짜·비고 하나씩.
    edited.loc[:, "분류1"] = "NA"
    edited.loc[:, "반출일정"] = ""
    edited.loc[:, "비고"] = ""
    rows = [list(edited.columns), *edited.values.tolist()]

    from_csv = read_equipment_csv(_csv_bytes(rows))
    from_clipboard = read_equipment_clipboard(_tab_text(rows))

    assert_frame_equal(from_csv, from_clipboard)
    assert from_csv.loc[0, "분류1"] == "NA"
    assert pd.isna(from_csv.loc[0, "반출일정"])
    assert pd.isna(from_csv.loc[0, "비고"])


# ---------------------------------------------------------------------------
# 5. 파일 업로드가 붙여넣기와 같은 글을 만든다
# ---------------------------------------------------------------------------


def test_the_upload_builds_the_very_text_a_paste_would_hold(tmp_path: Path) -> None:
    """내려받은 양식을 올린 것과 Excel 에서 복사해 붙여넣은 것이 **같은 글**이어야 한다.

    업로드가 따로 파싱·검증을 갖지 않는 것이 이 개편의 전제다. 파일은 붙여넣기 칸을 채우고
    그 뒤는 같은 길을 간다 — 그래서 변환 결과가 한 글자라도 다르면 「파일로는 되는데
    붙여넣으면 안 된다」가 생긴다.

    **줄 끝은 `\n` 으로 맞춘다.** 비교 대상인 `_as_clipboard_text` 는 pandas `to_csv` 라
    Windows 에서 `os.linesep`(=`\r\n`)을 쓰는데, 브라우저의 `st.text_area` 에 든 글은
    `\n` 이다. 화면이 실제로 받는 쪽에 맞추고 비교에서 그 차이만 지운다(파서는 `read_csv`
    라 둘 다 같은 표로 읽는다).
    """
    app = AppTest.from_string(
        _upload_probe_script(tmp_path / "upload_equivalence.duckdb"), default_timeout=90
    ).run()

    assert not app.exception
    converted = app.session_state[UPLOAD_PROBE_KEY]
    for name, payload in (
        ("baseline", baseline_csv_template()),
        ("equipment", equipment_csv_template()),
        ("downtime", downtime_csv_template()),
    ):
        assert converted[name] == _as_clipboard_text(payload).replace("\r\n", "\n"), name


def test_each_uploaded_template_reaches_the_editor_through_the_paste_path(
    tmp_path: Path,
) -> None:
    """세 양식 모두 올린 그대로 미리보기를 거쳐 편집본에 닿는다.

    비가동 일정 양식은 호기 마스터의 예시 호기를 참조하므로 순서가 정해져 있다 — 마스터를
    먼저 넣지 않으면 붙여넣기 단계에서 막힌다. 그 순서까지 한 번에 돌려 둔다.
    """
    app = AppTest.from_string(
        _upload_probe_script(tmp_path / "upload_chain.duckdb"), default_timeout=90
    )
    _seed_user_drafts(app)
    app.run()

    assert not app.exception
    converted = app.session_state[UPLOAD_PROBE_KEY]

    _paste_and_apply(
        app,
        converted["equipment"],
        text_area_key=MASTER_CLIPBOARD_KEY,
        confirm_key=MASTER_CONFIRM_KEY,
    )
    assert app.session_state[MASTER_DRAFT_KEY]["호기"].tolist() == [SAMPLE_EQUIPMENT_ID]

    _paste_and_apply(
        app,
        converted["downtime"],
        text_area_key=DOWNTIME_CLIPBOARD_KEY,
        confirm_key=DOWNTIME_CONFIRM_KEY,
    )
    assert app.session_state[DOWNTIME_DRAFT_KEY]["호기"].tolist() == [SAMPLE_EQUIPMENT_ID]

    _paste_and_apply(app, converted["baseline"])
    assert SAMPLE_BASELINE_PROCESS in app.session_state[BASELINE_DRAFT_KEY]["공정"].tolist()

    # 기존 보유대수 양식의 예시 한 줄은 **저장에서** 막힌다. 올리는 길이 늘어도 그 가드는
    # 그대로다(`test_the_untouched_template_row_reaches_the_editor_but_not_the_revision`).
    _save(app)
    assert any("예시 행이" in element.value for element in app.error)
