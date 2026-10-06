# 화면 디자인 규칙

마지막 갱신일: 2026-10-06

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

## 1-1. 서체 규칙 — 자리마다 한 벌 (B 균형형, 2026-10-06 사용자 결정)

입장 화면·Summary 의 「영문·숫자는 Archivo, 한글은 Noto Sans KR」 짝을 본문 화면의 **세 자리**(페이지
제목·상자 제목·큰 숫자)에만 넓힌다. 나머지는 지금 그대로다. `headingFont`(= `FONT_FAMILY`)는 바꾸지
않는다 — 세 자리는 `components/typography.py` 의 스타일이 본문(`stMain`) 안에서만 덮는다.

| 자리 | 서체 · 굵기 · 폭 | 크기 | 정하는 곳 |
|---|---|---|---|
| 페이지 제목(`st.title` h1) | `FONT_FAMILY_DISPLAY` 800 · 폭 100% · 자간 -0.01em | 30px(`headingFontSizes[0]`) | `typography.py` |
| 상자·구획 제목(`####` h4, `st.subheader` h3, h2, HOME 구획 제목 `section_title_markup`) | `FONT_FAMILY_DISPLAY` 700 · 폭 100% | 그대로(h4 16px · h3 19px · 구획 20px) | `typography.py` |
| HOME `Summary` 접힘 제목 | `FONT_FAMILY_DISPLAY` 700 | 20px | `home_rendering.summary_notice_style` |
| 큰 숫자(`st.metric` 값, HOME 결론 줄의 확보율 칸 `typography.FIGURE_CLASS`) | `FONT_FAMILY_DISPLAY` 700 · 숫자 폭 고정(`tabular-nums`) | 그대로(metric 2.25rem · 결론 줄 본문 크기) | `typography.py`·`decision_summary.py` |
| 본문 한글·캡션·알림 | Streamlit 본문 서체 | 14px(`baseFontSize`) | `config.toml` |
| 표·차트 숫자 | `FONT_FAMILY_NUMERIC`(Calibri) | 표마다 | Plotly·`tokens` |
| 사이드바 메뉴·상자 머리글 | 그대로 | 그대로 | `sidebar_style.py` |
| 사이드바 `S.PKG CAPA` 워드마크 | Archivo 800 · 폭 75%(`CapaIntroDisplay`) | — | `intro_summary.py` |
| 입장 화면 워드마크·타이틀·단추·시트의 달 | Archivo 800 · 폭 75%(`CapaIntroDisplay`) | — | `intro_overlay` |
| Summary 차트 숫자 | Archivo 700 · 폭 100%(`CapaIntroNumber`) | — | `intro_overlay` |

`FONT_FAMILY_DISPLAY` 는 `CapaDisplay, ` + `FONT_FAMILY` 다. Archivo 부분 글꼴에는 인쇄 가능한 ASCII 만
들어 있어 한글은 스택의 다음 글꼴(Noto Sans KR → 맑은 고딕 굵게)로 그려진다. 브라우저 실측(8518,
접두 경로 `/proxy/8518/`): 제목 줄 높이는 영문 제목(`Capa LOB Summary`)·한글 제목(`시나리오 관리`) 모두
67.5px 로 스타일을 끈 것과 같고, HOME 결론 상자 높이도 같다. metric 카드는 1px 낮아졌다(99.5 → 98.5).

**글꼴 파일과 전달.** 사내 PC 는 외부 글꼴 서버에 못 나가 Google Fonts 를 부르지 않는다. Archivo 700·800
(폭 100%)의 ASCII 부분 글꼴 둘(`static/fonts/archivo-700.woff2` 8,588B · `archivo-800.woff2` 8,100B,
SIL OFL 1.1 — 같은 폴더 `OFL.txt`)을 **Streamlit 정적 서빙**(`[server] enableStaticServing = true`)으로
보낸다. 주소는 상대 경로 `app/static/fonts/…` 라 접두 경로 아래에서도 맞는다(8518 을
`--server.baseUrlPath proxy/8518` 로 띄워 HOME·하위 페이지 직접 열기·페이지 이동에서 두 글꼴이
`loaded`, 끝 빗금 없는 주소는 Streamlit 이 빗금 붙은 주소로 307). 서버는 woff2 를
`application/octet-stream` 으로 보내지만(`nosniff`) Chrome 은 글꼴의 MIME 을 따지지 않아 그대로 쓴다.
`font-display: swap`, `unicode-range: U+20-7E`.

