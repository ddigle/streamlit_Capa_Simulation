# Capa Simulation 개발 에이전트 가이드

이 문서는 저장소 전체에 적용되는 개발 규칙의 색인이다 — 장마다 한 파일(`docs/rules/`), 파일별 책임은
`docs/reference/files/`, 모듈 색인은 생성한다(`docs/reference/module_index.md`). 작업을 시작하기 전에
`README.md`, 이 색인에서 맡은 장, `docs/TODO.md`를 읽고 실제 코드와 함께 현재 상태를 확인한다.
규칙이 바뀌면 그 규칙을 맡은 파일 한 곳을 그 자리에서 고쳐 쓴다(덧붙이지 않는다). 다른 곳은 링크로 둔다.

> **사내(WebIDE)에서 이 문서를 읽고 있다면 `docs/dual_env_workflow.md` 와
> `docs/internal_update_runbook.md` 를 먼저 읽는다.** 사내에서는 소스를 고치지 않고
> `review/` 에만 쓴다. 어느 환경인지는 `git remote -v` 로 가른다 — `github.com` 이면
> 사외다. 모듈 담당자의 에이전트라면 `docs/module_guide.md` 만 따르고 자기 `modules/<id>/` 밖을 고치지 않는다.

- 0장 소스 파일 Purpose 헤더 규칙 → [docs/rules/00-purpose-header.md](docs/rules/00-purpose-header.md)
- 1장 프로젝트 목표와 현재 경계 → [docs/rules/01-goals-and-boundaries.md](docs/rules/01-goals-and-boundaries.md)
- 2장 실행환경과 검증 기준 → [docs/rules/02-runtime-and-verification.md](docs/rules/02-runtime-and-verification.md)

## 3. 파일별 책임

- 3장 파일별 책임 > 실행과 UI → [docs/reference/files/app-and-ui.md](docs/reference/files/app-and-ui.md)
- 3장 파일별 책임 > 실행과 UI → [docs/rules/09-streamlit-implementation.md](docs/rules/09-streamlit-implementation.md)
- 3장 파일별 책임 > 입력과 상태 → [docs/reference/files/input-and-state.md](docs/reference/files/input-and-state.md)
- 3장 파일별 책임 > 입력과 상태 → [docs/rules/05-state-cache-invariants.md](docs/rules/05-state-cache-invariants.md)
- 3장 파일별 책임 > 입력과 상태 → [docs/rules/09-streamlit-implementation.md](docs/rules/09-streamlit-implementation.md)
- 3장 파일별 책임 > 계산 서비스 → [docs/reference/files/services.md](docs/reference/files/services.md)
- 3장 파일별 책임 > 계산 서비스 → [docs/rules/07-join-validation.md](docs/rules/07-join-validation.md)
- 3장 파일별 책임 > 화면 공통 계층 → [docs/reference/files/components.md](docs/reference/files/components.md)
- 3장 파일별 책임 > 화면 공통 계층 → [docs/rules/09-streamlit-implementation.md](docs/rules/09-streamlit-implementation.md)
- 3장 파일별 책임 > 화면 공통 계층 → [docs/rules/08-display-sorting.md](docs/rules/08-display-sorting.md)
- 3장 파일별 책임 > 영속성 모듈 → [docs/reference/files/persistence.md](docs/reference/files/persistence.md)
- 3장 파일별 책임 > 영속성 모듈 → [docs/rules/05-state-cache-invariants.md](docs/rules/05-state-cache-invariants.md)
- 3장 파일별 책임 > 모듈 색인 → [docs/reference/module_index.md](docs/reference/module_index.md)
- 3장 파일별 책임 > 자료실(GitHub Pages)과 발표 자료 → [docs/rules/10-local-files-security.md](docs/rules/10-local-files-security.md)
- 4장 기준정보 테이블 계약 → [docs/rules/04-reference-table-contract.md](docs/rules/04-reference-table-contract.md)
- 5장 상태와 캐시 불변조건 → [docs/rules/05-state-cache-invariants.md](docs/rules/05-state-cache-invariants.md)
- 6장 핵심 계산 규칙 → [docs/rules/06-core-calculation.md](docs/rules/06-core-calculation.md)
- 7장 조인과 데이터 검증 규칙 → [docs/rules/07-join-validation.md](docs/rules/07-join-validation.md)
- 8장 표시·정렬 규칙 → [docs/rules/08-display-sorting.md](docs/rules/08-display-sorting.md)
- 9장 Streamlit 구현 규칙 → [docs/rules/09-streamlit-implementation.md](docs/rules/09-streamlit-implementation.md)
- 10장 로컬 파일과 보안 → [docs/rules/10-local-files-security.md](docs/rules/10-local-files-security.md)
- 10-1장 로컬 데이터는 합성 표본이다 — 관측을 업무 사실로 적지 않는다 → [docs/rules/10-1-synthetic-local-data.md](docs/rules/10-1-synthetic-local-data.md)
- 11장 현재 미구현 및 주의 사항 → [docs/rules/11-unimplemented-caveats.md](docs/rules/11-unimplemented-caveats.md)
- 12장 변경 작업 체크리스트 → [docs/rules/12-change-checklist.md](docs/rules/12-change-checklist.md)
- 13장 문서 우선순위 → [docs/rules/13-document-priority.md](docs/rules/13-document-priority.md)
- 14장 병행 개발 규칙 (에이전트 둘 이상이 동시에 일할 때) → [docs/rules/14-parallel-development.md](docs/rules/14-parallel-development.md)
- TODO 2장 구현 사항 > 문서 및 테스트 → [docs/rules/15-runbook-writing.md](docs/rules/15-runbook-writing.md)
- CLAUDE 「아키텍처」 — 계산 파이프라인 · 계층과 경계 · DB 두 개 → [docs/rules/16-layers-and-boundaries.md](docs/rules/16-layers-and-boundaries.md)
- 닫힌 항목(TODO 1장 · 2장 · 4장에서 닫은 것) → [docs/records/closed.md](docs/records/closed.md)
- TODO 3장 결정 기록 → [docs/records/decisions.md](docs/records/decisions.md)
- design_rules 6장 · 8장 결정 기록 → [docs/records/design_rules_log.md](docs/records/design_rules_log.md)
