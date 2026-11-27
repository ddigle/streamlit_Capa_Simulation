# Purpose: 부대공정 양식(CSV 여섯 장 — 낱장 한 벌 · ZIP)을 읽어 접수 검증 V-01 ~ V-14 를 거친
# 판으로 만들고 양식을 다시 쓴다.

"""부대공정(BDQ 밖) 생산성 기준정보 양식 — 읽기 · 접수 검증 · 판 번호 판정 · 양식 쓰기.

**한 벌**은 CSV 여섯 장이다(`PACK_HEADERS` — 파일 이름은 영문, 머리 칸은 Core_Data 칸 이름 그대로).
사람은 S3 Drive 의 놓는 자리에 **낱장 여섯**을 놓는다(2026-11-20 보드 결정-2 (가) — S3 Drive 웹이
`.zip` 올리기를 막음). 앱 안의 판 한 벌(DB 판 내용 · 양식 내려받기 · 「새 판으로」)은 그 여섯을 묶은
ZIP 하나다 — 낱장 한 벌은 `bundle_pack_files` 가 `pack_to_zip` 과 같은 꼴(차례 · 고정 시각 · 압축)로
묶어 같은 길(`read_pack_zip`)을 지난다. 그래서 내려받은 양식을 풀어 그대로 놓은 여섯 장은 그 판과
같은 바이트(sha)다. ZIP 안의 폴더 이름은 보지 않고 파일 이름으로 찾는다. 글은 UTF-8(BOM 허용)로 읽고
안 되면 CP949 로 한 번 더 읽는다 — UTF-8 로 읽히지 않은 장의 거절 까닭은 메모장 「UTF-8」 저장을
가리킨다(Excel 로 저장한 CSV 는 사용자 PC 에서 사내 DRM 머리가 붙는다 — 사내 확인 부대 5). 글자 칸은
앞뒤 공백을 떼고 Excel 텍스트 가드 `="..."` 를 벗긴다.

**접수 검증**(설계 부록 A — `V-01` ~ `V-14`)은 BDQ 없이 파일만으로 본다. V-01(파일 · 인코딩 · 머리
칸 · 칸 수)이 어긋나면 뒤 검사를 하지 않고 거절한다. 판 번호 · sha 를 DB 의 판 이력과 견주는 V-02
뒷부분은 `judge_pack` 이 따로 한다(순수 함수 — 가져오기 원천과 상관없이 같은 판정).

**측정률**은 빈칸 · 0 을 1.0 으로 센다(원천과 같은 뜻 — 설계 D23 (나)). 거절하지 않고 칸 수를
센다(`RatioCounts`) — 0 은 0 그대로 둔다(계산이 1.0 으로 읽는다).

**대소문자.** `WF 구분` 은 견줄 때 대소문자를 무시한다(02 `buffer` 와 03 `BUFFER` 는 같은 경로) —
데이터 쪽 글자로 맞추는 것은 합치기(`extra_process_merge`)다. 공정 이름은 대소문자를 가른다(계산도
가른다). 01 안의 겹침과 부대공정끼리의 참조만 대소문자를 무시해 본다.

**쓰기.** `pack_to_zip` 은 판을 같은 꼴의 ZIP 으로 다시 쓰고(글자 칸에 Excel 텍스트 가드),
`template_zip` 은 머리 칸만 든 빈 양식이다. 셋 다 같은 묶개(`_zip_members`)를 지난다 — 같은 장은 늘
같은 바이트다(표준 라이브러리 deflate 출력이 같은 동안). 칸 글은 줄 쓰개(`pack_rows` ·
`*_cells` · `number_cell` · `text_cell`)가, 장 바이트는 `pack_files` 가 짓는다 — 앱이 지은 검사 전
글 줄(편집기)도 같은 쓰개로 묶여 관문을 지난다. Streamlit 을 import 하지 않는다.
"""

from __future__ import annotations

import calendar
import csv
import hashlib
import io
import math
import re
import zipfile
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final

import pandas as pd

from capa_simulation.services.core_data_derivation import normalize_product_names
from capa_simulation.services.frame_contracts import (
    AREA_NAMES,
    DEMAND_BASES,
    normalize_demand_basis_value,
)
from capa_simulation.services.reference_csv import guard_excel_text, strip_excel_text_guard

FORMAT_VERSION: Final = 1
KNOWN_FORMATS: Final = frozenset({FORMAT_VERSION})
# S3 Drive 에서 받는 상한 — 모듈 도우미와 같은 8 MiB(설계 3-1).
PACK_MAX_BYTES: Final = 8 * 1024 * 1024
# 풀린 크기 상한 — 장마다 · 여섯 장 합(작은 ZIP 이 수 GB 로 풀려 메모리를 다 쓰지 않게). 머리의
# 크기 값은 믿지 않고 읽는 바이트로도 센다.
PACK_MEMBER_MAX_BYTES: Final = 8 * 1024 * 1024
PACK_UNPACKED_MAX_BYTES: Final = 32 * 1024 * 1024

INFO_FILE: Final = "00_info.csv"
PROCESS_FILE: Final = "01_process.csv"
ROUTE_FILE: Final = "02_route.csv"
PRODUCTIVITY_FILE: Final = "03_productivity.csv"
EQUIPMENT_FILE: Final = "04_equipment_days.csv"
RATE_FILE: Final = "05_rate_vital.csv"
# 묶은 ZIP 안의 장 시각 — 고정이라 같은 장은 늘 같은 바이트(sha)로 묶인다.
_MEMBER_TIME: Final = (2026, 1, 1, 0, 0, 0)
# UTF-8 로 읽히지 않은 장의 거절 까닭 — 사람이 고칠 길(메모장 「UTF-8」 저장)을 함께 말한다.
NOT_UTF8_HINT: Final = "메모장에서 UTF-8 로 다시 저장해 놓으세요"
PACK_HEADERS: Final[Mapping[str, tuple[str, ...]]] = {
    INFO_FILE: ("항목", "값"),
    PROCESS_FILE: ("공정", "Area_Name", "소요기준", "모듈수", "메모"),
    ROUTE_FILE: (
        "공정",
        "참조공정",
        "제품정보",
        "Stack",
        "WF 구분",
        "STEP_SEQ",
        "MCP_SEQ",
        "시작월",
        "끝월",
    ),
    PRODUCTIVITY_FILE: (
        "공정",
        "제품정보",
        "Stack",
        "WF 구분",
        "STEP_SEQ",
        "MCP_SEQ",
        "양산구분",
        "시작월",
        "끝월",
        "UPEH",
        "ST",
        "Lot 측정률",
        "WF측정률",
    ),
    EQUIPMENT_FILE: ("공정", "시작월", "끝월", "RUN_DAY", "설비보유", "설비대여평가"),
    RATE_FILE: ("공정", "양산구분", "시작월", "끝월", "CAPA_RUN_RATE", "편중률"),
}
# 판 기록 항목 — 필수 둘 · 선택 셋. 그 밖은 모르는 항목으로 거절한다(도구 항목 `올린시각` 포함).
INFO_REQUIRED: Final = ("형식판", "판")
INFO_OPTIONAL: Final = ("작성시각", "작성자", "메모")
CALENDAR_WORD: Final = "달력"
MASS: Final = "양산"
ENGINEERING: Final = "ER"
BOTH_CLASSES: Final = "모두"
CLASS_EXPANSION: Final[Mapping[str, tuple[str, ...]]] = {
    MASS: (MASS,),
    ENGINEERING: (ENGINEERING,),
    BOTH_CLASSES: (MASS, ENGINEERING),
}
RATIO_COLUMNS: Final = ("Lot 측정률", "WF측정률")
BUFFER_WORD: Final = "buffer"
# 끝이 열린 기간의 RUN_DAY 는 앞으로 이만큼 달을 본다(설계 V-11 — 사실상 28 이하).
OPEN_LOOKAHEAD_MONTHS: Final = 12
_NON_FINITE: Final = frozenset({"inf", "-inf", "+inf", "infinity", "-infinity", "+infinity", "nan"})
_MONTH_PATTERN: Final = re.compile(r"\d{6}")
_POSITIVE_INT: Final = re.compile(r"[1-9]\d*")
_OPEN_END: Final = 10**9


