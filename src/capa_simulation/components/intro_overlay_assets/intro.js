// 첫 접속 입장 화면. `intro_overlay.py` 가 이 파일 앞에 OVERLAY_HTML · OVERLAY_CSS · FONT_DATA 세
// 상수를 붙여 등록한다(파일에서 읽은 intro.html · intro.css 와 base64 로 바꾼 글꼴).
//
// 오버레이는 컴포넌트 칸이 아니라 document.body 에 붙인 호스트(shadow root)에 그린다. 칸 안에
// 두면 Streamlit 의 머리말·사이드바 쌓임 맥락 아래에 깔리고, 칸은 파이썬이 display:none 으로
// 접어 둔다. 파이썬으로는 아무것도 보내지 않는다 — setStateValue · setTriggerValue 는 rerun 을
// 부르고, 첫 실행 도중이면 그 실행을 끊는다.
//
// **움직임은 메인 스레드에서 돌리지 않는다.** 첫 로딩 동안 메인 스레드는 Streamlit 이 HOME 의 표·
// 그림을 그리느라 수백 ms 씩 막힌다(8514 실측 최대 0.5초). 그 사이 메인 스레드의 캔버스·선 긋기·자간
// 애니메이션은 그대로 멈춘다. 그래서 심볼·워드마크·원형 펼침·웨이퍼 맵은 모두 `scene()` 이 **워커의
// OffscreenCanvas** 에 그리고, 입장 화면의 글자·단추는 합성기가 돌리는 투명도·이동만 쓰며 시작 시각을
// 미리 예약한다. 워커나 OffscreenCanvas 를 못 쓰는 브라우저에서는 같은 `scene()` 을 메인 스레드에서
// 돌린다(전과 같은 품질).
//
// 「다 그렸다」는 신호는 `[data-testid="stApp"]` 의 `data-test-script-state` 다(running →
// notRunning). 파이썬이 끝에 표지를 그리는 방식은 `st.stop()` 뒤로는 아무것도 보낼 수 없어 쓸 수
// 없다. 비공식 속성이라 Streamlit 을 올릴 때 확인한다 — 속성이 없으면 인트로가 끝나는 대로
// 버튼을 켠다(덮개가 앱을 가두는 일은 없게 한다).

const HOST_ID = "capa-intro-host";
const FONT_FAMILY = "CapaIntroDisplay";
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

