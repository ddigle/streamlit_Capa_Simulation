# Purpose: 부대공정 양식 읽기 · 접수 검증 V-01 ~ V-14 · 판 번호 판정 · 양식 쓰기를 견본과
# 고친 사본으로 본다.

"""부대공정 양식(`services/extra_process_pack.py`).

견본은 오류 0 · 경고 0 이고 측정률 빈칸 → 1.0 이 2칸이다. 설계 부록 A 의 고친 사본 13개를 같은
고침으로 다시 만들어 규칙과 건수를 고정한다 — 둘(측정률 0 · PKG 소문자 buffer)은 설계대로 받는다.
"""

from __future__ import annotations

import csv
import io
import zipfile
from collections.abc import Callable
from dataclasses import replace

import pytest
from extra_process_fixtures import (
    AOI,
    BOND,
    Table,
    bump_version,
    edited,
    set_cell,
    template_files,
    zip_files,
)

from capa_simulation.services import extra_process_pack as pack_module
from capa_simulation.services.extra_process_pack import (
    INFO_FILE,
    JUDGE_APPLY,
    JUDGE_BACKWARD,
    JUDGE_RESUME,
    JUDGE_UNCHANGED,
    PACK_HEADERS,
    judge_pack,
    pack_sha256,
    pack_to_zip,
    read_pack_files,
    read_pack_zip,
    template_zip,
)

Files = dict[str, bytes]


def _codes(files: Files) -> list[str]:
    return [problem.code for problem in read_pack_files(files).problems]


def test_the_template_passes_with_two_blank_ratios_counted() -> None:
    reading = read_pack_zip(zip_files(template_files()))

    assert reading.accepted and reading.pack is not None
    assert reading.problems == () and reading.warnings == ()
    assert (reading.ratio.blank, reading.ratio.zero) == (2, 0)
    assert reading.version_no == 1
    assert reading.pack.process_names() == (BOND, AOI)
    assert reading.pack.row_counts() == {
        "01_process.csv": 2,
        "02_route.csv": 3,
        "03_productivity.csv": 4,
        "04_equipment_days.csv": 3,
        "05_rate_vital.csv": 3,
    }


def test_folders_inside_the_zip_are_ignored() -> None:
    reading = read_pack_zip(zip_files(template_files(), folder="부대공정/판1/"))

    assert reading.accepted


def test_cp949_files_are_read_when_utf8_fails() -> None:
    files = {
        name: data.decode("utf-8-sig").replace("—", "-").encode("cp949")
        for name, data in template_files().items()
    }

    assert read_pack_files(files).accepted


def _rows(files: Files, name: str) -> Table:
    from extra_process_fixtures import read_table

    return read_table(files[name])


def _drop_column(rows: Table, column: str) -> Table:
    index = rows[0].index(column)
    return [[cell for at, cell in enumerate(row) if at != index] for row in rows]


def _without(rows: Table, match: Callable[[list[str]], bool]) -> Table:
    return [rows[0], *(row for row in rows[1:] if not match(row))]


def _with_row(rows: Table, row: list[str]) -> Table:
    return [*rows, row]


def _first_bond_row(row: list[str]) -> bool:
    return row[0] == BOND and row[7] == "202601"


def _second_bond_row(row: list[str]) -> bool:
    return row[0] == BOND and row[7] == "202607"


def _aoi_as_pkg(files: Files) -> Files:
    return edited(
        files,
        "01_process.csv",
        lambda rows: set_cell(rows, lambda r: r[0] == AOI, "소요기준", "PKG"),
    )


def _buffer_mixed_case(files: Files) -> Files:
    files = _aoi_as_pkg(files)
    for name in ("02_route.csv", "03_productivity.csv"):
        files = edited(
            files,
            name,
            lambda rows: set_cell(
                set_cell(
                    rows, lambda r: r[0] == AOI and "DEMO PRODUCT A" in r, "WF 구분", "buffer"
                ),
                lambda r: r[0] == AOI and "DEMO PRODUCT B" in r,
                "WF 구분",
                "BUFFER",
            ),
        )
    return files