data URI 로 스타일에 싣는 길과 비교했다(내장 시드, AppTest HOME 웜 rerun 20회 × 2벌 — 중앙값이
340~441ms 로 회차 잡음이 두 방식 차이보다 커서 HOME 회차 시간으로는 갈리지 않는다). 그래서 그 요소
하나를 따로 쟀다: 정적 서빙은 스타일 1,105B·직렬화+해시 14µs, data URI 는 23,341B·52µs 다. 회차마다
보내야 하는 요소라 data URI 는 매 회차 23KB 를 직렬화·해시하고(10KB 이상이라 Streamlit 메시지 캐시가
두 번째부터 참조로 줄이기는 한다), 정적 파일은 브라우저가 한 번 받아 캐시한다 — 가벼운 정적 서빙을
골랐다. 입장 화면 글꼴 둘은 입장 화면 JS 가 `FontFace` 로 등록하고 워커 캔버스에도 넘기는 따로 된
한 벌이라 합치지 않았다(이름도 `CapaDisplay` 와 갈린다).

부분 글꼴을 다시 받는 법은 `typography.py` 머리 설명에 있다(글자 목록 `FONT_SUBSET_TEXT`).
`tests/test_typography.py` 가 파일·라이선스·상대 경로·외부 서버 없음·`enableStaticServing`·선택자가
본문 안인지를 지킨다.

## 2. 지켜야 할 규칙

- **파이썬 코드에 색 리터럴을 쓰지 않는다.** `tests/test_design_tokens.py`가
  `app.py`·`app_pages/`·`src/` 전체를 검사해 `#RRGGBB`·`rgb()`·`rgba()`가 `tokens.py` 밖에
  있으면 실패한다. 투명·히트 타깃 같은 기술 상수도 `tokens.TRANSPARENT`·`tokens.HIT_TARGET`
  으로 참조한다.
- **서체는 `tokens.FONT_FAMILY`를 쓴다.** `"Malgun Gothic"` 단독 지정은 금지다. Windows
  전용 서체라 다른 OS에서 서체와 함께 **컬럼 폭 계산까지** 어긋난다. 숫자를 정렬해 보여야
  하는 자리는 `FONT_FAMILY_NUMERIC`을 쓴다. 페이지 제목·상자 제목·큰 숫자는 `FONT_FAMILY_DISPLAY`
  (1-1 절)이고, 그 밖의 예외는 첫 접속 입장 화면의 워드마크 서체 하나다(4장).
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

**Streamlit 이 그리는 `st.container(border=True)` 와 `st.metric(border=True)` 는 위 표의 면을
쓰지 않는다.** 테두리만 긋고 배경은 투명해 페이지 바탕이 그대로 비친다. 표의 `SURFACE` 는
우리가 Plotly 로 그리는 표·패널의 채움색이다. 그래서 테두리 상자 안에 테두리 상자나 metric
카드를 넣어도 층은 생기지 않고 선만 두 겹이 된다 — 겹칠지 말지는 **안쪽이 누를 수 있는
칸인가**로 가른다. 누를 수 있으면(링크 카드 등) 테두리가 표적의 경계라 값이 있고, 읽기만
하는 칸이면 `gap` 으로 가른다.

가로막대 트랙(`BAR_TRACK`)은 상세 B/N 공정 시트에서 막대 길이 눈금(확보율 80~150%)의 전체
구간을 보여주는 홈이다. 표 머리글·스크롤바 트랙과 값이 가깝지만 역할이 달라 별도 토큰이며,
그 둘을 재사용하지 않는다. 셀 면(`SURFACE`) 대비 1.27:1 로 홈이 먼저 읽히고, 그 위의 확보
막대(`STATUS_SECURE`)와는 1.17:1 뿐이라 막대의 끝은 테두리(`LINE`, 트랙 대비 8.25:1)를
`BAR_OUTLINE_WIDTH_PX` 굵기로 그어 만든다.

