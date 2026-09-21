# Purpose: HOME Figure 가족 네 모듈이 내보내는 이름을 한 자리에 모아 다시 내보낸다.

"""HOME Figure 의 import 파사드.

Figure 생성 코드는 가족별로 나뉘어 있다 — `home_lob_figures`(요약 LOB),
`home_plan_detail_figures`(계획 세부수량), `home_key_process_figures`(주요공정 히트맵),
`home_bottleneck_figures`(상세 B/N)이고, 넷을 넘나드는 조각은 `home_figure_common` 이다.

**이 모듈은 코드를 갖지 않는다.** 페이지와 테스트가 부르는 이름을 한 자리에 모아 두어,
가족 모듈이 더 쪼개지거나 이름이 옮겨 다녀도 부르는 쪽이 따라 고쳐지지 않게 한다.
"""

from __future__ import annotations

from capa_simulation.components.home_bottleneck_figures import (
    BOTTLENECK_DETAIL_RANK_LIMIT as BOTTLENECK_DETAIL_RANK_LIMIT,
)
from capa_simulation.components.home_bottleneck_figures import (
    BOTTLENECK_NAME_INSET_RATIO as BOTTLENECK_NAME_INSET_RATIO,
)
from capa_simulation.components.home_bottleneck_figures import (
    BOTTLENECK_NAME_MIN_FONT_PX as BOTTLENECK_NAME_MIN_FONT_PX,
)
from capa_simulation.components.home_bottleneck_figures import (
    bottleneck_bar_ratio as bottleneck_bar_ratio,
)
from capa_simulation.components.home_bottleneck_figures import (
    bottleneck_name_layout as bottleneck_name_layout,
)
from capa_simulation.components.home_bottleneck_figures import (
    build_bottleneck_detail_figures as build_bottleneck_detail_figures,
)
from capa_simulation.components.home_bottleneck_figures import (
    format_bottleneck_process_name as format_bottleneck_process_name,
)
from capa_simulation.components.home_figure_common import (
    BOTTLENECK_NAME_ELLIPSIS as BOTTLENECK_NAME_ELLIPSIS,
)
from capa_simulation.components.home_figure_common import (
    capacity_status as capacity_status,
)
from capa_simulation.components.home_key_process_figures import (
    KEY_PROCESS_EMPTY_NOTICE as KEY_PROCESS_EMPTY_NOTICE,
)
from capa_simulation.components.home_key_process_figures import (
    build_key_process_heatmap_figures as build_key_process_heatmap_figures,
)
from capa_simulation.components.home_lob_figures import (
    ExecutionDeltaBars as ExecutionDeltaBars,
)
from capa_simulation.components.home_lob_figures import (
    build_execution_delta_bars as build_execution_delta_bars,
)
from capa_simulation.components.home_lob_figures import (
    build_lob_summary_figures as build_lob_summary_figures,
)
from capa_simulation.components.home_plan_detail_figures import (
    build_plan_detail_figures as build_plan_detail_figures,
)

__all__ = [
    "BOTTLENECK_DETAIL_RANK_LIMIT",
    "BOTTLENECK_NAME_ELLIPSIS",
    "BOTTLENECK_NAME_INSET_RATIO",
    "BOTTLENECK_NAME_MIN_FONT_PX",
    "ExecutionDeltaBars",
    "KEY_PROCESS_EMPTY_NOTICE",
    "bottleneck_bar_ratio",
    "bottleneck_name_layout",
    "build_bottleneck_detail_figures",
    "build_execution_delta_bars",
    "build_key_process_heatmap_figures",
    "build_lob_summary_figures",
    "build_plan_detail_figures",
    "capacity_status",
    "format_bottleneck_process_name",
]
