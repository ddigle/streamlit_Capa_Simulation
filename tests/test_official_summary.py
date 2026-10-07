# Purpose: 입장 화면 Summary 의 공식버전 6개월 요약 계산과 브라우저로 보내는 값을 검증한다.

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from types import SimpleNamespace

import pandas as pd
import pytest
import streamlit as st

from capa_simulation.components.intro_summary import summary_payload
from capa_simulation.design import tokens
from capa_simulation.services.official_summary import (
    OfficialSummary,
    build_official_summary,
    shift_month,
    short_units,
    summary_months,
)
from capa_simulation.services.securement_threshold import SecurementThresholds

MONTHS = [202610, 202611, 202612, 202701, 202702, 202703]


def test_months_shift_across_year_ends_in_both_directions() -> None:
    assert shift_month(202611, 3) == 202702
    assert shift_month(202612, 1) == 202701
    assert shift_month(202701, -1) == 202612
    assert shift_month(202610, 0) == 202610
    assert shift_month(202601, 24) == 202801


def test_the_window_starts_at_the_later_of_the_saved_start_and_the_first_plan_month() -> None:
    """앞쪽은 데이터가 없는 달이고, 뒤쪽은 공식버전을 지정한 사람이 보라고 저장한 시작이다."""
    assert summary_months(202601, 202610, 202812) == MONTHS
    assert summary_months(202611, 202610, 202812)[0] == 202611
    # 계획이 여섯 달보다 짧으면 있는 달까지만.
    assert summary_months(202610, 202610, 202612) == [202610, 202611, 202612]
    assert summary_months(202701, 202610, 202612) == []


@pytest.mark.parametrize(
    ("required", "available", "expected"),
    [
        (34.0, 32.0, 2),
        (32.2, 32.0, 1),  # 0.2대 모자라도 한 대를 더 들여야 한다
        (31.0, 32.0, 0),
        (33.0 + 1e-12, 33.0, 0),  # 계산의 부동소수 꼬리는 한 대를 만들지 않는다
        (None, 32.0, None),
        (34.0, None, None),
    ],
)
def test_short_units_round_up_the_missing_equipment(
    required: float | None, available: float | None, expected: int | None
) -> None:
    assert short_units(required, available) == expected


def _securement() -> pd.DataFrame:
    rows = []
    for index, month in enumerate(MONTHS):
        # P-LOW 는 늘 가장 낮지만 필터에서 빠진다. 필터 안에서는 달마다 B/N 이 바뀐다.
        rows.append((month, "P-LOW", 0.5, 10.0, 20.0))
        rows.append((month, "P-A", 0.94 + index * 0.01, 32.0, 34.0))
        rows.append((month, "P-B", 1.2 - index * 0.06, 50.0, 41.0))
    return pd.DataFrame(rows, columns=["생산계획년월", "공정", "확보율", "가용대수", "소요대수"])


def _volume(edp: bool) -> pd.DataFrame:
    rows = []
    for month in MONTHS:
        rows.append((month, "PROD-A", 120.0, 900.0, False))
        rows.append((month, "PROD-B", 60.0, 300.0, False))
        if edp:
            rows.append((month, "PROD-EDP", 20.0, 100.0, False))
    return pd.DataFrame(
        rows, columns=["생산계획년월", "제품정보", "Wafer 부하량", "생산수량", "과거"]
    )


def _summary() -> OfficialSummary:
    density = pd.DataFrame(
        {"생산계획년월": MONTHS, "부하량": [14.97, 15.24, 14.8, 14.33, 14.57, 15.42]}
    )
    wafer = pd.DataFrame(
        {"생산계획년월": MONTHS, "Wafer 부하량": [211000.0, 215000, 209000, 202000, 206000, 214000]}
    )
    return build_official_summary(
        months=MONTHS,
        monthly_density=density,
        monthly_wafer=wafer,
        securement_rate=_securement(),
        product_volume=_volume(edp=False),
        slot_volume=_volume(edp=True),
        display_order=None,
        included_processes=["P-A", "P-B"],
    )


