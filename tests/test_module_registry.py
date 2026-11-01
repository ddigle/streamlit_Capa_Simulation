# Purpose: 사내 모듈 찾기·module.json 검증·상태와 까닭·끄는 환경변수·찾기 캐시를 고정한다.

from __future__ import annotations

import ast
import json
import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from capa_simulation import module_registry, settings
from capa_simulation.module_registry import (
    API_MINOR,
    DISABLED_ENV_VAR,
    GROUP_MAIN_TITLE,
    MANIFEST_NAME,
    ROOT_ENV_VAR,
    ManifestError,
    ModuleScan,
    TitleClash,
    cached_manifest,
    discovered,
    key_prefix,
    module_folder_for,
    modules_root,
    page_url_path,
    parse_disabled,
    parse_manifest,
    scan_modules,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = PROJECT_ROOT / "tests" / "fixtures" / "modules"
# 코어 화면 이름(「(구현중)」 뗀 것) 가운데 시험에 쓰는 둘.
CORE_TITLES = ("HOME", "생산 계획")


def _states(scan: ModuleScan) -> dict[str, tuple[str, str]]:
    return {record.folder_name: (record.state, record.reason) for record in scan.records}


def _write_module(
    root: Path,
    module_id: str,
    *,
    folder: str | None = None,
    write_pages: bool = True,
    **fields: Any,
) -> Path:
    """tmp 모듈 하나 — 맞는 선언에 `fields` 를 덮는다(값이 None 이면 그 칸을 뺀다)."""
    place = root / (folder or module_id)
    place.mkdir(parents=True, exist_ok=True)
    declared: dict[str, Any] = {
        "id": module_id,
        "name": "데모",
        "api": 1,
        "owner": "데모 담당",
        "enabled": True,
        "maturity": "L0",
        "pages": [{"slug": "main", "file": "page.py", "title": f"화면 {len(module_id)}"}],
    }
    for name, value in fields.items():
        if value is None:
            declared.pop(name, None)
        else:
            declared[name] = value
    (place / MANIFEST_NAME).write_text(json.dumps(declared, ensure_ascii=False), encoding="utf-8")
    pages = declared.get("pages")
    if write_pages and isinstance(pages, list):
        for page in pages:
            if isinstance(page, dict) and isinstance(page.get("file"), str):
                target = place / page["file"]
                if "/" not in page["file"] and not target.exists():
                    target.write_text("# Purpose: 시험 화면.\n", encoding="utf-8")
    return place


def _one(root: Path) -> tuple[str, str]:
    (record,) = scan_modules(root, reserved_titles=CORE_TITLES).records
    return record.state, record.reason


# ------------------------------------------------------------------ 견본


def test_the_fixture_modules_get_their_states_and_reasons() -> None:
    scan = scan_modules(FIXTURES, reserved_titles=CORE_TITLES)

    assert scan.root_exists and not scan.root_error
    # 모듈 order → id 차례(order 를 주지 않은 것은 100).
    assert [record.folder_name for record in scan.records] == [
        "demo_ok",
        "demo_crash",
        "demo_keys",
        "demo_bad_manifest",
        "demo_future_api",
        "demo_off",
    ]
    assert _states(scan) == {
        "demo_ok": ("on", ""),
        "demo_crash": ("on", ""),
        "demo_keys": ("on", ""),
        "demo_off": ("off", "module.json enabled=false"),
        "demo_future_api": ("failed", "API 판 99 — 이 코어는 1 만 받는다"),
        "demo_bad_manifest": ("failed", "모르는 칸: enable"),
    }
    assert [record.folder_name for record in scan.active] == ["demo_ok", "demo_crash", "demo_keys"]
    ok = scan.records[0].manifest
    assert ok is not None
    # 화면은 order → slug 차례로 정렬되고, 아이콘을 주지 않으면 기본 아이콘이다.
    assert [page.slug for page in ok.pages] == ["main", "second"]
    crash = scan.records[1].manifest
    assert crash is not None and {page.icon for page in crash.pages} == {":material/extension:"}
    # 선언을 못 읽은 모듈은 manifest 가 없고, 판이 틀린 모듈은 선언을 들고 있다.
    by_name = {record.folder_name: record for record in scan.records}
    assert by_name["demo_bad_manifest"].manifest is None
    assert by_name["demo_future_api"].manifest is not None


def test_active_is_computed_once_per_scan() -> None:
    scan = scan_modules(FIXTURES)

    assert scan.active is scan.active


# ------------------------------------------------------------------ 뿌리


def test_a_missing_or_empty_root_gives_an_empty_scan(tmp_path: Path) -> None:
    missing = scan_modules(tmp_path / "nowhere")
    empty = scan_modules(tmp_path)
    off = scan_modules(None)

    assert (missing.root_exists, missing.records) == (False, ())
    assert (empty.root_exists, empty.records) == (True, ())
    assert (off.root, off.root_exists, off.records) == (None, False, ())


@pytest.mark.parametrize("value", ["off", "OFF", " Off "])
def test_the_root_variable_off_means_no_root(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv(ROOT_ENV_VAR, value)

    assert modules_root() is None
    scan = discovered()
    assert (scan.root, scan.root_exists, scan.records) == (None, False, ())


def test_the_root_variable_points_at_its_folder(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ROOT_ENV_VAR, str(FIXTURES))
    assert modules_root() == FIXTURES
    assert len(discovered().active) == 3

    monkeypatch.setenv(ROOT_ENV_VAR, "")
    assert modules_root() == settings.MODULES_DIR


def test_dot_and_underscore_folders_and_plain_files_are_skipped(tmp_path: Path) -> None:
    _write_module(tmp_path, "demo_a")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / ".cache").mkdir()
    (tmp_path / "_draft").mkdir()
    (tmp_path / "README.md").write_text("모듈 폴더 설명", encoding="utf-8")

    assert [record.folder_name for record in scan_modules(tmp_path).records] == ["demo_a"]


# ------------------------------------------------------------------ 선언 파일


def test_broken_json_fails_with_where_it_broke(tmp_path: Path) -> None:
    folder = tmp_path / "demo_a"
    folder.mkdir()
    (folder / MANIFEST_NAME).write_text('{"id": "demo_a",', encoding="utf-8")

    state, reason = _one(tmp_path)
    assert state == "failed" and reason.startswith("module.json 파일이 JSON 이 아닙니다 — 1줄")


def test_utf8_with_a_bom_is_read_and_utf16_is_not(tmp_path: Path) -> None:
    folder = _write_module(tmp_path / "bom", "demo_a")
    text = (folder / MANIFEST_NAME).read_text(encoding="utf-8")
    (folder / MANIFEST_NAME).write_bytes(text.encode("utf-8-sig"))
    assert _one(tmp_path / "bom") == ("on", "")

    other = _write_module(tmp_path / "utf16", "demo_a")
    (other / MANIFEST_NAME).write_bytes(text.encode("utf-16"))
    assert _one(tmp_path / "utf16") == ("failed", "module.json 파일이 UTF-8 이 아닙니다")


def test_a_manifest_over_64_kb_fails(tmp_path: Path) -> None:
    folder = _write_module(tmp_path, "demo_a")
    (folder / MANIFEST_NAME).write_text(" " * 65_537, encoding="utf-8")

    assert _one(tmp_path) == ("failed", "module.json 파일이 64 KB 를 넘습니다")
    with pytest.raises(ManifestError, match="64 KB"):
        parse_manifest(b" " * 65_537, folder_name="demo_a")


def test_a_missing_manifest_fails(tmp_path: Path) -> None:
    (tmp_path / "demo_a").mkdir()

    assert _one(tmp_path) == ("failed", "module.json 파일이 없습니다")


# ------------------------------------------------------------------ id


@pytest.mark.parametrize(
    ("folder", "module_id", "expected"),
    [
        ("demo_a", "demo_b", "id 와 폴더 이름이 다릅니다: id demo_b · 폴더 demo_a"),
        ("Demo_a", "Demo_a", "폴더 이름이 규칙에 맞지 않음"),
        ("demo__a", "demo__a", "폴더 이름이 규칙에 맞지 않음"),
        ("demo_", "demo_", "폴더 이름이 규칙에 맞지 않음"),
        ("import", "import", "폴더 이름이 규칙에 맞지 않음"),
        ("class", "class", "폴더 이름이 규칙에 맞지 않음"),
    ],
)
def test_module_ids_follow_the_rule(
    tmp_path: Path, folder: str, module_id: str, expected: str
) -> None:
    _write_module(tmp_path, module_id, folder=folder)

    assert _one(tmp_path) == ("failed", expected)


def test_the_id_rule_rejects_keywords_case_and_double_underscores() -> None:
    valid = module_registry.is_valid_module_id

    assert valid("demo_ok") and valid("ab") and valid("a1_b2")
    for value in ("a", "Demo", "demo__x", "1abc", "demo_", "import", "class", "async", "x" * 25):
        assert not valid(value), value
    declared = {
        "id": "global",
        "name": "데모",
        "api": 1,
        "owner": "데모 담당",
        "enabled": True,
        "maturity": "L0",
        "pages": [{"slug": "main", "file": "page.py", "title": "화면"}],
    }
    with pytest.raises(ManifestError, match="파이썬 예약어"):
        parse_manifest(json.dumps(declared).encode(), folder_name="global")


# ------------------------------------------------------------------ 화면 파일·아이콘


def test_a_missing_page_file_fails(tmp_path: Path) -> None:
    _write_module(tmp_path, "demo_a", write_pages=False)

    assert _one(tmp_path) == ("failed", "화면 파일이 없습니다: page.py")


def test_a_symlink_page_pointing_outside_fails(tmp_path: Path) -> None:
    root = tmp_path / "modules"
    folder = _write_module(root, "demo_a", write_pages=False)
    outside = tmp_path / "outside.py"
    outside.write_text("# Purpose: 밖.\n", encoding="utf-8")
    (folder / "page.py").symlink_to(outside)

    assert _one(root) == ("failed", "화면 파일이 심볼릭 링크입니다: page.py")


def test_a_page_in_a_subfolder_is_a_manifest_error(tmp_path: Path) -> None:
    _write_module(
        tmp_path, "demo_a", pages=[{"slug": "main", "file": "sub/page.py", "title": "화면"}]
    )

    state, reason = _one(tmp_path)
    assert state == "failed" and "하위 폴더 안 됨" in reason


def test_a_page_file_spelled_with_other_case_on_disk_fails(tmp_path: Path) -> None:
    folder = _write_module(tmp_path, "demo_a", write_pages=False)
    (folder / "Page.py").write_text("# Purpose: 대문자.\n", encoding="utf-8")

    assert _one(tmp_path) == (
        "failed",
        "화면 파일 이름의 대소문자가 다릅니다: 디스크 Page.py · 선언 page.py",
    )


@pytest.mark.parametrize(
    ("icon", "expected"),
    [
        (":material/nope_nope:", "아이콘 이름이 Material 에 없습니다: :material/nope_nope:"),
        ("🧩", "icon 은 :material/<이름>: 꼴이어야 합니다"),
        (" :material/extension: ", "icon 은 :material/<이름>: 꼴이어야 합니다"),
    ],
)
def test_page_icons_are_exact_material_names(tmp_path: Path, icon: str, expected: str) -> None:
    _write_module(
        tmp_path,
        "demo_a",
        pages=[{"slug": "main", "file": "page.py", "title": "화면", "icon": icon}],
    )

    state, reason = _one(tmp_path)
    assert state == "failed" and expected in reason, reason


# ------------------------------------------------------------------ 화면 이름


@pytest.mark.parametrize("title", ["**굵게**", ":red[x]", "a_b", "[링크]", "가$1"])
def test_titles_with_markdown_characters_fail(tmp_path: Path, title: str) -> None:
    _write_module(tmp_path, "demo_a", pages=[{"slug": "main", "file": "page.py", "title": title}])

    state, reason = _one(tmp_path)
    assert state == "failed" and "Markdown 글자" in reason


@pytest.mark.parametrize("title", ["HOME", "생산 계획", GROUP_MAIN_TITLE])
def test_titles_that_clash_with_core_names_fail(tmp_path: Path, title: str) -> None:
    _write_module(tmp_path, "demo_a", pages=[{"slug": "main", "file": "page.py", "title": title}])

    assert _one(tmp_path) == ("failed", f"화면 이름 겹침: {title} — 코어 화면")


def test_a_title_repeated_inside_one_module_is_a_manifest_error(tmp_path: Path) -> None:
    _write_module(
        tmp_path,
        "demo_a",
        pages=[
            {"slug": "one", "file": "one.py", "title": "같은 이름"},
            {"slug": "two", "file": "two.py", "title": "같은 이름"},
        ],
    )

    assert _one(tmp_path) == ("failed", "모듈 안에서 겹치는 화면 title: 같은 이름")


def test_a_title_clash_between_modules_fails_only_the_later_one(tmp_path: Path) -> None:
    same = [{"slug": "main", "file": "page.py", "title": "같은 이름"}]
    _write_module(tmp_path, "demo_a", pages=same, order=10)
    _write_module(tmp_path, "demo_b", pages=same, order=20)
    # 꺼진 모듈은 겹침을 보지 않고 뒤 모듈을 막지도 않는다.
    _write_module(tmp_path, "demo_c", pages=same, order=5, enabled=False)

    scan = scan_modules(tmp_path)
    assert _states(scan) == {
        "demo_c": ("off", "module.json enabled=false"),
        "demo_a": ("on", ""),
        "demo_b": ("failed", "화면 이름 겹침: 같은 이름 — 차례가 앞인 모듈 demo_a"),
    }
    clashes = {record.folder_name: record.clash for record in scan.records}
    assert clashes == {"demo_c": None, "demo_a": None, "demo_b": TitleClash("같은 이름", "demo_a")}


def test_a_new_module_earlier_in_order_pushes_out_a_running_one_and_is_named(
    tmp_path: Path,
) -> None:
    """겹침은 「나중에 들어온 쪽」 이 아니라 차례(order → id)가 뒤인 쪽 **전체**를 뺀다 — 겹치지
    않는 화면까지 빠진다. 기존 모듈 담당자가 자기가 바꾸지 않은 실패를 받으므로 까닭에 상대를
    적는다(지침서 3-3 · 부록 B M01)."""
    _write_module(
        tmp_path,
        "demo_port",
        pages=[
            {"slug": "main", "file": "page.py", "title": "개요"},
            {"slug": "detail", "file": "detail.py", "title": "상세"},
        ],
    )
    _write_module(
        tmp_path,
        "demo_table",
        pages=[{"slug": "main", "file": "page.py", "title": "개요"}],
        order=50,
    )

    assert _states(scan_modules(tmp_path)) == {
        "demo_table": ("on", ""),
        "demo_port": ("failed", "화면 이름 겹침: 개요 — 차례가 앞인 모듈 demo_table"),
    }


def test_a_module_switched_off_by_the_variable_does_not_block_others(tmp_path: Path) -> None:
    same = [{"slug": "main", "file": "page.py", "title": "같은 이름"}]
    _write_module(tmp_path, "demo_a", pages=same, order=10)
    _write_module(tmp_path, "demo_b", pages=same, order=20)

    assert _states(scan_modules(tmp_path, disabled="demo_a")) == {
        "demo_a": ("off", f"환경변수 {DISABLED_ENV_VAR}"),
        "demo_b": ("on", ""),
    }


# ------------------------------------------------------------------ 칸


@pytest.mark.parametrize(
    ("fields", "expected"),
    [
        ({"enable": True}, "모르는 칸: enable"),
        ({"enabled": "true"}, 'enabled 는 true 또는 false 여야 합니다(글자 "true" 안 됨)'),
        ({"order": 1000}, "0 ~ 999 사이 정수여야 하는 칸입니다: order"),
        ({"order": -1}, "0 ~ 999 사이 정수여야 하는 칸입니다: order"),
        ({"order": True}, "0 ~ 999 사이 정수여야 하는 칸입니다: order"),
        ({"api": "1"}, "api 는 정수여야 합니다"),
        ({"maturity": "L3"}, "maturity 는 L0 · L1 · L2 가운데 하나여야 합니다"),
        ({"name": ""}, "1 ~ 30자여야 하는 칸입니다: name"),
        ({"owner": "가" * 31}, "1 ~ 30자여야 하는 칸입니다: owner"),
        ({"description": "가" * 121}, "0 ~ 120자여야 하는 칸입니다: description"),
        ({"pages": []}, "pages 는 화면 1 ~ 8개의 배열이어야 합니다"),
        ({"pages": None}, "빠진 칸: pages"),
        ({"api_minor": 100}, "0 ~ 99 사이 정수여야 하는 칸입니다: api_minor"),
    ],
)
def test_manifest_fields_are_checked(tmp_path: Path, fields: dict[str, Any], expected: str) -> None:
    _write_module(tmp_path, "demo_a", **fields)

    assert _one(tmp_path) == ("failed", expected)


def test_a_newer_api_minor_than_the_core_fails_with_both_versions(tmp_path: Path) -> None:
    _write_module(tmp_path, "demo_a", api_minor=API_MINOR + 1)

    assert _one(tmp_path) == ("failed", f"API 1.{API_MINOR + 1} 필요 — 이 코어는 1.{API_MINOR}")


def test_a_wrong_manifest_fails_even_when_switched_off(tmp_path: Path) -> None:
    _write_module(tmp_path, "demo_a", enabled=False, order=5000)

    assert scan_modules(tmp_path, disabled="*").records[0].state == "failed"


def test_one_folder_raising_leaves_the_others_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_module(tmp_path, "demo_a")
    _write_module(tmp_path, "demo_b", pages=[{"slug": "m", "file": "page.py", "title": "둘째"}])
    original = module_registry.read_manifest

    def exploding(folder: Path) -> module_registry.ModuleManifest:
        if folder.name == "demo_a":
            raise KeyError("터짐")
        return original(folder)

    monkeypatch.setattr(module_registry, "read_manifest", exploding)

    assert _states(scan_modules(tmp_path)) == {
        "demo_a": ("failed", "검사 중 예외 KeyError"),
        "demo_b": ("on", ""),
    }


# ------------------------------------------------------------------ 끄는 환경변수


def test_parse_disabled_reads_all_ids_and_spaces() -> None:
    assert parse_disabled(None) == (False, frozenset())
    assert parse_disabled("") == (False, frozenset())
    assert parse_disabled("*") == (True, frozenset())
    assert parse_disabled(" demo_a , demo_b ,") == (False, frozenset({"demo_a", "demo_b"}))


def test_the_disabled_variable_switches_modules_off_and_names_unknown_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(ROOT_ENV_VAR, str(FIXTURES))
    monkeypatch.setenv(DISABLED_ENV_VAR, "demo_ok, demo_ghost")
    scan = discovered()

    assert _states(scan)["demo_ok"] == ("off", f"환경변수 {DISABLED_ENV_VAR}")
    assert [record.folder_name for record in scan.active] == ["demo_crash", "demo_keys"]
    assert scan.unknown_disabled == ("demo_ghost",)
    assert scan.disabled_value == "demo_ok, demo_ghost"

    monkeypatch.setenv(DISABLED_ENV_VAR, "*")
    every = discovered()
    assert every.active == ()
    # 선언이 틀린 모듈은 꺼 두어도 실패로 남는다 — 고칠 것이 보이게.
    assert {record.state for record in every.records} == {"off", "failed"}


# ------------------------------------------------------------------ 캐시·성능


@contextmanager
def _counting(monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, int]]:
    # `Path.stat` 은 3.10 에서 `os.stat` 을 import 때 붙잡아 따로 센다.
    counts = {"scandir": 0, "resolve": 0, "stat": 0}

    def wrap(name: str, function: Callable[..., Any]) -> Callable[..., Any]:
        def counted(*args: Any, **kwargs: Any) -> Any:
            counts[name] += 1
            return function(*args, **kwargs)

        return counted

    with monkeypatch.context() as patch:
        patch.setattr(os, "scandir", wrap("scandir", os.scandir))
        patch.setattr(os, "stat", wrap("stat", os.stat))
        patch.setattr(Path, "stat", wrap("stat", Path.stat))
        patch.setattr(Path, "resolve", wrap("resolve", Path.resolve))
        yield counts


