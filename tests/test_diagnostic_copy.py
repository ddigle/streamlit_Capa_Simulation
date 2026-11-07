# Purpose: 진단 글 복사의 평문 꼴 · 막힌 환경의 대체 꼴과 펼침마다 싣는 글을 지킨다.

"""`components/diagnostic_copy.py`(설계 규칙 UI-NTF-10).

AppTest 는 컴포넌트 JS 를 못 돌리므로 클립보드 판정 구획(`// <diagnostic-copy>`)은 node(없으면
bun)로 돌리고, 펼침이 싣는 글은 컴포넌트 대역(`diagnostic_copies`)으로 본다. 복사 글은 리뷰로 나가는
글이라 통합인증 점검의 포털 등록값 셋이 글자 그대로 실리지 않는지 함께 본다. 브라우저 동작은 사본
앱으로 본다.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from js_runner import run_js_json
from sso_support import CLIENT_ID, ISSUER, PUBLIC_URL, sso_secret, use_config
from streamlit.testing.v1 import AppTest

import capa_simulation.settings as settings
from capa_simulation import object_sync_worker, sync_boot
from capa_simulation.components import (
    container_start_check,
    diagnostic_copy,
    module_status,
    object_sync_status,
    sso_status,
)
from capa_simulation.components.diagnostic_copy import (
    COMPONENT_KEY_PREFIX,
    diagnostic_text,
    plain_lines,
    table_lines,
)
from capa_simulation.module_registry import ModuleRecord, ModuleScan
from capa_simulation.object_sync_worker import WorkerStatus
from capa_simulation.sync_boot import SyncBoot

SSO_SCRIPT = """
from capa_simulation.components.sso_status import render_sso_status

render_sso_status()
"""
START_SCRIPT = """
from capa_simulation.components.container_start_check import render_container_start_check

render_container_start_check()
"""
SYNC_SCRIPT = """
from capa_simulation.components.object_sync_status import render_object_sync_status

render_object_sync_status()
"""


def _copy_key(name: str) -> str:
    return f"{COMPONENT_KEY_PREFIX}{name}"


def _node(runner: str) -> Any:
    match = re.search(r"// <diagnostic-copy>\n(?P<body>.*?)\n// </diagnostic-copy>", _js(), re.S)
    assert match, "diagnostic_copy 스크립트에 // <diagnostic-copy> 구획이 없습니다"
    return run_js_json(match.group("body") + "\n" + runner, what="진단 글 복사 판정 구획 시험")


def _js() -> str:
    return diagnostic_copy._JS


def test_a_table_is_tab_separated_with_blank_cells() -> None:
    """표는 탭으로 나눈 줄이고 빈 칸은 빈 글이다 — 「None」 · 「<NA>」 글자를 쓰지
    않는다(UI-DAT-06)."""
    frame = pd.DataFrame({"모듈": ["demo_a", "demo_b"], "회차": [12, None]})
    frame["회차"] = frame["회차"].astype("Int64")

    assert table_lines(frame) == ["모듈\t회차", "demo_a\t12", "demo_b\t"]


def test_lines_lose_their_markdown_and_empty_blocks_are_dropped() -> None:
    lines = plain_lines(
        ["**마지막 올림** · 없음", "`ADFS_ISSUER`: a\\-b", ":material/lock_open: 값"]
    )

    assert lines == ["마지막 올림 · 없음", "ADFS_ISSUER: a-b", "값"]
    assert diagnostic_text("제목", ["가"], [], ["나", "다"]) == "제목\n\n가\n\n나\n다"


def test_the_clipboard_is_used_only_when_it_can_be_trusted() -> None:
    """보안 연결의 `writeText` 만 믿는다 — 막히면 글 칸(수동 복사)으로 간다. `execCommand` 는 막힌
    클립보드에서도 참을 돌려 「복사했습니다」 가 거짓이 된다(Alarm 「로그」 와 같은 규약)."""
    runner = """
