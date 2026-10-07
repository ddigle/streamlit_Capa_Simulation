# Purpose: HOME Figure 캐시(묶음별 세션·세션 공용 칸)와 화면 렌더링·성능 표시를 담당한다.

"""Session and shared figure caches and rendering for the HOME dashboard."""

from __future__ import annotations

import html
import pickle
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Generic, NamedTuple, TypeVar, cast

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# 이름이 아니라 모듈을 잡는다. 이름을 직접 import 하면 테스트의 교체가 무시된다.
import capa_simulation.components.horizontal_scrollbar as horizontal_scrollbar
from capa_simulation.components.home_dimensions import (
    DASHBOARD_LABEL_COLUMN_WIDTH_PX,
    DASHBOARD_PANEL_TITLE_GAP_PX,
    DASHBOARD_SECTION_GAP_PX,
    DASHBOARD_TITLE_HEIGHT_PX,
)
from capa_simulation.components.home_preference import (
    SECTION_BAR_GAP_PX,
    SECTION_TITLE_FONT_PX,
    STATUS_LEGEND_CLASS,
    STATUS_LEGEND_ROW_KEY,
    render_section_title_row,
    section_accent_bar_css,
)
from capa_simulation.components.loading_progress import LoadingStage
from capa_simulation.components.plotly_layout import (
    hover_chart_config,
    static_chart_config,
)
from capa_simulation.components.scroll_shell import (
    horizontal_scroll_canvas,
    split_scroll_columns_style,
)
from capa_simulation.components.tab_state import OpenTab, tab_is_hidden
from capa_simulation.design import theme, tokens
from capa_simulation.io.reference_cache import HOME_FIGURE_CACHE_KEY
from capa_simulation.performance import PerformanceTrace
from capa_simulation.scenario_state import is_pristine_content_token
from capa_simulation.services.simulation_cache import shared_home_figure_store


class HomeFigureCacheKey(NamedTuple):
    """HOME 그림을 바꾸는 **화면 조건 전부**를 이름으로 적는다. 캐시 칸 이름은 이것이 아니다.

    페이지는 이 한 벌만 채우고, 캐시는 묶음마다 제 몫의 칸만 **같은 이름으로** 골라 만든
    키(`LobFigureKey` 등, `home_figure_key`)로 찾는다. 토글 하나가 닿지 않는 묶음까지 다시
    그리지 않으려는 것이다. 칸을 손으로 옮겨 적지 않으므로 이름이 어긋날 일이 없고, 여기 칸을
    더하면 어느 묶음이 읽는지 정해 그 키에도 같은 이름으로 넣어야 한다(`tests/
    test_home_figure_cache.py` 가 어느 묶음에도 없는 칸을 잡는다).

    내용은 편집 카운터가 아니라 `content_token` 으로 구분한다. 표시명은 계산 입력이
    아니라 라벨이므로 계산 캐시 대신 여기서만 버전을 본다. 비교 리비전과 주요공정은
    사용자가 고른 값이 아니라 **실제 그림에 적용된 값**이다.
    """

    schema_version: int
    process_label_version: int
    reference_version: int
    content_token: str
    start_month: int
    end_month: int
    display_order_digest: str
    included_processes: tuple[str, ...]
    # 판정 기준의 **내용 지문**(`SecurementThresholds.digest`) — 기본값과 월별 예외를 함께 담는다.
    # 프로필 version 만으로는 모자란다. 저장 전에는 version 이 0 에 머물지만 기본값은 최신
    # 공식버전 프리셋을 따라 바뀐다.
    threshold_digest: str
    include_edp: bool
    plan_detail_customer: bool
    comparison_revision_id: str
    show_advance: bool
    advance_profile_version: int
    show_execution: bool
    execution_profile_version: int
    top5_band_version: int
    top5_min_rate: float
    top5_max_rate: float
    past_profile_version: int
    key_processes: tuple[str, ...]
    key_process_profile_version: int
    # `제품별 비중` 행의 단위. 제품별 수량 자체는 위의 내용 토큰·기간·EDP·선행·과거 칸이 이미
    # 가른다 — 단위만 새로 갈린다.
    product_share_basis: str
    # 「선행 입고」 토글과 선행 입고 실적 프로필 version(토글이 꺼져 있으면 0). Density 칸 오른쪽
    # 끝 글자가 Figure 에 구워지므로 키에 든다 — Summary 공지와 다르다.
    show_advance_shipment: bool
    advance_shipment_profile_version: int
    # 주요공정 히트맵이 그릴 공정이 하나도 없을 때 남기는 한 줄. 프리셋이 비었는지(고르라)와
    # 프리셋의 공정이 이 화면에 없는지(없다)가 갈리는데, 둘 다 `key_processes` 가 `()` 라 그것만
    # 으로는 갈리지 않는다 — 프리셋만 바꿨을 때 앞 프리셋의 안내가 남았다.
    key_process_empty_notice: str
    # 월 축. 네 묶음이 모두 이 축 위에 그린다. 축은 계산 결과에서 나오므로(EDP 를 뺀 계획에는
    # EDP 만 있던 달이 없다, 과거 구간이 앞에 붙는다) 토글 값으로 짐작하지 않고 **축 자체**를
    # 넣는다. 과거·GAP 경계는 집합이라 정렬해 담는다.
    month_labels: tuple[str, ...]
    year_total_labels: tuple[str, ...]
    past_month_labels: tuple[str, ...]
    gap_month_labels: tuple[str, ...]

    @property
    def advance_ratio_includes_edp(self) -> bool:
        """선행 B/O 변동률이 EDP 를 넣은 계획에서 나왔나. 선행이 꺼져 있으면 늘 False 다.

        변동률은 **화면이 지금 쓰는 계획**(EDP 를 뺀 화면이면 뺀 계획)으로 내어 확보율에 곱한다
        (`build_advance_load_ratio`). 그래서 선행을 켜면 확보율 — 곧 주요공정 히트맵 — 이 EDP
        토글을 따라 움직이고, 끄면 움직이지 않는다. EDP 만 바꿀 때 히트맵을 다시 그리지 않으려고
        `include_edp` 를 그대로 넣지 않고 이렇게 접는다(`show_advance` 는 따로 키에 있다).
        """
        return self.include_edp and self.show_advance


