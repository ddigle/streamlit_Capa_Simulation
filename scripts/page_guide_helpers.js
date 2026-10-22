// Purpose: 따라하기 가이드 촬영기가 페이지에 심는 도우미(window.__g) — 표적 찾기 · 격자 칸 자리 · 가림.
// scripts/page_guide_capture.py 가 읽어 evaluate 마다 앞에 붙인다. 시안 guide/capture/lib.mjs · capture.mjs 에서 옮겼다.
(()=>{ if (window.__g) return;
const g = {};
const TID = (e)=> (e && e.getAttribute && e.getAttribute('data-testid')) || '';
g.norm = (s)=> (s||'').replace(/\s+/g,' ').trim();
g.txt = (e)=>{ if(!e) return ''; let s=e.innerText||e.textContent||''; e.querySelectorAll('[data-testid="stIconMaterial"]').forEach(i=>{ const t=(i.innerText||i.textContent||''); if(t) s=s.replace(t,''); }); return g.norm(s); };
g.R = (e)=>{ if(!e) return null; const r=e.getBoundingClientRect(); return [r.x,r.y,r.width,r.height].map(v=>Math.round(v*10)/10); };
g.vis = (e)=>{ if(!e) return false; const r=e.getBoundingClientRect(); if(!(r.width>0&&r.height>0)) return false; const cs=getComputedStyle(e); return cs.visibility!=='hidden' && cs.display!=='none'; };
g.scope = (s)=> !s ? document : (typeof s==='string' ? document.querySelector(s) : s);
g.main = ()=> document.querySelector('[data-testid="stMain"]');
g.key = (k)=> document.querySelector('.st-key-'+CSS.escape(k));
g.btns = (text, scope)=>{ const sc=g.scope(scope); if(!sc) return []; return [...sc.querySelectorAll('button,[role="button"],a,[role="tab"],label')].filter(b=>g.vis(b) && g.txt(b)===text); };
g.btn = (text, scope)=> g.btns(text, scope)[0] || null;
g.texts = (t, scope, exact)=>{ const sc=g.scope(scope); if(!sc) return []; const all=[...sc.querySelectorAll('*')].filter(e=>{ const s=g.norm(e.textContent); return exact ? s===t : s.includes(t); });
  return all.filter(e=> !all.some(o=>o!==e && e.contains(o))).filter(g.vis); };
g.text = (t, scope, exact)=> g.texts(t, scope, exact)[0] || null;
g.tab = (t, scope)=>{ const sc=g.scope(scope)||document; const tabs=[...sc.querySelectorAll('[role="tab"]')].filter(g.vis); return tabs.find(e=>g.txt(e)===t) || tabs.find(e=>g.txt(e).endsWith(t)||g.txt(e).startsWith(t)) || null; };
g.up = (e, pred)=>{ while(e && !pred(e)) e=e.parentElement; return e; };
g.widget = (label, scope)=>{
  const sc=g.scope(scope)||document; const labs=[...sc.querySelectorAll('[data-testid="stWidgetLabel"]')].filter(l=>g.vis(l)&&g.txt(l)===label);
  if(!labs.length) return null; return g.up(labs[0], e=>/^st(TextInput|TextArea|NumberInput|Selectbox|MultiSelect|Checkbox|Toggle|Radio|DateInput|SelectSlider|Slider|ButtonGroup)$/.test(TID(e))) || labs[0].parentElement; };
g.idle = ()=>{ const a=document.querySelector('[data-testid="stApp"]'); return a ? a.getAttribute('data-test-script-state') : 'noapp'; };
g.dialog = ()=> [...document.querySelectorAll('[role="dialog"]')].filter(g.vis).pop() || null;
g.dialogFirst = (fn)=>{ const d=g.dialog(); return (d && fn(d)) || fn(null); };
g.box = (e)=> g.up(e && e.parentElement, x=> TID(x)==='stVerticalBlock' && parseFloat(getComputedStyle(x).borderTopWidth)>0);
g.headBox = (t, scope)=>{ const sc=g.scope(scope)||document; const h=[...sc.querySelectorAll('h1,h2,h3,h4,h5,h6')].filter(e=>g.vis(e)&&g.txt(e).includes(t))[0]; return h? g.box(h): null; };
g.headerBand = ()=>{ const h=document.querySelector('[data-testid="stHeader"]'); if(!h) return null; const hr=h.getBoundingClientRect(); const rs=['::before','::after'].map(p=>{const c=getComputedStyle(h,p); if(!c.content||c.content==='none') return null; const l=parseFloat(c.left), t=parseFloat(c.top), w=parseFloat(c.width), ht=parseFloat(c.height); return [hr.x+l, hr.y+t, w+parseFloat(c.paddingLeft||0)+parseFloat(c.borderLeftWidth||0), ht];}).filter(Boolean); if(!rs.length) return null; const x=Math.min(...rs.map(r=>r[0])), y=Math.min(...rs.map(r=>r[1])), r2=Math.max(...rs.map(r=>r[0]+r[2])), b=Math.max(...rs.map(r=>r[1]+r[3])); return [x,y,r2-x,b-y]; };
g.inView = (e)=>{ const r=Array.isArray(e)? {top:e[1], bottom:e[1]+e[3], left:e[0], right:e[0]+e[2]} : e.getBoundingClientRect(); return r.top>=0 && r.bottom<=innerHeight && r.left>=0 && r.right<=innerWidth; };
g.asRect = (v)=>{ if(!v) return null; const r=Array.isArray(v)? v : g.R(v); return r && r[2]>0 && r[3]>0 ? r.map(x=>Math.round(x*10)/10) : null; };
g.union = (vs)=>{ const rs=vs.filter(Boolean).map(g.asRect).filter(Boolean); if(!rs.length) return null; const x=Math.min(...rs.map(r=>r[0])), y=Math.min(...rs.map(r=>r[1])), r2=Math.max(...rs.map(r=>r[0]+r[2])), b=Math.max(...rs.map(r=>r[1]+r[3])); return [x,y,r2-x,b-y].map(v=>Math.round(v*10)/10); };
// 사각형(요소 · 배열)을 다른 요소의 가로 범위로 자른다 — 보이는 창보다 긴 가로 굴림 캔버스
g.clip = (v, region)=>{ if(!v||!region) return v||null; const a=Array.isArray(v)?v:g.R(v); const b=g.R(region); const x=Math.max(a[0],b[0]), r=Math.min(a[0]+a[2],b[0]+b[2]); return [x,a[1],r-x,a[3]]; };
// 누를 요소: 접기 상자는 머리(summary)를
g.clickable = (v)=>{ if(!v || Array.isArray(v)) return v||null; if(TID(v)==='stExpander' || v.tagName==='DETAILS') return v.querySelector('summary')||v; return v; };
g.prepClick = (v)=>{ const e=g.clickable(v); if(!e) return null; if(Array.isArray(e)) return e; if(!g.inView(e)) e.scrollIntoView({block:'center',inline:'nearest'}); return g.R(e); };
g.rectNow = (v)=>{ const e=g.clickable(v); if(!e) return null; return Array.isArray(e)? e : g.R(e); };
g.hit = (v)=>{ if(!v) return 'none'; if(!g.vis(v)) return 'none'; const r=v.getBoundingClientRect(); const h=document.elementFromPoint(r.x+r.width/2, r.y+r.height/2); return h && v.contains(h) ? 'ok' : 'blocked'; };
g.mainTop = ()=>{ const m=g.main(); if(m) m.scrollTop=0; return 1; };
g.blur = ()=>{ const a=document.activeElement; if(a && a!==document.body) a.blur(); return 1; };
g.scrollTo = (v, o)=>{ if(!v||Array.isArray(v)) return false; v.scrollIntoView({block:o.block}); if(o.offset){ const m=g.main(); if(m) m.scrollBy(0,o.offset); } return true; };
// 사이드바 메뉴
g.navs = ()=> [...document.querySelectorAll('[data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"]')];
g.nav = (t)=> g.navs().find(a=>g.vis(a)&&g.txt(a)===t) || null;
g.navIntoView = (t)=>{ const e=g.nav(t); if(e && !g.inView(e)) e.scrollIntoView({block:'center'}); return 1; };
g.openGroupOf = (t)=>{ const a=g.navs().find(a=>g.txt(a)===t); const ex=a && g.up(a, x=>TID(x)==='stExpander'); if(!ex) return null; const d=ex.tagName==='DETAILS'? ex : ex.querySelector('details'); if(d && d.open) return null; const sm=ex.querySelector('summary'); if(!sm) return null; sm.scrollIntoView({block:'center'}); return g.R(sm); };
// 글 표적은 그 글을 가진 가장 작은 요소를 글 감싸개(markdown · caption · alert)까지 올린다
g.textBox = (t)=>{ const e=g.dialogFirst(s=>g.text(t, s)); if(!e) return null; return g.up(e, x=>/stMarkdownContainer|stCaptionContainer|stAlert/.test(TID(x))) || e; };
// 팝업을 여는 단추 — 칸 안의 마지막 보이는 단추(이름 줄의 작은 단추가 앞에 올 수 있다)
g.popupButton = (v)=>{ if(!v||Array.isArray(v)) return null; if(v.tagName==='BUTTON') return v; return [...v.querySelectorAll('button')].filter(g.vis).pop() || null; };
g.sectionButton = (t)=>{ const d=g.dialog(); if(!d) return null; return [...d.querySelectorAll('[data-testid="stButtonGroup"] button')].find(b=>g.vis(b)&&g.txt(b)===t) || null; };
g.isActive = (b)=> !!b && (b.getAttribute('aria-checked')==='true' || b.getAttribute('aria-pressed')==='true' || b.getAttribute('aria-selected')==='true' || /Active/.test(b.getAttribute('kind')||'') || /Active/.test(TID(b)));
g.sectionState = (t)=>{ const b=g.sectionButton(t); return b ? (g.isActive(b) ? 'active' : 'idle') : null; };
// 입력칸
g.fillWidget = (label)=> g.dialogFirst(s=>g.widget(label, s));
g.widgetKind = (label)=>{ const w=g.fillWidget(label); return w ? TID(w) : null; };
g.fillInput = (label)=>{ const w=g.fillWidget(label); return w && (w.querySelector('textarea')||w.querySelector('input')); };
g.optionFor = (v)=>{ const o=[...document.querySelectorAll('[role="option"]')].filter(g.vis).find(o=>g.txt(o).includes(v)); return o ? g.R(o) : null; };
g.dialogQuiet = ()=>{ const d=g.dialog(); return d ? [...d.querySelectorAll('h1,h2,h3,[data-testid="stCaptionContainer"],p')].filter(g.vis)[0] || null : null; };
// 가림
g.hideAll = (vs, needles)=>{ let n=0; vs.forEach(v=>{ if(v && v.style){ v.style.visibility='hidden'; n++; } }); (needles||[]).forEach(t=>{ g.texts(t).forEach(e=>{ e.style.visibility='hidden'; n++; }); }); return n; };
g.shows = (needles)=> needles.filter(t=> (document.body.innerText||'').includes(t)).length;
// 캔버스 격자(glide-data-grid) — 열 폭 · 행 높이 · 고정 열을 React fiber 의 DataGrid 속성에서 읽는다
g.gridGeom = (el)=>{ if(!el) return null; const cv=el.querySelector('canvas'); if(!cv) return null; const fk=Object.keys(cv).find(k=>k.startsWith('__reactFiber$')); let f=fk&&cv[fk]; let p=null;
  while(f){ const q=f.memoizedProps; if(q && Array.isArray(q.columns) && q.headerHeight!==undefined && q.cellXOffset!==undefined){ p=q; break; } f=f.return; }
  if(!p) return null; const cr=cv.getBoundingClientRect(); const rh=typeof p.rowHeight==='number'?p.rowHeight:p.rowHeight(0);
  return {canvas:[cr.x,cr.y,cr.width,cr.height], rowHeight:rh, headerHeight:p.headerHeight, groupHeaderHeight:p.groupHeaderHeight, enableGroups:p.enableGroups, freezeColumns:p.freezeColumns||0, rows:p.rows, cols:p.columns.map(c=>({t:c.title, w:c.width}))}; };
g.gridHead = (G)=> G.headerHeight + (G.enableGroups ? G.groupHeaderHeight : 0);
// 칸 사각형 — 고정 열은 굴림과 무관, 나머지는 `.dvn-scroller` 의 scrollLeft · scrollTop 만큼 밀린다
g.cellRect = (el, col, row)=>{ const G=g.gridGeom(el); if(!G || col<0 || col>=G.cols.length) return null; const sc=el.querySelector('.dvn-scroller'); const sl=sc?sc.scrollLeft:0, st=sc?sc.scrollTop:0; const ws=G.cols.map(c=>c.w); const sum=(a,b)=>ws.slice(a,b).reduce((s,w)=>s+w,0); const head=g.gridHead(G); const fz=G.freezeColumns;
  const x = col<fz ? G.canvas[0]+sum(0,col) : G.canvas[0]+sum(0,col)-sl; const y = row<0 ? G.canvas[1] : G.canvas[1]+head+row*G.rowHeight-st;
  return [x, y, ws[col], row<0 ? head : G.rowHeight].map(v=>Math.round(v*10)/10); };
g.revealCell = (el, col, row)=>{ const G=g.gridGeom(el); const sc=el && el.querySelector('.dvn-scroller'); if(!G||!sc) return false; const ws=G.cols.map(c=>c.w); const sum=(a,b)=>ws.slice(a,b).reduce((s,w)=>s+w,0); const head=g.gridHead(G); const fz=G.freezeColumns; let moved=false;
  const visH=sc.clientHeight-head, top=row*G.rowHeight;
  if(row>=0 && (top<sc.scrollTop || top+G.rowHeight>sc.scrollTop+visH)){ sc.scrollTop=Math.max(0, top-Math.max(0,(visH-G.rowHeight)/2)); moved=true; }
  if(col>=fz){ const visW=sc.clientWidth-sum(0,fz), left=sum(fz,col); if(left<sc.scrollLeft || left+ws[col]>sc.scrollLeft+visW){ sc.scrollLeft=Math.max(0, left-Math.max(0,(visW-ws[col])/2)); moved=true; } }
  return moved; };
g.colIndex = (el, title)=>{ const G=g.gridGeom(el); return G? G.cols.findIndex(c=>c.t===title) : -1; };
g.gridProps = (el)=>{ const cv=el&&el.querySelector('canvas'); if(!cv) return null; const fk=Object.keys(cv).find(k=>k.startsWith('__reactFiber$')); let f=fk&&cv[fk]; while(f){ const q=f.memoizedProps; if(q && Array.isArray(q.columns) && typeof q.getCellContent==='function') return q; f=f.return; } return null; };
g.cellContent = (el, col, row)=>{ const p=g.gridProps(el); return p ? p.getCellContent([col,row]) : null; };
g.cellText = (el, col, row)=>{ const c=g.cellContent(el, col, row); return c? String(c.displayData ?? c.data ?? '').trim() : null; };
g.cellData = (el, col, row)=>{ const c=g.cellContent(el, col, row); return c ? c.data : null; };
g.rowIndex = (el, colTitle, value)=>{ const G=g.gridGeom(el); if(!G) return -1; const c=G.cols.findIndex(x=>x.t===colTitle); if(c<0) return -1; for(let r=0;r<G.rows;r++){ if(g.cellText(el,c,r)===value) return r; } return -1; };
g.locateCell = (el, s)=>{ const G=g.gridGeom(el); if(!G) return null;
  const col = typeof s.column==='number' ? s.column : G.cols.findIndex(c=>c.t===String(s.column)); let row=-1;
  if(typeof s.row==='number') row=s.row;
  else if(s.rowColumn) row=g.rowIndex(el, s.rowColumn, String(s.row));
  else { for(let r=0;r<G.rows && row<0;r++){ for(let c=0;c<G.cols.length;c++){ if(g.cellText(el,c,r)===String(s.row)){ row=r; break; } } } }
  return col>=0 && col<G.cols.length && row>=0 && row<G.rows ? {col, row} : null; };
g.editRow = (el, row)=>{ const a=g.cellRect(el, 0, row); const G=g.gridGeom(el); if(!a||!G) return null; const w=G.cols.reduce((s,c)=>s+c.w,0); return [a[0], a[1], Math.min(w, G.canvas[2]), a[3]]; };
g.gridColumn = (el, title)=>{ const c=g.colIndex(el, title); if(c<0) return null; const h=g.cellRect(el,c,-1), b=g.cellRect(el,c,0); return h&&b? [h[0],h[1],h[2],b[1]+b[3]-h[1]] : null; };
// 화면 고유 표적(시안 capture.mjs 에서 옮김)
g.grid = ()=> [...document.querySelectorAll('[data-testid="stDataFrame"]')].filter(g.vis)[0] || null;
g.lastGrid = ()=> [...document.querySelectorAll('[data-testid="stMain"] [data-testid="stDataFrame"]')].filter(g.vis).pop() || null;
g.pageTitle = ()=> [...document.querySelectorAll('[data-testid="stMain"] h1')].filter(g.vis)[0] || null;
g.mainLink = (t)=> [...document.querySelectorAll('[data-testid="stMain"] a[data-testid="stPageLink-NavLink"]')].find(a=>g.vis(a)&&g.txt(a)===t) || null;
g.mainAlert = (t)=> [...document.querySelectorAll('[data-testid="stMain"] [data-testid="stAlert"]')].filter(e=>g.vis(e)&&g.txt(e).includes(t))[0] || null;
g.expander = (k)=>{ const e=g.key(k); if(!e) return null; return g.up(e, x=>TID(x)==='stExpander') || e.querySelector('[data-testid="stExpander"]') || e; };
g.keyButton = (k)=>{ const e=g.key(k); return e ? (e.tagName==='BUTTON' ? e : e.querySelector('button')) : null; };
g.formOf = (label)=> g.up(g.fillWidget(label), e=>TID(e)==='stForm');
g.sidebarScen = ()=> g.key('condition_field_scenario') || document.querySelector('[class*="st-key-condition_field_scenario"]');
g.sidebarBadge = ()=>{ const f=g.key('condition_name_scenario'); if(!f) return null; return [...f.querySelectorAll('span,div,p')].filter(e=>g.vis(e)&&/^(미저장 변경|저장된 리비전|공식 v\d+)$/.test(g.norm(e.textContent))).sort((a,b)=>a.getBoundingClientRect().width-b.getBoundingClientRect().width)[0]||null; };
g.sidebarPending = ()=>{ const t=g.text("적용 전 편집", document.querySelector('[data-testid="stSidebar"]')); if(!t) return null; return g.up(t, e=>/stMarkdownContainer|stCaptionContainer|stAlert/.test(TID(e)))||t; };
g.lobChart = ()=> g.union([g.key('production_lob_labels'), g.clip(g.key('production_lob_months'), g.key('production_lob_month_region'))]);
g.lobLabel = (t)=>{ const L=g.key('production_lob_labels'); return L ? g.text(t, L) : null; };
// LOB 라벨 그림의 가로 구분선(shapes)으로 행 경계를 찾아, 그 라벨이 든 행 전체(라벨 칸 + 보이는 달 칸)
g.lobRow = (label)=>{ const L=g.key('production_lob_labels'), M=g.key('production_lob_month_region'); if(!L||!M) return null; const t=g.text(label, L); if(!t) return null; const tr=t.getBoundingClientRect(); const cy=tr.y+tr.height/2; const lr=L.getBoundingClientRect(), mr=M.getBoundingClientRect();
  const ys=[...L.querySelectorAll('.shapelayer path')].map(p=>p.getBoundingClientRect()).filter(r=>r.height<3&&r.width>lr.width*0.5).map(r=>r.y+r.height/2).sort((a,b)=>a-b);
  const svg=L.querySelector('svg.main-svg'); const sr=svg?svg.getBoundingClientRect():lr; const all=[sr.y, ...ys, sr.y+sr.height];
  let top=sr.y, bot=sr.y+sr.height; for(const y of all){ if(y<=cy && y>top) top=y; if(y>=cy && y<bot) bot=y; }
  return [lr.x, top, mr.x+mr.width-lr.x, bot-top]; };
// 생산계획 LOB 의 「B/N 공정」 막대(trace 이름) — 보이는 달 칸 안 막대들의 합
g.lobBnBars = ()=>{ const C=g.key('production_lob_months'), M=g.key('production_lob_month_region'); if(!C||!M) return null; const mr=M.getBoundingClientRect();
  const tr=[...C.querySelectorAll('.barlayer .trace')].filter(x=>{const d=x.__data__; const t=d&&d[0]&&d[0].trace; return t && t.name==='B/N 공정'});
  const rs=tr.flatMap(x=>[...x.querySelectorAll('.point path')]).map(p=>p.getBoundingClientRect()).filter(r=>r.width>1&&r.height>1&&r.right>mr.left&&r.left<mr.right);
  if(!rs.length) return null; const x=Math.max(mr.left, Math.min(...rs.map(r=>r.left))), y=Math.min(...rs.map(r=>r.top)), r2=Math.min(mr.right, Math.max(...rs.map(r=>r.right))), b=Math.max(...rs.map(r=>r.bottom)); return [x,y,r2-x,b-y]; };
g.keyProcessGrid = ()=> g.union([g.key('key_process_title_row'), g.key('key_process_heatmap_labels'), g.clip(g.key('key_process_heatmap_months'), g.key('production_lob_month_region'))]);
g.detailBn = ()=> g.union([g.key('bottleneck_title_row'), g.key('bottleneck_detail_labels'), g.clip(g.key('bottleneck_detail_months'), g.key('production_lob_month_region'))]);
// 상세 B/N 그림에서 누를 칸 — 보이는 칸 가운데 빨강(부족)을 먼저, 위 · 왼쪽 차례
g.bnCell = ()=>{ const region=g.key('production_lob_month_region'), months=g.key('bottleneck_detail_months'); if(!region||!months) return null; const reg=region.getBoundingClientRect(); const red=(e)=>{const m=(getComputedStyle(e).fill||'').match(/\d+/g); return m&&+m[0]>=180&&+m[1]<120&&+m[2]<120};
  const ps=[...months.querySelectorAll('.barlayer .point path')].map(p=>({r:p.getBoundingClientRect(), red:red(p)})).filter(({r})=>r.width>2&&r.height>2&&r.left>=reg.left&&r.right<=reg.right&&r.top>=0&&r.bottom<=innerHeight);
  ps.sort((a,b)=>(b.red-a.red)||a.r.top-b.r.top||a.r.left-b.r.left); const r=ps[0]&&ps[0].r; return r?[r.x,r.y,r.width,r.height]:null; };
g.procHead = ()=>{ const t=g.text("공식 · Core Data")||g.text("Core Data"); return t? g.up(t, x=>TID(x)==='stHorizontalBlock') || t.parentElement : null; };
g.procMonthCanvas = ()=> g.union([g.key('process_detail_label_canvas'), g.clip(g.key('process_detail_canvas_canvas'), g.key('process_detail_month_region'))]);
g.pfTiles = ()=>{ const d=g.dialog(); if(!d) return null; const ts=[...d.querySelectorAll('[class*="st-key-home_bn_tile_"]')].filter(g.vis); if(!ts.length) return null; let a=ts[0].parentElement; while(a && !ts.every(t=>a.contains(t))) a=a.parentElement; return a; };
window.__g = g; })()
