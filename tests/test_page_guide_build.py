# Purpose: 가이드 생성기 · 점검기의 조립 · 덮어쓰기 · 거절 · 쓰기 등급을 가짜 촬영으로 잰다.

"""따라하기 가이드 생성기(`scripts/build_page_guide.py`)와 점검기(`scripts/check_page_guide.py`).

촬영은 브라우저 · 앱이 있어야 하므로 여기서는 가짜 촬영 결과(단색 그림 + 계획의 표적 좌표)로
조립 · 리뷰 한 줄을 돌리고, 촬영 차례(새 세션 · 쓰기 등급으로 건너뛰기)는 가짜 촬영기로 잰다.
실제 촬영은 사외 예시판을 만들 때(`--example`) 사람이 돌려 본다.
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import re
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import build_page_guide as builder  # noqa: E402
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
    assert line.startswith("가이드 lob@1022 판 다름(덮어쓰기 lob@1015) ")


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

    assert camera.calls.count("session") == 7  # 첫 세션 + 04 · 05 · 06 · 07 · 08 · 15 앞
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
        f"가이드 lob@1022 상태 18/18; 표적 {total}/{total} ok; 고아 0; 덮어씀 1; 예시 4; "
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
    assert "가이드 lob@1022 상태 18/18;" in out
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
    assert capsys.readouterr().out.strip().endswith("가이드 lob@1022 고아 0; 덮어씀 0")


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
