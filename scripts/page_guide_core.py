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

화면 글자는 여기서 다루지 않는다 — 좌표와 상태 ID · 표적 이름만 다룬다.
"""

from __future__ import annotations

import base64
import copy
import io
import json
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

import jsonschema  # type: ignore[import-untyped]
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]
HOWTO_DIR: Final = PROJECT_ROOT / "src" / "capa_simulation" / "guides" / "howto"
SCHEMA_NAMES: Final = ("content", "plan", "overrides", "params")
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
INTERNAL_LABEL: Final = "사내 화면 · {date}"

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
    """촬영 결과를 잘라 원고와 묶는다(시안 build_guide.py 의 규칙)."""

    def __init__(self, shots: ShotSet) -> None:
        self.shots = shots
        self.images: dict[str, str] = {}
        self._pictures: dict[str, Image.Image] = {}
        self.report = AssemblyReport()
        self.whole: list[int] = [0, 0, shots.viewport[0], shots.viewport[1]]

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

    def _put(self, key: str, picture: Image.Image, quality: int, state_id: str) -> dict[str, str]:
        if key not in self.images:
            buffer = io.BytesIO()
            picture.save(buffer, "WEBP", quality=quality, method=6)
            encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
            self.images[key] = "data:image/webp;base64," + encoded
        return {"src": key, "cap": self._label(state_id)}

    def full(self, state_id: str) -> dict[str, str]:
        picture = self._picture(state_id)
        height = round(picture.height * FULL_W / picture.width)
        resized = picture.resize((FULL_W, height), Image.Resampling.LANCZOS)
        return self._put("full:" + state_id, resized, FULL_QUALITY, state_id)

    def crop(
        self,
        state_id: str,
        frame: Sequence[int],
        *,
        width: int = CROP_MAX,
        quality: int = CROP_QUALITY,
    ) -> dict[str, str]:
        scale = self.shots.states[state_id].scale
        box = (
            round(frame[0] * scale),
            round(frame[1] * scale),
            round((frame[0] + frame[2]) * scale),
            round((frame[1] + frame[3]) * scale),
        )
        cut = self._picture(state_id).crop(box)
        out_w = min(width, cut.width)
        resized = cut.resize(
            (out_w, max(1, round(cut.height * out_w / cut.width))), Image.Resampling.LANCZOS
        )
        key = f"crop:{state_id}:{','.join(map(str, frame))}:{width}"
        return self._put(key, resized, quality, state_id)

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
                    thumb["state"], frame, width=THUMB_WIDTH, quality=THUMB_QUALITY
                )
                self._note_picture(f"thumb:{task['id']}", thumb["state"])
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
            return out
        out["crop"] = self.crop(state_id, frame)
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
                    {"crop": self.crop(state_id, one), "boxes": self.boxes(state_id, [item], one)}
                )
            out["crops"] = crops
        else:
            if frame[2] > clip_w and len(framed) <= 1:
                frame = [frame[0], frame[1], clip_w, frame[3]]
            out["crop"] = self.crop(state_id, frame)
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
        spots: list[dict[str, Any]] = []
        for spot in concept["spots"]:
            item = dict(spot)
            state_id = spot["state"]
            if self.shots.ok(state_id) and self.target(state_id, spot["t"]):
                frame = self.rect(
                    state_id, [spot["t"]], pad=SPOT_PAD, min_w=SPOT_MIN[0], min_h=SPOT_MIN[1]
                )
                assert frame is not None
                item["crop"] = self.crop(state_id, frame, width=SPOT_WIDTH)
                number = len(spots) + 1
                item["boxes"] = self.boxes(
                    state_id, [{"t": spot["t"], "n": number, "kind": "see"}], frame
                )
                item["full"] = self.full(state_id)
                item["fullBoxes"] = self.boxes(
                    state_id, [{"t": spot["t"], "kind": "see"}], self.whole
                )
                self._note_picture(f"concept:{concept['id']}", state_id)
            else:
                self.report.no_picture.append(f"concept:{concept['id']}.{spot['t']}")
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


def review_line(
    skeleton: Skeleton,
    shots: ShotSet | None,
    run: RunFacts | None,
    overrides: OverrideReport,
    params: ParamReport | None = None,
    *,
    example_count: int = 0,
) -> str:
    """리뷰 md 에 옮길 한 줄(handoff §6 의 압축 꼴). ID · 수 · 고정 글자만 담는다.

    `가이드 lob@1022 상태 18/18; 표적 n/N ok|ng <표적@상태>; 고아 0; 덮어씀 n; 예시 4; DB 변화 없음`
    """
    head = f"가이드 {compact_version(skeleton.version)}"
    stale = []
    if overrides.skeleton is not None and not overrides.version_matches:
        stale.append(f"덮어쓰기 {compact_version(overrides.skeleton)}")
    if params is not None and params.skeleton is not None and not params.version_matches:
        stale.append(f"매개값 {compact_version(params.skeleton)}")
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


def review_for_work(
    skeleton: Skeleton,
    content: Mapping[str, Any],
    work: Path,
    overrides: OverrideReport,
    params: ParamReport | None,
) -> tuple[str, list[str]]:
    """작업 폴더로 리뷰 한 줄과 자세한 목록(못 찾은 표적 · 고아 주소)을 낸다 — 생성기 끝과
    점검기가 같은 길을 쓴다."""
    shots, run = board_shots(skeleton, work)
    examples = example_spots(content, shots)
    line = review_line(skeleton, shots, run, overrides, params, example_count=len(examples))
    _, _, missing = target_tally(skeleton, shots, expected_states(skeleton, run))
    details = [f"못 찾은 표적 {item}" for item in missing]
    details += [f"고아 {address}" for address in overrides.orphans]
    details += [f"예시 {where}" for where in sorted(examples)]
    details += [f"남은 상태 {state_id}" for state_id in run.left]
    return line, details
