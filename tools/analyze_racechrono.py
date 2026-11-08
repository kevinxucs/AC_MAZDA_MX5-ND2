#!/usr/bin/env python3
"""Read Sonoma RaceChrono RCZ archives without modifying/extracting the originals.

Requires numpy. Example (quote the glob so Python expands it):
  python3 tools/analyze_racechrono.py \
    '/Volumes/Share/Videos/GoProRaw/20261031_sonoma_speedsf_yellow_session*/*.rcz' \
    --output-dir analysis/sonoma_20261031

The legacy GPS streams use little-endian integers; channel2 streams use doubles.
Each stream has its own clock. Channel IDs are documented by RaceChrono at:
https://racechrono.com/forum/d/2659-2659
This is a reader for the layout observed in these recordings, not every RCZ version.
"""

import argparse
import csv
import glob
import hashlib
import json
from pathlib import Path
import zipfile

import numpy as np


G = 9.80665
KPA_PER_PSI = 6.894757293168
DT = 0.05
CAN = {
    4: "can_speed_mps", 7: "lateral_mps2", 8: "longitudinal_mps2",
    51: "yaw_deg_s", 1001: "steering_right_deg", 1002: "brake_pct",
    1004: "gear", 10024: "rpm", 10026: "coolant_c", 10029: "intake_c",
    10071: "accelerator_pct",
}
# Position order is RR, LR, RF, LF (not LF, RF, LR, RR).
POSITIONS = {3: "rr", 4: "lr", 5: "rf", 6: "lf"}


def quantiles(values):
    values = np.asarray(values)
    values = values[np.isfinite(values)]
    if not len(values):
        return None
    return dict(zip(("p05", "p50", "p95", "p99", "max"),
                    map(float, np.percentile(values, [5, 50, 95, 99, 100]))))


def mean_window(values, samples=11):
    """Centered 0.55 s filter; preserve missing samples instead of bridging them."""
    finite = np.isfinite(values)
    total = np.convolve(np.where(finite, values, 0), np.ones(samples), "same")
    count = np.convolve(finite.astype(float), np.ones(samples), "same")
    return np.divide(total, count, out=np.full(len(values), np.nan),
                     where=count == samples)


class Recording:
    def __init__(self, path):
        self.path = Path(path)
        self.streams = {}
        with zipfile.ZipFile(path) as archive:
            self.meta = json.loads(archive.read("session.json"))
            self.origin_ms = self.meta["firstTimestamp"]
            self.fragment = json.loads(archive.read("sessionfragment.json"))
            for name in archive.namelist():
                if not name.startswith("channel2_"):
                    continue
                _, kind, device, group, channel, storage = name.split("_")
                if storage != "3":
                    raise ValueError(f"Unsupported double stream: {name}")
                clock = f"channel_{kind}_{device}_{group}_1_1"
                self.add_stream(
                    f"{kind}:{channel}",
                    np.frombuffer(archive.read(clock), "<i8"),
                    np.frombuffer(archive.read(name), "<f8"), name)
            gps = self.fragment["primaryGpsDeviceIndex"]
            clock = np.frombuffer(archive.read(f"channel_1_{gps}_0_1_1"), "<i8")
            for channel, scale in [(4, 1000), (5, 1000), (6, 1000), (30007, 1000)]:
                name = f"channel_1_{gps}_0_{channel}_0"
                self.add_stream(f"gps:{channel}", clock,
                                np.frombuffer(archive.read(name), "<i4") / scale, name)
            name = f"channel_1_{gps}_0_3_1"
            coords = np.frombuffer(archive.read(name), "<i4").reshape(-1, 2) / 6_000_000
            self.add_stream("gps:lat", clock, coords[:, 0], name)
            self.add_stream("gps:lon", clock, coords[:, 1], name)

    def add_stream(self, key, times, values, source):
        if abs(len(times) - len(values)) > 1:
            raise ValueError(f"Clock/value length mismatch in {source}")
        n = min(len(times), len(values))
        times = (times[:n].astype(float) - self.origin_ms) / 1000
        values = values[:n].astype(float)
        if not np.all(np.diff(times) >= 0):
            raise ValueError(f"Non-monotonic clock in {source}")
        # Keep the last sample at duplicate timestamps; never shift streams by row.
        keep = np.r_[np.diff(times) > 0, True]
        self.streams[key] = (times[keep], values[keep])

    def interpolate(self, key, target, max_gap=0.25, hold=False):
        times, values = self.streams[key]
        right = np.searchsorted(times, target, side="right")
        left = np.clip(right - 1, 0, len(times) - 1)
        following = np.clip(right, 0, len(times) - 1)
        result = values[left].copy() if hold else np.interp(target, times, values)
        valid = (target >= times[0]) & (target <= times[-1])
        if hold:
            valid &= target - times[left] <= max_gap
        else:
            valid &= ((times[following] - times[left] <= max_gap)
                      | (times[left] == target))
        result[~valid] = np.nan
        return result

    def lap_ranges(self):
        return [(lap, (lap["startTimestamp"] - self.origin_ms) / 1000,
                 (lap["finishTimestamp"] - self.origin_ms) / 1000)
                for lap in self.meta["laps"]
                if "finishTimestamp" in lap and not lap.get("isInvalid", False)]

    def grid(self):
        t = np.arange(0, self.meta["lengthTime"] / 1000, DT)
        d = {"session_s": t}
        for ch, label in CAN.items():
            d[label] = self.interpolate(f"12:{ch}", t, hold=ch == 1004,
                                        max_gap=2 if ch in (10026, 10029) else 0.25)
        for ch, label in [(4, "gps_speed_mps"), (5, "altitude_m"),
                          ("lat", "latitude_deg"), ("lon", "longitude_deg")]:
            d[label] = self.interpolate(f"gps:{ch}", t)
        for pos, wheel in POSITIONS.items():
            for base, label, scale in [(1014, "pressure_psi", KPA_PER_PSI),
                                       (1013, "tpms_c", 1)]:
                d[f"{wheel}_{label}"] = self.interpolate(
                    f"5:{pos * 32768 + base}", t, max_gap=3, hold=True) / scale
        d["lateral_g_filtered"] = mean_window(d["lateral_mps2"]) / G
        d["longitudinal_g_filtered"] = mean_window(d["longitudinal_mps2"]) / G
        d["gps_dvdt_g_filtered"] = np.gradient(mean_window(d["gps_speed_mps"]), DT) / G
        return d


