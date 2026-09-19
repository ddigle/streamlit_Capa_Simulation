# 화면 디자인 규칙

마지막 갱신일: 2026-09-10

이 문서는 색·서체·표 밀도를 어디서 정하고 어떻게 쓰는지 규정한다. 규칙이 없으면 토큰을
만들어도 다시 갈라진다. 실제로 갈라져 있었다 — 같은 "분류 컬럼 음영"이 HOME은
`#F4F4F5`, 편집 페이지 3곳은 팔레트 밖 `#F0F2F6`이었고, 같은 "흐린 텍스트"가
`#52525B`와 `#71717A`로 나뉘어 있었다.

## 1. 단일 근거

```text
.streamlit/config.toml  [theme]        브라우저 크롬(위젯·사이드바·기본 서체)
        ↕ 1:1 대응
src/capa_simulation/design/tokens.py   파이썬이 그리는 Plotly·Altair·CSS
```

Streamlit 위젯은 `config.toml`을 직접 읽지만 Plotly Figure와 주입 CSS는 읽지 않는다.
그래서 같은 값을 `tokens.py`에 한 번 더 선언하고, **화면 코드는 토큰만 참조한다.**
두 파일 중 하나를 고치면 다른 하나도 같은 변경에서 맞춘다.

한쪽만 고치는 실수는 `tests/test_design_tokens.py`가 잡는다. 최상위 `[theme]`의 단일
색 항목과 대응 토큰을 1:1로 비교한다(대조 범위는 4장). 실제로
`dataframeHeaderBackgroundColor`가 `#E4E4E7`, `HEADER_BACKGROUND`가 `#E4E7EB`로 갈라져
있었다. `st.dataframe` 헤더와 Plotly 표 헤더가 서로 다른 회색이었는데 두 표를 나란히
놓기 전에는 눈에 띄지 않았다.

### 제목 서체도 같은 근거를 따른다

`[theme]`에 `headingFont`가 없으면 제목은 Streamlit 기본 Source Sans로 그려진다. 그 폰트에는
한글 글리프가 없어 **한글 제목만 브라우저 폴백 face로 넘어간다.** 같은 줄상자
(`headingFontSizes[0]` 40px × line-height 1.2)에서 폴백 face의 잉크 상단 위치가 라틴과 달라,
영어 제목 페이지(`HOME`의 `Capa LOB Summary`)와 한글 제목 페이지(`부하량`)의 제목·헤더 간격이
서로 다르게 보였다. 여백 문제가 아니라 서체 문제였다.

그래서 `headingFont`를 `tokens.FONT_FAMILY`와 **같은 문자열**로 선언한다. 한 face로 통일해야
간격이 언어에 따라 어긋나지 않는다. `tests/test_design_tokens.py`의
`test_heading_font_matches_the_token_stack`이 두 선언이 갈라지는 것을 막는다.

스택은 `Noto Sans KR` 을 앞에 두고 `Malgun Gothic` 을 폴백으로 받친다. Malgun 은 Windows 에
항상 있어 안전하지만 자간과 획 굵기가 고르지 않다. **사내 PC 에 Noto Sans KR 이 설치돼 있는지는
확인되지 않았다** — 없으면 사내는 Malgun 으로 폴백되어 개발 PC 와 다르게 보인다. 어느 쪽이든
한 화면 안에서는 제목·본문·차트가 모두 같은 face 라 간격은 일정하다.

Streamlit은 `headingFont` 값에 콜론이 없으면 문자열 전체를 폰트 이름으로 넘긴다
(`runtime/theme_util.py`의 `_parse_font_config`). 스택에 콜론을 넣으면 `<이름>:<URL>` 형식으로
오인되므로 넣지 않는다.

## 2. 지켜야 할 규칙

- **파이썬 코드에 색 리터럴을 쓰지 않는다.** `tests/test_design_tokens.py`가
  `app.py`·`app_pages/`·`src/` 전체를 검사해 `#RRGGBB`·`rgb()`·`rgba()`가 `tokens.py` 밖에
  있으면 실패한다. 투명·히트 타깃 같은 기술 상수도 `tokens.TRANSPARENT`·`tokens.HIT_TARGET`
  으로 참조한다.
- **서체는 `tokens.FONT_FAMILY`를 쓴다.** `"Malgun Gothic"` 단독 지정은 금지다. Windows
  전용 서체라 다른 OS에서 서체와 함께 **컬럼 폭 계산까지** 어긋난다. 숫자를 정렬해 보여야
  하는 자리는 `FONT_FAMILY_NUMERIC`을 쓴다.