const run = async (win, nav) => {
  const seen = []
  await new Promise((resolve) => {
    const mark = (name) => () => { seen.push(name); resolve() }
    copyText(win, nav, '글', mark('done'), mark('manual'))
  })
  return seen
}
const secure = { isSecureContext: true }
;(async () => {
  const wrote = []
  const out = {
    ok: await run(secure, { clipboard: { writeText: async (text) => { wrote.push(text) } } }),
    insecure: await run({ isSecureContext: false }, { clipboard: { writeText: async () => {} } }),
    none: await run(secure, {}),
    refused: await run(secure, { clipboard: { writeText: () => Promise.reject(new Error('x')) } }),
    thrown: await run(secure, { clipboard: { writeText: () => { throw new Error('x') } } }),
    wrote,
  }
  process.stdout.write(JSON.stringify(out))
})()
"""
    assert _node(runner) == {
        "ok": ["done"],
        "insecure": ["manual"],
        "none": ["manual"],
        "refused": ["manual"],
        "thrown": ["manual"],
        "wrote": ["글"],
    }
    assert "execCommand" not in _js()


def test_the_copy_of_the_sso_status_leaves_the_portal_values_out(
    diagnostic_copies: dict[str, str],
) -> None:
    """복사 글은 리뷰로 나간다 — redirect_uri · issuer · 인증서 지문은 화면에서만 글자 그대로다."""
    cfg = use_config()
    cert = cfg.signing_certs[0]

    app = AppTest.from_string(SSO_SCRIPT).run()

    assert not list(app.exception)
    text = diagnostic_copies[_copy_key("sso_status")]
    assert text.splitlines()[0] == "통합인증 점검 · 켜짐"
    assert "환경변수\t상태\t까닭" in text
    assert "redirect_uri: 있음" in text and "ADFS_ISSUER: 있음" in text
    assert "서명 인증서 만료" in text and "로그인 갱신(기동 뒤 누계)" in text
    for value in (PUBLIC_URL, ISSUER, CLIENT_ID, sso_secret(), cert.x5t, cert.sha256[:16]):
        assert value not in text, value
    # 화면은 포털과 대 보는 자리라 글자 그대로다.
    assert cert.sha256[:16] in "\n".join(str(caption.value) for caption in app.caption)


def test_the_copy_of_the_sso_status_carries_the_failures_too(
    diagnostic_copies: dict[str, str],
) -> None:
    """꺼짐(운영)은 결론 · 「켜면 막힐 문제」 를 든다 — 화면과 같은 차례다."""
    use_config({"APP_ENV": "prod"}, drop=["ADFS_CLIENT_ID"])

    AppTest.from_string(SSO_SCRIPT).run()

    lines = diagnostic_copies[_copy_key("sso_status")].splitlines()
    assert lines[:3] == [
        "통합인증 점검 · 꺼짐(운영)",
        "",
        sso_status.OFF_IN_PRODUCTION_CONCLUSION,
    ]
    assert lines[3].startswith("켜면 막힐 문제: ")


def test_the_copy_of_the_start_check_carries_the_table_and_the_pip_tail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, diagnostic_copies: dict[str, str]
) -> None:
    report = tmp_path / "container_start.json"
    report.write_text(
        json.dumps(
            {
                "version": 1,
                "written_at": "2026-11-07T09:00:00+09:00",
                "steps": {
                    "install": {"status": "failed", "reason": "pip 설치 실패"},
                    "token": {"status": "skipped", "reason": "토큰 없음"},
                    "user_name": {"status": "failed", "reason": "계정 없음"},
                },
                "bigdataquery_version": None,
                "token_file": {"exists": False, "modified_at": None, "path": None},
                "user_name": {"present": False, "masked": None},
                "missing_environment": ["CAPA_BDQ_TOKEN"],
                "pip_tail": ["ERROR: No matching distribution  found"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "CONTAINER_START_REPORT_PATH", report)

    app = AppTest.from_string(START_SCRIPT).run()

    assert not list(app.exception), [item.message for item in app.exception]
    text = diagnostic_copies[_copy_key("container_start_check")]
    assert text.splitlines()[0] == "서버 시작 점검 · 실패 있음"
    assert "시작 기록 · 2026-11-07T09:00:00+09:00" in text
    assert "단계\t결과\t까닭" in text and "pip 설치 실패" in text
    assert "시작 때 비어 있던 CD 환경변수: CAPA_BDQ_TOKEN" in text
    # pip 출력은 마크다운이 아니라 받은 글 그대로다(빈칸도) — 주소만 가린다.
    assert f"{container_start_check.COPY_PIP_TAIL_LABEL}\nERROR: No matching" in text
    assert "ERROR: No matching distribution  found" in text
    assert "`" not in text and "**" not in text


FAKE_INDEX_HOST = "artifactory.example.invalid"


@pytest.mark.parametrize(
    ("line", "shared"),
    [
        (
            f"Looking in indexes: https://***@{FAKE_INDEX_HOST}/repository/demo/simple",
            "Looking in indexes: <주소>",
        ),
        (
            f"WARNING: The repository located at {FAKE_INDEX_HOST} is not a trusted host.",
            "WARNING: The repository located at <주소> is not a trusted host.",
        ),
        (
            f"Failed to connect to {FAKE_INDEX_HOST}.",
            "Failed to connect to <주소>.",
        ),
        (
            f"HTTPSConnectionPool(host='{FAKE_INDEX_HOST}', port=443): Max retries exceeded "
            "with url: /repository/demo/simple/bigdataquery/ (Caused by SSLError(x))",
            "HTTPSConnectionPool(host='<주소>', port=443): Max retries exceeded "
            "with url: <주소> (Caused by SSLError(x))",
        ),
        (
            f"Could not fetch URL https://{FAKE_INDEX_HOST}/simple/bigdataquery/: There was a "
            "problem confirming the ssl certificate",
            "Could not fetch URL <주소>: There was a problem confirming the ssl certificate",
        ),
        (
            "'Connection to 10.1.2.3 timed out. (connect timeout=15)'",
            "'Connection to <주소> timed out. (connect timeout=15)'",
        ),
        (
            "ERROR: 403 Client Error: Forbidden for url: "
            f"https://{FAKE_INDEX_HOST}/simple/bigdataquery/",
            "ERROR: 403 Client Error: Forbidden for url: <주소>",
        ),
    ],
)
def test_the_copy_of_a_pip_line_hides_the_address(line: str, shared: str) -> None:
    """복사 글은 리뷰로 나간다 — 주소는 URL · 경로 · 호스트 · IP 어느 꼴이든 가린다(런북 7-7)."""
    assert container_start_check.share_pip_line(line) == shared


@pytest.mark.parametrize(
    "line",
    [
        "── Artifactory 인덱스에서 bigdataquery",
        "ERROR: Could not find a version that satisfies the requirement bigdataquery==2.5.0",
        "Downloading bigdataquery-2.5.0-py3-none-any.whl (5 kB)",
        "bigdataquery-2.5.0.tar.gz",
        "Successfully installed bigdataquery-2.5.0",
        "urllib3.exceptions.MaxRetryError: certificate verify failed (_ssl.c:1007)",
        "<pip._vendor.urllib3.connection.HTTPSConnection object at 0x7f0>",
        "-c /project/requirements.txt (line 3)",
    ],
)
def test_the_copy_of_a_pip_line_keeps_what_tells_the_failures_apart(line: str) -> None:
    """판 · 파일 이름 · 모듈 경로는 주소가 아니다 — 갈래를 가르는 글이 뭉개지지 않는다."""
    assert container_start_check.share_pip_line(line) == line


@pytest.mark.parametrize("body", ["{깨진 JSON", ""])
def test_the_copy_of_a_broken_start_report_is_the_notice_on_the_screen(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    diagnostic_copies: dict[str, str],
    body: str,
) -> None:
    report = tmp_path / "container_start.json"
    report.write_text(body, encoding="utf-8")
    monkeypatch.setattr(settings, "CONTAINER_START_REPORT_PATH", report)

    AppTest.from_string(START_SCRIPT).run()

    text = diagnostic_copies[_copy_key("container_start_check")]
    assert text.startswith("서버 시작 점검 · 결과 파일을 읽지 못함\n\n")
    assert "읽지 못했습니다(꼴이 다름)" in text


def test_the_copy_of_the_sync_panel_is_its_lines(
    monkeypatch: pytest.MonkeyPatch, diagnostic_copies: dict[str, str]
) -> None:
    monkeypatch.setattr(sync_boot, "_boot", lambda: SyncBoot(True, None, None, False))
    status = WorkerStatus(
        alive=True, phase=object_sync_worker.PHASE_IDLE, last_tick=0.0, seq=7, failures=2
    )
    monkeypatch.setattr(object_sync_worker, "current_status", lambda: status)
    monkeypatch.setattr(object_sync_status, "_viewer_is_admin", lambda: False)

    app = AppTest.from_string(SYNC_SCRIPT).run()

    assert not list(app.exception), [item.message for item in app.exception]
    text = diagnostic_copies[_copy_key("object_sync")]
    assert text.splitlines()[0].startswith("DB 동기화 · ")
    assert "세대 · 7" in text and "연속 실패 · 2회" in text
    assert "**" not in text


def test_the_copy_of_the_module_status_is_its_table() -> None:
    """회차 기록이 없는 모듈의 칸은 빈 글이다 — 화면 표와 같다."""
    record = ModuleRecord("demo_a", Path("demo_a"), "failed", "선언을 읽지 못함", None)
    scan = ModuleScan(
        root=None,
        root_exists=True,
        records=(record,),
        disabled_value="",
        unknown_disabled=(),
        root_error="뿌리를 읽지 못함",
    )

    table = module_status.build_status_table(scan)
    text = module_status.status_text("모듈 상태 — 켜짐 0 · 꺼짐 0 · 실패 1", scan, table)

    assert text.startswith("모듈 상태 — 켜짐 0 · 꺼짐 0 · 실패 1\n\n뿌리를 읽지 못함\n\n모듈\t")
    assert "demo_a\t\t실패\t선언을 읽지 못함" in text
    assert "CAPA_MODULES_DISABLED 없음" in text
    assert "None" not in text and "<NA>" not in text
