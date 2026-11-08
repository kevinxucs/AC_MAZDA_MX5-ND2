# Sonoma real-car calibration — 2026-10-31

This is the first telemetry-based calibration of `ks_mazda_mx5_nd2_kevin`.
The source recordings are four local RaceChrono `.rcz` files under
`/Volumes/Share/Videos/GoProRaw/20261031_sonoma_speedsf_yellow_session*/`.
The original recordings are read-only inputs; their SHA-256 hashes are in
`summary.json`. No raw archives or videos are copied into the repository.

Kevin confirmed that the hardware and alignment are unchanged: 235/40R17
Nankang CR-S, 17x9 Hypergrams, 12k/6k Xidas, and -3.5/-2.5 camber.
Kevin explicitly confirmed the brake hardware:

- Front: Mazda Motorsports big brake kit for the ND Miata, with Ferodo DS1.11 pads.
- Rear: stock ND calipers and discs, with G-Loc R8 pads.

The front kit is the Mazda Motorsports Brembo package, rather than the factory
optional Brembo brake package. Mazda specifies four-piston front calipers and
310 x 28 mm discs for the Motorsports kit. Confirming this hardware does not
measure hydraulic brake torque or the variable front/rear distribution; the
existing AC 2900 Nm / 72% settings remain estimates.

Kevin supplied hot pressure targets of **31 psi front / 30 psi rear**.

## Applied physics changes

| Setting | Previous | New | Basis / confidence |
| --- | --- | --- | --- |
| CR-S front starting pressure | 25 psi | 28 psi | Rounded pre-lap TPMS observations in sessions 2–4; high confidence as a starting reference, not proof of fully cold pressure |
| CR-S rear starting pressure | 25 psi | 27 psi | Same method |
| CR-S front ideal/hot reference | 29 psi | 31 psi | Kevin's stated target; an explicit modeling choice, not a measured optimum |
| CR-S rear ideal/hot reference | 29 psi | 30 psi | Kevin's stated target |
| Manual gearbox ratios | 5.09 / 2.99 / 2.04 / 1.59 / 1.29 / 1.0 | 5.087 / 2.991 / 2.035 / 1.594 / 1.286 / 1.000 | Exact factory 2023 specifications; a small accuracy correction |
| Final drive | 2.87 | 2.866 | Exact factory specification; not a fit to RPM/GPS speed |

Only the active CR-S compound's pressure parameters change. Increasing its
starting pressure also affects AC's existing pressure-dependent tire stiffness,
flex, and rolling resistance. The simulated pressure rise still needs an AC
run; the edits do not guarantee that 28/27 will settle at exactly 31/30.
Load/reset the default setup or update saved setups manually, since saved
pressure settings can override `PRESSURE_STATIC`.

## What the recordings show

There are **81.93 minutes and 24 complete timed laps**. GPS is effectively
25 Hz. Most vehicle CAN channels average about 50–61 Hz, steering about
45–53 Hz, and brake input about 31–36 Hz. Bluetooth delivery is irregular;
the much shorter median sample interval would misleadingly imply ~91 Hz.
TPMS delivery averages about 1.5 Hz, but repeated identical values mean this
is not necessarily the sensors' physical refresh rate.

| Session | Complete laps | Best metadata time | Upper observed cornering* | Upper observed straight braking** |
| --- | ---: | ---: | ---: | ---: |
| 1 | 3 | 2:21.423 | 0.96 g | 0.88 g |
| 2 | 5 | 2:04.586 | 1.15 g | 1.01 g |
| 3 | 8 | 2:00.157 | 1.21 g | 1.11 g |
| 4 | 8 | 1:59.170 | 1.22 g | 1.13 g |

*99th percentile of absolute CAN lateral acceleration after a centered 0.55 s
mean, complete laps only, GPS speed >15 m/s, brake <2%, absolute longitudinal
acceleration <0.25 g. This still includes road banking, grade/body attitude,
load transfer, and the driver's chosen line; it is not tire friction coefficient.

**99th percentile of deceleration under >50% logged brake, >15 m/s, and
absolute lateral acceleration <0.3 g, with the same filter. Session 4's maximum
under this filter is 1.16 g. This is observed performance, not a proven limit.

