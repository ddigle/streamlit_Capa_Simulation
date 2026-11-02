# Purpose: 범용 편집 그리드 시험 앱 — DEMO 합성 표 둘을 한 마운트에 바꿔 그린다(시험 전용).

"""AppTest 대본이자 사본 앱 브라우저 확인 대상(`streamlit run tests/edit_grid_demo_app.py`). 앱
화면에는 넣지 않는다. 값은 모두 합성 `DEMO_*` 이다. 표 고르기는 네이티브 segmented
control(`demo_table`)이고, 그리드 마운트는 표를 바꿔도 같은 key·같은 자리다. 「적용」 은 양식에
초안을 되머지해 고친 칸 수만 보인다(저장하지 않는다).
"""

from __future__ import annotations

from functools import partial

import numpy as np
import pandas as pd
import streamlit as st

from capa_simulation.components import edit_grid
from capa_simulation.services import edit_grid as eg
from capa_simulation.services.edit_grid_payload import base_key, labels_digest
from capa_simulation.services.simulation_cache import get_edit_grid_base

HOST = "demo_grid"
KEYS = edit_grid.GridKeys(
    inbox="demo_grid_inbox", applied="demo_grid_applied", toast="demo_grid_toast"
)
SMALL = "DEMO_SMALL"
BIG = "DEMO_BIG"
SMALL_MONTHS = tuple(f"2027{month:02d}" for month in range(1, 7))
BIG_MONTHS = tuple(f"{2027 + (k // 12)}{k % 12 + 1:02d}" for k in range(30))
SPECS = {
    SMALL: eg.GridSpec(
        SMALL,
        "효율(데모)",
        ("공정", "양산구분"),
        SMALL_MONTHS,
        eg.ValueFormat("percent", 2, max_value=1.0),
    ),
    BIG: eg.GridSpec(
        BIG,
        "UPEH(데모)",
        tuple(f"분류{j}" for j in range(9)),
        BIG_MONTHS,
        eg.ValueFormat("sig", 6),
        value_help="Main 행은 UPEH(시간당 처리량), MI 행은 ST(분) — 데모 풍선입니다.",
    ),
}
LABELS = {SMALL: {"공정": {"DEMO_P01": "데모 공정 1"}}, BIG: None}


def _small() -> pd.DataFrame:
    rows = 20
    frame = pd.DataFrame(
        {
            "공정": [f"DEMO_P{k // 2 + 1:02d}" for k in range(rows)],
            "양산구분": ["양산" if k % 2 == 0 else "ER" for k in range(rows)],
        }
    )
    for column, month in enumerate(SMALL_MONTHS):
        frame[month] = [round(0.8 + ((k + column) % 7) / 50, 4) for k in range(rows)]
    frame.loc[3, SMALL_MONTHS[2]] = np.nan
    return frame


def _big() -> pd.DataFrame:
    rows = 2660
    sizes = (70, 2, 2, 2, 8, 4, 6, 70, 2)
    order = np.arange(rows)
    frame = pd.DataFrame(
        {
            f"분류{j}": [f"DEMO_{j}_{value}" for value in (order * (j + 3) // 7) % size]
            for j, size in enumerate(sizes)
        }
    )
    rng = np.random.default_rng(11)
    pool = np.round(rng.uniform(0.02, 600, size=2400), 6)
    first = pool[rng.integers(0, 2400, size=rows)]
    second = pool[rng.integers(0, 2400, size=rows)]
    step = rng.integers(0, 60, size=rows)
    values = np.where(np.arange(30)[None, :] >= step[:, None], second[:, None], first[:, None])
    for column, month in enumerate(BIG_MONTHS):
        frame[month] = values[:, column]
    return frame


def cells_key(table: str) -> str:
    return f"demo_grid_cells__{table}"


def history_key(table: str) -> str:
    return f"demo_grid_history__{table}"


# 앱 화면과 같은 넓은 본문(앱은 `app.py` 가 wide 로 연다) — 큰 표의 월 칸이 보이게.
st.set_page_config(layout="wide")

if "demo_frames" not in st.session_state:
    st.session_state["demo_frames"] = {SMALL: _small(), BIG: _big()}
    st.session_state["demo_versions"] = {SMALL: 0, BIG: 0}
frames: dict[str, pd.DataFrame] = st.session_state["demo_frames"]
versions: dict[str, int] = st.session_state["demo_versions"]


def content_key(table: str) -> str:
    """내용 토큰 대신 — 「적용」 마다 판이 올라 껍데기 지문도 바뀐다."""
    return f"demo:{table}:{versions[table]}"


bases = {
    table: get_edit_grid_base(
        content_key(table),
        "-",
        table,
        labels_digest(LABELS[table]),
        _template=frames[table],
        _spec=SPECS[table],
        _labels=LABELS[table],
    )
    for table in SPECS
}
slots = {
    table: edit_grid.TableSlot(base.index, SPECS[table], cells_key(table), history_key(table))
    for table, base in bases.items()
}
edit_grid.apply_inbox(KEYS, slots)

choice = st.segmented_control(
    "표",
    list(SPECS),
    format_func=lambda table: SPECS[table].title,
    key="demo_table",
    default=SMALL,
)
table = choice if choice in SPECS else SMALL
counts = {name: eg.change_counts(edit_grid.draft_of(cells_key(name))) for name in SPECS}
st.caption(
    " · ".join(
        f"{SPECS[name].title} 고친 칸 {cells:,} · 오류 {errors:,}"
        for name, (cells, _, errors) in counts.items()
    ),
    help="데모 — 저장하지 않습니다",
)
if st.button("적용", key="demo_apply", disabled=not edit_grid.draft_pending(cells_key(table))):
    try:
        merged = eg.merge_into_template(
            frames[table], SPECS[table], edit_grid.draft_of(cells_key(table))
        )
    except ValueError as error:
        st.warning(str(error))
    else:
        frames[table] = merged
        versions[table] += 1
        edit_grid.discard_table((cells_key(table), history_key(table)))
        st.rerun()

key_text = base_key(table, content_key(table), "-", labels_digest(LABELS[table]))
shell = edit_grid.shell_data(
    HOST, bases[table], SPECS[table], base_key=key_text, changes_label="적용 전 변경"
)
feed = edit_grid.feed_data(HOST, slots[table], KEYS, base_key=key_text)
with st.container(key="demo_grid_box"):
    edit_grid.render_edit_grid(
        HOST, shell, feed, on_outbox=partial(edit_grid.collect_outbox, HOST, KEYS)
    )
