# Purpose: UPEH 가정 입력의 세션 키·기본값을 UI·시나리오 전환 초기화에 나눠 준다.

"""UI 모듈을 import 하지 않아도 읽을 수 있는 「UPEH 가정」 세션 계약.

공정 Capa 상세와 필요 단축 일정이 **같은 세 칸**(%·적용 시작 월·적용 끝 월)을 함께 쓴다 — 한
화면에서 110% 로 둔 채 다른 화면으로 옮겨도 같은 가정으로 이어 본다. 위젯은
`components/upeh_assumption_controls.py` 가 그리고, 시나리오를 바꾸는 길(`scenario_activation`)은 %
칸에 100 을 **적는다**(구간은 조회 조건이라 둔다 — HOME 토글을 푸는 규칙과 같다).
"""

from capa_simulation.services.upeh_assumption import PERCENT_DEFAULT

UPEH_ASSUMPTION_PERCENT_KEY = "upeh_assumption_percent"
UPEH_ASSUMPTION_START_KEY = "upeh_assumption_start_month"
UPEH_ASSUMPTION_END_KEY = "upeh_assumption_end_month"
UPEH_ASSUMPTION_DEFAULT_PERCENT = PERCENT_DEFAULT