def test_the_bottleneck_is_the_lowest_process_inside_the_saved_filter() -> None:
    summary = _summary()

    bottlenecks = [month for month in summary.bottlenecks if month is not None]
    # 여섯 달 모두 필터 안 공정이 있어 B/N 이 빈 달은 없다.
    assert len(bottlenecks) == len(summary.bottlenecks)
    processes = [month.process for month in bottlenecks]
    # P-LOW 는 필터 밖이라 한 번도 B/N 이 되지 않는다. P-B 가 내려와 P-A 아래로 지나간다.
    assert "P-LOW" not in processes
    assert processes[0] == "P-A" and processes[-1] == "P-B"
    first = bottlenecks[0]
    assert first.rate == pytest.approx(0.94)
    assert (first.required, first.available, first.short_units) == (34.0, 32.0, 2)
    # 소요보다 가용이 많으면 부족 대수는 0 이다.
    assert bottlenecks[-1].short_units == 0


def test_monthly_values_and_product_mix_follow_the_six_months() -> None:
    summary = _summary()

    assert summary.labels == ("26.10", "26.11", "26.12", "27.01", "27.02", "27.03")
    assert summary.density[0] == pytest.approx(14.97)
    assert summary.wafer[0] == pytest.approx(211000.0)
    # 색 칸은 EDP 포함 수량으로 정하고, 그리는 비중은 EDP 를 뺀 수량이다(HOME 과 같은 짝).
    assert summary.products[: summary.products.index("PROD-B") + 1] == ("PROD-A", "PROD-B")
    for month in summary.mix:
        assert sum(share for _, share in month) == pytest.approx(1.0)
        named = {summary.products[index]: share for index, share in month}
        assert named["PROD-A"] == pytest.approx(120 / 180)
        assert "PROD-EDP" not in named


def test_a_month_without_any_value_stays_empty_instead_of_zero() -> None:
    density = pd.DataFrame({"생산계획년월": MONTHS[:5], "부하량": [1.0] * 5})
    summary = build_official_summary(
        months=MONTHS,
        monthly_density=density,
        monthly_wafer=pd.DataFrame({"생산계획년월": MONTHS, "Wafer 부하량": [1.0] * 6}),
        securement_rate=_securement().loc[lambda frame: frame["생산계획년월"] != MONTHS[-1]],
        product_volume=_volume(edp=False),
        slot_volume=_volume(edp=False),
        display_order=None,
        included_processes=["P-A", "P-B"],
    )

    assert summary.density[-1] is None
    assert summary.bottlenecks[-1] is None


def test_the_payload_is_rounded_theme_independent_and_serializable() -> None:
    """같은 요약이면 늘 같은 값이어야 Streamlit 이 다시 보내지 않는다. 색은 다크 팔레트 고정이다."""
    summary = _summary()
    payload = summary_payload(
        summary,
        release_name="공식 v4",
        scenario_name="DEMO",
        thresholds=SecurementThresholds(1.095, 0.995),
        process_label=lambda process: f"<{process}>",
    )

    assert json.loads(json.dumps(payload)) == payload
    assert payload["available"] is True
    assert payload["period"] == "26.10–27.03" and payload["count"] == 6
    assert payload["wafer"][0] == pytest.approx(211.0)
    # 숫자는 기준선 자리라 정확하고, 이름표 글자는 사사오입한 정수 퍼센트다. 달마다 하나씩이다.
    assert payload["secure"] == [109.5] * 6 and payload["warning"] == [99.5] * 6
    assert payload["secure_label"] == ["110%"] * 6 and payload["warning_label"] == ["100%"] * 6
    first = payload["bn"][0]
    assert first == {
        "process": "<P-A>",
        "rate": 94.0,
        "need": 34.0,
        "have": 32.0,
        "short": 2,
        "status": "shortage",
    }
    dark = tokens.palette_value("dark", "PRODUCT_SHARE_COLORS")
    assert payload["products"][0]["color"] == dark[0]
    assert payload == summary_payload(
        summary,
        release_name="공식 v4",
        scenario_name="DEMO",
        thresholds=SecurementThresholds(1.095, 0.995),
        process_label=lambda process: f"<{process}>",
    )


# --------------------------------------------------------------- HOME 을 무겁게 하지 않는다
# 주 업무 화면은 HOME 이다(2026-10-03 사용자 결정). 요약은 회차마다 DB 를 보지 않고, 세션이
# 바뀌어도 다시 만들지 않으며, 데이터 오류로 실패했으면 회차마다 다시 계산하지 않는다.