The best lap is **session 4, lap 5**, with approximately **3.966 km** integrated
GPS distance and **171.4 km/h** peak GPS speed. The day's peak on a complete
lap is approximately **172.7 km/h**. Session metadata says 119.170 s; subtracting
lap 5's stored integer-millisecond timestamps gives 119.171 s. The reference
CSV uses those timestamps; the 1 ms discrepancy is retained, not hidden.
Its session-aligned 20 Hz grid begins 0.032 s after the gate and ends 0.039 s
before it, so the CSV's trapezoidal distance spans about 3.964 km; the session
summary's rectangular sum over all selected lap samples is about 3.966 km.

The strong lateral-acceleration versus speed × yaw-rate correlation
(0.980–0.987 across sessions) supports the basic channel identification and
units. Right steering is positive in this recording, while right yaw/lateral
acceleration have the opposite sign. Steering input must be inverted when
comparing against a logger using the yaw sign convention.

The later sessions are faster despite the same hardware. Traffic, driver
inputs, weather, and tire state can all contribute. This is not evidence that
the car's tire friction coefficient should be different in each session.

## Tire observations

The packed channel positions are **3=RR, 4=LR, 5=RF, 6=LF**. Assigning them
in the more familiar LF/RF/LR/RR order would reverse the axle inference.
Pressure is recorded in kPa and converted to psi. Temperature channels here
are internal TPMS measurements, **not tread surface or carcass temperatures**.

| Session | Pre-lap LF/RF (psi) | Pre-lap LR/RR (psi) | Final minute LF/RF (psi) | Final minute LR/RR (psi) |
| --- | --- | --- | --- | --- |
| 1 | 29.07 / 28.87 | 29.47 / 29.07 | 30.07 / 29.87 | 30.07 / 30.27 |
| 2 | 28.28 / 28.08 | 27.68 / 27.48 | 31.26 / 31.46 | 30.47 / 30.67 |
| 3 | 28.08 / 27.68 | 27.28 / 26.68 | 31.86 / 32.66 | 31.07 / 31.26 |
| 4 | 28.08 / 27.48 | 27.28 / 26.09 | 30.87 / 30.87 | 30.47 / 30.27 |

Pre-lap = median before the first complete lap. Final minute = median in the
last 60 s of the final complete lap. These are deliberately not called
fully-cold or true pit-exit temperatures/pressures. Sessions 2–4 front pre-lap
medians center around 28 psi, rears around 27 psi. Session 1 is much slower and
starts close to 29 psi at all corners; it is retained for context rather than
used for the later-session starting-pressure reference.

The recorded rear/front tire temperature progression and pressure rise are
useful for checking warmup and axle differences. They cannot establish an
optimal tire pressure, tread-temperature performance curve, heat-transfer
coefficients, or pressure sensitivity by themselves.

## What can be estimated, and what cannot yet be identified

| Data / measurement | Useful inference | Limitation / action |
| --- | --- | --- |
| GPS speed, position, distance, altitude, lap gates | Line, speed by location, braking points, lap/segment reference | Use the matching Sonoma layout and compare driving inputs; GPS altitude is noisy |
| CAN speed, RPM, gear | Shift points and relative gear spacing; RPM/speed benchmark | Absolute gearing and tire rolling radius are coupled; preserve factory ratios and physical tire size |
| Accelerator + RPM + speed + longitudinal acceleration | Acceleration response in gears 3/4, by RPM bin | Road grade, wind, tire slip, vehicle mass, inertia, and drag prevent a unique engine-power fit |
| Brake percentage + acceleration | Brake-release shape and observed deceleration by input range | No calibrated hydraulic pressure, pedal force, individual wheel speeds, or ABS state; cannot infer brake torque or bias uniquely |
| Steering + yaw + lateral acceleration + speed | Transient response, apparent understeer, steering corrections, and repeatable corner targets | Banking, compliance, sideslip, steering offset, and driver corrections are confounded; no unique ARB, steer ratio, or axle grip fit |
| TPMS pressure/internal temperature | Starting/hot references and warmup differences | Internal sensor temperature is not AC tread/core temperature |
| External three-axis IMU / gyroscope | Potential bump, pitch, roll, and yaw analysis | Recorded mounting orientation/bias require validation; no suspension position, wheel load, or damper velocity measurements |
| Missing fuel level / accurate ambient conditions | — | Cannot calibrate consumption, actual session mass, air density, or heat exchange |

