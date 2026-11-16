# Purpose: 시험용 가짜 bigdataquery 의 예외 모듈 — 토큰 파일 없음 종류를 실제와 같은 자리에.

"""가짜 `bigdataquery.exceptions` — 사내 패키지와 같은 모듈 자리 · 이름(2026-11-16 사내 확인)."""


class TokenNotFoundException(Exception):
    """토큰 파일이 없을 때(`getData` · `getTokenTime`)."""
