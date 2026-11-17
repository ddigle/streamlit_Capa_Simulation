# Purpose: 앱이 뜨기 전 같은 포트에서 상태 검사에 답하고 시작 단계 · 머무는 까닭을 값 없이 보인다.
"""시작 스크립트의 임시 응답.

C-DEP 의 상태 검사는 시작 제한이 1분이고 무엇을 묻는지 모른다(TCP · `/` · `/_stcore/health`). 설치는
240초까지, 두 DB 받기는 그보다 오래 걸릴 수 있어 시작 스크립트가 **맨 앞에서** 앱의 포트를 잡고 그
셋에 다 답한다. 끝나면 소켓을 닫고 앱이 같은 포트를 잡는다.

**로그인 전 화면이다.** 고정 글 · 실패 갈래 낱말(`FAILURE_LABELS`) · 시각 · 횟수만
싣는다 — 데이터 · 주소 · 키 · 버킷 이름이 들어갈 칸이 없다. 이 서버에는 셸 · 로그가 없어
이 화면이 머문 까닭의 유일한 단서다.

**꼴은 앱 밖 화면의 공통 틀이다** — 4px 강조 줄 · 앱 마크 · 「S.PKG CAPA」/「AX
Management」 · 상태 표지(낱말 + 색) · 제목 · 까닭 · 단계 줄 「준비 · 점검 → 설치 →
데이터 받기 → 앱」(받지 않는 서버는 받기 칸 없음) · 값 줄(지난 시간 · 다음 시도 n초) ·
문의 줄 · 참고 줄 · 접힌 「관리자용 진단」. 앱이 서기 전의 단순한 꼴(스크립트 · 단계 줄 ·
값 줄)은 이 화면 몫이고, 낱말(표지 셋 · 「관리자용 진단」 · 「문의」 · 「참고」)과 표지 색 역할은
로그인 화면 틀(`auth/page_frame.py` 의 `CHIP_WORDS` · `CHIP_ROLES`)과 한 표다 — 그 표를
불러 쓴다. 포트를 잡는 첫 순간이라 Streamlit · `design.tokens` 를 불러오지 않는다
(`page_frame` 도 tokens 를 그릴 때만 부른다) — 두 팔레트는 상수(`PALETTES`)이고 시험이 토큰과
맞댄다. 밝게 · 어둡게는 `prefers-color-scheme` 로 고른다(앱 테마를 모르는 화면). 글은 틀처럼
띄어쓰기에서만 줄을 바꾸고(`word-break: keep-all`) 띄어쓰기 없는 긴 메일 · 주소만 접는다.

**한 상태 → 한 보기.** 시작 스크립트는 단계 · 받기 시도 · 실패만 알리고(`Stage.begin` ·
`step` · `attempt` · `fail`), 보이는 글은 순수 함수 `stage_view` 하나가 정한다 — 쪽
HTML 과 `/_capa_stage` 가 같은 보기에서 나온다. 시도가 실제 내려받기로 넘어갔는지는 시작
스크립트가 준 물음(`download_seen` — 받기 하위 프로세스가 남기는 표지 파일)을 상태를 읽을 때 묻고
판을 올린다 — 받기는 하위 프로세스라 시작 스크립트가 그 순간을 알릴 수 없다.

- 모든 경로의 GET · HEAD · POST 가 200 + 안내 쪽이다. `/_stcore/health` 는 200 `ok` 이고 그 밖의
  `/_stcore/*` 는 503 이다 — 옛 탭의 재접속이 HTML 을 JSON 으로 읽지 않게.
- 답마다 `X-Capa-Stage: 1` 표가 붙는다. 쪽의 JS 는 health 가 `ok` 이고 표가 **없을** 때만(앱의 답)
  앱으로 간다 — 앞단의 502 · Streamlit 준비 전 503 은 표가 없어도 기다린다.
- `/_capa_stage` 는 세 줄이다 — 제목 · 값 한 줄(옛 쪽 스크립트가 읽는 꼴 그대로) ·
  JSON(판 번호 · 재시작 띠 글 · 서버 시각). 열어 둔 앱 탭의 재시작 띠
  (`components/sso_reconnect.py`)도 이 줄을 읽는다.
- 쪽의 JS 는 3초마다 health · 상태를 묻고, 판이 바뀌면 쪽을 다시 받아 본문만 갈아
  끼운다. 지난 시간 · 남은 초는 1초마다 서버 시각 차로 센다(브라우저 시계를 믿지 않는다).
- 앱이 답하면 **처음 연 주소를 다시 읽는다** — 재시작 중에 누른 로그아웃 · 로그인 경로도
  그대로 이어진다. POST 로 받은 쪽(콜백 form_post 등)과 콜백 경로만 바탕 주소로 간다 —
  다시 읽으면 다시 보내거나 쓴 코드를 되풀이한다. 예외는 거절 화면의 「접속 권한 신청」
  (`REGISTER_PATH` POST)이다 — 신청이 앱에 닿지 않았으니 「다시 눌러 주세요」 한 줄
  (`NOTE_REGISTER_LOST`)을 띄우고, 앱이 뜨면 같은 주소를 GET 으로 연다(다시 보내지 않는다 —
  앱이 그 GET 을 거절 화면으로 보내 단추가 다시 선다). 요청 경로는 HTML 에 싣지 않는다(표지
  `data-return` 만).
- 질의까지 찍는 기본 요청 기록을 끈다 — `/auth/callback?code=…` 가 표준 오류에 남는다.
- POST 본문은 상한 안에서 읽어 버린다 — 안 읽고 닫으면 보낸 쪽이 `BrokenPipe` 로 끊긴다.
- 듣는 소켓은 비상속이다(Python 기본) — 시작 스크립트의 자식(pip · aws)이 포트를 물지 않는다.
"""

from __future__ import annotations

import html
import json
import math
import os
import re
import socket
import socketserver
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Final
from urllib.parse import quote, urlsplit

from capa_simulation.auth.names import CALLBACK_PATH, ENV_ACCESS_CONTACT, REGISTER_PATH
from capa_simulation.auth.page_frame import (
    CHIP_ROLES,
    CHIP_WORDS,
    CONTACT_LABEL,
    DIAGNOSTIC_LABEL,
    REFERENCE_LABEL,
)
from capa_simulation.services.object_storage_manifest import (
    DATASET_LABELS,
    FAILURE_CLI_MISSING,
    FAILURE_CONFIG,
    FAILURE_CORRUPT,
    FAILURE_DENIED,
    FAILURE_DISK_FULL,
    FAILURE_DIVERGED,
    FAILURE_FORKED,
    FAILURE_LABELS,
    FAILURE_NO_BUCKET,
    FAILURE_OTHER,
    FAILURE_REMOTE_EMPTY,
    FAILURE_SCHEMA_NEWER,
    FAILURE_TIMEOUT,
    FAILURE_UNREACHABLE,
)
from capa_simulation.settings import APP_LABEL, APP_SUBTITLE, app_contact_email

