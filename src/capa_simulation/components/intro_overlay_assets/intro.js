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
// 툴바 Summary 단추 id. `intro_summary.SUMMARY_BUTTON_ID` 와 같아야 한다.
const SUMMARY_BUTTON_ID = "capa-summary-button";
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
  const button = document.getElementById(SUMMARY_BUTTON_ID);
  if (button) button.style.display = "none";
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

// HTML 글자(타이틀·라벨·단추·툴바 Summary)가 쓰는 글꼴. 워커는 따로 받는다(`fontBuffers`).
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

function waferLogo(palette) {
  const cells = [];
  for (const y of [27, 43.5, 60]) {
    for (const x of [27, 43.5, 60]) {
      const fill = x === 43.5 && y === 43.5 ? palette["die-warn"] : palette.accent;
      cells.push(`<rect x="${x}" y="${y}" width="13" height="13" rx="2" fill="${fill}"/>`);
    }
  }
  return `<svg viewBox="0 0 100 100" aria-hidden="true"><path d="M53 93.9 A44 44 0 1 0 47 93.9 L50 90.6 Z" fill="none" stroke="${palette.text}" stroke-width="5"/>${cells.join("")}</svg>`;
}

// Summary 의 격자(CSS px). 왼쪽 행 이름 칸 + 여섯 달 칸, 세 줄(선 · 막대 · 시트). 메인 스레드(행 이름
// 위치)와 장면(차트)이 같이 쓴다 — 장면에는 이 함수의 원문을 함께 실어 보낸다. 그래서 **이 함수도
// 바깥 이름을 쓰지 않는다.** 화면이 낮으면 위 두 줄이 줄고 시트 줄만 200px 를 지킨다(스크롤 없음).
function summaryGrid(W, H) {
  const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
  const side = clamp(W * 0.045, 16, 64);
  const bottom = clamp(W * 0.03, 16, 36);
  const top = 96;
  const gap = 12;
  const labelW = W <= 900 ? 104 : 156;
  const left = side;
  const colW = Math.max(0, (W - side * 2 - labelW - gap * 6) / 6);
  const cols = [0, 1, 2, 3, 4, 5].map((i) => left + labelW + gap + i * (colW + gap));
  const avail = Math.max(0, H - top - bottom - gap * 2);
  const third = Math.max(200, (avail * 1.45) / 3.53);
  const rest = Math.max(0, avail - third);
  const h0 = rest / 2.08;
  const h1 = (rest * 1.08) / 2.08;
  const rows = [
    { y: top, h: h0 },
    { y: top + h0 + gap, h: h1 },
    { y: top + h0 + h1 + gap * 2, h: third },
  ];
  return { left, labelW, colW, gap, cols, rows, spanX: cols[0], spanW: colW * 6 + gap * 5 };
}

