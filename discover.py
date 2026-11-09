"""One-off helper: list ocarina product links on Nintendo Store locales."""
import asyncio, re, sys
from playwright.async_api import async_playwright


async def main():
    async with async_playwright() as pw:
        b = await pw.chromium.launch(channel="chrome", headless=True)
        p = await (await b.new_context(viewport={"width": 1366, "height": 900})).new_page()
        for loc in sys.argv[1:]:
            hits = {}
            for q in ["ocarina", "okarina", "ocarina of time"]:
                try:
                    await p.goto(f"https://store.nintendo.com/{loc}/search?q={q}", wait_until="load")
                    await p.wait_for_timeout(4000)
                    for _ in range(3):
                        await p.mouse.wheel(0, 3000); await p.wait_for_timeout(800)
                    links = await p.eval_on_selector_all(
                        "a[href]", "as => as.map(a => [a.href.split('?')[0], a.innerText.trim().replace(/\\s+/g, ' ').slice(0, 120)])")
                    for h, t in links:
                        if re.search(r"o[ck]arin", h, re.I) and re.search(r"\d{10,}$", h):
                            hits.setdefault(h, t)
                except Exception as e:
                    print(loc, "ERR", q, str(e)[:100], flush=True)
            for h, t in sorted(hits.items()):
                print(loc, "LINK", h, "|", t, flush=True)
            if not hits:
                print(loc, "NONE", flush=True)


asyncio.run(main())
