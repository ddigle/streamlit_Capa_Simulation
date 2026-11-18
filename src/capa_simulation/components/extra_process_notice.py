# Purpose: 부대공정 판을 합친 결과(합침 · 뺌 · BDQ 에 생김)를 알림창 · Alarm 한 줄로 담는다.

"""등록 · 부대공정 얹기 · 파생 저장의 부대공정 결과 알림 한 꼴(설계 3-4 등록 쪽 · A8).

알림창 짧은 글은 「부대공정 2 합침」 · 「부대공정 1 합침 · 1 뺌」 만이고, 뺀 · BDQ 에 생긴 공정과
까닭은 Alarm 전문에 둔다. 뺀 · BDQ 에 생긴 공정이 있거나 판을 합치지 못했으면(예외 — BDQ 만으로
등록함) 경고, 모두 합쳤으면 알리기만 한다. 저장은
끝났고 그 자리에 고칠 입력이 없어 알림창 · Alarm 에만 낸다(설계 규칙 UI-NTF-03). 조건이 남아 있는
동안의 상태 알림(`EP-03` · `EP-04` — 최신 공식버전 기준)은 Admin 「부대공정」 탭이 낸다.
"""

from __future__ import annotations

from capa_simulation.components.flash import queue_flash
from capa_simulation.services.extra_process_merge import ExtraMergeReport


def extra_report_message(report: ExtraMergeReport) -> str:
    """알림 글(마크다운 원문) — 첫 줄이 짧은 글, 그 아래 목록이 까닭."""
    lines = report.detail_lines()
    if not lines:
        return report.flash_text()
    return "\n\n".join([report.flash_text(), "\n".join(f"- {line}" for line in lines)])


def queue_extra_report(key: str, report: ExtraMergeReport) -> None:
    """판을 합친 결과를 칸 `key` 에 담는다. 판이 없었으면 아무것도 담지 않는다."""
    if report.version is None:
        return
    if report.dropped or report.graduated or report.failed is not None:
        queue_flash(
            key,
            extra_report_message(report),
            kind="warning",
            icon=":material/warning:",
            popup_only=True,
        )
        return
    queue_flash(key, report.flash_text(), kind="info", popup_only=True)