# 설계 부록 A 의 고친 사본 13개 — (이름, 고침, 기대 규칙 · 건수(받으면 빈 목록), 측정률 0 칸 수).
TAMPERED: list[tuple[str, Callable[[Files], Files], list[str], int]] = [
    (
        "대여 > 보유",
        lambda f: edited(
            f,
            "04_equipment_days.csv",
            lambda r: set_cell(r, lambda x: x[0] == AOI, "설비대여평가", "3.5"),
        ),
        ["V-11"],
        0,
    ),
    (
        "소요기준 빈칸",
        lambda f: edited(
            f, "01_process.csv", lambda r: set_cell(r, lambda x: x[0] == BOND, "소요기준", "")
        ),
        ["V-03"],
        0,
    ),
    (
        "소요기준 칸 없음",
        lambda f: edited(f, "01_process.csv", lambda r: _drop_column(r, "소요기준")),
        ["V-01"],
        0,
    ),
    (
        "올린시각 적음",
        lambda f: edited(
            f, "00_info.csv", lambda r: _with_row(r, ["올린시각", "2026-11-13T09:00:00+09:00"])
        ),
        ["V-02"],
        0,
    ),
    (
        "판 없음",
        lambda f: edited(f, "00_info.csv", lambda r: _without(r, lambda x: x[0] == "판")),
        ["V-02"],
        0,
    ),
    (
        "측정률 0",
        lambda f: edited(
            f, "03_productivity.csv", lambda r: set_cell(r, _second_bond_row, "WF측정률", "0")
        ),
        [],
        1,
    ),
    (
        "측정률 음수",
        lambda f: edited(
            f, "03_productivity.csv", lambda r: set_cell(r, _second_bond_row, "WF측정률", "-0.5")
        ),
        ["V-10"],
        0,
    ),
    (
        "05 ER 빠짐",
        lambda f: edited(
            f, "05_rate_vital.csv", lambda r: _without(r, lambda x: x[0] == AOI and x[1] == "ER")
        ),
        ["V-13", "V-13"],
        0,
    ),
    ("PKG 소문자 buffer", _buffer_mixed_case, [], 0),
    (
        "PKG 에 Core",
        lambda f: _aoi_as_pkg(f),
        ["V-06", "V-06"],
        0,
    ),
    (
        "04 기간 겹침",
        lambda f: edited(
            f,
            "04_equipment_days.csv",
            lambda r: set_cell(r, lambda x: x[0] == BOND and x[1] == "202607", "시작월", "202606"),
        ),
        ["V-08"],
        0,
    ),
    (
        "Main 에 ST",
        lambda f: edited(
            f, "03_productivity.csv", lambda r: set_cell(r, _first_bond_row, "ST", "0.5")
        ),
        ["V-10"],
        0,
    ),
    (
        "04 파일 없음",
        lambda f: {name: data for name, data in f.items() if name != "04_equipment_days.csv"},
        ["V-01"],
        0,
    ),
]


@pytest.mark.parametrize(
    ("label", "tamper", "expected", "zeros"), TAMPERED, ids=[row[0] for row in TAMPERED]
)
def test_the_thirteen_tampered_copies_hit_the_designed_rules(
    label: str, tamper: Callable[[Files], Files], expected: list[str], zeros: int
) -> None:
    reading = read_pack_files(tamper(template_files()))

    assert sorted(problem.code for problem in reading.problems) == expected, label
    assert reading.accepted is (not expected)
    if not expected:
        assert reading.ratio.zero == zeros


def test_buffer_spelled_differently_in_route_and_productivity_still_covers() -> None:
    """02 `buffer` · 03 `BUFFER` 처럼 같은 제품끼리 갈려도 받는다 — 설계 점검 스크립트의 한계를
    구현은 대소문자를 무시해 견준다(설계 부록 A 끝)."""
    files = _aoi_as_pkg(template_files())
    files = edited(
        files, "02_route.csv", lambda r: set_cell(r, lambda x: x[0] == AOI, "WF 구분", "buffer")
    )
    files = edited(
        files,
        "03_productivity.csv",
        lambda r: set_cell(r, lambda x: x[0] == AOI, "WF 구분", "BUFFER"),
    )

    assert _codes(files) == []


