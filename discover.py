"""One-off helper: list Zelda 40th product links on Nintendo Store locales."""
import asyncio, sys
from playwright.async_api import async_playwright

LOCALES = sys.argv[1:] or ["en-ie", "fr-fr"]


async def main():
    async with async_playwright() as pw:
        b = await pw.chromium.launch(channel="chrome", headless=True)
        p = await (await b.new_context(viewport={"width": 1366, "height": 900})).new_page()
        for loc in LOCALES:
            for q in ["zelda 40th", "zelda 40e"]:
                await p.goto(f"https://store.nintendo.com/{loc}/search?q={q}", wait_until="load")
                await p.wait_for_timeout(5000)
                links = await p.eval_on_selector_all(
                    "a[href]", "as => [...new Set(as.map(a => a.href))]")
                for h in links:
                    if "zelda" in h.lower() and ("40" in h):
                        print(loc, h, flush=True)


asyncio.run(main())