@dataclass(frozen=True)
class PackProblem:
    """거절 표 한 줄 — 규칙 · 파일 · 행 번호(머리 칸 = 1) · 칸 · 까닭. 값 원문은 싣지 않는다."""

    code: str
    file: str
    row: int | None
    column: str
    reason: str

    def text(self) -> str:
        where = " ".join(
            part for part in (self.file, f"{self.row}행" if self.row else "", self.column) if part
        )
        return f"{self.code} {where} — {self.reason}" if where else f"{self.code} {self.reason}"


@dataclass(frozen=True)
class RatioCounts:
    """측정률을 1.0 으로 센 칸 수 — 빈칸 · 0(설계 D23 (나) — 미리보기가 보인다)."""

    blank: int = 0
    zero: int = 0

    def text(self) -> str:
        return f"측정률 빈칸 → 1.0 {self.blank}칸 · 0 → 1.0 으로 셈 {self.zero}칸"


@dataclass(frozen=True)
class Period:
    """시작월 · 끝월(YYYYMM, 끝 None = 계속)."""

    start: int
    end: int | None

    def covers(self, month: int) -> bool:
        return self.start <= month and (self.end is None or month <= self.end)

    def span(self) -> tuple[int, int]:
        return (_month_index(self.start), _OPEN_END if self.end is None else _month_index(self.end))


@dataclass(frozen=True)
class ProcessRow:
    name: str
    area: str
    basis: str
    modules: float
    memo: str
    row: int


@dataclass(frozen=True)
class RouteRow:
    process: str
    reference: str
    product: str
    stack: str
    wf: str
    step: str
    mcp: str
    period: Period
    row: int

    @property
    def follows(self) -> bool:
        """따라가기 꼴(참조 공정을 적음)인가 — 아니면 지정 꼴."""
        return bool(self.reference)


@dataclass(frozen=True)
class ProductivityRow:
    process: str
    product: str
    stack: str
    wf: str
    step: str
    mcp: str
    mass_class: str
    period: Period
    upeh: float | None
    st: float | None
    lot_ratio: float | None
    wf_ratio: float | None
    row: int

    @property
    def common(self) -> bool:
        """공정 공통 값(제품 칸 셋이 빔)인가."""
        return not (self.product or self.stack or self.wf)


@dataclass(frozen=True)
class EquipmentRow:
    process: str
    period: Period
    run_day: int | None  # None = 달력(그 달 날수)
    owned: float
    lent: float | None
    row: int


@dataclass(frozen=True)
class RateVitalRow:
    process: str
    mass_class: str
    period: Period
    run_rate: float
    vital: float
    row: int


@dataclass(frozen=True)
class PackInfo:
    format_version: int
    version_no: int
    written_at: str = ""
    author: str = ""
    memo: str = ""


@dataclass(frozen=True)
class ExtraProcessPack:
    """접수 검증을 지난 판 한 벌(파일 꼴 그대로 — `모두` · `달력` 을 펼치지 않는다)."""

    sha256: str
    info: PackInfo
    processes: tuple[ProcessRow, ...]
    routes: tuple[RouteRow, ...]
    productivity: tuple[ProductivityRow, ...]
    equipment: tuple[EquipmentRow, ...]
    rate_vital: tuple[RateVitalRow, ...]
    ratio: RatioCounts = field(default_factory=RatioCounts)

    def process_names(self) -> tuple[str, ...]:
        return tuple(process.name for process in self.processes)

    def row_counts(self) -> dict[str, int]:
        """파일마다 행 수(판 기록 빼고) — 판 이력 · 상태 줄이 싣는다."""
        return {
            PROCESS_FILE: len(self.processes),
            ROUTE_FILE: len(self.routes),
            PRODUCTIVITY_FILE: len(self.productivity),
            EQUIPMENT_FILE: len(self.equipment),
            RATE_FILE: len(self.rate_vital),
        }


@dataclass(frozen=True)
class PackReading:
    """읽기 한 번의 결과 — 판(거절이면 None) · 거절 표 · 경고 · 측정률 칸 수."""

    sha256: str
    byte_size: int
    pack: ExtraProcessPack | None
    problems: tuple[PackProblem, ...] = ()
    warnings: tuple[PackProblem, ...] = ()
    ratio: RatioCounts = field(default_factory=RatioCounts)
    version_no: int | None = None

    @property
    def accepted(self) -> bool:
        return self.pack is not None


def pack_sha256(data: bytes) -> str:
    """판을 가르는 값 — 받은 본문의 sha256(ETag 는 「바뀌었다」 신호로만 쓴다 — 설계 3-2)."""
    return hashlib.sha256(data).hexdigest()


