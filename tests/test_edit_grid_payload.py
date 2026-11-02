# Purpose: 범용 편집 그리드 껍데기·feed 꼴(64자 코드·값 사전·줄 RLE)과 그 바이트 예산을 단위로 본다.

from __future__ import annotations

import time

import numpy as np
import pandas as pd
import pytest

from capa_simulation.services import edit_grid as eg
from capa_simulation.services import edit_grid_payload as payload


def test_code_width_grows_by_powers_of_sixty_four() -> None:
    assert [payload.code_width(n) for n in (0, 1, 64, 65, 4096, 4097)] == [1, 1, 1, 2, 2, 3]
    assert payload.encode_codes([0, 63, 1], 1) == "0_1"
    assert payload.encode_codes([64, 0], 2) == "1000"
    assert payload.encode_codes([], 2) == ""


def test_runs_pair_codes_with_lengths_and_split_long_runs() -> None:
    codes = np.array([[1, 1, 2, 2, 2, 0], [3, 3, 3, 3, 3, 3]], dtype=np.int64)
    assert payload.encode_runs(codes, 1) == ["122301", "36"]
    long = np.full((1, 130), 5, dtype=np.int64)
    # 63 + 63 + 4 — 길이 글자는 1~63 이다.
    assert payload.encode_runs(long, 1) == ["5_5_54"]
    assert payload.encode_runs(np.zeros((2, 0), dtype=np.int64), 1) == ["", ""]


def test_json_numbers_drop_needless_fractions() -> None:
    assert payload.json_number(30.0) == 30 and isinstance(payload.json_number(30.0), int)
    assert payload.json_number(-0.0) == 0
    assert payload.json_number(0.9875) == 0.9875
    assert isinstance(payload.json_number(2.0**60), float)


def _small() -> tuple[pd.DataFrame, eg.GridSpec]:
    frame = pd.DataFrame(
        {
            "공정": ["DEMO_B", "DEMO_A", "DEMO_B", "DEMO_A"],
            "구분": ["양산", "양산", "ER", "양산"],
            "202701": [1.0, 2.0, np.nan, 2.0],
            "202702": [1.0, 2.5, 3.0, 2.0],
        }
    )
    spec = eg.GridSpec(
        "RQ_DEMO",
        "데모",
        ("공정", "구분"),
        ("202701", "202702"),
        eg.ValueFormat("fixed", 2, blank_zero=True),
        value_help="값 칸 도움말",
    )
    return frame, spec


def test_the_table_body_carries_dictionaries_codes_and_runs() -> None:
    frame, spec = _small()
    base = payload.build_base(frame, spec, {"공정": {"DEMO_A": "에이"}, "구분": {}})
    body = base.body
    assert body["dims"] == [["DEMO_B", "DEMO_A"], ["양산", "ER"]]
    assert body["labels"] == [["DEMO_B", "에이"], None]
    assert body["codes"] == ["0101", "0010"] and body["codeWidths"] == [1, 1]
    assert body["vals"] == [None, 1, 2, 2.5, 3]
    assert body["runs"] == ["12", "2131", "0141", "22"]
    assert body["dupes"] == [[3, 1]]
    assert body["fmt"] == {
        "kind": "fixed",
        "digits": 2,
        "int": False,
        "min": 0.0,
        "max": None,
        "blankZero": True,
    }
    assert body["valueHelp"] == "값 칸 도움말" and body["rows"] == 4
    assert base.index.keys == (
        "DEMO_B\x1f양산",
        "DEMO_A\x1f양산",
        "DEMO_B\x1fER",
        "DEMO_A\x1f양산\x1e1",
    )