상단 띠(화면 맨 위 `3.75rem`)는 본문 너비만 덮는 `stHeader` 와 사이드바 위쪽을 같은 색으로
이어 붙여 만든다. 한쪽만 칠하면 색이 화면 중간에서 끊겨, 같은 줄에 놓인 사이드바 `S.PKG CAPA`
라벨과 시나리오 글이 서로 다른 면 위에 앉는다. 칠하는 곳은 `components/app_header.py` 한 곳이다.
본문 쪽 띠에는 적용 중인 시나리오 두 줄(위 `TEXT` 600, 아래 `TEXT_MUTED`)과 왼쪽 `ACCENT` 3px 막대,
사이드바 쪽에는 웨이퍼 심볼(링 `TEXT`·다이 `ACCENT`) + `S.PKG CAPA`(Archivo 800 · 폭 75%, 입장 화면
워드마크와 같은 글꼴)를 둔다. 라벨은 앱 테마를 따르고(입장 화면·Summary 의 고정 팔레트와 다르다),
올리면 `SURFACE` 면·`BORDER` 윤곽이 서고 안내 글자 `Summary` 가 `ACCENT` 가 된다. 초점은 `ACCENT` 2px
윤곽이다.

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

## 2-3. 알림 상자 세 색은 뜻으로 가른다

- `st.info` — 조건에 맞는 것이 없다. 사용자가 할 일은 없고 조건을 넓히면 나온다.
- `st.warning` — 입력이 빠져 결과 일부가 비었거나, 고르지 않으면 화면이 이어지지 않는다.
  사용자가 채워야 한다. **찾아봤는데 문제가 있다**(`st.success` 의 짝)도 여기다.
- `st.success` — 찾아봤는데 문제가 없다. 그 짝은 위의 `st.warning` 이다 — 판정 결과를
  알리는 자리는 문제 없음이 초록, 문제 있음이 주황으로 한 쌍이다.

둘 다 맞는 자리는 **`st.warning` 이 이긴다.** 사용자가 할 일이 있으면 그것이 더 급한
정보다 — 조건을 넓히면 나오는지 여부는 그다음이다.

주황은 확보 상태색에서 `경고` 다. 단순 조회 결과 없음에 주황을 쓰면 같은 화면의 표·차트에
있는 주황과 뜻이 어긋난다 — 배지에서 같은 이유로 이미 한 번 정리했다(`docs/TODO.md` 3-4절).
색을 정하는 자리는 `config.toml` 이고 **알림 상자와 배지가 서로 다른 슬롯을 본다** —
`st.success`→`greenColor`, `st.info`→`blueColor`, `st.warning`→`yellowColor` 다. 경고를
주황으로 만드는 것은 `orangeColor` 가 아니라 `yellowColor` 이므로 둘을 같은 값으로 둔다.

**적용·저장하지 않은 편집**도 같은 주황이다 — 사이드바 시나리오 상자의 `미저장 변경` 배지
(`:orange-badge[]`)와, 적용하지 않은 편집이 남은 탭 이름 옆의 점(`tokens.PENDING_MARK`,
`orangeColor` 와 같은 값)이 한 뜻이다.

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

## 3-2. 사이드바 상자는 모양이 아니라 표식으로 용도를 말한다

사이드바 상자는 모두 한 모양이다(폭·높이·모서리·테두리·제목 글자). 모양으로 가르지 않는
대신 **누르면 무슨 일이 일어나는지**를 오른쪽 끝 표식이 늘 보이게 말한다.

| 상자 | 표식 | 뜻 |
|---|---|---|
| 하위 없는 페이지 그룹(Capa Chatbot, 시나리오 관리) | `→` `arrow_forward`, `TEXT_MUTED` | 곧바로 그 화면으로 간다. 지금 보고 있으면 뺀다 |
| 확장 패널 전부(페이지 그룹·조회 조건·Support) | `⌄` `expand_more`, 펴면 뒤집힌다 | 이 자리에서 펼쳐진다 |
| 조회 조건 상자(시나리오·리비전, 조회기간, 화면마다의 조건 카드 — HOME 의 B/N 집계 공정, 생산 계획의 환산 조건 등) | 「조회 조건 · 이 화면에 적용」 구역 제목 아래, 왼쪽 아이콘 `ACCENT` | 지금 화면이 읽는 조건이다 |

- 조건 상자의 `ACCENT` 아이콘은 2-2 의 「누를 수 있는 곳」의 한 갈래다. 눌러서 바꾸는 것이
  화면이 아니라 계산 조건일 뿐이다.
