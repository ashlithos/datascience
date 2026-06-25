"""
build_web.py — generate web/index.html, a self-contained interactive preview of the
FlowDash DS-agent demo.

It reproduces the Jetski chat + canvas layout (Material 3 dark, blue/cyan; tokens
from jetski-design/) with NO build step: one static HTML file, charts embedded as
base64, the demo flow scripted in vanilla JS. Maya clicks a question → the agent
plays a reasoning trace → answers → mounts a card/chart in the canvas pane.

Run:  python web/build_web.py   (after building charts via tools/viz_tool.py)
Output: web/index.html  (open directly, or deploy the web/ folder as a static site)
"""
import base64
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
REPORTS = os.path.join(ROOT, "reports")

from key_driver import scan   # noqa: E402


def b64(png):
    p = os.path.join(REPORTS, png)
    return "data:image/png;base64," + base64.b64encode(open(p, "rb").read()).decode()


CHARTS = {k: b64(v) for k, v in {
    "wau": "wau_trend.png", "driver": "driver_cells.png",
    "feature": "sql_export_trend.png", "errors": "error_rate.png"}.items()}

R = scan()
TOP = R["top_driver"]
O = R["overall"]

# --- canvas artifact builders (return HTML strings) -------------------------
def canvas_cleaning():
    return """
    <span class="kicker">Data cleaning · approval required</span>
    <h3 class="ctitle">3 data-quality issues found</h3>
    <p class="csub">I can detect these on my own (read-only). Nothing is written until you approve — your call, per issue.</p>
    <div class="approve">
      <div class="aicon">&#10697;</div>
      <div><div class="ah">35 duplicate session rows</div>
      <div class="ad">Same <code>session_id</code> logged twice. Fix: keep first, drop the rest.</div>
      <div class="btnrow"><button class="btn btn-primary">Approve de-dupe</button><button class="btn">Show all 35</button><button class="btn btn-ghost">Skip</button></div></div>
    </div>
    <div class="approve">
      <div class="aicon">&minus;</div>
      <div><div class="ah">28 negative durations</div>
      <div class="ad">Clock bug, <code>duration_sec &lt; 0</code>. Fix: exclude from aggregates (keep source rows).</div>
      <div class="btnrow"><button class="btn btn-primary">Approve exclude</button><button class="btn btn-ghost">Skip</button></div></div>
    </div>
    <div class="approve">
      <div class="aicon">Aa</div>
      <div><div class="ah">Inconsistent region spelling</div>
      <div class="ad">EMEA appears as <code>EMEA</code> / <code>emea</code> / <code>E.M.E.A</code> / <code>" EMEA "</code>. Fix: normalise to <code>EMEA</code>.</div>
      <div class="btnrow"><button class="btn btn-primary">Approve normalise</button><button class="btn btn-ghost">Skip</button></div></div>
    </div>
    <p class="foot">Shallow autonomy: detection is automatic; every <b>write</b> waits for you.</p>"""