# 묶음별 의존 표 — `app_pages/home.py` 의 프레임 흐름을 코드로 따라가 정했다. 줄일 때는 짐작이
# 아니라 그 흐름을 다시 따라가서 줄인다(틀린 그림은 느린 그림보다 나쁘다).
#
#   조건                          LOB  계획 세부수량  주요공정  상세 B/N
#   원천·기간·표시순서·과거·월 축   O    O             O         O     (1)
#   공정 표시명                    O    -             O         O     (2)
#   판정 기준                      O    -             O         O
#   B/N 집계 공정                  O    -             -         O     (3)
#   EDP 포함                       O    O             △         O     (4)
#   상세 계획(Customer)            -    O             -         -
#   GAP(실제로 붙은 비교 리비전)    O    O             -         -     (5)
#   선행 B/O                       O    -             O         O     (6)
#   실행 Loss                      O    -             O         O
#   Top 5 구간                     O    -             -         -
#   제품별 비중 단위               O    -             -         -
#   선행 입고                      O    -             -         -     (7)
#   주요공정 프리셋·빈 안내        -    -             O         -
#   테마                           네 묶음 모두 칸 이름 앞(`_themed_key`)
#
#   (1) 모든 프레임과 월 축. 계획 세부수량 묶음에는 비교 덤벨이 함께 든다.
#   (2) 세부수량·덤벨은 공정명을 쓰지 않는다.
#   (3) 순위 집계 입력. 히트맵은 B/N 집계 공정이 아니라 주요공정 목록을 그린다.
#   (4) 상세 B/N 의 Wafer Capa 는 Wafer 부하량 × 확보율이다. △ 는 선행 B/O 를 켰을 때만이다 —
#       변동률을 화면 계획(EDP 를 뺀 화면이면 뺀 계획)으로 내어 확보율에 곱한다
#       (`HomeFigureCacheKey.advance_ratio_includes_edp`).
#   (5) Density·Wafer 계획 증감, 세부수량 증감·덤벨. 비교 Density·Wafer 는 분류와 무관하다.
#   (6) Density·Wafer·확보율에 변동률을 건다. 세부수량에는 걸지 않는다.
#   (7) Density 칸 글자. 계산은 바꾸지 않는다.
#
# 「O」 칸을 「-」 로 바꾸면 그 조건을 바꿔도 옛 그림이 나온다. 반대로 「-」 를 「O」 로 바꾸는
# 것은 느려질 뿐 틀리지 않는다 — 확신이 서지 않으면 넓게 둔다.


class HomeFigureBaseKey(NamedTuple):
    """네 묶음이 모두 읽는 것 — 계산 원천·조회기간·표시순서·과거 구간과 그 위의 월 축."""

    schema_version: int
    reference_version: int
    content_token: str
    start_month: int
    end_month: int
    display_order_digest: str
    past_profile_version: int
    month_labels: tuple[str, ...]
    year_total_labels: tuple[str, ...]
    past_month_labels: tuple[str, ...]
    gap_month_labels: tuple[str, ...]


class LobFigureKey(NamedTuple):
    """`Capa LOB 현황` — 거의 모든 토글이 닿는다. 상세 계획·주요공정만 닿지 않는다."""

    base: HomeFigureBaseKey
    process_label_version: int
    threshold_digest: str
    included_processes: tuple[str, ...]
    include_edp: bool
    comparison_revision_id: str
    show_advance: bool
    advance_profile_version: int
    show_execution: bool
    execution_profile_version: int
    top5_band_version: int
    top5_min_rate: float
    top5_max_rate: float
    product_share_basis: str
    show_advance_shipment: bool
    advance_shipment_profile_version: int


class PlanDetailFigureKey(NamedTuple):
    """`계획 세부수량` 과 접힌 비교 덤벨 — 계획 세부수량과 비교 계획만 읽는다."""

    base: HomeFigureBaseKey
    include_edp: bool
    plan_detail_customer: bool
    comparison_revision_id: str


class KeyProcessFigureKey(NamedTuple):
    """`주요공정 확보율` 히트맵 — 최종 확보율과 고른 주요공정만 읽는다."""

    base: HomeFigureBaseKey
    process_label_version: int
    threshold_digest: str
    show_advance: bool
    advance_profile_version: int
    advance_ratio_includes_edp: bool
    show_execution: bool
    execution_profile_version: int
    key_processes: tuple[str, ...]
    key_process_profile_version: int
    key_process_empty_notice: str


class BottleneckFigureKey(NamedTuple):
    """`상세 B/N 공정` — B/N 순위(최종 확보율·집계 공정)와 그 달 Wafer 부하량을 읽는다."""

    base: HomeFigureBaseKey
    process_label_version: int
    threshold_digest: str
    included_processes: tuple[str, ...]
    include_edp: bool
    show_advance: bool
    advance_profile_version: int
    show_execution: bool
    execution_profile_version: int


class LobFigures(NamedTuple):
    labels: go.Figure
    months: go.Figure


