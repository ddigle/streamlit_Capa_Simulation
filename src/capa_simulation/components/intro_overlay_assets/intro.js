// 첫 접속 입장 화면과 Summary 요약 화면. `intro_overlay.py` 가 이 파일 앞에 OVERLAY_HTML · OVERLAY_CSS ·
// FONT_DATA · NUMBER_FONT_DATA 네 상수를 붙여 등록한다(파일에서 읽은 intro.html · intro.css 와 base64 로
// 바꾼 부분 글꼴 둘).
//
// 오버레이는 컴포넌트 칸이 아니라 document.body 에 붙인 호스트(shadow root)에 그린다. 칸 안에
// 두면 Streamlit 의 머리말·사이드바 쌓임 맥락 아래에 깔리고, 칸은 파이썬이 display:none 으로
// 접어 둔다. 파이썬으로는 아무것도 보내지 않는다 — setStateValue · setTriggerValue 는 rerun 을
// 부르고, 첫 실행 도중이면 그 실행을 끊는다.
//
// **움직임은 메인 스레드에서 돌리지 않는다.** 첫 로딩 동안 메인 스레드는 Streamlit 이 HOME 의 표·
// 그림을 그리느라 수백 ms 씩 막힌다(8514 실측 최대 0.5초). 그래서 심볼·워드마크·원형 펼침·웨이퍼 맵과
// Summary 의 차트(선·막대·시트·도넛·숫자 세기)는 모두 `scene()` 이 **워커의 OffscreenCanvas** 에 그리고,
// HTML 글자·단추·행 이름은 합성기가 돌리는 투명도·이동만 쓰며 시작 시각을 미리 예약한다. 워커나
// OffscreenCanvas 를 못 쓰는 브라우저에서는 같은 `scene()` 을 메인 스레드에서 돌린다(전과 같은 품질).
//
// 요약 값은 Components v2 `capa_intro_summary` 가 따로 보낸다(`intro_summary.py`). 로딩 중에 닿으면
// 워커가 글꼴을 올리고 배치를 끝내 둔다 — Summary 를 누른 뒤에는 그리기만 한다.
//
// 「다 그렸다」는 신호는 `[data-testid="stApp"]` 의 `data-test-script-state` 다(running →
// notRunning). 파이썬이 끝에 표지를 그리는 방식은 `st.stop()` 뒤로는 아무것도 보낼 수 없어 쓸 수
// 없다. 비공식 속성이라 Streamlit 을 올릴 때 확인한다 — 속성이 없으면 인트로가 끝나는 대로
// 버튼을 켠다(덮개가 앱을 가두는 일은 없게 한다).

const HOST_ID = "capa-intro-host";
const FONT_FAMILY = "CapaIntroDisplay";
const NUMBER_FAMILY = "CapaIntroNumber";
// 사이드바 머리칸의 S.PKG CAPA 라벨 id. `intro_overlay.SUMMARY_LABEL_ID` 와 같아야 한다.
const SUMMARY_LABEL_ID = "capa-brand-label";
// 이 탭에서 이미 들어갔다는 표시. 테마 버튼·새로고침은 새 세션을 만들지만 같은 탭이라 다시 띄우지 않는다.
const ENTERED_KEY = "capa-intro-entered";
const EASE = "cubic-bezier(.6,0,0,1)";
const OUT = "cubic-bezier(.16,1,.3,1)";
const READY_STATES = new Set(["notRunning", "compilationError"]);
// theme_toggle 이 곧 한 번 새로고침할 차례면(주소의 테마 인자가 저장된 테마와 다르거나 없으면)
// 그동안은 앱 바탕색 한 장만 보여 주고 인트로를 아낀다. 헤더에 테마 버튼이 서면 새로고침이 없다는
// 뜻이라 바로 시작하고, 실행이 끝나고도 이만큼 조용하거나 최대 시간이 지나도 시작한다.
const THEME_SETTLE_AFTER_RUN_MS = 2000;
const THEME_RELOAD_HOLD_MAX_MS = 10000;
const HINT_AFTER_MS = 5000;
// 계산이 이만큼 넘게 끝나지 않으면 버튼을 켜 HOME 의 진행 막대를 직접 보게 한다.
const FALLBACK_ENTER_MS = 60000;
const POLL_MS = 150;
// 장면 시간표(인트로 시작부터 ms). `scene()` 안에도 같은 값이 있다 — 워커로 보내는 함수는 이 파일의
// 다른 이름을 보지 못한다. 바꾸면 두 곳을 같이 고친다.
const REVEAL_AT_MS = 2600;
const REVEAL_MS = 1200;
// 입장 화면 글자는 원형 펼침이 시작되고 이만큼 뒤에 떠오른다(승인 시안과 같은 값). 원이 그때 이미
// 글자 자리를 거의 덮어 글자가 원 밖에 걸쳐 보이지 않는다.
const TEXT_AFTER_REVEAL_MS = 620;
// Summary 시간표(누른 때부터 ms, 승인 시안 그대로). 워커에는 절대 시각으로 실어 보내므로 장면에
// 같은 값을 두지 않는다. `rows` 는 세 줄(선·막대·시트)이 조립을 시작하는 차이다.
const SUMMARY_TIMING = Object.freeze({
  outMs: 650,
  tuckDelay: 180,
  tuckMs: 520,
  dockMs: 900,
  asofDelay: 500,
  veilAt: 200,
  veilMs: 900,
  lookAt: 700,
  lookMs: 1150,
  chartsAt: 1080,
  openChartsAt: 420,
  rows: [0, 380, 800],
});
// 요약 화면의 웨이퍼: 제자리·같은 크기·같은 속도로 돌며 20% 만 남기고 무채색이 된다(사용자 결정).
const SUMMARY_LOOK = Object.freeze({ fade: 0.2, mono: 1 });
const EXIT_MS = 950;
const FOLD_MS = 850;
// 메인 심볼 — C 링 + 3×3 다이(2026-10-07 사용자 결정, 뷰박스 100). 반지름 41 링의 오른쪽 ±35° 를 열어
// 「C」로 두고(굵기 9 · 둥근 끝), 크기 12 · 모서리 2 다이 아홉을 28 · 44 · 60 에 둔다. 사이드바 라벨
// (`intro_overlay.MARK_RING_PATH` · `MARK_DIE_ORIGINS`)과 탭 아이콘(`static/icons/capa_mark.svg`)이 같은
// 모양이고 `test_intro_overlay` 가 셋을 맞춰 본다. 장면(`scene()`)은 이 이름을 못 보므로 값을 따로 적는다.
const MARK_RING = "M83.59 26.48 A41 41 0 1 0 83.59 73.52";
const MARK_DIES = [28, 44, 60];
// 머리 심볼 모션(2026-10-07 사용자 결정 — 모션 시안 넷 중 셋). 「그리며 모이기」는 다이가 바깥에서
// 시계 방향으로(왼쪽 위부터) 서고 가운데가 마지막이다.
const MARK_DRAW_MS = 1700;
const MARK_SCAN_MS = 1800;
const MARK_SPIN_MS = 1500;
const MARK_DRAW_ORDER = [0, 1, 2, 5, 8, 7, 6, 3];
// 앱에서 Summary 를 열 때 머리 심볼을 다시 그리기 시작하는 때(누른 때부터 ms). 화면이 라벨 쪽으로
// 접히며(FOLD_MS) 머리 자리를 늦게 드러내므로 그 중간쯤이다.
const MARK_REDRAW_AFTER_MS = 400;

export default function (component) {
  // 같은 페이지에서 다시 불리는 경우(테마 변경 등)는 이미 떠 있거나 끝난 것이다.
  if (window.__capaIntro) return;
  const api = (window.__capaIntro = { done: false });
  try {
    boot(api, component.data || {});
  } catch (error) {
    console.error("[capa-intro]", error);
    release();
  }
}

function enteredBefore() {
  try {
    return window.sessionStorage.getItem(ENTERED_KEY) === "1";
  } catch (error) {
    return false;
  }
}

function rememberEntered() {
  try {
    window.sessionStorage.setItem(ENTERED_KEY, "1");
  } catch (error) {
    /* 저장을 못 하면 다음 새로고침에 한 번 더 뜰 뿐이다 */
  }
}

// 덮개를 걷는다. 어떤 실패에서도 이 길을 지나 앱을 돌려준다.
function release() {
  const state = window.__capaIntro;
  if (state) {
    state.done = true;
    try {
      if (state.stop) state.stop();
    } catch (error) {
      /* 멈추는 데 실패해도 덮개는 걷는다 */
    }
  }
  const host = document.getElementById(HOST_ID);
  if (host) host.remove();
  // 사이드바 라벨은 남겨 두고 누를 수 없게만 한다 — 라벨은 앱 이름이기도 하다.
  const label = document.getElementById(SUMMARY_LABEL_ID);
  if (label) {
    label.setAttribute("aria-disabled", "true");
    label.title = (state && state.offTitle) || "";
  }
  setInert(false);
}

// 덮개 아래 앱으로 Tab 이 들어가지 않게 한다. 호스트는 #root 밖(body 직속)이라 영향이 없다.
function setInert(on) {
  const root = document.getElementById("root");
  if (!root) return;
  try {
    root.inert = on;
  } catch (error) {
    /* inert 를 모르는 브라우저에서는 덮개가 클릭만 막는다 */
  }
}

