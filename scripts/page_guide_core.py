# Purpose: 따라하기 가이드의 순수 부분 — 뼈대 · 덮어쓰기 · 매개값 검사, 조립, 리뷰 한 줄.

"""따라하기 가이드의 순수 부분 — 브라우저 · 앱 없이 돈다.

`scripts/build_page_guide.py`(촬영 → 조립)와 `scripts/check_page_guide.py`(점검기)가 함께 쓴다.
뼈대(`src/capa_simulation/guides/howto/`)는 사외 정본이고, 사내는 글 덮어쓰기
(`review/guide/overrides.json`)와 매개값(`review/guide/params.json`)만 얹는다.

- **뼈대** `load_skeleton` — 원고 `content.json` · 계획 `plan.json` 을 읽는다(같은 키가 두 번
  나오면 실패). `skeleton_problems` 가 형식과 참조를 본다.
- **덮어쓰기** `check_overrides` · `apply_overrides` — 형식에 어긋나면(금지 칸 · HTML ·
  `javascript:`) 조립을 거절하고, 원고에 없는 주소(고아)는 건너뛰며 센다. 적용 차례는
  원고 → `text` 바꿈 → `add` 덧붙임 → `hide` 감춤. `hide` · `text` 의 `stuck.<번호>` 는 원고의
  번호다(덧붙인 줄은 감출 수 없다).
- **매개값** `resolve_params` — 계획에 선언된 이름 · 형(글자 · 정수 · 고르기)만 받는다.
- **조립** `assemble` — 촬영 결과(`shots.json` + 화면 그림)를 잘라 번호 상자와 함께 틀
  (`template.html`)의 `/*__DATA__*/null` 자리에 JSON 으로 넣는다. 자르기 규칙은 시안
  `build_guide.py` 그대로다(아래 상수).
- **리뷰 한 줄** `review_line` — 리뷰 md 에 옮길 압축 꼴. ID · 수만 담는다.
- **바뀐 자리 검수** `compare_accepted` — 원고 자리마다(`place_geometry`) 표적 자리 · 자르기
  틀 · 원고 · 덮어쓰기 · 촬영 동작의 지문을 사내 기준 파일(`review/guide/accepted.json` — 지난번
  검수를 마친 판, 점검기 `--accept` 만 쓴다)과 견줘 바뀐 자리만 검수 목록에 올린다(리뷰 칸
  `바뀜 n/N`). 기준 파일을 못 읽으면 멈추지 않고 `바뀜 na` 다. 데이터 자리(`DATA_SHAPED`)는 좌표를
  남기지 않고 늘 목록에 든다. 생성기는 조립할 때마다 조립 도장(`--work/assembled.json`)을 남긴다.

화면 글자는 여기서 다루지 않는다 — 좌표와 상태 ID · 표적 이름만 다룬다.
"""

from __future__ import annotations

import base64
import contextlib
import copy
import hashlib
import io
import json
import os
import re
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

import jsonschema  # type: ignore[import-untyped]
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]
HOWTO_DIR: Final = PROJECT_ROOT / "src" / "capa_simulation" / "guides" / "howto"
SCHEMA_NAMES: Final = ("content", "plan", "overrides", "params", "accepted")
DEFAULT_GUIDE: Final = "lob"

# 쓰기 등급(plan.schema.json 의 `writes`). 사내 1단계는 사슬 전체가 앞의 둘인 상태만 찍는다.
WRITE_GRADES: Final = ("none", "session", "db", "shared")
READ_ONLY_GRADES: Final = frozenset({"none", "session"})

# 동작 낱말 — 생성기가 구현하는 목록이 정본이다(계획 형식 `op` 와 시험이 이것과 같은지 본다).
OPS: Final = frozenset(
    {
        "enter_app",
        "nav",
        "tab",
        "click",
        "fill",
        "key",
        "scroll",
        "open_popup",
        "grid_edit",
        "egrid_edit",
        "wait_idle",
    }
)
TARGET_KINDS: Final = frozenset({"key", "button", "tab", "nav", "text", "named"})
# 코드로 찾는 표적 — 이름 → 괄호 안 글자를 받는지. 생성기(`build_page_guide.NAMED_JS`)가 같은
# 이름을 모두 구현하고, 계획 형식의 `target_word` pattern 이 같은 목록을 적는다.
NAMED_TARGETS: Final[dict[str, bool]] = {
    "SIDEBAR_SCEN": False,
    "SIDEBAR_BADGE": False,
    "SIDEBAR_PENDING": False,
    "SIDEBAR_FOOTER": False,
    "HEADER_BAND": False,
    "PAGE_TITLE": False,
    "DIALOG": False,
    "DIALOG_SECTIONS": False,
    "GRID": False,
    "LAST_GRID": False,
    "EDIT_CELL": False,
    "EDIT_ROW": False,
    "EGRID": False,
    "EGRID_CELL": False,
    "LOB_CHART": False,
    "LOB_BN_BARS": False,
    "KEY_PROCESS_GRID": False,
    "DETAIL_BN": False,
    "BN_CELL": False,
    "PROC_HEAD": False,
    "PROC_MONTH_CANVAS": False,
    "PF_TILES": False,
    "MAIN_LINK": True,
    "MAIN_ALERT": True,
    "HEAD_BOX": True,
    "WIDGET": True,
    "FORM_OF": True,
    "EXPANDER": True,
    "KEY_BUTTON": True,
    "GRID_COLUMN": True,
    "LOB_LABEL": True,
    "LOB_ROW": True,
}

# 그림 밑 꼬리표(handoff §7). 사내판의 사내 화면은 촬영 날짜를 단다.
EXAMPLE_LABEL: Final = "예시 화면 · 합성 샘플"
INTERNAL_LABEL: Final = "실제 화면 · {date}"

# 조립 규칙(시안 build_guide.py 그대로). 좌표는 화면 CSS px, 그림은 배율(scale)배다.
PAD: Final = 44  # 잘라 낼 때 표적 둘레 여백
MIN_W: Final = 460  # 너무 작게 잘리면 어디인지 모른다
MIN_H: Final = 250
FULL_W: Final = 1440  # 전체 화면 그림(작은 지도 · 크게 보기 · 앱 창 예시)의 폭
CROP_MAX: Final = 960  # 단계 그림 폭 상한(가이드 창 480px 의 2배)
SPLIT_W: Final = 760  # 표적이 이보다 넓게 흩어지면 표적마다 잘라 위아래로 쌓는다
SPLIT_MIN_W: Final = 440
SPLIT_MIN_H: Final = 150
CLIP_W: Final = 700  # 한 표적이 이보다 넓으면(폼 · 넓은 표) 왼쪽(이름 · 입력 시작)만
CROP_QUALITY: Final = 80
FULL_QUALITY: Final = 72
THUMB_PAD: Final = 28
THUMB_MIN: Final = (420, 262)
THUMB_CLIP_W: Final = 640
THUMB_WIDTH: Final = 360
THUMB_QUALITY: Final = 74
MAP_PAD: Final = 14
SPOT_PAD: Final = 30
SPOT_MIN: Final = (360, 150)
SPOT_WIDTH: Final = 720

# 사내판이 대신 끼우는 합성 예시 그림(배율 그대로 저장 — 사내 조립이 다시 자른다).
EXAMPLE_QUALITY: Final = 88

DATA_SLOT: Final = "/*__DATA__*/null"
SHOTS_FILE: Final = "shots.json"
RUN_FILE: Final = "run.json"
EXAMPLE_DIR: Final = "example"

Rect = list[float]


class GuideInputError(ValueError):
    """조립을 거절한다 — 뼈대 · 덮어쓰기 · 매개값 · 작업 폴더가 받을 수 없는 꼴이다.

    `problems` 는 주소 · 이름 · 고정 글자만 담는다(사내 글 값은 담지 않는다).
    """

    def __init__(self, what: str, problems: Sequence[str]) -> None:
        super().__init__(f"{what} — {len(problems)}곳")
        self.what = what
        self.problems = list(problems)


# ------------------------------------------------------------------ JSON · 뼈대


def load_json(path: Path) -> Any:
    """JSON 을 읽는다. 같은 키가 두 번 나오면 실패한다 — `json` 은 뒤 값으로 조용히 덮는다."""

    def no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        keys = [key for key, _ in pairs]
        repeated = sorted({key for key in keys if keys.count(key) > 1})
        if repeated:
            raise ValueError(f"{path.name}: 같은 키가 두 번 나옵니다 — {repeated}")
        return dict(pairs)

    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=no_duplicates)


def schema_errors(document: Any, name: str, howto: Path = HOWTO_DIR) -> list[str]:
    """형식(`schema/<name>.schema.json`)에 어긋나는 곳 — `자리: 까닭` 꼴(자리는 JSON 경로)."""
    schema = load_json(howto / "schema" / f"{name}.schema.json")
    validator = jsonschema.Draft202012Validator(schema)
    return sorted(
        "/".join(str(part) for part in error.absolute_path) or "(뿌리)"
        for error in validator.iter_errors(document)
    )