def canvas_driver():
    ev = ""
    for e in R["evidence"]:
        cls = ' class="cause"' if e["is_cause"] else ""
        tag = ' <span class="pill pill-bad">cause</span>' if e["is_cause"] else ""
        ev += (f'<tr{cls}><td>{e["cell"]}{tag}</td><td class="num">{e["first"]}</td>'
               f'<td class="num">{e["last"]}</td><td class="num">{e["change_pct"]:+.0f}%</td></tr>')
    singles = "".join(f'<tr><td>{s["dim"]} = {s["value"]}</td><td class="num">{s["change_pct"]:+.0f}%</td></tr>'
                      for s in R["singles"][:5])
    return f"""
    <span class="kicker">Key-driver analysis</span>
    <h3 class="ctitle">Why is weekly active down {abs(O['change_pct'])}%?</h3>
    <p class="csub">wk{O['first_week']} &rarr; wk{O['last_week']}: {O['wau_first']} &rarr; {O['wau_last']} active users.</p>
    <div class="metrics">
      <div><div class="mval bad">{TOP['change_pct']}%</div><div class="mlbl">{TOP['value']}</div></div>
      <div><div class="mval">{TOP['share_of_base']}%</div><div class="mlbl">of the user base</div></div>
      <div><div class="mval">{R['combos_tried']}</div><div class="mlbl">combinations scanned</div></div>
    </div>
    <p>The decline is <b>not</b> platform-wide or new-user-wide. It concentrates almost entirely in one cell: <b>{TOP['value']}</b>. Every sibling segment is flat.</p>
    <div class="conf"><div class="conf-track"><div class="conf-fill" style="width:{R['confidence']}%"></div></div>
      <div class="conf-lbl">Confidence in this driver: <b>{R['confidence']}%</b> &middot; heuristic: drop severity, base share, sibling flatness</div></div>
    <img class="chart" src="{CHARTS['driver']}" alt="driver breakdown">
    <details class="evidence"><summary>&#9656; Show the evidence (what I actually checked)</summary>
      <p class="foot">Single-dimension cuts only show a diffuse, misleading dip — none isolate the cause:</p>
      <table class="tbl"><thead><tr><th>single-dimension cut</th><th class="num">wk1&rarr;wk8</th></tr></thead><tbody>{singles}</tbody></table>
      <p class="foot" style="margin-top:12px">Crossing platform &times; user_type localises it:</p>
      <table class="tbl"><thead><tr><th>cell</th><th class="num">wk1</th><th class="num">wk8</th><th class="num">&Delta;</th></tr></thead><tbody>{ev}</tbody></table>
    </details>
    <p class="foot">This is a probabilistic finding, not a fact. Open the evidence before acting.</p>"""


def canvas_story():
    return f"""
    <span class="kicker">Storytelling · B / C comparison</span>
    <h3 class="ctitle">Weekly summary — two structures, same facts</h3>
    <div class="tabs"><button class="tab tab-on" data-tab="C">Version C · fixed</button><button class="tab" data-tab="B">Version B · agent-decided</button></div>
    <div class="tabpane" data-pane="C">
      <p class="csub">Predictable template: Overview &rarr; Findings &rarr; Evidence &rarr; Recommendations.</p>
      <p><b>Overview.</b> Weekly active down 18% over 8 weeks. Not broad-based — one segment.</p>
      <p><b>Key findings.</b> WAU &minus;18%; cause is <b>android &times; new</b> &minus;61% (92% conf.); <code>sql_export</code> up ~3&times;; EMEA wk-6 errors ~7%.</p>
      <img class="chart" src="{CHARTS['wau']}" alt="wau trend">
      <p><b>Recommendation.</b> Investigate Android new-user onboarding — the entire decline lives there.</p>
    </div>
    <div class="tabpane" data-pane="B" hidden>
      <p class="csub">Agent-decided structure: it chose to <b>open on the good news</b>.</p>
      <p class="m3head">The thing nobody's looking at is going right.</p>
      <p>Everyone's about to panic about the 18% WAU drop. First: <b><code>sql_export</code> has tripled</b> (5%&rarr;15% of sessions), climbing every week with zero marketing. That's where FlowDash is getting sticky.</p>
      <img class="chart" src="{CHARTS['feature']}" alt="sql_export trend">
      <p>Now the drop — it's precise: new users on Android, &minus;61%. Not all of Android, not all new users. The intersection. ~92% sure.</p>
    </div>
    <p class="foot">C is predictable & audit-friendly; B noticed the surprise and restructured around it. Different surfaces want different ones.</p>"""


def canvas_alert():
    return f"""
    <span class="kicker alert-k">Threshold breach · autonomous alert</span>
    <h3 class="ctitle">EMEA error rate broke 5% in week 6</h3>
    <p class="csub">I noticed this without being asked. Want me to dig in?</p>
    <div class="metrics">
      <div><div class="mval bad">7.17%</div><div class="mlbl">EMEA wk-6 error rate (vs ~1.3% normal)</div></div>
      <div><div class="mval bad">56.5%</div><div class="mlbl">in the 2h after deploy</div></div>
    </div>
    <p>Spike concentrates in the <b>~2 hours after deploy v2026.06.03</b> and is confined to <b>EMEA</b>. Other regions stayed ~1–2%.</p>
    <img class="chart" src="{CHARTS['errors']}" alt="error rate">
    <div class="btnrow"><button class="btn btn-primary">Expand investigation</button><button class="btn btn-ghost">Snooze · adjust threshold</button></div>
    <p class="foot">Was this worth interrupting you for? The threshold is the etiquette of autonomy.</p>"""


