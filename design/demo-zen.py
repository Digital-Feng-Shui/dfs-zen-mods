"""A clean demo Zen for store screenshots: its own profile (never your own), only the three DFS mods, neutral tabs.

  python3 -I design/demo-zen.py start      fresh profile in ~/Library/Caches/dfs-zen-demo, launch, install mods, open tabs,
                                           then keep running (in the background) holding the one Marionette session
  python3 -I design/demo-zen.py start --bare   the same without the mods, to test Zen's Import
  python3 -I design/demo-zen.py js '<js>'  run chrome-scope JS in the demo window (Marionette on port 2829)
  python3 -I design/demo-zen.py ctrltab    bring the demo window forward and open Ctrl Tab (stays open, no key held)
  python3 -I design/demo-zen.py bounds     the demo window's position and size on screen (for cropping a ⌘⇧3 shot)
  python3 -I design/demo-zen.py quit       close the demo Zen

It runs next to your own Zen (-no-remote), with a second Zen icon in the Dock while it is open.
Why a held session: once Zen has essentials and pinned tabs, a new Marionette session fails (registerWindow meets a
tab without a browser), so `start` keeps the first session and the other commands talk to it on port 2830."""
import json, os, shutil, socket, subprocess, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
PROFILE = Path.home() / "Library/Caches/dfs-zen-demo"
PORT = 2829
RELAY = 2830  # the held session listens here
MODS = ["dfs-calm", "dfs-quiet", "dfs-nav-panel"]

PREFS = {
    "marionette.port": PORT,
    "zen.welcome-screen.seen": True,
    "browser.shell.checkDefaultBrowser": False,
    "browser.startup.page": 0,
    "browser.startup.homepage_override.mstone": "ignore",
    "startup.homepage_welcome_url": "",
    "browser.aboutwelcome.enabled": False,
    "datareporting.policy.dataSubmissionPolicyBypassNotification": True,
    "datareporting.policy.dataSubmissionEnabled": False,
    "toolkit.telemetry.reportingpolicy.firstRun": False,
    "app.update.disabledForTesting": True,
    "browser.tabs.warnOnClose": False,
    "browser.warnOnQuit": False,
    "browser.sessionstore.resume_from_crash": False,
    "browser.translations.automaticallyPopup": False,
    "signon.rememberSignons": False,
    "browser.ctrlTab.sortByRecentlyUsed": True,
    "browser.ctrlTab.maxPreviews": 9,  # Zen's default is 7; 9 fills the Nav Panel's 3 x 3
    "browser.engagement.ctrlTab.has-used": True,
    "browser.theme.toolbar-theme": 0,
    "zen.view.window.scheme": 0,
    # the mods at their defaults (what someone gets after installing)
    "mod.dfs-calm.selected-tab": "edge",
    "mod.dfs-calm.ghost-tabs": "grey",
    "mod.dfs-calm.tab-text": "12",
    "mod.dfs-calm.space-heading": True,
    "mod.dfs-calm.faint-buttons": True,
    "mod.dfs-calm.hide-link-preview": True,
    "mod.dfs-calm.tidy-rows": True,
    "mod.dfs-quiet.hide-buttons": True,
    "mod.dfs-quiet.hide-urlbar": True,
    "mod.dfs-nav.grid": "9",
    "mod.dfs-nav.close-hint": True,
}

# Neutral tabs: no sign-ins, no cookie walls. Essentials first, then pinned, then normal tabs.
ESSENTIALS = ["https://en.wikipedia.org/wiki/Main_Page", "https://github.com/Digital-Feng-Shui/dfs-zen-mods", "https://zen-browser.app/"]
PINNED = ["https://digital-fengshui.com/", "https://addons.mozilla.org/firefox/addon/reframe/", "https://addons.mozilla.org/firefox/addon/backflip/"]
TABS = [
    "https://en.wikipedia.org/wiki/Japanese_rock_garden",
    "https://en.wikipedia.org/wiki/Ry%C5%8Dan-ji",
    "https://en.wikipedia.org/wiki/Feng_shui",
    "https://en.wikipedia.org/wiki/Bonsai",
    "https://developer.mozilla.org/en-US/docs/Web/CSS",
    "https://en.wikipedia.org/wiki/Wabi-sabi",
    "https://en.wikipedia.org/wiki/Ikebana",
]


class M:
    """Tiny Marionette client (same as dfs-quiet/zen_inspect.py), chrome scope."""
    def __init__(self, port=PORT, timeout=60):
        self.s = socket.create_connection(("127.0.0.1", port), timeout=timeout); self.i = 0; self._recv()
        self.cmd("WebDriver:NewSession", {"capabilities": {}}); self.cmd("Marionette:SetContext", {"value": "chrome"})
        self.cmd("WebDriver:SetTimeouts", {"script": 60000})
    def _recv(self):
        buf = b""
        while b":" not in buf: buf += self.s.recv(1)
        n = int(buf[:-1]); data = b""
        while len(data) < n: data += self.s.recv(n - len(data))
        return json.loads(data)
    def cmd(self, name, params=None):
        self.i += 1; msg = json.dumps([0, self.i, name, params or {}]).encode()
        self.s.sendall(str(len(msg)).encode() + b":" + msg)
        while True:
            r = self._recv()
            if r[0] == 1 and r[1] == self.i:
                if r[2]: raise RuntimeError(r[2])
                return r[3]
    def js(self, script):
        if "return" not in script: script = "return (" + script + ")"
        r = self.cmd("WebDriver:ExecuteScript", {"script": script, "args": []})
        return r.get("value") if isinstance(r, dict) else r


