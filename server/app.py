"""
app.py — live backend for the FlowDash DS-agent demo.

Pure standard-library HTTP server (no Flask, no pip installs) so anyone can clone
and run it. It serves the live chat UI and answers real questions by routing intent
to the actual tools and querying the real SQLite database.

Run:   python server/app.py          # -> http://localhost:8000
       PORT=9000 python server/app.py

Endpoints:
  GET  /                -> the live chat + canvas app
  POST /api/ask  {text} -> {skill, calls[], answer, canvas}   (runs real analysis)
  POST /api/action {id, choice} -> updated cleaning panel (approve/skip is non-destructive)
  GET  /health          -> {ok, nl_to_sql}

NL->SQL: rule-based by default; if ANTHROPIC_API_KEY is set the /api/ask route could
be upgraded to true text-to-SQL (hook present in web/render.py).
"""
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "web"))
import render  # noqa: E402

PORT = int(os.environ.get("PORT", "8000"))

# in-memory session state (demo = single user). Tracks cleaning approvals.
STATE = {"clean": {}}

QUICK = [
    "Is this data clean enough to trust?",
    "Why is weekly active down?",
    "How's sql_export doing?",
    "Write me the weekly summary.",
    "Assume a week has passed.",
    "Show weekly active by region",
]


def page():
    chips = "".join(f'<button class="chip" data-q="{q}">{q}</button>' for q in QUICK)
    live = "live backend" if True else ""
    nl = "· NL→SQL on" if render.nl_to_sql_available() else "· rule-routed"
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>FlowDash · DS agent (live)</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Roboto:wght@400;500;700&family=Roboto+Mono&display=swap" rel="stylesheet">
<style>{render.CSS}</style></head><body>
<header><div class="logo">F</div><div class="name">FlowDash</div>
  <span style="font-size:13px;color:var(--on-surface-variant)">· data-science agent</span>
  <span class="live">{live} {nl}</span>
  <span class="demo" style="margin-left:10px">demo · synthetic data</span></header>
<div class="wrap">
  <div class="chat" id="chat">
    <div class="thread" id="thread">
      <div class="turn agent"><div class="avatar">F</div><div class="bubble">
        <p>Hi — I'm the FlowDash analyst. Ask me anything about product usage in plain English, or tap a suggestion. I'll show my work on the right.</p></div></div>
    </div>
    <div class="composer">
      <div class="chips" id="chips">{chips}</div>
      <form class="form" id="form" autocomplete="off">
        <input id="input" placeholder="Ask about FlowDash, or paste a SELECT…">
        <button class="send" id="send" type="submit">↑</button>
      </form>
    </div>
  </div>
  <div class="canvas" id="canvas"></div>
</div>
<script>{JS}</script></body></html>"""


JS = r"""
const thread=document.getElementById('thread'),chat=document.getElementById('chat'),
 canvas=document.getElementById('canvas'),input=document.getElementById('input'),
 form=document.getElementById('form'),send=document.getElementById('send');
function el(h){const d=document.createElement('div');d.innerHTML=h.trim();return d.firstChild;}
function scroll(){thread.scrollTop=thread.scrollHeight;}
function wait(ms){return new Promise(r=>setTimeout(r,ms));}

