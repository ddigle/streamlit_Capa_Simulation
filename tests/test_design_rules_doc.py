# Purpose: 화면 설계 · 검수 규칙 문서(docs/design_rules.md)의 꼴과 진입 문서 연결을 지킨다.

"""화면 설계 · 검수 규칙(`docs/design_rules.md`)의 꼴.

규칙집은 설계 · 검수가 규칙 id 로 대 보는 정본이다(PRC-07). 꼴이 흐트러지면
id 로 찾을 수 없고, 답한 물음이 「제안」 으로 남거나 결정 기록이 빠지면 같은 것을
다시 묻게 된다(PRC-02). 여기서는 글의 뜻이 아니라 꼴을 본다 — id 꼴 · 겹침 · 묶음
자리 · 칸 · 수준 · 판단 질문 · 상태 · 머리의 수 · 결정 기록 18줄과 답 · 반영 검수표 8줄과
답 · 그림 검수표 메모 10줄 · 남은 결정 보드 10줄과 답 · 전후 그림 보드 4줄과 답 · 사용자 기록
5줄 · 이번 배포 전후 보드 7줄과 답 · 통합 검수 보드 줄과 답 · 작업 줄 규칙 둘(v1.9) · 전 화면 점검
보드 15줄 · 2차 보드 7줄과 답(v1.10) · 아침 검수 보드 줄과 답 · 메모 원문(v1.11) · 2026-11-09 검수
보드 · 칩 자리 · 상단 판단 줄과 답 · 메모 원문 · 새 규칙(v1.12) · 상단 정리 검수 보드 줄과 고른
글 · 메모 원문 · 해석 셋(v1.13) · 문서 안팎의 id 참조 · 그물 경로 · 진입 문서(AGENTS · CLAUDE.md ·
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
# 2026-11-05 남은 결정 보드(6-4)의 사용자 답 — 열 칸 모두 (가) 권장이다.
BOARD_ANSWERS = {f"v{n}": "가" for n in range(1, 11)}
# 2026-11-05 전후 그림 보드(6-5)에서 고친 네 칸의 사용자 답 — 그림 칸은 「더 필요」 + 메모, 물음
# 칸은 고른 답.
BEFORE_AFTER_ANSWERS = {
    "v1": "더 필요",
    "v9": "더 필요",
    "q-wip04": "걷는다",
    "q-newunit": "나눈다",
}
# 2026-11-05 사용자 기록(6-6) — 묻고 고른 답이 아니라 기록이라 칸마다 고친 꼴을 맞댄다.
USER_RECORDS = {
    "static-csv": "걷는다",
    "scn-tabs": "탭 넷",
    "scn-text": "걷는다",
    "scn-repo": "걷는다",
    "plan-excluded": "Alarm 으로",
}
# 2026-11-06 이번 배포 전후 보드(6-7)에서 고친 칸의 사용자 답 — 물음 여섯은 고른 답, list-caption 은
# 메모라 고친 꼴을 맞댄다.
DEPLOY_BOARD_ANSWERS = {
    "q-csv": "단추 없이 파일 값을 바로잡는다",
    "q-hover": "고친다",
    "q-unit-change": "원인을 보고 고친다",
    "q-locked": "수율 행도 같은 꼴로 옮긴다",
    "q-id": "지금대로",
    "q-labels": "둘 다 라벨을 둔다",
    "list-caption": "걷는다",
}
# 2026-11-07 통합 검수 보드(6-8)에서 화면에 닿는 칸의 사용자 답 — 결정은 고른 답, list-main 은 고침
# 요청이라 고친 꼴을 맞댄다. equip-toolbar 는 같은 날 이어서 물은 작업 줄의 답이다.
INTEGRATION_BOARD_ANSWERS = {
    "list-main": "맞춘다",
    "D1": "(가)",
    "D2": "(가)",
    "D3": "(가)",
    "D4": "(가)",
    "D5": "(가)",
    "equip-toolbar": "안 A",
}
# 2026-11-07 전 화면 규칙 점검 보드(6-9)의 사용자 답 — 고른 선택지 글. 권장이 아닌 셋은 head-desc ·
# filter-empty · pickers 다.
SWEEP_BOARD_ANSWERS = {
    "narrow": "셋 다 손본다",
    "table-top": "줄을 합친다",
    "place-box": "흔적 · 호기는 Alarm 으로 옮기고, 결론 둘은 상자 없는 한 줄로 바꾼다",
    "undo-strip": "띠를 걷고 되돌리기는 오른쪽 칸 「한 단계 되돌리기」 로 모은다",
    "head-desc": "머리말을 모두 걷는다",
    "side-pending": "왼쪽 문장을 걷고 칩 · 변경 판에 맡긴다",
    "filter-empty": "지금대로",
    "bottom-row": (
        "CSV 는 단축 일정 표 곁으로 올리고, 필요 단축 일정 단추는 다른 길이 없는 공정에만 남긴다"
    ),
    "csv-dup": "왕복 양식 · 전체 행은 두고, 읽기만 하는 표의 곁 CSV 단추는 걷는다",
    "csv-name": "지금대로",
    "desc-blocks": (
        "개발 메모는 할 일 문서로 옮기고, 연결 전 설명은 한 줄 표지로 줄이고, 산식 설명은 화면을"
        " 완성할 때 Guide 로 옮긴다"
    ),
    "pickers": "공정 고르기까지 모두 같은 꼴로 바꾼다(큰 고침)",
    "names": "권장 이름표대로 모두 바꾼다",
    "small-fixes": "권장대로 모두 고친다",
    "rule-notes": "화면 그대로, 규칙에 적는다",
}
# 같은 날 2차 보드(6-10)의 결정 일곱 — 모두 (가).
SECOND_BOARD_ANSWERS = {f"R{n}": "가" for n in range(1, 8)}
# rule-notes 열한 칸이 적힌 규칙과 칸(규칙 id → (칸, 후보 꼬리표)).
RULE_NOTES = {
    "UI-TXT-01": ("예외", "rule-notes g1-15"),
    "UI-LAY-03": ("예외", "rule-notes g2-10"),
    "UI-INP-03": ("예외", "rule-notes g2-19"),
    "UI-INP-01": ("예외", "rule-notes g2-20"),
    "UI-NTF-03": ("text", "rule-notes g2-21"),
    "UI-DAT-02": ("예외", "rule-notes g2-26"),
    "UI-INP-08": ("예외", "rule-notes g3-14"),
    "UI-LAY-09": ("근거", "rule-notes g5-21"),
    "UI-LAY-12": ("예외", "rule-notes g6-23"),
    "UI-STA-06": ("예외", "rule-notes g6-29"),
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
    review = section[section.index("\n### 6-2. ") : section.index("\n### 6-3. ")]
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
    본다 — UI-INP-03 수준은 그 뒤 따로 물어 올렸다(6-4 v4 — 아래 시험)."""
    section = _chapter(_text(), 6)
    memos = section[section.index("\n### 6-3. ") : section.index("\n### 6-4. ")]
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
    assert "왼쪽 「적용」 · 오른쪽 「양식 다운로드」" in rules["UI-INP-08"].text
    assert _level_and_state(rules["UI-INP-08"]) == ("MUST", "확정")
    assert "떠 있으며" in rules["UI-LAY-09"].text
    assert "판 한 곳" in rules["UI-INP-02"].text
    assert "Alarm 줄" in rules["UI-TXT-08"].text


