# 검수용 합성 샘플

화면 검수와 따라하기 가이드 촬영에 쓰는 **이야기가 든 큰 합성 샘플**이다. 내장 시드(`builtin_seed` — 제품 2 · 공정 3)는 확보율이
수만 % 로 나와 그림으로 쓸 수 없고, 로컬 개발 DB 는 사람마다 다르다. 이 샘플은 저장소 코드만으로 늘 같은 DB 를 만든다 — 숫자 ·
이름은 모두 합성(`DEMO-` 꼴 제품 · 코드 · 설비명, 일반 후공정 이름)이고 업무 계약이 아니다(`AGENTS.md` 10-1).

- 입구 `scripts/generate_review_sample.py` — 시뮬레이션 DB → 설비 DB → (`--modules`) 모듈 견본 차례로 만든다.
- 부품 `scripts/review_sample_sim.py`(시뮬레이션 DB) · `review_sample_equip.py`(설비 DB) · `review_sample_modules.py`(모듈 견본) ·
  `review_sample_story.py`(이야기 상수 · 산출 자리 지킴 — 앱 import 없음) · `review_sample_core_frame.py`(78컬럼 원천).
- 쓰는 곳 — 사용자 화면 검수(2026-11-02 `review-sample-1102`), 가이드 예시판 시드(`scripts/build_page_guide.py --example` 이
  `git archive` 사본 뿌리에 만든다 — `docs/dual_env_workflow.md` 1-1). 시험은 `tests/test_review_sample.py`.

## 1. 만드는 법

```bash
.venv/bin/python scripts/generate_review_sample.py --out <저장소 밖 뿌리>              # 두 DB + data/input/ CSV 둘
.venv/bin/python scripts/generate_review_sample.py --out <뿌리> --modules --replace    # 모듈 견본도, 있던 산출물을 덮어
.venv/bin/python scripts/generate_review_sample.py --count <뿌리>                      # 개수만(읽기 전용)
```

- 약 50초(사본 점검 포함). `--skip-inspect` 는 `inspect_revision_calculations.py` 사본 점검만 건너뛰고(앱 계산 점검은 그대로),
  `--no-csv` 는 `data/input/` CSV 를 쓰지 않는다 — 가이드 예시판 시드는 둘 다 붙인다.
- **산출은 늘 저장소 밖이다.** 뿌리가 git 작업 트리(이 저장소 · 워크트리 포함) 안이면 아무것도 쓰지 않고 2 로 끝난다. 저장소의
  `data/` · `modules/` 를 만들지 않는다(사외 저장소에는 `modules/` 를 두지 않는다 — 배포 빌더가 멈춘다). `git archive` 사본은
  `.git` 이 없어 받는다. 실제 날짜가 2026-11-02 보다 이르면 돌지 않는다(설비 실적 검사가 그날 기준이다).
- 이미 있는 산출물은 `--replace` 일 때만 덮는다 — 그 생성기가 쓰는 파일(DB · `.wal` · CSV 둘)만이다.
- **결정적이다**(난수 없음 — `zlib.crc32`). 두 번 돌리면 리비전의 내용 지문(`reference_hash`)이 같다 — 뿌리의
  `fingerprint-sim.txt` 와 견줘 기록에 「지난 실행과 리비전 내용 지문 같음」 이 찍힌다. id · 시각 · 월 머지/연도 Shift 원천 코드
  꼬리(uuid)만 다르다.
- 쓰는 길은 앱 저장소 · 등록 · 자동 갱신 공개 함수뿐이다(SQL INSERT · UPDATE 없음). 시뮬레이션 DB 는 준비 자리(`<뿌리>/.gen-sim-work/
  stage`)에서 다 만든 뒤 한 번에 옮긴다 — 끝 점검이 하나라도 어긋나면 옮기지 않고 1 로 끝난다(뒤 단계도 돌지 않는다).

**앱 띄우기.** 앱은 저장소의 `data/` 를 연다(`settings.DATA_DIR`). 저장소를 건드리지 않으려면 `git archive` 사본 뿌리에 만들고 그
사본으로 띄운다.

```bash
T=<저장소 밖 사본>; mkdir -p $T && git archive HEAD | tar -x -C $T
.venv/bin/python scripts/generate_review_sample.py --out $T --modules
cd $T && PYTHONPATH=$T/src CAPA_MODULES_ROOT=$T/modules CAPA_MODULES_DATA_ROOT=$T/module-data \
  <저장소>/.venv/bin/python -m streamlit run app.py --server.port <8560 이상> --server.address 127.0.0.1
```

