# Purpose: 가용설비 화면의 CSV·붙여넣기 Import 왕복을 화면과 서비스 계층 양쪽에서 고정한다.

"""양식 내려받기부터 저장까지 한 번에 도는 길을 끝에서 끝까지 묶어 둔다.

이 파일은 두 층을 함께 본다.

* **화면 왕복(AppTest)** — 빈 설비 DB 로 `app_pages/available_equipment_status.py` 를 실제로
  실행해 `양식 → 붙여넣기 → 미리보기 → 확인 후 리비전 저장`을 누른다. 양식의 예시 한 줄을
  그대로 저장하려 하면 막히고, 값을 고치면 새 리비전이 생긴다.
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

from capa_simulation.persistence.equipment_repository import DuckDBEquipmentRepository
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
    baseline_csv_template,
    build_baseline_import_preview,
    build_equipment_import_preview,
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

IMPORT_TARGET_KEY = "equipment_import_target_v1"
CLIPBOARD_KEY = "equipment_import_clipboard_v1"
PREVIEW_KEY = "equipment_import_preview_v1"
IMPORT_SAVE_KEY = "equipment_import_save_v1"
BASELINE_DRAFT_KEY = "equipment_baseline_draft_v3"
MASTER_DRAFT_KEY = "equipment_master_draft_v3"
DRAFT_REVISION_KEY = "equipment_draft_revision_v4"

# 미리보기 한 번의 상한. 이전 UI는 미리보기를 매 rerun 다시 계산했고, 현재 UI는 검토
# 요청 시에만 만든다. 어느 동선에서도 행 수가 늘 때 지연이 급증하면 안 된다. 칸마다 1원소
# Series 를 만들어 결측을 재던 구현은 31열 기준 행당 수 ms 가 들어 200행이 1초를 넘었다.
# 상한은 지금 구현(행당 1ms 미만)에 한참 여유를 두면서도 그 구현은 반드시 넘도록 잡는다.
PREVIEW_BUDGET_PER_200_ROWS_SECONDS = 1.0


def _page_script(database_path: Path) -> str:
    """두 DB 경로를 임시 폴더로 격리해 화면을 실행하는 AppTest 스크립트.

    `tests/conftest.py` 가 테스트마다 `settings` 의 경로를 되돌리므로 여기서는 덮어쓰기만
    한다. 다른 테스트 파일에서 같은 도우미를 가져오지 않는다 — 이 파일 혼자 성립해야 한다.
    """
    simulation_database_path = database_path.with_name(f"{database_path.stem}_simulation.duckdb")
    return f"""
from pathlib import Path
import capa_simulation.settings as settings

settings.EQUIPMENT_DUCKDB_PATH = Path({str(database_path)!r})
settings.DUCKDB_PATH = Path({str(simulation_database_path)!r})
page_source = Path({str(EQUIPMENT_PAGE)!r}).read_text(encoding="utf-8")
exec(compile(page_source, {str(EQUIPMENT_PAGE)!r}, "exec"), {{"__name__": "__main__"}})
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
    """이미 다른 공정 값을 편집한 상태에서도 Import 저장이 그 값을 보존해야 한다."""
    app.session_state[DRAFT_REVISION_KEY] = "empty"
    app.session_state[BASELINE_DRAFT_KEY] = _user_baseline()
    app.session_state[MASTER_DRAFT_KEY] = empty_equipment_master()
    app.session_state["equipment_downtime_draft_v3"] = empty_downtime_schedule()


def _preview_import(
    app: AppTest,
    clipboard: str,
    *,
    target: str = "기존 보유대수",
) -> None:
    """입력 대상을 고르고 붙여넣은 뒤 변경 미리보기까지만 진행한다."""
    app.selectbox(IMPORT_TARGET_KEY).set_value(target).run()
    app.text_area(CLIPBOARD_KEY).set_value(clipboard)
    app.run()
    app.button(PREVIEW_KEY).click().run()
    assert not app.exception


def _save(app: AppTest) -> None:
    """미리보기를 확인한 사용자가 불변 리비전 저장을 확정한다."""
    app.button(IMPORT_SAVE_KEY).click().run()


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


