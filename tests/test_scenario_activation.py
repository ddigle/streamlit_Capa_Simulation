# Purpose: 시나리오를 활성화할 때 버릴 세션 값의 목록과 떠 두는 머리 띠 이름표를 고정한다.

import ast
import inspect
from datetime import datetime
from pathlib import Path

import pytest

import capa_simulation.components.home_preference as home_preference
from capa_simulation.home_state import HOME_TOGGLE_DEFAULTS, PAST_DATA_TOGGLE_KEY
from capa_simulation.io.reference_cache import HOME_FIGURE_CACHE_KEY
from capa_simulation.persistence.models import (
    RevisionSummary,
    ScenarioPreset,
    ScenarioSnapshot,
    ScenarioSummary,
)
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


def test_home_toggles_take_their_default_from_the_session_not_from_value() -> None:
    """HOME 토글 위젯에는 `value=` 를 주지 않는다 — 기본값은 카드가 세션에 심는다.

    시나리오를 바꾸면 토글 칸에 기본값을 **적어** 브라우저에 밀어 넣는다. `value=True`
    (`Past Data 포함`)를 준 위젯에 세션 값까지 적으면 Streamlit 이 둘을 함께 썼다고 경고하므로,
    새 토글이 `value=` 를 다시 들고 오면 여기서 잡는다.
    """
    source = Path(inspect.getfile(home_preference)).read_text(encoding="utf-8")
    offenders: list[int] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        function = node.func
        if not (isinstance(function, ast.Attribute) and function.attr == "toggle"):
            continue
        if any(item.arg == "value" for item in node.keywords) or node.args[1:]:
            offenders.append(node.lineno)
    assert not offenders, f"`value=` 를 받은 HOME 토글이 있습니다(행): {offenders}"


