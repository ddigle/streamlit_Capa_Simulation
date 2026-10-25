# Purpose: 설비 마스터 엑셀·CSV 팝업의 CSV 칸이 서버 전체보다 낮은 칸 고유 상한을 쓰는지 본다.

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
