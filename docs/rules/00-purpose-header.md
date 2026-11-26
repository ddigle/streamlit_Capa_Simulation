# AGENTS 0장 — 소스 파일 Purpose 헤더 규칙

## 0. 소스 파일 Purpose 헤더 규칙

Git으로 관리하는 Python·PowerShell 소스에는 파일 최상단에 다음 한 줄의 주석 헤더를
유지한다. 적용 대상은 `app.py`, `app_pages/`, `src/`, `scripts/`, `tests/` 아래의
`.py`·`.ps1` 파일이며 `#`를 주석 기호로 사용한다.

```text
# Purpose: 이 파일이 담당하는 단일 책임을 구체적인 한 문장으로 기술
```

- `Purpose`는 파일명 반복이 아니라 입력·처리·출력 또는 UI 책임을 알 수 있게 작성한다.
- 파일의 책임이 달라지면 같은 변경에서 `Purpose`도 함께 고친다.
- 변경 출처와 이력은 주석에 적지 않는다. 누가·언제·무엇을 바꿨는지는 Git commit history가
  단일 근거이며, 필요하면 `git log -1 --format='%ad %an %s' -- <파일>`로 확인한다.
  이전에 사용하던 `Applied`·`Agent`·`Model`·`Change` 네 줄은 파일마다 충돌만 만들고
  Git이 이미 더 정확히 답하므로 제거했다.
- 기존 SQL 마이그레이션은 적용 체크섬이 달라지므로 주석 추가를 포함해 절대 수정하지
  않는다. 목적과 문서화 출처는 `docs/migration_catalog.md`에서 관리한다. 신규 SQL은 최초
  생성 시 `--` 형식의 `Purpose` 한 줄과 카탈로그 항목을 함께 작성하며, 적용 후에는 헤더도
  수정하지 않고 후속 번호의 마이그레이션을 추가한다.
  - `tests/test_migration_checksums.py` 가 두 DB 의 적용된 파일 체크섬을 버전별 표로 고정하고,
    러너가 바뀐 체크섬을 거부하는지도 돌려 본다 — 그 거부는 그 번호가 이미 적용된 DB 에서만 나서
    새 DB 를 만드는 다른 시험으로는 드러나지 않는다. **새 번호를 더하면 그 표에 한 줄을 더한다**
    (빠지면 실패 문구가 붙여 넣을 줄을 찍는다).
  - **새 마이그레이션을 쓰는 중에는 pytest 를 돌린 뒤 그 파일을 고치지 않는다.** 검사가
    도는 동안 개발 DuckDB 에 그 번호가 적용되므로, 그다음 한 글자만 고쳐도 온 검사가
    「이미 적용된 마이그레이션이 변경되었습니다」로 죽는다. 아직 **어디에도 배포하지 않은**
    번호라면 개발 DB 에서 그 행만 지우고 다시 적용하면 된다 —
    `DELETE FROM app_meta.schema_migration WHERE version = <번호>`. 체크섬 표의 그 줄도 새 값으로
    바꾼다. 한 번이라도 배포한 번호에는 쓰지 않는다. 후속 번호를 쓰는 것이 그때의 유일한 길이다.
- 새 소스 파일도 같은 헤더를 포함해야 한다. `tests/test_source_metadata.py`가 Python·
  PowerShell `Purpose`의 누락·빈 항목과 모든 SQL의 카탈로그 등록을 검사하므로 기본
  검증 명령에 포함된 pytest를 반드시 통과시킨다.
- `modules/<id>/` 는 코어 시험이 훑지 않아 `check_module.py`(M13)가 같은 헤더를 본다.

### SQL 마이그레이션

적용된 마이그레이션은 **버전 번호로 체크섬을 대조**하므로 주석 추가를 포함해 절대 수정하지
않는다. 후속 번호를 새로 추가한다. **시뮬레이션 DB의 2·3번은 영구 결번**이고 재사용하면
기존 DB에서 앱이 시작조차 못 한다(`tests/test_migration_numbering.py`가 막는다). 신규 SQL은
`--` 형식의 `Purpose` 한 줄과 `docs/migration_catalog.md` 항목을 함께 작성하고,
`tests/test_migration_checksums.py` 의 체크섬 표에 한 줄을 더한다(적용된 파일의 수정을 그 시험이 잡는다).
