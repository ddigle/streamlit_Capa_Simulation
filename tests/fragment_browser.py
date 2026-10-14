# Purpose: AppTest 에서 프래그먼트 저장소를 회차 사이에 쥐고 프래그먼트만 도는 회차를 흉내 낸다.

"""프래그먼트만 다시 도는 회차를 AppTest 로 돌리는 테스트 대역.

AppTest 는 `run()` 마다 러너를 새로 만들고 그때마다 프래그먼트 저장소도 새로 만든다. 그래서
위젯 콜백의 `st.rerun(<프래그먼트 key>)` 는 프래그먼트를 찾지 못하고, 프래그먼트 안 위젯을 눌러도
앱 전체가 돈다. 이 대역은 러너를 바꿔 끼워 서버처럼 저장소 하나를 계속 쥐고, `fragment_queue` 가
차 있으면 브라우저처럼 그 프래그먼트만 돌리는 요청(`fragment_id_queue`)을 보낸다.

**Streamlit 내부를 쓴다** — `LocalScriptRunner` 의 `_fragment_storage`·`_requests`·
`require_widgets_deltas` 와 `RerunData`, 델타의 `fragment_id`. `streamlit==1.63.0`
(`pyproject.toml` 의 `>=1.63,<1.64`)에 기댄다. 판을 올려 이 대역을 쓰는 시험이 러너 쪽에서 깨지면
시험 대상이 아니라 이 대역부터 그 판에 맞춘다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest
from streamlit.proto.ForwardMsg_pb2 import ForwardMsg
from streamlit.proto.WidgetStates_pb2 import WidgetStates
from streamlit.runtime.fragment import MemoryFragmentStorage
from streamlit.runtime.scriptrunner import RerunData, ScriptRunnerEvent
from streamlit.runtime.scriptrunner_utils.script_requests import ScriptRequests
from streamlit.testing.v1 import app_test as app_test_module
from streamlit.testing.v1.element_tree import ElementTree, parse_tree_from_messages
from streamlit.testing.v1.local_script_runner import LocalScriptRunner, require_widgets_deltas


@dataclass
class FragmentBrowser:
    """브라우저 대역 — 회차 사이에 쥐는 프래그먼트 저장소와, 다음 회차에 돌릴 프래그먼트.

    `fragment_queue` 가 비어 있으면 앱 전체 회차다. `started` 는 마지막 `run()` 안에서 시작한
    회차마다의 `fragment_ids_this_run`(앱 전체 회차와 콜백만 도는 회차는 `[]`)이고, `messages` 는 그
    `run()` 이 내보낸 메시지다. 프래그먼트 회차의 `run()` 이 돌려주는 요소 트리는 그 회차가 보낸
    델타뿐이다(사이드바 위젯을 누르려면 앱 전체 회차를 한 번 돌린다).
    """

    storage: MemoryFragmentStorage = field(default_factory=MemoryFragmentStorage)
    fragment_queue: list[str] = field(default_factory=list)
    started: list[list[str]] = field(default_factory=list)
    messages: list[ForwardMsg] = field(default_factory=list)

    def fragment_of(self, widget_key: str) -> str:
        """그 키의 위젯을 그린 프래그먼트 — 브라우저가 프래그먼트 회차를 청할 때 보내는 id 다."""
        for message in self.messages:
            if message.WhichOneof("type") != "delta":
                continue
            delta = message.delta
            if delta.WhichOneof("type") != "new_element":
                continue
            kind = delta.new_element.WhichOneof("type")
            widget = getattr(delta.new_element, kind) if kind else None
            if str(getattr(widget, "id", "")).endswith(f"-{widget_key}"):
                assert delta.fragment_id, f"{widget_key} 는 프래그먼트 안이 아니다"
                return str(delta.fragment_id)
        raise AssertionError(f"{widget_key} 위젯을 그린 메시지가 없다")

    def fragment_keyed(self, key: str) -> str:
        """`@st.fragment(key=...)` 로 단 프래그먼트의 id. 이번 앱 전체 회차에 등록돼 있어야 한다."""
        (fragment_id,) = self.storage.resolve_target(key)
        return fragment_id


def install_fragment_browser(monkeypatch: pytest.MonkeyPatch) -> FragmentBrowser:
    """AppTest 의 러너를 프래그먼트 회차를 도는 러너로 바꾼다(그 시험 안에서만)."""
    state = FragmentBrowser()

    class _BrowserLikeRunner(LocalScriptRunner):
        def run(
            self,
            widget_state: WidgetStates | None = None,
            query_params: dict[str, Any] | None = None,
            timeout: float = 3,
            page_hash: str = "",
        ) -> ElementTree:
            # 서버처럼 저장소 하나를 계속 쥔다. 새로 만들면 프래그먼트 회차가 「모르는
            # 프래그먼트」를 건너뛴다.
            self._fragment_storage = state.storage
            if state.fragment_queue:
                # 생성자가 넣어 둔 앱 전체 회차 요청을 버린다. 남기면 프래그먼트 요청과 합쳐져
                # 앱 전체 회차가 된다(`ScriptRequests.request_rerun` 의 합치기 규칙).
                self._requests = ScriptRequests()
                self.request_rerun(
                    RerunData(
                        widget_states=widget_state,
                        page_script_hash=page_hash,
                        fragment_id_queue=list(state.fragment_queue),
                    )
                )
                if not self._script_thread:
                    self.start()
                require_widgets_deltas(self, timeout)
                tree = parse_tree_from_messages(self.forward_msgs())
            else:
                tree = super().run(widget_state, query_params, timeout, page_hash)
            state.started = [
                list(data.get("fragment_ids_this_run") or [])
                for event, data in zip(self.events, self.event_data, strict=False)
                if event == ScriptRunnerEvent.SCRIPT_STARTED
            ]
            state.messages = list(self.forward_msgs())
            return tree

    monkeypatch.setattr(app_test_module, "LocalScriptRunner", _BrowserLikeRunner)
    return state
