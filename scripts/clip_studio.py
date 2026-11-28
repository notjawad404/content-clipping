"""Local page for browsing rendered clips and copying their post text.

Run: uv run python scripts/clip_studio.py [--port 8765] [--no-browser]
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from clipper.publish import PublishError  # noqa: E402
from clipper.publish.tiktok import PRIVACY_LEVELS, TikTokClient  # noqa: E402
from scripts.tiktok_auth import read_env  # noqa: E402

JOBS, OUTPUT, QUEUE = ROOT / "jobs", ROOT / "output", ROOT / "queue"
ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
TT_KEYS = ("TT_CLIENT_KEY", "TT_CLIENT_SECRET", "TT_REFRESH_TOKEN")
_tt: dict = {"client": None, "refresh": None, "connecting": False}


def _read(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _status(video_id: str, clip_id: str) -> str:
    name = f"{video_id}_{clip_id}.json"
    for state in ("posted", "pending", "failed"):
        if (QUEUE / state / name).exists():
            return state
    return "not queued"


def load_videos() -> list[dict]:
    videos = []
    for out_dir in OUTPUT.iterdir() if OUTPUT.is_dir() else []:
        vid = out_dir.name
        resolved = _read(JOBS / vid / "clips.resolved.json")
        if not resolved.get("clips"):
            continue
        meta = _read(JOBS / vid / "meta.json")
        clips = []
        for c in resolved["clips"]:
            mp4 = out_dir / f"{c['id']}.mp4"
            if not mp4.exists():
                continue
            post = c.get("post", {})
            caption = post.get("instagram", "")
            clips.append({
                "id": c["id"], "score": c.get("score"), "hook": c.get("hook_text", ""),
                "start": c.get("start"), "end": c.get("end"),
                "yt_title": c.get("title", ""), "yt_desc": post.get("youtube") or caption,
                "yt_tags": ", ".join(c.get("youtube_tags") or []),
                "tiktok": post.get("tiktok") or caption, "instagram": caption,
                "status": _status(vid, c["id"]),
            })
        if clips:
            videos.append({"id": vid, "title": meta.get("title", vid), "clips": clips,
                           "mtime": out_dir.stat().st_mtime})
    videos.sort(key=lambda v: -v["mtime"])
    return videos


def _tiktok() -> TikTokClient | None:
    env = read_env()
    if not all(env.get(k) for k in TT_KEYS):
        return None
    if _tt["refresh"] != env["TT_REFRESH_TOKEN"]:
        _tt["client"] = TikTokClient(*(env[k] for k in TT_KEYS))
        _tt["refresh"] = env["TT_REFRESH_TOKEN"]
    return _tt["client"]


def _connect() -> None:
    try:
        subprocess.run([sys.executable, str(ROOT / "scripts" / "tiktok_auth.py")], cwd=ROOT, timeout=330)
    finally:
        _tt["connecting"] = False
        _tt["refresh"] = None


def tiktok_post(body: dict) -> dict:
    """Validates the composer's choices against creator_info, then direct-posts the clip."""
    client = _tiktok()
    if client is None:
        raise PublishError("TikTok is not connected")
    path = _clip_path(str(body.get("video", "")), str(body.get("clip", "")))
    if not path:
        raise PublishError("clip file not found")
    info = client.creator_info()
    privacy = body.get("privacy")
    if privacy not in PRIVACY_LEVELS or privacy not in (info.get("privacy_level_options") or []):
        raise PublishError("choose who can view this video")
    duration, limit = float(body.get("duration") or 0), info.get("max_video_post_duration_sec")
    if limit and duration > limit:
        raise PublishError(f"this clip is {duration:.0f}s; your account allows up to {limit}s")
    commercial, organic, branded = (bool(body.get(k)) for k in ("commercial", "brand_organic", "brand_content"))
    if commercial and not (organic or branded):
        raise PublishError("indicate if your content promotes yourself, a third party, or both")
    publish_id = client.upload(
        path.read_bytes(), str(body.get("caption", "")), privacy,
        allow_comment=bool(body.get("allow_comment")) and not info.get("comment_disabled"),
        allow_duet=bool(body.get("allow_duet")) and not info.get("duet_disabled"),
        allow_stitch=bool(body.get("allow_stitch")) and not info.get("stitch_disabled"),
        brand_organic=commercial and organic, brand_content=commercial and branded)
    return {"publish_id": publish_id}