- 조건 상자 셋은 옅은 `ACCENT` 면(`NAV_CONTROL_TINT`, 알파 0.12)을 **안쪽 확장 패널**에 깐다.
  요약 줄과 펼친 몸이 한 장으로 읽히도록 요약 줄의 제 면은 걷되, hover·keyboard focus 때는
  걷지 않는다 — 그 순간 면이 바뀌는 것이 「누를 수 있다」는 신호다.
  - 면 위의 알림은 제 반투명 면이 청록과 섞여 흐려진다(오류 글자 대비 밝게 4.57 → 3.89,
    어둡게 4.51 → 3.71). 알림 밑에 `SURFACE` 를 깔아 면 밖과 같은 색으로 둔다.
  - 면 위에서 공식버전 배지의 경계가 흐려져 1px `BORDER` 윤곽을 준다.
  - 세기는 2026-09-28 에 제안서 시안 그대로 시험 중이다. 되돌릴 때는 이 면을 넣은 커밋
    하나만 되돌리면 표식·아이콘은 남는다.
- 마우스를 올려야 보이는 신호는 쓰지 않는다. Streamlit 이 hover 때 왼쪽 아이콘을 `›` 로
  바꾸므로 `›` 를 「이동」 표식으로 쓰면 같은 기호가 두 뜻이 된다 — 그래서 `→` 다.
- 맨 아래 `Support` 는 다시 목록이라 조건 구역과 **간격**(0.9rem)으로 떨어진다. 「관리」 같은
  제목을 하나 더 세우지 않는다 — 사용자가 없앤 낱말을 되살리고 사이드바만 길어진다.
- **조건 카드**(2026-09-28): 화면 고유의 필터·표시 설정은 본문이 아니라 조회 조건 구역의
  카드다. 조건 상자와 같은 면·아이콘·표식이고(접두어 `condition_card_` 로 서식이 걸린다),
  기본은 접힘, 한 번 편 카드는 탭·페이지를 오가도 편 채다. 쓰기 작업(붙여넣기·등록)은 넣지
  않는다 — 작업은 표 위 작업 줄의 버튼과 팝업이다.

## 3-2-1. 본문은 결과와 행동만, 설명은 Guide

본문에는 표·그림과 그 결과에 대한 행동(적용·붙여넣기·등록), 그리고 상태 알림(오류·제외
경고·적용 완료)만 둔다. 「이 설정은 무엇이고 어떤 순서로 쓰나」는 헤더 테마 버튼 옆 `Guide`
버튼의 대화상자가 말한다(원문 `src/capa_simulation/guides/<페이지>.md`). 가이드가 없는 화면에서는
버튼이 보이지 않는다.

- **작업 줄은 표 위다.** 적용 버튼이 긴 표 아래에 있으면 고친 뒤 보이지 않아 적용을 건너뛴다.
  완료·오류 알림도 작업 줄 바로 아래 — 누른 자리에서 보인다.
- 동작을 좌우하는 짧은 안내(「적용해야 반영된다」)는 Guide 로만 보내지 않고 버튼 툴팁에 남긴다.
- 샘플은 `생산 계획` 하나다. 보고 괜찮으면 다른 화면으로 넓힌다.

## 3-3. 막대는 값 쪽 끝만 둥글다

막대의 값 쪽 끝(세로 막대의 위, 가로 막대의 오른쪽)만 둥글린다. 반경은 **막대 굵기로 고른
등급** 셋이다(`tokens.BAR_CORNER_RADIUS_*_PX`). 같은 반경도 가는 막대에서는 머리 전체가
반원이 된다.

| 등급 | 반경 | 굵기 | 쓰는 곳 |
|---|---|---|---|
| 넓음 `WIDE` | 8px | 40px 이상 | HOME 생산계획 LOB(70px), 가용설비 주차별 설비 현황(Altair, 기본 17주에 53px — 주 수로 등급을 고른다), Space 전환 단계(Altair, 70px 고정) |
| 중간 `MEDIUM` | 5px | 20~40px | Dynamic Capa 공정별 Capa 실현 수준(가로, 25px) |
| 좁음 `NARROW` | 3px | 20px 미만 | HOME B/N Top 5(15px) |

