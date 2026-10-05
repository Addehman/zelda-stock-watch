#!/usr/bin/env python3
"""
Zelda 40th Anniversary Switch 2 stock watcher.

- Polls every product page in config.json using your real Google Chrome
  (dedicated profile in ./chrome-profile, so you can log in to stores once).
- Decides availability from schema.org JSON-LD + a visible, enabled
  "add to cart" button + multilingual "sold out" phrases.
- On a hit: push notification via ntfy.sh (tap opens the page), opens the
  page in a visible Chrome window, tries to click "add to cart", then opens
  the cart. YOU finish checkout and payment yourself.

Usage:
  .venv/bin/python watch.py            # run the monitor
  .venv/bin/python watch.py --login    # open the profile to log in to stores
  .venv/bin/python watch.py --once     # single pass, print status table
  .venv/bin/python watch.py --test-notify
"""
import argparse, asyncio, json, os, platform, random, re, sys, time, urllib.request
from datetime import datetime
from pathlib import Path

from playwright.async_api import async_playwright, TimeoutError as PWTimeout

ROOT = Path(__file__).parent
CONFIG = json.loads((ROOT / "config.json").read_text())
PROFILE = ROOT / "chrome-profile"
STATE_FILE = ROOT / "state.json"
TOPIC = os.environ.get("NTFY_TOPIC") or ((ROOT / ".topic").read_text().strip()
                                         if (ROOT / ".topic").exists() else "")

ADD_TO_CART = re.compile(
    r"(add to (cart|basket|bag)|buy now|pre-?order|"          # en
    r"in den warenkorb|jetzt kaufen|vorbestellen|"            # de
    r"lägg (i|till i) (kundvagn|varukorg)|^köp( nu)?$|förbeställ|förköp|"      # sv
    r"læg i (kurv|indkøbskurv)|forudbestil|"                  # da
    r"in (de )?winkelwagen|bestel nu|"                        # nl
    r"lisää ostoskoriin|"                                     # fi
    r"ajouter au panier|précommander|"                        # fr
    r"añadir al carrito|aggiungi al carrello)", re.I)

SOLD_OUT = re.compile(
    r"(out of stock|sold out|currently unavailable|not available|notify me|"
    r"ausverkauft|nicht (verfügbar|lieferbar)|derzeit nicht|benachrichtig|"
    r"slutsåld|tillfälligt slut|ej i lager|inte i lager|inte tillgänglig|fullbokad|bevaka|"
    r"udsolgt|ikke på lager|"
    r"uitverkocht|niet (op voorraad|leverbaar)|"
    r"loppuunmyyty|"
    r"épuisé|rupture de stock|agotado|esaurito)", re.I)

BLOCKED = re.compile(r"(captcha|are you a robot|access denied|robot check|"
                     r"verify you are human|unusual traffic|pardon our interruption|just a moment|checking your browser)", re.I)

COOKIE_REJECT = re.compile(
    r"^(reject all|decline|only necessary|necessary only|use necessary cookies only|"
    r"alle ablehnen|ablehnen|nur notwendige|"
    r"avvisa alla|neka|endast nödvändiga|"
    r"afvis alle|kun nødvendige|alles weigeren|weigeren|hylkää kaikki)$", re.I)

AVAILABLE_LD = ("instock", "preorder", "presale", "limitedavailability", "onlineonly")


def log(msg):
    print(f"{datetime.now():%H:%M:%S} {msg}", flush=True)


def notify(title, body, url=None, priority="urgent", tags="rotating_light,video_game"):
    topic = TOPIC
    if not topic:
        log("no NTFY_TOPIC set - skipping push"); return
    req = urllib.request.Request(
        f"https://ntfy.sh/{topic}", data=body.encode(), method="POST",
        headers={"Title": title.encode("utf-8").decode("latin-1", "ignore"),
                 "Priority": priority, "Tags": tags,
                 **({"Click": url, "Actions": f"view, Open store, {url}"} if url else {})})
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        log(f"ntfy failed: {e}")
    if platform.system() != "Darwin":
        return
    # local fallback: macOS banner + sound
    import subprocess
    subprocess.run(["osascript", "-e",
                    f'display notification {json.dumps(body)} with title {json.dumps(title)} sound name "Glass"'],
                   capture_output=True)


async def dismiss_cookies(page):
    try:
        for btn in await page.get_by_role("button").all():
            txt = (await btn.inner_text(timeout=500)).strip()
            if COOKIE_REJECT.match(txt) and await btn.is_visible():
                await btn.click(timeout=2000)
                return
    except Exception:
        pass