def read_pack_zip(data: bytes) -> PackReading:
    """양식 ZIP 바이트를 읽어 접수 검증까지 마친 결과."""
    sha = pack_sha256(data)
    if len(data) > PACK_MAX_BYTES:
        return _rejected(
            sha, len(data), "", f"파일이 상한 {PACK_MAX_BYTES // (1024 * 1024)} MiB 를 넘음"
        )
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        return _rejected(sha, len(data), "", "ZIP 이 아님(파일 깨짐 · DRM)")
    files: dict[str, bytes] = {}
    problems: list[PackProblem] = []
    unpacked = 0
    with archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            name = info.filename.replace("\\", "/").rsplit("/", 1)[-1]
            if name not in PACK_HEADERS:
                continue
            if name in files:
                problems.append(PackProblem("V-01", name, None, "", "같은 이름의 파일이 둘 이상"))
                continue
            room = min(PACK_MEMBER_MAX_BYTES, PACK_UNPACKED_MAX_BYTES - unpacked)
            if info.file_size > room:
                problems.append(_too_big(name))
                break
            try:
                with archive.open(info) as member:
                    body = member.read(room + 1)
            except (zipfile.BadZipFile, RuntimeError, ValueError, OSError, NotImplementedError):
                problems.append(PackProblem("V-01", name, None, "", "ZIP 안 파일을 읽지 못함"))
                continue
            if len(body) > room:
                problems.append(_too_big(name))
                break
            unpacked += len(body)
            files[name] = body
    if problems:
        return PackReading(sha, len(data), None, tuple(problems))
    return read_pack_files(files, sha256=sha, byte_size=len(data))


def _too_big(name: str) -> PackProblem:
    return PackProblem(
        "V-01",
        name,
        None,
        "",
        f"풀면 너무 큼 — 장마다 {PACK_MEMBER_MAX_BYTES // (1024 * 1024)} MiB · "
        f"합 {PACK_UNPACKED_MAX_BYTES // (1024 * 1024)} MiB 까지",
    )


def _rejected(sha: str, size: int, file: str, reason: str) -> PackReading:
    return PackReading(sha, size, None, (PackProblem("V-01", file, None, "", reason),))


def read_pack_files(
    files: Mapping[str, bytes], *, sha256: str | None = None, byte_size: int | None = None
) -> PackReading:
    """파일 이름 → 바이트 여섯 장을 읽어 접수 검증까지 마친 결과(`read_pack_zip` 의 몸통)."""
    sha = sha256 or pack_sha256(b"".join(files.get(name, b"") for name in PACK_HEADERS))
    size = byte_size if byte_size is not None else sum(len(value) for value in files.values())
    checker = _Checker()
    tables = checker.read_tables(files)
    if checker.problems or tables is None:
        return PackReading(sha, size, None, tuple(checker.problems), tuple(checker.warnings))
    pack = checker.validate(tables, sha)
    return PackReading(
        sha,
        size,
        pack,
        tuple(checker.problems),
        tuple(checker.warnings),
        checker.ratio(),
        checker.version_no,
    )


# --------------------------------------------------------------------------- 판 번호 판정

JUDGE_APPLY: Final = "apply"
JUDGE_UNCHANGED: Final = "unchanged"
JUDGE_RESUME: Final = "resume"
JUDGE_BACKWARD: Final = "backward"
# 뒤로 간 판의 까닭 끝 — 옛 사본에서 판 번호만 올려 놓지 않게 지금 판에서 고치라고 한다.
BACKWARD_ADVICE: Final = "양식 내려받기로 지금 판을 받아 고쳐 놓으세요"


@dataclass(frozen=True)
class PackJudgement:
    """받은 판을 DB 의 판 이력과 견준 결과(설계 3-2 · V-02 뒷부분)."""

    verdict: str
    reason: str

    @property
    def applicable(self) -> bool:
        """「적용」 단추를 열 수 있는가 — 새 판이거나 끈 동안 마지막 판(다시 켜기)."""
        return self.verdict in (JUDGE_APPLY, JUDGE_RESUME)


def judge_pack(
    sha256: str,
    version_no: int,
    *,
    active_sha: str | None,
    latest_version_no: int | None,
    latest_sha: str | None,
    off: bool,
) -> PackJudgement:
    """받은 판(sha · 판 번호)을 활성 판 · 적용한 가장 큰 판(P · S) · 끔 상태와 견준다.

    - 활성 판과 sha 가 같으면 「바뀐 것 없음」(아무것도 쓰지 않는다).
    - 끈 동안 마지막 내용 판과 sha 가 같으면 「다시 켜기」 로 받는다(설계 D22).
    - 판 번호가 P 보다 크면 적용할 수 있다. 그 밖(판 번호가 P 이하인데 내용이 다름)은 옛 파일을
      잘못 놓은 것으로 보고 거절한다 — 옛 사본의 판 번호만 올리면 지금 판에서 고친 값이 돌아가므로,
      까닭 글은 판 번호를 올리라고 하지 않고 지금 판(양식 내려받기)에서 고쳐 놓으라고 한다.
    """
    if active_sha is not None and sha256 == active_sha:
        return PackJudgement(JUDGE_UNCHANGED, "바뀐 것 없음 — 활성 판과 같은 파일")
    if off and latest_sha is not None and sha256 == latest_sha:
        return PackJudgement(JUDGE_RESUME, f"끈 동안 마지막 판(판 {latest_version_no})과 같은 파일")
    if latest_version_no is None or version_no > latest_version_no:
        return PackJudgement(JUDGE_APPLY, f"새 판 {version_no}")
    return PackJudgement(
        JUDGE_BACKWARD,
        f"판 번호({version_no})가 적용한 가장 큰 판({latest_version_no}) 이하인데 내용이 다름 — "
        f"{BACKWARD_ADVICE}",
    )


# --------------------------------------------------------------------------- 양식 쓰기


def template_zip() -> bytes:
    """빈 양식 — 머리 칸과 판 기록(형식판 · 판 1)만. 내용 판이 하나도 없을 때 내려받는다."""
    rows: dict[str, list[list[str]]] = {name: [] for name in PACK_HEADERS}
    rows[INFO_FILE] = info_rows(PackInfo(FORMAT_VERSION, 1))
    return _zip_members(pack_files(rows))


def pack_to_zip(pack: ExtraProcessPack) -> bytes:
    """판을 같은 꼴의 ZIP 으로 다시 쓴다 — 글자 칸에 Excel 텍스트 가드를 씌운다(양식 내려받기)."""
    return _zip_members(pack_files(pack_rows(pack)))


def pack_rows(pack: ExtraProcessPack) -> dict[str, list[list[str]]]:
    """판을 파일마다 글 줄(머리 칸 빼고)로 편다 — `pack_to_zip` 이 쓰는 칸 글 그대로다."""
    return {
        INFO_FILE: info_rows(pack.info),
        PROCESS_FILE: [process_cells(item) for item in pack.processes],
        ROUTE_FILE: [route_cells(item) for item in pack.routes],
        PRODUCTIVITY_FILE: [productivity_cells(item) for item in pack.productivity],
        EQUIPMENT_FILE: [equipment_cells(item) for item in pack.equipment],
        RATE_FILE: [rate_cells(item) for item in pack.rate_vital],
    }