- 반경은 trace 마다 **스칼라**로 준다. plotly.js 3.7 은 점마다 다른 반경 배열을 조용히
  버리고 직각으로 그린다. `layout.barcornerradius` 는 쓰지 않는다 — 증감 조각·hover 표적까지
  둥글어진다.
- Altair 쌓인 막대는 Vega-Lite 가 막대 전체를 둥근 틀로 잘라 그려 조각 사이 이음매가 네모로
  남는다. Plotly 는 부호마다 가장 바깥의 0 아닌 조각만 둥글린다 — 높이 0 조각은 테두리를
  긋지 않아야 머리 위에 납작한 뚜껑이 생기지 않는다.
- 폭이 조회 기간으로 바뀌는 막대(가용설비 Static/Dynamic 비교는 월 수, 주차별 설비 현황은
  주 수)는 그 수로 막대 폭을 어림해 `tokens.bar_corner_radius` 한 함수로 등급을 고른다. 비교
  차트는 넉 달이면 넓음, 열두 달이면 중간, 서른 달이면 좁음이다. 폭의 비율 반경은 넓은
  막대에서 8px 을 훌쩍 넘어 쓰지 않는다.
- `base` 로 띄운 막대(상세 B/N 공정, 주요공정 확보율 칸, 호기 생애주기 Gantt)와 Waterfall 에는
  주지 않는다. 앞의 셋은 네 모서리가 모두 둥근 알약이 되고, Waterfall 은 반경을 받지 않는다.
- **입체감(광택·그림자·그라데이션)은 넣지 않았다**(2026-09-28). 이 앱의 막대 색은 확보·경고·
  부족과 실행 증감을 뜻하는데 광택 띠가 그 색과 섞이고(밝게 부족 막대의 광택 줄이 감소분
  분홍과 OKLab ΔE 6.4), 그림자는 사이드바 「지금 여기」 전용 신호다(3-1).

## 4. 의도적으로 분리한 것

- **Space 배치도 팔레트**(`SPACE_*`)는 zinc가 아니라 blue-grey다. FAB 도면 관례에 맞춘
  하위 팔레트이며 표·차트와 섞어 쓰지 않는다.
- **첫 접속 입장 화면과 Summary 요약 화면**(`components/intro_overlay.py`)은 앱 테마와 무관한
  어두운 한 벌(`tokens.INTRO_PALETTE`)이고, 워드마크·타이틀·`Detail`·`Summary`·시트의 달만 Archivo
  800·폭 75%, 요약 차트의 숫자만 Archivo 700 을 쓴다. 사내망에 외부 글꼴이 없어 이 화면이 쓰는 글자만
  담은 부분 글꼴 둘(SIL OFL 1.1)을 저장소에 두었다. 한글은 `FONT_FAMILY` 그대로다. 제품 비중 도넛은
  다크 테마의 `PRODUCT_SHARE_COLORS` 를 테마와 무관하게 쓰고, 막대 상태색은 웨이퍼 다이 셋(확보·경고·
  부족)이다. 요약 차트의 글자 크기는 한 단계로 맞춘다 — 생산계획 점 위 값(700 14px)과 그 달 이름,
  B/N 막대 밑의 공정 이름·상태(부족 대수)가 모두 14px 이고, 행 이름은 20px 다. 행 이름 아래 설명은
  생산계획의 단위(`Density · 억Gb`) 하나만 둔다(2026-10-03 사용자 결정). 판정 기준 숫자는 사사오입한
  정수 퍼센트로 적는다(AGENTS.md 8장 「판정 기준 표시」). 본문 화면에는 쓰지 않는다. **Summary 를 여는 사이드바 머리칸의 `S.PKG CAPA` 라벨도 이 한 벌을
  쓰지 않는다**(2-1 절) — 웨이퍼 심볼(노치 있는 링 `TEXT` · 다이 3×3 `ACCENT`)과 워드마크를 앱 테마
  색으로 그리고, 입장 화면에서 빌려 오는 것은 워드마크 글꼴(Archivo 800 · 폭 75%) 하나다. 입장 화면의
  어두운 색·떠오르는 움직임은 쓰지 않는다(2026-10-06 사용자 결정 — 툴바의 Summary 단추를 걷고 이
  라벨로 옮겼다). 테마 버튼 바로 오른쪽의 `Print` 단추(`components/print_button.py`)는 Guide 와 같은
  윤곽 단추(본문 글꼴 13px/600 · 모서리 8px · 높이 27px · 테두리 `BORDER` · 글자 `TEXT`)이고 글자만
  둔다(2026-10-05 사용자 결정 — ⋮ 메뉴를 감추며 그 안의 인쇄를 옮겼다).