def test_discovery_scans_once_and_a_repeat_touches_no_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(ROOT_ENV_VAR, str(FIXTURES))
    with _counting(monkeypatch) as first:
        scan = discovered(reserved_titles=CORE_TITLES)
    with _counting(monkeypatch) as second:
        again = discovered(reserved_titles=CORE_TITLES)

    assert first["scandir"] == 1
    assert again is scan
    assert second == {"scandir": 0, "resolve": 0, "stat": 0}


def test_without_modules_the_first_run_only_asks_whether_the_root_is_a_folder(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(ROOT_ENV_VAR, str(tmp_path / "absent"))
    with _counting(monkeypatch) as first:
        discovered()
    with _counting(monkeypatch) as second:
        discovered()

    assert first == {"scandir": 0, "resolve": 0, "stat": 1}
    assert second == {"scandir": 0, "resolve": 0, "stat": 0}


def test_the_cache_key_follows_the_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ROOT_ENV_VAR, str(FIXTURES))
    on = discovered()
    monkeypatch.setenv(ROOT_ENV_VAR, "off")
    off = discovered()

    assert len(on.active) == 3 and off.records == ()
    module_registry.clear_discovery_cache()
    monkeypatch.setenv(ROOT_ENV_VAR, str(FIXTURES))
    assert discovered() is not on


