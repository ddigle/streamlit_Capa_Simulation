# Purpose: 화면 설계 · 검수 규칙 문서(docs/design_rules.md)의 꼴과 진입 문서 연결을 지킨다.

"""화면 설계 · 검수 규칙(`docs/design_rules.md`)의 꼴.

규칙집은 설계 · 검수가 규칙 id 로 대 보는 정본이다(PRC-07). 꼴이 흐트러지면
id 로 찾을 수 없고, 답한 물음이 「제안」 으로 남거나 결정 기록이 빠지면 같은 것을
다시 묻게 된다(PRC-02). 여기서는 글의 뜻이 아니라 꼴을 본다 — id 꼴 · 겹침 · 묶음
자리 · 칸 · 수준 · 판단 질문 · 상태 · 머리의 수 · 결정 기록 18줄과 답 · 반영 검수표 8줄과
답 · 그림 검수표 메모 9줄 · 문서 안팎의 id 참조 · 그물 경로 · 진입 문서(AGENTS · CLAUDE.md ·
README)의 연결.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RULES_LINK = "docs/design_rules.md"
RULES_PATH = PROJECT_ROOT / RULES_LINK

GROUPS = (
    "UI-TXT",
    "UI-NTF",
    "UI-LAY",
    "UI-INP",
    "UI-PRF",
    "UI-CON",
    "UI-DAT",
    "UI-NAV",
    "UI-STA",
    "UI-ACC",
    "PRC",
)
RULE_ID = re.compile(r"^(?:UI-(?:TXT|NTF|LAY|INP|PRF|CON|DAT|NAV|STA|ACC)|PRC)-\d{2}$")
RULE_TOKEN = re.compile(r"\b(?:UI-[A-Z]{3}|PRC)-\d{2}\b")
QUESTION_TOKEN = re.compile(r"\bAMB-\d{2}\b")
LEVELS = ("MUST", "SHOULD", "MAY")
FIELDS = ("수준", "범위", "예외", "판단", "그물", "그물 후보", "근거", "지금 값")
# 2026-11-04 설계 규칙 확인 보드의 사용자 답 — 05 · 06 만 (나), 나머지 열여섯은 (가) 권장이다.
ANSWERS = {
    **{f"AMB-{n:02d}": "가" for n in (1, 2, 7, 8, 9, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21)},
    "AMB-05": "나",
    "AMB-06": "나",
}
# 합치거나 재료에 답이 있어 묻지 않은 물음(7-2) — 결정 기록 줄은 없고 참고 절에만 선다.
CLOSED_QUESTIONS = {"AMB-03", "AMB-04", "AMB-10"}
# 2026-11-04 설계 규칙 반영 검수표(6-2)의 사용자 답 — D1 만 (나), 나머지 일곱은 (가) 권장이다.
REVIEW_ANSWERS = {**{f"D{n}": "가" for n in range(2, 9)}, "D1": "나"}
# 2026-11-05 그림 검수표(6-3)의 메모 칸 — 고른 답이 아니라 메모라 칸 이름만 맞댄다.
PICTURE_MEMOS = {
    "static-12",
    "static-32",
    "static-35",
    "static-37",
    "equip-13",
    "equip-41",
    "equip-44",
    "equip-60",
    "equip-61",
    "eqp-side-01",
}
# 이 문서의 규칙 id 를 부를 수 있는 진입 · 짝 문서.
CITING_DOCUMENTS = (
    "AGENTS.md",
    "CLAUDE.md",
    "README.md",
    "docs/TODO.md",
    "docs/design_system.md",
    "docs/module_guide.md",
)

_FENCE = re.compile(r"^[ ]*```.*?^[ ]*```[ ]*$", re.S | re.M)
_RULE_HEAD = re.compile(r"^#### (\S+) · (.+)$")
_GROUP_HEAD = re.compile(r"^### 3-\d+\. (\S+) — ")
_FIELD = re.compile(r"^- ([^:]+): (.*)$")


@dataclass(frozen=True)
class Rule:
    id: str
    group: str
    title: str
    text: str
    fields: dict[str, list[str]]


@dataclass
class _Draft:
    id: str
    group: str
    title: str
    text: list[str] = field(default_factory=list)
    fields: dict[str, list[str]] = field(default_factory=dict)


def _text() -> str:
    """코드 블록을 걷은 본문 — 블록 안의 `#` · `-` 줄은 머리 · 칸이 아니다."""
    return _FENCE.sub("", RULES_PATH.read_text(encoding="utf-8"))


def _chapter(text: str, number: int) -> str:
    """`## <number>. ` 머리부터 다음 `## ` 머리 앞까지."""
    start = text.index(f"\n## {number}. ")
    following = text.find("\n## ", start + 1)
    return text[start : following if following != -1 else len(text)]


def _rules() -> list[Rule]:
    """3장의 규칙 블록 — 묶음 머리(### 3-n.) 아래 `#### <id> · <이름>`,
    규칙 글 문단, `- 칸: 값` 줄."""
    drafts: list[_Draft] = []
    current: _Draft | None = None
    group = ""
    for line in _chapter(_text(), 3).splitlines():
        if match := _GROUP_HEAD.match(line):
            group, current = match.group(1), None
        elif match := _RULE_HEAD.match(line):
            current = _Draft(match.group(1), group, match.group(2))
            drafts.append(current)
        elif current is not None and (item := _FIELD.match(line)):
            current.fields.setdefault(item.group(1), []).append(item.group(2).strip())
        elif current is not None and line.strip():
            current.text.append(line.strip())
    return [Rule(d.id, d.group, d.title, " ".join(d.text), d.fields) for d in drafts]


def _level_and_state(rule: Rule) -> tuple[str, str]:
    level, _, state = rule.fields["수준"][0].partition(" · ")
    return level.strip(), state.strip()


def test_rule_ids_have_the_shape_and_do_not_repeat() -> None:
    ids = [rule.id for rule in _rules()]

    assert ids, "3장에서 규칙 블록(#### <id> · <이름>)을 찾지 못했습니다."
    assert [rule_id for rule_id in ids if not RULE_ID.match(rule_id)] == []
    assert len(ids) == len(set(ids)), sorted({rule_id for rule_id in ids if ids.count(rule_id) > 1})


def test_each_rule_sits_under_its_own_group_in_order() -> None:
    """묶음 머리는 정한 차례로 한 번씩 서고, 규칙은 제 묶음 아래에 번호가 오르는 차례로 선다."""
    rules = _rules()
    heads = [
        match.group(1)
        for line in _chapter(_text(), 3).splitlines()
        if (match := _GROUP_HEAD.match(line))
    ]

    assert tuple(heads) == GROUPS
    assert [rule.id for rule in rules if not rule.id.startswith(f"{rule.group}-")] == []
    for group in GROUPS:
        numbers = [int(rule.id[-2:]) for rule in rules if rule.group == group]
        assert numbers and numbers == sorted(numbers), group


def test_every_rule_carries_its_text_and_every_field_once() -> None:
    for rule in _rules():
        assert rule.title.strip() and rule.text, rule.id
        assert sorted(rule.fields) == sorted(FIELDS), rule.id
        assert all(len(values) == 1 and values[0] for values in rule.fields.values()), rule.id


def test_levels_are_must_should_or_may_and_every_rule_is_settled() -> None:
    """답이 모두 왔으므로 「제안」 상태가 남지 않는다 — 새로 추정한 규칙은 짝 질문과
    함께 다음 판에 올린다."""
    for rule in _rules():
        level, state = _level_and_state(rule)
        assert level in LEVELS, rule.id
        assert state == "확정", f"{rule.id}: {state}"


def test_every_rule_asks_a_judgment_question() -> None:
    assert [rule.id for rule in _rules() if "?" not in rule.fields["판단"][0]] == []


def test_the_header_counts_are_the_rules() -> None:
    rules = _rules()
    head = re.search(r"규칙 (\d+) — MUST (\d+) · SHOULD (\d+) · MAY (\d+)", _text())
    levels = [_level_and_state(rule)[0] for rule in rules]

    assert head is not None
    assert [int(number) for number in head.groups()] == [
        len(rules),
        *(levels.count(level) for level in LEVELS),
    ]


def test_chapters_are_parted_by_a_blank_line() -> None:
    """`## n.` 머리 앞에는 빈 줄이 있다 — 붙으면 앞 목록의 마지막 줄에 이어진다."""
    lines = RULES_PATH.read_text(encoding="utf-8").splitlines()
    glued = [
        lines[index]
        for index in range(1, len(lines))
        if lines[index].startswith("## ") and lines[index - 1].strip()
    ]
    assert glued == []


def test_the_decision_record_holds_the_eighteen_answers() -> None:
    """6장은 물음 하나에 한 줄 — 고른 답 · 날짜 · 걸린 규칙을 적고, 사용자 답
    (05 · 06 만 (나))과 같다."""
    lines = [line for line in _chapter(_text(), 6).splitlines() if line.startswith("- AMB-")]
    known = {rule.id for rule in _rules()}
    found: dict[str, str] = {}
    for line in lines:
        match = re.match(
            r"^- (AMB-\d{2}) · .+ → \*\*\((가|나|다)\)\*\* .+\((2026-11-04) · (.+)\)$", line
        )
        assert match, line
        found[match.group(1)] = match.group(2)
        cited = RULE_TOKEN.findall(match.group(4))
        assert cited and set(cited) <= known, line

    assert len(lines) == 18
    assert found == ANSWERS


def test_the_review_sheet_answers_are_recorded_and_written_into_the_rules() -> None:
    """6-2 는 반영 검수표 한 칸에 한 줄이고 답이 사용자 답과 같다. 답이 규칙 글로 들어갔는지 핵심만
    본다 — D1 (나): UI-TXT-04 는 SHOULD(앱 세션이 대신 올린 MUST 를 되돌림 — 다시 올리지 않는다).
    D3 (가): UI-NTF-03 의 예외 「확인 칸을 다시 세우는 거절」. D6 (가): UI-LAY-01 의 예외 「미지정
    주요 Case 칩」."""
    section = _chapter(_text(), 6)
    review = section[section.index("\n### 6-2. ") :]
    lines = [line for line in review.splitlines() if re.match(r"^- D\d+ · ", line)]
    known = {rule.id for rule in _rules()}
    found: dict[str, str] = {}
    for line in lines:
        match = re.match(
            r"^- (D\d+) · .+ → \*\*\((가|나|다)\)\*\* .+\((2026-11-04) · (.+)\)$", line
        )
        assert match, line
        found[match.group(1)] = match.group(2)
        cited = RULE_TOKEN.findall(match.group(4))
        assert cited and set(cited) <= known, line

    assert len(lines) == len(REVIEW_ANSWERS)
    assert found == REVIEW_ANSWERS

    rules = {rule.id: rule for rule in _rules()}
    assert _level_and_state(rules["UI-TXT-04"]) == ("SHOULD", "확정")
    assert "확인 칸을 다시 세우는 거절" in rules["UI-NTF-03"].fields["예외"][0]
    assert "미지정 주요 Case 칩" in rules["UI-LAY-01"].fields["예외"][0]


def test_the_picture_review_memos_are_recorded_and_written_into_the_rules() -> None:
    """6-3 은 메모 칸 하나에 한 줄이고 걸린 규칙이 있는 id 다. 메모가 규칙 글로 들어갔는지 핵심만
    본다 — 수준은 따로 묻기 전에는 올리지 않으므로(7-1) UI-INP-03 은 SHOULD 그대로다."""
    section = _chapter(_text(), 6)
    memos = section[section.index("\n### 6-3. ") :]
    lines = [line for line in memos.splitlines() if line.startswith("- ")]
    known = {rule.id for rule in _rules()}
    found = set()
    for line in lines:
        match = re.match(r"^- ([a-z-]+-\d+) · .+ → .+\((2026-11-05) · (.+)\)$", line)
        assert match, line
        found.add(match.group(1))
        cited = RULE_TOKEN.findall(match.group(3))
        assert cited and set(cited) <= known, line

    assert len(lines) == len(PICTURE_MEMOS)
    assert found == PICTURE_MEMOS

    rules = {rule.id: rule for rule in _rules()}
    assert "데이터 Error" in rules["UI-NTF-08"].title
    assert "Alarm 확인 필요" in rules["UI-NTF-08"].text
    assert "확인 체크" in rules["UI-NTF-09"].fields["예외"][0]
    assert "st.date_input" in rules["UI-INP-03"].text
    assert _level_and_state(rules["UI-INP-03"]) == ("SHOULD", "확정")
    assert "왼쪽 「적용」 · 오른쪽 「양식 다운로드」" in rules["UI-INP-08"].text
    assert _level_and_state(rules["UI-INP-08"]) == ("MUST", "확정")
    assert "떠 있으며" in rules["UI-LAY-09"].text
    assert "판 한 곳" in rules["UI-INP-02"].text
    assert "Alarm 줄" in rules["UI-TXT-08"].text


def test_ids_cited_in_and_around_the_rules_exist() -> None:
    """이 문서와 그것을 부르는 문서의 규칙 id · 물음 id 는 모두 정의된 것이다
    (지운 id 를 가리키지 않는다)."""
    known = {rule.id for rule in _rules()}
    for name in (RULES_LINK, *CITING_DOCUMENTS):
        text = _FENCE.sub("", (PROJECT_ROOT / name).read_text(encoding="utf-8"))
        assert set(RULE_TOKEN.findall(text)) <= known, name
        assert set(QUESTION_TOKEN.findall(text)) <= set(ANSWERS) | CLOSED_QUESTIONS, name


def test_the_nets_named_by_the_rules_exist() -> None:
    """그물 경로는 있는 파일이고, `경로::이름` 꼴로 부른 시험은 그 파일에 그 이름의 함수가 있다."""
    text = _text()
    paths = set(re.findall(r"(?:tests|scripts)/[\w/]+\.py", text))
    nodes = set(re.findall(r"((?:tests|scripts)/[\w/]+\.py)::(\w+)", text))

    assert paths and nodes
    assert sorted(path for path in paths if not (PROJECT_ROOT / path).is_file()) == []
    missing = [
        f"{path}::{name}"
        for path, name in sorted(nodes)
        if not re.search(rf"^def {name}\(", (PROJECT_ROOT / path).read_text(encoding="utf-8"), re.M)
    ]
    assert missing == []


def test_the_two_other_answers_are_written_into_the_rules() -> None:
    """(나) 로 답한 둘은 권장안과 반대라 규칙 글이 그 답을 말한다 — 꼴만 보는 시험이 지나쳐도
    권장안 글로 되돌아가지 않게 핵심 문구를 본다. AMB-06 (나): 길 안내 글을 걷은 자리에 바로 가기도
    두지 않는다(UI-TXT-03). AMB-05 (나): 남은 Capa 계산 오류 · HOME 주요 Case 칩 경고는 자리에서
    걷고 알림창 · Alarm 에만(UI-NTF-03)."""
    rules = {rule.id: rule for rule in _rules()}

    txt03 = f"{rules['UI-TXT-03'].title} {rules['UI-TXT-03'].text}"
    assert "바로 가기" in txt03 and "두지 않는다" in txt03, txt03
    ntf03 = rules["UI-NTF-03"].text
    assert "남은 Capa 계산 오류" in ntf03 and "주요 Case 칩" in ntf03, ntf03
    assert "알림창 · Alarm 에만" in ntf03, ntf03
    assert "UI-NTF-03" in rules["UI-NTF-02"].text


def test_entry_documents_point_at_the_rules() -> None:
    """AGENTS 8장 머리 · 12장 체크리스트 · 13장 문서 우선순위, CLAUDE.md 「문서
    우선순위」, README 문서 표가 이 문서를 부른다."""
    agents = (PROJECT_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    claude = (PROJECT_ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

    def section(text: str, head: str) -> str:
        start = text.index(head)
        following = text.find("\n## ", start + 1)
        return text[start : following if following != -1 else len(text)]

    display = section(agents, "\n## 8. ")
    assert RULES_LINK in display[: display.index("\n- ")]
    assert RULES_LINK in section(agents, "\n## 12. ")
    assert RULES_LINK in section(agents, "\n## 13. ")
    assert RULES_LINK in section(claude, "\n## 문서 우선순위")
    assert f"| `{RULES_LINK}` |" in readme