모듈 상자를 보지 않으려면 `CAPA_MODULES_ROOT=off`(가이드 촬영은 늘 끈다). `CAPA_AUTO_OFFICIAL_UPDATE=1` 을 더하면 예약 스레드가
기동하자마자 끊긴 회차(아래 ⑤ 앞)를 「앱이 꺼져 중단」 오류로 닫는다 — **한 번만** 보이는 장면이다.

## 2. 시뮬레이션 DB — `data/capa_simulation.duckdb`

약 43 MB · 시나리오 9(활성 7 · 보관 2) · 리비전 16 · 공식 v1 ~ v4 · 자동 갱신 회차 6(끊긴 회차 1) · 공용 프로필 전부(Proc Rename 6).
CSV 를 쓰면 `data/input/Core_Data.csv`(W44 원천 78컬럼, cp949) · `RQ_DISPLAY_ORDER.csv`(표시순서 14범위)도 둔다.

시나리오(목록 차례 — `S<n>` 은 생성기 · 이야기 상수의 이름표):

1. **S1 26년 11월 정기 Capa 검토** — BigDataQuery 자동 등록 W44 → r2 자동 공정 필터(공식 v3) → r3 「11월 정기 확정 · 가용
   보정」 = **공식 v4**(정상 길 — 가이드는 여기서 찍는다).
2. S2 26년 10월 정기 — CSV W40, r1 = v2, r2 Wafer Saw 반입 지연, r3 수율 보정 가지(부모 r1).
3. S4 Case · 27년 증산안(+8%) — 복제, r1 = Case1(배지 「최신 rN 있음」), r2 TC Bonding +2.
4. S5 Case · Hybrid Bonding 도입안 — BDQ 손 등록, r2 가상 제품 2 · Lot 측정률 일부 미정 = Case2.
5. S6 월 머지(S2 r1 + S4 r1, 27.07 ~ donor) · 6. S7 연도 Shift(+1).
7. S8 DEMO PSM W43 정기 — 자동 등록, r1 **계산 멈춤**(일부러 넣은 이상 사례) · r2 효율 채움.
8. 보관: S3 26년 9월 정기(공식 v1) · S9 임시 · 붙여넣기 시험본.

**이야기 칸** — 26.12 Pre B/D 소요 33.3 · 가용 32(보유 34 · 대여 2) = **96.1% 부족**, 가용 +2 → **102.1%**. 가이드 「가용대수
바꾸기」 의 고칠 칸(`guides/howto/lob/plan.json` 의 `edit_*` 기본값)이 이 칸이다 — `tests/test_review_sample.py` 가 맞물림을 본다.
Summary B/N(26.11 ~ 27.04): Wafer Saw 확보 · Pre B/D 부족 · Mold 경고 · Mold 부족 · TC Bonding 경고 · Ball Attach 확보.

**일부러 넣은 이상 사례**(가이드는 「막히면」 에만 쓴다) — S8 r1 계산 멈춤(RQ_RUN_RATE 빈 값), 소요대수 밖 수요(빠진 계획 · 빈
생산수량 · 경로 없는 부하 · 제외 경로), 대당 Capa 제외 사유 2종, 보유 공정에 없는 표시명 규칙 둘 · 겹침 규칙, 끊긴 자동 갱신 회차,
DAF Attach 27.02 ~ 04 가용만 −1(보유 − 대여 ≠ 가용 「불일치」), 최저 확보율 80% 미만 공정 Laser Marking 하나(자동 off).

보정(메모리, 쓰기 전) — W44 원천을 장비 자리표시로 돌려 공정별 26.11 소요를 재고 공정마다 UPEH 배수로 목표 소요에 맞춘다 → 반입
계단(여유 하한 1.17 ~ 1.30, 소요 10 이상은 2대 단위)으로 보유 = 계단 + 1, 대여 1 → 이야기 칸 · 반입 늦은 칸은 **대여를 늘려** 가용을
내리고 그 공정 · 그 달 UPEH 만 곱해 확보율을 목표에 정확히 맞춘다. 그래서 공식 v4 의 보유(`RQ_EQP_OWN`)는 달마다 줄지 않는다.

**끝 점검(52개 — 실패면 종료 1)** — 공식 v4 = S1 r3 · 계산 · Density 오류 없음 · 이야기 칸 확보율 · 판정(월별 기준 포함) · 판정 분포
(부족 8 ~ 12 · 경고 15 ~ 25) · Summary B/N 차례 · 소요대수 밖 수요 수 · PKG 규칙 안내 · 자동 갱신 회차 꼴 · 선행 입고 칸 글자 넷 ·
Proc Rename 6 · S8 r1 만 멈춤(앱 계산과 사본 점검 둘 다) · 기동 정리(사본에서 끊긴 회차가 오류로 닫힘) · 가상 제품 · 목록 7 · 보관 2
· 공식 4 · 설정 v2 · CSV 다시 읽기 · WAL 없음 · 식별값 검사(옛 데모 값 · 메일 꼴 0). 기록은 `<뿌리>/build-log-sim.txt`, 공식 v4 의
공정 × 월 표는 `v4_cells.csv`, 사본 점검 결과는 `inspect_revision_calculations.md`.