export default function (component) {
  // 같은 페이지에서 다시 불리는 경우(테마 변경 등)는 이미 떠 있거나 끝난 것이다.
  if (window.__capaIntro) return;
  window.__capaIntro = { done: false };
  if (enteredBefore()) {
    window.__capaIntro.done = true;
    return;
  }
  try {
    start(component.data || {});
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

// 입장 화면의 HTML 글자(타이틀·라벨·Enter)가 쓰는 글꼴. 워커는 따로 받는다(`fontBuffer`).
function registerFont() {
  if (!FONT_DATA || !document.fonts || typeof FontFace === "undefined") return;
  for (const face of document.fonts) if (face.family === FONT_FAMILY) return;
  const face = new FontFace(FONT_FAMILY, `url(data:font/woff2;base64,${FONT_DATA})`, {
    weight: "800",
    stretch: "75%",
  });
  document.fonts.add(face);
  face.load().catch(() => {});
}

function fontBuffer() {
  if (!FONT_DATA) return null;
  const binary = window.atob(FONT_DATA);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes.buffer;
}

// theme_toggle.py 의 place() 와 같은 규칙이다 — 저장된 값이 "Dark" 면 dark, 그 밖(고른 적 없음 포함)은
// light 이고, 주소의 테마 인자가 그와 다르면 그 스크립트가 고쳐 쓰고 새로고침한다.
function themeReloadPending(theme) {
  if (!theme || !theme.param) return false;
  let stored = "System";
  try {
    const key = theme.storage_prefix + window.location.pathname + theme.storage_suffix;
    stored = JSON.parse(window.localStorage.getItem(key) || '"System"');
  } catch (error) {
    stored = "System";
  }
  const mode = stored === "Dark" ? "dark" : "light";
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

/* ============================================================================================
 * 장면 — 심볼·워드마크·원형 펼침·웨이퍼 맵을 캔버스 하나에 그린다.
 *
 * 이 함수는 문자열로 바뀌어 워커에서 돈다(`startScene`). **이 파일의 다른 이름을 하나도 쓰지 않는다**
 * — 필요한 것은 모두 `init` 메시지로 받고 도우미는 전부 안에 둔다. 워커를 못 쓰면 같은 함수를 메인
 * 스레드에서 `port` 흉내로 돌린다. 시각은 절대값(timeOrigin + now)이다.
 *
 * 메시지: init(canvas·크기·팔레트·글꼴…) · begin(at) · progress(reached·total·ready) · resize · stats · stop
 * ============================================================================================ */
function scene(port) {
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
  let frame0 = [0, 0, 0, 1];
  let surface = [0, 0, 0, 1];
  let initAt = 0;
  let beginAt = 0;
  let reached = 0;
  let total = 5;
  let ready = false;
  let stopped = false;
  let shown = 0;
  let settle = 0;
  let last = 0;
  const stats = { frames: 0, slow: 0, max: 0 };
  let symbolDies = [];
  let mapDies = [];
  // 테두리 길이(뷰박스 100 단위): 노치를 뺀 원호 + 노치 두 변.
  const RIM_START = Math.atan2(43.9, 3);
  const RIM_END = Math.atan2(43.9, -3);
  const RIM_LEN = 44 * (TAU - (RIM_END - RIM_START)) + 2 * Math.hypot(3, 3.3);

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
    if (canvas) {
      canvas.width = Math.max(1, Math.round(W * dpr));
      canvas.height = Math.max(1, Math.round(H * dpr));
    }
  }

  function loadFont(buffer, family) {
    if (!buffer || typeof FontFace === "undefined") return;
    const set = typeof self !== "undefined" && self.fonts ? self.fonts : null;
    if (!set) return;
    try {
      const face = new FontFace(family, buffer, { weight: "800", stretch: "75%" });
      set.add(face);
      face.load().catch(() => {});
    } catch (error) {
      /* 글꼴을 못 올려도 본문 글꼴로 그린다 */
    }
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
  function drawMap(clock) {
    const narrow = W <= 760; // intro.css 의 @media (max-width: 760px) 와 같은 경계
    const R = narrow ? Math.min(W * 0.6, H * 0.32) : Math.min(H * 0.6, W * 0.4);
    const cx = narrow ? W * 0.64 : W * 0.7;
    const cy = narrow ? H * 0.28 : H * 0.5;
    const t = reduce ? 0 : clock;
    const front = shown * 1.06;
    const EDGE = 0.07;
    const smooth = (v) => {
      const x = clamp01(v);
      return x * x * (3 - 2 * x);
    };
    const colors = [pal["die-ok"], pal["die-warn"], pal["die-short"]];
    g.save();
    g.translate(cx, cy);
    g.rotate(t * 0.000035);
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
        g.globalAlpha = 1 - cover;
        g.fillStyle = pal["die-idle"];
        g.fillRect(x, y, sz, sz);
      }
      if (cover > 0) {
        const loading = 0.62 + 0.3 * d.k;
        const resting = 0.5 + 0.3 * (0.5 + 0.5 * Math.sin(t * 0.0012 + d.k * 30));
        g.globalAlpha = cover * (loading + (resting - loading) * settle);
        g.fillStyle = colors[d.st];
        g.fillRect(x, y, sz, sz);
      }
    }
    const ring = 0.75 * smooth((1.04 - front) / 0.14) * (1 - settle);
    if (ring > 0.01) {
      g.globalAlpha = ring;
      g.strokeStyle = pal.accent;
      g.lineWidth = 1.5;
      g.beginPath();
      g.arc(0, 0, Math.max(2, Math.min(front, 1) * R), 0, TAU);
      g.stroke();
    }
    g.globalAlpha = 0.24;
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
    g.fillStyle = grad;
    g.fillRect(0, 0, W, H);
  }

  function draw(at) {
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, W, H);
    // 시작 전(테마 새로고침을 기다리는 동안)에는 아무것도 그리지 않는다 — 아래 HTML 바탕(앱 바탕색)만 보인다.
    if (!beginAt) return;
    const t = at - beginAt;
    const clock = at - initAt;
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
    if (stopped) return;
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

  port.onmessage = (event) => {
    const m = (event && event.data) || {};
    if (m.type === "init") {
      canvas = m.canvas;
      pal = m.palette || {};
      brand = m.brand || "";
      reduce = !!m.reduce;
      fontStack = `"${m.family}", ${m.body || "sans-serif"}`;
      frame0 = parseColor(m.frame0 || pal.surface);
      surface = parseColor(pal.surface);
      resize(m.width, m.height, m.dpr);
      g = canvas.getContext("2d");
      build();
      loadFont(m.font, m.family);
      initAt = now();
      nextFrame(frame);
    } else if (m.type === "begin") {
      beginAt = m.at;
    } else if (m.type === "progress") {
      reached = m.reached;
      total = Math.max(1, m.total);
      ready = !!m.ready;
    } else if (m.type === "resize") {
      resize(m.width, m.height, m.dpr);
    } else if (m.type === "stats") {
      port.postMessage({ type: "stats", frames: stats.frames, slow: stats.slow, max: Math.round(stats.max) });
    } else if (m.type === "stop") {
      stopped = true;
    }
  };
}

// 장면을 워커에 띄운다. 못 하면(워커·OffscreenCanvas 없음, 워커 오류) 같은 장면을 메인 스레드에서 돌린다.
function startScene(canvas, init) {
  let mode = "main";
  let worker = null;
  let workerUrl = "";
  let send = () => {};
  let replay = [];
  const waiting = [];
  const onReply = (m) => {
    if (m && m.type === "stats") waiting.splice(0).forEach((resolve) => resolve({ mode, ...m }));
  };
  const runOnMain = (target) => {
    mode = "main";
    const port = { onmessage: null, postMessage: onReply };
    scene(port);
    send = (m) => port.onmessage && port.onmessage({ data: m });
    send({ ...init, type: "init", canvas: target, font: null });
    replay.forEach((m) => send(m));
  };
  try {
    if (typeof Worker !== "function" || typeof OffscreenCanvas !== "function" || !canvas.transferControlToOffscreen) {
      throw new Error("worker canvas unavailable");
    }
    workerUrl = URL.createObjectURL(new Blob([`(${scene.toString()})(self);`], { type: "text/javascript" }));
    worker = new Worker(workerUrl);
    const offscreen = canvas.transferControlToOffscreen();
    const font = fontBuffer();
    worker.onmessage = (event) => onReply(event.data);
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
    worker.postMessage({ ...init, type: "init", canvas: offscreen, font }, font ? [offscreen, font] : [offscreen]);
    send = (m) => worker && worker.postMessage(m);
    mode = "worker";
  } catch (error) {
    if (worker) worker.terminate();
    worker = null;
    runOnMain(canvas);
  }
  return {
    post(m) {
      if (m.type === "begin" || m.type === "progress") replay = [...replay.filter((r) => r.type !== m.type), m];
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

function start(data) {
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const palette = data.palette || {};
  const text = data.text || {};
  const steps = Array.isArray(data.steps) && data.steps.length ? data.steps : [{ label: "" }];
  const app = document.querySelector('[data-testid="stApp"]');
  const frame0 = app ? getComputedStyle(app).backgroundColor : palette.surface;

  registerFont();
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
    "--line": palette.line,
    "--track": palette.track,
    "--button": palette.button,
    "--button-text": palette["button-text"],
    "--button-off-line": palette["button-off-line"],
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

  // 덮개 위 휠·터치가 아래 앱을 굴리지 않게 한다.
  host.addEventListener("wheel", (event) => event.preventDefault(), { passive: false });
  host.addEventListener("touchmove", (event) => event.preventDefault(), { passive: false });
  document.body.appendChild(host);
  setInert(true);

  const sceneHandle = startScene($(".scene"), {
    width: window.innerWidth,
    height: window.innerHeight,
    dpr: window.devicePixelRatio || 1,
    palette,
    brand: data.brand || "",
    reduce,
    family: FONT_FAMILY,
    body: data.font_body || "sans-serif",
    frame0,
  });
  window.__capaIntro.mode = sceneHandle.mode;
  window.__capaIntro.stats = () => sceneHandle.stats();
  const onResize = () =>
    sceneHandle.post({ type: "resize", width: window.innerWidth, height: window.innerHeight, dpr: window.devicePixelRatio || 1 });
  window.addEventListener("resize", onResize);

  const timers = [];
  let alive = true;
  let poller = 0;
  window.__capaIntro.stop = () => {
    alive = false;
    timers.forEach((id) => window.clearTimeout(id));
    window.clearInterval(poller);
    document.removeEventListener("keydown", onKey);
    window.removeEventListener("resize", onResize);
    sceneHandle.stop();
  };
  const anim = (el, keyframes, options = {}) =>
    el.animate(keyframes, { fill: "both", easing: EASE, ...options }).finished.catch(() => {});
  const revealAnimations = new Map();

  /* ------------------------------------------------ 입장 상태: 인트로 → 로딩 → 준비 → 입장 */
  const button = $(".enter");
  const buttonText = $(".enter .txt");
  const status = $(".status");
  const hint = $(".hint");
  const items = $$(".steps li");
  const t0 = performance.now();
  let reached = 0; // 끝낸 단계 수
  let ready = false;
  let introDone = false;
  let readyAt = 0;
  let progressText = "";
  let fallback = false;

  const sendProgress = () => sceneHandle.post({ type: "progress", reached, total: steps.length, ready });

  function render() {
    items.forEach((li, index) => {
      li.className = ready || index < reached ? "done" : index === reached ? "active" : "";
    });
    if (ready) status.textContent = `${text.ready || ""} · ${((readyAt - t0) / 1000).toFixed(1)}초`;
    else if (fallback) status.textContent = text.slow || "";
    else status.textContent = progressText || text.boot || "";
    const can = (ready || fallback) && introDone;
    button.disabled = !can;
    buttonText.textContent = can ? text.enter || "Enter" : text.waiting || "";
  }

  function arm() {
    if (!((ready || fallback) && introDone)) return;
    hint.hidden = true;
    render();
    if (!reduce) {
      // 단추가 다 떠오른 뒤에 한 번 맥동한다. `scale` 은 떠오르기의 transform 과 따로 놀아 서로 덮지 않는다.
      const rising = revealAnimations.get(button);
      Promise.resolve(rising && rising.finished)
        .catch(() => {})
        .then(() => {
          if (alive) button.animate([{ scale: 1 }, { scale: 1.04 }, { scale: 1 }], { duration: 520, easing: OUT });
        });
    }
    button.focus({ preventScroll: true });
  }

  function reach(count) {
    if (ready || count <= reached) return;
    reached = Math.min(steps.length - 1, count);
    render();
    sendProgress();
  }

  function setReady() {
    if (ready) return;
    ready = true;
    readyAt = performance.now();
    render();
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

  function onKey(event) {
    if (event.key === "Enter" && !button.disabled && event.target === document.body) leave();
  }
  document.addEventListener("keydown", onKey);
  button.addEventListener("click", () => {
    if (!button.disabled) leave();
  });

  let leaving = false;
  async function leave() {
    if (leaving) return;
    leaving = true;
    rememberEntered();
    setInert(false);
    const box = button.getBoundingClientRect();
    const x = box.left + box.width / 2;
    const y = box.top + box.height / 2;
    const radius = Math.hypot(Math.max(x, window.innerWidth - x), Math.max(y, window.innerHeight - y));
    // 이때는 앱이 다 그려져 메인 스레드가 한가하다 — 원형으로 접는 것은 그대로 clip-path 로 한다.
    if (reduce) await anim(stage, [{ opacity: 1 }, { opacity: 0 }], { duration: 260, easing: "linear" });
    else {
      await anim(stage, [{ clipPath: `circle(${radius}px at ${x}px ${y}px)` }, { clipPath: `circle(0px at ${x}px ${y}px)` }], {
        duration: 950,
      });
    }
    release();
  }

  /* --------------------------------------------------------- 진행 신호(앱 실행 상태·HOME 막대) */
  // HOME 은 본문 맨 위에 `LoadingProgress` 막대를 「단계 이름 · N%」로 띄운다. 그 퍼센트가 각
  // 단계의 `until` 을 넘으면 그 단계를 끝낸 것으로 친다. 막대가 처음 보이면 첫 단계(시나리오)가 끝난
  // 것이다. HOME 이 아닌 화면에는 막대가 없으므로 실행이 끝날 때 한꺼번에 찬다.
  const signalMissing = !app || app.getAttribute("data-test-script-state") == null;
  const theme = data.theme || {};
  let holding = false;
  let settledAt = 0;
  let topPercent = 0;
  function poll() {
    if (!alive) return;
    const bar = document.querySelector('[data-testid="stProgress"]');
    if (bar) {
      const label = (bar.innerText || "").trim().replace(/\s+/g, " ");
      const meter = bar.querySelector('[role="progressbar"]');
      const fromMeter = meter ? Number(meter.getAttribute("aria-valuenow")) : NaN;
      const fromLabel = Number((label.match(/(\d+)\s*%\s*$/) || [])[1]);
      const percent = Number.isFinite(fromLabel) ? fromLabel : Number.isFinite(fromMeter) ? fromMeter : 0;
      topPercent = Math.max(topPercent, percent);
      if (label) progressText = label;
      let count = 1;
      steps.forEach((step, index) => {
        if (step.until != null && topPercent >= step.until) count = Math.max(count, index + 1);
      });
      reach(count);
      render();
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
  poller = window.setInterval(poll, POLL_MS);
  if (signalMissing) setReady();

  // 입장 화면 글자는 시작할 때 **지연을 실어 미리** 걸어 둔다. 투명도·이동 애니메이션은 합성기가 돌리므로,
  // 그 순간 메인 스레드가 막혀 있어도 제때 나타난다.
  function revealEntry(delay) {
    $$(".head > *, .main > *").forEach((part, index) => {
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
  render();
  function begin() {
    if (!alive || window.__capaIntro.begun) return;
    window.__capaIntro.begun = true;
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
  if (themeReloadPending(theme)) {
    holding = true;
    timers.push(window.setTimeout(begin, THEME_RELOAD_HOLD_MAX_MS));
  } else begin();
}
