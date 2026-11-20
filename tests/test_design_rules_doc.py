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
글 · 메모 원문 · 해석 셋(v1.13) · 2차 검수 보드 · 밤샘 다 물음 줄과 고른 글 · 갈래 수 · 답 밖
줄(v1.14) · 「권장대로 반영 결과」 보드 줄과 고른 글 · 고칠 것 메모 원문 · 닫힌 따라온 물음(v1.15) ·
「남은 물음 11-11」 보드 줄과 고른 글 · 고친 줄 커밋 · 메모 해석(v1.16) · 입력 점검 시안 보드 줄과
고른 글 · 앱 세션이 정한 줄(v1.17) · 「다음 배포 물음 11-11」 보드 줄과 고른 글 · 고친 줄 커밋 ·
메모(v1.18) · 사내 리뷰 202611111500 보드 줄과 고른 글 · 고친 줄 커밋 · 메모 · 다시 물음 답(v1.19) ·
「배포 뒤 할 일 넷」 시안 보드 줄과 고른 글 · 메모 · 권장과 다른 답 · 커밋 · 예외(v1.20) ·
「남은 물음 11-12」 보드 줄과 고른 글 · 고친 줄 커밋 · 권장과 다른 답 · 가린 메모(v1.21) ·
문서 안팎의 id 참조 · 그물 경로 · 진입 문서(AGENTS · CLAUDE.md · README)의 연결.
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
}
# rule-notes 가운데 2026-11-12 Space 보드 답 1-4(「캔버스 편집」 팝업 걷기)로 거둔 칸 — 예외에서
# 빠진다.
WITHDRAWN_RULE_NOTES = {"UI-LAY-12": "rule-notes g6-23", "UI-STA-06": "rule-notes g6-29"}
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
    핵심만 본다 — v4: UI-INP-03 은 MUST. v2: 확인 체크를 남기는 저장은 UI-NTF-09 예외(v3
    「알고 저장」 은 2026-11-12 Space 보드 답 1-4 로 걷음). v7: 일정 글 칸은 UI-INP-03 예외.
    v8: 입력 빠짐 멈춤도 마크 + 「그 화면으로」. v9: placeholder 는 창 안 글. v10: 충돌 보고는
    자리에 두는 갈래가 아니다. v5: 제안 값 넷은 확정이다. 답이 왔으므로 규칙 칸에 「답 대기」 가
    남지 않는다."""
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
    # v3 의 「이탈 호기 n대 알고 저장」 은 2026-11-12 Space 보드 답 1-4 로 그 팝업과 함께 걷었다 —
    # 확인 체크를 남기는 저장은 시뮬레이션 사이드바 하나다.
    assert "이탈 호기 n대 알고 저장" not in exceptions
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
    assert "Admin 표시순서" in rules["UI-INP-08"].fields["범위"][0]
    exceptions = rules["UI-INP-08"].fields["예외"][0]
    # 라벨을 보이는 창 「둘」 은 v1.37 에 하나가 되었다(접속 명단 추가 창을 편집 표로 걷음).
    assert "표 상자" in exceptions and "라벨을 보이는 창은" in exceptions
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
    # Space 캔버스 크기의 두 자리(g6-23)와 한 번에 끝나는 크기 창(g6-29)은 「캔버스 편집」 팝업을
    # 걷어 거뒀다(2026-11-12 Space 보드 답 1-4) — 캔버스는 배치 편집 왼쪽 칸 「캔버스」 한 자리다.
    for rule_id, tag in WITHDRAWN_RULE_NOTES.items():
        assert tag not in rules[rule_id].fields["예외"][0], rule_id
        assert "캔버스 편집" not in rules[rule_id].fields["예외"][0], rule_id
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
    assert "- **v1.13 — 2026-11-10.**" in _chapter(document, 8)

    section = _chapter(document, 6)
    board = section[section.index("\n### 6-13. ") : section.index("\n### 6-14. ")]
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


# 2026-11-10 밤 2차 검수 보드 · 밤샘 다 물음(6-14)의 답 — 「전부 권장대로」. 보드 물음은 답할 때
# 있던 27 이 권장 원문 그대로이고, 답 뒤에 더해진 셋(Q2-1 · Q2-4 · Q2-9)은 열린 물음, 권장이 없는
# Q2-6 은 사용자 실기 확인이다. 반영 13 · 그대로 12 · 규칙집 예외 1 로 가른다.
SECOND_CHECK_REFLECTED = {
    "Q2-2": "셋과 같게 줄인다 — 같은 꼴 같은 간격",
    "Q2-7": (
        "내려받기 둘을 「내려받기 ▾」 메뉴 하나(이 공정 단축 일정 CSV · 시트 엑셀)로 묶어 한 줄"
    ),
    "Q2-8": (
        "맨 아래 정리 줄 「필요 단축 일정에서 전체 공정·진척 비교 보기」 를 일정 부족 달이 있는"
        " 공정에도 세운다 — 그 카드에서 온 방문만 뺌, 위 띠는 그대로"
    ),
    "Q2-13": "상태 알림으로 보낸다 — 입력 비가동 CS-05 와 같은 꼴, 새 알림 코드",
    "Q2-14": "Guide 로 옮긴다 — 제약 영향 그래프 · 계산표와 같은 꼴",
    "Q2-17": "탭 풍선도 그 화면 글자로 — Space 탭은 원본",
    "Q2-18": "칩 · 판 · 풍선은 늘 그 화면 글자로 — 표시명 화면은 그 화면 표시명",
    "Q2-24": "Guide 로 옮기고 카드에는 제목과 목록만 남긴다 — 설명 글 규칙(UI-TXT-01)대로",
    "Q2-26": "필요 단축 일정도 조회 조건 패널 줄(값 칸 + 팝업)로 — 진척 비교는 카드에 그대로",
    "Q2-27": (
        "경로 표처럼 「「PKG PLAN」 표가 비어 계산이 멈춥니다 — 원천을 고쳐 다시 등록하세요.」"
        " 로 맞춘다"
    ),
    "Q2-28": "같은 잠긴 줄 「계산 멈춤」 으로 자리를 지킨다",
    "Q2-29": "설비 시나리오 줄도 정상 회차처럼 세운다 — 잠그지 않음, 다른 시나리오로 옮기는 길",
    "Q2-30": "푸는 길이 원천 다시 등록이면 끝 꼬리를 「…은 남겼습니다」 까지만 쓴다",
}
SECOND_CHECK_KEPT = {
    "Q2-3": "그대로 — 모든 저장 폼이 같은 테두리 꼴",
    "Q2-5": "받는다",
    "Q2-10": "화면 그대로 — 30대까지(더 보기를 켜면 모두)",
    "Q2-11": "그대로 — 결정 기록을 따름",
    "Q2-12": "지금대로 — 칩 · 전환 바로 뒤",
    "Q2-15": (
        "「확인 필요」 그대로 — 같은 띠 글 · 같은 「가용 넘침」 꼬리를 쓰는 RS-05 와 같은 단계"
    ),
    "Q2-16": "그대로 — 지난 보드 Q-1 답대로",
    "Q2-19": "「선택」 그대로 받는다",
    "Q2-20": "받는다 — 막대가 단추를 덮지 않는 쪽",
    "Q2-21": "받는다 — 지금대로",
    "Q2-22": "지금대로 — 닫힌 채 세 수가 보이고, 사내 런북 4-7 화면 확인이 이 글을 그대로 읽음",
    "Q2-25": "그대로 — 단추 차례를 읽는 값 줄로 본다",
}
SECOND_CHECK_EXCEPTION = {"Q2-23": "지금대로 — 규칙집에 예외로 적는다"}
SECOND_CHECK_OPEN = ("Q2-1", "Q2-4", "Q2-9")
NIGHT_DA_ANSWERS = {
    "다-0": "(가) 다음 배포는 1차만, 2차는 사내 사용 뒤",
    "다-1": "권장대로",
    "다-2": (
        "① 일정 리비전에 실음 ② 복제 · 발행 때 따라감 ③ 모든 시나리오에 복사 ④ 주차별에서는 안 뺌"
        " ⑤ 다음 배포 뒤 착수"
    ),
    "다-3": (
        "① 느린 둘째 누름 조용히 거름 ② BDQ 지금대로 ③ scripts 조사 그물 넓히고 고침 ④ 선행 B/O ·"
        " Past Data · 선행 입고 공용 프로필 유지 · 방침 거둠 ⑤ 이름 꾸밈 지금대로"
    ),
    "다-4": "① 시안 그림 보드 먼저 ② 리비전 저장 · 등록 때 원천 파일 이름 · 수정 시각 · 해시만",
}


def test_the_second_check_board_and_the_night_answers_are_recorded() -> None:
    """v1.14 — 6-14 는 보드 물음 Q2-1 ~ Q2-30 이 차례대로 한 줄씩이고 다 물음 다섯이 그 뒤다.
    고른 글은 보드 권장 원문 그대로(반영 13 · 그대로 12 · 규칙집 예외 1), 답 뒤에 생긴 셋은
    「열린 물음」, Q2-6 은 「사용자 실기 확인 대기」 다. 반영 줄은 커밋을 든다. Q2-24 의 답 밖
    목록 줄과 Q2-23 의 예외 글(UI-LAY-13), 뒤집힌 옛 결정 둘(다-3 ④ · bottom-row → Q2-8)이
    문서에 있다."""
    document = _text()
    assert "- **v1.14 — 2026-11-11.**" in _chapter(document, 8)

    section = _chapter(document, 6)
    board = section[section.index("\n### 6-14. ") : section.index("\n### 6-15. ")]
    assert "https://claude.ai/artifact/GABcdxkXpoLAxUqGALsr26" in board
    assert "「전부 권장대로」" in board
    lines = [line for line in board.splitlines() if line.startswith("- ")]
    known = {rule.id for rule in _rules()}
    found: dict[str, str] = {}
    for line in lines:
        match = re.match(r"^- ([\w-]+) · .+ → \*\*([^*]+)\*\*.*\((2026-11-10) · ([^()]+)\)$", line)
        assert match, line
        found[match.group(1)] = match.group(2)
        cited = RULE_TOKEN.findall(match.group(4))
        assert cited and set(cited) <= known, line
    assert list(found) == [*(f"Q2-{n}" for n in range(1, 31)), *NIGHT_DA_ANSWERS]
    chosen = {**SECOND_CHECK_REFLECTED, **SECOND_CHECK_KEPT, **SECOND_CHECK_EXCEPTION}
    assert len(SECOND_CHECK_REFLECTED) == 13 and len(SECOND_CHECK_KEPT) == 12
    for key, answer in {**chosen, **NIGHT_DA_ANSWERS}.items():
        assert found[key] == answer, key
    for key in SECOND_CHECK_OPEN:
        assert found[key] == "열린 물음", key
    assert found["Q2-6"] == "사용자 실기 확인 대기"
    assert len(chosen) + len(SECOND_CHECK_OPEN) + 1 == 30

    by_id = {line.split(" · ", 1)[0][2:]: line for line in lines}
    for key in SECOND_CHECK_REFLECTED:
        assert re.search(r"커밋 `[0-9a-f]{7}`", by_id[key]), key
    assert "a1ee769" in by_id["Q2-24"] and "답 밖" in by_id["Q2-24"]
    rules = {rule.id: rule for rule in _rules()}
    assert "Q2-23" in rules["UI-LAY-13"].fields["예외"][0]
    assert SECOND_CHECK_EXCEPTION["Q2-23"] in rules["UI-LAY-13"].fields["예외"][0]
    reversed_ = _chapter(document, 7)
    for phrase in ("다-3 ④", "Q2-8", "bottom-row"):
        assert phrase in reversed_, phrase


# 2026-11-11 「권장대로 반영 결과」 보드(6-15)의 답 — 줄 44 가운데 43 「좋음」 · Q2-26 「고칠 것」.
# 「좋음」 은 카드에 보인 지금 꼴을 받은 것으로 읽어 답 밖 표지와 권장이 「그대로」 인 따라온 물음이
# 닫혔다. 권장이 지금 꼴을 바꾸는 물음은 열린 채라 여기 줄이 없다(docs/TODO.md 4장).
RESULT_BOARD_MEMO = "목표 확보율 5개 프리셋 외에 직접 입력도 가능하도록 수정"
RESULT_BOARD_ANSWERS = {
    "rows-ok": "좋음",
    "Q2-26": "고칠 것",
    "Q2-1": "좋음 — 지금 꼴 14px",
    "Q2-6": "「복구」 창 없음 — 견본 11개",
    "bdq-guard": "(가) 지금은 둔다",
    "home-bar": "(가) 받는다",
    "one-button": "(가) 그대로",
    "units-xlsx": "(가) 그대로",
    "beyond-wide": "그대로",
    "cs06-scope": "(가) 리비전만",
    "cs06-when": "(가) 늘",
    "clash": "(가) 이대로",
    "master-tab": "(가) 페이지 단위 그대로",
    "q224-list": "(가) 그대로",
    "q230-tail": "(가) 지금대로",
}


def test_the_result_board_answers_are_recorded_and_the_fix_is_in_the_rules() -> None:
    """v1.15 — 6-15 는 「좋음」 한 줄(43) · 「고칠 것」 Q2-26(메모 원문 · 커밋) · Q2-1 · Q2-6 실기 ·
    닫힌 줄 열하나가 차례대로 한 줄씩이다. 고칠 것은 UI-LAY-02 예외 · UI-INP-05 근거 · 6-14 Q2-26
    밑 들여쓴 줄에 들고, 6-14 의 다른 줄은 그때 기록 그대로다(앞 시험이 본다)."""
    document = _text()
    assert "- **v1.15 — 2026-11-11.**" in _chapter(document, 8)

    section = _chapter(document, 6)
    board = section[section.index("\n### 6-15. ") : section.index("\n### 6-16. ")]
    assert "https://claude.ai/artifact/QNkbQ4RA3brfurDztUevCN" in board
    lines = [line for line in board.splitlines() if line.startswith("- ")]
    known = {rule.id for rule in _rules()}
    found: dict[str, str] = {}
    for line in lines:
        match = re.match(r"^- ([\w-]+) · .+ → \*\*([^*]+)\*\*.*\((2026-11-11) · ([^()]+)\)$", line)
        assert match, line
        found[match.group(1)] = match.group(2)
        cited = RULE_TOKEN.findall(match.group(4))
        assert cited and set(cited) <= known, line
    assert list(found.items()) == list(RESULT_BOARD_ANSWERS.items())

    by_id = {line.split(" · ", 1)[0][2:]: line for line in lines}
    assert "줄 43" in by_id["rows-ok"]
    assert RESULT_BOARD_MEMO in by_id["Q2-26"]
    assert re.search(r"커밋 `[0-9a-f]{7}`", by_id["Q2-26"])
    rules = {rule.id: rule for rule in _rules()}
    assert "직접 입력" in rules["UI-LAY-02"].fields["예외"][0]
    assert RESULT_BOARD_MEMO in rules["UI-INP-05"].fields["근거"][0]
    earlier = section[section.index("\n### 6-14. ") : section.index("\n### 6-15. ")]
    assert "\n  - 2026-11-11 사용자 고칠 것 — 직접 입력" in earlier


# 2026-11-11 「남은 물음 11-11」 보드(6-16)의 답 — 카드 스물, 고른 선택지는 모두 카드
# 권장이다. 고친 열은 갈래 셋(`night/board-a-1111` · `night/board-b-1111` ·
# `night/board-c-1111`)이 입혔고, 그대로 일곱은 코드 · 규칙 글을 바꾸지 않았다. D8 은
# 선택지 없는 메모 카드라 메모 원문이 고른 글이다.
REMAINING_BOARD_ADDRESS = "https://claude.ai/artifact/8QQvnxf6SypbaezyGKNjBF"
REMAINING_BOARD_FIXED = {
    "Q226-stepper": (
        "(나) 이 팝업 숫자 칸만 − · + · ⊗ 를 숨기고 Enter · 칸 떠남으로만 적용 — ↑/↓ 키는 그대로"
        " 한 걸음 적용"
    ),
    "B2": "(가) 예를 짧게 — 「표시순서 변경」 · 「26.07 PM 1.5대」",
    "B3": "(가) 두 파일 이름 끝에 공정 이름을 붙인다",
    "C1": "(가) 공정 Capa 상세 Q2-29 처럼 잠그지 않고 세움",
    "C9": "(나) render_download_pair 한 곳에서 같은 높이",
    "D1": '(나) 모두 통째로 내려가는 꼴("push")로 — 좁으면 통째로 내려가고 접히지 않음',
    "D2": (
        "(가) e4-1 처럼 전환 줄 오른쪽 끝 칸에 작은 글로 — 표지 둘이 함께 서면 1100 창에서 접히는지"
        " 다시 잼"
    ),
    "D3": "(나) 아이콘을 붙임(한 줄)",
    "D4": (
        "(나) 그 회차에 알림창 사건을 한 번 냄(알림 단계 · Alarm 기록 — 예 「보던 기준선 「…」 이"
        " 지워져 진척 비교를 껐습니다」), 화면 자리에는 글을 달지 않음"
    ),
    "D6": "(다) 앞을 줄이고 이름 끝(호기 번호)을 남기는 말줄임",
}
REMAINING_BOARD_KEPT = {
    "Q226-csv": "(가) 그대로",
    "Q226-baseline": "(가) 그대로",
    "Q226-compare": "(가) 그대로",
    "C3": "(가) 그대로",
    "C10": "(가) 그대로",
    "D5": "(가) 지금대로",
    "D7": "(가) 지금대로",
}
REMAINING_BOARD_ORDER = (
    "Q2-26-fix",
    "Q226-csv",
    "Q226-baseline",
    "Q226-compare",
    "Q226-stepper",
    "B2",
    "B3",
    "C1",
    "C3",
    "C6",
    "C9",
    "C10",
    "D1",
    "D2",
    "D3",
    "D4",
    "D5",
    "D6",
    "D7",
    "D8",
)
REMAINING_BOARD_LATER = (
    "(가) CSV 와 시트 엑셀 하나를 「내려받기 ▾」 메뉴로 — 공정 공유 2차를 합친 뒤"
)


def test_the_remaining_questions_board_answers_are_recorded() -> None:
    """v1.16 — 6-16 은 보드 카드 스물이 보드 차례대로 한 줄씩이고 고른 글은 선택지
    원문이다. 고친 열 줄은 커밋을 들고, 그대로 일곱 · C6(공정 공유 2차를 합친 뒤) ·
    D8(메모)은 커밋이 없다. D8 은 메모 원문 「권장대로」 를 「D7 과 한 번에 — 지금대로」
    로 읽은 것을 밝힌다. 6-15 줄은 그때 기록 그대로다(앞 시험이 6-16 앞에서 끊어 본다).
    6-17 은 뒤 시험이 본다."""
    document = _text()
    assert "- **v1.16 — 2026-11-11.**" in _chapter(document, 8)
    assert "보드의 답은 6-16 에" in _chapter(document, 1)

    section = _chapter(document, 6)
    board = section[section.index("\n### 6-16. ") : section.index("\n### 6-17. ")]
    assert REMAINING_BOARD_ADDRESS in board
    lines = [line for line in board.splitlines() if line.startswith("- ")]
    known = {rule.id for rule in _rules()}
    found: dict[str, str] = {}
    for line in lines:
        match = re.match(r"^- ([\w-]+) · .+ → \*\*([^*]+)\*\*.*\((2026-11-11) · ([^()]+)\)$", line)
        assert match, line
        found[match.group(1)] = match.group(2)
        cited = RULE_TOKEN.findall(match.group(4))
        assert cited and set(cited) <= known, line
    assert tuple(found) == REMAINING_BOARD_ORDER
    assert len(REMAINING_BOARD_FIXED) == 10 and len(REMAINING_BOARD_KEPT) == 7
    for key, answer in {**REMAINING_BOARD_FIXED, **REMAINING_BOARD_KEPT}.items():
        assert found[key] == answer, key
    assert found["Q2-26-fix"] == "좋음"
    assert found["C6"] == REMAINING_BOARD_LATER
    assert found["D8"] == "메모 「권장대로」"

    by_id = {line.split(" · ", 1)[0][2:]: line for line in lines}
    commit = re.compile(r"커밋 `[0-9a-f]{7}`")
    for key in (*REMAINING_BOARD_FIXED, "Q2-26-fix"):
        assert commit.search(by_id[key]), key
    for key in (*REMAINING_BOARD_KEPT, "C6", "D8"):
        assert not commit.search(by_id[key]), key
    assert "「D7 과 한 번에 — 지금대로」" in by_id["D8"]
    assert "pp2 합친 뒤 할 일" in by_id["C6"]


# 2026-11-11 입력 점검 시안 보드(6-17)의 답 — q1 ~ q7 모두 권장 (가)이고, 조사 뒤 더한 답
# 하나(reg-rows)가 있다. 고른 글은 보드 선택지 원문 그대로다. 그 뒤 `ic-` 줄은 답이 말하지 않아
# 앱 세션이 정한 작은 결정이다(사용자 답이 아니다).
INPUT_CHECK_CHOICES = {
    "q1": "(가) 시나리오 관리 › 목록 관리 오른쪽 칸 「점검」",
    "q2": "빠진 행 네 묶음 + 계산 멈춤 까닭 + 측정률 1.0 가정 + 등록 때 뺀 원천 행 수",
    "q3": "맨 아래 접힌 한 줄에 수만 — 펼치면 행",
    "q4": "묶음마다 「그 화면으로」 하나 — Alarm 줄과 같은 꼴, 그 표 · 종류 단추까지 연다",
    "q5": "리비전 전체 기간 — 저장 · 공식 지정 검사와 같은 셈",
    "q6": "고른 리비전만 그때 센다 — 이번에 센 것만 채우고 나머지는 「—」",
    "q7": "새 자리로 합치고 탭은 걷는다",
    "reg-rows": "다른 묶음과 같은 꼴 — 수 + 「행 보기」 · CSV",
}
INPUT_CHECK_DECIDED = tuple(f"ic-{n}" for n in range(1, 14))


def test_the_input_check_board_is_recorded_with_the_app_decisions() -> None:
    """v1.17 — 6-17 은 입력 점검 시안 보드 물음 q1 ~ q7 과 조사 뒤 더한 답(reg-rows)이 차례대로
    한 줄씩이고 고른 글은 보드 선택지 원문 그대로다(답 줄은 커밋을 든다). 그 뒤 `ic-` 줄은 앱
    세션이 정한 작은 결정이라 줄마다 그렇게 밝힌다. q4 는 UI-TXT-03 예외 칸에, q7 이 뒤집은 옛
    결정 셋(2026-10-19 Admin 탭 · T7 수 표지 · Q-19)은 7-1 에, 펼친 표 칸은 4장에 있다. 6-18 은 뒤
    시험이 본다."""
    document = _text()
    assert "- **v1.17 — 2026-11-11.**" in _chapter(document, 8)
    assert "등록 행 보기)은 6-17 에" in _chapter(document, 1)

    section = _chapter(document, 6)
    board = section[section.index("\n### 6-17. ") : section.index("\n### 6-18. ")]
    assert "https://claude.ai/artifact/27hDnALn8KGm3zR4opa4PE" in board
    lines = [line for line in board.splitlines() if line.startswith("- ")]
    known = {rule.id for rule in _rules()}
    found: dict[str, str] = {}
    for line in lines:
        match = re.match(r"^- ([\w-]+) · .+ → \*\*([^*]+)\*\*.*\((2026-11-11) · ([^()]+)\)$", line)
        assert match, line
        found[match.group(1)] = match.group(2)
        cited = RULE_TOKEN.findall(match.group(4))
        assert cited and set(cited) <= known, line
    assert list(found) == [*INPUT_CHECK_CHOICES, *INPUT_CHECK_DECIDED]
    for key, answer in INPUT_CHECK_CHOICES.items():
        assert found[key] == answer, key
    by_id = {line.split(" · ", 1)[0][2:]: line for line in lines}
    for key in INPUT_CHECK_CHOICES:
        assert re.search(r"커밋 `[0-9a-f]{7}`", by_id[key]), key
        assert "앱 세션이 정함" not in by_id[key], key
    for key in INPUT_CHECK_DECIDED:
        assert "앱 세션이 정함" in by_id[key], key

    rules = {rule.id: rule for rule in _rules()}
    exception = rules["UI-TXT-03"].fields["예외"][0]
    assert "q4" in exception and "「그 화면으로」" in exception
    assert "「점검」 칸" in rules["UI-NTF-05"].text
    values = _chapter(document, 4)
    assert any(line.startswith("| 점검 표 앞 다섯 칸 |") for line in values.splitlines())
    reversed_ = _chapter(document, 7)
    for phrase in ("q7 (가)로 탭을 걷음", "T7 (가)", "Q-19 (가)"):
        assert phrase in reversed_, phrase


# 2026-11-11 「다음 배포 물음 11-11」 보드(6-18)의 답 — 카드 열아홉, 고른 선택지는 모두 카드
# 권장이다. 고친 여섯은 갈래 넷(`night/nq-dl-1111` · `night/nq-gap-1111` · `night/nq-goto-1111` ·
# `night/nq-stop-1111`)이 입혔고, 그대로 · 기록만 열셋은 코드 · 규칙 글을 바꾸지 않았다. D6 뒤 ② 는
# 선택지 없는 메모 카드라 메모 원문이 고른 글이다. 줄 id 는 보드 카드 id 다.
NEXT_BOARD_ADDRESS = "https://claude.ai/artifact/VB98KF7QZBgHfvMxFEBcPt"
NEXT_BOARD_FIXED = {
    "n-c9-row": (
        "(나) 표 제목 줄 높이를 35 로 고정하고 메뉴만 28 — 두 흔들림이 다 없어지고 표 윗선은"
        " 바탕과 같은 210.5"
    ),
    "n-b3-clash": "(나) 겹친 표시명이면 칩 · 판처럼 「표시명 (원본)」 꼴(Q2-18)",
    "n-d2-menu": (
        "(나) 두 표지 모두 짧은 표지 + 풍선(예 「한쪽 공정 · GAP 없음 ⓘ」 · 「호기 필터 ⓘ」 —"
        " 까닭 · 고른 값 · 호기 수는 풍선)"
    ),
    "n-f4-target": (
        "(a) 줄이 리비전을 들고 가고 누를 때만 고른다 — ① · ② 를 한 길로 풂(누름이 서버로 오는"
        " 길을 새로 냄)"
    ),
    "n-space-stop": "(다) F7 꼴 + 원본 공정명 — 「예시 27.04 TC Bonding 양산」, D10 그대로",
    "n-f7-clash": "(나) 공용 표시명 규칙 전체의 원본과 겹치면 「표시명 (원본)」",
}
NEXT_BOARD_KEPT = {
    "n-d6-wide": "(가) 그대로 — 같은 이름은 같은 꼴(PRC-01)",
    "n-d6-name": "메모 「대부분 끝 글자로 갈림」",
    "n-rs06": "(가) 그대로 — 앱 공통 꼴",
    "n-d2-gap": "(가) 그대로 — 내려간 줄 위 빈 틈이 줄어듦",
    "n-d1-820": "(가) 그대로 — 820 은 기준 창 밖",
    "n-f2-slack": "(나) 지금대로 — 값 줄에만 적고, 사내 글꼴에서 두 줄이면 리뷰에 적어 다시 물음",
    "n-f7-rest": "(가) 지금대로",
    "n-f7-beyond": "받음 — 지금 꼴 그대로",
    "n-autolog": "(가) 지금대로 — 기록은 원문",
    "n-summary": "(가) 지금대로",
    "n-runbook": "(가) 다음 배포 7장을 쓸 때 둘 다 넣음",
    "n-f9-draft": "(가) 초안 그대로",
    "n-handoff": "(가) 다음 배포 준비 때 HANDOFF 를 새로 쓰며 함께",
}
NEXT_BOARD_ORDER = (
    "n-c9-row",
    "n-b3-clash",
    "n-d6-wide",
    "n-d6-name",
    "n-rs06",
    "n-d2-menu",
    "n-d2-gap",
    "n-d1-820",
    "n-f4-target",
    "n-f2-slack",
    "n-space-stop",
    "n-f7-rest",
    "n-f7-clash",
    "n-f7-beyond",
    "n-autolog",
    "n-summary",
    "n-runbook",
    "n-f9-draft",
    "n-handoff",
)


def test_the_next_deploy_questions_board_answers_are_recorded() -> None:
    """v1.18 — 6-18 은 「다음 배포 물음 11-11」 보드 카드 열아홉이 보드 차례대로 한 줄씩이고
    고른 글은 선택지 원문이다(D6 뒤 ② 는 메모 원문). 고친 여섯 줄은 커밋을 들고, 그대로 · 기록만
    열셋은 커밋이 없다. F2 뒤 (나) 는 사내 글꼴에서 다시 물을 자리(TODO 4장)를 가리키고, 앱 세션이
    답을 읽은 셋은 줄에 밝힌다. 6-17 줄은 그때 기록 그대로다(앞 시험이 6-18 앞에서 끊어 본다).
    6-19 는 뒤 시험이 본다."""
    document = _text()
    assert "- **v1.18 — 2026-11-11.**" in _chapter(document, 8)
    assert "보드의 답은 6-18 에" in _chapter(document, 1)

    section = _chapter(document, 6)
    board = section[section.index("\n### 6-18. ") : section.index("\n### 6-19. ")]
    assert NEXT_BOARD_ADDRESS in board
    lines = [line for line in board.splitlines() if line.startswith("- ")]
    known = {rule.id for rule in _rules()}
    found: dict[str, str] = {}
    for line in lines:
        match = re.match(r"^- ([\w-]+) · .+ → \*\*([^*]+)\*\*.*\((2026-11-11) · ([^()]+)\)$", line)
        assert match, line
        found[match.group(1)] = match.group(2)
        cited = RULE_TOKEN.findall(match.group(4))
        assert cited and set(cited) <= known, line
    assert tuple(found) == NEXT_BOARD_ORDER
    assert len(NEXT_BOARD_FIXED) == 6 and len(NEXT_BOARD_KEPT) == 13
    for key, answer in {**NEXT_BOARD_FIXED, **NEXT_BOARD_KEPT}.items():
        assert found[key] == answer, key

    by_id = {line.split(" · ", 1)[0][2:]: line for line in lines}
    commit = re.compile(r"커밋 `[0-9a-f]{7}`")
    for key in NEXT_BOARD_FIXED:
        assert commit.search(by_id[key]), key
    for key in NEXT_BOARD_KEPT:
        assert not commit.search(by_id[key]), key
    for key in ("n-d6-name", "n-f4-target", "n-f7-clash"):
        assert "앱 세션 해석 — 밝힘" in by_id[key], key
    assert "`docs/TODO.md` 4장" in by_id["n-f2-slack"]
    assert "`docs/TODO.md` 2장" in by_id["n-runbook"]


# 2026-11-11 ~ 12 사내 리뷰 202611111500 보드(6-19)의 답 — 카드 마흔하나(C1 ~ C9 · N1 ~ N13 ·
# R1 ~ R10 · G1 ~ G9). 고른 선택지 스물아홉은 모두 카드 권장이고, 메모 카드 다섯은 메모 원문이 고른
# 글이다. 메모로 되물은 다섯과 빈칸이던 G1 은 다시 물어 그 물음의 권장을 받았다(「다시 물음 답」).
# 고친 열다섯은 갈래(`night/noread-1111` · `night/rv-*-1112`)의 커밋을 들고, 문서 한 줄 · 7장 초안 ·
# 기록만인 스물여섯은 커밋이 없다. C1 ~ C8 은 2026-11-11 밤, 나머지는 2026-11-12 새벽 답이다.
# 줄 id 는 보드 카드 id 다.
REVIEW_1500_ADDRESS = "https://claude.ai/artifact/Wm2johykyy7eaRQ6Dsn6Lf"
REVIEW_1500_FIXED = {
    "f-key": (
        "(가) 이번은 그대로 — 다음 7장 · objectstore 2장에 「키를 다시 발급하면 두 곳을 함께"
        " 바꾼다」 한 줄"
    ),
    "f-merge": "메모 「막혀서가 아니고 Squash를 몰랐음」",
    "x-port": "(가) 그 시험만 Windows 에서 건너뛴다",
    "x-tests": "(가) 싣고 Windows CI 조각 1 · 5 · 7 결론으로 확인",
    "x-proxy": (
        "(가) tests/conftest.py 에 NO_PROXY 로 127.0.0.1 · [::1] · localhost 를 더하는 공용"
        " 설정 하나"
    ),
    "x-upeh": "(가) A안 — 계산 쪽 멈춤에 꼴을 싣는다(반나절)",
    "x-c11": "(가) 다음 배포에서 「빈 칸 · 다른 표기」 두 수로 센다(값은 찍지 않음)",
    "x-tokdiag": "(가) 둘 다 — 짧은 토큰은 실패, invalid token 은 새 갈래 「토큰」",
    "x-tokrenew": ("(가) 사내 확인 여섯을 먼저 받고, 그 전에는 N7 고침과 토큰 실패 관리자 알림만"),
    "x-modwin": "다시 물음 답 「도우미 함수로」",
    "x-modenv": "다시 물음 답 「도우미 함수로」",
    "x-mods3": "다시 물음 답 「도우미 함수로」",
    "x-shard": (
        "(가) 실행기 고침(끝줄 · 캐시 · 조각별 임시 폴더) + 7장 선택 줄로 넷 꼴을 한 번 시험한"
        " 뒤 기본으로"
    ),
    "z-sync7": "다시 물음 답 「앱 · 런북 둘 다」",
    "g-d2-icon": "(가) 앞 아이콘을 뗀다 — 끝 풍선 ⓘ 하나",
}
REVIEW_1500_KEPT = {
    "f-syncmode": "메모 「local로 넣었음」",
    "f-doctor": "메모 「그랬던것 같은데 확실히 하기위해 사내 체크 리스트로 따로 뺴줘」",
    "f-filter": "(나) 모름 — 확인 없이 닫음(필요하면 조건 카드에서 다시 고름)",
    "f-admin": (
        "메모 「사내 BDQ 및 S3 토큰정보 배치 여부 확인을 위한 임시 수정이었음. 필요한거 다"
        " 진행했으니 더이상 체크안해도됨」"
    ),
    "f-ci6": "메모 「사내 체크리스트로 빼줘」",
    "f-fulltext": "(가) 다음 사내 세션에 한 줄로 받는다",
    "f-s33": "(가) 묻지 않고 꼴 이름 고침(N5)이 실린 다음 배포의 6-3 a 를 기다린다",
    "x-ci": "(가) 빌드 뒤 · 서피스 전달 전에 CI 끝을 확인 — 빨가면 전달 전에 알림",
    "x-awsdoc": (
        "(가) objectstore 문서에 「pod 에 HTTP(S)_PROXY 가 있으면 S3 주소를 NO_PROXY 에」 한 줄만"
    ),
    "z-push": ("(가) 결함 아님으로 닫고, 다음 7장에 「푸시 <언제>; CI/CD <언제>」 줄을 정식 키로"),
    "z-mem": "(가) 이관 전에 C-DEP 에서 HOME 첫 화면 시간을 한 번 재 보고 판단",
    "z-perm": "(가) 묻지 않고 닫는다 — 다음에도 「복사함」 이면 그때 대조 줄 수만 청함",
    "z-size": "(가) 청하지 않는다 — 이관 배포 7장에서 다시 잰다",
    "z-84u": "(가) 규칙 그대로 — 사내가 사용기준 칸을 채운다",
    "z-s27": "(가) 닫는다 — 앱은 고치지 않고, S27 을 쓸지 · 보관할지는 사내 몫",
    "z-d9": "다시 물음 답 「닫음(안내 안 붙임)」",
    "z-82lt": "(가) 청하지 않고, 다음 7장에 「8장 =<stamp> 로 접지 않는다」 를 못 박는다",
    "z-grid4": "(가) 지금대로 닫는다",
    "g-f7-scope": "다시 물음 답 「지금대로」",
    "g-f4-blocked": "(가) 대상째 버림 — 지금 그대로",
    "g-d6-read": "(가) 맞다",
    "g-b3-head": "(가) 그대로 — 파일 이름만 가름",
    "g-d2-static": "(가) 그대로 — 까닭은 풍선",
    "g-d2-1100": "(가) 그대로",
    "g-f4-gone": "(가) 지금대로 조용히 버림",
    "g-f2-runbook": "(가) 넣는다 — 「창 1283 · 목록 관리 오른쪽 칸 고르기 다섯이 한 줄인가」",
}
REVIEW_1500_ORDER = (
    *("f-syncmode", "f-key", "f-doctor", "f-filter", "f-admin", "f-merge", "f-ci6"),
    *("f-fulltext", "f-s33"),
    *("x-port", "x-tests", "x-proxy", "x-ci", "x-upeh", "x-c11", "x-tokdiag", "x-tokrenew"),
    *("x-modwin", "x-modenv", "x-mods3", "x-shard", "x-awsdoc"),
    *("z-push", "z-sync7", "z-mem", "z-perm", "z-size", "z-84u", "z-s27", "z-d9", "z-82lt"),
    "z-grid4",
    *("g-f7-scope", "g-f4-blocked", "g-d6-read", "g-b3-head", "g-d2-icon", "g-d2-static"),
    *("g-d2-1100", "g-f4-gone", "g-f2-runbook"),
)
# C1 ~ C8 — 2026-11-11 밤에 답한 카드.
REVIEW_1500_NIGHT = REVIEW_1500_ORDER[:8]


def test_the_review_1500_board_answers_are_recorded() -> None:
    """v1.19 — 6-19 는 사내 리뷰 202611111500 보드 카드 마흔하나가 보드 차례대로 한 줄씩이고
    고른 글은 선택지 원문(메모 카드는 메모 원문, 다시 물은 카드는 「다시 물음 답」)이다. 고친
    열다섯 줄은 커밋을 들고 나머지 스물여섯은 커밋이 없다. C1 ~ C8 은 2026-11-11 밤, 나머지는
    2026-11-12 답이다. 앱 세션이 답을 읽은 둘(C7 메모의 갈 곳 · R2 차례)은 줄에 밝히고, 바꾼 옛
    결정 셋은 7-1 에 있다. 6-18 줄은 그때 기록 그대로다(앞 시험이 6-19 앞에서 끊어 본다).
    6-20 은 뒤 시험이 본다."""
    document = _text()
    assert "- **v1.19 — 2026-11-12.**" in _chapter(document, 8)
    assert "보드의 답은 6-19 에" in _chapter(document, 1)

    section = _chapter(document, 6)
    board = section[section.index("\n### 6-19. ") : section.index("\n### 6-20. ")]
    assert REVIEW_1500_ADDRESS in board
    lines = [line for line in board.splitlines() if line.startswith("- ")]
    known = {rule.id for rule in _rules()}
    found: dict[str, str] = {}
    dates: dict[str, str] = {}
    for line in lines:
        match = re.match(
            r"^- ([\w-]+) · .+ → \*\*([^*]+)\*\*.*\((2026-11-1[12]) · ([^()]+)\)$", line
        )
        assert match, line
        found[match.group(1)] = match.group(2)
        dates[match.group(1)] = match.group(3)
        cited = RULE_TOKEN.findall(match.group(4))
        assert cited and set(cited) <= known, line
    assert tuple(found) == REVIEW_1500_ORDER
    assert len(REVIEW_1500_FIXED) == 15 and len(REVIEW_1500_KEPT) == 26
    assert set(REVIEW_1500_FIXED) | set(REVIEW_1500_KEPT) == set(REVIEW_1500_ORDER)
    for key, answer in {**REVIEW_1500_FIXED, **REVIEW_1500_KEPT}.items():
        assert found[key] == answer, key
    for key, date in dates.items():
        assert date == ("2026-11-11" if key in REVIEW_1500_NIGHT else "2026-11-12"), key

    by_id = {line.split(" · ", 1)[0][2:]: line for line in lines}
    commit = re.compile(r"커밋 `[0-9a-f]{7}`")
    for key in REVIEW_1500_FIXED:
        assert commit.search(by_id[key]), key
    for key in REVIEW_1500_KEPT:
        assert not commit.search(by_id[key]), key
    memo = [key for key, answer in found.items() if answer.startswith("메모 「")]
    assert memo == ["f-syncmode", "f-doctor", "f-admin", "f-merge", "f-ci6"]
    asked_again = [key for key, answer in found.items() if answer.startswith("다시 물음 답 「")]
    assert asked_again == ["x-modwin", "x-modenv", "x-mods3", "z-sync7", "z-d9", "g-f7-scope"]
    for key in ("f-ci6", "z-sync7"):
        assert "앱 세션 해석 — 밝힘" in by_id[key], key
    for key in ("f-doctor", "f-s33", "x-tokrenew", "x-shard", "z-push", "z-mem", "g-f2-runbook"):
        assert "`docs/TODO.md` 2장" in by_id[key], key
    assert "`docs/TODO.md` 4장" in by_id["z-sync7"]

    reversed_ = _chapter(document, 7)
    for phrase in ("보드 N10 다시 물음 답", "같은 보드 N11", "같은 보드 R2 다시 물음 답"):
        assert phrase in reversed_, phrase


# 2026-11-12 「배포 뒤 할 일 넷」 시안 보드(6-20)의 답 — 카드 스물넷(확인 열둘 · 고를 것
# 열둘). 확인 열둘은 모두 「좋음」 이고, 고를 것 열둘의 고른 글은 선택지 원문이다 — 둘(n2 ·
# q6b)은 카드 권장 (가) 와 다른 (나) 다. 스물넷 모두 화면에 입혀 갈래(`feat/post-ed-1112` ·
# `feat/post-capa-1112`)의 커밋을 든다. 줄 id 는 보드 카드 id 이고 차례는 보드 차례다.
POST_FOUR_ADDRESS = "https://claude.ai/artifact/1H2oVt4fcZard14zboQkcU"
POST_FOUR_ANSWERS = {
    "k-a1": "좋음",
    "k-a2": "좋음",
    "q1": (
        "(가) 되돌리기 · 다시 실행 · 칸 폭 맞춤 · 전체 화면을 그림 단추로(이름은 풍선), 찾기 칸도"
        " 조금 줄임 — 사내 보고 창(1283)에서도 한 줄"
    ),
    "n2": (
        "(나) 「PKG PLAN 변경사항 적용」 을 「변경사항 적용」 으로 줄이고, 「가상 제품 등록」 은"
        " 「⋯」 메뉴로"
    ),
    "k-b1": "좋음",
    "k-b2": "좋음",
    "k-b3": "좋음",
    "k-c0": "좋음",
    "k-c1": "좋음",
    "q2": (
        "(가) Core Data 숫자의 「공식」 은 모두 「Static」, 가정과 견주는 값은 「가정 전」, 발행본"
        " 이름은 그대로"
    ),
    "n1": (
        "(가) 일정 가용의 가용대수는 비가동을 빼기 전 값(설비 일정상 쓸 수 있는 대수). 비가동은"
        " 비가동 구획에서 한 번만 뺌"
    ),
    "k-c2": "좋음",
    "k-c3": "좋음",
    "q3": "(가) 반출 · 이설하는 날이 든 달부터 뺌. 정지만 한 호기는 아직 가지고 있으니 남김",
    "q4": "(가) 함께 펼침 — 「제품별 소요대수」 를 켜면 두 구획 모두 제품 줄까지",
    "q5": "(가) 둘의 합(호기별 비가동 일정이 깎은 대수 + 입력 비가동 대수)",
    "q5b": "(가) 처음은 Static",
    "q8": (
        "(가) 지금대로 Static 하나. 띠 · 카드 · 근거는 Static(가정을 켜면 가정). 일정 가용 ·"
        " 비가동 구획의 확보율 칸은 제 판정 색만 칠함"
    ),
    "q6": "(가) 지금 줄 모두 그대로",
    "q6b": "(나) 구획 맨 위에 「단축 후 확보율」 한 줄(단축으로 바뀐 달만 값)",
    "q7": (
        "(가) 같은 비가동(시작일 · 종료일 · 유형)이 그 호기의 모든 모듈에 있으면 화살표 하나로"
        " 합침. 일부 모듈에만 있는 것은 그 모듈 것만 둘째 줄에"
    ),
    "k-c4": "좋음",
    "k-c5": "좋음",
    "k-c6": "좋음",
}
# 사용자 메모 원문 — 확인 카드 셋(k-b1 · k-c0 · k-c4)과 고른 선택지에 단 셋(q1 · q6 · q7).
POST_FOUR_MEMOS = {
    "q1": "이 양식을 가능한 다른 편집기에도 공통 적용",
    "k-b1": "나머지 설비대수 3항목의 이름은 보유대수, 대여대수, 가용대수 로 적용",
    "k-c0": (
        "비가동 대수 만 띄어쓰기 적용됐는데 다른 행과 동일하게 비가동대수 로 띄어쓰기 빼고"
        " 붙여서넣어줘"
    ),
    "q6": "옵션 버튼 추가해서 전체를 보이기 or 단축필요만 보이기 선택할 수 있게 구현해",
    "q7": (
        "가 기준으로 적용한다면, 같은 호기로 행에 표현되는 모듈은 일정이 다름 등의 이유가"
        " 있을텐데, 이런경우엔 '... 같은호기' 로 표현하지말고 '[여백]└ 모듈명' 이런식으로"
        " 표현되게해"
    ),
    "k-c4": "단축 목표 = 확보기준 (월별) 문구는 가이드로 빼",
}
# 갈래가 답 밖에서 정한 것을 밝힌 줄.
POST_FOUR_BEYOND = ("k-a1", "q4", "q5", "q5b", "q6", "q7", "k-c6")


def test_the_post_deploy_four_board_answers_are_recorded() -> None:
    """v1.20 — 6-20 은 「배포 뒤 할 일 넷」 시안 보드 카드 스물넷이 보드 차례대로 한 줄씩이고
    고른 글은 선택지 원문(확인 카드는 「좋음」)이다. 메모 여섯은 원문 그대로 그 줄에 있고, 권장
    (가) 와 다른 답 둘(n2 · q6b)은 그 줄이 밝힌다. 스물넷 모두 커밋을 들고, 갈래가 답 밖에서
    정한 것은 그 줄이 밝힌다. q4 (가) 가 받은 ① · ② 의 같은 소요대수 줄은 UI-TXT-07 예외이고,
    뒤집은 옛 결정은 7-1 에 있다. 6-19 줄은 그때 기록 그대로다(앞 시험이 6-20 앞에서 끊어 본다).
    6-21 은 뒤 시험이 본다."""
    document = _text()
    assert "- **v1.20 — 2026-11-12.**" in _chapter(document, 8)
    assert "6-20 에 있다" in _chapter(document, 1)

    section = _chapter(document, 6)
    board = section[section.index("\n### 6-20. ") : section.index("\n### 6-21. ")]
    assert POST_FOUR_ADDRESS in board
    lines = [line for line in board.splitlines() if line.startswith("- ")]
    known = {rule.id for rule in _rules()}
    found: dict[str, str] = {}
    for line in lines:
        match = re.match(r"^- ([\w-]+) · .+ → \*\*([^*]+)\*\*.*\((2026-11-12) · ([^()]+)\)$", line)
        assert match, line
        found[match.group(1)] = match.group(2)
        cited = RULE_TOKEN.findall(match.group(4))
        assert cited and set(cited) <= known, line
    assert tuple(found) == tuple(POST_FOUR_ANSWERS)
    assert len(found) == 24
    assert found == POST_FOUR_ANSWERS
    assert sum(answer == "좋음" for answer in found.values()) == 12

    by_id = {line.split(" · ", 1)[0][2:]: line for line in lines}
    commit = re.compile(r"커밋 `[0-9a-f]{7}`")
    for key, line in by_id.items():
        assert commit.search(line), key
    memo = [key for key, line in by_id.items() if "— 메모 「" in line]
    assert memo == list(POST_FOUR_MEMOS)
    for key, note in POST_FOUR_MEMOS.items():
        assert f"메모 「{note}」" in by_id[key], key
    others = [key for key, answer in found.items() if answer.startswith("(나) ")]
    assert others == ["n2", "q6b"]
    for key in others:
        assert "권장과 다른 답" in by_id[key], key
    beyond = [key for key, line in by_id.items() if "답 밖 — 갈래가 정함" in line]
    assert beyond == list(POST_FOUR_BEYOND)

    rules = {rule.id: rule for rule in _rules()}
    assert "q4 (가)" in rules["UI-TXT-07"].fields["예외"][0]
    reversed_ = _chapter(document, 7)
    for phrase in ("「배포 뒤 할 일 넷」 시안 보드 k-c2 · n1 (가) · q5 (가)", "같은 보드 q1 (가)"):
        assert phrase in reversed_, phrase
    assert "n2 (나) · q6b (나)" in _chapter(document, 8)


# 2026-11-12 「남은 물음 11-12」 보드(6-21)의 답 — 카드 마흔하나. 고른 글은 선택지 원문이고 마흔은
# 카드 권장(⑤-4 는 권장이 (나)), ①-1 만 권장 (가) 와 다른 (나) 다. 고친 열여덟 줄은 갈래
# (`night/e2e-1112` · `night/pre-ui-1112` · `night/pre-ops-1112`)나 그 합침의 커밋을 들고,
# 기록 · 다음 7장 몫 · 뒤로 미룬 스물셋은 커밋이 없다. 줄 id 는 보드 카드 id 이고 차례는
# 보드 차례다.
REMAINING_1112_ADDRESS = "https://claude.ai/artifact/RxRM2KSDtKKKdDC2ER5dsh"
REMAINING_1112_ANSWERS = {
    "ship-post": "(나) 다음 배포에 함께 싣는다",
    "ship-e2e": "(가) 다음 배포 후보에 합쳐 싣는다",
    "count-lines": (
        "(가) 사외가 결과 파일을 쓰는 짧은 스크립트로 옮긴다 — 사용자는 짧은 한 줄만 친다"
    ),
    "census-bundle": "(가) 이번에도 센다 — 그 줄에 「사용자 승인 11-12」 를 단다",
    "migrate-order": "(가) 정본 문서 두 곳의 차례 번호도 「받기 모드 먼저」 로 맞춘다",
    "bucket-text": "(가) 정본 문서도 「그 창의 변수로만」 꼴로 맞춘다",
    "summary-length": (
        "(가) 둘 다 줄인다 — 늦게 보내도 되는 줄은 「남김(리뷰 뒤)」 으로, 겹치는 알림 칸은 한"
        " 곳으로"
    ),
    "rollback-path": "(가) 그때 따로 — 지금대로",
    "home-time-after": "(가) 이관 뒤 한 번 더 잰다 — 7장 이관 확인 줄에 초 칸 하나",
    "c11-tab": "(가) 사내 확인도 앱처럼 Y 로 본다",
    "draft-self": "(가) 넷 다 받는다(초안대로)",
    "owned-vs-avail": "(가) 그런 호기는 총보유대수도 처음부터 가진 것으로 센다",
    "toolrow-1600": "(가) 보이는 글 「비가동 기준」 · 「④」 를 걷고 ⓘ 풍선 하나로 뜻을 단다",
    "main-head": "(가) 지금처럼 Main 머리 줄을 둔다",
    "word-downtime": "(가) 붙여 쓴다",
    "word-official": "(가) 그대로 둔다",
    "discard-notice": "(가) 지금대로",
    "plan-cap": (
        "(가) 다음 배포 7장에 생산 계획 두 표 크기 세기를 더해(사용자 별도 창 · 개수만) 잰 뒤"
        " 정한다"
    ),
    "locked-color": "(가) 그대로",
    "yield-apply": "(가) 「변경사항 적용」 으로 맞춘다",
    "search-width": "(가) 세 그리드 공용 찾기 칸을 140 으로",
    "cancel-icon": "(가) 「편집 취소」 를 다른 그림으로 바꾼다",
    "small-keep": "(가) 다섯 다 지금대로",
    "m1-when": (
        "(가) 이번 배포부터 셋 다 켠다 — 적용 앞에 담당자가 도우미로 옮기는 PR 을 먼저 받는다"
    ),
    "m1-names": "(가) 그대로 — 앞머리로 한꺼번에 막는다",
    "mod-s3-open": "(가) 지금대로 — 이관과 함께 연다",
    "mod-other-id": "(가) 모듈 점검에서 그렇게 만드는 코드를 오류로 막는다",
    "token-min": "(가) 16 그대로",
    "sy05-off": "(가) 두지 않는다 — 그런 서버가 생기면 그때",
    "ad10-nosso": "(가) 지금대로 — 아무에게도 안 띄운다",
    "token-msg": "(나) WebIDE 에서는 「BigDataQuery 로그인을 다시 하세요」 로 가른다",
    "deny-data-read": (
        "(가) 막는다 — 실데이터 폴더 · 사본 폴더 · 백업 폴더 읽기를 권한 설정에서 거절"
    ),
    "pytest-guard": "(가) 둔다 — 시험이 운영 DB 자리를 열면 실패하게, 다음 배포에 함께",
    "pub-image": (
        "(가) 이번 배포는 그대로 — C-DEP 담당에게 보내기로 한 물음(이미지 만들 때 바깥 값 · 사내"
        " 바탕 이미지)의 답을 받은 뒤 옮길 길을 정한다"
    ),
    "pub-index": (
        "(가) 다음 배포 뒤 따로 환경변수로 옮긴다 — 사내 PC · C-DEP 표에 한 칸씩(S3 값과 같은 길)"
    ),
    "pub-mail": "(가) 환경변수로 받는다 — 비어 있으면 연락처 없이 팀 이름만(다음 배포 뒤 따로)",
    "unused-bits": (
        "(가) 글은 지금 이름으로 고치고(공식 확보율 판정과 설비 일정 확보율 판정이 네 가지"
        " 조합으로 다 나오는지 보는 점검은 그대로 남김), 안 쓰는 칸은 걷는다"
    ),
    "grid-next": "(가) 이 가지를 실은 뒤 사내 사용을 보고, 차례 2 설비 마스터부터",
    "test-env": "(가) 다음 배포 뒤 정리 때 일곱을 한꺼번에 본다",
    "upeh-msg": "(가) 셋 다 고친다 — 다음 배포 뒤",
    "admin-check": "(가) 다음에 그 근처를 손볼 때 모은다",
}
# 화면 · 런북 · 스크립트 · 보안 · 모듈을 고친 줄(커밋을 듦).
REMAINING_1112_FIXED = (
    "ship-post",
    "ship-e2e",
    "count-lines",
    "migrate-order",
    "bucket-text",
    "c11-tab",
    "owned-vs-avail",
    "toolrow-1600",
    "word-downtime",
    "plan-cap",
    "yield-apply",
    "search-width",
    "cancel-icon",
    "mod-other-id",
    "token-msg",
    "deny-data-read",
    "pytest-guard",
    "unused-bits",
)
# 기록만 한 것 · 다음 7장에서 쓸 것 · 뒤로 미룬 것(커밋 없음).
REMAINING_1112_KEPT = tuple(
    key for key in REMAINING_1112_ANSWERS if key not in REMAINING_1112_FIXED
)
# 갈래가 답 밖에서 정한 것을 밝힌 줄.
REMAINING_1112_BEYOND = ("toolrow-1600", "cancel-icon", "unused-bits")
# 구현이 답 밖에서 고른 것에 뒤에 「답 밖 — 구현이 정함」 표시를 단 줄과 그 줄이 드는 것.
REMAINING_1112_BEYOND_IMPLEMENTED = {
    "deny-data-read": ("`e2e_copy` 통째로", "`capa-copy`(DB 사본 폴더) 막음", "셸 읽기 명령 묶음"),
}
# ②-2 메모 — 실제 설비명 둘은 공개 저장소라 가린 꼴로 적는다.
REMAINING_1112_MEMO = (
    "이거 원인 파악됐어 붙여넣기가 잘못반영돼서 여러개의 모듈에 한개 메인설비명이 들어갔고, 그걸로"
    " 인해 발생된 현상임. [설비명 1]가 40개, [설비명 2]가 8개 모듈로 확인됐고, 다시 정상적으로"
    " 원복해뒀음"
)
# 다음 7장 몫 · 뒤로 미룬 것으로 할 일 문서 2장을 가리키는 줄.
REMAINING_1112_TODO_2 = (
    *("count-lines", "census-bundle", "summary-length", "home-time-after", "draft-self"),
    *("m1-when", "token-min", "deny-data-read", "pub-image", "pub-index", "pub-mail"),
    *("grid-next", "test-env", "upeh-msg", "admin-check"),
)


def test_the_remaining_1112_board_answers_are_recorded() -> None:
    """v1.21 — 6-21 은 「남은 물음 11-12」 보드 카드 마흔하나가 보드 차례대로 한 줄씩이고 고른 글은
    선택지 원문이다. 고친 열여덟 줄은 커밋을 들고 나머지 스물셋은 커밋이 없다. 권장과 다른 답은
    ①-1 하나이고(⑤-4 (나) 는 카드 권장), 메모는 ②-2 하나 — 실제 설비명 둘은 가린 꼴이다. 갈래가
    답 밖에서 정한 것(ⓘ 자리 · 고른 그림 · 점검 글)은 그 줄이 밝힌다. 뒤집은 옛 결정은 7-1 에
    있다. 6-20 줄은 그때 기록 그대로다(앞 시험이 6-21 앞에서 끊어 본다). 6-22 는 뒤 시험이 본다."""
    document = _text()
    assert "- **v1.21 — 2026-11-12.**" in _chapter(document, 8)
    assert "6-21 에 있다" in _chapter(document, 1)

    section = _chapter(document, 6)
    board = section[section.index("\n### 6-21. ") : section.index("\n### 6-22. ")]
    assert REMAINING_1112_ADDRESS in board
    lines = [line for line in board.splitlines() if line.startswith("- ")]
    known = {rule.id for rule in _rules()}
    found: dict[str, str] = {}
    for line in lines:
        match = re.match(r"^- ([\w-]+) · .+ → \*\*([^*]+)\*\*.*\((2026-11-12) · ([^()]+)\)$", line)
        assert match, line
        found[match.group(1)] = match.group(2)
        cited = RULE_TOKEN.findall(match.group(4))
        assert cited and set(cited) <= known, line
    assert tuple(found) == tuple(REMAINING_1112_ANSWERS)
    assert len(found) == 41
    assert found == REMAINING_1112_ANSWERS
    assert len(REMAINING_1112_FIXED) == 18 and len(REMAINING_1112_KEPT) == 23

    by_id = {line.split(" · ", 1)[0][2:]: line for line in lines}
    commit = re.compile(r"커밋 `[0-9a-f]{7}`")
    for key in REMAINING_1112_FIXED:
        assert commit.search(by_id[key]), key
    for key in REMAINING_1112_KEPT:
        assert not commit.search(by_id[key]), key
    others = [key for key, line in by_id.items() if "권장과 다른 답" in line]
    assert others == ["ship-post"]
    assert found["ship-post"].startswith("(나) ")
    assert found["token-msg"].startswith("(나) ") and "카드 권장이다" in by_id["token-msg"]
    memo = [key for key, line in by_id.items() if "— 메모 「" in line]
    assert memo == ["census-bundle"]
    assert f"메모 「{REMAINING_1112_MEMO}」" in by_id["census-bundle"]
    assert "`more sizes` 에 8 · 40 이 없음" in by_id["census-bundle"]
    beyond = [key for key, line in by_id.items() if "답 밖 — 갈래가 정함" in line]
    assert beyond == list(REMAINING_1112_BEYOND)
    implemented = [key for key, line in by_id.items() if "답 밖 — 구현이 정함" in line]
    assert implemented == list(REMAINING_1112_BEYOND_IMPLEMENTED)
    for key, parts in REMAINING_1112_BEYOND_IMPLEMENTED.items():
        for part in parts:
            assert part in by_id[key], (key, part)
    for key in REMAINING_1112_TODO_2:
        assert "`docs/TODO.md` 2장" in by_id[key], key

    reversed_ = _chapter(document, 7)
    for phrase in (
        "「남은 물음 11-12」 보드 ③-1 (가)",
        "같은 보드 ③-2 (가)",
        "같은 보드 ③-10 (가)",
        "「남은 물음 11-12」 보드 ②-3 (가)",
        "같은 보드 ②-8 (가)",
        "같은 보드 ⑤-4 (나)",
    ):
        assert phrase in reversed_, phrase
    assert "①-1 (나) 는 권장과 다른 답" in _chapter(document, 8)


# 2026-11-12 Space 요청 시안 보드(6-22)의 답 — 카드 서른여덟(고침 확인 셋 · 고침에 넣은 갈림 넷 ·
# 규칙집 하나 · 시안 스물일곱 · 메모 카드 하나 · 실을 배포 둘). 고른 글은 선택지 원문(고침 확인은
# 「좋음」, 메모 카드는 메모)이고, 선택지가 있는 서른넷 가운데 넷(3-1 · 3-3 · 7-2 · 배포1)이 카드
# 권장과 다른 답이다. 3-2 move 밖의 줄은 커밋을 든다. 줄 id 는 보드 카드 id 이고 차례는 보드 차례다.
SPACE_1112_ADDRESS = "https://claude.ai/artifact/3PQ7AAePoajQTpqLxJ6srk"
SPACE_1112_ANSWERS = {
    "fix-wheel": "좋음",
    "fix-dropdown": "좋음",
    "q-dd-wheel": "(가) 창을 닫는다 — 지금 넣은 꼴",
    "q-draft": "(가) 그 순간 확정한다 — 지금 넣은 꼴",
    "q-rule-net": "(가) 적는다",
    "fix-group-cover": "좋음",
    "q-partial": "(가) 반입 전 모듈만 숨기고 반입한 모듈은 남긴다 — 지금 넣은 꼴",
    "q-hidden-count": "(가) 그린 모듈 몫의 합 — 지금 넣은 꼴",
    "arr-format": "(가) 27.05.09",
    "arr-place": "(가) 상자 안, 이름 아래 작은 줄",
    "arr-group": "(가) 묶음 범위 바로 아래에 한 번",
    "arr-toggle": (
        "(가) 사이드바 「Space 도면」 상자의 「공식과 견주기」 바로 아래 토글 「반입 일정」 —"
        " 처음엔 꺼짐"
    ),
    "arr-target": "(가) 이대로",
    "arr-edit": "(가) 보기 화면만",
    "sib-cols": "(다) 여섯 + 레이아웃표시",
    "sib-main": "(나) 지금처럼 이 모듈만 옮긴다 — 묶음 이름 바꾸기는 Space 편집기에서",
    "sib-free": "(나) 예 — 늘 같다고 보고 묶음 규칙에도 더한다",
    "sib-unloaded": (
        "(가) 형제 줄을 고친 줄 바로 아래 끼워 넣어 「고친 칸」 표지를 보이고, 알림창에 한 줄"
    ),
    "sib-paths": "(가) 모든 고치는 길에 같은 규칙 + 호기 상세 「묶음」 표지",
    "hl-group": (
        "(가) 층 보기만 — 묶음 테를 실선으로, 누른 모듈 후광은 없앰(묶음이 아닌 호기는 후광 그대로)"
    ),
    "hl-when": ("(나) (가) + 필터 · 「도면에서 강조」 로 맞는 호기가 바뀌었는데 5대 이하일 때"),
    "hl-origin": "(가) 도면 무대 가장자리",
    "sheet-cols": "(가) 설비 마스터 탭과 같은 칸 · 같은 잠금",
    "sheet-apply": (
        "(가) 편집기 「적용」 때 들어가고, 칸만 고쳐도 「배치 저장」 이 켜져 함께 저장 —"
        " 되돌리기 · 처음 상태로에도 듦"
    ),
    "sheet-reject": "메모 「호기 정보 창에서 즉시 막고, 알람으로 띄우게끔」",
    "foot-kind": "(가) 새 도면 요소 「발자국」 — 도면 요소 칸의 동선 옆 단추",
    "foot-shape": "(가) 신발 밑창 꼴, 왼발 · 오른발 번갈아",
    "foot-gap": "(가) 좁게 · 보통 · 넓게 고르는 칸을 둔다",
    "foot-dir": "(가) 한쪽 — 처음은 왼쪽→오른쪽, 돌리기 · 뒤집기로 바꿈",
    "foot-color": "(가) 동선과 같은 선 색 고르기 — 처음은 강조색",
    "foot-fab": "(나) 층 · FAB 둘 다",
    "zone-tag": ("(가) 위 변 바로 바깥(위)으로 올린다 — 도면 위 끝이면 안쪽 그대로 호기 위에"),
    "zone-order-scope": "(다) 호기끼리 순서도",
    "zone-order-ui": "(가) 넷 — 맨 앞으로 · 앞으로 · 뒤로 · 맨 뒤로, 선택 칸 단추",
    "zone-order-whatif": "(가) 공식에서만 바꾼다 — 가정에서는 단추를 잠그고 까닭은 풍선",
    "zone-order-fab": "(가) 층 · FAB 둘 다",
    "ship-space": "(나) 다음 배포",
    "ship-bugs": "(가) 넣는다 — 답을 받은 뒤 다음 배포 후보에 합친다",
}
# 고른 선택지에 단 사용자 메모 원문(끝 빈칸만 뺌). 메모 카드(5-6)는 고른 글 자리에 메모가 선다.
SPACE_1112_MEMOS = {
    "arr-format": (
        "모듈로 구성된 경우, 각 모듈별 일정이 동일하다면 메인호기명 밑에 한번만 날짜를"
        " 표시하고, 모듈별로 차이가 있는경우 각 모듈마다 아래에 날짜를 표시"
    ),
    "arr-group": (
        "보통 모듈 개수는 4개인 경우가 많음. 그러면 메인 설비명이 정가운데 배치가 되고, 그런"
        " 경우를 가정해서 정가운데의 메인 설비명 아래에 일정을 적도록 하라는 의도임"
    ),
    "arr-toggle": ("배치 편집의 캔버스 편집버튼은 지우고, 각 버튼의 간격 일정하게 배치해."),
    "sib-free": "사용기준만 제외",
    "foot-shape": (
        "신발 밑창 꼴을 기본으로 하고, 모양을 바꿀 수 있게 해서, 발가락과 점도 추가하고"
        " 여기에 고양이 발바닥, 그 외에도 몇가지 더 추가해줘"
    ),
    "foot-gap": (
        "상자 형태가 아니라 선 형태로만 편집할 수 있게 해서 발크기를 상자높이로 바꿀수 없게"
        " 하고, 좁게 · 보통 · 넓게로 선택하게끔 함."
    ),
    "foot-color": "색상은 다른 도면 요소처럼 여러가지 색상 선택할 수 있도록",
}
SPACE_1112_OTHERS = ("sib-cols", "sib-free", "zone-order-scope", "ship-space")
SPACE_1112_NO_COMMIT = ("sib-main",)
# 계획 · 갈래가 답 밖에서 정한 것을 밝힌 줄.
SPACE_1112_BEYOND = (
    "arr-format",
    "arr-place",
    "arr-group",
    "arr-toggle",
    "arr-target",
    "arr-edit",
    "sib-cols",
    "sib-free",
    "sib-unloaded",
    "sib-paths",
    "hl-group",
    "hl-when",
    "hl-origin",
    "sheet-cols",
    "sheet-apply",
    "sheet-reject",
    "foot-kind",
    "foot-shape",
    "foot-gap",
    "foot-dir",
    "foot-color",
    "zone-tag",
    "zone-order-ui",
    "zone-order-whatif",
    "zone-order-fab",
)


def test_the_space_1112_board_answers_are_recorded() -> None:
    """v1.22 — 6-22 는 Space 요청 시안 보드 카드 서른여덟이 보드 차례대로 한 줄씩이고 고른 글은
    선택지 원문(고침 확인은 「좋음」, 메모 카드는 메모)이다. 권장과 다른 답은 넷(3-1 · 3-3 · 7-2 ·
    배포1)이고, 메모 여덟은 원문 그대로다. 3-2 move 밖의 줄은 커밋을 들고, 계획 · 갈래가 답 밖에서
    정한 것은 그 줄이 밝힌다. 설계 조사 뒤 물음 둘(Q0 「둘로 나눔」 · P2 「답 그대로 전체」)도 이
    절에 있고, 뒤집은 옛 결정 둘은 7-1 에 있다. 6-21 줄은 그때 기록 그대로다(앞 시험이 6-22 앞에서
    끊어 본다). 6-23 은 뒤 시험이 본다."""
    document = _text()
    assert "- **v1.22 — 2026-11-13.**" in _chapter(document, 8)
    assert "6-22 에 있다" in _chapter(document, 1)

    section = _chapter(document, 6)
    board = section[section.index("\n### 6-22. ") : section.index("\n### 6-23. ")]
    assert SPACE_1112_ADDRESS in board
    lines = [line for line in board.splitlines() if line.startswith("- ")]
    known = {rule.id for rule in _rules()}
    found: dict[str, str] = {}
    for line in lines:
        match = re.match(r"^- ([\w-]+) · .+ → \*\*([^*]+)\*\*.*\((2026-11-12) · ([^()]+)\)$", line)
        assert match, line
        found[match.group(1)] = match.group(2)
        cited = RULE_TOKEN.findall(match.group(4))
        assert cited and set(cited) <= known, line
    assert tuple(found) == tuple(SPACE_1112_ANSWERS)
    assert len(found) == 38
    assert found == SPACE_1112_ANSWERS
    assert sum(answer == "좋음" for answer in found.values()) == 3

    by_id = {line.split(" · ", 1)[0][2:]: line for line in lines}
    commit = re.compile(r"커밋 `[0-9a-f]{7}`")
    for key, line in by_id.items():
        assert bool(commit.search(line)) is (key not in SPACE_1112_NO_COMMIT), key
    others = [key for key, line in by_id.items() if "권장과 다른 답" in line]
    assert others == list(SPACE_1112_OTHERS)
    memo = [key for key, line in by_id.items() if "— 메모 「" in line]
    assert memo == list(SPACE_1112_MEMOS)
    for key, note in SPACE_1112_MEMOS.items():
        assert f"메모 「{note}」" in by_id[key], key
    assert found["sheet-reject"] == "메모 「호기 정보 창에서 즉시 막고, 알람으로 띄우게끔」"
    beyond = [key for key, line in by_id.items() if "답 밖 — 갈래가 정함" in line]
    assert beyond == list(SPACE_1112_BEYOND)
    for phrase in ("「둘로 나눔 (권장)」", "「답 그대로 전체 (권장)」", "설비 마이그레이션 `0034`"):
        assert phrase in board, phrase
    assert "`docs/TODO.md` 2장 「뒤로 미룬 것 — order 2단」" in by_id["zone-order-scope"]

    reversed_ = _chapter(document, 7)
    for phrase in ("Space 요청 시안 보드 1-4 메모", "같은 보드 7-1 (가)"):
        assert phrase in reversed_, phrase
    assert "3-1 (다) · 3-3 (나) · 7-2 (다) · 배포1 (나) 는 권장과 다른 답" in _chapter(document, 8)


# 2026-11-12 밤 「남은 물음」 둘째 보드(6-23)의 답 — 카드 열넷. 고른 글은 선택지 원문이고 열은 카드
# 권장, 셋(11 · 13 · 14)은 사외 권장 없이 보드 의견을 따랐고, 4 만 권장 (나) 와 다른 (가) 다. 코드를
# 고친 셋(5 · 7 · 12)은 `night/qb-1112` 의 커밋을 들고, 런북 몫 · 기록만 한 열하나는 커밋이 없다.
# 줄 id 는 보드 카드 id 이고 차례는 보드 표시 차례다.
REMAINING_1112B_ADDRESS = "https://claude.ai/artifact/9dPJtHaZJMsqxMzw21ximn"
REMAINING_1112B_ANSWERS = {
    "peer-off": (
        "(가) 꺼 둔 채 첫 CI/CD 를 누르고, 리뷰를 보낸 뒤 담당자 고침을 점검 · 합쳐 다시 켠다"
        "(지금 런북 초안)"
    ),
    "peer-count": "(가) 세지 않는다 — 판정 줄에만 그 모듈이 걸렸다고 적는다(지금 런북 초안)",
    "toolrow-two": "(가) 두 줄을 받는다",
    "owned-exit": "(가) 지금대로 둔다",
    "word-downtime2": (
        "(가) 모두 붙여 쓰고, 한 개념 한 이름 시험에 「입력 비가동 대수」 를 더해 다시 띄어 쓰지"
        " 못하게 한다"
    ),
    "peer-name-ask": (
        "(가) 예 — 배포 전 미리 확인 9 처럼 사용자가 담당자에게 「모듈 코드나 그 시험이 이름표를"
        " 손으로 만드는지」 를 함께 묻는다"
    ),
    "ctx-file": (
        "(가) 다른 파일 자리를 넣는 꼴만 점검 오류로 막고, 돌아가는 꼴은 앱 관리자의 PR 점검에"
        " 맡긴다"
    ),
    "names-public": "(가) 가린 채로 둔다",
    "guard-temp": (
        "(가) 지금대로 둔다 — 이번 배포 뒤 「시험 임시 폴더를 저장소 안에 두면 처음부터 거절」 과"
        " 함께 본다"
    ),
    "deny-guide": "(가) 지금은 두지 않고, 사내판 가이드를 다시 시작할 때 정한다",
    "deny-shell": "(가) 지금대로 둔다",
    "deny-copy": "(가) 지금대로 통째로 막는다",
    "plan-hand": "(가) 더한다 — 사내 손 확인에 한 칸",
    "token-pc": "(가) 이번 배포는 지금대로 둔다",
}
# 코드를 고친 줄과 그 커밋.
REMAINING_1112B_COMMITS = {
    "word-downtime2": ("55e4858", "8124f4e"),
    "ctx-file": ("db89e3a", "82a50c8"),
    "deny-copy": ("fd22922",),
}
# 사외 권장 없이 보드 의견을 따른 줄.
REMAINING_1112B_BOARD_VIEW = ("deny-shell", "plan-hand", "token-pc")


def test_the_second_remaining_1112_board_answers_are_recorded() -> None:
    """v1.23 — 6-23 은 「남은 물음」 둘째 보드 카드 열넷이 보드 차례대로 한 줄씩이고 고른 글은
    선택지 원문이다. 코드를 고친 셋(5 · 7 · 12)은 커밋을 들고 나머지 열하나는 커밋이 없다. 권장과
    다른 답은 4 owned-exit 하나이고, 셋은 사외 권장 없이 보드 의견을 따랐다. 12 는 6-21
    deny-data-read 줄에 「답 밖 — 구현이 정함」 표시를 달았고, 뒤집은 옛 결정 둘(6-21 m1-when ·
    word-downtime)은 7-1 에 있다. 6-22 줄은 그때 기록 그대로다(앞 시험이 6-23 앞에서 끊어 본다).
    6-24 는 뒤 시험이 본다."""
    document = _text()
    assert "- **v1.23 — 2026-11-13.**" in _chapter(document, 8)
    assert "6-23 에 있다" in _chapter(document, 1)

    section = _chapter(document, 6)
    board = section[section.index("\n### 6-23. ") : section.index("\n### 6-24. ")]
    assert REMAINING_1112B_ADDRESS in board
    lines = [line for line in board.splitlines() if line.startswith("- ")]
    known = {rule.id for rule in _rules()}
    found: dict[str, str] = {}
    for line in lines:
        match = re.match(r"^- ([\w-]+) · .+ → \*\*([^*]+)\*\*.*\((2026-11-12) · ([^()]+)\)$", line)
        assert match, line
        found[match.group(1)] = match.group(2)
        cited = RULE_TOKEN.findall(match.group(4))
        assert cited and set(cited) <= known, line
    assert tuple(found) == tuple(REMAINING_1112B_ANSWERS)
    assert len(found) == 14
    assert found == REMAINING_1112B_ANSWERS

    by_id = {line.split(" · ", 1)[0][2:]: line for line in lines}
    commit = re.compile(r"커밋 `[0-9a-f]{7}`")
    for key, line in by_id.items():
        assert bool(commit.search(line)) is (key in REMAINING_1112B_COMMITS), key
    for key, shas in REMAINING_1112B_COMMITS.items():
        for sha in shas:
            assert f"`{sha}`" in by_id[key], (key, sha)
    others = [key for key, line in by_id.items() if "권장과 다른 답" in line]
    assert others == ["owned-exit"]
    view = [key for key, line in by_id.items() if "보드 의견(사외 권장 없음" in line]
    assert view == list(REMAINING_1112B_BOARD_VIEW)
    assert "— 메모 「" not in board
    assert "6-21 deny-data-read 줄에 「답 밖 — 구현이 정함」 표시를 달아" in by_id["deny-copy"]
    assert "B 는 둘이다" in by_id["plan-hand"]

    reversed_ = _chapter(document, 7)
    for phrase in (
        "「남은 물음」 둘째 보드 1 (가)",
        "둘째 보드 5 (가)",
    ):
        assert phrase in reversed_, phrase
    assert "4 owned-exit (가) 는 권장 (나) 와 다른 답" in _chapter(document, 8)


# 2026-11-13 아침 「Space 구현 확인」 보드(6-24)의 답 — 카드 열일곱(① 발자국 저장 계약
# 하나 · ② 시안과 달라진 화면 열다섯 · ③ 알림 하나). 고른 글은 선택지 원문(알림 카드는
# 메모)이고, 선택지가 있는 열여섯 가운데 열넷은 카드 권장 (가), 둘(1 · 2-10)은 고양이 발
# 모양만 바꾸라는 권장과 다른 (나) 다. 커밋은 그 고양이 그림 고침 하나를 두 줄이 들고,
# 나머지 열다섯은 6-22 구현을 그대로 받아 커밋이 없다. 줄 id 는 보드 카드 id 이고 차례는
# 보드 차례다.
CONFIRM_1113_ADDRESS = "https://claude.ai/artifact/FdycLjSu3wtuf4sCEFHrEK"
CONFIRM_1113_ANSWERS = {
    "foot-contract": "(나) 이름이나 꼴을 바꾼다 — 메모에 적기",
    "d-arrival-bundle": "(가) 이대로 싣는다",
    "d-canvas": "(가) 이대로 싣는다",
    "d-save-only": "(가) 이대로 싣는다",
    "d-paths": "(가) 이대로 싣는다",
    "d-reduced-motion": "(가) 이대로 싣는다",
    "d-sheet-cols": "(가) 이대로 싣는다",
    "d-sheet-check": "(가) 이대로 싣는다",
    "d-refuse-alert": "(가) 이대로 싣는다",
    "d-foot-line": "(가) 이대로 싣는다",
    "d-foot-shapes": "(나) 고쳐 달라 — 메모에 적기",
    "d-zone-tag": "(가) 이대로 싣는다",
    "d-order-step": "(가) 이대로 싣는다",
    "d-new-unit-fill": "(가) 이대로 싣는다",
    "d-small-five": "(가) 다섯 다 그대로 싣는다",
    "d-multipick": "(가) 이대로 싣는다 — 고름을 두고 칸을 연다",
    "later-stack": "메모 「권장대로 진행해」",
}
# 고른 선택지에 단 사용자 메모 원문. 알림 카드(3)는 고른 글 자리에 메모가 선다.
CONFIRM_1113_MEMOS = {
    "foot-contract": (
        "다른건 다 좋은데 고양이 모양은 고양이 발바닥 젤리같은 모양으로 좀더 귀엽게 바꿔줘. 잘"
        " 모르겠으면 인터넷에서 검색되는 모양으로 해보고 다시 시안 제안해줘"
    ),
    "d-foot-shapes": "고양이 모양만 바꾸는것으로 1번문항에 답변함",
}
CONFIRM_1113_OTHERS = ("foot-contract", "d-foot-shapes")
# 고양이 그림 고침 커밋 — 두 (나) 줄이 함께 든다.
CONFIRM_1113_CAT_COMMITS = ("87b6df4", "d7db0ba")
CONFIRM_1113_COMMITS = {key: CONFIRM_1113_CAT_COMMITS for key in CONFIRM_1113_OTHERS}
CONFIRM_1113_CAT_ADDRESS = "https://claude.ai/artifact/WyNh8ACZXtHBR15WDmr9LT"


def test_the_space_confirm_1113_board_answers_are_recorded() -> None:
    """v1.24 — 6-24 는 「Space 구현 확인」 보드 카드 열일곱이 보드 차례대로 한 줄씩이고
    고른 글은 선택지 원문(알림 카드는 메모)이다. 권장과 다른 답은 둘(1 · 2-10 — 고양이 발
    모양만 바꿈)이고 둘 다 메모 원문과 고양이 그림 고침 커밋을 든다. 나머지 열다섯은 커밋이
    없다. 저장 키 `cat` 은 그대로이고 바꾼 그림은 시안 보드에서 다시 골랐다(B). 6-22 · 6-23 줄은
    그때 기록 그대로다(앞 시험이 6-24 앞에서 끊어 본다). 6-25 는 뒤 시험이 본다."""
    document = _text()
    assert "- **v1.24 — 2026-11-13.**" in _chapter(document, 8)
    assert "6-24 에 있다" in _chapter(document, 1)

    section = _chapter(document, 6)
    board = section[section.index("\n### 6-24. ") : section.index("\n### 6-25. ")]
    assert CONFIRM_1113_ADDRESS in board
    lines = [line for line in board.splitlines() if line.startswith("- ")]
    known = {rule.id for rule in _rules()}
    found: dict[str, str] = {}
    for line in lines:
        match = re.match(r"^- ([\w-]+) · .+ → \*\*([^*]+)\*\*.*\((2026-11-13) · ([^()]+)\)$", line)
        assert match, line
        found[match.group(1)] = match.group(2)
        cited = RULE_TOKEN.findall(match.group(4))
        assert cited and set(cited) <= known, line
    assert tuple(found) == tuple(CONFIRM_1113_ANSWERS)
    assert len(found) == 17
    assert found == CONFIRM_1113_ANSWERS
    assert sum(answer.startswith("(가) ") for answer in found.values()) == 14

    by_id = {line.split(" · ", 1)[0][2:]: line for line in lines}
    commit = re.compile(r"커밋 `[0-9a-f]{7}`")
    for key, line in by_id.items():
        assert bool(commit.search(line)) is (key in CONFIRM_1113_COMMITS), key
    for key, shas in CONFIRM_1113_COMMITS.items():
        for sha in shas:
            assert f"`{sha}`" in by_id[key], (key, sha)
    others = [key for key, line in by_id.items() if "권장과 다른 답" in line]
    assert others == list(CONFIRM_1113_OTHERS)
    memo = [key for key, line in by_id.items() if "— 메모 「" in line]
    assert memo == list(CONFIRM_1113_MEMOS)
    for key, note in CONFIRM_1113_MEMOS.items():
        assert f"메모 「{note}」" in by_id[key], key
    assert "`cat`" in by_id["foot-contract"]
    assert "「B 큰 젤리」" in by_id["foot-contract"]
    assert CONFIRM_1113_CAT_ADDRESS in board
    assert "`docs/TODO.md` 2장 「뒤로 미룬 것 — order 2단」" in by_id["later-stack"]
    for phrase in ("Ctrl+Z", "「다음 배포로」", "`202611131000`"):
        assert phrase in board, phrase

    assert "1 foot-contract (나) · 2-10 d-foot-shapes (나) 는 권장과 다른 답" in _chapter(
        document, 8
    )


# 2026-11-13 배포 뒤 다섯 일(6-25)의 기록 — 보드 답이 아니라 앞서 받은 답(2026-11-12 사용자 결정
# 하나 · 6-21 ⑤-8 · ⑤-9 · ⑥-3 · 6-23 9)을 입힌 줄 다섯이다. 줄마다 커밋을 들고 구현이 답 밖에서
# 정한 것을 밝힌다. 줄 id 는 그 답의 id 이고 차례는 절 차례다.
POST_1113_LINES = ("token-entry", "pub-index", "pub-mail", "test-env", "guard-temp")


def test_the_post_1113_records_are_recorded() -> None:
    """v1.25 — 6-25 는 배포 뒤 다섯 일이 입힌 앞 답의 기록 다섯 줄이고, 줄마다 커밋과 「답 밖 —
    구현이 정함」 을 든다. 6-21 · 6-23 의 그 줄들은 커밋 없이 6-25 를 가리킨다(앞 시험들이 커밋
    없음을 본다). 6-24 줄은 그때 기록 그대로다(앞 시험이 6-25 앞에서 끊어 본다). 6-26 은 뒤 시험이
    본다."""
    document = _text()
    assert "- **v1.25 — 2026-11-13.**" in _chapter(document, 8)
    assert "6-25 에 있다" in _chapter(document, 1)

    section = _chapter(document, 6)
    record = section[section.index("\n### 6-25. ") : section.index("\n### 6-26. ")]
    lines = [line for line in record.splitlines() if line.startswith("- ")]
    known = {rule.id for rule in _rules()}
    found: list[str] = []
    for line in lines:
        match = re.match(
            r"^- ([\w-]+) · .+ → \*\*([^*]+)\*\*.*\((2026-11-1[23]) · ([^()]+)\)$", line
        )
        assert match, line
        found.append(match.group(1))
        cited = RULE_TOKEN.findall(match.group(4))
        assert cited and set(cited) <= known, line
        assert re.search(r"커밋 `[0-9a-f]{7}`", line), line
        assert "답 밖 — 구현이 정함" in line, line
    assert tuple(found) == POST_1113_LINES

    earlier = section[section.index("\n### 6-21. ") : section.index("\n### 6-24. ")]
    for key in ("pub-index", "pub-mail", "test-env", "guard-temp"):
        line = next(item for item in earlier.splitlines() if item.startswith(f"- {key} · "))
        assert f"6-25 {key}" in line, key


# 2026-11-13 오후 「배포 뒤 다섯 일」 확인 보드(6-26)의 답 — 카드 열일곱 모두 카드 권장이고 메모는
# 없다. 사외 작업 방식 · 정리 넷(6 ~ 9)은 이 문서에 줄을 두지 않아 줄은 열셋이다. 고른 글은 보드
# 선택지 라벨(권장대로 해 둔 카드는 「좋음」)이고, 고친 셋만 커밋을 든다. 줄 id 는 보드 카드 id 이고
# 차례는 보드 차례다.
NEXT_1113_ADDRESS = "https://claude.ai/artifact/Gdfawn1fhgjiB2yrZepB6z"
NEXT_1113_ANSWERS = {
    "order2-raised-back": "(가) 고친다",
    "token-start-fail": "(가) 지금대로",
    "env-name-net": "(가) 지문 그대로 + 할 일 한 줄",
    "ci-win-tmp": "(가) 한 조각에 건다",
    "claude-md-0034": "(가) 넣는다",
    "order2-rules": "좋음",
    "sheet2-six": "좋음",
    "sheet2-locked": "좋음",
    "sheet2-sorted": "좋음",
    "sheet2-perf": "좋음",
    "token-expiry": "좋음",
    "token-restart": "좋음",
    "testenv-lines": "좋음",
}
NEXT_1113_COMMITS = {
    "order2-raised-back": ("c8c33af", "63a076c"),
    "ci-win-tmp": ("b3e911a",),
    "claude-md-0034": ("b3e911a",),
}


def test_the_next_1113_board_answers_are_recorded() -> None:
    """v1.26 — 6-26 은 「배포 뒤 다섯 일」 확인 보드 카드 가운데 이 문서 몫 열셋이 보드 차례대로 한
    줄씩이고 고른 글은 선택지 라벨이다. 모두 카드 권장이고 메모가 없다. 고친 셋(1 · 4 · 5)은 커밋을
    들고 나머지 열은 커밋이 없다. 1 (가) 의 예외는 6-22 zone-order-ui · 6-24 d-order-step 줄과 7-1
    에 있다. 6-25 줄은 답 구절만 고쳤다(앞 시험이 6-26 앞에서 끊어 본다). 6-27 은 뒤 시험이 본다."""
    document = _text()
    assert "- **v1.26 — 2026-11-13.**" in _chapter(document, 8)
    assert "6-26 에 있다" in _chapter(document, 1)

    section = _chapter(document, 6)
    board = section[section.index("\n### 6-26. ") : section.index("\n### 6-27. ")]
    assert NEXT_1113_ADDRESS in board
    lines = [line for line in board.splitlines() if line.startswith("- ")]
    known = {rule.id for rule in _rules()}
    found: dict[str, str] = {}
    for line in lines:
        match = re.match(r"^- ([\w-]+) · .+ → \*\*([^*]+)\*\*.*\((2026-11-13) · ([^()]+)\)$", line)
        assert match, line
        found[match.group(1)] = match.group(2)
        cited = RULE_TOKEN.findall(match.group(4))
        assert cited and set(cited) <= known, line
    assert tuple(found) == tuple(NEXT_1113_ANSWERS)
    assert len(found) == 13
    assert found == NEXT_1113_ANSWERS

    by_id = {line.split(" · ", 1)[0][2:]: line for line in lines}
    commit = re.compile(r"커밋 `[0-9a-f]{7}`")
    for key, line in by_id.items():
        assert bool(commit.search(line)) is (key in NEXT_1113_COMMITS), key
    for key, shas in NEXT_1113_COMMITS.items():
        for sha in shas:
            assert f"`{sha}`" in by_id[key], (key, sha)
    assert "권장과 다른 답" not in board
    assert "— 메모 「" not in board

    def earlier(head: str, key: str) -> str:
        part = section[section.index(head) :]
        return next(item for item in part.splitlines() if item.startswith(f"- {key} · "))

    assert "같은 보드 1 (가)" in earlier("\n### 6-22. ", "zone-order-ui")
    assert "확인 보드 1 (가)로 예외 하나" in earlier("\n### 6-24. ", "d-order-step")
    assert "2026-11-13 오후 확인 보드 1 (가)로 호기 위로 올린 영역" in _chapter(document, 7)


# 2026-11-14 「월요일 배포 앞」 물음 보드(6-27)의 답 — 카드 아홉(여쭘 일곱 · 정한 것
# 두 장) 모두 카드 권장이고 메모는 없다. 정한 것 두 장(열둘 · 열)은 점마다 한 줄이라
# 줄은 스물아홉이다. 고른 글은 보드 선택지 라벨(정한 것은 「좋음」)이고, 커밋은 미리 짠
# 갈래 다섯 · 통합 커밋의 것이다. 범위 답 · 지금대로 · 런북 몫 줄은 커밋이 없다. 줄 id 는
# 보드 카드 id(정한 것은 `decided-n` · `decided-login-n`)이고 차례는 보드 차례다.
MONDAY_1114_ADDRESS = "https://claude.ai/artifact/NndcBhF6q2wcvuMHqPKwJ9"
MONDAY_1114_ANSWERS = {
    "ship": "모두 싣기 — E2E 를 통과하면",
    "seed": "운영 서버에서는 올리지 않는다",
    "stop-panels": "한 꼴로 맞춘다",
    "english": "한국어 띠로 바꾼다",
    "boot-record": "Admin Area 통합인증 점검의 「최근 사건」 에 한 줄 남긴다",
    "prod-off": "잠금 유지",
    "logout": "실제대로 고침",
    **{f"decided-{number}": "좋음" for number in range(1, 13)},
    **{f"decided-login-{number}": "좋음" for number in range(1, 11)},
}
MONDAY_1114_COMMITS = {
    "seed": ("98f4995", "2735684"),
    "stop-panels": ("e7a34af", "5e89cbc"),
    "english": ("a24bde1", "8281cb3", "f152833"),
    "boot-record": ("86dc0d1", "0582511", "bc8f6e2"),
    "prod-off": ("aeff718", "a930ad3", "537ae0a"),
    "logout": ("931b130",),
    "decided-1": ("a930ad3", "d1aed42", "537ae0a"),
    "decided-2": ("b0bcfcc",),
    "decided-3": ("e2a199b",),
    "decided-4": ("b8ae0a4",),
    "decided-5": ("91cb4fd", "12931ca"),
    "decided-6": ("d6ae6d9",),
    "decided-7": ("445dcb4", "5adba78", "9b45426", "1f44374"),
    "decided-8": ("ebcb1ba",),
    "decided-9": ("9c0ce55", "0a757a3"),
    "decided-10": ("8d1cf6e", "e9598db"),
    "decided-11": ("c121117", "1b03493"),
    "decided-login-1": ("18d42dc",),
    "decided-login-2": ("18d42dc",),
    "decided-login-3": ("18d42dc", "466ec88", "5378d46"),
    "decided-login-5": ("2ae91dc",),
    "decided-login-7": ("eca1b21", "cfe84e7"),
    "decided-login-8": ("7806a60",),
}
# 보드에 올리지 않고 구현이 좁게 정한 것 — 절 끝 표의 줄 이름. 뒤의 줄은 2026-11-15 E2E 그림
# 보드 규칙 판정(PRC-07)이 「표에 없는 구현의 좁은 결정」 으로 찾아 v1.29 에 더한 것이다.
MONDAY_1114_NARROW = (
    "register-label",
    "login-fail-kinds",
    "loop-time",
    "config-fold",
    "official-narrow",
    "boot-contact",
    "intro-stopped",
)


def test_the_monday_1114_board_answers_are_recorded() -> None:
    """v1.27 — 6-27 은 「월요일 배포 앞」 물음 보드 카드 아홉이 보드 차례대로이고, 정한 것
    두 장은 점마다 한 줄이라 스물아홉 줄이다. 고른 글은 선택지 라벨(정한 것은 「좋음」)이고
    모두 카드 권장 · 메모 없음이다. 고친 줄만 커밋을 든다. 끝 표는 보드에 올리지 않고 구현이
    정한 줄이다(갈래 결과 다섯 · v1.29 에 E2E 규칙 판정이 찾은 것). 6-26 줄은 그때 기록
    그대로다(앞 시험이 6-27 앞에서 끊어 본다). 6-28 은 뒤 시험이 본다."""
    document = _text()
    assert "- **v1.27 — 2026-11-14.**" in _chapter(document, 8)
    assert "6-27 에 있다" in _chapter(document, 1)

    section = _chapter(document, 6)
    board = section[section.index("\n### 6-27. ") : section.index("\n### 6-28. ")]
    assert MONDAY_1114_ADDRESS in board
    lines = [line for line in board.splitlines() if line.startswith("- ")]
    known = {rule.id for rule in _rules()}
    found: dict[str, str] = {}
    for line in lines:
        match = re.match(r"^- ([\w-]+) · .+ → \*\*([^*]+)\*\*.*\((2026-11-14) · ([^()]+)\)$", line)
        assert match, line
        found[match.group(1)] = match.group(2)
        cited = RULE_TOKEN.findall(match.group(4))
        assert cited and set(cited) <= known, line
    assert tuple(found) == tuple(MONDAY_1114_ANSWERS)
    assert len(found) == 29
    assert found == MONDAY_1114_ANSWERS

    by_id = {line.split(" · ", 1)[0][2:]: line for line in lines}
    commit = re.compile(r"커밋 `[0-9a-f]{7}`")
    for key, line in by_id.items():
        assert bool(commit.search(line)) is (key in MONDAY_1114_COMMITS), key
    for key, shas in MONDAY_1114_COMMITS.items():
        for sha in shas:
            assert f"`{sha}`" in by_id[key], (key, sha)
    assert "권장과 다른 답" not in board
    assert "— 메모 「" not in board
    assert "`fallback/pre-p0-1116`" in by_id["ship"]

    rows = re.findall(
        r"^\| ([\w-]+) \| .+ \| (`[0-9a-f]{7}`(?: · `[0-9a-f]{7}`)*) \| ([^|]+) \|$",
        board,
        re.MULTILINE,
    )
    assert tuple(row[0] for row in rows) == MONDAY_1114_NARROW
    for _, _, rules in rows:
        cited = RULE_TOKEN.findall(rules)
        assert cited and set(cited) <= known, rules


# 2026-11-15 다섯 사람 E2E 1바퀴 고침이 앞 답(6-11 b2 · 6-27 english)을 넓혀 읽은 것(6-28) — 보드
# 답이 아니라 기록이고 사용자 확인은 그림 보드로 받는다. 줄 id 와 그 줄이 드는 커밋.
WIDENED_1115_LINES = {"band-connecting": ("946025e",)}


def test_the_widened_1115_readings_are_recorded() -> None:
    """v1.28 — 6-28 은 E2E 고침이 앞 답을 넓혀 읽은 기록 한 줄이고, 줄마다 커밋 · 「답 밖 — 구현이
    정함」 · 그림 보드 확인을 든다. 넓힌 뜻은 UI-LAY-05 그물 줄(머리 CONNECTING 과 그 시험)에도
    섰다. 앞 절 줄은 그때 기록 그대로다(앞 시험이 6-28 앞에서 끊어 본다). 판 머리와 6-29 는 뒤
    시험이 본다."""
    document = _text()
    assert "- **v1.28 — 2026-11-15.**" in _chapter(document, 8)
    assert "6-28 에 있다" in _chapter(document, 1)

    section = _chapter(document, 6)
    record = section[section.index("\n### 6-28. ") : section.index("\n### 6-29. ")]
    lines = [line for line in record.splitlines() if line.startswith("- ")]
    known = {rule.id for rule in _rules()}
    found: list[str] = []
    for line in lines:
        match = re.match(r"^- ([\w-]+) · .+ → \*\*([^*]+)\*\*.*\((2026-11-15) · ([^()]+)\)$", line)
        assert match, line
        found.append(match.group(1))
        cited = RULE_TOKEN.findall(match.group(4))
        assert cited and set(cited) <= known, line
        assert "답 밖 — 구현이 정함" in line and "그림 보드" in line, line
        for sha in WIDENED_1115_LINES[match.group(1)]:
            assert f"`{sha}`" in line, (line, sha)
    assert tuple(found) == tuple(WIDENED_1115_LINES)
    band = lines[0]
    assert "6-11 b2" in band and "6-27 english" in band
    assert "UI-LAY-05" in band

    net = {rule.id: rule for rule in _rules()}["UI-LAY-05"].fields["그물"][0]
    assert "영어 연결 오류 창 · 머리 CONNECTING 감춤" in net
    assert (
        "tests/test_sso_reconnect.py::"
        "test_a_standing_band_also_hides_the_header_connecting_status_and_gives_it_back" in net
    )


# 2026-11-15 다섯 사람 E2E 그림 보드 카드를 규칙집에 대 본 판정(PRC-07)이 찾은 규칙집 · 기록
# 빈칸 — 판정의 「예외」 근거가 규칙집 밖 보드 답뿐이던 자리를 규칙 글에 이름으로 올린다(PRC-08).
# 6-29 는 설계 문서에만 있던 2026-11-14 토큰 자동 갱신 틀 사용자 결정의 기록이다 — 줄 id 와 커밋.
TOKEN_FRAME_1114_LINES = {
    "token-auto-frame": (
        "d7415a9",
        "c170434",
        "303a0be",
        "57b91c2",
        "405380e",
        "0086c6b",
        "357dd58",
    )
}
TOKEN_SHIP_MEMO = (
    "다음 배포는 월요일 예정인데 그때까지 토큰 자동 갱신 기능을 구현하는것을 목표로 하자"
)


def test_the_e2e_1115_judgment_gaps_are_written_into_the_rules() -> None:
    """v1.29 — UI-TXT-01 예외가 앱이 서기 전 시작 임시 화면(`scripts/container_stage.py`)을 이름으로
    든다(판정 s-D-01 ~ 07 의 근거가 「앱 대신 뜨는 화면」 보드 답뿐이었다). UI-NTF-10 은
    「예외: 없음」 이던 자리에 앱 밖 틀의 「한 번 눌러 통째로 고름」(보드 frame)을 든다(판정 s-A-01
    등). 6-29 는 2026-11-14 토큰 자동 갱신 틀의 사용자 결정 한 줄 — 메모 원문 · 「답 밖 — 구현이
    정함」 · 지금 「준비」 · 커밋을 들고, 뒤집힌 6-25 token-entry 「조사만」 은 7-1 에 남는다(6-25
    줄은 그대로). 판 머리와 6-30 은 뒤 시험이 본다."""
    document = _text()
    assert "- **v1.29 — 2026-11-15.**" in _chapter(document, 8)

    rules = {rule.id: rule for rule in _rules()}
    txt01 = rules["UI-TXT-01"].fields["예외"][0]
    assert "시작 임시 화면" in txt01 and "`scripts/container_stage.py`" in txt01
    assert "p1-stage-start" in txt01 and "p2-stage-human" in txt01

    ntf10 = rules["UI-NTF-10"].fields["예외"][0]
    assert ntf10 != "없음"
    assert "`auth/page_frame.py`" in ntf10 and "`default-src 'none'`" in ntf10
    assert "한 번 눌러 통째로 고른다" in ntf10 and "frame" in ntf10
    assert "`scripts/container_stage.py`" in ntf10

    assert "6-29 에 있다" in _chapter(document, 1)
    section = _chapter(document, 6)
    record = section[section.index("\n### 6-29. ") : section.index("\n### 6-30. ")]
    lines = [line for line in record.splitlines() if line.startswith("- ")]
    known = {rule.id for rule in _rules()}
    found: list[str] = []
    for line in lines:
        match = re.match(r"^- ([\w-]+) · .+ → \*\*([^*]+)\*\*.*\((2026-11-14) · ([^()]+)\)$", line)
        assert match, line
        found.append(match.group(1))
        cited = RULE_TOKEN.findall(match.group(4))
        assert cited and set(cited) <= known, line
        assert "답 밖 — 구현이 정함" in line and f"「{TOKEN_SHIP_MEMO}」" in line, line
        for sha in TOKEN_FRAME_1114_LINES[match.group(1)]:
            assert f"`{sha}`" in line, (line, sha)
    assert tuple(found) == tuple(TOKEN_FRAME_1114_LINES)
    frame = lines[0]
    assert "「준비」" in frame and "6-25 token-entry" in frame
    assert "`AD-17`" in frame and "`AD-18`" in frame
    earlier = section[section.index("\n### 6-25. ") : section.index("\n### 6-26. ")]
    assert "REST 자동 갱신은 조사만" in earlier, "6-25 token-entry 줄은 그때 기록 그대로다"

    reversed_ = _chapter(document, 7)
    turned_lines = [line for line in reversed_.splitlines() if "REST 자동 갱신은 조사만" in line]
    assert len(turned_lines) == 1, "7-1 에 뒤집힌 6-25 token-entry 「조사만」 줄이 하나 있다"
    turned = turned_lines[0]
    assert "6-25 token-entry" in turned and "6-29" in turned and TOKEN_SHIP_MEMO in turned


# 2026-11-15 E2E 그림 검수 보드(6-30)의 답 — 카드 열하나(여쭘 여덟 · 되돌리기 어려운 화면
# 하나 · 정한 것 한 장 · 규칙 판정 목록). 선택지가 있는 여덟은 모두 카드 권장이고, 화면 · 정한
# 것은 「좋음」, 규칙 판정 목록은 메모 「오케이」 다. 고른 글은 보드 선택지 라벨이고 줄 id 는 보드
# 카드 id, 차례는 보드 차례다. 고칠 것은 같은 답을 입히는 코드 갈래 몫이라 그 줄은 커밋을 들지
# 않는다.
E2E_1115_ADDRESS = "https://claude.ai/artifact/RXJnm5dTtyADFK5gHXeWUL"
E2E_1115_ANSWERS = {
    "q-self-fail-rev": "실패 줄은 「판 1(그대로)」 로",
    "q-narrow-admin": "다음 판에 고침",
    "s-A-13": "두 화면 모두 작은 링크로 낮춤",
    "s-A-14": "표지를 「점검 중」 으로",
    "s-C-02": "「등록 길」 값을 「관리자가 넣음」 으로",
    "s-C-13": "지금대로",
    "s-C-14": "80일 좋음",
    "s-B-12": "이대로",
    "s-A-01": "좋음",
    **{f"decided-e2e-{number}": "좋음" for number in range(1, 4)},
    "rule-list": "메모 「오케이」",
}
# 커밋을 든 줄 — 답 앞 E2E 고침의 커밋이다(정한 것 셋 — 점마다 한 줄).
E2E_1115_COMMITS: dict[str, tuple[str, ...]] = {
    "q-self-fail-rev": ("06475ad",),
    "s-A-13": ("331aa64",),
    "s-A-14": ("19b94c0",),
    "s-C-02": ("a077a65",),
    "decided-e2e-1": ("946025e",),
    "decided-e2e-2": ("00ddc26", "b3e55e8"),
    "decided-e2e-3": ("9375577",),
}
# 코드 갈래가 고쳐 합친 줄은 커밋을 든다 — 「코드 갈래가 고친다」 자리표가 남지 않는다.
E2E_1115_CODE_LANE: tuple[str, ...] = ()
# q-narrow-admin 「다음 판에 고침」 이 남긴 TODO 2장 할 일의 첫 구절(다른 문서가 이 구절로 찾는다).
E2E_1115_NARROW_TODO = (
    "좁은 창(390)에서 낱말 단위 줄바꿈을 앱 안 카드(모듈 오류 카드 머리 줄) · Admin Area 탭 줄 · "
    "로그인 전 실패 표 · Alarm 줄 · 알림창 글로 넓힘 — "
    "2026-11-15 E2E 보드 q-narrow-admin 답 「다음 판」"
)


def test_the_e2e_1115_board_answers_are_recorded() -> None:
    """v1.30 — 6-30 은 E2E 그림 검수 보드 카드가 보드 차례대로 한 줄씩(정한 것 한 장은 점마다 한 줄
    — 열셋)이고 고른 글은 선택지 라벨이다. 모두 카드 권장이고 권장과 다른 답이 없으며 메모는 규칙
    판정 목록 하나다. 고칠 것 넷은 같은 날 코드 갈래가 고쳐 합친 커밋을 들고, 정한 것 셋은 답 앞 E2E
    고침의 커밋을 든다. 답이 걸린 규칙은 글 · 예외 · 근거 줄에 카드 id 를 든다 — 실패한 쓰기 ·
    엇갈린 표지(UI-DAT-11), 「관리자」 한 낱말 두 뜻(UI-CON-02), 누르기 전에 보이는 저장(UI-NTF-09),
    「정본 아님」 표지(UI-LAY-05 · UI-TXT-06 · UI-ACC-02 · 4장), 갱신 토큰 80일(4장 — 같은 날 밤
    6-31 로 뒤집혀 그 줄은 7-1 로 옮기고 6-30 줄에 표지), 「토큰 자동 갱신」 줄 낱말(UI-CON-02 ·
    UI-DAT-11 예외 — 2026-11-16 틀을 걷어 v1.32 가 예외를 「없음」 으로 되돌림), 배지 정확성
    (UI-PRF-01 예외), 판정 목록 보고 꼴(PRC-07). 공통 틀 「주 단추 하나」 를 좁힌 것은 7-1 에, 다음
    판 할 일은 TODO 2장에 있다. 6-28 · 6-29 줄은 받은 답 구절만 더했다(앞 시험들이 저마다 다음 절
    앞에서 끊어 본다). 판 머리는 v1.32 시험이 본다."""
    document = _text()
    assert "- **v1.30 — 2026-11-15.**" in _chapter(document, 8)
    assert "6-30 에 있다" in _chapter(document, 1)

    section = _chapter(document, 6)
    board = section[section.index("\n### 6-30. ") : section.index("\n### 6-31. ")]
    assert E2E_1115_ADDRESS in board
    lines = [line for line in board.splitlines() if line.startswith("- ")]
    known = {rule.id for rule in _rules()}
    found: dict[str, str] = {}
    for line in lines:
        match = re.match(r"^- ([\w-]+) · .+ → \*\*([^*]+)\*\*.*\((2026-11-15) · ([^()]+)\)$", line)
        assert match, line
        found[match.group(1)] = match.group(2)
        cited = RULE_TOKEN.findall(match.group(4))
        assert cited and set(cited) <= known, line
    assert tuple(found) == tuple(E2E_1115_ANSWERS)
    assert found == E2E_1115_ANSWERS

    by_id = {line.split(" · ", 1)[0][2:]: line for line in lines}
    commit = re.compile(r"커밋 `[0-9a-f]{7}`")
    for key, line in by_id.items():
        assert bool(commit.search(line)) is (key in E2E_1115_COMMITS), key
        assert ("코드 갈래가 고친다" in line) is (key in E2E_1115_CODE_LANE), key
    for key, shas in E2E_1115_COMMITS.items():
        for sha in shas:
            assert f"`{sha}`" in by_id[key], (key, sha)
    assert "권장과 다른 답" not in board
    memos = [key for key, chosen in E2E_1115_ANSWERS.items() if chosen.startswith("메모 「")]
    assert [key for key, line in by_id.items() if "메모 「" in line] == memos

    rules = {rule.id: rule for rule in _rules()}
    dat11 = rules["UI-DAT-11"].fields["근거"][0]
    assert "q-self-fail-rev" in dat11 and "s-A-14" in dat11 and "「판 1(그대로)」" in dat11
    con02 = rules["UI-CON-02"].fields["근거"][0]
    assert "s-C-02" in con02 and "「관리자가 넣음」" in con02
    assert "s-A-01" in rules["UI-NTF-09"].fields["근거"][0]

    # s-B-12 「이대로」 — 「정본 아님」 머리 표지의 모양은 4장에 확정, 머리 목록 · 예외에 이름.
    assert "「정본 아님」 표지" in rules["UI-LAY-05"].text
    assert "정본 아님으로 확인되지 않은 서버" in rules["UI-LAY-05"].text
    assert "정본을 받은 서버" not in rules["UI-LAY-05"].text
    assert "s-B-12" in rules["UI-LAY-05"].fields["근거"][0]
    txt06 = rules["UI-TXT-06"].fields["예외"][0]
    assert "「정본 아님」 표지" in txt06 and "s-B-12" in txt06 and "줄이지 않는다" in txt06
    assert "「정본 아님」 표지" in rules["UI-ACC-02"].fields["예외"][0]
    canon = next(
        row
        for row in _chapter(document, 4).splitlines()
        if row.startswith("| 「정본 아님」 표지 |")
    )
    for phrase in ("실선", "`cloud_off`", "12px 700", "`SY-01`", "s-B-12 「이대로」"):
        assert phrase in canon, phrase

    # s-C-14 「80일 좋음」 — 6-29 의 답 밖 값을 받았고 6-29 줄이 그 답을 가리킨다. 같은 날 밤
    # 토큰 입력 결정(6-31)으로 뒤집혀 6-30 줄은 그대로 두고 표지를 달았고, 4장 줄은 걷어 그 값을
    # 7-1 로 옮겼다.
    assert not any(
        row.startswith("| 갱신 토큰 알림 |") for row in _chapter(document, 4).splitlines()
    ), "4장 「갱신 토큰 알림」 줄은 7-1 로 옮겼다"
    refresh = next(
        line
        for line in _chapter(document, 7).splitlines()
        if line.startswith("- ") and "4장 옛 지금 값 「갱신 토큰 알림" in line
    )
    for phrase in ("처음 쓴 날부터 80일", "`AD-18`", "셈 시작일", "s-C-14 「80일 좋음」", "(6-31)"):
        assert phrase in refresh, phrase
    assert "토큰 입력 결정(6-31)으로 뒤집힘" in by_id["s-C-14"]
    frame = section[section.index("\n### 6-29. ") : section.index("\n### 6-30. ")]
    assert "s-C-14 「80일 좋음」" in frame

    # s-C-13 「지금대로」 — 시작 점검 표 「토큰 자동 갱신」 줄의 결과 낱말 · 제목 판정 밖을 예외로
    # 받았다. 2026-11-16 틀을 걷어 두 예외는 「없음」 으로 돌아갔다(v1.32 시험이 본다) — 6-29 줄의
    # 답 구절은 그때 기록 그대로다.
    assert "s-C-13 「지금대로」" in frame

    # decided-e2e 「좋음」 — 1 은 6-28 이 받은 답을 가리키고, 2 는 UI-PRF-01 예외(정확성이 이김)다.
    widened = section[section.index("\n### 6-28. ") : section.index("\n### 6-29. ")]
    band = next(line for line in widened.splitlines() if line.startswith("- band-connecting · "))
    assert "decided-e2e 1" in band and "「좋음」" in band
    assert "사용자 확인은 그림 보드에서 「좋음」" in _chapter(document, 1)
    prf01 = rules["UI-PRF-01"]
    assert "`run_every`" in prf01.fields["예외"][0] and "decided-e2e 2" in prf01.fields["예외"][0]
    assert (
        "tests/test_sidebar_box_toggle.py::"
        "test_a_page_with_a_periodic_fragment_keeps_toggles_on_the_whole_app"
        in prf01.fields["그물"][0]
    )
    assert "decided-e2e 2 · 3" in dat11

    # q-narrow-admin 「다음 판에 고침」 — TODO 2장 열린 할 일 · 3장 결정 기록 줄을 가리킨다.
    todo = (PROJECT_ROOT / "docs/TODO.md").read_text(encoding="utf-8")
    assert E2E_1115_NARROW_TODO in todo
    assert "「좁은 창(390)에서 낱말 단위 줄바꿈을 …」" in by_id["q-narrow-admin"]
    assert f"`{E2E_1115_ADDRESS}` — 규칙집 6-30 · v1.30" in todo

    # rule-list 메모 「오케이」 — 규칙 안 화면은 판정 목록으로만 보고하는 꼴을 받았다.
    prc07 = rules["PRC-07"].fields["근거"][0]
    assert "rule-list" in prc07 and "「오케이」" in prc07 and "규칙 판정 목록" in prc07

    narrowed = [line for line in _chapter(document, 7).splitlines() if "s-A-13" in line]
    assert len(narrowed) == 1, "7-1 에 공통 틀 「주 단추 하나」 를 좁힌 줄이 하나 있다"
    assert "frame" in narrowed[0] and "p1-login-fail" in narrowed[0]


TOKEN_RENEW_1115_LINES = {"token-renew-input": ("6dde83a", "6430f3b", "94a4977", "f7307b8")}
TOKEN_RENEW_MEMO = (
    "일단 내가 인지하고있는건 3개월짜리를 받는 방법은 특수한 케이스고, 우리는 8시간짜리 토큰을 "
    "6시간마다 갱신하는 방향으로 가는게 좋을것같음. 내일 토큰 갱신하는 명령어 전달해주겠음"
)


def test_the_token_renewal_input_decision_is_recorded_and_the_refresh_token_turned() -> None:
    """v1.31 — 6-31 은 2026-11-15 대화의 사용자 결정 한 줄(3개월 갱신 토큰 대신 지금 쓰는 8시간짜리
    로그인 토큰을 6시간마다) — 대화 원문 · 「답 밖 — 구현이 정함」 · 지금 「준비」 · 커밋 · 걷은
    `AD-18` 을 든다. 뒤집힌 6-29 token-auto-frame 의 갱신 토큰 몫과 그 80일을 받은 6-30 s-C-14 ·
    4장 옛 지금 값은 7-1 한 줄에 남고 6-29 줄은 그대로다(6-30 s-C-14 줄 · 4장은 v1.30 시험이
    본다). 판 머리는 v1.34 시험이 보고, 6-31 구간은 6-32 앞에서 끊는다."""
    document = _text()
    assert "- **v1.31 — 2026-11-15.**" in _chapter(document, 8)
    assert "6-31 에 있다" in _chapter(document, 1)

    section = _chapter(document, 6)
    record = section[section.index("\n### 6-31. ") : section.index("\n### 6-32. ")]
    lines = [line for line in record.splitlines() if line.startswith("- ")]
    known = {rule.id for rule in _rules()}
    found: list[str] = []
    for line in lines:
        match = re.match(r"^- ([\w-]+) · .+ → \*\*([^*]+)\*\*.*\((2026-11-15) · ([^()]+)\)$", line)
        assert match, line
        found.append(match.group(1))
        cited = RULE_TOKEN.findall(match.group(4))
        assert cited and set(cited) <= known, line
        assert "답 밖 — 구현이 정함" in line and f"「{TOKEN_RENEW_MEMO}」" in line, line
        for sha in TOKEN_RENEW_1115_LINES[match.group(1)]:
            assert f"`{sha}`" in line, (line, sha)
    assert tuple(found) == tuple(TOKEN_RENEW_1115_LINES)
    renew = lines[0]
    assert "「준비 · 요청 꼴 미정」" in renew and "6-29 token-auto-frame" in renew
    assert "renew(current_token, account)`" in renew and "`CAPA_BDQ_AUTO_REFRESH`" in renew
    assert "`AD-18`" in renew and "걷었다" in renew
    frame = section[section.index("\n### 6-29. ") : section.index("\n### 6-30. ")]
    assert "`CAPA_BDQ_REFRESH_TOKEN`" in frame and "`AD-18`" in frame, (
        "6-29 줄은 그때 기록 그대로다"
    )

    reversed_ = _chapter(document, 7)
    turned_lines = [line for line in reversed_.splitlines() if TOKEN_RENEW_MEMO in line]
    assert len(turned_lines) == 1, "7-1 에 뒤집힌 6-29 갱신 토큰 몫 줄이 하나 있다"
    turned = turned_lines[0]
    assert "6-29 token-auto-frame" in turned and "(6-31)" in turned
    assert "s-C-14" in turned and "`AD-18`" in turned and "`CAPA_BDQ_AUTO_REFRESH=on`" in turned


TOKEN_FRAME_REMOVED = "2026-11-16 사용자 결정으로 틀을 걷음(7-1)"


def test_the_token_refresh_frame_removal_is_recorded_and_its_exceptions_are_gone() -> None:
    """v1.32 — 2026-11-16 사용자 결정으로 BigDataQuery 토큰 자동 갱신 틀(6-29 · 6-31)을 걷었다.
    「서버 시작 점검」 표의 「토큰 자동 갱신」 줄이 없어져 UI-CON-02 · UI-DAT-11 예외는
    「없음」 으로 돌아갔고 규칙 글 · 4장에 그 줄이 없다. 6-29 token-auto-frame · 6-30 s-C-13 ·
    6-31 token-renew-input 줄은 그때 기록 그대로이고 걷음 표지만 달며, 뒤집힌 것은 7-1 한 줄이다.
    판 머리는 v1.34 시험이 본다."""
    document = _text()
    assert "- **v1.32 — 2026-11-16.**" in _chapter(document, 8)

    rules = {rule.id: rule for rule in _rules()}
    for rule_id in ("UI-CON-02", "UI-DAT-11"):
        assert rules[rule_id].fields["예외"] == ["없음"], rule_id
    assert "토큰 자동 갱신" not in _chapter(document, 3)
    assert "토큰 자동 갱신" not in _chapter(document, 4)

    section = _chapter(document, 6)
    for key in ("token-auto-frame", "s-C-13", "token-renew-input"):
        [line] = [line for line in section.splitlines() if line.startswith(f"- {key} · ")]
        assert TOKEN_FRAME_REMOVED in line, key

    turned_lines = [
        line
        for line in _chapter(document, 7).splitlines()
        if "2026-11-16 사용자 결정으로 틀을 걷었다" in line
    ]
    assert len(turned_lines) == 1, "7-1 에 걷은 자동 갱신 틀 줄이 하나 있다"
    turned = turned_lines[0]
    for phrase in (
        "6-29 token-auto-frame",
        "6-31 token-renew-input",
        "s-C-13",
        "`CAPA_BDQ_AUTO_REFRESH`",
        "`AD-17`",
        "「토큰 넣기」",
    ):
        assert phrase in turned, phrase


AUTO_LOGIN_1116_LINES = {"bdq-auto-login": ("7fa04ef4", "a334b157", "a8680b16", "57dcd76b")}
AUTO_LOGIN_WEBIDE_MEMO = (
    "WebIDE에서 이 계정으로 BDQ를 쓰지 않는다는것은 아님. 테스트용으로 쓸수있는데, 그 과정에서 "
    "운영서버 동작으로 인해 토큰이 초기화되는것을 감수하겠다는것."
)
AUTO_LOGIN_ADMIN_MEMO = "입력한 관리자의 앱 로그인 ID였음."
# v1.34 — 6-32 줄 밑 들여쓴 줄(같은 날 사용자 답 둘)과 그 답이 닫지 않은 「답 밖」 꼴.
AUTO_LOGIN_ANSWER_HEAD = "\n  - 2026-11-16 사용자 답 — D6 좁힘 · 새 화면 꼴: "
AUTO_LOGIN_ANSWERS = ("「이대로 (Recommended)」", "「그대로 싣기 (Recommended)」")
AUTO_LOGIN_STILL_WAITING = (
    "`BDQ_LOGIN_LABEL`",
    "`AD-23`",
    "서 있는 동안 `AD-11` 해소",
    "60초",
    "접힌 펼침 하나",
    "폼 아래 닿지 못함 · 패키지 없음 한 줄",
    "지우기 숨김",
    "「넣기」 단추 둘",
    "펼침 안 인라인 비밀 폼",
    "`AD-10` 의 할 일 다시 넣기 먼저",
)


def test_the_bdq_auto_login_decision_is_recorded_with_what_the_implementation_chose() -> None:
    """v1.33 — 6-32 는 2026-11-16 BigDataQuery 자동 로그인 사용자 결정(D1 ~ D11) 가운데 화면에
    걸리는 몫 한 줄이다 — 폼 자리 · 실패면 저장 안 함 · 폼에 보일 것 · 멈춤 알림 · 서버 혼잡 안내와
    대화 원문 둘(D7 넣은 관리자 · D11 WebIDE)을 들고, 구현이 답 밖에서 정한 꼴은 「답 밖 — 구현이
    정함」 에 사용자 확인 대기로 남긴다(규칙 예외 칸에는 올리지 않음). 뒤집힌 결정은 없다.
    판 머리는 v1.34 시험이 보고, 6-32 구간은 v1.34 의 들여쓴 줄 앞에서 끊는다."""
    document = _text()
    assert "- **v1.33 — 2026-11-16.**" in _chapter(document, 8)
    assert "6-32 에 있다" in _chapter(document, 1)

    section = _chapter(document, 6)
    start = section.index("\n### 6-32. ")
    record = section[start : section.index(AUTO_LOGIN_ANSWER_HEAD, start)]
    lines = [line for line in record.splitlines() if line.startswith("- ")]
    known = {rule.id for rule in _rules()}
    found: list[str] = []
    for line in lines:
        match = re.match(r"^- ([\w-]+) · .+ → \*\*([^*]+)\*\*.*\((2026-11-16) · ([^()]+)\)$", line)
        assert match, line
        found.append(match.group(1))
        cited = RULE_TOKEN.findall(match.group(4))
        assert cited and set(cited) <= known, line
        for sha in AUTO_LOGIN_1116_LINES[match.group(1)]:
            assert f"`{sha}`" in line, (line, sha)
    assert tuple(found) == tuple(AUTO_LOGIN_1116_LINES)
    [decision] = lines
    for phrase in (
        "D1 ~ D11",
        f"「{AUTO_LOGIN_WEBIDE_MEMO}」",
        f"「{AUTO_LOGIN_ADMIN_MEMO}」",
        "답 밖 — 구현이 정함(사용자 확인 대기)",
        "`AD-23`",
        "`AD-11`",
        "`BDQ_LOGIN_LABEL`",
        "저장하지 않고 폼에 실패만",
        "BDQ 계정 ID 는 보이지 않는다",
    ):
        assert phrase in decision, phrase
    assert "bdq-auto-login" not in _chapter(document, 7), "뒤집힌 결정이 없어 7-1 에 줄이 없다"


def test_the_bdq_auto_login_answers_close_the_narrowed_d6_and_the_new_forms() -> None:
    """v1.34 — 6-32 줄은 그때 기록 그대로 두고, 그 밑 들여쓴 줄 하나(6-14 Q2-26 선례)가 같은 날
    사용자 답 둘(D6 좁힘 · 새 화면 꼴)을 고른 글 원문으로 들어 그 꼴들의 사용자 확인 대기를 닫는다.
    묻지 않은 나머지 「답 밖」 꼴은 그대로 대기이고, 셋째 답(토큰 만료 대응)은 화면 결정이 아니라
    TODO 에만 있다. D6 은 좁혔을 뿐이라 7-1 줄이 없다. 판 머리는 v1.35 시험이 보고, 6-32 구간은
    6-33 앞에서 끊는다."""
    document = _text()
    assert "- **v1.34 — 2026-11-16.**" in _chapter(document, 8)

    section = _chapter(document, 6)
    record = section[section.index("\n### 6-32. ") : section.index("\n### 6-33. ")]
    [decision] = [line for line in record.splitlines() if line.startswith("- ")]
    assert "답 밖 — 구현이 정함(사용자 확인 대기)" in decision, "6-32 줄은 그때 기록 그대로다"
    assert record.count(AUTO_LOGIN_ANSWER_HEAD) == 1
    tail = record[record.index(AUTO_LOGIN_ANSWER_HEAD) + 1 :]
    [answer] = [line for line in tail.splitlines() if line.startswith("  - ")]
    match = re.search(r"\((2026-11-16) · ([^()]+)\)$", answer)
    assert match, answer
    cited = RULE_TOKEN.findall(match.group(2))
    assert cited and set(cited) <= {rule.id for rule in _rules()}, answer
    for phrase in (
        *AUTO_LOGIN_ANSWERS,
        "`AD-24`",
        "「로그인 확인 못 함(까닭) — 저장 안 함」",
        "「결과 저장 못 함」",
        "「멈춤 — 닿지 못함 · 확인 못 함 연속 상한」",
        "「멈춤 — 시도 결과를 적지 못함」",
        "「꺼짐 — 키 없음」",
        "성공 없이 3번",
        "뒤집은 것이 아니다",
    ):
        assert phrase in answer, phrase
    waiting = answer[answer.index("묻지 않은 나머지") :]
    for phrase in AUTO_LOGIN_STILL_WAITING:
        assert phrase in waiting, phrase
    assert "그대로 사용자 확인 대기다" in waiting
    assert "셋째 답(토큰 만료 대응)" in answer and "`docs/TODO.md` 1장" in answer
    assert "bdq-auto-login" not in _chapter(document, 7), "D6 은 좁혔을 뿐이라 7-1 에 줄이 없다"

    todo = (PROJECT_ROOT / "docs/TODO.md").read_text(encoding="utf-8")
    entry = todo[todo.index("- [ ] **BigDataQuery 자동 로그인**") :]
    entry = entry[: entry.index("\n- [")]
    for answer_text in AUTO_LOGIN_ANSWERS:
        assert answer_text in entry, answer_text
    assert "「일반 오류일 때만 넣기 (Recommended)」" in entry


NOTICE_1117_LINES = (
    "q-use",
    "q-look",
    "q-speed",
    "q-until",
    "q-name",
    *(f"decided-{n}" for n in range(1, 10)),
)
NOTICE_1117_NAME_MEMO = "HOME의 공지는 'Capa 요약'으로 변경"


def test_the_notice_board_answers_are_recorded_with_what_the_implementation_chose() -> None:
    """v1.35 — 6-33 은 2026-11-17 공지 기능 보드의 카드 다섯과 정한 것 아홉이 차례대로 한 줄씩이고
    (모두 「(2026-11-17 · 규칙 id)」 로 끝남), 권장이 아닌 이름 답의 메모가 원문 그대로다. 구현이
    좁게 정한 것은 표로 사용자 확인 대기에 남는다. 예외를 더한 UI-TXT-06 · 차례를 고친 UI-LAY-05 가
    「공지」 칩을 든다."""
    document = _text()
    assert "- **v1.35 — 2026-11-17.**" in _chapter(document, 8)
    assert "6-33 에 있다" in _chapter(document, 1)

    section = _chapter(document, 6)
    record = section[section.index("\n### 6-33. ") : section.index("\n### 6-34. ")]
    assert "https://claude.ai/artifact/B1pkodTjQDZLJseRW9F57F" in record
    lines = [line for line in record.splitlines() if line.startswith("- ")]
    known = {rule.id for rule in _rules()}
    found: list[str] = []
    for line in lines:
        match = re.match(r"^- ([\w-]+) · .+ → \*\*([^*]+)\*\*.*\((2026-11-17) · ([^()]+)\)$", line)
        assert match, line
        found.append(match.group(1))
        cited = RULE_TOKEN.findall(match.group(4))
        assert cited and set(cited) <= known, line
    assert tuple(found) == NOTICE_1117_LINES
    name = next(line for line in lines if line.startswith("- q-name "))
    assert f"「{NOTICE_1117_NAME_MEMO}」" in name and "권장이 아닌 답" in name
    for phrase in ("`GL-09`", "`admin_notice_send`", "`window.__capaAlerts.notice`", "본문은 싣지"):
        assert phrase in record, phrase
    table = record[record.index("구현이 좁게 정한 것(보드에 올리지 않음") :]
    assert "| 알림 번호 · 단계 |" in table and "| 끝 시각 기본값 |" in table

    rules = {rule.id: rule for rule in _rules()}
    assert "「공지」 칩(2026-11-17 공지 보드 답 q-look" in " ".join(
        rules["UI-TXT-06"].fields["예외"]
    )
    assert "「공지」 칩은 Guide 바로 왼쪽" in rules["UI-LAY-05"].text


def test_the_notice_name_answer_reverses_the_old_home_box_name_once() -> None:
    """v1.35 — q-name(권장이 아닌 답)은 2026-11-07 names 의 HOME 상자 이름 「공지」 를
    뒤집는다. 7-1 에 그 줄이 하나 있고 UI-CON-02 근거가 q-name 을 들며, 6-9 names 줄은 그때
    기록 그대로다."""
    document = _text()
    turned = [line for line in _chapter(document, 7).splitlines() if "q-name" in line]
    assert len(turned) == 1, "7-1 에 q-name 이 뒤집은 HOME 상자 이름 줄이 하나 있다"
    assert "6-9 names" in turned[0] and f"「{NOTICE_1117_NAME_MEMO}」" in turned[0]
    assert "「Capa 요약 · 표시」" in turned[0]
    rules = {rule.id: rule for rule in _rules()}
    assert "공지 기능 보드 q-name" in " ".join(rules["UI-CON-02"].fields["근거"])
    names = next(
        line for line in _chapter(document, 6).splitlines() if line.startswith("- names · ")
    )
    assert "HOME 상자 「공지」" in names, "6-9 names 줄은 그때 기록 그대로다"


def test_the_notice_chip_exceptions_and_values_match_the_code() -> None:
    """v1.35 — 「공지」 칩은 좁은 창(900px 미만)에서 공정 칩 · 합성 샘플 표지처럼 확성기
    아이콘만이다(같은 날 공지 확인 보드 q-narrow — 권장이 아닌 답. UI-ACC-02 예외에 그 칩이 없고
    코드는 `alert_center.css` 900px 미만 규칙의 `.notice .word`). 풍선 · 읽기
    이름은 짧은 글 표의 고정 글(UI-TXT-06 예외 — 관리자 글 없음)이며, Admin 끝 시각 칸
    (`st.time_input`)은 UI-INP-03 밖이다. 4장 지금 값에 「공지」 칩 줄이 있고(검수 전),
    「정본 아님」 줄은 변경 칩 다음을 Guide 로 적지 않고 이제 그 표지만 좁은 창 규칙이 없다고
    말한다. 6-33 표는 끝 시각 기본값을 「세션에 한 번」 으로 적지 않는다(화면을 떠났다 오면 다시
    심고, 손대지 않은 기본값이 지나면 새 기본값). 확인 보드가 답한 표 칸(「칩 풍선 · 좁은 창」 ·
    「끝 시각 글」)은 그 답을 든다. 8장 v1.35 기록에 확인 보드 답 넷이 있다."""
    document = _text()
    rules = {rule.id: rule for rule in _rules()}
    narrow = " ".join(rules["UI-ACC-02"].fields["예외"])
    assert "「정본 아님」 표지는 좁은 창에서도" in narrow and "「공지」" not in narrow
    assert "공지 확인 보드 q-narrow" in " ".join(rules["UI-ACC-02"].fields["근거"])
    assert "Admin 「공지」 끝 시각" in " ".join(rules["UI-INP-03"].fields["예외"])
    plain = " ".join(rules["UI-TXT-06"].fields["예외"])
    assert "칩 풍선 · 읽기 이름도 같은 표의 고정 글" in plain
    assert "좁은 창에서는 공정 칩 · 합성 샘플 표지처럼 확성기 아이콘만" in plain

    values = _chapter(document, 4).splitlines()
    [chip] = [line for line in values if line.startswith("| 「공지」 칩 |")]
    for phrase in ("`campaign` 13px", "확성기 아이콘만", "q-narrow", "Guide 바로 왼쪽", "검수 전"):
        assert phrase in chip, phrase
    assert "좁은 창 규칙 없음" not in chip
    [canon] = [line for line in values if line.startswith("| 「정본 아님」 표지 |")]
    assert "변경 칩 · 「공지」 칩 · Guide 왼쪽" in canon
    assert "이 표지만 좁은 창 규칙이 없다" in canon
    assert "합성 샘플 표지 · 「공지」 칩은 900px 미만 아이콘만" in canon

    section = _chapter(document, 6)
    record = section[section.index("\n### 6-33. ") : section.index("\n### 6-34. ")]
    table = record[record.index("구현이 좁게 정한 것(보드에 올리지 않음") :]
    for row in ("| 끝 시각 글 |", "| 끝 시각 칸 |", "| 칩 풍선 · 좁은 창 |", "| 공지 줄 보관 |"):
        assert row in table, row
    [tip] = [line for line in table.splitlines() if line.startswith("| 칩 풍선 · 좁은 창 |")]
    assert "900px 미만 창에서는 확성기 아이콘만" in tip and "글째" not in tip
    # 확인 보드가 답한 칸은 「사용자 확인 대기」 표 안에서도 그 답을 든다(PRC-02).
    [until] = [line for line in table.splitlines() if line.startswith("| 끝 시각 글 |")]
    assert "공지 확인 보드 q-long 「값 줄만으로 둔다」" in until and "사용자 확인" in until
    assert "q-narrow" in tip
    assert "세션에 한 번" not in table
    assert "다른 관리자가 공지를 바꿨습니다" not in record
    history = _chapter(document, 8)
    assert "UI-ACC-02 「공지」 칩" in history
    v135 = history[history.index("- **v1.35 — 2026-11-17.**") :]
    v135 = v135[: v135.index("\n- **v1.3")] if "\n- **v1.3" in v135 else v135
    for phrase in (
        "https://claude.ai/artifact/FVdiHY3N3fH6dNa5oJeVdZ",
        "q-narrow 「좁은 창에서는 확성기 아이콘만」(권장이 아닌 답",
        "q-voc 「그대로 둔다」",
        "q-long 「값 줄만으로 둔다」",
        "checked 「좋음」",
        "7-1 줄은 없다",
    ):
        assert phrase in v135, phrase


# 2026-11-17 접속 등급 두 차례 보드(6-34) — 1차 카드 넷 · 2차 카드 다섯, 이 차례로 한 줄씩.
ACCESS_GRADES_1117_LINES = (
    "existing-members",
    "m-grades",
    "new-members",
    "viewer-what-if",
    "readback-2",
    "downtime-which-2",
    "m-grades-2",
    "view-as-2",
    "decided-2",
)
# 메모 원문(줄바꿈은 「 / 」 — 2차 메모의 겹빈칸도 그대로).
ACCESS_GRADES_1117_MEMOS = {
    "existing-members": (
        "스스로 등록은 열람으로 등록, 기존 명단 또한 개발자 외 전부 열람 권한으로 반영"
    ),
    "m-grades": (
        "열람자 → 열람, 실무자, 공식 지정자 → 관리자, 관리자 → 개발자 / 이렇게 이름 지정하고,"
    ),
    "m-grades-2": (
        "설비마스터  비가동 일정 표 고치기  저장 내려받기  실무자 가능 / "
        "입력 비가동 - 고치기 저장 실무자 가능"
    ),
}


def test_the_access_grade_board_answers_are_recorded_with_what_the_implementation_chose() -> None:
    """v1.36 — 6-34 는 2026-11-17 접속 등급 보드 두 차례의 카드 아홉이 차례대로 한 줄씩이고
    (모두 「(2026-11-17 · 규칙 id)」 로 끝남), 메모 셋이 원문 그대로이며 권장이 아닌 답(비가동
    「둘 다」)이 그렇다고 적힌다. 답 밖에서 구현이 정한 것은 표로 사용자 확인 대기에 남는다.
    등급 밖 기능 숨김은 UI-INP-07 의 예외, 카드 등급 표지는 UI-TXT-05 의 예외(「없음」 이던
    자리), 누른 순간 거절은 UI-NTF-03 글, 넣는 창 등급 칸은 UI-INP-08 예외다."""
    document = _text()
    assert "- **v1.36 — 2026-11-18.**" in _chapter(document, 8)
    assert "6-34 에 있다" in _chapter(document, 1)

    section = _chapter(document, 6)
    record = section[section.index("\n### 6-34. ") : section.index("\n### 6-35. ")]
    lines = [line for line in record.splitlines() if line.startswith("- ")]
    known = {rule.id for rule in _rules()}
    found: list[str] = []
    for line in lines:
        match = re.match(r"^- ([\w-]+) · .+ → \*\*([^*]+)\*\*.*\((2026-11-17) · ([^()]+)\)$", line)
        assert match, line
        found.append(match.group(1))
        cited = RULE_TOKEN.findall(match.group(4))
        assert cited and set(cited) <= known, line
    assert tuple(found) == ACCESS_GRADES_1117_LINES
    for card, memo in ACCESS_GRADES_1117_MEMOS.items():
        line = next(line for line in lines if line.startswith(f"- {card} · "))
        assert f"「{memo}" in line and "메모 답" in line, card
    downtime = next(line for line in lines if line.startswith("- downtime-which-2 · "))
    assert "**(다) 둘 다**(권장이 아닌 답" in downtime and "통째로 저장하지 않는다" in downtime
    view_as = next(line for line in lines if line.startswith("- view-as-2 · "))
    assert "**(가) 싣는다**" in view_as and "실제 등급" in view_as
    table = record[record.index("답 밖 — 구현이 정함(") :]
    for row in (
        "| 「이 등급으로 보기」 끝내기 |",
        "| 숨은 탭 멈춤 |",
        "| 고침 꼬리 |",
        "| 입력 비가동 내려받기 |",
        "| 표 도구 막대 감춤 |",
        "| 주요공정 히트맵 프리셋 |",
    ):
        assert row in table, row

    rules = {rule.id: rule for rule in _rules()}
    hidden = rules["UI-INP-07"].fields["예외"][0]
    assert "등급 밖 기능은 숨긴다" in hidden and "그대로 잠금 + 까닭 풍선" in hidden
    assert "등급 때문에 못 하는 것인가" in rules["UI-INP-07"].fields["판단"][0]
    assert "tests/test_grade_ui_core.py" in rules["UI-INP-07"].fields["그물"][0]
    mark = rules["UI-TXT-05"].fields["예외"][0]
    assert mark != "없음" and "열람 · 실무자만" in mark and "6-34" in mark
    assert "누른 순간의 등급 거절" in rules["UI-NTF-03"].text
    history = _chapter(document, 8)
    v136 = history[history.index("- **v1.36 — 2026-11-18.**") :]
    for phrase in ("6-34", "UI-INP-07", "UI-TXT-05", "UI-INP-08", "UI-NTF-03", "7-1 줄은 없다"):
        assert phrase in v136, phrase


def test_the_next_deploy_grid_fixes_close_the_6_34_paragraph_and_fit_ui_inp_08() -> None:
    """v1.37 — 6-34 구현 확인 보드의 「고칠 것」 둘(접속 명단 편집 표 · 설비 마스터 같은 편집 표의
    권한 잠금)이 6-34 끝 문단에 있고(카드 줄 꼴 밖 — `- ` 로 시작하지 않는다), UI-INP-08 범위 ·
    예외에서 걷은 접속 명단 추가 창이 빠졌다."""
    document = _text()
    history = _chapter(document, 8)
    v137 = history[history.index("- **v1.37 — 2026-11-18.**") :]
    for phrase in ("6-34", "UI-INP-08", "new-members (가)", "tests/test_access_list_grid.py"):
        assert phrase in v137, phrase
    # 새 줄 등급의 처음 값(실무자 → 빈칸)은 뒤집힌 답이라 7-1 에도 한 줄이다(PRC-02).
    flipped = _chapter(document, 7)
    assert "6-34 new-members (가)" in flipped and "새 줄 등급은 처음 값 없이 빈칸" in flipped
    section = _chapter(document, 6)
    record = section[section.index("\n### 6-34. ") : section.index("\n### 6-35. ")]
    (paragraph,) = [line for line in record.splitlines() if line.startswith("다음 배포 고침(")]
    for phrase in (
        "feat/grid-1118",
        "① Admin 「접속 명단」",
        "줄 규칙 표",
        "「줄 지우기」",
        "빼기 → 등급 바꿈 → 넣기",
        "② 가용설비 현황 › 설비 마스터",
        "UI-INP-07 등급 예외",
    ):
        assert phrase in paragraph, phrase
    rules = {rule.id: rule for rule in _rules()}
    assert "접속 명단 추가," not in rules["UI-INP-08"].fields["범위"][0]
    exceptions = rules["UI-INP-08"].fields["예외"][0]
    assert "「엑셀·CSV로 한꺼번에」(곁의 「또는 CSV 파일 업로드」 와 짝) 하나다" in exceptions
    assert "등급 고르기 칸(처음 값 실무자)" not in exceptions


def test_the_unsaved_guard_requests_are_judged_in_6_35() -> None:
    """v1.38 — 2026-11-19 사용자 미저장 보호 요청을 앱에 이미 있는 꼴로 입힌 판정이 6-35 줄마다
    있고(걸린 규칙 id · 「답 밖 — 구현이 정함」), 1장 안내가 그 절을 가리킨다. 판 머리는 v1.39
    시험이 보고, 6-35 구간은 6-36 앞에서 끊는다."""
    document = _text()
    assert "6-35 에 있다" in _chapter(document, 1)
    history = _chapter(document, 8)
    v138 = history[history.index("- **v1.38 — 2026-11-19.**") :]
    for phrase in ("6-35", "UI-STA-02", "tests/test_manual_downtime_tab.py"):
        assert phrase in v138, phrase
    section = _chapter(document, 6)
    record = section[section.index("\n### 6-35. ") : section.index("\n### 6-36. ")]
    lines = {
        line.split(" · ", 1)[0][2:]: line for line in record.splitlines() if line.startswith("- ")
    }
    manual = lines["guard-manual"]
    for phrase in (
        "UI-STA-02 판정",
        "떠나기 확인",
        "답 밖 — 구현이 정함",
        "「되돌리기」",
        "UI-NTF-09",
    ):
        assert phrase in manual, phrase
    floor = lines["guard-floor"]
    for phrase in (
        "브라우저 확인 창",
        "「변경을 버리고 열기」",
        "새 꼴은 만들지 않았다",
        "UI-STA-02 판정",
        "UI-NTF-09 판정",
        "답 밖 — 구현이 정함",
        # 「누른 화면 탭이 Space 에 남는 수」 는 같은 날 밤 서버 막이로 닫았다.
        "고쳐 닫았다",
        "`stale_page_guard`",
    ):
        assert phrase in floor, phrase
    assert "tests/test_space_floor_state_page.py" in v138


# 2026-11-19 아침 확인 보드(6-36) — 카드 스물다섯, 보드 차례대로 한 줄씩.
MORNING_1119_LINES = (
    "m19-guard-manual",
    "m19-guard-floor",
    "m19-extra2-screen",
    "m19-extra2-avail",
    "m19-extra2-newfile",
    "m19-extra2-button",
    "m19-extra2-shift",
    "m19-manual-rerun",
    "m19-manual-hidden",
    "m19-manual-undo",
    "m19-rr-result",
    "m19-rr-tooltip",
    "m19-rr-autotab",
    "m19-rr-d1",
    "m19-rr-d3",
    "m19-rr-d4",
    "m19-rr-d5",
    "m19-rr-d8",
    "m19-e2e-space-leave",
    "m19-e2e-first-apply",
    "m19-e2e-repeat-alert",
    "m19-e2e-percent",
    "m19-e2e-chart-copy",
    "m19-v-fix4",
    "m19-v-e2e",
)
# 고른 안의 글(보드 카드 choices) — 「좋음」 은 확인 · 정한 것 · 판정 카드.
MORNING_1119_ANSWERS = {
    "m19-extra2-avail": "(가) 지금대로 — 그 공정은 통째로 옮기지 않음",
    "m19-extra2-newfile": "(가) 가져오기만으로 세우고, 쓰는 쪽이 없는 동안 상태 알림 하나",
    "m19-extra2-button": "(가) 잠긴 채 둠",
    "m19-extra2-shift": "(나) 안 넣음",
    "m19-manual-rerun": "(가) 먼저 재고, 느리면 그때 묻기",
    "m19-manual-hidden": "(가) 모두 버리고 수만 알림",
    "m19-manual-undo": "(가) 확인 없음",
    "m19-rr-tooltip": "(가) 받아들임",
    "m19-rr-autotab": "(가) 받아들임",
    **{f"m19-rr-d{n}": "(나) 그대로 — 사내에서 재 본 뒤" for n in (1, 3, 4, 5, 8)},
    "m19-e2e-space-leave": "(나) 층 사용 편집을 화면을 떠나도 남김",
    "m19-e2e-first-apply": "(가) 단추를 늘 켜 둠",
    "m19-e2e-repeat-alert": "(가) 그대로",
    "m19-e2e-percent": "(나) 앱의 % 표 칸을 한 번에 소수 둘째 자리",
}
# 같은 판에서 따로 갈래가 구현하는 답 — 여기 줄은 답과 걸린 규칙 id 만.
MORNING_1119_CODE_CHANGES = ("m19-e2e-space-leave", "m19-e2e-first-apply", "m19-e2e-percent")


def test_the_morning_1119_board_answers_are_recorded_in_6_36() -> None:
    """v1.39 — 6-36 은 2026-11-19 아침 확인 보드의 카드 스물다섯이 보드 차례대로 한 줄씩이고
    (모두 「(2026-11-19 · 규칙 id)」 로 끝남), 고른 안의 글이 굵게 선다. 권장이 아닌 답은 부대공정
    가용대수 (가) 하나이고 그 까닭 글이 「새 판으로」 의 코드 상수와 같다(지금 코드가 그 답대로
    그 공정을 옮기지 않음). 코드를 바꾸는 셋은 「같은 판에서 구현」 이고, space-leave 가 바꾼
    2026-10-24 답은 7-1 에 한 줄이다."""
    from capa_simulation.services.extra_process_revision import AVAILABLE_REASON

    document = _text()
    assert "6-36 에 있다" in _chapter(document, 1)
    section = _chapter(document, 6)
    record = section[section.index("\n### 6-36. ") : section.index("\n### 6-37. ")]
    lines = [line for line in record.splitlines() if line.startswith("- ")]
    known = {rule.id for rule in _rules()}
    found: list[str] = []
    for line in lines:
        match = re.match(r"^- ([\w-]+) · .+ → \*\*([^*]+)\*\*.*\((2026-11-19) · ([^()]+)\)$", line)
        assert match, line
        card, answer = match.group(1), match.group(2)
        found.append(card)
        assert answer == MORNING_1119_ANSWERS.get(card, "좋음"), card
        cited = RULE_TOKEN.findall(match.group(4))
        assert cited and set(cited) <= known, line
        assert ("권장이 아닌 답" in line) == (card == "m19-extra2-avail"), card
        assert ("같은 판에서 구현" in line) == (card in MORNING_1119_CODE_CHANGES), card
    assert tuple(found) == MORNING_1119_LINES
    by_id = {line.split(" · ", 1)[0][2:]: line for line in lines}
    avail = by_id["m19-extra2-avail"]
    assert "권장은 (다)" in avail and f"「{AVAILABLE_REASON}」" in avail
    leave = by_id["m19-e2e-space-leave"]
    assert "「사이드바 링크 · 뒤로가기는 그대로」" in leave and "(7-1)" in leave

    turned = [line for line in _chapter(document, 7).splitlines() if "m19-e2e-space-leave" in line]
    assert len(turned) == 1, "7-1 에 space-leave 가 바꾼 2026-10-24 답 줄이 하나 있다"
    assert "2026-10-24 페이지 탭 1단계 답" in turned[0] and "6-36" in turned[0]
    # percent 는 새 규칙 UI-DAT-12 를 세우고 2026-10-24 결정 판 P1 「지금대로」 를 바꾼다(7-1).
    percent = by_id["m19-e2e-percent"]
    assert "UI-DAT-12" in percent and "(7-1)" in percent
    assert "#### UI-DAT-12 · " in document
    p1 = [line for line in _chapter(document, 7).splitlines() if "m19-e2e-percent" in line]
    assert len(p1) == 1 and "결정 판 P1 「지금대로」" in p1[0] and "UI-DAT-12" in p1[0]
    history = _chapter(document, 8)
    v139 = history[history.index("- **v1.39 — 2026-11-19.**") :]
    for phrase in ("6-36", "m19-extra2-avail", "7-1", "규칙 82", "UI-DAT-12"):
        assert phrase in v139, phrase


# 2026-11-20 필요 단축 일정 「누적 진척」 시안 보드(6-37)의 카드 차례와 고른 답.
CUMULATIVE_1120_ANSWERS = {
    "cum-form": "(가) A 한 줄 띠 + 「주차별」 을 누르면 B",
    "cum-record": "(다) 손으로 적기",
    "cum-goal": "(가) 사용자가 정함 — 목표 일수와 목표 주차 하나",
    "cum-scope": "「한 줄 기록」",
    "cum-place": "(가) 늘 보임(머리 한 줄)",
}


def test_the_cumulative_1120_board_answers_are_recorded_in_6_37() -> None:
    """v1.40 — 6-37 은 2026-11-20 「누적 진척」 시안 보드 카드 다섯이 보드 차례대로 한 줄씩이고(모두
    「(2026-11-20 · 규칙 id)」 로 끝남), 고른 답이 굵게 선다. 권장이 아닌 답은 cum-record 하나이고
    cum-scope 는 다시 물은 답이다. UI-LAY-13 예외에 그 띠가 선다."""
    document = _text()
    assert "6-37 에 있다" in _chapter(document, 1)
    section = _chapter(document, 6)
    record = section[section.index("\n### 6-37. ") : section.index("\n### 6-38. ")]
    lines = [line for line in record.splitlines() if line.startswith("- ")]
    known = {rule.id for rule in _rules()}
    found: list[str] = []
    for line in lines:
        match = re.match(r"^- ([\w-]+) · .+ → \*\*([^*]+)\*\*.*\((2026-11-20) · ([^()]+)\)$", line)
        assert match, line
        card, answer = match.group(1), match.group(2)
        found.append(card)
        assert answer == CUMULATIVE_1120_ANSWERS[card], card
        cited = RULE_TOKEN.findall(match.group(4))
        assert cited and set(cited) <= known, line
        assert ("권장이 아닌 답" in line) == (card == "cum-record"), card
    assert tuple(found) == tuple(CUMULATIVE_1120_ANSWERS)
    top = document[document.index("#### UI-LAY-13 · ") : document.index("#### UI-INP-01 · ")]
    assert "「누적 진척」 한 줄 띠" in top and "6-37" in top
    history = _chapter(document, 8)
    v140 = history[history.index("- **v1.40 — 2026-11-20.**") :]
    for phrase in ("6-37", "cum-record", "UI-LAY-13", "규칙 82"):
        assert phrase in v140, phrase


def test_the_result_1120_board_answers_are_recorded_in_6_38() -> None:
    """v1.41 — 6-38 은 2026-11-20 다음 배포 후보 결과 보드의 답이다(확인 넷 「좋음」 · 여쭘
    다섯 모두 a). 코드를 바꾸는 답은 한 줄씩이고(「(2026-11-20 · 규칙 id)」 로 끝남) 고른 답이
    굵게 선다 — 여쭘-2 a 는 설비 마스터 표 글 칸 머리 정렬도 설비명 칸과 같은 비교 하나이고,
    그 답이 UI-CON-04 근거 · 그물에 선다."""
    document = _text()
    assert "판 v1.41" in document.split("\n## 1. ")[0]
    assert "6-38 에 있다" in _chapter(document, 1)
    section = _chapter(document, 6)
    record = section[section.index("\n### 6-38. ") :]
    assert "확인 넷은 모두 「좋음」" in record and "여쭘 다섯은 모두 a" in record
    known = {rule.id for rule in _rules()}
    answers: dict[str, str] = {}
    for line in (line for line in record.splitlines() if line.startswith("- ")):
        match = re.match(r"^- ([\w-]+) · .+ → \*\*([^*]+)\*\*.*\((2026-11-20) · ([^()]+)\)$", line)
        assert match, line
        cited = RULE_TOKEN.findall(match.group(4))
        assert cited and set(cited) <= known, line
        answers[match.group(1)] = match.group(2)
    assert answers["여쭘-2"] == "a 글 칸 모두 설비명 칸과 같은 차례"
    con04 = next(rule for rule in _rules() if rule.id == "UI-CON-04")
    assert "결과 보드 여쭘-2 a(6-38)" in con04.fields["근거"][0]
    net = "test_text_columns_sort_in_the_same_order_as_the_name_column_and_the_condition_values"
    assert net in con04.fields["그물"][0]
    history = _chapter(document, 8)
    v141 = history[history.index("- **v1.41 — 2026-11-20.**") :]
    for phrase in ("6-38", "여쭘-2 a", "UI-CON-04", "규칙 82"):
        assert phrase in v141, phrase


def test_the_rule_chapters_name_the_developer_for_the_old_manager_sense() -> None:
    """v1.36 — 3 · 4장이 지금 화면을 말하는 자리의 옛 뜻 「관리자」(접힌 진단 이름 · 진단 몫 · 공지
    보낸 이 · 칩 풍선 글)는 「개발자」 다. 날짜 붙은 결정 기록(6장)과 근거 칸의 인용은 그대로다."""
    document = _text()
    rules_part = document[document.index("\n## 3. ") : document.index("\n## 6. ")]
    for old in (
        "「관리자용 진단」",
        "admin_notes_visible",
        "「공지 · 관리자 · 17:40」",
        "관리자가 보낸 글",
    ):
        assert old not in rules_part, old
    assert "「개발자용 진단」" in rules_part and "「공지 · 개발자 · 17:40」" in rules_part
