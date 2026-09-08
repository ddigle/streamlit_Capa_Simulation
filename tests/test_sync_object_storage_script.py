# Purpose: 오브젝트 스토리지 운영 스크립트의 인자 처리와 설정 우선순위를 검증한다.

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "sync_object_storage.py"


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("sync_object_storage", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["sync_object_storage"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def script() -> ModuleType:
    return _load_script()


def test_every_subcommand_is_wired(script: ModuleType) -> None:
    """도움말에만 있고 구현이 없는 명령이 생기면 사내에서 처음 눌렀을 때 죽는다."""
    expected = {
        "profile",
        "doctor",
        "probe",
        "init",
        "status",
        "pull",
        "push",
        "resolve",
        "adopt",
        "prune",
    }

    assert set(script.COMMANDS) == expected


def test_command_line_profile_overrides_the_configured_one(script: ModuleType) -> None:
    """WebIDE 로 옮기면 프로필명이 바뀐다. 손으로 덮어쓸 수 있어야 한다."""
    args = script.parse_args(["--profile", "other-profile", "status"])

    settings = script.build_settings(args)

    assert settings.profile == "other-profile"


def test_settings_fall_back_to_the_committed_configuration(script: ModuleType) -> None:
    args = script.parse_args(["status"])

    settings = script.build_settings(args)

    assert settings.bucket == "Capa_simulation_project"
    assert settings.endpoint_url.endswith(":9020")
    # 커밋된 설정은 local 이어야 한다. 개발 PC 가 사내 스토리지를 건드리면 안 된다.
    assert settings.mode == "local"


def test_dataset_selection_defaults_to_both_databases(script: ModuleType) -> None:
    assert script.datasets(script.parse_args(["status"])) == ["simulation", "equipment"]
    assert script.datasets(script.parse_args(["--dataset", "equipment", "status"])) == ["equipment"]


def test_prune_requires_an_explicit_yes(script: ModuleType) -> None:
    """정리는 되돌릴 수 없다. 확인 없이 지우지 않는다."""
    args = script.parse_args(["prune"])

    assert args.yes is False
    assert args.include_orphans is False
    assert args.keep_last == 10


def test_resolve_requires_choosing_a_side(script: ModuleType) -> None:
    with pytest.raises(SystemExit):
        script.parse_args(["resolve"])

    assert script.parse_args(["resolve", "--keep", "mine"]).keep == "mine"


def test_dataset_paths_cover_both_databases(script: ModuleType) -> None:
    assert set(script.DATASET_PATHS) == {"simulation", "equipment"}
    assert script.DATASET_PATHS["simulation"].name.endswith(".duckdb")


def test_profile_command_prints_a_ready_to_paste_block(
    script: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    """사내 PC 에서 손으로 옮겨 적다가 오타 나는 일을 없앤다."""
    script.command_profile(script.parse_args(["profile"]))

    printed = capsys.readouterr().out

    assert "--profile $PROF" in printed
    assert "s3.addressing_style path" in printed
    assert "request_checksum_calculation when_required" in printed
    assert "org-system_package_mfg_team" in printed
