# Purpose: 등록되는 컴포넌트 JS 와 자산 · static JS 파일이 ES 모듈로 읽히는지 node 로 본다.

"""브라우저는 컴포넌트 JS 를 통째로 모듈로 들인다 — 한 글자라도 읽히지 않으면 그 컴포넌트 전체가
아무 말 없이 서지 않는다. 두 가지를 합친 머리에서 알림 칸 JS 맨 위 `const DIALOG` 가 두 번 남아
알림창 · Alarm · 변경 칩이 앱 전체에서 사라졌는데, 구획만 떼어 돌리는 자산 시험
(`tests/test_alert_center_assets.py`)은 통과했다(2026-11-07 전 화면 점검). 글자 충돌 없는
합침이 겹친 선언을 만들 수 있으므로 파일 하나하나와 **실제로 등록되는 글**(서식 · 다른 자산을 앞에
붙인 것)을 모두 `node --check` 로 읽는다.

등록되는 글은 `st.components.v2.component(…)` 를 부르는 소스 모듈을 기록 대역 아래에서 새로 읽어
받는다 — 등록 목록을 손으로 두지 않아 새 컴포넌트도 저절로 든다.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import streamlit.components.v2 as components_v2
from js_runner import check_js_module

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PROJECT_ROOT / "src" / "capa_simulation"
COMPONENTS = SOURCE_ROOT / "components"
STATIC = PROJECT_ROOT / "static"
_REGISTER_CALL = "components.v2.component("


def _asset_files() -> list[Path]:
    """자산 폴더(`components/*_assets/`)와 `static/` 의 JS 파일."""
    found = [*COMPONENTS.glob("*_assets/*.js"), *STATIC.rglob("*.js")]
    return sorted(found)


def _registering_modules() -> list[Path]:
    """컴포넌트를 등록하는 소스 모듈."""
    return sorted(
        path
        for path in SOURCE_ROOT.rglob("*.py")
        if _REGISTER_CALL in path.read_text(encoding="utf-8")
    )


def _label(path: Path) -> str:
    return path.relative_to(PROJECT_ROOT).as_posix()


def _registered_js(module_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """`module_path` 를 새 이름으로 한 번 더 읽어 그 모듈이 등록하는 {컴포넌트 이름: js} 를 받는다.

    이미 읽힌 모듈은 등록을 끝냈으므로 같은 소스를 다른 이름으로 다시 돌린다. dataclass 가 제 모듈을
    `sys.modules` 에서 찾으므로 그 동안만 넣어 둔다."""
    seen: dict[str, str] = {}

    def record(name: str, *, js: str | None = None, **_: Any) -> SimpleNamespace:
        if js is not None:
            seen[name] = js
        return SimpleNamespace()

    monkeypatch.setattr(components_v2, "component", record)
    name = f"_js_syntax_{module_path.stem}"
    spec = importlib.util.spec_from_file_location(name, module_path)
    assert spec is not None and spec.loader is not None, module_path
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    return seen


def test_the_net_finds_the_assets_and_the_registering_modules() -> None:
    """그물이 빈손으로 지나가지 않는다 — 알림 칸 자산과 그 등록 모듈이 목록에 든다."""
    assets = {_label(path) for path in _asset_files()}
    modules = {_label(path) for path in _registering_modules()}
    assert "src/capa_simulation/components/alert_center_assets/alert_center.js" in assets
    assert "src/capa_simulation/components/alert_center.py" in modules


@pytest.mark.parametrize("path", _asset_files(), ids=_label)
def test_every_asset_js_file_parses_as_a_module(path: Path) -> None:
    """자산 · static JS 파일 하나하나가 모듈로 읽힌다."""
    completed = check_js_module(path.read_text(encoding="utf-8"), what=_label(path))
    assert completed.returncode == 0, f"{_label(path)} 이 읽히지 않는다:\n{completed.stderr}"


@pytest.mark.parametrize("module_path", _registering_modules(), ids=_label)
def test_every_registered_component_js_parses_as_a_module(
    module_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """등록되는 글(앞에 붙인 서식 · 다른 자산 포함) 그대로 모듈로 읽힌다."""
    registered = _registered_js(module_path, monkeypatch)
    assert registered, f"{_label(module_path)} 이 js 를 등록하지 않았다"
    for name, js in registered.items():
        completed = check_js_module(js, what=f"{_label(module_path)} {name}")
        assert completed.returncode == 0, (
            f"{_label(module_path)} 의 컴포넌트 {name} JS 가 읽히지 않는다:\n{completed.stderr}"
        )


def test_a_declaration_left_twice_by_a_merge_fails_the_check() -> None:
    """이번 그물이 막으려는 꼴 — 맨 위 같은 이름 `const` 두 줄 — 은 읽기에서 실패한다."""
    source = (COMPONENTS / "alert_center_assets" / "alert_center.js").read_text(encoding="utf-8")
    doubled = "const DIALOG = '[role=\"dialog\"]'\n" + source
    completed = check_js_module(doubled, what="겹친 선언 대조")
    assert completed.returncode != 0
    assert "DIALOG" in completed.stderr
