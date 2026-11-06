# 운영 DB 정본 — C-DEP 운영 절차

C-DEP 운영 서버는 영속 볼륨을 쓸 수 없고 CI/CD 때 디스크(`/project/data`)가 사라진다. 그래서 두 DuckDB(`data/capa_simulation.duckdb` · `data/equipment_availability.duckdb`)의
**정본을 운영 버킷에 둔다.** 앱이 시작할 때 받고 저장하면 올린다. 이 문서는 **사람이 넣고 · 보고 · 하는 것**을 적는다. 차례의 정본은 코드(`scripts/container_start.py` · `object_sync_engine.py` ·
`object_sync_worker.py`), 파일별 책임은 `AGENTS.md` 3장, 결정은 `docs/TODO.md` 3장 「데이터·DB」 2026-11-07 이다.

**쓰는 쪽은 운영 앱 하나다.** 이관이 끝나면 사내 PC 앱은 쓰지 않고, 읽을 때는 사본을 받는다(5장).

**접속 명단 파일은 이 절차 밖이다.** 앱이 환경변수 키로 작은 JSON 하나를 직접 받고 올린다(표준 라이브러리 SigV4 — `io/s3_small.py` · `auth/access_store.py`, `aws` CLI · 프로필을 쓰지 않는다).
켜는 법과 진단은 `docs/sso_setup.md` 2 · 5 · 7장이고 같은 버킷 · 같은 키다.

**두 DB 는 한 쌍이다.** 세대 포인터 하나(`generations/heads/`)가 두 스냅샷을 함께 가리키고 그 PUT 이 게시다. 포인터는 맨 마지막에 쓴다 — 올리는 중 죽으면 앞 세대로 온전히 복구된다. 바뀌지 않은 DB 는
앞 세대의 스냅샷을 그대로 이어 적는다.

## 1. 확인된 환경

| 항목 | 값 |
|---|---|
| CLI | 운영 이미지 `aws-cli/1.46.3`(`docker/Dockerfile-prod` 의 따로 된 한 줄 — 판 값은 `AWS_CLI_VERSION` 과 시험이 맞댄다) · 사내 PC `aws-cli/2.36.8` (Windows exe 번들, 자체 Python 3.14) |
| 엔드포인트 | `http://s3.dataplatform.samsungds.net:9020` |
| 프로필 | `hoyeon.jeon-org-system_package_mfg_team` |
| 네임스페이스 | `org-system_package_mfg_team` — **프로필에 매여 있고 명령 인자가 아니다** |
| 버킷 | 운영 `SPKGCAPA_Ops`(코드에 없다 — `CAPA_S3_BUCKET` 환경변수로만) · 개발 `SPKGCAPA_Dev`(`config/object_storage.json` 기본값) · 각 1000GiB |
| 전송 | http 9020(폐쇄망). https 는 서버 TLS 문제로 쓰지 않는다 |
| 닿음 | 운영 pod 에서 http 403(인증 없는 요청의 정상 답) 확인 · WebIDE 에서 개발 버킷 읽기 쓰기 · probe 셋 true(2026-11-06) |
| 서버 | 쓰는 쪽 운영 앱 하나 · pod 는 겹치지 않음(새로 띄우면 기존은 죽음) · 끄면 바로 꺼짐(끌 때 올릴 기회가 없다) · 상태 검사 시작 제한 1분 · 메모리 한도 1GiB · 노드 디스크 여유 40GiB · overlay 하나 |
| 명령 접두 | 사내는 `uv` 구성이라 **`uv run --no-sync python`** (재잠금·재설치를 막는 안전장치다. `bigdataquery` 를 지우는 것은 맨 `uv sync` 쪽이다) — 아래 본문의 `.\.venv\Scripts\python.exe` 는 개발 PC 표기다 |

## 2. C-DEP 환경변수 표

값은 배포 설정의 표에만 넣는다 — 그 표는 가림이 없고 그룹원 전권이다. 키는 개인 키로 시작해 공용 계정으로 옮긴다. **이 키는 운영 DB 삭제 권한이다.** 공용 계정으로 옮길 때 버킷 정책을 좁힐 수 있는지 사내가 본다.