STEPS = [
    {"chip": "Is this data clean enough to trust?",
     "user": "Is this data clean enough to trust?",
     "skill": "data-cleaning",
     "calls": ['sql_tool · SELECT session_id, COUNT(*) … HAVING c&gt;1', 'sql_tool · COUNT(*) WHERE duration_sec&lt;0', 'sql_tool · SELECT DISTINCT region'],
     "answer": "Short answer: not yet — but the issues are small and fixable. I scanned it and found <b>three</b> data-quality problems: 35 duplicate session rows, 28 negative durations, and EMEA spelled four different ways. I've laid them out on the right with a proposed fix for each. I won't change anything until you approve — your call, per issue.",
     "canvas": canvas_cleaning()},
    {"chip": "Why is weekly active down?",
     "user": "Why is weekly active down?",
     "skill": "key-driver-analysis",
     "calls": ['key_driver · scanning 55 dimension combinations', 'viz_tool · driver', 'components · key-driver'],
     "answer": f"Weekly active is down 18%, but here's the thing — it's <b>not</b> everyone leaving. I crossed every dimension (55 combinations) and the entire decline sits in <b>one cell: new users on Android, down 61%</b>. Every other segment is flat. If you'd only looked at \"Android\" (&minus;41%) or \"new users\" (&minus;35%) alone you'd have chased the wrong fix — it's the <i>intersection</i> that broke. I'm about {R['confidence']}% sure. Full evidence trail is on the right.",
     "canvas": canvas_driver()},
    {"chip": "Write me the weekly summary.",
     "user": "Write me the weekly summary.",
     "skill": "storytelling",
     "calls": ['key_driver · gather facts', 'viz_tool · wau feature', 'write story_C.md + story_B.md'],
     "answer": "Done — two versions on the right. <b>C</b> is the fixed template (predictable, good for a recurring digest). <b>B</b> I structured myself, and I chose to <b>lead with the good news</b>: <code>sql_export</code> has quietly tripled, which a template would've buried under the scary WAU number. Toggle between them — that contrast is the point.",
     "canvas": canvas_story()},
    {"chip": "Assume a week has passed.",
     "user": "Assume a week has passed.",
     "skill": "alert (autonomous)",
     "calls": ['monitor · error_rate by region', 'threshold breach: EMEA &gt; 5%', 'components · alert'],
     "answer": "⚠️ Before you do anything else — while you were away I caught something. <b>EMEA's error rate broke 5% in week 6</b> (hit ~7%), and it's concentrated in the two hours right after deploy <code>v2026.06.03</code>. Looks contained to that release, but I wanted to flag it rather than let it sit a week. Details on the right — want me to expand?",
     "canvas": canvas_alert()},
]