async function ask(text){
  if(!text.trim())return;
  input.value='';send.disabled=true;
  thread.appendChild(el(`<div class="turn user fade-up"><div class="bubble"></div></div>`));
  thread.lastChild.querySelector('.bubble').textContent=text;scroll();
  const turn=el(`<div class="turn agent fade-up"><div class="avatar">F</div><div class="bubble">
    <details class="trace" open><summary><span class="dot"></span> Thinking…</summary></details></div></div>`);
  thread.appendChild(turn);scroll();
  let data;
  try{ const r=await fetch('/api/ask',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text})}); data=await r.json(); }
  catch(e){ data={skill:'error',calls:['network error'],answer:'Sorry — the backend is unreachable.',canvas:''}; }
  const calls=data.calls.map(c=>`<div class="call"><span class="dot"></span><span>${c}</span></div>`).join('');
  turn.querySelector('.trace').innerHTML=`<summary><span class="dot"></span> Thinking · ${data.skill}…</summary>${calls}`;
  await wait(800);
  const done=data.calls.map(c=>`<div class="call"><span class="ok">✓</span><span>${c}</span></div>`).join('');
  const tr=turn.querySelector('.trace');
  tr.innerHTML=`<summary><span class="ok">✓</span> Reasoning · ${data.skill} · ${data.calls.length} steps</summary>${done}`;
  tr.open=false;
  turn.querySelector('.bubble').appendChild(el(`<div class="fade-up">${data.answer}</div>`));
  scroll();
  if(data.canvas){ await wait(220); mount(data.canvas); }
  send.disabled=false;input.focus();
}
function mount(html){
  canvas.classList.add('on');chat.classList.add('has-canvas');
  canvas.innerHTML=`<div class="fade-up">${html}</div>`;wireCanvas();
}
function wireCanvas(){
  canvas.querySelectorAll('.tab').forEach(t=>t.onclick=()=>{
    canvas.querySelectorAll('.tab').forEach(x=>x.classList.remove('tab-on'));t.classList.add('tab-on');
    canvas.querySelectorAll('.tabpane').forEach(p=>p.hidden=p.dataset.pane!==t.dataset.tab);});
  canvas.querySelectorAll('[data-act="clean"]').forEach(b=>b.onclick=async()=>{
    const r=await fetch('/api/action',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({id:b.dataset.id,choice:b.dataset.choice})});
    const d=await r.json(); canvas.innerHTML=`<div class="fade-up">${d.canvas}</div>`;wireCanvas();
    if(d.note){thread.appendChild(el(`<div class="turn agent fade-up"><div class="avatar">F</div><div class="bubble"><div>${d.note}</div></div></div>`));scroll();}
  });
  canvas.querySelectorAll('[data-act="ask"]').forEach(b=>b.onclick=()=>ask(b.dataset.q));
}
form.onsubmit=e=>{e.preventDefault();ask(input.value);};
document.getElementById('chips').onclick=e=>{const b=e.target.closest('.chip');if(b)ask(b.dataset.q);};
"""

# patch JS reference into page() (page defined before JS); rebuild closure
def page_html():
    return page()


CLEAN_NOTES = {
    ("dedupe", "approve"): "Done — de-duped on session_id (kept first occurrence). The clean recipe now runs in every aggregate.",
    ("negatives", "approve"): "Done — negative-duration rows excluded from aggregates (source rows untouched).",
    ("regions", "approve"): "Done — region normalised to EMEA everywhere. Breakdowns will be consistent now.",
}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):   # quieter logs
        pass

    def _send(self, code, body, ctype="application/json"):
        b = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _body(self):
        n = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(n) or "{}") if n else {}

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, page_html(), "text/html; charset=utf-8")
        elif self.path == "/health":
            self._send(200, json.dumps({"ok": True, "nl_to_sql": render.nl_to_sql_available()}))
        else:
            self._send(404, json.dumps({"error": "not found"}))

    def do_POST(self):
        try:
            data = self._body()
        except Exception:
            return self._send(400, json.dumps({"error": "bad json"}))
        if self.path == "/api/ask":
            res = render.route(data.get("text", ""), STATE)
            self._send(200, json.dumps(res))
        elif self.path == "/api/action":
            cid, choice = data.get("id"), data.get("choice")
            if choice in ("approve", "skip"):
                STATE["clean"][cid] = "approved" if choice == "approve" else "skipped"
            note = CLEAN_NOTES.get((cid, choice), "")
            self._send(200, json.dumps({"canvas": render.canvas_cleaning(STATE["clean"]), "note": note}))
        else:
            self._send(404, json.dumps({"error": "not found"}))


if __name__ == "__main__":
    print(f"FlowDash DS-agent (live) → http://localhost:{PORT}")
    print(f"  NL→SQL: {'on (ANTHROPIC_API_KEY set)' if render.nl_to_sql_available() else 'rule-routed'}")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
