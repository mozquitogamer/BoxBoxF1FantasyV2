# V13 history correction — 7 November 2026

Completed through Mexico (R21). All 19 completed weekends were examined. Fifteen have genuine saved pre-lock practice forecasts; R1–R3 remain reconstructed research and R6 has no verifiable pre-lock forecast. Older session coverage is not fully recorded, so this report does not claim FP3 where it cannot be verified.

| Measure | Previous | Corrected |
|---|---:|---:|
| Points through R21 | 4582 | 4587 |
| Spending power | $135.3M | $138.6M |
| Bank | $1.5M | $1.2M |

The replay selects using forecast points and risk only. Official results settle each selected team; closing prices then carry its budget into the next round. The original V13 research chip dates are preserved as policy inputs; Final Fix is recalculated from qualifying-locked race projections and later 3x decisions use the horizon saved before each weekend’s lock.

| Round | Race | Previous score | Corrected score | Change | Previous budget | Corrected budget | Source time (UTC) | Recorded sessions |
|---|---|---:|---:|---:|---:|---:|---|---|
| 1 | Australian Grand Prix | 251 | 251 | +0 | $103.4M | $103.4M | 2026-05-16 05:09:27 | Reconstructed |
| 2 | Chinese Grand Prix | 331 | 331 | +0 | $103.4M | $103.4M | 2026-05-16 05:11:53 | Reconstructed |
| 3 | Japanese Grand Prix | 206 | 206 | +0 | $106.2M | $106.2M | 2026-05-16 05:06:33 | Reconstructed |
| 6 | Miami Grand Prix | 179 | 179 | +0 | $108.3M | $108.3M | 2026-05-19 06:17:38 | Pre-lock unverified |
| 7 | Canadian Grand Prix | 283 | 283 | +0 | $109.8M | $109.8M | 2026-05-23 09:52:58 | Not recorded |
| 8 | Monaco Grand Prix | 171 | 171 | +0 | $111.9M | $111.9M | 2026-06-06 12:13:58 | Not recorded |
| 9 | Spanish Grand Prix | 113 | 113 | +0 | $114.4M | $114.4M | 2026-06-12 22:48:06 | Not recorded |
| 10 | Austrian Grand Prix | 238 | 238 | +0 | $116.3M | $116.3M | 2026-06-26 13:21:06 | Not recorded |
| 11 | British Grand Prix | 330 | 330 | +0 | $119.2M | $119.2M | 2026-07-04 06:44:20 | Not recorded |
| 12 | Belgian Grand Prix | 269 | 269 | +0 | $122.3M | $122.3M | 2026-07-18 13:49:58 | Not recorded |
| 13 | Hungarian Grand Prix | 223 | 223 | +0 | $125.3M | $125.6M | 2026-07-25 12:12:18 | Not recorded |
| 14 | Dutch Grand Prix | 246 | 246 | +0 | $127.0M | $127.3M | 2026-08-21 15:48:55 | Not recorded |
| 15 | Italian Grand Prix | 358 | 358 | +0 | $129.2M | $129.5M | 2026-09-05 12:46:28 | Not recorded |
| 16 | Spanish Grand Prix (Madrid) | 151 | 187 | +36 | $130.6M | $131.5M | 2026-09-12 12:31:39 | Not recorded |
| 17 | Azerbaijan Grand Prix | 250 | 196 | -54 | $132.5M | $133.6M | 2026-09-25 11:25:19 | Not recorded |
| 18 | Bahrain Grand Prix in Malaysia | 247 | 279 | +32 | $133.1M | $135.4M | 2026-10-03 06:11:06 | FP1, FP2, FP3 |
| 19 | Singapore Grand Prix | 255 | 216 | -39 | $134.9M | $137.0M | 2026-10-09 19:16:46 | FP1 |
| 20 | United States Grand Prix | 311 | 305 | -6 | $135.8M | $138.5M | 2026-10-24 19:40:42 | FP1, FP2, FP3 |
| 21 | Mexican Grand Prix | 170 | 206 | +36 | $135.3M | $138.6M | 2026-10-31 20:07:48 | FP1, FP2, FP3 |

The R13 Final Fix remains Hamilton → Norris, adding 22 realised points. Its replacement-price effect is now included in the closing team value and carried forward. The missing Singapore decision records were also recovered from the original local audit.

| Chip | Completed-round use |
|---|---|
| Wild Card | R7 |
| Limitless | R8 |
| No Negative | R10 |
| Autopilot | R12 |
| Final Fix | R13 |

Current Brazil proposal: VER, ANT, CAM, PER, BOR; constructors red_bull, mercedes. Chip: 3x_boost; captain VER; second boost ANT. 322.2 net projected points, 4 transfers and 10 penalty points. Team cost $138.4M; remaining bank $0.2M. This is provisional until the configured 18:00 UTC team lock. The latest forecast includes Hamilton's ten-place penalty, Russell's five-place penalty, and Verstappen starting at the back.

Every actionable export now requires a matching V13 choice, including standalone exports. The decision fingerprint includes carried team, bank, budget, transfers, chips, policy and horizon. Vercel rejects a stale or over-budget choice. New simulations append revisions while preserving earlier decision records.

Immutable ledger: `data/v13/replays/2026-11-07T14-45-33Z/ledger.json`
Ledger SHA-256: `3cd6c832808354a43dbfe01e905e0d2f7e9991008e1f88bc4b92be5585965337`

Source forecasts, archived horizons, original public record, and settlement inputs are retained with the correction.
