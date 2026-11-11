# Purpose: 사내 런북의 모델 구간 표지 · 7장 군살 규칙 · 그림 읽기 막기 권한이 서로 맞는지 본다.

"""런북 0-2 — 사내 적용은 기본 Sonnet 이고 Opus 구간 넷에서만 모델을 바꿔 달라고 한다(2026-11-03).

구간 2(6-3 B 대행)와 6(9장 사내 탐색)은 그 일을 걷어(에이전트는 사내 DB 를 여는 코드를 치지 않는다 —
런북 0장) 번호를 비워 둔다. 지난 리뷰의 `모델 sonnet <n>` 뜻이 바뀌지 않게 다시 매기지 않는다.

Sonnet 은 구간을 스스로 가르지 않고 표지를 보고 멈춘다. 그래서 0-2 표의 구간 번호와 구간 머리의
표지가 한 꼴 · 한 벌로 맞아야 하고, 표지는 표가 적은 자리에 서야 한다. 7장은 배포마다 다시 쓰이므로
7장 머리의 표지와 「하지 않는 앞 배포 몫은 싣지 않는다」 규칙은 여기서 지킨다(`docs/TODO.md`
「다음 배포 7장 쓰기 규칙」). 권한 템플릿의 그림 읽기 막기는 런북 0장 문장과 함께 본다.
"""

import json
import re
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNBOOK = PROJECT_ROOT / "docs" / "internal_update_runbook.md"
TEMPLATE = PROJECT_ROOT / "docs" / "internal_claude_settings.json"
DUAL_ENV = PROJECT_ROOT / "docs" / "dual_env_workflow.md"
README = PROJECT_ROOT / "README.md"
MARKER = re.compile(
    r"^> \*\*\[Opus 구간 (?P<number>\d)\]\*\* 들어가기 전에 0-2 대로 모델을 바꿔 달라고 한다"
    r"(?: — [^\n]+)?\.$",
    re.MULTILINE,
)
# 표지가 그 머리 바로 아래(빈 줄 하나 뒤) 첫 문단이어야 하는 구간.
HEADED = {
    1: "## 7. 이번 배포에서 사내가 따로 확인해야 하는 것",
    3: "### 4-6. ",
    4: "## 6. 막혔을 때",
    5: "## 5. 리뷰 문서 쓰기",
}
EMPTIED = (2, 6)
PICTURES = ("png", "jpg", "jpeg", "webp", "gif", "bmp")


def _text() -> str:
    return RUNBOOK.read_text(encoding="utf-8")


def _section(text: str, start: str, end: str) -> str:
    begin = text.index(start)
    return text[begin : text.index(end, begin + len(start))]


def _first_paragraph_after(text: str, heading: str) -> str:
    begin = text.index(heading)
    after = text[text.index("\n", begin) + 1 :].lstrip("\n")
    return after.split("\n\n", 1)[0]


def test_the_model_section_sits_between_the_two_ways_and_chapter_one() -> None:
    text = _text()
    assert text.index("## 0-1. ") < text.index("## 0-2. ") < text.index("## 1. 시작 전 점검")
    assert "**0장 · 0-1 · 0-2 · 1장 ~ 6장 · 8장은 배포마다 같다**" in text


def test_every_opus_section_has_one_marker_where_the_table_says() -> None:
    """0-2 표의 구간 번호마다 표지가 한 번씩, 표가 적은 자리(그 머리 바로 아래)에 선다. 걷은 구간
    2 · 6 은 표에도 표지에도 없고, 0-2 가 번호를 비워 둔 까닭을 적는다."""
    text = _text()
    model = _section(text, "## 0-2. ", "\n## 1. ")
    table = [int(number) for number in re.findall(r"^\| (\d) \| ", model, re.MULTILINE)]
    assert table == [1, 3, 4, 5]

    found = Counter(int(match.group("number")) for match in MARKER.finditer(text))
    assert sorted(found) == table
    assert set(found.values()) == {1}, found

    for number, heading in HEADED.items():
        assert MARKER.fullmatch(_first_paragraph_after(text, heading)), heading
        assert f"[Opus 구간 {number}]" in _first_paragraph_after(text, heading), heading

    for number in EMPTIED:
        assert f"[Opus 구간 {number}]" not in text, number
    assert "번호 2(옛 6-3 B 대행)와 6(옛 9장 탐색)은 비워 둔다" in model


