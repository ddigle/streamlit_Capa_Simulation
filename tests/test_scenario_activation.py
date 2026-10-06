# Purpose: 시나리오를 활성화할 때 버릴 세션 값의 목록과 떠 두는 머리 띠 이름표를 고정한다.

import ast
import inspect
from pathlib import Path

import pytest

import capa_simulation.components.home_preference as home_preference
from capa_simulation.home_state import HOME_TOGGLE_DEFAULTS, PAST_DATA_TOGGLE_KEY
from capa_simulation.io.reference_cache import HOME_FIGURE_CACHE_KEY
from capa_simulation.scenario_activation import _STALE_UI_KEYS

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _home_toggle_keys() -> set[str]:
    """`home_preference` 가 만드는 **모든** `st.toggle` 의 세션 키.

    손으로 나열하지 않는 이유가 이 함수의 존재 이유다. 「실행 Loss」 토글은 목록이 만들어진 뒤에
    추가됐고, 추가한 커밋은 `scenario_activation.py` 를 한 줄도 건드리지 않았다. 그래서
    선행·GAP·상세는 꺼지는데 실행만 켜진 채 남는 비대칭이 한동안 있었다. 사람이 목록을
    늘려야 하는 그물은 같은 방식으로 또 흘러내린다.
    """
    source = Path(inspect.getfile(home_preference)).read_text(encoding="utf-8")
    names: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        function = node.func
        if not (isinstance(function, ast.Attribute) and function.attr == "toggle"):
            continue
        keyword = next((item for item in node.keywords if item.arg == "key"), None)
        if keyword is None or not isinstance(keyword.value, ast.Name):
            continue
        names.add(keyword.value.id)
    assert names, "토글을 하나도 찾지 못했습니다 — 화면 구조가 바뀌었으면 이 그물부터 고칩니다."
    return {getattr(home_preference, name) for name in names}


def test_every_home_toggle_is_cleared_when_another_scenario_is_activated() -> None:
    """HOME 토글은 시나리오를 바꾸면 **전부** 풀린다.

    토글은 모두 기준정보 위에 무언가를 얹거나 빼는 스위치이고, 켠 사람은 그 시나리오를
    보며 켰다. 켠 채로 바꾸면 얹힌 것이 새 계획 위에 그대로 남는다 — 실행 Capa 증감은
    확보율을 통해 B/N 순위·Top5 막대·히트맵까지 바꾼다. 그런데 화면에는 토글이 켜져 있으니
    사용자는 그것을 새 시나리오의 원래 값으로 읽는다.

    `Past Data 포함` 만 기본값이 **켬**이라, 풀린다는 것은 켜진 상태로 돌아간다는 뜻이다.
    나머지 다섯은 기본값이 꺼짐이다.
    """
    missing = sorted(_home_toggle_keys() - set(_STALE_UI_KEYS))

    assert not missing, (
        "HOME 토글이 `_STALE_UI_KEYS` 에 없습니다. 시나리오를 바꿔도 켜진 채 남아 "
        "남의 시나리오를 전제로 켠 상태가 새 계획 위에 얹힙니다:\n" + "\n".join(missing)
    )


def test_every_home_toggle_has_one_shared_default() -> None:
    """계산 진입점과 뒤에 그리는 위젯이 같은 기본 표시를 쓰며 모두 초기화된다."""
    assert set(HOME_TOGGLE_DEFAULTS) == _home_toggle_keys()
    assert HOME_TOGGLE_DEFAULTS[PAST_DATA_TOGGLE_KEY] is True
    assert not any(
        value for key, value in HOME_TOGGLE_DEFAULTS.items() if key != PAST_DATA_TOGGLE_KEY
    )


def test_view_state_is_not_cleared() -> None:
    """탭과 조회 조건은 지우지 않는다. 무엇을 보고 있는지일 뿐 값에 닿지 않는다.

    지우면 시나리오를 바꿀 때마다 보던 자리를 다시 찾아야 한다. 그 둘을 살리는 장치는
    `components/tab_state.py` 와 위젯의 `persist_state="session"` 이고,
    `tests/test_view_state_survives_reload.py` 가 실제 동작으로 고정한다.
    """
    for key in _STALE_UI_KEYS:
        assert "active_tab" not in key, key
        assert "_filter" not in key, key


def test_only_previous_values_and_home_toggles_are_dropped() -> None:
    """목록에 남는 것은 **앞 시나리오의 값이 담긴 칸**과 HOME 토글뿐이다."""
    assert set(_STALE_UI_KEYS) - _home_toggle_keys() == {
        "load_conversion_source_token",
        "reference_data_source_token",
        "load_conversion_own_change",
        "reference_data_own_change",
        HOME_FIGURE_CACHE_KEY,
    }


def test_the_stale_key_list_has_no_duplicates() -> None:
    assert len(set(_STALE_UI_KEYS)) == len(_STALE_UI_KEYS)


def test_the_figure_cache_key_has_one_owner() -> None:
    """Figure 캐시 칸의 이름은 세 곳이 쓴다. 리터럴로 흩어 두면 이름을 바꿀 때 한 곳만 고쳐진다.

    그러면 시나리오를 바꿔도 옛 칸이 남아 **남의 시나리오 그림이 그대로 뜬다.**
    소유자는 `io/reference_cache` 하나다 — pandas·streamlit 만 보는 잎이라 셋 다 여기서
    가져올 수 있고, `components` 쪽에 두면 `scenario_activation` 이 import 하지 못한다.
    """
    from capa_simulation.components.home_rendering import (
        HOME_FIGURE_CACHE_KEY as rendering_key,
    )

    assert rendering_key is HOME_FIGURE_CACHE_KEY
    assert HOME_FIGURE_CACHE_KEY in _STALE_UI_KEYS