def test_the_shell_adds_host_key_texts_palette_and_limits() -> None:
    frame, spec = _small()
    base = payload.build_base(frame, spec, None)
    shell = payload.encode_base(
        base.body,
        host="demo",
        base_key="k1",
        texts={"a": "b"},
        palette={"text": "x"},
        row_height=30,
    )
    assert shell["host"] == "demo" and shell["baseKey"] == "k1"
    assert shell["rowHeight"] == 30 and shell["headHeight"] == payload.HEAD_HEIGHT_PX
    assert shell["limits"] == {"paste": 15_000, "outbox": 30_000, "bad": 2_000, "undo": 40}
    again = payload.encode_base(
        payload.build_base(frame, spec, None).body,
        host="demo",
        base_key="k1",
        texts={"a": "b"},
        palette={"text": "x"},
        row_height=30,
    )
    assert payload.payload_bytes(again) == payload.payload_bytes(shell) and again == shell
    empty = payload.empty_base(host="demo", texts={}, palette={})
    assert empty["table"] is None and empty["baseKey"] == ""


def test_the_feed_carries_draft_runs_errors_counts_and_acks() -> None:
    frame, spec = _small()
    index = payload.build_base(frame, spec, None).index
    draft: eg.DraftState = {
        "cells": {index.keys[1]: {"202701": 7.0, "202702": 7.0}, index.keys[3]: {"202702": None}},
        "bad": {index.keys[0]: {"202702": ("x", "num")}, "없는\x1f키": {"202701": ("y", "num")}},
    }
    history: eg.HistoryState = {"gen": "g7", "undo": [], "redo": []}
    feed = payload.encode_feed(
        index,
        draft,
        history,
        host="demo",
        base_key="k1",
        acks={"m": 4},
        toast={"id": 2, "text": "t"},
        filters={0: [1]},
    )
    assert feed["gen"] == "g7" and feed["table"] == "RQ_DEMO" and feed["baseKey"] == "k1"
    assert feed["dvals"] == [7] and feed["dwidth"] == 1
    # 줄 0: 칸 1 이 못 읽음(2) · 줄 1: 칸 0~1 이 값(3) · 줄 3: 칸 1 이 빈칸(1).
    assert feed["drows"] == [[0, 1, "21"], [1, 0, "32"], [3, 1, "11"]]
    assert feed["bad"] == [[0, 1, "x", "num"]] and feed["badCount"] == 1
    assert feed["counts"] == {"cells": 5, "rows": 4, "errors": 2}
    assert feed["acks"] == {"m": 4} and feed["toast"] == {"id": 2, "text": "t"}
    assert feed["filters"] == {"0": [1]}
    blank = payload.encode_feed(None, None, None, host="demo", base_key="", acks={}, toast=None)
    assert blank["table"] is None and blank["drows"] == [] and blank["gen"] == ""