- **토큰 이름은 값이 아니라 역할이다.** `BORDER`와 `STATUS_SECURE`는 현재 둘 다 zinc-300
  이지만 확보 상태색을 조정할 때 표 테두리가 함께 바뀌면 안 되므로 따로 둔다. 값이 같다고
  합치지 않는다.
- **Plotly Figure는 배경과 서체를 토큰에서 가져온다.** 예전에는 `design/plotly_theme.py`의
  `base_layout()`을 거치라고 규정했지만 그 모듈을 부르는 곳이 한 곳도 없었고, Figure마다
  여백과 높이가 실제로 달라 공통 레이아웃으로 묶이지 않았다. 그래서 그 파일은 지웠고
  전체 레이아웃을 강제하는 진입점은 지금 없다. 값은 `tokens`에서만 가져오면 되고, 그
  이탈은 `tests/test_design_tokens.py`가 이미 검사한다. Figure 공통 유틸리티는
  `components/plotly_layout.py`에 있는데 제목·테두리·분기 경계·고정 행처럼 여러 Figure가
  실제로 똑같이 그리는 조각만 담는다. 새 헬퍼도 같은 기준으로, 실제 호출부와 함께 만든다.
- **Figure 의 `paper_bgcolor`·`plot_bgcolor` 는 `CHART_CANVAS` 다.** 모든 Figure 는 배경이
  투명한 `st.container(border=True)` 안에 놓여 페이지 바탕 위에 그려진다. 흰 면(`SURFACE`)
  을 쓰면 Figure 만 흰 사각형으로 떠서 컨테이너 테두리 안이 두 색으로 갈린다. 표의 셀
  채움색은 그대로 `SURFACE` 이고, 바뀌는 것은 셀 바깥의 캔버스뿐이다.
- **범주형 색은 항상 명시 scale로 넘긴다.** Altair에 `scale`을 주지 않으면 `config.toml`의
  `chartCategoricalColors` 4색을 순환한다. 설비 상태는 9종이라 5~9번째가 앞의 것과 같은
  색으로 그려졌다.

## 2-1. 면의 층

페이지 바탕은 흰색이 아니라 `#F7F8FA`다. 표와 카드가 흰 면(`SURFACE`)이라 바탕 위로
떠 보이고, 밀도 높은 화면에서 어디까지가 한 덩어리인지 테두리에만 의존하지 않고 읽힌다.
사이드바는 흰 면이라 본문 바탕과 층이 나뉜다.

| 역할 | 토큰 | 값 |
|---|---|---|
| 페이지 바탕 | `SURFACE_PAGE` | `#F7F8FA` |
| 표·카드 면 | `SURFACE` | `#FFFFFF` |
| Plotly 캔버스 | `CHART_CANVAS` | `#F7F8FA` |
| 분류 컬럼 음영 | `SURFACE_CLASSIFICATION` | `#F1F3F6` |
| 표 머리글 | `HEADER_BACKGROUND` | `#E4E7EB` |
| 가로막대 트랙 | `BAR_TRACK` | `#E1E5EA` |
| 테두리 | `BORDER` | `#DDE0E5` |
| 상단 띠 | `HEADER_BAR` | `#EFF1F5` |

가로막대 트랙(`BAR_TRACK`)은 상세 B/N 공정 시트에서 막대 길이 눈금(확보율 80~150%)의 전체
구간을 보여주는 홈이다. 표 머리글·스크롤바 트랙과 값이 가깝지만 역할이 달라 별도 토큰이며,
그 둘을 재사용하지 않는다. 셀 면(`SURFACE`) 대비 1.27:1 로 홈이 먼저 읽히고, 그 위의 확보
막대(`STATUS_SECURE`)와는 1.17:1 뿐이라 막대의 끝은 테두리(`LINE`, 트랙 대비 8.25:1)를
`BAR_OUTLINE_WIDTH_PX` 굵기로 그어 만든다.

상단 띠(화면 맨 위 `3.75rem`)는 본문 너비만 덮는 `stHeader` 와 사이드바 위쪽을 같은 색으로
이어 붙여 만든다. 한쪽만 칠하면 색이 화면 중간에서 끊겨, 같은 줄에 놓인 앱 이름과 문의처가
서로 다른 면 위에 앉는다. 칠하는 곳은 `components/app_header.py` 한 곳이다.

## 2-2. 강조색은 상호작용에만 쓴다

