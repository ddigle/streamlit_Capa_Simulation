# Purpose: 알림 등록부(코드·단계·갈래·글)와 사건·상태 알림을 알림 칸에 보내는 표지 API 를 둔다.

"""알림 한 꼴(2026-11-03 결정 보드 D1 ~ D6 — 검수표 home-06 · home-08 · home-09).

알림은 **사건 · 상태 · 자리 글** 셋으로 가른다. 사건과 상태는 오른쪽 아래 알림창 한 꼴로 뜨고 머리
툴바 `Alarm` 패널에 쌓인다(`components/alert_center.py` — 이 브라우저 탭의 `sessionStorage`, 200줄 ·
12시간). 자리 글(빈 상태 · 잠금 까닭 · 폼 안 검증 · 확인 창)은 알림이 아니라 화면의 일부라 이 모듈을
지나지 않는다.

**단계 넷**(`LEVELS`): 알림(`info` — 알리기만) · 확인 필요(`check` — 결과를 믿기 전에 볼 것) · 조치
필요(`action` — 사용자가 무엇을 해야 풀린다) · 오류(`error` — 동작 · 계산 실패). 색은
`tokens.ALERT_*` 이고 단계는 색만으로 가르지 않는다 — 알림창 맨 앞에 단계 이름
글자(`LEVEL_LABELS`)가 붙는다.

**등록부**(`SPECS` → `REGISTRY`). 한 줄이 알림 하나다 — 코드 · 단계 · 갈래(사건 · 상태) · 이름 ·
기본 짧은 글 · 기본 전문. 코드는 `AB-01` 꼴(영문 대문자 2 ~ 4자 + 두 자리 수)의 짧은 고정 id 이고
**한 번 쓴 번호는 다시 쓰지 않는다**(지운 알림의 번호도 비워 둔다 — 분석 기록이 코드로 센다).
겹치거나 꼴이 어긋나면 이 모듈을 읽는 순간 멈춘다. 2단계(상태 알림 옮기기)는 `SPECS` 끝에 줄을
더하고 그 코드로 `state(...)` 를 부른다.

**보내는 길 — 표지.** 페이지가 `st.stop()` 하면 그 뒤에 만든 요소는 브라우저에 닿지 않아(AGENTS 9장)
알림 칸이 회차 끝에 모아 보낼 수 없다. 그래서 알림을 내는 자리가 **스타일만 든 `st.html`** 한
칸(`<style data-capa-alerts="…">` — 본문 자리를 먹지 않는 이벤트 칸 요소)에 알림을 JSON 으로 싣고,
알림 칸 JS 가 회차가 끝날 때(`stApp` 의 `data-test-script-state`) 문서의 표지를 한 번 훑는다.
**표지를 쓰는 함수(`state` · `flush` · `flash.render_flash`)는 부를 때마다 이벤트 칸에 정확히 한
자리를 쓴다** — 알릴 것이 없어도 빈 `<style></style>` 를 쓴다. 팝업(`st.dialog`) 본문 안에서는
이벤트 칸을 쓰지 않고 그 자리 칸 안에 숨은 표지(`<span hidden data-capa-alerts>`)를 그린다(`emit`).
프래그먼트 · 팝업 본문은 이벤트 칸에 갈래와 상관없이 같은 수만 써야 하므로(AGENTS 9장 「프래그먼트 ·
이벤트 칸」) 이 함수들을 갈래 안에서 부르지 말고 늘 같은 자리에서 부른다.

**사건 알림**(`event`) — 한 번 일어난 일(동작 결과 · 남의 저장 · 세션 이동 · 탭 상한 · 공식 복귀).
담기만 하고 그리지 않는다. 같은 회차의 다음 표지 자리(`render_flash` · `state` · `flush`)나 다음 앱
전체 회차의 알림 칸 data 가 보낸다. id 가 붙어 브라우저가 한 번만 띄운다. 같은 코드 + 같은 짧은 글이
앞 알림창이 떠 있는 동안이나 사라진 뒤 `REPEAT_WINDOW_SECONDS` 안에 다시 나면 새 칸을 쌓지 않고 앞
칸에 「×n」 을 붙여 시선을 끈다(D4). 버튼 곁 결과 알림(`queue_flash`)은 `render_flash` 가 사건
알림으로 바꿔 보낸다 — 성공 · 안내는 알림창으로만, 경고 · 오류는 버튼 곁에도 남는다(D3).

**상태 알림**(`state`) — 조건이 남아 있는 동안 회차마다 다시 그리던 경고. 그 자리를 그리는
회차마다(조건이 없어도 `active=False` 로) 부른다. 알림창은 **지문이 바뀔 때만** 뜨고, 자리에는
아무것도 그리지 않는다(D2 (나) — Alarm 에만 둔다). 조건이 사라지면(`active=False`) Alarm 줄에 「해소
hh:mm」 이 선다.

- **지문 = 코드 + 범위 + 내용**(`fingerprint`). 범위는 그 알림이 무엇에 대한 것인지다 — 시뮬레이션
  알림은 활성 리비전 `content_token` + 조회기간(`{"token": …, "period": [시작, 끝]}`), 설비 알림은
  (공통 대장 리비전, 일정 리비전) 쌍, 껍데기 알림은 없음(None). 시나리오나 조회기간을 바꾸면 수가
  같아도 새 알림이다. 내용은 글이 아니라 **구조 값**(건수 · 이름 목록)을 쓴다 — 문구만 고친 배포가
  같은 조건을 다시 띄우지 않게. 구조 값이 없으면 글을 쓴다.
- 판정은 브라우저 탭 하나가 한다(`sessionStorage` 의 「코드 + 범위 → 마지막 지문」 표) — 새로고침 ·
  테마 전환(새 세션)에도 같은 내용이 다시 뜨지 않는다. 화면이 달라도 같은 코드 + 범위 + 내용이면
  다시 띄우지 않는다.
- 닫힌 탭 · 접힌 펼침 안의 조건은 보일 때 부른다(그 탭이 열린 회차 — `stateful_tabs` 의 지금 탭
  라벨로 가른다).

**분석 기록(L2)은 아직 없다**(D6 (가) — usage-log 1단계와 함께). 붙일 자리는 `record_server_event`
하나와 스위치 `ALERT_LOG_SWITCH` 이고 지금은 아무것도 쓰지 않는다(`docs/TODO.md` 2장).

예 — 버튼 곁에 늘 그리던 상태 경고를 옮기는 꼴(2단계):

```python
# 전: 회차마다 큰 상자
if dropped:
    st.warning(f"소요대수에 들지 않은 수요가 있습니다 — {len(dropped)}건 …")
# 뒤: 회차마다 한 번(조건이 없어도) 부르고 자리에는 그리지 않는다
alerts.state(
    "ST-01",
    scope={"token": active.content_token, "period": [start, end]},
    content=sorted(dropped),
    active=bool(dropped),
    text=f"소요대수에 들지 않은 수요 {len(dropped)}건",
    full=f"소요대수에 들지 않은 수요가 있습니다 — {len(dropped)}건 …",
    scope_label=f"{scenario_name} · r{revision_no} · {start}–{end}",
)
```
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import time
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, Literal, TypedDict, cast, get_args

import streamlit as st
from streamlit.delta_generator import DeltaGenerator
from streamlit.delta_generator_singletons import get_last_dg_added_to_context_stack

Level = Literal["info", "check", "action", "error"]
Kind = Literal["event", "state"]

LEVELS: Final[tuple[Level, ...]] = get_args(Level)
# 단계 이름 글자 — 알림창 맨 앞 · Alarm 패널 줄 · 거르기 단추가 같은 글을 쓴다.
LEVEL_LABELS: Final[Mapping[Level, str]] = {
    "info": "알림",
    "check": "확인 필요",
    "action": "조치 필요",
    "error": "오류",
}
# 알림창이 떠 있는 시간(초). 알림은 짧게, 나머지는 읽고 손댈 시간을 둔다(기본값 — 설계 7장 끝).
POPUP_SECONDS: Final[Mapping[Level, int]] = {"info": 8, "check": 15, "action": 15, "error": 15}
# 알림창은 이만큼까지 쌓는다 — 넘치면 가장 오래된 칸을 걷는다.
POPUP_LIMIT: Final = 3
# 같은 사건 알림(코드 + 짧은 글)이 앞 알림창이 떠 있거나 사라진 뒤 이 안에 다시 나면 시선을
# 끈다(D4).
REPEAT_WINDOW_SECONDS: Final = 60
# 시선 끌기 — 창 가장자리 테두리가 이 시간 동안 easeOutQuad 로 알림창에 모인다(D4 A 한 겹).
ATTENTION_MS: Final = 450
ATTENTION_EASING: Final = "cubic-bezier(0.5, 1, 0.89, 1)"
# Alarm 기록 보관 — 이 브라우저 탭에 이 줄 수 또는 이 시간 가운데 먼저 닿는 쪽까지(D1 (가)).
HISTORY_ROWS: Final = 200
HISTORY_HOURS: Final = 12
# 알림창 글(짧은 글)은 이 글자 수 안팎이다 — 36rem 에서 두 줄. 넘치면 말줄임하고 전문은 패널 ·
# 로그에 둔다.
SHORT_LIMIT: Final = 60
# 표지를 다시 보내는 창(초). 표지를 그린 회차가 브라우저가 훑기 전에 다음 회차에 끊기면(아주 빠른 두
# 번 누름) 그 표지가 덮여 알림창이 뜨지 않는다 — 같은 자리를 이 안에 다시 그리는 회차가 같은 id 로
# 한 번 더 보낸다 (`again` — 브라우저는 id 로 한 번만 띄운다).
RESEND_SECONDS: Final = 3.0
# 알림에 딸린 표(`AlertTable`)에 싣는 행 수의 끝. 표지는 그 알림을 내는 회차마다 가고 기록은 이
# 브라우저 탭 `sessionStorage`(대개 5MB)에 쌓이므로 끝을 둔다 — 넘는 표는 화면이 본문 목록을 그대로
# 둔다(`components/state_alerts.alert_table`).
TABLE_ROW_LIMIT: Final = 2000

# 표지 속성 이름 — 알림 칸 JS 가 `style[data-capa-alerts]` 로 훑는다.
MARKER_ATTRIBUTE: Final = "data-capa-alerts"
# 분석 기록(L2 — 서버 익명 사건 줄)의 스위치 이름. usage-log 1단계가 같은 이름으로 켠다(D6 (가)).
# 지금은 읽지 않는다.
ALERT_LOG_SWITCH: Final = "CAPA_USAGE_LOG"

_CODE_PATTERN: Final = re.compile(r"^[A-Z]{2,4}-\d{2}$")
# 세션 칸. 이름은 알림 칸(`components/alert_center.py`)과 시험만 읽는다.
OUTBOX_KEY: Final = "alerts_outbox_v1"
PAGE_KEY: Final = "alerts_page_v1"
RECENT_KEY: Final = "alerts_recent_v1"


@dataclass(frozen=True)
class AlertSpec:
    """등록부 한 줄 — 코드 · 단계 · 갈래 · 이름 · 기본 짧은 글 · 기본 전문.

    `title` 은 그 알림이 무엇인지 한 줄(로그의 「갈래」 옆 · 시험이 읽는다)이다. `short`·`full` 은
    부르는 쪽이 글을 주지 않을 때 쓴다 — 글이 그때그때 다르면 비워 두고 부를 때 준다.
    """

    code: str
    level: Level
    kind: Kind
    title: str
    short: str = ""
    full: str = ""


# 등록부. **끝에만 더한다** — 차례는 뜻이 없지만 번호를 다시 쓰지 않는 규칙을 눈으로 보기 쉽다.
# - `FL-*` — 버튼 곁 결과 알림(`components/flash.queue_flash`)의 종류별 기본 코드. 칸마다 코드를
#   따로 두려면 `queue_flash(…, alert="XX-01")` 로 등록부의 사건 코드를 준다.
# - `TAB-*` — 화면 탭 줄 JS 가 내는 알림(`page_tabs.js`). 글은 `page_tabs.TEXT` 다.
SPECS: Final[tuple[AlertSpec, ...]] = (
    AlertSpec("FL-01", "info", "event", "동작 결과 — 성공"),
    AlertSpec("FL-02", "info", "event", "동작 결과 — 안내"),
    AlertSpec("FL-03", "check", "event", "동작 결과 — 경고"),
    AlertSpec("FL-04", "error", "event", "동작 결과 — 실패"),
    AlertSpec("TAB-01", "action", "event", "탭 상한 — 안 쓰는 탭을 닫아야 열린다"),
    AlertSpec("TAB-02", "check", "event", "새로고침 뒤 설비 시나리오가 공식으로 돌아옴"),
    AlertSpec("TAB-03", "check", "event", "테마 전환 뒤 설비 시나리오가 공식으로 돌아옴"),
    # 2단계 a — Static 계산 화면(`ST-*`) · HOME(`HM-*`) · 사이드바(`SB-*`) · 껍데기(`GL-*`). 번호는
    # 알림 자리 목록(설계 인벤토리)의 id 를 잇고, 같은 자리를 둘로 가른 것만 새 번호다.
    AlertSpec("ST-01", "check", "state", "소요대수에 들지 않은 수요 — 계획 쪽(조회기간)"),
    AlertSpec("ST-04", "check", "state", "PKG PLAN 적용 뒤 소요대수에 들지 않은 수요(전체 기간)"),
    AlertSpec("ST-05", "check", "state", "환산에서 빠진 계획 — 기준정보 없음 · 빈 생산수량"),
    AlertSpec("ST-06", "action", "state", "수율 표에서 값을 뺀 원천 행 — 빈 값 · 범위 밖"),
    AlertSpec("ST-09", "action", "event", "공용 표시순서가 바뀌어 적용 전 편집을 버림"),
    AlertSpec("ST-14", "check", "state", "대당 Capa 산출에서 뺀 기준(제외 기준정보)"),
    AlertSpec("ST-15", "check", "state", "대당 Capa 가 없어 소요대수 산출에서 뺀 경로"),
    AlertSpec("ST-17", "check", "state", "가용대수가 없어 빈칸인 공정 · 주차(표준 목표)"),
    AlertSpec("ST-20", "error", "event", "계산 화면을 그리지 못함 — 같은 글이면 한 번"),
    AlertSpec("ST-21", "info", "state", "소요기준 PKG 의 Buffer 밖 행 — 규칙대로 세지 않음"),
    AlertSpec("HM-01", "error", "event", "HOME 을 그리지 못함 — 같은 글이면 한 번"),
    AlertSpec("HM-02", "check", "state", "측정률 행이 없어 중립값 1.0 으로 계산한 경로"),
    AlertSpec("HM-04", "check", "state", "선행 B/O 반영 계획이 0 이하라 적용하지 못한 달"),
    AlertSpec("SB-14", "action", "event", "설비 시나리오를 합칠 수 없어 다른 리비전으로 옮겨 엶"),
    AlertSpec("SB-19", "action", "state", "옛 배포 설비 리비전이 있어 설비 저장이 막힘"),
    AlertSpec("SB-20", "action", "state", "옛 배포 공통 대장이 일정과 합쳐지지 않아 일정 없이 엶"),
    AlertSpec("GL-02", "check", "state", "시뮬레이션 DB 가 이 코드보다 새 버전"),
    AlertSpec("GL-06", "check", "state", "설비 DB 가 이 코드보다 새 버전"),
    # 2단계 b — 설비 · Space(`EQ-*`) · 실행 관리(`PD-*` · `RS-*` · `CS-*`) · Dynamic
    # 재공(`WIP-*`) · 시나리오 관리(`SC-*`) · 자동 갱신(`AU-*`) · Admin(`AD-*`) · 모듈(`MO-*`) ·
    # VOC(`VO-*`)(설계 6장 2 · 3). 화면을 그리지 못한 오류(「… 그리지 못함」)는 자리 `st.error` 를
    # 그대로 두고 같은 글이면 한 번만 뜨는 사건 알림을 더한다(`state_alerts.alert_page_error` —
    # ST-20 과 같은 꼴).
    AlertSpec("EQ-04", "check", "state", "이 설비 시나리오에 일정이 없는 호기"),
    AlertSpec("EQ-05", "check", "event", "남의 저장이 내 설비 편집을 버림"),
    AlertSpec("EQ-06", "check", "state", "Static 대비 일정 — 두 쪽 공정명이 맞지 않음"),
    AlertSpec(
        "EQ-07", "action", "state", "Static 대비 일정 — Cut-off 에 견줘 조회기간 시작이 늦음"
    ),
    AlertSpec("EQ-08", "error", "state", "Static 대비 일정 — Static 가용대수를 읽지 못함"),
    AlertSpec("EQ-09", "error", "event", "가용설비 현황을 그리지 못함 — 같은 글이면 한 번"),
    AlertSpec("EQ-10", "error", "event", "Space 현황을 그리지 못함 — 같은 글이면 한 번"),
    AlertSpec("EQ-12", "action", "state", "Cut-off 를 적지 않은 공정 — 가용대수 산출에서 빠짐"),
    AlertSpec("PD-01", "error", "event", "공정 Capa 상세를 그리지 못함 — 같은 글이면 한 번"),
    AlertSpec("PD-02", "check", "event", "넘겨받은 공정이 시나리오 · 조회기간에 없음"),
    AlertSpec("PD-03", "info", "event", "넘겨받은 달이 화면 기간 밖"),
    AlertSpec("RS-01", "error", "event", "필요 단축 일정을 그리지 못함 — 같은 글이면 한 번"),
    AlertSpec("CS-01", "error", "event", "제약 시뮬레이션을 그리지 못함 — 같은 글이면 한 번"),
    AlertSpec("CS-02", "check", "event", "넘겨받은 공정이 시나리오 · 조회기간에 없음"),
    AlertSpec("WIP-01", "error", "event", "재공 현황을 그리지 못함 — 같은 글이면 한 번"),
    AlertSpec(
        "WIP-04", "action", "state", "재공 현황 — 가용대수가 없어 기준선을 못 그린 공정 · 주차"
    ),
    AlertSpec("SC-01", "check", "state", "공식버전이 없음"),
    AlertSpec("SC-02", "error", "event", "시나리오 관리를 그리지 못함 — 같은 글이면 한 번"),
    AlertSpec("AU-01", "action", "state", "자동 갱신 예약이 멈춘 것 같음"),
    AlertSpec("AU-02", "action", "state", "자동 갱신 예약 스레드가 서 있지 않음"),
    AlertSpec("AD-01", "action", "state", "서버 시작 점검 결과 없음 · 못 읽음"),
    AlertSpec("AD-02", "action", "state", "운영인데 통합인증이 꺼짐"),
    AlertSpec("AD-03", "action", "state", "통합인증 서명 인증서 만료 임박"),
    AlertSpec("AD-04", "action", "state", "BigDataQuery 조회 SQL · 패키지 준비 안 됨"),
    AlertSpec("AD-05", "action", "state", "표시순서 분류값이 대소문자 · 공백만 달라 겹침"),
    AlertSpec("AD-06", "check", "state", "공정 표시명이 다른 공정의 원본명과 같음"),
    AlertSpec("AD-07", "error", "event", "Admin Area 를 그리지 못함 — 같은 글이면 한 번"),
    AlertSpec("MO-01", "error", "state", "모듈 폴더를 읽지 못함"),
    AlertSpec("MO-02", "action", "state", "모듈이 접두 없는 세션 키를 건드림"),
    AlertSpec("VO-01", "error", "event", "VOC 를 그리지 못함 — 같은 글이면 한 번"),
    AlertSpec(
        "SC-03", "check", "state", "옛 판이 저장해 가정 배치가 빠진 리비전이 있는 설비 시나리오"
    ),
)


def _registry(specs: Sequence[AlertSpec]) -> dict[str, AlertSpec]:
    """코드 → 줄. 꼴이 어긋나거나 겹치는 코드 · 모르는 단계 · 갈래는 읽는 순간 멈춘다."""
    registry: dict[str, AlertSpec] = {}
    for spec in specs:
        if not _CODE_PATTERN.match(spec.code):
            raise ValueError(f"알림 코드 꼴이 아닙니다(AB-01): {spec.code}")
        if spec.code in registry:
            raise ValueError(f"알림 코드가 겹칩니다: {spec.code}")
        if spec.level not in LEVELS or spec.kind not in get_args(Kind):
            raise ValueError(f"알림 단계 · 갈래가 어긋납니다: {spec.code}")
        registry[spec.code] = spec
    return registry


REGISTRY: Final[Mapping[str, AlertSpec]] = _registry(SPECS)

# `flash` 종류 → 기본 코드.
FLASH_CODES: Final[Mapping[str, str]] = {
    "success": "FL-01",
    "info": "FL-02",
    "warning": "FL-03",
    "error": "FL-04",
}


class AlertTable(TypedDict):
    """알림에 딸린 표 — Alarm 줄의 표 단추가 펼쳐 보이고 CSV 로 내려받는다(화면 본문에서 뺀 목록,
    예: 산출 결과 대당 Capa 의 「제외 기준정보」 — 2026-11-02 사용자 요청(검수표)).

    - `title` 단추 · 표 머리 글, `columns` 칸 이름, `rows` 행 값(JSON 값 — 수 · 글 · None),
    - `total` 원래 행 수(`rows` 보다 크면 앞 `TABLE_ROW_LIMIT` 행만 실은 것), `file` CSV 파일 이름,
    - `shown` 화면 표에서만 바꿔 보일 값(칸 → {원본: 표시명} — 공정 표시명. CSV 는 원본이다).
    """

    title: str
    columns: list[str]
    rows: list[list[str | int | float | None]]
    total: int
    file: str
    shown: dict[str, dict[str, str]]


class AlertNote(TypedDict, total=False):
    """표지 한 칸에 싣는 알림 하나(JSON). 알림 칸 JS 가 읽는 계약이다.

    - 사건: `id`(브라우저가 한 번만 띄운다) · `code` · `kind="event"` · `level` · `short` · `full`.
    - 상태: `kind="state"` · `scope`(지문 범위의 짧은 해시) · `fp`(지문) · `active` · 글.
    - 둘 다: `page`·`href`(그 화면 이름 · 주소 — 「그 화면으로」) · `tab`(그 화면 안 탭 이름 —
      「그 화면으로」 가 그 탭을 연다) · `scope_label`(로그의 범위 줄) · `cause`(계기) ·
      `detail`(원본 오류) · `table`(딸린 표 — `AlertTable`) · `origin`(버튼 곁 칸의 세션 key) ·
      `flash`(버튼 곁 결과의 종류) · `markdown` · `icon`(버튼 곁 원문 · 아이콘 — 시험 · 화면 확인이
      읽는다) · `again`(다시 보냄).
    """

    id: str
    code: str
    kind: Kind
    level: Level
    short: str
    full: str
    page: str
    href: str
    tab: str
    scope: str
    scope_label: str
    fp: str
    active: bool
    cause: str
    detail: str
    table: AlertTable
    origin: str
    flash: str
    markdown: str
    icon: str
    again: bool


def spec(code: str) -> AlertSpec:
    """등록부의 줄. 없는 코드는 `KeyError` — 등록하지 않은 코드로 알리지 않는다."""
    return REGISTRY[code]


def new_id() -> str:
    """사건 알림 id — 브라우저가 이 값으로 한 번만 띄운다."""
    return uuid.uuid4().hex[:16]


def short_text(text: str, limit: int = SHORT_LIMIT) -> str:
    """알림창 글 — 줄바꿈을 한 칸으로 접고 `limit` 자를 넘으면 말줄임한다."""
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 1].rstrip() + "…"


_MATERIAL_ICON: Final = re.compile(r":material/[a-z0-9_]+:")
_DIRECTIVE: Final = re.compile(r":[a-z]+(?:-[a-z]+)?\[([^\]]*)\]")
_CODE_SPAN: Final = re.compile(r"`([^`]*)`")
_STRONG: Final = re.compile(r"(\*\*|__)(.+?)\1")
_EMPHASIS: Final = re.compile(r"(?<![\\\w*])\*(?![\s*])(.+?)(?<![\s\\])\*")
_ESCAPED: Final = re.compile(r"\\([!-/:-@\[-`{-~])")


def plain_text(markdown: str) -> str:
    """마크다운 알림 글(버튼 곁 `st.success` 따위의 인자)을 알림창 · 패널의 평문으로 —
    아이콘(`:material/…:`) · 색 지시문(`:orange-badge[…]` → 안 글) · 코드 · 굵게 · 기울임 표지와
    구두점 막음(`literal_markdown` 의 `\\`)을 걷는다. 알림창은 글을 `textContent` 로 넣어 꾸밈이
    글자로 보이지 않게 한다."""
    text = _MATERIAL_ICON.sub("", markdown)
    text = _DIRECTIVE.sub(r"\1", text)
    text = _CODE_SPAN.sub(r"\1", text)
    text = _STRONG.sub(r"\2", text)
    text = _EMPHASIS.sub(r"\1", text)
    text = _ESCAPED.sub(r"\1", text)
    return " ".join(text.split())


def _digest(value: object) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def fingerprint(code: str, scope: object, content: object) -> str:
    """상태 알림의 지문 — 코드 + 범위 + 내용(구조 값). JSON 으로 고정해 해시한다(키 차례 무관)."""
    return _digest([code, scope, content])


def note_page(title: str, href: str) -> None:
    """이번 회차의 화면(이름 · 주소). `app.py` 가 앱 전체 회차마다 페이지 앞에서 부른다 — 표지가
    「화면」 · 「그 화면으로」 를 이 값으로 단다. 프래그먼트 회차는 앞 앱 전체 회차의 값을 그대로
    쓴다(같은 화면)."""
    st.session_state[PAGE_KEY] = {"page": title, "href": href}


def current_page() -> tuple[str, str]:
    value = st.session_state.get(PAGE_KEY)
    if not isinstance(value, dict):
        return "", ""
    page, href = value.get("page"), value.get("href")
    return (page if isinstance(page, str) else ""), (href if isinstance(href, str) else "")


def _base(code: str, level: Level | None, text: str | None, full: str | None) -> AlertNote:
    entry = spec(code)
    long_text = full or text or entry.full or entry.short or entry.title
    page, href = current_page()
    return AlertNote(
        code=code,
        kind=entry.kind,
        level=level or entry.level,
        short=short_text(text or entry.short or long_text),
        full=long_text,
        page=page,
        href=href,
    )


def event_note(
    code: str,
    *,
    text: str | None = None,
    full: str | None = None,
    level: Level | None = None,
    cause: str = "",
    detail: str = "",
    origin: str = "",
    alert_id: str | None = None,
    tab: str = "",
) -> AlertNote:
    """사건 알림 표지 한 칸(그리지 않는다). `flash.render_flash` 와 `event` 가 쓴다.

    `alert_id` 를 고정 값(같은 글이면 같은 id — `fingerprint`)으로 주면 브라우저 탭이 그 알림을 한
    번만 띄운다 — 회차마다 다시 그리는 자리 오류(화면을 그리지 못함)가 그 꼴이다
    (`components/state_alerts.alert_page_error`)."""
    note = _base(code, level, text, full)
    note["id"] = alert_id or new_id()
    for name, value in (("cause", cause), ("detail", detail), ("origin", origin), ("tab", tab)):
        if value:
            note[name] = value  # type: ignore[literal-required]
    return note


def event(
    code: str,
    *,
    text: str | None = None,
    full: str | None = None,
    level: Level | None = None,
    cause: str = "",
    detail: str = "",
) -> None:
    """사건 알림 하나를 담는다 — **그리지 않는다**(이벤트 칸을 쓰지 않으니 어느 갈래에서 불러도
    된다).

    같은 회차의 다음 표지 자리(`render_flash` · `state` · `flush`)가 보내고, 그런 자리가 없으면 다음
    앱 전체 회차의 알림 칸 data 가 보낸다(콜백에서 담은 것은 바로 그 회차다). `text` 는 알림창 짧은
    글(60자 안팎), `full` 은 패널 · 로그의 전문, `cause` 는 로그의 계기(「「저장」 누름」), `detail`
    은 원본 오류 글이다.
    """
    note = event_note(code, text=text, full=full, level=level, cause=cause, detail=detail)
    outbox = st.session_state.get(OUTBOX_KEY)
    st.session_state[OUTBOX_KEY] = [*outbox, note] if isinstance(outbox, list) else [note]


def drain_outbox() -> list[AlertNote]:
    """담아 둔 사건 알림을 꺼내 비운다."""
    outbox = st.session_state.pop(OUTBOX_KEY, None)
    if not isinstance(outbox, list):
        return []
    return [cast(AlertNote, note) for note in outbox if isinstance(note, dict)]


def state(
    code: str,
    *,
    scope: object,
    content: object,
    active: bool,
    text: str | None = None,
    full: str | None = None,
    level: Level | None = None,
    scope_label: str = "",
    cause: str = "",
    detail: str = "",
    tab: str = "",
    table: AlertTable | None = None,
) -> None:
    """상태 알림 — 그 조건을 보는 회차마다(없어도 `active=False`) 부른다. **이벤트 칸에 늘 한 자리를
    쓴다.**

    `scope` · `content` 는 지문 재료(구조 값 — 모듈 설명), `text` · `full` 은 조건이 있을 때의 짧은
    글 · 전문, `scope_label` 은 로그의 범위 줄(「시나리오 · rN · 조회기간」)이다. `tab` 은 그 화면
    안 탭 이름(아이콘 없이 — 「그 화면으로」 가 그 탭을 열고 줄의 화면 칸이 「화면 › 탭」 이다),
    `table` 은 Alarm 줄에서 펼쳐 볼 표(`AlertTable` — 조건이 있을 때만 싣는다)다. 자리에는 아무것도
    그리지 않는다(D2 (나)).
    """
    note = _base(code, level, text, full)
    note["kind"] = "state"
    note["scope"] = _digest([code, scope])
    note["fp"] = fingerprint(code, scope, content) if active else ""
    note["active"] = active
    for name, value in (
        ("scope_label", scope_label),
        ("cause", cause),
        ("detail", detail),
        ("tab", tab),
    ):
        if value:
            note[name] = value  # type: ignore[literal-required]
    if active and table is not None:
        note["table"] = table
    emit([note])


def flush() -> None:
    """담아 둔 사건 알림을 지금 보낸다 — 이벤트 칸에 늘 한 자리를 쓴다(없으면 빈 칸)."""
    emit([])


def emit(notes: Sequence[AlertNote], *, slot: DeltaGenerator | None = None) -> None:
    """표지 한 칸 — 담아 둔 사건 알림과 `notes` 를 한 표지에 싣는다.

    - 보통은 스타일만 든 `st.html`(이벤트 칸 한 자리)이다. 알릴 것이 없으면 빈 `<style></style>` 를
      쓴다 — 갈래와 상관없이 부를 때마다 정확히 한 자리다.
    - **팝업(`st.dialog`) 본문 안에서는 이벤트 칸을 쓰지 않는다.** 팝업 호스트는 열렸든 닫혔든
      이벤트 칸에 정확히 한 자리(팝업 블록 또는 빈 스타일)를 써야 하는데(AGENTS 9장), 본문이 스타일
      표지를 더 쓰면 연 회차만 한 자리가 는다. 그때는 `slot`(없으면 이 자리에 세운 칸) 안에 숨은
      표지(`<span hidden data-capa-alerts>`)를 그린다 — 알릴 것이 없으면 그리지 않는다(칸은 늘
      선다).
    """
    sending = [*drain_outbox(), *notes]
    payload = html.escape(json.dumps(sending, ensure_ascii=False), quote=True) if sending else ""
    if in_dialog(slot):
        holder = slot if slot is not None else st.container()
        if sending:
            holder.html(f'<span hidden {MARKER_ATTRIBUTE}="{payload}"></span>')
        return
    if not sending:
        st.html("<style></style>")
        return
    st.html(f'<style {MARKER_ATTRIBUTE}="{payload}"></style>')


def in_dialog(target: DeltaGenerator | None = None) -> bool:
    """지금 그리는 자리가 팝업(`st.dialog`) 본문 안인가 — `target`(없으면 지금 문맥의 마지막 칸)의
    조상 블록에 `dialog` 가 있는가. Streamlit 1.63 의 비공식 속성(`_ancestor_block_types` — 팝업
    겹침 검사가 쓰는 것)이라 못 읽으면 밖으로 본다."""
    dg = target if target is not None else get_last_dg_added_to_context_stack()
    if dg is None:
        return False
    try:
        return "dialog" in set(dg._ancestor_block_types)
    except AttributeError:
        return False


def remember_sent(key: str, note: AlertNote) -> None:
    """`key` 칸이 방금 보낸 사건 알림을 적는다 — 그 칸을 `RESEND_SECONDS` 안에 다시 그리는 회차가
    같은 id 로 한 번 더 보낸다(`recent_again`)."""
    recent = st.session_state.get(RECENT_KEY)
    marks = recent if isinstance(recent, dict) else {}
    marks[key] = (dict(note), time.monotonic())
    st.session_state[RECENT_KEY] = marks


def recent_sent(key: str) -> AlertNote | None:
    """`key` 칸이 `RESEND_SECONDS` 안에 보낸 사건 알림(없거나 지났으면 None)."""
    recent = st.session_state.get(RECENT_KEY)
    entry = recent.get(key) if isinstance(recent, dict) else None
    if not (isinstance(entry, tuple) and len(entry) == 2 and isinstance(entry[0], dict)):
        return None
    note, moment = entry
    if not isinstance(moment, float) or time.monotonic() - moment >= RESEND_SECONDS:
        return None
    return cast(AlertNote, dict(note))


def recent_again(key: str) -> AlertNote | None:
    """`recent_sent` 의 다시 보내는 꼴(`again`) — 브라우저는 같은 id 를 다시 띄우지 않는다."""
    note = recent_sent(key)
    if note is None:
        return None
    again = cast(AlertNote, dict(note))
    again["again"] = True
    return again


def marker_notes(body: str) -> list[dict[str, Any]]:
    """표지 HTML 한 칸에서 알림 목록을 읽는다(시험 · 화면 확인 도우미). 표지가 아니면 빈 목록."""
    match = re.search(rf'{MARKER_ATTRIBUTE}="([^"]*)"', body)
    if match is None:
        return []
    value = json.loads(html.unescape(match.group(1)))
    return [note for note in value if isinstance(note, dict)] if isinstance(value, list) else []


def record_server_event(note: Mapping[str, object]) -> None:
    """분석 기록(L2 — 서버 익명 사건 줄)을 붙일 자리. **지금은 아무것도 하지 않는다**(D6 (가) —
    usage-log 1단계와 함께 만든다). 그때 `ALERT_LOG_SWITCH` 실행 줄 환경변수가 켜졌을 때만 코드 ·
    단계 · 화면 코드 · 분 단위 시각 · 배포 번호 · 세션 표지 · 갈래(new · change · resolved · event ·
    repeat)를 한 줄 덧붙이고 글 · 이름 · 값 · 지문 · 오류 원문 · loginid 는 남기지 않는다(설계
    3-4)."""
    return None