| 이름 | 필수 | 뜻 |
|---|---|---|
| `CAPA_S3_SYNC_MODE` | 운영 `managed` | 비면 `local`. 틀린 값은 동기화 꺼짐 + `SY-01`. 키가 있고 버킷에 세대가 있는데 비면 `SY-05` — 일부러 끈 서버는 `local` 을 적는다 |
| `CAPA_S3_BUCKET` | `managed` 필수 | 운영 버킷(예: `SPKGCAPA_Ops`). 없으면 받지 않고 머문다 — config 기본은 개발 버킷이다. 접속 명단도 같은 버킷 |
| `CAPA_S3_ACCESS_KEY` | `managed` 필수 · 비밀 | `~/.aws` 프로필 · 접속 명단 |
| `CAPA_S3_SECRET_KEY` | `managed` 필수 · 비밀 | `~/.aws` 프로필 · 접속 명단 |
| `CAPA_S3_ENDPOINT_URL` | 선택 | 없으면 config 값(1장). 접속 명단을 켤 때는 필수 |
| `CAPA_S3_REGION` | 선택 | 기본 `us-east-1` |
| `CAPA_S3_PROFILE` | 선택 | aws 프로필 이름, 기본 config 값 |
| `CAPA_ACCESS_S3_OBJECT` | 선택 | 기본 `access/access_list.json` |
| `CAPA_ACCESS_USERS` | 선택 | 명단 **파일이 처음 없을 때** 첫 판(`docs/sso_setup.md` 5장) |
| `CAPA_ACCESS_ADMINS` | 운영 필수 | 관리자 — 「지금 올리기」 |

`HOME`(`~/.aws` 자리) · `HOSTNAME`(pod 이름)은 런타임이 준다. 시간 상수는 코드에 두고 환경변수로 늘리지 않는다.

## 3. 운영 서버가 스스로 하는 것

**시작 차례**(`scripts/container_start.py`). 시작 스크립트가 맨 앞에서 8080 을 잡고, 끝나면 소켓을 닫고 앱이 같은 포트를 잡는다.

| 차례 | 하는 일 | 실패하면 |
|---|---|---|
| ① 임시 응답 | 모든 경로 200 · `/_stcore/health` 200 — 상태 검사(TCP · `/` · health 어느 것이든)를 통과시키고 접속자에게 「데이터 받는 중」 만 보인다. 로그인 전 화면이라 데이터 · 주소 · 키 · 버킷을 싣지 않는다 | 이어 간다 |
| ② 프로필 | 키 둘로 `~/.aws/credentials` · `config` (0600) — `sync_object_storage.py profile` 이 찍는 설정과 같은 한 벌 | 줄에 적고 이어 간다 |
| ③ 점검 | aws 판 · ECS 연결 · 버킷 목록 · `/project` 디스크 · pod · cgroup · DuckDB 기본값 | 줄에 적고 이어 간다 |
| ④ 설치 · 토큰 | `bigdataquery` 설치(240초까지) · 로그인 토큰 · 요청자 계정 | 줄에 적고 이어 간다 |
| ⑤ 받기 | `managed` 면 `sync_object_storage.py boot-pull`(하위 프로세스) | **앱을 띄우지 않는다** — 그 화면에 머물며 물러나서 다시 시도(5 · 10 · 20 · 40 · 60초, 이후 60초. 사람이 손대야 풀리는 셋은 300초) |
| ⑥ 넘김 | 결과 파일 → 소켓 닫기 → 앱. 틈은 0.7초 안팎, 캐시 없는 첫 실행 1.2초(샘플 관측)이고 쪽의 JS 가 기다렸다 앱으로 간다 | — |

**모드**: 키도 모드도 없으면 지금처럼 ② ③ ⑤ 를 건너뛴다. 키만 있으면 ② ③ 까지 돌고 앱은 빈 디스크로 뜬다(첫 CI/CD 로 aws 판 · 연결을 보는 판). `managed` 면 ⑤ 까지 간다. 그 밖의 값은 동기화 꺼짐으로 앱이 뜨고 `SY-01` 이 알린다
(올리지도 않으니 정본을 덮지 않는다). **이관 뒤 환경변수 표에서 모드 칸이 빠지면** 앱은 같은 길로 빈 디스크로 뜬다 — 빈 값은 유효한 `local` 이라 CI/CD 가 초록이다. 그때는 ③ 의 버킷 목록에 세대가 보여 `SY-05` 가 알린다(이 앱의 저장은 다음 CI/CD 에 사라진다).

