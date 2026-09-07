# Monza settlement and Madrid pre-FP refresh

Official fantasy feeds retrieved on 7 September 2026:

- [Monza game day 13](https://fantasy.formula1.com/feeds/drivers/13_en.json): driver and constructor `GamedayPoints`.
- [Previous game day 12](https://fantasy.formula1.com/feeds/drivers/12_en.json): baseline for cumulative statistics.
- [Madrid game day 14](https://fantasy.formula1.com/feeds/drivers/14_en.json): closing Monza prices in `Value`.

These fantasy game-day numbers omit the two cancelled races: Monza is internal round 15 and Madrid is internal round 16. Active players are selected by `IsActive`, preserving the distinction between the inactive Racing Bulls Lawson asset and active Red Bull Lawson asset.

Official overtakes, net positions gained/lost, Driver of the Day and fastest-lap awards are the differences between the Monza and previous feed's cumulative `AdditionalStats`, matched by `PlayerId`. Antonelli received both awards. Constructor pit-stop points are the official constructor race points minus both drivers' official race points, adding back the drivers' DOTD award. The resulting actuals reconcile exactly for all 22 drivers and 11 constructors.

The legacy price-history keys are retained to satisfy the price loader. Madrid's seat-specific Lawson and Tsunoda prices are recorded in a new round-16 override; the round-14 override is preserved.

[F1's race-day team report](https://www.formula1.com/en/latest/article/what-the-teams-said-race-day-in-italy-2026.43DzkIlg5jfZZOc1IBjSv3) supports the retirement labels: Leclerc lost the car off-line, Alonso damaged the car running wide over a kerb, and Stroll suffered a hydraulic issue. These map to `driver_error`, `driver_error`, and `mechanical`, respectively.

The fallback JoshCBruce fantasy-data repository was rejected because its latest Norris feed was timestamped November 2025.