@dataclass(frozen=True)
class Skeleton:
    """한 가이드의 뼈대 — 원고와 촬영 계획."""

    name: str
    folder: Path
    content: Mapping[str, Any]
    plan: Mapping[str, Any]

    @property
    def version(self) -> str:
        return str(self.plan["version"])

    @property
    def states(self) -> list[Mapping[str, Any]]:
        return list(self.plan["states"])

    def state(self, state_id: str) -> Mapping[str, Any]:
        for state in self.plan["states"]:
            if state["id"] == state_id:
                return dict(state)
        raise KeyError(state_id)

    def state_ids(self) -> list[str]:
        return [str(state["id"]) for state in self.plan["states"]]

    def chain(self, state_id: str) -> list[str]:
        """뿌리부터 그 상태까지의 사슬."""
        by_id = {state["id"]: state for state in self.plan["states"]}
        chain = [state_id]
        while "from" in by_id[chain[0]]:
            chain.insert(0, str(by_id[chain[0]]["from"]))
        return chain

    def read_only(self, state_id: str) -> bool:
        """사슬 전체가 `none` · `session` 인가 — 사본 DB 를 바꾸지 않고 닿는 화면인가."""
        grades = {str(self.state(link)["writes"]) for link in self.chain(state_id)}
        return grades <= READ_ONLY_GRADES

    def read_only_ids(self) -> list[str]:
        return [state_id for state_id in self.state_ids() if self.read_only(state_id)]

    def target_names(self, state_id: str) -> list[str]:
        return list(self.state(state_id)["targets"])


def load_skeleton(name: str = DEFAULT_GUIDE, howto: Path = HOWTO_DIR) -> Skeleton:
    folder = howto / name
    return Skeleton(
        name=name,
        folder=folder,
        content=load_json(folder / "content.json"),
        plan=load_json(folder / "plan.json"),
    )


def picture_refs(content: Mapping[str, Any]) -> Iterator[tuple[str, str]]:
    """(자리, 그림 상태) — 원고가 그림으로 쓰는 곳. 자리는 `step:과업.단계` · `thumb:과업` ·
    `map:과업` · `concept:개념` 꼴이다(같은 자리가 여러 번 나올 수 있다)."""
    for task in content["tasks"]:
        yield f"thumb:{task['id']}", str(task["thumb"]["state"])
        if "map" in task:
            yield f"map:{task['id']}", str(task["map"]["state"])
        for step in task.get("steps", []):
            yield f"step:{task['id']}.{step['id']}", str(step["state"])
    for concept in content["concepts"]:
        for spot in concept.get("spots", []):
            yield f"concept:{concept['id']}", str(spot["state"])


def _target_refs(content: Mapping[str, Any]) -> Iterator[tuple[str, str, str]]:
    """(자리, 상태, 표적) — 원고가 상자로 가리키는 모든 곳(`from` 은 빌려 온 상태로)."""
    for task in content["tasks"]:
        thumb = task["thumb"]
        for target in thumb["targets"]:
            yield f"thumb:{task['id']}", str(thumb["state"]), str(target)
        if "map" in task:
            board = task["map"]
            for target in board["frame"]:
                yield f"map:{task['id']}", str(board["state"]), str(target)
            for spot in board["spots"]:
                yield f"map:{task['id']}", str(board["state"]), str(spot["t"])
        for step in task.get("steps", []):
            for focus in step["focus"]:
                state = str(focus.get("from", step["state"]))
                yield f"step:{task['id']}.{step['id']}", state, str(focus["t"])
    for concept in content["concepts"]:
        for spot in concept.get("spots", []):
            yield f"concept:{concept['id']}", str(spot["state"]), str(spot["t"])


def skeleton_problems(skeleton: Skeleton, howto: Path = HOWTO_DIR) -> list[str]:
    """뼈대가 깨졌는가 — 형식 · 판 · 원고가 가리키는 상태와 표적. 사외 시험이 막는 것을 사내
    실행 앞에서 한 번 더 본다(빈 목록이어야 돈다)."""
    problems = [f"content:{where}" for where in schema_errors(skeleton.content, "content", howto)]
    problems += [f"plan:{where}" for where in schema_errors(skeleton.plan, "plan", howto)]
    if problems:
        return problems
    if skeleton.content["version"] != skeleton.plan["version"]:
        problems.append("판: 원고와 계획이 다름")
    planned = {state["id"]: set(state["targets"]) for state in skeleton.plan["states"]}
    for where, state, target in _target_refs(skeleton.content):
        if target not in planned.get(state, set()):
            problems.append(f"{where}: {target}@{state}")
    for where, state in picture_refs(skeleton.content):
        if state not in planned:
            problems.append(f"{where}: {state}")
    ids = [state["id"] for state in skeleton.plan["states"]]
    if len(ids) != len(set(ids)):
        problems.append("상태 ID 겹침")
    return problems


def compact_version(version: str) -> str:
    """`lob@2026-10-22` → `lob@1022`(리뷰 한 줄 꼴)."""
    name, _, date = version.partition("@")
    parts = date.split("-")
    return f"{name}@{parts[1]}{parts[2]}" if len(parts) == 3 else version


# ------------------------------------------------------------------ 덮어쓰기


@dataclass
class OverrideReport:
    """덮어쓰기를 원고에 대 본 결과. 주소만 담는다."""

    skeleton: str | None = None
    version_matches: bool = True
    orphans: list[str] = field(default_factory=list)
    applied: int = 0


def check_overrides(document: Any, howto: Path = HOWTO_DIR) -> None:
    """형식에 어긋나면(주소 꼴 · 금지 칸 · HTML · `javascript:`) `GuideInputError`."""
    problems = schema_errors(document, "overrides", howto)
    if problems:
        raise GuideInputError("조립 거절 — 덮어쓰기 형식", problems)


def _by_id(items: Iterable[Mapping[str, Any]], key: str = "id") -> dict[str, dict[str, Any]]:
    return {str(item[key]): item for item in items}  # type: ignore[misc]


def _text_slot(content: dict[str, Any], address: str) -> tuple[Any, Any] | None:
    """덮어쓸 글의 자리 (담는 것, 키) — 원고에 없으면 None(고아)."""
    parts = address.split(".")
    tasks = _by_id(content["tasks"])
    if parts[0] == "concept":
        concept = _by_id(content["concepts"]).get(parts[1])
        if concept is None:
            return None
        if len(parts) == 3:
            return (concept, parts[2]) if isinstance(concept.get(parts[2]), str) else None
        spots = {str(spot["t"]): spot for spot in concept.get("spots", [])}
        spot = spots.get(parts[3])
        return (
            (spot, parts[4]) if spot is not None and isinstance(spot.get(parts[4]), str) else None
        )
    task = tasks.get(parts[0])
    if task is None:
        return None
    if len(parts) == 2:
        return (task, parts[1]) if isinstance(task.get(parts[1]), str) else None
    if parts[1] == "spot":
        spots = {str(spot["t"]): spot for spot in task.get("map", {}).get("spots", [])}
        spot = spots.get(parts[2])
        return (
            (spot, parts[3]) if spot is not None and isinstance(spot.get(parts[3]), str) else None
        )
    step = _by_id(task.get("steps", [])).get(parts[1])
    if step is None:
        return None
    if len(parts) == 3:
        return (step, parts[2]) if isinstance(step.get(parts[2]), str) else None
    stuck = step.get("stuck", [])
    index = int(parts[3])
    return (stuck, index) if index < len(stuck) else None


def _step_of(content: dict[str, Any], address: str) -> dict[str, Any] | None:
    task_id, step_id = address.split(".")[:2]
    task = _by_id(content["tasks"]).get(task_id)
    if task is None:
        return None
    return _by_id(task.get("steps", [])).get(step_id)


def apply_overrides(
    content: Mapping[str, Any],
    document: Mapping[str, Any] | None,
    *,
    version: str,
    howto: Path = HOWTO_DIR,
) -> tuple[dict[str, Any], OverrideReport]:
    """원고 사본에 덮어쓰기를 얹는다 — 원고 → `text` → `add` → `hide`.

    형식에 어긋나면 `GuideInputError`(조립 거절). 원고에 없는 주소는 건너뛰고 `orphans` 에 센다.
    """
    result: dict[str, Any] = copy.deepcopy(dict(content))
    report = OverrideReport()
    if document is None:
        return result, report
    check_overrides(document, howto)
    report.skeleton = str(document["skeleton"])
    report.version_matches = report.skeleton == version

    # 원고 번호를 기억해 둔다 — `text`·`hide` 의 stuck 번호는 덧붙이기 전 원고의 번호다.
    stuck_rows: dict[int, list[tuple[int | None, str]]] = {}
    for task in result["tasks"]:
        for step in task.get("steps", []):
            if "stuck" in step:
                stuck_rows[id(step)] = list(enumerate(step["stuck"]))

    for address, text in document.get("text", {}).items():
        slot = _text_slot(result, address)
        if slot is None:
            report.orphans.append(address)
            continue
        holder, key = slot
        if isinstance(holder, list):
            step = _step_of(result, address)
            assert step is not None
            rows = stuck_rows[id(step)]
            rows[key] = (key, text)
        else:
            holder[key] = text
        report.applied += 1

    for address, lines in document.get("add", {}).items():
        step = _step_of(result, address)
        if step is None:
            report.orphans.append(address)
            continue
        rows = stuck_rows.setdefault(id(step), [])
        rows += [(None, line) for line in lines]
        report.applied += len(lines)

    hidden: dict[int, set[int]] = {}
    for address in document.get("hide", []):
        step = _step_of(result, address)
        index = int(address.rsplit(".", 1)[1])
        if step is None or index >= len(step.get("stuck", [])):
            report.orphans.append(address)
            continue
        hidden.setdefault(id(step), set()).add(index)
        report.applied += 1

    for task in result["tasks"]:
        for step in task.get("steps", []):
            final = stuck_rows.get(id(step))
            if final is None:
                continue
            gone = hidden.get(id(step), set())
            kept = [text for original, text in final if original is None or original not in gone]
            if kept:
                step["stuck"] = kept
            else:
                step.pop("stuck", None)
    return result, report