STAGE_HEADER: Final = "X-Capa-Stage"
HEALTH_SUFFIX: Final = "/_stcore/health"
STREAMLIT_INFIX: Final = "/_stcore/"
STATUS_SUFFIX: Final = "/_capa_stage"
SOCKET_TIMEOUT_SECONDS: Final = 5
DISCARD_LIMIT_BYTES: Final = 1024 * 1024
_DISCARD_CHUNK: Final = 64 * 1024
_BASE_PATH: Final = re.compile(r"(?:/[A-Za-z0-9._~-]+)*/?")
# 창구 글 — 통합인증 설정(`auth/config._check_plain`)과 같은 문턱. 넘으면 싣지 않는다.
_CONTACT_LIMIT: Final = 500
_CONTROL: Final = re.compile(r"[\x00-\x1f\x7f]")

# 단계 — 시작 스크립트가 차례대로 알린다. 「앱」 은 넘긴 뒤라 지금 칸이 되지 않는다.
STEP_CHECK: Final = "check"
STEP_INSTALL: Final = "install"
STEP_PULL: Final = "pull"
STEP_APP: Final = "app"
STEP_LABELS: Final[Mapping[str, str]] = {
    STEP_CHECK: "준비 · 점검",
    STEP_INSTALL: "설치",
    STEP_PULL: "데이터 받기",
    STEP_APP: "앱",
}
NOW_WORD: Final = "지금"

# 상태 표지 — 앱 밖 화면의 공통 다섯 낱말 가운데 이 화면이 쓰는 셋(낱말 · 색 역할은 로그인 화면
# 틀의 표). 색은 낱말과 늘 함께다(색만으로 뜻을 싣지 않음). 결(tone)은 이 화면의 이름이다 —
# `/_capa_stage` 셋째 줄 · 쪽 서식의 `tone-*` 가 쓰는 값이라 그대로 두고, 틀의 표지 키로 잇는다.
TONE_START: Final = "start"
TONE_RETRY: Final = "retry"
TONE_CHECK: Final = "check"
TONE_CHIPS: Final[Mapping[str, str]] = {
    TONE_START: "starting",
    TONE_RETRY: "retry",
    TONE_CHECK: "maintenance",
}
CHIP_STARTING: Final = CHIP_WORDS[TONE_CHIPS[TONE_START]]
CHIP_RETRY: Final = CHIP_WORDS[TONE_CHIPS[TONE_RETRY]]
CHIP_MAINTENANCE: Final = CHIP_WORDS[TONE_CHIPS[TONE_CHECK]]

TITLE_STARTING: Final = "앱을 시작하는 중입니다"
TITLE_PULLING: Final = "데이터를 받는 중입니다"
TITLE_REMOTE_EMPTY: Final = "데이터를 처음 올리는 중입니다"
TITLE_TRANSIENT: Final = "저장소에 잠시 닿지 못했습니다"
# 「다시 시도」 판의 제목 · 열어 둔 탭의 띠 글은 저장소에 닿지 못함 · 시간 초과일 때만 그
# 원인을 말하고, 원인을 모르는 실패(`other` 등)는 원인을 말하지 않는다 — 표지 · 까닭 · 값 줄은
# 같다.
STORE_NOT_REACHED: Final = (FAILURE_UNREACHABLE, FAILURE_TIMEOUT)
TITLE_TRANSIENT_UNKNOWN: Final = "데이터를 잠시 받지 못했습니다"
BAND_TRANSIENT: Final = "저장소에 잠시 닿지 못함 · 다시 시도 중"
BAND_TRANSIENT_UNKNOWN: Final = "데이터를 잠시 받지 못함 · 다시 시도 중"
NOTE_AUTO: Final = "끝나면 저절로 앱으로 넘어갑니다."
NOTE_MINUTES: Final = "몇 분 걸릴 수 있습니다."
NOTE_NO_CICD: Final = "받는 동안 CI/CD 를 다시 누르면 받기가 처음부터 다시 시작됩니다."
REASON_REMOTE_EMPTY: Final = (
    "개발자가 데이터를 서버에 처음 올리고 있습니다. 끝나면 저절로 열립니다."
)
REASON_TRANSIENT: Final = "저절로 다시 시도합니다."
NOTE_LONG_RETRY: Final = "계속되면 문의처에 알려 주세요."
# 재시작 틈에 이 응답이 대신 받은 「접속 권한 신청」(거절 화면 단추 — `auth/web.REGISTER_LABEL` 과
# 같은 이름, 시험이 맞댄다).
NOTE_REGISTER_LOST: Final = "「접속 권한 신청」 이 닿지 않았습니다 — 앱이 열리면 다시 눌러 주세요."
# 쪽이 앱으로 갈 길(`data-return`) — 처음 연 주소 · 바탕 주소 · 같은 주소를 GET 으로(잃은 신청).
RETURN_HERE: Final = "here"
RETURN_BASE: Final = "base"
RETURN_RESEND: Final = "resend"
NOSCRIPT_NOTE: Final = "저절로 넘어가지 않으면 잠시 뒤 새로고침하세요."
# 사람이 고쳐야 풀리는 갈래(시작 스크립트가 300초마다 다시 본다) — (제목, 까닭). 표지는 「점검 중」.
HUMAN_SCREENS: Final[Mapping[str, tuple[str, str]]] = {
    **dict.fromkeys(
        (FAILURE_CONFIG, FAILURE_CLI_MISSING, FAILURE_DENIED, FAILURE_NO_BUCKET),
        (
            "서버 설정 때문에 시작하지 못했습니다",
            "개발자가 배포 설정을 고쳐야 열립니다. 문의처에 알려 주세요.",
        ),
    ),
    FAILURE_DISK_FULL: (
        "서버 디스크가 모자라 시작하지 못했습니다",
        "개발자가 디스크를 늘려야 열립니다. 문의처에 알려 주세요.",
    ),
    **dict.fromkeys(
        (FAILURE_CORRUPT, FAILURE_FORKED),
        (
            "데이터를 되돌려야 열립니다",
            "개발자가 데이터를 앞 판으로 되돌려야 합니다. 문의처에 알려 주세요.",
        ),
    ),
    FAILURE_DIVERGED: (
        "서버 데이터가 정본과 달라 멈췄습니다",
        "개발자의 판단이 필요합니다. 문의처에 알려 주세요.",
    ),
    FAILURE_SCHEMA_NEWER: (
        "앱 판이 데이터보다 오래됐습니다",
        "개발자가 최신 판으로 다시 배포해야 열립니다.",
    ),
}
# 관리자가 앱 밖에서 고치면(되돌리기 — rollback) 다음 확인이 그대로 받기가 되는 사람 갈래. 그 확인이
# 실제 내려받기로 넘어간 뒤(`StageState.downloading`)는 잠시 닿지 못한 뒤의 다시 받기와 같은 값 줄 ·
# 노트다(이관 전 `remote_empty` 의 처음 올리기 — init — 도 같다). 고치기 전이어도 확인이 멤버를
# 받기 시작하면(깨진 멤버는 받는 도중에 드러난다) 그동안은 그 값 줄이다. 받기 전에 머무는 확인과
# 다른 사람 갈래(CI/CD 로 고침)는 「다시 확인하는 중」 이다.
REPAIRED_IN_PLACE: Final = (FAILURE_CORRUPT, FAILURE_FORKED)
# 경우별 할 일 한 줄(접힌 「관리자용 진단」).
HUMAN_ACTIONS: Final[Mapping[str, str]] = {
    FAILURE_CONFIG: "C-DEP 환경변수 표를 고친 뒤 CI/CD",
    FAILURE_CLI_MISSING: "이미지 문제 — 사외에 요청",
    FAILURE_DENIED: "S3 키 · 권한 확인(키 둘을 함께 다시 발급했는지)",
    FAILURE_NO_BUCKET: "버킷 이름 확인(CAPA_S3_BUCKET)",
    FAILURE_DISK_FULL: "C-DEP 담당에게 컨테이너 디스크 늘리기 요청",
    FAILURE_CORRUPT: "앱 관리자(개발자) PC 에서 generations → rollback(런북 「세대 되돌리기」)",
    FAILURE_FORKED: "앱 관리자(개발자) PC 에서 generations → rollback(런북 「세대 되돌리기」)",
    FAILURE_DIVERGED: (
        "CI/CD 를 다시 누르면 풀리지만 이 서버에서 정본에 올리지 못한 변경은 사라집니다"
    ),
    FAILURE_SCHEMA_NEWER: "앞 판으로 되돌릴 수 없음 — 최신 배포를 다시 CI/CD(런북 4-2)",
}
_ENV_NAME: Final = re.compile(r"[A-Z][A-Z0-9_]{0,63}")
_DATASET_WORDS: Final[Mapping[str, str]] = {
    str(name): word for name, word in DATASET_LABELS.items()
}
_MIB: Final = 1024 * 1024
LABEL_NEXT_TRY: Final = "다음 시도"
LABEL_NEXT_CHECK: Final = "다음 확인"
CLOCK_WORD: Final = "지난 시간"
DIAGNOSTICS_SUMMARY: Final = DIAGNOSTIC_LABEL
# 잠시 닿지 못함이 이만큼 이어지면 문의 줄을 세운다.
LONG_RETRY_SECONDS: Final = 600