async def ld_availability(page):
    """Return list of schema.org availability values found in JSON-LD."""
    vals = []
    for raw in await page.locator('script[type="application/ld+json"]').all_inner_texts():
        for m in re.finditer(r'"availability"\s*:\s*"([^"]+)"', raw):
            vals.append(m.group(1).rsplit("/", 1)[-1].lower())
    return vals


async def find_buy_button(page, item):
    if item.get("buy_selector"):
        loc = page.locator(item["buy_selector"]).first
        if await loc.count() and await loc.is_visible() and await loc.is_enabled():
            return loc
        return None
    for role in ("button", "link"):
        loc = page.get_by_role(role, name=ADD_TO_CART)
        for i in range(min(await loc.count(), 6)):
            b = loc.nth(i)
            try:
                if await b.is_visible() and await b.is_enabled() \
                        and await b.get_attribute("aria-disabled") != "true":
                    return b
            except Exception:
                pass
    return None


def parse_price(text):
    """'519,99 €' / '7 290:-' / '£434.99' / '1.299,00' -> float"""
    m = re.search(r"\d[\d\s.,\u00a0]*", text or "")
    if not m:
        return None
    n = re.sub(r"[\s\u00a0]", "", m.group()).rstrip(".,")
    dec = re.search(r"[.,](\d{1,2})$", n)
    whole = re.sub(r"[.,]", "", n[:dec.start()] if dec else n)
    try:
        return float(f"{whole}.{dec.group(1)}" if dec else whole)
    except ValueError:
        return None


async def page_price(page, item):
    if item.get("price_selector"):
        loc = page.locator(item["price_selector"]).first
        if await loc.count():
            return parse_price(await loc.text_content(timeout=2000))
    for raw in await page.locator('script[type="application/ld+json"]').all_inner_texts():
        m = re.search(r'"price"\s*:\s*"?([\d.]+)', raw)
        if m:
            return float(m.group(1))
    return None


def price_check(item, price):
    """None if fine, else a reason string (overpriced reseller etc.)."""
    mx = item.get("max_price")
    if mx and price and price > mx:
        return f"price {price:g} > max {mx:g} (reseller?)"
    return None


async def check_webhallen(page, item):
    pid = re.search(r"/product/(\d+)", item["url"]).group(1)
    r = await page.request.get(f"https://www.webhallen.com/api/product/{pid}")
    d = (await r.json())["product"]
    st, price = d.get("stock", {}), float(d["price"]["price"])
    if (st.get("web") or 0) > 0 or st.get("isTrue"):
        bad = price_check(item, price)
        return ("OVERPRICED", bad) if bad else ("IN_STOCK", f"web stock {st.get('web')} @ {price:g}")
    return "OUT", f"web stock 0 @ {price:g}"


async def check(page, item):
    """-> (status, detail). status in IN_STOCK, OUT, OVERPRICED, BLOCKED, ERROR"""
    try:
        if item.get("type") == "webhallen":
            return await check_webhallen(page, item)
        await page.goto(item["url"], wait_until="domcontentloaded", timeout=45000)
        try:
            await page.wait_for_load_state("networkidle", timeout=8000)
        except PWTimeout:
            pass
        await dismiss_cookies(page)
        body = (await page.locator("body").inner_text(timeout=5000))[:20000]
        if len(body.strip()) < 200:
            return "BLOCKED", "empty page (likely bot protection)"
        if BLOCKED.search(body) or BLOCKED.search(await page.title()):
            return "BLOCKED", "bot check / captcha"
        ld = await ld_availability(page)
        ld_ok = any(any(a in v for a in AVAILABLE_LD) for v in ld)
        btn = await find_buy_button(page, item)
        sold = item.get("sold_out_text")
        sold_hit = re.search(sold, body, re.I) if sold else SOLD_OUT.search(body)
        # explicit schema.org "OutOfStock" wins over a lookalike button
        ld_out = bool(ld) and not ld_ok
        if not ld_out and ((btn and (ld_ok or not sold_hit)) or (ld_ok and not sold_hit)):
            price = await page_price(page, item)
            bad = price_check(item, price)
            if bad:
                return "OVERPRICED", bad
            return "IN_STOCK", f"btn={'y' if btn else 'n'} ld={ld or '-'} price={price}"
        return "OUT", f"ld={ld or '-'} soldout={'y' if sold_hit else 'n'} btn={'y' if btn else 'n'}"
    except Exception as e:
        return "ERROR", str(e).splitlines()[0][:120]


_shop_ctx = None


