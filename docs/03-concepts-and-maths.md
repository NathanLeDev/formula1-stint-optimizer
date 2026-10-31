# Concepts and maths with worked examples

All examples use Austin (slope 0.045 s/lap, pit stop 20.8 s, 56 laps) unless stated otherwise.

## 1. What a tyre slope means
A slope of 0.045 s/lap means each extra lap of tyre age makes the next lap 0.045 s slower. It is a loss
**per lap of age**, not a total. On a 5-lap stint, relative to a new tyre: ages 0, 1, 2, 3, 4 lose
0, 0.045, 0.090, 0.135, 0.180 s; the stint costs the sum, 0.45 s.

## 2. Cost of a stint of n laps
0 + 1 + ... + (n-1) = n(n-1)/2, so **cost = slope x n(n-1)/2**.

| n | n(n-1)/2 | cost at 0.045 |
|---|---|---|
| 10 | 45 | 2.0 s |
| 20 | 190 | 8.6 s |
| 25 | 300 | 13.5 s |
| 28 | 378 | 17.0 s |
| 36 | 630 | 28.4 s |
| 40 | 780 | 35.1 s |

Common mistake: slope x n (0.045 x 25 = 1.1 s) is only the slowdown of the **last** lap against a new tyre,
not the cost of the stint. The cost grows with the square of the length: 4 times longer (40 vs 10 laps) costs
about 17 times more. Counting ages from 1 instead of 0 gives 14.6 s instead of 13.5 s for 25 laps.

## 3. Equal stints win (single slope)
56 laps, one stop: 28 + 28 costs 2 x 17.0 = 34.0 s; 20 + 36 costs 8.6 + 28.4 = 36.9 s. For a fixed sum, the sum
of squares is smallest when the parts are equal. With different compounds (different slopes and base pace) the best
split is unequal. Invented illustration, not Austin: a soft 0.5 s faster than a new hard but wearing at 0.08 s/lap
against 0.03 for the hard gives 28+28 = 27.6 s and 20 soft + 36 hard = 24.1 s.

## 4. How many stops
Equal stints, k stops, race of L laps: **cost(k) = k x pit + slope x L x (L/(k+1) - 1) / 2**.
Austin: 1 stop 20.8 + 34.0 = 54.8 s; 2 stops 41.6 + 22.3 = 63.9 s; 3 stops 62.4 + 16.4 = 78.8 s. Each extra stop saves wear
but costs a full stop. Fuel is ignored (same in every strategy). Assumptions: equal stints, one slope for all compounds,
new tyres at each stop, constant pit loss.

## 5. Fuel correction
Lap time falls as fuel burns. Illustration (assumed, not measured): 110 kg / 56 laps = 1.96 kg per lap, x 0.03 s per kg
= 0.058 s gained per lap. The fitted coefficient of the regression (-0.069 at Austin) also contains track evolution, so it
is not "the effect of fuel". Section 8 correction: `adjusted = lap time - BURN x (laps remaining)` puts every lap at the
end-of-race fuel level; the section 10 gap uses the median lap of the race as the fuel level instead.

## 6. The section 10 gap (normalised lap time)
`gap = lap time - median lap of the race - fuel x (lap number - median lap number)`. With fuel = -0.061 (Monza), a lap 10 in a
race whose median lap is lap 28 gets -(-0.061) x (10 - 28) = -1.1 s: it carried more fuel, so it is made faster.
The reference (race median) is a per-race constant: it cancels when comparing two strategies in the same race, but
it is information from the tested race, so a gap-based RMSE is not a pure forecast.
(The phase 2 target `gap` is simpler: lap time minus the race median, with no fuel correction; the fuel effect stays in it and the model learns it.)

## 7. Why offset and slope are tied (section 11)
A per-compound line `offset + slope x age` is estimated from points centred around some age (say 10). The fit is accurate near
that centre, so tilting the line moves its value at age 0 by (tilt x 10). Example: true value +0.5 s at age 10; slope estimate
0.05 gives an age-0 offset of 0.0 s, slope estimate 0.15 gives -1.0 s. An error of 0.1 s/lap on the slope becomes a 1 s error on the
offset, in the opposite direction. Hence offsets are read at a common age (10 laps), where all compounds have data.

## 8. Mean, median and the pit stop tail
Monza: most stops lose 24-26 s but the mean is 26.0 s because of a tail at 30-40 s. A typical stop costs about 1 s less than the mean.
Expected race time -> use the mean; a typical stop -> the median; risk -> the whole distribution. A strategy with more stops
is exposed to the tail more often. The loss formula can be inflated by yellow flags or traffic, so part of the tail may be measurement.

## 9. Reading counts against chance
Three compounds have 6 possible orders, so a random fit puts soft > medium > hard in 1/6 of circuits (about 2.5 of 15).
Observed 6/15 (p about 0.03) is a weak signal; 6/21 for the offsets (p about 0.12) is compatible with chance; 34 wins out of 76
for the per-compound slope is a coin flip (p about 0.42). Win counts are weaker evidence than an average RMSE difference with an
interval obtained by resampling races.

## 10. Rules of thumb
- A normalisation computed from the laps being predicted injects information about them; define the reference once, on the full table.
- A within-race standard error assumes independent laps; laps of one stint are correlated, so it understates the uncertainty.
- Fit on 2023-2024 / choose features by leave-one-race-out / read 2025 once / report 2026 separately.
