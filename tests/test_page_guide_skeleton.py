# Purpose: 따라하기 가이드 뼈대(원고 · 계획 · 형식 · 틀 · ID 장부)가 서로와 앱 글자에 맞는지 잰다.

"""따라하기 가이드 뼈대 — `src/capa_simulation/guides/howto/`.

뼈대는 사외 정본이고, 사내는 그 위에 글 덮어쓰기(`review/guide/overrides.json`)와 매개값
(`review/guide/params.json`)만 얹는다. 사내가 고칠 수 없는 것은 여기서 사외가 막는다.

- 형식: 원고 · 계획이 `schema/*.json`(JSON Schema 2020-12)에 맞고, 사내 두 파일 형식도 잰다.
- ID: 겹치지 않고, 단계가 가리키는 상태 · 표적이 계획에 있다(`from` 으로 빌린 자리 포함).
- 낱말: 동작 · 표적은 정해진 낱말만 쓴다 — 생성기가 구현하는 목록과 계획 형식의 목록이 같다.
- 앱 글자: 원고의 [[버튼]] · ((메뉴)) · {{배지}} · 「인용」과 계획의 표적 글자가 앱 소스에 있다.
  앱 글자를 바꾸면 여기서 깨진다 — 원고나 계획을 같은 변경에서 고친다.
- 장부: 한 번 쓴 ID 는 사라지지 않는다(사내 덮어쓰기가 그 ID 에 붙는다). 빼려면 `retired` 로 옮긴다.

`jsonschema` 는 `altair`(직접 의존)가 끌고 오는 전이 의존이라 개발 · 사내 가상환경에 늘 있다.
py.typed 가 없어 mypy 에는 타입 없는 모듈로 들인다.
"""

from __future__ import annotations

import ast
import functools
import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import jsonschema  # type: ignore[import-untyped]
import pytest

from capa_simulation import settings

PROJECT_ROOT = Path(__file__).resolve().parents[1]
HOWTO = PROJECT_ROOT / "src" / "capa_simulation" / "guides" / "howto"
SCHEMA_DIR = HOWTO / "schema"
LOB = HOWTO / "lob"
SCHEMAS = ("content", "plan", "overrides", "params")

