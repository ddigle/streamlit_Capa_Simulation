# Purpose: 원천 Core Data의 78컬럼에서 RQ 파생에 쓰는 정규화된 작업 프레임을 만든다.

"""원천 Core Data의 78컬럼에서 RQ 파생에 쓰는 정규화된 작업 프레임을 만든다."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

import pandas as pd

from capa_simulation.io.core_data_source import (
    CoreDataContract,
    normalize_core_data,
)
from capa_simulation.services.frame_contracts import normalize_demand_basis
from capa_simulation.services.product_type import apply_edp_wf_division

ACTIVE_CORE_COLUMNS = (
    "제품타입",
    "U/PKG",
    "PKG1",
    "LOB Code",
    "Capa Code",
    "제품정보",
    "생산계획년월",
    "생산수량",
    "Stack",
    "Customer",
    "Pack Code",
    "CS",
    "D_EQ",
    "WF 구분",
    "구분_Chip",
    "구분_EQ",
    "Plan_Chip(K개)",
    "CHIP",
    "Net Die",
    "Month",
    "8H 환산 계획(K개)",
    "WF수(매)",
    "EQ(억Gb)",
    "계획기초정보여부",
    "Area_Name",
    "공정",
    "STEP_SEQ",
    "MCP_SEQ",
    "Para",
    "Step수",
    "CAPA_RUN_RATE",
    "소요기준",
    "RUN_DAY",
    "일 필요",
    "UPEH",
    "ST",
    "Lot 측정률",
    "WF측정률",
    "EDS_수율",
    "BE_수율",
    "CUM_수율",
    "GOOD_DIE",
    "TEST WF수(매)",
    "Shot Time",
    "Shot수",
    "Index Time",
    "모듈수",
    "Side반영률",
    "편중률",
    "설비보유",
    "설비대수변화관리",
    "설비대여평가",
    "설비대여평가항목",
    "설비대여평가DESC",
    "MCP_Chip_Ratio",
    "소요대수",
    "시뮬레이션 누락여부",
)


# 원천 `CS` 코드 → `양산구분`. 계산은 양산구분을 **양산·ER 두 값**으로만 본다(ER 은 제품 Mix·표준
# 목표 등에서 뺀다). **여기 없는 코드는 등록을 막는다**(`reject_unmapped_cs_codes`) — 새 코드를 어느
# 쪽으로 셀지는 업무 결정이라 조용히 한쪽으로 넣지 않는다. 사내 1월 시나리오에 새 코드 `CB` 가 와서
# 「RQ_PKG_PLAN 업무 키에 null 또는 빈값이 있습니다: 양산구분」으로만 막혔다(2026-09-30).
# 코드는 앞뒤 공백을 지우고 대문자로 맞춘 뒤 대조한다. **CS 가 빈 행은 막지 않고 파생에서 뺀다**
# (`derive_q_core_data` — 2026-10-27 사용자 결정). 코드가 없어 양산·ER 어느 쪽인지 정할 근거가 없고,
# 그 행 때문에 시나리오 전체를 저장하지 못했다.
#
# 코드를 더할 때 볼 것 둘. 원천에서 그 코드가 계획 행(`계획기초정보여부=Y`)에만 붙고 경로 행은 다른
# CS 면 부하가 `RQ_REQB`(키에 CS 가 있다)에 붙지 못해 「경로 없는 계획」으로 빠진다. `RQ_RUN_RATE`·
# `RQ_VITAL`·UPEH·측정률 키에는 CS 가 없어, 그 코드의 기준값이 고른 분류의 값과 다르면 충돌 보고서에
# 남고 원천 차례에 따라 한쪽 값으로 합쳐진다.
CS_PRODUCTION_CLASSES: Final[Mapping[str, str]] = MappingProxyType(
    {
        "MP": "양산",
        "CS": "양산",
        # 사내 1월 시나리오에 새로 온 코드. 양산으로 센다(2026-09-30 사용자 결정) — HOME 생산계획·
        # Density·표준 목표 Capa 에 들어가고, 효율·여유율은 같은 달·공정의 양산 값과 한 칸을 쓴다.
        "CB": "양산",
        "ER": "ER",
    }
)
# 오류문에 싣는 규칙 밖 코드 수. 코드 종류가 이보다 많으면 원천 매핑 자체가 틀렸을 공산이 크다.
UNMAPPED_CS_EXAMPLE_LIMIT: Final = 10


@dataclass(frozen=True)
class BlankCsDrop:
    """CS 가 비어 양산구분(양산·ER)을 정할 수 없어 파생에서 뺀 원천 행 수.

    `plan_rows` 는 그 가운데 계획 행(`계획기초정보여부 = Y` — PKG PLAN 에 실리는 행)이고 나머지는
    경로 행(`route_rows`)이다. `plans_missing_routes` 는 **남은** 계획 줄 가운데 뺀 경로 행 때문에
    경로 일부를 잃었을 수 있는 줄 수다(`_plan_lines_losing_routes`) — 계획 행을 하나도 빼지 않았어도
    소요대수가 줄 수 있고, 그 몫은 소요대수 밖 수요 경고에 잡히지 않을 수 있어 따로 센다. 등록
    결과 알림(`notice`)과 리비전 메모(`memo`)가 같은 수를 쓴다. 원천 스냅샷(typed raw)에는 받은
    행이 그대로 남는다 — 빼는 것은 RQ 표를 만드는 작업 프레임뿐이다.
    """

    rows: int = 0
    plan_rows: int = 0
    plans_missing_routes: int = 0

    @property
    def dropped(self) -> bool:
        return self.rows > 0

    @property
    def route_rows(self) -> int:
        """뺀 행 가운데 계획 행이 아닌 행(경로·기준정보 행) 수."""
        return self.rows - self.plan_rows

    def notice(self) -> str:
        """등록 결과 알림. 뺀 행이 없으면 빈 글."""
        if not self.dropped:
            return ""
        counts = f"계획 {self.plan_rows:,}행 · 경로 {self.route_rows:,}행"
        sentences = [
            f"CS 가 빈 행 {self.rows:,}개({counts})는 양산구분(양산·ER)을 정할 수 없어 빼고 "
            "저장했습니다."
        ]
        if self.plan_rows:
            sentences.append("뺀 계획 행의 생산수량은 부하량·소요대수에 들지 않습니다.")
        if self.plans_missing_routes:
            sentences.append(
                f"남은 계획 {self.plans_missing_routes:,}줄은 같은 달·제품의 경로 행이 함께 "
                "빠져, 그 경로 공정의 소요대수가 줄 수 있습니다 — 이 몫은 「소요대수에 들지 않은 "
                "수요」 경고에 잡히지 않을 수 있습니다."
            )
        sentences.append(
            "계산 표에서만 뺐고, 받은 원천 행(Admin Area 「원천 품질」)은 그대로 남습니다."
        )
        return " ".join(sentences)

    def memo(self) -> str:
        """리비전 메모에 붙이는 짧은 조각. 뺀 행이 없으면 빈 글."""
        if not self.dropped:
            return ""
        memo = (
            f"CS 빈 행 {self.rows:,}개(계획 {self.plan_rows:,}행 · 경로 {self.route_rows:,}행) 뺌"
        )
        if self.plans_missing_routes:
            memo = f"{memo} · 경로 일부 빠진 계획 {self.plans_missing_routes:,}줄"
        return memo


@dataclass(frozen=True)
class DerivedCoreData:
    """RQ 파생용 작업 프레임과 그 프레임에서 뺀 CS 빈 행 수."""

    frame: pd.DataFrame
    blank_cs: BlankCsDrop


def reject_unmapped_cs_codes(core: pd.DataFrame) -> None:
    """`CS_PRODUCTION_CLASSES` 에 없는 CS 코드가 있으면 코드별 행 수와 함께 막는다.

    막지 않으면 그 행의 양산구분이 비고, 첫 RQ 표의 업무 키 검사에서 「업무 키에 null 또는
    빈값이 있습니다: 양산구분」으로만 멈춰 어떤 코드 때문인지 알 길이 없었다(2026-09-30).
    `build_q_core_data` 를 거친 프레임을 받는다 — CS 가 빈 행은 거기서 이미 빠져, 여기 남는 것은
    대개 값이 있는데 규칙에 없는 코드뿐이다. 그래도 빈 CS 는 `(빈값)` 으로 적는다 — 파생을 거치지
    않은 프레임이 오면 코드 자리가 빈 문구가 된다. 계획 행(`계획기초정보여부 = Y`) 수를 따로 적는다
    — PKG PLAN 에 실리는 행이다.
    """
    unmapped = core["양산구분"].isna()
    if not bool(unmapped.any()):
        return
    codes = core.loc[unmapped, "CS"].astype("string").str.strip().fillna("").replace("", "(빈값)")
    plan = core.loc[unmapped, "계획기초정보여부"].astype("string").str.strip().eq("Y").fillna(False)
    counts = codes.value_counts()
    plan_counts = codes.loc[plan].value_counts()
    shown = [
        f"`{code}` {int(count):,}행(계획 {int(plan_counts.get(code, 0)):,}행)"
        for code, count in counts.head(UNMAPPED_CS_EXAMPLE_LIMIT).items()
    ]
    rest = len(counts) - len(shown)
    raise ValueError(
        "원천 CS 코드 중 양산구분(양산·ER) 규칙에 없는 값이 있습니다: "
        + ", ".join(shown)
        + (f" 외 {rest:,}종" if rest > 0 else "")
        + f". 규칙에 있는 코드는 {', '.join(CS_PRODUCTION_CLASSES)} 입니다. 새 코드를 양산·ER 중 "
        "어느 쪽으로 셀지 정해 사외에 알려 주세요 — 규칙에 더해야 등록할 수 있습니다."
    )


def _drop_blank_cs_rows(core: pd.DataFrame) -> tuple[pd.DataFrame, BlankCsDrop]:
    """CS 가 빈(NULL·빈 글자·공백뿐) 행을 빼고 그 수를 센다. 행 번호(index)는 그대로 둔다.

    index 를 다시 매기지 않는 까닭: 충돌 보고서의 `원천행번호` 가 이 프레임의 index 로 원천 행을
    가리킨다(`reference_conflicts`). CS 는 이미 앞뒤 공백을 지운 값을 받는다.

    모든 행이 비었거나, 계획 행이 있었는데 그 계획 행이 모두 비면 막는다 — 빼고 나면 저장할 행이나
    생산계획이 남지 않아 빈 시나리오가 된다.
    """
    blank = core["CS"].fillna("").eq("")
    if not bool(blank.any()):
        return core, BlankCsDrop()
    plan = core["계획기초정보여부"].eq("Y").fillna(False)
    dropped = BlankCsDrop(
        rows=int(blank.sum()),
        plan_rows=int((blank & plan).sum()),
        plans_missing_routes=_plan_lines_losing_routes(core, blank, plan),
    )
    if bool(blank.all()):
        raise ValueError(
            f"원천 {len(core):,}행의 CS 가 모두 비어 있어 양산구분(양산·ER)을 정할 수 없습니다 — "
            "빼고 나면 저장할 행이 없어 저장하지 않았습니다. 원천의 CS 칸을 확인하세요."
        )
    if bool(plan.any()) and not bool((plan & ~blank).any()):
        raise ValueError(
            f"계획 행(계획기초정보여부 = Y) {dropped.plan_rows:,}행의 CS 가 모두 비어 있어 "
            "양산구분(양산·ER)을 정할 수 없습니다 — 빼고 나면 생산계획이 남지 않아 저장하지 "
            "않았습니다. 원천의 CS 칸을 확인하세요."
        )
    return core.loc[~blank].copy(), dropped


# CS 가 빈 경로 행을 뺐을 때 남은 계획 줄이 그 경로를 잃었는지 맞대는 키. 계획 쪽은 `RQ_PKG_PLAN`
# 업무 키에서 CS·양산구분을 뺀 것이다 — 뺀 행에는 CS 가 없어 그 둘로는 어느 계획의 경로였는지 알 수
# 없다. 경로 쪽은 `RQ_REQB` 의 나머지 칸이다.
_ROUTE_OWNER_KEYS: Final = ("생산계획년월", "제품정보", "Stack", "Capa Code", "Customer")
_ROUTE_PATH_KEYS: Final = ("Area_Name", "공정", "소요기준", "WF 구분", "STEP_SEQ", "MCP_SEQ")


def _plan_lines_losing_routes(core: pd.DataFrame, blank: pd.Series, plan: pd.Series) -> int:
    """CS 가 빈 경로 행을 빼서 경로 일부를 잃었을 수 있는 **남은** 계획 줄(`RQ_PKG_PLAN` 키) 수.

    `RQ_REQB` 경로 키에는 CS 가 있어 CS 가 빈 경로 행은 어느 계획에도 닿지 못한다. 그 행과 같은
    달·제품정보·Stack·Capa Code·Customer 의 남은 계획이 같은 경로(Area·공정·소요기준·WF 구분·
    STEP·MCP)를 CS 가 있는 다른 행으로 갖지 않으면, 그 몫의 부하는 남은 경로에만 붙고 빠진 공정은
    그 몫 없이 계산된다. 그 소요기준·WF 구분의 경로가 하나도 남지 않으면 「그 소요기준·WF 구분 경로
    없음」(세지 않는 사유)이 된다 — 어느 쪽도 소요대수 밖 수요 경고(`required_exclusion_counts`)에
    잡히지 않을 수 있어 등록 때 센다. 계획 행을 하나도 빼지 않았어도 0 이 아닐 수 있다.

    「잃었을 수 있는」 까닭: 그 행이 원래 어느 CS 의 경로였는지는 원천만 안다. 그래서 같은 달·제품의
    남은 계획 줄마다 따로 맞대고, 그 줄이 같은 경로를 이미 가지면 세지 않는다. 행 단위 정규화
    (`제품정보`·`Area_Name`)를 거친 프레임을 받고, 계산처럼 앞뒤 공백·대소문자를 무시하며 소요기준은
    `WAFER` 를 `WF` 로 본다(`frame_contracts.duplicate_route_rows` 와 같은 꼴). `RQ_REQB` 처럼
    `Area_Name` 이 빈 행은 경로로 치지 않는다.
    """
    route = core["Area_Name"].astype("string").str.strip().fillna("").ne("")
    dropped_routes = blank & route
    if not bool(dropped_routes.any()):
        return 0
    owner = list(_ROUTE_OWNER_KEYS)
    path = list(_ROUTE_PATH_KEYS)
    # 뺀 경로 행의 제품만 맞대면 된다 — 큰 원천에서 열두 칸 글자 키를 모든 행에 만들지 않게 먼저
    # 거른다.
    products = core["제품정보"].astype("string").str.strip().str.casefold()
    related = products.isin(products.loc[dropped_routes].dropna().unique())
    keys = _route_match_keys(core.loc[related], [*owner, "CS", *path])
    lost_paths = keys.loc[dropped_routes[related], [*owner, *path]].drop_duplicates()
    plan_lines = keys.loc[(plan & ~blank)[related], [*owner, "CS"]].drop_duplicates()
    candidates = plan_lines.merge(lost_paths, on=owner)
    if candidates.empty:
        return 0
    kept_routes = keys.loc[(route & ~blank)[related], [*owner, "CS", *path]].drop_duplicates()
    matched = candidates.merge(kept_routes, how="left", on=[*owner, "CS", *path], indicator=True)
    missing = matched.loc[matched["_merge"].eq("left_only"), [*owner, "CS"]]
    return len(missing.drop_duplicates())


def _route_match_keys(core: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """경로 맞대기용 글자 키. NULL 과 빈 글자를 같은 빈값(빈 글자)으로 맞춰 병합 키에 NA 를 두지
    않는다."""
    keys = pd.DataFrame(index=core.index)
    for column in columns:
        values = core[column].astype("string").str.strip()
        if column == "소요기준":
            values = normalize_demand_basis(values)
        keys[column] = values.str.casefold().fillna("")
    return keys


def derive_q_core_data(
    source: pd.DataFrame,
    contract: CoreDataContract | None = None,
) -> DerivedCoreData:
    """`build_q_core_data` 와 같은 작업 프레임에 CS 가 비어 뺀 행 수를 함께 돌려준다.

    수는 계획 행·경로 행과 경로 일부 빠진 남은 계획 줄이다(`BlankCsDrop`). 등록 경로
    (`reference_transformer`)가 그 수를 결과 알림·리비전 메모로 올린다.
    """
    normalized = normalize_core_data(source, contract)
    core = normalized.loc[:, list(ACTIVE_CORE_COLUMNS)].copy()
    # `normalize_core_data` 가 붙인 attrs(원천 dtype 78항목)는 컬럼 프로파일이 원본에서 읽는다.
    # 파생 프레임까지 들고 가면 pandas 가 연산마다 `__finalize__` 에서 deepcopy 한다 —
    # RQ 16표를 만드는 동안 5만 6천 회. 여기서 비운다. 원본(normalized)은 건드리지 않는다.
    core.attrs = {}
    # CS 는 업무 키(RQ_PKG_PLAN·RQ_REQB)이기도 하다. 모든 표가 이 프레임에서 나오므로 여기서 한 번
    # 맞추면 표 사이 조인이 같은 값을 본다. 원천 스냅샷(typed raw)은 그대로 둔다.
    core["CS"] = core["CS"].astype("string").str.strip().str.upper()
    # 계획 행 표시. `RQ_PKG_PLAN` 이 `Y` 를 글자 그대로 고르므로 ` y ` 로 온 계획 행이 말없이 빠지지
    # 않게 여기서 맞춘다.
    core["계획기초정보여부"] = core["계획기초정보여부"].astype("string").str.strip().str.upper()
    # BigDataQuery can represent blanks in product names with underscores. Keep
    # the typed raw snapshot unchanged, but normalize the RQ business key before
    # any table is derived so every downstream join receives the same value.
    core["제품정보"] = (
        core["제품정보"]
        .str.replace("*_", " ", regex=False)
        .str.replace("_", " ", regex=False)
        .str.replace(r"\s+", " ", regex=True)
        .str.strip()
    )
    area_names = core["Area_Name"].astype("string").str.strip()
    normalized_areas = area_names.str.casefold()
    core["Area_Name"] = area_names
    core.loc[normalized_areas.eq("main").fillna(False), "Area_Name"] = "Main"
    core.loc[normalized_areas.eq("mi").fillna(False), "Area_Name"] = "MI"
    # CS 가 빈 행은 프레임 전체를 보는 정규화(가장 많이 쓰인 `WF 구분` 표기 고르기 등)보다 먼저
    # 뺀다 — 남는 행만으로 표기를 고르고 표를 만든다. 위 두 칸은 행마다 따로 바꾸는 정규화라 빼기
    # 전에 해도 남는 행의 값이 같고, 뺀 경로 행을 남은 계획과 같은 꼴로 맞대려고 먼저 한다.
    core, blank_cs = _drop_blank_cs_rows(core)
    core["양산구분"] = core["CS"].map(dict(CS_PRODUCTION_CLASSES)).astype("string")
    core["가용대수"] = core["설비보유"] - core["설비대여평가"]
    core["WF 구분"] = unify_case_variants(core["WF 구분"])
    # EDP-TSV 의 `Top` 을 `Top_e` 로 가른다. 원천에는 `Top_e` 가 없으므로 입력은 그대로
    # 받고 여기서 한 번만 바꾼다 — 아래로 내려가는 16개 RQ 표와 화면이 전부 같은 값을 본다.
    core = apply_edp_wf_division(core)
    return DerivedCoreData(frame=core, blank_cs=blank_cs)


def build_q_core_data(
    source: pd.DataFrame,
    contract: CoreDataContract | None = None,
) -> pd.DataFrame:
    """Q_Core_Data 의 형·활성 컬럼·파생 컬럼을 입힌 작업 프레임. CS 가 빈 행은 빠져 있다.

    뺀 행 수가 필요하면 `derive_q_core_data` 를 쓴다. 대조 스크립트도 이 함수를 지나므로 RQ 표와
    같은 행 집합을 본다.
    """
    return derive_q_core_data(source, contract).frame


def unify_case_variants(values: pd.Series) -> pd.Series:
    """대소문자·앞뒤 공백만 다른 표기를 한 표기로 맞춘다. 표기가 하나뿐인 값은 공백만 뗀다.

    `WF 구분` 을 맞대는 자리는 둘로 갈린다 — 부하량 ↔ `RQ_REQB`·수율·Chip 구성 조인은 글자
    그대로, Dummy·PKG Buffer 판정은 대소문자를 없애고(`match_key`) 본다. 원천 한 벌에 `Core` 와
    `CORE` 가 함께 오면 `RQ_CHIP_QTY` 가 두 줄이 되어 계획이 두 번 펼쳐지고, 한쪽 표기의 부하량은
    경로에 닿지 않는다. 그래서 파생 경계에서 **한 번** 맞춘다(16개 RQ 표가 모두 이 프레임에서
    나온다).

    계산 쪽 조인을 대소문자 무시로 바꾸지 않는 까닭: 이미 두 표기로 저장된 리비전에서는 같은 키가
    두 줄이 되어 `many_to_one` 검증이 계산 전체를 멈춘다. 그래서 그런 리비전은 표기마다 따로
    계산되고, 어긋남은 대개 경고 없이 지나간다.

    - 한 경로가 두 표기 행으로 있으면 두 행이 다 계산된다. PKG Buffer 는 `WF 구분` 없이 부하량이
      붙어 두 행이 같은 부하를 받고(그 경로의 소요대수가 두 배), CHIP·WF 는 부하량도 두 표기로
      날 때(Chip 구성·수율도 두 표기) 두 배다. 어느 목록에도 남지 않으므로
      `scripts/inspect_revision_calculations.py` 의 「겹친 경로 키」(`WF 구분` 대소문자 무시)가
      이 행을 센다 — 사내 런북 6-3 a.
    - 경로와 Chip 구성의 표기가 엇갈리면(`Core` 경로, `CORE` Chip 구성) 그 부하량은 경로에 닿지
      않는다. 그 소요기준·표기의 경로가 그 제품에 하나도 없으면 「경로 없는 계획」 가운데 세지 않는
      사유(「그 소요기준·WF 구분 경로 없음」)로 남아 건수·산출 결과 목록에 나오지 않는다.

    고르는 표기는 그 값 가운데 **가장 많이 쓰인 것**이고, 같으면 글자 차례가 앞인 것이다. 원천
    표기를 지어내지 않고(표시는 원천 그대로라는 `product_type` 규칙), 행 차례에도 기대지 않는다.
    """
    text = values.astype("string").str.strip()
    folded = text.str.casefold()
    spellings = (
        pd.DataFrame({"folded": folded, "text": text})
        .dropna()
        .value_counts()
        .rename("count")
        .reset_index()
    )
    if spellings["folded"].is_unique:
        return text
    chosen = spellings.sort_values(
        ["folded", "count", "text"], ascending=[True, False, True]
    ).drop_duplicates("folded")
    return folded.map(dict(zip(chosen["folded"], chosen["text"], strict=True))).astype("string")