**받기 판정** — 받기 성공의 끝에 같은 멤버로 포인터 G+1(`origin: boot`, 펜스)을 낸다. 끝나는 옛 pod 가 그 뒤로 내는 게시는 「HEAD 그대로인가」 에서 멈춘다. **그래서 시작마다 세대가 하나 는다.**

| 로컬 | 표시 | 원격 | 행동 |
|---|---|---|---|
| 없음 | — | 있음 | 받기 |
| 있음 | 변경 없음 · 세대 같음 | 있음 | 그대로 |
| 있음 | 변경 없음 · 세대 다름 | 있음 | 받기(옛 파일은 superseded) |
| 있음 | 변경 있음 · 세대 같음 | 있음 | 그대로 — 일꾼이 올린다 |
| 있음 | 변경 있음 · 세대 다름 | 있음 | 머문다(`diverged`) |
| 있음 | 세대 모름 | 있음 | 받기 — 컨테이너에서 세대 없는 DB 는 빈 시드뿐이다 |
| — | — | 없음 | 머문다(`remote_empty`) — 이관 전. 이관이 끝나면 다음 시도가 받는다 |
| — | — | 갈라짐 | 머문다(`forked`) |

**저장 뒤**(일꾼 `capa-object-sync`): 첫 저장 뒤 쉬면 20초, 늦어도 60초에 올리기를 **시작**한다. 공식 발행 · 「지금 올리기」 는 바로다. 실패는 30 · 60 · 120 · 300초로 물러나고, 쉬는 동안 10분마다 HEAD 를 본다. 끝나는 시각은 전송 속도에
달렸다 — 63MiB · 1 MiB/s 면 1 ~ 2분(계산). **끌 때는 올릴 기회가 없다** — Admin 「DB 동기화」 가 `올릴 것 있음` 이면 CI/CD 를 누르기 전에 기다리거나 「지금 올리기」 를 누른다.

**정리**: 앱이 시작 10분 뒤 · 이후 하루 한 번 스스로 돈다(C-DEP 에는 셸이 없다). 남기는 것은 HEAD · 멤버 쌍이 다른 최신 5세대 · HEAD 시각 기준 7일 안 세대이고 그 세대가 가리키는 스냅샷이다. 나이는 저장소가 준 시각으로 잰다. 고아는 지키고, 저장을 막지 않는다.

**볼 자리** — Admin 「서버 시작 점검」(aws 판 · ECS 연결 · 버킷 목록 · DB 받기 · 디스크 · pod · 메모리와 CPU 한도 · DuckDB 기본값 · `받기 n초 · 앱 응답까지 n초` · 앞 pod 마지막 올림과 이번 앱 준비 사이)과 「DB 동기화」(올릴 것 · 마지막 올림 · 세대 · 크기 · 실패 · 갈래).
알림은 `SY-01`(설정 오류) · `SY-02`(올라가지 못함) · `SY-03`(멈춤) · `SY-04`(정본을 넘긴 사본) · `SY-05`(버킷의 정본을 받지 않은 서버)다. 값에 주소 · 버킷 · 키가 없어 리뷰에 옮겨도 된다(pod 은 이름 끝 다섯 글자만 보인다).

## 4. 이관 차례 (한 번)

사내 PC 앱이 정본이던 것을 운영 버킷으로 옮긴다. 지금 C-DEP 에 있는 저장은 버린다. 그 뒤 사내 PC 앱은 쓰지 않는다.