class PlanDetailFigures(NamedTuple):
    labels: go.Figure
    months: go.Figure
    # 접힌 「시나리오 비교 · 차이 큰 분류」 덤벨. 비교가 붙지 않았거나 차이가 하나도 없으면
    # None 이다. 입력(세부수량·비교 세부수량·분류)이 이 묶음과 같아 함께 둔다 — 따로 두면 접혀
    # 있어도 회차마다 다시 만든다.
    comparison_dumbbell: go.Figure | None


class KeyProcessFigures(NamedTuple):
    labels: go.Figure
    months: go.Figure


class BottleneckFigures(NamedTuple):
    labels: go.Figure
    months: go.Figure


class HomeFigureSet(NamedTuple):
    """네 구획의 라벨·월 Figure 를 화면 순서대로 담는다. 네 묶음에서 한 벌로 모은 것이다."""

    lob_labels: go.Figure
    lob_months: go.Figure
    plan_detail_labels: go.Figure
    plan_detail_months: go.Figure
    key_process_labels: go.Figure
    key_process_months: go.Figure
    bottleneck_labels: go.Figure
    bottleneck_months: go.Figure


KeyT = TypeVar("KeyT", bound=tuple[Any, ...])
FiguresT = TypeVar("FiguresT", bound=tuple[Any, ...])


@dataclass(frozen=True)
class HomeFigureBundle(Generic[KeyT, FiguresT]):
    """따로 캐시하는 Figure 묶음 하나. `name` 은 세션·공용 칸 이름, `title` 은 성능 진단 표시다."""

    name: str
    title: str
    key_type: type[KeyT]
    figures_type: type[FiguresT]


LOB_FIGURES = HomeFigureBundle("lob", "LOB", LobFigureKey, LobFigures)
PLAN_DETAIL_FIGURES = HomeFigureBundle(
    "plan_detail", "계획 세부수량", PlanDetailFigureKey, PlanDetailFigures
)
KEY_PROCESS_FIGURES = HomeFigureBundle(
    "key_process", "주요공정", KeyProcessFigureKey, KeyProcessFigures
)
BOTTLENECK_FIGURES = HomeFigureBundle(
    "bottleneck", "상세 B/N", BottleneckFigureKey, BottleneckFigures
)
HOME_FIGURE_BUNDLES: tuple[HomeFigureBundle[Any, Any], ...] = (
    LOB_FIGURES,
    PLAN_DETAIL_FIGURES,
    KEY_PROCESS_FIGURES,
    BOTTLENECK_FIGURES,
)

# 세션 칸은 **묶음마다** 여덟이다. 키가 묶기 전 키의 일부만 고른 것이라 같은 여덟 칸이면 어느
# 묶음이든 적중이 묶기 전보다 줄지 않고(같은 조작 순서에서 LRU 거리가 늘지 않는다), 다 찼을 때
# 메모리도 묶기 전 여덟 벌과 같다. 객체 크기는 LOB 약 0.75MB·상세 B/N 0.26MB·주요공정 0.13MB·
# 계획 세부수량 0.08MB 로 한 벌 약 1.2MB, 묶음마다 여덟이면 세션당 약 10MB 다(70공정·32개월 로컬
# DB 사본의 샘플 관측). LOB 는 토글 일곱이 닿아 조합이 가장 많지만 가장 크기도 해 늘리지 않는다.
HOME_FIGURE_CACHE_MAX_ENTRIES = 8

# 캐시에 든 옛 그림을 버리게 하는 번호. 묶음 구조뿐 아니라 **그림 모양**(막대 폭·둥근 머리
# 처럼 Figure 에 구워지는 것)을 바꿀 때도 올린다. 편집 없는 리비전의 그림은 세션 공용
# 저장소에도 들어가고 그 토큰은 리비전에서 나온 고정값이라, 올리지 않으면 새 세션과 다른
# 사용자까지 옛 그림을 받는다. 42 는 이름 있는 묶음, 43 은 막대 둥근 머리·LOB 폭 70px,
# 44 는 `제품별 비중` 도넛 행과 `B/N Top 5` 구분 글자의 세로 가운데, 45 는 공용 칸에 Figure
# 대신 `to_dict()` 목록을 넣는 저장 형식, 46 은 기준과 같은 확보율의 색(확보)·선행 B/O 이름
# (`Density (선행 B/O 전)`)·선행 입고 실적 칸 글자, 47 은 그 글자의 자리(값과 같은 높이)·고정
# 크기·색, 48 은 묶음별 칸(네 묶음 + 계획 세부수량 묶음의 비교 덤벨), 49 는 덤벨이 과거 구간
# 달을 빼고 견줌.
HOME_FIGURE_SCHEMA_VERSION = 49

# 누적 퍼센트는 합성 시드 콜드 실행의 단계별 소요 시간 비율에서 잡았다. 차트 생성이
# 대부분을 쓰고 계산 파이프라인이 그 다음이다. 단계 수로 균등 분할하면 막대가 30% 까지
# 순식간에 찬 뒤 남은 구간에서 멈춰 선 것처럼 보인다.
HOME_LOADING_STAGES = (
    LoadingStage("기준정보와 활성 시나리오를 확인하는 중", 5),
    LoadingStage("Capa 를 계산하는 중", 25),
    LoadingStage("B/N 순위를 집계하는 중", 32),
    LoadingStage("차트를 그리는 중", 95),
    LoadingStage("화면에 전달하는 중", 100),
)


def home_figure_key(bundle: HomeFigureBundle[KeyT, Any], conditions: HomeFigureCacheKey) -> KeyT:
    """화면 조건에서 그 묶음이 읽는 칸만 **같은 이름으로** 골라 묶음 키를 만든다."""
    return _project(bundle.key_type, conditions)