def test_the_board_answers_are_recorded_and_written_into_the_rules() -> None:
    """6-4 는 남은 결정 보드 한 칸에 한 줄이고 답이 사용자 답과 같다. 답이 규칙 글로 들어갔는지
    핵심만 본다 — v4: UI-INP-03 은 MUST. v2 · v3: 확인 체크를 남기는 저장 둘은 UI-NTF-09 예외.
    v7: 일정 글 칸은 UI-INP-03 예외. v8: 입력 빠짐 멈춤도 마크 + 「그 화면으로」. v9: placeholder 는
    창 안 글. v10: 충돌 보고는 자리에 두는 갈래가 아니다. v5: 제안 값 넷은 확정이다. 답이 왔으므로
    규칙 칸에 「답 대기」 가 남지 않는다."""
    section = _chapter(_text(), 6)
    board = section[section.index("\n### 6-4. ") : section.index("\n### 6-5. ")]
    lines = [line for line in board.splitlines() if line.startswith("- ")]
    known = {rule.id for rule in _rules()}
    found: dict[str, str] = {}
    for line in lines:
        match = re.match(
            r"^- (v\d+) · .+ → \*\*\((가|나|다)\)\*\* .+\((2026-11-05) · (.+)\)$", line
        )
        assert match, line
        found[match.group(1)] = match.group(2)
        cited = RULE_TOKEN.findall(match.group(4))
        assert cited and set(cited) <= known, line

    assert found == BOARD_ANSWERS

    rules = {rule.id: rule for rule in _rules()}
    assert _level_and_state(rules["UI-INP-03"]) == ("MUST", "확정")
    assert "일정 글 칸" in rules["UI-INP-03"].fields["예외"][0]
    exceptions = rules["UI-NTF-09"].fields["예외"][0]
    assert "적용하지 않은 편집을 버리고 저장" in exceptions
    assert "이탈 호기 n대 알고 저장" in exceptions
    assert "입력이 빠져 멈춤" not in rules["UI-NTF-08"].fields["예외"][0]
    assert "빠져 멈춤" in rules["UI-NTF-08"].text and "그 화면으로" in rules["UI-NTF-08"].text
    assert "placeholder" in rules["UI-INP-08"].text
    assert "점검 보고" not in rules["UI-TXT-08"].fields["예외"][0]
    assert "SC-04" in rules["UI-TXT-08"].fields["예외"][0]

    values = _chapter(_text(), 4)
    for name in ("날짜 판 빠른 선택", "붙여넣기 창", "설비 마스터 오른쪽 칸 폭", "Alarm 딸린 표"):
        row = next(line for line in values.splitlines() if line.startswith(f"| {name} |"))
        assert "v5 확정" in row and "검수 전" not in row, row

    assert [rule.id for rule in rules.values() if "답 대기" in " ".join(rule.fields["예외"])] == []


def test_the_before_after_board_answers_are_recorded_and_written_into_the_rules() -> None:
    """6-5 는 전후 그림 보드에서 고친 칸 하나에 한 줄이고 답이 사용자 답과 같다. 답이 규칙 글로
    들어갔는지 핵심만 본다 — v1: 단추 판정 글은 풍선(UI-INP-07). v9: 작업 줄은 창 제목 옆, 글 칸
    라벨 없음(UI-INP-08 — 표 상자 칸 · 라벨 보이는 창 둘은 예외). q-wip04: 다른 화면의 입력은 Alarm
    줄이 연다(UI-NTF-02). q-newunit: 지우기 머리 글을 가른다(UI-NTF-09). 메모 원문은 근거에
    남는다."""
    section = _chapter(_text(), 6)
    board = section[section.index("\n### 6-5. ") : section.index("\n### 6-6. ")]
    lines = [line for line in board.splitlines() if line.startswith("- ")]
    known = {rule.id for rule in _rules()}
    found: dict[str, str] = {}
    for line in lines:
        match = re.match(r"^- ([a-z0-9-]+) · .+ → \*\*([^*]+)\*\* .+\((2026-11-05) · (.+)\)$", line)
        assert match, line
        found[match.group(1)] = match.group(2)
        cited = RULE_TOKEN.findall(match.group(4))
        assert cited and set(cited) <= known, line

    assert found == BEFORE_AFTER_ANSWERS

    rules = {rule.id: rule for rule in _rules()}
    assert "칸에 늘 세우지" in rules["UI-INP-07"].text
    assert "호기 추가버튼에 마우스" in rules["UI-INP-07"].fields["근거"][0]
    assert "창 제목 옆" in rules["UI-INP-08"].text and "라벨" in rules["UI-INP-08"].text
    assert "제목 옆" in rules["UI-INP-08"].fields["판단"][0]
    assert "타이틀 옆에 배치" in rules["UI-INP-08"].fields["근거"][0]
    assert "접속 명단 추가" in rules["UI-INP-08"].fields["범위"][0]
    exceptions = rules["UI-INP-08"].fields["예외"][0]
    assert "표 상자" in exceptions and "라벨을 보이는 창은 둘" in exceptions
    assert (
        "그 화면으로" in rules["UI-NTF-02"].text
        and "q-wip04" in rules["UI-NTF-02"].fields["근거"][0]
    )
    assert "새 호기 n대 뺌" in rules["UI-NTF-09"].fields["예외"][0]


