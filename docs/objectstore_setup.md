# 사내 오브젝트 스토리지 연동 절차

DuckDB 파일을 WebIDE 밖의 S3 호환 스토리지(사내 구축, Dell ECS 로 추정)에 두기 위한
**사람이 해야 하는 절차**다. 코드가 대신할 수 없는 것만 담는다. 설계 근거는
`docs/TODO.md` 3-9 절, 파일별 책임은 `AGENTS.md` 3장에 있다.

지금 단계는 **수동 왕복**이다. 앱은 스스로 올리거나 받지 않는다 — 저장할 때마다 사이드카에
"변경 있음" 만 남기고(`managed` 모드에서만), 실제 `pull`·`push` 는 이 스크립트로 사람이 돌린다.
`local` 모드(개발 PC 기본값)에서는 그 표시조차 남기지 않는다.

## 확인된 환경

| 항목 | 값 |
|---|---|
| CLI | `aws-cli/2.36.8` (Windows exe 번들, 자체 Python 3.14) |
| 엔드포인트 | `http://s3.dataplatform.samsungds.net:9020` |
| 프로필 | `hoyeon.jeon-org-system_package_mfg_team` |
| 네임스페이스 | `org-system_package_mfg_team` — **프로필에 매여 있고 명령 인자가 아니다** |
| 버킷 | `Capa_simulation_project` |
| 명령 접두 | 사내는 `uv` 구성이라 **`uv run python`** — 아래 본문의 `.\.venv\Scripts\python.exe` 는 개발 PC 표기다 |

---

## 0단계 — 프로필 설정 (한 번만)

출력되는 블록을 그대로 붙여 넣는다. 손으로 옮겨 적지 않는다.

```powershell
.\.venv\Scripts\python.exe scripts\sync_object_storage.py profile
```

키 두 줄만 실제 값으로 바꾼다. 나머지 다섯 줄 중 **체크섬 두 줄과 주소 스타일 한 줄이 핵심**이다.

- `s3.addressing_style path` — 버킷명에 대문자와 언더바가 있어 가상 호스트 스타일로는
  표현할 수 없다. 없으면 서명 불일치나 DNS 오류가 난다.
- `request_checksum_calculation` / `response_checksum_validation` = `when_required` —
  AWS CLI 2.23.0 이상은 ECS 에서 `Missing required header for this request: Content-MD5` 로
  실패한다(Dell KB 000299507). **이 오류를 방화벽·권한 문제로 오진하면 며칠을 태운다.**

## 1단계 — 접속 확인

```powershell
setx CAPA_S3_SYNC_MODE managed       # 앱용. 새로 여는 창부터 적용되므로 앱을 다시 띄워야 한다
$env:CAPA_S3_SYNC_MODE = "managed"   # 지금 창에서 돌릴 스크립트용. 이 셸이 닫히면 사라진다
.\.venv\Scripts\python.exe scripts\sync_object_storage.py doctor
```

`$env:` 만 걸고 앱을 다른 창에서 띄우면 **앱은 `local` 로 뜬다.** 커밋된
`config/object_storage.json` 의 `mode` 가 `local` 이고 `sync_boot.py` 는 `managed` 가 아니면
사이드카 등록을 건너뛴다 — 그러면 리비전을 아무리 저장해도 `mark_dirty()` 가 파일을 쓰지
않아 사이드카가 `dirty: false` 로 남고 `push` 가 영원히 "올릴 것 없음" 이 된다.
**이미 한 번 일어난 결함이다.** 그래서 `setx` 는 앱용, `$env:` 는 이 창의 스크립트용이다.

모드·엔드포인트·버킷·프로필과 CLI 버전, 그리고 두 DB 의 원격/로컬 세대를 찍는다.
원격이 비어 있는 것이 최초 상태의 정상이다.

`mode` 는 이 스크립트에서 **출력에만 쓰이고 어떤 하위 명령도 막지 않는다.** 모드가 실제로
가르는 것은 앱 쪽 `sync_boot.py` 의 사이드카 등록뿐이다.

여기서 `Content-MD5` 오류가 나면 0단계의 체크섬 설정이 안 먹은 것이다. 그래도 나면
**CLI 를 2.22.x 로 내린다.** 이것이 이 연동에서 1순위 위험이다.

## 2단계 — 능력 실측

스토리지가 실제로 무엇을 지원하는지 재서 파일에 남긴다. **확인하지 못한 능력은 없는 것으로
본다** — 코드가 그렇게 동작하고, 없는 능력을 있다고 가정하면 데이터가 조용히 갈라진다.

```powershell
.\.venv\Scripts\python.exe scripts\sync_object_storage.py probe `
    --write config\object_storage_capabilities.json
```

`_probe/` 아래에 임시 객체를 만들었다 지운다. 실패해도 그 접두사만 지우면 된다.

## 3단계 — 최초 이관 (앱을 끈 채로)

```powershell
.\.venv\Scripts\python.exe scripts\sync_object_storage.py init --note "최초 이관"
.\.venv\Scripts\python.exe scripts\sync_object_storage.py status
```

`init` 은 원격이 비어 있을 때만 동작한다. 이미 세대가 있으면 건너뛴다.
`compact_duckdb.py` 를 먼저 돌릴 필요가 없다 — 스냅샷을 만드는 과정이 곧 재구축이라
**67 MB 가 21 MB 로 줄어든다**(개발 PC 실측, 2.11초).

## 4단계 — 왕복 확인

```powershell
# 앱에서 리비전을 하나 저장한 뒤
.\.venv\Scripts\python.exe scripts\sync_object_storage.py status   # 변경: 있음
# — 앱 프로세스가 managed 로 떠 있어야 여기에 "변경 있음" 이 찍힌다(1단계 `setx`)
.\.venv\Scripts\python.exe scripts\sync_object_storage.py push --note "왕복 확인"
.\.venv\Scripts\python.exe scripts\sync_object_storage.py status   # 원격 seq 증가