def summarize(recording, d):
    t = d["session_s"]
    laps = np.zeros(len(t), dtype=bool)
    lap_summaries = []
    for lap, start, finish in recording.lap_ranges():
        selected = (t >= start) & (t < finish)
        laps |= selected
        gps = d["gps_speed_mps"][selected]
        lap_summaries.append({
            "number": lap["number"], "seconds": round(finish - start, 3),
            "gps_distance_m": float(np.nansum(gps) * DT),
            "gps_valid_fraction": float(np.mean(np.isfinite(gps))),
            "gps_top_speed_kmh": float(np.nanmax(gps) * 3.6),
            "lateral_g_filtered": quantiles(abs(d["lateral_g_filtered"][selected])),
            "braking_g_filtered": quantiles(-d["longitudinal_g_filtered"][selected]),
            "accelerator_full_fraction": float(np.nanmean(d["accelerator_pct"][selected] > 98)),
            "braking_fraction": float(np.nanmean(d["brake_pct"][selected] > 2)),
        })
    moving = laps & (d["gps_speed_mps"] > 15)
    corner = moving & (d["brake_pct"] < 2) & (abs(d["longitudinal_g_filtered"]) < 0.25)
    braking = moving & (d["brake_pct"] > 50) & (abs(d["lateral_g_filtered"]) < 0.3)
    straight = moving & (d["brake_pct"] < 1) & (abs(d["steering_right_deg"]) < 5)
    inventory = {}
    for key, (clock, values) in recording.streams.items():
        inventory[key] = {"count": len(values),
                          "effective_hz": round((len(values) - 1) / (clock[-1] - clock[0]), 2),
                          "max_gap_s": round(float(np.max(np.diff(clock))), 3),
                          "values": quantiles(values)}
    tire = {}
    start = recording.lap_ranges()[0][1]
    finish = recording.lap_ranges()[-1][2]
    for pos, wheel in POSITIONS.items():
        clock, pressure = recording.streams[f"5:{pos * 32768 + 1014}"]
        pressure = pressure / KPA_PER_PSI
        pre = clock < start
        last = (clock >= finish - 60) & (clock < finish)
        tire[wheel] = {
            "pre_lap_pressure_psi": float(np.median(pressure[pre])),
            "last_lap_final_minute_pressure_psi": float(np.median(pressure[last])),
            "on_lap_pressure_psi": quantiles(d[f"{wheel}_pressure_psi"][laps]),
            "on_lap_internal_tpms_c": quantiles(d[f"{wheel}_tpms_c"][laps]),
        }
    ratios = {}
    for gear in range(2, 5):
        selected = straight & (d["gear"] == gear) & (d["accelerator_pct"] > 20)
        ratios[str(gear)] = {
            "seconds": round(float(sum(selected) * DT), 2),
            "rpm_per_can_mps": quantiles(d["rpm"][selected] / d["can_speed_mps"][selected]),
            "rpm_per_gps_mps": quantiles(d["rpm"][selected] / d["gps_speed_mps"][selected]),
        }
    brake_bins = []
    for lo, hi in [(5, 20), (20, 40), (40, 60), (60, 80), (80, 101)]:
        selected = moving & (abs(d["lateral_g_filtered"]) < 0.2)
        selected &= (d["brake_pct"] >= lo) & (d["brake_pct"] < hi)
        selected &= d["accelerator_pct"] < 1
        brake_bins.append({"input_range_pct": [lo, min(hi, 100)],
                           "seconds": round(float(sum(selected) * DT), 2),
                           "braking_g": quantiles(-d["longitudinal_g_filtered"][selected])})
    wot = []
    for gear in [3, 4]:
        for rpm in range(4000, 7500, 500):
            selected = moving & (d["gear"] == gear) & (d["accelerator_pct"] > 98)
            selected &= (d["brake_pct"] < 1) & (abs(d["lateral_g_filtered"]) < 0.3)
            selected &= (d["rpm"] >= rpm) & (d["rpm"] < rpm + 500)
            wot.append({"gear": gear, "rpm_bin": [rpm, rpm + 500],
                        "seconds": round(float(sum(selected) * DT), 2),
                        "specific_accel_g": quantiles(d["longitudinal_g_filtered"][selected]),
                        "gps_accel_g": quantiles(d["gps_dvdt_g_filtered"][selected])})
    agreement = moving & np.isfinite(d["yaw_deg_s"]) & np.isfinite(d["lateral_mps2"])
    agreement &= np.isfinite(d["can_speed_mps"])
    summary = {
        "file": recording.path.name,
        "sha256": hashlib.sha256(recording.path.read_bytes()).hexdigest(),
        "title": recording.meta["title"],
        "duration_s": recording.meta["lengthTime"] / 1000,
        "best_lap_metadata_s": recording.meta["bestLaptime"] / 1000,
        "laps": lap_summaries,
        "cornering_g_filtered": quantiles(abs(d["lateral_g_filtered"][corner])),
        "straight_braking_g_filtered": quantiles(-d["longitudinal_g_filtered"][braking]),
        "can_vs_gps_speed_ratio_straight": quantiles(
            d["can_speed_mps"][straight] / d["gps_speed_mps"][straight]),
        "lateral_vs_speed_times_yaw_correlation": float(np.corrcoef(
            d["lateral_mps2"][agreement], d["can_speed_mps"][agreement]
            * np.deg2rad(d["yaw_deg_s"][agreement]))[0, 1]),
        "tires": tire, "gearing_observed": ratios,
        "brake_response": brake_bins, "wot_response": wot,
        "channel_inventory": inventory,
    }
    return summary