| 차례 | 누가 | 할 일 | 볼 것 |
|---|---|---|---|
| 1 | 사용자 | 환경변수 표에 키 둘 · `CAPA_S3_BUCKET` · 주소를 넣고 CI/CD(`CAPA_S3_SYNC_MODE` 는 아직 비움) | Admin 「서버 시작 점검」 — aws 판 `1.46.3` · ECS `HTTP 403 닿음` · 버킷 목록 정상. 이미지의 pip 한 줄이 공개 미러로 받히는지가 여기서 답이 난다 |
| 2 | 사용자 | 사내 PC 앱을 끄고 `sync_object_storage.py --bucket <운영 버킷> init` → `status`(6장). `aws s3 cp` 를 쓰지 않는다 — 세대 포인터가 없어 받지 못한다 | `status` 의 세대 1 |
| 3 | 사용자 | `CAPA_S3_SYNC_MODE=managed` 를 넣고 CI/CD | 앱이 뜨고 「DB 받기」 정상 · HOME 이 사내 PC 와 같다 |
| 4 | 사용자 | 앱에서 저장 하나 | 「DB 동기화 · 올릴 것 없음」 · 마지막 올림 시각 |
| 5 | 사용자 | CI/CD 다시 — 저장이 살아 있나. 로그인 중에 한 번 눌러 임시 화면 · 로그인 복귀도 본다 | 그 저장이 보인다 · 「받기 n초 · 앱 응답까지 n초」 |
| 6 | 사용자 | 첫 명단 저장 뒤 `CAPA_ACCESS_USERS` 를 지운다(`docs/sso_setup.md` 5장) | 「S3 명단」 줄 |

2 · 3 은 바꿔도 된다 — 먼저 켜면 임시 화면에서 `remote_empty` 로 기다리다 `init` 뒤 스스로 받는다.

## 5. 사내 PC — 읽기는 사본으로

`init` 뒤 그 PC 는 쓰는 쪽이 아니다. 사이드카에 넘긴 표지(`handed_over_utc`)가 남아 `push` · `resolve --keep mine` · `adopt --source local` 이 거절되고 앱에는 `SY-04` 가 뜬다(그 PC 의 저장은 막지 않는다 — 정본에 닿지 않을 뿐이다). 운영 앱이 포인터를 낸 뒤(`origin` 이
`app` · `boot` · `rollback`)에는 표지가 없는 PC 도 같다. `--override-writer` 는 운영 앱의 저장을 덮을 수 있다.

```powershell
.\.venv\Scripts\python.exe scripts\sync_object_storage.py --bucket <운영 버킷> fetch-copy --to C:\capa-copy
.\.venv\Scripts\python.exe scripts\sync_object_storage.py --bucket <운영 버킷> fetch-copy --to C:\capa-copy --seq 12
```

HEAD(또는 그 세대) 두 멤버를 받아 검증한 뒤에만 그 폴더에 두 DB 와 `generation.json` 을 둔다. `data/` 를 건드리지 않고 운영 DB 자리는 거절한다. 앱이 떠 있어도 된다. 런북의 점검 스크립트는 이 사본을 `--database` · `--equipment-database` 로 받는다(런북 6-4).

## 6. 사내 PC 준비 · 이관 명령

**0단계 — 프로필(한 번만).** 출력되는 블록을 그대로 붙여 넣는다. 손으로 옮겨 적지 않는다. 키 두 줄만 실제 값으로 바꾼다.

```powershell
.\.venv\Scripts\python.exe scripts\sync_object_storage.py profile
```

- `s3.addressing_style path` — 버킷명에 대문자와 언더바가 있어 가상 호스트 스타일로는 표현할 수 없다. 없으면 서명 불일치나 DNS 오류가 난다.
- `request_checksum_calculation` / `response_checksum_validation` = `when_required` — AWS CLI 2.23.0 이상은 ECS 에서 `Missing required header for this request: Content-MD5` 로 실패한다(Dell KB 000299507). **이 오류를 방화벽 · 권한 문제로 오진하면 며칠을 태운다.**

**1단계 — 접속 확인.** `$env:` 는 이 창의 스크립트용이다. 이관 뒤 사내 PC 앱은 `managed` 로 띄우지 않는다.

```powershell
$env:CAPA_S3_SYNC_MODE = "managed"
.\.venv\Scripts\python.exe scripts\sync_object_storage.py --bucket <운영 버킷> doctor
```

모드 · 엔드포인트 · 버킷 · 프로필과 CLI 버전, 두 DB 의 원격 · 로컬 세대를 찍는다. 원격이 비어 있는 것이 최초 상태의 정상이다. `mode` 는 이 스크립트에서 출력에만 쓰이고 어떤 하위 명령도 막지 않는다. `Content-MD5` 오류가 나면 0단계의 체크섬 설정이 안 먹은 것이다 — 그래도 나면 CLI 를 2.22.x 로 내린다.

