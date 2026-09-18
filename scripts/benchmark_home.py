# Purpose: Measure cold, warm, and per-toggle HOME Python reruns without exposing source data.

"""HOME 의 파이썬 rerun 시간을 단계별로 잰다.

**세션 키는 화면이 실제로 읽는 이름이어야 한다.** 예전에는 아무도 읽지 않는
`dashboard_show_details` 를 심어 두고 「상세」 단계를 잰다고 적었다. 그 단계는 직전 단계와
같은 화면을 한 번 더 그린 것이라 늘 캐시 적중만 쟀고, 상세를 켜는 비용은 한 번도 잰 적이
없다. 키는 `components/home_preference.py` 에서 가져온다 — 여기 문자열로 베껴 두면 한쪽만
바뀌어도 드러나지 않는다.

토글을 하나씩 켜며 재는 이유는 **시나리오를 바꿔도 화면 상태를 유지하기로** 했기 때문이다.
유지하면 바꾼 직후 rerun 이 그 토글들의 몫까지 지고 간다. 그 몫이 얼마인지 숫자로 알아야
「유지가 무겁다」 를 말할 수 있다.

수치는 이 PC 의 합성 표본 기준이고 실데이터 크기에 따라 달라진다. 절대값이 아니라
**단계 사이의 차이**를 본다.
"""

import json
import sys
from pathlib import Path
from time import perf_counter

from streamlit.testing.v1 import AppTest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from capa_simulation.components.home_preference import (  # noqa: E402
    ADVANCE_TOGGLE_KEY,
    COMPARISON_TOGGLE_KEY,
    EDP_TOGGLE_KEY,
    EXECUTION_TOGGLE_KEY,
    PLAN_DETAIL_CUSTOMER_KEY,
)

HOME_TAB_KEY = "home_active_tab"


def run_phase(app: AppTest, phase: str) -> tuple[AppTest, dict[str, object]]:
    started_at = perf_counter()
    app.run()
    elapsed = perf_counter() - started_at
    exceptions = [str(exception.value) for exception in app.exception]
    return app, {
        "phase": phase,
        "seconds": round(elapsed, 3),
        "exceptions": exceptions,
    }


def main() -> int:
    app = AppTest.from_file(str(PROJECT_ROOT / "app.py"), default_timeout=300)
    results: list[dict[str, object]] = []

    app, result = run_phase(app, "cold_summary")
    results.append(result)
    app, result = run_phase(app, "warm_summary")
    results.append(result)

    # 토글을 하나씩 켠다. 끄지 않고 쌓는 것은 실제 사용이 그렇기 때문이다 — 켜 둔 채로
    # 다음 것을 켠다. 각 줄의 차이가 그 토글 하나가 더하는 몫이다.
    for phase, key in (
        ("plan_detail_customer", PLAN_DETAIL_CUSTOMER_KEY),
        ("advance", ADVANCE_TOGGLE_KEY),
        ("execution", EXECUTION_TOGGLE_KEY),
        ("comparison", COMPARISON_TOGGLE_KEY),
        ("edp", EDP_TOGGLE_KEY),
    ):
        app.session_state[key] = True
        app, result = run_phase(app, f"on_{phase}")
        results.append(result)

    # 켠 상태 그대로 한 번 더. 캐시가 흡수하는 몫을 가른다.
    app, result = run_phase(app, "warm_all_on")
    results.append(result)

    # 숨은 탭으로 옮긴다. `stateful_tabs` 가 Main 의 Figure 를 건너뛰는 몫이다.
    app.session_state[HOME_TAB_KEY] = ":material/history: Past Data"
    app, result = run_phase(app, "hidden_main_tab")
    results.append(result)

    print(json.dumps(results, ensure_ascii=False, indent=2))
    return int(any(result["exceptions"] for result in results))


if __name__ == "__main__":
    raise SystemExit(main())