# 다른 PC(또는 DB 를 지운 뒤)에서
.\.venv\Scripts\python.exe scripts\sync_object_storage.py pull
```

`--dry-run` 은 **하위 명령 앞에** 놓는다. 뒤에 붙이면 `unrecognized arguments` 로 죽는다.

```powershell
.\.venv\Scripts\python.exe scripts\sync_object_storage.py --dry-run push --note "왕복 확인"
```

실제로 올리거나 받지 않고 무엇을 할지만 찍는다. 처음에는 붙여서 보는 편이 좋다.

## 막혔을 때

| 증상 | 뜻 | 할 일 |
|---|---|---|
| `Missing required header ... Content-MD5` | CLI 2.23+ × ECS 비호환 | 0단계 체크섬 설정 확인 → 안 되면 CLI 2.22.x |
| `[건너뜀] … 세대를 알 수 없습니다` | 로컬 DB 가 어느 스냅샷에서 왔는지 모름 | `adopt --source local` 또는 `pull --force` |
| `[중단] … 원격이 먼저 앞섰습니다` | 남이 먼저 저장 | `resolve --keep mine` 또는 `--keep remote` |
| `[중단] … 갈라졌습니다` | 같은 세대에 포인터가 둘 | 양쪽 파일 모두 남아 있다. 한쪽을 골라 `resolve` |
| `IOException` 류 | 앱이 DB 파일을 잡고 있음 | 앱을 끄고 다시 실행 |

**어떤 경우에도 올라간 스냅샷은 지워지지 않는다.** 경합에서 지면 고아 스냅샷으로 남고
`status` 가 그 키를 그대로 보여 준다. `prune` 은 고아를 기본으로 보호한다.

---

## 사내에서 확인해 주셔야 하는 것

개발 PC 에는 `aws` CLI 도 `boto3` 도 없고 사내 엔드포인트에 닿지 않는다. 아래는 **여기서
검증할 수 없어 사내에서만 답이 나오는** 항목이다. 확인하면 이 표에 날짜와 결과를 적는다.

| # | 항목 | 왜 필요한가 | 확인 | 결과 |
|---|---|---|---|---|
| 1 | 체크섬 옵트아웃이 실제로 먹는가 | 1순위 위험. 안 되면 CLI 다운그레이드 | 1단계 `doctor` | **2026-09-09 정상.** `init`·`push` 가 `Content-MD5` 오류 없이 끝났다 |
| 2 | ECS 버전 | 조건부 쓰기·체크섬 지원이 여기서 갈린다 | 스토리지 팀 문의 | |
| 3 | `--if-none-match '*'` 지원 | 동시 저장 예방의 3겹째를 켤지 결정 | 2단계 `probe` | |
| 4 | 단일 PUT ETag 가 MD5 인가 | 무결성 검증 수단 유무 | 2단계 `probe` | |
| 5 | 업로드·다운로드 실측 시간 | 타임아웃 상수의 근거 | 4단계 왕복 | **2026-09-09 push 66초 / pull 50초.** 시뮬레이션 62.6→42.8 MiB(스냅샷 생성 2.88초), 설비 0.4→0.4 MiB(0.06초). 전송은 양방향 모두 대략 1 MiB/s. 제한시간은 고정 300초가 아니라 크기에 딸린 `max(300, 60 + MiB/0.3)` 초라(`transfer_timeout_seconds()`) 42.8 MiB 에서는 여전히 300초 — 여유는 그대로다 |
| 6 | `aws s3 ls s3://` 전체 목록 권한 | 없어도 되지만 진단이 편해진다 | 손으로 | |
| 7 | 9021(HTTPS) 개방 여부 | 지금은 평문 HTTP 라 생산계획이 사내망에 그대로 흐른다 | 네트워크 담당 | |
| 8 | WebIDE 안에서 `aws` 가 PATH 에 있는가 | 앱이 `subprocess` 로 부른다. 없으면 자동화를 못 붙인다 | 컨테이너에서 `aws --version` | |
| 9 | WebIDE 재시작 주기·프로필명 변화 | 환경변수로 덮어쓸 준비는 돼 있다 | 운영 담당 | |
| 10 | 동시 사용자가 늘어날 시점 | 지금은 단일 사용자 전제다 | 업무 판단 | |

1·5번이 확인 완료인 것은 **4단계 왕복으로 확인한 것이지 `probe` 결과가 아니다.** 2단계
`probe` 는 아직 사내에서 돌리지 않았으므로 `config/object_storage_capabilities.json` 이
비어 있는 것이 정상이다 — 그 파일과 이 표를 나란히 놓고 "실측 결과가 반영되지 않았다"고
읽지 않는다. 또 `probe` 는 3·4번과 `content_md5_rejects_mismatch` 만 덮어쓰고
`checksum_optout_required`·`bucket_versioning` 은 채우지 않는다. 이 둘은 손으로 적는다.

## 이 단계에서 하지 않은 것

- **앱 자동 동기화.** 기동 시 pull, 저장 후 push, 사이드바 상태 표시는 다음 단계다.
  변경 표시(`mark_dirty`)까지만 붙였다 — 8번(WebIDE 안 `aws` PATH)이 남아 있어 앱이
  `aws` 를 직접 부르는 단계는 아직 이르다.
- **다중 사용자 잠금.** `docs/TODO.md` 3-9 의 남은 항목이다. 지금 설계는 유실을 막고
  갈라짐을 즉시 알리는 데까지다.
