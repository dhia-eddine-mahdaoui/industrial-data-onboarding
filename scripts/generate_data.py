#!/usr/bin/env python3
"""Seeded synthetic data generator for the onboarding demo.

Produces messy "customer system" exports for two fictional plants:
  * sensor readings   - mixed timestamp formats, units, duplicates, gaps,
                        spikes, sentinel values, missing values
  * maintenance log   - free-text asset names, duplicate exports, unknown assets
  * asset register    - canonical IDs, some missing, some renamed (legacy names)

Every name, identifier and value is invented. Also writes ground_truth_entities.csv
(raw asset name -> true asset) for the entity-resolution eval. Output goes to data/raw/
and is gitignored; only this generator is versioned.

Usage:
  python scripts/generate_data.py --customer plant_alpha --out data/raw/plant_alpha
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

UTC = timezone.utc
SEED = 20260901
ALPHA_TZ = ZoneInfo("Europe/Berlin")
ALPHA_START = datetime(2026, 9, 1, tzinfo=UTC)
ALPHA_STEPS = 30 * 48  # 30 days sampled every 30 minutes
TS_KINDS = ["iso_z", "iso_offset", "naive_local", "epoch"]
TS_WEIGHTS = [30, 25, 30, 15]

# true_id is the generator's ground truth. register_id is what the customer
# register holds (None = the register lost the ID for that asset).
ALPHA_ASSETS = [
    {"true_id": "PMP-01A", "register_id": "PMP-01A", "name": "Feed Pump 1A",
     "asset_class": "pump", "area": "Intake", "legacy_names": [],
     "texts": ["Pump 1A", "PMP-01A", "pump1a", "Feed Pump 1A", "P-1A"], "sensors": ["brg_temp", "disch_press"]},
    {"true_id": "PMP-02A", "register_id": "PMP-02A", "name": "Feed Pump 2A",
     "asset_class": "pump", "area": "Intake", "legacy_names": ["Feed Pump 2"],
     "texts": ["Pump 2A", "PMP-02A", "pump2a north"], "sensors": ["brg_temp", "disch_press"]},
    {"true_id": "PMP-03A", "register_id": "PMP-03A", "name": "Feed Pump 3A",
     "asset_class": "pump", "area": "Intake", "legacy_names": ["Feed Pump 3 (old)"],
     "texts": ["Pump 3A", "PMP-03A", "pump3a north", "P-3A (north)", "PMP03A"],
     "sensors": ["brg_temp", "disch_press"],
     "failure_at": datetime(2026, 9, 22, 6, 0, tzinfo=UTC)},
    {"true_id": "PMP-03B", "register_id": "PMP-03B", "name": "Dosing Pump 3B",
     "asset_class": "pump", "area": "Process", "legacy_names": [],
     "texts": ["Pump 3B", "PMP-03B"], "sensors": ["brg_temp", "disch_press"]},
    {"true_id": "CMP-01", "register_id": "CMP-01", "name": "Air Compressor 1",
     "asset_class": "compressor", "area": "Utilities", "legacy_names": ["Compressor C1"],
     "texts": ["Compressor 1", "CMP-01", "cmp 01", "Air Compressor 1", "Compressor C1"], "sensors": ["brg_temp", "disch_press"],
     "failure_at": datetime(2026, 9, 27, 14, 0, tzinfo=UTC)},
    {"true_id": "CMP-02", "register_id": "CMP-02", "name": "Air Compressor 2",
     "asset_class": "compressor", "area": "Utilities", "legacy_names": [],
     "texts": ["Compressor 2", "CMP-02", "cmp 02"], "sensors": ["brg_temp", "disch_press"]},
    {"true_id": "MTR-01", "register_id": "MTR-01", "name": "Mixer Motor 1",
     "asset_class": "motor", "area": "Process", "legacy_names": [],
     "texts": ["Motor 1", "MTR-01", "mtr01", "Mixer Motor 1"], "sensors": ["brg_temp"]},
    {"true_id": "MTR-02", "register_id": None, "name": "Mixer Motor 2",
     "asset_class": "motor", "area": "Process", "legacy_names": ["MTR 02", "Motor M2"],
     "texts": ["MTR-02", "Motor 2", "mtr02"], "sensors": ["brg_temp"],
     "failure_at": datetime(2026, 9, 15, 9, 30, tzinfo=UTC)},
    {"true_id": "FAN-01", "register_id": "FAN-01", "name": "Cooling Fan 1",
     "asset_class": "fan", "area": "Cooling", "legacy_names": [],
     "texts": ["Fan 1", "FAN-01", "fan01", "Cooling Fan 1"], "sensors": ["brg_temp"]},
    {"true_id": "HX-01", "register_id": "HX-01", "name": "Heat Exchanger 1",
     "asset_class": "heat_exchanger", "area": "Cooling", "legacy_names": [],
     "texts": ["Heat Exchanger 1", "HX-01", "hx01"], "sensors": []},
    {"true_id": "TNK-01", "register_id": "TNK-01", "name": "Buffer Tank 1",
     "asset_class": "tank", "area": "Process", "legacy_names": [],
     "texts": ["Buffer Tank 1", "TNK-01"], "sensors": []},
]

BETA_START = datetime(2026, 9, 10, tzinfo=UTC)
BETA_HOURS = 7 * 24
BETA_ASSETS = [
    {"code": "BT-01", "description": "Cooling pump 1",
     "texts": ["Cooling pump 1", "BT-01", "bt01"], "sensors": ["bearing temp", "discharge pressure"]},
    {"code": "BT-02", "description": "Cooling motor 2",
     "texts": ["Cooling motor 2", "BT-02", "bt02"], "sensors": ["bearing temp"]},
    {"code": "BT-03", "description": "Cooling compressor 3",
     "texts": ["Cooling compressor 3", "BT-03", "bt03"], "sensors": ["bearing temp", "discharge pressure"]},
]


def write_csv(path: Path, header: list[str], rows: list[list]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        writer.writerows(rows)


TYPO_RATE = 0.12


def _typo(rng: random.Random, text: str) -> str:
    """Swap two adjacent characters or drop one letter, as a hurried technician would."""
    positions = [i for i, c in enumerate(text[:-1]) if c.isalpha()]
    if len(text) < 7 or not positions:
        return text
    i = rng.choice(positions)
    if rng.random() < 0.5:
        return text[:i] + text[i + 1] + text[i] + text[i + 2:]
    return text[:i] + text[i + 1:]


def _ts_text(kind: str, ts_utc: datetime) -> str:
    local = ts_utc.astimezone(ALPHA_TZ)
    if kind == "iso_z":
        return ts_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    if kind == "iso_offset":
        return local.isoformat(timespec="seconds")
    if kind == "naive_local":
        return local.strftime("%d/%m/%Y %H:%M")
    if kind == "epoch":
        return str(int(ts_utc.timestamp()))
    raise ValueError(kind)


def _gen_alpha_readings(rng: random.Random, truth: dict) -> list[list]:
    rows: list[list] = []
    for asset in ALPHA_ASSETS:
        for sensor in asset["sensors"]:
            gap_at = rng.randint(100, ALPHA_STEPS - 200) if rng.random() < 0.3 else None
            for i in range(ALPHA_STEPS):
                if gap_at is not None and gap_at <= i < gap_at + 12:
                    continue  # 6 hours without samples
                ts = ALPHA_START + timedelta(minutes=30 * i)
                phase = math.sin(2 * math.pi * i / 48)
                spike = rng.random() < 0.004
                if sensor == "brg_temp":
                    celsius = 62.0 + 2.0 * phase + rng.gauss(0, 0.6)
                    fail_at = asset.get("failure_at")
                    if fail_at is not None:
                        hours_before = (fail_at - ts).total_seconds() / 3600
                        if 0 <= hours_before <= 96:
                            celsius += 15.0 * (1 - hours_before / 96)  # pre-failure ramp
                    if spike:
                        celsius += 40.0
                    if rng.random() < 0.4:
                        unit, value = "degF", celsius * 9 / 5 + 32
                    else:
                        unit, value = "C", celsius
                else:
                    bar = 4.5 + 0.15 * phase + rng.gauss(0, 0.05)
                    if spike:
                        bar += 4.0
                    if rng.random() < 0.3:
                        unit, value = "psi", bar * 14.5038
                    else:
                        unit, value = "bar", bar
                roll = rng.random()
                if roll < 0.004:
                    value_text = "-999"  # sentinel
                elif roll < 0.009:
                    value_text = ""  # missing
                else:
                    value_text = f"{value:.2f}"
                if rng.random() < 0.0005:
                    unit = "K"  # unit not in the mapping
                if rng.random() < 0.0005:
                    ts_text = ts.strftime("%Y/%m/%d %H%M")  # unparseable
                else:
                    ts_text = _ts_text(rng.choices(TS_KINDS, weights=TS_WEIGHTS)[0], ts)
                equipment = rng.choice([asset["true_id"],
                                        asset["true_id"].replace("-", ""),
                                        asset["true_id"].lower()])
                truth[("readings", equipment)] = asset["name"]
                row = [ts_text, equipment, sensor.upper(), value_text, unit]
                rows.append(row)
                if rng.random() < 0.01:
                    rows.append(list(row))  # re-sent record
    return rows


def _gen_alpha_maintenance(rng: random.Random, truth: dict) -> list[list]:
    rows: list[list] = []
    counter = [4000]

    def add(ts: datetime, text: str, activity: str, failure: str, note: str,
            true_name: str, typo_ok: bool = True) -> None:
        counter[0] += 1
        if typo_ok and rng.random() < TYPO_RATE:
            text = _typo(rng, text)
        truth[("maintenance", text)] = true_name
        opened = ts.astimezone(ALPHA_TZ).strftime("%d.%m.%Y %H:%M")
        rows.append([f"WO-{counter[0]:06d}", text, opened, activity, failure, note])

    for asset in ALPHA_ASSETS:
        t = ALPHA_START + timedelta(days=rng.randint(0, 6), hours=rng.randint(6, 16))
        while t < ALPHA_START + timedelta(days=30):
            add(t, rng.choice(asset["texts"]), "PM", "N", "Routine lubrication and inspection",
                asset["name"])
            t += timedelta(days=7)
        if "failure_at" in asset:
            add(asset["failure_at"], rng.choice(asset["texts"]), "CM", "Y",
                "Bearing overheating, unplanned stop", asset["name"])
    # work orders on equipment that is not in the register at all: must never be auto-matched
    add(datetime(2026, 9, 9, 11, 15, tzinfo=UTC), "Pump 9", "CM", "N", "Noise reported at coupling",
        "", typo_ok=False)
    add(datetime(2026, 9, 18, 7, 40, tzinfo=UTC), "Compressor C-7", "INSP", "N", "Ad hoc inspection",
        "", typo_ok=False)
    rows.extend([list(r) for r in rng.sample(rows, 4)])  # duplicate exports
    rng.shuffle(rows)
    return rows


def _gen_alpha(out: Path, rng: random.Random, truth: dict) -> dict:
    readings = _gen_alpha_readings(rng, truth)
    rng.shuffle(readings)
    write_csv(out / "readings_export.csv", ["timestamp", "equipment", "sensor", "value", "unit"], readings)
    maintenance = _gen_alpha_maintenance(rng, truth)
    write_csv(out / "maintenance_log.csv",
              ["wo_number", "asset_text", "opened_date", "activity_type", "is_failure", "notes"],
              maintenance)
    register = {"assets": [
        {"asset_id": a["register_id"], "name": a["name"], "asset_class": a["asset_class"],
         "area": a["area"], "legacy_names": a["legacy_names"]}
        for a in ALPHA_ASSETS
    ]}
    (out / "asset_register.json").write_text(json.dumps(register, indent=2), encoding="utf-8")
    return {"readings": len(readings), "maintenance": len(maintenance), "assets": len(ALPHA_ASSETS)}


def _gen_beta(out: Path, rng: random.Random, truth: dict) -> dict:
    readings: list[list] = []
    for asset in BETA_ASSETS:
        for sensor in asset["sensors"]:
            for h in range(BETA_HOURS):
                ts = BETA_START + timedelta(hours=h)
                if sensor == "bearing temp":
                    value, unit = 58.0 + 1.5 * math.sin(2 * math.pi * h / 24) + rng.gauss(0, 0.5), "C"
                else:
                    value, unit = 3.2 + 0.1 * math.sin(2 * math.pi * h / 24) + rng.gauss(0, 0.03), "bar"
                text = "" if rng.random() < 0.005 else f"{value:.2f}"
                name = rng.choice(asset["texts"])
                truth[("readings", name)] = asset["description"]
                row = [ts.strftime("%Y-%m-%d %H:%M:%S"), name, sensor, text, unit]
                readings.append(row)
                if rng.random() < 0.005:
                    readings.append(list(row))
    rng.shuffle(readings)
    write_csv(out / "sensor_feed.csv", ["ts_utc", "asset", "measure", "val", "uom"], readings)

    plan = [(0, "2026-09-11 08:00", "PM", "N"), (1, "2026-09-12 09:30", "PM", "N"),
            (2, "2026-09-14 13:15", "CM", "Y"), (2, "2026-09-16 07:45", "PM", "N"),
            (0, "2026-09-16 10:00", "INSP", "N")]
    work_orders = [[f"WB-{i + 1:04d}", BETA_ASSETS[idx]["texts"][i % 3], opened, act, failed]
                   for i, (idx, opened, act, failed) in enumerate(plan)]
    for (idx, *_), wo in zip(plan, work_orders):
        truth[("maintenance", wo[1])] = BETA_ASSETS[idx]["description"]
    write_csv(out / "work_orders.csv", ["WO", "Equipment", "Opened", "Type", "Failed"], work_orders)
    register = {"items": [{"code": a["code"], "description": a["description"]} for a in BETA_ASSETS]}
    (out / "asset_list.json").write_text(json.dumps(register, indent=2), encoding="utf-8")
    return {"readings": len(readings), "maintenance": len(work_orders), "assets": len(BETA_ASSETS)}


def write_ground_truth(path: Path, truth: dict) -> None:
    """Labels for the entity-resolution eval: raw name -> true asset name ('' = not in the register)."""
    rows = [[source, raw, name] for (source, raw), name in sorted(truth.items())]
    write_csv(path, ["source", "raw_name", "true_asset_name"], rows)


def generate(customer: str, out: Path, seed: int = SEED) -> dict:
    rng = random.Random(seed)
    out.mkdir(parents=True, exist_ok=True)
    truth: dict = {}
    if customer == "plant_alpha":
        counts = _gen_alpha(out, rng, truth)
    elif customer == "plant_beta":
        counts = _gen_beta(out, rng, truth)
    else:
        raise ValueError(f"unknown customer profile: {customer}")
    write_ground_truth(out / "ground_truth_entities.csv", truth)
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--customer", required=True, choices=["plant_alpha", "plant_beta"])
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args()
    counts = generate(args.customer, args.out, args.seed)
    print(f"generated {args.customer}: {counts}")


if __name__ == "__main__":
    main()