def _project(key_type: type[KeyT], conditions: HomeFigureCacheKey) -> KeyT:
    fields: tuple[str, ...] = cast(Any, key_type)._fields
    values = [
        _project(HomeFigureBaseKey, conditions) if name == "base" else getattr(conditions, name)
        for name in fields
    ]
    return cast(Callable[..., KeyT], key_type)(*values)


# 캐시 칸은 **테마별로 갈린다.** Plotly Figure 는 색을 구워 넣으므로 밝은 테마에서 만든
# 그림을 어두운 테마가 쓰면 흰 배경에 밝은 회색 글자가 얹힌다.
#
# 테마가 바뀔 때 통째로 비우지 않고 키로 가르는 이유는 `st.context.theme.type` 이
# **믿을 수 없는 순간이 있기 때문**이다. Streamlit 문서가 「세션에서 앱이 처음 로드될 때」와
# 「사용자가 테마를 바꾼 직후」에는 값이 틀릴 수 있다고 적는다(배경색에서 추론하는 값이다).
# 이 앱의 테마 버튼은 `localStorage` 를 쓰고 새로고침하므로 **정확히 그 두 순간**에 걸린다.
# 비우는 방식이면 그때 잘못 읽은 테마로 만든 그림이 그대로 눌러앉지만, 키로 가르면 다음
# 실행에서 값이 바로잡히는 순간 칸이 달라져 저절로 다시 그린다.
ThemedFigureCacheKey = tuple[str, tuple[Any, ...]]


def home_figure_cache(
    bundle: HomeFigureBundle[Any, FiguresT],
) -> dict[ThemedFigureCacheKey, FiguresT]:
    """그 묶음의 세션 칸. 묶음 칸들은 세션 키 하나(`HOME_FIGURE_CACHE_KEY`) 아래에 모인다.

    한 키 아래 두는 것은 시나리오 전환(`_STALE_UI_KEYS`)·표시순서 교체가 그 키 하나를 지워
    네 묶음을 한꺼번에 버리기 때문이다.
    """
    root = st.session_state.get(HOME_FIGURE_CACHE_KEY)
    if not isinstance(root, dict) or not all(isinstance(name, str) for name in root):
        # 묶음을 가르기 전 모양(칸 이름이 (테마, 키) 튜플)이 남은 세션은 통째로 버린다. 그 칸들은
        # 어느 묶음의 LRU 에도 들지 않아 세션이 끝날 때까지 밀려나지 않는다.
        root = {}
        st.session_state[HOME_FIGURE_CACHE_KEY] = root
    return cast(dict[ThemedFigureCacheKey, FiguresT], root.setdefault(bundle.name, {}))


def latest_home_figure_key(cache_root: object, bundle: HomeFigureBundle[KeyT, Any]) -> KeyT | None:
    """세션 칸(`st.session_state[HOME_FIGURE_CACHE_KEY]`)에서 그 묶음이 가장 최근에 쓴 키.

    벤치마크가 「켠 토글이 그림에 실제로 적용됐나」를 보는 창구다. 꺼내 쓴 칸도 맨 뒤로 옮기므로
    (`take_home_figures`) 맨 뒤가 이번 회차에 화면에 나간 그림의 키다.
    """
    if not isinstance(cache_root, dict):
        return None
    entries = cache_root.get(bundle.name)
    if not isinstance(entries, dict) or not entries:
        return None
    _, key = next(reversed(entries))
    return cast(KeyT, key)


def _themed_key(key: tuple[Any, ...]) -> ThemedFigureCacheKey:
    """이 실행의 테마를 앞에 붙인 칸 이름. 그림을 만든 팔레트와 같은 값이다."""
    return (theme.current_mode(), key)


def take_home_figures(
    bundle: HomeFigureBundle[Any, FiguresT],
    conditions: HomeFigureCacheKey,
) -> FiguresT | None:
    """그 묶음의 그림을 꺼내면서 **가장 최근에 쓴 칸**으로 옮긴다.

    dict 는 넣은 차례만 기억한다. 꺼내 쓰기만 하면 차례가 그대로여서, 칸이 넘칠 때
    `store_home_figures` 가 방금 쓴 칸을 버린다. 토글 조합은 LOB 만 해도 백스물여덟 가지인데
    칸은 여덟이라 축출이 실제로 일어난다.
    """
    cache = home_figure_cache(bundle)
    themed = _themed_key(home_figure_key(bundle, conditions))
    figures = cache.pop(themed, None)
    if figures is None and is_pristine_content_token(conditions.content_token):
        # 세션 칸이 비었으면 다른 세션이 같은 리비전으로 만든 그림을 본다. 새로고침한
        # 세션이 Figure 생성을 건너뛴다. 세션 칸에도 넣어 같은 세션의 다음 실행은 복원도
        # 건너뛴다.
        blob = shared_home_figure_store(bundle.name).get(themed)
        if blob is not None:
            figures = _figures_from_blob(bundle, blob)
    if figures is not None:
        _remember(cache, themed, figures)
    return figures


def store_home_figures(
    bundle: HomeFigureBundle[Any, FiguresT],
    conditions: HomeFigureCacheKey,
    figures: FiguresT,
) -> None:
    cache = home_figure_cache(bundle)
    themed = _themed_key(home_figure_key(bundle, conditions))
    _remember(cache, themed, figures)
    # 편집 중인 세션의 그림은 남이 쓸 일이 없다. 공용 칸에 넣으면 남의 칸만 밀어낸다.
    if is_pristine_content_token(conditions.content_token):
        shared_home_figure_store(bundle.name).put(themed, _figures_to_blob(figures))