def test_the_untouched_template_row_can_be_previewed_but_not_saved(
    tmp_path: Path,
) -> None:
    """양식을 그대로 붙여넣으면 변경 내용은 보여 주고 저장 확정에서 예시 행을 막는다.

    예시 행은 네 컬럼이 다 차 있어 `prepare_equipment_baseline` 을 그냥 통과한다. 그래서
    붙여넣기·미리보기는 정상이며, 마지막 저장이 이것을 걸러낸다.
    리비전은 불변이라 한 번 들어가면 지울 수 없다 — 막는 자리가 여기뿐이다.
    """
    database_path = tmp_path / "template_guard.duckdb"
    app = AppTest.from_string(_page_script(database_path), default_timeout=90)
    _seed_user_drafts(app)
    app.run()

    assert not app.exception
    # 사용자가 실제로 내려받는 버튼이 이 화면에 있다는 것까지 함께 묶어 둔다.
    # 없는 키를 찾으면 `KeyError` 라, 이 한 줄이 곧 존재 검사다.
    app.selectbox(IMPORT_TARGET_KEY).set_value("기존 보유대수").run()
    assert (
        app.download_button("equipment_baseline_template_download_v3").label == "기존 보유대수 양식"
    )

    _preview_import(app, _as_clipboard_text(baseline_csv_template()))

    draft = app.session_state[BASELINE_DRAFT_KEY]
    assert SAMPLE_BASELINE_PROCESS not in draft["공정"].tolist()

    _save(app)

    assert not app.exception
    assert any("예시 행이 1건" in element.value for element in app.error)
    assert not any("설비 운영 데이터 r" in element.value for element in app.success)
    assert not DuckDBEquipmentRepository(database_path).list_revisions()


def test_an_edited_count_turns_the_template_row_into_a_saved_revision(tmp_path: Path) -> None:
    """한 칸만 고치면 그 행은 사용자의 것이 되어 저장이 끝까지 간다.

    가드가 네 컬럼 전부 일치를 요구하는 이유가 여기다. 예시와 같은 공정명을 쓰는 것이 실제로
    맞는 현장이라면 저장 자체가 불가능해서는 안 된다.
    """
    database_path = tmp_path / "template_fix.duckdb"
    app = AppTest.from_string(_page_script(database_path), default_timeout=90)
    _seed_user_drafts(app)
    app.run()

    _preview_import(app, _as_clipboard_text(baseline_csv_template()))
    _save(app)
    assert any("예시 행이" in element.value for element in app.error)

    # Excel 에서 대수만 고쳐 다시 복사한다. 자연키(공정 + 분류)가 같아 그 행을 대체한다.
    header = "\t".join(BASELINE_COLUMNS)
    corrected = str(SAMPLE_BASELINE_COUNT + 5)
    _preview_import(app, f"{header}\n{_template_row(corrected)}")
    _save(app)

    assert not app.exception
    assert not app.error
    assert any("설비 운영 데이터 r1" in element.value for element in app.success)
    repository = DuckDBEquipmentRepository(database_path)
    revisions = repository.list_revisions()
    assert len(revisions) == 1
    saved = repository.load_snapshot(revisions[0].revision_id)
    assert len(saved.baseline) == len(_user_baseline()) + 1
    assert saved.baseline.loc[
        saved.baseline["공정"].eq(SAMPLE_BASELINE_PROCESS), "기존보유대수"
    ].tolist() == [float(corrected)]


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
    _preview_import(app, f"{header}\n{row}")
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

    _preview_import(
        app,
        _as_clipboard_text(equipment_csv_template()),
        target="호기 마스터",
    )

    assert app.session_state[MASTER_DRAFT_KEY].empty

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
    repeated["설비명"] = [f"EQ{index:05d}" for index in range(len(repeated))]
    incoming = prepare_equipment_master(repeated)
    current = incoming.copy()
    for column in current.columns:
        if column == "설비명":
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


def test_the_full_width_master_reads_the_same_on_both_paths() -> None:
    """네 컬럼짜리 표뿐 아니라 날짜·숫자가 섞인 설비 마스터 전체 열에서도 두 경로가 같아야 한다.

    빈 칸이 날짜면 `NaT`, 좌표면 `NaN` 이 되고 글자면 `<NA>` 가 된다. 결측 판정이 경로마다
    다르면 이 셋이 전부 갈라지므로, 폭이 넓은 표에서 한 번 더 묶어 둔다.
    """
    template = pd.read_csv(BytesIO(equipment_csv_template()), **TEXT_TABLE_READ_OPTIONS)
    edited = template.iloc[[0]].fillna("").astype(str).copy()
    # 업무 값으로서의 `NA` 하나와, 비워 둔 날짜·설비이력 하나씩.
    edited.loc[:, "구분"] = "NA"
    edited.loc[:, "반출일정"] = ""
    edited.loc[:, "설비이력"] = ""
    rows = [list(edited.columns), *edited.values.tolist()]

    from_csv = read_equipment_csv(_csv_bytes(rows))
    from_clipboard = read_equipment_clipboard(_tab_text(rows))

    assert_frame_equal(from_csv, from_clipboard)
    assert from_csv.loc[0, "구분"] == "NA"
    assert pd.isna(from_csv.loc[0, "반출일정"])
    assert pd.isna(from_csv.loc[0, "설비이력"])
