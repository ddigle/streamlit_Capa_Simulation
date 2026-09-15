# Purpose: Capa Chatbot 이 연결되면 어떤 모양으로 답하는지 보여 줄 대본과 근거 표를 만든다.

"""Chatbot 답변 대본.

LLM 을 붙이기 전에 정해야 할 것은 모델이 아니라 **답변의 모양**이다. 결론 한 줄, 근거 표,
쓴 조건과 산식, 못 하는 것. 이 네 칸이 비면 답이 그럴듯해도 쓸 수가 없다.

그래서 대본을 데이터로 둔다. 화면은 이 대본을 그리기만 하고, 연결할 때는 같은 네 칸을
LLM 응답으로 채우면 된다 — 화면을 다시 뜯지 않는다.

숫자는 `performance_actuals` 의 데모에서 나온다. Chatbot 만 다른 세계를 말하면 옆 화면과
대조해 보는 순간 신뢰를 잃는다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from capa_simulation.services.performance_actuals import (
    ALL_METRICS,
    EFFICIENCY_METRIC,
    build_gap_table,
    build_monthly_actual_demo,
    build_priority_table,
)


@dataclass(frozen=True)
class SampleAnswer:
    """답변 한 개. 네 칸이 모두 차야 답으로 친다."""

    question: str
    conclusion: str
    evidence: pd.DataFrame
    evidence_caption: str
    conditions: tuple[str, ...]
    limits: tuple[str, ...] = field(default_factory=tuple)


def build_sample_answers() -> list[SampleAnswer]:
    """추천 질문 네 개와 그 답. 순서는 실제로 묻게 되는 차례다.

    무엇이 나쁜가 → 왜 나쁜가 → 무엇부터 할까 → 데이터는 믿을 만한가.
    """
    monthly = build_monthly_actual_demo()
    months = sorted(int(value) for value in monthly["생산계획년월"].unique())
    window = f"{months[0] // 100 % 100:02d}.{months[0] % 100:02d}~{months[-1] % 100:02d}월"
    return [
        _shortfall_answer(monthly, window),
        _cause_answer(monthly, window),
        _priority_answer(monthly, window),
        _reference_answer(monthly, window),
    ]


def _shortfall_answer(monthly: pd.DataFrame, window: str) -> SampleAnswer:
    priority = build_priority_table(monthly, EFFICIENCY_METRIC, ["공정"])
    trouble = priority.loc[priority["상태"].ne("정상")]
    evidence = trouble[["공정", "기준 효율", "실적 효율", "Gap", "연속 미달", "상태"]].reset_index(
        drop=True
    )
    worst = trouble.iloc[0] if not trouble.empty else None
    conclusion = (
        f"{window} 기준으로 효율이 기준에 못 미치는 공정은 {len(trouble):,}개입니다. "
        f"가장 나쁜 곳은 **{worst['공정']}** 로 기간 평균 {float(worst['Gap']):.1%}p, "
        f"{int(worst['연속 미달'])}개월 연속 미달입니다."
        if worst is not None
        else f"{window} 기준으로 효율이 기준에 못 미치는 공정이 없습니다."
    )
    return SampleAnswer(
        question="이번 기간에 기준 미달인 공정 알려줘",
        conclusion=conclusion,
        evidence=evidence,
        evidence_caption="효율 실적 화면의 우선순위 표와 같은 값입니다.",
        conditions=(
            f"조회기간 {window} · 양산 구분 「양산」",
            "Gap = 실적 효율 − 기준 효율 (%p)",
            "상태 = 마지막 달 기준 연속 미달 개월 (0 정상 · 1~2 관찰 · 3 이상 개선 필요)",
        ),
        limits=("효율 한 지표만 본 답입니다. UPEH·수율은 다른 순서가 나옵니다.",),
    )


def _cause_answer(monthly: pd.DataFrame, window: str) -> SampleAnswer:
    rows: list[dict[str, object]] = []
    for metric in ALL_METRICS:
        priority = build_priority_table(monthly, metric, ["공정"])
        worst = priority.iloc[0]
        rows.append(
            {
                "지표": metric.name,
                "기준": float(worst[metric.standard_column]),
                "실적": float(worst[metric.actual_column]),
                "Gap": float(worst["Gap"]),
                "단위": metric.gap_unit,
                "공정": str(worst["공정"]),
            }
        )
    evidence = pd.DataFrame(rows)
    target = str(evidence["공정"].iloc[0])
    return SampleAnswer(
        question=f"{target} 은 왜 부족해?",
        conclusion=(
            f"**{target}** 은 효율·UPEH·수율 세 지표가 모두 기준을 밑돕니다. "
            "세 지표가 함께 내려가면 설비 한 대의 성능이 아니라 공정 조건이나 "
            "기준값 자체를 의심할 차례입니다."
        ),
        evidence=evidence[["지표", "기준", "실적", "Gap", "단위"]],
        evidence_caption="각 지표 화면의 우선순위 1위 행에서 그대로 가져왔습니다.",
        conditions=(
            f"조회기간 {window} · 공정 {target}",
            "효율·수율 Gap 은 %p, UPEH Gap 은 비율입니다",
            "비율은 월별 평균이 아니라 생산수량 가중으로 다시 계산했습니다",
        ),
        limits=(
            "원인을 **지목**한 것이 아니라 함께 내려간 지표를 보여 준 것입니다. "
            "설비·호기 단위 데이터가 붙으면 여기서 한 단계 더 좁힐 수 있습니다.",
        ),
    )


def _priority_answer(monthly: pd.DataFrame, window: str) -> SampleAnswer:
    priority = build_priority_table(monthly, EFFICIENCY_METRIC, ["공정"])
    evidence = priority[["우선순위", "공정", "Gap", "영향 비중", "연속 미달", "점수"]].head(5)
    return SampleAnswer(
        question="무엇부터 개선해야 해?",
        conclusion=(
            f"**{priority['공정'].iloc[0]}** 부터입니다. 미달폭만 보면 다른 공정이 더 "
            "나쁠 수 있지만, 영향 물량과 연속 미달 개월을 함께 곱하면 순서가 바뀝니다."
        ),
        evidence=evidence.reset_index(drop=True),
        evidence_caption="점수 = 미달폭 × 영향 비중 × 연속 미달 가중.",
        conditions=(
            f"조회기간 {window}",
            "영향 비중은 **PKG 환산 물량** 기준입니다 — WF 매와 CHIP Kea 를 그대로 더하면 "
            "단위 차이가 순위로 둔갑합니다",
        ),
        limits=("가중치는 실제 데이터 분포를 보고 확정해야 합니다.",),
    )


def _reference_answer(monthly: pd.DataFrame, window: str) -> SampleAnswer:
    products = build_gap_table(monthly, EFFICIENCY_METRIC, ["공정", "제품정보"])
    evidence = products.sort_values("Gap").head(5)[
        ["공정", "제품정보", "기준 효율", "실적 효율", "Gap", "영향 비중"]
    ]
    return SampleAnswer(
        question="제품까지 내려가면 어디가 문제야?",
        conclusion=(
            "제품 단위로 내리면 같은 공정 안에서도 갈립니다. 아래 다섯 줄이 미달폭이 "
            "가장 큰 조합이고, 공정 평균만 보면 가려지는 값입니다."
        ),
        evidence=evidence.rename(columns={"제품정보": "제품"}).reset_index(drop=True),
        evidence_caption="공정 × 제품 조합을 미달폭 순으로 다섯 줄만 잘랐습니다.",
        conditions=(
            f"조회기간 {window} · 공정 × 제품",
            "Stack·WF 속성까지 더 내려갈 수 있습니다",
        ),
        limits=("물량이 아주 작은 조합도 같은 줄에 섞입니다. 영향 비중을 함께 보세요.",),
    )