## 3. 설비 DB — `data/equipment_availability.duckdb`

시뮬레이션 DB 를 **임시 사본으로만** 읽어 공식 v4 의 소요대수 · `RQ_EQP_AVBL` · 판정 기준을 얻고, 설비 대장을 짜서
`DuckDBEquipmentRepository` 공개 메서드로만 쓴다. 시뮬레이션 DB 를 다시 만들면 이것도 다시 만든다(입구가 늘 차례로 돈다).

| 무엇 | 값 |
|---|---|
| 설비 시나리오 | 운영 일정(공식) r1 · r2 · r3 = 설비 공식 v1 · v2 · **v3** / 셋업 가속안 r1 ~ r3(Qual 당김 · 배치 차이 → 공식 발행 막힘) / 반입 지연 대비안 r1 ~ r5(8대 +45일 · 배치 차이 정리 · 되돌림) |
| 호기 | 공식 쌍 약 640행 · 24공정 · 9개 층 · 모듈 묶음 4(2 · 3 · 4모듈, 미배치 서랍 1, 숨은 모듈 1) · 사용기준 HBM · EDP · 범용 · 빈칸 · 환산비 여럿 |
| 상태(2026-11-02 기준) | 가용 · 입고 예정 · 셋업 진행중 · 정지 예정 · 반출/이설 예정 · 보관 · 반출/이설 완료 · 정지 · 운영 비가동 / Qual상태 지연 |
| 일정 확인 | 미확인(반입 · Qual) · 실적 누락 · 상태 갱신 필요 — 설비 마스터 「일정 확인」, Space 「!」 |
| 비가동 · 기존보유 | 비가동 37(TC Bonding 32 — 「이전부터」 · 「계속」 포함) · 기존보유(Burn-In · Final Test 1/3 모듈 · Packing) |
| 공용 값 | Cut-off 23공정(Shipping Inspection 미기재) · 기준선 둘 · 표준 목표 주차 가용 · 입력 비가동 4칸(PMC 27.05 > 가용 ⚠) · 공용 조회 조건 12공정 · 층 비활성 둘 |
| Space | 층 9 · 도면 요소 88 · Main 설비명 위치 · 겹침 1쌍 · 레이아웃표시 N · 미배치 서랍 |

끝 점검 — 리비전 수 · 출처 · 공식 v3 · 셋업 가속안 발행 막힘 · 110% 단축 카드 8공정과 상태 4종(단축으로 해소 · 신규 포함 해소 · 앞달
단축으로 해소 · 기한 지남) · 추가N · 공정 Capa 상세 판정(READY · Cut-off 미기재 · 호기 없음) · 설비 일정 가용 ÷ 공식 가용 ±10% · 판정
대조 · 겹침 · 일정 확인 · 모듈 묶음 · 기준선. 끝에 제약 시뮬레이션 추천 조합(다섯 + 참고 하나)을 기록에 남긴다
(`<뿌리>/build-log-equip.txt`).

## 4. 모듈 견본 — `<뿌리>/modules/` · `<뿌리>/module-data/`(`--modules` 일 때만)

저장소 시험 견본 `tests/fixtures/modules/` 의 합성 모듈 여섯을 파일 내용 그대로 복사하고(바이트 대조) 빈 모듈 데이터 뿌리를 만든다.
그 여섯 폴더만 지우고 다시 쓰며, 모듈 데이터 뿌리에 앱이 쓴 파일이 있으면 지우지 않는다. 앱의 `module_registry.scan_modules` 로 다시
읽어 상태가 기대와 다르면 1.

| 견본 | 상태 | 보이는 것 |
|---|---|---|
| `demo_ok` | 켜짐 | 「모듈」 상자 · 화면 둘 |
| `demo_crash` | 켜짐 | 그 화면만 오류 카드 · import 실패 격리 |
| `demo_keys` | 켜짐 | 접두 없는 키 알림 |
| `demo_off` | 꺼짐 | `module.json enabled=false` |
| `demo_bad_manifest` | 실패 | 선언 오류(모르는 칸) |
| `demo_future_api` | 실패 | API 판이 코어보다 높음 |

실행 줄에 `CAPA_MODULES_ROOT=<뿌리>/modules CAPA_MODULES_DATA_ROOT=<뿌리>/module-data` 를 준다. 하나를 끄려면
`CAPA_MODULES_DISABLED=demo_keys` 를 더한다.
