# Purpose: 가이드 생성기 · 점검기의 조립 · 덮어쓰기 · 거절 · 쓰기 등급을 가짜 촬영으로 잰다.

"""따라하기 가이드 생성기(`scripts/build_page_guide.py`)와 점검기(`scripts/check_page_guide.py`).

촬영은 브라우저 · 앱이 있어야 하므로 여기서는 가짜 촬영 결과(단색 그림 + 계획의 표적 좌표)로
조립 · 리뷰 한 줄을 돌리고, 촬영 차례(새 세션 · 쓰기 등급으로 건너뛰기)는 가짜 촬영기로 잰다.
생성기의 촬영 길(사내 쓰기 등급 건너뛰기 · 사본 DB 기준 지문 · 종료 코드)은 앱 · 브라우저 ·
촬영기만 가짜로 바꾸고 `build_page_guide.main` 을 끝까지 돌려 잰다. 실제 촬영은 사외 예시판을
만들 때(`--example`) 사람이 돌려 본다.
"""

from __future__ import annotations

import argparse
import base64
import copy
import dataclasses
import hashlib
import io
import json
import os
import re
import subprocess
import sys
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import build_page_guide as builder  # noqa: E402
import check_deploy_screens as screens  # noqa: E402
import check_page_guide as checker  # noqa: E402
import page_guide_capture as capture  # noqa: E402
import page_guide_core as core  # noqa: E402

from capa_simulation import settings  # noqa: E402
from capa_simulation.components import app_credits  # noqa: E402

VIEWPORT = (1440, 900)
SKELETON = core.load_skeleton()
INTERNAL_FIRST_PASS = 18
DATE = "2026-10-22"


# ------------------------------------------------------------------ 가짜 촬영 결과


def _rect_for(index: int) -> list[float]:
    """표적마다 겹치지 않는 작은 사각형 — 화면 왼쪽 위에서 차례로 쌓는다."""
    column, row = divmod(index, 12)
    return [40.0 + column * 300, 40.0 + row * 70, 220.0, 40.0]


def _fake_shots(
    folder: Path,
    state_ids: Sequence[str],
    *,
    mode: str,
    missing: Mapping[str, Sequence[str]] | None = None,
    scale: float = 1.0,
    suffix: str = "png",
) -> core.ShotSet:
    """계획의 상태 · 표적대로 단색 그림과 좌표를 만든다."""
    shots = core.ShotSet(viewport=VIEWPORT, scale=scale, mode=mode, version=SKELETON.version)
    pictures = folder / "shots"
    pictures.mkdir(parents=True, exist_ok=True)
    for number, state_id in enumerate(state_ids):
        size = (int(VIEWPORT[0] * scale), int(VIEWPORT[1] * scale))
        image = pictures / f"{state_id}.{suffix}"
        Image.new("RGB", size, (200, 210 + number % 40, 220)).save(image)
        absent = set((missing or {}).get(state_id, ()))
        names = [name for name in SKELETON.target_names(state_id) if name not in absent]
        shots.states[state_id] = core.ShotState(
            id=state_id,
            image=image,
            targets={name: _rect_for(i) for i, name in enumerate(names)},
            missing=sorted(absent),
            date=DATE,
            scale=scale,
        )
    core.save_shots(shots, folder)
    return shots


def _run_facts(folder: Path, *, mode: str, db: str, **extra: Any) -> core.RunFacts:
    facts = core.RunFacts(mode=mode, version=SKELETON.version, db=db, **extra)
    core.save_run(facts, folder)
    return facts


def _decode(uri: str) -> Image.Image:
    head, _, body = uri.partition(",")
    assert head == "data:image/webp;base64"
    return Image.open(io.BytesIO(base64.b64decode(body)))


# ------------------------------------------------------------------ 조립 계산


def test_frame_adds_padding_keeps_minimum_and_stays_inside_the_screen() -> None:
    # 여백 44 를 붙여도 최소 460×250 에 못 미쳐 가운데로 넓히고, 화면 밖은 안으로 민다
    assert core.frame_around([[100, 100, 50, 20]], VIEWPORT) == [0, 0, 460, 250]
    # 넓은 합집합은 왼쪽을 0 으로 밀고 오른쪽은 화면 끝(1440)에서 자른다
    wide = core.frame_around([[10, 300, 900, 40], [1300, 320, 100, 40]], VIEWPORT)
    assert wide == [0, 205, 1440, 250]

    assert core.frame_around([], VIEWPORT) is None


def test_pct_boxes_are_relative_to_the_frame_and_clipped() -> None:
    assert core.pct([150, 150, 100, 50], [100, 100, 400, 200]) == {
        "x": 12.5,
        "y": 25.0,
        "w": 25.0,
        "h": 25.0,
    }
    # 틀 밖으로 나간 부분은 잘라 낸다(긴 표 · 화면 아래로 이어지는 요소)
    assert core.pct([450, 250, 200, 200], [100, 100, 400, 200]) == {
        "x": 87.5,
        "y": 75.0,
        "w": 12.5,
        "h": 25.0,
    }


def _one_step_shots(tmp_path: Path, rects: Mapping[str, list[float]]) -> core.ShotSet:
    image = tmp_path / "s.png"
    Image.new("RGB", (VIEWPORT[0] * 2, VIEWPORT[1] * 2), (240, 240, 240)).save(image)
    shots = core.ShotSet(viewport=VIEWPORT, scale=2.0, mode="example", version=SKELETON.version)
    shots.states["s"] = core.ShotState(id="s", image=image, targets=dict(rects), scale=2.0)
    return shots


def test_scattered_targets_are_cut_one_by_one_and_stacked(tmp_path: Path) -> None:
    shots = _one_step_shots(tmp_path, {"a": [20, 100, 120, 30], "b": [900, 700, 120, 30]})
    assembler = core.Assembler(shots)
    step = assembler.step(
        {"id": "t"},
        {"id": "x", "state": "s", "focus": [{"t": "a", "n": 1}, {"t": "b", "n": 2}]},
    )

    assert "crop" not in step and len(step["crops"]) == 2
    for piece, number in zip(step["crops"], (1, 2), strict=True):
        assert [box["n"] for box in piece["boxes"]] == [number]
        picture = _decode(assembler.images[piece["crop"]["src"]])
        # 장마다 최소 440×150 을 배율 2 로 자르고 폭 960 이하로 줄였다
        assert picture.width == 880 and picture.height == 300
        assert piece["crop"]["cap"] == core.EXAMPLE_LABEL
    assert len(step["fullBoxes"]) == 2


def test_one_wide_target_keeps_only_its_left_part(tmp_path: Path) -> None:
    shots = _one_step_shots(tmp_path, {"form": [100, 200, 1200, 300]})
    assembler = core.Assembler(shots)
    step = assembler.step({"id": "t"}, {"id": "x", "state": "s", "focus": [{"t": "form", "n": 1}]})
    narrow = assembler.step(
        {"id": "t"}, {"id": "y", "state": "s", "clip_w": 620, "focus": [{"t": "form", "n": 1}]}
    )

    assert step["area"]["w"] == pytest.approx(core.CLIP_W / VIEWPORT[0] * 100, abs=0.01)
    assert narrow["area"]["w"] == pytest.approx(620 / VIEWPORT[0] * 100, abs=0.01)
    picture = _decode(assembler.images[step["crop"]["src"]])
    assert picture.width == core.CROP_MAX  # 700 × 2 = 1400 을 960 으로 줄였다
    # 상자는 틀 밖으로 나간 부분을 잘라 % 로 — 오른쪽이 잘려 100% 에 닿는다
    box = step["boxes"][0]
    assert box["x"] + box["w"] == pytest.approx(100.0, abs=0.01)


def test_frame_false_targets_get_a_box_but_do_not_widen_the_cut(tmp_path: Path) -> None:
    shots = _one_step_shots(tmp_path, {"cell": [600, 400, 80, 30], "area": [0, 0, 1440, 900]})
    assembler = core.Assembler(shots)
    step = assembler.step(
        {"id": "t"},
        {
            "id": "x",
            "state": "s",
            "focus": [{"t": "cell", "n": 1}, {"t": "area", "kind": "see", "frame": False}],
        },
    )

    assert step["area"]["w"] == pytest.approx(core.MIN_W / VIEWPORT[0] * 100, abs=0.01)
    assert [box["kind"] for box in step["boxes"]] == ["do", "see"]


def test_assembler_records_its_cut_frames_and_can_run_without_opening_pictures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """바뀐 자리 검수의 틀 기록 — 원고 자리마다 `crop()` 에 넘긴 틀을 적고(그림을 못 낸 조각은
    None), `pictures=False` 는 그림을 열지 않고 같은 데이터 · 같은 틀을 낸다."""
    _fake_shots(tmp_path, SKELETON.state_ids(), mode="example")
    _run_facts(tmp_path, mode="example", db="example")
    shots, _run = core.board_shots(SKELETON, tmp_path)
    shots.states["04_procfilter_open"].targets["pf_all_on"] = [1200.0, 700.0, 100.0, 40.0]
    del shots.states["01_home_main"].targets["lob_chart"]

    def assemble_with(assembler: core.Assembler) -> list[dict[str, Any]]:
        pieces = [assembler.task(task) for task in SKELETON.content["tasks"]]
        return pieces + [assembler.concept(concept) for concept in SKELETON.content["concepts"]]

    pictured = core.Assembler(shots)
    with_pictures = assemble_with(pictured)

    def refuse_to_open(*_args: Any, **_kwargs: Any) -> Image.Image:
        raise AssertionError("pictures=False 인데 그림을 열었다")

    monkeypatch.setattr(Image, "open", refuse_to_open)
    plain = core.Assembler(shots, pictures=False)

    assert assemble_with(plain) == with_pictures
    assert plain.images == {} and plain.frames == pictured.frames
    assert plain.frames["thumb:lob_map"] == [None]  # 썸네일 표적을 못 찾았다
    assert len(plain.frames["step:proc_filter.toggle"]) == 2  # 흩어진 표적은 표적마다 한 장
    assert set(plain.frames) == {where for where, _state in core.picture_refs(SKELETON.content)}
    cut = {
        tuple(int(value) for value in key.split(":")[2].split(","))
        for key in pictured.images
        if key.startswith("crop:")
    }
    assert cut == {tuple(f) for frames in plain.frames.values() for f in frames if f is not None}


def test_whole_board_assembles_from_fake_shots_and_injects_safe_json(tmp_path: Path) -> None:
    _fake_shots(tmp_path, SKELETON.state_ids(), mode="example")
    _run_facts(tmp_path, mode="example", db="example")
    shots, _run = core.board_shots(SKELETON, tmp_path)
    content = json.loads(json.dumps(SKELETON.content))
    content["tasks"][0]["sub"] = "</script><script>alert(1)</script><!--"
    data, report = core.assemble(content, shots)
    template = (core.HOWTO_DIR / "template.html").read_text(encoding="utf-8")
    html = core.render_html(template, data)

    assert report.no_picture == [] and report.missing_boxes == []
    assert report.images == len(data["images"]) > 40
    assert all(uri.startswith("data:image/webp;base64,") for uri in data["images"].values())
    assert html.count("</script>") == template.count("</script>")
    assert "<!--" not in html.split("const DATA = ", 1)[1].split(";\n", 1)[0]
    assert data["shotLabel"] == core.EXAMPLE_LABEL
    assert not re.findall(r"""(?:src|href)\s*=\s*["']?\s*(?:https?:)?//""", html)