**2단계 — 능력 측정.** 확인하지 못한 능력은 없는 것으로 본다. `_probe/` 아래에 임시 객체를 만들었다 지운다. 사내 값은 이미 파일에 있다(2026-11-06) — 저장소가 바뀌었을 때만 돌린다.

```powershell
.\.venv\Scripts\python.exe scripts\sync_object_storage.py probe --write config\object_storage_capabilities.json
```

**3단계 — 최초 이관(앱을 끈 채로).** `aws s3 cp` 가 아니라 `init` 이다.

```powershell
.\.venv\Scripts\python.exe scripts\sync_object_storage.py --bucket <운영 버킷> init --note "최초 이관"
.\.venv\Scripts\python.exe scripts\sync_object_storage.py --bucket <운영 버킷> status
```

`init` 은 원격이 비어 있을 때만 동작하고 두 DB 를 함께 올린다. 이미 세대가 있으면 건너뛴다. 스냅샷을 만드는 과정이 곧 재구축이라 파일이 줄어든다. 넘기지 않고 시험할 때(개발 버킷)는 `init --keep-writer` 다.

`--bucket` · `--dry-run` 은 **하위 명령 앞에** 놓는다. 뒤에 붙이면 `unrecognized arguments` 로 죽는다. 사내 PC 의 기본 버킷은 개발 버킷이다 — 운영 버킷은 늘 적는다.

## 7. 세대 되돌리기

앱 결함으로 망가진 세대가 게시됐거나 원격이 갈라졌으면 앞 세대의 멤버로 새 HEAD 를 낸다. 지우지 않고 앞으로만 간다.

```powershell
.\.venv\Scripts\python.exe scripts\sync_object_storage.py --bucket <운영 버킷> generations
.\.venv\Scripts\python.exe scripts\sync_object_storage.py --bucket <운영 버킷> rollback --to 12 --yes
```

`generations` 는 세대 번호 · 두 멤버의 세대 · 키 꼬리 · 시각을 최신부터 찍는다(포인터 키에 실린 값이라 받지 않는다). **시작마다 같은 멤버의 펜스 세대가 쌓이므로 바로 앞 세대는 깨진 멤버를 그대로 가리킬 수 있다 — 멤버 세대가 HEAD 와 다른 앞 세대를 고른다.** `rollback` 은 멤버가 저장소에 있는지와 크기만 대조한다. 같은 세대에 포인터가 둘이면 `--token <키 꼬리 8자리>` 로 고른다. 그 뒤 운영 앱의 일꾼은 HEAD 가 움직인 것을 보고 멈춘다(`SY-03`) — CI/CD 로 새 pod 가 그 세대를 받게 한다. **멈춘 pod 의 미반영 변경은 그 CI/CD 로 사라진다.**

## 8. 막혔을 때

임시 화면 둘째 줄의 낱말과 Admin 의 갈래는 같은 말이다.

