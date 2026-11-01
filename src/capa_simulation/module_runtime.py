# Purpose: 사내 모듈 화면 실행을 감싸 그 화면에만 오류 카드를 그리고 접두 없는 세션 키를 알린다.

"""사내 모듈 화면 실행 감싸기(고장 격리 — 화면 본문).

`app.py` 가 **모듈 화면일 때만** `navigation.run()` 을 `run_module_page` 로 부른다. 고장 격리는 세
겹이다 — 화면 본문은 여기, 위젯 콜백은 `module_api` 의 `ctx.callback`(콜백은 회차 맨 앞, `app.py`
보다 먼저 돈다), 프래그먼트만 도는 회차는 `ctx.guard`(그 회차는 `app.py` 밖이다).

- 화면 본문의 `Exception`·`SystemExit`(옮긴 독립 앱의 `argparse`·`sys.exit`)은 적고 그 화면에 카드를
  그린 뒤 **정상으로 돌아온다** — `app.py` 꼬리(`app_run.finish()`·`warm_intro_summary`)가 돌아
  회차가 정상으로 끝나고 사이드바·머리 띠·탭 줄·다른 화면은 그대로다. `SystemExit` 을 두면
  ScriptRunner 스레드가 끝나 세션이 「실행 중」 에 머문다.
- `FragmentHandledException`(전체 실행 안 프래그먼트 실패 — Streamlit 이 이미 그 안에 그렸다)은 적고
  카드 없이 정상으로 돌아온다. 다시 던지면 그 회차가 끝나지 않은 회차가 된다.
- `StopException`(`st.stop()`)·`RerunException`(`st.rerun`·`st.switch_page`)은 다시 던진다.
- 앞선 콜백 실패(세션 표지)는 그 화면 맨 위에 카드로 먼저 그린다.
- 접두 없는 세션 키(새로·바꿈·지움)를 실행 앞뒤 값의 객체(`is`)로 견주어 알린다 — 제자리 바꿈과
  콜백에서 바뀐 키는 놓친다(알 수 있는 만큼, 정적 점검이 주된 그물이다). 읽을 때마다 새 객체가
  나오는 칸(Components v2 위젯 값 — 입장 화면·Summary·탭 줄)은 실행 앞에 두 번 읽어 가려내고
  「바꿈」 을 보지 않는다(브라우저 확인에서 거짓 알림으로 드러났다 — AppTest 는 그 컴포넌트를
  대역으로 바꿔 보지 못한다).
- `st.stop()` 뒤에는 화면에 그리는 것도 세션 칸을 읽고 쓰는 것도 다시 멈춤 예외를 낸다(Streamlit
  1.63 — 그러면 `app.py` 가 「끊긴 회차」 로 본다). 그래서 견주기는 멈추지 않는
  `st.session_state.to_dict()` 로 하고, 그 알림은 기록(Admin)에 바로 적고 화면에는 같은 세션의
  다음 그 모듈 회차 맨 위에 세운다(세션 칸이 아니라 프로세스 안 칸에 넘긴다).
"""

from __future__ import annotations

import logging
import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final

import streamlit as st
from streamlit.errors import FragmentHandledException
from streamlit.runtime.scriptrunner import get_script_run_ctx
from streamlit.runtime.scriptrunner_utils.exceptions import StopException

from capa_simulation import module_failures, module_registry, settings
from capa_simulation.components.literal_markdown import literal_names
from capa_simulation.components.module_failure_card import (
    FailureParts,
    render_failure_parts,
    render_module_failure_card,
)
from capa_simulation.module_failures import ModuleFailure

if TYPE_CHECKING:
    from capa_simulation.navigation import PageSpec

# 모듈 회차에 코어가 만드는 세션 키(지금 없음). 생기면 여기에 적어 거짓 알림을 막는다.
CORE_KEYS_DURING_MODULE_RUN: Final[frozenset[str]] = frozenset()
KEY_WARNING_ICON: Final = ":material/key:"
_LOGGER = logging.getLogger("capa_simulation.modules")
_IMPLEMENTING_TAIL: Final = f" {module_registry.IMPLEMENTING_MARK}"
# `st.stop()` 으로 멈춘 회차의 키 알림 — (세션 id, 모듈 id) → 글. 그 세션의 다음 그 모듈 회차가
# 꺼낸다. 끝난 세션의 칸이 쌓이지 않게 오래된 것부터 버린다.
_DEFERRED_LIMIT: Final = 256
_DEFERRED: OrderedDict[tuple[str, str], str] = OrderedDict()
_DEFERRED_LOCK = threading.Lock()


