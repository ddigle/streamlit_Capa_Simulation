// Purpose: 입장 화면 intro.js 의 장면(scene)을 가짜 캔버스로 돌려 Summary 토글의 그리기 동작을 잰다.
//
// `tests/test_intro_scene_behavior.py` 가 node(또는 bun)로 부른다. 인자: intro.js 경로, 요약 값 JSON 경로,
// 팔레트 JSON 경로. 결과는 JSON 한 덩어리로 stdout 에 찍는다. 시간·난수·프레임은 여기서 정한다 — 같은
// 입력이면 같은 그리기 호출이 나온다. 그리기 호출은 (이름, 인자, 그 순간의 그리기 상태)로 기록한다.
import crypto from "crypto";
import fs from "fs";

const [, , introPath, payloadPath, palettePath] = process.argv;
const payload = JSON.parse(fs.readFileSync(payloadPath, "utf8"));
const PALETTE = JSON.parse(fs.readFileSync(palettePath, "utf8"));

function loadScene() {
  const src = fs.readFileSync(introPath, "utf8");
  const code =
    'const OVERLAY_HTML="";const OVERLAY_CSS="";const FONT_DATA="";const NUMBER_FONT_DATA="";\n' +
    src.replace("export default function", "function __entry") +
    "\n;return { scene, summaryGrid };";
  return new Function(code)();
}

let clock = 0;
let queue = [];
Object.defineProperty(globalThis, "performance", {
  value: { timeOrigin: 0, now: () => clock },
  configurable: true,
  writable: true,
});
globalThis.requestAnimationFrame = (cb) => queue.push(cb);
let seed = 1;
Math.random = () => {
  seed = (seed * 16807) % 2147483647;
  return (seed - 1) / 2147483646;
};

const DRAW = new Set(["fill", "stroke", "fillText", "fillRect", "strokeText", "clearRect"]);
const STATE = ["globalAlpha", "fillStyle", "strokeStyle", "font", "textAlign", "lineWidth"];
const round = (v) => (typeof v === "number" ? Math.round(v * 1000) / 1000 : Array.isArray(v) ? v.map(round) : v);

function fakeCanvas(log) {
  const state = { font: "10px sans" };
  const ctx = new Proxy(
    {},
    {
      get(_t, prop) {
        if (prop === "measureText") {
          return (text) => {
            const m = /(\d+(?:\.\d+)?)px/.exec(state.font || "10px");
            return { width: String(text).length * parseFloat(m ? m[1] : 10) * 0.56 };
          };
        }
        if (prop === "createLinearGradient") {
          return (...a) => {
            log.push(["grad", ...a.map(round)]);
            return { addColorStop: (...b) => log.push(["stop", ...b]) };
          };
        }
        if (prop in state) return state[prop];
        if (DRAW.has(prop)) {
          return (...args) => log.push([prop, ...args.map(round), STATE.map((k) => round(state[k])).join("|")]);
        }
        return (...args) => log.push([prop, ...args.map(round)]);
      },
      set(_t, prop, value) {
        state[prop] = value;
        return true;
      },
    },
  );
  return { width: 1, height: 1, getContext: () => ctx };
}

async function open(summary, { reduce = false, width = 1400, height = 900 } = {}) {
  const { scene, summaryGrid } = loadScene();
  seed = 1;
  clock = 1000;
  queue = [];
  const log = [];
  const port = { onmessage: null, postMessage: () => {} };
  scene(port, summaryGrid);
  const send = (m) => port.onmessage({ data: m });
  send({ type: "init", canvas: fakeCanvas(log), palette: PALETTE, brand: "S.PKG CAPA", reduce, paused: false, family: "D", number: "N", body: "B", frame0: PALETTE.surface, width, height, dpr: 1, fonts: [] });
  send({ type: "begin", at: clock });
  send({ type: "progress", reached: 6, total: 6, ready: true });
  send({ type: "summary", summary: { ...summary, text: { secure: "확보", warning: "경고", shortage: "부족", lowest: "최저", wafer: "Wafer 계획", past: "과거 구간" } } });
  await new Promise((resolve) => setTimeout(resolve, 0));
  const tick = (to) => {
    while (clock < to) {
      clock = Math.min(to, clock + 16);
      for (const cb of queue.splice(0)) cb();
    }
  };
  tick(clock + 3000);
  send({ type: "summary-on", at: clock, charts: clock + 420, rows: [0, 380, 800], look: { fade: 0.2, mono: 1 }, instant: true, fromApp: true });
  const frame = () => {
    log.length = 0;
    clock += 16;
    for (const cb of queue.splice(0)) cb();
    return log.slice();
  };
  return { send, tick, frame, log, queued: () => queue.length, now: () => clock };
}