def _fake_session(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    """`scenario_activation` 이 보는 세션을 dict 로 바꾸고 앞 시나리오의 흔적을 채워 둔다."""
    from types import SimpleNamespace

    import capa_simulation.scenario_activation as activation

    state: dict[str, object] = {key: f"앞 시나리오의 {key}" for key in activation._STALE_VALUE_KEYS}
    state.update({key: not default for key, default in HOME_TOGGLE_DEFAULTS.items()})
    monkeypatch.setattr(activation, "st", SimpleNamespace(session_state=state))
    return state


def _assert_released(state: dict[str, object]) -> None:
    """값 칸은 지워지고, 토글 칸은 **남은 채** 기본값이 적혀 있다.

    토글 칸이 없어지면(`pop`) 서버는 기본값으로 그리지만 브라우저는 그 사실을 듣지 못해 옛 값을
    들고 있다가 다음 조작에 되보낸다(2026-10-08 안정화 점검 B1). 칸이 있고 값이 기본값이어야
    Streamlit 이 다음에 위젯을 만들 때 브라우저에 새 값을 보낸다.
    """
    from capa_simulation.scenario_activation import _STALE_VALUE_KEYS

    assert not [key for key in _STALE_VALUE_KEYS if key in state]
    toggles = {key: state.get(key, "칸 없음") for key in HOME_TOGGLE_DEFAULTS}
    assert toggles == dict(HOME_TOGGLE_DEFAULTS)


def test_activating_a_snapshot_writes_the_toggle_defaults_instead_of_dropping_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import capa_simulation.scenario_activation as activation

    state = _fake_session(monkeypatch)
    monkeypatch.setattr(activation, "activate_persisted_reference_tables", lambda *a, **k: 3)
    monkeypatch.setattr(activation, "activate_scenario_tables", lambda *a, **k: {"revision": 7})
    monkeypatch.setattr(activation, "queue_scenario_preset", lambda preset: None)

    activation.activate_persisted_snapshot(
        _label_snapshot(registered_at=None, plan_months=(202607,))
    )

    _assert_released(state)
    assert state[activation.ACTIVE_PERSISTED_REVISION_ID_KEY] == "revision-2"


def test_clearing_the_activation_writes_the_toggle_defaults_too(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """시나리오를 보관·삭제해 활성화를 걷을 때도 같다 — 이어서 공식버전 부트스트랩이 돈다."""
    import capa_simulation.scenario_activation as activation

    state = _fake_session(monkeypatch)
    state[activation.ACTIVE_PERSISTED_REVISION_ID_KEY] = "revision-2"
    monkeypatch.setattr(activation, "clear_persisted_reference_tables", lambda: None)
    monkeypatch.setattr(activation, "clear_active_scenario", lambda: None)

    activation.clear_persisted_scenario_activation()

    _assert_released(state)
    assert activation.ACTIVE_PERSISTED_REVISION_ID_KEY not in state


def test_saving_a_revision_of_the_active_scenario_keeps_the_toggles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """활성 시나리오의 새 리비전 저장은 HOME 토글을 건드리지 않는다. 값 칸은 그대로 버린다.

    저장한 리비전은 방금 보던 내용을 그대로 적은 것이라 토글의 전제가 바뀌지 않는다. 값 칸은
    리비전이 바뀌어 편집 화면의 원본 토큰·Figure 캐시가 새로 서야 하므로 버린다.
    """
    import capa_simulation.scenario_activation as activation

    state = _fake_session(monkeypatch)
    flipped = {key: not default for key, default in HOME_TOGGLE_DEFAULTS.items()}
    state[activation.ACTIVE_PERSISTED_SCENARIO_ID_KEY] = "scenario-1"
    monkeypatch.setattr(activation, "activate_persisted_reference_tables", lambda *a, **k: 3)
    monkeypatch.setattr(activation, "activate_scenario_tables", lambda *a, **k: {"revision": 7})
    monkeypatch.setattr(activation, "queue_scenario_preset", lambda preset: None)

    activation.activate_saved_revision(_label_snapshot(registered_at=None, plan_months=(202607,)))

    assert not [key for key in activation._STALE_VALUE_KEYS if key in state]
    assert {key: state[key] for key in HOME_TOGGLE_DEFAULTS} == flipped
    assert state[activation.ACTIVE_PERSISTED_REVISION_ID_KEY] == "revision-2"


def test_a_saved_revision_of_another_scenario_releases_the_toggles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """저장 경로라도 올리는 리비전이 지금 활성인 시나리오의 것이 아니면 내용이 바뀐 것이다."""
    import capa_simulation.scenario_activation as activation

    state = _fake_session(monkeypatch)
    state[activation.ACTIVE_PERSISTED_SCENARIO_ID_KEY] = "scenario-other"
    monkeypatch.setattr(activation, "activate_persisted_reference_tables", lambda *a, **k: 3)
    monkeypatch.setattr(activation, "activate_scenario_tables", lambda *a, **k: {"revision": 7})
    monkeypatch.setattr(activation, "queue_scenario_preset", lambda preset: None)

    activation.activate_saved_revision(_label_snapshot(registered_at=None, plan_months=(202607,)))

    _assert_released(state)


def _activation_calls_by_function() -> dict[str, tuple[set[str], set[str]]]:
    """활성화를 부르는 함수마다 (부르는 활성화 함수, 그 함수 안의 모든 호출 이름)."""
    names = {"activate_persisted_snapshot", "activate_saved_revision"}
    found: dict[str, tuple[set[str], set[str]]] = {}
    for root in (PROJECT_ROOT / "app_pages", PROJECT_ROOT / "src"):
        for path in root.rglob("*.py"):
            if path.name == "scenario_activation.py":
                continue
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if not isinstance(node, ast.FunctionDef):
                    continue
                calls: set[str] = set()
                for inner in ast.walk(node):
                    if isinstance(inner, ast.Call):
                        function = inner.func
                        if isinstance(function, ast.Name):
                            calls.add(function.id)
                        elif isinstance(function, ast.Attribute):
                            calls.add(function.attr)
                if calls & names:
                    found[f"{path.name}:{node.name}"] = (calls & names, calls)
    return found


def test_only_saving_a_revision_keeps_the_toggles() -> None:
    """활성화 경로 표를 코드로 고정한다 — 새 리비전을 저장하는 함수(`save_revision`)만 토글을
    두는 `activate_saved_revision` 을 부르고, 나머지(불러오기·새 시나리오 복제·BigDataQuery
    등록)는 모두 토글을 푸는 `activate_persisted_snapshot` 을 부른다."""
    found = _activation_calls_by_function()
    assert found, "활성화를 부르는 함수를 하나도 찾지 못했습니다 — 그물부터 고칩니다."
    wrong = {
        name: sorted(used)
        for name, (used, calls) in found.items()
        if used
        != (
            {"activate_saved_revision"}
            if "save_revision" in calls
            else {"activate_persisted_snapshot"}
        )
    }
    assert not wrong, f"활성화 경로가 표와 다릅니다: {wrong}"
    savers = sorted(name for name, (_, calls) in found.items() if "save_revision" in calls)
    # 저장 경로는 사이드바 「신규 리비전 저장」과 시나리오 관리 「새 리비전 저장」 둘이다.
    assert savers == [
        "scenario_management.py:_render_revision_save",
        "scenario_status.py:_render_revision_save",
    ], savers


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
    from capa_simulation.scenario_activation import _STALE_VALUE_KEYS

    assert set(_STALE_VALUE_KEYS) == set(_STALE_UI_KEYS) - _home_toggle_keys()
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
    import capa_simulation.components.home_rendering as home_rendering

    # 다시 내보내는 이름이 아니라서 모듈 이름공간에서 직접 읽는다.
    assert vars(home_rendering)["HOME_FIGURE_CACHE_KEY"] is HOME_FIGURE_CACHE_KEY
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


def _label_snapshot(
    *, registered_at: datetime | None, plan_months: tuple[int, ...]
) -> ScenarioSnapshot:
    import pandas as pd

    from capa_simulation.services.month_filter import MONTH_COLUMN

    return ScenarioSnapshot(
        scenario=ScenarioSummary(
            scenario_id="scenario-1",
            dataset_id="dataset-1",
            scenario_name="DEMO 시나리오",
            source_simulation_code="DEMO-CODE",
            source_simulation_name="DEMO 원천",
            source_type="BIGDATAQUERY",
            status="active",
            active_revision_id="revision-2",
            active_revision_no=2,
            created_at=datetime(2026, 10, 1, 8, 0),
            updated_at=datetime(2026, 10, 5, 9, 0),
            source_registered_at=registered_at,
        ),
        revision=RevisionSummary(
            revision_id="revision-2",
            scenario_id="scenario-1",
            revision_no=2,
            revision_name="보정",
            parent_revision_id=None,
            note=None,
            reference_hash="hash",
            created_at=datetime(2026, 10, 5, 9, 0),
        ),
        preset=ScenarioPreset(start_month=202601, end_month=202612, included_processes=()),
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