| 낱말 | 뜻 | 할 일 |
|---|---|---|
| 원격이 비어 있음 | 이관 전 | 4장 2 의 `init` — 다음 시도가 스스로 받는다 |
| 설정 오류 | `CAPA_S3_BUCKET` · 키 없음, 설정 파일 깨짐, `~/.aws` 를 못 써 프로필 없음(`HOME`) | 환경변수 표를 고치고 CI/CD. 표가 맞는데 그대로면 `HOME` 자리에 쓸 수 있는지 담당에 묻는다(임시 화면에 머무는 동안은 Admin 이 없다) |
| aws 명령 없음 | 이미지에 `aws` 가 없다 | `docker/Dockerfile-prod` 한 줄 · PATH — 사외 요청 |
| 저장소가 거절 | 키 · 권한 | 키를 고치고 CI/CD |
| 버킷 없음 | 버킷 이름 | 이름을 고치고 CI/CD |
| 저장소에 닿지 못함 · 시간 초과 | 망 · 저장소. 받는 도중 연결이 끊긴 것도 여기다 | 저절로 다시 시도한다 |
| 디스크 부족 | `/project` 자리. 받는 도중 찬 것도 여기다 | 앞 배포의 「서버 시작 점검」 디스크 값을 보고 담당에 묻는다 |
| 스냅샷이 깨짐 | 받은 파일이 검증에 실패했거나 HEAD 의 스냅샷이 저장소에 없다 | 사내 PC `generations` 로 멤버 세대가 다른 앞 세대를 골라 `rollback`(7장) |
| 원격이 갈라짐 | 같은 세대에 포인터가 둘 | `rollback` 으로 이어 갈 세대를 고른다 |
| 원격과 어긋남 | pod 의 미반영 변경이 있는데 세대가 다르다 | CI/CD — 디스크가 비어 풀린다. 그 변경은 사라진다 |
| DB 판이 코드보다 새로움 | 마이그레이션이 든 배포를 앞으로 되돌렸다 | 최신을 다시 CI/CD |
| 그 밖의 실패 | 위에 없는 실패(저장소의 5xx 등) | 저절로 다시 시도한다. 오래 가면 사내 PC 에서 `doctor` 를 돌려 원문을 본다 |

**임시 화면은 HTTP 200 이라 CI/CD 는 성공으로 보인다.** CI/CD 뒤에는 앱을 열어 본다.

| 스크립트 출력 | 뜻 | 할 일 |
|---|---|---|
| `Missing required header ... Content-MD5` | CLI 2.23+ × ECS 비호환 | 6장 0단계 체크섬 설정 확인 → 안 되면 CLI 2.22.x |
| `[건너뜀] … 어느 세대에서 왔는지 모릅니다` | 로컬 DB 가 어느 세대에서 왔는지 모름 | `adopt --source local` 또는 `pull --force` |
| `[중단] … 원격이 먼저 앞섰습니다` | 남이 먼저 저장 | `resolve --keep mine` 또는 `--keep remote`. 승격은 멤버가 저장소에 있는지 먼저 보고, 내 세대가 만들지 않은 멤버는 HEAD 값으로 적는다 — 그러면 `[주의]` 가 뜨고 `pull` 로 받는다 |
| `판정 : 정본은 운영 앱에 있습니다` | 정본을 넘긴 PC 의 평상 상태(시작마다 세대가 는다) | 할 일 없음. 읽을 때는 `fetch-copy` |
| `[중단] … 갈라졌습니다` | 같은 세대에 포인터가 둘 | 양쪽 파일 모두 남아 있다. `rollback` 으로 이어 갈 세대를 고른다 |
| `[중단] 이 PC 는 … 정본을 넘겼습니다` | `init` 뒤의 쓰기 | 정본은 운영 앱이 쓴다. 읽을 때는 `fetch-copy` |
| `IOException` 류 | 앱이 DB 파일을 잡고 있음 | 앱을 끄고 다시 실행 |

**올라간 스냅샷은 정리(3장) 밖에서는 지워지지 않는다.** 경합에서 지면 고아 스냅샷으로 남고 `--dry-run prune` 의 「지킨 고아 n」 이 수를 보여 준다. `prune` 은 고아를 기본으로 지키고, 같은 세대 번호의 스냅샷이 둘 이상이면 어느 쪽이 참조인지 목록으로 모르므로 둘 다 지킨다(재시도의 찌꺼기도 함께 남는다). 손으로 돌릴 때는 `prune --keep-last 5 --keep-days 7` 이다.

## 9. 잰 수

**사내 측정** — 2026-09-09 push 66초 · pull 50초. 시뮬레이션 62.6 → 42.8 MiB(스냅샷 생성 2.88초), 설비 0.4 → 0.4 MiB(0.06초). 전송은 양방향 모두 대략 1 MiB/s. 앱 최고 메모리 747MB(사내 PC 실데이터).

**샘플 관측**(합성 DB · 기계 32코어 WSL · 실제 `aws` 1.46.3 · 루프백 가짜 S3 — 실데이터 · 사내 망이 아니다).

| 항목 | 62.8MiB | 308.4MiB |
|---|---|---|
| ATTACH 복사(제한 없음) | 2.0초 · +555MiB | 7.3초 · +1,655MiB |
| 앱 안 복사(쓰기 잠금 + CHECKPOINT + 바이트 복사) | 잠금 0.09초 · 전체 0.20초 · +16MiB | 잠금 0.28초 · 전체 0.73초 · +19MiB |