# ------------------------------------------------------------------ 매개값


@dataclass
class ParamReport:
    skeleton: str | None = None
    version_matches: bool = True
    given: int = 0


def resolve_params(
    plan: Mapping[str, Any],
    document: Mapping[str, Any] | None,
    *,
    howto: Path = HOWTO_DIR,
) -> tuple[dict[str, str | int], ParamReport]:
    """계획의 기본값 위에 사내 매개값을 얹는다. 이름 · 형이 어긋나면 `GuideInputError`."""
    declared: Mapping[str, Any] = plan["params"]
    values: dict[str, str | int] = {name: spec["default"] for name, spec in declared.items()}
    report = ParamReport()
    if document is None:
        return values, report
    problems = schema_errors(document, "params", howto)
    if problems:
        raise GuideInputError("조립 거절 — 매개값 형식", problems)
    report.skeleton = str(document["skeleton"])
    report.version_matches = report.skeleton == plan["version"]
    wrong: list[str] = []
    for name, value in document["values"].items():
        spec = declared.get(name)
        if spec is None:
            wrong.append(f"{name}: 계획에 없음")
            continue
        kind = spec["type"]
        if kind == "int" and not (isinstance(value, int) and not isinstance(value, bool)):
            wrong.append(f"{name}: 정수가 아님")
        elif kind in ("text", "choice") and not isinstance(value, str):
            wrong.append(f"{name}: 글자가 아님")
        elif kind == "choice" and value not in spec["choices"]:
            wrong.append(f"{name}: 고를 수 있는 값이 아님")
        else:
            values[name] = value
            report.given += 1
    if wrong:
        raise GuideInputError("조립 거절 — 매개값 형", wrong)
    return values, report


def bind_params(value: Any, params: Mapping[str, str | int]) -> Any:
    """계획 조각의 `{"param", "default"}` 자리를 값으로 바꾼 사본."""
    if isinstance(value, dict):
        if set(value) == {"param", "default"}:
            return params[str(value["param"])]
        return {key: bind_params(item, params) for key, item in value.items()}
    if isinstance(value, list):
        return [bind_params(item, params) for item in value]
    return value


# ------------------------------------------------------------------ 촬영 결과


@dataclass
class ShotState:
    """상태 하나의 촬영 결과. 좌표는 화면 CSS px."""

    id: str
    image: Path | None
    targets: dict[str, Rect]
    missing: list[str] = field(default_factory=list)
    failed: str | None = None
    date: str | None = None
    scale: float = 2.0
    substitute: bool = False  # 사내 실행에서 찍지 못해 합성 예시 그림으로 대신했다

    @property
    def ok(self) -> bool:
        return self.failed is None and self.image is not None and self.image.exists()


@dataclass
class ShotSet:
    """촬영 결과 묶음(`shots.json` + 그림). 사내판은 예시 그림을 대신 끼운다."""

    viewport: tuple[int, int] = (1440, 900)
    scale: float = 2.0
    mode: str = "example"
    version: str = ""
    states: dict[str, ShotState] = field(default_factory=dict)

    def ok(self, state_id: str) -> bool:
        state = self.states.get(state_id)
        return state is not None and state.ok

    def to_json(self, folder: Path) -> dict[str, Any]:
        """`folder/shots.json` 의 내용 — 그림 자리는 `folder` 에 대한 상대 경로."""
        records = []
        for state in self.states.values():
            file = None
            if state.image is not None:
                try:
                    file = state.image.relative_to(folder).as_posix()
                except ValueError:
                    file = state.image.name
            record: dict[str, Any] = {"id": state.id, "file": file, "targets": state.targets}
            if state.missing:
                record["missing"] = state.missing
            if state.failed:
                record["failed"] = state.failed
            if state.date:
                record["date"] = state.date
            records.append(record)
        return {
            "version": self.version,
            "mode": self.mode,
            "viewport": list(self.viewport),
            "scale": self.scale,
            "states": records,
        }


def load_shots(folder: Path) -> ShotSet:
    """`folder/shots.json` 을 읽는다. 그림 파일은 같은 폴더(또는 `shots/`)에 있다."""
    meta = load_json(folder / SHOTS_FILE)
    viewport = meta.get("viewport", [1440, 900])
    shots = ShotSet(
        viewport=(int(viewport[0]), int(viewport[1])),
        scale=float(meta.get("scale", 2)),
        mode=str(meta.get("mode", "example")),
        version=str(meta.get("version", "")),
    )
    for record in meta.get("states", []):
        name = record.get("file")
        image = None
        if name:
            image = folder / name
            if folder.resolve() not in image.resolve().parents:
                raise GuideInputError("작업 폴더 밖 그림", [str(record["id"])])
        shots.states[str(record["id"])] = ShotState(
            id=str(record["id"]),
            image=image,
            targets={
                key: list(map(float, rect)) for key, rect in record.get("targets", {}).items()
            },
            missing=list(record.get("missing", [])),
            failed=record.get("failed"),
            date=record.get("date"),
            scale=shots.scale,
        )
    return shots


