"""One-off helper: list Zelda 40th product links on Nintendo Store locales."""
import asyncio, re, sys
from playwright.async_api import async_playwright

CODES = re.compile(r"(P00211|10019437|10019439)$")


async def main():
    async with async_playwright() as pw:
        b = await pw.chromium.launch(channel="chrome", headless=True)
        p = await (await b.new_context(viewport={"width": 1366, "height": 900})).new_page()
        for loc in sys.argv[1:]:
            hits = set()
            for q in ["10019439", "10019437", "P00211", "zelda 40", "zelda 40th anniversary"]:
                try:
                    await p.goto(f"https://store.nintendo.com/{loc}/search?q={q}", wait_until="load")
                    await p.wait_for_timeout(4000)
                    for _ in range(3):
                        await p.mouse.wheel(0, 3000); await p.wait_for_timeout(800)
                    links = await p.eval_on_selector_all("a[href]", "as => as.map(a => a.href.split('?')[0])")
                    hits |= {h for h in links if CODES.search(h)}
                    if p.url.rstrip("/").endswith(("P00211", "10019437", "10019439")):
                        hits.add(p.url)
                except Exception as e:
                    print(loc, "ERR", q, str(e)[:100], flush=True)
            for h in sorted(hits):
                print(loc, "LINK", h, flush=True)


asyncio.run(main())