def test_the_first_section_says_when_it_starts() -> None:
    """Sonnet 첫 읽기(2026-11-03)가 헷갈린 자리 — 구간 1 은 2-1 앞에서 한 번이고, 4장 뒤 7장으로
    돌아와 표지를 다시 만나도 청하지 않는다."""
    text = _text()
    model = _section(text, "## 0-2. ", "\n## 1. ")
    first = next(line for line in model.splitlines() if line.startswith("| 1 | "))
    assert "2-1 앞" in first and "다시 만나도 청하지 않는다" in first
    assert "2-1 앞에서 한 번" in _first_paragraph_after(text, HEADED[1])


def test_every_marker_line_keeps_the_one_form() -> None:
    """표지를 손으로 고치다 꼴이 흐트러지면 Sonnet 이 표지를 놓친다 — `> **[Opus` 로 시작하는 줄은
    모두 한 꼴이다."""
    lines = [line for line in _text().splitlines() if line.startswith("> **[Opus")]
    assert lines
    for line in lines:
        assert MARKER.fullmatch(line), line


def test_the_model_section_asks_the_user_and_records_a_sonnet_run() -> None:
    text = _text()
    model = _section(text, "## 0-2. ", "\n## 1. ")
    assert "`/model opus`" in model and "`/model sonnet`" in model
    assert "짐작하지 않는다" in model and "이미 Opus 면 청하지 않는다" in model
    assert "`/compact`" in model and "백그라운드" in model

    order = _section(text, "**압축본 줄 — 이 차례로**", "**B 세는 법**")
    third = next(line for line in order.splitlines() if line.startswith("3. "))
    assert "`모델`" in third
    assert "`모델 sonnet <구간 번호>`" in order
    assert "`모델 sonnet <구간 번호>`" in _section(text, "## 6-1. ", "## 6-2. ")


def test_chapter_seven_keeps_no_section_it_says_not_to_do() -> None:
    """하지 않는 앞 배포 몫은 7장에 싣지 않는다 — git 이력에 맡긴다(2026-11-03 Sonnet 진행)."""
    chapter = _section(_text(), "\n## 7. ", "\n## 8. ")
    headings = [line for line in chapter.splitlines() if line.startswith("### 7-")]
    assert headings
    assert [line for line in headings if "하지 않는다" in line] == []
    assert "git 이력에 있다" in chapter


def test_the_settings_template_denies_reading_pictures_inside_and_outside() -> None:
    """그림 파일 `Read` 는 세션 폴더 아래(`**/`)와 파일 시스템 뿌리부터(`//**/`) 둘 다 막힌다 — 사내
    사본 폴더는 저장소 밖이다. allow 의 `Read` 를 deny 가 이긴다."""
    permissions = json.loads(TEMPLATE.read_text(encoding="utf-8"))["permissions"]
    deny, allow = permissions["deny"], permissions["allow"]

    assert "Read" in allow
    for picture in PICTURES:
        assert f"Read(**/*.{picture})" in deny, picture
        assert f"Read(//**/*.{picture})" in deny, picture
    assert not [rule for rule in allow if rule.startswith("Read(")]


def test_the_documents_say_what_the_template_blocks() -> None:
    text = _text()
    chapter_zero = _section(text, "## 0. ", "## 0-1. ")
    assert "권한 템플릿이 그림 읽기를 막는다" in chapter_zero
    assert "셸 · 파이썬으로 돌아가 열지 않는다" in chapter_zero
    assert "그림 파일 읽기도 막는다" in " ".join(_section(text, "### 1-2. ", "### 1-3. ").split())
    blocked = _section(text, "## 6. 막혔을 때", "## 6-1. ")
    assert "| 그림 파일(png · jpg 등)을 `Read` 로 열려다 권한에 막힌다 |" in blocked

    assert "그림 파일(png · jpg · jpeg · webp · gif · bmp)의 `Read`" in DUAL_ENV.read_text(
        encoding="utf-8"
    )
    assert "실화면 그림 파일(png · jpg 등)을 `Read` 로 열지" in README.read_text(encoding="utf-8")