/* ============================================================================================
 * 장면 — 심볼·워드마크·원형 펼침·웨이퍼 맵과 Summary 차트를 캔버스 하나에 그린다.
 *
 * 이 함수는 문자열로 바뀌어 워커에서 돈다(`startScene`). **이 파일의 다른 이름을 하나도 쓰지 않는다**
 * — 필요한 것은 모두 `init` 메시지와 인자(`gridOf` = summaryGrid)로 받고 도우미는 전부 안에 둔다.
 * 워커를 못 쓰면 같은 함수를 메인 스레드에서 `port` 흉내로 돌린다. 시각은 절대값(timeOrigin + now)이다.
 *
 * 메시지: init · begin(at) · progress(reached·total·ready) · resize · summary(값) ·
 *         summary-on(at·charts·rows·look·veil·instant) · pause · resume(크기) · stats · stop
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
  // 테두리 길이(뷰박스 100 단위): 노치를 뺀 원호 + 노치 두 변.
  const RIM_START = Math.atan2(43.9, 3);
  const RIM_END = Math.atan2(43.9, -3);
  const RIM_LEN = 44 * (TAU - (RIM_END - RIM_START)) + 2 * Math.hypot(3, 3.3);

  // ---- Summary 상태
  let sum = null;
  let sumL = null;
  let sumAt = 0;
  let rowsAt = null;
  const look = { fade: 1, mono: 0 };
  let lookTween = null;
  let veil = 1;
  let veilTween = null;

  function build() {
    symbolDies = [];
    const step = 7.4;
    const size = 6;
    let n = 0;
    for (let y = -5; y <= 5; y++) {
      for (let x = -5; x <= 5; x++) {
        const far = Math.hypot(Math.abs(x * step) + size / 2, Math.abs(y * step) + size / 2);
        if (far > 40) continue;
        const order = ((Math.atan2(y, x) + Math.PI) / TAU) * 0.7 + (Math.hypot(x, y) / 6) * 0.3;
        const fill = n % 13 === 5 ? pal["die-warn"] : n === 31 ? pal["die-short"] : pal.accent;
        symbolDies.push({ x: 50 + x * step, y: 50 + y * step, order, fill });
        n += 1;
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

  // 웨이퍼 테두리. 대시 양끝은 이음 없이 끊기므로 둥근 끝으로 맞물리게 그리고, 다 그리면 대시를
  // 걷어 닫힌 경로의 모서리 이음으로 마감한다(노치 옆 틈이 없게).
  function drawSymbol(t, L) {
    const k = L.S / 100;
    g.save();
    g.translate(L.cx - 50 * k, L.cy - 50 * k);
    g.scale(k, k);
    const p = EASE(clamp01((t - 260) / 1000));
    if (p > 0) {
      g.beginPath();
      g.moveTo(53, 93.9);
      g.arc(50, 50, 44, RIM_START, RIM_END, true);
      g.lineTo(50, 90.6);
      g.closePath();
      g.lineWidth = 1.6;
      g.lineCap = "round";
      g.lineJoin = "round";
      g.strokeStyle = pal.text;
      g.setLineDash(p < 1 ? [RIM_LEN * p, RIM_LEN + 10] : []);
      g.stroke();
      g.setLineDash([]);
    }
    const base = g.globalAlpha;
    for (const d of symbolDies) {
      const e = OUT(clamp01((t - 780 - d.order * 620) / 320));
      if (e <= 0) continue;
      const s = 6 * (0.3 + 0.7 * e);
      g.globalAlpha = base * e;
      g.fillStyle = d.fill;
      g.beginPath();
      if (g.roundRect) g.roundRect(d.x - s / 2, d.y - s / 2, s, s, 0.8 * (s / 6));
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

  // 배치는 값이 닿을 때와 창 크기가 바뀔 때 한 번 정한다. 프레임마다는 그리기만 한다.
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
    // 선: 값 범위의 위아래에 여백을 두고 눈금 셋 안팎이 서게 한다.
    const vals = sum.density.filter((v) => v != null);
    let lo = vals.length ? Math.min(...vals) : 0;
    let hi = vals.length ? Math.max(...vals) : 1;
    const span = Math.max(hi - lo, Math.abs(hi) * 0.02, 0.1);
    lo -= span * 0.6;
    hi += span * 0.6;
    const step = niceStep((hi - lo) / 3);
    const ticks = [];
    for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) ticks.push(v);
    // 아래 30px 는 달 이름(14px — 점 위 값 글자와 같은 크기) 자리다.
    const lineTop = line.y + 30;
    const lineBot = line.y + line.h - 30;
    const yLine = (v) => lineBot - ((v - lo) / (hi - lo)) * Math.max(1, lineBot - lineTop);
    const points = sum.density.map((v, i) => (v == null ? null : { x: colX(i), y: yLine(v), v }));
    // 막대: 0 에서 시작한다. 기준선과 가장 큰 값이 다 들어오도록 위를 잡는다.
    const rates = sum.bn.filter(Boolean).map((b) => b.rate);
    const max = Math.max(130, ...rates.map((r) => r * 1.12), (sum.secure || 110) * 1.15);
    // 아래 50px 는 막대 밑 두 줄(공정 이름·상태 — 둘 다 14px) 자리다. 기준선 자리는 정확한 기준이다.
    const barTop = bars.y + 24;
    const barBot = bars.y + bars.h - 50;
    const yBar = (v) => barBot - (v / max) * Math.max(1, barBot - barTop);
    const bw = Math.min(54, G.colW * 0.42);
    let lowest = -1;
    sum.bn.forEach((b, i) => {
      if (b && (lowest < 0 || b.rate < sum.bn[lowest].rate)) lowest = i;
    });
    // 시트: 달 · Density · Wafer 계획 · 도넛. 도넛은 남은 칸의 짧은 쪽에 맞춘다.
    const sheets = G.cols.slice(0, n).map((x, i) => {
      const s = { x, y: G.rows[2].y, w: G.colW, h: G.rows[2].h, i };
      const top = s.y + 10;
      const kv1 = top + 20 + 6;
      const kv2 = kv1 + 22 + 6;
      const donutTop = kv2 + 22 + 6;
      const donutH = Math.max(0, s.y + s.h - 10 - donutTop);
      const box = Math.max(0, Math.min(s.w - 24, donutH));
      return { ...s, top, kv1, kv2, box, cx: s.x + s.w / 2, cy: donutTop + donutH / 2 };
    });
    sumL = { G, line, bars, colX, ticks, step, lineBot, points, yLine, max, barTop, barBot, yBar, bw, lowest, sheets };
    // 말풍선 자리. 그리는 자리와 같은 값으로 메인 스레드에 돌려준다.
    const hits = [];
    sheets.forEach((s) => {
      const r = s.box * 0.36;
      const half = s.box * 0.065;
      let acc = 0;
      for (const [p, share] of sum.mix[s.i] || []) {
        hits.push({ k: "seg", i: s.i, p, cx: s.cx, cy: s.cy, r0: r - half - 3, r1: r + half + 3, a0: acc * TAU, a1: (acc + share) * TAU });
        acc += share;
      }
    });
    points.forEach((pt, i) => {
      if (pt) hits.push({ k: "line", i, x: pt.x, y: pt.y, r: 16 });
    });
    sum.bn.forEach((b, i) => {
      if (b) hits.push({ k: "bar", i, x: G.cols[i], y: bars.y, w: G.colW, h: bars.h });
    });
    port.postMessage({ type: "hits", hits });
  }

  function drawLine(c) {
    const L = sumL;
    const k = OUT(clamp01((c - 60) / 700));
    if (k <= 0) return;
    const { line } = L;
    g.save();
    g.globalAlpha = k;
    g.translate(0, 18 * (1 - k));
    panel(line.x, line.y, line.w, line.h);
    g.font = `500 10px ${bodyStack}`;
    g.textAlign = "left";
    g.textBaseline = "alphabetic";
    // 눈금 글자는 간격의 자릿수만큼 찍는다(0.05 간격이면 둘째 자리).
    const digits = Math.max(0, -Math.floor(Math.log10(L.step) + 1e-9));
    for (const v of L.ticks) {
      const y = L.yLine(v);
      g.strokeStyle = rgba(textColor, 0.08);
      g.lineWidth = 1;
      g.beginPath();
      g.moveTo(line.x, Math.round(y) + 0.5);
      g.lineTo(line.x + line.w, Math.round(y) + 0.5);
      g.stroke();
      g.fillStyle = pal.faint;
      g.fillText(`${v.toFixed(digits)}억Gb`, line.x + 6, y - 4);
    }
    // 달 이름은 점 위 값 글자(14px)와 같은 크기다(2026-10-03 사용자 결정).
    g.font = `500 14px ${bodyStack}`;
    g.textAlign = "center";
    g.fillStyle = pal.muted;
    sum.months.forEach((m, i) => g.fillText(m, L.colX(i), line.y + line.h - 9));
    const pts = L.points.filter(Boolean);
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
      L.points.forEach((pt, i) => {
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

  function drawBars(c) {
    const L = sumL;
    const k = OUT(clamp01((c - 60) / 700));
    if (k <= 0) return;
    const { bars } = L;
    g.save();
    g.globalAlpha = k;
    g.translate(0, 18 * (1 - k));
    panel(bars.x, bars.y, bars.w, bars.h);
    // 기준선 둘은 몇 px 떨어져 있어 이름표를 양 끝에 나눠 단다(경고 기준은 왼쪽 선 아래, 확보 기준은 오른쪽 선 위).
    // 선은 정확한 기준(109.5) 자리에 긋고, 이름표는 사사오입한 글자(`*_label`, 110%)를 단다.
    g.font = `500 10px ${bodyStack}`;
    g.textBaseline = "alphabetic";
    for (const [v, label, dash, alignLeft] of [
      [sum.warning, sum.warning_label, [4, 4], true],
      [sum.secure, sum.secure_label, [1, 4], false],
    ]) {
      if (v == null) continue;
      const y = Math.round(L.yBar(v)) + 0.5;
      g.strokeStyle = rgba(textColor, 0.28);
      g.lineWidth = 1;
      g.setLineDash(dash);
      g.beginPath();
      g.moveTo(bars.x, y);
      g.lineTo(bars.x + bars.w, y);
      g.stroke();
      g.setLineDash([]);
      g.fillStyle = pal.muted;
      g.textAlign = alignLeft ? "left" : "right";
      g.fillText(label || `${v}%`, alignLeft ? bars.x + 6 : bars.x + bars.w - 6, alignLeft ? y + 12 : y - 4);
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
      const color = statusColor(b.status);
      const s = EASE(clamp01((c - 250 - i * 90) / 800));
      const top = L.yBar(b.rate);
      const full = L.barBot - top;
      if (s > 0 && full > 0) {
        const h = full * s;
        rr(cx - L.bw / 2, L.barBot - h, L.bw, h, Math.min(4, h / 2));
        g.fillStyle = color;
        g.fill();
      }
      const a = clamp01((c - 800 - i * 90) / 400);
      if (a > 0) {
        g.globalAlpha = k * a;
        g.font = `700 15px ${numStack}`;
        g.fillStyle = pal.text;
        g.fillText(`${round(b.rate, 1)}%`, cx, top - 7);
        g.globalAlpha = k;
      }
      // 막대 밑 두 줄(공정 이름·상태)은 생산계획 값 글자와 같은 14px 다(2026-10-03 사용자 결정).
      g.font = `500 14px ${bodyStack}`;
      g.fillStyle = pal.muted;
      g.fillText(fit(b.process, L.G.colW - 8), cx, L.barBot + 19);
      // 부족 대수 — 부족한 달만 숫자로 세우고(상태색), 나머지는 상태 이름만 단다.
      const a2 = clamp01((c - 900 - i * 90) / 400);
      if (a2 > 0) {
        g.globalAlpha = k * a2;
        const short = b.status === "shortage" && b.short != null && b.short > 0;
        g.font = `700 14px ${bodyStack}`;
        g.fillStyle = short ? color : pal.muted;
        g.fillText(short ? `${sum.text.shortage} ${b.short}대` : sum.text[b.status] || "", cx, L.barBot + 38);
        g.globalAlpha = k;
      }
    });
    if (L.lowest >= 0) {
      const e = OUT(clamp01((c - 1500) / 500));
      if (e > 0) {
        const b = sum.bn[L.lowest];
        g.globalAlpha = k * e;
        g.font = `600 11px ${bodyStack}`;
        g.textAlign = "center";
        g.fillStyle = pal["die-short"];
        g.fillText(sum.text.lowest, L.colX(L.lowest), L.yBar(b.rate) - 30 + 3 * (1 - e));
      }
    }
    g.restore();
  }

  function drawSheets(c) {
    const L = sumL;
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
      const padX = 12;
      g.textBaseline = "alphabetic";
      g.textAlign = "left";
      g.fillStyle = pal.text;
      g.font = `800 20px ${fontStack}`;
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
      const rows = [
        ["Density", sum.density[i], 2, "억Gb", s.kv1],
        [sum.text.wafer, sum.wafer[i], 0, "K", s.kv2],
      ];
      for (const [label, value, digits, unit, top] of rows) {
        const base = top + 17;
        g.font = `500 11px ${bodyStack}`;
        g.textAlign = "left";
        g.fillStyle = pal.muted;
        g.fillText(label, s.x + padX, base);
        g.textAlign = "right";
        g.font = `500 10px ${bodyStack}`;
        const unitW = g.measureText(unit).width;
        g.fillText(unit, s.x + s.w - padX, base);
        g.font = `700 18px ${numStack}`;
        g.fillStyle = pal.text;
        g.fillText(value == null ? "—" : (value * cnt).toFixed(digits), s.x + s.w - padX - unitW - 2, base);
      }
      // 도넛: 조각마다 50ms 씩 늦게 자란다. 조각 사이는 둘레의 0.9% 를 비운다.
      const slices = sum.mix[i] || [];
      if (s.box > 8 && slices.length) {
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
        const [topP, topShare] = slices.reduce((a, b) => (b[1] > a[1] ? b : a), slices[0]);
        g.textAlign = "center";
        g.fillStyle = pal.text;
        g.font = `700 ${Math.round(s.box * 0.15)}px ${numStack}`;
        g.fillText(`${Math.round(topShare * 100)}%`, s.cx, s.cy - s.box * 0.02);
        g.font = `500 ${Math.max(8, Math.round(s.box * 0.08))}px ${bodyStack}`;
        g.fillStyle = pal.muted;
        g.fillText(fit(sum.products[topP] ? sum.products[topP].name : "", s.box * 0.62), s.cx, s.cy + s.box * 0.12);
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

  function loop() {
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
    } else if (m.type === "begin") {
      beginAt = m.at;
    } else if (m.type === "progress") {
      reached = m.reached;
      total = Math.max(1, m.total);
      ready = !!m.ready;
    } else if (m.type === "resize") {
      resize(m.width, m.height, m.dpr);
    } else if (m.type === "summary") {
      sum = m.summary || null;
      fontsReady.then(() => {
        layoutSummary();
        port.postMessage({ type: "summary-ready", ok: !!sum });
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
      if (["begin", "progress", "summary", "summary-on", "run", "resize"].includes(key)) {
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

  // 툴바 Summary 단추. 테마 버튼 iframe 의 스크립트가 세우고 칠한다(intro_summary.summary_toolbar_script).
  // 여기서는 보임만 정한다 — 요약이 있고 오버레이가 감춰져 있을 때만 선다.
  function syncToolbar() {
    const button = document.getElementById(SUMMARY_BUTTON_ID);
    if (!button) return;
    const show = !api.done && !!summary && (!overlay || !overlay.visible);
    button.style.display = show ? "inline-flex" : "none";
  }

  api.setSummary = (payload) => {
    summary = payload && payload.available ? payload : null;
    // 요약이 없어 걷었던 오버레이(공식버전 계산 실패 뒤 Detail 등)는 새 요약이 오면 감춘 채 다시
    // 만든다 — 그래야 새로고침 없이 툴바 Summary 가 살아난다.
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
    "--tip": palette.tip,
    "--tip-shadow": palette["tip-shadow"],
    "--body": data.font_body || "sans-serif",
    "--display": `"${FONT_FAMILY}", ${data.font_body || "sans-serif"}`,
  };
  for (const [name, value] of Object.entries(vars)) if (value) stage.style.setProperty(name, value);

  $('[data-slot="brand"]').textContent = data.brand || "";
  $('[data-slot="logo"]').innerHTML = waferLogo(palette);
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
      if (m.type === "hits") hits = m.hits || [];
      else if (m.type === "summary-ready") {
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

  /* ------------------------------------------------ 상태: intro(입장) · summary(요약) · hidden(감춤) */
  let mode = intro ? "intro" : "hidden";
  let busy = false;
  // 툴바 Summary 로 연 요약을 닫으면 포커스를 그 단추로 돌려준다. 돌려주지 않으면 body 에 남아
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
    if (mode === "intro") update();
    else render();
  }

  function buildLabels() {
    const rows = text.rows || [];
    // 범례의 기준 숫자는 파이썬이 사사오입해 보낸 글자다(`secure_label` — 109.5 → 110%).
    const legendStatus = [
      [palette["die-ok"], `${(text.status || {}).secure || ""} >${summary.secure_label || `${summary.secure}%`}`],
      [palette["die-warn"], (text.status || {}).warning || ""],
      [palette["die-short"], `${(text.status || {}).shortage || ""} <${summary.warning_label || `${summary.warning}%`}`],
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
    // 차트는 캔버스라 낭독기가 읽지 못한다. 같은 값을 숨은 표로 둔다.
    const head = ["", "Density(억Gb)", "Wafer 계획(K)", "B/N 공정", "확보율(%)", "부족 대수"];
    const body = summary.months.map((month, i) => {
      const b = summary.bn[i];
      return [month, summary.density[i] ?? "", summary.wafer[i] ?? "", b ? b.process : "", b ? b.rate : "", b && b.short != null ? b.short : ""];
    });
    table.innerHTML =
      `<caption>${escapeHtml(summary.release || "")} ${escapeHtml(summary.period || "")}</caption>` +
      `<tr>${head.map((h) => `<th>${escapeHtml(h)}</th>`).join("")}</tr>` +
      body.map((r) => `<tr>${r.map((v) => `<td>${escapeHtml(v)}</td>`).join("")}</tr>`).join("");
    placeLabels();
  }

  function placeLabels() {
    if (!summary) return;
    const G = summaryGrid(window.innerWidth, window.innerHeight);
    $$(".sum-label").forEach((el, i) => {
      const row = G.rows[i];
      el.style.left = `${G.left}px`;
      el.style.width = `${Math.max(0, G.labelW - 6)}px`;
      el.style.top = `${row.y}px`;
      el.style.height = `${row.h}px`;
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
      if (h.k === "bar" && x >= h.x && x <= h.x + h.w && y >= h.y && y <= h.y + h.h) return h;
    }
    return null;
  }
  function tipHtml(h) {
    const month = summary.months[h.i];
    if (h.k === "line") return `<b>${escapeHtml(month)}</b> 생산계획 <b>${Number(summary.density[h.i]).toFixed(2)}</b>억Gb`;
    if (h.k === "seg") {
      const p = summary.products[h.p] || {};
      const share = (summary.mix[h.i] || []).find(([index]) => index === h.p);
      return `<b>${escapeHtml(p.name || "")}</b> · ${share ? (share[1] * 100).toFixed(1) : ""}% <span class="dim">${escapeHtml(month)}</span>`;
    }
    const b = summary.bn[h.i];
    const st = (text.status || {})[b.status] || "";
    const short = b.status === "shortage" && b.short ? `${(text.status || {}).shortage || ""} <b>${b.short}대</b>` : st;
    const units = b.need != null && b.have != null ? `<br><span class="dim">소요 ${b.need}대 / 보유 ${b.have}대</span>` : "";
    return `<b>${escapeHtml(month)}</b> B/N ${escapeHtml(b.process)}<br>확보율 <b>${b.rate}%</b> · ${short}${units}`;
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
    // 화면이 Summary 단추 속으로 접히며 뒤의 요약이 드러난다.
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