class _Repo:
    def __init__(self, release_id: str) -> None:
        self.calls = 0
        self.release = SimpleNamespace(
            official_release_id=release_id, scenario_name="DEMO", revision_id="rev", release_no=1
        )

    def latest_official_release(self) -> SimpleNamespace:
        self.calls += 1
        return self.release


@pytest.fixture
def summary_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[SimpleNamespace]:
    from capa_simulation.components import intro_summary
    from capa_simulation.services import simulation_cache

    simulation_cache.get_intro_summary_payload.clear()
    simulation_cache.shared_intro_toggle_store.clear()
    env = SimpleNamespace(
        session={},
        now=1000.0,
        repo=_Repo("rel-1"),
        builds=[],
        fail=None,
        module=intro_summary,
        thresholds=SecurementThresholds(1.095, 0.995),
        versions={"advance": 0, "shipment": 0, "comparison": 0},
        profile_reads=0,
        parts=[],
        part_fail=None,
        comparison_target=("S-CMP", "R-CMP"),
    )

    def fake_profiles(path: str) -> SimpleNamespace:
        env.profile_reads += 1
        return SimpleNamespace(
            advance=SimpleNamespace(version=env.versions["advance"]),
            shipment=SimpleNamespace(version=env.versions["shipment"]),
            comparison=SimpleNamespace(
                version=env.versions["comparison"],
                scenario_id=env.comparison_target[0],
                revision_id=env.comparison_target[1],
            ),
        )

    def fake_build(
        path: str, release: SimpleNamespace, thresholds: SecurementThresholds
    ) -> dict[str, object]:
        env.builds.append(release.official_release_id)
        if env.fail is not None:
            raise env.fail
        # 토글 몫이 쓸 재료(`_context`)는 브라우저로 가기 전에 떼어진다.
        return {
            "available": True,
            "release": release.official_release_id,
            "_context": {"months": [202610]},
        }

    def fake_part(name: str) -> Callable[..., dict[str, object]]:
        def build(*args: object) -> dict[str, object]:
            env.parts.append(name)
            if env.part_fail is not None:
                raise env.part_fail
            return {"available": True, "part": name, "version": env.versions[name]}

        return build

    monkeypatch.setattr(st, "session_state", env.session)
    monkeypatch.setattr(intro_summary, "time", SimpleNamespace(monotonic=lambda: env.now))
    monkeypatch.setattr(intro_summary, "get_scenario_repository", lambda path: env.repo)
    monkeypatch.setattr(
        intro_summary, "load_global_display_order", lambda path: SimpleNamespace(version=1)
    )
    monkeypatch.setattr(
        intro_summary,
        "get_process_labels",
        lambda: SimpleNamespace(version=0, format_func=lambda: str),
    )
    monkeypatch.setattr(
        intro_summary,
        "load_global_securement_threshold",
        lambda path: SimpleNamespace(thresholds=env.thresholds),
    )
    monkeypatch.setattr(intro_summary, "load_toggle_profiles", fake_profiles)
    monkeypatch.setattr(intro_summary, "_build", fake_build)
    for name in ("advance", "shipment", "comparison"):
        monkeypatch.setattr(intro_summary, f"_{name}_part", fake_part(name))
    yield env
    simulation_cache.get_intro_summary_payload.clear()
    simulation_cache.shared_intro_toggle_store.clear()


def test_home_reruns_reuse_the_session_value_without_touching_the_db(
    summary_env: SimpleNamespace,
) -> None:
    data = summary_env.module.official_summary_data
    first = data("db")
    summary_env.now += 10
    assert data("db") == first
    # 30초 안의 회차는 DB(공식버전 조회)도 서버 캐시도 보지 않는다.
    assert summary_env.repo.calls == 1 and summary_env.builds == ["rel-1"]
    summary_env.now += summary_env.module.RECHECK_SECONDS
    assert data("db") == first
    # 다시 확인해도 같은 공식버전이면 서버 캐시에서 꺼낸다 — 다시 만들지 않는다.
    assert summary_env.repo.calls == 2 and summary_env.builds == ["rel-1"]


def test_toggle_profiles_are_read_only_when_the_official_version_is_checked(
    summary_env: SimpleNamespace,
) -> None:
    """토글 셋의 공용 프로필(선행 B/O·선행 입고·비교 대상)은 30초에 한 번 하는 확인 때만 읽는다 —
    HOME 회차는 세션 값만 보낸다."""
    data = summary_env.module.official_summary_data
    data("db")
    summary_env.now += 10
    data("db")
    assert summary_env.profile_reads == 1
    summary_env.now += summary_env.module.RECHECK_SECONDS
    data("db")
    assert summary_env.profile_reads == 2 and summary_env.builds == ["rel-1"]