def test_board_carries_no_owner_contact_or_email(tmp_path: Path) -> None:
    """예시판 · 사내판은 그림 밖으로 담당 조직 · 문의처를 싣지 않는다(그림은 촬영기가 가린다)."""
    _fake_shots(tmp_path, SKELETON.state_ids(), mode="example")
    _run_facts(tmp_path, mode="example", db="example")
    shots, _run = core.board_shots(SKELETON, tmp_path)
    data, _report = core.assemble(SKELETON.content, shots)
    html = core.render_html((core.HOWTO_DIR / "template.html").read_text(encoding="utf-8"), data)
    text = re.sub(r"data:image/webp;base64,[A-Za-z0-9+/=]+", "", html)

    assert settings.APP_OWNER_TEAM not in text
    assert settings.APP_CONTACT_EMAIL not in text
    assert not re.findall(r"[\w.+-]+@[\w-]+\.[A-Za-z]{2,}", text)


def test_render_refuses_a_template_without_one_data_slot() -> None:
    with pytest.raises(core.GuideInputError):
        core.render_html("<script>const DATA = 1;</script>", {})


# ------------------------------------------------------------------ 덮어쓰기


def _overrides(**parts: Any) -> dict[str, Any]:
    return {"skeleton": SKELETON.version, **parts}


def test_overrides_apply_text_then_add_then_hide_by_script_numbers() -> None:
    step = SKELETON.content["tasks"][6]["steps"][2]  # change_plan.apply
    assert step["id"] == "apply" and len(step["stuck"]) >= 2
    document = _overrides(
        text={
            "change_plan.apply.stuck.0": "사내 첫 줄",
            "change_plan.apply.do": "사내 문장",
            "lob_map.spot.lob_wafer_capa.what": "사내 설명",
            "concept.read_state.title": "사내 제목",
        },
        add={"change_plan.apply.stuck": ["덧붙인 줄"]},
        hide=["change_plan.apply.stuck.1"],
    )

    content, report = core.apply_overrides(SKELETON.content, document, version=SKELETON.version)
    changed = content["tasks"][6]["steps"][2]

    assert changed["do"] == "사내 문장"
    assert changed["stuck"] == ["사내 첫 줄", *step["stuck"][2:], "덧붙인 줄"]
    assert content["tasks"][0]["map"]["spots"][2]["what"] == "사내 설명"
    assert content["concepts"][1]["title"] == "사내 제목"
    assert report.applied == 6 and report.orphans == [] and report.version_matches
    # 원고는 그대로다
    assert SKELETON.content["tasks"][6]["steps"][2]["do"] == step["do"]


def test_override_addresses_not_in_the_script_are_counted_as_orphans() -> None:
    document = _overrides(
        text={
            "change_avail.apply.stuck.0": "원고에 「막히면」이 없는 단계",
            "lob_map.end": "지도 과업에는 끝 문장이 없다",
            "nothing.here.do": "없는 과업",
        },
        add={"gone.step.stuck": ["없는 단계"]},
        hide=["change_plan.apply.stuck.9"],
    )

    _content, report = core.apply_overrides(SKELETON.content, document, version=SKELETON.version)

    assert sorted(report.orphans) == sorted(
        [
            "change_avail.apply.stuck.0",
            "lob_map.end",
            "nothing.here.do",
            "gone.step.stuck",
            "change_plan.apply.stuck.9",
        ]
    )
    assert report.applied == 0


@pytest.mark.parametrize(
    "document",
    [
        _overrides(text={"change_avail.apply.do": "<b>굵게</b>"}),
        _overrides(text={"change_avail.apply.ok": "javascript:alert(1)"}),
        _overrides(text={"change_avail.apply.state": "09_ref_edited"}),
        _overrides(text={"change_avail.apply.focus.0.t": "ref_cancel"}),
        _overrides(add={"change_avail.apply.do": ["덧붙임"]}),
        _overrides(hide=["change_avail.apply"]),
        _overrides(steps=[]),
    ],
)
def test_forbidden_fields_markup_and_scripts_refuse_assembly(document: dict[str, Any]) -> None:
    with pytest.raises(core.GuideInputError) as caught:
        core.apply_overrides(SKELETON.content, document, version=SKELETON.version)

    assert caught.value.what.startswith("조립 거절")


def test_an_older_skeleton_version_is_reported_not_refused() -> None:
    document = {"skeleton": "lob@2026-10-15", "text": {"change_avail.apply.do": "사내 문장"}}

    _content, report = core.apply_overrides(SKELETON.content, document, version=SKELETON.version)
    line = core.review_line(SKELETON, None, None, report)

    assert report.applied == 1 and not report.version_matches
    assert line.startswith("가이드 lob@1023 판 다름(덮어쓰기 lob@1015) ")


# ------------------------------------------------------------------ 매개값


def test_params_take_declared_names_with_their_types() -> None:
    document = {
        "skeleton": SKELETON.version,
        "values": {"edit_process": "Mold", "edit_delta": 3, "edit_month": "202701"},
    }

    values, report = core.resolve_params(SKELETON.plan, document)
    ops = core.bind_params(SKELETON.state("09_ref_edited")["ops"], values)

    assert values["edit_process"] == "Mold" and values["edit_delta"] == 3
    assert values["revision_name"] == SKELETON.plan["params"]["revision_name"]["default"]
    assert report.given == 3
    assert ops[0]["row"] == "Mold" and ops[0]["column"] == "202701" and ops[0]["delta"] == 3


@pytest.mark.parametrize(
    "values",
    [
        {"edit_delta": "2"},
        {"edit_process": 3},
        {"unknown_name": "x"},
        {"edit_delta": True},
        {"edit_process": "<b>"},
        {"edit_process": ["a"]},
    ],
)
def test_params_with_wrong_names_or_types_refuse_assembly(values: dict[str, Any]) -> None:
    with pytest.raises(core.GuideInputError) as caught:
        core.resolve_params(SKELETON.plan, {"skeleton": SKELETON.version, "values": values})

    assert caught.value.what.startswith("조립 거절")


def test_choice_params_accept_only_their_choices() -> None:
    plan = json.loads(json.dumps(SKELETON.plan))
    plan["params"]["pick"] = {"type": "choice", "default": "a", "choices": ["a", "b"], "about": "x"}

    values, _ = core.resolve_params(plan, {"skeleton": plan["version"], "values": {"pick": "b"}})
    assert values["pick"] == "b"
    with pytest.raises(core.GuideInputError):
        core.resolve_params(plan, {"skeleton": plan["version"], "values": {"pick": "c"}})


# ------------------------------------------------------------------ 경로 · 포트 · 사본


def _namespace(tmp_path: Path, **values: Any) -> argparse.Namespace:
    base: dict[str, Any] = {
        "work": tmp_path / "work",
        "dist": tmp_path / "dist",
        "output": tmp_path / "guide.md",
        "playwright_dir": tmp_path / "pw",
    }
    base.update(values)
    return argparse.Namespace(**base)


def test_output_folders_inside_the_repository_are_refused(tmp_path: Path) -> None:
    assert builder.refused_paths(_namespace(tmp_path), []) == []
    for flag, name in (("--work", "work"), ("--dist", "dist"), ("--output", "output")):
        inside = _namespace(tmp_path, **{name: PROJECT_ROOT / "static" / "guides" / "x"})
        assert builder.refused_paths(inside, []) == [flag]


def test_output_folders_inside_the_copy_or_any_git_tree_are_refused(tmp_path: Path) -> None:
    copy_root = tmp_path / "copy"
    copy_root.mkdir()
    in_copy = _namespace(tmp_path, dist=copy_root / "out")
    assert builder.refused_paths(in_copy, [copy_root]) == ["--dist"]

    other = tmp_path / "other_repo"
    (other / ".git").mkdir(parents=True)
    in_git = _namespace(tmp_path, work=other / "work")
    assert builder.refused_paths(in_git, []) == ["--work"]


def _copy_tree(root: Path) -> Path:
    (root / "src" / "capa_simulation").mkdir(parents=True)
    (root / "app.py").write_text("", encoding="utf-8")
    (root / "data").mkdir()
    for name in builder.DATABASE_NAMES:
        (root / "data" / name).write_bytes(b"duck")
    return root


def test_copy_root_must_be_an_archived_tree_with_both_databases(tmp_path: Path) -> None:
    good = _copy_tree(tmp_path / "e2e")
    assert builder.copy_root_problems(good) == []

    in_git = tmp_path / "repo"
    (in_git / ".git").mkdir(parents=True)
    nested = _copy_tree(in_git / "copy")
    assert any(".git" in problem for problem in builder.copy_root_problems(nested))

    with_git = _copy_tree(tmp_path / "with_git")
    (with_git / ".git").write_text("gitdir: x", encoding="utf-8")
    assert any(".git" in problem for problem in builder.copy_root_problems(with_git))

    inside_repo = PROJECT_ROOT / "data"
    assert builder.copy_root_problems(inside_repo)

    (good / "data" / builder.DATABASE_NAMES[1]).unlink()
    (good / "data" / f"{builder.DATABASE_NAMES[0]}.wal").write_bytes(b"w")
    problems = builder.copy_root_problems(good)
    assert any("없습니다" in problem for problem in problems)
    assert any(".wal" in problem for problem in problems)

    assert builder.copy_root_problems(tmp_path / "missing") == ["사본 폴더가 없습니다"]


@pytest.mark.parametrize("port", [8501, 8551])
def test_reserved_ports_are_refused(tmp_path: Path, port: int) -> None:
    args = builder.parse_args(
        ["--example", "--work", str(tmp_path / "w"), "--dist", str(tmp_path / "d")]
        + ["--playwright-dir", str(tmp_path / "pw"), "--port", str(port)]
    )
    assert any(str(port) in problem for problem in builder.mode_problems(args))
    assert builder.choose_port(port, lambda _port: False) is None


def test_port_search_starts_at_8552_and_skips_busy_ones() -> None:
    busy = {8552, 8553}
    assert builder.choose_port(None, lambda port: port in busy) == 8554
    assert builder.choose_port(8560, lambda port: port in busy) == 8560
    assert builder.choose_port(8552, lambda port: port in busy) is None