CSS = """
:root{
 --primary:#a8c7fa;--on-primary:#062e6f;--primary-container:#0842a0;--on-primary-container:#d3e3fd;
 --secondary:#85d2e3;--secondary-container:#004e5a;--on-secondary-container:#adebff;
 --tertiary:#dbc66e;--tertiary-container:#544600;--on-tertiary-container:#f9e287;
 --error:#ffb4ab;--error-container:#93000a;--on-error-container:#ffdad6;--good:#8ed8a9;--good-container:#1d4a2f;
 --bg:#111418;--on-surface:#e2e2e9;--on-surface-variant:#c4c6d0;--sc-lowest:#0c0e13;--sc-low:#191c20;
 --sc:#1d2024;--sc-high:#282a2f;--sc-highest:#33353a;--outline:#8e9099;--outline-variant:#44474e;
 --erosion:#ff8a65;--r-sm:8px;--r-md:12px;
 --font:Roboto,"Google Sans Flex",ui-sans-serif,system-ui,sans-serif;
 --mono:"Roboto Mono",ui-monospace,Menlo,monospace;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--on-surface);font-family:var(--font);-webkit-font-smoothing:antialiased}
.kicker{font-size:11px;font-weight:500;letter-spacing:.5px;text-transform:uppercase;color:var(--on-surface-variant);display:block;margin-bottom:8px}
.tnum,.num{font-variant-numeric:tabular-nums}
code{font-family:var(--mono);font-size:.92em;color:var(--on-surface-variant)}
@keyframes fade-up{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
@keyframes rise-in{from{opacity:0;transform:translateY(14px);filter:blur(4px)}to{opacity:1;transform:none;filter:none}}
.fade-up{animation:fade-up .32s cubic-bezier(.2,0,0,1) both}
@media(prefers-reduced-motion:reduce){.fade-up{animation:none}*{transition-duration:.01ms!important}}

/* shell */
header{display:flex;align-items:center;gap:12px;padding:14px 22px;border-bottom:1px solid var(--outline-variant);position:sticky;top:0;background:var(--bg);z-index:5}
header .logo{width:26px;height:26px;border-radius:7px;background:var(--primary);color:var(--on-primary);display:grid;place-items:center;font-weight:700;font-size:14px}
header .name{font-weight:500;font-size:15px}
header .demo{margin-left:auto;font-size:11px;color:var(--on-tertiary-container);background:var(--tertiary-container);padding:4px 9px;border-radius:var(--r-sm);font-weight:500}
.wrap{display:flex;height:calc(100vh - 55px)}
.chat{flex:1;min-width:0;display:flex;flex-direction:column}
.chat.has-canvas{max-width:46%;border-right:1px solid var(--outline-variant)}
.chat:not(.has-canvas) .thread{max-width:680px;margin:0 auto;width:100%}
.thread{flex:1;overflow-y:auto;padding:26px 24px 8px}
.canvas{flex:1;min-width:0;overflow-y:auto;padding:26px 26px 60px;display:none}
.canvas.on{display:block}
.canvas-empty{height:100%;display:grid;place-items:center;color:var(--outline);font-size:13px}

/* messages */
.turn{display:flex;gap:12px;margin-bottom:22px}
.turn.user{justify-content:flex-end}
.avatar{width:24px;height:24px;border-radius:50%;background:var(--primary);color:var(--on-primary);display:grid;place-items:center;font-size:12px;font-weight:700;flex:none}
.spacer{width:24px;flex:none}
.bubble{max-width:80%}
.turn.user .bubble{background:var(--sc-high);padding:10px 14px;border-radius:14px 14px 4px 14px;font-size:14.5px}
.agent .bubble{font-size:14.5px;line-height:1.55}
.agent .bubble p{margin:0 0 8px}
.m3head{font-size:18px;font-weight:500;margin:4px 0 8px}

/* reasoning trace */
.trace{border-left:2px solid var(--outline-variant);padding:2px 0 2px 12px;margin:2px 0 12px;font-size:12.5px;color:var(--on-surface-variant)}
.trace summary{cursor:pointer;list-style:none;color:var(--on-surface-variant);font-weight:500;display:flex;align-items:center;gap:7px}
.trace summary::-webkit-details-marker{display:none}
.trace .call{font-family:var(--mono);font-size:11.5px;margin-top:6px;color:var(--outline);display:flex;gap:7px;align-items:baseline}
.trace .call .ok{color:var(--good)}
.dot{width:7px;height:7px;border-radius:50%;border:2px solid var(--primary);border-top-color:transparent;display:inline-block;animation:spin .7s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}

/* composer */
.composer{padding:14px 24px 22px;border-top:1px solid var(--outline-variant)}
.chips{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:10px}
.chip{font-size:13px;font-weight:500;padding:8px 14px;border-radius:999px;border:1px solid var(--outline);background:transparent;color:var(--primary);cursor:pointer;transition:all .15s cubic-bezier(.22,1,.36,1)}
.chip:hover{background:rgba(168,199,250,.08)}
.chip:active{transform:scale(.97)}
.chip.flow{background:var(--primary);border-color:var(--primary);color:var(--on-primary)}
.fakeinput{display:flex;align-items:center;gap:10px;border:1px solid var(--outline-variant);border-radius:22px;padding:11px 16px;color:var(--outline);font-size:14px;background:var(--sc-low)}
.replay{margin-left:auto;font-size:12px;color:var(--primary);cursor:pointer;background:none;border:none;font-weight:500}

/* canvas cards */
.ctitle{font-size:20px;font-weight:500;line-height:1.3;margin:0 0 6px}
.csub{color:var(--on-surface-variant);font-size:14px;margin:0 0 16px}
.metrics{display:flex;gap:26px;flex-wrap:wrap;margin:8px 0 14px}
.mval{font-size:26px;font-weight:500;letter-spacing:-.01em}.mval.bad{color:var(--error)}
.mlbl{font-size:12px;color:var(--on-surface-variant);margin-top:2px}
.conf{margin:12px 0}.conf-track{height:6px;border-radius:999px;background:var(--sc-high);overflow:hidden}
.conf-fill{height:100%;background:var(--primary);border-radius:999px}
.conf-lbl{font-size:12px;color:var(--on-surface-variant);margin-top:7px}
.chart{width:100%;border-radius:var(--r-sm);border:1px solid var(--outline-variant);margin:14px 0;display:block}
.evidence{margin-top:14px;border-top:1px solid var(--outline-variant);padding-top:12px}
.evidence summary{cursor:pointer;list-style:none;font-size:13px;font-weight:500;color:var(--primary)}
.evidence summary::-webkit-details-marker{display:none}
.tbl{width:100%;border-collapse:collapse;font-size:12.5px;margin-top:8px}
.tbl th,.tbl td{text-align:left;padding:7px 10px;border-bottom:1px solid var(--outline-variant)}
.tbl th{color:var(--on-surface-variant);font-weight:500}
.tbl td.num,.tbl th.num{text-align:right}
.tbl tr.cause td{background:color-mix(in srgb,var(--error-container) 45%,transparent)}
.pill{display:inline-flex;align-items:center;border-radius:var(--r-sm);padding:2px 7px;font-size:11px;font-weight:500}
.pill-bad{background:var(--error-container);color:var(--on-error-container)}
.foot{font-size:11.5px;color:var(--outline);margin-top:12px}
.approve{display:flex;gap:12px;padding:14px 0;border-bottom:1px solid var(--outline-variant)}
.approve:last-of-type{border-bottom:none}
.aicon{width:28px;height:28px;flex:none;border-radius:var(--r-sm);display:grid;place-items:center;font-size:13px;font-weight:600;background:var(--sc-high);color:var(--on-surface-variant)}
.ah{font-weight:500;font-size:15px}.ad{font-size:13px;color:var(--on-surface-variant);margin-top:3px}
.btnrow{display:flex;gap:8px;margin-top:10px;flex-wrap:wrap}
.btn{font-size:13px;font-weight:500;padding:8px 15px;border-radius:999px;border:1px solid var(--outline);background:transparent;color:var(--primary);cursor:pointer;transition:all .15s}
.btn:active{transform:scale(.97)}.btn-primary{background:var(--primary);border-color:var(--primary);color:var(--on-primary)}
.btn-ghost{border-color:transparent}
.alert-k{color:var(--error)}
.tabs{display:flex;gap:8px;margin-bottom:14px}
.tab{font-size:13px;font-weight:500;padding:7px 14px;border-radius:999px;border:1px solid var(--outline-variant);background:transparent;color:var(--on-surface-variant);cursor:pointer}
.tab-on{background:var(--secondary-container);border-color:transparent;color:var(--on-secondary-container)}
"""

