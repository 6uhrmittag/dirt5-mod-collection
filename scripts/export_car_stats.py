"""export_car_stats.py - the game's car cards for the Car Companion overlay (read-only).

Reads data:event/vehicledata/vehicledata.json from YOUR game install (d5x, never writes it)
and saves one card per car to %APPDATA%\\Dirt5TrackCompanion\\carstats.json - outside the
repo, because it's game data. The overlay (src/Dirt5.TrackCompanion) picks it up on start.

  python scripts/export_car_stats.py [--out <file>] [--print]

Card fields: name, manufacturer, performance + handling grade (the letters on the in-game
card; vehicledata stores an enum 0..3 - verified: Lancia 037 = 3/2 = "C"/"B" in livery
select, the rest of the mapping 0=S 1=A 2=B 3=C is inferred), power (bhp), torque (Nm),
weight (kg), drivetrain + class from DataTagList.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from d5x import GAME_DAT, Index  # noqa: E402

GRADES = {0: "S", 1: "A", 2: "B", 3: "C"}


def default_out():
    return os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "Dirt5TrackCompanion", "carstats.json")


def cards():
    orig = os.path.join(GAME_DAT, "index", "dat.ndx.d5x-orig")      # vanilla data even while mods are applied
    idx = Index(ndx_path=orig) if os.path.exists(orig) else Index()
    doc = json.loads(idx.read(idx.find("data:event/vehicledata/vehicledata.json")).rstrip(b"\0"))
    out = {}
    for v in doc["objectInstances"]:
        chassis = v.get("ChassisName")
        if not chassis or v.get("type") != "VehData":
            continue
        tags = {}
        for t in v.get("DataTagList", []):
            tag = next(iter(t.values()))
            tags.setdefault(tag.get("TagType"), tag.get("Name"))
        out[chassis] = {
            "name": v.get("Name"), "manufacturer": v.get("Manufacturer"),
            "performance": GRADES.get(v.get("PerformanceOverview")), "handling": GRADES.get(v.get("HandlingOverview")),
            "powerBhp": v.get("Power"), "torqueNm": v.get("Torque"), "weightKg": v.get("Weight"),
            "drivetrain": tags.get("Drivetrain"), "carClass": (tags.get("Class") or "").replace("_", " ") or None,
        }
    return out


def main(argv):
    out = argv[argv.index("--out") + 1] if "--out" in argv else default_out()
    data = cards()
    if "--print" in argv:
        for k, c in sorted(data.items()):
            print(f"{k:42} {c['name'][:24]:24} perf {c['performance']} hand {c['handling']} {c['powerBhp']} bhp {c['weightKg']} kg {c['drivetrain']} {c['carClass']}")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
    print(f"{len(data)} car cards -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