def test_the_user_records_are_recorded_and_written_into_the_rules() -> None:
    """6-6 은 사용자 기록 칸 하나에 한 줄이고 고친 꼴이 기록과 같다. 기록이 규칙 글로 들어갔는지
    핵심만 본다 — plan-excluded: 큰 목록은 Alarm 표 앞부분 + 탭 맨 아래 CSV 라 UI-LAY-03 의 예외이고
    UI-TXT-08 · 4장도 같은 말을 한다. scn-tabs: 근거가 UI-LAY-07 에 있다."""
    section = _chapter(_text(), 6)
    records = section[section.index("\n### 6-6. ") : section.index("\n### 6-7. ")]
    lines = [line for line in records.splitlines() if line.startswith("- ")]
    known = {rule.id for rule in _rules()}
    found: dict[str, str] = {}
    for line in lines:
        match = re.match(r"^- ([a-z-]+) · .+ → \*\*([^*]+)\*\* .+\((2026-11-05) · (.+)\)$", line)
        assert match, line
        found[match.group(1)] = match.group(2)
        cited = RULE_TOKEN.findall(match.group(4))
        assert cited and set(cited) <= known, line

    assert len(lines) == len(USER_RECORDS)
    assert found == USER_RECORDS

    rules = {rule.id: rule for rule in _rules()}
    exceptions = rules["UI-LAY-03"].fields["예외"][0]
    assert "Alarm 표에 다 못 싣는 목록의 전체 CSV" in exceptions
    assert "plan-excluded" in rules["UI-LAY-03"].fields["근거"][0]
    assert "앞부분" in rules["UI-TXT-08"].text and "UI-LAY-03 예외" in rules["UI-TXT-08"].text
    assert "scn-tabs" in rules["UI-LAY-07"].fields["근거"][0]

    values = next(
        line for line in _chapter(_text(), 4).splitlines() if line.startswith("| Alarm 딸린 표 |")
    )
    assert "탭 맨 아래 CSV" in values, values


def test_the_deploy_board_answers_are_recorded_and_written_into_the_rules() -> None:
    """6-7 은 이번 배포 전후 보드에서 고친 칸 하나에 한 줄이고 답이 사용자 답과 같다. 답이 규칙 글로
    들어갔는지 핵심만 본다 — q-csv: 도구 막대 CSV 도 원본이고 UI-DAT-10 은 예외 없이 답 대기를
    닫는다. q-unit-change: 저장할 것이 없으면 표지도 없다(UI-DAT-11). q-hover: 칠한 단추
    호버(UI-ACC-01). q-locked: 수율 행도 앞부분 + 탭 맨 아래 CSV 다(UI-TXT-08 · UI-LAY-03 · 4장).
    q-labels: 라벨을 보이는 창 둘은 예외로 확정(UI-INP-08). 답이 왔으므로 규칙 글에 「답 대기」 가
    남지 않는다."""
    section = _chapter(_text(), 6)
    board = section[section.index("\n### 6-7. ") : section.index("\n### 6-8. ")]
    lines = [line for line in board.splitlines() if line.startswith("- ")]
    known = {rule.id for rule in _rules()}
    found: dict[str, str] = {}
    for line in lines:
        match = re.match(r"^- ([a-z-]+) · .+ → \*\*([^*]+)\*\* .+\((2026-11-06) · (.+)\)$", line)
        assert match, line
        found[match.group(1)] = match.group(2)
        cited = RULE_TOKEN.findall(match.group(4))
        assert cited and set(cited) <= known, line

    assert len(lines) == len(DEPLOY_BOARD_ANSWERS)
    assert found == DEPLOY_BOARD_ANSWERS

    rules = {rule.id: rule for rule in _rules()}
    assert "도구 막대 CSV" in rules["UI-DAT-10"].text and "Static Capa" in rules["UI-DAT-10"].text
    assert rules["UI-DAT-10"].fields["예외"] == ["없음"]
    assert "tests/test_static_capa_layout.py" in rules["UI-DAT-10"].fields["그물"][0]
    assert "q-csv" in rules["UI-DAT-10"].fields["근거"][0]
    assert [rule.id for rule in rules.values() if "답 대기" in rule.text] == []

    assert "미저장 표지" in rules["UI-DAT-11"].text
    for rule_id in ("UI-DAT-11", "UI-STA-02"):
        assert "tests/test_equipment_unsaved_mark.py" in rules[rule_id].fields["그물"][0]
    assert "q-unit-change" in rules["UI-LAY-04"].fields["근거"][0]

    assert "호버" in rules["UI-ACC-01"].text
    assert "tests/test_equipment_master_grid_assets.py" in rules["UI-ACC-01"].fields["그물"][0]

    assert "편집 불가 수율 행" in rules["UI-TXT-08"].text
    assert "편집 불가 수율 행" in rules["UI-LAY-03"].fields["예외"][0]
    values = next(
        line for line in _chapter(_text(), 4).splitlines() if line.startswith("| Alarm 딸린 표 |")
    )
    assert "편집 불가 수율 행" in values, values

    assert "q-labels" in rules["UI-INP-08"].fields["예외"][0]
    assert "고친것 이름0 순서0" in rules["UI-TXT-01"].fields["근거"][0]