JS = """
const STEPS = __STEPS__;
let i = 0;
const thread = document.getElementById('thread');
const chat = document.getElementById('chat');
const canvas = document.getElementById('canvas');
const chips = document.getElementById('chips');

function el(html){const d=document.createElement('div');d.innerHTML=html.trim();return d.firstChild;}
function scroll(){thread.scrollTop=thread.scrollHeight;}

function renderChips(){
  chips.innerHTML='';
  if(i>=STEPS.length){
    const done=el('<div style="font-size:13px;color:var(--outline)">— end of scripted demo —</div>');
    chips.appendChild(done);
    return;
  }
  STEPS.forEach((s,idx)=>{
    if(idx<i) return;
    const b=document.createElement('button');
    b.className='chip'+(idx===i?' flow':'');
    b.textContent=s.chip;
    b.disabled=idx!==i;
    if(idx===i) b.onclick=()=>play();
    if(idx!==i){b.style.opacity=.4;b.style.cursor='default';}
    chips.appendChild(b);
  });
}

async function play(){
  const s=STEPS[i];
  chips.innerHTML='';
  // user turn
  thread.appendChild(el(`<div class="turn user fade-up"><div class="bubble">${s.user}</div></div>`));
  scroll();
  await wait(380);
  // agent reasoning trace (running)
  const calls=s.calls.map(c=>`<div class="call"><span class="dot"></span><span>${c}</span></div>`).join('');
  const turn=el(`<div class="turn agent fade-up"><div class="avatar">F</div><div class="bubble">
    <details class="trace" open><summary><span class="dot"></span> Thinking · ${s.skill}…</summary>${calls}</details></div></div>`);
  thread.appendChild(turn);scroll();
  await wait(1100);
  // collapse trace -> done
  const done=s.calls.map(c=>`<div class="call"><span class="ok">✓</span><span>${c}</span></div>`).join('');
  turn.querySelector('.trace').innerHTML=
    `<summary><span class="ok">✓</span> Reasoning · ${s.skill} · ${s.calls.length} steps</summary>${done}`;
  turn.querySelector('.trace').open=false;
  // answer
  turn.querySelector('.bubble').appendChild(el(`<div class="ans fade-up">${s.answer}</div>`));
  scroll();
  // mount canvas
  await wait(280);
  canvas.classList.add('on');chat.classList.add('has-canvas');
  canvas.innerHTML=`<div class="fade-up">${s.canvas}</div>`;
  wireCanvas();
  i++;
  renderChips();
  scroll();
}

function wireCanvas(){
  canvas.querySelectorAll('.tab').forEach(t=>t.onclick=()=>{
    canvas.querySelectorAll('.tab').forEach(x=>x.classList.remove('tab-on'));
    t.classList.add('tab-on');
    canvas.querySelectorAll('.tabpane').forEach(p=>p.hidden=p.dataset.pane!==t.dataset.tab);
  });
}
function wait(ms){return new Promise(r=>setTimeout(r,ms));}
function replay(){i=0;thread.innerHTML='';canvas.innerHTML='';canvas.classList.remove('on');chat.classList.remove('has-canvas');renderChips();}
document.getElementById('replay').onclick=replay;
renderChips();
"""

HTML = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>FlowDash · DS agent</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Roboto:wght@400;500;700&family=Roboto+Mono&display=swap" rel="stylesheet">
<style>{CSS}</style></head>
<body>
<header>
  <div class="logo">F</div><div class="name">FlowDash</div>
  <span style="font-size:13px;color:var(--on-surface-variant)">· data-science agent</span>
  <span class="demo">demo · synthetic data</span>
</header>
<div class="wrap">
  <div class="chat" id="chat">
    <div class="thread" id="thread"></div>
    <div class="composer">
      <div class="chips" id="chips"></div>
      <div class="fakeinput">Ask anything about FlowDash…
        <button class="replay" id="replay">↻ replay</button></div>
    </div>
  </div>
  <div class="canvas" id="canvas"></div>
</div>
<script>{JS.replace("__STEPS__", json.dumps(STEPS))}</script>
</body></html>"""

out = os.path.join(HERE, "index.html")
open(out, "w").write(HTML)
print(out, f"({len(HTML)//1024} KB)")