앱 747MiB 위 최고 RSS 는 ATTACH 1,316 · 2,410MiB, 바이트 복사 769 · 772MiB 다. 그래서 앱 안에서는 바이트 복사를 쓰고(대가: 압축이 없어 전송이 늘 수 있다) 사내 PC `init` 은 ATTACH 복사 그대로다. `aws` 하나는 파일 크기와 무관하게 최고 RSS 57MiB, 기동 0.2 ~ 0.4초다. 1GiB 예산은 747 + 25 + 57 = 829MiB 다.

| 시작 차례(합성 약 41 + 4 MiB) | 값 |
|---|---|
| 임시 응답 첫 답 | 0.1초 |
| 빈 디스크 받기(`boot-pull`) | 1.8 ~ 2.6초 |
| 소켓 닫기 → 앱 첫 200 | 0.64 ~ 0.70초(듣기 없음 0.18 ~ 0.21초), 파일 캐시가 찬 줄 없는 첫 실행 1.13 ~ 1.17초 |
| 공식 발행 → 게시 | 1.58초(잠금 0.029초 · 전송 0.88초) |
| 평범한 저장 → 게시 | 21.5초(모으기 20초) |

**못 잰 것** — 실제 cgroup, 빈 컨테이너 첫 시작, overlay 복사 시간, 사내 망 전송, 운영 코어 수, C-DEP 검사 간격, 옛 pod 가 죽는 때. 앞의 다섯은 Admin 값이 알려 준다. 바이트 복사의 일관성은 DuckDB 내부 동작에 기대고 샘플 겹침 시험 694회는 증명이 아니다 — DuckDB 판을 올릴 때 겹침 시험을 다시 돈다.

## 10. 사내에서 확인할 것

| # | 항목 | 왜 필요한가 | 확인 | 결과 |
|---|---|---|---|---|
| 1 | 체크섬 옵트아웃이 먹는가 | 1순위 위험 | 6장 1단계 | **2026-09-09 정상** |
| 3 | `--if-none-match '*'` 지원 | 동시 저장 예방 | 2단계 `probe` | **2026-11-06 true.** 포인터 키에 토큰이 있어 쓰지 않는다 — 겹침 막기는 세대 대조 |
| 4 | 단일 PUT ETag 가 MD5 인가 | 무결성 검증 | 2단계 `probe` | **2026-11-06 true** |
| 5 | 업로드 · 다운로드 시간 | 제한시간 근거 | 9장 | **2026-09-09** — 9장 |
| 7 | 9021(HTTPS) | — | — | **2026-11-06 닫음.** 서버 TLS 문제로 쓰지 않는다 |
| 8 | 운영 이미지에서 `aws` 가 PATH 에 있는가 | 앱이 `subprocess` 로 부른다 | Admin 「서버 시작 점검」 aws 줄 | 첫 CI/CD 가 답한다 |
| 11 | C-DEP pod 에서 키로 버킷에 닿는가 | 정본 · 명단이 여기로 간다 | Admin 「버킷 목록」 · 「S3 명단」 줄 | 주소는 닿음(2026-11-06) · 키는 첫 CI/CD 가 답한다 |
| 12 | 옛 pod 가 죽는 때 | 새 pod 시작 전인가, 상태 검사 뒤인가 — 펜스는 어느 쪽이든 안전하다 | C-DEP 담당 | |
| 13 | 공용 계정의 버킷 정책 | 키가 운영 DB 삭제 권한이다 | 담당 | |

`probe` 는 3 · 4번과 `content_md5_rejects_mismatch` 만 덮어쓰고 `checksum_optout_required` · `bucket_versioning` 은 채우지 않는다. 이 둘은 손으로 적는다.

## 하지 않은 것

- **모듈 데이터 동기화.** `data/modules/<id>/` 는 CI/CD 마다 사라지는 것이 지금과 같다.
- **개발 서버 읽기 전용 화면.** 다운 시간 값을 보고 정한다(`docs/TODO.md` 「S3 분리」).
