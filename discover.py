# Temporary: find search-result links for the Zelda 40th items on stores the Mac can't reach.
import asyncio, sys
from playwright.async_api import async_playwright
import watch
LOCS = ["de-de", "nl-nl", "fr-be", "de-at", "fr-fr", "en-ie", "it-it", "es-es", "pt-pt"]
URLS = [f"https://store.nintendo.com/{l}/search?q=zelda" for l in LOCS] + [
    "https://www.retrospelbutiken.se/store/", "https://www.retrospelbutiken.se/store/sok.php?q=zelda",
    "https://www.retrospelbutiken.se/store/sok.php?sok=zelda", "https://www.retrospelbutiken.se/store/search.php?q=zelda"]
async def one(ctx, u):
    p = await ctx.new_page()
    try:
        await p.goto(u, wait_until="domcontentloaded", timeout=40000)
        await p.wait_for_timeout(6000)
        await watch.dismiss_cookies(p)
        for _ in range(3):
            await p.mouse.wheel(0, 3000); await p.wait_for_timeout(800)
        links = await p.eval_on_selector_all("a[href]", "es=>es.map(e=>e.href+' | '+e.innerText.replace(/\\s+/g,' ').slice(0,80))")
        forms = await p.eval_on_selector_all("form", "fs=>fs.map(f=>f.action+' '+f.method+' '+[...f.querySelectorAll('input')].map(i=>i.name+'='+i.type).join(','))")
        out = [f"== {u} -> {p.url} ({len(links)} links) forms={forms}"]
        out += ["    " + l[:240] for l in dict.fromkeys(links) if 'zelda' in l.lower() and ('40' in l or 'jubil' in l.lower() or 'anniv' in l.lower())]
        print("\n".join(out), flush=True)
    except Exception as e:
        print(f"== {u} ERR {str(e)[:150]}", flush=True)
    await p.close()
async def main():
    async with async_playwright() as pw:
        b = await pw.chromium.launch(channel="chrome", headless=True)
        ctx = await b.new_context(locale="en-GB", viewport={"width": 1366, "height": 900})
        sem = asyncio.Semaphore(5)
        async def g(u):
            async with sem: await one(ctx, u)
        await asyncio.gather(*(g(u) for u in URLS))
        await b.close()
asyncio.run(main())