# 공용 칸의 값은 **바이트**다 — 객체를 그대로 나누면 한 세션이 꺼낸 Figure 를 고칠 때 남의
# 화면이 바뀐다. Figure 를 통째로 pickle 하면 꺼낼 때 `Figure(...)` 검증 생성자가 모든 속성을
# 다시 검사해 새 세션마다 그 비용을 치른다. 그래서 필드 차례대로 `to_dict()` 목록을 넣고,
# 꺼낼 때는 검증 없이 다시 세운다 — 넣은 dict 는 이미 검증을 마친 Figure 에서 나왔다. 없는
# 그림(비교가 없을 때의 덤벨)은 None 그대로 둔다.
# `_validate` 는 Plotly 의 **비공개** 인자다(`plotly>=5.24,<7` 고정). 인자가 사라지면
# `go.Figure` 가 모르는 속성으로 거절하므로 `tests/test_home_figure_cache.py` 의 공용 칸
# 왕복 테스트가 먼저 깨진다.
def _figures_to_blob(figures: tuple[Any, ...]) -> bytes:
    specs = [None if figure is None else figure.to_dict() for figure in figures]
    return pickle.dumps(specs, protocol=pickle.HIGHEST_PROTOCOL)


def _figures_from_blob(bundle: HomeFigureBundle[Any, FiguresT], blob: bytes) -> FiguresT:
    specs: list[dict[str, Any] | None] = pickle.loads(blob)
    fields: tuple[str, ...] = cast(Any, bundle.figures_type)._fields
    return cast(Callable[..., FiguresT], bundle.figures_type)(
        **{
            name: None if spec is None else go.Figure(spec, _validate=False)
            for name, spec in zip(fields, specs, strict=True)
        }
    )


def _remember(
    cache: dict[ThemedFigureCacheKey, FiguresT],
    themed: ThemedFigureCacheKey,
    figures: FiguresT,
) -> None:
    """가장 최근에 쓴 칸으로 넣고 넘치는 칸을 오래된 것부터 버린다."""
    cache.pop(themed, None)
    cache[themed] = figures
    while len(cache) > HOME_FIGURE_CACHE_MAX_ENTRIES:
        cache.pop(next(iter(cache)))


# 성능 진단 패널을 켜는 세션 키. 사이드바 토글이 아니다 — 개발용 계측 하나가 모든
# 사용자가 늘 보는 자리를 차지하지 않게 한다. 단계별 소요 시간의 정본은
# `scripts/benchmark_home.py` 이고, 화면에서 봐야 할 때 이 키를 세션에 직접 넣는다.
HOME_PERFORMANCE_KEY = "dashboard_show_performance"


def render_home_performance(
    trace: PerformanceTrace,
    *,
    rebuilt: Sequence[str],
    enabled: bool,
) -> None:
    """단계별 시간과 Figure 캐시 결과. `rebuilt` 는 이번 회차에 새로 만든 묶음의 표시 이름이다.

    한 줄 요약은 네 묶음이 모두 맞았을 때만 「적중」이고 하나라도 만들었으면 「생성」이다.
    어느 묶음을 만들었는지는 다음 줄이 적는다.
    """
    if not enabled:
        return
    with st.sidebar.expander("HOME 실행 시간", expanded=True):
        st.caption(f"Figure 캐시: {'생성' if rebuilt else '적중'}")
        if rebuilt:
            st.caption(f"새로 만든 묶음: {' · '.join(rebuilt)}")
        st.dataframe(
            pd.DataFrame(trace.rows()),
            hide_index=True,
            width="stretch",
        )


def dashboard_title_row_style() -> str:
    """네 구획 제목 줄과 그 짝인 빈 줄의 높이를 하나로 못박는다.

    위젯 기본 높이에 맡기면 브라우저 글꼴이나 Streamlit 판이 바뀔 때마다 두 칸이
    어긋난다. 네 제목이 같은 높이라야 제목과 표 사이 간격도 하나로 맞는다.

    **한 줄이라도 빠지면 그 아래 전부가 어긋난다.** 월 칸 스페이서는 여기서 44px 로
    못박히는데 라벨 칸 제목 줄은 CSS 가 없으면 Streamlit 기본 높이다 — 증상은 그
    구획이 아니라 **그 아래 구획**에서 먼저 보인다.
    """
    return f"""
    <style>
    .st-key-lob_title_row,
    .st-key-plan_detail_title_row,
    .st-key-plan_detail_title_spacer,
    .st-key-key_process_title_row,
    .st-key-key_process_title_spacer,
    .st-key-bottleneck_title_row,
    .st-key-bottleneck_title_spacer {{
        height: {DASHBOARD_TITLE_HEIGHT_PX}px;
        min-height: {DASHBOARD_TITLE_HEIGHT_PX}px;
        margin: 0;
    }}
    .st-key-lob_title_row,
    .st-key-plan_detail_title_row,
    .st-key-key_process_title_row,
    .st-key-bottleneck_title_row {{ align-items: center; }}
    /* 구분 칸의 세 제목 줄은 **넘쳐도 한 줄**이다(`section_title_markup` 이 말줄임한다). 그러려면
       줄부터 제목 글까지 모든 겹이 칸 폭 아래로 줄어들 수 있어야 한다 — flex 항목의 기본
       `min-width:auto` 가 한 겹이라도 남으면 제목이 칸 밖(월 칸 위)으로 삐져나간다. */
    .st-key-plan_detail_title_row,
    .st-key-key_process_title_row,
    .st-key-bottleneck_title_row {{ overflow: hidden; }}
    .st-key-plan_detail_title_row *,
    .st-key-key_process_title_row *,
    .st-key-bottleneck_title_row * {{ min-width: 0; max-width: 100%; }}
    /* 범례는 제목과 같은 줄의 오른쪽 끝이다. 아래 월 영역 위에 얹힌 가로
       스크롤바와 겹치지 않게 별도 블록으로 두지 않는다. */
    /* 범례는 제목 줄의 오른쪽 끝이다. `margin-left:auto` 를 받아야 하는 것은 **flex
       항목**이라 `.st-key-*` 한 겹 바깥의 래퍼를 겨냥한다 — 안쪽에 주면 형제가 자기
       자신뿐이라 아무 일도 일어나지 않는다(Admin 의 `order` 와 같은 함정). */
    [data-testid="stLayoutWrapper"]:has(> .st-key-{STATUS_LEGEND_ROW_KEY}) {{
        margin-left: auto;
        width: auto;
        flex: 0 0 auto;
        align-self: stretch;
    }}
    /* 색칩을 토글 글자와 **같은 눈높이**에 세운다. Streamlit 의 마크다운 칸은 높이를
       글줄에서 잡아 7.5px 로 주저앉고 그 위로 11px 칩이 삐져나가, 줄 가운데보다 7.5px
       아래에 앉아 있었다. 래퍼부터 마크다운 칸까지 높이를 물려 주고 각 단계에서 가운데로
       모은다. */
    .st-key-{STATUS_LEGEND_ROW_KEY},
    .st-key-{STATUS_LEGEND_ROW_KEY} [data-testid="stElementContainer"],
    .st-key-{STATUS_LEGEND_ROW_KEY} [data-testid="stMarkdown"],
    /* 이름 없는 emotion 한 겹. testid 가 없어 자식 선택자로 집는다 — 이 한 겹이 높이를
       4px 로 떨어뜨려 아래 문단이 그만큼 처져 있었다. */
    .st-key-{STATUS_LEGEND_ROW_KEY} [data-testid="stMarkdown"] > div,
    .st-key-{STATUS_LEGEND_ROW_KEY} [data-testid="stMarkdownContainer"],
    .st-key-{STATUS_LEGEND_ROW_KEY} .{STATUS_LEGEND_CLASS} {{
        display: flex;
        align-items: center;
        height: 100%;
        min-height: 0;
        /* 마크다운 칸은 문단 아래 여백을 음수 margin 으로 걷어낸다. 줄 안에 세울 때는
           그 음수가 그대로 아래로 미는 힘이 된다. */
        margin: 0;
    }}
    </style>
    """