def test_no_key_in_the_list_is_a_fossil() -> None:
    """목록에 **아무도 만들지 않는 칸**이 남으면 최신인 척하는 화석이 된다.

    지운 화면의 세션 키 셋이 그렇게 남아 있었다. 지우는 코드는 계속 도는데 그 칸은 애초에
    생기지 않으니 아무 일도 하지 않고, 목록만 길어 보인다. 같은 이유로 **오타도 잡힌다** —
    철자가 한 글자 틀리면 그 칸은 어디서도 만들어지지 않는 이름이 된다.
    `scenario_activation.py` 주석이 "검사가 철자를 지킨다" 고 적어 둔 약속이 이것이다.

    토글 키는 위 검사가 AST 로 이미 보므로 여기서는 나머지만 본다. **스캔에서 `tests/` 와
    `scenario_activation.py` 자신을 반드시 뺀다** — 안 빼면 목록에 적었다는 이유로 통과해서
    화석이 그대로 산다.
    """
    literals: set[str] = set()
    for root in (PROJECT_ROOT / "app_pages", PROJECT_ROOT / "src"):
        for path in root.rglob("*.py"):
            if path.name == "scenario_activation.py":
                continue
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    literals.add(node.value)

    fossils = sorted(
        key for key in set(_STALE_UI_KEYS) - _home_toggle_keys() if key not in literals
    )

    assert not fossils, (
        "이 키를 만드는 곳이 저장소에 없습니다. 화면이 지워졌거나 철자가 틀렸습니다 — "
        "목록에서 빼거나 철자를 맞춥니다:\n" + "\n".join(fossils)
    )


def _label_snapshot(*, registered_at: object, plan_months: tuple[int, ...]) -> object:
    from datetime import datetime
    from types import SimpleNamespace

    import pandas as pd

    from capa_simulation.services.month_filter import MONTH_COLUMN

    return SimpleNamespace(
        scenario=SimpleNamespace(
            scenario_id="scenario-1",
            scenario_name="DEMO 시나리오",
            source_simulation_code="DEMO-CODE",
            source_type="BIGDATAQUERY",
            source_registered_at=registered_at,
            created_at=datetime(2026, 10, 1, 8, 0),
        ),
        revision=SimpleNamespace(
            revision_id="revision-2",
            revision_no=2,
            revision_name="보정",
            created_at=datetime(2026, 10, 5, 9, 0),
        ),
        tables={"RQ_PKG_PLAN": pd.DataFrame({MONTH_COLUMN: list(plan_months)})},
    )


def test_the_header_label_is_taken_once_from_the_activated_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """머리 띠 이름표는 활성화할 때 스냅샷에서 한 번 떠 둔다. 원천 등록시점이 없으면 시나리오를 만든
    시각이고, 시나리오 기간은 생산계획의 첫 달·끝 달이다. 다른 리비전이 올라와 있으면 믿지
    않는다."""
    from datetime import datetime
    from types import SimpleNamespace

    import capa_simulation.scenario_activation as activation

    state: dict[str, object] = {}
    monkeypatch.setattr(activation, "st", SimpleNamespace(session_state=state))
    state[activation.ACTIVE_PERSISTED_REVISION_ID_KEY] = "revision-2"

    activation._remember_label(
        _label_snapshot(registered_at=datetime(2026, 9, 28), plan_months=(202609, 202607, 202812))
    )
    label = activation.active_scenario_label()
    assert label is not None
    assert label.registered_at == datetime(2026, 9, 28)
    assert (label.first_month, label.last_month) == (202607, 202812)
    assert (label.revision_no, label.revision_name, label.simulation_code) == (
        2,
        "보정",
        "DEMO-CODE",
    )

    activation._remember_label(_label_snapshot(registered_at=None, plan_months=()))
    label = activation.active_scenario_label()
    assert label is not None
    assert label.registered_at == datetime(2026, 10, 1, 8, 0)
    assert (label.first_month, label.last_month) == (None, None)

    state[activation.ACTIVE_PERSISTED_REVISION_ID_KEY] = "revision-other"
    assert activation.active_scenario_label() is None


def test_renaming_the_active_scenario_renames_its_header_label(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """이름표는 떠 둔 값이라 시나리오명을 바꾸면 따로 고친다. 다른 시나리오의 이름 변경은
    무시한다."""
    from datetime import datetime
    from types import SimpleNamespace

    import capa_simulation.scenario_activation as activation

    state: dict[str, object] = {activation.ACTIVE_PERSISTED_REVISION_ID_KEY: "revision-2"}
    monkeypatch.setattr(activation, "st", SimpleNamespace(session_state=state))
    activation._remember_label(
        _label_snapshot(registered_at=datetime(2026, 9, 28), plan_months=(202607,))
    )

    activation.rename_active_scenario_label("scenario-other", "남의 이름")
    label = activation.active_scenario_label()
    assert label is not None and label.scenario_name == "DEMO 시나리오"
    activation.rename_active_scenario_label("scenario-1", "바뀐 이름")
    label = activation.active_scenario_label()
    assert label is not None and label.scenario_name == "바뀐 이름"