def test_the_integration_board_answers_are_recorded_and_written_into_the_rules() -> None:
    """6-8 은 통합 검수 보드에서 화면에 닿는 칸 하나에 한 줄이고 답이 사용자 답과 같다. D1 은
    UI-LAY-03 예외, list-main 은 UI-LAY-09 글이다 — 머리선 맞춤은 표가 나란히 서는 칸으로 한정하고
    설비 마스터 오른쪽 칸은 해당이 없다고 글이 말한다. 물은 판의 「물을 것」 은 답으로 닫힌다.
    """
    document = _text()
    section = _chapter(document, 6)
    board = section[section.index("\n### 6-8. ") : section.index("\n### 6-9. ")]
    lines = [line for line in board.splitlines() if line.startswith("- ")]
    known = {rule.id for rule in _rules()}
    found: dict[str, str] = {}
    for line in lines:
        match = re.match(r"^- ([\w-]+) · .+ → \*\*([^*]+)\*\* .+\((2026-11-07) · (.+)\)$", line)
        assert match, line
        found[match.group(1)] = match.group(2)
        cited = RULE_TOKEN.findall(match.group(4))
        assert cited and set(cited) <= known, line

    assert len(lines) == len(INTEGRATION_BOARD_ANSWERS)
    assert found == INTEGRATION_BOARD_ANSWERS
    assert "- **v1.8 — 2026-11-07.**" in _chapter(document, 8)

    rules = {rule.id: rule for rule in _rules()}
    exceptions = rules["UI-LAY-03"].fields["예외"][0]
    assert "선택한 리비전 불러오기" in exceptions and "6-8 D1" in exceptions
    assert "통합 검수 D1 (가)" in rules["UI-LAY-03"].fields["근거"][0]

    panel = rules["UI-LAY-09"]
    assert "본문 표와 나란히 서는 칸은 두 표의 머리선을 맞춘다" in panel.text
    assert "맨 위가 표가 아닌 칸(설비 마스터 오른쪽 칸 등)은 해당이 없다" in panel.text
    assert "tests/test_scenario_list_grid_assets.py" in panel.fields["그물"][0]
    for tag in ("통합 검수 list-main", "통합 검수 D2 (가)"):
        assert tag in panel.fields["근거"][0]

    previous = next(
        line for line in document.splitlines() if line.startswith("  - 물을 것: 상세 칸")
    )
    assert "6-8 · v1.8 로 답했다" in previous, previous

    toolbar = next(line for line in lines if line.startswith("- equip-toolbar · "))
    for phrase in ("한 줄", "오른쪽 칸 탭과 중복", "static-csv 「기능 중복」", "flex 기준 220px"):
        assert phrase in toolbar, phrase
    assert "메뉴 「엑셀·CSV」 로 묶었다" in toolbar
    values = _chapter(document, 4)
    row = next(line for line in values.splitlines() if line.startswith("| 설비 마스터 작업 줄 |"))
    assert "flex 기준 220px" in row and "안 A" in row and "검수 전" in row
    assert "| 편집기 왼쪽 칸 아래 한계 | 안쪽 224px" in values


def test_the_work_row_rules_carry_the_remarks_of_the_day() -> None:
    """v1.9 — 2026-11-07 지적을 규칙이 잡지 못해 올렸다. 작업 줄 석 줄은 UI-LAY-11(기준 창 한 줄 ·
    메뉴로 묶음), 같은 일 단추는 UI-LAY-12 다. 단추를 두고 한 사용자 글이 하나씩이라 둘 다 SHOULD
    이고(1-2) 근거에 원문이 있다. 기준 창은 4장에 「검수 전」 이고 사내 보고 창은 두 줄까지라 안 A
    의 문턱 1,363 과 어긋나지 않는다. 짝 규칙은 경계를 맞췄고 표 머리선은 패널 밖 두 표로 넓혔다."""
    document = _text()
    assert "- **v1.9 — 2026-11-07.**" in _chapter(document, 8)

    rules = {rule.id: rule for rule in _rules()}
    toolbar = rules["UI-LAY-11"]
    assert _level_and_state(toolbar) == ("SHOULD", "확정")
    assert "기준 창(4장)에서 한 줄" in toolbar.text and "메뉴 하나로 묶는다" in toolbar.text
    assert "이 버튼들이 많아서 현재 총 3줄로 보임" in toolbar.fields["근거"][0]
    assert "「표 위 작업 줄 기준 창」" in toolbar.fields["지금 값"][0]

    same_job = rules["UI-LAY-12"]
    assert _level_and_state(same_job) == ("SHOULD", "확정")
    assert "옆 칸 탭 · 고르기 · 표 도구 막대" in same_job.text
    for phrase in ("「기능 중복」", "중복된 내용 표기에 걸림", "「+ 새 호기」 를 뺌"):
        assert phrase in same_job.fields["근거"][0], phrase
    for phrase in ("빈 표 자리의 시작 단추", "단축키", "결과가 다르면 같은 일이 아니다"):
        assert phrase in same_job.fields["예외"][0], phrase

    values = _chapter(document, 4)
    row = next(line for line in values.splitlines() if line.startswith("| 표 위 작업 줄 기준 창 |"))
    for phrase in ("1600×1000", "1283×911", "두 줄까지", "창 1,363", "검수 전"):
        assert phrase in row, phrase

    assert "UI-LAY-11" in rules["UI-LAY-03"].text and "UI-LAY-12" in rules["UI-LAY-03"].text
    assert "표 위 작업 줄" in rules["UI-ACC-02"].fields["범위"][0]
    assert "UI-LAY-12" in rules["UI-TXT-07"].fields["범위"][0]
    panel = rules["UI-LAY-09"]
    assert "나란히 선 두 표 전부" in panel.fields["범위"][0]
    assert "작업 줄이 접혀" in panel.text and "작업 줄이 접혀도" in panel.fields["판단"][0]

    nets = _chapter(document, 5)
    for rule_id in ("UI-LAY-09", "UI-LAY-11", "UI-LAY-12"):
        assert f"({rule_id})" in nets, rule_id


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