SUMMARY_NOTICE_KEY = "home_summary_notice"


def summary_notice_style() -> str:
    """공지 상자를 다른 구획 제목과 같은 모양으로 맞춘다.

    `st.expander` 의 기본 제목은 본문 글씨 크기다. 그대로 두면 바로 아래 `Capa LOB 현황`
    보다 작아 두 상자가 다른 화면에서 온 것처럼 보인다. 제목 글자와 앞의 강조 막대를
    구획 제목(`section_title_markup`)과 **같은 상수**로 맞춘다. 막대를 `▍` 글자로 두면
    높이가 상속한 글자 크기를 따라가 이 상자(20px)에서만 크게 나왔다 — 사각형을 px 로
    그리면 어느 제목 옆에 놓아도 같다. 서체도 구획 제목과 같은 짝(`tokens.FONT_FAMILY_DISPLAY`
    700 — `components/typography.py`)이다. 구획 제목은 앱 전체 규칙이 `role="heading"` 으로 잡지만
    이 제목은 `st.expander` 의 `summary` 라 여기서 건다.

    **본문은 내용만큼 자란다.** 높이를 주거나 `overflow` 를 걸면 긴 공지가 잘려 스크롤
    안에 숨는데, 공지는 접힘을 펴는 순간 전부 보여야 하는 글이다.

    본문 글자는 본문 기본 크기의 1.5배다. 공지는 화면을 지나가며 읽는 글이 아니라 펴서
    읽는 글이라 대시보드 본문과 같은 크기면 눈에 들어오지 않는다. `em` 으로 두는 것은
    브라우저·사용자 배율을 그대로 따라가게 하려는 것이다 — px 로 박으면 확대했을 때만
    이 상자가 따라오지 않는다. 제목(20px)은 건드리지 않는다. 바로 아래 `Capa LOB 현황`
    과 같은 값이라 흔들면 두 상자가 다시 어긋난다.
    """
    return f"""
    <style>
    .st-key-{SUMMARY_NOTICE_KEY} [data-testid="stExpander"] summary p {{
        display: inline-flex;
        align-items: center;
        gap: {SECTION_BAR_GAP_PX}px;
        font-family: {tokens.FONT_FAMILY_DISPLAY};
        font-size: {SECTION_TITLE_FONT_PX}px;
        font-weight: 700;
        line-height: 1.2;
    }}
    .st-key-{SUMMARY_NOTICE_KEY} [data-testid="stExpander"] summary p::before {{
        content: "";
        {section_accent_bar_css()};
    }}
    /* 접힘 표시 꺾쇠를 감춘다. **여닫는 기능은 그대로다** — 아이콘만 숨기고 `summary`
       자체는 건드리지 않으므로 줄 어디를 눌러도 펴진다. 다른 세 구획 제목에는 없는
       글리프라 이 상자만 제목 옆에 군더더기가 하나 붙어 보였다. */
    .st-key-{SUMMARY_NOTICE_KEY} [data-testid="stExpander"] summary
        [data-testid="stIconMaterial"] {{
        display: none;
    }}
    /* **아이콘을 감싼 칸과 그 옆 간격까지 없앤다.** 아이콘만 숨기면 빈 칸과 flex 간격이
       그대로 남아 제목이 20px 오른쪽으로 밀린다 — 바로 아래 `Capa LOB 현황` 과 첫 글자가
       어긋나 두 상자가 계단처럼 보인다. */
    .st-key-{SUMMARY_NOTICE_KEY} [data-testid="stExpander"] summary
        span:has(> [data-testid="stIconMaterial"]) {{
        display: none;
    }}
    .st-key-{SUMMARY_NOTICE_KEY} [data-testid="stExpander"] summary > span {{
        gap: 0;
    }}
    /* 제목 첫 글자를 아래 대시보드 상자의 제목과 **같은 세로선**에 세운다. 두 상자는
       테두리 위치가 같으므로 안쪽 여백만 맞추면 된다(테두리 1px + 안쪽 14px). 줄 전체를
       눌러 여닫는다는 것은 손 모양 커서가 말한다. */
    .st-key-{SUMMARY_NOTICE_KEY} [data-testid="stExpander"] summary {{
        justify-content: flex-start;
        cursor: pointer;
        padding-left: 14px;
    }}
    .capa-summary-note {{
        margin: 0;
        font-size: 1.5em;
        white-space: pre-wrap;
        overflow-wrap: anywhere;
        overflow: visible;
        max-height: none;
        line-height: 1.65;
        color: {tokens.TEXT};
    }}
    </style>
    """


