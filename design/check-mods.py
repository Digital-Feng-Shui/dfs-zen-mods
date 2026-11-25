"""Deep check of the three DFS Zen mods. Run after every Zen release.

  python3 -I design/check-mods.py static          files only: settings vs CSS, non-ASCII, braces, versions, repo vs working folders
  python3 -I design/check-mods.py live [label]    against the running demo Zen (design/demo-zen.py start [--app …]):
                                                  CSS parse errors, rules that match nothing, each promise of each mod,
                                                  every setting value, Ctrl Tab geometry; writes design/check-out/<label>/

Each check prints ok / FAIL / note. FAIL means a promise of the mod is broken; note means look at it by eye."""
import base64, json, re, sys, importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
WORK = REPO.parent  # DFS/browser, the working folders
MODS = ["dfs-calm", "dfs-quiet", "dfs-nav-panel", "dfs-minimal-menus"]


# ---------- static ----------

def strip_comments(css):
    return re.sub(r"/\*.*?\*/", lambda m: " " * len(m.group(0)), css, flags=re.S)


def static():
    out = []
    say = lambda kind, msg: out.append(f"{kind:5} {msg}")
    entries = json.loads((REPO / "import/dfs-zen-mods.json").read_text())
    for mod in MODS:
        css = (REPO / mod / "chrome.css").read_text()
        code = strip_comments(css)
        prefs = json.loads((REPO / mod / "preferences.json").read_text())
        declared = {p["property"] for p in prefs}
        used = set(re.findall(r'-moz-pref\("([^"]+)"', code))
        for p in sorted(declared - used): say("FAIL", f"{mod}: setting {p} is in preferences.json but no CSS reads it")
        for p in sorted(used - declared): say("FAIL", f"{mod}: CSS reads {p}, which preferences.json doesn't offer")
        for p in prefs:  # dropdown values the CSS never tests
            if p["type"] == "dropdown":
                for o in p["options"]:
                    if f'"{p["property"]}", "{o["value"]}"' not in code:
                        say("note", f"{mod}: {p['property']} option {o['value']!r} has no rule of its own (fine if it's the base look)")
        bad = [(i + 1, ch) for i, line in enumerate(code.splitlines()) for ch in line if ord(ch) > 127]
        for ln, ch in bad: say("FAIL", f"{mod}: non-ASCII {ch!r} outside a comment on line {ln} (Zen reads sheets without UTF-8)")
        if code.count("{") != code.count("}"): say("FAIL", f"{mod}: braces don't balance ({code.count('{')} open, {code.count('}')} close)")
        entry = next(e for e in entries.values() if e["homepage"].endswith("/" + mod))
        vs = {"import file": entry["version"]}
        if (WORK / mod / "theme.json").exists():  # Rim's working folders; a plain clone of the repo has none (Greptile, 23 Nov)
            for f in ("chrome.css", "preferences.json", "readme.md"):
                if (WORK / mod / f).read_bytes() != (REPO / mod / f).read_bytes():
                    say("FAIL", f"{mod}/{f}: the public copy differs from the working folder (run sync.py)")
            vs["theme.json"] = json.loads((WORK / mod / "theme.json").read_text())["version"]
        readme_v = re.search(r"v(\d+\.\d+\.\d+)", (REPO / mod / "readme.md").read_text())
        if readme_v: vs["readme"] = readme_v.group(1)  # only Nav Panel's readme names its version
        if len(set(vs.values())) != 1: say("FAIL", f"{mod}: versions disagree {vs}")
        if len(entry["name"]) >= 25: say("FAIL", f"{mod}: store name {len(entry['name'])} chars (must be under 25)")
        if len(entry["description"]) >= 100: say("FAIL", f"{mod}: store description {len(entry['description'])} chars (must be under 100)")
        transitions = re.findall(r"transition:\s*([^;]+);", code)
        for t in transitions:
            if re.search(r"background|box-shadow|\ball\b", t): say("note", f"{mod}: transition on {t.strip()} (repaints; see How to work here)")
        if not out or not any(l.split()[0] == "FAIL" and l.split()[1].startswith(mod) for l in out):
            say("ok", f"{mod}: settings, characters, braces, copies and versions ({vs['import file']})")
    return out