def test_the_sweep_board_answers_are_recorded_and_written_into_the_rules() -> None:
    """v1.10 — 6-9 는 전 화면 점검 보드 한 칸에 한 줄이고 답이 사용자 답과 같다. 권장이 아닌 둘의
    메모 원문이 줄에 있다. 답이 규칙 글로 들어갔는지 핵심만 본다 — head-desc: 머리 설명 줄 없음 ·
    남은 두 자리 · 그물, 정체성은 Guide 첫 단락. csv-name: UI-DAT-10 범위를 왕복 양식과 Static 두
    표로 좁히고 예외 칸은 그대로. csv-dup: UI-LAY-12 예외. names: 이름 바꿈 사전 그물이 섰다.
    table-top: 꼴 그물은 섰고 줄 수 그물은 후보로 남는다. pickers 는 조사 중이다."""
    document = _text()
    assert "- **v1.10 — 2026-11-08.**" in _chapter(document, 8)

    section = _chapter(document, 6)
    board = section[section.index("\n### 6-9. ") : section.index("\n### 6-10. ")]
    lines = [line for line in board.splitlines() if line.startswith("- ")]
    known = {rule.id for rule in _rules()}
    found: dict[str, str] = {}
    for line in lines:
        match = re.match(r"^- ([\w-]+) · .+ → \*\*([^*]+)\*\* .+\((2026-11-07) · (.+)\)$", line)
        assert match, line
        found[match.group(1)] = match.group(2)
        cited = RULE_TOKEN.findall(match.group(4))
        assert cited and set(cited) <= known, line
    assert len(lines) == len(SWEEP_BOARD_ANSWERS)
    assert found == SWEEP_BOARD_ANSWERS
    by_id = {line.split(" · ", 1)[0][2:]: line for line in lines}
    assert "「꼭 필요한 소개 문구는 guide에 포함.」" in by_id["head-desc"]
    assert "기준정보 페이지로 갔을때도 자동적으로 공정 A에 필터가" in by_id["pickers"]
    assert "조사 중" in by_id["pickers"]

    rules = {rule.id: rule for rule in _rules()}
    txt01 = rules["UI-TXT-01"]
    assert "화면 머리(제목 줄)" in txt01.text and "Guide 첫 단락" in txt01.text
    # head-desc 가 남긴 두 자리는 6-11 d1 · g03 으로 걷어 예외에서 빠졌다.
    for phrase in ("module_api.page_header(description=)", "필요 단축 일정 머리말"):
        assert phrase not in txt01.fields["예외"][0], phrase
    assert "6-11 d1 · g03" in txt01.fields["그물"][0]
    assert "tests/test_page_header_description.py" in txt01.fields["그물"][0]
    assert "tests/test_page_header_description.py" in rules["UI-TXT-02"].fields["그물"][0]
    assert "Guide 첫 단락" in rules["UI-LAY-08"].text

    dat10 = rules["UI-DAT-10"]
    assert "Static Capa 두 부족 표" in dat10.fields["범위"][0]
    assert "6-9 csv-name" in dat10.text and dat10.fields["예외"] == ["없음"]
    lay12 = rules["UI-LAY-12"].fields["예외"][0]
    assert "왕복 양식 · 전체 행" in lay12 and "6-9 csv-dup" in lay12

    con02 = rules["UI-CON-02"]
    assert "tests/test_one_concept_one_name.py" in con02.fields["그물"][0]
    assert con02.fields["그물 후보"] == ["없음"]
    assert "이름 바꿈 사전 그물" not in _chapter(document, 5)

    lay11 = rules["UI-LAY-11"]
    assert "tests/test_table_top_rows.py" in lay11.fields["그물"][0]
    assert lay11.fields["그물 후보"] == ["표 위 작업 줄 줄 수"]
    values = _chapter(document, 4)
    for name in ("기준 정보 표 위 한 줄", "달 표 분류 칸 곁 달 몫", "생산 진도 자리 높이"):
        row = next(line for line in values.splitlines() if line.startswith(f"| {name} |"))
        assert "검수 전" in row, row
    side = next(
        line for line in values.splitlines() if line.startswith("| 설비 마스터 오른쪽 칸 폭 |")
    )
    assert "줄의 40%" in side

    for rule_id, (place, tag) in RULE_NOTES.items():
        written = rules[rule_id].text if place == "text" else rules[rule_id].fields[place][0]
        assert tag in written, (rule_id, tag)
    assert "여덟 곳" in rules["UI-NTF-03"].fields["예외"][0]
    # rule-notes 의 「구현 중 화면 유예」(UI-LAY-02 예외 — 조회 조건은 구현 완료 때 사이드바로)는
    # 2026-11-09 상단 정리 보드 T8 (가)로 거뒀다 — 예외에서 빠지고 범위가 구현 중 화면을 품는다.
    assert "2026-09-29 범위 결정" not in rules["UI-LAY-02"].fields["예외"][0]
    assert "2026-11-09 보드 T8" in rules["UI-LAY-02"].fields["범위"][0]
    assert "2026-09-29 범위 결정" in rules["UI-INP-03"].fields["예외"][0]


def test_the_second_board_answers_are_recorded_and_close_the_open_check() -> None:
    """6-10 은 2차 보드 결정 하나에 한 줄이고 모두 (가)다. R6 은 v1.8 이 「사용자 확인 전」 으로
    더한 UI-PRF-03 상자 예외를 확정하므로 그 말이 문서에 남지 않는다."""
    document = _text()
    section = _chapter(document, 6)
    board = section[section.index("\n### 6-10. ") : section.index("\n### 6-11. ")]
    lines = [line for line in board.splitlines() if line.startswith("- ")]
    known = {rule.id for rule in _rules()}
    found: dict[str, str] = {}
    for line in lines:
        match = re.match(r"^- (R\d) · .+ → \*\*\((가|나)\)\*\* .+\((2026-11-07) · (.+)\)$", line)
        assert match, line
        found[match.group(1)] = match.group(2)
        cited = RULE_TOKEN.findall(match.group(4))
        assert cited and set(cited) <= known, line
    assert found == SECOND_BOARD_ANSWERS

    assert "사용자 확인 전" not in document
    rules = {rule.id: rule for rule in _rules()}
    assert "2차 보드 R6 · R7 (가)" in rules["UI-PRF-03"].fields["근거"][0]
    assert "2차 보드 R5 (가)" in rules["UI-CON-02"].fields["근거"][0]
    assert "2차 보드 R4 (가)" in rules["UI-LAY-11"].fields["근거"][0]


