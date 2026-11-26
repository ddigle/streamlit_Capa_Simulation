# Purpose: 개발자 전용 잠금과 표시명·표시순서·원천 품질·부대공정·공정 그룹·접속 기록·부하 예외·공지
# 탭, 위의 서버 점검·BDQ 자동 로그인·통합인증 점검·접속 명단과 탭 줄 끝 「이 등급으로 보기」.

from __future__ import annotations

import pandas as pd
import streamlit as st

from capa_simulation.components.access_list_admin import (
    render_access_list_admin,
    render_grade_preview,
)
from capa_simulation.components.audit_log_view import render_audit_tab
from capa_simulation.components.bdq_login_admin import render_bdq_login_admin
from capa_simulation.components.container_start_check import render_container_start_check
from capa_simulation.components.data_error_mark import render_data_error
from capa_simulation.components.display_order_management import (
    render_display_order_management,
)
from capa_simulation.components.extra_process_admin import render_extra_process_admin
from capa_simulation.components.module_status import render_module_status
from capa_simulation.components.notice_admin import render_notice_admin
from capa_simulation.components.object_sync_status import render_object_sync_status
from capa_simulation.components.page_guide import render_page_guide
from capa_simulation.components.page_header import render_page_header
from capa_simulation.components.page_link import render_page_link
from capa_simulation.components.process_group_editor import (
    ADMIN_SAVE_HELP,
    AdminTab,
    render_process_group_editor,
)
from capa_simulation.components.process_labels import get_process_labels
from capa_simulation.components.process_rename_management import (
    render_process_rename_management,
)
from capa_simulation.components.route_load_exception_admin import (
    render_route_load_exception_admin,
)
from capa_simulation.components.source_quality import render_source_quality
from capa_simulation.components.sso_identity import (
    ADMIN_ONLY_NOTICE,
    HOME_LINK_LABEL,
    admin_area_locked,
    viewer_can,
    viewer_can_audit,
)
from capa_simulation.components.sso_status import (
    render_off_in_production_alert,
    render_sso_status,
)
from capa_simulation.components.state_alerts import open_tab_name, tab_name
from capa_simulation.components.tab_state import stateful_tabs, tab_is_hidden
from capa_simulation.io.reference_cache import get_effective_reference_tables
from capa_simulation.navigation import (
    ADMIN_AREA_LOG_TAB,
    ADMIN_AREA_NOTICE_TAB,
    ADMIN_AREA_ROUTE_EXCEPTION_TAB,
    ADMIN_AREA_TAB_KEY,
    ADMIN_AREA_TABS,
    HOME,
    module_scan,
)
from capa_simulation.page_bootstrap import BOOTSTRAP_ERRORS, bootstrap_error_message
from capa_simulation.persistence.cache import get_scenario_repository
from capa_simulation.scenario_activation import active_persisted_scenario_id
from capa_simulation.services.display_order_scopes import PAGE_CALCULATION, TAB_SECUREMENT
from capa_simulation.services.simulation_cache import (
    display_order_digest,
    get_display_ordered_values,
    get_prepared_display_order,
)
from capa_simulation.settings import DUCKDB_PATH

# 탭을 더할 자리다. 이름을 여기에 모아 두고 아래에서 같은 순서로 그린다. 탭은 `stateful_tabs` 라
# 열린 탭을 서버가 안다 — 위젯이 없는 「원천 품질」 은 닫혀 있으면 건너뛴다. 입력 위젯이 든 탭은
# 닫혀 있어도 늘 그린다 — 건너뛰면 Streamlit 이 그 위젯의 값을 버린다. 계산 알림은 이 화면에 두지
# 않는다 — 리비전마다 계산에서 빠진 행은 시나리오 관리 › 목록 관리 「점검」 칸이 센다 (2026-11-11
# 입력 점검 보드 q7). 라벨은 사이드바도 읽어 `navigation` 한 곳에 둔다. 넷째 「부대공정」 은 늘 서는
# 탭이고(위젯이 단추 · 내려받기 · 확인 칸뿐이라 닫혀 있으면 건너뜀) 쓰는 단추는 C-DEP 의
# 개발자에게만 열린다. 다섯째 「공정 그룹」 은 늘 서는 입력 탭이다(편집 표). 여섯째 「접속 · 작업
# 기록」 은 감사 기록이 켜진 서버의 개발자 회차에만 선다.
# 그 뒤 「부하 예외」 는 늘 서는 입력 탭이라(공정 고르기 칸) 닫혀 있어도 그리고 저장 단추는
# 「부대공정」 과 같은 판정으로 C-DEP 의 개발자에게만 열린다. 맨 끝 「공지」 는 늘 서는 입력
# 탭이다(2026-11-17 공지 보드 답 decided 2 — DB 를 쓰지 않는다).
TAB_NAMES = ADMIN_AREA_TABS
LOG_TAB = ADMIN_AREA_LOG_TAB
ROUTE_EXCEPTION_TAB = ADMIN_AREA_ROUTE_EXCEPTION_TAB
NOTICE_TAB = ADMIN_AREA_NOTICE_TAB
TABS_KEY = ADMIN_AREA_TAB_KEY
# 안쪽 탭 묶음을 담는 칸 — 그 안 맨 앞에 「모듈 상태」 팝오버 단추를 두면 탭 줄 오른쪽 끝에 선다
# (`module_status.tools_style`).
TABS_BOX_KEY = "admin_area_tabs_box"