`ACCENT`(`#0F766E`)는 버튼·포커스·활성 탭·구획 제목 앞 막대처럼 **누를 수 있거나 지금
보고 있는 곳**을 가리킬 때만 쓴다. 데이터의 의미를 담지 않는다. 데이터의 의미는 상태색과
계열색이 담당한다.

강조색을 회색(`#3F3F46`)에서 teal 로 바꾼 이유는 버튼과 포커스가 배경과 구분되지 않아
화면이 눌린 상태처럼 보였기 때문이다. 상태색이 주황·장미 계열이라 색상이 겹치지 않고,
상태색은 표·차트 안에만 있어 강조색과 나란히 놓이지 않는다.

측정한 대비: 흰 글자 위 5.47:1, 새 바탕 위 보조 텍스트(`TEXT_MUTED` `#646973`) 5.19:1,
본문(`TEXT`) 16.67:1. 보조 텍스트는 기존 `#71717A` 가 새 바탕에서 4.55:1 로 빠듯해
함께 낮췄다.

## 3. 상태색은 휘도가 단조 감소해야 한다

확보 → 경고 → 부족 순으로 **어두워진다**. 색만으로 심각도를 인코딩하면 흑백 출력과
적록색각 이상에서 순서를 읽을 수 없으므로, 명도 자체가 순서를 담아야 한다.

| 상태 | 색 | 상대 휘도 | 검은 글자 대비 |
|---|---|---|---|
| 확보 | `#D4D4D8` | 0.660 | 11.99:1 |
| 경고 | `#FB923C` | 0.414 | 7.83:1 |
| 부족 | `#F43F5E` | 0.236 | 4.83:1 |

이전 팔레트는 경고(`#FDE68A`, 0.793)가 확보(0.660)보다 **밝아** 순서가 거꾸로 읽혔다.
`test_design_tokens.py`가 단조 감소를 검사한다.

색 외 채널(패턴·아이콘·수치 라벨)을 하나 더 얹는 것은 아직 하지 않았다. 색 단독 인코딩을
완전히 벗어나려면 필요하다.

## 3-1. 융기는 사이드바 네비게이션 전용이다

이 앱에는 그림자가 **사이드바 페이지 링크 한 군데**밖에 없다. 화면 어디에도 융기가 없기
때문에 거기서만 쓰면 장식이 아니라 신호가 된다 — **떠 있는 것이 지금 있는 곳**이다.

| 상태 | 표현 |
|---|---|
| 평소 | 납작. 투명 1px 테두리로 자리만 예약해 옮겨 다닐 때 글자가 흔들리지 않는다 |
| hover | `translateY(-1px)` + `0 2px 6px NAV_SHADOW` |
| 현재 페이지 | 떠오른 채 유지 + `0 0 0 3px NAV_ACTIVE_RING` + `SURFACE` 면 + `ACCENT` 글자 |

- **현재 페이지는 hover 에서 더 움직이지 않는다.** 마우스에 반응하면 "지금 여기" 가 아니라
  "누를 수 있는 것" 으로 읽힌다.
- 토큰은 둘로 나눠 둔다 — `NAV_ACTIVE_RING`(ACCENT 기반, 색)과 `NAV_SHADOW`(TEXT 기반, 깊이).
  값이 겹쳐 보여도 역할이 다르므로 합치지 않는다.
- 활성 판정은 **파이썬**이 한다. 활성 링크에 `aria-current` 도 안정적인 클래스도 없어
  (emotion 해시뿐) CSS 로는 가릴 수 없다. `st.navigation()` 이 돌려주는 페이지의
  `url_path` 가 곧 링크의 `href` 라 그것으로 선택자를 만든다.
- **`:hover`·`:focus-visible` 을 같은 묶음에 함께 적는다.** Streamlit 이 emotion 으로 까는
  `.st-emotion-cache-XXXX:hover` 의 특정도 (0,2,0) 가 속성 선택자 없는 규칙을 이긴다.
  의사클래스를 붙이면 우리가 이기므로 `!important` 는 필요 없다.

이 규칙을 다른 화면으로 넓히지 않는다. 그림자가 흔해지는 순간 네비게이션의 신호가 사라진다.

## 4. 의도적으로 분리한 것

- **Space 배치도 팔레트**(`SPACE_*`)는 zinc가 아니라 blue-grey다. FAB 도면 관례에 맞춘
  하위 팔레트이며 표·차트와 섞어 쓰지 않는다.
