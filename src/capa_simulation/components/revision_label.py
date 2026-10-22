# Purpose: 리비전 선택지·이름 줄에 쓰는 「r{번호} · {리비전명}」 글자를 한 곳에서 만든다.

"""리비전을 사람에게 가리킬 때 쓰는 글자.

시나리오 관리 카드·사이드바 시나리오 팝업·HOME 비교 리비전·파생 원본 리비전·월 머지 표가 모두 이
글자로 리비전을 보인다. 리비전명은 고칠 수 있으므로(`DuckDBScenarioRepository.rename_revision`) 이
글자도 바뀐다 — 이것을 선택지 글자로 쓰는 상자는 위젯 앞에서 매 회차 고른 id 를 다시 적는다
(AGENTS 9장 「글자가 바뀌는 것을 피할 수 없는 상자」). 번호가 리비전을 늘 가르므로 같은 이름도 된다.

마크다운으로 그리는 자리(라디오 선택지·캡션·알림)에 실을 때는 부르는 쪽이
`literal_markdown` 으로 감싼다. 선택 상자 글자는 마크다운이 아니라 그대로 둔다.
"""

from __future__ import annotations

from capa_simulation.persistence.models import RevisionSummary


def revision_label(revision: RevisionSummary) -> str:
    """「r3 · 필터저장」. 상태(공식·올라와 있음 등)는 넣지 않는다 — 그것은 캡션이 말한다."""
    return f"r{revision.revision_no} · {revision.revision_name}"