# 두 팔레트의 값 — `design/tokens.py` 의 같은 이름 값과 시험이 맞댄다
# (`tests/test_container_stage.py`). 이 화면은 tokens 를 불러오지 않는다(모듈 설명).
# CSS 변수 이름 → 토큰 이름. 표지 색(`chip-<틀의 표지 키>`)은 틀의 역할 표에서 온다 — 틀이 역할을
# 바꾸면 아래 상수에 그 토큰이 없을 때 시험이 잡는다.
PALETTE_ROLES: Final[tuple[tuple[str, str], ...]] = (
    ("fg", "TEXT"),
    ("muted", "TEXT_MUTED"),
    ("bg", "SURFACE_PAGE"),
    ("card", "SURFACE"),
    ("line", "BORDER"),
    ("accent", "ACCENT"),
    ("warm", "BRAND_DIE_WARM"),
    *((f"chip-{chip}", CHIP_ROLES[chip]) for chip in TONE_CHIPS.values()),
)
PALETTES: Final[Mapping[str, Mapping[str, str]]] = {
    "light": {
        "TEXT": "#18181B",
        "TEXT_MUTED": "#646973",
        "SURFACE_PAGE": "#F7F8FA",
        "SURFACE": "#FFFFFF",
        "BORDER": "#DDE0E5",
        "ACCENT": "#0F766E",
        "BRAND_DIE_WARM": "#D29A3A",
        "ALERT_CHECK": "#B45309",
        "ALERT_ACTION": "#1D4ED8",
    },
    "dark": {
        "TEXT": "#E9E9EC",
        "TEXT_MUTED": "#9B9BA6",
        "SURFACE_PAGE": "#131316",
        "SURFACE": "#1C1C21",
        "BORDER": "#35353E",
        "ACCENT": "#2DD4BF",
        "BRAND_DIE_WARM": "#D29A3A",
        "ALERT_CHECK": "#F0B37A",
        "ALERT_ACTION": "#9DB8FF",
    },
}
# `tokens.FONT_FAMILY` 와 같은 값(시험이 맞댄다) — 웹 글꼴을 들이지 않는다.
FONT_FAMILY: Final = "Noto Sans KR, Malgun Gothic, 'Apple SD Gothic Neo', sans-serif"
# 앱 메인 심볼(C 링 + 3×3 다이) — `static/icons/capa_mark.svg` 와 같은 모양(시험이
# 맞댄다). 이 응답은 정적 파일을 서빙하지 않아 쪽 안에 넣는다.
MARK_RING_PATH: Final = "M83.59 26.48 A41 41 0 1 0 83.59 73.52"
MARK_DIE_ORIGINS: Final = (28, 44, 60)


def _mark_svg() -> str:
    dies = "".join(
        f'<rect class="{"core" if (x, y) == (44, 44) else "die"}" x="{x}" y="{y}" width="12" '
        'height="12" rx="2"/>'
        for y in MARK_DIE_ORIGINS
        for x in MARK_DIE_ORIGINS
    )
    return (
        '<svg class="mark" viewBox="0 0 100 100" width="30" height="30" aria-hidden="true">'
        f'<path class="ring" d="{MARK_RING_PATH}" fill="none" stroke-width="9" '
        f'stroke-linecap="round"/>{dies}</svg>'
    )


_CSS_BODY: Final = """
* { box-sizing: border-box; }
html, body { margin: 0; }
body { min-height: 100vh; display: flex; justify-content: center; align-items: flex-start;
  padding: 48px 16px; background: var(--bg); color: var(--fg); font-family: var(--font);
  line-height: 1.6; word-break: keep-all; overflow-wrap: anywhere; }
main { width: 100%; max-width: 640px; background: var(--card); border: 1px solid var(--line);
  border-top: 4px solid var(--accent); border-radius: 12px; padding: 24px 28px; }
.brand { display: flex; align-items: center; gap: 10px; margin: 0 0 20px; }
.brand strong { display: block; font-size: 1rem; line-height: 1.2; }
.brand span { display: block; font-size: .78rem; color: var(--muted); line-height: 1.3; }
.mark { flex: none; }
.mark .ring { stroke: var(--fg); }
.mark .die { fill: var(--accent); }
.mark .core { fill: var(--warm); }
.chip { display: inline-flex; align-items: center; gap: 6px; margin: 0 0 10px; padding: 1px 10px;
  border: 1px solid currentColor; border-radius: 999px; font-size: .8rem; font-weight: 700; }
.chip::before { content: ""; width: 8px; height: 8px; border-radius: 50%;
  background: currentColor; }
__TONE_RULES__
h1 { font-size: 1.3rem; line-height: 1.4; margin: 0 0 8px; }
p { margin: 6px 0; }
.steps { list-style: none; display: flex; flex-wrap: wrap; gap: 4px 8px; padding: 0;
  margin: 14px 0 8px; font-size: .85rem; color: var(--muted); }
.steps li { display: inline-flex; align-items: center; gap: 6px; }
.steps li + li::before { content: "→"; color: var(--muted); font-weight: 400; }
.steps li.now { color: var(--accent); font-weight: 700; }
.steps li.now b { font-size: .72rem; border: 1px solid currentColor; border-radius: 4px;
  padding: 0 4px; }
.value { font-weight: 700; font-variant-numeric: tabular-nums; }
.lost { font-weight: 700; }
.note { color: var(--muted); font-size: .9rem; }
.contact { margin-top: 16px; font-size: .9rem; }
a { color: var(--accent); }
.ref { margin-top: 16px; font-size: .78rem; color: var(--muted); user-select: all; }
details { margin-top: 4px; font-size: .85rem; color: var(--muted); }
summary { cursor: pointer; }
details ul { margin: 6px 0 0; padding-left: 18px; }
@media (max-width: 480px) { body { padding: 16px; } main { padding: 20px 16px; } }
"""