- **월 스크롤 임계**가 상세표 8, HOME 대시보드 10으로 다르다. 두 화면의 밀도가 달라
  유지하되 같은 개념이므로 `tokens.py`에 나란히 두어 차이가 보이게 했다.
- **`[theme]` ↔ 토큰 1:1 대조에서 빠지는 것**이 둘 있다. `[theme.sidebar]` 하위 블록은
  사이드바 전용 팔레트라 본문 토큰과 값이 달라도 되므로 파서가 통째로 건너뛴다. 같은
  `[theme]` 안이라도 `chartCategoricalColors`처럼 색 목록으로 적힌 항목은 단일
  `#RRGGBB` 한 줄만 읽는 파서에 걸리지 않아 대조되지 않는다. 실제로 대조되는 것은
  최상위 단색 8개(`primaryColor`·`backgroundColor`·`secondaryBackgroundColor`·`textColor`·
  `borderColor`·`grayColor`·`dataframeBorderColor`·`dataframeHeaderBackgroundColor`)뿐이고,
  나머지는 손으로 맞춰야 한다.
- **위젯 고정 px 폭은 그대로 둔다.** 더 손대지 않기로 닫혔다
  (`docs/TODO.md` 3-1 [결정]). Streamlit 가로 컨테이너는 `flex-wrap: wrap`이라 폭이
  모자라면 다음 줄로 접힐 뿐이고, 앱을 띄워 `scrollWidth == clientWidth`까지 재 보니
  잘리지도 가로 스크롤이 생기지도 않았다.

## 5. 아직 남은 것

- **표가 `staticPlot` Plotly SVG다.** 정렬·검색(Ctrl+F)·텍스트 선택·복사·키보드 이동·
  스크린리더가 모두 없고 긴 분류값은 말줄임 없이 잘린다. 실제 `<table>`로 바꾸는
  중기안은 진행하지 않기로 닫혔고(`docs/TODO.md` 3-2 [결정]), 표가 그림이라 못 하는
  것은 모든 결과표에 붙어 있는 `CSV 다운로드`가 대신한다. 화면 안에서 그대로 다루는
  방법은 여전히 없다.
- ~~다크 테마가 없다.~~ **넣었다**(2026-09-19). `config.toml` 의 `[theme]`·`[theme.dark]`
  가 Streamlit 이 그리는 것(위젯·사이드바·알림)을 맡고, `design/tokens.py` 의 `_LIGHT`·
  `_DARK` 두 팔레트가 우리 Figure 를 맡는다. 둘이 갈라지면 한 화면에서 위젯만 밝고 그림만
  어두워지므로 `tests/test_design_tokens.py` 가 양쪽을 대조한다.
  - **쓰는 쪽은 한 글자도 바뀌지 않았다.** `tokens.SURFACE` 가 그대로다 — 이름이 모듈에
    없어 파이썬이 `__getattr__` 을 부르고 그때 지금 세션의 팔레트에서 꺼내 준다(PEP 562).
    호출부가 414 곳이라 그것을 전부 고치는 것은 답이 아니었다.
  - **테마는 세션마다 다르다.** 모듈 전역에 담으면 한 사용자가 어둡게 쓰는 동안 동시에
    도는 다른 세션까지 어두워진다. `design/theme.py` 가 스레드에 담고, 실행 첫머리에
    한 번만 해석한다(접근마다 읽으면 rerun 당 3.83ms, 한 번이면 0.05ms).
  - **면의 층은 방향이 뒤집힌다.** 어두운 바탕에서는 위로 올라온 면이 밝다. 같은 방향을
    유지하면 합계 행이 배경에 가라앉는다.
  - 색이 구워진 캐시는 세션 Figure 캐시 하나뿐이라(전역 캐시 32개를 전수 확인했다)
    테마가 바뀌면 그것만 비운다.
  - 전환은 **헤더 오른쪽 Deploy 왼쪽의 버튼**이다(`components/theme_toggle.py`). 누르면
    Streamlit 이 테마를 기억하는 `localStorage` 값을 바꾸고 새로고침하므로 위젯과 Figure 가
    함께 바뀐다. 아무것도 고르지 않으면 브라우저·OS 설정을 따른다.
- **월별 표 두 컴포넌트에 아직 남은 복제**: 테두리·머리선·경계선은 `monthly_table_base`로
  합쳤고 행 경계 주입도 같은 방식(일괄 주입)이다. 남은 것은 `_classification_widths`·
  go.Table 조립·반복 접두 생략 루프 정도이며 실행 시간·화면 결함은 없다(순수 유지보수 비용).
