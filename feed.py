"""Watch the Makkah live camera and publish the latest Kaaba view with a measured crowd level.

Runs in GitHub Actions (see .github/workflows/feed.yml). YouTube blocks video downloads from
cloud servers, but not the live thumbnail, which YouTube refreshes every few minutes. So every
CHECK seconds we fetch the thumbnail; when it's a new picture we look at it, and if it shows the
Kaaba we measure the crowd and publish to the `feed` branch:

  kaaba.jpg    the latest Kaaba view
  latest.json  {"at": <unix s when seen>, "crowd": 0-1, "level": ..., "camera_at": <last camera check>}
  log.json     every reading of the last 14 days: [[unix s, crowd], ...] (the app plots today's)
"""
import collections, hashlib, io, json, os, subprocess, sys, time, urllib.request
from PIL import Image
import analyze as A

VIDEO = os.environ.get("LIVE_VIDEO", "IsJTAdC3-Jw")   # Saudi Quran TV, Makkah Live
CHANNEL = "UCos52azQNBgW63_9uDJoPDA"
CHECK = 60                                             # seconds between thumbnail checks
RUN_FOR = int(os.environ.get("RUN_FOR", 3300))        # one job = 55 min; the workflow starts one hourly
OUT = sys.argv[1] if len(sys.argv) > 1 else "out"     # checkout of the feed branch
KEEP = 14 * 86400
# Only for the family's trip (24 Nov - 6 Dec 2026): after this Makkah date the job does nothing.
STOP_AFTER = os.environ.get("STOP_AFTER", "2026-12-07")

def fetch(url, tries=3):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=20) as r:
                return r.read()
        except Exception as e:
            err = e; time.sleep(3)
    raise err

def live_video():
    # The channel's /live page names the current stream; fall back to the known one.
    try:
        html = fetch(f"https://www.youtube.com/channel/{CHANNEL}/live").decode("utf8", "ignore")
        i = html.find('"videoId":"')
        if i > 0 and '"isLive":true' in html:
            return html[i + 11:i + 22]
    except Exception:
        pass
    return VIDEO

def load_json(name, default):
    try:
        with open(os.path.join(OUT, name)) as f:
            return json.load(f)
    except Exception:
        return default

def write_json(name, obj):
    with open(os.path.join(OUT, name), "w") as f:
        json.dump(obj, f, separators=(",", ":"))

def publish(msg):
    g = lambda *a: subprocess.run(["git", "-C", OUT, *a], check=True, capture_output=True)
    g("add", "-A")
    # One commit only (amend + force push), so the branch never grows with old pictures.
    g("commit", "--amend", "-m", msg, "--allow-empty")
    g("push", "-f", "origin", "HEAD:feed")

def main():
    if time.strftime("%Y-%m-%d", time.gmtime(time.time() + 3 * 3600)) > STOP_AFTER:
        print("past", STOP_AFTER, "- feed is off"); return
    start, vid, n = time.time(), live_video(), 0
    seen = collections.deque(maxlen=12)   # the hosts update at different times, so remember recent pictures
    told = 0                              # when we last published a plain "camera checked"
    print("video", vid, flush=True)
    latest = load_json("latest.json", {})
    log = load_json("log.json", [])
    while time.time() - start < RUN_FOR:
        host = ["i", "i1", "i2", "i3", "i4"][n % 5]; n += 1
        try:
            raw = fetch(f"https://{host}.ytimg.com/vi/{vid}/maxresdefault_live.jpg")
        except Exception as e:
            print("fetch failed", e, flush=True); vid = live_video(); time.sleep(CHECK); continue
        h = hashlib.md5(raw).hexdigest()
        now = int(time.time())
        if h not in seen:
            seen.append(h)
            im = Image.open(io.BytesIO(raw)).convert("RGB")
            if im.width <= 120:                      # YouTube's "no thumbnail" placeholder
                vid = live_video(); time.sleep(CHECK); continue
            L, S = A.load_image(im)
            k = A.kaaba(L, S)
            c = A.crowd(L, S, k["box"]) if k else None
            print(time.strftime("%H:%M:%S"), "kaaba" if k else "other angle", c, flush=True)
            if k and c is not None:
                im.resize((960, 540), Image.LANCZOS).save(os.path.join(OUT, "kaaba.jpg"), quality=78, optimize=True)
                latest = {"at": now, "crowd": c, "level": A.level(c), "video": vid}
                log = [r for r in log if r[0] > now - KEEP] + [[now, c]]
                write_json("log.json", log)
            latest["camera_at"] = now
            write_json("latest.json", latest)
            if not k and now - told < 600:
                time.sleep(CHECK); continue
            told = now
            try:
                publish(f"Kaaba view {A.level(c)} {c}" if k else "Camera checked")
            except subprocess.CalledProcessError as e:
                print("publish failed", e.stderr.decode()[-300:], flush=True)
        time.sleep(CHECK)

if __name__ == "__main__":
    main()