def page_css() -> str:
    """밝은 · 어두운 팔레트 변수 + 본문 규칙. 표지 결(`tone-*`)은 틀의 표지 색 변수를 쓴다."""

    def variables(mode: str) -> str:
        palette = PALETTES[mode]
        return " ".join(f"--{name}: {palette[role]};" for name, role in PALETTE_ROLES)

    tones = "\n".join(
        f".tone-{tone} {{ color: var(--chip-{chip}); }}" for tone, chip in TONE_CHIPS.items()
    )
    return (
        f":root {{ color-scheme: light dark; {variables('light')} --font: {FONT_FAMILY}; }}\n"
        f"@media (prefers-color-scheme: dark) {{ :root {{ {variables('dark')} }} }}"
        f"{_CSS_BODY.replace('__TONE_RULES__', tones)}"
    )


# ---------------------------------------------------------------- 상태 → 보기
@dataclass(frozen=True)
class StageFacts:
    """머문 까닭의 이름 · 수(값 아님 — 2026-11-14 보드 D9) — 접힌 「관리자용 진단」 이 싣는다.
    모르면 비운다. 환경변수 이름은 꼴(대문자 · 숫자 · 밑줄)만, DB 이름은 아는 것만 지난다."""

    missing_environment: tuple[str, ...] = ()
    needed_bytes: int | None = None
    free_bytes: int | None = None
    seq: int | None = None
    datasets: tuple[str, ...] = ()
    file_version: int | None = None
    code_version: int | None = None

    def checked(self) -> StageFacts:
        def count(value: int | None) -> int | None:
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                return None
            return value

        return StageFacts(
            missing_environment=tuple(
                name for name in self.missing_environment if _ENV_NAME.fullmatch(name)
            ),
            needed_bytes=count(self.needed_bytes),
            free_bytes=count(self.free_bytes),
            seq=count(self.seq),
            datasets=tuple(name for name in _DATASET_WORDS if name in self.datasets),
            file_version=count(self.file_version),
            code_version=count(self.code_version),
        )


@dataclass(frozen=True)
class StageState:
    """시작 스크립트가 알린 것. 시각은 모두 서버 시계(epoch 초)다."""

    started_at: float
    managed: bool = False
    step: str = STEP_CHECK
    # 지금(받는 중) 또는 마지막(실패한) 받기 시도 번호.
    attempt: int = 0
    trying: bool = False
    # 이 시도가 실제 내려받기로 넘어갔다(원격 머리가 비지 않았고 받기로 판정 — 받기 하위 프로세스의
    # 표지). 시도마다 새로 센다.
    downloading: bool = False
    kind: str | None = None
    failed_at: float | None = None
    # 잠시 닿지 못함 갈래(`retry_kind`)가 끊김 없이 이어진 첫 실패 시각 — 다른 갈래를 지나면
    # 새로 센다.
    failing_since: float | None = None
    next_at: float | None = None
    facts: StageFacts = StageFacts()
    version: int = 0

    @property
    def failures(self) -> int:
        """실패로 끝난 받기 수."""
        return max(self.attempt - (1 if self.trying else 0), 0)


@dataclass(frozen=True)
class StageView:
    """보이는 것 한 벌. 쪽 HTML · `/_capa_stage` · 재시작 띠가 함께 쓴다."""

    tone: str
    chip: str
    title: str
    reasons: tuple[str, ...] = ()
    # (칸 이름, 지금 칸) — 비면 단계 줄을 그리지 않는다.
    steps: tuple[tuple[str, bool], ...] = ()
    # 값 줄. `since` 가 있으면 「<progress> · 지난 시간 …」, `until` 이 있으면
    # 「<until_label> n초 뒤」.
    progress: str = ""
    since: float | None = None
    until: float | None = None
    until_label: str = ""
    notes: tuple[str, ...] = ()
    # `late_after` 가 지나면 서는 줄.
    late_note: str = ""
    late_after: float | None = None
    # 참고 줄 — 갈래 키 · 그 시각.
    reference: str = ""
    reference_at: float | None = None
    diagnostics: tuple[str, ...] = ()
    # 열어 둔 앱 탭의 재시작 띠에 넣을 짧은 상태 글.
    band: str = ""


def clock_text(seconds: float) -> str:
    """지난 시간 글 — 쪽 JS 의 `clockText` 와 같은 꼴(시험이 맞댄다)."""
    total = max(int(seconds), 0)
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    if hours > 0:
        return f"{hours}시간 {minutes}분"
    if minutes > 0:
        return f"{minutes}분 {secs}초"
    return f"{secs}초"


def value_text(view: StageView, now: float) -> str:
    """값 줄의 지금 글 — 쪽 JS 의 `sinceText` · `untilText` 와 같은 꼴."""
    if view.since is not None:
        clock = f"{CLOCK_WORD} {clock_text(now - view.since)}"
        return f"{view.progress} · {clock}" if view.progress else clock
    if view.until is not None:
        left = max(math.ceil(view.until - now), 0)
        return f"{view.until_label} {left}초 뒤"
    return view.progress


def _steps(state: StageState) -> tuple[tuple[str, bool], ...]:
    names = [STEP_CHECK, STEP_INSTALL, *([STEP_PULL] if state.managed else []), STEP_APP]
    return tuple((STEP_LABELS[name], name == state.step) for name in names)


def _label(kind: str) -> str:
    return FAILURE_LABELS.get(kind, FAILURE_LABELS[FAILURE_OTHER])


def _pull_band(count: int) -> str:
    """받는 동안의 재시작 띠 글 — 첫 받기 · 다시 받기 · 처음 올리기 · 되돌리기 뒤 받기가 같은
    말이다."""
    return f"데이터 받는 중 · {count}번째 받기"


def _starting_view(state: StageState) -> StageView:
    if state.step != STEP_PULL:
        return StageView(
            tone=TONE_START,
            chip=CHIP_STARTING,
            title=TITLE_STARTING,
            steps=_steps(state),
            since=state.started_at,
            notes=(NOTE_AUTO,),
            band="앱 시작 중",
        )
    count = max(state.attempt, 1)
    return StageView(
        tone=TONE_START,
        chip=CHIP_STARTING,
        title=TITLE_PULLING,
        steps=_steps(state),
        progress=f"{count}번째 받기",
        since=state.started_at,
        notes=(NOTE_MINUTES, NOTE_NO_CICD),
        band=_pull_band(count),
    )