def _clip_path(vid: str, clip: str) -> Path | None:
    if not (ID_RE.match(vid) and ID_RE.match(clip)):
        return None
    path = OUTPUT / vid / f"{clip}.mp4"
    return path if path.is_file() else None


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Clip Studio</title>
<style>
:root{--bg:#0f1115;--card:#181b22;--line:#2a2f3a;--text:#e8eaf0;--muted:#9aa3b2;--accent:#4f8cff;--ok:#3fb950;--warn:#d29922}
*{box-sizing:border-box}body{margin:0;font:14px/1.45 system-ui,Segoe UI,sans-serif;background:var(--bg);color:var(--text)}
header{position:sticky;top:0;z-index:2;display:flex;gap:12px;align-items:center;padding:12px 20px;background:#0f1115ee;border-bottom:1px solid var(--line);backdrop-filter:blur(6px)}
h1{font-size:16px;margin:0 8px 0 0}select,input{background:var(--card);color:var(--text);border:1px solid var(--line);border-radius:6px;padding:6px 8px;font:inherit}
input{flex:1;max-width:320px}main{padding:20px;display:grid;gap:16px;grid-template-columns:repeat(auto-fill,minmax(560px,1fr))}
.card{display:grid;grid-template-columns:200px 1fr;gap:14px;background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px}
video{width:200px;aspect-ratio:9/16;background:#000;border-radius:6px}
.top{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:6px}.id{font-weight:600}
.pill{font-size:12px;padding:1px 8px;border-radius:99px;border:1px solid var(--line);color:var(--muted)}
.pill.posted{color:var(--ok);border-color:var(--ok)}.pill.pending{color:var(--warn);border-color:var(--warn)}
.tabs{display:flex;gap:4px;margin:6px 0}.tabs button{background:none;border:1px solid var(--line);color:var(--muted);border-radius:6px;padding:4px 10px;cursor:pointer;font:inherit}
.tabs button.on{color:var(--text);border-color:var(--accent);background:#4f8cff22}
.field{margin-bottom:8px}.label{display:flex;justify-content:space-between;align-items:center;color:var(--muted);font-size:12px;margin-bottom:3px}
pre{margin:0;white-space:pre-wrap;word-break:break-word;background:#0f1115;border:1px solid var(--line);border-radius:6px;padding:8px;font:13px/1.4 system-ui,Segoe UI,sans-serif;max-height:170px;overflow:auto}
.copy,.act{background:var(--accent);color:#fff;border:0;border-radius:5px;padding:3px 10px;cursor:pointer;font:inherit;font-size:12px}
.copy.done{background:var(--ok)}.act{background:#2a2f3a}.act:hover{background:#3a4150}.actions{display:flex;gap:6px;margin-top:8px}
.meta{color:var(--muted);font-size:12px}.empty{padding:40px;color:var(--muted)}
.act.tt{background:#fe2c55}.act.tt:hover{background:#e0244a}
#acct{margin-left:auto;display:flex;align-items:center;gap:8px}#acct img{width:26px;height:26px;border-radius:50%}
.overlay{position:fixed;inset:0;z-index:5;background:#000a;display:none;align-items:flex-start;justify-content:center;overflow:auto;padding:30px 12px}
.overlay.on{display:flex}.modal{width:min(820px,100%);background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px;display:grid;grid-template-columns:240px 1fr;gap:18px}
.modal video{width:240px}.modal h2{font-size:16px;margin:0 0 10px}.row{margin-bottom:14px}.row>label,.row .h{display:block;font-weight:600;margin-bottom:5px}
textarea{width:100%;min-height:110px;background:#0f1115;color:var(--text);border:1px solid var(--line);border-radius:6px;padding:8px;font:inherit;resize:vertical}
.modal select{width:100%}.checks label{display:inline-flex;align-items:center;gap:5px;margin-right:16px}.checks label.off{opacity:.45}
.switch{display:flex;justify-content:space-between;align-items:center}.sub{margin:8px 0 0 4px}.sub label{display:block;margin:6px 0}
.note{color:var(--muted);font-size:12px;margin-top:4px}.notice{background:#4f8cff1a;border:1px solid #4f8cff55;border-radius:6px;padding:7px 9px;font-size:12px;margin-top:6px}
.err{color:#ff6b6b;font-size:13px;margin-top:6px}.decl{font-size:12px;color:var(--muted)}.decl a{color:var(--accent)}
.foot{display:flex;gap:8px;justify-content:flex-end;margin-top:10px}.btn{border:0;border-radius:6px;padding:8px 18px;font:inherit;cursor:pointer;background:#2a2f3a;color:var(--text)}
.btn.primary{background:#fe2c55;color:#fff}.btn:disabled{opacity:.4;cursor:not-allowed}.who{display:flex;align-items:center;gap:8px;margin-bottom:12px}.who img{width:34px;height:34px;border-radius:50%}
</style></head><body>
<header><h1>Clip Studio</h1><select id="video"></select><input id="q" placeholder="Filter by title or text"><span class="meta" id="count"></span>
<span id="acct"></span></header>
<main id="grid"></main>
<div class="overlay" id="ov"><div class="modal" id="modal"></div></div>
<script>
const DATA = __DATA__;
const PLATFORMS = {
  youtube: [["Title","yt_title"],["Description","yt_desc"],["Tags","yt_tags"]],
  tiktok: [["Caption","tiktok"]],
  instagram: [["Caption","instagram"]],
};
const sel = document.getElementById("video"), grid = document.getElementById("grid"), q = document.getElementById("q");
DATA.forEach((v,i)=>sel.add(new Option(`${v.title} (${v.clips.length})`, i)));
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const fmt = s => s==null ? "" : new Date(s*1000).toISOString().substr(11,8).replace(/^00:/,"");

function render(){
  const v = DATA[sel.value]; if(!v){grid.innerHTML='<div class="empty">No rendered clips found in output/.</div>';return}
  const term = q.value.trim().toLowerCase();
  const clips = v.clips.filter(c => !term || [c.yt_title,c.yt_desc,c.tiktok,c.instagram,c.hook].join(" ").toLowerCase().includes(term));
  document.getElementById("count").textContent = `${clips.length} clip${clips.length===1?"":"s"}`;
  grid.innerHTML = clips.map(c => `
  <div class="card" data-clip="${c.id}">
    <video src="/media/${v.id}/${c.id}.mp4" controls preload="metadata"></video>
    <div>
      <div class="top"><span class="id">${c.id}</span><span class="pill">score ${c.score ?? "-"}</span>
        <span class="pill ${c.status.replace(" ","-")}">${c.status}</span><span class="meta">${fmt(c.start)}–${fmt(c.end)}</span></div>
      <div class="meta">${esc(c.hook)}</div>
      <div class="tabs">${Object.keys(PLATFORMS).map((p,i)=>`<button data-p="${p}" class="${i?"":"on"}">${p[0].toUpperCase()+p.slice(1)}</button>`).join("")}</div>
      <div class="fields"></div>
      <div class="actions"><button class="act" data-open="${c.id}">Open in folder</button><button class="act" data-play="${c.id}">Play</button><button class="act tt" data-tt="${c.id}">Post to TikTok</button></div>
    </div>
  </div>`).join("");
  grid.querySelectorAll(".card").forEach(card => showPlatform(card, "youtube"));
}

function showPlatform(card, p){
  const c = DATA[sel.value].clips.find(x => x.id === card.dataset.clip);
  card.querySelectorAll(".tabs button").forEach(b => b.classList.toggle("on", b.dataset.p === p));
  card.querySelector(".fields").innerHTML = PLATFORMS[p].map(([label,key]) => `
    <div class="field"><div class="label"><span>${label} <span class="meta">(${(c[key]||"").length} chars)</span></span>
    <button class="copy" data-key="${key}">Copy</button></div><pre>${esc(c[key])}</pre></div>`).join("");
}

grid.addEventListener("click", async e => {
  const card = e.target.closest(".card"); if(!card) return;
  const c = DATA[sel.value].clips.find(x => x.id === card.dataset.clip);
  if(e.target.dataset.p) showPlatform(card, e.target.dataset.p);
  if(e.target.dataset.key){
    await navigator.clipboard.writeText(c[e.target.dataset.key] || "");
    e.target.textContent = "Copied"; e.target.classList.add("done");
    setTimeout(()=>{e.target.textContent="Copy"; e.target.classList.remove("done")}, 1200);
  }
  if(e.target.dataset.open){
    const r = await fetch(`/open?video=${DATA[sel.value].id}&clip=${c.id}`, {method:"POST"});
    if(!r.ok) alert(await r.text());
  }
  if(e.target.dataset.play) card.querySelector("video").play();
  if(e.target.dataset.tt) openComposer(DATA[sel.value], c);
});
sel.onchange = render; q.oninput = render; render();

const PRIVACY = {PUBLIC_TO_EVERYONE:"Everyone", FOLLOWER_OF_CREATOR:"Followers", MUTUAL_FOLLOW_FRIENDS:"Friends", SELF_ONLY:"Only me"};
const ov = document.getElementById("ov"), modal = document.getElementById("modal"), acct = document.getElementById("acct");
let poll = null;

async function loadCreator(){
  const info = await (await fetch("/tiktok/creator")).json();
  if(info.connecting){ acct.innerHTML = '<span class="meta">Waiting for TikTok login in your browser...</span>'; setTimeout(loadCreator, 2000); return info }
  acct.innerHTML = !info.connected
    ? '<button class="act tt" id="connect">Connect TikTok</button>'
    : info.error ? `<span class="meta">TikTok: ${esc(info.error)}</span><button class="act" id="connect">Reconnect</button>`
    : `<img src="${esc(info.creator_avatar_url)}" alt=""><span>${esc(info.creator_nickname)} <span class="meta">@${esc(info.creator_username)}</span></span>`;
  const btn = document.getElementById("connect");
  if(btn) btn.onclick = async () => { await fetch("/tiktok/connect", {method:"POST"}); loadCreator() };
  return info;
}

async function openComposer(v, c){
  clearInterval(poll);
  ov.classList.add("on");
  modal.innerHTML = '<div class="meta">Loading your TikTok account...</div>';
  const info = await loadCreator();
  if(!info.connected || info.error){
    const why = info.error ? `TikTok says: ${esc(info.error)}. You can't post right now; try again later.` : "Connect your TikTok account first (top right).";
    modal.innerHTML = `<div style="grid-column:1/-1"><h2>Post to TikTok</h2><p>${why}</p><div class="foot"><button class="btn" data-close>Close</button></div></div>`;
    return;
  }
  const duration = Math.max(0, (c.end ?? 0) - (c.start ?? 0));
  const limit = info.max_video_post_duration_sec;
  const tooLong = !!limit && duration > limit;
  const opts = info.privacy_level_options || [];
  const box = (k, label, off) => `<label class="${off ? "off" : ""}" title="${off ? "Turned off in your TikTok settings" : ""}"><input type="checkbox" id="${k}" ${off ? "disabled" : ""}> ${label}</label>`;
  modal.innerHTML = `
    <video src="/media/${v.id}/${c.id}.mp4" controls autoplay muted playsinline></video>
    <div>
      <h2>Post to TikTok</h2>
      <div class="who"><img src="${esc(info.creator_avatar_url)}" alt=""><div><b>${esc(info.creator_nickname)}</b><div class="meta">Posting to @${esc(info.creator_username)}</div></div></div>
      ${tooLong ? `<div class="err">This clip is ${Math.round(duration)}s long. Your account can post videos up to ${limit}s.</div>` : ""}
      <div class="row"><label for="cap">Title</label><textarea id="cap" maxlength="2200">${esc(c.tiktok)}</textarea><div class="note" id="capn"></div></div>
      <div class="row"><label for="priv">Who can view this video</label>
        <select id="priv"><option value="" selected disabled>Select privacy level</option>
        ${opts.map(o => `<option value="${o}">${PRIVACY[o] || o}</option>`).join("")}</select></div>
      <div class="row"><span class="h">Allow users to</span><div class="checks">
        ${box("cmt", "Comment", info.comment_disabled)}${box("duet", "Duet", info.duet_disabled)}${box("stitch", "Stitch", info.stitch_disabled)}</div></div>
      <div class="row"><div class="switch"><span class="h">Disclose video content</span><input type="checkbox" id="com"></div>
        <div class="note">Turn on to disclose that this video promotes goods or services in exchange for something of value. Your video could promote yourself, a third party, or both.</div>
        <div class="sub" id="comsub" hidden>
          <label><input type="checkbox" id="org"> <b>Your brand</b> <span class="note">You are promoting yourself or your own business.</span></label>
          <label><input type="checkbox" id="brand"> <b>Branded content</b> <span class="note">You are promoting another brand or a third party.</span></label>
          <div class="notice" id="comlabel"></div></div></div>
      <div class="decl" id="decl"></div>
      <div class="err" id="err"></div>
      <div class="foot"><button class="btn" data-close>Cancel</button><button class="btn primary" id="post" disabled>Post</button></div>
    </div>`;
  const $ = id => document.getElementById(id);
  const MUSIC = '<a href="https://www.tiktok.com/legal/page/global/music-usage-confirmation/en" target="_blank">Music Usage Confirmation</a>';
  const BRAND = '<a href="https://www.tiktok.com/legal/page/global/bc-policy/en" target="_blank">Branded Content Policy</a>';
  function sync(){
    const com = $("com").checked, org = $("org").checked, brand = $("brand").checked;
    $("comsub").hidden = !com;
    const self = [...$("priv").options].find(o => o.value === "SELF_ONLY");
    if(self){
      self.disabled = com && brand;
      self.textContent = self.disabled ? "Only me (branded content can't be private)" : "Only me";
      if(self.disabled && $("priv").value === "SELF_ONLY") $("priv").value = "";
    }
    $("comlabel").textContent = !com ? "" : brand ? "Your photo/video will be labeled as 'Paid partnership'."
      : org ? "Your photo/video will be labeled as 'Promotional content'." : "You need to indicate if your content promotes yourself, a third party, or both.";
    $("decl").innerHTML = `By posting, you agree to TikTok's ${com && brand ? BRAND + " and " : ""}${MUSIC}.`;
    $("capn").textContent = `${$("cap").value.length}/2200`;
    const missing = !$("priv").value ? "Choose who can view this video." : com && !org && !brand ? "Choose Your brand, Branded content, or both." : "";
    $("post").disabled = !!missing || tooLong;
    $("post").title = missing;
  }
  modal.querySelectorAll("input,select,textarea").forEach(el => { el.addEventListener("input", sync); el.addEventListener("change", sync) });
  sync();
  $("post").onclick = async () => {
    $("post").disabled = true; $("err").textContent = ""; $("post").textContent = "Uploading...";
    const r = await fetch("/tiktok/post", {method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify({
      video: v.id, clip: c.id, caption: $("cap").value, privacy: $("priv").value, duration,
      allow_comment: $("cmt").checked, allow_duet: $("duet").checked, allow_stitch: $("stitch").checked,
      commercial: $("com").checked, brand_organic: $("org").checked, brand_content: $("brand").checked})});
    const res = await r.json();
    if(!r.ok){ $("err").textContent = res.error; $("post").textContent = "Post"; sync(); return }
    showProgress(res.publish_id);
  };
}

function showProgress(id){
  const LABEL = {PROCESSING_UPLOAD:"Uploading to TikTok...", PROCESSING_DOWNLOAD:"TikTok is fetching the video...", PUBLISH_COMPLETE:"Posted to TikTok.", FAILED:"TikTok could not publish this video."};
  modal.innerHTML = `<div style="grid-column:1/-1"><h2>Post to TikTok</h2><p id="st">Your video is uploaded. TikTok is processing it; it can take a few minutes to appear on your profile.</p><p class="meta" id="st2"></p><div class="foot"><button class="btn" data-close>Close</button></div></div>`;
  poll = setInterval(async () => {
    const r = await fetch(`/tiktok/status?id=${encodeURIComponent(id)}`), d = await r.json();
    const st = document.getElementById("st"), st2 = document.getElementById("st2");
    if(!st) return clearInterval(poll);
    if(!r.ok){ st2.textContent = d.error; return }
    st2.textContent = LABEL[d.status] || d.status;
    if(d.status === "PUBLISH_COMPLETE"){ clearInterval(poll); st.textContent = "Done. Your video is on TikTok; it may take a few minutes to show on your profile." }
    if(d.status === "FAILED"){ clearInterval(poll); st.textContent = "TikTok reported: " + (d.fail_reason || "unknown error") }
  }, 3000);
}

ov.addEventListener("click", e => { if(e.target === ov || "close" in e.target.dataset){ ov.classList.remove("on"); clearInterval(poll); modal.innerHTML = "" } });
loadCreator();
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, code: int, body: bytes, ctype: str = "text/plain; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urlparse(self.path)
        if url.path == "/":
            data = json.dumps(load_videos(), ensure_ascii=False).replace("</", "<\\/")
            return self._send(200, PAGE.replace("__DATA__", data).encode("utf-8"), "text/html; charset=utf-8")
        if url.path == "/tiktok/creator":
            return self._tiktok_creator()
        if url.path == "/tiktok/status":
            return self._tiktok_call(lambda c: c.status(parse_qs(url.query).get("id", [""])[0]))
        m = re.match(r"^/media/([^/]+)/([^/]+)\.mp4$", url.path)
        if m and (path := _clip_path(m.group(1), m.group(2))):
            return self._serve_video(path)
        self._send(404, b"not found")

    def do_POST(self):
        url = urlparse(self.path)
        if url.path == "/tiktok/connect":
            if not _tt["connecting"]:
                _tt["connecting"] = True
                threading.Thread(target=_connect, daemon=True).start()
            return self._json(202, {"connecting": True})
        if url.path == "/tiktok/post":
            length = int(self.headers.get("Content-Length") or 0)
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
            except ValueError:
                return self._json(400, {"error": "bad request"})
            return self._tiktok_call(lambda _: tiktok_post(body))
        if url.path != "/open":
            return self._send(404, b"not found")
        qs = parse_qs(url.query)
        path = _clip_path(qs.get("video", [""])[0], qs.get("clip", [""])[0])
        if not path:
            return self._send(404, b"clip file not found")
        if sys.platform == "win32":
            subprocess.Popen(["explorer", f"/select,{path}"])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path.parent)])
        self._send(200, b"ok")

    def _json(self, code: int, payload: dict):
        self._send(code, json.dumps(payload).encode(), "application/json")

    def _tiktok_creator(self):
        if _tt["connecting"]:
            return self._json(200, {"connected": False, "connecting": True})
        client = _tiktok()
        if client is None:
            return self._json(200, {"connected": False})
        try:
            return self._json(200, {"connected": True, **client.creator_info()})
        except PublishError as exc:
            return self._json(200, {"connected": True, "error": str(exc)})

    def _tiktok_call(self, fn):
        client = _tiktok()
        try:
            return self._json(200, fn(client))
        except PublishError as exc:
            return self._json(400, {"error": str(exc)})

    def _serve_video(self, path: Path):
        size = path.stat().st_size
        start, end = 0, size - 1
        rng = re.match(r"bytes=(\d*)-(\d*)", self.headers.get("Range", ""))
        if rng:
            if rng.group(1):
                start = int(rng.group(1))
                end = int(rng.group(2)) if rng.group(2) else end
            elif rng.group(2):
                start = max(0, size - int(rng.group(2)))
            end = min(end, size - 1)
            if start > end:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.end_headers()
                return
        length = end - start + 1
        self.send_response(206 if rng else 200)
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        if rng:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        try:
            with path.open("rb") as f:
                f.seek(start)
                while length > 0:
                    chunk = f.read(min(1 << 20, length))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    length -= len(chunk)
        except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError):
            pass


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    url = f"http://127.0.0.1:{args.port}/"
    print(f"Clip Studio running at {url} (Ctrl+C to stop)")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
