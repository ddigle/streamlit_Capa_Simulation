# Purpose: 앱 전체 올리기 상한 200MB 와 그보다 낮은 설비 CSV 칸 고유 상한을 고정한다.

from __future__ import annotations

import importlib
from pathlib import Path

from test_equipment_data_workspace import _app, _open_import

from capa_simulation.components.equipment_data_workspace import CSV_UPLOAD_LIMIT_MB
from capa_simulation.settings import PROJECT_ROOT


def _server_upload_limit_mb() -> int:
    """`.streamlit/config.toml` 의 `server.maxUploadSize`(MB) — Streamlit 과 같은 파서로 읽는다."""
    toml = importlib.import_module("toml")
    parsed: dict[str, dict[str, object]] = toml.loads(
        (PROJECT_ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8")
    )
    value = parsed["server"]["maxUploadSize"]
    assert isinstance(value, int)
    return value


def test_the_equipment_csv_upload_box_has_its_own_limit_below_the_server_limit(
    tmp_path: Path,
) -> None:
    """설비 CSV 칸은 `server.maxUploadSize`(앱 전체 상한)를 물려받지 않고 50MB 로 막는다.

    CSV 파싱은 파일 크기의 몇 배 메모리를 쓰므로 잘못 고른 큰 파일 하나가 공용 앱 프로세스를 몰 수
    있다. 칸 안내(「50MB per file」)와 브라우저가 올리기 전에 막는 크기가 이 값이다.
    """
    app = _open_import(_app(tmp_path / "equipment.duckdb"))

    assert not app.exception
    uploaders = app.get("file_uploader")
    assert [element.proto.label for element in uploaders] == ["또는 CSV 파일 업로드"]
    assert CSV_UPLOAD_LIMIT_MB == 50
    assert uploaders[0].proto.max_upload_size_mb == CSV_UPLOAD_LIMIT_MB
    assert CSV_UPLOAD_LIMIT_MB < _server_upload_limit_mb()


def test_the_server_upload_limit_is_the_streamlit_default() -> None:
    """앱 전체 상한은 200MB(Streamlit 기본값)다 — 2026-11-17 메모리 보드 q-upload 「200MB 로
    낮춘다」 가 2026-10-22 「1024 유지」 를 뒤집었다. 올린 파일은 통째로 서버 메모리 바이트라 큰
    파일 하나가 컨테이너 메모리 한도(1GiB)를 넘기면 앱이 다시 선다. 모듈 올리기 칸도 이 값을
    물려받는다(`docs/module_guide.md` 3-9 데모 표 예시 아래)."""
    assert _server_upload_limit_mb() == 200