render_page_header("Admin Area")
# 운영인데 통합인증이 꺼진 서버(`AD-02`)는 개발자 신원이 없어 아래 잠금이 모두를 멈춘다 — 그
# 알림만은 잠금 앞에서 내 잠긴 회차에도 Alarm 으로 닿게 한다.
render_off_in_production_alert()
# 운영 서버에서 화면 등급이 개발자가 아니면(「이 등급으로 보기」 동안 포함) 메뉴가 없고(`app.py`),
# 주소로 열어도 여기서 「개발자만 여는 화면입니다」 + 「HOME 으로」 뒤 멈춘다 — 판정은
# `sso_identity.admin_area_locked` 하나다(설계 규칙 UI-INP-07 예외 — 등급 밖 기능은 숨김).
if admin_area_locked():
    st.warning(ADMIN_ONLY_NOTICE, icon=":material/lock:")
    render_page_link(HOME.path, label=HOME_LINK_LABEL, icon=":material/home:")
    st.stop()
render_page_guide("admin_area", title="Admin Area")
# C-DEP CD 서버에는 셸도 로그도 없어 시작 스크립트의 결과를 여기서 읽는다. 결과 파일이 없는
# 개발·사내 PC 에서는 아무것도 그리지 않는다(DB 를 열지 않고 작은 JSON 하나만 읽는다).
render_container_start_check()
# BigDataQuery 자동 로그인 계정 넣기 · 지우기 — `managed` + 키(`CAPA_BDQ_SECRET_KEY`) 서버의 개발자
# 회차에만 선다(그 밖에는 아무것도 그리지 않는다). 예비 「토큰 넣기」 는 바로 위 펼침 안에 그대로다.
render_bdq_login_admin()
# 정본 버킷 동기화 — CI/CD 를 누르기 전에 보는 자리. `managed` 서버에만 선다(개발·사내 PC 그대로).
render_object_sync_status()
# 통합인증의 설정 판정 · 서명 인증서 · 최근 사건. 꺼짐이고 운영(`APP_ENV=prod`)이 아니면 아무것도
# 그리지 않는다(개발·사내 PC 화면 그대로). 값은 싣지 않는다.
render_sso_status()
# S3 접속 명단 · 등급 파일 편집. 통합인증 · S3 명단이 켜진 서버의 개발자 회차에만 선다 — 그 밖에는
# 아무것도 그리지 않는다(개발·사내 PC 화면 그대로). DB 를 열지 않는다.
render_access_list_admin()
# 모듈(`modules/<id>/`)이 있을 때만 켜짐·꺼짐·실패 수를 단추 글로 단 팝오버가 안쪽 탭 줄 오른쪽 끝에
# 서고, 까닭·마지막 오류 표는 그 안이다 — 탭 위에 줄을 세우지 않는다(2026-11-10 보드 Q-6, 설계 규칙
# UI-LAY-13). 사외와 `CAPA_MODULES_ROOT=off` 에서는 아무것도 그리지 않는다(DB 를 열지 않는다). 탭을
# 담을 칸을 DB 를 열기 전에 세워 그 안에 먼저 그린다 — DB 를 못 열어 멈추는 회차에도 선다(탭이
# 없으면 흐름 안 한 줄).
tabs_box = st.container(key=TABS_BOX_KEY)
with tabs_box:
    render_module_status(box_key=TABS_BOX_KEY)
    # 「이 등급으로 보기」 — 운영 + 통합인증 켜짐의 실제 개발자에게만 탭 줄 오른쪽 끝(모듈 상태
    # 단추가
    # 있으면 그 왼쪽) 팝오버로 선다(설계 규칙 UI-LAY-13). 그 밖에는 아무것도 그리지 않는다.
    scanned = module_scan()
    render_grade_preview(
        box_key=TABS_BOX_KEY,
        beside_module_status=bool(scanned.records or scanned.root_error),
    )
    # 탭 묶음은 DB 를 열기 **앞**이다 — DB 를 못 열어도 DB 를 쓰지 않는 기록 탭은 열린다(DB
    # 탭 안에만 「데이터 Error」 마크). 명단에서 개발자 등급이 바뀌면 세션 중에도 라벨 목록이
    # 바뀐다 — 세션의 탭 값이 라벨 밖이면 첫 라벨로 새로 적는다(pop 하지 않는다 — AGENTS 9장).
    shows_log = viewer_can_audit()
    tab_labels = (*TAB_NAMES, *((LOG_TAB,) if shows_log else ()), ROUTE_EXCEPTION_TAB, NOTICE_TAB)
    if st.session_state.get(TABS_KEY, tab_labels[0]) not in tab_labels:
        st.session_state[TABS_KEY] = tab_labels[0]
    opened_tabs = stateful_tabs(tab_labels, key=TABS_KEY)