async def grab(pw, item):
    """Open the item in the visible, logged-in Chrome profile, add to cart,
    open the cart, and leave the window for the user."""
    global _shop_ctx
    if _shop_ctx is None:
        _shop_ctx = await pw.chromium.launch_persistent_context(
            PROFILE, channel="chrome", headless=False, no_viewport=True)
        _shop_ctx.on("close", lambda *_: globals().__setitem__("_shop_ctx", None))
    page = await _shop_ctx.new_page()
    await page.goto(item["url"], wait_until="domcontentloaded")
    await page.bring_to_front()
    await dismiss_cookies(page)
    added = False
    if item.get("auto_add_to_cart", True):
        btn = await find_buy_button(page, item)
        if btn:
            try:
                await btn.click(timeout=5000)
                await page.wait_for_timeout(3000)
                added = True
                if item.get("cart_url"):
                    await page.goto(item["cart_url"], wait_until="domcontentloaded")
            except Exception as e:
                log(f"add-to-cart click failed: {e}")
    return added


async def main(args):
    state = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
    items = [i for i in CONFIG["items"] if i.get("enabled", True)]
    interval = CONFIG.get("interval_seconds", 120)
    async with async_playwright() as pw:
        if args.login:
            ctx = await pw.chromium.launch_persistent_context(
                PROFILE, channel="chrome", headless=False, no_viewport=True)
            for it in {i["store"]: i for i in items}.values():
                p = await ctx.new_page(); await p.goto(it["url"])
            print("Log in / set cookies in the opened tabs, then close the window.")
            await ctx.wait_for_event("close", timeout=0)
            return

        browser = await pw.chromium.launch(channel="chrome", headless=True)
        sem = asyncio.Semaphore(CONFIG.get("parallel_tabs", 4))

        async def handle(ctx, it):
            async with sem:
                page = await ctx.new_page()
                try:
                    status, detail = await check(page, it)
                finally:
                    await page.close()
            prev = state.get(it["url"], {}).get("status")
            log(f"{status:10} p{it.get('priority', 5)} {it['store']:<16} {it['product']:<10} {detail}")
            if status == "BLOCKED" and prev != "BLOCKED" and not (args.ci or args.once):
                notify(f"Bot check at {it['store']}",
                       "Watcher can't see this store right now. Tap to check it yourself.",
                       it["url"], priority="default", tags="warning")
            return it, status, detail, prev

        def rank(it):
            return it.get("priority", 5)

        async def alert(product, results):
            """One push per product: best-ranked store in stock, others listed."""
            now = sorted((it for it, st, _, _ in results if st == "IN_STOCK"), key=rank)
            before = [it for it, _, _, prev in results if prev == "IN_STOCK"]
            if not now:
                return
            best = now[0]
            prev_best = min(before, key=rank) if before else None
            if prev_best is not None and (best["url"] in {i["url"] for i in before}
                                          or rank(best) >= rank(prev_best)):
                return  # already alerted for this or a better store
            others = ", ".join(i["store"] for i in now[1:6])
            more = f" +{len(now) - 6} more" if len(now) > 6 else ""
            also = f" Also in stock at: {others}{more}." if others else ""
            upgrade = "Better store now in stock! " if prev_best else ""
            if args.ci:
                notify(f"IN STOCK: {product} @ {best['store']}",
                       f"{upgrade}Tap to open and buy now!{also}", best["url"])
                return
            notify(f"IN STOCK: {product} @ {best['store']}",
                   f"{upgrade}Opening it and adding to cart on your Mac.{also}", best["url"])
            try:
                added = await grab(pw, best)
                notify(f"{'In cart' if added else 'Opened'}: {product} @ {best['store']}",
                       "Go to your Mac and finish checkout now." if added
                       else "Couldn't auto-add - page is open, click Buy yourself.",
                       best.get("cart_url") or best["url"], priority="high", tags="shopping_cart")
            except Exception as e:
                log(f"grab failed: {e}")

        while True:
            ctx = await browser.new_context(locale="en-GB", viewport={"width": 1366, "height": 900})
            # lower "priority" = preferred store (Nintendo DE = 1.0); started first
            items.sort(key=lambda i: (rank(i), random.random()))
            results = await asyncio.gather(*(handle(ctx, it) for it in items))
            await ctx.close()
            if not args.once:
                for product in dict.fromkeys(it["product"] for it in items):
                    await alert(product, [r for r in results if r[0]["product"] == product])
            for it, status, detail, _ in results:
                state[it["url"]] = {"status": status, "at": time.time(), "detail": detail}
            STATE_FILE.write_text(json.dumps(state, indent=1))
            if args.once or args.ci:
                return
            await asyncio.sleep(interval * random.uniform(0.8, 1.2))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--login", action="store_true")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--test-notify", action="store_true")
    ap.add_argument("--ci", action="store_true", help="single pass, push alerts only (GitHub Actions)")
    a = ap.parse_args()
    if a.test_notify:
        notify("Zelda watcher test", "If you see this on your phone, alerts work.",
               "https://www.nintendo.com", priority="high"); sys.exit()
    asyncio.run(main(a))