# ---------- live ----------

LIVE_JS = r"""
return (async () => {
  const R = { zen: Services.appinfo.version, checks: [] };
  const wait = ms => new Promise(r => setTimeout(r, ms));
  const ok = (name, pass, detail) => R.checks.push([pass === true ? "ok" : pass === false ? "FAIL" : "note", name, detail ?? ""]);
  const $ = s => document.querySelector(s);
  const cs = (el, pseudo) => el ? getComputedStyle(el, pseudo) : null;
  const r1 = n => Math.round(n * 10) / 10;
  const box = el => { if (!el) return null; const r = el.getBoundingClientRect(); return [r1(r.x), r1(r.y), r1(r.width), r1(r.height)]; };
  const prefs = Services.prefs;
  // The demo window sits behind other windows, where Zen refreshes styles late; force a refresh after each change.
  const wu = window.windowUtils, tick = () => { try { wu.advanceTimeAndRefresh(16); wu.restoreNormalRefresh(); } catch (e) {} };
  const setPref = async (p, v) => { typeof v === "boolean" ? prefs.setBoolPref(p, v) : prefs.setStringPref(p, v); tick(); await wait(400); tick(); };
  const resetAll = async () => { for (const [p, v] of Object.entries(DEFAULTS)) typeof v === "boolean" ? prefs.setBoolPref(p, v) : prefs.setStringPref(p, v); tick(); await wait(600); tick(); };
  const DEFAULTS = { "mod.dfs-calm.selected-tab": "edge", "mod.dfs-calm.ghost-tabs": "grey", "mod.dfs-calm.tab-text": "12",
    "mod.dfs-calm.space-heading": true, "mod.dfs-calm.faint-buttons": true, "mod.dfs-calm.hide-link-preview": true,
    "mod.dfs-calm.tidy-rows": true, "mod.dfs-quiet.hide-buttons": true, "mod.dfs-quiet.hide-urlbar": true,
    "mod.dfs-nav.grid": "9", "mod.dfs-nav.close-hint": true, "mod.dfs-menus.close-tab": false, "mod.dfs-menus.new-tab": false };
  await resetAll();

  // 1. Each mod's CSS parsed on its own: parse errors, and rules whose selector matches nothing right now.
  const sources = ARGS_SOURCES;
  R.parse = {};
  for (const [mod, text] of Object.entries(sources)) {
    const errors = [];
    const listener = { observe(m) { try { if (m instanceof Ci.nsIScriptError && /CSS/.test(m.category)) errors.push(`line ${m.lineNumber}: ${m.errorMessage}`); } catch (e) {} } };
    prefs.setBoolPref("layout.css.report_errors", true);
    Services.console.registerListener(listener);
    const sheet = new CSSStyleSheet();
    try { sheet.replaceSync(text); } catch (e) { errors.push("replaceSync: " + e); }
    await wait(300);
    Services.console.unregisterListener(listener);
    const unmatched = [], walk = (rules, parent) => {
      for (const rule of rules) {
        if (rule instanceof CSSStyleRule) {
          let sel = rule.selectorText;
          if (parent) sel = sel.includes("&") ? sel.replaceAll("&", `:is(${parent})`) : `:is(${parent}) ${sel}`;
          const testable = sel.replace(/::?(before|after|part\([^)]*\)|placeholder|marker)/g, "").replace(/:(hover|focus|focus-visible|active)/g, "");
          let n = -1; try { n = document.querySelectorAll(testable).length; } catch (e) { n = -2; }
          if (n === 0) unmatched.push(sel.slice(0, 140));
          if (n === -2) unmatched.push("UNPARSEABLE " + sel.slice(0, 140));
          if (rule.cssRules?.length) walk(rule.cssRules, sel);
        } else if (rule.cssRules) walk(rule.cssRules, parent);
      }
    };
    walk(sheet.cssRules, null);
    R.parse[mod] = { errors, unmatched };
    ok(`${mod}: CSS parses without errors`, errors.length === 0, errors.join(" | "));
  }

  // 2. DFS Calm
  const indicator = $("zen-workspace .zen-current-workspace-indicator-name") || $(".zen-current-workspace-indicator-name");
  const ind = cs(indicator);
  ok("Calm: space name is a small capitals heading", ind?.textTransform === "uppercase" && ind?.fontSize === "11px", `${ind?.textTransform} ${ind?.fontSize} ${ind?.fontWeight}`);
  ok("Calm: space name has no icon", cs($(".zen-current-workspace-indicator-icon"))?.display === "none");
  const normal = gBrowser.tabs.find(t => !t.pinned && !t.hasAttribute("pending") && !t.selected && !t.hasAttribute("zen-empty-tab"));
  ok("Calm: tab names 12px", cs(normal?.querySelector(".tab-label"))?.fontSize === "12px", cs(normal?.querySelector(".tab-label"))?.fontSize);
  const sel = gBrowser.selectedTab, selBg = cs(sel.querySelector(".tab-background"));
  ok("Calm: selected tab has the Edge ring", /inset/.test(selBg.boxShadow) && /1px/.test(selBg.boxShadow), selBg.boxShadow.slice(0, 80));
  const pending = gBrowser.tabs.find(t => t.hasAttribute("pending") && !t.hasAttribute("zen-essential"));
  ok("Calm: sleeping tabs fade, grey icons", pending ? cs(pending).opacity === "0.5" && /grayscale/.test(cs(pending).filter) : null, pending ? `${cs(pending).opacity} ${cs(pending).filter}` : "no sleeping tab to test");
  for (const id of ["zen-create-new-button", "zen-toggle-compact-mode"]) ok(`Calm: #${id} faint until hover`, cs($("#" + id))?.opacity === "0.3", cs($("#" + id))?.opacity);
  ok("Calm: extensions button shown (faint)", cs($("#zen-sidebar-top-buttons #unified-extensions-button"))?.display === "flex", cs($("#zen-sidebar-top-buttons #unified-extensions-button"))?.display);
  ok("Calm: link preview hidden", cs($("#statuspanel"))?.display === "none", cs($("#statuspanel"))?.display);
  const top = box($("#zen-sidebar-top-buttons")), ess = box($(".zen-essentials-container")), foot = box($("#zen-sidebar-foot-buttons"));
  const essIcon = box(gBrowser.tabs.find(t => t.hasAttribute("zen-essential"))?.querySelector(".tab-icon-image"));
  const lights = box($(".titlebar-buttonbox-container")) || box($(".titlebar-buttonbox"));
  R.layout = { top, ess, foot, essIcon, lights, lightsVisible: lights ? cs($(".titlebar-buttonbox-container") || $(".titlebar-buttonbox")).visibility : null };
  ok("Calm: top row 32px", top?.[3] === 32, JSON.stringify(top));
  ok("Calm: Essentials icons 18px", essIcon?.[2] === 18, JSON.stringify(essIcon));
  ok("Calm: bottom row 24px", foot?.[3] === 24, JSON.stringify(foot));
  const plus = box($("#zen-create-new-button"));
  ok("Calm: + in the bottom-right corner (also with one space)", plus && foot ? Math.abs((plus[0] + plus[2]) - (foot[0] + foot[2])) <= 3 : null, `+ ends at ${plus ? plus[0] + plus[2] : "?"}, row ends at ${foot ? foot[0] + foot[2] : "?"}`);
  ok("Calm: stoplights", null, `buttons at ${JSON.stringify(lights)}, ${R.layout.lightsVisible}; Essentials start ${ess ? r1(ess[1] - (lights ? lights[1] + lights[3] : 0)) : "?"}px under them (Calm aims at 12)`);

  // Calm settings sweep: each value changes what it should, then back.
  const look = () => { const b = cs(gBrowser.selectedTab.querySelector(".tab-background")); return b.backgroundImage + " " + b.boxShadow; };
  const looks = {};
  for (const v of ["edge", "glass", "clear", "none"]) { await setPref("mod.dfs-calm.selected-tab", v); looks[v] = look(); }
  ok("Calm setting: Selected tab, four different looks", new Set(Object.values(looks)).size === 4, Object.keys(looks).join("/"));
  const sizes = {};
  for (const v of ["11", "12", "13", "none"]) { await setPref("mod.dfs-calm.tab-text", v); sizes[v] = cs(normal?.querySelector(".tab-label"))?.fontSize; }
  ok("Calm setting: Tab text size", sizes["11"] === "11px" && sizes["12"] === "12px" && sizes["13"] === "13px" && !["11px", "12px", "13px"].includes(sizes.none), JSON.stringify(sizes));
  const ghosts = {};
  for (const v of ["grey", "faded", "none"]) { await setPref("mod.dfs-calm.ghost-tabs", v); ghosts[v] = pending ? cs(pending).opacity + " " + cs(pending).filter : "-"; }
  ok("Calm setting: Sleeping tabs", pending ? /grayscale/.test(ghosts.grey) && ghosts.faded.startsWith("0.5") && !/grayscale/.test(ghosts.faded) && ghosts.none.startsWith("1") : null, JSON.stringify(ghosts));
  await setPref("mod.dfs-calm.space-heading", false);
  ok("Calm setting: space name off gives Zen's own", cs(indicator)?.textTransform !== "uppercase", cs(indicator)?.textTransform);
  await setPref("mod.dfs-calm.faint-buttons", false);
  ok("Calm setting: faint buttons off", cs($("#zen-create-new-button"))?.opacity === "1", cs($("#zen-create-new-button"))?.opacity);
  await setPref("mod.dfs-calm.tidy-rows", false);
  ok("Calm setting: tidy rows off gives Zen's top row", box($("#zen-sidebar-top-buttons"))?.[3] !== 32, JSON.stringify(box($("#zen-sidebar-top-buttons"))));
  await setPref("mod.dfs-calm.hide-link-preview", false);
  ok("Calm setting: link preview back", cs($("#statuspanel"))?.display !== "none", cs($("#statuspanel"))?.display);
  await resetAll();

  // DFS Minimal Menus (needs Zen-drawn menus on a Mac; the check switches them on for itself)
  const nativeWas = [prefs.getBoolPref("widget.macos.native-context-menus", true), prefs.getBoolPref("widget.macos.native-anchored-menus", true)];
  prefs.setBoolPref("widget.macos.native-context-menus", false); prefs.setBoolPref("widget.macos.native-anchored-menus", false); tick();
  const itemName = c => { const a = cs(c, "::after").content; return /^".+"$/.test(a || "") ? a.slice(1, -1) : (c.getAttribute("label") || c.label || c.id); };
  const shownIn = m => [...m.children].filter(c => cs(c).display !== "none" && !c.hidden && c.getBoundingClientRect().height > 0).sort((a, b) => a.getBoundingClientRect().y - b.getBoundingClientRect().y).filter(c => c.localName !== "menuseparator").map(c => itemName(c).replace(/[.…]+$/, ""));
  const tabMenu = $("#tabContextMenu"), st = gBrowser.selectedTab.getBoundingClientRect();
  gBrowser.selectedTab.dispatchEvent(new MouseEvent("contextmenu", { bubbles: true, cancelable: true, button: 2, clientX: st.x + 20, clientY: st.y + 10, screenX: mozInnerScreenX + st.x + 20, screenY: mozInnerScreenY + st.y + 10 }));
  await wait(700); tick(); await wait(200); tick();
  const menuItems = shownIn(tabMenu); tabMenu.hidePopup(); await wait(300);
  ok("Minimal Menus: tab menu is Move to Folder, Change Name, Change Icon", JSON.stringify(menuItems) === JSON.stringify(["Move to Folder", "Change Name", "Change Icon"]), menuItems.join(", "));
  const spaceMenu = $("#zenWorkspaceMoreActions");
  spaceMenu.openPopup($(".zen-workspaces-actions"), "after_start", 0, 0, false, false, null); await wait(700); tick(); await wait(200); tick();
  const spaceItems = shownIn(spaceMenu); spaceMenu.hidePopup(); await wait(300);
  ok("Minimal Menus: space menu without the spaces list and unloading", !spaceItems.some(n => /Unload|Studio/.test(n)) && spaceItems.includes("Manage Spaces") && spaceItems.includes("Create Space"), spaceItems.join(", "));
  prefs.setBoolPref("widget.macos.native-context-menus", nativeWas[0]); prefs.setBoolPref("widget.macos.native-anchored-menus", nativeWas[1]);

  // 3. DFS Quiet
  for (const id of ["back-button", "forward-button", "stop-reload-button", "reload-button"]) {
    const el = $("#" + id);
    ok(`Quiet: #${id} hidden`, el ? cs(el).display === "none" || box(el)[2] === 0 : null, el ? cs(el).display : "not in this Zen");
  }
  const navbar = () => box($("#nav-bar"))?.[3];
  ok("Quiet: URL bar row closed", navbar() === 0, navbar());
  document.getElementById("cmd_newNavigatorTab").doCommand(); await wait(1200);
  ok("Quiet: Cmd T floats the bar, row stays closed", gURLBar.hasAttribute("zen-floating-urlbar") || gURLBar.hasAttribute("zen-newtab") ? navbar() === 0 : null,
     `row ${navbar()}, bar ${JSON.stringify(box(gURLBar))}, floating=${gURLBar.hasAttribute("zen-floating-urlbar")}, newtab=${gURLBar.hasAttribute("zen-newtab")}`);
  R.quietFloating = box(gURLBar);
  gURLBar.handleRevert(); gURLBar.view.close(); gURLBar.blur();
  document.getElementById("cmd_zenCloseUrlbar")?.doCommand?.(); await wait(600);
  document.getElementById("Browser:OpenLocation")?.doCommand(); await wait(1000);
  ok("Quiet: Cmd L opens the bar where you can see it", box(gURLBar)?.[2] > 100 && box(gURLBar)?.[3] > 20, `row ${navbar()}, bar ${JSON.stringify(box(gURLBar))}, floating=${gURLBar.hasAttribute("zen-floating-urlbar")}`);
  gURLBar.handleRevert(); gURLBar.view.close(); gURLBar.blur(); await wait(600);
  await setPref("mod.dfs-quiet.hide-urlbar", false);
  ok("Quiet setting: URL bar off gives the row back", navbar() > 0, navbar());
  await setPref("mod.dfs-quiet.hide-buttons", false);
  ok("Quiet setting: buttons back", $("#back-button") ? cs($("#back-button")).display !== "none" : null, $("#back-button") ? cs($("#back-button")).display : "-");
  await resetAll();

  // 4. DFS Nav Panel (needs 9 awake tabs; the demo has them)
  const panel = ctrlTab.panel;
  const openPanel = async () => { if (ctrlTab.isOpen) ctrlTab.close(); await wait(300); ctrlTab.open(); await wait(700); tick(); await wait(150); tick(); };
  const measure = () => {
    const cards = [...panel.querySelectorAll(".ctrlTab-preview")].filter(p => cs(p).display !== "none" && !p.hidden && p._tab);
    const xs = new Set(cards.map(c => Math.round(box(c)[0]))), card = box($("#ctrlTab-previews")), page = box($("#tabbrowser-tabpanels"));
    return { n: cards.length, cols: xs.size, card, page,
      dx: card && page ? r1(card[0] + card[2] / 2 - (page[0] + page[2] / 2)) : null,
      dy: card && page ? r1(card[1] + card[3] / 2 - (page[1] + page[3] / 2)) : null,
      inside: card && card[0] >= 0 && card[1] >= 0 && card[0] + card[2] <= innerWidth + 1 && card[1] + card[3] <= innerHeight + 1,
      names: cards.map(c => { const l = c.querySelector(".ctrlTab-label"), b = cs(l, "::before").content; return b && !/none|normal|-moz-label-content/.test(b) ? `${b} (for ${c.getAttribute("tooltiptext")?.slice(0, 30)})` : (l.value || l.textContent).slice(0, 30); }) };
  };
  await openPanel();
  const m9 = measure();
  R.nav = { grid9: m9 };
  ok("Nav: panel opens", ["open", "showing"].includes(panel.state), panel.state + (panel.state === "showing" ? " (still opening: the hidden demo window holds popups back)" : ""));
  ok("Nav: 3 x 3, nine cards", m9.n === 9 && m9.cols === 3, `${m9.n} cards, ${m9.cols} columns`);
  ok("Nav: card centred on the page (within 3px)", Math.abs(m9.dx) <= 3 && Math.abs(m9.dy) <= 3, `off by ${m9.dx}, ${m9.dy}`);
  ok("Nav: card fully on screen", m9.inside, JSON.stringify(m9.card));
  ok("Nav: short names", null, m9.names.join(" | "));
  for (const [g, n, cols] of [["12", 9, 4], ["6", 6, 3]]) {
    await setPref("mod.dfs-nav.grid", g); await openPanel(); const m = measure(); R.nav["grid" + g] = m;
    ok(`Nav setting: Grid ${g}`, m.n === n && m.cols === cols && Math.abs(m.dx) <= 3 && Math.abs(m.dy) <= 3, `${m.n} cards, ${m.cols} columns, off by ${m.dx}, ${m.dy} (maxPreviews ${prefs.getIntPref("browser.ctrlTab.maxPreviews")})`);
  }
  await setPref("mod.dfs-nav.grid", "9");
  // few tabs: the card must still centre (the 0.10.3 fix)
  const hidden = gBrowser.tabs.filter(t => !t.pinned && !t.selected && !t.hasAttribute("pending")).slice(2);
  for (const t of hidden) gBrowser.discardBrowser(t);
  await openPanel(); const mFew = measure(); R.nav.few = mFew;
  ok("Nav: few tabs, still centred", Math.abs(mFew.dx) <= 3 && Math.abs(mFew.dy) <= 3, `${mFew.n} cards, off by ${mFew.dx}, ${mFew.dy}`);
  ctrlTab.close(); await wait(300);
  for (const t of hidden) { gBrowser.selectedTab = t; await wait(250); }
  gBrowser.selectedTab = gBrowser.tabs.find(t => t.label.startsWith("Japanese")) || gBrowser.selectedTab;
  await wait(1500);
  return R;
})();
"""