def test_the_summary_sends_the_toggle_parts_but_not_their_ingredients(
    summary_env: SimpleNamespace,
) -> None:
    sent = summary_env.module.official_summary_data("db")
    assert "_context" not in sent
    assert {name: part["part"] for name, part in sent["toggles"].items()} == {
        "advance": "advance",
        "shipment": "shipment",
        "comparison": "comparison",
    }
    # 서버에 처음 만드는 요약(입장 화면이 로딩을 덮는 때)은 GAP 도 미루지 않는다.
    assert summary_env.parts == ["advance", "shipment", "comparison"]


@pytest.mark.parametrize("profile", ["advance", "shipment"])
def test_a_saved_toggle_profile_rebuilds_only_its_own_part(
    summary_env: SimpleNamespace, profile: str
) -> None:
    """토글 몫은 요약과 따로 서버에 둔다 — 선행 B/O·선행 입고를 저장해도 요약과 다른 몫은 다시
    만들지 않는다(그 회차에 HOME 보다 먼저 리비전 스냅샷을 다시 풀던 것)."""
    data = summary_env.module.official_summary_data
    data("db")
    summary_env.parts.clear()
    summary_env.versions[profile] += 1
    summary_env.module.forget_intro_summary_check()
    sent = data("db")
    assert summary_env.builds == ["rel-1"]
    assert summary_env.parts == [profile]
    assert sent["toggles"][profile]["version"] == 1


def test_a_changed_comparison_is_built_after_the_page_and_sent_on_the_next_run(
    summary_env: SimpleNamespace,
) -> None:
    """비교 대상을 바꾼 회차에는 GAP 을 HOME 앞에서 만들지 않는다 — 「준비 중」으로 보내고
    `warm_intro_summary`(페이지 뒤)가 만들어 다음 회차에 싣는다. 켜 둔 GAP 은 브라우저가 지킨다."""
    module = summary_env.module
    data = module.official_summary_data
    data("db")
    summary_env.parts.clear()
    summary_env.versions["comparison"] += 1
    module.forget_intro_summary_check()
    sent = data("db")
    assert summary_env.parts == []
    assert sent["toggles"]["comparison"] == {
        "available": False,
        "pending": True,
        "reason": module.COMPARISON_PENDING,
    }
    assert sent["toggles"]["advance"]["available"] is True
    module.warm_intro_summary("db")
    assert summary_env.parts == ["comparison"]
    summary_env.now += 1  # 다음 회차 — 다시 확인하지 않고 세션 값을 보낸다
    calls = summary_env.repo.calls
    after = data("db")
    assert after["toggles"]["comparison"]["version"] == 1
    assert summary_env.repo.calls == calls and summary_env.builds == ["rel-1"]


@pytest.mark.parametrize("target", [(None, None), ("S-OFFICIAL", "rev")])
def test_a_comparison_that_needs_no_plan_is_answered_at_once(
    summary_env: SimpleNamespace, target: tuple[str | None, str | None]
) -> None:
    """비교 대상을 비우거나 공식버전 자신으로 두면 까닭만 내면 된다 — 미루지 않는다."""
    module = summary_env.module
    module.official_summary_data("db")
    summary_env.parts.clear()
    summary_env.comparison_target = target
    summary_env.versions["comparison"] += 1
    module.forget_intro_summary_check()
    sent = module.official_summary_data("db")
    assert summary_env.parts == ["comparison"]
    assert "pending" not in sent["toggles"]["comparison"]
    assert summary_env.session[module._SESSION_KEY]["pending"] is False


def test_a_session_that_has_its_summary_defers_the_gap_even_on_a_rebuild(
    summary_env: SimpleNamespace,
) -> None:
    """요약을 다시 만드는 회차(판정 기준·표시순서 저장, 공식버전 교체 뒤)라도 이 세션이 요약을 이미
    받았으면 GAP 은 페이지 뒤에서 만든다 — 「처음 받는 세션(입장 로딩)」만 페이지 앞에서 함께
    만든다."""
    module = summary_env.module
    module.official_summary_data("db")
    summary_env.parts.clear()
    summary_env.thresholds = SecurementThresholds(1.195, 0.995)
    summary_env.versions["comparison"] += 1
    module.forget_intro_summary_check()
    sent = module.official_summary_data("db")
    assert summary_env.builds == ["rel-1", "rel-1"]
    assert (
        sent["toggles"]["comparison"]["pending"] is True and "comparison" not in summary_env.parts
    )
    # 새 탭(이 세션이 아직 요약을 받은 적 없음)은 입장 화면이 덮으므로 GAP 도 함께 만든다.
    summary_env.session.clear()
    fresh = module.official_summary_data("db")
    assert fresh["toggles"]["comparison"]["version"] == 1