WRITES = ("none", "session", "db", "shared")
OPS = frozenset(
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
TARGET_KINDS = frozenset({"key", "button", "tab", "nav", "text", "named"})
# 코드로 찾는 표적 — 이름 → 괄호 안 글자를 받는지. 생성기가 이 목록을 그대로 구현한다.
NAMED_TARGETS: dict[str, bool] = {
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
# 사내 1단계(`db` · `shared` 상태는 건너뛴다)가 찍을 수 있는 상태 — handoff §4-4 의 18상태.
INTERNAL_FIRST_PASS = frozenset(
    {
        "01_home_main",
        "02_home_lower",
        "03_process_detail",
        "03b_process_detail_lower",
        "04_procfilter_open",
        "05_lobcond_open",
        "06_home_pref",
        "07_sidebar_static_open",
        "08_ref_avail",
        "09_ref_edited",
        "10_ref_applied",
        "11_home_after_apply",
        "12_loadconv_pkgplan",
        "13_scenario_popup_save",
        "15_scenmgmt_list",
        "16_scenmgmt_selected",
        "17_official_dialog",
        "19_scenario_popup_load",
    }
)
# 사내판에서도 합성 예시 그림으로 남는 자리. `set_official.nav` 는 HOME 첫 화면으로 옮겨 사내 화면이
# 된다.
EXAMPLE_ONLY = frozenset(
    {
        "step:save_revision.badge",
        "step:set_official.check",
        "step:gap.pick_compare",
        "thumb:gap",
    }
)

# 「인용」 안의 자리표시 — 앱이 실제 값(번호 · 이름 · 조사)으로 채우는 곳.
PLACEHOLDER = re.compile(
    r"…|\.\.\.|을\(를\)|[XY]%|시나리오명|공식버전명|(?<![A-Za-z/])[rv]?[NMn](?![A-Za-z/])"
)
# 앱이 여러 글 조각을 이어 만드는 인용 — 조각마다 앱 소스에 있어야 한다.
SPANS: dict[str, tuple[str, ...]] = {
    "RQ_EQP_AVBL 편집값을 활성 시나리오에 적용했습니다.": (
        "RQ_EQP_AVBL",
        "편집값을",
        " 활성 시나리오에 적용했습니다.",
    ),
}
# 표적 · 동작 글자 가운데 앱 글자와 **똑같아야** 하는 것(나머지는 아이콘 · 꾸밈이 붙어 포함만 본다).
EXACT_WORDS = frozenset(
    {"button", "nav", "fill", "section", "WIDGET", "FORM_OF", "GRID_COLUMN", "MAIN_LINK", "column"}
)


def _load(path: Path) -> Any:
    """JSON 을 읽는다. 같은 키가 두 번 나오면 실패한다 — `json` 은 뒤 값으로 조용히 덮는다."""

    def no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        keys = [key for key, _ in pairs]
        repeated = sorted({key for key in keys if keys.count(key) > 1})
        if repeated:
            raise ValueError(f"{path.name}: 같은 키가 두 번 나옵니다 — {repeated}")
        return dict(pairs)

    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=no_duplicates)


def _content() -> Any:
    return _load(LOB / "content.json")


def _plan() -> Any:
    return _load(LOB / "plan.json")


def _schema_errors(document: Any, schema_name: str) -> list[str]:
    schema = _load(SCHEMA_DIR / f"{schema_name}.schema.json")
    validator = jsonschema.Draft202012Validator(schema)
    return sorted(
        f"{'/'.join(str(part) for part in error.absolute_path) or '(뿌리)'}: {error.message}"
        for error in validator.iter_errors(document)
    )


def _strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


def _target_words(value: Any) -> Iterator[str]:
    if isinstance(value, list):
        yield from value
    else:
        yield value


def _plan_target_words(plan: Any) -> Iterator[tuple[str, str]]:
    """(자리, 표적 낱말) — 상태의 표적 · 동작이 가리키는 표적 · 가림."""
    for word in plan["mask"]:
        yield "mask", word
    for state in plan["states"]:
        for name, value in state["targets"].items():
            for word in _target_words(value):
                yield f"{name}@{state['id']}", word
        for index, op in enumerate(state["ops"]):
            for field in ("target", "grid"):
                if field in op:
                    for word in _target_words(op[field]):
                        yield f"{state['id']}.ops.{index}.{field}", word


def _split_target(word: str) -> tuple[str, str, str | None]:
    """`종류:글자` → (종류, 이름 또는 글자, 괄호 안 글자)."""
    kind, _, rest = word.partition(":")
    if kind != "named":
        return kind, rest, None
    matched = re.fullmatch(r"(?P<name>[A-Z][A-Z0-9_]*)(?:\((?P<arg>.+)\))?", rest)
    assert matched, f"named 표적 꼴이 아닙니다: {word}"
    return kind, matched["name"], matched["arg"]


def _param_refs(value: Any) -> Iterator[dict[str, Any]]:
    if isinstance(value, dict):
        if "param" in value:
            yield value
        else:
            for item in value.values():
                yield from _param_refs(item)
    elif isinstance(value, list):
        for item in value:
            yield from _param_refs(item)


def _chains(plan: Any) -> dict[str, list[str]]:
    """상태 → 뿌리부터 그 상태까지의 사슬."""
    by_id = {state["id"]: state for state in plan["states"]}
    chains: dict[str, list[str]] = {}
    for state_id in by_id:
        chain = [state_id]
        while "from" in by_id[chain[0]]:
            chain.insert(0, by_id[chain[0]]["from"])
        chains[state_id] = chain
    return chains


def _internally_capturable(plan: Any) -> set[str]:
    writes = {state["id"]: state["writes"] for state in plan["states"]}
    return {
        state_id
        for state_id, chain in _chains(plan).items()
        if all(writes[link] in ("none", "session") for link in chain)
    }


def _content_state_refs(content: Any) -> Iterator[tuple[str, str, str]]:
    """(자리, 상태, 표적) — 원고가 그림 · 상자로 가리키는 모든 곳. `from` 은 빌려 온 상태로 낸다."""
    for task in content["tasks"]:
        thumb = task["thumb"]
        for target in thumb["targets"]:
            yield f"thumb:{task['id']}", thumb["state"], target
        if "map" in task:
            board = task["map"]
            for target in board["frame"]:
                yield f"map:{task['id']}", board["state"], target
            for spot in board["spots"]:
                yield f"map:{task['id']}", board["state"], spot["t"]
        for step in task.get("steps", []):
            for focus in step["focus"]:
                yield (
                    f"step:{task['id']}.{step['id']}",
                    focus.get("from", step["state"]),
                    focus["t"],
                )
    for concept in content["concepts"]:
        for spot in concept.get("spots", []):
            yield f"concept:{concept['id']}", spot["state"], spot["t"]


def _current_ids(content: Any, plan: Any) -> list[str]:
    ids = [f"group:{group[0]}" for group in content["groups"]]
    for task in content["tasks"]:
        ids.append(f"task:{task['id']}")
        ids += [f"step:{task['id']}.{step['id']}" for step in task.get("steps", [])]
        ids += [
            f"spot:{task['id']}.spot.{spot['t']}" for spot in task.get("map", {}).get("spots", [])
        ]
    ids += [f"concept:{concept['id']}" for concept in content["concepts"]]
    for state in plan["states"]:
        ids.append(f"state:{state['id']}")
        ids += [f"target:{name}@{state['id']}" for name in state["targets"]]
    ids += [f"param:{name}" for name in plan["params"]]
    return ids


@functools.cache
def _app_strings() -> frozenset[str]:
    """앱 소스(app.py · app_pages · src/capa_simulation)의 모든 문자열 상수(f-string 조각 포함)."""
    sources = [
        PROJECT_ROOT / "app.py",
        *sorted((PROJECT_ROOT / "app_pages").glob("*.py")),
        *sorted((PROJECT_ROOT / "src" / "capa_simulation").rglob("*.py")),
    ]
    found: set[str] = set()
    for path in sources:
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"), filename=str(path))):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                found.add(node.value)
    return frozenset(found)


@functools.cache
def _app_text_blob() -> str:
    return "\x00".join(sorted(_app_strings()))


def _in_app(text: str) -> bool:
    """`text` 가 앱 문자열 상수 **하나** 안에 들어 있다."""
    return text in _app_text_blob()


def _key_in_app(key: str) -> bool:
    """`st-key` 이름 — 상수 그대로이거나 상수 둘을 이은 것(`f"condition_field_{name}"`)."""
    strings = _app_strings()
    return key in strings or any(
        key[:cut] in strings and key[cut:] in strings for cut in range(1, len(key))
    )


# ------------------------------------------------------------------ 형식


@pytest.mark.parametrize("name", SCHEMAS)
def test_every_skeleton_schema_is_a_valid_json_schema(name: str) -> None:
    schema = _load(SCHEMA_DIR / f"{name}.schema.json")

    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    jsonschema.Draft202012Validator.check_schema(schema)


def test_content_matches_its_schema() -> None:
    assert _schema_errors(_content(), "content") == []


def test_plan_matches_its_schema() -> None:
    assert _schema_errors(_plan(), "plan") == []


def test_content_and_plan_carry_one_skeleton_version() -> None:
    content, plan = _content(), _plan()

    assert content["version"] == plan["version"]
    assert re.fullmatch(r"lob@\d{4}-\d{2}-\d{2}", content["version"])
    assert content["page"] == plan["page"]


HANDOFF_OVERRIDES: dict[str, Any] = {
    "skeleton": "lob@2026-10-22",
    "text": {
        "change_avail.edit_cell.do": "사내 표에서는 칸을 고르고 바로 숫자를 칩니다.",
        "change_avail.apply.stuck.0": "적용 버튼이 흐리면 먼저 칸에서 Enter 를 누르세요.",
        "lob_map.spot.lob_wafer_capa.what": "Wafer 계획 × B/N 공정 확보율",
        "concept.read_state.title": "상태는 네 자리에서 읽습니다",
    },
    "add": {"change_avail.apply.stuck": ["사내에서 자주 묻는 것 — 확보율 < 100 이면 빨강"]},
    "hide": ["change_plan.apply.stuck.1"],
}


def test_override_schema_accepts_the_handoff_shape() -> None:
    assert _schema_errors(HANDOFF_OVERRIDES, "overrides") == []


@pytest.mark.parametrize(
    "change",
    [
        {"text": {"change_avail.apply.do": "<b>굵게</b> 누릅니다"}},
        {"text": {"change_avail.apply.do": "<img src=x onerror=alert(1)>"}},
        {"text": {"change_avail.apply.ok": "JavaScript:alert(1)"}},
        {"text": {"change_avail.apply.state": "09_ref_edited"}},
        {"text": {"change_avail.apply.focus.0.n": "3"}},
        {"text": {"change_avail.id": "other"}},
        {"text": {"change_avail.apply.do": ""}},
        {"add": {"change_avail.apply.do": ["덧붙임"]}},
        {"hide": ["change_avail.apply"]},
        {"steps": []},
        {"skeleton": "lob-2026-10-22"},
    ],
)
def test_override_schema_rejects_markup_structure_and_ids(change: dict[str, Any]) -> None:
    document = {**HANDOFF_OVERRIDES, **change}

    assert _schema_errors(document, "overrides")


def test_param_schema_accepts_plain_names_and_numbers() -> None:
    document = {
        "skeleton": "lob@2026-10-22",
        "values": {"edit_process": "Pre B/D", "edit_month": "202612", "edit_delta": 2},
    }

    assert _schema_errors(document, "params") == []


@pytest.mark.parametrize(
    "value",
    [{"expr": "1+1"}, ["a", "b"], 1.5, True, "", "두 줄\n글", "<script>", "${env}", "`id`"],
)
def test_param_schema_rejects_code_lists_and_markup(value: Any) -> None:
    document = {"skeleton": "lob@2026-10-22", "values": {"edit_process": value}}

    assert _schema_errors(document, "params")


# ------------------------------------------------------------------ ID 와 참조


def test_skeleton_ids_do_not_repeat() -> None:
    content, plan = _content(), _plan()
    task_ids = [task["id"] for task in content["tasks"]]
    group_ids = [group[0] for group in content["groups"]]
    concept_ids = [concept["id"] for concept in content["concepts"]]
    state_ids = [state["id"] for state in plan["states"]]

    for label, ids in (
        ("과업", task_ids),
        ("묶음", group_ids),
        ("개념", concept_ids),
        ("상태", state_ids),
    ):
        assert len(ids) == len(set(ids)), f"{label} ID 가 겹칩니다: {ids}"
    for task in content["tasks"]:
        step_ids = [step["id"] for step in task.get("steps", [])]
        assert len(step_ids) == len(set(step_ids)), f"{task['id']} 의 단계 ID 가 겹칩니다"
        # 덮어쓰기 주소 `과업.spot.<표적>.칸` · `과업.단계.stuck.<번호>` 와 헷갈리지 않게
        assert not {"spot", "stuck"} & set(step_ids), task["id"]
    # 덮어쓰기 주소 `concept.<id>.…` 와 헷갈리지 않게
    assert "concept" not in task_ids


def test_every_picture_reference_points_at_a_planned_state_and_target() -> None:
    content, plan = _content(), _plan()
    planned = {state["id"]: set(state["targets"]) for state in plan["states"]}

    missing = [
        f"{where} → {target}@{state}"
        for where, state, target in _content_state_refs(content)
        if target not in planned.get(state, set())
    ]
    step_states = [
        f"step:{task['id']}.{step['id']} → {step['state']}"
        for task in content["tasks"]
        for step in task.get("steps", [])
        if step["state"] not in planned
    ]

    assert not missing, "계획에 없는 표적을 가리킵니다:\n" + "\n".join(missing)
    assert not step_states, "계획에 없는 상태를 가리킵니다:\n" + "\n".join(step_states)


def test_every_task_link_points_at_an_existing_task_or_group() -> None:
    content = _content()
    task_ids = {task["id"] for task in content["tasks"]}
    group_ids = {group[0] for group in content["groups"]}

    links = [pick["go"] for pick in content["state_pick"]]
    for task in content["tasks"]:
        assert task["group"] in group_ids, task["id"]
        links += task.get("next", [])
        if "map" in task:
            links += [spot["go"] for spot in task["map"]["spots"]]
            links.append(task["map"]["color"]["go"])
    for targets in content["synonyms"].values():
        links += targets

    assert set(links) <= task_ids, sorted(set(links) - task_ids)


def test_state_writes_use_the_four_grades() -> None:
    grades = [state["writes"] for state in _plan()["states"]]

    assert set(grades) <= set(WRITES), grades
    assert {"none", "session", "db", "shared"} == set(grades)


def test_states_form_a_tree_from_one_entry() -> None:
    states = _plan()["states"]
    seen: list[str] = []

    for index, state in enumerate(states):
        uses_entry = any(op["op"] == "enter_app" for op in state["ops"])
        if index == 0:
            assert "from" not in state and state["ops"][0]["op"] == "enter_app"
        else:
            # 앞 상태는 계획에서 먼저 나온다 — 생성기가 계획 차례대로 돌며 사슬을 다시 열 수 있게
            assert state.get("from") in seen, state["id"]
            assert not uses_entry, state["id"]
        seen.append(state["id"])


def test_internal_first_pass_reaches_the_eighteen_read_only_states() -> None:
    """사내 1단계는 `db` · `shared` 를 건너뛴다 — 그 앞을 지나는 상태는 사내 화면이 될 수 없다."""
    plan = _plan()

    assert _internally_capturable(plan) == INTERNAL_FIRST_PASS


def test_only_the_agreed_spots_stay_as_example_pictures() -> None:
    content, plan = _content(), _plan()
    capturable = _internally_capturable(plan)

    example_only = {
        where for where, state, _target in _content_state_refs(content) if state not in capturable
    }
    example_only |= {
        f"step:{task['id']}.{step['id']}"
        for task in content["tasks"]
        for step in task.get("steps", [])
        if step["state"] not in capturable
    }

    assert example_only == EXAMPLE_ONLY


def test_params_are_declared_used_and_keep_one_default() -> None:
    plan = _plan()
    declared = plan["params"]
    refs = list(_param_refs(plan["states"]))

    for ref in refs:
        name = ref["param"]
        assert name in declared, f"선언하지 않은 매개값: {name}"
        assert ref["default"] == declared[name]["default"], name
    for name, spec in declared.items():
        expected = int if spec["type"] == "int" else str
        assert type(spec["default"]) is expected, name
        if spec["type"] == "choice":
            assert spec["default"] in spec["choices"], name
    assert {ref["param"] for ref in refs} == set(declared)


# ------------------------------------------------------------------ 정해진 낱말


def test_ops_and_targets_use_only_the_fixed_words() -> None:
    plan = _plan()

    used_ops = {op["op"] for state in plan["states"] for op in state["ops"]}
    assert used_ops <= OPS, sorted(used_ops - OPS)

    wrong = []
    for where, word in _plan_target_words(plan):
        kind, name, arg = _split_target(word)
        if kind not in TARGET_KINDS:
            wrong.append(f"{where}: 모르는 종류 {word}")
        elif kind == "named" and name not in NAMED_TARGETS:
            wrong.append(f"{where}: 모르는 이름 {word}")
        elif kind == "named" and NAMED_TARGETS[name] != (arg is not None):
            wrong.append(f"{where}: 괄호 글자 {'빠짐' if arg is None else '남음'} {word}")
    assert not wrong, "\n".join(wrong)


def test_plan_schema_lists_the_same_words_as_the_generator_table() -> None:
    """계획 형식의 낱말 목록과 이 시험의 목록이 같다 — 한쪽만 늘리면 점검과 생성기가 갈라진다."""
    schema = _load(SCHEMA_DIR / "plan.schema.json")
    defs = schema["$defs"]

    schema_ops = {variant["properties"]["op"]["const"] for variant in defs["op"]["oneOf"]}
    pattern = defs["target_word"]["pattern"]
    plain, with_arg = re.findall(r"named:\(\?:([A-Z0-9_|]+)\)", pattern)

    assert schema_ops == OPS
    assert set(plain.split("|")) == {name for name, arg in NAMED_TARGETS.items() if not arg}
    assert set(with_arg.split("|")) == {name for name, arg in NAMED_TARGETS.items() if arg}
    assert f"named:(?:{with_arg})\\(.+\\)" in pattern


# ------------------------------------------------------------------ 앱 글자


def test_button_labels_in_the_script_are_app_labels() -> None:
    """[[버튼 · 탭 · 입력칸 이름]] 은 앱 소스의 글자 그대로다."""
    labels = {
        label for text in _strings(_content()) for label in re.findall(r"\[\[(.+?)\]\]", text)
    }

    assert labels
    assert sorted(label for label in labels if label not in _app_strings()) == []


def test_menu_and_badge_chips_in_the_script_appear_in_the_app() -> None:
    """((메뉴)) · {{배지}} 는 앱 글자 안에 있다(아이콘이 붙은 탭 이름 · 번호 자리표시는 뺀다)."""
    chips = set()
    for text in _strings(_content()):
        chips |= set(re.findall(r"\(\((.+?)\)\)", text))
        chips |= {
            fragment.strip()
            for badge in re.findall(r"\{\{(.+?)\}\}", text)
            for fragment in PLACEHOLDER.split(badge)
            if fragment.strip()
        }

    assert chips
    assert sorted(chip for chip in chips if not _in_app(chip)) == []


def test_quoted_app_phrases_in_the_script_appear_in_the_app() -> None:
    """「인용」은 앱이 띄우는 글이다 — 성공 · 오류 문구나 칸 이름이 앱에서 바뀌면 여기서 깨진다.

    가이드 자기 이름(과업 묶음 · 과업 제목)을 가리키는 인용은 앱 글자가 아니라서 뺀다.
    """
    content = _content()
    own_names = {group[1] for group in content["groups"]} | {
        task["title"] for task in content["tasks"]
    }
    missing = []
    used_spans = set()
    for text in _strings(content):
        for quote in re.findall(r"「(.+?)」", text):
            for fragment in (part.strip() for part in PLACEHOLDER.split(quote)):
                if len(fragment) < 2 or fragment in own_names or _in_app(fragment):
                    continue
                if fragment in SPANS:
                    used_spans.add(fragment)
                    missing += [
                        f"{quote} ← {piece!r}" for piece in SPANS[fragment] if not _in_app(piece)
                    ]
                else:
                    missing.append(f"{quote} ← {fragment!r}")

    assert not missing, "앱에 없는 인용입니다:\n" + "\n".join(missing)
    assert used_spans == set(SPANS), "쓰이지 않는 SPANS 항목은 지웁니다"


def test_plan_target_and_action_words_are_app_words() -> None:
    plan = _plan()
    words: list[tuple[str, str]] = []
    for _where, word in _plan_target_words(plan):
        kind, name, arg = _split_target(word)
        if kind == "named":
            if arg is not None:
                words.append((name, arg))
        else:
            words.append((kind, name))
    for state in plan["states"]:
        for op in state["ops"]:
            if op["op"] in ("nav", "tab"):
                words.append((op["op"], op["text"]))
            elif op["op"] == "fill":
                words.append(("fill", op["label"]))
            elif op["op"] == "open_popup" and "section" in op:
                words.append(("section", op["section"]))
            elif op["op"] == "grid_edit":
                words += [
                    (field, op[field])
                    for field in ("column", "row_column")
                    if isinstance(op.get(field), str)
                ]

    missing = []
    for kind, text in sorted(set(words)):
        if kind in ("key", "EXPANDER", "KEY_BUTTON"):
            found = _key_in_app(text)
        elif kind in EXACT_WORDS:
            found = text in _app_strings()
        else:
            found = _in_app(text)
        if not found:
            missing.append(f"{kind}:{text}")

    assert not missing, "앱에 없는 표적 · 동작 글자입니다:\n" + "\n".join(missing)


# ------------------------------------------------------------------ 장부 · 틀 · 위생


def test_stable_ids_never_disappear() -> None:
    """한 번 쓴 ID 는 장부에서 지우지 않는다. 더하면 `active` 에, 빼면 `retired` 로 옮긴다."""
    ledger = _load(LOB / "ids.json")
    active, retired = ledger["active"], ledger["retired"]
    current = _current_ids(_content(), _plan())

    assert len(current) == len(set(current))
    assert active == sorted(set(active)), "장부 active 는 겹침 없이 정렬해 둡니다"
    gone = sorted(set(active) - set(current))
    new = sorted(set(current) - set(active))
    reused = sorted(set(current) & set(retired))
    assert not gone, "원고 · 계획에서 사라진 ID 입니다(빼려면 retired 로 옮깁니다):\n" + "\n".join(
        gone
    )
    assert not new, "장부에 없는 새 ID 입니다(active 에 더합니다):\n" + "\n".join(new)
    assert not reused, "물러난 ID 를 다시 썼습니다:\n" + "\n".join(reused)
    assert not set(active) & set(retired)


def test_template_has_one_data_slot_and_no_outside_references() -> None:
    html = (HOWTO / "template.html").read_text(encoding="utf-8")

    assert html.count("/*__DATA__*/null") == 1
    assert "\r" not in html
    assert not re.findall(r"""(?:src|href)\s*=\s*["']?\s*(?:https?:)?//""", html)
    assert not re.findall(r"""url\(\s*["']?\s*(?:https?:)?//""", html)
    assert not re.findall(r"""@import""", html)


def test_skeleton_carries_no_owner_or_contact_values() -> None:
    """뼈대는 공개 저장소에 실린다 — 담당 조직 · 문의처는 생성기가 settings 에서 읽어 가린다."""
    files = [*sorted(HOWTO.rglob("*.json")), HOWTO / "template.html"]
    texts = {path.name: path.read_text(encoding="utf-8") for path in files}

    for name, text in texts.items():
        assert settings.APP_OWNER_TEAM not in text, name
        assert settings.APP_CONTACT_EMAIL not in text, name
        assert not re.findall(r"[\w.+-]+@[\w-]+\.[A-Za-z]{2,}", text), name