# 2026-11-08 아침 검수 보드(6-11)의 답 — 보드가 낸 답 파일의 원문을 여기 옮긴다(저장소 밖
# 파일이라 시험이 읽지 않는다). 정할 칸은 고른 선택지 글, 작은 결정은 46줄 모두 권장, 그림은 고침
# 요청 여섯의 메모.
MORNING_DECISIONS = {
    "D1": (
        "나눠 한다 — 이번 배포는 화면 고침과 C-DEP 첫 CI/CD(S3 키 넣기)까지, 이관은 다음 배포에서."
        " 직전 배포 뒤 커밋이 421개라 문제가 나면 어느 쪽 탓인지 가르기 쉽다"
    ),
    "D2": "된다 — deploy: 커밋만 먼저 올린다(초안이 이렇게 쓰였다)",
    "D3": "공지에 이관 소식 한 줄을 저장하고 그대로 둔다 — 동료가 봐도 되는 글",
    "X1": "넷 다 권장대로 고친다",
    "P1": "권장안 — 세 번에 나눠 한다(1차부터, 사용자 검수 두 번)",
    "P2": "다섯 모두 권장대로",
    "U1": "「Select all」 을 뺀다 — 한 사람씩 고른다",
    "U2": "화면이 본 기본과 지금 기본이 다르면 거절한다 — 묶음에 하나뿐인 값이라 이 값만 본다",
    "U3": "등록 점검이 빈 표를 잡아 기존 등록 뒤 「계산 멈춤」 알림으로 낸다",
    "U4": (
        "둘 다 고친다 — 거절 글을 「확인하지 못했습니다」 로 가르고 관리자에게 어느 화면에서나"
        " 알린다"
    ),
    "U5": "여덟 팝업 모두 이번에 옮긴다 — 크기가 크다",
}
MORNING_SMALL_IDS = (
    [f"a{n}" for n in range(1, 12)]
    + [f"b{n}" for n in range(1, 7)]
    + [f"c{n}" for n in range(1, 12)]
    + [f"d{n}" for n in range(1, 16)]
    + [f"e{n}" for n in range(1, 4)]
)
MORNING_PICTURE_FIXES = ("g01", "g03", "g05", "g12", "g17", "g18")
# 메모 원문 가운데 줄마다 하나씩 — 고친 칸 줄에 그대로 있어야 한다.
MORNING_MEMOS = {
    "P1": (
        "공정 Capa 상세, 가용설비 Main, Space는 공용 칸에 넣었을때 간격이 일정하지 않게 더 많이"
        " 들어간거같아"
    ),
    "P2": "계속 모니터링해보고 적절치 않다고 판단되면 다른 구조로 바꾸거나 원복을 검토해야겠음.",
    "g01": "이거 무슨 규칙에 의해 이렇게 만들게된거지? 요청이 있었나?",
    "g03": "그리고 공정 진척 보드도 접고 펼수있게하고, 기본적으로 접혀있게 셋팅해",
    "g05": "뷰어 상태에서 목표 확보율 선택 버튼 사이드바 조회조건 박스로 이동",
    "g12": "제약 영향, 개조 일정 버튼도  사이드바 조건박스로 배치",
    "g17": "CSV 다운로드 버튼도 cut저장 버튼 옆으로 한줄에 세워",
    "g18": "공용 버전v3 .... 타임스탬프 줄을 각 타이틀 옆으로 배치",
}


def test_the_morning_board_answers_are_recorded_and_written_into_the_rules() -> None:
    """v1.11 — 6-11 은 아침 검수 보드 정할 칸 열하나 · 작은 결정 마흔여섯 · 고침 그림 여섯 · 괜찮음
    그림 한 줄이고, 정할 칸 답은 고른 글 그대로, 고침 칸 · P1 · P2 에는 메모 원문이 있다. 답이 규칙
    글로 들어갔는지 핵심만 본다 — 공정 공유 다섯 규칙과 두 모듈 경계(UI-LAY-02), 공정 판(UI-INP-03),
    범위 바뀜(UI-NTF-02), 팝업 호스트(UI-PRF-01), 잠긴 Cut-off 왕복 양식(UI-LAY-12)."""
    document = _text()
    assert "- **v1.11 — 2026-11-08.**" in _chapter(document, 8)

    section = _chapter(document, 6)
    board = section[section.index("\n### 6-11. ") : section.index("\n### 6-12. ")]
    lines = [line for line in board.splitlines() if line.startswith("- ")]
    known = {rule.id for rule in _rules()}
    found: dict[str, str] = {}
    for line in lines:
        match = re.match(r"^- ([\w-]+) · .+ → \*\*([^*]+)\*\*.*\((2026-11-08) · ([^()]+)\)$", line)
        assert match, line
        found[match.group(1)] = match.group(2)
        cited = RULE_TOKEN.findall(match.group(4))
        assert cited and set(cited) <= known, line
    expected_ids = [
        *MORNING_DECISIONS,
        *MORNING_SMALL_IDS,
        *MORNING_PICTURE_FIXES,
        "pictures-ok",
    ]
    assert list(found) == expected_ids
    assert len(MORNING_SMALL_IDS) == 46
    for key, answer in MORNING_DECISIONS.items():
        assert found[key] == answer, key
    for key in MORNING_PICTURE_FIXES:
        assert found[key] == "고친다", key
    assert found["pictures-ok"] == "괜찮음"
    by_id = {line.split(" · ", 1)[0][2:]: line for line in lines}
    for key, memo in MORNING_MEMOS.items():
        assert memo in by_id[key], key
    assert "그림 18칸" in by_id["pictures-ok"]

    rules = {rule.id: rule for rule in _rules()}
    lay02 = rules["UI-LAY-02"]
    for phrase in (
        "HOME 은 보내기만",
        "받기만",
        "저장값은 건드리지 않는다",
        "`shared_process`",
        "`process_field`",
    ):
        assert phrase in lay02.text, phrase
    assert "원복" in lay02.text
    assert "tests/test_shared_process.py" in lay02.fields["그물"][0]
    assert "6-11 g12" in lay02.fields["예외"][0]
    assert "공정 판" in rules["UI-INP-03"].fields["범위"][0]
    assert "범위 바뀜" in rules["UI-NTF-02"].text
    assert "tests/test_dialog_host.py" in rules["UI-PRF-01"].fields["그물"][0]
    assert "6-11 d6" in rules["UI-LAY-12"].fields["예외"][0]
    assert "6-11 c10" in rules["UI-PRF-02"].fields["예외"][0]
    assert "6-11 d11" in rules["UI-DAT-03"].fields["예외"][0]
    values = _chapter(document, 4)
    for name in ("공정 값 칸 글", "공용 공정 표지", "조건 패널 줄 사이", "팝업 여닫기 회차"):
        assert any(line.startswith(f"| {name} |") for line in values.splitlines()), name