The observed third-gear RPM/CAN-speed median is approximately 187.1–187.3
rpm per m/s; fourth is about 146.3–146.4. GPS-based ratios differ slightly.
Their relative spacing is broadly consistent with factory gearing. However,
using factory gearing and treating GPS speed as perfect would imply an
effective rolling radius around 0.296–0.297 m. That is smaller than the
0.310 m unloaded tire radius currently in `tyres.ini`. Loaded rolling radius,
tire slip, filtering, sensor scale, and stream delays have not been separated.
**Do not shrink the tire or change final drive solely to force this match.**
An AC RPM/speed log at the same speed/load is needed to see whether the
existing tire deflection already accounts for the difference.

Existing suspension geometry, 12k/6k spring wheel rates, front/rear ARB
19000/4800, estimated Xida damping, tire friction/load sensitivity, differential,
engine power, ABS, and 2900 Nm / 72% brake settings are preserved.
This does **not** validate those earlier modeling assumptions. In particular,
the brake values are not a measured match to the real hydraulic system.
Nor does a 1.22 g observed corner justify setting `DY_REF=1.22`: AC's reference
friction is per tire at a specified load, not whole-car measured lateral g.

## Files and reproduction

- `summary.json`: per-session/lap statistics, channel inventory, SHA-256 hashes,
  tire observations, brake-input bins, and WOT acceleration by gear/RPM.
- `best_lap_20hz.csv`: synchronized fastest-lap reference with speed, GPS path,
  RPM, gear, pedals, steering, yaw, accelerations, and TPMS channels.
- `best_lap_distance_bins.csv`: compact 100 m distance-bin reference for AC comparison.
- `best_lap.svg`: fastest-lap speed, pedal, and filtered acceleration plot.
- `../../tools/analyze_racechrono.py`: reproducible read-only archive decoder.

Run from the repository root with Python 3 and NumPy installed:

```sh
python3 tools/analyze_racechrono.py \
  '/Volumes/Share/Videos/GoProRaw/20261031_sonoma_speedsf_yellow_session*/*.rcz' \
  --output-dir analysis/sonoma_20261031
```

Streams are synchronized by their own millisecond timestamps, not row number.
The final unmatched timestamp/value (where lengths differ by one) is dropped.
Continuous CAN/GPS gaps longer than 0.25 s are blanked; TPMS is held for up to
3 s. Gear is held rather than interpolated through impossible fractional gears.
No independent sensor time-lag correction has been established. The 20 Hz
reference is appropriate for driver/car response comparisons, not damper dyno
or high-frequency suspension analysis. Filtered acceleration is a CAN sensor
measurement; GPS dv/dt is exported separately because grade and body attitude
make them different, especially at Sonoma.

## Next in-game validation

Use the matching approximately 4 km Sonoma course, CR-S compound, comparable
fuel/driver mass and dry conditions. Reset the setup to apply the pressure
defaults and warm the tires; adjust cold pressure if needed to reach 31/30 hot.
Log AC speed, gear, RPM, gas, brake, steering, yaw rate, accelerations, wheel
slip, tire pressures/temperatures, ride heights, and suspension travel if available.

First compare RPM/speed at low slip in gears 3/4. Next compare acceleration and
braking at matched locations, speeds, gears, and inputs. Finally compare steering
angle versus yaw and lateral response through the same corners, including how
the response builds and releases. Use the 100 m bins for finding differences,
then inspect the synchronized trace. Fit one subsystem at a time and check
against multiple laps/sessions. Matching the lap time alone is not validation.

There is no AC runtime or AC telemetry supplied with this analysis, so handling,
pressure warmup, absolute power, brake bias, and suspension response have not
been validated in game. This patch establishes measured pressure references,
correct factory gearing, and a repeatable baseline for that comparison.

## External references

- [Mazda Motorsports ND front big brake kit](https://www.mazdamotorsports.com/2024/09/11/parts-spotlight-brembo-mx-5-cup-big-brake-package-for-nd-chassis-mx-5/):
  four-piston Brembo calipers and 310 x 28 mm discs, designed for OEM ABS / variable proportioning.
- [RaceChrono channel identifiers and packed positions](https://racechrono.com/forum/d/2659-2659):
  channel numbers and axle/corner decoding; raw storage layout additionally
  checked against timestamps, plausible units, and cross-channel agreement.
- [Mazda USA 2023 MX-5 specification deck](https://filecache.mediaroom.com/mr5mr_mazdausa2/223258/download/2023%20MX-5%20Spec%20Deck.pdf):
  factory six-speed manual and final-drive ratios. These are factory facts,
  distinct from the measurements in the Sonoma archives.