@pytest.mark.parametrize("bad", ["1,000", "inf", "nan", "abc"])
def test_unreadable_numbers_are_refused_apart_from_blanks(bad: str) -> None:
    files = edited(
        template_files(), "03_productivity.csv", lambda r: set_cell(r, _first_bond_row, "UPEH", bad)
    )

    assert "V-14" in _codes(files)


def test_an_excel_text_guard_is_stripped_from_text_cells() -> None:
    files = edited(
        template_files(),
        "02_route.csv",
        lambda r: set_cell(r, lambda x: x[0] == BOND, "STEP_SEQ", '="DEMO-P150"'),
    )
    reading = read_pack_files(files)

    assert reading.pack is not None
    assert reading.pack.routes[0].step == "DEMO-P150"


def test_a_non_integer_run_day_is_refused() -> None:
    files = edited(
        template_files(),
        "04_equipment_days.csv",
        lambda r: set_cell(r, lambda x: x[0] == AOI, "RUN_DAY", "20.5"),
    )

    assert _codes(files) == ["V-11"]


def test_a_pack_without_processes_is_refused() -> None:
    reading = read_pack_zip(template_zip())

    assert not reading.accepted
    assert [problem.code for problem in reading.problems] == ["V-03"]
    assert {name for name in PACK_HEADERS} <= set(_zip_names(template_zip()))


def _zip_names(data: bytes) -> list[str]:
    import io
    import zipfile

    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return archive.namelist()


def test_a_too_large_or_broken_file_is_refused_at_v01(monkeypatch: pytest.MonkeyPatch) -> None:
    assert [p.code for p in read_pack_zip(b"not a zip").problems] == ["V-01"]
    monkeypatch.setattr(pack_module, "PACK_MAX_BYTES", 10)
    assert [p.code for p in read_pack_zip(zip_files(template_files())).problems] == ["V-01"]


def _deflated(files: dict[str, bytes]) -> bytes:
    import io
    import zipfile

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return buffer.getvalue()


