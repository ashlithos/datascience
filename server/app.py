"""
app.py — live backend for the FlowDash DS-agent demo.

Pure standard-library HTTP server (no Flask). Two answer engines:

  * AGENT  (default if the Claude Agent SDK is available): a REAL agentic loop
    (server/agent.py) — an LLM that reads the project skills + data dictionary,
    decides which data-science tools to call, runs real SQL, and streams its
    thinking / tool-calls / answer to the UI over Server-Sent Events. Reviewable.

  * FAST   (always available): the deterministic rule router (web/render.py) that
    maps intent to a real query. Used as fallback and as a snappy alternative.

Run:   python server/app.py            # -> http://localhost:8000
       PORT=9000 python server/app.py
       AGENT_MODEL=claude-sonnet-4-6 python server/app.py   # pick the agent model

Endpoints:
  GET  /                 -> the chat + canvas app
  GET  /api/agent?text=  -> text/event-stream of agent events (real LLM loop)
  POST /api/ask  {text}  -> {skill, calls, answer, canvas}   (rule router, one-shot)
  POST /api/action {id,choice} -> updated cleaning panel (approve/skip, non-destructive)
  GET  /health           -> {ok, agent, nl_to_sql}
"""
import asyncio
import json
import os
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "web"))
import render  # noqa: E402

# the real agent is optional — degrade gracefully to the rule router if missing
try:
    import agent  # noqa: E402
    AGENT_OK = True
    AGENT_ERR = ""
except Exception as e:  # ImportError or SDK load failure
    AGENT_OK = False
    AGENT_ERR = f"{type(e).__name__}: {e}"

PORT = int(os.environ.get("PORT", "8000"))
STATE = {"clean": {}}

QUICK = [
    "Is this data clean enough to trust?",
    "Why is weekly active down?",
    "How's sql_export doing?",
    "Write me the weekly summary.",
    "Assume a week has passed.",
    "Show weekly active by region",
]

CLEAN_NOTES = {
    ("dedupe", "approve"): "Done — de-duped on session_id (kept first occurrence). The clean recipe now runs in every aggregate.",
    ("negatives", "approve"): "Done — negative-duration rows excluded from aggregates (source rows untouched).",
    ("regions", "approve"): "Done — region normalised to EMEA everywhere. Breakdowns will be consistent now.",
}


def page():
    chips = "".join(f'<button class="chip" data-q="{q}">{q}</button>' for q in QUICK)
    if AGENT_OK:
        badge = '<span class="live">agent · LLM loop</span>'
        default_mode = "agent"
    else:
        badge = '<span class="demo" title="' + AGENT_ERR.replace('"', "'") + '">rule-routed (SDK off)</span>'
        default_mode = "fast"
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>FlowDash · DS agent</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Roboto:wght@400;500;700&family=Roboto+Mono&display=swap" rel="stylesheet">
<style>{render.CSS}{EXTRA_CSS}</style></head><body data-mode="{default_mode}" data-agent="{int(AGENT_OK)}">
<header><div class="logo">F</div><div class="name">FlowDash</div>
  <span class="hdr-sub" style="font-size:13px;color:var(--on-surface-variant)">· data-science agent</span>
  {badge}
  <div class="modesw" id="modesw">
    <button data-m="agent" class="{'on' if default_mode=='agent' else ''}" {'disabled' if not AGENT_OK else ''}>Agent</button>
    <button data-m="fast" class="{'on' if default_mode=='fast' else ''}">Fast</button>
  </div>
  <span class="demo" style="margin-left:10px">demo · synthetic data</span></header>
<div class="wrap">
  <div class="chat" id="chat">
    <div class="thread" id="thread">
      <div class="turn agent"><div class="avatar">F</div><div class="bubble">
        <p>Hi — I'm the FlowDash analyst. Ask me anything about product usage in plain English, or tap a suggestion. In <b>Agent</b> mode you'll see me actually reason and call tools; I show my work on the right.</p></div></div>
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


EXTRA_CSS = """
.modesw{display:flex;margin-left:14px;border:1px solid var(--outline-variant);border-radius:999px;overflow:hidden}
.modesw button{background:transparent;border:none;color:var(--on-surface-variant);font-size:12px;font-weight:500;padding:5px 12px;cursor:pointer}
.modesw button.on{background:var(--primary);color:var(--on-primary)}
.modesw button:disabled{opacity:.35;cursor:not-allowed}
.trace .think{font-style:italic;color:var(--on-surface-variant);margin-top:6px;font-size:12px;font-family:var(--font);opacity:.92}
"""

