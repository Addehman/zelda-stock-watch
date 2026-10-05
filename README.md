# Zelda 40th Switch 2 stock watcher

Watches the Zelda 40th Anniversary **console, Pro Controller and carrying case** at the
Nintendo Store (IE, FR, DE, AT, IT, ES, NL, BE, PT), Amazon EU (de/es/fr/it/nl) and Swedish shops (Webhallen, Inet,
NetOnNet, Power, Elgiganten, Amazon.se). It checks in priority order: Nintendo first, then Amazon EU, then Sweden.

When one comes in stock:
1. **Urgent push to your Android** via ntfy. Tap it to open the product.
2. Your Mac opens it in the watcher's Chrome window, clicks **Add to cart** and shows the cart.
3. A second push says "In cart". **You** finish checkout and payment.

If several stores restock at once you get **one push per product**, for the best store
(Nintendo DE → NL → BE → AT → FR → IE → IT → ES → PT → Amazon EU → Sweden), listing the others.
A later push only comes if a *better* store gets stock.

Anything priced above `max_price` (resellers) is ignored.

## Two ways it runs
- **GitHub Actions (always on):** `.github/workflows/watch.yml` checks every ~5 min, around the clock.
  It only sends push alerts, because it isn't logged in to your stores. Tap the push and buy on your phone.
- **Your Mac (optional extra):** `./run.sh` also adds to cart automatically in your logged-in Chrome profile.

## One-time setup
1. On your phone, install **ntfy** from Google Play and subscribe to your topic (stored in the local `.topic` file and in the `NTFY_TOPIC` GitHub secret, never in the code).
   In the topic settings, allow it to override Do Not Disturb.
2. Test it: `./run.sh --test-notify`
3. Log in to the stores in the watcher's own Chrome profile. Set your delivery address to Sweden
   on Amazon. Close the window when done:
   `./run.sh --login`

## Run
```
./run.sh            # runs until you press Ctrl-C; keeps the Mac awake
./run.sh --once     # one pass, prints status for every store
```
`state.json` holds the last status of each page.

## Notes
- Adding to cart does **not** reserve stock at most shops. Check out quickly.
- The watcher never solves CAPTCHAs. If a store shows a bot check, you get a "Bot check" push.
- Your work network blocks store.nintendo.com, so the Nintendo checks only work on another network (home Wi-Fi or a phone hotspot).
- Edit `config.json` to add or remove pages, change priority or change price ceilings.
