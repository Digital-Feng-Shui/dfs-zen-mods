// Two images per mod from its screenshot (design/shots/<mod>.png):
//   <mod>/image.png    600x400, the store image Zen's guidelines ask for (a 3:2 crop, no text: the store card shows name and description)
//   <mod>/preview.png  1600x900, design/frame.html with name and line, for the README
// Shots are full ⌘⇧3 screens of the demo Zen (design/demo-zen.py); CROP cuts out the part that shows the mod
// (source pixels; the menu bar is 66px at 2x, the demo window starts right under it).
// Usage: NODE_PATH=<folder with playwright-core> node design/make-previews.cjs   (needs Playwright's Chromium)
const path = require("path"), fs = require("fs");
const { chromium } = require("playwright-core");
const root = path.resolve(__dirname, "..");
const MODS = {
  "dfs-calm": { name: "DFS Calm", line: "A calmer sidebar for everyone: a clear selected tab, sleeping tabs that fade, one text size, tidy margins." },
  "dfs-quiet": { name: "DFS Quiet", line: "For keyboard people: no buttons a shortcut covers, and the URL bar only when you call it with ⌘T or ⌘L." },
  "dfs-nav-panel": { name: "DFS Nav Panel", line: "A calmer Ctrl Tab: your recent tabs as big previews on one dark card, centred on the page." },
};
const CROP = {
  "dfs-calm": { x: 0, y: 66, w: 950, h: 1264 },        // the sidebar, from the window buttons to the last tab
  "dfs-quiet": { x: 0, y: 66, w: 2350, h: 1300 },      // top left of the window: no URL bar row, the bar floats on ⌘T
  "dfs-nav-panel": { x: 600, y: 130, w: 2270, h: 1670 }, // the card with a little page around it (a window shot without the menu bar)
};
// Store crops: 3:2, edge to edge, so the mod's part fills the small card.
const STORE = {
  "dfs-calm": { x: 0, y: 66, w: 1755, h: 1170 },       // window buttons to the selected tab, with the start of the page
  "dfs-quiet": { x: 0, y: 66, w: 2350, h: 1567 },      // no URL bar row, the floating bar
  "dfs-nav-panel": { x: 480, y: 130, w: 2532, h: 1688 }, // the card
};
const { execFileSync } = require("child_process");
(async () => {
  const b = await chromium.launch({ headless: true });
  for (const [mod, m] of Object.entries(MODS)) {
    const shot = path.join(__dirname, "shots", `${mod}.png`);
    if (!fs.existsSync(shot)) { console.log(`skip ${mod}: no design/shots/${mod}.png yet`); continue; }
    const p = await b.newPage({ viewport: { width: 1600, height: 900 }, deviceScaleFactor: 1 });
    await p.goto("file://" + path.join(__dirname, "frame.html"));
    await p.evaluate(async ({ m, src, crop }) => {
      document.getElementById("name").textContent = m.name; document.getElementById("line").textContent = m.line;
      const img = new Image(); img.src = src; await img.decode();
      const c = crop || { x: 0, y: 0, w: img.naturalWidth, h: img.naturalHeight };
      const cv = document.getElementById("shot"); cv.width = c.w; cv.height = c.h;
      cv.getContext("2d").drawImage(img, c.x, c.y, c.w, c.h, 0, 0, c.w, c.h);
      const box = cv.parentElement.getBoundingClientRect(), maxW = box.width - 520 - 56 - 144, k = Math.min(maxW / c.w, 780 / c.h);
      cv.style.width = Math.round(c.w * k) + "px"; cv.style.height = Math.round(c.h * k) + "px";
    }, { m, src: "file://" + shot, crop: CROP[mod] });
    await p.waitForTimeout(400);
    await p.screenshot({ path: path.join(root, mod, "preview.png") });
    await p.close(); console.log(`${mod}/preview.png`);
    // store image: crop at full size, then let sips scale it down to 600x400
    const c = STORE[mod], tmp = path.join(require("os").tmpdir(), `dfs-store-${mod}.png`);
    const q = await b.newPage({ viewport: { width: c.w, height: c.h }, deviceScaleFactor: 1 });
    await q.goto("file://" + path.join(__dirname, "frame.html"));  // a file:// page, so it may load the file:// shot
    await q.evaluate(async ({ src, c }) => {
      document.body.outerHTML = '<body style="margin:0;padding:0;display:block;width:auto;height:auto"><canvas id="c"></canvas></body>';
      const img = new Image(); img.src = src; await img.decode();
      const cv = document.getElementById("c"); cv.width = c.w; cv.height = c.h; cv.style.display = "block";
      cv.getContext("2d").drawImage(img, c.x, c.y, c.w, c.h, 0, 0, c.w, c.h);
    }, { src: "file://" + shot, c });
    await q.screenshot({ path: tmp, clip: { x: 0, y: 0, width: c.w, height: c.h } });
    await q.close();
    execFileSync("sips", ["-z", "400", "600", tmp, "--out", path.join(root, mod, "image.png")], { stdio: "ignore" });
    console.log(`${mod}/image.png`);
  }
  await b.close();
})().catch(e => { console.error(e.message); process.exit(1); });