- **인쇄**는 화면과 따로 다듬는다(2026-10-05 사용자 요청). `app_header.SHELL_STYLE` 의 `@media print`
  하나가 사이드바(펼쳐 있어도)·머리 띠와 툴바 단추·입장 화면/Summary 덮개를 빼고, 본문 폭 상한을 풀어
  종이 폭을 다 쓰게 한다. 색은 `print-color-adjust: exact` 로 화면 토큰 그대로 찍는다 — 인쇄용 팔레트를
  따로 두지 않는다. Vega 차트·CCv2 칸·지표 카드는 쪽 사이에서 자르지 않고(`break-inside: avoid`), 긴
  표·Plotly(월별 표가 Plotly 라 긴 표와 같은 꼴이다)·테두리 상자에는 걸지 않는다. 용지 방향은 인쇄 창에
  맡기고 `@page` 에는 여백(10mm)만 둔다. `st.dataframe` 은 지금 그려진 행만, 월별 표의 가로 스크롤 칸은
  종이 폭에 드는 달만 찍힌다 — 가로로 넓은 표가 보이는 부분만 찍히는 것은 그대로 두고, 인쇄 창의 가로
  방향이나 좁힌 조회기간으로 안내한다(2026-10-06 사용자 결정 A). 어두운 테마의 `Print` 단추는 인쇄용
  팔레트로 바꾸지 않고 먼저 묻는다(`DARK_PRINT_CONFIRM`, 같은 날 결정 B) — 확인이면 화면 색 그대로,
  취소면 아무것도 하지 않는다.
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
- **HOME 만 제목 아래 설명이 없다.** 탭(`Main`·`Preference`·`Past Data`)이 그 자리를 쓰면서
  설명 문구·상세표 토글·세부수량 CSV 를 함께 뺐다(`AGENTS.md` 3장 `app_pages/home.py`).
  빠진 것이 아니므로 다시 넣지 않는다.

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
  - 전환은 **헤더 오른쪽 Deploy 왼쪽의 버튼**이다(`components/theme_toggle.py`). 고른 값의
    정본은 `localStorage` 의 앱 키 `capa-theme`(`THEME_APP_KEY`) 하나이고, Streamlit 이
    페이지 경로마다 따로 두는 테마 키(`stActiveTheme-<경로>-v2`)는 그 사본이다. 누르면 앱 키와
    경로별 키를 함께 바꾸고 새로고침하므로 위젯과 Figure 가 함께 바뀐다. **처음 여는 화면은
    밝은 테마다** — 앱 키가 비었으면 예전 판이 그 경로에 남긴 선택을 한 번 이어받고, 그것도
    없으면 `"Light"` 를 적는다. 브라우저·OS 설정은 따르지 않는다.
    **테마를 바꾸는 길은 이 버튼 하나다** — Streamlit 의 ⋮ 메뉴는 통째로 감춘다(2026-10-05 사용자
    결정, `components/app_header.py`). 메뉴로 고른 Light·Dark 를 다음 로드에 앱 키로 받아들이는
    규칙은 판올림으로 감춤이 풀릴 때를 위한 안전망으로 남긴다(메뉴의 `System` 은 고른 값으로 치지
    않는다). 규칙 전문은 그 모듈 설명의 「키 규칙」이다.
- **월별 표 두 컴포넌트에 아직 남은 복제**: 테두리·머리선·경계선은 `monthly_table_base`로
  합쳤고 행 경계 주입도 같은 방식(일괄 주입)이다. 분류 컬럼 폭 계산(`classification_widths`)과
  `go.Table` 두 벌 조립(`build_split_table_figures`)도 그쪽으로 옮겼다. 남은 것은 두 표가
  각자 적는 반복 접두 생략 루프와 격자·머리선 도우미 호출 여섯 번(테두리 둘·머리선 둘·
  경계선 둘) 정도이며 실행 시간·화면 결함은 없다(순수 유지보수 비용).