def test_the_feed_keeps_only_the_first_error_cells(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(payload, "BAD_LIMIT", 2)
    frame, spec = _small()
    index = payload.build_base(frame, spec, None).index
    draft: eg.DraftState = {
        "cells": {},
        "bad": {key: {"202701": ("x", "num"), "202702": ("z", "num")} for key in index.keys},
    }
    feed = payload.encode_feed(
        index, draft, eg.new_history(), host="demo", base_key="k", acks={}, toast=None
    )
    assert len(feed["bad"]) == 2 and feed["badCount"] == 8


def test_labels_digest_follows_the_mapping_not_its_order() -> None:
    assert payload.labels_digest(None) == "-" and payload.labels_digest({}) == "-"
    one = payload.labels_digest({"공정": {"a": "가", "b": "나"}})
    two = payload.labels_digest({"공정": {"b": "나", "a": "가"}})
    assert one == two != payload.labels_digest({"공정": {"a": "다"}})
    assert payload.base_key("T", "tok", "ord", one) == f"T:tok:ord:{one}"


# ------------------------------------------------------------------ 예산(합성 표본 — 샘플 관측)


def _upeh_like(rows: int = 2660, months: int = 30) -> tuple[pd.DataFrame, eg.GridSpec]:
    """UPEH 꼴 합성 DEMO 2,660×30 고정 사례 — 열쇠 칸 9개(사전 크기 70·2·2·2·8·4·6·70·2), 값 사전 약
    1,950개, 줄마다 한 번 값이 바뀐다."""
    cards = (70, 2, 2, 2, 8, 4, 6, 70, 2)
    names = tuple(f"K{j}" for j in range(9))
    order = np.arange(rows)
    frame = pd.DataFrame(
        {
            name: [f"DEMO_{name}_{v}" for v in (order * (j + 3) // 7) % size]
            for j, (name, size) in enumerate(zip(names, cards, strict=True))
        }
    )
    rng = np.random.default_rng(11)
    pool = np.round(rng.uniform(0.02, 600, size=2400), 6)
    first = pool[rng.integers(0, 2400, size=rows)]
    second = pool[rng.integers(0, 2400, size=rows)]
    step = rng.integers(0, months * 2, size=rows)
    values = np.where(np.arange(months)[None, :] >= step[:, None], second[:, None], first[:, None])
    values[::13, :3] = np.nan
    month_names = tuple(f"M{k:02d}" for k in range(months))
    for column, name in enumerate(month_names):
        frame[name] = values[:, column]
    return frame, eg.GridSpec("RQ_UPEH", "UPEH", names, month_names, eg.ValueFormat("sig", 6))


def test_a_large_shell_stays_within_budget_and_builds_quickly() -> None:
    """명세 12장 — 껍데기 UPEH ≤ 104 KB(D2 80 KB). 이 고정 사례의 잰 값은 본문 76,809 B · 짓기 21~26
    ms
    (numpy) 라 예산을 잰 값 × 1.3 = 100,000 B 로 둔다. 짓기 목표 ≤ 100 ms 는 관문 부하를 넘겨 넉넉히
    본다."""
    frame, spec = _upeh_like()
    payload.build_base(frame, spec, None)
    began = time.perf_counter()
    base = payload.build_base(frame, spec, None)
    elapsed = time.perf_counter() - began
    assert payload.payload_bytes(base.body) <= 100_000
    assert elapsed < 0.4, elapsed


def test_feeds_stay_within_budget_for_one_hundred_and_fifteen_thousand_cells() -> None:
    """명세 12장 — feed 고친 칸 1 / 100 / 15,000 ≤ 1 KB / 4 KB / 64 KB. 잰 값: 359 B · 2,347
    B(흩어진
    100칸 — 값이 모두 다름) · 14,993 B(같은 표의 500×30 덩어리를 붙여넣은 꼴). 값이 모두 다른
    15,000칸은 값 사전이 커서 약 155 KB 다(무작위 값 — 실제 붙여넣기는 표의 값이라 겹친다)."""
    frame, spec = _upeh_like()
    index = payload.build_base(frame, spec, None).index
    history = eg.new_history()

    def size(draft: eg.DraftState) -> int:
        feed = payload.encode_feed(
            index,
            draft,
            history,
            host="reference_grid",
            base_key="RQ_UPEH:" + "x" * 40,
            acks={"g-abcdef12345": 12},
            toast={"id": 3, "text": "없는 줄 1개는 건너뛰었습니다"},
        )
        return payload.payload_bytes(feed)

    one: eg.DraftState = {"cells": {index.keys[5]: {"M03": 12.5}}, "bad": {}}
    scattered: eg.DraftState = {
        "cells": {index.keys[k * 20]: {f"M{(k * 7) % 30:02d}": k + 0.5} for k in range(100)},
        "bad": {},
    }
    block: eg.DraftState = {"cells": {}, "bad": {}}
    for k in range(500):
        source = index.values[(k + 1000) % len(index.keys)]
        block["cells"][index.keys[k]] = {
            f"M{c:02d}": None if np.isnan(source[c]) else float(source[c]) for c in range(30)
        }
    assert size(one) <= 1_000
    assert size(scattered) <= 4_000
    assert size(block) <= 64_000
