# Purpose: 검수용 합성 샘플의 78컬럼 Core Data 원천(계획 행 + 공정 경로 행)을 원천판별로 만든다.
"""78컬럼 Core Data 빌더(검수용 합성 샘플).

제품 8(HBM Buffer·Core·Top·Dummy, EDP TOP·Master·Slave), 변형(Capa Code × Customer × CS ×
Pack Code × Stack) 2~3개, 변형별 경로, TC Bonding Core 의 둘째 STEP, 원천판(W36·W40·W43·W44·
HYBRID), W44 quirk 9종. UPEH(Main)·ST(MI, 분)는 환산 UPEH(= 60 ÷ ST, CHIP·PKG 는 ÷ 1000)에서
거꾸로 내고, 환산 UPEH 는 `upeh_scale[(달, 공정)]` × 제품·WF 구분별 고정 편차(0.94~1.06) × STEP
배수다 — 보정(`review_sample_sim.calibrate`)이 `upeh_scale` 만 바꾼다.

앱 패키지는 `load_core_data_contract` 하나만 쓴다(컬럼 목록).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Final

import pandas as pd
import review_sample_story as story

from capa_simulation.io.core_data_source import load_core_data_contract

EquipmentPlan = Mapping[tuple[int, str], tuple[float, float]]
UpehScale = Mapping[tuple[int, str], float]
VARIANTS: Final = ("W36", "W40", "W43", "W44", "HYBRID")
QUIRK_VARIANTS: Final = frozenset({"W43", "W44", "HYBRID"})
PLACEHOLDER_EQUIPMENT: Final = (999.0, 0.0)
ER_RUN_RATE_FACTOR: Final = 0.85


def _columns() -> list[str]:
    return [column.name for column in load_core_data_contract().columns]


def production_class(cs: str) -> str:
    return "ER" if cs == "ER" else "양산"


def route_factor(process: str, product: str, stack: str, division: str) -> float:
    """제품·WF 구분별 고정 UPEH 편차(0.94~1.06) — 달·변형과 무관(업무 키 충돌 없음)."""
    return 0.94 + 0.12 * story.stable_fraction("upeh", process, product, stack, division)


def process_divisions(process: story.Process, product: story.Product) -> tuple[str, ...]:
    if product.product_type == story.EDP:
        return process.edp_divisions
    return process.hbm_divisions


def process_steps(process: story.Process, division: str) -> tuple[tuple[str, str, float], ...]:
    """(STEP_SEQ, MCP_SEQ, 환산 UPEH 배수)."""
    return ((story.step_seq(process), "1A", 1.0), *process.extra_steps.get(division, ()))


def plan_quantity(
    product: story.Product, variant: story.Variant, month: int, scale: float
) -> float:
    """K PKG = 투입 Wafer × 비중 × 변형 몫 × Net Die × EDS × BE ÷ CHIP."""
    active = [item for item in product.variants if item.start <= month <= item.end]
    if variant not in active:
        return 0.0
    weight = variant.weight / sum(item.weight for item in active)
    chips = story.chip_count(product, variant.stack)
    return (
        story.wafer_k(month)
        * story.product_share(product.name, month)
        * weight
        * product.net_die
        * product.eds
        * product.be
        / chips
        * scale
    )


class _Builder:
    def __init__(
        self,
        variant: str,
        equipment: EquipmentPlan,
        upeh_scale: UpehScale,
        months: Iterable[int] | None,
    ) -> None:
        if variant not in VARIANTS:
            raise ValueError(f"모르는 원천판: {variant}")
        self.variant = variant
        self.spec = story.SOURCES[variant]
        self.equipment = equipment
        self.upeh_scale = upeh_scale
        self.months: tuple[int, ...] = (
            story.months_between(self.spec.first_month, 202812) if months is None else tuple(months)
        )
        self.columns = _columns()
        self.rows: list[dict[str, object]] = []
        self.quirks = variant in QUIRK_VARIANTS
        self.processes: tuple[story.Process, ...] = story.PROCESSES + (
            (story.HYBRID_PROCESS,) if variant == "HYBRID" else ()
        )

    # ------------------------------------------------------------------ 계획
    def product_scale(self, product: story.Product) -> float:
        scale = self.spec.plan_scale
        if self.variant == "W40":
            scale *= story.W40_PRODUCT_FACTORS.get(product.name, 1.0)
        return scale

    def yields(self, product: story.Product, month: int) -> tuple[float | None, float | None]:
        eds: float | None = product.eds
        be: float | None = product.be
        if self.quirks:
            if (product.name, month) == story.QUIRK_NO_YIELD:
                return None, None
            if (product.name, month) == story.QUIRK_BLANK_EDS:
                eds = None
        return eds, be

    def build(self) -> pd.DataFrame:
        for month in self.months:
            for product_no, product in enumerate(story.PRODUCTS, start=1):
                if product.name == story.NEW_PRODUCT and not self.spec.with_new_product:
                    continue
                self._product_month(product_no, product, month)
            if self.quirks:
                self._quirk_lines(month)
        return pd.DataFrame(self.rows, columns=self.columns)

    def _product_month(self, product_no: int, product: story.Product, month: int) -> None:
        for variant_no, variant in enumerate(product.variants, start=1):
            if not variant.start <= month <= variant.end:
                continue
            quantity = plan_quantity(product, variant, month, self.product_scale(product))
            discontinued = product.name == story.DISCONTINUED_PRODUCT and (
                month > story.DISCONTINUED_LAST_MONTH
            )
            if discontinued:
                # 단종 뒤로는 첫 변형만 0(계획 없음) 줄로 남는다 — W44 는 28.11·28.12 를 빈칸으로.
                if variant_no != 1:
                    continue
                blank = self.quirks and month in story.QUIRK_BLANK_QUANTITY[1]
                self._plan_lines(
                    product_no,
                    variant_no,
                    product,
                    variant,
                    month,
                    None if blank else 0.0,
                    with_routes=False,
                )
                continue
            self._plan_lines(product_no, variant_no, product, variant, month, quantity)
        if self.quirks and (product.name, month) == story.QUIRK_BLANK_CS:
            # CS 빈 계획 1줄 + 그 경로 — 파생에서 빠진다(BDQ 메모 「CS 빈 행 n개 뺌」).
            base = product.variants[0]
            blank_cs = story.Variant("DEMO-CAPA-06", "DEMO_CUST-4", "", "PK-D3", base.stack, 0.0)
            quantity = 0.04 * plan_quantity(product, base, month, self.product_scale(product))
            self._plan_lines(product_no, 9, product, blank_cs, month, quantity)

    def _quirk_lines(self, month: int) -> None:
        name, customer, months = story.QUIRK_MISMATCH_CUSTOMER
        if month in months:
            product = story.PRODUCT_BY_NAME[name]
            variant = story.Variant("DEMO-CAPA-04", customer, "MP", "PK-A1", "12H", 0.0)
            self._plan_lines(31, 8, product, variant, month, 3.2, with_routes=False)
        unknown, unknown_month = story.QUIRK_UNKNOWN_PRODUCT
        if month == unknown_month:
            product = story.Product(
                unknown,
                story.HBM,
                16,
                600,
                540,
                0.85,
                0.93,
                (story.Variant("DEMO-CAPA-99", "DEMO_CUST-5", "ER", "PK-X1", "8H", 1.0),),
            )
            self._plan_lines(32, 1, product, product.variants[0], month, 2.0, with_routes=False)

    def _common(
        self,
        product: story.Product,
        variant: story.Variant,
        month: int,
        quantity: float | None,
        division: str,
        chips: int,
        net_die: int,
        gb: int | None,
    ) -> dict[str, object]:
        eds, be = self.yields(product, month)
        height = story.stack_height(variant.stack)
        row: dict[str, object] = dict.fromkeys(self.columns, pd.NA)
        plan = 0.0 if quantity is None else quantity
        row.update(
            {
                "기준정보년월": month,
                "제품타입": product.product_type,
                "U/PKG": "HBM" if product.product_type == story.HBM else "TSV",
                "UsreFamily3": "HBM" if product.product_type == story.HBM else "EDP",
                "PKG1": "PKG-S",
                "SITE": "DEMO-SITE",
                "Area Class": "PKG",
                "Module/comp": "COMP",
                "LOB Code": product.lob,
                "PKG Part No": f"{variant.capa_code}-P",
                "Capa Code": variant.capa_code,
                "제품정보": product.name,
                "생산계획년월": month,
                "생산수량": pd.NA if quantity is None else round(quantity, 4),
                "Stack": variant.stack,
                "Customer": variant.customer,
                "Pack Code": variant.pack_code,
                "S/H": "*",
                "CS": variant.cs if variant.cs else pd.NA,
                "D_EQ": height * product.gb_per_chip,
                "WF 구분": division,
                "구분_Chip": chips,
                "구분_EQ": pd.NA if gb is None else gb,
                "Chip수": story.chip_count(product, variant.stack),
                "Plan_Chip(K개)": round(plan * chips, 4),
                "CHIP": story.chip_count(product, variant.stack),
                "Net Die": net_die,
                "Month": month % 10000,
                "계획(K개)": round(plan, 4),
                "8H 환산 계획(K개)": round(plan * height / 8, 4),
                "WF수(매)": round(plan * 1000 * chips / net_die, 3),
                "EQ(억Gb)": pd.NA if gb is None else round(plan * chips * gb / 1e5, 5),
                "누락여부": "N",
                "EDS_수율": pd.NA if eds is None else eds,
                "BE_수율": pd.NA if be is None else be,
                "CUM_수율": pd.NA if eds is None or be is None else round(eds * be, 6),
                "시뮬레이션 누락여부": "N",
                "CUSTOM": "ST_DEMO",
                "BONDING": "TC",
            }
        )
        return row

    def _plan_lines(
        self,
        product_no: int,
        variant_no: int,
        product: story.Product,
        variant: story.Variant,
        month: int,
        quantity: float | None,
        *,
        with_routes: bool = True,
    ) -> None:
        code = self.spec.code
        plan_id = f"{code}-P{month}-{product_no:02d}{variant_no}"
        for division, chips, net_die, gb in story.divisions(product, variant.stack):
            common = self._common(product, variant, month, quantity, division, chips, net_die, gb)
            plan_row = dict(common)
            plan_row.update(
                {
                    "시뮬레이션 ID": f"{plan_id}-{division}",
                    "PLAN ID": plan_id,
                    "계획기초정보여부": "Y",
                }
            )
            self.rows.append(plan_row)
            if not with_routes:
                continue
            for process_no, process in enumerate(self.processes, start=1):
                if division not in process_divisions(process, product):
                    continue
                if process.name == story.HYBRID_PROCESS.name and (
                    product.name not in story.HYBRID_PRODUCTS or month < story.HYBRID_START
                ):
                    continue
                for step, mcp, step_factor in process_steps(process, division):
                    self.rows.append(
                        self._route_row(
                            common,
                            plan_id,
                            process_no,
                            process,
                            product,
                            variant,
                            month,
                            division,
                            step,
                            mcp,
                            step_factor,
                        )
                    )

    def _route_row(
        self,
        common: dict[str, object],
        plan_id: str,
        process_no: int,
        process: story.Process,
        product: story.Product,
        variant: story.Variant,
        month: int,
        division: str,
        step: str,
        mcp: str,
        step_factor: float,
    ) -> dict[str, object]:
        converted = (
            self.upeh_scale.get((month, process.name), 1.0)
            * route_factor(process.name, product.name, variant.stack, division)
            * step_factor
        )
        per_kea = process.basis in ("CHIP", "PKG")
        if self.quirks and (product.name, process.name) == story.QUIRK_ZERO_UPEH:
            converted = 0.0
        upeh: object = pd.NA
        standard_time: object = pd.NA
        if process.area == "Main":
            upeh = round(converted * (1000.0 if per_kea else 1.0), 6)
        else:
            standard_time = (0.06 if per_kea else 60.0) / converted
        er = production_class(variant.cs) == "ER"
        run_rate = process.run_rate * (ER_RUN_RATE_FACTOR if er else 1.0)
        if self.quirks and er and process.name == story.QUIRK_ZERO_ER_RUN_RATE:
            run_rate = 0.0
        run_rate_value: object = round(run_rate, 4)
        if self.variant == "W43" and (month, process.name) == story.W43_BLANK_RUN_RATE:
            run_rate_value = pd.NA
        owned, lent = self.equipment.get((month, process.name), PLACEHOLDER_EQUIPMENT)
        row = dict(common)
        row.update(
            {
                "시뮬레이션 ID": f"{plan_id}-{division}-{process_no:02d}{step[-1]}",
                "PLAN ID": plan_id,
                "계획기초정보여부": "N",
                "FAB": "PKG",
                "Area_Name": process.area,
                "공정": process.name,
                "메이커": f"DEMO-MAKER-{'ABCD'[process_no % 4]}",
                "STEP_SEQ": step,
                "MCP_SEQ": mcp,
                "모델명": f"DEMO-MDL-{process_no:02d}",
                "Para": "1",
                "Step수": "1",
                "CAPA_RUN_RATE": run_rate_value,
                "소요기준": process.basis,
                "RUN_DAY": story.run_day(month),
                "UPEH": upeh,
                "ST": standard_time,
                "Lot 측정률": process.lot_ratio,
                "WF측정률": process.wf_ratio,
                "모듈수": process.modules,
                "Side반영률": 1,
                "편중률": process.vital,
                "설비보유": round(float(owned), 3),
                "설비대수변화관리": "0",
                "설비대여평가": round(float(lent), 3),
                "설비대여평가항목": "DEMO 정기",
                "설비대여평가DESC": "개발 대여" if lent > 1 else "DEMO 합성",
                "MCP_Chip_Ratio": 1,
            }
        )
        return row


def build_core_frame(
    variant: str,
    equipment: EquipmentPlan,
    upeh_scale: UpehScale,
    *,
    months: Iterable[int] | None = None,
) -> pd.DataFrame:
    """원천판 하나의 78컬럼 Core Data. `months` 를 주면 그 달만(보정용 — 원천판 첫 달 제한 없음)."""
    return _Builder(variant, equipment, upeh_scale, months).build()