(
    process_rename_tab,
    display_order_tab,
    source_quality_tab,
    extra_process_tab,
    process_group_tab,
) = opened_tabs[: len(TAB_NAMES)]
route_exception_tab = opened_tabs[-2]

if shows_log:
    log_tab = opened_tabs[len(TAB_NAMES)]
    with log_tab:
        # 닫혀 있으면 읽지 않는다 — 기록 조건 카드도 이 탭이 열린 회차에만 선다.
        if not tab_is_hidden(log_tab):
            render_audit_tab()

# 공지 — DB 를 쓰지 않는 입력 탭이라 DB 를 열기 앞에서 늘 그린다(DB 를 못 열어 멈추는 회차에도
# 선다). 보내기 · 거두기는 그 순간 실제 개발자 판정을 다시 본다(`components/notice_admin.py`).
with opened_tabs[-1]:
    render_notice_admin()

try:
    database_path = str(DUCKDB_PATH.resolve())
    repository = get_scenario_repository(database_path)
except BOOTSTRAP_ERRORS as exc:
    message = bootstrap_error_message(exc)
    # 마크는 DB 를 쓰는 탭 가운데 열린 탭 안에만 선다(같은 글의 알림은 한 번 — 기록 탭이
    # 열린 회차에는 서지 않고, DB 탭을 여는 회차에 선다).
    for database_tab, label in zip(
        (
            process_rename_tab,
            display_order_tab,
            source_quality_tab,
            extra_process_tab,
            process_group_tab,
            route_exception_tab,
        ),
        (*TAB_NAMES, ROUTE_EXCEPTION_TAB),
        strict=True,
    ):
        if tab_is_hidden(database_tab):
            continue
        with database_tab:
            render_data_error(
                message,
                code="AD-07",
                tab=tab_name(label),
                text="Admin Area 를 준비하지 못했습니다(시뮬레이션 DB)",
            )
    st.stop()

# 공정 목록은 안내·편집 보조일 뿐이라 활성 시나리오가 없어도 화면을 멈추지 않는다.
# 공용 표시명 저장 자체는 시나리오와 무관하다. 시나리오 `RQ_MODULE` 공정만 본다 — 설비 마스터의
# 공정소분류까지 보려면 이 화면이 설비 DB 를 읽어야 해서 넓히지 않는다(겹침 경고 문구에 적는다).
try:
    reference_tables = get_effective_reference_tables()
    available_processes = sorted(
        reference_tables["RQ_MODULE"]["공정"]
        .astype("string")
        .str.strip()
        .dropna()
        .unique()
        .tolist()
    )
    # 「부하 예외」 의 선택지는 소요기준 원본 공정명이다 — 선언은 원본 표기로 저장하고 견줌은 계산
    # 쪽 견줌 키가 한다(앞뒤 공백을 떼지 않는다).
    requirement_processes = sorted(
        reference_tables["RQ_REQB"]["공정"].dropna().astype(str).unique().tolist()
    )
except BOOTSTRAP_ERRORS:
    available_processes = []
    requirement_processes = []