def last_failures() -> Mapping[str, ModuleFailure]:
    """id → 마지막 실패(`module_failures.last_failures`)."""
    return module_failures.last_failures()


def key_warnings() -> Mapping[str, tuple[str, ...]]:
    """id → 마지막으로 알린 접두 없는 키 이름(`module_failures.key_warnings`)."""
    return module_failures.key_warnings()


def clear_runtime_records() -> None:
    """실행 기록을 비운다(시험용)."""
    module_failures.clear_records()
    with _DEFERRED_LOCK:
        _DEFERRED.clear()


def _session_id() -> str:
    ctx = get_script_run_ctx(suppress_warning=True)
    return "" if ctx is None else str(ctx.session_id)


def _defer_key_warning(module_id: str, text: str) -> None:
    with _DEFERRED_LOCK:
        _DEFERRED[(_session_id(), module_id)] = text
        while len(_DEFERRED) > _DEFERRED_LIMIT:
            _DEFERRED.popitem(last=False)


def _pop_deferred_key_warning(module_id: str) -> str | None:
    with _DEFERRED_LOCK:
        return _DEFERRED.pop((_session_id(), module_id), None)


def _slug(spec: PageSpec) -> str:
    return (spec.url_path or "").removeprefix(f"mod-{spec.module}-")


def _page_title(spec: PageSpec) -> str:
    return spec.title.removesuffix(_IMPLEMENTING_TAIL)


def _module_facts(spec: PageSpec) -> tuple[str, str, Path]:
    """(모듈 이름, 담당, 모듈 폴더). 선언을 다시 못 읽으면 id·빈 담당·화면 폴더로 물러선다."""
    page = Path(spec.path)
    page = page if page.is_absolute() else settings.PROJECT_ROOT / page
    try:
        folder = module_registry.module_folder_for(page)
        manifest = module_registry.cached_manifest(folder)
    except module_registry.ManifestError:
        return spec.module or "", "", page.parent
    return manifest.name, manifest.owner, folder


def render_failure(spec: PageSpec, exc: BaseException, *, where: str = "page") -> None:
    """모듈 화면 `spec` 의 오류 카드를 지금 자리에 그린다."""
    name, owner, folder = _module_facts(spec)
    render_module_failure_card(
        module_id=spec.module or "",
        module_name=name,
        owner=owner,
        folder=folder,
        page_title=_page_title(spec),
        exc=exc,
        where=where,
    )


def _render_pending_callback_failure(spec: PageSpec) -> None:
    """앞선 콜백 실패 표지(`ctx.callback` 이 남긴 것)를 꺼내 화면 맨 위에 카드로 그린다."""
    module_id = spec.module or ""
    marker = st.session_state.pop(module_failures.callback_failure_key(module_id), None)
    if not isinstance(marker, Mapping):
        return
    frames = marker.get("frames")
    parts = FailureParts(
        kind=str(marker.get("kind", "")),
        message=str(marker.get("message", "")),
        frames=tuple(str(frame) for frame in frames) if isinstance(frames, list) else (),
        hint=str(marker.get("hint", "")),
    )
    name, owner, _ = _module_facts(spec)
    render_failure_parts(
        module_id=module_id,
        module_name=name,
        owner=owner,
        page_title=_page_title(spec),
        parts=parts,
        where="callback",
    )


def _unprefixed_snapshot(module_id: str) -> dict[str, object]:
    """접두 없는 글자 키 → 값(객체 그대로). 읽기만 한다(위젯 값은 한 번 읽으면 같은 객체로 남는다).

    `to_dict()` 는 멈춤 요청을 보지 않는다 — `st.stop()` 뒤에도 돈다(칸 하나씩 읽으면 다시 멈춘다).
    `id()` 가 아니라 객체를 쥐고 `is` 로 견준다 — 버려진 객체의 `id` 는 새 객체에 다시 쓰인다.
    """
    prefix = module_registry.key_prefix(module_id)
    return {
        key: value
        for key, value in st.session_state.to_dict().items()
        if isinstance(key, str)
        and not key.startswith(prefix)
        and key not in CORE_KEYS_DURING_MODULE_RUN
    }