@pytest.mark.parametrize(
    ("extra", "needle"),
    [
        (["--internal"], "--copy-root"),
        (["--example", "--copy-root", "x"], "--copy-root"),
        (["--example", "--overrides", "o.json"], "덮어쓰기"),
        (["--example", "--allow-writes"], "--allow-writes"),
    ],
)
def test_mode_combinations_are_checked(tmp_path: Path, extra: list[str], needle: str) -> None:
    args = builder.parse_args(
        [*extra, "--work", str(tmp_path / "w"), "--dist", str(tmp_path / "d")]
        + ["--playwright-dir", str(tmp_path / "pw")]
    )
    assert any(needle in problem for problem in builder.mode_problems(args))


def test_cli_refuses_a_work_folder_inside_the_repository_before_anything_runs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = builder.main(
        ["--example", "--work", str(PROJECT_ROOT / "data" / "temp" / "guide")]
        + ["--dist", str(tmp_path / "d"), "--playwright-dir", str(tmp_path / "pw")]
    )

    assert code == builder.EXIT_NOT_READY
    assert "--work" in capsys.readouterr().out
    assert not (PROJECT_ROOT / "data" / "temp" / "guide").exists()


# ------------------------------------------------------------------ DB 지문


def test_db_fingerprint_sees_any_change_or_new_wal(tmp_path: Path) -> None:
    data = _copy_tree(tmp_path / "e2e") / "data"
    before = builder.db_fingerprint(data)

    assert builder.db_verdict(before, builder.db_fingerprint(data)) == "same"
    (data / builder.DATABASE_NAMES[0]).write_bytes(b"duck!")
    assert builder.db_verdict(before, builder.db_fingerprint(data)) == "changed"
    (data / builder.DATABASE_NAMES[0]).write_bytes(b"duck")
    (data / f"{builder.DATABASE_NAMES[1]}.wal").write_bytes(b"")
    assert builder.db_verdict(before, builder.db_fingerprint(data)) == "changed"


# ------------------------------------------------------------------ 쓰기 등급 · 촬영 차례


class FakeCamera:
    """`run_states` 가 부르는 차례를 적는 가짜 촬영기."""

    def __init__(self, folder: Path, fail: Sequence[str] = ()) -> None:
        self.folder = folder
        self.fail = set(fail)
        self.where = ""
        self.calls: list[str] = []

    def open_session(self) -> None:
        self.calls.append("session")

    def run_ops(self, state_id: str, ops: Sequence[Mapping[str, Any]]) -> None:
        self.where = f"{state_id}.ops.0 {ops[0]['op']}"
        self.calls.append(f"ops:{state_id}")
        if state_id in self.fail:
            raise capture.CaptureError("가짜 실패")

    def capture(self, state: Mapping[str, Any], folder: Path) -> core.ShotState:
        self.calls.append(f"shot:{state['id']}")
        return core.ShotState(id=str(state["id"]), image=None, targets={})


def _run(
    camera: FakeCamera,
    *,
    skip: Sequence[str] = (),
    wanted: Sequence[str] | None = None,
    deadline: float = 1e12,
) -> list[capture.StateOutcome]:
    outcomes: list[capture.StateOutcome] = []
    capture.run_states(
        camera,
        SKELETON,
        core.resolve_params(SKELETON.plan, None)[0],
        wanted=list(wanted or SKELETON.state_ids()),
        skip=list(skip),
        deadline=deadline,
        folder=camera.folder,
        on_state=lambda outcome, _shot: outcomes.append(outcome),
    )
    return outcomes


def test_internal_first_pass_skips_states_whose_chain_writes(tmp_path: Path) -> None:
    skip = [sid for sid in SKELETON.state_ids() if not SKELETON.read_only(sid)]
    camera = FakeCamera(tmp_path)

    outcomes = _run(camera, skip=skip)

    assert sorted(skip) == ["14_scenario_saved", "18_official_done", "20_home_pref_compare"]
    assert [o.state_id for o in outcomes if o.result == "captured"] == SKELETON.read_only_ids()
    assert len(SKELETON.read_only_ids()) == INTERNAL_FIRST_PASS
    assert {o.state_id for o in outcomes if o.result == "skipped"} == set(skip)
    # 건너뛴 상태의 동작은 한 번도 돌지 않는다(사본 DB 에 쓰지 않는다)
    assert not [call for call in camera.calls if any(sid in call for sid in skip)]


def test_a_new_session_replays_the_chain_when_the_previous_state_is_not_the_parent(
    tmp_path: Path,
) -> None:
    camera = FakeCamera(tmp_path)
    _run(camera)

    # 첫 세션 + 04 · 05 · 06 · 07 · 08 · 15 · 19 앞(19 는 팝업이 뜬 17 이 아니라 16 에서 잇는다)
    assert camera.calls.count("session") == 8
    first_08 = camera.calls.index("shot:08_ref_avail")
    session = max(i for i, call in enumerate(camera.calls[:first_08]) if call == "session")
    assert camera.calls[session + 1 : first_08] == [
        "ops:01_home_main",
        "ops:07_sidebar_static_open",
        "ops:08_ref_avail",
    ]


def test_a_failed_state_is_recorded_by_kind_and_the_next_one_reopens(tmp_path: Path) -> None:
    camera = FakeCamera(tmp_path, fail=["02_home_lower"])
    outcomes = {o.state_id: o for o in _run(camera)}

    assert outcomes["02_home_lower"].result == "failed"
    assert outcomes["02_home_lower"].failure == "02_home_lower.ops.0 scroll CaptureError"
    assert outcomes["03_process_detail"].result == "failed"  # 사슬에 02 가 있어 다시 실패
    assert outcomes["04_procfilter_open"].result == "captured"


def test_states_past_the_budget_are_left_for_a_later_run(tmp_path: Path) -> None:
    outcomes = _run(FakeCamera(tmp_path), deadline=0)

    assert {o.result for o in outcomes} == {"left"}


# ------------------------------------------------------------------ 리뷰 한 줄 · 사내판


def _internal_work(
    tmp_path: Path, *, missing: Mapping[str, Sequence[str]] | None = None, db: str = "same"
) -> Path:
    work = tmp_path / "work"
    _fake_shots(work, SKELETON.read_only_ids(), mode="internal", missing=missing)
    skipped = [sid for sid in SKELETON.state_ids() if not SKELETON.read_only(sid)]
    _run_facts(work, mode="internal", db=db, skipped=skipped)
    return work


@pytest.fixture
def example_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """합성 예시 그림을 임시 폴더에 내보내고 뼈대의 예시 자리 대신 읽게 한다."""
    folder = tmp_path / "skeleton"
    source = tmp_path / "example_run"
    shots = _fake_shots(source, SKELETON.state_ids(), mode="example", scale=1.0)
    substitute = [sid for sid in SKELETON.state_ids() if not SKELETON.read_only(sid)]
    exported = core.export_examples(shots, substitute, folder / core.EXAMPLE_DIR)
    assert exported == substitute
    examples = core.load_shots(folder / core.EXAMPLE_DIR)
    monkeypatch.setattr(core, "load_examples", lambda _skeleton: examples)
    return folder


def test_review_line_for_a_clean_internal_first_pass(tmp_path: Path, example_dir: Path) -> None:
    work = _internal_work(tmp_path)
    content, overrides = core.apply_overrides(
        SKELETON.content,
        _overrides(text={"change_avail.apply.do": "사내 문장"}),
        version=SKELETON.version,
    )

    line, details = core.review_for_work(SKELETON, content, work, overrides, None)
    total = sum(len(SKELETON.target_names(sid)) for sid in SKELETON.read_only_ids())

    assert line == (
        f"가이드 lob@1023 상태 18/18; 표적 {total}/{total} ok; 고아 0; 덮어씀 1; 예시 4; "
        "DB 변화 없음"
    )
    assert sorted(d for d in details if d.startswith("예시")) == [
        "예시 step:gap.pick_compare",
        "예시 step:save_revision.badge",
        "예시 step:set_official.check",
        "예시 thumb:gap",
    ]


def test_review_line_lists_missing_targets_and_db_change(tmp_path: Path, example_dir: Path) -> None:
    missing = {"09_ref_edited": ["ref_cancel"], "02_home_lower": ["bn_cell", "detail_bn"]}
    work = _internal_work(tmp_path, missing=missing, db="changed")
    shots = core.load_shots(work)
    shots.states["06_home_pref"] = core.ShotState(
        id="06_home_pref", image=None, targets={}, failed="06_home_pref.ops.0 tab CaptureError"
    )
    core.save_shots(shots, work)

    line, _details = core.review_for_work(
        SKELETON, SKELETON.content, work, core.OverrideReport(), None
    )

    assert "상태 17/18;" in line
    assert "ng detail_bn@02_home_lower, bn_cell@02_home_lower, *@06_home_pref 외 1;" in line
    assert line.endswith("예시 4; DB 변화 있음")


def test_internal_board_labels_its_own_pictures_with_the_date(
    tmp_path: Path, example_dir: Path
) -> None:
    work = _internal_work(tmp_path)
    shots, _run = core.board_shots(SKELETON, work)
    data, report = core.assemble(SKELETON.content, shots)
    steps = {(t["id"], s["id"]): s for t in data["tasks"] for s in t.get("steps", [])}

    assert data["shotLabel"] == f"사내 화면 · {DATE}"
    assert steps[("change_avail", "apply")]["crop"]["cap"] == f"사내 화면 · {DATE}"
    assert steps[("save_revision", "badge")]["crop"]["cap"] == core.EXAMPLE_LABEL
    assert report.example_spots == {
        "step:save_revision.badge",
        "step:set_official.check",
        "step:gap.pick_compare",
        "thumb:gap",
    }
    assert report.no_picture == []


def test_work_folder_from_another_skeleton_version_is_refused(tmp_path: Path) -> None:
    work = _internal_work(tmp_path)
    meta = json.loads((work / core.SHOTS_FILE).read_text(encoding="utf-8"))
    meta["version"] = "lob@2026-10-01"
    (work / core.SHOTS_FILE).write_text(json.dumps(meta), encoding="utf-8")

    with pytest.raises(core.GuideInputError):
        core.board_shots(SKELETON, work)


def test_merging_a_later_run_keeps_earlier_states_and_any_db_change() -> None:
    first = core.ShotSet(mode="internal", version=SKELETON.version)
    first.states["01_home_main"] = core.ShotState("01_home_main", None, {})
    later = core.ShotSet(mode="internal", version=SKELETON.version)
    later.states["02_home_lower"] = core.ShotState("02_home_lower", None, {})

    merged = core.merge_shots(first, later)
    facts = core.merge_runs(
        core.RunFacts(mode="internal", db="changed"), core.RunFacts(mode="internal", db="same")
    )

    assert set(merged.states) == {"01_home_main", "02_home_lower"}
    assert facts.db == "changed"
    with pytest.raises(core.GuideInputError):
        core.merge_shots(first, core.ShotSet(mode="example", version=SKELETON.version))