# 2026-11-09 검수 보드 · 칩 자리 · 상단 판단 보드(6-12)의 답 — 결정 셋과 남은 물음 표는
# 권장, C1 은 (라) · T1 은 (나) 이고 나머지 C · T 는 (가)다. 고침 그림은 메모 원문(앞부분)을
# 맞댄다.
TOP_DECISIONS = {
    "top-rule": "인터페이스 구성 규칙으로 둔다",
    "K1": "1차를 이번 배포에 싣고, 사내에서 써 본 뒤 2차를 시작한다",
    "K2": "지금대로 — 사이드바를 굴려 본다",
    "K3": "받는다 — 지금처럼 내려가 빛난다",
    "Q": "권장대로 모두",
}
TOP_PICTURE_MEMOS = {
    "P1-3": "굳이 그렇게 안해도될것같음.",
    "P1-5": "space 도면 박스에서는 자리, 도면 문구 제거해",
    "P1-6": "HB 접합 없음이 무슨뜻?",
    "P1-11": "여기서 공정을 바꾸면 다른페이지에서도 그 공정 필터가 적용되게끔.",
    "U5-1": "공정명 옆에 최저 확보율도 작게 같이 표기해줘",
    "g03-1": "Qual 마감 계산기도 사이드바 조건박스 상자로 이동",
    "g03-2": "(Wafer Saw 외 n개 선택) 이렇게 보여지게 한줄로 정리해줘",
    "g05": "단축없는호기 흐리게, 날짜, 맞대지 못한 공정 등 3줄도 다른 위치로 옮겨",
    "g12-1": "추가설명필요한건 가이드로",
    "g12-2": "월별 확보율에도 옅은 칠 문구 가이드배치 or 제거",
    "g17": "표 보기 설정 위아래로 여백이 뜨는데 공간 최적화해",
    "g18": "중간중간 중복되는 문구(공지)나 여백이 있는데 최적화해",
}
TOP_CHOICES = {
    "C1": "(라) (가) + (다) 함께",
    "C2": "(가) 둘 다 주고받기 — 사이드바 칸에서 직접 고른 공정만 보냄",
    "C3": (
        "(가) 사이드바 「제약 시뮬레이션 조건」 카드로 옮기고 이름을 「비중 배분 비교」 로 줄임"
        " — 설명은 Guide"
    ),
    "T1": "(나) 그대로",
    "T2": "(가) 합침",
    "T3": "(가) 옆 줄 오른쪽 끝으로 합침",
    "T4": "(가) 걷음",
    "T5": "(가) 표 작업 줄 끝 「표 보기 ▾」 팝오버로",
    "T6": "(가) 라벨만 걷고 칸은 그 자리",
    "T7": "(가) 보유 공정 → 표 머리 풍선 · 팝오버, 알림 수 → 탭 이름 곁 수 표지",
    "T8": (
        "(가) 지금 정리 — 배지 → 화면 탭 이름 곁 「구현중」 표지 + 풍선, 샘플 토글 → 사이드바"
        " 조회 조건, 「합성 샘플」 → 머리 띠 표지, 조회 조건 → 사이드바"
    ),
    "T9": "(가) 그대로 — 탭은 탐색이라 남김",
    "T10": "(가) 한 번 뜨는 알림창 알림으로",
}
TOP_RULE_QUOTE = (
    "페이지 상단의 여백이나 문구를 최소화해서 본문, 핵심내용이 상단에 꽉 차게 배치하는게"
)


def test_the_top_boards_are_recorded_and_the_top_rule_stands() -> None:
    """v1.12 — 6-12 는 사용자 규칙 한 줄 · 결정 셋 · 남은 물음 표 · 고침 그림 열둘 · 괜찮음
    그림 한 줄 · 칩 자리 C1 ~ C3 · 상단 판단 T1 ~ T10 이고, 고른 글 그대로 · 메모 원문이 있다.
    새 규칙 UI-LAY-13 은 사용자 원문을 근거로 싣고 예외(T1 공지 · T9 탭 줄 아래 14px · 안쪽
    탭)를 적으며, UI-LAY-02 는 구현 중 화면 예외를 거뒀다(T8)."""
    document = _text()
    assert "- **v1.12 — 2026-11-10.**" in _chapter(document, 8)

    section = _chapter(document, 6)
    board = section[section.index("\n### 6-12. ") : section.index("\n### 6-13. ")]
    lines = [line for line in board.splitlines() if line.startswith("- ")]
    known = {rule.id for rule in _rules()}
    found: dict[str, str] = {}
    for line in lines:
        match = re.match(r"^- ([\w-]+) · .+ → \*\*([^*]+)\*\*.*\((2026-11-09) · ([^()]+)\)$", line)
        assert match, line
        found[match.group(1)] = match.group(2)
        cited = RULE_TOKEN.findall(match.group(4))
        assert cited and set(cited) <= known, line
    assert list(found) == [*TOP_DECISIONS, *TOP_PICTURE_MEMOS, "pictures-ok", *TOP_CHOICES]
    for key, answer in {**TOP_DECISIONS, **TOP_CHOICES}.items():
        assert found[key] == answer, key
    for key in TOP_PICTURE_MEMOS:
        assert found[key] == "고친다", key
    assert found["pictures-ok"] == "괜찮음"
    by_id = {line.split(" · ", 1)[0][2:]: line for line in lines}
    for key, memo in TOP_PICTURE_MEMOS.items():
        assert memo in by_id[key], key
    assert "그림 14칸" in by_id["pictures-ok"]
    assert TOP_RULE_QUOTE in by_id["top-rule"]

    rules = {rule.id: rule for rule in _rules()}
    top = rules["UI-LAY-13"]
    assert _level_and_state(top) == ("MUST", "확정")
    assert TOP_RULE_QUOTE in top.fields["근거"][0]
    for phrase in ("T1 (나)", "T9 (가)", "안쪽 탭"):
        assert phrase in top.fields["예외"][0], phrase
    assert "탭 줄 아래선" in top.fields["범위"][0]
    assert "bandlib" in top.fields["그물 후보"][0]
    for neighbour in ("UI-TXT-04", "UI-TXT-06", "UI-LAY-04"):
        rule = rules[neighbour]
        assert "UI-LAY-13" in " ".join([rule.text, *rule.fields["예외"]]), neighbour
    lay02 = rules["UI-LAY-02"]
    assert "구현 중 화면도 같다" in lay02.fields["범위"][0]
    assert "구현 중" not in lay02.fields["예외"][0]
    values = _chapter(document, 4)
    for name in ("상단 띠", "Proc Rename 제목 줄", "본문 빈 칸"):
        assert any(line.startswith(f"| {name} |") for line in values.splitlines()), name


