# Purpose: 운영 진입 파일을 Streamlit 이 st.App 으로 찾고 경로 다섯·문지기를 싣는지 고정한다.

"""진입 파일 시험.

`streamlit run capa_server.py` 는 파일을 실행하지 않고 AST 로 모듈 수준 `app = st.App(...)` 대입을
찾는다 — 함수가 만든 App 은 오류 없이 빈 화면이 된다(실측). 그래서 꼴을 AST 로 고정하고, 실제로
import 해 경로 · 미들웨어를 보는 것은 **하위 프로세스**에서 한다(`st.App` 이 프로세스 전역 Streamlit
설정 — 주 스크립트 자리 — 을 잡기 때문이다).
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

from capa_simulation.auth import names

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENTRY = PROJECT_ROOT / "capa_server.py"

_PROBE = """
import json
from pathlib import Path

from streamlit.web.server.app_discovery import discover_asgi_app

found = discover_asgi_app(Path("capa_server.py"))
import capa_server

app = capa_server.app
print(json.dumps({
    "is_asgi_app": found.is_asgi_app,
    "import_string": found.import_string,
    "type": type(app).__module__ + "." + type(app).__name__,
    "script": app.script_path.name,
    "routes": [[route.path, sorted(route.methods or [])] for route in app._user_routes],
    "middleware": [item.cls.__module__ + "." + item.cls.__name__ for item in app._user_middleware],
}))
"""


def test_the_entry_is_discovered_as_an_st_app_with_routes_and_gate() -> None:
    environ = {key: value for key, value in os.environ.items() if key not in names.SSO_ENVIRONMENT}
    environ["PYTHONPATH"] = os.pathsep.join(
        [str(PROJECT_ROOT / "src"), *filter(None, [os.environ.get("PYTHONPATH")])]
    )
    completed = subprocess.run(
        [sys.executable, "-c", _PROBE],
        cwd=PROJECT_ROOT,
        env=environ,
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout.strip().splitlines()[-1])
    assert result["is_asgi_app"] is True
    assert result["import_string"] == "capa_server:app"
    assert result["type"].endswith(".App")
    assert result["script"] == "app.py"
    assert result["routes"] == [
        [names.CALLBACK_PATH, ["GET", "HEAD", "POST"]],
        [names.LOGIN_PATH, ["GET", "HEAD"]],
        [names.LOGOUT_PATH, ["GET", "HEAD"]],
        [names.ERROR_PATH, ["GET", "HEAD"]],
        # 갱신은 POST 하나지만 GET 도 붙여 처리기가 답한다(꺼짐 404 · 그 밖 405) — 붙이지 않으면
        # Streamlit 정적 마운트가 그 주소에 앱 껍데기를 낸다.
        [names.REFRESH_PATH, ["GET", "HEAD", "POST"]],
    ]
    assert result["middleware"] == ["capa_simulation.auth.gate.SsoGate"]


def test_the_app_is_a_module_level_literal_assignment() -> None:
    tree = ast.parse(ENTRY.read_text(encoding="utf-8"))
    assignments = [
        node
        for node in tree.body
        if isinstance(node, ast.Assign)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Attribute)
        and node.value.func.attr == "App"
    ]

    assert len(assignments) == 1
    target = assignments[0].targets[0]
    assert isinstance(target, ast.Name) and target.id == "app"
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, (ast.Attribute, ast.Name))
        and (node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id)
        in ("App", "Starlette", "FastAPI")
    ]
    assert len(calls) == 1, "진입 파일에 다른 ASGI 앱을 두면 Streamlit 이 엉뚱한 것을 띄울 수 있다"


def test_our_paths_avoid_streamlit_reserved_and_auth_names() -> None:
    reserved = ("/_stcore/", "/media/", "/component/", "/static/")

    for path in names.SSO_PATHS:
        assert not path.startswith(reserved)
        assert path not in names.STREAMLIT_AUTH_PATHS
    assert names.CALLBACK_PATH == "/auth/callback"
