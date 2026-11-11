// Installs or updates the DFS Zen Mods. Paste into Zen's Browser Console (see README).
await (async () => {
  const list = "https://raw.githubusercontent.com/Digital-Feng-Shui/dfs-zen-mods/main/import/dfs-zen-mods.json";
  const ours = await (await fetch(list, { cache: "no-store" })).json();
  const mods = await gZenMods.getMods();
  for (const [id, mod] of Object.entries(ours)) {
    if (mods[id]) await gZenMods.removeMod(id, false); // an older copy goes, so Zen fetches the latest
    mods[id] = { ...mod, enabled: mods[id]?.enabled ?? true };
  }
  await gZenMods.updateMods(mods); // Zen downloads each mod from its GitHub links and turns it on
  return "Installed: " + Object.values(ours).map((m) => `${m.name} ${m.version}`).join(", ");
})();