def fresh_profile(bare=False):
    if PROFILE.exists(): shutil.rmtree(PROFILE)
    themes = PROFILE / "chrome/zen-themes"; themes.mkdir(parents=True)
    entries = {} if bare else json.loads((REPO / "import/dfs-zen-mods.json").read_text())
    for mod_id, entry in entries.items():
        mod = entry["homepage"].rsplit("/", 1)[1]  # .../tree/main/dfs-calm
        dest = themes / mod_id; dest.mkdir()
        for f in ("chrome.css", "preferences.json", "readme.md"): shutil.copy(REPO / mod / f, dest / f)
        entry["enabled"] = True
    (PROFILE / "zen-themes.json").write_text(json.dumps(entries, indent=2))
    (PROFILE / "user.js").write_text("".join(f'user_pref("{k}", {json.dumps(v)});\n' for k, v in PREFS.items()))


def wait_for_marionette(seconds=40):
    end = time.time() + seconds
    while time.time() < end:
        try:
            m = M(timeout=5); m.s.settimeout(180); return m  # short wait to connect, long wait for scripts
        except OSError: time.sleep(0.5)
    sys.exit("The demo Zen did not open Marionette on port %d." % PORT)


SETUP = r"""
return (async () => {
  const P = Services.scriptSecurityManager.getSystemPrincipal();
  await gZenMods.triggerModsUpdate();
  const open = (u) => gBrowser.addTab(u, { triggeringPrincipal: P, inBackground: true });
  const ess = arguments[0].map(open), pin = arguments[1].map(open), tabs = arguments[2].map(open);
  for (const t of ess) gZenPinnedTabManager.addToEssentials(t);
  for (const t of pin) gBrowser.pinTab(t);
  // the empty start tab goes, a normal tab gets selected
  for (const t of [...gBrowser.tabs]) if (t.linkedBrowser.currentURI.spec == "about:blank" && !ess.includes(t) && !pin.includes(t) && !tabs.includes(t)) gBrowser.removeTab(t);
  // the space gets a name, the window fills the screen
  const ws = gZenWorkspaces.getWorkspaces()[0]; ws.name = "Studio"; await gZenWorkspaces.saveWorkspace(ws);
  window.moveTo(screen.availLeft, screen.availTop); window.resizeTo(screen.availWidth, screen.availHeight);
  await new Promise(r => setTimeout(r, 6000));  // pages load, so Ctrl Tab has previews
  // a few tabs go to sleep (Calm fades them); sleeping tabs are left out of Ctrl Tab, nine stay awake
  for (const t of [tabs[3], tabs[4], tabs[5], pin[2]]) gBrowser.discardBrowser(t);
  gBrowser.selectedTab = tabs[0];
  return { tabs: gBrowser.tabs.length };
})();
"""


def start(bare=False):
    fresh_profile(bare)
    subprocess.run(["open", "-n", "-a", "Zen", "--env", "MOZ_REMOTE_ALLOW_SYSTEM_ACCESS=1", "--args",
                    "-profile", str(PROFILE), "-no-remote", "--marionette"], check=True)
    m = wait_for_marionette()
    time.sleep(3)  # let the first window settle
    script = SETUP.replace("arguments[0]", json.dumps(ESSENTIALS)).replace("arguments[1]", json.dumps(PINNED)).replace("arguments[2]", json.dumps(TABS))
    print(m.js(script), flush=True)
    serve(m)


def serve(m):
    srv = socket.socket(); srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", RELAY)); srv.listen(1)
    print("holding the session on port %d" % RELAY, flush=True)
    while True:
        c, _ = srv.accept()
        with c:
            data = b""
            while not data.endswith(b"\n"):
                chunk = c.recv(65536)
                if not chunk: break
                data += chunk
            try: out = {"ok": m.js(json.loads(data)["js"])}
            except Exception as e:
                if isinstance(e, OSError): return
                out = {"error": str(e)}
            c.sendall(json.dumps(out).encode() + b"\n")
            if json.loads(data).get("quit"): return


def relay(script, quit=False):
    c = socket.create_connection(("127.0.0.1", RELAY), timeout=90)
    c.sendall(json.dumps({"js": script, "quit": quit}).encode() + b"\n")
    data = b""
    while not data.endswith(b"\n"):
        chunk = c.recv(65536)
        if not chunk: break
        data += chunk
    out = json.loads(data or b"{}")
    if "error" in out: sys.exit(out["error"])
    return out.get("ok")


CTRLTAB = r"""
window.focus();
if (ctrlTab.isOpen) ctrlTab.close();
ctrlTab.open();
return new Promise(r => setTimeout(() => r({ open: ctrlTab.isOpen, panel: ctrlTab.panel.state }), 700));
"""

BOUNDS = "return { x: window.screenX, y: window.screenY, w: window.outerWidth, h: window.outerHeight, scale: window.devicePixelRatio, screen: [screen.width, screen.height] };"


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "start"
    if cmd == "start": start(bare="--bare" in sys.argv)  # --bare: no mods installed (to test an import)
    elif cmd == "js": print(json.dumps(relay(sys.argv[2]), indent=1))
    elif cmd == "ctrltab": print(relay(CTRLTAB))
    elif cmd == "bounds": print(json.dumps(relay(BOUNDS)))
    elif cmd == "quit":
        try: relay("Services.startup.quit(Ci.nsIAppStartup.eAttemptQuit); return 1;", quit=True)
        except Exception: pass
    else: sys.exit(__doc__)


if __name__ == "__main__":
    main()