def render_summary_notice(note: str) -> None:
    """`Main` 탭 맨 위의 공지. 접힌 채로 열리고 내용이 없으면 아예 그리지 않는다.

    **Plotly 상자 밖**이다. 안에 두면 스크롤되는 월 영역과 폭을 나눠 가져 문구가 월 칸
    너비에 갇힌다.

    기본이 접힘인 이유는 이 화면의 주인공이 대시보드이기 때문이다. 공지가 펼친 채로
    뜨면 긴 글 하나가 차트를 화면 밖으로 밀어낸다.

    `st.expander` 를 쓰는 것은 펴고 접는 데 rerun 이 필요 없어서다. 버튼으로 만들면 누를
    때마다 HOME 전체가 다시 돌고, 그 비용을 문구 하나를 여닫는 데 치르게 된다.
    """
    if not note.strip():
        return
    st.html(summary_notice_style())
    with st.container(key=SUMMARY_NOTICE_KEY):
        with st.expander("Summary", expanded=False):
            # `st.markdown` 이 아니라 `st.html` 이다. 마크다운은 raw HTML 블록을
            # **빈 줄에서 끊으므로**(CommonMark block type 6), 문단을 나눈 공지의 둘째
            # 문단부터는 `<div>` 밖으로 나가 줄 앞의 `#`·`-` 가 제목과 목록으로 바뀐다.
            # `st.html` 은 파서를 거치지 않는다. `pre-wrap` 이 줄바꿈과 들여쓰기를 살리고
            # `html.escape` 가 태그를 막는다.
            st.html(f'<div class="capa-summary-note">{html.escape(note)}</div>')


@contextmanager
def home_dashboard_panel() -> Iterator[None]:
    """`Capa LOB 현황` 제목 줄과 여덟 Figure 를 함께 감싸는 테두리 상자.

    상자를 `render_home_figures` 안에서 열면 제목 줄만 상자 밖에 남는다. 제목 줄(제목·범례)은
    fragment 밖에서 그리므로 상자만 한 단계 위로 올리고 제목 줄과 Figure 를 나란히 받는다.
    보는 조건 토글은 제목 줄이 아니라 사이드바 `LOB 표시 조건` 카드다.

    `gap` 이 `DASHBOARD_SECTION_GAP_PX` 가 아닌 이유는 상수 주석에 적었다 — 라벨 캔버스가
    스크롤바 높이만큼 이미 내려와 있어 남는 몫만 여기서 준다.
    """
    st.html(dashboard_title_row_style())
    with st.container(border=True, key="home_dashboard_panel", gap=DASHBOARD_PANEL_TITLE_GAP_PX):
        yield