def test_a_refresh_request_rechecks_a_pending_summary_at_once(
    summary_env: SimpleNamespace,
) -> None:
    """Summary 를 열 때의 다시 받아 오기 — 「준비 중」을 든 세션은 그 회차에 곧바로 다시 확인해,
    그 사이(다른 세션의 페이지 뒤에서) 만들어진 값을 싣는다. 평소에는 아무것도 하지 않는다."""
    module = summary_env.module
    module.official_summary_data("db")
    summary_env.versions["comparison"] += 1
    module.forget_intro_summary_check()
    assert module.official_summary_data("db")["toggles"]["comparison"]["pending"] is True
    module._look_up("db", defer=False)  # 다른 세션의 페이지 뒤 데우기
    summary_env.now += 1
    assert module.official_summary_data("db")["toggles"]["comparison"].get("pending") is True
    module._refresh_requested()
    assert module.official_summary_data("db")["toggles"]["comparison"]["version"] == 1
    calls = summary_env.repo.calls
    module._refresh_requested()  # 「준비 중」이 없으면 다시 확인하지 않는다
    module.official_summary_data("db")
    assert summary_env.repo.calls == calls


def test_a_failed_warm_waits_one_recheck_period(summary_env: SimpleNamespace) -> None:
    """페이지 뒤 데우기가 또 일시적 실패면 그 확인 주기 동안은 다시 하지 않는다(회차마다 무거운
    재시도를 막는다). 성공하면 표지를 남기지 않는다."""
    import duckdb

    module = summary_env.module
    summary_env.part_fail = duckdb.IOException("잠김")
    module.official_summary_data("db")
    module.warm_intro_summary("db")
    tries = summary_env.parts.count("comparison")
    module.warm_intro_summary("db")
    assert summary_env.parts.count("comparison") == tries
    summary_env.now += module.RECHECK_SECONDS
    summary_env.part_fail = None
    module.warm_intro_summary("db")
    assert module.official_summary_data("db")["toggles"]["comparison"]["available"] is True


def test_warming_does_nothing_when_nothing_is_pending(summary_env: SimpleNamespace) -> None:
    module = summary_env.module
    module.official_summary_data("db")
    calls = summary_env.repo.calls
    module.warm_intro_summary("db")
    assert summary_env.repo.calls == calls


def test_a_transient_failure_in_a_part_stays_pending_and_is_not_kept(
    summary_env: SimpleNamespace,
) -> None:
    """DB 잠금 같은 일시적 실패로 만든 토글 몫은 서버에 남기지 않는다 — 「준비 중」으로 두고 페이지
    뒤에서 다시 해 본다(같은 확인 주기 안에서는 한 번만)."""
    import duckdb

    module = summary_env.module
    summary_env.part_fail = duckdb.IOException("잠김")
    sent = module.official_summary_data("db")
    assert all(part.get("pending") for part in sent["toggles"].values())
    summary_env.part_fail = None
    module.warm_intro_summary("db")
    module.warm_intro_summary("db")
    assert summary_env.parts.count("advance") == 2
    summary_env.now += 1
    assert module.official_summary_data("db")["toggles"]["advance"]["available"] is True


def test_a_new_session_takes_the_summary_from_the_server_cache(
    summary_env: SimpleNamespace,
) -> None:
    data = summary_env.module.official_summary_data
    first = data("db")
    summary_env.session.clear()  # 새 탭·F5·테마 전환
    assert data("db") == first
    assert summary_env.builds == ["rel-1"]


def test_publishing_an_official_version_rechecks_at_once(summary_env: SimpleNamespace) -> None:
    data = summary_env.module.official_summary_data
    data("db")
    summary_env.repo = _Repo("rel-2")
    assert data("db")["release"] == "rel-1"  # 평소에는 30초에 한 번 본다
    summary_env.module.forget_intro_summary_check()
    assert data("db")["release"] == "rel-2"