# ------------------------------------------------------------------ 꼴·문맥


def test_key_prefix_and_page_address_shapes() -> None:
    assert key_prefix("demo_ok") == "mod_demo_ok__"
    assert page_url_path("demo_ok", "main") == "mod-demo_ok-main"


def test_the_module_folder_is_found_up_to_four_levels(tmp_path: Path) -> None:
    folder = _write_module(tmp_path, "demo_a")
    deep = folder / "a" / "b" / "c"
    deep.mkdir(parents=True)

    assert module_folder_for(folder / "page.py") == folder
    assert module_folder_for(deep / "x.py") == folder
    with pytest.raises(ManifestError):
        module_folder_for(deep / "d" / "x.py")
    with pytest.raises(ManifestError):
        module_folder_for(tmp_path / "elsewhere" / "x.py")


def test_the_cached_manifest_is_read_again_after_the_file_changes(tmp_path: Path) -> None:
    folder = _write_module(tmp_path, "demo_a", name="처음")
    assert cached_manifest(folder).name == "처음"
    assert cached_manifest(folder) is cached_manifest(folder)

    path = folder / MANIFEST_NAME
    declared = json.loads(path.read_text(encoding="utf-8"))
    declared["name"] = "나중 이름"
    path.write_text(json.dumps(declared, ensure_ascii=False), encoding="utf-8")
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))

    assert cached_manifest(folder).name == "나중 이름"


def test_the_data_root_follows_its_variable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(module_registry.DATA_ROOT_ENV_VAR, str(tmp_path))
    assert module_registry.data_root() == tmp_path

    monkeypatch.delenv(module_registry.DATA_ROOT_ENV_VAR)
    assert module_registry.data_root() == settings.MODULES_DATA_DIR


def test_the_group_main_title_matches_the_app_label() -> None:
    """`app.py` 를 import 하면 앱이 통째로 돌아 AST 로 읽는다(`_app_constant` 꼴)."""
    tree = ast.parse((PROJECT_ROOT / "app.py").read_text(encoding="utf-8"))
    values = [
        ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "GROUP_MAIN_LABEL"
            for target in node.targets
        )
    ]

    assert values == [GROUP_MAIN_TITLE]