# 「공정 그룹」 탭의 줄 차례만 HOME 설정 카드 · 공정 필터와 같은 공용 표시순서(산출 결과 › 확보율
# 범위)다 — 규칙 밖 공정은 이름 차례로 뒤에 선다. Proc Rename · 부하 예외 목록은 원본 이름 차례
# 그대로다. 준비 · 정렬은 표시순서 지문 키 캐시라, 편집 표라 늘 그리는 닫힌 탭 회차도 캐시만
# 꺼낸다(줄 차례가 열린 회차와 같아야 표 key 의 줄 지문이 같다). 잘못 저장된 규칙이면 이름 차례로
# 물러선다 — 겹친 분류값은 「표시순서 관리」 탭의 `AD-05` 가 알린다.
group_processes = available_processes
if available_processes:
    try:
        display_order = reference_tables["RQ_DISPLAY_ORDER"]
        group_processes = get_display_ordered_values(
            pd.DataFrame({"공정": available_processes}),
            display_order_digest(display_order),
            PAGE_CALCULATION,
            TAB_SECUREMENT,
            _display_order=get_prepared_display_order(display_order),
        )
    except BOOTSTRAP_ERRORS:
        group_processes = available_processes

# 탭 안 상태 알림(Proc Rename 표시명 겹침 `AD-06` · 표시순서 분류값 겹침 `AD-05`)은 그 탭이 열린
# 회차에만 낸다(닫힌 탭이면 None — `open_tab_name`). 「그 화면으로」 가 그 탭을 연다.
with process_rename_tab:
    render_process_rename_management(
        repository,
        available_processes,
        alert_tab=open_tab_name(process_rename_tab, TAB_NAMES[0]),
    )
with display_order_tab:
    render_display_order_management(
        repository, alert_tab=open_tab_name(display_order_tab, TAB_NAMES[1])
    )
with source_quality_tab:
    # 위젯 없는 읽기 전용 표라 닫혀 있으면 건너뛴다. 원천 읽기는 캐시가 없고 앞 두 탭은 캐시만
    # 읽어서, 이 탭과 「부대공정」 이 열린 회차에만 Admin 회차가 DB 를 읽는다 — 닫힌 탭이 회차마다
    # DuckDB 인스턴스를 열고 닫게 하지 않는다.
    if not tab_is_hidden(source_quality_tab):
        # 원천이 없는 시나리오(복제본 등)가 정상이다. 그때 화면을 멈추지 않는다.
        scenario_id = active_persisted_scenario_id()
        if scenario_id is None:
            st.caption("활성 시나리오가 없습니다.")
        else:
            try:
                source_profile = repository.load_source_profile(scenario_id)
                source_rows = repository.load_source_row_count(scenario_id)
            except BOOTSTRAP_ERRORS as exc:
                render_data_error(
                    bootstrap_error_message(exc),
                    code="AD-07",
                    tab=tab_name(TAB_NAMES[2]),
                    text="원천 품질을 읽지 못했습니다",
                )
            else:
                render_source_quality(source_profile, source_rows)
with extra_process_tab:
    # 판 이력 · 상태 줄 · 양식 내려받기 · 끄기 / 다시 켜기 · 받은 판의 미리보기. 위젯은 단추 ·
    # 내려받기 · 확인 칸뿐이라 버릴 값이 없어 닫혀 있으면 건너뛴다 — 접속 명단 표 · Proc Rename 처럼
    # 회차가 잦은 조작마다 판 이력을 읽어 DuckDB 를 열지 않게. 받은 판 · 미리보기는 세션 칸에
    # 남는다.
    if not tab_is_hidden(extra_process_tab):
        render_extra_process_admin(
            repository, alert_tab=open_tab_name(extra_process_tab, TAB_NAMES[3])
        )
with process_group_tab:
    # HOME 공정 필터 그룹 단추가 쓰는 공용 공정 그룹 — HOME 설정 카드와 같은 부품에 활성
    # 시나리오의 모든 공정(`RQ_MODULE` — Proc Rename 과 같은 목록, 차례는 공용 표시순서)을 줄로
    # 넘겨 조회기간에 확보율이 없는 공정에도 그룹을 준다. 편집 표가 있어 닫혀 있어도 그린다(닫힌
    # 회차는 공용 프로필 캐시만 읽는다). 저장 벽은 HOME 설정과 같은 `home.settings` 다(쓰기 하나에
    # 벽 하나).
    render_process_group_editor(
        process_options=group_processes,
        process_labels=get_process_labels(),
        database_path=database_path,
        read_only=not viewer_can("home.settings"),
        save_help=ADMIN_SAVE_HELP,
        admin=AdminTab(tab_name(TAB_NAMES[4]), not tab_is_hidden(process_group_tab)),
    )
with route_exception_tab:
    # 공정별 부하 산출 예외 선언 — 고르기 칸이 있어 닫혀 있어도 그린다(닫힌 회차는 공용 프로필
    # 캐시만 읽고 판 이력 표는 열린 회차에만 읽는다).
    render_route_load_exception_admin(
        repository,
        requirement_processes,
        database_path=database_path,
        alert_tab=open_tab_name(route_exception_tab, ROUTE_EXCEPTION_TAB),
    )