@pytest.mark.parametrize(("db", "code"), [("same", 0), ("changed", 2)])
def test_assemble_only_writes_the_board_outside_and_stops_on_a_db_change(
    tmp_path: Path, example_dir: Path, capsys: pytest.CaptureFixture[str], db: str, code: int
) -> None:
    work = _internal_work(tmp_path, db=db)
    copy_root = _copy_tree(tmp_path / "e2e")
    dist = tmp_path / "out"
    output = tmp_path / "guide.md"

    result = builder.main(
        ["--internal", "--copy-root", str(copy_root), "--assemble-only", "--work", str(work)]
        + ["--dist", str(dist), "--output", str(output)]
    )
    out = capsys.readouterr().out

    assert result == code
    assert (dist / "lob.html").stat().st_size > 10_000
    assert "가이드 lob@1023 상태 18/18;" in out
    block = output.read_text(encoding="utf-8")
    assert ("끝 — 조립만" in block) == (db == "same")
    assert ("DB 변화 있음" in block) == (db == "changed")


def test_assemble_only_without_earlier_shots_stops(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    copy_root = _copy_tree(tmp_path / "e2e")

    result = builder.main(
        ["--internal", "--copy-root", str(copy_root), "--assemble-only"]
        + ["--work", str(tmp_path / "work"), "--dist", str(tmp_path / "out")]
    )

    assert result == builder.EXIT_NOT_READY
    assert "shots.json" in capsys.readouterr().out


# ------------------------------------------------------------------ 촬영 길(가짜 앱 · 촬영기)


WRITING_STATES = ["14_scenario_saved", "18_official_done", "20_home_pref_compare"]


@dataclass
class Rig:
    """생성기의 촬영 길을 끝까지 돌리는 판 — 앱 · 브라우저 · 촬영기만 가짜다.

    `write_db` 상태의 동작을 돌 때 사본 DB 에 한 바이트를 쓰고, `app_problem` 상태에서 앱 오류
    화면을 낸다. `skips` 는 `run_states` 가 받은 건너뛸 목록, `apps` 는 띄운 앱 수를 적는다.
    """

    root: Path
    copy_root: Path
    write_db: str | None = None
    app_problem: str | None = None
    apps: int = 0
    app_roots: list[Path] = field(default_factory=list)
    skips: list[list[str]] = field(default_factory=list)
    cameras: list[RigCamera] = field(default_factory=list)

    @property
    def work(self) -> Path:
        return self.root / "work"

    @property
    def output(self) -> Path:
        return self.root / "guide.md"

    def main(self, *extra: str) -> int:
        return self.run("--internal", "--copy-root", str(self.copy_root), *extra)

    def run(self, *mode: str) -> int:
        return builder.main(
            [*mode, "--work", str(self.work), "--dist", str(self.root / "out")]
            + ["--output", str(self.output), "--playwright-dir", str(self.root / "pw")]
        )

    def ops(self) -> list[str]:
        return [call for camera in self.cameras for call in camera.calls if call.startswith("ops:")]


class RigCamera:
    """`capture.Camera` 자리 — 동작 차례를 적고, 찍기는 작은 그림과 계획의 표적 좌표를 남긴다."""

    def __init__(self, rig: Rig, scale: float) -> None:
        self.rig = rig
        self.scale = scale
        self.where = ""
        self.calls: list[str] = []

    def open_session(self) -> None:
        self.calls.append("session")

    def run_ops(self, state_id: str, ops: Sequence[Mapping[str, Any]]) -> None:
        self.where = f"{state_id}.ops.0 {ops[0]['op']}"
        self.calls.append(f"ops:{state_id}")
        if state_id == self.rig.write_db:
            with (self.rig.copy_root / "data" / builder.DATABASE_NAMES[0]).open("ab") as stream:
                stream.write(b"!")
        if state_id == self.rig.app_problem:
            raise capture.AppProblem("가짜 앱 오류 화면")

    def capture(self, state: Mapping[str, Any], folder: Path) -> core.ShotState:
        state_id = str(state["id"])
        folder.mkdir(parents=True, exist_ok=True)
        image = folder / f"{state_id}.png"
        Image.new("RGB", (64, 40), (200, 210, 220)).save(image)
        targets = {str(name): _rect_for(i) for i, name in enumerate(state["targets"])}
        return core.ShotState(state_id, image, targets, date=DATE, scale=self.scale)

    def close(self) -> None:
        self.calls.append("close")


@pytest.fixture
def rig(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, example_dir: Path) -> Rig:
    built = Rig(root=tmp_path, copy_root=_copy_tree(tmp_path / "e2e"))

    class FakeApp:
        def __init__(self, port: int, *, root: Path, **_options: Any) -> None:
            built.app_roots.append(root)
            built.apps += 1
            self.base_url = f"http://127.0.0.1:{port}/"
            self.started_seconds = 0.1

        def __enter__(self) -> FakeApp:
            return self

        def __exit__(self, *_exc: object) -> None:
            return None

    @contextmanager
    def fake_browser(_sync_api: Any, _channel: str, _no_sandbox: bool) -> Iterator[object]:
        yield object()

    def fake_camera(_browser: Any, _base_url: str, *, scale: float, **_options: Any) -> RigCamera:
        camera = RigCamera(built, scale)
        built.cameras.append(camera)
        return camera

    real_run_states = capture.run_states

    def spy_run_states(
        camera: capture.Shooter,
        skeleton: core.Skeleton,
        params: Mapping[str, str | int],
        **options: Any,
    ) -> None:
        built.skips.append(list(options["skip"]))
        real_run_states(camera, skeleton, params, **options)

    monkeypatch.setattr(screens, "load_playwright", lambda _folder: object())
    monkeypatch.setattr(screens, "locked_databases", lambda _paths: [])
    monkeypatch.setattr(screens, "StreamlitApp", FakeApp)
    monkeypatch.setattr(builder, "choose_port", lambda _requested: 8545)
    monkeypatch.setattr(builder, "open_browser", fake_browser)
    monkeypatch.setattr(capture, "Camera", fake_camera)
    monkeypatch.setattr(capture, "run_states", spy_run_states)
    return built


def _last_line(capsys: pytest.CaptureFixture[str]) -> tuple[str, str]:
    out = capsys.readouterr().out
    return out, out.strip().splitlines()[-1]


def test_internal_run_skips_writing_states_and_finds_the_copy_unchanged(
    rig: Rig, capsys: pytest.CaptureFixture[str]
) -> None:
    code = rig.main()
    _out, line = _last_line(capsys)

    assert code == builder.EXIT_OK
    assert [sorted(skip) for skip in rig.skips] == [WRITING_STATES]
    # 건너뛴 상태의 동작은 사슬 재생으로도 한 번도 돌지 않는다
    assert rig.ops() and not [call for call in rig.ops() if call[4:] in WRITING_STATES]
    assert core.load_run(rig.work).db == "same"
    assert core.load_run(rig.work).skipped == sorted(WRITING_STATES)
    assert f"상태 {INTERNAL_FIRST_PASS}/{INTERNAL_FIRST_PASS};" in line
    assert line.endswith("DB 변화 없음")
    assert rig.app_roots == [rig.copy_root]
    assert (rig.work / builder.BASELINE_FILE).exists()
    assert "끝" in rig.output.read_text(encoding="utf-8")


def test_a_copy_database_changed_by_the_run_stops_with_2(
    rig: Rig, capsys: pytest.CaptureFixture[str]
) -> None:
    rig.write_db = "01_home_main"

    code = rig.main()
    out, _line = _last_line(capsys)

    assert code == builder.EXIT_NOT_READY
    assert builder.DB_CHANGED_MESSAGE in out
    assert core.load_run(rig.work).db == "changed"
    block = rig.output.read_text(encoding="utf-8")
    assert "DB 변화 있음" in block and "멈춤 — DB 변화 있음" in block


def test_allow_writes_shoots_every_state_and_marks_the_run_as_writes(
    rig: Rig, capsys: pytest.CaptureFixture[str]
) -> None:
    rig.write_db = "14_scenario_saved"

    code = rig.main("--allow-writes")
    _out, line = _last_line(capsys)

    assert code == builder.EXIT_OK
    assert rig.skips == [[]]
    assert {f"ops:{sid}" for sid in WRITING_STATES} <= set(rig.ops())
    assert core.load_run(rig.work).db == "writes"
    assert f"상태 {len(SKELETON.state_ids())}/{len(SKELETON.state_ids())};" in line
    assert line.endswith(core.DB_WORDS["writes"])


@pytest.mark.parametrize("again", [[], ["--states", "02_home_lower"]])
def test_a_rerun_on_a_changed_copy_stops_before_the_app_instead_of_taking_a_new_baseline(
    rig: Rig, capsys: pytest.CaptureFixture[str], again: list[str]
) -> None:
    rig.write_db = "01_home_main"
    assert rig.main() == builder.EXIT_NOT_READY
    rig.write_db = None
    capsys.readouterr()

    code = rig.main(*again)
    out = capsys.readouterr().out

    assert code == builder.EXIT_NOT_READY
    assert "기준 지문" in out and "새 --work" in out
    assert rig.apps == 1 and len(rig.cameras) == 1  # 다시 띄우지도 찍지도 않는다
    assert core.load_run(rig.work).db == "changed"
    assert "DB 변화 없음" not in out


def test_an_app_error_after_a_write_records_the_change_and_blocks_the_rerun(
    rig: Rig, capsys: pytest.CaptureFixture[str]
) -> None:
    rig.write_db = "01_home_main"
    rig.app_problem = "02_home_lower"

    assert rig.main() == builder.EXIT_NOT_READY
    out = capsys.readouterr().out
    assert "앱이 오류 화면입니다" in out and builder.DB_CHANGED_MESSAGE in out
    assert core.load_run(rig.work).db == "changed"

    rig.write_db = rig.app_problem = None
    assert rig.main() == builder.EXIT_NOT_READY
    assert "기준 지문" in capsys.readouterr().out
    assert rig.apps == 1
    # 그 --work 를 조립만 해도 「DB 안 봄」이 아니라 변화가 남는다
    assert rig.main("--assemble-only") == builder.EXIT_NOT_READY
    assert capsys.readouterr().out.strip().splitlines()[-1] == builder.DB_CHANGED_MESSAGE


def test_a_clean_rerun_with_states_compares_with_the_first_baseline_and_goes_on(
    rig: Rig, capsys: pytest.CaptureFixture[str]
) -> None:
    assert rig.main() == builder.EXIT_OK
    baseline = (rig.work / builder.BASELINE_FILE).read_bytes()
    capsys.readouterr()

    code = rig.main("--states", "02_home_lower")
    _out, line = _last_line(capsys)

    assert code == builder.EXIT_OK
    assert rig.apps == 2
    assert (rig.work / builder.BASELINE_FILE).read_bytes() == baseline
    assert line.endswith("DB 변화 없음")


def test_example_run_shoots_every_state_on_its_own_copy_without_a_baseline(
    rig: Rig, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(builder, "uncommitted_app_changes", lambda: 0)
    monkeypatch.setattr(builder, "make_example_copy", lambda work: _copy_tree(work / "app-x"))
    monkeypatch.setattr(builder, "seed_example", lambda _copy: None)

    code = rig.run("--example")
    _out, line = _last_line(capsys)

    assert code == builder.EXIT_OK
    assert rig.skips == [[]]
    assert rig.app_roots == [rig.work / "app-x"]
    assert not (rig.work / "app-x").exists()  # 쓴 앱 사본은 지운다
    assert not (rig.work / builder.BASELINE_FILE).exists()
    assert core.load_run(rig.work).db == "example"
    assert line.endswith(core.DB_WORDS["example"])
    assert (rig.root / "out" / core.EXAMPLE_DIR / core.SHOTS_FILE).exists()


# ------------------------------------------------------------------ 점검기 CLI


def test_checker_prints_the_review_line_for_a_work_folder(
    tmp_path: Path, example_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    work = _internal_work(tmp_path)
    overrides = tmp_path / "overrides.json"
    overrides.write_text(
        json.dumps(_overrides(text={"lob_map.end": "고아", "change_avail.apply.do": "사내"})),
        encoding="utf-8",
    )

    code = checker.main(["--work", str(work), "--overrides", str(overrides)])
    out = capsys.readouterr()

    assert code == checker.EXIT_OK
    assert out.out.strip().endswith("고아 1; 덮어씀 1; 예시 4; DB 변화 없음")
    assert "고아 lob_map.end" in out.err
    assert "사내" not in out.err  # 사내 글 값은 찍지 않는다


def test_checker_refuses_markup_in_overrides_and_bad_param_types(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    overrides = tmp_path / "overrides.json"
    overrides.write_text(
        json.dumps(_overrides(text={"change_avail.apply.do": "<img src=x onerror=alert(1)>"})),
        encoding="utf-8",
    )
    params = tmp_path / "params.json"
    params.write_text(
        json.dumps({"skeleton": SKELETON.version, "values": {"edit_delta": "2"}}), encoding="utf-8"
    )

    assert checker.main(["--overrides", str(overrides)]) == checker.EXIT_NOT_READY
    assert "onerror" not in capsys.readouterr().err
    assert checker.main(["--params", str(params)]) == checker.EXIT_NOT_READY
    assert checker.main([]) == checker.EXIT_OK
    assert capsys.readouterr().out.strip().endswith("가이드 lob@1023 고아 0; 덮어씀 0")


# ------------------------------------------------------------------ 낱말 · 가림


def test_generator_vocabulary_matches_the_plan_schema() -> None:
    schema = core.load_json(core.HOWTO_DIR / "schema" / "plan.schema.json")
    schema_ops = {
        variant["properties"]["op"]["const"] for variant in schema["$defs"]["op"]["oneOf"]
    }
    camera = capture.Camera(None, "", viewport=VIEWPORT, scale=2, mask=[], needles=[])

    assert schema_ops == core.OPS
    assert capture.IMPLEMENTED_NAMED == frozenset(core.NAMED_TARGETS)
    for op in core.OPS:
        assert callable(getattr(camera, f"_{op}"))


def test_every_plan_target_word_compiles_to_a_page_expression() -> None:
    helpers = capture.HELPERS_JS
    edit = capture.LastEdit("named:GRID", 1, 2)
    for state in SKELETON.states:
        for word in [*state["targets"].values(), *SKELETON.plan["mask"]]:
            expression = capture.target_expr(word, edit)
            for name in re.findall(r"__g\.(\w+)\(", expression):
                assert f"g.{name} = " in helpers, (word, name)


def test_mask_hides_the_credit_card_and_the_settings_owner_and_contact() -> None:
    assert SKELETON.plan["mask"] == ["named:SIDEBAR_FOOTER"]
    assert capture.APP_CREDITS_KEY == app_credits.APP_CREDITS_KEY
    assert capture.APP_CREDITS_KEY in capture.target_expr("named:SIDEBAR_FOOTER", None)
    assert builder.MASK_NEEDLES == (settings.APP_OWNER_TEAM, settings.APP_CONTACT_EMAIL)


class _MaskPage:
    def __init__(self, visible: int) -> None:
        self.visible = visible
        self.scripts: list[str] = []

    def evaluate(self, script: str, arg: Any = None) -> Any:
        self.scripts.append(script)
        return self.visible if "__g.shows(" in script else 1


def test_capture_stops_when_owner_or_contact_text_stays_visible() -> None:
    camera = capture.Camera(
        None,
        "",
        viewport=VIEWPORT,
        scale=2,
        mask=["named:SIDEBAR_FOOTER"],
        needles=[settings.APP_OWNER_TEAM, settings.APP_CONTACT_EMAIL],
    )
    camera.page = _MaskPage(visible=1)
    with pytest.raises(capture.CaptureError):
        camera.mask()

    camera.page = _MaskPage(visible=0)
    camera.mask()
    assert any("__g.hideAll(" in script for script in camera.page.scripts)


def test_generator_files_are_tracked_so_the_archived_copy_carries_them() -> None:
    """생성기 셋과 도우미 JS 는 사본(`git archive`)에 실려야 사내에서 돈다."""
    names = [
        "scripts/build_page_guide.py",
        "scripts/check_page_guide.py",
        "scripts/page_guide_core.py",
        "scripts/page_guide_capture.py",
        "scripts/page_guide_helpers.js",
    ]
    listed = subprocess.run(
        ["git", "ls-files", "--error-unmatch", *names],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert listed.returncode == 0, listed.stderr


# ------------------------------------------------------------------ 바뀐 자리 검수(순수 함수)

# 실데이터가 자리 · 크기를 정한다고 코드로 확인한 넷(명세 1-3) — 측정으로 후보를 빼도 남는다.
CONFIRMED_DATA_SHAPED = {"BN_CELL", "EDIT_CELL", "EDIT_ROW", "HEADER_BAND", "SIDEBAR_BADGE"}
CONFIRMED_DATA_PLACES = {
    "concept:read_state",
    "step:bn_drill.pick_cell",
    "step:change_avail.edit_cell",
    "thumb:change_avail",
}


def test_fingerprint_is_the_sorted_compact_json_sha256_head() -> None:
    expected = hashlib.sha256('{"a":"가","b":[1,null]}'.encode()).hexdigest()[:12]

    assert core._fingerprint({"b": [1, None], "a": "가"}) == expected
    assert core.seal({"seal": "x", "b": [1, None], "a": "가"}) == expected


def test_a_move_of_up_to_the_tolerance_is_not_a_change_for_boxes_and_frames() -> None:
    def record(shift: int) -> dict[str, Any]:
        return {
            "f": [[shift, 10, 460, 250]],
            "t": {"a@s": [40 + shift, 50, 220, 40]},
            "sk": "0" * 12,
            "tx": "0" * 12,
            "pl": "0" * 12,
        }

    edge = core.MOVE_TOL_PX
    assert core._place_reasons(record(0), record(edge)) == ([], edge)
    assert core._place_reasons(record(0), record(edge + 1)) == (["상자 a@s", "틀"], edge + 1)


def test_keys_outside_the_script_or_on_data_places_are_named_before_writing() -> None:
    layout = "step:proc_filter.apply"
    record = {"f": [], "t": {"pf_apply@04_procfilter_open": None}, "sk": "", "tx": "", "pl": ""}
    document = {
        "places": {
            layout: record,
            "step:proc_filter.nowhere": record,
            "step:bn_drill.pick_cell": {**record, "t": {}},
            "step:proc_filter.open": {**record, "t": {"pf_apply@04_procfilter_open": None}},
        }
    }

    assert core.accepted_key_problems(SKELETON, document) == [
        "step:proc_filter.nowhere",
        "pf_apply@04_procfilter_open",
        "step:bn_drill.pick_cell",
        "pf_apply@04_procfilter_open",
    ]


def test_accepted_record_refuses_a_place_outside_the_script(
    tmp_path: Path, example_dir: Path
) -> None:
    shots, _run = core.board_shots(SKELETON, _internal_work(tmp_path))
    report = core.compare_accepted(SKELETON, SKELETON.content, shots, (None, "없음"))
    report.records["step:proc_filter.nowhere"] = report.records["step:proc_filter.apply"]
    report.order.append("step:proc_filter.nowhere")

    with pytest.raises(ValueError):
        core.accepted_record(SKELETON, report, shots, date=DATE)


def test_data_shaped_keeps_the_measured_names() -> None:
    """2026-11-02 사외 측정(합성 시드를 바꾼 판 둘) — 움직인 이름은 데이터 자리로 남고, 두 판
    모두에서 Δ0 이던 LOB_CHART · LOB_LABEL 만 뺐다. 목록을 줄이려면 다시 재고 이 시험을 고친다."""
    moved = {"GRID", "LAST_GRID", "DETAIL_BN", "KEY_PROCESS_GRID", "LOB_BN_BARS"}
    moved |= {"PROC_MONTH_CANVAS", "PF_TILES", "DIALOG"}

    assert core.DATA_SHAPED == CONFIRMED_DATA_SHAPED | moved
    assert {"thumb:proc_filter", "step:proc_filter.toggle"} <= core.data_places(SKELETON)
    assert "thumb:lob_map" not in core.data_places(SKELETON)


def test_the_lob_script_has_38_places_and_the_data_places_follow_data_shaped() -> None:
    places = core.place_order(SKELETON.content)
    data = core.data_places(SKELETON)

    assert len(places) == 38
    assert CONFIRMED_DATA_SHAPED <= core.DATA_SHAPED <= set(core.NAMED_TARGETS)
    assert CONFIRMED_DATA_PLACES <= data <= set(places)
    planned = {state["id"]: state["targets"] for state in SKELETON.plan["states"]}
    for where, state, target in core._target_refs(SKELETON.content):
        words = planned[state][target]
        shaped = any(
            word.startswith("named:") and word[6:].partition("(")[0] in core.DATA_SHAPED
            for word in ([words] if isinstance(words, str) else words)
        )
        assert not shaped or where in data, (where, target)


def test_the_internal_first_pass_compares_34_places(tmp_path: Path, example_dir: Path) -> None:
    shots, _run = core.board_shots(SKELETON, _internal_work(tmp_path))

    compared = core.compared_places(SKELETON.content, shots)

    assert len(compared) == 34
    assert set(core.place_order(SKELETON.content)) - set(compared) == {
        "thumb:gap",
        "step:gap.pick_compare",
        "step:save_revision.badge",
        "step:set_official.check",
    }


def test_place_geometry_holds_ids_integers_and_digests_only(
    tmp_path: Path, example_dir: Path
) -> None:
    work = _internal_work(tmp_path)
    shots = core.load_shots(work)
    shots.states["02_home_lower"].targets["bn_cell"] = [-10.4, 880.6, 30.2, 60.0]
    core.save_shots(shots, work)
    shots, _run = core.board_shots(SKELETON, work)

    records = core.place_geometry(SKELETON, SKELETON.content, shots)

    assert list(records) == core.place_order(SKELETON.content)
    # 화면 밖으로 나간 부분은 잘라 정수로
    assert records["step:bn_drill.pick_cell"]["t"]["bn_cell@02_home_lower"] == [0, 881, 20, 19]
    for record in records.values():
        assert set(record) == {"f", "t", "sk", "tx", "pl"}
        boxes = [*record["f"], *record["t"].values()]
        assert all(box is None or all(type(v) is int for v in box) for box in boxes)
        assert all(re.fullmatch(r"[0-9a-f]{12}", record[key]) for key in ("sk", "tx", "pl"))


# ------------------------------------------------------------------ 바뀐 자리 검수(점검기)

PLACES_COMPARED = 34  # 사내 1단계 — 자리 38 가운데 예시 4 를 뺀다(명세 1-4)


def _data_count() -> int:
    """k — 데이터 자리 수(`DATA_SHAPED` 로 센다). 사내 1단계에서 모두 견준다."""
    return len(core.data_places(SKELETON))


def _review_repo(root: Path) -> Path:
    """`--accept` 가 받는 가짜 저장소 뿌리 — `.git` · `app.py` · `src/capa_simulation/` ·
    `review/guide/`."""
    (root / ".git").mkdir(parents=True)
    (root / "app.py").write_text("", encoding="utf-8")
    (root / "src" / "capa_simulation").mkdir(parents=True)
    (root / "review" / "guide").mkdir(parents=True)
    return root


@dataclass
class Outcome:
    code: int
    out: str
    err: str

    @property
    def line(self) -> str:
        lines = self.out.strip().splitlines()
        return lines[-1] if lines else ""

    @property
    def changed(self) -> dict[str, str]:
        """stderr 의 `  바뀜 <자리> <까닭>` → {자리: 까닭}(「바뀜 전부」 줄은 뺀다)."""
        rows = [row.strip()[3:] for row in self.err.splitlines() if row.startswith("  바뀜 ")]
        return dict(row.partition(" ")[::2] for row in rows if not row.startswith("전부"))


@dataclass
class Desk:
    """점검기의 바뀐 자리 검수를 돌리는 판 — 사내 1단계 가짜 촬영 · 가짜 저장소 · 사내 두 파일."""

    root: Path
    work: Path
    capsys: pytest.CaptureFixture[str]

    @property
    def accepted(self) -> Path:
        return self.root / "repo" / "review" / "guide" / core.ACCEPTED_FILE

    @property
    def overrides(self) -> Path:
        return self.root / "overrides.json"

    @property
    def params(self) -> Path:
        return self.root / "params.json"

    def write_overrides(self, **parts: Any) -> None:
        text = json.dumps(_overrides(**parts), ensure_ascii=False)
        self.overrides.write_text(text, encoding="utf-8")

    def write_params(self, values: Mapping[str, Any] | None = None) -> None:
        document = {"skeleton": SKELETON.version, "values": dict(values or {})}
        self.params.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")

    def content(self) -> dict[str, Any]:
        skeleton = core.load_skeleton()
        document = core.load_json(self.overrides)
        return core.apply_overrides(skeleton.content, document, version=skeleton.version)[0]

    def write_baseline(self) -> None:
        """지금 촬영을 검수 마친 판으로 쓴다(점검기를 거치지 않는 길 — 읽는 쪽 시험용)."""
        skeleton = core.load_skeleton()
        shots, _run = core.board_shots(skeleton, self.work)
        report = core.compare_accepted(
            skeleton, self.content(), shots, core.load_accepted(self.accepted)
        )
        core.save_accepted(self.accepted, core.accepted_record(skeleton, report, shots, date=DATE))

    def baseline(self) -> dict[str, Any]:
        return dict(json.loads(self.accepted.read_text(encoding="utf-8")))

    def rewrite(self, *, reseal: bool = True, **change: Any) -> None:
        document = {**self.baseline(), **change}
        if reseal:
            document["seal"] = core.seal(document)
        self.accepted.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")

    def edit(self, key: str, **delta: float) -> None:
        """촬영 결과의 표적 하나를 옮긴다(`x` · `y` · `w` · `h` 에 더한다)."""
        name, _, state_id = key.partition("@")
        shots = core.load_shots(self.work)
        rect = shots.states[state_id].targets[name]
        for index, axis in enumerate("xywh"):
            rect[index] += delta.get(axis, 0.0)
        core.save_shots(shots, self.work)

    def check(self, *extra: str) -> Outcome:
        code = checker.main(
            ["--work", str(self.work), "--overrides", str(self.overrides)]
            + ["--params", str(self.params), "--accepted", str(self.accepted), *extra]
        )
        captured = self.capsys.readouterr()
        return Outcome(code, captured.out, captured.err)

    def stamp(self) -> None:
        """조립 도장 — 생성기가 조립 끝에 쓰는 것과 같은 값(지금 덮어쓰기 · 계획)."""
        plan = core.load_skeleton().plan
        core.save_assembly_stamp(self.work, core.assembly_stamp(self.work, self.content(), plan))

    def accept(self, *extra: str) -> Outcome:
        self.stamp()
        return self.check("--accept", *extra)


@pytest.fixture
def desk(tmp_path: Path, example_dir: Path, capsys: pytest.CaptureFixture[str]) -> Desk:
    built = Desk(tmp_path, _internal_work(tmp_path), capsys)
    _review_repo(tmp_path / "repo")
    built.write_overrides()
    built.write_params()
    return built


def test_review_line_puts_the_change_cell_between_examples_and_db(
    tmp_path: Path, example_dir: Path
) -> None:
    work = _internal_work(tmp_path)
    shots, run = core.board_shots(SKELETON, work)
    report = core.compare_accepted(SKELETON, SKELETON.content, shots, (None, "없음"))

    plain = core.review_line(SKELETON, shots, run, core.OverrideReport(), example_count=4)
    line = core.review_line(
        SKELETON, shots, run, core.OverrideReport(), example_count=4, changes=report
    )

    assert plain.endswith("예시 4; DB 변화 없음")
    assert line == plain.replace("예시 4; ", "예시 4; 바뀜 na; ")


def test_checker_without_a_baseline_file_says_na_and_exits_0(desk: Desk) -> None:
    result = desk.check()

    assert result.code == checker.EXIT_OK
    assert result.line.endswith("예시 4; 바뀜 na; DB 변화 없음")
    assert "  기준 없음 — 모든 자리" in result.err.splitlines()
    assert not desk.accepted.exists()


def test_checker_compares_with_the_accepted_board_and_lists_only_data_places(desk: Desk) -> None:
    desk.write_baseline()

    result = desk.check()
    lines = result.err.splitlines()

    assert result.code == checker.EXIT_OK
    assert f"바뀜 {_data_count()}/{PLACES_COMPARED};" in result.line
    assert set(result.changed.values()) == {"데이터 자리"}
    assert set(result.changed) == core.data_places(SKELETON)
    start = lines.index(f"  기준 lob@1023 · {DATE} · {PLACES_COMPARED - _data_count()}자리")
    assert lines[start + 1] == f"  흔들림 0:{PLACES_COMPARED - _data_count()} 1-2:0 3-9:0 10+:0"
    # 기준 줄들은 지금 목록(못 찾은 표적 → 고아 → 예시 → 남은 상태) 뒤에 온다
    assert all(not row.startswith("  예시 ") for row in lines[start:])
    assert "px" not in result.err


@pytest.mark.parametrize(
    ("spoil", "reason"),
    [
        ("json", "JSONDecodeError"),
        ("empty", "JSONDecodeError"),
        ("deep", "RecursionError"),
        ("extra", "형식"),
        ("form", "형식"),
        ("seal", "봉인"),
        ("mode", "모드"),
    ],
)
def test_a_baseline_that_cannot_be_used_is_dropped_with_na_and_exit_0(
    desk: Desk, spoil: str, reason: str
) -> None:
    desk.write_baseline()
    if spoil == "json":
        desk.accepted.write_text("{not json", encoding="utf-8")
    elif spoil == "empty":
        desk.accepted.write_bytes(b"")
    elif spoil == "deep":  # 너무 깊게 겹친 JSON — 읽는 쪽이 RecursionError 로 멈추지 않는다
        desk.accepted.write_text("[" * 100_000, encoding="utf-8")
    elif spoil == "extra":
        desk.rewrite(text="화면 글")
    elif spoil == "form":
        desk.rewrite(form=2)
    elif spoil == "seal":
        places = desk.baseline()["places"]
        first = next(iter(places.values()))
        first["f"][0][0] += 1
        desk.rewrite(reseal=False, places=places)
    else:
        desk.rewrite(mode="example")

    result = desk.check()

    assert result.code == checker.EXIT_OK
    assert "; 바뀜 na; " in result.line
    assert f"  기준 버림 — {reason} — 모든 자리" in result.err.splitlines()


def test_the_change_cell_needs_both_accepted_and_work(
    desk: Desk, capsys: pytest.CaptureFixture[str]
) -> None:
    desk.write_baseline()

    code = checker.main(["--overrides", str(desk.overrides), "--accepted", str(desk.accepted)])

    assert code == checker.EXIT_OK
    assert capsys.readouterr().out.strip().endswith("고아 0; 덮어씀 0")


def test_the_generator_stamps_each_assembly_and_keeps_its_last_line(
    rig: Rig, capsys: pytest.CaptureFixture[str]
) -> None:
    assert rig.main() == builder.EXIT_OK
    _out, shot_line = _last_line(capsys)
    stamp = rig.work / core.ASSEMBLED_FILE
    first = core.load_assembly_stamp(rig.work)
    assert first == core.assembly_stamp(rig.work, SKELETON.content, SKELETON.plan)
    block = rig.output.read_text(encoding="utf-8")
    stamp.unlink()

    code = rig.main("--assemble-only")
    out, line = _last_line(capsys)

    assert code == builder.EXIT_OK
    assert core.load_assembly_stamp(rig.work) == first
    assert line == shot_line and "바뀜" not in out  # 생성기 끝 줄에는 바뀜 칸이 없다
    assert "조립 기록" not in rig.output.read_text(encoding="utf-8")
    assert block.splitlines()[0] == rig.output.read_text(encoding="utf-8").splitlines()[0]


def test_a_stamp_that_fails_to_write_leaves_no_old_stamp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    core.save_assembly_stamp(tmp_path, {"shots": "a", "content": "b", "plan": "c"})
    assert core.load_assembly_stamp(tmp_path) is not None

    def fail(_source: Any, _target: Any) -> None:
        raise OSError("가짜")

    monkeypatch.setattr(os, "replace", fail)
    with pytest.raises(OSError):
        core.save_assembly_stamp(tmp_path, {"shots": "d", "content": "e", "plan": "f"})

    # 옛 도장이 남으면 「조립 기록 없음」 대신 옛 조립과 견주게 된다
    assert core.load_assembly_stamp(tmp_path) is None
    assert not list(tmp_path.glob("*.tmp"))


def test_a_stamp_that_cannot_be_written_is_reported_by_kind_and_the_run_goes_on(
    rig: Rig, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(_work: Path, _stamp: Mapping[str, str]) -> None:
        raise PermissionError("가짜")

    monkeypatch.setattr(core, "save_assembly_stamp", fail)

    code = rig.main()
    captured = capsys.readouterr()

    assert code == builder.EXIT_OK
    assert "조립 기록을 쓰지 못했습니다 — PermissionError" in captured.err
    assert captured.out.strip().splitlines()[-1].endswith("DB 변화 없음")
    assert "조립 기록" not in rig.output.read_text(encoding="utf-8")


# ------------------------------------------------------------------ 바뀐 자리 검수(`--accept`)

LAYOUT = "pf_apply@04_procfilter_open"  # 배치 자리 하나(step:proc_filter.apply)만 쓰는 표적
SHARED = "sidebar_scenario@10_ref_applied"  # 배치 자리 둘과 데이터 자리 하나가 함께 쓰는 표적


def _layout_places_using(states: set[str]) -> set[str]:
    """그 상태들을 사슬에 둔 상태를 쓰는 배치 자리(데이터 자리가 아니고 사내 1단계가 견주는 것)."""
    data = core.data_places(SKELETON)
    using: set[str] = set()
    for where, state in [
        *core.picture_refs(SKELETON.content),
        *[(w, s) for w, s, _t in core._target_refs(SKELETON.content)],
    ]:
        if set(SKELETON.chain(state)) & states and SKELETON.read_only(state):
            using.add(where)
    return (
        using
        - data
        - {"thumb:gap", "step:gap.pick_compare", "step:save_revision.badge"}
        - {"step:set_official.check"}
    )


def _skeleton_with(**change: Any) -> core.Skeleton:
    """원고 · 계획을 바꾼 뼈대(판은 같다) — `content` · `plan` 은 고친 사본을 받는다."""
    return dataclasses.replace(SKELETON, **change)


def test_accept_writes_the_board_then_the_same_shots_list_only_data_places(desk: Desk) -> None:
    first = desk.accept()

    assert first.code == checker.EXIT_OK
    assert "; 바뀜 na; " in first.line  # 앞 기준이 없었다
    layout = PLACES_COMPARED - _data_count()
    assert first.err.splitlines()[-1] == f"  기준 씀 — {layout}자리"
    assert core.schema_errors(desk.baseline(), "accepted") == []
    again = desk.check()
    assert f"; 바뀜 {_data_count()}/{PLACES_COMPARED}; " in again.line
    assert set(again.changed.values()) == {"데이터 자리"}


def test_a_move_within_the_tolerance_is_not_a_change_and_keeps_the_old_record(desk: Desk) -> None:
    desk.accept()
    before = desk.baseline()["places"]["step:proc_filter.apply"]
    desk.edit(LAYOUT, x=1.5)

    result = desk.check()

    assert f"; 바뀜 {_data_count()}/{PLACES_COMPARED}; " in result.line
    layout = PLACES_COMPARED - _data_count()
    assert f"  흔들림 0:{layout - 1} 1-2:1 3-9:0 10+:0" in result.err.splitlines()
    desk.accept()
    assert desk.baseline()["places"]["step:proc_filter.apply"] == before


@pytest.mark.parametrize("delta", [{"y": 20.0}, {"w": 10.0}])
def test_a_moved_or_resized_box_is_a_change_without_px(desk: Desk, delta: dict[str, float]) -> None:
    desk.accept()
    desk.edit(LAYOUT, **delta)

    result = desk.check()

    assert f"; 바뀜 {_data_count() + 1}/{PLACES_COMPARED}; " in result.line
    assert result.changed["step:proc_filter.apply"].split(" · ")[0] == f"상자 {LAYOUT}"
    assert "px" not in result.err and not re.search(r"\d+\.\d", result.err)  # 소수 좌표도 없다


def test_a_box_shared_by_places_is_compared_in_each_place(desk: Desk) -> None:
    desk.accept()
    desk.edit(SHARED, y=20.0)

    changed = desk.check().changed

    for where in ("step:change_avail.badge", "step:save_revision.open_popup"):
        assert f"상자 {SHARED}" in changed[where].split(" · ")
    assert changed["concept:read_state"] == "데이터 자리"


def test_a_lost_and_then_found_target_is_named(desk: Desk) -> None:
    key = "subtab_own@08_ref_avail"  # 배치 자리 하나(step:change_avail.tabs)만 쓰는 표적
    name, _, state_id = key.partition("@")
    shots = core.load_shots(desk.work)
    rect = shots.states[state_id].targets.pop(name)
    shots.states[state_id].missing.append(name)
    core.save_shots(shots, desk.work)
    desk.write_baseline()
    shots.states[state_id].targets[name] = rect
    shots.states[state_id].missing.remove(name)
    core.save_shots(shots, desk.work)

    found = desk.check()
    desk.write_baseline()
    shots.states[state_id].targets.pop(name)
    shots.states[state_id].missing.append(name)
    core.save_shots(shots, desk.work)
    lost = desk.check()

    assert f"찾음 {key}" in found.changed["step:change_avail.tabs"].split(" · ")
    assert f"잃음 {key}" in lost.changed["step:change_avail.tabs"].split(" · ")
    assert f"ng {key}" in lost.line
    assert {where for where, why in lost.changed.items() if "잃음" in why} == {
        "step:change_avail.tabs"
    }


def test_a_different_piece_count_is_a_frame_change_and_is_not_counted_as_wobble(
    desk: Desk,
) -> None:
    desk.accept()
    desk.edit("subtab_own@08_ref_avail", x=1100.0)  # 흩어져 SPLIT_W 를 넘는다

    result = desk.check()

    assert "틀" in result.changed["step:change_avail.tabs"].split(" · ")
    counted = sum(int(part.split(":")[1]) for part in result.err.split("흔들림 ")[1].split()[:4])
    assert counted == PLACES_COMPARED - _data_count() - 1


@pytest.mark.parametrize("cause", ["scale", "rules"])
def test_a_new_picture_size_or_assembly_rule_changes_every_place(
    desk: Desk, monkeypatch: pytest.MonkeyPatch, cause: str
) -> None:
    desk.accept()
    if cause == "scale":
        shots = core.load_shots(desk.work)
        shots.scale = 2.0
        core.save_shots(shots, desk.work)
    else:
        monkeypatch.setattr(core, "ACCEPT_RULES", core.ACCEPT_RULES + 1)

    result = desk.check()

    assert f"; 바뀜 {PLACES_COMPARED}/{PLACES_COMPARED}; " in result.line
    word = "그림 크기" if cause == "scale" else "조립 규칙"
    assert [row for row in result.err.splitlines() if row.startswith("  바뀜")] == [
        f"  바뀜 전부 {word}"
    ]
    assert "흔들림" not in result.err


def test_a_changed_script_step_is_named_only_there(
    desk: Desk, monkeypatch: pytest.MonkeyPatch
) -> None:
    desk.accept()
    content = copy.deepcopy(dict(SKELETON.content))
    task = next(task for task in content["tasks"] if task["id"] == "proc_filter")
    next(step for step in task["steps"] if step["id"] == "apply")["do"] = "판은 같고 글만 다른 원고"
    monkeypatch.setattr(core, "load_skeleton", lambda *_a, **_k: _skeleton_with(content=content))

    changed = desk.check().changed

    assert {where: why for where, why in changed.items() if why != "데이터 자리"} == {
        "step:proc_filter.apply": "원고"
    }


def test_changed_override_text_is_named_on_its_step_and_its_task_card(desk: Desk) -> None:
    desk.write_overrides(text={"criteria.find_box.do": "사내 문장 A"})
    desk.accept()
    desk.write_overrides(
        text={"criteria.find_box.do": "사내 문장 B", "criteria.title": "사내 제목 B"}
    )

    result = desk.check()

    assert {where: why for where, why in result.changed.items() if why != "데이터 자리"} == {
        "thumb:criteria": "덮어씀",
        "step:criteria.find_box": "덮어씀",
    }
    assert "사내" not in result.err


def test_changed_capture_steps_are_named_on_every_place_whose_chain_has_them(
    desk: Desk, monkeypatch: pytest.MonkeyPatch
) -> None:
    desk.accept()
    plan = copy.deepcopy(dict(SKELETON.plan))
    state = next(state for state in plan["states"] if state["id"] == "08_ref_avail")
    state["ops"].append({"op": "wait_idle", "seconds": 3})
    monkeypatch.setattr(core, "load_skeleton", lambda *_a, **_k: _skeleton_with(plan=plan))

    changed = desk.check().changed

    planned = {where for where, why in changed.items() if "계획" in why.split(" · ")}
    assert planned == _layout_places_using({"08_ref_avail"})
    assert "step:change_avail.tabs" in planned and "step:proc_filter.apply" not in planned


def test_a_baseline_from_an_older_skeleton_is_compared_by_ids(desk: Desk) -> None:
    desk.accept()
    desk.rewrite(skeleton="lob@2026-10-15")

    result = desk.check()

    assert f"; 바뀜 {_data_count()}/{PLACES_COMPARED}; " in result.line
    assert any(row.startswith("  기준 lob@1015 · ") for row in result.err.splitlines())


def test_accept_after_a_dropped_baseline_writes_a_fresh_board(desk: Desk) -> None:
    desk.accept()
    desk.accepted.write_text("{broken", encoding="utf-8")

    result = desk.accept()

    assert result.code == checker.EXIT_OK and "; 바뀜 na; " in result.line
    assert "  기준 버림 — JSONDecodeError — 모든 자리" in result.err.splitlines()
    assert core.load_accepted(desk.accepted)[0] is not None


def test_the_board_holds_no_override_text_param_value_or_screen_text(desk: Desk) -> None:
    markers = ("사내표식ZQ", "ZQ7MARK")
    desk.write_overrides(
        text={"proc_filter.apply.do": f"{markers[0]} 문장", "change_avail.title": markers[1]},
        add={"change_plan.apply.stuck": [f"{markers[1]} 줄"]},
    )
    desk.write_params({"edit_process": markers[1], "revision_name": markers[0]})

    result = desk.accept()
    raw = desk.accepted.read_bytes().decode("utf-8")

    assert result.code == checker.EXIT_OK
    for marker in markers:
        assert marker not in raw and marker not in result.out and marker not in result.err
    board = desk.baseline()
    assert core.schema_errors(board, "accepted") == []
    assert core.accepted_key_problems(SKELETON, board) == []
    assert set(board["places"]) <= set(core.place_order(SKELETON.content))


def test_data_places_leave_no_coordinates_in_the_board(desk: Desk) -> None:
    shaped = [
        "bn_cell@02_home_lower",
        "ref_edited_cell@09_ref_edited",
        "header_band@10_ref_applied",
    ]
    for key in shaped:
        desk.edit(key, x=7.3, y=11.6, w=3.2)

    result = desk.accept()
    board = desk.baseline()
    again = desk.check()

    keys = {key for place in board["places"].values() for key in place["t"]}
    assert not set(shaped) & keys
    assert not core.data_places(SKELETON) & set(board["places"])
    assert "px" not in result.err + again.err
    for where in ("step:bn_drill.pick_cell", "step:change_avail.edit_cell", "concept:read_state"):
        assert again.changed[where] == "데이터 자리"


def test_a_place_that_became_a_data_place_is_dropped_from_the_board(
    desk: Desk, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 앞 기준은 PF_TILES 가 데이터 표적이 아니던 판 — 사외가 DATA_SHAPED 에 이름을 더한 다음 회차
    with monkeypatch.context() as earlier:
        earlier.setattr(core, "DATA_SHAPED", core.DATA_SHAPED - {"PF_TILES"})
        assert desk.accept().code == checker.EXIT_OK
    grown = core.data_places(SKELETON) - {"thumb:proc_filter", "step:proc_filter.toggle"}
    assert {"thumb:proc_filter", "step:proc_filter.toggle"} <= set(desk.baseline()["places"])
    assert not grown & set(desk.baseline()["places"])

    result = desk.accept()

    assert result.code == checker.EXIT_OK
    assert result.changed["step:proc_filter.toggle"] == "데이터 자리"
    assert not core.data_places(SKELETON) & set(desk.baseline()["places"])


@pytest.mark.parametrize("field", ["skeleton", "date"])
def test_a_baseline_version_or_date_with_a_line_break_is_dropped(desk: Desk, field: str) -> None:
    # 형식 pattern 의 `$` 는 끝 줄바꿈을 받는다 — stderr 첫 줄에 찍는 두 값은 코드가 한 번 더 본다
    desk.write_baseline()
    desk.rewrite(**{field: desk.baseline()[field] + "\n"})

    result = desk.check()

    assert result.code == checker.EXIT_OK and "; 바뀜 na; " in result.line
    assert "  기준 버림 — 형식 — 모든 자리" in result.err.splitlines()


@pytest.mark.parametrize("place", ["outside", "no_git", "linked", "dotdot", "missing"])
def test_accept_refuses_a_place_that_is_not_review_guide_of_a_repository(
    desk: Desk, place: str
) -> None:
    repo = desk.root / "repo"
    target = desk.accepted
    if place == "outside":
        target = desk.root / "elsewhere" / core.ACCEPTED_FILE
        target.parent.mkdir()
    elif place == "dotdot":
        # 글자로는 review/guide/accepted.json 이지만 연결 `x` 를 따라 풀면 저장소 밖(far/)이다
        far = desk.root / "far" / "sub"
        far.mkdir(parents=True)
        (repo / "review" / "guide" / "x").symlink_to(far, target_is_directory=True)
        target = Path(f"{repo / 'review' / 'guide' / 'x'}{os.sep}..{os.sep}{core.ACCEPTED_FILE}")
    elif place == "no_git":
        (repo / ".git").rmdir()
    elif place == "linked":
        real = desk.root / "real_guide"
        real.mkdir()
        (repo / "review" / "guide").rmdir()
        (repo / "review" / "guide").symlink_to(real, target_is_directory=True)
    else:
        (repo / "review" / "guide").rmdir()
    desk.stamp()

    code = checker.main(
        ["--work", str(desk.work), "--overrides", str(desk.overrides), "--params"]
        + [str(desk.params), "--accepted", str(target), "--accept"]
    )
    out = desk.capsys.readouterr().out

    assert code == checker.EXIT_NOT_READY
    assert out.strip() == "기준을 쓰지 않았습니다 — 자리가 아님"
    assert not target.exists() and not list(desk.root.rglob(core.ACCEPTED_FILE))


@pytest.mark.parametrize("linked", ["file", "folder"])
def test_accept_refuses_a_board_linked_to_another_repository(desk: Desk, linked: str) -> None:
    # 이름 셋(review · guide · accepted.json)과 뿌리 검사는 맞는 다른 저장소 — 연결 검사만 막는다
    other = _review_repo(desk.root / "other") / "review" / "guide" / core.ACCEPTED_FILE
    if linked == "file":
        desk.accepted.symlink_to(other)
    else:
        desk.accepted.parent.rmdir()
        desk.accepted.parent.symlink_to(other.parent, target_is_directory=True)

    result = desk.accept()

    assert result.code == checker.EXIT_NOT_READY
    assert result.out.strip() == "기준을 쓰지 않았습니다 — 자리가 아님"
    assert not other.exists()


@pytest.mark.parametrize("link", ["symlink", "hardlink"])
def test_accept_does_not_write_through_a_temporary_file_left_as_a_link(
    desk: Desk, link: str
) -> None:
    outside = desk.root / "outside.txt"
    outside.write_bytes(b"OUTSIDE")
    temporary = desk.accepted.with_name(core.ACCEPTED_FILE + ".tmp")
    if link == "symlink":
        temporary.symlink_to(outside)
    else:
        os.link(outside, temporary)

    result = desk.accept()

    assert result.code == checker.EXIT_OK
    assert outside.read_bytes() == b"OUTSIDE"
    assert not desk.accepted.is_symlink() and not temporary.exists()
    assert core.load_accepted(desk.accepted)[1] == ""


def test_accept_needs_all_four_paths(desk: Desk, capsys: pytest.CaptureFixture[str]) -> None:
    code = checker.main(
        ["--work", str(desk.work), "--params", str(desk.params)]
        + ["--accepted", str(desk.accepted), "--accept"]
    )

    assert code == checker.EXIT_NOT_READY
    assert capsys.readouterr().out.strip() == "기준을 쓰지 않았습니다 — 인자 모자람"
    assert not desk.accepted.exists()


@pytest.mark.parametrize(
    ("spoil", "reason"),
    [
        ("stale", "판 다름"),
        ("db", "DB 변화 있음"),
        ("no_stamp", "조립 기록 없음"),
        ("shots_after", "조립 뒤 바뀜"),
        ("overrides_after", "조립 뒤 바뀜"),
        ("plan_after", "조립 뒤 바뀜"),
    ],
)
def test_accept_refuses_and_keeps_the_old_board(
    desk: Desk, spoil: str, reason: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    desk.accept()
    old = desk.accepted.read_bytes()
    desk.edit(LAYOUT, y=30.0)
    desk.stamp()
    if spoil == "stale":
        document = json.loads(desk.overrides.read_text(encoding="utf-8"))
        document["skeleton"] = "lob@2026-10-15"
        desk.overrides.write_text(json.dumps(document), encoding="utf-8")
        desk.stamp()
    elif spoil == "db":
        _run_facts(desk.work, mode="internal", db="changed")
    elif spoil == "no_stamp":
        (desk.work / core.ASSEMBLED_FILE).unlink()
    elif spoil == "shots_after":
        desk.edit(LAYOUT, x=5.0)
    elif spoil == "plan_after":
        # 조립 뒤 계획만 바뀜(note 는 촬영 동작 지문에 들지 않지만 도장에는 든다)
        plan = copy.deepcopy(dict(SKELETON.plan))
        plan["states"][0]["note"] = "조립 뒤에 고친 메모"
        monkeypatch.setattr(core, "load_skeleton", lambda *_a, **_k: _skeleton_with(plan=plan))
    else:
        desk.write_overrides(text={"proc_filter.apply.do": "조립 뒤에 고친 문장"})

    result = desk.check("--accept")

    assert result.code == checker.EXIT_NOT_READY
    assert result.out.strip() == f"기준을 쓰지 않았습니다 — {reason}"
    assert desk.accepted.read_bytes() == old


def test_a_failed_write_keeps_the_old_board_and_prints_no_review_line(
    desk: Desk, monkeypatch: pytest.MonkeyPatch
) -> None:
    desk.accept()
    old = desk.accepted.read_bytes()
    desk.edit(LAYOUT, y=30.0)

    def fail(_source: Any, _target: Any) -> None:
        raise OSError("가짜")

    desk.stamp()
    monkeypatch.setattr(os, "replace", fail)
    result = desk.check("--accept")

    assert result.code == checker.EXIT_NOT_READY
    assert result.out.strip() == "기준을 쓰지 못했습니다 — OSError"
    assert desk.accepted.read_bytes() == old
    assert not list(desk.accepted.parent.glob("*.tmp"))


def test_accept_keeps_the_old_record_of_a_place_not_compared_this_time(
    desk: Desk, monkeypatch: pytest.MonkeyPatch, example_dir: Path
) -> None:
    desk.accept()
    before = desk.baseline()["places"]["step:gap.gap_on"]
    examples = core.load_shots(example_dir / core.EXAMPLE_DIR)
    shots = core.load_shots(desk.work)
    examples.states["05_lobcond_open"] = dataclasses.replace(
        shots.states["05_lobcond_open"], substitute=False
    )
    monkeypatch.setattr(core, "load_examples", lambda _skeleton: examples)
    shots.states["05_lobcond_open"] = core.ShotState(
        "05_lobcond_open", None, {}, failed="05_lobcond_open.ops.0 click CaptureError"
    )
    core.save_shots(shots, desk.work)

    result = desk.accept()

    assert f"; 바뀜 {_data_count()}/{PLACES_COMPARED - 1}; " in result.line
    assert "예시 step:gap.gap_on" in result.err
    assert desk.baseline()["places"]["step:gap.gap_on"] == before


def test_raising_a_state_look_names_every_place_whose_chain_has_it(
    desk: Desk, monkeypatch: pytest.MonkeyPatch
) -> None:
    desk.accept()
    plan = copy.deepcopy(dict(SKELETON.plan))
    state = next(state for state in plan["states"] if state["id"] == "08_ref_avail")
    state["look"] = 2
    looked = _skeleton_with(plan=plan)
    assert core.skeleton_problems(looked) == []  # 계획 형식이 `look` 을 받는다
    monkeypatch.setattr(core, "load_skeleton", lambda *_a, **_k: looked)

    changed = desk.check().changed

    planned = {where for where, why in changed.items() if "계획" in why.split(" · ")}
    assert planned == _layout_places_using({"08_ref_avail"})


def test_a_state_note_is_not_part_of_the_capture_fingerprint(
    desk: Desk, monkeypatch: pytest.MonkeyPatch
) -> None:
    desk.accept()
    plan = copy.deepcopy(dict(SKELETON.plan))
    next(state for state in plan["states"] if state["id"] == "08_ref_avail")["note"] = "메모만"
    monkeypatch.setattr(core, "load_skeleton", lambda *_a, **_k: _skeleton_with(plan=plan))

    assert set(desk.check().changed.values()) == {"데이터 자리"}


def test_the_internal_settings_template_asks_for_the_checker_and_guards_the_board() -> None:
    """런북 10-4 — `--accept` 줄의 승인이 「검수 끝」 확인이라 점검기 · 생성기는 allow 에 없고,
    검수 마친 판은 점검기만 쓴다(편집 도구로 쓰지 않는다)."""
    template = json.loads(
        (PROJECT_ROOT / "docs" / "internal_claude_settings.json").read_text(encoding="utf-8")
    )
    allow, deny = template["permissions"]["allow"], template["permissions"]["deny"]

    assert not [rule for rule in allow if "page_guide" in rule]
    assert "Edit(review/**)" in allow
    assert f"Edit(review/guide/{core.ACCEPTED_FILE})" in deny