@dataclass(frozen=True)
class _Wait:
    """실패 뒤 값 줄 — 시도가 돌면 그 글, 아니면 다음 시각까지 센다. 다시 받기가 도는 동안이면
    지난 시간(서버 시작부터)과 첫 받기의 두 노트, 그 받기의 재시작 띠 글도 함께다(비면 갈래의
    띠 글)."""

    progress: str = ""
    since: float | None = None
    until: float | None = None
    until_label: str = ""
    notes: tuple[str, ...] = ()
    band: str = ""


def _waiting(state: StageState, label: str, trying: str) -> _Wait:
    if state.trying:
        return _Wait(progress=trying)
    return _Wait(until=state.next_at, until_label=label)


def _pulling(state: StageState) -> _Wait:
    """실패 뒤 다시 받기가 도는 동안 — 「n번째 받는 중 · 지난 시간」 이 흐르고 첫 받기의 두 노트가
    선다. 정상으로 받는 몇 분이 멈춘 것처럼 보이지 않게. 열어 둔 탭의 재시작 띠도 같은 때 같은 말
    「데이터 받는 중 · n번째 받기」 다."""
    return _Wait(
        progress=f"{state.attempt}번째 받는 중",
        since=state.started_at,
        notes=(NOTE_MINUTES, NOTE_NO_CICD),
        band=_pull_band(state.attempt),
    )


def _remote_empty_view(state: StageState) -> StageView:
    """이관 전. 관리자가 처음 올리면(init) 다음 확인이 그대로 받기라 실제 내려받기로 넘어간 뒤는
    다시 받기의 값 줄이다. 아직 비어 있는지 보는 짧은 확인은 「확인하는 중」 이다."""
    assert state.kind is not None
    wait = (
        _pulling(state)
        if state.trying and state.downloading
        else _waiting(state, LABEL_NEXT_CHECK, "확인하는 중")
    )
    return StageView(
        tone=TONE_CHECK,
        chip=CHIP_MAINTENANCE,
        title=TITLE_REMOTE_EMPTY,
        reasons=(REASON_REMOTE_EMPTY,),
        reference=state.kind,
        reference_at=state.failed_at,
        diagnostics=(
            _label(state.kind),
            "버킷에 정본 세대가 없음 — 앱 관리자(개발자) PC 에서 doctor → init",
            "이미 init 했다면 CAPA_S3_BUCKET 이 같은 버킷인지 확인",
            f"시도 {state.failures}회",
        ),
        progress=wait.progress,
        since=wait.since,
        until=wait.until,
        until_label=wait.until_label,
        notes=wait.notes,
        band=wait.band or "점검 중 · 데이터를 처음 올리는 중",
    )


def retry_kind(kind: str) -> bool:
    """「다시 시도」 갈래인가 — 원격이 비어 있음 · 사람이 고쳐야 풀리는 갈래가 아닌 실패(닿지 못함 ·
    시간 초과 · 원인 모름)."""
    return kind != FAILURE_REMOTE_EMPTY and kind not in HUMAN_SCREENS


def _retry_view(state: StageState) -> StageView:
    """잠시 닿지 못함 · 시간 초과 · 원인 모름 — 저절로 다시 시도한다. 제목 · 띠 글만 원인을
    아는지에 따라 갈리고(`STORE_NOT_REACHED`) 나머지는 같다. 다시 받기가 도는 동안은 값 줄이
    「n번째 받는 중 · 지난 시간」 으로 흐르고 첫 받기의 두 노트가 선다 — 정상으로 받는 몇 분이
    멈춘 것처럼 보이지 않게."""
    assert state.kind is not None
    since = state.failing_since
    reached = state.kind in STORE_NOT_REACHED
    if state.trying:
        wait = _pulling(state)
    else:
        wait = _Wait(until=state.next_at, until_label=LABEL_NEXT_TRY)
    return StageView(
        tone=TONE_RETRY,
        chip=CHIP_RETRY,
        title=TITLE_TRANSIENT if reached else TITLE_TRANSIENT_UNKNOWN,
        reasons=(REASON_TRANSIENT,),
        notes=wait.notes,
        late_note=NOTE_LONG_RETRY,
        late_after=None if since is None else since + LONG_RETRY_SECONDS,
        reference=state.kind,
        reference_at=state.failed_at,
        diagnostics=(
            _label(state.kind),
            "앱 관리자(개발자) PC 에서 doctor 로 원문 보기",
            "pod 에 프록시 변수가 있으면 NO_PROXY 에 S3 주소가 있는지 확인",
            f"시도 {state.failures}회",
        ),
        progress=wait.progress,
        since=wait.since,
        until=wait.until,
        until_label=wait.until_label,
        band=wait.band or (BAND_TRANSIENT if reached else BAND_TRANSIENT_UNKNOWN),
    )