def info_rows(info: PackInfo) -> list[list[str]]:
    """판 기록(00) 다섯 줄 — 작성시각 · 작성자 · 메모는 다른 글자 칸과 같은 Excel 가드
    (`text_cell`)를 씌운다(편집기 00 메모는 화면 자유 글이다). 읽기(`_clean`)가 벗겨 같은 글로
    돌아온다."""
    return [
        ["형식판", str(info.format_version)],
        ["판", str(info.version_no)],
        ["작성시각", text_cell(info.written_at)],
        ["작성자", text_cell(info.author)],
        ["메모", text_cell(info.memo)],
    ]


def process_cells(item: ProcessRow) -> list[str]:
    return [
        text_cell(item.name),
        item.area,
        item.basis,
        number_cell(item.modules),
        text_cell(item.memo),
    ]


def route_cells(item: RouteRow) -> list[str]:
    return [
        text_cell(item.process),
        text_cell(item.reference),
        text_cell(item.product),
        text_cell(item.stack),
        text_cell(item.wf),
        text_cell(item.step),
        text_cell(item.mcp),
        *period_cells(item.period),
    ]


def productivity_cells(item: ProductivityRow) -> list[str]:
    return [
        text_cell(item.process),
        text_cell(item.product),
        text_cell(item.stack),
        text_cell(item.wf),
        text_cell(item.step),
        text_cell(item.mcp),
        item.mass_class,
        *period_cells(item.period),
        number_cell(item.upeh),
        number_cell(item.st),
        number_cell(item.lot_ratio),
        number_cell(item.wf_ratio),
    ]


def equipment_cells(item: EquipmentRow) -> list[str]:
    return [
        text_cell(item.process),
        *period_cells(item.period),
        CALENDAR_WORD if item.run_day is None else str(item.run_day),
        number_cell(item.owned),
        number_cell(item.lent),
    ]


def rate_cells(item: RateVitalRow) -> list[str]:
    return [
        text_cell(item.process),
        item.mass_class,
        *period_cells(item.period),
        number_cell(item.run_rate),
        number_cell(item.vital),
    ]


def pack_files(rows: Mapping[str, Sequence[Sequence[str]]]) -> dict[str, bytes]:
    """파일마다 글 줄 → 장 바이트(UTF-8 BOM · CRLF · 머리 칸 먼저) — `pack_to_zip` 과 같은 쓰개.

    여섯 장을 모두 쓴다(줄이 없는 장은 머리 칸만). 값은 검사하지 않는다 — 앱이 지은 검사 전 글
    줄(편집기)도 이 꼴로 묶어 관문(`read_pack_zip`)에 넘긴다.
    """
    members: dict[str, bytes] = {}
    for name, header in PACK_HEADERS.items():
        text = io.StringIO()
        writer = csv.writer(text, lineterminator="\r\n")
        writer.writerow(header)
        writer.writerows(rows.get(name, ()))
        members[name] = ("\ufeff" + text.getvalue()).encode("utf-8")
    return members


def bundle_pack_files(files: Mapping[str, bytes]) -> bytes:
    """낱장 한 벌(파일 이름 → 바이트)을 판 한 벌의 ZIP 으로 묶는다 — 바이트는 고치지 않는다.

    `pack_to_zip` 과 같은 묶개라 내려받은 양식을 풀어 그대로 놓은 여섯 장은 그 판과 같은 바이트다.
    빠진 장은 묶지 않는다 — 읽기(`read_pack_zip`)가 「파일 없음」 으로 거절한다. 양식 밖 이름은 받지
    않는다(부르는 쪽이 정해진 이름 여섯으로만 받는다).
    """
    unknown = sorted(name for name in files if name not in PACK_HEADERS)
    if unknown:
        raise ValueError(f"양식 밖 파일 이름 {len(unknown)}개")
    return _zip_members(files)