// HTML 글자(타이틀·라벨·단추·사이드바 S.PKG CAPA 라벨)가 쓰는 글꼴. 워커는 따로 받는다(`fontBuffers`).
function registerFont() {
  if (!document.fonts || typeof FontFace === "undefined") return;
  const have = new Set([...document.fonts].map((face) => face.family.replace(/"/g, "")));
  for (const [family, data, weight, stretch] of [
    [FONT_FAMILY, FONT_DATA, "800", "75%"],
    [NUMBER_FAMILY, NUMBER_FONT_DATA, "700", "100%"],
  ]) {
    if (!data || have.has(family)) continue;
    const face = new FontFace(family, `url(data:font/woff2;base64,${data})`, { weight, stretch });
    document.fonts.add(face);
    face.load().catch(() => {});
  }
}

function fontBuffer(data) {
  if (!data) return null;
  const binary = window.atob(data);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes.buffer;
}

function fontBuffers() {
  return [
    { family: FONT_FAMILY, buffer: fontBuffer(FONT_DATA), weight: "800", stretch: "75%" },
    { family: NUMBER_FAMILY, buffer: fontBuffer(NUMBER_FONT_DATA), weight: "700", stretch: "100%" },
  ].filter((font) => font.buffer);
}

// 구멍 반지름을 애니메이션할 수 있게 등록한다(등록하지 않은 사용자 속성은 중간값 없이 뛴다).
function registerHole() {
  try {
    CSS.registerProperty({ name: "--capa-hole", syntax: "<length>", inherits: false, initialValue: "0px" });
  } catch (error) {
    /* 이미 등록됐거나 모르는 브라우저 — 뒤쪽은 구멍이 한 번에 열린다 */
  }
}

// theme_toggle.py 의 place() 와 같은 규칙이다 — 등록 JS 앞에 붙은 `capaTheme`(THEME_RULE_SCRIPT)가 앱 키·
// 지금 경로의 Streamlit 키·⋮ 메뉴 표지로 테마를 정한다. 지금 경로의 Streamlit 키가 그와 다르거나(`stale`)
// 주소의 테마 인자가 다르면 그 스크립트가 고쳐 쓰고 새로고침한다. 여기서는 아무것도 적지 않고 예측만 한다.
// 그 스크립트가 이 파일보다 먼저 돌아 이미 키를 맞추고 새로고침을 걸었으면 예측으로는 알 수 없으므로,
// 그 스크립트가 창에 남긴 표지를 함께 본다.
function themeReloadPending(theme) {
  if (window.__capaThemeReloading === true) return true;
  if (!theme || !theme.param || typeof capaTheme === "undefined") return false;
  const state = capaTheme.resolve(window);
  if (state.stale) return true;
  const mode = state.choice === "Dark" ? "dark" : "light";
  try {
    return new URL(window.location.href).searchParams.get(theme.param) !== mode;
  } catch (error) {
    return false;
  }
}

// 워커와 메인 스레드는 performance.now() 의 기준점이 다르다. 시각은 늘 이 절대값으로 주고받는다.
const absoluteNow = () => performance.timeOrigin + performance.now();

function escapeHtml(text) {
  return String(text).replace(/[&<>"']/g, (ch) => `&#${ch.charCodeAt(0)};`);
}

// 머리 심볼. 링은 글자색, 다이는 강조색이고 가운데만 주황(`die-warn`)이다. 링과 다이를 **두 장의 SVG**
// 로 겹친다 — 링이 도는 움직임(스캔·스핀)을 SVG 안의 `<g>` 가 아니라 바깥 `<svg>` 상자의 transform 에
// 건다. SVG 안 요소의 transform 은 메인 스레드에서만 돌고, 스캔은 로딩 중, 곧 메인 스레드가 막히는
// 동안 돈다 — 바깥 상자라야 브라우저가 합성기로 넘길 여지가 있다. `pathLength` 는 그리며 모이기의 대시
// 길이(100)다.
function brandMark(palette) {
  const dies = [];
  MARK_DIES.forEach((y, row) =>
    MARK_DIES.forEach((x, col) => {
      const fill = row === 1 && col === 1 ? palette["die-warn"] : palette.accent;
      dies.push(`<rect class="die" x="${x}" y="${y}" width="12" height="12" rx="2" fill="${fill}"/>`);
    }),
  );
  return (
    `<svg class="mark-ring" viewBox="0 0 100 100" aria-hidden="true"><path d="${MARK_RING}" pathLength="100" fill="none" stroke="${palette.text}" stroke-width="9" stroke-linecap="round"/></svg>` +
    `<svg class="mark-dies" viewBox="0 0 100 100" aria-hidden="true">${dies.join("")}</svg>`
  );
}

// 머리 심볼의 움직임. 링만 돌고 다이는 제자리다. 끝 모습은 늘 그린 그대로의 심볼이라, 어느 순간에
// 취소해도 그 모습으로 돌아간다. 다음 움직임은 앞 움직임을 걷고 시작한다 — 앞의 끝 모습과 다음의
// 첫 모습이 같아 이음매가 없다. `cancel` 은 이어 걸린 흐름(`settle`)도 끊는다.
function markMotion(host, palette) {
  const ring = host.querySelector(".mark-ring");
  const path = ring.querySelector("path");
  const dies = [...host.querySelectorAll(".die")];
  const core = dies[4];
  const idle = palette["die-idle"];
  let generation = 0;
  const live = [];
  const clear = () => live.splice(0).forEach((animation) => animation.cancel());
  const play = (el, keyframes, options) => {
    const animation = el.animate(keyframes, { fill: "both", ...options });
    live.push(animation);
    return animation;
  };
  const finished = (list) =>
    Promise.all(list.map((animation) => animation.finished)).then(
      () => true,
      () => false,
    );

  // 2 「그리며 모이기」 — 링이 C 의 위쪽 끝에서 펜으로 긋듯 이어지고, 다이가 바깥부터 차례로 튀어나와
  // 서며, 주황 가운데가 마지막에 들어온다. 대시 [100, 110] 을 105 → 0 으로 당긴다 — 틈을 길이보다 길게
  // 두어야 처음 모습에 둥근 끝 점이 남지 않는다.
  function draw(delay) {
    clear();
    const options = { duration: MARK_DRAW_MS, delay };
    const dash = (offset) => ({ strokeDasharray: "100 110", strokeDashoffset: offset });
    const list = [play(path, [{ ...dash(105), easing: "cubic-bezier(.6,0,.2,1)" }, { ...dash(0), offset: 0.45 }, dash(0)], options)];
    MARK_DRAW_ORDER.forEach((index, k) => {
      const start = 0.42 + k * 0.045;
      list.push(
        play(
          dies[index],
          [
            { transform: "scale(0)", opacity: 0, offset: 0 },
            { transform: "scale(0)", opacity: 0, offset: start, easing: "cubic-bezier(.3,1.6,.5,1)" },
            { transform: "scale(1)", opacity: 1, offset: Math.min(0.98, start + 0.16) },
            { transform: "scale(1)", opacity: 1 },
          ],
          options,
        ),
      );
    });
    list.push(
      play(
        core,
        [
          { transform: "scale(0)", opacity: 0, offset: 0 },
          { transform: "scale(0)", opacity: 0, offset: 0.82, easing: "cubic-bezier(.3,1.8,.5,1)" },
          { transform: "scale(1.15)", opacity: 1, offset: 0.93 },
          { transform: "scale(1)", opacity: 1 },
        ],
        options,
      ),
    );
    return finished(list);
  }

  // 3 「검사 스캔」 한 바퀴 — C 의 열린 틈이 한 바퀴 돌고, 틈이 지난 다이부터 회색에서 제 색으로 켜진다
  // (가운데는 마지막). 바퀴 첫머리에 다이를 잠깐 회색으로 되돌리므로 바퀴를 이어 돌려도 끊김이 없다.
  function scan() {
    clear();
    const options = { duration: MARK_SCAN_MS };
    const list = [
      play(
        ring,
        [
          { transform: "rotate(0deg)", easing: "cubic-bezier(.5,0,.5,1)" },
          { transform: "rotate(366deg)", offset: 0.78, easing: "cubic-bezier(.4,0,.6,1)" },
          { transform: "rotate(357deg)", offset: 0.9 },
          { transform: "rotate(360deg)" },
        ],
        options,
      ),
    ];
    dies.forEach((die, index) => {
      const color = die.getAttribute("fill");
      const angle = ((Math.atan2(Math.floor(index / 3) - 1, (index % 3) - 1) * 180) / Math.PI + 360) % 360;
      const lit = die === core ? 0.8 : 0.05 + (angle / 360) * 0.7;
      list.push(
        play(
          die,
          [
            { fill: color, transform: "scale(1)", offset: 0 },
            { fill: idle, transform: "scale(1)", offset: 0.03 },
            { fill: idle, transform: "scale(1)", offset: lit },
            { fill: color, transform: "scale(1.25)", offset: lit + 0.05 },
            { fill: color, transform: "scale(1)", offset: lit + 0.12 },
            { fill: color, transform: "scale(1)" },
          ],
          options,
        ),
      );
    });
    return finished(list);
  }

  // 1 「반동 스핀」 — 뒤로 살짝 감았다가 한 바퀴 돌고, 제자리를 조금 지나쳐 두 번 흔들리며 멈춘다.
  // 멈추는 순간 가운데 다이가 한 번 톡 튄다.
  function spin() {
    clear();
    const options = { duration: MARK_SPIN_MS };
    return finished([
      play(
        ring,
        [
          { transform: "rotate(0deg) scale(1)", easing: "cubic-bezier(.3,0,.6,1)" },
          { transform: "rotate(-30deg) scale(.94)", offset: 0.15, easing: "cubic-bezier(.25,.9,.3,1)" },
          { transform: "rotate(374deg) scale(1.02)", offset: 0.62, easing: "cubic-bezier(.4,0,.6,1)" },
          { transform: "rotate(354deg) scale(1)", offset: 0.76, easing: "cubic-bezier(.4,0,.6,1)" },
          { transform: "rotate(364deg) scale(1)", offset: 0.88, easing: "cubic-bezier(.4,0,.6,1)" },
          { transform: "rotate(360deg) scale(1)" },
        ],
        options,
      ),
      play(
        core,
        [
          { transform: "scale(1)", offset: 0 },
          { transform: "scale(1)", offset: 0.62 },
          { transform: "scale(1.35)", offset: 0.7 },
          { transform: "scale(.92)", offset: 0.78 },
          { transform: "scale(1)", offset: 0.86 },
          { transform: "scale(1)" },
        ],
        options,
      ),
    ]);
  }

  // 다 그린 뒤: 아직 읽는 중이면 스캔을 이어 돌리고, 준비되면 그 바퀴를 마저 돈 다음 스핀 한 번으로
  // 멈춘다. 이미 준비됐으면 스캔 없이 곧장 스핀이다.
  async function settle(isReady) {
    const mine = generation;
    while (!isReady()) {
      if (!(await scan()) || mine !== generation) return;
    }
    if (mine === generation) await spin();
  }

  return {
    draw(delay) {
      generation += 1;
      return draw(delay);
    },
    settle,
    cancel() {
      generation += 1;
      clear();
    },
  };
}

// Summary 의 격자(CSS px). 왼쪽 행 이름 칸 + 여섯 달 칸, 세 줄(선 · 막대 · 시트). 메인 스레드(행 이름
// 위치)와 장면(차트)이 같이 쓴다 — 장면에는 이 함수의 원문을 함께 실어 보낸다. 그래서 **이 함수도
// 바깥 이름을 쓰지 않는다.** 화면이 낮으면 위 두 줄이 줄고 시트 줄만 200px 를 지킨다(스크롤 없음).
// 좁은 화면(760px 이하 — intro.css 의 @media 와 같은 경계)은 행 이름 칸을 없애고 이름을 각 줄 **위**
// 띠(`rows[i].head`)에 올린다 — 칸을 남기면 390px 에서 여섯 달 칸이 30px 로 줄어 글자가 서로 겹친다.
function summaryGrid(W, H) {
  const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
  const narrow = W <= 760;
  const side = narrow ? 16 : clamp(W * 0.045, 16, 64);
  const bottom = clamp(W * 0.03, 16, 36);
  const top = 96;
  const rowGap = 12;
  const gap = narrow ? 6 : 12;
  const labelW = narrow ? 0 : W <= 900 ? 104 : 156;
  const heads = narrow ? [24, 24, 44] : [0, 0, 0];
  const left = side;
  const lead = labelW ? labelW + gap : 0;
  const colW = Math.max(0, (W - side * 2 - lead - gap * 5) / 6);
  const cols = [0, 1, 2, 3, 4, 5].map((i) => left + lead + i * (colW + gap));
  const avail = Math.max(0, H - top - bottom - rowGap * 2 - heads[0] - heads[1] - heads[2]);
  const third = Math.max(200, (avail * 1.45) / 3.53);
  const rest = Math.max(0, avail - third);
  const h0 = rest / 2.08;
  const h1 = (rest * 1.08) / 2.08;
  const y0 = top + heads[0];
  const y1 = y0 + h0 + rowGap + heads[1];
  const y2 = y1 + h1 + rowGap + heads[2];
  const rows = [
    { y: y0, h: h0, head: heads[0] },
    { y: y1, h: h1, head: heads[1] },
    { y: y2, h: third, head: heads[2] },
  ];
  return { left, labelW, colW, gap, cols, rows, narrow, spanX: cols[0], spanW: colW * 6 + gap * 5 };
}

/* ============================================================================================
 * 장면 — 심볼·워드마크·원형 펼침·웨이퍼 맵과 Summary 차트를 캔버스 하나에 그린다.
 *
 * 이 함수는 문자열로 바뀌어 워커에서 돈다(`startScene`). **이 파일의 다른 이름을 하나도 쓰지 않는다**
 * — 필요한 것은 모두 `init` 메시지와 인자(`gridOf` = summaryGrid)로 받고 도우미는 전부 안에 둔다.
 * 워커를 못 쓰면 같은 함수를 메인 스레드에서 `port` 흉내로 돌린다. 시각은 절대값(timeOrigin + now)이다.
 *
 * 메시지: init · begin(at) · progress(reached·total·ready) · resize · summary(값) ·
 *         summary-on(at·charts·rows·look·veil·instant) · view(토글 셋·instant) · pause · resume(크기) ·
 *         stats · stop
 * 회신: stats · summary-ready · hits(말풍선 자리)
 * ============================================================================================ */
function scene(port, gridOf) {
  "use strict";
  const TAU = Math.PI * 2;
  const REVEAL_AT = 2600;
  const REVEAL_MS = 1200;
  const now = () => performance.timeOrigin + performance.now();
  const nextFrame =
    typeof requestAnimationFrame === "function"
      ? (cb) => requestAnimationFrame(cb)
      : (cb) => setTimeout(cb, 16);
  const clamp01 = (v) => Math.min(1, Math.max(0, v));
  // CSS cubic-bezier 와 같은 곡선(뉴턴법 + 이분법).
  function bezier(x1, y1, x2, y2) {
    const cx = 3 * x1;
    const bx = 3 * (x2 - x1) - cx;
    const ax = 1 - cx - bx;
    const cy = 3 * y1;
    const by = 3 * (y2 - y1) - cy;
    const ay = 1 - cy - by;
    const sx = (t) => ((ax * t + bx) * t + cx) * t;
    const sy = (t) => ((ay * t + by) * t + cy) * t;
    const dx = (t) => (3 * ax * t + 2 * bx) * t + cx;
    return (x) => {
      if (x <= 0) return 0;
      if (x >= 1) return 1;
      let t = x;
      for (let i = 0; i < 8; i++) {
        const err = sx(t) - x;
        const d = dx(t);
        if (Math.abs(err) < 1e-6 || Math.abs(d) < 1e-6) break;
        t -= err / d;
      }
      if (!(t >= 0 && t <= 1) || Math.abs(sx(t) - x) > 1e-4) {
        let lo = 0;
        let hi = 1;
        t = x;
        for (let i = 0; i < 40; i++) {
          const v = sx(t);
          if (Math.abs(v - x) < 1e-6) break;
          if (v < x) lo = t;
          else hi = t;
          t = (lo + hi) / 2;
        }
      }
      return sy(t);
    };
  }
  const EASE = bezier(0.6, 0, 0, 1);
  const OUT = bezier(0.16, 1, 0.3, 1);
  const IN = bezier(0.5, 0, 0.75, 0);
  const IN_OUT = bezier(0.42, 0, 0.58, 1);
  // 시안의 숫자 세기 곡선(빠르게 오르고 길게 내려앉는다).
  const COUNT = bezier(0.16, 1, 0.3, 1);
  function parseColor(value) {
    const c = String(value || "").trim();
    if (c[0] === "#") {
      const hex = c.length === 4 ? c.slice(1).split("").map((ch) => ch + ch).join("") : c.slice(1, 7);
      const n = parseInt(hex, 16);
      return [(n >> 16) & 255, (n >> 8) & 255, n & 255, 1];
    }
    const m = c.match(/rgba?\(([^)]+)\)/);
    if (m) {
      const p = m[1].split(/[\s,/]+/).filter(Boolean).map(Number);
      return [p[0] || 0, p[1] || 0, p[2] || 0, p.length > 3 ? p[3] : 1];
    }
    return [0, 0, 0, 1];
  }
  const rgba = (c, a) => `rgba(${c[0]}, ${c[1]}, ${c[2]}, ${a})`;
  const mix = (a, b, k) =>
    `rgb(${Math.round(a[0] + (b[0] - a[0]) * k)}, ${Math.round(a[1] + (b[1] - a[1]) * k)}, ${Math.round(a[2] + (b[2] - a[2]) * k)})`;

  let canvas = null;
  let g = null;
  let W = 0;
  let H = 0;
  let dpr = 1;
  let pal = {};
  let brand = "";
  let reduce = false;
  let fontStack = "sans-serif";
  let numStack = "sans-serif";
  let bodyStack = "sans-serif";
  let frame0 = [0, 0, 0, 1];
  let surface = [0, 0, 0, 1];
  let textColor = [255, 255, 255, 1];
  let initAt = 0;
  let beginAt = 0;
  let reached = 0;
  let total = 5;
  let ready = false;
  let stopped = false;
  let paused = false;
  let looping = false;
  let shown = 0;
  let settle = 0;
  let last = 0;
  const stats = { frames: 0, slow: 0, max: 0 };
  let symbolDies = [];
  let mapDies = [];
  let fontsReady = Promise.resolve();
  // 가운데 심볼 링의 길이(뷰박스 100 단위): 반지름 41 원에서 오른쪽 ±35° 를 뺀 호. 모양은 머리 줄의
  // 메인 심볼과 같다 — 장면은 바깥 이름을 못 보므로 값을 그대로 적는다.
  const RIM_OPEN = (35 * Math.PI) / 180;
  const RIM_LEN = 41 * (TAU - 2 * RIM_OPEN);

  // ---- Summary 상태
  let sum = null;
  let sumL = null;
  let sumAt = 0;
  let rowsAt = null;
  const look = { fade: 1, mono: 0 };
  let lookTween = null;
  let veil = 1;
  let veilTween = null;
  let accentColor = [0, 0, 0, 1];

  // ---- 머리 줄 토글 셋(선행 B/O·선행 입고·GAP). `viewWant` 는 켜려는 모습(0·1)이다. 움직임은 달마다 하나씩의
  // 트윈(`months` — 달 하나 `ms`, 달 사이 시차 `lag`, ease-out)과 축처럼 한 번에 움직이는 트윈(`all`)이다. 누를
  // 때마다 **지금 값에서** 새 목표로 트윈을 다시 건다 — 움직이는 중에 다시 눌러도 튀지 않고 이어 간다. 아직
  // 출발하지 않은 달만 시차를 두고, 남은 거리가 짧으면 그만큼 빨리 닿는다. 켜고 끄는 두 방향 모두 ease-out 이라
  // 끌 때도 누르는 즉시 움직인다. 움직임을 줄인 사용자에게는 바로 바뀐다.
  const VIEW_MOTION = {
    bo: { ms: 600, lag: 70 },
    ship: { ms: 420, lag: 80 },
    gap: { ms: 480, lag: 80 },
  };
  const VIEW_MONTHS = 6;
  const viewWant = { bo: 0, ship: 0, gap: 0 };
  const rest = (v) => ({ from: v, to: v, start: 0, dur: 0 });
  const viewTween = {};
  for (const ch of Object.keys(viewWant)) {
    viewTween[ch] = { all: rest(0), months: Array.from({ length: VIEW_MONTHS }, () => rest(0)) };
  }
  // 그리는 순간의 시각. `draw` 가 맨 앞에서 맞춘다.
  let viewAt = 0;
  function tweenValue(tw, t, ease) {
    if (tw.dur <= 0 || t >= tw.start + tw.dur) return tw.to;
    if (t <= tw.start) return tw.from;
    return tw.from + (tw.to - tw.from) * ease((t - tw.start) / tw.dur);
  }
  function retarget(ch, want, t, instant) {
    const motion = VIEW_MOTION[ch];
    const state = viewTween[ch];
    state.months = state.months.map((tw, i) => {
      const cur = tweenValue(tw, t, OUT);
      if (instant) return rest(want);
      const waiting = Math.abs(cur - (1 - want)) < 1e-6;
      return { from: cur, to: want, start: t + (waiting ? i * motion.lag : 0), dur: motion.ms * Math.max(0.35, Math.abs(want - cur)) };
    });
    const cur = tweenValue(state.all, t, IN_OUT);
    const span = motion.ms + motion.lag * (VIEW_MONTHS - 1);
    state.all = instant ? rest(want) : { from: cur, to: want, start: t, dur: span * Math.max(0.35, Math.abs(want - cur)) };
  }
  const monthMix = (ch, i) => tweenValue(viewTween[ch].months[Math.min(i, VIEW_MONTHS - 1)], viewAt, OUT);
  const viewMix = (ch) => tweenValue(viewTween[ch].all, viewAt, IN_OUT);
  // 토글 값 — 켤 수 있는 것(`available`)만. 없으면 null 이라 그 토글은 그림을 바꾸지 않는다.
  function toggleData(key) {
    const t = sum && sum.toggles ? sum.toggles[key] : null;
    return t && t.available ? t : null;
  }

  function build() {
    // 가운데 심볼의 다이 아홉. 중심이 34 · 50 · 66(메인 심볼의 다이 자리 + 크기 절반 6)이고 가운데만
    // 주황이다.
    symbolDies = [];
    for (let y = -1; y <= 1; y++) {
      for (let x = -1; x <= 1; x++) {
        const order = ((Math.atan2(y, x) + Math.PI) / TAU) * 0.7 + (Math.hypot(x, y) / 6) * 0.3;
        const fill = x === 0 && y === 0 ? pal["die-warn"] : pal.accent;
        symbolDies.push({ x: 50 + x * 16, y: 50 + y * 16, order, fill });
      }
    }
    mapDies = [];
    const N = 24;
    for (let i = -N; i < N; i++) {
      for (let j = -N; j < N; j++) {
        const x = (i + 0.5) / N;
        const y = (j + 0.5) / N;
        const r = Math.hypot(x, y);
        if (r > 0.93) continue;
        const edge = r > 0.78;
        const q = Math.random();
        const st = q < (edge ? 0.05 : 0.012) ? 2 : q < (edge ? 0.2 : 0.07) ? 1 : 0;
        mapDies.push({ x, y, r, st, k: Math.random() });
      }
    }
  }

  function resize(width, height, ratio) {
    W = Math.max(1, width);
    H = Math.max(1, height);
    dpr = Math.min(2, ratio || 1);
    if (canvas && !paused) {
      canvas.width = Math.max(1, Math.round(W * dpr));
      canvas.height = Math.max(1, Math.round(H * dpr));
    }
    layoutSummary();
  }

  function loadFonts(list, families) {
    const set = typeof self !== "undefined" && self.fonts ? self.fonts : null;
    if (set && typeof FontFace !== "undefined" && list && list.length) {
      const loads = [];
      for (const font of list) {
        try {
          const face = new FontFace(font.family, font.buffer, { weight: font.weight, stretch: font.stretch });
          set.add(face);
          loads.push(face.load().catch(() => {}));
        } catch (error) {
          /* 글꼴을 못 올려도 본문 글꼴로 그린다 */
        }
      }
      return Promise.all(loads);
    }
    // 메인 스레드에서 돌 때는 문서에 등록한 글꼴을 쓴다.
    if (typeof document !== "undefined" && document.fonts) {
      return Promise.all(families.map((f) => document.fonts.load(`${f.weight} 20px "${f.family}"`).catch(() => {})));
    }
    return Promise.resolve();
  }

  function layout() {
    const S = Math.min(124, Math.max(88, W * 0.1));
    const gap = Math.min(28, Math.max(18, W * 0.024));
    const fs = Math.min(36, Math.max(24, W * 0.03));
    const cx = W / 2;
    const cy = H / 2 - (S + gap + fs) / 2 + S / 2;
    return { S, gap, fs, cx, cy };
  }

  // 가운데 심볼 — 메인 심볼(C 링 + 3×3 다이)을 크게 그린다. 링은 C 의 위쪽 끝(−35°)에서 왼쪽을 돌아
  // 아래 끝(+35°)까지 펜으로 긋듯 이어지고(대시 길이 = 호 길이, 둥근 끝), 다이는 차례로 커지며 선다.
  function drawSymbol(t, L) {
    const k = L.S / 100;
    g.save();
    g.translate(L.cx - 50 * k, L.cy - 50 * k);
    g.scale(k, k);
    const p = EASE(clamp01((t - 260) / 1000));
    if (p > 0) {
      g.beginPath();
      g.arc(50, 50, 41, -RIM_OPEN, RIM_OPEN, true);
      g.lineWidth = 9;
      g.lineCap = "round";
      g.strokeStyle = pal.text;
      g.setLineDash(p < 1 ? [RIM_LEN * p, RIM_LEN + 10] : []);
      g.stroke();
      g.setLineDash([]);
    }
    const base = g.globalAlpha;
    for (const d of symbolDies) {
      const e = OUT(clamp01((t - 780 - d.order * 620) / 320));
      if (e <= 0) continue;
      const s = 12 * (0.3 + 0.7 * e);
      g.globalAlpha = base * e;
      g.fillStyle = d.fill;
      g.beginPath();
      if (g.roundRect) g.roundRect(d.x - s / 2, d.y - s / 2, s, s, 2 * (s / 12));
      else g.rect(d.x - s / 2, d.y - s / 2, s, s);
      g.fill();
    }
    g.globalAlpha = base;
    g.restore();
  }

  // 워드마크. 벌어진 글자가 모여들며(.6em → 0) 흐림이 걷힌다. 글자마다 45ms 씩 늦게 시작한다.
  function drawWord(t, L, alpha) {
    if (t < 1200 || alpha <= 0) return;
    const chars = [...brand];
    g.font = `800 ${L.fs}px ${fontStack}`;
    g.textBaseline = "middle";
    g.textAlign = "left";
    g.fillStyle = pal.text;
    const widths = chars.map((ch) => g.measureText(ch).width);
    const spacing = 0.6 * L.fs * (1 - OUT(clamp01((t - 1200) / 1200)));
    const width = widths.reduce((a, b) => a + b, 0) + spacing * (chars.length - 1);
    let x = L.cx - width / 2;
    const y = L.cy + L.S / 2 + L.gap + L.fs / 2;
    const canBlur = "filter" in g;
    chars.forEach((ch, i) => {
      const e = OUT(clamp01((t - 1200 - i * 45) / 700));
      if (e > 0 && ch !== " ") {
        g.globalAlpha = e * alpha;
        // 캔버스 filter 길이는 비트맵 화소라 setTransform(dpr) 을 따르지 않는다 — CSS 8px 와 같게 dpr 을 곱한다.
        if (canBlur) g.filter = e < 0.99 ? `blur(${(8 * dpr * (1 - e)).toFixed(2)}px)` : "none";
        g.fillText(ch, x, y);
      }
      x += widths[i] + spacing;
    });
    if (canBlur) g.filter = "none";
    g.globalAlpha = 1;
  }

  // 검사 원이 중심에서 퍼지며 다이마다 확보·경고·부족 색이 들어간다. 준비되면 천천히 돈다.
  // 덮인 범위·다이 밝기·검사 원 모두 연속값(shown · settle)에서 나온다 — 준비 순간에도 끊기지 않는다.
  // Summary 에서는 자리·크기·회전 속도는 그대로 두고 투명도(look.fade)와 무채색(look.mono)만 바뀐다.
  function drawMap(clock) {
    const narrow = W <= 760; // intro.css 의 @media (max-width: 760px) 와 같은 경계
    const R = narrow ? Math.min(W * 0.6, H * 0.32) : Math.min(H * 0.6, W * 0.4);
    const cx = narrow ? W * 0.64 : W * 0.7;
    const cy = narrow ? H * 0.28 : H * 0.5;
    const t = reduce ? 0 : clock;
    const front = shown * 1.06;
    const EDGE = 0.07;
    const fade = look.fade;
    if (fade <= 0.003) return;
    const smooth = (v) => {
      const x = clamp01(v);
      return x * x * (3 - 2 * x);
    };
    const muted = parseColor(pal.muted);
    const colors =
      look.mono > 0.001
        ? [pal["die-ok"], pal["die-warn"], pal["die-short"]].map((c) => mix(parseColor(c), muted, look.mono))
        : [pal["die-ok"], pal["die-warn"], pal["die-short"]];
    g.save();
    g.translate(cx, cy);
    g.rotate(t * 0.000035);
    g.globalAlpha = fade;
    g.beginPath();
    g.arc(0, 0, R, 0, TAU);
    g.fillStyle = pal.wafer;
    g.fill();
    const N = 24;
    const sz = (R / N) * 0.8;
    for (const d of mapDies) {
      const cover = smooth((front - d.r) / EDGE);
      const x = d.x * R - sz / 2;
      const y = d.y * R - sz / 2;
      if (cover < 1) {
        g.globalAlpha = fade * (1 - cover);
        g.fillStyle = pal["die-idle"];
        g.fillRect(x, y, sz, sz);
      }
      if (cover > 0) {
        const loading = 0.62 + 0.3 * d.k;
        const resting = 0.5 + 0.3 * (0.5 + 0.5 * Math.sin(t * 0.0012 + d.k * 30));
        g.globalAlpha = fade * cover * (loading + (resting - loading) * settle);
        g.fillStyle = colors[d.st];
        g.fillRect(x, y, sz, sz);
      }
    }
    const ring = 0.75 * smooth((1.04 - front) / 0.14) * (1 - settle);
    if (ring > 0.01) {
      g.globalAlpha = fade * ring;
      g.strokeStyle = pal.accent;
      g.lineWidth = 1.5;
      g.beginPath();
      g.arc(0, 0, Math.max(2, Math.min(front, 1) * R), 0, TAU);
      g.stroke();
    }
    g.globalAlpha = fade * 0.24;
    g.strokeStyle = pal.text;
    g.lineWidth = 1;
    const notch = 0.035;
    g.beginPath();
    g.arc(0, 0, R * 1.02, Math.PI / 2 + notch, Math.PI / 2 - notch + TAU);
    g.lineTo(0, R * 0.985);
    g.closePath();
    g.stroke();
    g.globalAlpha = 1;
    g.restore();
  }

  // 글자 쪽(넓은 화면은 왼쪽, 좁은 화면은 아래)을 바탕색으로 덮어 웨이퍼 맵 위 글자가 읽히게 한다.
  function drawVeil() {
    if (veil <= 0.003) return;
    let grad;
    if (W <= 760) {
      grad = g.createLinearGradient(0, H, 0, 0);
      grad.addColorStop(0, rgba(surface, 1));
      grad.addColorStop(0.38, rgba(surface, 1));
      grad.addColorStop(0.82, rgba(surface, 0));
    } else {
      grad = g.createLinearGradient(0, 0, W, 0);
      grad.addColorStop(0, rgba(surface, 1));
      grad.addColorStop(0.36, rgba(surface, 0.8));
      grad.addColorStop(0.68, rgba(surface, 0));
    }
    g.globalAlpha = veil;
    g.fillStyle = grad;
    g.fillRect(0, 0, W, H);
    g.globalAlpha = 1;
  }

  /* ------------------------------------------------------------------ Summary 차트 */
  const round = (v, d) => (v == null ? "" : Number(v).toFixed(d));
  function niceStep(raw) {
    const pow = Math.pow(10, Math.floor(Math.log10(Math.max(raw, 1e-9))));
    const m = raw / pow;
    return (m <= 1 ? 1 : m <= 2 ? 2 : m <= 5 ? 5 : 10) * pow;
  }
  function rr(x, y, w, h, r) {
    g.beginPath();
    if (g.roundRect) g.roundRect(x, y, w, h, r);
    else g.rect(x, y, w, h);
  }
  function panel(x, y, w, h) {
    rr(x + 0.5, y + 0.5, w - 1, h - 1, 8);
    g.fillStyle = pal.panel;
    g.fill();
    g.strokeStyle = pal["panel-line"];
    g.lineWidth = 1;
    g.stroke();
  }
  function fit(text, max) {
    let s = String(text || "");
    if (g.measureText(s).width <= max) return s;
    while (s.length > 1 && g.measureText(`${s}…`).width > max) s = s.slice(0, -1);
    return `${s}…`;
  }
  function statusColor(key) {
    return key === "secure" ? pal["die-ok"] : key === "warning" ? pal["die-warn"] : pal["die-short"];
  }
  // 막대 밑 둘째 줄 — 부족한 달만 부족 대수를 세우고, 나머지는 상태 이름만 단다.
  const isShort = (b) => b.status === "shortage" && b.short != null && b.short > 0;
  const statusText = (b) => (isShort(b) ? `${sum.text.shortage} ${b.short}대` : sum.text[b.status] || "");
  const valueText = (v, d) => (v == null ? "—" : Number(v).toFixed(d));

  // ---- 글자 자리 맞추기. 배치(`layoutSummary`)에서 한 번만 잰다 — 프레임마다는 그리기만 한다.
  // 사각형은 {x, y, w, h}(CSS px)다.
  const overlaps = (a, b) => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
  // 지금 글꼴(g.font)로 쓴 글자의 상자. y 는 글자 바탕선, px 는 글자 크기다.
  function textBox(text, x, y, align, px) {
    const w = g.measureText(String(text)).width;
    const x0 = align === "left" ? x : align === "right" ? x - w : x - w / 2;
    return { x: x0 - 2, y: y - px * 0.85 - 1, w: w + 4, h: px + 2 };
  }
  // 후보 자리를 차례로 보며 판(frame) 안에 들고 장애물과 겹치지 않는 첫 자리를 고른다. 없으면 null.
  function freeSpot(text, px, spots, obstacles, frame) {
    for (const spot of spots) {
      const box = textBox(text, spot.x, spot.y, spot.align, px);
      const inside =
        box.x >= frame.x && box.y >= frame.y && box.x + box.w <= frame.x + frame.w && box.y + box.h <= frame.y + frame.h;
      if (inside && !obstacles.some((o) => overlaps(box, o))) return { ...spot, box };
    }
    return null;
  }
  // 선분을 3px 마다 작은 상자로 바꾼다 — 글자가 선 위에 얹히는지 볼 때 쓴다.
  function segmentBoxes(x1, y1, x2, y2) {
    const steps = Math.max(1, Math.ceil(Math.hypot(x2 - x1, y2 - y1) / 3));
    const boxes = [];
    for (let k = 0; k <= steps; k++) {
      boxes.push({ x: x1 + ((x2 - x1) * k) / steps - 1, y: y1 + ((y2 - y1) * k) / steps - 1, w: 2, h: 2 });
    }
    return boxes;
  }
  function widest(font, texts) {
    g.font = font;
    return Math.max(0, ...texts.map((t) => g.measureText(String(t)).width));
  }
  // 여러 글자를 한 크기로 폭(max)에 맞춘다. 기본 크기에서 넘치면 비례해 줄이고(0.5px 단위) 바닥(floor)
  // 아래로는 내리지 않는다. 캔버스 글자 폭은 크기에 비례하므로 기본 크기에서 한 번 재면 된다.
  function fitPx(texts, weight, base, floor, family, max) {
    const w = widest(`${weight} ${base}px ${family}`, texts);
    return w <= max ? base : Math.max(floor, Math.floor(((base * max) / w) * 2) / 2);
  }

  // 배치는 값이 닿을 때와 창 크기가 바뀔 때 한 번 정한다. 프레임마다는 그리기만 한다.
  //
  // 머리 줄 토글(선행 B/O·GAP)이 그림을 바꾸는 몫도 **여기서 한 번** 정한다. 변형마다(`base` 기본 · `A`
  // 선행 B/O · `G` GAP · `AG` 둘 다) 선의 축 범위·눈금 글자 자리와 막대의 위끝·기준선 이름표 자리를 따로
  // 잡아 두고, 그리기는 토글 진행만큼 그 사이를 잇는다. `base` 는 토글이 없던 때와 같은 계산이라 셋을 다
  // 끄면 지금 화면 그대로다. 토글 값이 지금 범위 안이면 범위를 그대로 둔다(`extendRange`) — 켜도 축은
  // 제자리이고 값만 차오른다. 범위 밖으로 나가는 값이 있을 때만 그만큼 넓힌다.
  function layoutSummary() {
    if (!sum || !gridOf) {
      sumL = null;
      return;
    }
    const G = gridOf(W, H);
    const n = sum.months.length;
    const line = { x: G.spanX, y: G.rows[0].y, w: G.spanW, h: G.rows[0].h };
    const bars = { x: G.spanX, y: G.rows[1].y, w: G.spanW, h: G.rows[1].h };
    const colX = (i) => G.cols[i] + G.colW / 2;
    const adv = toggleData("advance");
    const cmp = toggleData("comparison");
    // 아래 30px 는 달 이름(14px — 점 위 값 글자와 같은 크기) 자리다.
    const lineTop = line.y + 30;
    const lineBot = line.y + line.h - 30;
    const lineCtx = { line, colX, lineTop, lineBot };
    const range = baseRange(sum.density);
    const rangeA = adv ? extendRange(range, adv.density) : range;
    const rangeG = cmp ? extendRange(range, cmp.density) : range;
    const lineBase = lineLayout(lineCtx, range, sum.density, null, null);
    const lineA = adv ? lineLayout(lineCtx, rangeA, adv.density, sum.density, null) : lineBase;
    const lineG = cmp ? lineLayout(lineCtx, rangeG, sum.density, null, cmp.density) : lineBase;
    const lineAG =
      adv && cmp
        ? lineLayout(
            lineCtx,
            { lo: Math.min(rangeA.lo, rangeG.lo), hi: Math.max(rangeA.hi, rangeG.hi) },
            adv.density,
            sum.density,
            cmp.density,
          )
        : adv
          ? lineA
          : lineG;
    // 막대: 0 에서 시작한다. 기준선과 가장 큰 값이 다 들어오도록 위를 잡는다.
    const rates = sum.bn.filter(Boolean).map((b) => b.rate);
    // 기준은 달마다 하나다(`sum.secure[i]`). 가장 높은 기준선까지 들어오게 잡는다.
    const topSecure = (sum.secure || []).filter((v) => v != null);
    const max = Math.max(130, ...rates.map((r) => r * 1.12), (topSecure.length ? Math.max(...topSecure) : 110) * 1.15);
    // 선행 B/O 로 확보율이 오르는 달(음수 입력)만 위끝을 넓힌다 — 내려앉는 달은 같은 축이다.
    const maxA = adv ? Math.max(max, ...adv.bn.filter(Boolean).map((b) => b.rate * 1.12)) : max;
    // 아래 50px 는 막대 밑 두 줄(공정 이름·상태 — 둘 다 14px) 자리다. 기준선 자리는 정확한 기준이다.
    const barTop = bars.y + 24;
    const barBot = bars.y + bars.h - 50;
    const bw = Math.min(54, G.colW * 0.42);
    // 기준선. 기준은 **달마다** 온다(월별 기준). 같은 값이 이어지는 달끼리 한 구간으로 묶어 그 칸 폭만큼
    // 긋고, 값이 바뀌는 자리는 세로로 이어 계단으로 만든다. 모든 달이 같으면 판 전체를 가로지르는 선 한 줄이다.
    const edgeLeft = (i) => (i === 0 ? bars.x : G.cols[i] - G.gap / 2);
    const edgeRight = (i) => (i === n - 1 ? bars.x + bars.w : G.cols[i] + G.colW + G.gap / 2);
    const barCtx = { G, bars, colX, barTop, barBot, bw, edgeLeft, edgeRight, n };
    const barBase = barLayout(barCtx, sum.bn, max);
    const barA = adv ? barLayout(barCtx, adv.bn, maxA) : barBase;
    const sheet = layoutSheets(G, n);
    // 선행 B/O 를 켠 값 글자. 같은 모양(한 줄·두 줄·접기) 안에서 크기만 다시 맞춘다 — 기본보다 크지 않다.
    sheet.pxA = adv ? sheetValuePx(sheet, [adv.density, adv.wafer], n) : sheet.px;
    const sheets = sheet.cards;
    sumL = {
      G,
      line,
      bars,
      colX,
      lineTop,
      lineBot,
      lineV: { base: lineBase, A: lineA, G: lineG, AG: lineAG },
      barTop,
      barBot,
      bw,
      edgeLeft,
      edgeRight,
      barV: { base: barBase, A: barA },
      sheet,
      sheets,
    };
    postHits();
  }

  // 선의 값 범위(지금 화면 그대로) — 값의 위아래에 폭의 60% 씩 여백을 둔다.
  function baseRange(values) {
    const vals = values.filter((v) => v != null);
    let lo = vals.length ? Math.min(...vals) : 0;
    let hi = vals.length ? Math.max(...vals) : 1;
    const span = Math.max(hi - lo, Math.abs(hi) * 0.02, 0.1);
    lo -= span * 0.6;
    hi += span * 0.6;
    return { lo, hi };
  }

  // 토글이 더하는 값이 범위 안이면 범위를 그대로 돌려준다. 밖으로 나가는 쪽만 그 값 + 범위의 8% 까지
  // 넓힌다 — 점이 판 위끝(lineTop)에 닿아도 값 글자는 판 안이다.
  function extendRange(range, values) {
    const vals = (values || []).filter((v) => v != null);
    if (!vals.length) return range;
    const pad = (range.hi - range.lo) * 0.08;
    const top = Math.max(...vals);
    const bottom = Math.min(...vals);
    const hi = top > range.hi ? top + pad : range.hi;
    const lo = bottom < range.lo ? bottom - pad : range.lo;
    return hi === range.hi && lo === range.lo ? range : { lo, hi };
  }

  // 선 한 변형의 배치. `values` 는 그 변형의 점, `before` 는 선행 B/O 전 점선(없으면 null), `ghost` 는 비교
  // 시나리오 점(없으면 null)이다. 눈금 글자 자리를 고를 때 셋을 모두 장애물로 본다.
  function lineLayout(C, range, values, before, ghost) {
    const { line, colX, lineTop, lineBot } = C;
    const { lo, hi } = range;
    const step = niceStep((hi - lo) / 3);
    const ticks = [];
    for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) ticks.push(v);
    const yLine = (v) => lineBot - ((v - lo) / (hi - lo)) * Math.max(1, lineBot - lineTop);
    const points = values.map((v, i) => (v == null ? null : { x: colX(i), y: yLine(v), v }));
    // 눈금 글자는 왼쪽 끝(기본) → 오른쪽 끝 → 눈금선 아래 왼쪽·오른쪽 차례로, 점·점 위 값·선·달 이름과
    // 겹치지 않는 첫 자리에 단다. 칸이 좁으면 첫 점이 왼쪽 끝 눈금 글자 자리에 온다. 어디에도 자리가
    // 없으면 그 눈금 글자는 쓰지 않는다 — 값은 점 위에 있다.
    const lineObstacles = [];
    const drawn = points.filter(Boolean);
    g.font = `700 14px ${numStack}`;
    for (const pt of drawn) {
      lineObstacles.push({ x: pt.x - 7, y: pt.y - 7, w: 14, h: 14 }, textBox(round(pt.v, 2), pt.x, pt.y - 12, "center", 14));
    }
    for (let k = 1; k < drawn.length; k++) {
      lineObstacles.push(...segmentBoxes(drawn[k - 1].x, drawn[k - 1].y, drawn[k].x, drawn[k].y));
    }
    // 선행 B/O 전 점선과 비교 시나리오 유령 선도 장애물이다(토글을 켠 변형에만 있다).
    for (const series of [before, ghost]) {
      if (!series) continue;
      const marks = series.map((v, i) => (v == null ? null : { x: colX(i), y: yLine(v) })).filter(Boolean);
      for (const pt of marks) lineObstacles.push({ x: pt.x - 5, y: pt.y - 5, w: 10, h: 10 });
      for (let k = 1; k < marks.length; k++) {
        lineObstacles.push(...segmentBoxes(marks[k - 1].x, marks[k - 1].y, marks[k].x, marks[k].y));
      }
    }
    g.font = `500 14px ${bodyStack}`;
    sum.months.forEach((m, i) => lineObstacles.push(textBox(m, colX(i), line.y + line.h - 9, "center", 14)));
    const digits = Math.max(0, -Math.floor(Math.log10(step) + 1e-9));
    g.font = `500 10px ${bodyStack}`;
    const tickLabels = ticks.map((v) => {
      const y = yLine(v);
      const text = `${v.toFixed(digits)}억Gb`;
      const left = line.x + 6;
      const right = line.x + line.w - 6;
      const spot = freeSpot(
        text,
        10,
        [
          { x: left, y: y - 4, align: "left" },
          { x: right, y: y - 4, align: "right" },
          { x: left, y: y + 12, align: "left" },
          { x: right, y: y + 12, align: "right" },
        ],
        lineObstacles,
        line,
      );
      if (spot) lineObstacles.push(spot.box);
      // `dy` 는 눈금선에서 글자 바탕선까지 — 축이 움직이는 동안에는 지금 눈금선 자리에 이만큼 띄워 단다.
      return spot && { text, x: spot.x, y: spot.y, align: spot.align, v, dy: spot.y - y };
    });
    return { lo, hi, step, ticks, tickLabels, yLine, points };
  }

  // 막대 한 변형의 배치. `bn` 은 그 변형의 B/N(달마다 하나 또는 null), `max` 는 막대 축의 위끝이다.
  function barLayout(B, bn, max) {
    const { G, bars, colX, barTop, barBot, bw, edgeLeft, edgeRight, n } = B;
    const yBar = (v) => barBot - (v / max) * Math.max(1, barBot - barTop);
    let lowest = -1;
    bn.forEach((b, i) => {
      if (b && (lowest < 0 || b.rate < bn[lowest].rate)) lowest = i;
    });
    // 막대 위 확보율(15px)과 막대 밑 상태(14px)는 제 칸 폭 안에만 쓴다 — 칸 사이 간격이 옆 칸 글자와의
    // 틈으로 남는다. 넘치면 여섯 칸을 같은 크기로 함께 줄인다(넓은 화면에서는 그대로다).
    const room = Math.max(1, G.colW - 2);
    const shown = bn.filter(Boolean);
    const ratePx = fitPx(shown.map((b) => `${round(b.rate, 1)}%`), 700, 15, 10, numStack, room);
    const statusPx = fitPx(shown.map(statusText), 700, 14, 10, bodyStack, room);
    const thresholds = [
      [sum.warning || [], sum.warning_label || [], [4, 4], true],
      [sum.secure || [], sum.secure_label || [], [1, 4], false],
    ].map(([values, labels, dash, alignLeft]) => {
      const runs = [];
      for (let i = 0; i < n; i += 1) {
        const v = values[i];
        if (v == null) continue;
        const last = runs[runs.length - 1];
        if (last && last.end === i - 1 && last.v === v) last.end = i;
        else runs.push({ start: i, end: i, v, label: labels[i] || `${v}%` });
      }
      return { dash, alignLeft, runs };
    });
    // 기준선 이름표 자리. 기본은 경고 기준이 구간 왼쪽 선 아래, 확보 기준이 구간 오른쪽 선 위다(선 둘이 몇 px
    // 떨어져 있어 양 끝에 나눠 단다). 칸이 좁아 막대·확보율 글자·「최저」·기준선·다른 이름표에 닿으면 같은 쪽의
    // 구간 다른 끝 → 막대 사이 → 선의 다른 쪽 차례로 옮긴다. 어디에도 자리가 없으면 기본 자리에 바탕을 깔아 단다.
    const barObstacles = [];
    g.font = `700 ${ratePx}px ${numStack}`;
    bn.forEach((b, i) => {
      if (!b) return;
      const top = yBar(b.rate);
      barObstacles.push({ x: colX(i) - bw / 2, y: top, w: bw, h: barBot - top });
      barObstacles.push(textBox(`${round(b.rate, 1)}%`, colX(i), top - 7, "center", ratePx));
    });
    if (lowest >= 0) {
      g.font = `600 11px ${bodyStack}`;
      barObstacles.push(textBox(sum.text.lowest, colX(lowest), yBar(bn[lowest].rate) - 30, "center", 11));
    }
    for (const t of thresholds) {
      t.runs.forEach((run, r) => {
        const y = Math.round(yBar(run.v)) + 0.5;
        const x0 = edgeLeft(run.start);
        barObstacles.push({ x: x0, y: y - 1, w: edgeRight(run.end) - x0, h: 2 });
        const prev = t.runs[r - 1];
        if (prev && prev.end === run.start - 1) {
          const py = Math.round(yBar(prev.v)) + 0.5;
          barObstacles.push({ x: x0 - 1, y: Math.min(py, y), w: 2, h: Math.abs(py - y) });
        }
      });
    }
    g.font = `500 10px ${bodyStack}`;
    for (const t of thresholds) {
      for (const run of t.runs) {
        const y = Math.round(yBar(run.v)) + 0.5;
        const start = { x: edgeLeft(run.start) + 6, align: "left" };
        const end = { x: edgeRight(run.end) - 6, align: "right" };
        const across = t.alignLeft ? [start, end] : [end, start];
        for (let i = run.start; i < run.end; i++) across.push({ x: (colX(i) + colX(i + 1)) / 2, align: "center" });
        const sides = t.alignLeft ? [y + 12, y - 4] : [y - 4, y + 12];
        const spots = sides.flatMap((sy) => across.map((p) => ({ ...p, y: sy })));
        const spot = freeSpot(run.label, 10, spots, barObstacles, bars);
        const fallback = { ...spots[0], box: textBox(run.label, spots[0].x, spots[0].y, spots[0].align, 10), backed: true };
        run.spot = spot || fallback;
        barObstacles.push(run.spot.box);
      }
    }
    return { max, yBar, lowest, ratePx, statusPx, thresholds };
  }

  // 말풍선 자리. 그리는 자리와 같은 값으로 메인 스레드에 돌려준다. 그리지 않는 도넛(`box` 0)은 자리도 없다.
  // 선의 점은 토글을 켜면 움직이므로 **켜려는 모습**(`viewWant`)의 자리를 보낸다.
  function postHits() {
    if (!sumL) return;
    const L = sumL;
    const hits = [];
    L.sheets.forEach((s) => {
      if (!s.box) return;
      const r = s.box * 0.36;
      const half = s.box * 0.065;
      let acc = 0;
      for (const [p, share] of sum.mix[s.i] || []) {
        hits.push({ k: "seg", i: s.i, p, cx: s.cx, cy: s.cy, r0: r - half - 3, r1: r + half + 3, a0: acc * TAU, a1: (acc + share) * TAU });
        acc += share;
      }
    });
    const variant = L.lineV[viewWant.bo ? (viewWant.gap ? "AG" : "A") : viewWant.gap ? "G" : "base"];
    variant.points.forEach((pt, i) => {
      if (pt) hits.push({ k: "line", i, x: pt.x, y: pt.y, r: 16 });
    });
    sum.bn.forEach((b, i) => {
      if (b) hits.push({ k: "bar", i, x: L.G.cols[i], y: L.bars.y, w: L.G.colW, h: L.bars.h });
    });
    // 시트의 글자 쪽(달·Density·Wafer — 도넛 위). 좁은 화면에서 시트에 다 못 적는 증감을 말풍선이 말한다.
    L.sheets.forEach((s) => {
      const bottom = s.box ? s.cy - s.box * 0.45 : s.y + s.h;
      hits.push({ k: "sheet", i: s.i, x: s.x, y: s.y, w: s.w, h: Math.max(0, bottom - s.y) });
    });
    port.postMessage({ type: "hits", hits });
  }

  // 월별 시트 — 달 · Density · Wafer 계획 · 도넛. 이름은 왼쪽, 값(18px)과 단위는 오른쪽이다. 칸이 좁으면
  // 값이 이름을 덮는다(1100px 창이면 「Density」의 y). 그래서 가장 긴 글자를 재어 여섯 칸을 한 모양으로 정한다:
  //   ① 이름 · 값 · 단위가 한 줄에 들어가면 그대로(넓은 화면의 기본 모양).
  //   ② 값을 바닥(SHEET_VALUE_FLOOR — 요약의 다른 숫자 글자와 같은 14px)까지 줄여 한 줄에 넣는다.
  //   ③ 그래도 안 되면 이름을 값 위 한 줄로 내리고 값은 다시 18px 부터 맞춘다(`stacked`).
  //   ④ 그마저 안 되는 칸(휴대폰)은 시트를 세 칸씩 두 줄로 접는다(`wrap`).
  // 값은 세기가 끝난 마지막 글자로 잰다 — 셀 때는 자릿수가 같거나 적고, 움직임을 줄여도 같은 배치다.
  // 도넛은 남은 자리의 짧은 쪽에 맞추고 40px 이 안 되면 그리지 않는다(말풍선 자리도 함께 없다). 가운데
  // 글자는 8px 이상일 때만 쓴다.
  const SHEET_PAD = 12;
  const SHEET_VALUE_PX = 18;
  const SHEET_VALUE_FLOOR = 14;
  const SHEET_LABEL_LINE = 13;
  function layoutSheets(G, n) {
    const rows = [
      { label: "Density", values: sum.density, digits: 2, unit: "억Gb" },
      { label: sum.text.wafer, values: sum.wafer, digits: 0, unit: "K" },
    ].map((row) => ({
      ...row,
      labelW: widest(`500 11px ${bodyStack}`, [row.label]),
      unitW: widest(`500 10px ${bodyStack}`, [row.unit]),
      valueW: widest(`700 ${SHEET_VALUE_PX}px ${numStack}`, row.values.slice(0, n).map((v) => valueText(v, row.digits))),
    }));
    // 값 글자 크기. 한 줄이면 이름 뒤 8px 를 띄우고 남는 폭, 두 줄이면 단위만 뺀 폭에 맞춘다.
    const valuePx = (inner, stacked) =>
      Math.min(
        SHEET_VALUE_PX,
        ...rows.map((r) => {
          const room = inner - r.unitW - 2 - (stacked ? 0 : r.labelW + 8);
          return r.valueW > 0 ? Math.floor(((SHEET_VALUE_PX * room) / r.valueW) * 2) / 2 : SHEET_VALUE_PX;
        }),
      );
    // 칸 안쪽 여백은 12px, 100px 가 안 되는 칸은 8px 이다(760px 바로 위 창에서 값이 바닥 아래로 내려가
    // 시트가 접히지 않게).
    const choose = (w) => {
      const pad = w >= 100 ? SHEET_PAD : 8;
      const inner = w - pad * 2;
      const inline = valuePx(inner, false);
      if (inline >= SHEET_VALUE_FLOOR) return { stacked: false, px: inline, inner, pad };
      const stacked = valuePx(inner, true);
      if (stacked >= SHEET_VALUE_FLOOR && rows.every((r) => r.labelW <= inner)) return { stacked: true, px: stacked, inner, pad };
      return null;
    };
    let wrap = false;
    let cellW = G.colW;
    let fitted = choose(cellW);
    if (!fitted && n > 3) {
      wrap = true;
      cellW = (G.spanW - G.gap * 2) / 3;
      fitted = choose(cellW);
    }
    if (!fitted) {
      // 이보다 좁은 화면은 없다고 보지만, 그래도 겹치지는 않게 바닥 아래로 줄이고 이름은 줄임표로 자른다.
      const inner = Math.max(1, cellW - 16);
      fitted = { stacked: true, px: Math.max(8, valuePx(inner, true)), inner, pad: 8 };
    }
    g.font = `500 11px ${bodyStack}`;
    for (const r of rows) r.text = fitted.stacked ? fit(r.label, fitted.inner) : r.label;
    // 달 글자는 자간(.4px)만큼 덜어 잰다.
    const monthPx = fitPx(sum.months, 800, 20, 12, fontStack, fitted.inner - 0.4 * 6);
    const rowH = fitted.stacked ? SHEET_LABEL_LINE + Math.ceil(fitted.px) + 3 : 22;
    const lines = wrap ? Math.ceil(n / 3) : 1;
    const cardH = (G.rows[2].h - G.gap * (lines - 1)) / lines;
    const cards = [];
    for (let i = 0; i < n; i++) {
      const x = wrap ? G.spanX + (i % 3) * (cellW + G.gap) : G.cols[i];
      const y = G.rows[2].y + (wrap ? Math.floor(i / 3) * (cardH + G.gap) : 0);
      const top = y + 10;
      const kv1 = top + 20 + 6;
      const kv2 = kv1 + rowH + 6;
      const donutTop = kv2 + rowH + 6;
      const donutH = Math.max(0, y + cardH - 10 - donutTop);
      const fits = Math.max(0, Math.min(cellW - 24, donutH));
      const box = fits >= 40 ? fits : 0;
      cards.push({ x, y, w: cellW, h: cardH, i, top, kv: [kv1, kv2], box, cx: x + cellW / 2, cy: donutTop + donutH / 2 });
    }
    return { ...fitted, wrap, rows, monthPx, cards };
  }

  // 선행 B/O 를 켠 값 글자 크기. 배치(`layoutSheets`)가 정한 모양(한 줄·두 줄·접기)은 그대로 두고 값 글자만
  // 다시 맞춘다 — 기본 크기보다 커지지 않는다. 값이 길어져 이름을 덮는 일이 없게 한다.
  function sheetValuePx(K, columns, n) {
    let px = K.px;
    K.rows.forEach((row, r) => {
      const w = widest(`700 ${SHEET_VALUE_PX}px ${numStack}`, columns[r].slice(0, n).map((v) => valueText(v, row.digits)));
      const room = K.inner - row.unitW - 2 - (K.stacked ? 0 : row.labelW + 8);
      if (w > 0) px = Math.min(px, Math.floor(((SHEET_VALUE_PX * room) / w) * 2) / 2);
    });
    return Math.max(8, px);
  }

  // 지금 선의 축과 변형별 무게. 축(lo·hi)은 토글 진행만큼 기본 범위에서 넓힌 범위로 옮겨 가고, 눈금은 변형
  // 사이를 엇갈려 바꾼다. 셋을 다 끄면 `base` 하나에 무게 1 이라 배치 그대로 그린다.
  function lineNow() {
    const V = sumL.lineV;
    const kA = viewMix("bo");
    const kG = viewMix("gap");
    const lo = Math.min(V.base.lo + kA * (V.A.lo - V.base.lo), V.base.lo + kG * (V.G.lo - V.base.lo));
    const hi = Math.max(V.base.hi + kA * (V.A.hi - V.base.hi), V.base.hi + kG * (V.G.hi - V.base.hi));
    const span = Math.max(1, sumL.lineBot - sumL.lineTop);
    const yLine = (v) => sumL.lineBot - ((v - lo) / (hi - lo)) * span;
    const weights = new Map();
    const add = (variant, w) => {
      if (w > 0.0005) weights.set(variant, (weights.get(variant) || 0) + w);
    };
    add(V.base, (1 - kA) * (1 - kG));
    add(V.A, kA * (1 - kG));
    add(V.G, (1 - kA) * kG);
    add(V.AG, kA * kG);
    return { lo, hi, yLine, weights };
  }

  // 그 달의 Density — 선행 B/O 를 켜는 만큼 원래 값에서 선행 반영 값으로 차오른다(숫자도 함께 센다).
  function densityNow(adv, i) {
    const v = sum.density[i];
    if (v == null || !adv) return v;
    const a = adv.density[i];
    const m = monthMix("bo", i);
    return a == null || m <= 0 ? v : v + (a - v) * m;
  }

  function drawLine(c) {
    const L = sumL;
    const k = OUT(clamp01((c - 60) / 700));
    if (k <= 0) return;
    const { line } = L;
    const adv = toggleData("advance");
    const cmp = toggleData("comparison");
    const now = lineNow();
    g.save();
    g.globalAlpha = k;
    g.translate(0, 18 * (1 - k));
    panel(line.x, line.y, line.w, line.h);
    g.font = `500 10px ${bodyStack}`;
    g.textBaseline = "alphabetic";
    // 눈금 글자는 간격의 자릿수만큼 찍고(0.05 간격이면 둘째 자리), 자리는 배치가 골라 둔 곳이다. 축이 움직이는
    // 동안에는 변형마다의 눈금을 무게만큼 겹쳐 그린다(지금 축의 자리에).
    for (const [V, w] of now.weights) {
      for (const v of V.ticks) {
        const y = now.yLine(v);
        g.strokeStyle = rgba(textColor, 0.08 * w);
        g.lineWidth = 1;
        g.beginPath();
        g.moveTo(line.x, Math.round(y) + 0.5);
        g.lineTo(line.x + line.w, Math.round(y) + 0.5);
        g.stroke();
      }
    }
    g.fillStyle = pal.faint;
    for (const [V, w] of now.weights) {
      const settled = V.lo === now.lo && V.hi === now.hi;
      g.globalAlpha = k * w;
      for (const t of V.tickLabels) {
        if (!t) continue;
        g.textAlign = t.align;
        g.fillText(t.text, t.x, settled ? t.y : now.yLine(t.v) + t.dy);
      }
    }
    g.globalAlpha = k;
    // 달 이름은 점 위 값 글자(14px)와 같은 크기다(2026-10-03 사용자 결정).
    g.font = `500 14px ${bodyStack}`;
    g.textAlign = "center";
    g.fillStyle = pal.muted;
    sum.months.forEach((m, i) => g.fillText(m, L.colX(i), line.y + line.h - 9));
    const points = sum.density.map((_, i) => {
      const v = densityNow(adv, i);
      return v == null ? null : { x: L.colX(i), y: now.yLine(v), v };
    });
    const pts = points.filter(Boolean);
    if (pts.length) {
      // 영역은 선이 다 그어질 즈음 번진다.
      const area = OUT(clamp01((c - 700) / 800));
      if (area > 0 && pts.length > 1) {
        const minY = Math.min(...pts.map((p) => p.y));
        const grad = g.createLinearGradient(0, minY, 0, L.lineBot);
        grad.addColorStop(0, rgba(parseColor(pal.accent), 0.28));
        grad.addColorStop(1, rgba(parseColor(pal.accent), 0));
        g.globalAlpha = k * area;
        g.beginPath();
        g.moveTo(pts[0].x, L.lineBot);
        pts.forEach((p) => g.lineTo(p.x, p.y));
        g.lineTo(pts[pts.length - 1].x, L.lineBot);
        g.closePath();
        g.fillStyle = grad;
        g.fill();
        g.globalAlpha = k;
      }
      if (adv) drawAdvanceBand(k, now, points);
      if (cmp) drawGhost(c, k, now, cmp);
      // 선은 왼쪽부터 길이 비율로 그어진다.
      const p = EASE(clamp01((c - 250) / 1000));
      if (p > 0 && pts.length > 1) {
        const lens = [];
        let totalLen = 0;
        for (let i = 1; i < pts.length; i++) {
          const d = Math.hypot(pts[i].x - pts[i - 1].x, pts[i].y - pts[i - 1].y);
          lens.push(d);
          totalLen += d;
        }
        let left = totalLen * p;
        g.beginPath();
        g.moveTo(pts[0].x, pts[0].y);
        for (let i = 1; i < pts.length && left > 0; i++) {
          const d = lens[i - 1];
          const f = Math.min(1, left / Math.max(d, 1e-6));
          g.lineTo(pts[i - 1].x + (pts[i].x - pts[i - 1].x) * f, pts[i - 1].y + (pts[i].y - pts[i - 1].y) * f);
          left -= d;
        }
        g.strokeStyle = pal.text;
        g.lineWidth = 2;
        g.lineJoin = "round";
        g.lineCap = "round";
        g.stroke();
      }
      points.forEach((pt, i) => {
        if (!pt) return;
        const e = OUT(clamp01((c - 350 - i * 140) / 500));
        if (e <= 0) return;
        const y = pt.y + 6 * (1 - e);
        g.globalAlpha = k * e;
        g.beginPath();
        g.arc(pt.x, y, 4.5, 0, TAU);
        g.fillStyle = pal.surface;
        g.fill();
        g.strokeStyle = pal.text;
        g.lineWidth = 2;
        g.stroke();
        g.font = `700 14px ${numStack}`;
        g.textAlign = "center";
        g.fillStyle = pal.text;
        g.fillText(round(pt.v, 2), pt.x, y - 12);
      });
    }
    g.restore();
  }

  // 선행 B/O 가 더한 몫 — 원래 선(점선)과 새 선 사이를 강조색으로 옅게 칠한다. 달마다 진행이 달라 몫이 시차를
  // 두고 아래에서 위로 차오른다(음수 입력이면 아래로 내려간다). HOME 의 「Density (선행 B/O 전)」 점선과 같은 뜻이다.
  function drawAdvanceBand(k, now, points) {
    const before = sum.density.map((v, i) => (v == null ? null : { x: sumL.colX(i), y: now.yLine(v) }));
    let shown = 0;
    for (let i = 0; i < points.length; i++) if (points[i]) shown = Math.max(shown, monthMix("bo", i));
    if (shown <= 0.001) return;
    g.save();
    g.globalAlpha = k;
    g.fillStyle = rgba(parseColor(pal.accent), 0.3);
    g.beginPath();
    for (let i = 1; i < points.length; i++) {
      const a0 = before[i - 1];
      const a1 = before[i];
      const b0 = points[i - 1];
      const b1 = points[i];
      if (!a0 || !a1 || !b0 || !b1) continue;
      g.moveTo(a0.x, a0.y);
      g.lineTo(b0.x, b0.y);
      g.lineTo(b1.x, b1.y);
      g.lineTo(a1.x, a1.y);
      g.closePath();
    }
    g.fill();
    g.globalAlpha = k * shown;
    g.strokeStyle = pal.muted;
    g.lineWidth = 1.5;
    g.setLineDash([2, 4]);
    g.beginPath();
    let open = false;
    for (const pt of before) {
      if (!pt) {
        open = false;
        continue;
      }
      if (open) g.lineTo(pt.x, pt.y);
      else g.moveTo(pt.x, pt.y);
      open = true;
    }
    g.stroke();
    g.setLineDash([]);
    g.restore();
  }

  // 비교 시나리오 쪽 값 — 속이 빈 유령 점과 끊긴 선. 달마다 시차를 두고 살짝 내려앉으며 나타난다. 차이 글자는
  // 월별 시트가 값 아래에 단다(HOME 처럼 값 아래).
  function drawGhost(c, k, now, cmp) {
    const marks = cmp.density.map((v, i) => {
      if (v == null) return null;
      const m = monthMix("gap", i) * OUT(clamp01((c - 350 - i * 140) / 500));
      return { x: sumL.colX(i), y: now.yLine(v) - 6 * (1 - m), m };
    });
    if (!marks.some((pt) => pt && pt.m > 0.001)) return;
    g.save();
    g.strokeStyle = pal.muted;
    g.lineWidth = 1.5;
    g.setLineDash([5, 4]);
    for (let i = 1; i < marks.length; i++) {
      const a = marks[i - 1];
      const b = marks[i];
      if (!a || !b) continue;
      const m = Math.min(a.m, b.m);
      if (m <= 0.001) continue;
      g.globalAlpha = k * m * 0.85;
      g.beginPath();
      g.moveTo(a.x, a.y);
      g.lineTo(b.x, b.y);
      g.stroke();
    }
    g.setLineDash([]);
    for (const pt of marks) {
      if (!pt || pt.m <= 0.001) continue;
      g.globalAlpha = k * pt.m;
      g.beginPath();
      g.arc(pt.x, pt.y, 3.5, 0, TAU);
      g.fillStyle = pal.surface;
      g.fill();
      g.stroke();
    }
    g.restore();
  }

  function drawBars(c) {
    const L = sumL;
    const k = OUT(clamp01((c - 60) / 700));
    if (k <= 0) return;
    const { bars } = L;
    const adv = toggleData("advance");
    // 막대 축의 위끝·글자 크기는 선행 B/O 진행만큼 두 변형 사이를 옮겨 간다. 끄면 기본 변형 그대로다.
    const B0 = L.barV.base;
    const BA = L.barV.A;
    const kA = adv ? viewMix("bo") : 0;
    const max = B0.max + kA * (BA.max - B0.max);
    const yBar = max === B0.max ? B0.yBar : (v) => L.barBot - (v / max) * Math.max(1, L.barBot - L.barTop);
    const ratePx = B0.ratePx + kA * (BA.ratePx - B0.ratePx);
    const statusPx = B0.statusPx + kA * (BA.statusPx - B0.statusPx);
    // 그 달의 확보율 — 선행 B/O 를 켜는 만큼 새 확보율로 내려앉는다(숫자도 함께 센다).
    const rateNow = (i) => {
      const b = sum.bn[i];
      const a = adv ? adv.bn[i] : null;
      const m = a ? monthMix("bo", i) : 0;
      return m > 0 ? b.rate + (a.rate - b.rate) * m : b.rate;
    };
    g.save();
    g.globalAlpha = k;
    g.translate(0, 18 * (1 - k));
    panel(bars.x, bars.y, bars.w, bars.h);
    // 기준선(구간·계단)과 이름표 자리는 배치(`barLayout`)가 정한다. 선은 정확한 기준(109.5) 자리에 긋고,
    // 이름표는 사사오입한 글자(`*_label`, 110%)를 단다. 선은 막대 밑에, 이름표는 막대 위에 그린다 — 자리가
    // 없어 바탕을 깐 이름표가 막대에 가리지 않게.
    g.textBaseline = "alphabetic";
    for (const t of B0.thresholds) {
      g.strokeStyle = rgba(textColor, 0.28);
      g.lineWidth = 1;
      g.setLineDash(t.dash);
      g.beginPath();
      t.runs.forEach((run, r) => {
        const y = Math.round(yBar(run.v)) + 0.5;
        const x0 = L.edgeLeft(run.start);
        const prev = t.runs[r - 1];
        if (prev && prev.end === run.start - 1) {
          g.moveTo(x0, Math.round(yBar(prev.v)) + 0.5);
          g.lineTo(x0, y);
        } else {
          g.moveTo(x0, y);
        }
        g.lineTo(L.edgeRight(run.end), y);
      });
      g.stroke();
      g.setLineDash([]);
    }
    sum.bn.forEach((b, i) => {
      const cx = L.colX(i);
      g.textAlign = "center";
      if (!b) {
        g.font = `500 14px ${bodyStack}`;
        g.fillStyle = pal.faint;
        g.fillText("—", cx, L.barBot + 19);
        return;
      }
      const a = adv ? adv.bn[i] : null;
      const m = a ? monthMix("bo", i) : 0;
      // 판정(확보·경고·부족)이 바뀌면 막대 색이 두 상태색 사이를 엇갈려 바뀐다.
      const color =
        m > 0 && a.status !== b.status
          ? mix(parseColor(statusColor(b.status)), parseColor(statusColor(a.status)), m)
          : statusColor(b.status);
      const s = EASE(clamp01((c - 250 - i * 90) / 800));
      const rate = rateNow(i);
      const top = yBar(rate);
      const full = L.barBot - top;
      if (s > 0 && full > 0) {
        const h = full * s;
        rr(cx - L.bw / 2, L.barBot - h, L.bw, h, Math.min(4, h / 2));
        g.fillStyle = color;
        g.fill();
      }
      // 선행 B/O 전 막대의 윤곽 — 얼마나 내려앉았는지(또는 올라섰는지) 남겨 둔다.
      if (m > 0.001 && s > 0 && Math.abs(a.rate - b.rate) >= 0.05) {
        const before = yBar(b.rate);
        const h = (L.barBot - before) * s;
        if (h > 1) {
          g.globalAlpha = k * m;
          g.strokeStyle = rgba(textColor, 0.4);
          g.lineWidth = 1;
          g.setLineDash([3, 3]);
          rr(cx - L.bw / 2 + 0.5, L.barBot - h + 0.5, L.bw - 1, h - 1, Math.min(4, h / 2));
          g.stroke();
          g.setLineDash([]);
          g.globalAlpha = k;
        }
      }
      const appear = clamp01((c - 800 - i * 90) / 400);
      if (appear > 0) {
        g.globalAlpha = k * appear;
        g.font = `700 ${ratePx}px ${numStack}`;
        g.fillStyle = pal.text;
        g.fillText(`${round(rate, 1)}%`, cx, top - 7);
        g.globalAlpha = k;
      }
      // 막대 밑 두 줄(공정 이름·상태)은 생산계획 값 글자와 같은 14px 다(2026-10-03 사용자 결정). 상태 글자는
      // 칸 간격을 넘을 때만 여섯 칸을 함께 줄인다(`statusPx` — 휴대폰 폭).
      g.font = `500 14px ${bodyStack}`;
      g.fillStyle = pal.muted;
      g.fillText(fit(b.process, L.G.colW - 8), cx, L.barBot + 19);
      // 부족 대수 — 부족한 달만 숫자로 세우고(상태색), 나머지는 상태 이름만 단다. 선행 B/O 로 판정이 바뀌면
      // 두 글자가 엇갈려 바뀐다.
      const a2 = clamp01((c - 900 - i * 90) / 400);
      if (a2 > 0) {
        g.font = `700 ${statusPx}px ${bodyStack}`;
        const states = m > 0.001 && statusText(a) !== statusText(b) ? [[b, 1 - m], [a, m]] : [[m > 0.5 && a ? a : b, 1]];
        for (const [x, w] of states) {
          if (w <= 0.001) continue;
          g.globalAlpha = k * a2 * w;
          g.fillStyle = isShort(x) ? statusColor(x.status) : pal.muted;
          g.fillText(statusText(x), cx, L.barBot + 38);
        }
        g.globalAlpha = k;
      }
    });
    g.font = `500 10px ${bodyStack}`;
    const labelSets = BA === B0 || kA <= 0 ? [[B0, 1]] : kA >= 1 ? [[BA, 1]] : [[B0, 1 - kA], [BA, kA]];
    for (const [V, w] of labelSets) {
      g.globalAlpha = k * w;
      for (const t of V.thresholds) {
        for (const run of t.runs) {
          const spot = run.spot;
          // 이름표는 그 변형의 선 자리에서 고른 것이다 — 축이 움직이면 지금 선 자리만큼 함께 옮긴다.
          const dy = V.max === max ? 0 : yBar(run.v) - V.yBar(run.v);
          if (spot.backed) {
            rr(spot.box.x, spot.box.y + dy, spot.box.w, spot.box.h, 3);
            g.fillStyle = rgba(surface, 0.86);
            g.fill();
          }
          g.fillStyle = pal.muted;
          g.textAlign = spot.align;
          g.fillText(run.label, spot.x, spot.y + dy);
        }
      }
    }
    g.globalAlpha = k;
    // 「최저」는 확보율이 가장 낮은 달 막대 위다. 선행 B/O 로 그 달이 바뀌면 두 자리를 엇갈려 바꾼다.
    const lows = B0.lowest === BA.lowest ? [[B0.lowest, 1]] : [[B0.lowest, 1 - kA], [BA.lowest, kA]];
    const e = OUT(clamp01((c - 1500) / 500));
    if (e > 0) {
      for (const [index, w] of lows) {
        if (index < 0 || w <= 0.001) continue;
        g.globalAlpha = k * e * w;
        g.font = `600 11px ${bodyStack}`;
        g.textAlign = "center";
        g.fillStyle = pal["die-short"];
        g.fillText(sum.text.lowest, L.colX(index), yBar(rateNow(index)) - 30 + 3 * (1 - e));
      }
    }
    g.restore();
  }

  function drawSheets(c) {
    const L = sumL;
    const K = L.sheet;
    const adv = toggleData("advance");
    const ship = toggleData("shipment");
    const cmp = toggleData("comparison");
    for (const s of L.sheets) {
      const i = s.i;
      const e = OUT(clamp01((c - 120 - i * 110) / 760));
      if (e <= 0) continue;
      const mx = s.x + s.w / 2;
      const my = s.y + s.h / 2;
      g.save();
      g.globalAlpha = e;
      // CSS 의 translateY(60px) rotate(-2deg) scale(.96) → none 과 같은 차례로 겹친다.
      g.translate(mx, my + 60 * (1 - e));
      g.rotate((-2 * Math.PI) / 180 * (1 - e));
      const sc = 0.96 + 0.04 * e;
      g.scale(sc, sc);
      g.translate(-mx, -my);
      panel(s.x, s.y, s.w, s.h);
      const padX = K.pad;
      g.textBaseline = "alphabetic";
      g.textAlign = "left";
      g.fillStyle = pal.text;
      g.font = `800 ${K.monthPx}px ${fontStack}`;
      try {
        g.letterSpacing = "0.4px";
      } catch (error) {
        /* 자간을 모르는 캔버스 */
      }
      g.fillText(sum.months[i], s.x + padX, s.top + 17);
      try {
        g.letterSpacing = "0px";
      } catch (error) {
        /* 자간을 모르는 캔버스 */
      }
      const cnt = COUNT(clamp01((c - 260 - i * 110) / 900));
      // 선행 B/O 진행(그 달). 값이 원래 값에서 선행 반영 값으로 차오르고 글자 크기는 두 배치 사이를 옮겨 간다.
      const mA = adv ? monthMix("bo", i) : 0;
      const px = mA > 0 ? K.px + (K.pxA - K.px) * mA : K.px;
      // 이름은 왼쪽, 값과 단위는 오른쪽. 한 줄(`stacked` 아님)이면 셋이 같은 바탕선이고, 두 줄이면 이름이
      // 값 위 줄로 올라간다. 글자 크기·모양은 배치(`layoutSheets`)가 여섯 칸에 한 번 정해 둔 것이다.
      K.rows.forEach((row, r) => {
        const top = s.kv[r];
        const base = K.stacked ? top + SHEET_LABEL_LINE + Math.round(px * 0.85) + 1 : top + 17;
        const right = s.x + s.w - padX;
        const own = row.values[i];
        const target = adv ? (r === 0 ? adv.density : adv.wafer)[i] : own;
        const value = own == null || target == null || mA <= 0 ? own : own + (target - own) * mA;
        g.font = `500 11px ${bodyStack}`;
        g.textAlign = "left";
        g.fillStyle = pal.muted;
        g.fillText(row.text, s.x + padX, K.stacked ? top + 10 : base);
        g.textAlign = "right";
        g.font = `500 10px ${bodyStack}`;
        g.fillText(row.unit, right, base);
        g.font = `700 ${px}px ${numStack}`;
        // 선행 B/O 가 바꾼 값은 토글 표식과 같은 강조색으로 물든다 — 끄면 본문 글자색으로 돌아온다.
        g.fillStyle = mA > 0 && target !== own ? mix(textColor, accentColor, 0.6 * mA) : pal.text;
        g.fillText(value == null ? "—" : (value * cnt).toFixed(row.digits), right - row.unitW - 2, base);
        // GAP — 비교 시나리오와의 차이를 값 아래에 단다(HOME 처럼 값 아래, 오른쪽 끝을 값에 맞춘다). 부호색은
        // 늘림·줄임 둘이고, 달마다 시차를 두고 아래에서 떠오른다.
        const gap = cmp ? (r === 0 ? cmp.density_gap : cmp.wafer_gap)[i] : "";
        const mG = gap ? monthMix("gap", i) : 0;
        if (mG > 0.001) {
          g.globalAlpha = e * mG;
          g.font = `700 10px ${numStack}`;
          g.fillStyle = gap.trim().startsWith("-") ? pal["gap-down"] : pal["gap-up"];
          g.fillText(gap, right - row.unitW - 2, base + 12 + 4 * (1 - mG));
          g.globalAlpha = e;
        }
        // 선행 입고 실적 — Density 값 옆(단위 위, 칸 오른쪽 끝)에 작게 붙는다. 계산에 들어가지 않는 표시값이라
        // 선·막대는 그대로이고, 달마다 시차를 두고 오른쪽에서 미끄러져 붙는다.
        const note = r === 0 && ship ? ship.notes[i] : "";
        const mS = note ? monthMix("ship", i) : 0;
        if (mS > 0.001) {
          g.globalAlpha = e * mS;
          g.font = `700 10px ${numStack}`;
          g.fillStyle = pal.text;
          g.fillText(note, right + 8 * (1 - mS), base - Math.round(px * 0.72) - 3);
          g.globalAlpha = e;
        }
      });
      // 도넛: 조각마다 50ms 씩 늦게 자란다. 조각 사이는 둘레의 0.9% 를 비운다.
      const slices = sum.mix[i] || [];
      if (s.box > 0 && slices.length) {
        const r = s.box * 0.36;
        g.lineWidth = s.box * 0.13;
        g.lineCap = "butt";
        let acc = 0;
        slices.forEach(([p, share], j) => {
          const grow = OUT(clamp01((c - 380 - i * 110 - j * 50) / 900));
          const len = Math.max(0.001, share - 0.009) * grow;
          if (grow > 0) {
            g.beginPath();
            g.arc(s.cx, s.cy, r, -Math.PI / 2 + acc * TAU, -Math.PI / 2 + (acc + len) * TAU);
            g.strokeStyle = (sum.products[p] && sum.products[p].color) || pal.muted;
            g.stroke();
          }
          acc += share;
        });
        // 가운데 글자(가장 큰 조각의 비중·제품)는 8px 이상으로 쓸 수 있을 때만 단다.
        const sharePx = Math.round(s.box * 0.15);
        if (sharePx >= 8) {
          const [topP, topShare] = slices.reduce((a, b) => (b[1] > a[1] ? b : a), slices[0]);
          g.textAlign = "center";
          g.fillStyle = pal.text;
          g.font = `700 ${sharePx}px ${numStack}`;
          g.fillText(`${Math.round(topShare * 100)}%`, s.cx, s.cy - s.box * 0.02);
          g.font = `500 ${Math.max(8, Math.round(s.box * 0.08))}px ${bodyStack}`;
          g.fillStyle = pal.muted;
          g.fillText(fit(sum.products[topP] ? sum.products[topP].name : "", s.box * 0.62), s.cx, s.cy + s.box * 0.12);
        }
      }
      g.restore();
    }
  }

  function drawSummary(at) {
    if (!sumL || !sumAt) return;
    // 움직임을 줄인 사용자에게는 조립 없이 끝 모습을 바로 그린다.
    const c = reduce ? 1e6 : at - sumAt;
    if (c < 0) return;
    drawLine(c - rowsAt[0]);
    drawBars(c - rowsAt[1]);
    drawSheets(c - rowsAt[2]);
  }

  function step(tween, target, at) {
    if (!tween) return null;
    const k = tween.ms > 0 ? clamp01((at - tween.at) / tween.ms) : 1;
    const e = tween.ease(k);
    for (const key of Object.keys(tween.to)) target[key] = tween.from[key] + (tween.to[key] - tween.from[key]) * e;
    return k >= 1 ? null : tween;
  }

  function draw(at) {
    viewAt = at;
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, W, H);
    // 시작 전(테마 새로고침을 기다리는 동안)에는 아무것도 그리지 않는다 — 아래 HTML 바탕(앱 바탕색)만 보인다.
    if (!beginAt) return;
    const t = at - beginAt;
    const clock = at - initAt;
    lookTween = step(lookTween, look, at);
    if (veilTween) {
      const v = { veil };
      veilTween = step(veilTween, v, at);
      veil = v.veil;
    }
    g.fillStyle = reduce ? rgba(surface, 1) : mix(frame0, surface, IN_OUT(clamp01(t / 700)));
    g.fillRect(0, 0, W, H);
    const L = layout();
    const rp = reduce ? 1 : clamp01((t - REVEAL_AT) / REVEAL_MS);
    if (rp > 0) {
      const e = reduce ? 1 : EASE(rp);
      if (e < 1) {
        const R = Math.hypot(Math.max(L.cx, W - L.cx), Math.max(L.cy, H - L.cy));
        const r0 = L.S * 0.44;
        g.save();
        g.beginPath();
        g.arc(L.cx, L.cy, r0 + (R - r0) * e, 0, TAU);
        g.clip();
        drawMap(clock);
        drawVeil();
        g.restore();
      } else {
        drawMap(clock);
        drawVeil();
      }
    }
    drawSummary(at);
    if (reduce) return;
    if (t < REVEAL_AT + 700) {
      // 원형 펼침이 시작되면 심볼은 앞으로 다가오며(1 → 1.9) 사라진다.
      const k = IN(clamp01((t - REVEAL_AT) / 700));
      g.save();
      g.globalAlpha = 1 - k;
      g.translate(L.cx, L.cy);
      g.scale(1 + 0.9 * k, 1 + 0.9 * k);
      g.translate(-L.cx, -L.cy);
      drawSymbol(t, L);
      g.restore();
    }
    if (t < REVEAL_AT + 280) drawWord(t, L, 1 - clamp01((t - REVEAL_AT) / 280));
  }

  function frame() {
    if (stopped || paused) {
      looping = false;
      return;
    }
    const at = now();
    const dt = last ? Math.min(64, at - last) : 16;
    if (beginAt && last && at - beginAt >= 0 && at - beginAt < 6000) {
      const gap = at - last;
      stats.frames += 1;
      if (gap > 25) stats.slow += 1;
      if (gap > stats.max) stats.max = gap;
    }
    last = at;
    const target = ready ? 1 : Math.min(0.97, (reached + 0.45) / total);
    // 준비 뒤 마지막 확장은 조금 더 느긋하게(시간 상수 0.8초) 가장자리까지 번진다.
    shown += (target - shown) * Math.min(1, dt / (ready ? 800 : 450));
    settle += ((ready ? 1 : 0) - settle) * Math.min(1, dt / 700);
    if (g) draw(at);
    nextFrame(frame);
  }

  // 움직임을 줄인 사용자에게는 그림이 시간에 따라 바뀌지 않는다 — 웨이퍼는 멈춰 있고(`drawMap` 의 t = 0) 요약과
  // 토글은 끝 모습이다. 그래서 프레임 루프를 세우지 않고, 그림을 바꾸는 메시지(init · begin · progress · resize ·
  // summary · summary-on · view · resume)를 받을 때와 글꼴이 올라왔을 때만 한 번 그린다. 루프를 세우면 같은
  // 그림을 매 프레임 다시 그리느라 렌더러·GPU 가 헛돈다(헤드리스 실측: 「준비 완료」 대기 10초에 CPU 3.05초).
  // 진행값(펼침 `shown` · 안정 `settle` · 토글 진행)은 그리는 순간의 목표로 바로 맞춘다.
  function paintOnce() {
    if (stopped || paused || !g) return;
    shown = ready ? 1 : Math.min(0.97, (reached + 0.45) / total);
    settle = ready ? 1 : 0;
    draw(now());
  }

  function loop() {
    if (reduce) {
      paintOnce();
      return;
    }
    if (looping || stopped || paused || !g) return;
    looping = true;
    last = 0;
    nextFrame(frame);
  }

  port.onmessage = (event) => {
    const m = (event && event.data) || {};
    if (m.type === "init") {
      canvas = m.canvas;
      pal = m.palette || {};
      brand = m.brand || "";
      reduce = !!m.reduce;
      paused = !!m.paused;
      fontStack = `"${m.family}", ${m.body || "sans-serif"}`;
      numStack = `"${m.number}", ${m.body || "sans-serif"}`;
      bodyStack = m.body || "sans-serif";
      frame0 = parseColor(m.frame0 || pal.surface);
      surface = parseColor(pal.surface);
      textColor = parseColor(pal.text);
      accentColor = parseColor(pal.accent);
      g = canvas.getContext("2d");
      resize(m.width, m.height, m.dpr);
      if (paused) {
        canvas.width = 1;
        canvas.height = 1;
      }
      build();
      fontsReady = loadFonts(m.fonts, [
        { family: m.family, weight: "800" },
        { family: m.number, weight: "700" },
      ]);
      initAt = now();
      loop();
      // 움직임을 줄였으면 글꼴이 올라온 뒤 한 번 더 그린다(루프가 없어 다음 프레임이 없다).
      fontsReady.then(() => loop());
    } else if (m.type === "begin") {
      beginAt = m.at;
      loop();
    } else if (m.type === "progress") {
      reached = m.reached;
      total = Math.max(1, m.total);
      ready = !!m.ready;
      loop();
    } else if (m.type === "resize") {
      resize(m.width, m.height, m.dpr);
      loop();
    } else if (m.type === "summary") {
      sum = m.summary || null;
      fontsReady.then(() => {
        layoutSummary();
        port.postMessage({ type: "summary-ready", ok: !!sum });
        loop();
      });
    } else if (m.type === "summary-on") {
      if (m.fromApp) {
        // 원래 화면에서 열 때: 인트로는 이미 끝난 것으로 둔다(펼침·확장 없이 바로 웨이퍼).
        beginAt = m.at - 100000;
        shown = 1;
        settle = 1;
        ready = true;
      }
      rowsAt = m.rows;
      sumAt = m.charts;
      const to = m.look;
      if (m.instant) {
        lookTween = null;
        veilTween = null;
        look.fade = to.fade;
        look.mono = to.mono;
        veil = 0;
      } else {
        lookTween = { from: { ...look }, to, at: m.lookAt, ms: m.lookMs, ease: EASE };
        veilTween = { from: { veil }, to: { veil: 0 }, at: m.veilAt, ms: m.veilMs, ease: (x) => x };
      }
      loop();
    } else if (m.type === "view") {
      // 머리 줄 토글. 켜려는 모습만 바꾸고 진행은 프레임이 옮긴다(지금 값에서 이어 간다).
      const v = m.view || {};
      const want = { bo: v.advance ? 1 : 0, ship: v.shipment ? 1 : 0, gap: v.comparison ? 1 : 0 };
      const t = now();
      // 값이 막 닿은 토글(켜 둔 채 「준비 중」이던 것) — 꺼진 자리에서 다시 움직여 들어온다.
      const channel = { advance: "bo", shipment: "ship", comparison: "gap" };
      for (const key of m.restart || []) {
        const ch = channel[key];
        if (!ch) continue;
        viewTween[ch] = { all: rest(0), months: Array.from({ length: VIEW_MONTHS }, () => rest(0)) };
        viewWant[ch] = 0;
      }
      for (const ch of Object.keys(want)) {
        if (want[ch] !== viewWant[ch] || reduce || m.instant) retarget(ch, want[ch], t, reduce || !!m.instant);
        viewWant[ch] = want[ch];
      }
      postHits();
      loop();
    } else if (m.type === "pause") {
      paused = true;
      if (canvas) {
        canvas.width = 1;
        canvas.height = 1;
      }
    } else if (m.type === "resume") {
      paused = false;
      resize(m.width, m.height, m.dpr);
      loop();
    } else if (m.type === "stats") {
      port.postMessage({ type: "stats", frames: stats.frames, slow: stats.slow, max: Math.round(stats.max) });
    } else if (m.type === "stop") {
      stopped = true;
    }
  };
}

// 장면을 워커에 띄운다. 못 하면(워커·OffscreenCanvas 없음, 워커 오류) 같은 장면을 메인 스레드에서 돌린다.
function startScene(canvas, init, onReply) {
  let mode = "main";
  let worker = null;
  let workerUrl = "";
  let send = () => {};
  // 워커가 죽으면 새 장면에 다시 보낼 마지막 상태들.
  const replay = new Map();
  const waiting = [];
  const reply = (m) => {
    if (m && m.type === "stats") waiting.splice(0).forEach((resolve) => resolve({ mode, ...m }));
    else if (m) onReply(m);
  };
  const runOnMain = (target) => {
    mode = "main";
    const port = { onmessage: null, postMessage: reply };
    scene(port, summaryGrid);
    send = (m) => port.onmessage && port.onmessage({ data: m });
    send({ ...init, type: "init", canvas: target, fonts: [] });
    replay.forEach((m) => send(m));
  };
  try {
    if (typeof Worker !== "function" || typeof OffscreenCanvas !== "function" || !canvas.transferControlToOffscreen) {
      throw new Error("worker canvas unavailable");
    }
    const source = `(${scene.toString()})(self, ${summaryGrid.toString()});`;
    workerUrl = URL.createObjectURL(new Blob([source], { type: "text/javascript" }));
    worker = new Worker(workerUrl);
    const offscreen = canvas.transferControlToOffscreen();
    const fonts = fontBuffers();
    worker.onmessage = (event) => reply(event.data);
    worker.onerror = (event) => {
      if (event && event.preventDefault) event.preventDefault();
      worker.terminate();
      worker = null;
      // 넘겨준 캔버스는 메인 스레드에서 다시 쓸 수 없다 — 새 캔버스로 갈아 끼운다.
      const fresh = document.createElement("canvas");
      fresh.className = canvas.className;
      fresh.setAttribute("aria-hidden", "true");
      canvas.replaceWith(fresh);
      runOnMain(fresh);
    };
    worker.postMessage({ ...init, type: "init", canvas: offscreen, fonts }, [offscreen, ...fonts.map((f) => f.buffer)]);
    send = (m) => worker && worker.postMessage(m);
    mode = "worker";
  } catch (error) {
    if (worker) worker.terminate();
    worker = null;
    runOnMain(canvas);
  }
  return {
    post(m) {
      const key = m.type === "pause" || m.type === "resume" ? "run" : m.type;
      // 지웠다 다시 넣어 마지막으로 받은 차례를 지킨다(Map 은 있는 키의 자리를 그대로 둔다) — 그래야
      // 되살린 장면이 resume 뒤의 resize 처럼 나중 값을 나중에 받는다.
      if (["begin", "progress", "summary", "summary-on", "view", "run", "resize"].includes(key)) {
        replay.delete(key);
        replay.set(key, m);
      }
      send(m);
    },
    stats() {
      return new Promise((resolve) => {
        waiting.push(resolve);
        send({ type: "stats" });
        window.setTimeout(() => resolve(null), 500);
      });
    },
    stop() {
      send({ type: "stop" });
      if (worker) worker.terminate();
      worker = null;
      if (workerUrl) URL.revokeObjectURL(workerUrl);
    },
    get mode() {
      return mode;
    },
  };
}

/* ============================================================================================
 * 시작 — 이 탭에서 처음이면 입장 화면을 띄우고, 이미 들어간 탭이면 요약만 감춰 둔 채 준비한다.
 * ============================================================================================ */
function boot(api, data) {
  registerFont();
  registerHole();
  let overlay = null;
  let summary = null;
  const ensure = (initial) => {
    if (!overlay) overlay = createOverlay(api, data, initial, syncToolbar);
    return overlay;
  };

  // 사이드바 S.PKG CAPA 라벨. 테마 버튼 iframe 의 스크립트가 세우고 칠한다
  // (intro_summary.summary_label_script). 여기서는 누를 수 있는지와 풍선만 정한다 — 라벨은 앱 이름이기도
  // 해서 늘 보인다. 요약이 있으면 누를 수 있고, 없으면 그 까닭을 풍선에 단다.
  const text = data.text || {};
  api.offTitle = text.label_off || "";
  let received = false;
  let reason = "";
  function syncToolbar() {
    const label = document.getElementById(SUMMARY_LABEL_ID);
    if (!label) return;
    const can = !api.done && !!summary;
    label.setAttribute("aria-disabled", can ? "false" : "true");
    if (can) label.title = text.label_open || "";
    else if (api.done) label.title = text.label_off || "";
    else label.title = received ? reason || text.label_off || "" : text.label_waiting || "";
  }

  api.setSummary = (payload) => {
    summary = payload && payload.available ? payload : null;
    received = true;
    reason = payload && !payload.available && payload.reason ? String(payload.reason) : "";
    // 요약이 없어 걷었던 오버레이(공식버전 계산 실패 뒤 Detail 등)는 새 요약이 오면 감춘 채 다시
    // 만든다 — 그래야 새로고침 없이 사이드바 라벨이 Summary 를 다시 연다.
    if (summary && api.done) {
      api.done = false;
      overlay = null;
    }
    // 이미 들어간 탭: 요약이 있으면 감춘 오버레이를 미리 만들어 워커가 준비해 두게 한다.
    if (!overlay && summary) ensure("hidden");
    if (overlay) overlay.setSummary(payload);
    syncToolbar();
  };
  api.openSummary = (button) => {
    if (!summary || api.done) return;
    ensure("hidden").openFromApp(button);
  };
  api.decorate = () => syncToolbar();

  if (!enteredBefore()) ensure("intro");
  if (window.__capaSummary !== undefined) api.setSummary(window.__capaSummary);
  syncToolbar();
}

function createOverlay(api, data, initial, syncToolbar) {
  const intro = initial === "intro";
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const palette = data.palette || {};
  const text = data.text || {};
  const steps = Array.isArray(data.steps) && data.steps.length ? data.steps : [{ label: "" }];
  const app = document.querySelector('[data-testid="stApp"]');
  const frame0 = app ? getComputedStyle(app).backgroundColor : palette.surface;

  const host = document.createElement("div");
  host.id = HOST_ID;
  const shadow = host.attachShadow({ mode: "open" });
  shadow.innerHTML = `<style>${OVERLAY_CSS}</style>${OVERLAY_HTML}`;
  const $ = (selector) => shadow.querySelector(selector);
  const $$ = (selector) => [...shadow.querySelectorAll(selector)];
  const stage = $(".stage");
  const vars = {
    "--frame0": frame0,
    "--text": palette.text,
    "--muted": palette.muted,
    "--accent": palette.accent,
    "--track": palette.track,
    "--button": palette.button,
    "--button-text": palette["button-text"],
    "--button-off-line": palette["button-off-line"],
    "--ghost-line": palette["ghost-line"],
    "--ghost-hover": palette["ghost-hover"],
    "--panel-line": palette["panel-line"],
    "--faint": palette.faint,
    "--toggle-on": palette["toggle-on"],
    "--toggle-on-line": palette["toggle-on-line"],
    "--gap-up": palette["gap-up"],
    "--gap-down": palette["gap-down"],
    "--tip": palette.tip,
    "--tip-shadow": palette["tip-shadow"],
    "--body": data.font_body || "sans-serif",
    "--display": `"${FONT_FAMILY}", ${data.font_body || "sans-serif"}`,
  };
  for (const [name, value] of Object.entries(vars)) if (value) stage.style.setProperty(name, value);

  $('[data-slot="brand"]').textContent = data.brand || "";
  $('[data-slot="logo"]').innerHTML = brandMark(palette);
  const mark = markMotion($('[data-slot="logo"]'), palette);
  const title = $('[data-slot="title"]');
  (data.title || []).forEach((line, index) => {
    if (index) title.appendChild(document.createElement("br"));
    title.appendChild(document.createTextNode(line));
  });
  $('[data-slot="steps"]').innerHTML = steps
    .map((step) => `<li><span class="track"></span><span class="lbl">${escapeHtml(step.label)}</span></li>`)
    .join("");

  const detail = $(".btn.detail");
  const detailText = $(".btn.detail .txt");
  const summaryButton = $(".btn.summary");
  $(".btn.summary .txt").textContent = text.summary || "Summary";
  summaryButton.title = text.summary_title || "";
  detail.title = text.detail_title || "";
  const dock = $('[data-slot="dock"]');
  const actions = $(".actions");
  const asof = $('[data-slot="asof"]');
  const main = $(".main");
  const status = $(".status");
  const hint = $(".hint");
  const tip = $(".tip");
  const labels = $('[data-slot="labels"]');
  const table = $('[data-slot="table"]');
  const items = $$(".steps li");

  // 덮개 위 휠·터치가 아래 앱을 굴리지 않게 한다.
  host.addEventListener("wheel", (event) => event.preventDefault(), { passive: false });
  host.addEventListener("touchmove", (event) => event.preventDefault(), { passive: false });
  if (!intro) host.style.display = "none";
  document.body.appendChild(host);
  if (intro) setInert(true);

  let hits = [];
  let summary = null;
  let summaryArrived = false;
  let prepared = false;
  let preparedWaiters = [];
  const sceneHandle = startScene(
    $(".scene"),
    {
      width: window.innerWidth,
      height: window.innerHeight,
      dpr: window.devicePixelRatio || 1,
      palette,
      brand: data.brand || "",
      reduce,
      paused: !intro,
      family: FONT_FAMILY,
      number: NUMBER_FAMILY,
      body: data.font_body || "sans-serif",
      frame0,
    },
    (m) => {
      if (m.type === "hits") {
        hits = m.hits || [];
        // 도넛을 그릴 자리가 없는 화면(휴대폰 — 시트를 접는다)에서는 제품 범례도 걷는다. 장면이 도넛 자리를
        // 말풍선 자리(`seg`)로 돌려주므로 그것으로 안다 — 두 곳에서 따로 셈하지 않는다.
        labels.classList.toggle("no-mix", !hits.some((h) => h.k === "seg"));
      } else if (m.type === "summary-ready") {
        prepared = !!m.ok;
        preparedWaiters.splice(0).forEach((resolve) => resolve());
        render();
      }
    },
  );
  api.mode = sceneHandle.mode;
  api.stats = () => sceneHandle.stats();
  const size = () => ({ width: window.innerWidth, height: window.innerHeight, dpr: window.devicePixelRatio || 1 });
  const onResize = () => {
    sceneHandle.post({ type: "resize", ...size() });
    placeLabels();
  };
  window.addEventListener("resize", onResize);

  const timers = [];
  let alive = true;
  let poller = 0;
  api.stop = () => {
    alive = false;
    timers.forEach((id) => window.clearTimeout(id));
    window.clearInterval(poller);
    document.removeEventListener("keydown", onKey);
    document.removeEventListener("focusin", onFocusIn);
    window.removeEventListener("resize", onResize);
    sceneHandle.stop();
  };
  const anim = (el, keyframes, options = {}) =>
    el.animate(keyframes, { fill: "both", easing: EASE, ...options }).finished.catch(() => {});
  const revealAnimations = new Map();

  /* -------------------------------------------- 보는 조건 토글 셋(선행 B/O · 선행 입고 · GAP) */
  // Summary 머리 줄에서 Detail 오른쪽에 조금 띄워 선다(입장 화면에서는 보이지 않는다). 브라우저 안에서만 켜고
  // 끈다 — 파이썬으로 아무것도 보내지 않아 rerun 이 없고, 값은 요약이 미리 보낸 `toggles` 다. 장면(워커)에는
  // 켜려는 모습만 보내고 움직임은 장면이 그린다. 상태는 이 탭이 살아 있는 동안 기억한다(`api.view` — Summary
  // 를 닫았다 다시 열어도 그대로, 새로 고치면 셋 다 꺼짐). 켤 수 없는 토글은 `aria-disabled` 로 두고 풍선에
  // 까닭을 단다 — `disabled` 가 아니라 Tab 으로 닿아 까닭을 읽을 수 있다.
  const view = api.view || (api.view = { advance: false, shipment: false, comparison: false });
  let viewSent = false;
  const toggleSpecs = Array.isArray(text.toggles) ? text.toggles : [];
  const toggleBox = $('[data-slot="toggles"]');
  toggleBox.setAttribute("aria-label", text.toggles_group || "");
  toggleBox.innerHTML = toggleSpecs
    .map(
      (spec) =>
        `<button type="button" class="tg" data-key="${escapeHtml(spec.key)}" aria-pressed="false" aria-disabled="true" aria-label="${escapeHtml(spec.label)}">` +
        `<i class="sw" aria-hidden="true"></i><span class="full" aria-hidden="true">${escapeHtml(spec.label)}</span>` +
        `<span class="short" aria-hidden="true">${escapeHtml(spec.short || spec.label)}</span></button>`,
    )
    .join("");
  const toggleButtons = $$(".tg");
  const toggleOf = (key) => (summary && summary.toggles && summary.toggles[key]) || null;
  const canToggle = (key) => {
    const t = toggleOf(key);
    return !!(t && t.available);
  };
  const isOn = (key) => !!view[key] && canToggle(key);

  function toggleTitle(spec) {
    const t = toggleOf(spec.key);
    if (!t || !t.available) return (t && t.reason) || reasonText || "";
    if (spec.key === "comparison" && t.name) return `${spec.title || ""} · ${t.name}`;
    if (spec.key === "advance" && t.unapplied && t.unapplied.length) {
      return `${spec.title || ""} (${text.advance_unapplied || ""} ${t.unapplied.join(", ")})`;
    }
    return spec.title || "";
  }

  // 단추의 눌림·쓸 수 있음·풍선을 지금 값에 맞춘다. 켤 수 없다고 **정해진** 토글만 끈다 — 요약이 잠깐
  // 없거나(공식버전을 못 읽은 일시적 실패) 그 몫이 「준비 중」(`pending` — 비교 값을 페이지 뒤에서
  // 만드는 중)이면 고른 상태를 지키고 단추만 잠근다. 값이 닿으면 그 모습으로 그린다.
  function syncToggles() {
    toggleButtons.forEach((button) => {
      const key = button.dataset.key;
      const spec = toggleSpecs.find((item) => item.key === key) || {};
      const part = toggleOf(key);
      const can = canToggle(key);
      const pending = !!(part && part.pending);
      if (summary && part && !part.available && !pending) view[key] = false;
      // 「준비 중」이면 켜기만 잠근다 — 켜 둔 것은 끌 수 있어야 한다.
      button.setAttribute("aria-disabled", can || (pending && view[key]) ? "false" : "true");
      button.setAttribute("aria-pressed", view[key] ? "true" : "false");
      button.toggleAttribute("data-pending", pending);
      button.title = toggleTitle(spec);
    });
  }

  // `restart` 는 값이 막 닿은 토글이다 — 켜 둔 채 기다렸으면 그 토글만 처음부터 다시 움직여 들어온다.
  function postView(instant, restart = []) {
    sceneHandle.post({ type: "view", view: { ...view }, instant: !!instant, restart });
  }

  function pressToggle(button) {
    if (button.getAttribute("aria-disabled") === "true") return;
    const key = button.dataset.key;
    if (!view[key] && !canToggle(key)) return;
    view[key] = !view[key];
    button.setAttribute("aria-pressed", view[key] ? "true" : "false");
    postView(false);
    buildTable();
    tip.style.opacity = "0";
    // 켤 때 표식이 한 번 톡 차오른다(움직임을 줄인 사용자에게는 없다).
    if (view[key] && !reduce) {
      button.querySelector(".sw").animate([{ transform: "scale(.6)" }, { transform: "scale(1.45)", offset: 0.55 }, { transform: "scale(1)" }], {
        duration: 360,
        easing: OUT,
      });
    }
  }
  // Space · Enter 는 단추가 스스로 click 으로 바꾼다. Esc 는 지금처럼 Detail 로 나간다(`onKey`).
  toggleButtons.forEach((button) => button.addEventListener("click", () => pressToggle(button)));

  // Summary 가 조립될 때 Detail 옆에 하나씩 떠오른다. 원래 화면에서 다시 열 때(`snapToSummary`)는 바로 선다.
  // 떠오르는 동안(아직 투명한 동안)은 `inert` 로 묶어 Tab 이 보이지 않는 단추에 닿지 않게 하고, 마지막
  // 단추가 다 선 뒤 푼다.
  // Summary 를 열 때 「준비 중」 몫(페이지 뒤에서 만드는 GAP)이 있으면 요약 값을 **한 번** 다시 받아 온다
  // (`intro_summary` 의 받은 값 JS 가 둔 `__capaSummaryRefresh` — rerun 한 번. 덮개가 앱을 가린다). 한 번
  // 열 때 한 번뿐이다 — 그래도 「준비 중」이면 그대로 두고, 다음에 열 때 다시 한 번 묻는다.
  let refreshAsked = false;
  function askRefreshIfPending() {
    if (refreshAsked || !summary || !summary.toggles) return;
    const waiting = Object.values(summary.toggles).some((part) => part && part.pending);
    if (!waiting || typeof window.__capaSummaryRefresh !== "function") return;
    refreshAsked = true;
    window.__capaSummaryRefresh();
  }

  let revealRound = 0;
  function revealToggles(animate) {
    const round = (revealRound += 1);
    const moving = [];
    toggleButtons.forEach((button, index) => {
      button.getAnimations().forEach((a) => a.cancel());
      button.style.opacity = "1";
      if (animate && !reduce) {
        moving.push(
          button.animate([{ opacity: 0, transform: "translateX(-10px)" }, { opacity: 1, transform: "none" }], {
            duration: 560,
            delay: SUMMARY_TIMING.asofDelay + index * 70,
            easing: OUT,
            fill: "backwards",
          }).finished,
        );
      }
    });
    toggleBox.inert = moving.length > 0;
    if (moving.length) {
      Promise.allSettled(moving).then(() => {
        // 그사이 다시 드러냈으면(닫았다 다시 연 때) 그 차례가 푼다.
        if (round === revealRound) toggleBox.inert = false;
      });
    }
  }

  /* ------------------------------------------------ 상태: intro(입장) · summary(요약) · hidden(감춤) */
  let mode = intro ? "intro" : "hidden";
  let busy = false;
  // 사이드바 라벨로 연 요약을 닫으면 포커스를 그 라벨로 돌려준다. 돌려주지 않으면 body 에 남아
  // 키보드 사용자가 제자리를 잃었다(Guide 는 돌려준다, 2026-10-05 E2E).
  let opener = null;
  const t0 = performance.now();
  let reached = 0; // 끝낸 단계 수
  let ready = !intro;
  let introDone = !intro;
  let progressText = "";
  let fallback = false;
  let barSeen = false;
  let topPercent = 0;

  const sendProgress = () => sceneHandle.post({ type: "progress", reached, total: steps.length, ready });
  const canEnter = () => (ready || fallback) && introDone;
  const canSummary = () => canEnter() && !!summary && prepared;

  function render() {
    items.forEach((li, index) => {
      li.className = ready || index < reached ? "done" : index === reached ? "active" : "";
    });
    if (ready) status.textContent = text.ready || "";
    else if (fallback) status.textContent = text.slow || "";
    else status.textContent = progressText || text.boot || "";
    const can = canEnter();
    detail.disabled = !can;
    detailText.textContent = can ? text.detail || "Detail" : text.waiting || "";
    // Summary 는 들어갈 수 있을 때 함께 선다. 요약을 만들지 못했으면 까닭을 달고 꺼 둔다.
    const appearing = can && summaryButton.hidden;
    summaryButton.hidden = !can;
    // 준비되는 순간 Detail 옆에 살짝 떠오른다(갑자기 튀어나오지 않게). 입장 화면에서만.
    if (appearing && mode === "intro" && !reduce) {
      summaryButton.animate([{ opacity: 0, transform: "translateY(6px)" }, { opacity: 1, transform: "none" }], {
        duration: 420,
        easing: OUT,
      });
    }
    summaryButton.disabled = !canSummary();
    summaryButton.title = summaryArrived && !summary ? reasonText : text.summary_title || "";
  }
  let reasonText = "";

  function arm() {
    if (!canEnter() || mode !== "intro") return;
    hint.hidden = true;
    render();
    if (!reduce) {
      // 단추가 다 떠오른 뒤에 한 번 맥동한다. `scale` 은 떠오르기의 transform 과 따로 놀아 서로 덮지 않는다.
      const rising = revealAnimations.get(actions);
      Promise.resolve(rising && rising.finished)
        .catch(() => {})
        .then(() => {
          if (alive && mode === "intro") detail.animate([{ scale: 1 }, { scale: 1.04 }, { scale: 1 }], { duration: 520, easing: OUT });
        });
    }
    detail.focus({ preventScroll: true });
  }

  // 단계는 앞에서부터 끝난 만큼 찬다. 신호의 뜻은 intro_overlay._steps 가 말한다.
  function stepDone(step) {
    if (ready) return true;
    if (step.signal === "boot") return summaryArrived || barSeen;
    if (step.signal === "summary") return summaryArrived;
    if (step.until != null) return topPercent >= step.until;
    return false;
  }
  function update() {
    let count = 0;
    while (count < steps.length && stepDone(steps[count])) count += 1;
    if (count > reached) {
      reached = Math.min(steps.length, count);
      sendProgress();
    }
    render();
  }

  function setReady() {
    if (ready) return;
    ready = true;
    update();
    sendProgress();
    arm();
  }

  function introFinished() {
    if (!alive || introDone) return;
    introDone = true;
    render();
    if (!ready) {
      timers.push(window.setTimeout(() => {
        if (alive && !ready) {
          hint.textContent = text.hint || "";
          hint.hidden = false;
        }
      }, HINT_AFTER_MS));
      timers.push(window.setTimeout(() => {
        if (alive && !ready) {
          fallback = true;
          arm();
        }
      }, FALLBACK_ENTER_MS));
    }
    arm();
  }

  /* ------------------------------------------------------------ 요약 값·행 이름·낭독용 표 */
  function setSummary(payload) {
    const readyBefore = Object.fromEntries(toggleSpecs.map((spec) => [spec.key, canToggle(spec.key)]));
    summaryArrived = true;
    summary = payload && payload.available ? payload : null;
    reasonText = payload && !payload.available ? String(payload.reason || "") : "";
    prepared = false;
    if (summary) {
      buildLabels();
      sceneHandle.post({
        type: "summary",
        summary: {
          ...summary,
          text: { ...(text.status || {}), lowest: text.lowest || "", wafer: "Wafer 계획" },
        },
      });
    }
    // 켤 수 없게 된 토글은 끈다. 이 장면이 처음 받는 상태면 움직임 없이 그 모습으로 시작한다(탭이 기억한
    // 상태로 새 오버레이를 만든 때). 켜 둔 채 「준비 중」이던 토글에 값이 닿으면 그 토글은 움직여 들어온다.
    const arrived = toggleSpecs.map((spec) => spec.key).filter((key) => view[key] && !readyBefore[key] && canToggle(key));
    syncToggles();
    postView(!viewSent, viewSent ? arrived : []);
    viewSent = true;
    buildTable();
    if (mode === "intro") update();
    else render();
  }

  function buildLabels() {
    const rows = text.rows || [];
    // 범례는 판정 세 색의 이름만 적는다(2026-10-06 사용자 결정). 기준 숫자는 달마다 다를 수 있어
    // 막대 위 기준선 이름표가 말한다. 막대 밑 상태 글자(`text.status`)와 이름이 달라 따로 받는다.
    const legendText = text.legend || {};
    const legendStatus = [
      [palette["die-ok"], legendText.secure || ""],
      [palette["die-warn"], legendText.warning || ""],
      [palette["die-short"], legendText.shortage || ""],
    ];
    const legend = (pairs) =>
      `<div class="legend">${pairs.map(([color, name]) => `<span><i style="background:${escapeHtml(color)}"></i>${escapeHtml(name)}</span>`).join("")}</div>`;
    // 설명(`sub`)이 없는 행은 그 줄을 아예 만들지 않는다 — 빈 줄이 남으면 범례가 위로 끌려 붙는다.
    const cell = (row, extra) =>
      `<div class="sum-label"><div class="t">${escapeHtml(row.title || "")}</div>${row.sub ? `<div class="s">${escapeHtml(row.sub)}</div>` : ""}${extra}</div>`;
    labels.innerHTML =
      cell(rows[0] || {}, "") +
      cell(rows[1] || {}, legend(legendStatus)) +
      cell(rows[2] || {}, legend(summary.products.map((p) => [p.color, p.name])));
    $(".asof .chip").textContent = summary.release || "";
    $(".asof .period").textContent = `${summary.period} · ${(text.months || "").replace("{n}", summary.count)}`;
    asof.title = summary.scenario || "";
    placeLabels();
  }

  // 차트는 캔버스라 낭독기가 읽지 못한다. 같은 값을 숨은 표로 둔다 — 켠 토글의 값도 함께(선행 B/O 를 켜면
  // 그 값, 선행 입고·GAP 은 칸을 더한다).
  function buildTable() {
    if (!summary) return;
    const adv = isOn("advance") ? toggleOf("advance") : null;
    const ship = isOn("shipment") ? toggleOf("shipment") : null;
    const cmp = isOn("comparison") ? toggleOf("comparison") : null;
    const head = ["", "Density(억Gb)", "Wafer 계획(K)", "B/N 공정", "확보율(%)", "부족 대수"];
    if (ship) head.push(`${text.shipment_note || ""}(억Gb)`);
    if (cmp) head.push("GAP Density(억Gb)", "GAP Wafer(K)");
    const body = summary.months.map((month, i) => {
      const b = (adv ? adv.bn : summary.bn)[i];
      const density = (adv ? adv.density : summary.density)[i];
      const wafer = (adv ? adv.wafer : summary.wafer)[i];
      const row = [month, density ?? "", wafer ?? "", b ? b.process : "", b ? b.rate : "", b && b.short != null ? b.short : ""];
      if (ship) row.push(ship.notes[i] || "");
      if (cmp) row.push(cmp.density_gap[i] || "", cmp.wafer_gap[i] || "");
      return row;
    });
    const labelsOn = toggleSpecs.filter((spec) => isOn(spec.key)).map((spec) => spec.label);
    table.innerHTML =
      `<caption>${escapeHtml(summary.release || "")} ${escapeHtml(summary.period || "")}${labelsOn.length ? ` · ${escapeHtml(labelsOn.join(", "))}` : ""}</caption>` +
      `<tr>${head.map((h) => `<th>${escapeHtml(h)}</th>`).join("")}</tr>` +
      body.map((r) => `<tr>${r.map((v) => `<td>${escapeHtml(v)}</td>`).join("")}</tr>`).join("");
  }

  // 행 이름 자리. 넓은 화면은 왼쪽 칸에 줄 높이만큼, 좁은 화면은 줄 위 띠(`head`)에 차트 폭만큼 둔다 —
  // 띠 안에서는 intro.css 의 @media (max-width: 760px) 가 이름과 범례를 한 줄로 잇는다.
  function placeLabels() {
    if (!summary) return;
    const G = summaryGrid(window.innerWidth, window.innerHeight);
    $$(".sum-label").forEach((el, i) => {
      const row = G.rows[i];
      el.style.left = `${G.narrow ? G.spanX : G.left}px`;
      el.style.width = `${Math.max(0, G.narrow ? G.spanW : G.labelW - 6)}px`;
      el.style.top = `${G.narrow ? row.y - row.head : row.y}px`;
      el.style.height = `${G.narrow ? Math.max(0, row.head - 6) : row.h}px`;
    });
  }

  // 행 이름은 그 줄의 차트와 같은 때 떠오른다. 지연을 실어 미리 걸어 두므로 합성기가 제때 돌린다.
  function scheduleLabels(offset) {
    $$(".sum-label").forEach((el, i) => {
      el.getAnimations().forEach((a) => a.cancel());
      el.animate(
        reduce
          ? [{ opacity: 0 }, { opacity: 1 }]
          : [{ opacity: 0, transform: "translateY(18px)" }, { opacity: 1, transform: "none" }],
        { duration: reduce ? 1 : 700, delay: reduce ? 0 : offset + SUMMARY_TIMING.rows[i], easing: OUT, fill: "both" },
      );
    });
  }

  /* ------------------------------------------------------------ 말풍선 */
  function hitAt(x, y) {
    for (const h of hits) {
      if (h.k === "seg") {
        const d = Math.hypot(x - h.cx, y - h.cy);
        if (d < h.r0 || d > h.r1) continue;
        let a = Math.atan2(y - h.cy, x - h.cx) + Math.PI / 2;
        if (a < 0) a += Math.PI * 2;
        if (a >= h.a0 && a < h.a1) return h;
      } else if (h.k === "line") {
        if (Math.hypot(x - h.x, y - h.y) <= h.r) return h;
      }
    }
    for (const h of hits) {
      if ((h.k === "bar" || h.k === "sheet") && x >= h.x && x <= h.x + h.w && y >= h.y && y <= h.y + h.h) return h;
    }
    return null;
  }
  // 말풍선은 켠 토글의 값으로 말한다 — 선행 B/O 를 켰으면 반영 값과 그 전 값, 선행 입고·GAP 을 켰으면 그 줄을 더한다.
  function tipHtml(h) {
    const month = summary.months[h.i];
    const adv = isOn("advance") ? toggleOf("advance") : null;
    const ship = isOn("shipment") ? toggleOf("shipment") : null;
    const cmp = isOn("comparison") ? toggleOf("comparison") : null;
    const dim = (html) => `<br><span class="dim">${html}</span>`;
    const fixed = (v, d) => (v == null ? "—" : Number(v).toFixed(d));
    const shipLine = () => (ship && ship.notes[h.i] ? dim(`${escapeHtml(text.shipment_note || "")} ${escapeHtml(ship.notes[h.i])}억Gb`) : "");
    if (h.k === "line") {
      let html = `<b>${escapeHtml(month)}</b> 생산계획 <b>${Number((adv ? adv.density : summary.density)[h.i]).toFixed(2)}</b>억Gb`;
      if (adv && adv.density_delta[h.i]) html += dim(`${escapeHtml(text.advance_before || "")} ${fixed(summary.density[h.i], 2)} · 선행 B/O ${escapeHtml(adv.density_delta[h.i])}`);
      html += shipLine();
      if (cmp && cmp.density[h.i] != null) {
        const gap = cmp.density_gap[h.i];
        html += dim(`${escapeHtml(text.comparison_value || "")} ${fixed(cmp.density[h.i], 2)}${gap ? ` · GAP ${escapeHtml(gap)}` : ""}`);
      }
      return html;
    }
    if (h.k === "seg") {
      const p = summary.products[h.p] || {};
      const share = (summary.mix[h.i] || []).find(([index]) => index === h.p);
      return `<b>${escapeHtml(p.name || "")}</b> · ${share ? (share[1] * 100).toFixed(1) : ""}% <span class="dim">${escapeHtml(month)}</span>`;
    }
    if (h.k === "sheet") {
      let html = `<b>${escapeHtml(month)}</b> Density <b>${fixed((adv ? adv.density : summary.density)[h.i], 2)}</b>억Gb · Wafer 계획 <b>${fixed((adv ? adv.wafer : summary.wafer)[h.i], 0)}</b>K`;
      if (adv && (adv.density_delta[h.i] || adv.wafer_delta[h.i])) {
        html += dim(`선행 B/O ${escapeHtml(adv.density_delta[h.i] || "—")} · ${escapeHtml(adv.wafer_delta[h.i] || "—")}`);
      }
      html += shipLine();
      if (cmp) html += dim(`GAP ${escapeHtml(cmp.density_gap[h.i] || "—")} · ${escapeHtml(cmp.wafer_gap[h.i] || "—")}`);
      return html;
    }
    const base = summary.bn[h.i];
    const b = (adv && adv.bn[h.i]) || base;
    const st = (text.status || {})[b.status] || "";
    const short = b.status === "shortage" && b.short ? `${(text.status || {}).shortage || ""} <b>${b.short}대</b>` : st;
    const units = b.need != null && b.have != null ? `<br><span class="dim">소요 ${b.need}대 / 보유 ${b.have}대</span>` : "";
    const before = adv && adv.rate_delta[h.i] ? dim(`${escapeHtml(text.advance_before || "")} ${base.rate}% · ${escapeHtml(adv.rate_delta[h.i])}`) : "";
    return `<b>${escapeHtml(month)}</b> B/N ${escapeHtml(b.process)}<br>확보율 <b>${b.rate}%</b> · ${short}${units}${before}`;
  }
  stage.addEventListener("pointermove", (event) => {
    const h = mode === "summary" && summary ? hitAt(event.clientX, event.clientY) : null;
    if (!h) {
      tip.style.opacity = "0";
      return;
    }
    tip.innerHTML = tipHtml(h);
    tip.style.opacity = "1";
    tip.style.left = `${Math.min(event.clientX + 14, window.innerWidth - tip.offsetWidth - 8)}px`;
    tip.style.top = `${Math.min(event.clientY + 14, window.innerHeight - tip.offsetHeight - 8)}px`;
  });
  stage.addEventListener("pointerleave", () => {
    tip.style.opacity = "0";
  });

  /* ------------------------------------------------------------ 입장 → 요약 */
  function cancelAll(elements) {
    elements.forEach((el) => el && el.getAnimations().forEach((a) => a.cancel()));
  }

  // Detail 이 심볼·라벨 옆으로 옮겨 가며 라벨과 같은 글자가 된다. 바탕은 148×52 → 86×30(같은 비율),
  // 글자는 20px → 18px 한 비율로 — 둘 다 transform 만 움직여 찌그러짐·글자 재배치가 없다.
  function dockDetail(animate) {
    if (detail.classList.contains("docked")) return;
    const bg = $(".btn.detail .bg");
    const tx = $(".btn.detail .tx");
    const fb = bg.getBoundingClientRect();
    const ft = tx.getBoundingClientRect();
    dock.appendChild(detail);
    detail.classList.add("docked");
    if (!animate || reduce || !fb.width || !ft.height) return;
    const lb = bg.getBoundingClientRect();
    const lt = tx.getBoundingClientRect();
    anim(bg, [{ transform: `translate(${fb.left - lb.left}px, ${fb.top - lb.top}px) scale(${fb.width / lb.width}, ${fb.height / lb.height})` }, { transform: "none" }], { duration: SUMMARY_TIMING.dockMs });
    anim(tx, [{ transform: `translate(${ft.left - lt.left}px, ${ft.top - lt.top}px) scale(${ft.height / lt.height})` }, { transform: "none" }], { duration: SUMMARY_TIMING.dockMs });
  }

  async function summaryFromEntry() {
    if (busy || mode !== "intro" || !canSummary()) return;
    busy = true;
    mode = "summary";
    window.clearInterval(poller);
    stage.classList.add("summary");
    // 토글은 이 순간부터 보이는 자리(투명)라 Tab 이 닿는다 — 다 떠오를 때까지 묶는다(`revealToggles`).
    if (!reduce) toggleBox.inert = true;
    refreshAsked = false;
    askRefreshIfPending();
    hint.hidden = true;
    timers.forEach((id) => window.clearTimeout(id));
    const T = SUMMARY_TIMING;
    const at = absoluteNow();
    sceneHandle.post({
      type: "summary-on",
      at,
      charts: at + T.chartsAt,
      rows: T.rows,
      look: SUMMARY_LOOK,
      lookAt: at + T.lookAt,
      lookMs: T.lookMs,
      veilAt: at + T.veilAt,
      veilMs: T.veilMs,
      instant: reduce,
    });
    scheduleLabels(T.chartsAt);
    // 1) 메인 타이틀과 로딩 막대가 위로 밀려나며 사라진다.
    anim(title, [{ opacity: 1, transform: "none" }, { opacity: 0, transform: "translateY(-48px)" }], { duration: reduce ? 1 : T.outMs });
    anim($(".load"), [{ opacity: 1, transform: "none" }, { opacity: 0, transform: "translateY(-36px)" }], { duration: reduce ? 1 : T.outMs, delay: reduce ? 0 : 60 });
    // 2) 누른 Summary 는 Detail 아래로 겹쳐 들어가며 사라진다.
    const dx = detail.getBoundingClientRect().left - summaryButton.getBoundingClientRect().left;
    await anim(summaryButton, [{ opacity: 1, transform: "none" }, { opacity: 0, transform: `translateX(${dx}px) scale(.94)` }], {
      duration: reduce ? 1 : T.tuckMs,
      delay: reduce ? 0 : T.tuckDelay,
    });
    // 3) Detail 이 심볼·라벨 옆으로.
    dockDetail(true);
    revealToggles(true);
    anim(asof, [{ opacity: 0, transform: "translateX(12px)" }, { opacity: 1, transform: "none" }], { duration: reduce ? 1 : 700, delay: reduce ? 0 : T.asofDelay, easing: OUT });
    main.style.visibility = "hidden";
    detail.focus({ preventScroll: true });
    // 그래프가 조립되는 동안에도 Detail · Esc 는 바로 받는다.
    busy = false;
  }

  /* ------------------------------------------------------------ 원래 화면 ↔ 요약 */
  // 입장 화면을 거치지 않고(또는 Detail 로 나갔다가) 요약을 열 때 쓰는 끝 모습.
  function snapToSummary() {
    cancelAll([title, $(".load"), summaryButton, asof, $(".btn.detail .bg"), $(".btn.detail .tx"), ...$$(".head > *")]);
    $$(".head > .logo, .head > .brand").forEach((el) => {
      el.style.opacity = "1";
    });
    stage.classList.add("summary");
    hint.hidden = true;
    ready = true;
    introDone = true;
    render();
    dockDetail(false);
    revealToggles(false);
    main.style.visibility = "hidden";
    asof.style.opacity = "1";
  }

  function holeAt(el) {
    const box = el.getBoundingClientRect();
    const x = box.left + box.width / 2;
    const y = box.top + box.height / 2;
    stage.style.setProperty("--hx", `${x}px`);
    stage.style.setProperty("--hy", `${y}px`);
    return Math.hypot(Math.max(x, window.innerWidth - x), Math.max(y, window.innerHeight - y));
  }

  async function openFromApp(button) {
    if (busy || mode !== "hidden" || !summary) return;
    busy = true;
    opener = button || null;
    if (!prepared) {
      await Promise.race([
        new Promise((resolve) => preparedWaiters.push(resolve)),
        new Promise((resolve) => window.setTimeout(resolve, 1500)),
      ]);
    }
    if (!summary) {
      busy = false;
      return;
    }
    snapToSummary();
    mode = "summary";
    refreshAsked = false;
    askRefreshIfPending();
    const radius = holeAt(button || detail);
    cancelAll([stage]);
    stage.style.opacity = "";
    if (!reduce) {
      stage.classList.add("masked");
      stage.style.setProperty("--capa-hole", `${radius}px`);
    }
    host.style.display = "";
    setInert(true);
    syncToolbar();
    sceneHandle.post({ type: "resume", ...size() });
    const at = absoluteNow();
    sceneHandle.post({ type: "summary-on", at, charts: at + SUMMARY_TIMING.openChartsAt, rows: SUMMARY_TIMING.rows, look: SUMMARY_LOOK, instant: true, fromApp: true });
    scheduleLabels(SUMMARY_TIMING.openChartsAt);
    // 머리 심볼은 접히는 화면이 그 자리(사이드바 라벨 곁)를 드러낼 즈음 다시 그려진다.
    if (!reduce) mark.draw(MARK_REDRAW_AFTER_MS);
    // 화면이 사이드바 라벨 속으로 접히며 뒤의 요약이 드러난다.
    if (reduce) await anim(stage, [{ opacity: 0 }, { opacity: 1 }], { duration: 260, easing: "linear" });
    else await anim(stage, [{ "--capa-hole": `${radius}px` }, { "--capa-hole": "0px" }], { duration: FOLD_MS });
    stage.classList.remove("masked");
    cancelAll([stage]);
    stage.style.removeProperty("--capa-hole");
    detail.focus({ preventScroll: true });
    busy = false;
  }

  // Detail: 누른 단추에서 구멍이 퍼지며 원래 화면이 드러난다. 오버레이는 걷지 않고 감춘다.
  async function toDetail() {
    if (busy || mode === "hidden" || detail.disabled) return;
    busy = true;
    rememberEntered();
    setInert(false);
    tip.style.opacity = "0";
    const radius = holeAt(detail);
    if (reduce) await anim(stage, [{ opacity: 1 }, { opacity: 0 }], { duration: 260, easing: "linear" });
    else {
      stage.classList.add("masked");
      await anim(stage, [{ "--capa-hole": "0px" }, { "--capa-hole": `${radius}px` }], { duration: EXIT_MS });
    }
    hide();
    busy = false;
    if (opener && opener.isConnected) opener.focus({ preventScroll: true });
    opener = null;
  }

  function hide() {
    mode = "hidden";
    mark.cancel();
    host.style.display = "none";
    stage.classList.remove("masked");
    cancelAll([stage]);
    stage.style.opacity = "";
    sceneHandle.post({ type: "pause" });
    window.clearInterval(poller);
    timers.forEach((id) => window.clearTimeout(id));
    api.done = !summary;
    if (!summary) {
      // 요약이 없으면 다시 열 일이 없다 — 예전처럼 걷는다.
      release();
      return;
    }
    syncToolbar();
  }

  // 덮개가 서 있는 동안 Tab · Shift+Tab 은 덮개 안의 단추만 돈다. 아래 앱(#root)은 inert 라
  // 건너뛰지만 덮개 호스트가 body 의 마지막이라, Detail 다음 Tab 은 페이지를 떠나 브라우저
  // 주소창으로 나갔다(2026-10-06 E2E). 보이지 않는 단추(접혀 들어간 Summary)는 돌지 않는다.
  function focusables() {
    return $$("button, [href], input, select, textarea, [tabindex]").filter(
      (el) =>
        !el.disabled &&
        !el.hidden &&
        !el.closest("[inert]") &&
        el.tabIndex >= 0 &&
        el.getClientRects().length > 0 &&
        getComputedStyle(el).visibility !== "hidden",
    );
  }
  function cycleFocus(event) {
    event.preventDefault();
    const items = focusables();
    if (!items.length) return;
    const index = items.indexOf(shadow.activeElement);
    const step = event.shiftKey ? -1 : 1;
    const next = index < 0 ? (event.shiftKey ? items.length - 1 : 0) : (index + step + items.length) % items.length;
    items[next].focus({ preventScroll: true });
  }
  // Tab 말고도 포커스가 덮개 밖으로 갈 수 있다(앱 다시 그리기 등). 그러면 덮개 첫 단추로 데려온다.
  function onFocusIn(event) {
    if (mode === "hidden" || event.target === host || host.style.display === "none") return;
    const items = focusables();
    if (items.length) items[0].focus({ preventScroll: true });
  }

  function onKey(event) {
    if (mode !== "hidden" && event.key === "Tab") cycleFocus(event);
    else if (mode === "intro" && event.key === "Enter" && !detail.disabled && event.target === document.body) toDetail();
    else if (mode === "summary" && event.key === "Escape") toDetail();
  }
  document.addEventListener("keydown", onKey);
  document.addEventListener("focusin", onFocusIn);
  detail.addEventListener("click", () => {
    if (!detail.disabled) toDetail();
  });
  summaryButton.addEventListener("click", () => summaryFromEntry());

  /* --------------------------------------------------------- 진행 신호(앱 실행 상태·HOME 막대) */
  // HOME 은 본문 맨 위에 `LoadingProgress` 막대를 「단계 이름 · N%」로 띄운다. 그 퍼센트가 각
  // 단계의 `until` 을 넘으면 그 단계를 끝낸 것으로 친다. HOME 이 아닌 화면에는 막대가 없으므로
  // 실행이 끝날 때 한꺼번에 찬다.
  const signalMissing = !app || app.getAttribute("data-test-script-state") == null;
  const theme = data.theme || {};
  let holding = false;
  let settledAt = 0;
  function poll() {
    if (!alive || mode !== "intro") return;
    const bar = document.querySelector('[data-testid="stProgress"]');
    if (bar) {
      barSeen = true;
      const label = (bar.innerText || "").trim().replace(/\s+/g, " ");
      const meter = bar.querySelector('[role="progressbar"]');
      const fromMeter = meter ? Number(meter.getAttribute("aria-valuenow")) : NaN;
      const fromLabel = Number((label.match(/(\d+)\s*%\s*$/) || [])[1]);
      const percent = Number.isFinite(fromLabel) ? fromLabel : Number.isFinite(fromMeter) ? fromMeter : 0;
      topPercent = Math.max(topPercent, percent);
      if (label) progressText = label;
      update();
    }
    const state = app ? app.getAttribute("data-test-script-state") : null;
    if (READY_STATES.has(state)) setReady();
    if (holding) {
      if (document.getElementById(theme.button_id)) begin();
      else if (READY_STATES.has(state)) {
        settledAt = settledAt || performance.now();
        if (performance.now() - settledAt > THEME_SETTLE_AFTER_RUN_MS) begin();
      }
    }
  }

  // 입장 화면 글자는 시작할 때 **지연을 실어 미리** 걸어 둔다. 투명도·이동 애니메이션은 합성기가 돌리므로,
  // 그 순간 메인 스레드가 막혀 있어도 제때 나타난다.
  function revealEntry(delay) {
    $$(".head > .logo, .head > .brand, .main > *").forEach((part, index) => {
      const animation = part.animate(
        reduce
          ? [{ opacity: 0 }, { opacity: 1 }]
          : [{ opacity: 0, transform: "translateY(16px)" }, { opacity: 1, transform: "translateY(0)" }],
        { duration: reduce ? 300 : 760, delay: delay + index * 55, easing: OUT, fill: "both" },
      );
      revealAnimations.set(part, animation);
    });
  }

  /* -------------------------------------------------------------------------- 시작 */
  function begin() {
    if (!alive || api.begun) return;
    api.begun = true;
    holding = false;
    sceneHandle.post({ type: "begin", at: absoluteNow() });
    if (reduce) {
      revealEntry(0);
      timers.push(window.setTimeout(introFinished, 350));
    } else {
      revealEntry(REVEAL_AT_MS + TEXT_AFTER_REVEAL_MS);
      timers.push(window.setTimeout(introFinished, REVEAL_AT_MS + REVEAL_MS));
      // 머리 심볼은 떠오르면서 그려지고, 아직 읽는 중이면 스캔하다가 준비되면 한 번 돌고 멈춘다.
      mark.draw(REVEAL_AT_MS + TEXT_AFTER_REVEAL_MS).then((drawn) => {
        if (drawn && alive) mark.settle(() => ready);
      });
    }
  }

  if (intro) {
    render();
    poller = window.setInterval(poll, POLL_MS);
    if (signalMissing) setReady();
    if (themeReloadPending(theme)) {
      holding = true;
      timers.push(window.setTimeout(begin, THEME_RELOAD_HOLD_MAX_MS));
    } else begin();
  }

  return {
    setSummary,
    openFromApp,
    get visible() {
      return mode !== "hidden";
    },
  };
}