const view = (advance, shipment, comparison) => ({ type: "view", view: { advance, shipment, comparison } });
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const results = {};
const plain = { ...payload };
delete plain.toggles;

// 장면 하나가 쓰는 시계·프레임 줄은 이 파일에 하나뿐이다 — 장면은 차례로 하나씩 열고 끝낸다.
// 1) 토글 셋을 다 끈 그림은 토글 값이 없는 요약의 그림과 같다(조립 중·끝).
const snapshots = async (summary) => {
  const scene = await open(summary);
  const frames = [];
  for (const at of [300, 900, 1800]) {
    scene.tick(scene.now() + at);
    frames.push(scene.frame());
  }
  return frames;
};
const offFrames = await snapshots(payload);
const plainFrames = await snapshots(plain);
[300, 1200, 3000].forEach((at, i) => {
  results[`off_equals_plain_${at}`] = same(offFrames[i], plainFrames[i]);
});
// 기본 장면 자체의 지문 — 조립이 끝난 요약 그리기 호출(웨이퍼 맵은 시각·삼각함수라 뺀다: 프레임의 둘째
// `save` 부터가 요약이다). 숫자는 소수 둘째 자리로 줄여 엔진(node·bun)의 끝자리 차이를 덮는다.
{
  const end = plainFrames[2];
  const saves = end.map((call, i) => (call[0] === "save" ? i : -1)).filter((i) => i >= 0);
  const coarse = (v) => (typeof v === "number" ? Math.round(v * 100) / 100 : Array.isArray(v) ? v.map(coarse) : v);
  const summaryCalls = end.slice(saves[1]).map((call) => call.map(coarse));
  results.base_fingerprint = crypto.createHash("sha256").update(JSON.stringify(summaryCalls)).digest("hex");
  results.base_calls = summaryCalls.length;
}

// 2) 셋을 켰다 다 끄면 같은 시각의 기본 그림과 같다.
const toggled = await open(payload);
toggled.tick(toggled.now() + 3000);
toggled.send(view(true, true, true));
toggled.tick(toggled.now() + 2000);
const allOn = toggled.frame();
results.on_texts = allOn.filter((c) => c[0] === "fillText").map((c) => c[1]).filter((t) => /^[+-]\d/.test(String(t)));
// 3) 움직이는 중에 다시 누르면 지금 값에서 이어 간다 — 점 위 값 글자가 한 프레임에 크게 튀지 않는다.
toggled.send(view(false, true, true));
const series = [];
for (let k = 0; k < 50; k++) {
  if (k === 22) toggled.send(view(true, true, true));
  const texts = toggled.frame().filter((c) => c[0] === "fillText" && String(c[c.length - 1]).includes('700 14px "N"')).map((c) => Number(c[1]));
  series.push(texts);
}
results.label_series = series;
toggled.send(view(false, false, false));
toggled.tick(toggled.now() + 2500);
const offFrame = toggled.frame();
const offAt = toggled.now();
const base = await open(payload);
base.tick(offAt - 16);
results.back_to_base = base.now() + 16 === offAt && same(base.frame(), offFrame);

// 3-1) 켜 둔 채 「준비 중」이던 GAP 에 값이 닿으면(`restart`) 꺼진 자리에서 다시 움직여 들어온다 — 유령 점의
// 투명도가 0 근처에서 다시 1 로 오른다.
{
  const ghost = await open(payload);
  ghost.tick(ghost.now() + 3000);
  ghost.send(view(false, false, true));
  ghost.tick(ghost.now() + 2000);
  const alphaOf = (frame) =>
    Math.max(0, ...frame.filter((c) => c[0] === "stroke" && String(c[c.length - 1]).split("|")[2] === PALETTE.muted).map((c) => Number(String(c[c.length - 1]).split("|")[0])));
  const settled = alphaOf(ghost.frame());
  ghost.send({ ...view(false, false, true), restart: ["comparison"] });
  const first = alphaOf(ghost.frame());
  ghost.tick(ghost.now() + 2000);
  results.restart_alpha = [settled, first, alphaOf(ghost.frame())];
}