SNAP_JS = r"""
return (async () => {
  const s = document.getElementById("navigator-toolbox").getBoundingClientRect();
  const w = Math.round(s.right + 8), h = window.innerHeight;
  const out = {};
  const snap = async (name, rect) => {
    const bmp = await window.browsingContext.currentWindowGlobal.drawSnapshot(new DOMRect(...rect), 2, "rgb(0,0,0)");
    const c = document.createElementNS("http://www.w3.org/1999/xhtml", "canvas"); c.width = bmp.width; c.height = bmp.height;
    c.getContext("2d").drawImage(bmp, 0, 0); out[name] = c.toDataURL("image/png");
  };
  await snap("sidebar", [0, 0, w, h]);
  document.getElementById("cmd_newNavigatorTab").doCommand(); await new Promise(r => setTimeout(r, 1200));
  await snap("quiet-floating", [0, 0, window.innerWidth, h]);
  gURLBar.handleRevert(); gURLBar.view.close(); gURLBar.blur();
  return out;
})();
"""


def live(label):
    spec = importlib.util.spec_from_file_location("dz", HERE / "demo-zen.py"); dz = importlib.util.module_from_spec(spec); spec.loader.exec_module(dz)
    sources = {mod: (REPO / mod / "chrome.css").read_text() for mod in MODS}
    r = dz.relay(LIVE_JS.replace("ARGS_SOURCES", json.dumps(sources)))
    out_dir = HERE / "check-out" / (label or r["zen"]); out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.json").write_text(json.dumps(r, indent=1))
    snaps = dz.relay(SNAP_JS)
    for name, url in snaps.items(): (out_dir / f"{name}.png").write_bytes(base64.b64decode(url.split(",", 1)[1]))
    lines = [f"Zen {r['zen']}"]
    lines += [f"{k:5} {name}{(': ' + str(d)) if d not in ('', None) else ''}" for k, name, d in r["checks"]]
    for mod, p in r["parse"].items():
        if p["unmatched"]: lines.append(f"note  {mod}: {len(p['unmatched'])} rules match nothing right now (state-dependent ones are expected):\n        " + "\n        ".join(p["unmatched"]))
    (out_dir / "report.txt").write_text("\n".join(lines) + "\n")
    return lines, out_dir


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "static"
    if cmd == "static": print("\n".join(static()))
    elif cmd == "live":
        lines, d = live(sys.argv[2] if len(sys.argv) > 2 else None); print("\n".join(lines)); print(f"\n(saved in {d})")
    else: sys.exit(__doc__)
