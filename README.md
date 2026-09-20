# Stage 2: CME GC manual PDF import

1. Download the official CME Daily Bulletin Metals / PG62 PDF manually.
2. Put it in `data/cme-pg62/`, e.g. `PG62_2026-09-18.pdf`.
3. Commit/push the PDF.
4. GitHub Actions runs the parser automatically.
5. `data/cme-gc-history.json` is updated.
6. The PWA can use `candles` for daily OHLC candles and `contracts` for Volume/OI.

Captured per contract/day: Open, High, Low, Settlement/Close, Volume (Globex + PNT/PIT), Open Interest, OI Change, contract, active flag.

Active contract is provisional: highest GC volume on each bulletin date. This can later be replaced with a formal roll rule.

No CME credentials are stored in the repository, and the workflow does not attempt to bypass CME access controls.