def write_best_lap(out, recording, data):
    lap, start, finish = min(recording.lap_ranges(), key=lambda item: item[2] - item[1])
    selected = (data["session_s"] >= start) & (data["session_s"] < finish)
    values = {k: v[selected] for k, v in data.items()}
    speed = values["gps_speed_mps"]
    increments = np.r_[0, (speed[1:] + speed[:-1]) * DT / 2]
    distance = np.cumsum(increments)  # A GPS gap invalidates downstream distance.
    values = {"lap_s": values["session_s"] - start,
              "distance_m": distance,
              **values}
    with (out / "best_lap_20hz.csv").open("w", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(values)
        for row in zip(*values.values()):
            writer.writerow([f"{x:.6f}" if np.isfinite(x) else "" for x in row])
    with (out / "best_lap_distance_bins.csv").open("w", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["distance_bin_start_m", "gps_speed_min_kmh", "gps_speed_max_kmh",
                         "gear_median", "rpm_median", "accelerator_median_pct",
                         "brake_max_pct", "steering_right_median_deg", "yaw_median_deg_s",
                         "lateral_g_median", "longitudinal_g_median"])
        for start_m in range(0, int(np.nanmax(distance)), 100):
            selected = (distance >= start_m) & (distance < start_m + 100)
            if not selected.any():
                continue
            writer.writerow([start_m, f"{np.nanmin(speed[selected]) * 3.6:.3f}",
                             f"{np.nanmax(speed[selected]) * 3.6:.3f}"]
                            + [f"{np.nanmedian(values[k][selected]):.3f}" for k in
                               ["gear", "rpm", "accelerator_pct"]]
                            + [f"{np.nanmax(values['brake_pct'][selected]):.3f}"]
                            + [f"{np.nanmedian(values[k][selected]):.3f}" for k in
                               ["steering_right_deg", "yaw_deg_s", "lateral_g_filtered",
                                "longitudinal_g_filtered"]])
    return lap, values


def write_plot(out, data):
    """Standalone SVG reference plot; gaps stay gaps. No plotting dependency."""
    width, height = 1000, 650
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
             '<rect width="100%" height="100%" fill="white"/>',
             '<style>text{font-family:system-ui,sans-serif;fill:#222;font-size:13px}</style>',
             '<text x="60" y="27" font-size="19">Sonoma 2026-10-31 — fastest recorded lap (1:59.170 metadata)</text>']
    series = [("GPS speed (km/h)", data["gps_speed_mps"] * 3.6, 0, 180, "#1359b6"),
              ("Accelerator / brake (%)", data["accelerator_pct"], 0, 100, "#17813b"),
              ("CAN acceleration (g), 0.55 s mean", data["lateral_g_filtered"], -1.6, 1.6, "#8246aa")]
    for panel, (label, y, lo, hi, color) in enumerate(series):
        top, ph = 60 + panel * 185, 140
        parts.append(f'<text x="60" y="{top - 12}">{label}</text>')
        for q in np.linspace(lo, hi, 5):
            py = top + ph * (hi - q) / (hi - lo)
            parts.extend([f'<path d="M60 {py:.1f}H960" stroke="#e0e0e0"/>',
                          f'<text x="12" y="{py + 4:.1f}">{q:.1f}</text>'])
        for sec in range(0, 121, 20):
            px = 60 + 900 * sec / 120
            parts.append(f'<path d="M{px} {top}v{ph}" stroke="#eee"/>')
            if panel == 2:
                parts.append(f'<text x="{px - 6}" y="{top + ph + 20}">{sec}</text>')
        plotted = [(y, color)]
        if panel == 1:
            plotted.append((data["brake_pct"], "#ca302e"))
            parts.append(f'<text x="740" y="{top - 12}">green: accelerator, red: brake</text>')
        if panel == 2:
            plotted.append((data["longitudinal_g_filtered"], "#df6c12"))
            parts.append(f'<text x="690" y="{top - 12}">purple: lateral, orange: longitudinal</text>')
        for yy, stroke in plotted:
            points, segments = [], []
            for sec, val in zip(data["lap_s"][::2], yy[::2]):
                if not np.isfinite(val):
                    if points:
                        segments.append(points)
                        points = []
                    continue
                px = 60 + 900 * sec / 120
                py = top + ph * (hi - np.clip(val, lo, hi)) / (hi - lo)
                points.append(f"{px:.2f},{py:.2f}")
            segments.append(points)
            for points in segments:
                if points:
                    parts.append(f'<polyline points="{" ".join(points)}" fill="none" stroke="{stroke}" stroke-width="1.2"/>')
    parts.extend(['<text x="460" y="625">Lap time (s)</text>', '</svg>'])
    (out / "best_lap.svg").write_text("\n".join(parts) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", help="RCZ files or quoted glob patterns")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    paths = sorted({p for pattern in args.inputs for p in glob.glob(pattern)})
    if not paths:
        parser.error("No RCZ files matched")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    summary = {"resample_hz": 1 / DT, "acceleration_mean_window_s": 11 * DT,
               "max_interpolated_gap_s": 0.25, "sessions": []}
    best = None
    for path in paths:
        recording = Recording(path)
        data = recording.grid()
        session = summarize(recording, data)
        summary["sessions"].append(session)
        best_time = min(finish - start for _, start, finish in recording.lap_ranges())
        if best is None or best_time < best[0]:
            best = best_time, recording, data
        print(f"{session['title']}: {len(session['laps'])} complete laps; "
              f"best {session['best_lap_metadata_s']:.3f} s")
    _, recording, data = best
    lap, values = write_best_lap(args.output_dir, recording, data)
    write_plot(args.output_dir, values)
    summary["best_reference"] = {"file": recording.path.name, "lap": lap["number"],
                                  "seconds": round(best[0], 3)}
    (args.output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, allow_nan=False) + "\n")
    print(f"Wrote reference data to {args.output_dir}")


if __name__ == "__main__":
    main()