def _zip_members(members: Mapping[str, bytes]) -> bytes:
    """장들을 양식 차례(`PACK_HEADERS`) · 고정 시각 · deflate 로 묶는다 — 같은 장은 늘 같은
    바이트."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in PACK_HEADERS:
            body = members.get(name)
            if body is None:
                continue
            entry = zipfile.ZipInfo(name, date_time=_MEMBER_TIME)
            entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, body)
    return buffer.getvalue()


def text_cell(value: str) -> str:
    """글자 칸 — Excel 이 바꿔 놓을 글만 `="..."` 로 감싼다(`guard_excel_text`)."""
    guarded = guard_excel_text(value)
    return guarded if isinstance(guarded, str) else value


def number_cell(value: float | None) -> str:
    """수 칸 — None 은 빈칸, 정수 값은 지수 · `.0` 없이, 그 밖은 가장 짧은 왕복 꼴(`repr`)."""
    if value is None:
        return ""
    if float(value).is_integer():
        return str(int(value))
    return repr(float(value))


def period_cells(period: Period) -> list[str]:
    """시작월 · 끝월 칸(끝 None = 빈칸)."""
    return [str(period.start), "" if period.end is None else str(period.end)]


# --------------------------------------------------------------------------- 검사기


def _month_index(month: int) -> int:
    return (month // 100) * 12 + (month % 100 - 1)


def _next_month(month: int) -> int:
    return month + 1 if month % 100 < 12 else (month // 100 + 1) * 100 + 1


def _clean(value: str | None) -> str:
    text = (value or "").strip()
    stripped = strip_excel_text_guard(text)
    return stripped.strip() if isinstance(stripped, str) else text


def normalize_product(value: str) -> str:
    """사람이 적은 제품정보를 원천 등록과 같은 꼴로 맞춘다
    (`core_data_derivation.normalize_product_names`)."""
    if not value:
        return ""
    normalized = normalize_product_names(pd.Series([value], dtype="string")).iloc[0]
    return "" if normalized is pd.NA else str(normalized)


def wf_key(value: str) -> str:
    """`WF 구분` 을 견줄 때 쓰는 꼴 — 앞뒤 공백을 떼고 대소문자를 없앤다(저장 글자는 그대로)."""
    return value.strip().casefold()


_Row = dict[str, str]


class _Checker:
    """V-01 ~ V-14 를 차례로 보며 거절 · 경고를 모은다."""

    def __init__(self) -> None:
        self.problems: list[PackProblem] = []
        self.warnings: list[PackProblem] = []
        self.ratio_blank = 0
        self.ratio_zero = 0
        self.version_no: int | None = None

    def err(self, code: str, file: str, row: int | None, column: str, reason: str) -> None:
        self.problems.append(PackProblem(code, file, row, column, reason))

    def warn(self, code: str, file: str, row: int | None, column: str, reason: str) -> None:
        self.warnings.append(PackProblem(code, file, row, column, reason))

    def ratio(self) -> RatioCounts:
        return RatioCounts(self.ratio_blank, self.ratio_zero)

    # ---- V-01
    def read_tables(self, files: Mapping[str, bytes]) -> dict[str, list[tuple[int, _Row]]] | None:
        tables: dict[str, list[tuple[int, _Row]]] = {}
        for name, header in PACK_HEADERS.items():
            raw = files.get(name)
            if raw is None:
                self.err("V-01", name, None, "", "파일 없음")
                continue
            text, utf8 = _decode(raw)
            if text is None:
                self.err(
                    "V-01",
                    name,
                    None,
                    "",
                    f"UTF-8 · CP949 로 읽히지 않음(DRM · 파일 깨짐) — {NOT_UTF8_HINT}",
                )
                continue
            if "\x00" in text:
                # NUL 이 든 장 — DRM · 저장 도구가 붙인 머리 꼴이거나 깨진 파일(csv 가 받지 않음).
                self.err(
                    "V-01",
                    name,
                    None,
                    "",
                    f"NUL 글자가 들어 있음(DRM · 파일 깨짐) — {NOT_UTF8_HINT}",
                )
                continue
            try:
                rows = list(csv.reader(io.StringIO(text)))
            except csv.Error:
                # 칸 하나가 csv 상한보다 큼 · 그 밖에 csv 가 받지 않는 꼴.
                self.err("V-01", name, None, "", f"CSV 로 읽히지 않음(파일 깨짐) — {NOT_UTF8_HINT}")
                continue
            if not rows:
                self.err("V-01", name, None, "", "비어 있음")
                continue
            got = tuple(cell.strip() for cell in rows[0])
            if got != header:
                # UTF-8 로 읽히지 않아 CP949 로 읽은 장이면 DRM 머리 · 저장 꼴일 수 있다.
                reason = "머리 칸이 양식과 다름"
                if not utf8:
                    reason += f"(UTF-8 로 읽히지 않음 — DRM · 저장 꼴) — {NOT_UTF8_HINT}"
                self.err("V-01", name, 1, "", reason)
                continue
            body: list[tuple[int, _Row]] = []
            for line_no, cells in enumerate(rows[1:], start=2):
                if not any(cell.strip() for cell in cells):
                    continue
                if len(cells) != len(header):
                    self.err("V-01", name, line_no, "", f"칸 수 {len(cells)} ≠ {len(header)}")
                    continue
                body.append((line_no, dict(zip(header, cells, strict=True))))
            tables[name] = body
        return None if self.problems else tables

    # ---- 칸 읽기
    def number(self, file: str, row: int, column: str, raw: str) -> float | None:
        """빈칸은 None, 못 읽는 값은 거절하고 NaN(V-14)."""
        value = _clean(raw)
        if value == "":
            return None
        if "," in value or value.lower() in _NON_FINITE:
            self.err("V-14", file, row, column, "읽을 수 없는 수(천 단위 쉼표 · inf · nan)")
            return math.nan
        try:
            number = float(value)
        except ValueError:
            self.err("V-14", file, row, column, "읽을 수 없는 수")
            return math.nan
        if not math.isfinite(number):
            self.err("V-14", file, row, column, "유한하지 않은 수")
            return math.nan
        return number

    def month(self, file: str, row: int, column: str, raw: str, *, required: bool) -> int | None:
        value = _clean(raw)
        if value == "":
            if required:
                self.err("V-07", file, row, column, "시작월 빈칸")
            return None
        if not _MONTH_PATTERN.fullmatch(value) or not 1 <= int(value[4:]) <= 12:
            self.err("V-07", file, row, column, "월 꼴(YYYYMM)이 아님")
            return None
        return int(value)

    def period(self, file: str, row: int, cells: _Row) -> Period | None:
        start = self.month(file, row, "시작월", cells["시작월"], required=True)
        end = self.month(file, row, "끝월", cells["끝월"], required=False)
        if start is None:
            return None
        if end is not None and end < start:
            self.err("V-07", file, row, "끝월", "끝월이 시작월보다 앞")
            return None
        return Period(start, end)

    # ---- V-02 ~ V-14
    def validate(
        self, tables: Mapping[str, list[tuple[int, _Row]]], sha: str
    ) -> ExtraProcessPack | None:
        info = self._info(tables[INFO_FILE])
        processes = self._processes(tables[PROCESS_FILE])
        by_name = {item.name: item for item in processes}
        extra_keys = {item.name.casefold() for item in processes}
        routes = self._routes(tables[ROUTE_FILE], by_name, extra_keys)
        productivity, modes = self._productivity(tables[PRODUCTIVITY_FILE], by_name)
        equipment = self._equipment(tables[EQUIPMENT_FILE], by_name)
        rate_vital = self._rate_vital(tables[RATE_FILE], by_name)
        self._coverage(processes, routes, productivity, modes, equipment, rate_vital)
        if self.problems or info is None:
            return None
        return ExtraProcessPack(
            sha256=sha,
            info=info,
            processes=tuple(processes),
            routes=tuple(routes),
            productivity=tuple(productivity),
            equipment=tuple(equipment),
            rate_vital=tuple(rate_vital),
            ratio=self.ratio(),
        )

    def _info(self, rows: Sequence[tuple[int, _Row]]) -> PackInfo | None:
        values: dict[str, str] = {}
        for line_no, cells in rows:
            key = _clean(cells["항목"])
            if key in values:
                self.err("V-02", INFO_FILE, line_no, "항목", f"항목 중복 {key}")
                continue
            if key not in INFO_REQUIRED + INFO_OPTIONAL:
                self.err("V-02", INFO_FILE, line_no, "항목", f"모르는 항목 {key}")
                continue
            values[key] = _clean(cells["값"])
        for key in INFO_REQUIRED:
            if key not in values:
                self.err("V-02", INFO_FILE, None, "항목", f"필수 항목 없음 {key}")
        format_text = values.get("형식판")
        if format_text is not None and (
            not _POSITIVE_INT.fullmatch(format_text) or int(format_text) not in KNOWN_FORMATS
        ):
            self.err("V-02", INFO_FILE, None, "값", "모르는 파일 형식(형식판)")
        version_text = values.get("판")
        if version_text is not None:
            if _POSITIVE_INT.fullmatch(version_text):
                self.version_no = int(version_text)
            else:
                self.err("V-02", INFO_FILE, None, "값", "판이 양의 정수가 아님")
        if self.version_no is None or format_text is None or not format_text.isdigit():
            return None
        return PackInfo(
            format_version=int(format_text),
            version_no=self.version_no,
            written_at=values.get("작성시각", ""),
            author=values.get("작성자", ""),
            memo=values.get("메모", ""),
        )

    def _processes(self, rows: Sequence[tuple[int, _Row]]) -> list[ProcessRow]:
        found: list[ProcessRow] = []
        seen: set[str] = set()
        areas = {name.casefold(): name for name in AREA_NAMES}
        for line_no, cells in rows:
            file = PROCESS_FILE
            name = _clean(cells["공정"])
            if not name:
                self.err("V-03", file, line_no, "공정", "공정 빈칸")
                continue
            if name.casefold() in seen:
                self.err("V-03", file, line_no, "공정", "공정 중복(대소문자 무시)")
                continue
            seen.add(name.casefold())
            area = areas.get(_clean(cells["Area_Name"]).casefold())
            if area is None:
                self.err("V-03", file, line_no, "Area_Name", "Area_Name 은 Main · MI")
            basis_text = _clean(cells["소요기준"])
            basis = normalize_demand_basis_value(basis_text) if basis_text else ""
            if not basis:
                self.err(
                    "V-03",
                    file,
                    line_no,
                    "소요기준",
                    "소요기준 빈칸 — 경로 · UPEH 의 연결 키라 비면 계산 전체가 멈춤",
                )
            elif basis not in DEMAND_BASES:
                self.err("V-03", file, line_no, "소요기준", "소요기준은 PKG · CHIP · WF")
            modules = self.number(file, line_no, "모듈수", cells["모듈수"])
            if modules is None or math.isnan(modules) or not modules > 0:
                if modules is None or not math.isnan(modules):
                    self.err("V-03", file, line_no, "모듈수", "모듈수는 0 보다 커야 함")
                modules = math.nan
            # 값이 틀린 공정도 이름은 남긴다 — 02 ~ 05 가 「01 에 없는 공정」 으로 한 번 더 걸리지
            # 않게(판은 이미 거절이다).
            found.append(
                ProcessRow(name, area or "", basis, float(modules), _clean(cells["메모"]), line_no)
            )
        if not rows:
            self.err("V-03", PROCESS_FILE, None, "공정", "공정이 하나도 없음")
        return found

    def _known(self, file: str, row: int, name: str, by_name: Mapping[str, ProcessRow]) -> bool:
        if name in by_name:
            return True
        self.err("V-04", file, row, "공정", "01 에 없는 공정")
        return False

    def _routes(
        self,
        rows: Sequence[tuple[int, _Row]],
        by_name: Mapping[str, ProcessRow],
        extra_keys: set[str],
    ) -> list[RouteRow]:
        file = ROUTE_FILE
        found: list[RouteRow] = []
        for line_no, cells in rows:
            name = _clean(cells["공정"])
            known = self._known(file, line_no, name, by_name)
            reference = _clean(cells["참조공정"])
            product = normalize_product(_clean(cells["제품정보"]))
            stack = _clean(cells["Stack"])
            wf = _clean(cells["WF 구분"])
            step = _clean(cells["STEP_SEQ"])
            mcp = _clean(cells["MCP_SEQ"])
            bad = False
            filled = (bool(product), bool(stack), bool(wf))
            if reference and any(filled):
                self.err("V-06", file, line_no, "참조공정", "참조공정과 제품 칸을 함께 적음")
                bad = True
            elif not reference and not all(filled):
                self.err("V-06", file, line_no, "제품정보", "지정 꼴은 제품 칸 셋을 다 적어야 함")
                bad = True
            if reference and reference.casefold() in extra_keys:
                self.err("V-06", file, line_no, "참조공정", "부대공정끼리는 참조하지 않음")
                bad = True
            if not step or not mcp:
                self.err("V-06", file, line_no, "STEP_SEQ", "STEP_SEQ · MCP_SEQ 빈칸")
                bad = True
            if (
                known
                and by_name[name].basis == "PKG"
                and not reference
                and wf
                and wf_key(wf) != BUFFER_WORD
            ):
                self.err("V-06", file, line_no, "WF 구분", "PKG 는 Buffer 만")
                bad = True
            period = self.period(file, line_no, cells)
            # 꼴이 틀린 줄도 기간이 읽히면 남겨 V-05 · V-13 이 한 번 더 걸리지 않게 한다(판은 이미
            # 거절이다).
            del bad
            if period is None or not known:
                continue
            found.append(RouteRow(name, reference, product, stack, wf, step, mcp, period, line_no))
        self._overlaps(
            file,
            [
                (
                    (
                        item.process,
                        item.reference.casefold(),
                        item.product,
                        item.stack,
                        wf_key(item.wf),
                        item.step,
                        item.mcp,
                    ),
                    item.period,
                    item.row,
                )
                for item in found
            ],
        )
        return found

    def _productivity(
        self, rows: Sequence[tuple[int, _Row]], by_name: Mapping[str, ProcessRow]
    ) -> tuple[list[ProductivityRow], dict[tuple[str, str, str], bool]]:
        file = PRODUCTIVITY_FILE
        found: list[ProductivityRow] = []
        modes: dict[tuple[str, str, str], bool] = {}
        for line_no, cells in rows:
            name = _clean(cells["공정"])
            known = self._known(file, line_no, name, by_name)
            product = normalize_product(_clean(cells["제품정보"]))
            stack = _clean(cells["Stack"])
            wf = _clean(cells["WF 구분"])
            step = _clean(cells["STEP_SEQ"])
            mcp = _clean(cells["MCP_SEQ"])
            filled = (bool(product), bool(stack), bool(wf))
            bad = False
            if any(filled) and not all(filled):
                self.err("V-09", file, line_no, "제품정보", "제품 칸 일부만 적음")
                bad = True
            common = not any(filled)
            path = (name, step, mcp)
            if not bad and modes.setdefault(path, common) != common:
                self.err("V-09", file, line_no, "제품정보", "한 경로에 공통 행과 제품 행을 섞음")
                bad = True
            mass_class = _clean(cells["양산구분"])
            if mass_class not in CLASS_EXPANSION:
                self.err("V-09", file, line_no, "양산구분", "양산구분은 양산 · ER · 모두")
                bad = True
            upeh = self.number(file, line_no, "UPEH", cells["UPEH"])
            st = self.number(file, line_no, "ST", cells["ST"])
            if known:
                area = by_name[name].area
                if area == "Main" and (upeh is None or not upeh > 0 or st is not None):
                    self.err("V-10", file, line_no, "UPEH", "Main 은 UPEH > 0 · ST 빈칸")
                if area == "MI" and (st is None or not st > 0 or upeh is not None):
                    self.err("V-10", file, line_no, "ST", "MI 는 ST > 0 · UPEH 빈칸")
            ratios: list[float | None] = []
            for column in RATIO_COLUMNS:
                value = self.number(file, line_no, column, cells[column])
                ratios.append(value)
                if value is None:
                    self.ratio_blank += 1
                elif math.isnan(value):
                    continue
                elif value == 0:
                    self.ratio_zero += 1
                elif value < 0:
                    self.err(
                        "V-10",
                        file,
                        line_no,
                        column,
                        "측정률 음수 — 빈칸 · 0(→ 1.0) · 0 보다 큰 수만",
                    )
            period = self.period(file, line_no, cells)
            # 값이 틀린 줄도 꼴(제품 칸 · 양산구분)이 맞고 기간이 읽히면 남겨 덮임(V-13)이 한 번 더
            # 걸리지 않게 한다(판은 이미 거절이다).
            if period is None or bad or not known:
                continue
            found.append(
                ProductivityRow(
                    name,
                    product,
                    stack,
                    wf,
                    step,
                    mcp,
                    mass_class,
                    period,
                    upeh,
                    st,
                    ratios[0],
                    ratios[1],
                    line_no,
                )
            )
        self._overlaps(
            file,
            [
                (
                    (
                        item.process,
                        item.product,
                        item.stack,
                        wf_key(item.wf),
                        item.step,
                        item.mcp,
                        cls,
                    ),
                    item.period,
                    item.row,
                )
                for item in found
                for cls in CLASS_EXPANSION[item.mass_class]
            ],
        )
        return found, modes

    def _equipment(
        self, rows: Sequence[tuple[int, _Row]], by_name: Mapping[str, ProcessRow]
    ) -> list[EquipmentRow]:
        file = EQUIPMENT_FILE
        found: list[EquipmentRow] = []
        for line_no, cells in rows:
            name = _clean(cells["공정"])
            known = self._known(file, line_no, name, by_name)
            period = self.period(file, line_no, cells)
            bad = False
            run_text = _clean(cells["RUN_DAY"])
            run_day: int | None = None
            if run_text != CALENDAR_WORD:
                value = self.number(file, line_no, "RUN_DAY", run_text)
                if (
                    value is None
                    or math.isnan(value)
                    or not 0 < value <= 31
                    or not value.is_integer()
                ):
                    if value is None or not math.isnan(value):
                        self.err(
                            "V-11", file, line_no, "RUN_DAY", "RUN_DAY 는 달력 또는 1 ~ 31 의 정수"
                        )
                    bad = True
                else:
                    run_day = int(value)
                    if period is not None and self._longer_than_month(run_day, period):
                        self.err(
                            "V-11",
                            file,
                            line_no,
                            "RUN_DAY",
                            "RUN_DAY 가 그 기간 어느 달의 날수보다 큼",
                        )
                        bad = True
            owned = self.number(file, line_no, "설비보유", cells["설비보유"])
            lent = self.number(file, line_no, "설비대여평가", cells["설비대여평가"])
            if owned is None or math.isnan(owned) or not owned >= 0:
                if owned is None or not math.isnan(owned):
                    self.err("V-11", file, line_no, "설비보유", "설비보유는 0 이상")
                bad = True
            if lent is not None and (math.isnan(lent) or not lent >= 0):
                if not math.isnan(lent):
                    self.err(
                        "V-11", file, line_no, "설비대여평가", "설비대여평가는 빈칸 또는 0 이상"
                    )
                bad = True
            if (
                owned is not None
                and lent is not None
                and not math.isnan(owned)
                and not math.isnan(lent)
                and lent > owned
            ):
                self.err(
                    "V-11",
                    file,
                    line_no,
                    "설비대여평가",
                    "대여 > 보유 — 가용대수가 음수면 확보율 계산 전체가 멈춤",
                )
                bad = True
            # 값이 틀린 줄도 기간이 읽히면 남겨 덮임(V-13)이 한 번 더 걸리지 않게 한다(`bad` 면
            # 판은 이미 거절이다).
            if period is None or not known:
                continue
            found.append(
                EquipmentRow(
                    name,
                    period,
                    None if bad else run_day,
                    math.nan if owned is None else float(owned),
                    lent,
                    line_no,
                )
            )
        self._overlaps(file, [((item.process,), item.period, item.row) for item in found])
        return found

    @staticmethod
    def _longer_than_month(run_day: int, period: Period) -> bool:
        month, seen = period.start, 0
        while True:
            if run_day > calendar.monthrange(month // 100, month % 100)[1]:
                return True
            seen += 1
            if (period.end is not None and month >= period.end) or (
                period.end is None and seen >= OPEN_LOOKAHEAD_MONTHS
            ):
                return False
            month = _next_month(month)

    def _rate_vital(
        self, rows: Sequence[tuple[int, _Row]], by_name: Mapping[str, ProcessRow]
    ) -> list[RateVitalRow]:
        file = RATE_FILE
        found: list[RateVitalRow] = []
        for line_no, cells in rows:
            name = _clean(cells["공정"])
            known = self._known(file, line_no, name, by_name)
            mass_class = _clean(cells["양산구분"])
            bad = False
            if mass_class not in CLASS_EXPANSION:
                self.err("V-12", file, line_no, "양산구분", "양산구분은 양산 · ER · 모두")
                bad = True
            run_rate = self.number(file, line_no, "CAPA_RUN_RATE", cells["CAPA_RUN_RATE"])
            vital = self.number(file, line_no, "편중률", cells["편중률"])
            if run_rate is None or math.isnan(run_rate) or not run_rate > 0:
                if run_rate is None or not math.isnan(run_rate):
                    self.err("V-12", file, line_no, "CAPA_RUN_RATE", "효율은 0 보다 커야 함")
                bad = True
            elif run_rate > 1:
                self.warn("V-12", file, line_no, "CAPA_RUN_RATE", "효율이 1 을 넘음")
            if vital is None or math.isnan(vital) or not vital > 0:
                if vital is None or not math.isnan(vital):
                    self.err("V-12", file, line_no, "편중률", "편중률은 0 보다 커야 함")
                bad = True
            period = self.period(file, line_no, cells)
            # 값이 틀린 줄도 양산구분이 맞고 기간이 읽히면 남긴다(판은 이미 거절이다).
            if period is None or not known or mass_class not in CLASS_EXPANSION:
                continue
            del bad
            found.append(
                RateVitalRow(
                    name,
                    mass_class,
                    period,
                    math.nan if run_rate is None else run_rate,
                    math.nan if vital is None else vital,
                    line_no,
                )
            )
        self._overlaps(
            file,
            [
                ((item.process, cls), item.period, item.row)
                for item in found
                for cls in CLASS_EXPANSION[item.mass_class]
            ],
        )
        return found

    def _overlaps(self, file: str, items: Iterable[tuple[tuple[str, ...], Period, int]]) -> None:
        """같은 키의 기간이 겹치면 V-08(`모두` 는 펼친 뒤에 본다)."""
        by_key: dict[tuple[str, ...], list[tuple[tuple[int, int], int]]] = {}
        for key, period, row in items:
            by_key.setdefault(key, []).append((period.span(), row))
        for spans in by_key.values():
            spans.sort()
            for (first, _), (second, row) in zip(spans, spans[1:], strict=False):
                if second[0] <= first[1]:
                    self.err("V-08", file, row, "시작월", "같은 키의 기간이 겹침")

    def _coverage(
        self,
        processes: Sequence[ProcessRow],
        routes: Sequence[RouteRow],
        productivity: Sequence[ProductivityRow],
        modes: Mapping[tuple[str, str, str], bool],
        equipment: Sequence[EquipmentRow],
        rate_vital: Sequence[RateVitalRow],
    ) -> None:
        """V-05 · V-09 끝 · V-13 — 경로가 있고, 값 표가 경로 기간을 덮는다."""
        for process in processes:
            if not any(route.process == process.name for route in routes):
                self.err("V-05", PROCESS_FILE, process.row, "공정", "경로(02)가 하나도 없음")
        for route in routes:
            path = (route.process, route.step, route.mcp)
            common = modes.get(path)
            if common is None:
                self.err(
                    "V-13", ROUTE_FILE, route.row, "STEP_SEQ", "이 경로의 생산성(03) 행이 없음"
                )
                continue
            if route.follows and not common:
                self.err(
                    "V-09",
                    ROUTE_FILE,
                    route.row,
                    "참조공정",
                    "따라가기 꼴 경로의 생산성은 공통 값이어야 함",
                )
                continue
            need = route.period.span()
            for cls in (MASS, ENGINEERING):
                have = [
                    item.period.span()
                    for item in productivity
                    if (item.process, item.step, item.mcp) == path
                    and cls in CLASS_EXPANSION[item.mass_class]
                    and (
                        item.common
                        if common
                        else (item.product, item.stack, wf_key(item.wf))
                        == (route.product, route.stack, wf_key(route.wf))
                    )
                ]
                if not _covered(need, have):
                    self.err(
                        "V-13",
                        ROUTE_FILE,
                        route.row,
                        "시작월",
                        f"{cls} 생산성(03) 기간이 경로를 덮지 않음",
                    )
            if not _covered(
                need, [item.period.span() for item in equipment if item.process == route.process]
            ):
                self.err(
                    "V-13",
                    ROUTE_FILE,
                    route.row,
                    "시작월",
                    "가동일수 · 설비(04) 기간이 경로를 덮지 않음",
                )
            for cls in (MASS, ENGINEERING):
                have = [
                    item.period.span()
                    for item in rate_vital
                    if item.process == route.process and cls in CLASS_EXPANSION[item.mass_class]
                ]
                if not _covered(need, have):
                    self.err(
                        "V-13",
                        ROUTE_FILE,
                        route.row,
                        "시작월",
                        f"{cls} 효율 · 여유율(05) 기간이 경로를 덮지 않음",
                    )


def _covered(need: tuple[int, int], have: Sequence[tuple[int, int]]) -> bool:
    """`need` 구간이 `have` 구간들의 합집합 안에 드는가(달 단위)."""
    low, high = need
    for start, end in sorted(have):
        if start > low:
            return False
        if end >= low:
            low = end + 1
        if low > high:
            return True
    return low > high


def _decode(raw: bytes) -> tuple[str | None, bool]:
    """(글, UTF-8 로 읽혔나) — UTF-8(BOM 허용), 안 되면 CP949, 둘 다 안 되면 글 None."""
    try:
        return raw.decode("utf-8-sig"), True
    except UnicodeDecodeError:
        try:
            return raw.decode("cp949"), False
        except UnicodeDecodeError:
            return None, False


# --------------------------------------------------------------------------- 판 견주기


@dataclass(frozen=True)
class PackChanges:
    """두 판의 차이 — 더한 공정 · 뺀 공정 · 바뀐 칸 수 · 그 가운데 앞 판 값으로 되돌리는 칸
    수(G12)."""

    added: tuple[str, ...] = ()
    removed: tuple[str, ...] = ()
    changed_cells: int = 0
    reverted_cells: int = 0


_Cell = tuple[str, tuple[object, ...], str]


def pack_cells(pack: ExtraProcessPack) -> dict[_Cell, object]:
    """판을 (파일, 줄 키, 칸) → 값으로 편다 — 줄 키는 값이 아닌 칸(공정 · 경로 · 제품 · 시작월)."""
    cells: dict[_Cell, object] = {}

    def put(file: str, key: tuple[object, ...], values: Mapping[str, object]) -> None:
        for column, value in values.items():
            cells[(file, key, column)] = value

    for item in pack.processes:
        put(
            PROCESS_FILE,
            (item.name,),
            {"Area_Name": item.area, "소요기준": item.basis, "모듈수": item.modules},
        )
    for route in pack.routes:
        key = (
            route.process,
            route.reference,
            route.product,
            route.stack,
            wf_key(route.wf),
            route.step,
            route.mcp,
            route.period.start,
        )
        put(ROUTE_FILE, key, {"끝월": route.period.end})
    for row in pack.productivity:
        key = (
            row.process,
            row.product,
            row.stack,
            wf_key(row.wf),
            row.step,
            row.mcp,
            row.mass_class,
            row.period.start,
        )
        put(
            PRODUCTIVITY_FILE,
            key,
            {
                "끝월": row.period.end,
                "UPEH": row.upeh,
                "ST": row.st,
                "Lot 측정률": row.lot_ratio,
                "WF측정률": row.wf_ratio,
            },
        )
    for equipment in pack.equipment:
        put(
            EQUIPMENT_FILE,
            (equipment.process, equipment.period.start),
            {
                "끝월": equipment.period.end,
                "RUN_DAY": equipment.run_day,
                "설비보유": equipment.owned,
                "설비대여평가": equipment.lent,
            },
        )
    for rate in pack.rate_vital:
        put(
            RATE_FILE,
            (rate.process, rate.mass_class, rate.period.start),
            {"끝월": rate.period.end, "CAPA_RUN_RATE": rate.run_rate, "편중률": rate.vital},
        )
    return cells


def pack_changes(
    new: ExtraProcessPack, current: ExtraProcessPack | None, before: ExtraProcessPack | None = None
) -> PackChanges:
    """새 판을 활성 판(`current`)과 견준다. `before` 는 활성 판의 바로 앞 판 — 바뀐 칸 가운데 그
    값과 같아지는 칸을 따로 센다(옛 사본에서 판 번호만 올려 놓은 파일을 알아보게 — 설계 3-2 ·
    G12)."""
    new_cells = pack_cells(new)
    old_cells = {} if current is None else pack_cells(current)
    before_cells = None if before is None else pack_cells(before)
    changed = [
        key
        for key in new_cells.keys() | old_cells.keys()
        if new_cells.get(key) != old_cells.get(key)
    ]
    reverted = (
        0
        if before_cells is None
        else sum(
            1
            for key in changed
            if key in new_cells and before_cells.get(key, _MISSING) == new_cells[key]
        )
    )
    new_names = new.process_names()
    old_names = () if current is None else current.process_names()
    return PackChanges(
        added=tuple(name for name in new_names if name not in old_names),
        removed=tuple(name for name in old_names if name not in new_names),
        changed_cells=len(changed),
        reverted_cells=reverted,
    )


_MISSING: Final = object()