def save_shots(shots: ShotSet, folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    text = json.dumps(shots.to_json(folder), ensure_ascii=False, indent=1)
    (folder / SHOTS_FILE).write_text(text + "\n", encoding="utf-8")


def load_examples(skeleton: Skeleton) -> ShotSet | None:
    """뼈대에 실린 합성 예시 그림(`<가이드>/example/`). 없으면 None."""
    folder = skeleton.folder / EXAMPLE_DIR
    if not (folder / SHOTS_FILE).exists():
        return None
    return load_shots(folder)


def export_examples(
    shots: ShotSet, state_ids: Iterable[str], folder: Path, *, quality: int = EXAMPLE_QUALITY
) -> list[str]:
    """사내가 찍지 않는 상태의 합성 화면을 예시 그림(WebP)과 좌표로 내보낸다. 내보낸 상태 ID."""
    folder.mkdir(parents=True, exist_ok=True)
    out = ShotSet(viewport=shots.viewport, scale=shots.scale, mode="example", version=shots.version)
    for state_id in state_ids:
        if not shots.ok(state_id):
            continue
        source = shots.states[state_id]
        assert source.image is not None
        target = folder / f"{state_id}.webp"
        with Image.open(source.image) as opened:
            opened.convert("RGB").save(target, "WEBP", quality=quality, method=6)
        out.states[state_id] = ShotState(
            id=state_id,
            image=target,
            targets=dict(source.targets),
            missing=list(source.missing),
            scale=source.scale,
        )
    save_shots(out, folder)
    return list(out.states)


def merge_shots(base: ShotSet, newer: ShotSet) -> ShotSet:
    """앞 결과에 새로 찍은 상태를 합친다(같은 상태는 새것). 판 · 모드가 다르면 거절."""
    if base.version != newer.version or base.mode != newer.mode:
        raise GuideInputError("작업 폴더의 앞 결과가 다른 판 · 모드", [base.version, base.mode])
    merged = ShotSet(
        viewport=newer.viewport,
        scale=newer.scale,
        mode=newer.mode,
        version=newer.version,
        states=dict(base.states),
    )
    merged.states.update(newer.states)
    return merged


def with_examples(shots: ShotSet, examples: ShotSet | None, wanted: Iterable[str]) -> ShotSet:
    """찍지 못한 상태를 합성 예시 그림으로 대신한 사본(사내판). 바꾼 상태는 `substitute`."""
    result = ShotSet(
        viewport=shots.viewport,
        scale=shots.scale,
        mode=shots.mode,
        version=shots.version,
        states=dict(shots.states),
    )
    if examples is None:
        return result
    for state_id in wanted:
        if result.ok(state_id) or not examples.ok(state_id):
            continue
        source = examples.states[state_id]
        result.states[state_id] = ShotState(
            id=state_id,
            image=source.image,
            targets=dict(source.targets),
            missing=list(source.missing),
            scale=examples.scale,
            substitute=True,
        )
    return result


def label_for(state: ShotState, mode: str) -> str:
    if mode == "internal" and not state.substitute:
        return INTERNAL_LABEL.format(date=state.date or "날짜 없음")
    return EXAMPLE_LABEL


# ------------------------------------------------------------------ 조립


def pct(rect: Sequence[float], frame: Sequence[float]) -> dict[str, float]:
    """화면 좌표 `rect` 를 `frame`(잘라 낸 상자 또는 전체 화면) 기준 % 로. 밖으로 나간 부분은
    잘라 낸다(긴 표 · 화면 아래로 이어지는 요소)."""
    fx, fy, fw, fh = frame
    x0, y0 = max(rect[0], fx), max(rect[1], fy)
    x1, y1 = min(rect[0] + rect[2], fx + fw), min(rect[1] + rect[3], fy + fh)
    width, height = max(0.0, x1 - x0), max(0.0, y1 - y0)
    return {
        "x": round((x0 - fx) / fw * 100, 3),
        "y": round((y0 - fy) / fh * 100, 3),
        "w": round(width / fw * 100, 3),
        "h": round(height / fh * 100, 3),
    }


def frame_around(
    rects: Sequence[Sequence[float]],
    viewport: tuple[int, int],
    *,
    pad: float = PAD,
    min_w: float = MIN_W,
    min_h: float = MIN_H,
) -> list[int] | None:
    """표적 합집합 + 여백, 최소 크기, 화면 안으로 밀어 넣기 — `[x, y, w, h]`(정수)."""
    if not rects:
        return None
    x0 = min(r[0] for r in rects) - pad
    y0 = min(r[1] for r in rects) - pad
    x1 = max(r[0] + r[2] for r in rects) + pad
    y1 = max(r[1] + r[3] for r in rects) + pad
    if x1 - x0 < min_w:
        middle = (x0 + x1) / 2
        x0, x1 = middle - min_w / 2, middle + min_w / 2
    if y1 - y0 < min_h:
        middle = (y0 + y1) / 2
        y0, y1 = middle - min_h / 2, middle + min_h / 2
    if x0 < 0:
        x1, x0 = x1 - x0, 0
    if y0 < 0:
        y1, y0 = y1 - y0, 0
    x1, y1 = min(x1, viewport[0]), min(y1, viewport[1])
    return [round(x0), round(y0), round(x1 - x0), round(y1 - y0)]


@dataclass
class AssemblyReport:
    """조립이 남긴 수 — 그림 장수 · 대신한 예시 자리 · 그림 없는 단계 · 못 찾은 상자."""

    images: int = 0
    example_spots: set[str] = field(default_factory=set)
    no_picture: list[str] = field(default_factory=list)
    missing_boxes: list[str] = field(default_factory=list)


class Assembler:
    """촬영 결과를 잘라 원고와 묶는다(시안 build_guide.py 의 규칙).

    `frames` 는 원고 자리(`step:` · `thumb:` · `map:` · `concept:`)마다 `crop()` 에 넘긴 틀을
    원고 차례로 적는다 — 그림을 못 낸 조각(표적을 못 찾은 썸네일 · 지도 · 개념 자리)은 None 이다.
    `pictures=False` 면 그림을 열지도 자르지도 않고 같은 데이터(그림 자리 이름)와 틀만 낸다 —
    바뀐 자리 검수(`place_geometry`)가 쓴다.
    """

    def __init__(self, shots: ShotSet, *, pictures: bool = True) -> None:
        self.shots = shots
        self.pictures = pictures
        self.images: dict[str, str] = {}
        self._pictures: dict[str, Image.Image] = {}
        self.report = AssemblyReport()
        self.whole: list[int] = [0, 0, shots.viewport[0], shots.viewport[1]]
        self.frames: dict[str, list[list[int] | None]] = {}

    # -- 표적

    def target(self, state_id: str, name: str) -> Rect | None:
        state = self.shots.states.get(state_id)
        rect = None if state is None else state.targets.get(name)
        return rect if rect and rect[2] > 0 and rect[3] > 0 else None

    def find(self, state_id: str, focus: str | Mapping[str, Any]) -> Rect | None:
        """표적 하나 — 원고가 `from` 으로 다른 상태를 가리키면 거기서 잰 자리를 빌린다."""
        if isinstance(focus, str):
            return self.target(state_id, focus)
        return self.target(str(focus.get("from", state_id)), str(focus["t"]))

    def rect(
        self,
        state_id: str,
        names: Sequence[str | Mapping[str, Any]],
        *,
        pad: float = PAD,
        min_w: float = MIN_W,
        min_h: float = MIN_H,
    ) -> list[int] | None:
        # `frame: false` 표적(넓은 구획 같은 「보는 곳」)은 상자만 그리고 자르는 범위에서 뺀다.
        framed = [
            name for name in names if isinstance(name, str) or name.get("frame", True) is not False
        ]
        rects = [r for r in (self.find(state_id, name) for name in framed) if r]
        return frame_around(rects, self.shots.viewport, pad=pad, min_w=min_w, min_h=min_h)

    # -- 그림

    def _picture(self, state_id: str) -> Image.Image:
        if state_id not in self._pictures:
            path = self.shots.states[state_id].image
            assert path is not None
            with Image.open(path) as opened:
                self._pictures[state_id] = opened.convert("RGB")
        return self._pictures[state_id]

    def _label(self, state_id: str) -> str:
        return label_for(self.shots.states[state_id], self.shots.mode)

    def _put(
        self, key: str, make: Callable[[], Image.Image], quality: int, state_id: str
    ) -> dict[str, str]:
        """그림 자리 하나 — 같은 자리는 한 번만 만든다. `pictures=False` 면 그림을 만들지 않는다."""
        if self.pictures and key not in self.images:
            buffer = io.BytesIO()
            make().save(buffer, "WEBP", quality=quality, method=6)
            encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
            self.images[key] = "data:image/webp;base64," + encoded
        return {"src": key, "cap": self._label(state_id)}

    def full(self, state_id: str) -> dict[str, str]:
        def make() -> Image.Image:
            picture = self._picture(state_id)
            height = round(picture.height * FULL_W / picture.width)
            return picture.resize((FULL_W, height), Image.Resampling.LANCZOS)

        return self._put("full:" + state_id, make, FULL_QUALITY, state_id)

    def crop(
        self,
        state_id: str,
        frame: Sequence[int],
        *,
        width: int = CROP_MAX,
        quality: int = CROP_QUALITY,
        where: str | None = None,
    ) -> dict[str, str]:
        if where is not None:
            self.frames.setdefault(where, []).append([int(value) for value in frame])

        def make() -> Image.Image:
            scale = self.shots.states[state_id].scale
            box = (
                round(frame[0] * scale),
                round(frame[1] * scale),
                round((frame[0] + frame[2]) * scale),
                round((frame[1] + frame[3]) * scale),
            )
            cut = self._picture(state_id).crop(box)
            out_w = min(width, cut.width)
            return cut.resize(
                (out_w, max(1, round(cut.height * out_w / cut.width))), Image.Resampling.LANCZOS
            )

        key = f"crop:{state_id}:{','.join(map(str, frame))}:{width}"
        return self._put(key, make, quality, state_id)

    def _no_piece(self, where: str) -> None:
        """그림을 못 낸 조각 — 틀 기록에 None 을 남긴다."""
        self.frames.setdefault(where, []).append(None)

    def boxes(
        self, state_id: str, focus: Sequence[Mapping[str, Any]], frame: Sequence[float]
    ) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for item in focus:
            rect = self.find(state_id, item)
            if not rect:
                self.report.missing_boxes.append(f"{item['t']}@{item.get('from', state_id)}")
                continue
            box: dict[str, Any] = dict(pct(rect, frame))
            box["kind"] = item.get("kind", "do")
            if "n" in item:
                box["n"] = item["n"]
            out.append(box)
        return out

    def _note_picture(self, where: str, state_id: str) -> None:
        if self.shots.states[state_id].substitute:
            self.report.example_spots.add(where)

    # -- 조각

    def task(self, task: Mapping[str, Any]) -> dict[str, Any]:
        out = {key: value for key, value in task.items() if key not in ("steps", "thumb", "map")}
        thumb = task.get("thumb")
        where = f"thumb:{task['id']}"
        frame = None
        if thumb and self.shots.ok(thumb["state"]):
            frame = self.rect(
                thumb["state"],
                thumb["targets"],
                pad=THUMB_PAD,
                min_w=THUMB_MIN[0],
                min_h=THUMB_MIN[1],
            )
            if frame and frame[2] > THUMB_CLIP_W:
                frame = [frame[0], frame[1], THUMB_CLIP_W, frame[3]]
            if frame:
                out["thumb"] = self.crop(
                    thumb["state"], frame, width=THUMB_WIDTH, quality=THUMB_QUALITY, where=where
                )
                self._note_picture(where, thumb["state"])
        if thumb and not frame:
            self._no_piece(where)
        if task.get("map"):
            out["map"] = self.board(task)
        steps = [self.step(task, step) for step in task.get("steps", [])]
        if steps:
            out["steps"] = steps
        return out

    def board(self, task: Mapping[str, Any]) -> dict[str, Any]:
        board = task["map"]
        state_id = board["state"]
        out: dict[str, Any] = {"color": board.get("color")}
        frame = (
            self.rect(state_id, board["frame"], pad=MAP_PAD, min_w=0, min_h=0)
            if self.shots.ok(state_id)
            else None
        )
        if frame is None:
            out["spots"] = board["spots"]
            self.report.no_picture.append(f"map:{task['id']}")
            self._no_piece(f"map:{task['id']}")
            return out
        out["crop"] = self.crop(state_id, frame, where=f"map:{task['id']}")
        out["full"] = self.full(state_id)
        out["fullBoxes"] = self.boxes(
            state_id, [{"t": name, "kind": "see"} for name in board["frame"]], self.whole
        )
        self._note_picture(f"map:{task['id']}", state_id)
        spots: list[dict[str, Any]] = []
        for spot in board["spots"]:
            rect = self.target(state_id, spot["t"])
            if rect and spot.get("row"):
                # 줄 이름에서 표 오른쪽 끝까지 — 「이 줄의 숫자들」을 누르는 자리
                left = rect[0] - 8
                rect = [left, rect[1] - 5, frame[0] + frame[2] - 10 - left, rect[3] + 10]
            elif rect:
                rect = [rect[0] - 4, rect[1] - 4, rect[2] + 8, rect[3] + 8]
            spots.append(dict(spot, box=pct(rect, frame) if rect else None))
        out["spots"] = spots
        return out

    def step(self, task: Mapping[str, Any], step: Mapping[str, Any]) -> dict[str, Any]:
        state_id = step["state"]
        where = f"step:{task['id']}.{step['id']}"
        out = {key: value for key, value in step.items() if key != "focus"}
        if not self.shots.ok(state_id):
            self.report.no_picture.append(where)
            return out
        focus = step["focus"]
        frame = self.rect(state_id, focus) or self.whole
        clip_w = int(step.get("clip_w", CLIP_W))
        framed = [f for f in focus if f.get("frame", True) is not False and self.find(state_id, f)]
        if frame[2] > SPLIT_W and len(framed) > 1:
            # 흩어진 표적 — 표적마다 한 장씩(번호 상자는 그 장에만)
            crops = []
            for item in framed:
                one = self.rect(state_id, [item], min_w=SPLIT_MIN_W, min_h=SPLIT_MIN_H)
                assert one is not None
                if one[2] > clip_w:
                    one = [one[0], one[1], clip_w, one[3]]
                crops.append(
                    {
                        "crop": self.crop(state_id, one, where=where),
                        "boxes": self.boxes(state_id, [item], one),
                    }
                )
            out["crops"] = crops
        else:
            if frame[2] > clip_w and len(framed) <= 1:
                frame = [frame[0], frame[1], clip_w, frame[3]]
            out["crop"] = self.crop(state_id, frame, where=where)
            out["boxes"] = self.boxes(state_id, focus, frame)
        out["full"] = self.full(state_id)
        out["fullBoxes"] = self.boxes(state_id, focus, self.whole)
        out["area"] = pct(frame, self.whole)
        self._note_picture(where, state_id)
        return out

    def concept(self, concept: Mapping[str, Any]) -> dict[str, Any]:
        out = dict(concept)
        if not concept.get("spots"):
            return out
        where = f"concept:{concept['id']}"
        spots: list[dict[str, Any]] = []
        for spot in concept["spots"]:
            item = dict(spot)
            state_id = spot["state"]
            if self.shots.ok(state_id) and self.target(state_id, spot["t"]):
                frame = self.rect(
                    state_id, [spot["t"]], pad=SPOT_PAD, min_w=SPOT_MIN[0], min_h=SPOT_MIN[1]
                )
                assert frame is not None
                item["crop"] = self.crop(state_id, frame, width=SPOT_WIDTH, where=where)
                number = len(spots) + 1
                item["boxes"] = self.boxes(
                    state_id, [{"t": spot["t"], "n": number, "kind": "see"}], frame
                )
                item["full"] = self.full(state_id)
                item["fullBoxes"] = self.boxes(
                    state_id, [{"t": spot["t"], "kind": "see"}], self.whole
                )
                self._note_picture(where, state_id)
            else:
                self.report.no_picture.append(f"{where}.{spot['t']}")
                self._no_piece(where)
            spots.append(item)
        out["spots"] = spots
        return out


def assemble(
    content: Mapping[str, Any], shots: ShotSet, *, home_state: str = "01_home_main"
) -> tuple[dict[str, Any], AssemblyReport]:
    """틀에 넣을 데이터(그림은 data URI 로 `images` 에)와 조립 보고."""
    assembler = Assembler(shots)
    tasks = [assembler.task(task) for task in content["tasks"]]
    concepts = [assembler.concept(concept) for concept in content["concepts"]]
    data = {
        "page": content["page"],
        "version": content["version"],
        "shotLabel": EXAMPLE_LABEL
        if shots.mode != "internal"
        else INTERNAL_LABEL.format(date=_latest_date(shots)),
        "groups": content["groups"],
        "statePick": content["state_pick"],
        "tasks": tasks,
        "concepts": concepts,
        "synonyms": content.get("synonyms", {}),
        "homeShot": assembler.full(home_state) if shots.ok(home_state) else None,
        "images": assembler.images,
    }
    assembler.report.images = len(assembler.images)
    return data, assembler.report


def _latest_date(shots: ShotSet) -> str:
    dates = sorted(
        state.date for state in shots.states.values() if state.date and not state.substitute
    )
    return dates[-1] if dates else "날짜 없음"


def render_html(template: str, data: Mapping[str, Any]) -> str:
    """틀의 `/*__DATA__*/null` 자리에 JSON 을 넣는다. `<` 는 모두 `\\u003c` 로 — 글에 든
    `</script>` · `<!--` 가 스크립트 칸을 끊지 못한다."""
    if template.count(DATA_SLOT) != 1:
        raise GuideInputError("틀의 데이터 자리", [DATA_SLOT])
    payload = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")
    return template.replace(DATA_SLOT, payload)


# ------------------------------------------------------------------ 리뷰 한 줄


@dataclass
class RunFacts:
    """작업 폴더의 `run.json` — 촬영 실행이 남긴 사실(ID · 수 · 고정 글자)."""

    mode: str = "example"
    version: str = ""
    allow_writes: bool = False
    skipped: list[str] = field(default_factory=list)
    left: list[str] = field(default_factory=list)
    db: str = "unchecked"  # same | changed | writes | example | unchecked

    def to_json(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "version": self.version,
            "allow_writes": self.allow_writes,
            "skipped": self.skipped,
            "left": self.left,
            "db": self.db,
        }


def load_run(folder: Path) -> RunFacts:
    path = folder / RUN_FILE
    if not path.exists():
        return RunFacts()
    raw = load_json(path)
    return RunFacts(
        mode=str(raw.get("mode", "example")),
        version=str(raw.get("version", "")),
        allow_writes=bool(raw.get("allow_writes", False)),
        skipped=list(raw.get("skipped", [])),
        left=list(raw.get("left", [])),
        db=str(raw.get("db", "unchecked")),
    )


def save_run(run: RunFacts, folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    text = json.dumps(run.to_json(), ensure_ascii=False, indent=1)
    (folder / RUN_FILE).write_text(text + "\n", encoding="utf-8")


def merge_runs(base: RunFacts, newer: RunFacts) -> RunFacts:
    """앞 실행과 합친다 — DB 변화는 한 번이라도 있으면 있음."""
    order = ("changed", "writes", "unchecked", "same", "example")
    db = min((base.db, newer.db), key=lambda value: order.index(value) if value in order else 0)
    return RunFacts(
        mode=newer.mode,
        version=newer.version,
        allow_writes=base.allow_writes or newer.allow_writes,
        skipped=sorted(set(newer.skipped)),
        left=sorted(set(newer.left)),
        db=db,
    )


DB_WORDS: Final[dict[str, str]] = {
    "same": "DB 변화 없음",
    "changed": "DB 변화 있음",
    "writes": "DB 쓰기 허락(안 봄)",
    "example": "DB 안 봄(예시판)",
    "unchecked": "DB 안 봄",
}
NG_SHOWN: Final = 3


def expected_states(skeleton: Skeleton, run: RunFacts) -> list[str]:
    """이 실행이 찍어야 하는 상태 — 사내 1단계는 읽기만 하는 사슬, 그 밖은 모두."""
    if run.mode == "internal" and not run.allow_writes:
        return skeleton.read_only_ids()
    return skeleton.state_ids()


def target_tally(
    skeleton: Skeleton, shots: ShotSet, expected: Sequence[str]
) -> tuple[int, int, list[str]]:
    """(찾은 표적, 잴 표적, 못 찾은 `표적@상태`) — 돌린(찍었거나 실패한) 상태만 센다. 실패한
    상태는 표적 전부를 못 찾은 것으로 세고 `*@상태` 한 줄로 적는다."""
    found = total = 0
    missing: list[str] = []
    for state_id in expected:
        state = shots.states.get(state_id)
        if state is None or state.substitute:
            continue
        names = skeleton.target_names(state_id)
        total += len(names)
        if not state.ok:
            missing.append(f"*@{state_id}")
            continue
        for name in names:
            if name in state.targets:
                found += 1
            else:
                missing.append(f"{name}@{state_id}")
    return found, total, missing


def example_spots(content: Mapping[str, Any], shots: ShotSet) -> set[str]:
    """그림을 합성 예시로 대신한 원고 자리(`step:` · `thumb:` · `map:` · `concept:`)."""
    return {
        where
        for where, state_id in picture_refs(content)
        if state_id in shots.states and shots.states[state_id].substitute and shots.ok(state_id)
    }


def stale_versions(overrides: OverrideReport, params: ParamReport | None) -> list[str]:
    """뼈대와 판이 다른 사내 파일 — `덮어쓰기 lob@1015` 꼴(리뷰 한 줄의 「판 다름」)."""
    stale = []
    if overrides.skeleton is not None and not overrides.version_matches:
        stale.append(f"덮어쓰기 {compact_version(overrides.skeleton)}")
    if params is not None and params.skeleton is not None and not params.version_matches:
        stale.append(f"매개값 {compact_version(params.skeleton)}")
    return stale


def review_line(
    skeleton: Skeleton,
    shots: ShotSet | None,
    run: RunFacts | None,
    overrides: OverrideReport,
    params: ParamReport | None = None,
    *,
    example_count: int = 0,
    changes: ChangeReport | None = None,
) -> str:
    """리뷰 md 에 옮길 한 줄(handoff §6 의 압축 꼴). ID · 수 · 고정 글자만 담는다.

    `가이드 lob@1022 상태 18/18; 표적 n/N ok|ng <표적@상태>; 고아 0; 덮어씀 n; 예시 4; DB 변화 없음`
    — 검수 마친 판과 견줬으면(`changes`) `예시 4;` 뒤에 `바뀜 n/N;` 또는 `바뀜 na;` 가 선다.
    """
    head = f"가이드 {compact_version(skeleton.version)}"
    stale = stale_versions(overrides, params)
    if stale:
        head += f" 판 다름({' · '.join(stale)})"
    parts: list[str] = []
    if shots is not None and run is not None:
        if run.mode == "example":
            head += " 예시판"
        expected = expected_states(skeleton, run)
        captured = sum(
            1
            for state_id in expected
            if shots.ok(state_id) and not shots.states[state_id].substitute
        )
        found, total, missing = target_tally(skeleton, shots, expected)
        verdict = "ok" if not missing else "ng " + ", ".join(missing[:NG_SHOWN])
        if len(missing) > NG_SHOWN:
            verdict += f" 외 {len(missing) - NG_SHOWN}"
        parts += [f"상태 {captured}/{len(expected)}", f"표적 {found}/{total} {verdict}"]
    parts += [f"고아 {len(overrides.orphans)}", f"덮어씀 {overrides.applied}"]
    if shots is not None and run is not None:
        parts.append(f"예시 {example_count}")
        if changes is not None:
            parts.append(changes.cell)
        parts.append(DB_WORDS.get(run.db, DB_WORDS["unchecked"]))
    return f"{head} " + "; ".join(parts)


def board_shots(skeleton: Skeleton, work: Path) -> tuple[ShotSet, RunFacts]:
    """작업 폴더의 촬영 결과 — 사내판이면 찍지 못한 상태를 합성 예시 그림으로 대신한다.

    작업 폴더가 다른 뼈대 판에서 찍은 것이면 거절한다(표적 · 상태가 달라졌을 수 있다).
    """
    shots = load_shots(work)
    if shots.version != skeleton.version:
        raise GuideInputError("작업 폴더가 다른 뼈대 판", [compact_version(shots.version)])
    run = load_run(work)
    if run.mode == "internal":
        shots = with_examples(shots, load_examples(skeleton), skeleton.state_ids())
    return shots, run


@dataclass
class WorkReview:
    """작업 폴더 하나의 점검 결과 — 리뷰 한 줄 · stderr 목록과 그 바탕(점검기 `--accept` 가 씀)."""

    line: str
    details: list[str]
    shots: ShotSet
    run: RunFacts
    changes: ChangeReport | None
    stale: list[str]


def work_review(
    skeleton: Skeleton,
    content: Mapping[str, Any],
    work: Path,
    overrides: OverrideReport,
    params: ParamReport | None,
    *,
    accepted: Path | None = None,
) -> WorkReview:
    """작업 폴더로 리뷰 한 줄과 자세한 목록을 낸다. 목록 차례는 못 찾은 표적 → 고아 → 예시 →
    남은 상태, 검수 마친 판(`accepted`)을 주면 그 뒤에 기준 → 흔들림 → 바뀜(원고 차례)이다."""
    shots, run = board_shots(skeleton, work)
    examples = example_spots(content, shots)
    changes = (
        None
        if accepted is None
        else compare_accepted(skeleton, content, shots, load_accepted(accepted))
    )
    line = review_line(
        skeleton, shots, run, overrides, params, example_count=len(examples), changes=changes
    )
    _, _, missing = target_tally(skeleton, shots, expected_states(skeleton, run))
    details = [f"못 찾은 표적 {item}" for item in missing]
    details += [f"고아 {address}" for address in overrides.orphans]
    details += [f"예시 {where}" for where in sorted(examples)]
    details += [f"남은 상태 {state_id}" for state_id in run.left]
    if changes is not None:
        details += changes.lines()
    return WorkReview(line, details, shots, run, changes, stale_versions(overrides, params))


def review_for_work(
    skeleton: Skeleton,
    content: Mapping[str, Any],
    work: Path,
    overrides: OverrideReport,
    params: ParamReport | None,
    *,
    accepted: Path | None = None,
) -> tuple[str, list[str]]:
    """작업 폴더로 리뷰 한 줄과 자세한 목록(못 찾은 표적 · 고아 주소 …)을 낸다 — 생성기 끝과
    점검기가 같은 길을 쓴다. 생성기는 `accepted` 를 주지 않는다(리뷰 칸 `바뀜` 은 점검기만)."""
    review = work_review(skeleton, content, work, overrides, params, accepted=accepted)
    return review.line, review.details


# ------------------------------------------------------------------ 바뀐 자리 검수

# 검수 마친 판(사내 `review/guide/accepted.json`, 점검기 `--accept` 만 쓴다)과 조립 도장
# (`--work/assembled.json`, 생성기가 조립할 때마다 쓴다)의 파일 이름.
ACCEPTED_FILE: Final = "accepted.json"
ASSEMBLED_FILE: Final = "assembled.json"
# 검수 마친 판의 꼴 번호 — 칸을 바꾸면 올리고 `schema/accepted.schema.json` 의 `form` 도 고친다.
ACCEPTED_FORM: Final = 1
# 조립 규칙 판 — 사외가 손으로 1 올린다. 좌표(`t` · `f`)로 잡히지 않는 그리기를 바꿀 때다:
# 상자 · 틀 식의 코드 숫자(`frame_around` · `Assembler.board` 의 지도 칸 보정 · 나눠 쌓기 갈래),
# `pct`, 틀 `template.html` 의 상자 그리기. 올리지 않는 것 — PAD · MIN_* · SPLIT_* 같은 틀 상수
# (바뀌면 `f` 로 잡힌다), 화질 · 출력 폭 상수(CROP_QUALITY · FULL_W · THUMB_WIDTH · SPOT_WIDTH 등 —
# 좌표와 상관없다). 올리면 다음 회차는 모든 자리를 바뀜으로 본다(`바뀜 전부 조립 규칙`).
ACCEPT_RULES: Final = 1
# 표적 자리 · 크기와 자르기 틀이 이 px 를 넘게 움직이면 바뀜이다(사내 첫 두 회차의 `흔들림` 으로
# 다시 정한다 — 명세 7절 8단계).
MOVE_TOL_PX: Final = 2
# 데이터 자리 — 실데이터가 자리나 크기를 정하는 `named:` 표적(첫 부족 칸 · 고칠 칸이 놓인 행 ·
# 머리 띠 글 폭 · 배지 글 · 행 수나 공정에 따라 높이가 바뀌는 그림 · 표 · 팝업). 원고 자리가 이
# 가운데 하나라도 쓰면 그 자리는 기준 파일에 좌표 · 틀 · 지문을 적지 않고 회차마다 `바뀜 <자리>
# 데이터 자리` 로 검수 목록에 든다. 코드로 확인한 넷(BN_CELL · EDIT_CELL · EDIT_ROW · HEADER_BAND ·
# SIDEBAR_BADGE)은 빼지 않는다. 나머지는 사외가 합성 시드를 바꿔 다시 찍어 움직인 것이다(2026-11-02
# — 행 · 부족 칸 · 이름 길이 · 리비전 · 시나리오를 늘린 판과 제품 · 공정을 줄인 판): 후보 가운데
# 움직인 GRID · LAST_GRID · DETAIL_BN · KEY_PROCESS_GRID · LOB_BN_BARS · PROC_MONTH_CANVAS 는 두고
# 움직이지 않은 LOB_CHART · LOB_LABEL 은 뺐으며, 후보 밖에서 움직인 PF_TILES(공정 수만큼 타일) ·
# DIALOG(그 안의 타일 · 리비전 목록)를 더했다. 같은 HEAD 두 벌은 모든 표적이 Δ0 이었다. 범용 편집
# 그리드의 고친 칸(EGRID_CELL)은 EDIT_CELL 과 같은 까닭(고칠 칸이 놓인 행)으로 든다 — 그리드 틀
# (EGRID)은 창 높이로 서서 데이터가 크기를 정하지 않는다.
DATA_SHAPED: Final = frozenset(
    {
        "BN_CELL",
        "EDIT_CELL",
        "EDIT_ROW",
        "EGRID_CELL",
        "HEADER_BAND",
        "SIDEBAR_BADGE",
        "GRID",
        "LAST_GRID",
        "DETAIL_BN",
        "KEY_PROCESS_GRID",
        "LOB_BN_BARS",
        "PROC_MONTH_CANVAS",
        "PF_TILES",
        "DIALOG",
    }
)
# 흔들림 구간 — 기준과 견준 배치 자리마다 가장 큰 Δ(px)를 센다.
WOBBLE_BINS: Final = (("0", 0, 0), ("1-2", 1, 2), ("3-9", 3, 9), ("10+", 10, None))
_VERSION_TEXT: Final = re.compile(r"[a-z][a-z0-9_]*@[0-9]{4}-[0-9]{2}-[0-9]{2}")
_DATE_TEXT: Final = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")

Box = list[int] | None


def _fingerprint(value: Any) -> str:
    """지문 — 정렬한 JSON(공백 없음)의 sha256 앞 12자."""
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def seal(document: Mapping[str, Any]) -> str:
    """검수 마친 판의 봉인 — `seal` 칸을 뺀 문서의 지문."""
    return _fingerprint({key: value for key, value in document.items() if key != "seal"})


def place_order(content: Mapping[str, Any]) -> list[str]:
    """원고 자리 — 원고 차례, 겹치지 않게."""
    return list(dict.fromkeys(where for where, _state in picture_refs(content)))


def _place_objects(content: Mapping[str, Any]) -> dict[str, Any]:
    """자리마다 지문을 뜨는 원고 객체 — 단계 · 과업(`steps` · `map` 빼고) · 지도 · 개념."""
    objects: dict[str, Any] = {}
    for task in content["tasks"]:
        objects[f"thumb:{task['id']}"] = {
            key: value for key, value in task.items() if key not in ("steps", "map")
        }
        if "map" in task:
            objects[f"map:{task['id']}"] = task["map"]
        for step in task.get("steps", []):
            objects[f"step:{task['id']}.{step['id']}"] = step
    for concept in content["concepts"]:
        objects[f"concept:{concept['id']}"] = concept
    return objects


def _place_states(content: Mapping[str, Any]) -> dict[str, list[str]]:
    """자리가 가리키는 상태 — 그림 상태와 표적을 빌려 오는 상태(`from`)."""
    states: dict[str, list[str]] = {}
    for where, state in picture_refs(content):
        states.setdefault(where, [])
        if state not in states[where]:
            states[where].append(state)
    for where, state, _target in _target_refs(content):
        if state not in states.setdefault(where, []):
            states[where].append(state)
    return states


def _place_targets(content: Mapping[str, Any]) -> dict[str, list[str]]:
    """자리가 상자로 가리키는 `표적@상태` — 원고 차례, 겹치지 않게."""
    keys: dict[str, list[str]] = {}
    for where, state, target in _target_refs(content):
        key = f"{target}@{state}"
        if key not in keys.setdefault(where, []):
            keys[where].append(key)
    return keys


def _named_names(word: str | Sequence[str]) -> set[str]:
    """표적 낱말(또는 합집합 목록)이 쓰는 `named:` 이름."""
    words = [word] if isinstance(word, str) else list(word)
    return {item[len("named:") :].partition("(")[0] for item in words if item.startswith("named:")}


def data_places(skeleton: Skeleton) -> set[str]:
    """데이터 자리 — `DATA_SHAPED` 표적을 하나라도 쓰는 원고 자리."""
    planned = {state["id"]: state["targets"] for state in skeleton.plan["states"]}
    return {
        where
        for where, state, target in _target_refs(skeleton.content)
        if _named_names(planned[state][target]) & DATA_SHAPED
    }


def _clip(rect: Sequence[float], viewport: tuple[int, int]) -> list[int]:
    """표적 사각형을 화면 안으로 잘라 정수로(`pct` 와 같은 자르기, 틀은 화면 전체)."""
    x0, y0 = max(rect[0], 0.0), max(rect[1], 0.0)
    x1, y1 = min(rect[0] + rect[2], viewport[0]), min(rect[1] + rect[3], viewport[1])
    return [round(x0), round(y0), round(max(0.0, x1 - x0)), round(max(0.0, y1 - y0))]


def _plan_print(skeleton: Skeleton, states: Iterable[str]) -> str:
    """촬영 동작 지문 — 그 상태들의 `from` 사슬 정의(뿌리까지, `note` 만 빼고 `look` 은 넣는다)와
    계획의 `viewport` · `mask`. 매개값을 얹기 전의 계획으로 뜬다."""
    links: dict[str, Any] = {}
    for state_id in states:
        for link in skeleton.chain(state_id):
            links[link] = {
                key: value for key, value in skeleton.state(link).items() if key != "note"
            }
    return _fingerprint(
        {"states": links, "viewport": skeleton.plan["viewport"], "mask": skeleton.plan["mask"]}
    )


def place_geometry(
    skeleton: Skeleton, content: Mapping[str, Any], shots: ShotSet
) -> dict[str, dict[str, Any]]:
    """원고 자리마다 지금 촬영의 기록 — `f` 자르기 틀(조각마다, 그림 없는 조각은 None) · `t`
    표적(`표적@상태` → 화면 안으로 자른 정수 `[x, y, w, h]`, 못 찾았으면 None) · `sk` 원고 지문 ·
    `tx` 덮어쓴 원고 지문 · `pl` 촬영 동작 지문. 좌표 · ID · 지문만 담는다(그림 · 화면 글자 ·
    매개값의 값은 읽지 않는다). `content` 는 덮어쓰기를 얹은 원고다."""
    assembler = Assembler(shots, pictures=False)
    for task in content["tasks"]:
        assembler.task(task)
    for concept in content["concepts"]:
        assembler.concept(concept)
    script = _place_objects(skeleton.content)
    written = _place_objects(content)
    states = _place_states(skeleton.content)
    targets = _place_targets(skeleton.content)
    records: dict[str, dict[str, Any]] = {}
    for where in place_order(skeleton.content):
        boxes: dict[str, Box] = {}
        for key in targets.get(where, []):
            name, _, state_id = key.partition("@")
            rect = assembler.target(state_id, name)
            boxes[key] = _clip(rect, shots.viewport) if rect else None
        records[where] = {
            "f": list(assembler.frames.get(where, [])),
            "t": boxes,
            "sk": _fingerprint(script[where]),
            "tx": _fingerprint(written.get(where, script[where])),
            "pl": _plan_print(skeleton, states[where]),
        }
    return records


def compared_places(content: Mapping[str, Any], shots: ShotSet) -> list[str]:
    """견줄 자리(N) — 가리키는 상태가 모두 찍혔고 예시로 대신하지 않은 자리(원고 차례)."""

    def real(state_id: str) -> bool:
        return shots.ok(state_id) and not shots.states[state_id].substitute

    states = _place_states(content)
    return [where for where in place_order(content) if all(map(real, states[where]))]


def load_accepted(path: Path, howto: Path = HOWTO_DIR) -> tuple[dict[str, Any] | None, str]:
    """검수 마친 판을 읽는다 — (문서, "") 또는 (None, 까닭). 까닭은 `없음` · `버림 — <종류>` 이고,
    못 읽어도 예외를 내지 않는다(기준 파일 문제로 멈추지 않는다 — 리뷰 칸은 `바뀜 na`)."""
    try:
        if not path.exists():
            return None, "없음"
        document = load_json(path)
    except (OSError, ValueError, RecursionError) as exc:  # RecursionError — 너무 깊게 겹친 JSON
        return None, f"버림 — {type(exc).__name__}"
    if schema_errors(document, "accepted", howto) or not (
        _VERSION_TEXT.fullmatch(document["skeleton"]) and _DATE_TEXT.fullmatch(document["date"])
    ):
        return None, "버림 — 형식"
    if document["seal"] != seal(document):
        return None, "버림 — 봉인"
    return document, ""


@dataclass
class ChangeReport:
    """검수 마친 판과 견준 결과 — 자리 ID · 까닭 낱말 · 수만 담는다.

    `baseline` 이 None 이면 기준이 없거나 버렸다(`problem` 이 까닭). `whole` 은 모든 자리를
    바뀜으로 보는 까닭(`그림 크기` · `조립 규칙`)이다. `records` 는 견준 자리 가운데 데이터 자리가
    아닌 자리의 지금 기록이다(`--accept` 가 쓴다)."""

    order: list[str]
    data: set[str]
    compared: list[str]
    records: dict[str, dict[str, Any]]
    baseline: dict[str, Any] | None = None
    problem: str = ""
    whole: list[str] = field(default_factory=list)
    changed: list[tuple[str, list[str]]] = field(default_factory=list)
    wobble: list[int] = field(default_factory=lambda: [0] * len(WOBBLE_BINS))

    @property
    def count(self) -> int:
        """n — 바뀜 · 새 자리 · 데이터 자리(모두 바뀜이면 N)."""
        return len(self.compared) if self.whole else len(self.changed)

    @property
    def cell(self) -> str:
        """리뷰 한 줄의 칸 — `바뀜 n/N` 또는 `바뀜 na`."""
        if self.baseline is None:
            return "바뀜 na"
        return f"바뀜 {self.count}/{len(self.compared)}"

    def lines(self) -> list[str]:
        """stderr 줄(앞 두 칸은 붙이지 않는다) — 기준 → 흔들림 → 바뀜. ID · 수 · 고정 낱말만."""
        if self.baseline is None:
            return [f"기준 {self.problem} — 모든 자리"]
        head = (
            f"기준 {compact_version(self.baseline['skeleton'])} · {self.baseline['date']} · "
            f"{len(self.baseline['places'])}자리"
        )
        if self.whole:
            return [head, *[f"바뀜 전부 {why}" for why in self.whole]]
        wobble = " ".join(
            f"{label}:{count}"
            for (label, _low, _high), count in zip(WOBBLE_BINS, self.wobble, strict=True)
        )
        return [
            head,
            f"흔들림 {wobble}",
            *[f"바뀜 {where} {' · '.join(reasons)}" for where, reasons in self.changed],
        ]


def _delta(before: Sequence[int], after: Sequence[int]) -> int:
    return max(abs(int(a) - int(b)) for a, b in zip(before, after, strict=True))


def _place_reasons(
    before: Mapping[str, Any], now: Mapping[str, Any]
) -> tuple[list[str], int | None]:
    """배치 자리 하나의 (까닭 낱말, 가장 큰 Δ — 조각 수가 다르면 None)."""
    reasons: list[str] = []
    deltas: list[int] = []
    for key, box in now["t"].items():
        if key not in before["t"]:
            continue  # 원고가 바뀌어 생긴 표적 — `원고` 가 잡는다
        old = before["t"][key]
        if old is None and box is not None:
            reasons.append(f"찾음 {key}")
        elif old is not None and box is None:
            reasons.append(f"잃음 {key}")
        elif old is not None and box is not None:
            deltas.append(_delta(old, box))
            if deltas[-1] > MOVE_TOL_PX:
                reasons.append(f"상자 {key}")
    same_count = len(before["f"]) == len(now["f"])
    moved = not same_count
    if same_count:
        for old, box in zip(before["f"], now["f"], strict=True):
            if (old is None) != (box is None):
                moved = True
            elif old is not None and box is not None:
                deltas.append(_delta(old, box))
                moved = moved or deltas[-1] > MOVE_TOL_PX
    if moved:
        reasons.append("틀")
    if before["pl"] != now["pl"]:
        reasons.append("계획")
    if before["sk"] != now["sk"]:
        reasons.append("원고")
    elif before["tx"] != now["tx"]:
        reasons.append("덮어씀")
    return reasons, (max(deltas, default=0) if same_count else None)


def compare_accepted(
    skeleton: Skeleton,
    content: Mapping[str, Any],
    shots: ShotSet,
    accepted: tuple[dict[str, Any] | None, str],
) -> ChangeReport:
    """지금 촬영을 검수 마친 판(`load_accepted` 의 결과)과 견준다. 모드가 다른 판은 버린다.
    판(`skeleton`)이 달라도 자리 ID 로 그대로 견준다."""
    data = data_places(skeleton)
    compared = compared_places(skeleton.content, shots)
    records = place_geometry(skeleton, content, shots)
    report = ChangeReport(
        order=place_order(skeleton.content),
        data=data,
        compared=compared,
        records={where: records[where] for where in compared if where not in data},
    )
    baseline, problem = accepted
    if baseline is not None and baseline["mode"] != shots.mode:
        baseline, problem = None, "버림 — 모드"
    report.baseline, report.problem = baseline, problem
    if baseline is None:
        return report
    if list(baseline["viewport"]) != list(shots.viewport) or float(baseline["scale"]) != float(
        shots.scale
    ):
        report.whole.append("그림 크기")
    if baseline["rules"] != ACCEPT_RULES:
        report.whole.append("조립 규칙")
    if report.whole:
        return report
    for where in compared:
        if where in data:
            report.changed.append((where, ["데이터 자리"]))
            continue
        before = baseline["places"].get(where)
        if before is None:
            report.changed.append((where, ["새 자리"]))
            continue
        reasons, delta = _place_reasons(before, report.records[where])
        if delta is not None:
            for index, (_label, low, high) in enumerate(WOBBLE_BINS):
                if delta >= low and (high is None or delta <= high):
                    report.wobble[index] += 1
        if reasons:
            report.changed.append((where, reasons))
    return report


def merge_accepted(report: ChangeReport) -> dict[str, dict[str, Any]]:
    """새로 쓸 `places` — 이번에 바뀜 · 새 자리로 찍힌 자리만 지금 값으로 바꾸고, 문턱 안의 자리와
    견주지 않은 자리(예시 · 그림 없음)는 앞 값을 둔다. 데이터 자리와 지금 원고에 없는 자리는 버린다.
    기준이 없거나 버렸거나 모든 자리가 바뀜이면(그림 크기 · 조립 규칙) 지금 값으로 새로 쓴다."""
    if report.baseline is None or report.whole:
        return {where: report.records[where] for where in report.order if where in report.records}
    changed = {where for where, _reasons in report.changed}
    before: Mapping[str, Any] = report.baseline["places"]
    places: dict[str, dict[str, Any]] = {}
    for where in report.order:
        if where in report.data:
            continue
        if where in report.records and (where in changed or where not in before):
            places[where] = report.records[where]
        elif where in before:
            places[where] = before[where]
    return places


def accepted_key_problems(skeleton: Skeleton, document: Mapping[str, Any]) -> list[str]:
    """쓰기 전에 본다 — 자리 키가 지금 원고의 자리이고 데이터 자리가 아니며, 표적 키가 그 자리가
    가리키는 `표적@상태` 인가. 어긋난 키(원고 · 계획 ID)만 돌려준다."""
    known = set(place_order(skeleton.content))
    targets = _place_targets(skeleton.content)
    data = data_places(skeleton)
    problems: list[str] = []
    for where, record in document["places"].items():
        if where not in known or where in data:
            problems.append(where)
        problems += [key for key in record["t"] if key not in targets.get(where, [])]
    return problems


def accepted_record(
    skeleton: Skeleton,
    report: ChangeReport,
    shots: ShotSet,
    *,
    date: str,
    howto: Path = HOWTO_DIR,
) -> dict[str, Any]:
    """새로 쓸 검수 마친 판(봉인까지). 앞 판에서 가져온 자리가 지금 원고와 어긋나면 그 자리를 버린다
    (다음 회차는 `새 자리`). 형식 · 키가 어긋나면 `ValueError` — 쓰지 않는다."""
    places = merge_accepted(report)
    targets = _place_targets(skeleton.content)
    for where in list(places):
        if set(places[where]["t"]) != set(targets.get(where, [])):
            if where in report.records:
                places[where] = report.records[where]
            else:
                del places[where]
    document: dict[str, Any] = {
        "form": ACCEPTED_FORM,
        "rules": ACCEPT_RULES,
        "skeleton": skeleton.version,
        "mode": shots.mode,
        "date": date,
        "viewport": list(shots.viewport),
        "scale": shots.scale,
        "places": places,
    }
    document["seal"] = seal(document)
    if schema_errors(document, "accepted", howto) or accepted_key_problems(skeleton, document):
        raise ValueError(ACCEPTED_FILE)
    return document


def _replace_file(path: Path, data: bytes) -> None:
    """옆 `.tmp` 를 새로 만들어 쓰고 `os.replace` 로 바꾼다. 남은 `.tmp` 는 먼저 걷고 `x`(있으면
    실패 — 연결을 따라가지 않는다)로 만든다 — 앞 실행이 남긴 `.tmp` 가 연결(symlink · 하드 링크)
    이면 그 너머 파일에 쓰게 되기 때문이다. 실패하면 `.tmp` 를 걷고 예외를 그대로 낸다(옛 파일은
    그대로다)."""
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.unlink(missing_ok=True)
        with temporary.open("xb") as handle:
            handle.write(data)
        os.replace(temporary, path)
    except OSError:
        with contextlib.suppress(OSError):
            temporary.unlink(missing_ok=True)
        raise


def save_accepted(path: Path, document: Mapping[str, Any]) -> None:
    """검수 마친 판을 원자적으로 쓴다(`_replace_file` — 옆 `.tmp` 에 쓰고 `os.replace`)."""
    text = json.dumps(document, ensure_ascii=False, indent=1) + "\n"
    _replace_file(path, text.encode("utf-8"))


def assembly_stamp(
    work: Path, content: Mapping[str, Any], plan: Mapping[str, Any]
) -> dict[str, str]:
    """조립 도장 — `shots.json` 바이트 · 덮어쓴 원고 · 계획의 지문. 조립한 뒤 이것들이 바뀌었으면
    `--accept` 가 거절한다(검수한 것이 조립한 것이 아니다)."""
    shots_digest = hashlib.sha256((work / SHOTS_FILE).read_bytes()).hexdigest()[:12]
    return {"shots": shots_digest, "content": _fingerprint(content), "plan": _fingerprint(plan)}


def save_assembly_stamp(work: Path, stamp: Mapping[str, str]) -> None:
    """조립 도장을 쓴다. 옛 도장을 먼저 걷는다 — 쓰다 실패해도 옛 도장이 남아 맞아 보이지 않게."""
    path = work / ASSEMBLED_FILE
    path.unlink(missing_ok=True)
    _replace_file(path, (json.dumps(dict(stamp), ensure_ascii=False) + "\n").encode("utf-8"))


def load_assembly_stamp(work: Path) -> dict[str, str] | None:
    """조립 도장 — 없거나 꼴이 아니면 None(`조립 기록 없음`)."""
    try:
        stamp = load_json(work / ASSEMBLED_FILE)
    except (OSError, ValueError):
        return None
    if not isinstance(stamp, dict) or set(stamp) != {"shots", "content", "plan"}:
        return None
    if not all(isinstance(value, str) for value in stamp.values()):
        return None
    return {str(key): str(value) for key, value in stamp.items()}