# 2026-11-10 상단 정리 검수 보드(6-13)의 답 — 그림은 넷이 「고칠 것」(메모 원문) · 마흔이
# 「좋음」, 물음은 Q-14 만 둘째 선택지이고 나머지 스물둘은 권장(첫 선택지)이다. 고른 글은 선택지
# 원문 그대로다.
TOP_CHECK_PICTURE_MEMOS = {
    "admin-rename": "저장 버튼과 시트 사이 여백 조정",
    "admin-order": "저장 버튼과 시트 사이 여백 조정",
    "eq-pref": "저장 버튼과 시트 사이 여백 조정",
    "c2-picked": "현재 화면에 적용된 서식이 반영되게끔해",
}
TOP_CHECK_CHOICES = {
    "Q-1": (
        "(가) 단계가 낮은 칸부터 걷는다 — 같은 단계면 오래된 칸부터."
        " 앱 전체 알림창 동작이 바뀝니다(UI-NTF-01)"
    ),
    "Q-2": "(가) 켬 그대로 — 지금 동작 · Guide 와 같음",
    "Q-3": "(가) 칩 · 판도 그 화면 글자로 — Space 에서는 원본명(한 화면 한 이름, UI-CON-02)",
    "Q-4": "(가) 상태 알림으로 — 필요 단축 일정 · 가용설비 Static 대비 일정의 같은 표지와 같은 꼴",
    "Q-5": (
        "(가) 배지 줄을 걷고 탭 표지 · 사이드바만 남긴다 — 동료 모듈 코드는 그대로 돌고,"
        " 모듈 지침서 · 창구 설명이 바뀜"
    ),
    "Q-6": "(가) T7 처럼 탭 표지 · 팝오버로 옮긴다 — 표는 팝오버 안, 수는 표지로",
    "Q-7": "(가) 처음 펼친 채 — 필요 단축 일정 조건 카드와 같은 꼴",
    "Q-8": "(가) 같은 줄 끝 ⓘ — 카드 맨 위 · 표 도구 줄이라 칸이 하나 늘어남",
    "Q-9": "(가) Guide 로 옮긴다 — 화면에 설명 글을 달지 않는 규칙대로",
    "Q-10": "(가) 그대로 — 알림의 「그 화면으로」 가 화면마다 다름",
    "Q-11": "(가) 이 보드 답과 함께 다음 묶음에서 입혀 같은 배포에 싣는다",
    "Q-12": "(가) 받는다 — 팝업 · 확인 창 셋은 이름 줄 그대로",
    "Q-13": "(가) 그대로 — 규칙집 4장 기대값을 199 · 192.6 으로 확정",
    "Q-14": (
        "(나) 한 줄로 — 「선택 해제 · 선택 행 삭제」 를 메뉴 하나로 묶거나 단추를 아이콘만으로"
    ),
    "Q-15": "(가) 받는다",
    "Q-16": "(가) 받는다",
    "Q-17": "(가) 받는다",
    "Q-18": "(가) 받는다",
    "Q-19": "(가) 받는다",
    "Q-20": "(가) 지금대로",
    "Q-21": "(가) 그대로",
    "Q-22": "(가) 그대로",
    "Q-23": "(가) 맞다 — 그대로",
}


def test_the_top_check_board_is_recorded_with_its_three_readings() -> None:
    """v1.13 — 6-13 은 고침 그림 넷 · 괜찮음 그림 한 줄(마흔) · 물음 스물셋이고, 고른 글은 선택지
    원문 그대로 · 고침 칸에는 메모 원문이 있다. 답끼리 엇갈려 앱 세션이 밝힌 해석 셋((가) 그림
    메모 셋은 세 화면에만 · (나) 엑셀은 표준 라이브러리 · (다) Q-14 는 메뉴 하나)은 그 답 원문 곁에
    있다. 답이 규칙 글로 들어갔는지 핵심만 본다 — 넘침 차례(UI-NTF-01), 「내용 바뀜」 · 「닫힌 것
    숨김」(UI-NTF-02), 모드 전환 ⓘ(UI-LAY-02), 메모 안내 글 근거 꼬리표(UI-TXT-01)."""
    document = _text()
    assert "판 v1.13" in document.split("\n## 1. ")[0]
    assert "- **v1.13 — 2026-11-10.**" in _chapter(document, 8)

    section = _chapter(document, 6)
    board = section[section.index("\n### 6-13. ") :]
    lines = [line for line in board.splitlines() if line.startswith("- ")]
    known = {rule.id for rule in _rules()}
    found: dict[str, str] = {}
    for line in lines:
        match = re.match(r"^- ([\w-]+) · .+ → \*\*([^*]+)\*\*.*\((2026-11-10) · ([^()]+)\)$", line)
        assert match, line
        found[match.group(1)] = match.group(2)
        cited = RULE_TOKEN.findall(match.group(4))
        assert cited and set(cited) <= known, line
    assert list(found) == [*TOP_CHECK_PICTURE_MEMOS, "pictures-ok", *TOP_CHECK_CHOICES]
    for key in TOP_CHECK_PICTURE_MEMOS:
        assert found[key] == "고친다", key
    assert found["pictures-ok"] == "괜찮음"
    for key, answer in TOP_CHECK_CHOICES.items():
        assert found[key] == answer, key
    by_id = {line.split(" · ", 1)[0][2:]: line for line in lines}
    for key, memo in TOP_CHECK_PICTURE_MEMOS.items():
        assert memo in by_id[key], key
    assert "그림 40칸" in by_id["pictures-ok"]
    for key in ("admin-rename", "admin-order", "eq-pref", "Q-13"):
        assert "해석 (가)" in by_id[key], key
    assert "해석 (나)" in by_id["c2-picked"]
    assert "해석 (다)" in by_id["Q-14"]
    assert "2026-10-15 사용자 결정 4" in by_id["c2-picked"]
    assert "정정" in by_id["Q-2"]
    assert "사용자 수락 11-10 Q-12" in by_id["Q-12"]

    rules = {rule.id: rule for rule in _rules()}
    assert "단계가 가장 낮은 칸부터" in rules["UI-NTF-01"].text
    assert "앱 전체 회차로 닫는다" in rules["UI-NTF-01"].text
    assert "내용 바뀜" in rules["UI-NTF-02"].text
    assert "닫힌 것 숨김" in rules["UI-NTF-02"].text
    assert "Q-8" in rules["UI-LAY-02"].fields["예외"][0]
    assert "사용자 수락 11-10 Q-12" in rules["UI-TXT-01"].fields["예외"][0]
    assert "2026-10-15 사용자 결정 4" in _chapter(document, 7)
    values = _chapter(document, 4)
    for name in ("표 도구 막대 자리", "공정 Capa 상세 표 도구 줄", "폼 안 알림 칸", "상단 띠"):
        assert any(line.startswith(f"| {name} |") for line in values.splitlines()), name
