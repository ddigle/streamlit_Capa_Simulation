// 첫 접속 입장 화면. `intro_overlay.py` 가 이 파일 앞에 OVERLAY_HTML · OVERLAY_CSS · FONT_DATA 세
// 상수를 붙여 등록한다(파일에서 읽은 intro.html · intro.css 와 base64 로 바꾼 글꼴).
//
// 오버레이는 컴포넌트 칸이 아니라 document.body 에 붙인 호스트(shadow root)에 그린다. 칸 안에
// 두면 Streamlit 의 머리말·사이드바 쌓임 맥락 아래에 깔리고, 칸은 파이썬이 display:none 으로
// 접어 둔다. 파이썬으로는 아무것도 보내지 않는다 — setStateValue · setTriggerValue 는 rerun 을
// 부르고, 첫 실행 도중이면 그 실행을 끊는다.
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

const sleep = (ms) => new Promise((resolve) => window.setTimeout(resolve, ms));

function withAlpha(hex, alpha) {
  const value = String(hex || "").replace("#", "");
  if (value.length !== 6) return hex;
  const n = parseInt(value, 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
}

function letters(text) {
  return [...String(text)]
    .map((ch) => (ch === " " ? "<span>&nbsp;</span>" : `<span>${escapeHtml(ch)}</span>`))
    .join("");
}

function escapeHtml(text) {
  return String(text).replace(/[&<>"']/g, (ch) => `&#${ch.charCodeAt(0)};`);
}

// 웨이퍼 심볼. 다이 순서(data-o)는 각도와 반지름으로 정해 나선처럼 차오르게 한다.
function waferSymbol(palette) {
  const step = 7.4;
  const size = 6;
  let dies = "";
  let n = 0;
  for (let y = -5; y <= 5; y++) {
    for (let x = -5; x <= 5; x++) {
      const far = Math.hypot(Math.abs(x * step) + size / 2, Math.abs(y * step) + size / 2);
      if (far > 40) continue;
      const cx = 50 + x * step;
      const cy = 50 + y * step;
      const order = ((Math.atan2(y, x) + Math.PI) / (2 * Math.PI)) * 0.7 + (Math.hypot(x, y) / 6) * 0.3;
      const fill = n % 13 === 5 ? palette["die-warn"] : n === 31 ? palette["die-short"] : palette.accent;
      dies += `<rect class="die" data-o="${order.toFixed(3)}" x="${(cx - size / 2).toFixed(2)}" y="${(cy - size / 2).toFixed(2)}" width="${size}" height="${size}" rx=".8" fill="${fill}"/>`;
      n += 1;
    }
  }
  return `<svg viewBox="0 0 100 100" aria-hidden="true"><path class="rim" pathLength="1" d="M53 93.9 A44 44 0 1 0 47 93.9 L50 90.6 Z"/><g>${dies}</g></svg>`;
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
    "--surface": palette.surface,
    "--veil-mid": withAlpha(palette.surface, 0.8),
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
  $('[data-slot="symbol"]').innerHTML = waferSymbol(palette);
  $('[data-slot="word"]').innerHTML = letters(data.brand || "");
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

  const timers = [];
  let alive = true;
  let poller = 0;
  window.__capaIntro.stop = () => {
    alive = false;
    timers.forEach((id) => window.clearTimeout(id));
    window.clearInterval(poller);
    document.removeEventListener("keydown", onKey);
  };
  const ok = () => alive;
  const anim = (el, keyframes, options = {}) =>
    el.animate(keyframes, { fill: "both", easing: EASE, ...options }).finished.catch(() => {});
  async function animClip(el, keyframes, options) {
    const animation = el.animate(keyframes, { fill: "forwards", easing: EASE, ...options });
    await animation.finished.catch(() => {});
    el.style.clipPath = "none";
    animation.cancel();
  }

  /* ------------------------------------------------ 입장 상태: 인트로 → 로딩 → 준비 → 입장 */
  const button = $(".enter");
  const buttonText = $(".enter .txt");
  const status = $(".status");
  const hint = $(".hint");
  const items = $$(".steps li");
  const entry = $(".entry");
  const t0 = performance.now();
  let reached = 0; // 끝낸 단계 수
  let ready = false;
  let introDone = false;
  let shown = 0;
  let readyAt = 0;
  let progressText = "";
  let fallback = false;

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
      button.animate([{ transform: "scale(1)" }, { transform: "scale(1.04)" }, { transform: "scale(1)" }], {
        duration: 520,
        easing: OUT,
      });
    }
    button.focus({ preventScroll: true });
  }

  function reach(count) {
    if (ready || count <= reached) return;
    reached = Math.min(steps.length - 1, count);
    render();
  }

  function setReady() {
    if (ready) return;
    ready = true;
    readyAt = performance.now();
    render();
    arm();
  }

  function introFinished() {
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

  /* -------------------------------------------------------------------- 인트로 연출 */
  async function intro() {
    const bg = $(".intro-bg");
    const symbol = $(".symbol svg");
    const rim = $(".rim");
    const dies = $$(".die");
    const word = $(".word");
    const glyphs = $$(".word span");
    dies.forEach((die) => (die.style.opacity = "0"));
    glyphs.forEach((glyph) => (glyph.style.opacity = "0"));
    anim(bg, [{ backgroundColor: frame0 }, { backgroundColor: palette.surface }], { duration: 700, easing: "ease-in-out" });
    await sleep(260);
    if (!ok()) return;
    anim(rim, [{ strokeDashoffset: 1 }, { strokeDashoffset: 0 }], { duration: 1000 }).then(() => {
      rim.style.strokeDasharray = "none";
    });
    await sleep(520);
    if (!ok()) return;
    dies.forEach((die) => {
      die.style.opacity = "";
      anim(die, [{ opacity: 0, transform: "scale(.3)" }, { opacity: 1, transform: "scale(1)" }], {
        duration: 320,
        delay: Number(die.dataset.o) * 620,
        easing: OUT,
      });
    });
    await sleep(420);
    if (!ok()) return;
    // 벌어진 글자가 모여드는 연출. 끝 자간은 메인 타이틀과 같은 0 이다(왼쪽 여백은 마지막 글자 뒤 자간을 상쇄해 가운데를 맞춘다).
    anim(word, [{ letterSpacing: ".6em", paddingLeft: ".6em" }, { letterSpacing: "0em", paddingLeft: "0em" }], {
      duration: 1200,
      easing: OUT,
    });
    glyphs.forEach((glyph, index) => {
      glyph.style.opacity = "";
      anim(glyph, [{ opacity: 0, filter: "blur(8px)" }, { opacity: 1, filter: "blur(0px)" }], {
        duration: 700,
        delay: index * 45,
        easing: OUT,
      });
    });
    await sleep(1400);
    if (!ok()) return;
    const box = symbol.getBoundingClientRect();
    const cx = box.left + box.width / 2;
    const cy = box.top + box.height / 2;
    const r0 = box.width * 0.44;
    const radius = Math.hypot(Math.max(cx, window.innerWidth - cx), Math.max(cy, window.innerHeight - cy));
    entry.style.clipPath = `circle(${r0}px at ${cx}px ${cy}px)`;
    entry.style.visibility = "visible";
    revealEntry(620);
    anim(symbol, [{ transform: "scale(1)", opacity: 1 }, { transform: "scale(1.9)", opacity: 0 }], {
      duration: 700,
      easing: "cubic-bezier(.5,0,.75,0)",
    });
    anim(word, [{ opacity: 1 }, { opacity: 0 }], { duration: 280, easing: "linear" });
    await animClip(entry, [{ clipPath: `circle(${r0}px at ${cx}px ${cy}px)` }, { clipPath: `circle(${radius}px at ${cx}px ${cy}px)` }], {
      duration: 1200,
    });
  }

  async function introReduced() {
    $(".intro").style.visibility = "hidden";
    $(".intro-bg").style.visibility = "hidden";
    entry.style.visibility = "visible";
    revealEntry(0);
    await sleep(350);
  }

  function revealEntry(delay) {
    $$(".head > *, .main > *").forEach((part, index) =>
      anim(
        part,
        reduce
          ? [{ opacity: 0 }, { opacity: 1 }]
          : [{ opacity: 0, transform: "translateY(16px)" }, { opacity: 1, transform: "translateY(0)" }],
        { duration: reduce ? 300 : 760, delay: delay + index * 55, easing: OUT },
      ),
    );
  }

  /* ---------------------------------------------------- 입장 화면 배경: 웨이퍼 맵 */
  // 검사 원이 중심에서 퍼지며 다이마다 확보·경고·부족 색이 들어간다. 준비되면 천천히 돈다.
  // 준비 신호는 한순간에 오지만 그림은 한 프레임도 건너뛰지 않는다 — 덮인 범위·다이 밝기·검사 원
  // 모두 연속값(shown · settle)에서 나온다.
  const canvas = $(".map");
  const EDGE = 0.07; // 검사 원 안쪽으로 색이 번지는 폭(반지름 비)
  const smooth = (value) => {
    const x = Math.min(1, Math.max(0, value));
    return x * x * (3 - 2 * x);
  };
  const N = 24;
  const mapDies = [];
  const colors = [palette["die-ok"], palette["die-warn"], palette["die-short"]];
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
  let last = performance.now();
  let settle = 0;
  function frame(now) {
    if (!alive) return;
    const dt = Math.min(64, now - last);
    last = now;
    const target = ready ? 1 : Math.min(0.97, (reached + 0.45) / steps.length);
    // 준비 뒤 마지막 확장은 조금 더 느긋하게(시간 상수 0.8초) 가장자리까지 번진다.
    shown += (target - shown) * Math.min(1, dt / (ready ? 800 : 450));
    settle += ((ready ? 1 : 0) - settle) * Math.min(1, dt / 700);
    if (entry.style.visibility === "visible") draw(reduce ? 0 : now);
    window.requestAnimationFrame(frame);
  }
  function draw(t) {
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    const w = canvas.clientWidth;
    const h = canvas.clientHeight;
    const W = Math.max(1, Math.round(w * dpr));
    const H = Math.max(1, Math.round(h * dpr));
    if (canvas.width !== W || canvas.height !== H) {
      canvas.width = W;
      canvas.height = H;
    }
    const g = canvas.getContext("2d");
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    const narrow = w < 760;
    const R = narrow ? Math.min(w * 0.6, h * 0.32) : Math.min(h * 0.6, w * 0.4);
    const cx = narrow ? w * 0.64 : w * 0.7;
    const cy = narrow ? h * 0.28 : h * 0.5;
    // shown 이 1 에 닿으면 front 1.06 — 가장 바깥 다이(반지름 0.93)까지 다 덮인다.
    const front = shown * 1.06;
    g.clearRect(0, 0, w, h);
    g.save();
    g.translate(cx, cy);
    g.rotate(t * 0.000035);
    g.beginPath();
    g.arc(0, 0, R, 0, Math.PI * 2);
    g.fillStyle = palette.wafer;
    g.fill();
    const ds = R / N;
    const sz = ds * 0.8;
    for (const d of mapDies) {
      const cover = smooth((front - d.r) / EDGE);
      const x = d.x * R - sz / 2;
      const y = d.y * R - sz / 2;
      if (cover < 1) {
        g.globalAlpha = 1 - cover;
        g.fillStyle = palette["die-idle"];
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
    // 검사 원은 가장자리에 다가가며 옅어지고, 준비 뒤에는 settle 만큼 사라진다.
    const ring = 0.75 * smooth((1.04 - front) / 0.14) * (1 - settle);
    if (ring > 0.01) {
      g.globalAlpha = ring;
      g.strokeStyle = palette.accent;
      g.lineWidth = 1.5;
      g.beginPath();
      g.arc(0, 0, Math.max(2, Math.min(front, 1) * R), 0, Math.PI * 2);
      g.stroke();
    }
    g.globalAlpha = 0.24;
    g.strokeStyle = palette.text;
    g.lineWidth = 1;
    const notch = 0.035;
    g.beginPath();
    g.arc(0, 0, R * 1.02, Math.PI / 2 + notch, Math.PI / 2 - notch + Math.PI * 2);
    g.lineTo(0, R * 0.985);
    g.closePath();
    g.stroke();
    g.globalAlpha = 1;
    g.restore();
  }
  window.requestAnimationFrame(frame);

  /* -------------------------------------------------------------------------- 시작 */
  render();
  function begin() {
    if (!alive || window.__capaIntro.begun) return;
    window.__capaIntro.begun = true;
    holding = false;
    stage.classList.add("begun");
    (reduce ? introReduced() : intro()).then(() => {
      if (alive) introFinished();
    });
  }
  if (themeReloadPending(theme)) {
    holding = true;
    timers.push(window.setTimeout(begin, THEME_RELOAD_HOLD_MAX_MS));
  } else begin();
}