def test_a_small_zip_that_unpacks_too_large_is_refused_without_reading_it_all(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ZIP 폭탄 — 받은 크기는 상한 안이어도 풀린 크기(장마다 · 합)가 상한을 넘으면 V-01 로
    거절한다. 머리의 크기 값을 속여도 읽는 바이트로 다시 센다."""
    files = template_files()
    files["05_rate_vital.csv"] = files["05_rate_vital.csv"] + b"\n" * (9 * 1024 * 1024)
    data = _deflated(files)
    assert len(data) < pack_module.PACK_MAX_BYTES

    (problem,) = read_pack_zip(data).problems
    assert (problem.code, problem.file) == ("V-01", "05_rate_vital.csv")
    assert problem.reason.startswith("풀면 너무 큼")

    small = template_files()
    monkeypatch.setattr(pack_module, "PACK_MEMBER_MAX_BYTES", 10**9)
    monkeypatch.setattr(
        pack_module, "PACK_UNPACKED_MAX_BYTES", sum(len(body) for body in small.values()) - 1
    )
    (total,) = read_pack_zip(zip_files(small)).problems
    assert total.reason.startswith("풀면 너무 큼")


def test_an_unsupported_compression_is_refused_at_v01() -> None:
    """지원하지 않는 압축 방식(Deflate64 등)은 처리 못 한 예외가 아니라 V-01 거절이다."""
    data = bytearray(_deflated(template_files()))
    at = data.find(b"PK\x01\x02")
    while at >= 0:
        data[at + 10 : at + 12] = (9).to_bytes(2, "little")
        at = data.find(b"PK\x01\x02", at + 4)

    problems = read_pack_zip(bytes(data)).problems
    assert problems and {problem.code for problem in problems} == {"V-01"}
    assert all(problem.reason == "ZIP 안 파일을 읽지 못함" for problem in problems)


def test_pack_to_zip_round_trips_the_same_rows_and_bytes() -> None:
    reading = read_pack_files(template_files())
    assert reading.pack is not None

    written = pack_to_zip(reading.pack)
    again = read_pack_zip(written)

    assert again.pack is not None
    assert again.pack.processes == reading.pack.processes
    assert again.pack.routes == reading.pack.routes
    assert again.pack.productivity == reading.pack.productivity
    assert again.pack.equipment == reading.pack.equipment
    assert again.pack.rate_vital == reading.pack.rate_vital
    # 같은 판은 늘 같은 바이트(sha)로 다시 쓰인다.
    assert pack_sha256(pack_to_zip(again.pack)) == pack_sha256(written)


def test_the_writer_bytes_of_the_template_and_the_empty_form_stay_pinned() -> None:
    """쓰개를 공개 도우미(`pack_rows` · `pack_files`)로 나눠도 바이트가 그대로다(나누기 전 값)."""
    reading = read_pack_files(template_files())
    assert reading.pack is not None

    assert pack_sha256(pack_to_zip(reading.pack)) == (
        "e50e7a942893cbe3ccb1baa193d37ea77915721df0e5b22128039499ff8897f2"
    )
    assert pack_sha256(template_zip()) == (
        "86455dc42cebf0a27f17f4c1fc5a41c03466dea0241234c0d6c54471eac982b7"
    )


def _info_cells(data: bytes) -> dict[str, str]:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        text = archive.read(INFO_FILE).decode("utf-8-sig")
    return {row[0]: row[1] for row in list(csv.reader(io.StringIO(text)))[1:]}


@pytest.mark.parametrize(
    "memo", ["=SUM(1)", "+DEMO", "@DEMO", "-DEMO", "TRUE", "2026-11-27", "010"]
)
def test_the_info_text_cells_carry_the_excel_guard_and_read_back_plain(memo: str) -> None:
    """G8 — 00 의 작성자 · 메모(편집기 화면 자유 글)도 다른 글자 칸과 같은 가드를 쓴다. 읽기가 벗겨
    같은 글로 돌아오고, 다시 쓰면 같은 바이트다(고정점)."""
    reading = read_pack_files(template_files())
    assert reading.pack is not None
    pack = replace(reading.pack, info=replace(reading.pack.info, author=memo, memo=memo))

    written = pack_to_zip(pack)
    cells = _info_cells(written)
    again = read_pack_zip(written)

    assert cells["메모"] == f'="{memo}"' and cells["작성자"] == f'="{memo}"'
    assert cells["작성시각"] == pack.info.written_at, "ISO 작성시각은 가드가 서지 않는다"
    assert again.pack is not None
    assert (again.pack.info.author, again.pack.info.memo) == (memo, memo)
    assert pack_to_zip(again.pack) == written


def test_a_guard_looking_info_memo_reaches_a_fixed_point_in_one_rewrite() -> None:
    """S3 꼴 — 이미 가드처럼 생긴 메모(`="=X"`)는 따옴표가 있어 가드가 서지 않고, 읽으면 벗겨진 `=X`
    가 다음 쓰기에서 가드를 받는다 — 한 번 더 쓰면 같은 바이트다."""
    reading = read_pack_files(template_files())
    assert reading.pack is not None
    pack = replace(reading.pack, info=replace(reading.pack.info, memo='="=DEMO"'))

    first = read_pack_zip(pack_to_zip(pack))
    assert first.pack is not None and first.pack.info.memo == "=DEMO"
    second = pack_to_zip(first.pack)
    assert _info_cells(second)["메모"] == '="=DEMO"'
    third = read_pack_zip(second)
    assert third.pack is not None and pack_to_zip(third.pack) == second


def test_judge_pack_tells_unchanged_resume_apply_and_backward() -> None:
    one = pack_sha256(zip_files(template_files()))
    two = pack_sha256(zip_files(bump_version(template_files(), 2)))

    assert (
        judge_pack(
            one, 1, active_sha=None, latest_version_no=None, latest_sha=None, off=False
        ).verdict
        == JUDGE_APPLY
    )
    assert (
        judge_pack(one, 1, active_sha=one, latest_version_no=1, latest_sha=one, off=False).verdict
        == JUDGE_UNCHANGED
    )
    assert (
        judge_pack(one, 1, active_sha=None, latest_version_no=1, latest_sha=one, off=True).verdict
        == JUDGE_RESUME
    )
    assert (
        judge_pack(two, 2, active_sha=one, latest_version_no=1, latest_sha=one, off=False).verdict
        == JUDGE_APPLY
    )
    backward = judge_pack(two, 1, active_sha=one, latest_version_no=1, latest_sha=one, off=False)
    assert backward.verdict == JUDGE_BACKWARD and not backward.applicable
