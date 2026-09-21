# Purpose: DuckDB 공용 헬퍼의 감사 해시가 표 하나·표 묶음에서 같은 바이트 열을 내는지 못박는다.

"""저장된 `reference_hash`·`equipment_hash` 는 append-only 감사값이다.

`hash_frame` 과 `hash_tables` 가 같은 digest 갱신 순서를 나눠 쓰므로, 어느 한쪽을 고치면
이미 DB 에 적힌 해시와 새로 계산한 해시가 어긋난다. 아래 값은 리팩토링 전 구현이 낸 것을
그대로 핀한 것이다 — 값이 바뀌면 감사 기록과의 호환이 깨진 것이지 테스트가 낡은 것이 아니다.
"""

import pandas as pd

from capa_simulation.persistence._sql_helpers import hash_frame, hash_tables


def _frames() -> dict[str, pd.DataFrame]:
    return {
        "A": pd.DataFrame(
            {
                "공정": ["P1", "P2", None],
                "수량": [1, 2, 3],
                "비율": [0.5, 1.5, 2.5],
                "일자": pd.to_datetime(["2026-01-01", "2026-02-01", "2026-03-01"]),
                "플래그": [True, False, True],
            }
        ),
        "B": pd.DataFrame({"x": [], "y": []}),
        "C": pd.DataFrame({"only": ["v"]}),
    }


def test_hash_frame_is_pinned_to_the_pre_refactor_digest() -> None:
    frames = _frames()

    assert hash_frame(frames["A"]) == (
        "996a8c1f1b6ce24207a9e2c024c9525ecc1c29e502e67cc179edf74354b64c34"
    )
    assert hash_frame(frames["B"]) == (
        "adbbc83fffe5c8ca4ebdb1c5071be05fb28ca885d36672e14a4a84f70c266eea"
    )
    assert hash_frame(frames["C"]) == (
        "8ba417e7074c94ed6bb2813f1bfaf22632917aecdb1416f2a4a30d3d4aa949df"
    )


def test_hash_tables_sorts_names_and_shares_the_frame_digest() -> None:
    frames = _frames()

    # 이름 순서를 섞어 넘겨도 정렬해서 더하므로 결과가 같다.
    assert hash_tables(frames, ["C", "A", "B"]) == (
        "413df6da994ea3baa12c6c882256d87f05054813408604f84cd570cbfc51c7a2"
    )
    assert hash_tables(frames, ["A", "B"]) == (
        "c22c7fb7a0b0a91565ce6ff988bd2470472f13b96ddf51745b5d63c23f44e6d0"
    )
