import csv
from pathlib import Path

for filename in ["idols.csv", "units.csv"]:
    path = Path(filename)
    if not path.exists():
        print(filename + " missing")
        continue
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))
    print(filename, repr(rows[:4]))

source = Path(r"C:\Users\takey\Downloads\無題のスプレッドシート - シート2.csv")
with source.open("r", encoding="utf-8-sig", newline="") as handle:
    radio_rows = list(csv.reader(handle))
print("radio header", repr(radio_rows[0]))
for row in radio_rows[-5:]:
    print("radio", repr(row))