def _megabytes(value: int) -> int:
    return -(-value // _MIB)


def _fact_lines(kind: str, facts: StageFacts) -> list[str]:
    """갈래별 이름 · 수 줄. 모르는 수는 줄을 빼고 짐작하지 않는다."""
    lines: list[str] = []
    if kind == FAILURE_CONFIG and facts.missing_environment:
        lines.append("비어 있는 환경변수: " + " · ".join(facts.missing_environment))
    if (
        kind == FAILURE_DISK_FULL
        and facts.needed_bytes is not None
        and facts.free_bytes is not None
    ):
        need, free = _megabytes(facts.needed_bytes), _megabytes(facts.free_bytes)
        lines.append(f"필요 {need} MB · 남음 {free} MB")
    if kind in (FAILURE_CORRUPT, FAILURE_FORKED) and facts.seq is not None:
        lines.append(f"멈춘 세대 {facts.seq}")
    names = " · ".join(_DATASET_WORDS[name] for name in facts.datasets)
    if kind == FAILURE_DIVERGED and names:
        lines.append(f"바뀐 DB: {names}")
    if kind == FAILURE_SCHEMA_NEWER and facts.file_version is not None:
        code = "?" if facts.code_version is None else str(facts.code_version)
        lines.append(f"{names or 'DB'} 판 {facts.file_version} · 코드 판 {code}")
    return lines


def _human_view(state: StageState) -> StageView:
    """사람이 고쳐야 풀리는 시작 실패 — 「점검 중」, 경우별 쉬운 말, 접힌 진단(이름 · 수).
    되돌리기로 풀리는 갈래(`REPAIRED_IN_PLACE`)의 확인이 실제 내려받기로 넘어간 뒤는 다시 받기의
    값 줄이다."""
    assert state.kind is not None
    title, reason = HUMAN_SCREENS[state.kind]
    retries = state.kind != FAILURE_SCHEMA_NEWER
    if state.trying and state.downloading and state.kind in REPAIRED_IN_PLACE:
        wait = _pulling(state)
    elif retries:
        wait = _waiting(state, LABEL_NEXT_CHECK, "다시 확인하는 중")
    else:
        wait = _Wait()
    return StageView(
        tone=TONE_CHECK,
        chip=CHIP_MAINTENANCE,
        title=title,
        reasons=(reason,),
        reference=state.kind,
        reference_at=state.failed_at,
        diagnostics=(
            _label(state.kind),
            HUMAN_ACTIONS[state.kind],
            *_fact_lines(state.kind, state.facts),
            f"시도 {state.failures}회",
        ),
        progress=wait.progress,
        since=wait.since,
        until=wait.until,
        until_label=wait.until_label,
        notes=wait.notes,
        band=wait.band or "점검 중 · 개발자가 고쳐야 열림",
    )


def stage_view(state: StageState) -> StageView:
    """보이는 것 한 벌을 정한다 — 쪽 · 상태 줄 · 재시작 띠가 이 하나에서 나온다."""
    if state.kind is None:
        return _starting_view(state)
    if state.kind == FAILURE_REMOTE_EMPTY:
        return _remote_empty_view(state)
    if state.kind in HUMAN_SCREENS:
        return _human_view(state)
    return _retry_view(state)


# ---------------------------------------------------------------- 그리기
@dataclass(frozen=True)
class StageContact:
    """문의 줄 — 메일 꼴만 받은 문의 메일과 창구 글. 둘 다 비면 줄을 그리지 않는다."""

    email: str = ""
    text: str = ""


def contact_of(environ: Mapping[str, str]) -> StageContact:
    """환경변수에서 문의 줄을 읽는다 — 앱 정보 카드 · 거절 화면과 같은 두 칸."""
    text = environ.get(ENV_ACCESS_CONTACT, "").strip()
    if len(text) > _CONTACT_LIMIT or _CONTROL.search(text):
        text = ""
    return StageContact(email=app_contact_email(environ), text=text)


def _esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def _ms(moment: float) -> int:
    return int(moment * 1000)


def _utc(moment: float) -> str:
    return datetime.fromtimestamp(moment, timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _value_html(view: StageView, now: float) -> str:
    text = _esc(value_text(view, now))
    if view.since is not None:
        attrs = f' data-since="{_ms(view.since)}" data-progress="{_esc(view.progress)}"'
    elif view.until is not None:
        attrs = f' data-until="{_ms(view.until)}" data-label="{_esc(view.until_label)}"'
    elif view.progress:
        attrs = ""
    else:
        return ""
    return f'<p class="value"{attrs}>{text}</p>'


# 문의 줄 · 참고 줄은 앱 안 멈춤 판(`components/stop_panel.py` 의 `contact_caption` ·
# `reference_line`)과 같은 글자 꼴이다 — Streamlit 을 부르지 않아 따로 짓고 시험이 맞댄다. 문의 줄은
# 앱 밖 공통 틀(`auth/page_frame.contact_line`)과도 같은 글자다.
def _contact_html(contact: StageContact) -> str:
    parts: list[str] = []
    if contact.email:
        parts.append(
            f'<a href="mailto:{quote(contact.email, safe="@.+-_")}">{_esc(contact.email)}</a>'
        )
    if contact.text:
        parts.append(_esc(contact.text))
    return f'<p class="contact">{CONTACT_LABEL} {" · ".join(parts)}</p>' if parts else ""


def render_main(
    view: StageView,
    *,
    now: float,
    version: int,
    contact: StageContact,
    register_lost: bool = False,
) -> str:
    """`<main>` 한 덩이 — 쪽 JS 가 판이 바뀌면 이것만 갈아 끼운다. `register_lost` 면 제목 · 까닭
    아래 「다시 눌러 주세요」 한 줄(`data-keep` — 갈아 끼워도 쪽 JS 가 옮겨 단다)."""
    parts = [
        f'<main data-version="{version}" data-now="{_ms(now)}">',
        f'<header class="brand">{_mark_svg()}<div><strong>{_esc(APP_LABEL)}</strong>'
        f"<span>{_esc(APP_SUBTITLE)}</span></div></header>",
        f'<p class="chip tone-{view.tone}">{_esc(view.chip)}</p>',
        f"<h1>{_esc(view.title)}</h1>",
        *(f'<p class="reason">{_esc(reason)}</p>' for reason in view.reasons),
    ]
    if register_lost:
        parts.append(f'<p class="lost" data-keep>{_esc(NOTE_REGISTER_LOST)}</p>')
    if view.steps:
        items = "".join(
            f'<li class="now">{_esc(label)} <b>{NOW_WORD}</b></li>'
            if now_step
            else f"<li>{_esc(label)}</li>"
            for label, now_step in view.steps
        )
        parts.append(f'<ol class="steps">{items}</ol>')
    parts.append(_value_html(view, now))
    parts.extend(f'<p class="note">{_esc(note)}</p>' for note in view.notes)
    if view.late_note and view.late_after is not None:
        hidden = " hidden" if now < view.late_after else ""
        after = _ms(view.late_after)
        parts.append(f'<p class="note" data-after="{after}"{hidden}>{_esc(view.late_note)}</p>')
    parts.append(f'<noscript><p class="note">{_esc(NOSCRIPT_NOTE)}</p></noscript>')
    parts.append(_contact_html(contact))
    if view.reference:
        at = "" if view.reference_at is None else f" · {_utc(view.reference_at)}"
        parts.append(f'<p class="ref">{REFERENCE_LABEL} {_esc(view.reference)}{at}</p>')
    if view.diagnostics:
        items = "".join(f"<li>{_esc(line)}</li>" for line in view.diagnostics)
        parts.append(
            f"<details><summary>{_esc(DIAGNOSTICS_SUMMARY)}</summary><ul>{items}</ul></details>"
        )
    parts.append("</main>")
    return "\n".join(part for part in parts if part)


_PAGE: Final = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>{title}</title>
<style>
{css}
</style>
</head>
<body data-base="{base}" data-return="{back}">
{main}
<script>
{script}
</script>
</body>
</html>
"""

# 쪽의 되풀이. 틈(소켓을 닫고 앱이 잡기까지)의 실패는 무시하고 다음 번에 다시 본다. 판정 구획
# (`// <stage-rule>`)은 DOM 을 모르는 순수 함수라 node 시험이 떼어 돌린다.
PAGE_SCRIPT: Final = (
    """
// <stage-rule>
function clockText(seconds) {
  const total = Math.max(Math.floor(seconds), 0);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  if (hours > 0) return hours + "시간 " + minutes + "분";
  if (minutes > 0) return minutes + "분 " + secs + "초";
  return secs + "초";
}
function sinceText(progress, sinceMs, nowMs) {
  const clock = "__CLOCK_WORD__ " + clockText((nowMs - sinceMs) / 1000);
  return progress ? progress + " · " + clock : clock;
}
function untilText(label, untilMs, nowMs) {
  return label + " " + Math.max(Math.ceil((untilMs - nowMs) / 1000), 0) + "초 뒤";
}
// 앱이 뜨면 갈 곳 — 처음 연 주소. POST 로 받은 쪽 · 콜백 경로는 바탕 주소. 잃은 신청은 처음
// 연 주소(신청 경로 — 앱이 GET 을 거절 화면으로 보낸다).
function returnTarget(mode, base, href) {
  return (mode === "__HERE__" || mode === "__RESEND__") && href ? href : base;
}
// 갈 곳이 지금 주소면 다시 읽는다("reload") — `#…` 가 붙은 주소에 replace 는 조각 이동만 해 쪽을
// 다시 받지 않는다. 잃은 신청은 같은 주소여도 "replace" 다 — 다시 읽으면 POST 를 다시 보낸다.
function returnWay(mode, target, current) {
  return mode !== "__RESEND__" && target === current ? "reload" : "replace";
}
// 상태 줄 셋째 줄(JSON). 없거나 못 읽으면 null — 옛 임시 응답이다.
function stageInfo(line) {
  if (typeof line !== "string" || line === "") return null;
  try {
    const info = JSON.parse(line);
    return info && typeof info === "object" ? info : null;
  } catch (error) {
    return null;
  }
}
// </stage-rule>
// 판이 바뀌어 갈아 끼우는 새 `<main>` 에 「다시 눌러 주세요」 한 줄(`[data-keep]`)을 옮겨 단다 —
// 서버는 바탕 주소 GET 으로 판을 다시 그려 그 한 줄을 모른다. 자리는 제목 · 까닭 바로 아래.
function carryKept(fresh, kept) {
  if (!kept || fresh.querySelector("[data-keep]")) return;
  const marks = fresh.querySelectorAll("h1, .reason");
  if (marks.length) marks[marks.length - 1].after(kept);
}
async function stageTick(deps) {
  const base = deps.base;
  try {
    const health = await deps.fetch(base + "_stcore/health", { cache: "no-store" });
    if (health.ok && !health.headers.has("X-Capa-Stage")) {
      deps.goTo(returnTarget(deps.mode, base, deps.href));
      return false;
    }
    const status = await deps.fetch(base + "_capa_stage", { cache: "no-store" });
    if (status.ok && status.headers.has("X-Capa-Stage")) {
      const lines = (await status.text()).split("\\n");
      const info = stageInfo(lines[2]);
      if (info) await deps.update(info);
      else deps.show(lines[0] || "", lines[1] || "");
    }
  } catch (error) {
    return true;
  }
  return true;
}
if (typeof document !== "undefined") {
  const body = document.body;
  const main = () => document.querySelector("main");
  let offset = Number(main().dataset.now) - Date.now() || 0;
  const paint = () => {
    const now = Date.now() + offset;
    document.querySelectorAll("[data-since]").forEach((node) => {
      node.textContent = sinceText(node.dataset.progress || "", Number(node.dataset.since), now);
    });
    document.querySelectorAll("[data-until]").forEach((node) => {
      node.textContent = untilText(node.dataset.label || "", Number(node.dataset.until), now);
    });
    document.querySelectorAll("[data-after]").forEach((node) => {
      node.hidden = now < Number(node.dataset.after);
    });
  };
  const deps = {
    base: body.dataset.base,
    mode: body.dataset.return,
    href: window.location.href,
    fetch: (url, options) => window.fetch(url, options),
    goTo: (url) =>
      returnWay(body.dataset.return, url, window.location.href) === "reload"
        ? window.location.reload()
        : window.location.replace(url),
    show: (headline, detail) => {
      const title = document.querySelector("h1");
      if (title) title.textContent = headline;
      const value = document.querySelector(".value");
      if (value) value.textContent = detail;
    },
    update: async (info) => {
      if (typeof info.now === "number") offset = info.now - Date.now();
      if (String(info.v) !== main().dataset.version) {
        const answer = await window.fetch(body.dataset.base, { cache: "no-store" });
        if (answer.ok && answer.headers.has("X-Capa-Stage")) {
          const next = new DOMParser().parseFromString(await answer.text(), "text/html");
          const found = next.querySelector("main");
          if (found) {
            const fresh = document.importNode(found, true);
            carryKept(fresh, main().querySelector("[data-keep]"));
            main().replaceWith(fresh);
            document.title = next.title;
          }
        }
      }
      paint();
    },
  };
  const again = () => stageTick(deps).then((more) => more && window.setTimeout(again, 3000));
  window.setTimeout(again, 3000);
  window.setInterval(paint, 1000);
}
""".replace("__CLOCK_WORD__", CLOCK_WORD)
    .replace("__HERE__", RETURN_HERE)
    .replace("__RESEND__", RETURN_RESEND)
)


def base_path_of(public_url: str) -> str:
    """공개 주소의 경로만 — 쪽이 앱으로 돌아갈 자리. 호스트는 싣지 않는다. 꼴이 이상하면 `/`."""
    try:
        path = urlsplit(public_url.strip()).path
    except ValueError:
        return "/"
    if not path or _BASE_PATH.fullmatch(path) is None:
        return "/"
    return path.rstrip("/") + "/"


def return_mode(method: str, path: str) -> str:
    """쪽이 앱으로 갈 길 — 「접속 권한 신청」 POST 는 잃은 신청, 그 밖의 POST · 콜백 경로는 바탕
    주소, 나머지는 처음 연 주소."""
    if method == "POST" and path.endswith(REGISTER_PATH):
        return RETURN_RESEND
    if method == "POST" or path.endswith(CALLBACK_PATH):
        return RETURN_BASE
    return RETURN_HERE


def status_text(view: StageView, *, now: float, version: int) -> str:
    """`/_capa_stage` 의 세 줄 — 제목 · 값 한 줄 · JSON(판 · 재시작 띠 글 · 서버 시각 ms)."""
    info = {"v": version, "band": view.band, "tone": view.tone, "now": _ms(now)}
    return "\n".join((view.title, value_text(view, now), json.dumps(info, ensure_ascii=False)))


class _Display:
    """지금 상태. 시작 스크립트가 쓰고 응답 스레드가 읽는다. `download_seen` 은 받기 시도가 실제
    내려받기로 넘어갔는가를 묻는 것이다 — 읽을 때 물어 넘어갔으면 상태를 올린다(판이 바뀌어 열어 둔
    쪽이 본문을 갈아 끼운다). 시도가 돌지 않는 동안(앞 시도의 표지가 남았어도)은 묻지 않는다."""

    def __init__(
        self,
        clock: Callable[[], float] = time.time,
        download_seen: Callable[[], bool] | None = None,
    ) -> None:
        self._lock = threading.Lock()
        self.clock = clock
        self._download_seen = download_seen
        self._state = StageState(started_at=clock())

    def change(self, how: Callable[[StageState], StageState]) -> None:
        with self._lock:
            changed = how(self._state)
            self._state = replace(changed, version=self._state.version + 1)

    def _downloading_now(self) -> bool:
        if self._download_seen is None:
            return False
        try:
            return bool(self._download_seen())
        except Exception:
            return False

    def read(self) -> StageState:
        with self._lock:
            state = self._state
        if not state.trying or state.downloading or not self._downloading_now():
            return state
        # 묻는 사이 시작 스크립트가 상태를 바꿨으면(실패 · 다음 시도) 올리지 않는다.
        with self._lock:
            if self._state.version == state.version:
                self._state = replace(state, downloading=True, version=state.version + 1)
            return self._state


class _StageServer(ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = False
    # Windows 의 `SO_REUSEADDR` 는 남이 듣는 포트까지 함께 잡는다 — 「포트를 못 잡음」 이 사라진다.
    allow_reuse_address = os.name == "posix"
    display: _Display
    base_path: str
    contact: StageContact

    def server_bind(self) -> None:
        # 듀얼스택 — Streamlit 과 같게 IPv4 도 받는다. 기본값은 환경마다 다르다.
        if self.address_family == socket.AF_INET6:
            self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        # `HTTPServer.server_bind` 의 `getfqdn` 을 지나지 않는다 — DNS 없는 컨테이너에서 포트를 잡는
        # 첫 순간이 이름 풀이 시간 초과를 기다린다.
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = "stage", int(self.server_address[1])

    def handle_error(self, request: object, client_address: object) -> None:
        """끊긴 연결은 조용히 버린다 — 표준 오류에 요청 내용이 남지 않게."""


class _V4StageServer(_StageServer):
    address_family = socket.AF_INET


class _V6StageServer(_StageServer):
    address_family = socket.AF_INET6


def prepare_server(
    server: _StageServer,
    *,
    base_path: str = "/",
    contact: StageContact | None = None,
    clock: Callable[[], float] = time.time,
    download_seen: Callable[[], bool] | None = None,
) -> None:
    """듣는 서버에 상태 · 바탕 경로 · 문의 줄 · 내려받기 물음을 단다."""
    server.display = _Display(clock, download_seen)
    server.base_path = base_path
    server.contact = contact or StageContact()


class _Handler(BaseHTTPRequestHandler):
    server: _StageServer
    server_version = "capa-stage"
    sys_version = ""
    timeout = SOCKET_TIMEOUT_SECONDS

    def log_message(self, format: str, *args: object) -> None:
        """요청 줄을 찍지 않는다 — 질의에 인증 코드가 든다."""

    def _answer(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header(STAGE_HEADER, "1")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _page(self, path: str) -> bytes:
        display = self.server.display
        state, now = display.read(), display.clock()
        view = stage_view(state)
        back = return_mode(self.command, path)
        return _PAGE.format(
            title=_esc(f"{view.title} · {APP_LABEL}"),
            css=page_css(),
            base=_esc(self.server.base_path),
            back=back,
            main=render_main(
                view,
                now=now,
                version=state.version,
                contact=self.server.contact,
                register_lost=back == RETURN_RESEND,
            ),
            script=PAGE_SCRIPT,
        ).encode("utf-8")

    def _respond(self) -> None:
        path = urlsplit(self.path).path
        if path.endswith(HEALTH_SUFFIX):
            self._answer(200, b"ok", "text/plain; charset=utf-8")
        elif STREAMLIT_INFIX in path:
            self._answer(503, b"", "text/plain; charset=utf-8")
        elif path.endswith(STATUS_SUFFIX):
            display = self.server.display
            state = display.read()
            text = status_text(stage_view(state), now=display.clock(), version=state.version)
            self._answer(200, text.encode("utf-8"), "text/plain; charset=utf-8")
        else:
            self._answer(200, self._page(path), "text/html; charset=utf-8")

    def _discard_body(self) -> None:
        try:
            left = min(int(self.headers.get("Content-Length") or 0), DISCARD_LIMIT_BYTES)
        except ValueError:
            return
        while left > 0:
            chunk = self.rfile.read(min(left, _DISCARD_CHUNK))
            if not chunk:
                return
            left -= len(chunk)

    def do_GET(self) -> None:  # noqa: N802
        self._respond()

    def do_HEAD(self) -> None:  # noqa: N802
        self._respond()

    def do_POST(self) -> None:  # noqa: N802
        self._discard_body()
        self._respond()


class Stage:
    """임시 응답 한 벌. 포트를 못 잡았으면 빈 껍데기다 — 시작 차례는 그대로 이어 간다."""

    def __init__(self, server: _StageServer | None) -> None:
        self._server = server
        self._thread: threading.Thread | None = None

    @property
    def bound(self) -> bool:
        return self._server is not None

    def start(self) -> None:
        if self._server is None:
            return
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            kwargs={"poll_interval": 0.1},
            name="capa-start-stage",
            daemon=True,
        )
        self._thread.start()

    def _change(self, how: Callable[[StageState], StageState]) -> None:
        if self._server is not None:
            self._server.display.change(how)

    def begin(self, *, managed: bool) -> None:
        """받는 서버인가(단계 줄의 「데이터 받기」 칸) — 첫 단계 「준비 · 점검」."""
        self._change(lambda state: replace(state, managed=managed, step=STEP_CHECK))

    def step(self, name: str) -> None:
        """다음 단계로(`STEP_INSTALL` · `STEP_PULL`)."""
        self._change(lambda state: replace(state, step=name))

    def attempt(self, number: int) -> None:
        """`number` 번째 받기를 시작한다 — 앞 실패 낱말은 남기고 값 줄은 그 갈래의 「받는 중」 ·
        「확인하는 중」 꼴이 된다(`stage_view`). 이관 전 · 되돌리기 갈래의 「n번째 받는 중」 과 두
        노트는 그 시도가 실제 내려받기로 넘어간 뒤(`download_seen`)다."""
        self._change(
            lambda state: replace(
                state, attempt=number, trying=True, downloading=False, next_at=None
            )
        )

    def fail(
        self,
        number: int,
        kind: str,
        *,
        wait_seconds: float,
        facts: StageFacts | None = None,
    ) -> None:
        """`number` 번째 받기가 `kind` 로 끝났다 — `wait_seconds` 뒤 다시. `facts` 는 접힌 진단의
        이름 · 수다."""
        if self._server is None:
            return
        moment = self._server.display.clock()
        # 갈래 칸은 고정 낱말 표의 키만 지난다 — 서버 글이 화면 · 참고 줄에 끼어들 자리가 없다.
        known = kind if kind in FAILURE_LABELS else FAILURE_OTHER

        def failed(state: StageState) -> StageState:
            return replace(
                state,
                attempt=number,
                trying=False,
                downloading=False,
                kind=known,
                facts=(facts or StageFacts()).checked(),
                failed_at=moment,
                failing_since=(
                    state.failing_since
                    if state.kind is not None
                    and retry_kind(state.kind)
                    and retry_kind(known)
                    and state.failing_since is not None
                    else moment
                ),
                next_at=moment + wait_seconds,
            )

        self._change(failed)

    def close(self) -> None:
        """듣기를 멈추고 소켓을 닫는다. 이 뒤에 앱이 같은 포트를 잡는다. 두 번 불러도 된다."""
        server, self._server = self._server, None
        if server is None:
            return
        server.shutdown()
        server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=SOCKET_TIMEOUT_SECONDS)


def open_stage(
    port: int,
    *,
    base_path: str = "/",
    contact: StageContact | None = None,
    clock: Callable[[], float] = time.time,
    download_seen: Callable[[], bool] | None = None,
) -> Stage:
    """포트를 잡아 답하기 시작한다. 잡지 못해도 예외를 내지 않는다 — 앱 띄우기가 먼저다.
    `download_seen` 은 받기 시도가 실제 내려받기로 넘어갔는가를 묻는다(`_Display`)."""
    choices: tuple[tuple[type[_StageServer], str], ...] = (
        (_V6StageServer, "::"),
        (_V4StageServer, "0.0.0.0"),
    )
    for factory, host in choices:
        try:
            server = factory((host, port), _Handler)
        except OSError:
            continue
        prepare_server(
            server, base_path=base_path, contact=contact, clock=clock, download_seen=download_seen
        )
        stage = Stage(server)
        stage.start()
        return stage
    return Stage(None)