// 4) 움직임을 줄였으면 프레임 루프가 없고, 메시지를 받을 때만 한 번 그린다.
const reduced = await open(payload, { reduce: true });
results.reduce_queued = reduced.queued();
const before = reduced.log.length;
reduced.tick(reduced.now() + 1000);
results.reduce_idle_calls = reduced.log.length - before;
reduced.send(view(true, false, false));
results.reduce_drawn_on_view = reduced.log.length - before > 0;
results.reduce_queued_after_view = reduced.queued();

// 5) 좁은 창에서도 오류 없이 그린다.
for (const [w, h] of [[390, 844], [768, 1024], [1100, 800]]) {
  const narrow = await open(payload, { width: w, height: h });
  narrow.send(view(true, true, true));
  narrow.tick(narrow.now() + 2000);
  results[`narrow_${w}`] = narrow.frame().length;
}

// 6) 좁고 낮은 창의 B/N 확보율 판 — 기준선 이름표(110%·100%)가 막대 위 확보율 글자·공정 이름·상태·「최저」와 겹치지
// 않고 공정 이름 띠(판 아래 50px)에 내려가지 않으며, 「최저」 는 판 위(범례 띠)로 올라가지 않는다. 확보율이 낮으면(합성
// 데모 2% 안팎) 막대가 바닥에 붙어 확보율 글자와 두 기준선이 판 아래쪽 한 줄에 몰린다(360x640·320x568 E2E). 글자 상자는
// 하네스의 가짜 글자 폭(글자 수 × 크기 × 0.56)으로 잰다 — 장면도 같은 폭으로 자리를 고른다.
{
  const { summaryGrid } = loadScene();
  const lowRates = [2.2, 2.2, 1.7, 1.6, 1.5, 1.6];
  const low = { ...plain, bn: plain.bn.map((b, i) => (b ? { ...b, rate: lowRates[i] } : b)) };
  const textBox = (call) => {
    const state = String(call[call.length - 1]).split("|");
    const px = parseFloat((/(\d+(?:\.\d+)?)px/.exec(state[3]) || [0, "10"])[1]);
    const text = String(call[1]);
    const w = text.length * px * 0.56;
    const x0 = state[4] === "left" ? call[2] : state[4] === "right" ? call[2] - w : call[2] - w / 2;
    return { text, font: state[3], alpha: Number(state[0]), x: x0, y: call[3] - px * 0.85, w, h: px };
  };
  const hit = (a, b) => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
  for (const [name, summary] of [["plain", plain], ["low", low]]) {
    for (const [w, h] of [[390, 844], [360, 640], [320, 568]]) {
      const crowded = await open(summary, { width: w, height: h });
      crowded.tick(crowded.now() + 3000);
      const frame = crowded.frame();
      const bars = summaryGrid(w, h).rows[1];
      const namesTop = bars.y + bars.h - 50;
      const texts = frame
        .filter((c) => c[0] === "fillText")
        .map(textBox)
        .filter((t) => t.alpha > 0.01 && t.y + t.h > bars.y - bars.head - 2 && t.y < bars.y + bars.h + 2);
      const labels = texts.filter((t) => /(^|\s)10px\s/.test(t.font) && /^\d+%$/.test(t.text));
      results[`crowded_${name}_${w}`] = {
        labels: labels.map((t) => t.text),
        overlaps: labels.flatMap((t) => texts.filter((o) => o !== t && hit(t, o)).map((o) => `${t.text}×${o.text}`)),
        intoNames: labels.filter((t) => t.y + t.h > namesTop + 0.5).map((t) => t.text),
        lowestAbove: texts.some((t) => t.text === "최저" && t.y < bars.y),
      };
    }
  }
}
// 7) 과거 구간 달(`past` — 제품별 Wafer 가 없어 도넛이 빈다)은 도넛 자리에 「과거 구간」 을 적는다. 과거가 아닌 달은 도넛이
// 비어도 적지 않는다(2026-11-02 사용자 요청(검수표) home-02 — 기본 창 첫 달이 과거 구간 달이다).
{
  const emptyFirst = plain.mix.map((month, i) => (i === 0 ? [] : month));
  const pastTexts = async (summary) => {
    const scene = await open(summary);
    scene.tick(scene.now() + 3000);
    return scene.frame().filter((c) => c[0] === "fillText" && String(c[1]) === "과거 구간").length;
  };
  results.past_texts = await pastTexts({ ...plain, mix: emptyFirst, past: plain.months.map((_, i) => i === 0) });
  results.past_plain_texts = await pastTexts({ ...plain, mix: emptyFirst });
}
console.log(JSON.stringify(results));