JS = r"""
const body=document.body;
let MODE=body.dataset.mode;
const thread=document.getElementById('thread'),chat=document.getElementById('chat'),
 canvas=document.getElementById('canvas'),input=document.getElementById('input'),
 form=document.getElementById('form'),send=document.getElementById('send');
function el(h){const d=document.createElement('div');d.innerHTML=h.trim();return d.firstChild;}
function scroll(){thread.scrollTop=thread.scrollHeight;}
function wait(ms){return new Promise(r=>setTimeout(r,ms));}
function esc(s){return (s||'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));}
function md(s){return esc(s).replace(/\*\*(.+?)\*\*/g,'<b>$1</b>').replace(/`(.+?)`/g,'<code>$1</code>').replace(/\n/g,'<br>');}
function mount(html){canvas.classList.add('on');chat.classList.add('has-canvas');canvas.innerHTML=`<div class="fade-up">${html}</div>`;wireCanvas();}

document.getElementById('modesw').onclick=e=>{const b=e.target.closest('button');if(!b||b.disabled)return;
  MODE=b.dataset.m;document.querySelectorAll('.modesw button').forEach(x=>x.classList.toggle('on',x===b));};

function userTurn(text){thread.appendChild(el(`<div class="turn user fade-up"><div class="bubble"></div></div>`));
  thread.lastChild.querySelector('.bubble').textContent=text;scroll();}
function agentTurn(){const t=el(`<div class="turn agent fade-up"><div class="avatar">F</div><div class="bubble">
  <details class="trace" open><summary><span class="dot"></span> Thinking…</summary><div class="calls"></div></details>
  <div class="ans"></div></div></div>`);thread.appendChild(t);scroll();return t;}

async function ask(text){
  if(!text||!text.trim())return; input.value='';send.disabled=true;
  if(MODE==='agent' && body.dataset.agent==='1'){ await askAgent(text); }
  else { await askFast(text); }
  send.disabled=false;input.focus();
}

// ---- FAST (rule router, one-shot POST) ----
async function askFast(text){
  userTurn(text); const turn=agentTurn(); const calls=turn.querySelector('.calls');
  let data;
  try{const r=await fetch('/api/ask',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text})});data=await r.json();}
  catch(e){data={skill:'error',calls:['network error'],answer:'Backend unreachable.',canvas:''};}
  data.calls.forEach(c=>calls.appendChild(el(`<div class="call"><span class="dot"></span><span>${esc(c)}</span></div>`)));
  await wait(700);
  calls.querySelectorAll('.dot').forEach(d=>{const s=document.createElement('span');s.className='ok';s.textContent='✓';d.replaceWith(s);});
  finalizeTrace(turn,data.skill,data.calls.length);
  turn.querySelector('.ans').innerHTML=`<div class="fade-up">${data.answer}</div>`;scroll();
  if(data.canvas){await wait(200);mount(data.canvas);}
}

// ---- AGENT (real LLM loop, SSE stream) ----
function askAgent(text){
  return new Promise(resolve=>{
    userTurn(text); const turn=agentTurn();
    const calls=turn.querySelector('.calls'), ans=turn.querySelector('.ans');
    const pending=[]; let steps=0, skill='agent';
    const es=new EventSource('/api/agent?text='+encodeURIComponent(text));
    es.onmessage=ev=>{
      const e=JSON.parse(ev.data);
      if(e.type==='thinking'){ calls.appendChild(el(`<div class="think">${esc(e.text)}</div>`)); steps++; scroll(); }
      else if(e.type==='tool'){ const d=el(`<div class="call"><span class="dot"></span><span>tool · ${esc(e.name)}</span></div>`);
        calls.appendChild(d); pending.push(d); steps++; scroll(); }
      else if(e.type==='tool_result'){ const d=pending.shift(); if(d){const k=d.querySelector('.dot');if(k){const s=document.createElement('span');s.className='ok';s.textContent='✓';k.replaceWith(s);}} }
      else if(e.type==='skill'){ skill=e.name; }
      else if(e.type==='text'){ ans.innerHTML+=md(e.text); scroll(); }
      else if(e.type==='artifact'){ mount(e.html); }
      else if(e.type==='error'){ ans.innerHTML+=`<div style="color:var(--error)">Agent error: ${esc(e.msg)}. Falling back to fast mode.</div>`;
        es.close(); finalizeTrace(turn,'error',steps); askFast(text).then(resolve); return; }
      else if(e.type==='done'){ es.close();
        calls.querySelectorAll('.dot').forEach(d=>{const s=document.createElement('span');s.className='ok';s.textContent='✓';d.replaceWith(s);});
        if(!ans.innerHTML && e.answer) ans.innerHTML=md(e.answer);
        finalizeTrace(turn,skill,steps); scroll(); resolve(); }
    };
    es.onerror=()=>{ es.close(); if(!ans.innerHTML){ans.innerHTML='<span style="color:var(--error)">Connection lost.</span>';} finalizeTrace(turn,skill,steps); resolve(); };
  });
}

function finalizeTrace(turn,skill,steps){
  const tr=turn.querySelector('.trace'); if(!tr)return;
  tr.querySelector('summary').innerHTML=`<span class="ok">✓</span> Reasoning · ${esc(skill)} · ${steps} step${steps===1?'':'s'}`;
  tr.open=false;
}

function wireCanvas(){
  canvas.querySelectorAll('.tab').forEach(t=>t.onclick=()=>{
    canvas.querySelectorAll('.tab').forEach(x=>x.classList.remove('tab-on'));t.classList.add('tab-on');
    canvas.querySelectorAll('.tabpane').forEach(p=>p.hidden=p.dataset.pane!==t.dataset.tab);});
  canvas.querySelectorAll('[data-act="clean"]').forEach(b=>b.onclick=async()=>{
    const r=await fetch('/api/action',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({id:b.dataset.id,choice:b.dataset.choice})});
    const d=await r.json(); canvas.innerHTML=`<div class="fade-up">${d.canvas}</div>`;wireCanvas();
    if(d.note){thread.appendChild(el(`<div class="turn agent fade-up"><div class="avatar">F</div><div class="bubble"><div>${d.note}</div></div></div>`));scroll();}});
  canvas.querySelectorAll('[data-act="ask"]').forEach(b=>b.onclick=()=>ask(b.dataset.q));
}
form.onsubmit=e=>{e.preventDefault();ask(input.value);};
document.getElementById('chips').onclick=e=>{const b=e.target.closest('.chip');if(b)ask(b.dataset.q);};
"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
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

    # ---- agent SSE stream ----
    def _stream_agent(self, text):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        def write(ev):
            self.wfile.write(f"data: {json.dumps(ev)}\n\n".encode())
            self.wfile.flush()

        loop = asyncio.new_event_loop()
        try:
            agen = agent.run_stream(text)
            while True:
                try:
                    ev = loop.run_until_complete(agen.__anext__())
                except StopAsyncIteration:
                    break
                write(ev)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:
            try:
                write({"type": "error", "msg": f"{type(e).__name__}: {e}"})
            except Exception:
                pass
        finally:
            loop.close()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path in ("/", "/index.html"):
            self._send(200, page(), "text/html; charset=utf-8")
        elif parsed.path == "/api/agent":
            if not AGENT_OK:
                self._send(503, json.dumps({"error": "agent unavailable", "detail": AGENT_ERR}))
                return
            qs = urllib.parse.parse_qs(parsed.query)
            text = (qs.get("text", [""])[0]).strip()
            self._stream_agent(text)
        elif parsed.path == "/health":
            self._send(200, json.dumps({"ok": True, "agent": AGENT_OK,
                                        "agent_err": AGENT_ERR,
                                        "nl_to_sql": render.nl_to_sql_available()}))
        else:
            self._send(404, json.dumps({"error": "not found"}))

    def do_POST(self):
        try:
            data = self._body()
        except Exception:
            return self._send(400, json.dumps({"error": "bad json"}))
        if self.path == "/api/ask":
            self._send(200, json.dumps(render.route(data.get("text", ""), STATE)))
        elif self.path == "/api/action":
            cid, choice = data.get("id"), data.get("choice")
            if choice in ("approve", "skip"):
                STATE["clean"][cid] = "approved" if choice == "approve" else "skipped"
            note = CLEAN_NOTES.get((cid, choice), "")
            self._send(200, json.dumps({"canvas": render.canvas_cleaning(STATE["clean"]), "note": note}))
        else:
            self._send(404, json.dumps({"error": "not found"}))


if __name__ == "__main__":
    print(f"FlowDash DS-agent → http://localhost:{PORT}")
    print(f"  engine: {'AGENT (real LLM loop via Claude Agent SDK)' if AGENT_OK else 'FAST rule-router only'}")
    if not AGENT_OK:
        print(f"  (agent off: {AGENT_ERR})")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