@dataclass(frozen=True)
class KeySnapshot:
    """실행 앞 접두 없는 키 → 값과, 두 번 읽어 다른 객체였던(읽을 때마다 새 객체인) 키."""

    values: Mapping[str, object]
    unstable: frozenset[str]


def key_snapshot(module_id: str) -> KeySnapshot:
    first = _unprefixed_snapshot(module_id)
    second = _unprefixed_snapshot(module_id)
    unstable = frozenset(
        key for key, value in first.items() if key in second and second[key] is not value
    )
    return KeySnapshot(second, unstable)


def key_warning_text(new: int, changed: int, removed: int, names: list[str]) -> str:
    return (
        f"이 모듈이 접두 없는 세션 키를 건드렸습니다 — 새로 {new} · 바꿈 {changed} · 지움 "
        f"{removed}: {literal_names(names)} — ctx.key(...) 로 바꿔 주세요"
        "(docs/module_guide.md 4장)."
    )


def _key_changes(module_id: str, before: KeySnapshot) -> tuple[str, list[str]] | None:
    after = _unprefixed_snapshot(module_id)
    new = sorted(set(after) - set(before.values))
    removed = sorted(set(before.values) - set(after))
    changed = sorted(
        key
        for key in set(before.values) & set(after) - before.unstable
        if before.values[key] is not after[key]
    )
    if not (new or removed or changed):
        return None
    names = [*new, *changed, *removed][: module_failures.MAX_KEY_WARNINGS]
    return key_warning_text(len(new), len(changed), len(removed), names), names


def _render_pending_key_warning(module_id: str) -> None:
    """`st.stop()` 으로 멈춘 앞 회차가 넘긴 키 알림을 화면 맨 위에 그린다."""
    text = _pop_deferred_key_warning(module_id)
    if text:
        st.warning(text, icon=KEY_WARNING_ICON)


def _finish(spec: PageSpec, before: KeySnapshot, started: float, *, stopped: bool) -> None:
    module_id = spec.module or ""
    module_failures.note_run_seconds(module_id, time.perf_counter() - started)
    changes = _key_changes(module_id, before)
    if changes is None:
        return
    text, names = changes
    module_failures.note_key_warnings(module_id, names)
    if stopped:
        # 멈춘 회차에는 그리지도 세션 칸에 쓰지도 못한다 — 다음 회차 맨 위로 넘긴다.
        _defer_key_warning(module_id, text)
        return
    st.warning(text, icon=KEY_WARNING_ICON)


def _record(spec: PageSpec, exc: BaseException) -> None:
    module_failures.record_failure(
        spec.module or "", page=_slug(spec), kind=type(exc).__name__, where="page"
    )
    _LOGGER.error("사내 모듈 %s 화면 %s 실패", spec.module, _slug(spec), exc_info=exc)


def run_module_page(run: Callable[[], None], spec: PageSpec) -> None:
    """모듈 화면 `spec` 을 `run`(보통 `navigation.run`)으로 돌리며 그 화면만 고장 나게 한다."""
    module_id = spec.module
    if module_id is None:
        run()
        return
    before = key_snapshot(module_id)
    _render_pending_callback_failure(spec)
    _render_pending_key_warning(module_id)
    started = time.perf_counter()
    try:
        run()
    except FragmentHandledException as handled:
        # Streamlit 이 이미 그 프래그먼트 안에 그렸다 — 카드 없이 적고 정상으로 돌아온다.
        original = handled.args[0] if handled.args else handled
        _record(spec, original if isinstance(original, BaseException) else handled)
    except StopException:
        _finish(spec, before, started, stopped=True)
        raise
    except (Exception, SystemExit) as error:
        _record(spec, error)
        render_failure(spec, error)
    _finish(spec, before, started, stopped=False)