def test_changing_the_shared_thresholds_rebuilds_the_summary(summary_env: SimpleNamespace) -> None:
    """판정 기준은 공용 프로필이다. 기준(내용 지문)이 바뀌면 같은 공식버전도 새로 만든다."""
    data = summary_env.module.official_summary_data
    data("db")
    summary_env.thresholds = SecurementThresholds(1.095, 0.995, monthly=((202701, 1.195, None),))
    summary_env.module.forget_intro_summary_check()
    data("db")
    assert summary_env.builds == ["rel-1", "rel-1"]


def test_data_errors_are_kept_but_transient_errors_are_retried(
    summary_env: SimpleNamespace,
) -> None:
    import duckdb

    data = summary_env.module.official_summary_data
    summary_env.fail = ValueError("기준정보 오류")
    assert data("db")["available"] is False
    summary_env.session.clear()
    assert data("db")["available"] is False
    # 데이터 오류는 서버 캐시에 남아 다른 세션도 다시 계산하지 않는다.
    assert summary_env.builds == ["rel-1"]

    summary_env.repo = _Repo("rel-3")
    summary_env.fail = duckdb.IOException("잠김")
    summary_env.session.clear()
    assert data("db")["available"] is False
    summary_env.now += summary_env.module.RECHECK_SECONDS
    summary_env.fail = None
    # DB 잠금은 남기지 않는다 — 다음 확인 때 다시 만들어 성공한다.
    assert data("db")["release"] == "rel-3"
    assert summary_env.builds == ["rel-1", "rel-3", "rel-3"]


def test_a_transient_failure_keeps_the_summary_already_held(summary_env: SimpleNamespace) -> None:
    """30초마다 하는 확인이 DB 잠금으로 실패해도 멀쩡한 요약을 지우지 않는다.

    지우면 사이드바 `S.PKG CAPA` 라벨이 Summary 를 열지 못한다.
    """
    import duckdb

    data = summary_env.module.official_summary_data
    good = data("db")
    summary_env.now += summary_env.module.RECHECK_SECONDS

    def locked() -> None:
        raise duckdb.IOException("잠김")

    summary_env.repo.latest_official_release = locked
    assert data("db") == good
    # 다음 확인도 30초 뒤다 — 잠긴 동안 HOME 회차가 DB 를 붙잡지 않는다.
    summary_env.now += 1
    assert data("db") == good


def test_other_always_failing_errors_are_kept_too(summary_env: SimpleNamespace) -> None:
    """DB·파일·메모리가 아닌 실패는 다시 해도 같은 결과라 서버 캐시에 남긴다."""
    data = summary_env.module.official_summary_data
    summary_env.fail = AttributeError("데이터 모양")
    assert data("db")["available"] is False
    summary_env.session.clear()
    assert data("db")["available"] is False
    assert summary_env.builds == ["rel-1"]


def test_the_payload_judges_and_draws_each_month_by_its_own_threshold() -> None:
    """월별 예외가 있는 달은 막대 색(상태)과 기준선 값·이름표가 그 달 기준을 따른다."""
    summary = _summary()
    july = summary.months[3]
    payload = summary_payload(
        summary,
        release_name="공식 v4",
        scenario_name="DEMO",
        thresholds=SecurementThresholds(1.095, 0.995, monthly=((july, 1.195, None),)),
        process_label=lambda process: process,
    )

    assert payload["secure"][3] == 119.5 and payload["secure_label"][3] == "120%"
    assert payload["secure"][2] == 109.5 and payload["warning"][3] == 99.5
    assert len(payload["secure"]) == len(payload["months"])


def test_a_failure_after_reading_the_official_version_keeps_its_identity(
    summary_env: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """공식버전을 읽은 뒤 요약 준비가 실패해도 그 공식버전은 세션에 남는다.

    남지 않으면 머리 띠는 「저장된 리비전」이라 적고 사이드바 배지는 「공식 vN」이라 적는다.
    """
    module = summary_env.module

    def broken(path: str) -> SimpleNamespace:
        raise RuntimeError("표시순서 모양")

    monkeypatch.setattr(module, "load_global_display_order", broken)
    assert module.official_summary_data("db")["available"] is False
    assert module.latest_official_revision() == ("rev", 1)