@st.fragment
def render_home_figures(
    figures: HomeFigureSet,
    month_labels: list[str],
    *,
    leading_past_month_count: int = 0,
    owner_tab: OpenTab | None = None,
    key_process_title: str = "주요공정 확보율",
) -> None:
    """대시보드 여덟 Figure. **숨은 탭에서는 그리지 않는다.**

    숨겨진 요소 안에서는 SVG 글자 폭 측정이 0 이라 `go.Table` 이 머리글을 셀 가운데에
    놓지 못하고, 상세 세 Figure 는 `staticPlot` 이라 탭을 열어도 다시 그리지 않는다.
    어긋난 머리글이 그대로 남는다.

    이 안에는 위젯이 없다 — 보는 조건은 사이드바 `LOB 표시 조건` 카드다. 테두리 상자는
    `home_dashboard_panel()` 이 한 단계 위에서 열어 제목 줄까지 함께 감싼다.
    """
    if tab_is_hidden(owner_tab):
        return
    visible_month_count = min(max(len(month_labels), 1), tokens.DASHBOARD_MONTH_SCROLL_THRESHOLD)

    # 구분 컬럼은 px 로 고정한다. 비율로 두면 창이 좁을 때 구획 제목이 잘리고, 조회
    # 월이 적을 때는 반대로 필요 이상 넓어진다. 비율은 CSS 적용 전 첫 그리기용이다.
    st.html(
        split_scroll_columns_style(
            label_key="production_lob_label_canvas",
            month_key="production_lob_month_region",
            label_width_px=DASHBOARD_LABEL_COLUMN_WIDTH_PX,
        )
    )
    label_column, month_column = st.columns(
        [
            DASHBOARD_LABEL_COLUMN_WIDTH_PX,
            visible_month_count * tokens.MONTH_COLUMN_WIDTH_PX,
        ],
        gap=None,
    )
    with label_column:
        with st.container(
            key="production_lob_label_canvas",
            gap=DASHBOARD_SECTION_GAP_PX,
        ):
            st.plotly_chart(
                figures.lob_labels,
                width="stretch",
                key="production_lob_labels",
                config=static_chart_config(),
            )
            # `계획 세부수량` 제목. 제목이 Plotly 주석으로 쓰던 자리를 그대로 받는다. 월 칸에도
            # 같은 높이의 빈 줄을 끼워야 행이 맞는다. 「상세 계획」 토글은 사이드바 조건 카드다.
            render_section_title_row("계획 세부수량", key="plan_detail_title_row")
            st.plotly_chart(
                figures.plan_detail_labels,
                width="stretch",
                key="production_detail_labels",
                config=static_chart_config(),
            )
            # `주요공정 확보율` 제목. 네 구획이 같은 줄 컴포넌트를 쓰므로 제목과 표
            # 사이 간격이 넷 다 같다.
            # 제목에 지금 보는 프리셋 이름을 단다 — 사이드바 카드가 접혀 있어도 무엇을 보는지 안다.
            render_section_title_row(key_process_title, key="key_process_title_row")
            st.plotly_chart(
                figures.key_process_labels,
                width="stretch",
                key="key_process_heatmap_labels",
                config=static_chart_config(),
            )
            render_section_title_row("상세 B/N 공정", key="bottleneck_title_row")
            st.plotly_chart(
                figures.bottleneck_labels,
                width="stretch",
                key="bottleneck_detail_labels",
                config=static_chart_config(),
            )
    with month_column:
        # 라벨 영역은 월 영역 위에 얹힌 스크롤바 높이만큼 내려야 행이 맞는다.
        # 아래 `render_horizontal_scrollbar` 와 **반드시 같은 값**을 읽는다.
        st.html(
            f"""
            <style>
            .st-key-production_lob_label_canvas {{
                padding-top: {tokens.SCROLLBAR_HEIGHT_PX}px;
            }}
            </style>
            """
        )
        with st.container(key="production_lob_month_region", gap=None):
            horizontal_scrollbar.render_horizontal_scrollbar(
                target_selector=".st-key-production_lob_month_scroll",
                height=tokens.SCROLLBAR_HEIGHT_PX,
                key="production_lob_custom_scrollbar",
                # 화면을 열면 **DB 계산 구간의 첫 달**이 왼쪽에 선다. 과거 구간은 앞에
                # 붙어 있으므로 그 칸 수만큼 지나야 한다 — 왼쪽 끝은 지난 이력이라
                # 화면을 열자마자 보이는 것이 계획이 아니게 된다.
                initial_offset_px=leading_past_month_count * tokens.MONTH_COLUMN_WIDTH_PX,
            )
            with horizontal_scroll_canvas(
                key="production_lob_month",
                content_width_px=len(month_labels) * tokens.MONTH_COLUMN_WIDTH_PX,
                hide_native_scrollbar=True,
                padding_bottom="0.25rem",
                gap=DASHBOARD_SECTION_GAP_PX,
            ):
                st.plotly_chart(
                    figures.lob_months,
                    width="stretch",
                    key="production_lob_months",
                    # 드래그 확대는 Figure 축의 `fixedrange` 와 `dragmode=False` 가 막는다.
                    # 여기서는 더블클릭 복귀와 축 손잡이를 함께 끈다 — 확대가 없는데 그
                    # 둘만 살아 있으면 누를 때마다 아무 일도 안 일어나는 조작이 된다.
                    # hover 는 그대로 살린다.
                    config={
                        "displayModeBar": False,
                        "responsive": True,
                        "doubleClick": False,
                        "showAxisDragHandles": False,
                        "scrollZoom": False,
                    },
                )
                # 라벨 칸의 제목 줄과 같은 높이로 비워 둔다. 두 칸의 자식 수와 높이가
                # 같아야 아래 표의 행이 맞는다. 높이를 주지 않으면 빈 컨테이너를
                # Streamlit 이 아예 그리지 않아 월 칸만 위로 올라붙는다.
                st.container(
                    key="plan_detail_title_spacer",
                    height=DASHBOARD_TITLE_HEIGHT_PX,
                    border=False,
                )
                st.plotly_chart(
                    figures.plan_detail_months,
                    width="stretch",
                    key="production_detail_months",
                    config=static_chart_config(),
                )
                # 라벨 칸의 `주요공정 확보율` 제목 줄과 짝이 되는 빈 줄.
                st.container(
                    key="key_process_title_spacer",
                    height=DASHBOARD_TITLE_HEIGHT_PX,
                    border=False,
                )
                # 히트맵은 hover 로 확보율·가용/필요대수를 읽는다. `staticPlot` 은 hover
                # 까지 끄므로 상세 B/N 월 Figure 와 같은 config 를 쓴다.
                st.plotly_chart(
                    figures.key_process_months,
                    width="stretch",
                    key="key_process_heatmap_months",
                    config=hover_chart_config(),
                )
                # 라벨 칸의 `상세 B/N 공정` 제목 줄과 짝이 되는 빈 줄.
                st.container(
                    key="bottleneck_title_spacer",
                    height=DASHBOARD_TITLE_HEIGHT_PX,
                    border=False,
                )
                # 상세 B/N 월 Figure 는 hover 를 쓰므로 `staticPlot` 을 빼 둔다.
                # 같은 캔버스의 상세 두 Figure 중 계획 세부수량 쪽은 켜져 있다.
                # `staticPlot` 은 hover 까지 함께 끈다. 빼면 `displayModeBar` 기본값이
                # "hover" 로, `doubleClick`·`showAxisDragHandles` 는 켜짐으로 돌아가므로
                # 셋을 직접 끈다. 드래그 확대는 Figure 축의 `fixedrange` 가 막는다.
                st.plotly_chart(
                    figures.bottleneck_months,
                    width="stretch",
                    key="bottleneck_detail_months",
                    config=hover_chart_config(),
                )
