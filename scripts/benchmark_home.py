# Purpose: Measure cold, warm, and detailed HOME Python reruns without exposing source data.

"""Measure cold, warm, and detailed HOME Python reruns without exposing source data."""

import json
from pathlib import Path
from time import perf_counter

from streamlit.testing.v1 import AppTest

PROJECT_ROOT = Path(__file__).resolve().parents[1]


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

    app.session_state["dashboard_show_details"] = True
    app, result = run_phase(app, "cold_details")
    results.append(result)

    app.session_state["dashboard_show_details"] = False
    app, result = run_phase(app, "reused_summary")
    results.append(result)

    print(json.dumps(results, ensure_ascii=False, indent=2))
    return int(any(result["exceptions"] for result in results))


if __name__ == "__main__":
    raise SystemExit(main())
