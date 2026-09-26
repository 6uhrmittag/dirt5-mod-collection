"""Regenerates mod.json + preview.png of the Rival Roster example mod (own names, own art).
Driver LocIDs come from the game's driverdata.json (extract it first:
python scripts/d5x.py extract 'data:event/driverdata/*' extracted/data)."""
import json
import os

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
TITLES = ["Captain", "Sir", "Lady", "Doctor", "Grandma", "Uncle", "Baron", "Professor", "Duchess", "Turbo",
          "Lil'", "Big", "Madame", "Count", "Auntie", "Coach", "Chef"]
NAMES = ["Handbrake", "Oversteer", "Mudflap", "Donut", "Sideways", "Pothole", "Gravel", "Airtime", "Wheelspin",
         "Burnout", "Splash", "Snowplough", "Crumplezone", "Hairpin", "Bumper", "Chicane", "Dustcloud", "Jumpstart",
         "Wobble"]
KEEP = {"alex-janicek", "bruno-durand", "bulldozer", "spark"}     # the story drivers keep their names


def main():
    src = os.path.join(ROOT, "extracted", "data", "event", "driverdata", "driverdata.json")
    drivers = [o for o in json.loads(open(src, "rb").read().rstrip(b"\0"))["objectInstances"] if o["Name"] not in KEEP]
    text, roster = {}, []
    for i, d in enumerate(sorted(drivers, key=lambda o: o["Name"])):
        first, last = TITLES[i % len(TITLES)], NAMES[i % len(NAMES)]      # 17 x 19 are coprime -> all pairs unique
        text[d["LongLocID"]] = f"{first} {last}"
        text[d["ShortLocID"]] = f"{first[0]}. {last}"
        roster.append(f"{first} {last}")
    meta = {
        "name": "Rival Roster",
        "version": "1.0.0",
        "author": "macha",
        "description": "the AI field gets silly racing names (Captain Handbrake, Grandma Sideways, Professor Airtime, ...) in all 9 languages; "
                       "also sets every AI racing number to 42 in the driver data (no arcade screen shows it)",
        "text": text,
        "json": [{"file": "data:event/driverdata/driverdata.json",
                  "set_object": {"match": {"type": "DVRDta"}, "set": {"racingNumber": 42}, "all": True}}],
    }
    with open(os.path.join(HERE, "mod.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
        f.write("\n")
    preview(roster[:10])
    print(f"{len(drivers)} drivers renamed")


def preview(rows):
    im = Image.new("RGB", (1280, 720), (24, 16, 40))
    dr = ImageDraw.Draw(im)
    big = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 64)
    mid = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 34)
    small = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 26)
    dr.text((60, 40), "RIVAL ROSTER", font=big, fill=(255, 214, 0))
    dr.text((64, 120), "your AI rivals, finally with proper names", font=small, fill=(230, 230, 240))
    for i, name in enumerate(rows):
        y = 180 + i * 50
        dr.rectangle((60, y, 760, y + 42), fill=(255, 0, 140) if i == 0 else (40, 30, 70))
        dr.text((74, y + 1), f"{i + 1:>2}", font=mid, fill=(255, 255, 255))
        dr.text((140, y + 1), name, font=mid, fill=(255, 255, 255))
    tag = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 44)
    for i, (pos, name) in enumerate([(7, "C. Handbrake"), (8, "P. Airtime"), (9, "U. Pothole")]):
        y = 250 + i * 110
        dr.rectangle((830, y, 1220, y + 64), fill=(20, 20, 24))
        dr.text((850, y + 4), f"{pos}  {name}", font=tag, fill=(255, 255, 255))
    dr.text((1025, 600), "the name tags above the AI cars", font=small, fill=(230, 230, 240), anchor="mm")
    im.save(os.path.join(HERE, "preview.png"))


if __name__ == "__main__":
    main()
