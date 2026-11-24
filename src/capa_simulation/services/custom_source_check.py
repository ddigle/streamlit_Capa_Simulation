# Purpose: 본 표에 CUSTOM 원천 답(둘째 표 · 원천 CSV)을 Capa Code 로 붙이고 행 수를 대조한다.

"""CUSTOM 원천 표 붙이기와 대조(Streamlit 없음 — 화면 등록과 자동 갱신이 같은 판정을 받는다).

본 조회문은 CUSTOM 칸을 상수로 싣는다. 부품(Capa Code)의 CUSTOM 은 따로 적재되는 CUSTOM 원천 표에
있고, 그 표를 `Capa Code · 생산계획년월 · CUSTOM` 마다 센 답(칸은 `CUSTOM_SOURCE_COLUMNS`)을 받아
본 표의 CUSTOM 칸을 **Capa Code 로만** 덮는다. 행을 이어 붙이지 않으므로(merge 가 아니라 조회표
map) 본 표 행 수 · 차례 · index 가 그대로다.

멈추는 것(2026-11-22 사용자 답 Q2 (가) · Q9 (가) — 그대로 등록하면 그 부품이 다른 부품과 「구분
없음」 으로 합쳐지거나 달마다 다른 제품으로 갈린다):

- 답이 0행 · 칸이 모자람 · `행수` 가 숫자가 아님.
- 한 Capa Code 에 CUSTOM 이 둘 이상(달마다 다른 것 포함). 앞뒤 공백 · 대소문자만 다른 표기는
  하나다 — 정규화는 `core_data_derivation.normalize_custom_values` 한 곳을 부른다.
- 줄은 있는데 CUSTOM 이 빈(NULL · 빈 글자 · 공백뿐) Capa Code. 원천 글자가 빈 값 표지
  (`CUSTOM_BLANK`) 그대로인 것도 같다 — 붙이면 빈 부품과 같은 키가 된다.
- 본 표의 Capa Code 가 CUSTOM 원천 표에 없음.

Capa Code 는 앞뒤 공백만 떼어 맞대고(대소문자는 둔다), 생산계획년월은 양쪽을 같은 글자로 맞춘다 —
정수 · 실수(`202611.0`) · 글자 어느 꼴로 와도 `202611` 이다. Capa Code 가 빈 행은 어느 쪽이든 짝짓지
않는다 — 본 표의 그 행은 CUSTOM 이 빈 값 표지가 되고 못 찾음 · 칸 대조에서 빠진다(그런 행은 RQ
표 업무 키 검사가 따로 막는다).

멈추지 않는 것: 한쪽에만 있는 (Capa Code, 생산계획년월) 칸과 두 표 행 수가 다른 칸은 알리고
등록한다(`CustomSourceCheck.warns`) — 붙이기가 Capa Code 단위라 값에는 영향이 없다. 칸 대조의 본 표
수는 받은 행 그대로(완전 중복 행 포함 — 등록이 그대로 싣는다)이고, 완전 중복을 접은 수는 합계로만
남긴다(`main_distinct_rows`).

원천 CSV 는 CUSTOM 이 본 표 칸에 실려 온다 — 그 표를 같은 꼴의 답으로 센 뒤(`custom_rows_of` —
빈 CUSTOM 줄 · 빈 달 줄도 한 줄로 남긴다) 같은 두 함수에 넣어 같은 규칙으로 멈춘다. 멈춤 글의
자리 낱말만 원천마다 다르다(`CustomSourceWords` — 둘째 표는 기본값 `TABLE_WORDS`, 파일은
`FILE_WORDS`).

끄개(어댑터의 `CAPA_BDQ_CUSTOM_SOURCE=off`)를 내린 등록은 CUSTOM 원천 표를 묻지 않는다 — 본 표
CUSTOM 칸을 모두 빈 값 표지(`CUSTOM_BLANK`)로 덮고(`blank_custom_values`) 대조는 「붙이지 않음」
(`CustomSourceCheck.switched_off`)이다. 옛 상수로 조용히 물러나지 않고 「부품 구분 없음」 을 글자
그대로 남기며, 메모 조각과 등록 알림이 그 사실을 늘 드러낸다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

import pandas as pd

from capa_simulation.services.core_data_derivation import CUSTOM_BLANK, normalize_custom_values

CODE_COLUMN: Final = "Capa Code"
MONTH_COLUMN: Final = "생산계획년월"
CUSTOM_COLUMN: Final = "CUSTOM"
ROWS_COLUMN: Final = "행수"
# CUSTOM 원천 표 조회 결과의 칸 — 조회문 별칭을 이름 바꾸기로 맞춘 뒤의 이름이다.
CUSTOM_SOURCE_COLUMNS: Final = (CODE_COLUMN, MONTH_COLUMN, CUSTOM_COLUMN, ROWS_COLUMN)
# 대조 표(`CustomSourceCheck.cells`)의 칸.
MAIN_ROWS_COLUMN: Final = "본 표 행"
CUSTOM_ROWS_COLUMN: Final = "CUSTOM 원천 표 행"
CELL_COLUMNS: Final = (CODE_COLUMN, MONTH_COLUMN, MAIN_ROWS_COLUMN, CUSTOM_ROWS_COLUMN)
# 멈춤 글에 싣는 부품 수. 넘으면 「외 n종」 이다.
CUSTOM_EXAMPLE_LIMIT: Final = 10
# 부품 하나에 싣는 달 수. 넘으면 「외 n개월」 이다.
_MONTH_EXAMPLE_LIMIT: Final = 3
_PLAN_FLAG_COLUMN: Final = "계획기초정보여부"
_MERGED_NOTE: Final = f"그대로 등록하면 그 부품은 구분 없음({CUSTOM_BLANK})으로 합쳐집니다."
# 끄개로 CUSTOM 원천 표를 묻지 않은 등록의 메모 조각 — 변수 이름은 싣지 않는다(시나리오 관리 목록
# 메모 칸은 모두가 본다).
SWITCHED_OFF_MEMO: Final = f"CUSTOM 원천 붙이지 않음 — 부품 구분 없음({CUSTOM_BLANK})"
# 같은 등록의 알림 글(사건 알림 `SC-06`) — 앞 60자가 무엇을 했는지를 말한다. 끄개 이름 · 코드는
# 알리는 쪽이 끝에 붙인다.
SWITCHED_OFF_NOTICE: Final = (
    "CUSTOM 원천 끄개로 부품 구분 없이 등록했습니다 — CUSTOM 원천 표를 묻지 않아 모든 부품의 "
    f"CUSTOM 이 구분 없음({CUSTOM_BLANK})이고, 리비전 메모에 「CUSTOM 원천 붙이지 않음」 이 "
    "남습니다. 이 코드는 끄개를 걷은 뒤에도 부품을 나눠 다시 받을 수 없습니다."
)


@dataclass(frozen=True)
class CustomSourceWords:
    """멈춤 글(둘 이상 · 빈 값 · 못 찾음)에서 원천마다 다른 낱말 — 판정은 같고 글만 갈린다.

    - `place` 답이 온 자리 — 글 머리 「<자리>에서 · <자리>에」 의 자리다(뒤 조사는 끝소리를 타지
      않는 「에 · 에서」 뿐이다).
    - `several_fix` 한 Capa Code 에 CUSTOM 이 둘 이상일 때 · `missing_fix` 본 표 Capa Code 가 답에
      없을 때의 끝 문장(고칠 곳).

    0행 · 칸 모자람 · 행수 글은 둘째 표 글 그대로다 — 원천 CSV 는 그 답을 본 표에서 세므로
    (`custom_rows_of`) 그 판정에 닿지 않는다.
    """

    place: str
    several_fix: str
    missing_fix: str


# 둘째 표(CUSTOM 원천 표 조회)의 낱말 — 두 공개 함수의 기본값이다.
TABLE_WORDS: Final = CustomSourceWords(
    place="CUSTOM 원천 표",
    several_fix="CUSTOM 원천 표를 바로잡은 뒤 다시 등록하세요.",
    missing_fix="CUSTOM 원천 표에 그 부품이 적재됐는지 확인한 뒤 다시 등록하세요.",
)
# 원천 CSV(파일 행에서 센 답)의 낱말. 못 찾음은 답을 같은 표에서 세어 닿지 않지만, 닿으면 같은
# 고침 글이다.
FILE_WORDS: Final = CustomSourceWords(
    place="CSV 파일",
    several_fix="원천에서 바로잡아 CSV 를 다시 받은 뒤 올리세요.",
    missing_fix="원천에서 바로잡아 CSV 를 다시 받은 뒤 올리세요.",
)


@dataclass(frozen=True)
class CustomSourceCheck:
    """본 표와 CUSTOM 원천 표의 대조 수 — 등록 알림(`notice`)과 리비전 · 자동 갱신 메모(`memo`)가
    같은 수를 쓴다.

    - `main_rows` 본 표 행 · `main_distinct_rows` 그 가운데 완전 중복을 접은 행 · `custom_rows`
      CUSTOM 원천 표 행(`행수` 합).
    - `kinds` 본 표에 붙은 CUSTOM 값 종류 수(Capa Code 가 빈 행의 빈 값 표지는 세지 않는다).
    - `one_side_cells` 한쪽 표에만 있는 (Capa Code, 생산계획년월) 칸 · `count_mismatch_cells` 두
      표에 다 있는데 행 수가 다른 칸. `cells` 는 그 칸들의 표(칸 `CELL_COLUMNS`, 없는 쪽은 0행)다.
    - `attached` CUSTOM 원천 표의 값을 붙였는가 — 끄개로 묻지 않은 등록은 거짓이고 대조 칸이 없다
      (`switched_off`).
    """

    main_rows: int
    main_distinct_rows: int
    custom_rows: int
    kinds: int
    one_side_cells: int
    count_mismatch_cells: int
    cells: pd.DataFrame = field(compare=False, repr=False)
    attached: bool = True

    @classmethod
    def switched_off(cls, frame: pd.DataFrame) -> CustomSourceCheck:
        """끄개로 CUSTOM 원천 표를 묻지 않은 등록의 대조 — 붙이지 않았고 대조 칸이 없으며, 종류는
        구분 없음 하나다(본 표가 0행이면 0). `frame` 은 CUSTOM 을 덮기 전이든 뒤든 같은 수다."""
        return cls(
            main_rows=len(frame),
            main_distinct_rows=len(frame) - int(frame.duplicated().sum()),
            custom_rows=0,
            kinds=1 if len(frame) else 0,
            one_side_cells=0,
            count_mismatch_cells=0,
            cells=pd.DataFrame(columns=list(CELL_COLUMNS)),
            attached=False,
        )

    @property
    def warns(self) -> bool:
        """알릴 것이 있는가 — 붙이지 않았거나(끄개) 알릴 칸(한쪽에만 있는 칸 · 행 수가 다른 칸)이
        있다."""
        return not self.attached or self.one_side_cells + self.count_mismatch_cells > 0

    def notice(self) -> str:
        """등록 결과 알림. 알릴 것이 없으면 빈 글. 붙이지 않은 등록은 그 사실(`SWITCHED_OFF_NOTICE`
        — 사건 알림 `SC-06`)이고, 붙인 등록은 어긋난 칸 수가 맨 앞이다 — 알림창 짧은 글
        (`alerts.short_text` — 60자)이 칸마다 네 자리 수까지 그 수를 싣는다(`SC-05`)."""
        if not self.attached:
            return SWITCHED_OFF_NOTICE
        if not self.warns:
            return ""
        cells = self.count_mismatch_cells + self.one_side_cells
        return (
            f"CUSTOM 원천 대조 어긋난 칸 {cells:,}개(행 수 다른 칸 {self.count_mismatch_cells:,} · "
            f"한쪽에만 있는 칸 {self.one_side_cells:,}) — 본 표와 CUSTOM 원천 표의 (Capa Code · "
            "생산계획년월) 칸 행 수가 다릅니다. CUSTOM 은 Capa Code 로 붙이므로 값에는 영향이 없어 "
            "등록했습니다."
        )

    def memo(self) -> str:
        """리비전 메모에 붙이는 짧은 조각 — 늘 붙는다. 붙이지 않은 등록은 `SWITCHED_OFF_MEMO` 다."""
        if not self.attached:
            return SWITCHED_OFF_MEMO
        return (
            f"CUSTOM 원천 대조 — 종류 {self.kinds:,} · 행 수 다른 칸 "
            f"{self.count_mismatch_cells:,} · 한쪽에만 있는 칸 {self.one_side_cells:,}"
        )


def check_custom_rows(
    custom: pd.DataFrame, *, words: CustomSourceWords = TABLE_WORDS
) -> pd.DataFrame:
    """CUSTOM 원천 표 조회 결과를 검사하고 맞춘 표를 돌려준다 — 본 조회 앞에서 부른다.

    0행 · 칸 모자람 · `행수` 숫자 아님 · 한 Capa Code 에 CUSTOM 둘 이상 · 빈 CUSTOM 은
    `ValueError` 다. 둘 이상 · 빈 CUSTOM 글의 자리 낱말은 `words` 다. 돌려주는 표는 칸이
    `CUSTOM_SOURCE_COLUMNS` 뿐이고 Capa Code(앞뒤 공백 뗌, 빈 값은 빈 글자) · 생산계획년월(글자) ·
    CUSTOM(정규화) · 행수(정수)다. 같은 표를 다시 넣어도 같은 표가 나온다.
    """
    if custom.empty:
        raise ValueError(
            "CUSTOM 원천 표의 조회 결과가 0행이라 등록하지 않았습니다 — 이 시뮬레이션 코드의 "
            "CUSTOM 이 아직 적재되지 않았을 수 있습니다. 적재된 뒤 다시 등록하세요."
        )
    missing = [column for column in CUSTOM_SOURCE_COLUMNS if column not in custom.columns]
    if missing:
        raise ValueError(f"CUSTOM 원천 표 조회 결과에 필요한 칸이 없습니다: {', '.join(missing)}")
    rows = pd.to_numeric(custom[ROWS_COLUMN], errors="coerce")
    if bool(rows.isna().any()):
        raise ValueError("CUSTOM 원천 표 조회 결과의 행수 칸에 숫자가 아닌 값이 있습니다.")
    checked = pd.DataFrame(
        {
            CODE_COLUMN: _code_text(custom[CODE_COLUMN]),
            MONTH_COLUMN: _month_text(custom[MONTH_COLUMN]),
            CUSTOM_COLUMN: normalize_custom_values(custom[CUSTOM_COLUMN]),
            ROWS_COLUMN: rows.astype("int64"),
        }
    ).reset_index(drop=True)
    listed = checked.loc[checked[CODE_COLUMN].ne("")]
    _reject_several_values(listed, words)
    _reject_blank_values(listed, words)
    return checked


def attach_custom_values(
    frame: pd.DataFrame, custom: pd.DataFrame, *, words: CustomSourceWords = TABLE_WORDS
) -> tuple[pd.DataFrame, CustomSourceCheck]:
    """본 표 CUSTOM 칸을 CUSTOM 원천 표의 값으로 덮고 두 표를 대조한다.

    `custom` 은 `check_custom_rows` 를 지나지 않은 답이어도 된다 — 여기서 같은 `words` 로 다시
    검사한다. 본 표에 Capa Code · 생산계획년월 칸이 없거나 본 표의 Capa Code 가 CUSTOM 원천 표에
    없으면 `ValueError` 다. 돌려주는 표는 받은 표의 사본이고 CUSTOM 칸만 다르다(행 수 · 차례 ·
    index · 칸 차례가 같고, 받은 표의 CUSTOM 칸이 글자 dtype 이면 그 dtype 을 지킨다).
    """
    checked = check_custom_rows(custom, words=words)
    absent = [column for column in (CODE_COLUMN, MONTH_COLUMN) if column not in frame.columns]
    if absent:
        raise ValueError(f"본 표에 CUSTOM 을 붙일 칸이 없습니다: {', '.join(absent)}")
    # 받은 표의 index 는 겹칠 수 있어 안에서는 차례로만 맞댄다.
    codes = _code_text(frame[CODE_COLUMN]).reset_index(drop=True)
    months = _month_text(frame[MONTH_COLUMN]).reset_index(drop=True)
    listed = codes.ne("")
    known = checked.loc[checked[CODE_COLUMN].ne("")]
    lookup = known.drop_duplicates(CODE_COLUMN).set_index(CODE_COLUMN)[CUSTOM_COLUMN]
    attached = codes.map(lookup)
    not_found = listed & attached.isna()
    if bool(not_found.any()):
        _reject_missing_codes(frame, codes, months, not_found, words)
    values = attached.where(listed, CUSTOM_BLANK)
    result = _with_custom(frame, values)
    cells = _cell_differences(codes.loc[listed], months.loc[listed], known)
    one_side = cells[MAIN_ROWS_COLUMN].eq(0) | cells[CUSTOM_ROWS_COLUMN].eq(0)
    check = CustomSourceCheck(
        main_rows=len(frame),
        main_distinct_rows=len(frame) - int(frame.duplicated().sum()),
        custom_rows=int(checked[ROWS_COLUMN].sum()),
        kinds=int(values.loc[listed].nunique()),
        one_side_cells=int(one_side.sum()),
        count_mismatch_cells=int((~one_side).sum()),
        cells=cells,
    )
    return result, check


def custom_rows_of(frame: pd.DataFrame) -> pd.DataFrame:
    """CUSTOM 이 본 표 칸에 실려 온 원천(원천 CSV)을 CUSTOM 원천 표 답 꼴로 센다(칸
    `CUSTOM_SOURCE_COLUMNS`) — 그 답을 `attach_custom_values(..., words=FILE_WORDS)` 에 넣어 둘째
    표와 같은 판정을 지나게 한다.

    (Capa Code, 생산계획년월, CUSTOM) 마다 행 수이고 차례는 처음 나온 차례다. Capa Code · CUSTOM 의
    빈 값(NA)은 빈 글자로 채우고, 생산계획년월의 빈 값은 그대로 한 줄로 센다(`dropna=False`). 기본
    묶기는 빈 열쇠 줄을 버려, 한 부품에 값 든 줄과 빈 줄이 섞이면 빈 줄이 그 값으로 조용히 채워지고
    빈 줄만인 부품은 「없는 Capa Code」 라는 틀린 글로 멈춘다. 앞뒤 공백 · 대소문자는 여기서 접지
    않는다 — 검사(`check_custom_rows`)가 둘째 표 답과 같이 접는다. 세는 칸이 없으면 `ValueError` 다.
    """
    absent = [
        column
        for column in (CODE_COLUMN, MONTH_COLUMN, CUSTOM_COLUMN)
        if column not in frame.columns
    ]
    if absent:
        raise ValueError(f"본 표에 CUSTOM 을 셀 칸이 없습니다: {', '.join(absent)}")
    keys = pd.DataFrame(
        {
            CODE_COLUMN: frame[CODE_COLUMN].astype("string").fillna("").reset_index(drop=True),
            MONTH_COLUMN: frame[MONTH_COLUMN].reset_index(drop=True),
            CUSTOM_COLUMN: frame[CUSTOM_COLUMN].astype("string").fillna("").reset_index(drop=True),
        }
    )
    counted = keys.groupby([CODE_COLUMN, MONTH_COLUMN, CUSTOM_COLUMN], dropna=False, sort=False)
    return counted.size().rename(ROWS_COLUMN).reset_index().loc[:, list(CUSTOM_SOURCE_COLUMNS)]


def blank_custom_values(frame: pd.DataFrame) -> tuple[pd.DataFrame, CustomSourceCheck]:
    """끄개로 CUSTOM 원천 표를 묻지 않은 등록 — 본 표 CUSTOM 칸을 모두 빈 값 표지(`CUSTOM_BLANK`)로
    덮고 「붙이지 않음」 대조(`CustomSourceCheck.switched_off`)를 낸다.

    조회문 상수를 그대로 두지 않고 덮는다 — 0039 가 옛 행에 넣은 표지와 같은 글자라 「부품 구분
    없음」 을 글자 그대로 말한다. Capa Code · 생산계획년월 칸이 없어도 멈추지 않는다(맞댈 것이
    없다). 돌려주는 표는 받은 표의 사본이고 CUSTOM 칸만 다르다(`attach_custom_values` 와 같은 꼴 —
    받은 표의 CUSTOM 칸이 글자 dtype 이면 그 dtype 을 지킨다, 칸이 없으면 끝에 더한다).
    """
    values = pd.Series([CUSTOM_BLANK] * len(frame), dtype=object)
    return _with_custom(frame, values), CustomSourceCheck.switched_off(frame)


def _with_custom(frame: pd.DataFrame, values: pd.Series) -> pd.DataFrame:
    """`frame` 의 CUSTOM 칸을 차례로 맞댄 `values` 로 바꾼 사본 — 받은 칸이 글자 dtype 이면 그
    dtype 을, 아니면 object 다."""
    original = frame[CUSTOM_COLUMN] if CUSTOM_COLUMN in frame.columns else None
    dtype = (
        original.dtype
        if original is not None and pd.api.types.is_string_dtype(original.dtype)
        else object
    )
    column = pd.Series(values.to_numpy(dtype=object), index=frame.index).astype(dtype)
    return frame.assign(**{CUSTOM_COLUMN: column})


def _code_text(values: pd.Series) -> pd.Series:
    """Capa Code 를 맞댈 글자 — 앞뒤 공백만 떼고, 빈 값(NULL · 빈 글자 · 공백뿐)은 빈 글자다."""
    return values.astype("string").str.strip().fillna("")


def _month_text(values: pd.Series) -> pd.Series:
    """생산계획년월을 맞댈 글자 — 정수로 읽히는 값(`202611` · `202611.0` · `" 202611 "`)은 그
    정수의 글자, 그 밖의 글자는 앞뒤 공백만 뗀 그대로, 빈 값은 빈 글자다."""
    text = values.astype("string").str.strip()
    numeric = pd.to_numeric(text, errors="coerce")
    whole = numeric.notna() & numeric.mod(1).eq(0)
    as_integer = numeric.where(whole).astype("Int64").astype("string")
    return as_integer.where(whole, text).fillna("")


def _cell_differences(codes: pd.Series, months: pd.Series, known: pd.DataFrame) -> pd.DataFrame:
    """한쪽에만 있거나 행 수가 다른 (Capa Code, 생산계획년월) 칸 — 없는 쪽은 0행이다."""
    main = (
        pd.DataFrame({CODE_COLUMN: codes, MONTH_COLUMN: months})
        .groupby([CODE_COLUMN, MONTH_COLUMN])
        .size()
        .rename(MAIN_ROWS_COLUMN)
    )
    source = (
        known.groupby([CODE_COLUMN, MONTH_COLUMN])[ROWS_COLUMN].sum().rename(CUSTOM_ROWS_COLUMN)
    )
    joined = pd.concat([main, source], axis=1).fillna(0).astype("int64")
    differs = joined[MAIN_ROWS_COLUMN].ne(joined[CUSTOM_ROWS_COLUMN])
    return (
        joined.loc[differs]
        .rename_axis([CODE_COLUMN, MONTH_COLUMN])
        .reset_index()
        .sort_values([CODE_COLUMN, MONTH_COLUMN], kind="stable")
        .reset_index(drop=True)
        .loc[:, list(CELL_COLUMNS)]
    )


def _months_text(months: pd.Series) -> str:
    """달 예시 — 차례대로 `_MONTH_EXAMPLE_LIMIT` 개, 넘으면 「외 n개월」."""
    unique = sorted({month or "(빈 달)" for month in months.tolist()})
    shown = " · ".join(unique[:_MONTH_EXAMPLE_LIMIT])
    rest = len(unique) - _MONTH_EXAMPLE_LIMIT
    return f"{shown} 외 {rest:,}개월" if rest > 0 else shown


def _more_text(total: int) -> str:
    rest = total - CUSTOM_EXAMPLE_LIMIT
    return f" 외 {rest:,}종" if rest > 0 else ""


def _reject_several_values(listed: pd.DataFrame, words: CustomSourceWords) -> None:
    """한 Capa Code 에 빈 값이 아닌 CUSTOM 이 둘 이상이면 부품 · 값 · 달 예시와 함께 멈춘다."""
    filled = listed.loc[listed[CUSTOM_COLUMN].ne(CUSTOM_BLANK)]
    counts = filled.groupby(CODE_COLUMN)[CUSTOM_COLUMN].nunique()
    several = sorted(counts.index[counts.gt(1)].tolist())
    if not several:
        return
    shown = []
    for code in several[:CUSTOM_EXAMPLE_LIMIT]:
        rows = filled.loc[filled[CODE_COLUMN].eq(code)]
        parts = [
            f"`{value}` {_months_text(group[MONTH_COLUMN])}"
            for value, group in sorted(rows.groupby(CUSTOM_COLUMN), key=lambda item: str(item[0]))
        ]
        shown.append(f"`{code}`({' / '.join(parts)})")
    raise ValueError(
        f"{words.place}에서 한 Capa Code 에 CUSTOM 이 둘 이상이라 등록하지 않았습니다: "
        + ", ".join(shown)
        + _more_text(len(several))
        + f". 한 부품(Capa Code)의 CUSTOM 은 달마다 같아야 합니다 — {words.several_fix}"
    )


def _reject_blank_values(listed: pd.DataFrame, words: CustomSourceWords) -> None:
    """줄은 있는데 CUSTOM 이 빈 Capa Code 가 있으면 부품 · 달 예시와 함께 멈춘다."""
    blank = listed.loc[listed[CUSTOM_COLUMN].eq(CUSTOM_BLANK)]
    if blank.empty:
        return
    codes = sorted(blank[CODE_COLUMN].unique().tolist())
    shown = [
        f"`{code}` {_months_text(blank.loc[blank[CODE_COLUMN].eq(code), MONTH_COLUMN])}"
        for code in codes[:CUSTOM_EXAMPLE_LIMIT]
    ]
    raise ValueError(
        f"{words.place}에 CUSTOM 이 빈 Capa Code 가 있어 등록하지 않았습니다: "
        + ", ".join(shown)
        + _more_text(len(codes))
        + f" — {_MERGED_NOTE}"
    )


def _reject_missing_codes(
    frame: pd.DataFrame,
    codes: pd.Series,
    months: pd.Series,
    not_found: pd.Series,
    words: CustomSourceWords,
) -> None:
    """CUSTOM 원천 표에 없는 Capa Code 를 행 수가 많은 차례로 부품 · 행 · 달 예시와 함께 멈춘다.

    `codes` · `months` · `not_found` 는 받은 표와 같은 차례의 0 부터 index 다. 본 표에 계획 표지 칸
    (`계획기초정보여부`)이 있으면 그 가운데 계획 행 수도 싣는다.
    """
    missing = pd.DataFrame({CODE_COLUMN: codes, MONTH_COLUMN: months}).loc[not_found]
    has_plan = _PLAN_FLAG_COLUMN in frame.columns
    if has_plan:
        flags = frame[_PLAN_FLAG_COLUMN].astype("string").str.strip().reset_index(drop=True)
        missing["plan"] = flags.loc[not_found].eq("Y").fillna(False).astype(bool)
    counts = missing[CODE_COLUMN].value_counts()
    ordered = sorted(counts.items(), key=lambda item: (-int(item[1]), str(item[0])))
    shown = []
    for code, count in ordered[:CUSTOM_EXAMPLE_LIMIT]:
        rows = missing.loc[missing[CODE_COLUMN].eq(str(code))]
        size = f"{int(count):,}행"
        if has_plan:
            size = f"{size}(계획 {int(rows['plan'].sum()):,}행)"
        shown.append(f"`{code}` {size} {_months_text(rows[MONTH_COLUMN])}")
    raise ValueError(
        f"{words.place}에 없는 Capa Code 가 있어 등록하지 않았습니다: "
        + ", ".join(shown)
        + _more_text(len(ordered))
        + f" — {_MERGED_NOTE} {words.missing_fix}"
    )
