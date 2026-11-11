# Copies the three DFS Zen mods from their working folders (DFS/browser/dfs-calm, dfs-quiet, dfs-nav-panel) into this
# public repo, points every mod at its files here (raw.githubusercontent.com), and writes the import files Zen's
# Settings > Mods > Import reads. Run before each push: python3 -I sync.py
import json, pathlib, shutil, datetime

here = pathlib.Path(__file__).resolve().parent
browser = here.parent
OWNER_REPO = "Digital-Feng-Shui/dfs-zen-mods"
RAW = f"https://raw.githubusercontent.com/{OWNER_REPO}/main"
PAGE = f"https://github.com/{OWNER_REPO}/tree/main"
MODS = ["dfs-calm", "dfs-quiet", "dfs-nav-panel"]   # order = order in the all-in-one import file
FILES = ["chrome.css", "preferences.json", "readme.md"]

today = datetime.date.today().isoformat()
everything = {}
(here / "import").mkdir(exist_ok=True)
for folder in MODS:
    src = browser / folder
    theme_path = src / "theme.json"
    theme = json.loads(theme_path.read_text())
    theme.update(
        homepage=f"{PAGE}/{folder}",
        style=f"{RAW}/{folder}/chrome.css",
        readme=f"{RAW}/{folder}/readme.md",
        preferences=f"{RAW}/{folder}/preferences.json",
        author="Digital Feng Shui",
    )
    theme_path.write_text(json.dumps(theme, indent=2, ensure_ascii=False) + "\n")   # the working folder follows too
    out = here / folder
    out.mkdir(exist_ok=True)
    for f in FILES:
        if (src / f).exists():
            shutil.copy(src / f, out / f)
    entry = {k: theme[k] for k in ("id", "name", "description", "homepage", "style", "readme", "preferences", "author", "version") if k in theme}
    entry.update(image=theme.get("image", ""), tags=theme.get("tags", []), createdAt=theme.get("createdAt", today), updatedAt=theme.get("updatedAt", today))
    (here / "import" / f"{folder}.json").write_text(json.dumps({entry["id"]: entry}, indent=2, ensure_ascii=False) + "\n")
    everything[entry["id"]] = entry
    print(f"{theme['name']} {theme['version']}")
(here / "import" / "dfs-zen-mods.json").write_text(json.dumps(everything, indent=2, ensure_ascii=False) + "\n")
print("import files written")
