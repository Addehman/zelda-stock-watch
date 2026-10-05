"""One-off helper: list Zelda 40th product links on Nintendo Store locales."""
import asyncio, re, sys
from playwright.async_api import async_playwright

CODES = re.compile(r"(P00211|10019437|10019439)$")


async def main():
    async with async_playwright() as pw:
        b = await pw.chromium.launch(channel="chrome", headless=True)
        p = await (await b.new_context(viewport={"width": 1366, "height": 900})).new_page()
        for loc in sys.argv[1:]:
            try:
                await p.goto(f"https://store.nintendo.com/{loc}/search?q=zelda", wait_until="load")
                await p.wait_for_timeout(5000)
                links = await p.eval_on_selector_all("a[href]", "as => [...new Set(as.map(a => a.href.split('?')[0]))]")
                hits = [h for h in links if CODES.search(h)]
                print(loc, "FINAL", p.url, flush=True)
                for h in hits:
                    print(loc, "LINK", h, flush=True)
            except Exception as e:
                print(loc, "ERR", str(e)[:100], flush=True)


asyncio.run(main())
