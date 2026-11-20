"""Post due items from tg/queue/*.json to the Telegram channel via the Bot API.
item: {"publish_at": ISO8601, "type": "message|photo|video|poll", "text": str,
       "photo": url, "video": url, "question": str, "options": [str], "parse_mode": "HTML"|None,
       "disable_preview": bool}
Posted items move to tg/sent/, failures are written to tg/errors/ (the item stays queued, retried next run)."""
import datetime as dt, glob, json, os, sys, urllib.parse, urllib.request
TOKEN, CHAT = os.environ.get("TG_BOT_TOKEN", ""), os.environ.get("TG_CHAT", "@neforyou_tw")
now = dt.datetime.now(dt.timezone.utc)
os.makedirs("tg/sent", exist_ok=True); os.makedirs("tg/errors", exist_ok=True)
LOG = []
def log(*a):
    LOG.append(" ".join(str(x) for x in a)); print(*a)
ACTED = []
def save_log():
    if LOG and ACTED:
        open("tg/last_run.log", "w", encoding="utf-8").write("\n".join(LOG) + "\n")
import atexit; atexit.register(save_log)
queued = sorted(glob.glob("tg/queue/*.json"))
if queued:
    log(now.isoformat(), "token present:", bool(TOKEN), "chat:", CHAT, "queued:", [os.path.basename(q) for q in queued])
if not TOKEN:
    open("tg/errors/no_token.txt", "w").write(f"{now.isoformat()} TG_BOT_TOKEN secret is missing\n"); sys.exit(0)
elif os.path.exists("tg/errors/no_token.txt"):
    os.remove("tg/errors/no_token.txt")
def api(method, payload):
    data = urllib.parse.urlencode({k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v)
                                   for k, v in payload.items() if v is not None}).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{TOKEN}/{method}", data=data)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        return json.loads(e.read().decode() or "{}") or {"ok": False, "description": str(e)}
for path in sorted(glob.glob("tg/queue/*.json")):
    it = json.load(open(path, encoding="utf-8"))
    when = dt.datetime.fromisoformat(it.get("publish_at", now.isoformat()))
    if when.tzinfo is None:
        when = when.replace(tzinfo=dt.timezone(dt.timedelta(hours=3)))
    if when > now + dt.timedelta(seconds=60):
        log("not due yet", os.path.basename(path), when.isoformat())
        continue
    ACTED.append(path)
    t, pm = it.get("type", "message"), it.get("parse_mode")
    if t == "photo":
        res = api("sendPhoto", {"chat_id": CHAT, "photo": it["photo"], "caption": it.get("text"), "parse_mode": pm})
    elif t == "video":
        res = api("sendVideo", {"chat_id": CHAT, "video": it["video"], "caption": it.get("text"), "parse_mode": pm,
                                "supports_streaming": "true"})
    elif t == "poll":
        res = api("sendPoll", {"chat_id": CHAT, "question": it["question"], "options": it["options"],
                               "is_anonymous": "true"})
    else:
        res = api("sendMessage", {"chat_id": CHAT, "text": it["text"], "parse_mode": pm,
                                  "disable_web_page_preview": "true" if it.get("disable_preview") else None})
    name = os.path.basename(path)
    if res.get("ok"):
        it["result"] = {"message_id": res["result"]["message_id"], "posted_at": now.isoformat()}
        json.dump(it, open(f"tg/sent/{name}", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        os.remove(path)
        err = f"tg/errors/{name}.txt"
        if os.path.exists(err): os.remove(err)
        log("posted", name, res["result"]["message_id"])
    else:
        open(f"tg/errors/{name}.txt", "w").write(f"{now.isoformat()} {res.get('description')}\n")
        log("FAILED", name, res.get("description"))
