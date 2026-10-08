"""CSV cleaning + city-level geocoding helpers (pure Python, no Django)."""
import csv
import io
import re
import zipfile

US_STATES = set(
    "AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY "
    "NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY".split()
)
# Place-type words the Census appends to names ("Big Cabin town", "Kansas City city").
PLACE_SUFFIXES = {
    "city", "town", "village", "borough", "cdp", "municipality", "township", "plantation",
    "government", "metropolitan", "consolidated", "balance",
}
TOKEN_MAP = {"saint": "st", "mount": "mt", "fort": "ft", "twp": "township", "ste": "sainte"}


def norm_tokens(name):
    s = re.sub(r"\(.*?\)", " ", name.lower())
    s = s.replace("&", " and ").replace("'", "")
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return [TOKEN_MAP.get(t, t) for t in s.split()]


def norm_city(name):
    return " ".join(norm_tokens(name))


def read_us_stations(csv_path):
    """Return (stations, stats). One row per OPIS id, cheapest posted price, US states only."""
    by_id, dropped_non_us, total = {}, 0, 0
    with open(csv_path, newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            total += 1
            state = row["State"].strip().upper()
            if state not in US_STATES:
                dropped_non_us += 1
                continue
            sid = int(row["OPIS Truckstop ID"])
            price = float(row["Retail Price"])
            cur = by_id.get(sid)
            if cur is None:
                by_id[sid] = {
                    "opis_id": sid,
                    "name": row["Truckstop Name"].strip(),
                    "address": row["Address"].strip(),
                    "city": row["City"].strip(),
                    "state": state,
                    "price": price,
                }
            elif price < cur["price"]:
                cur["price"] = price
    stats = {"rows": total, "dropped_non_us": dropped_non_us, "unique_us_stations": len(by_id)}
    return list(by_id.values()), stats


def _open_gazetteer_text(raw_bytes, filename):
    if filename.lower().endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(raw_bytes)) as zf:
            name = next(n for n in zf.namelist() if n.lower().endswith(".txt"))
            raw_bytes = zf.read(name)
    return raw_bytes.decode("utf-8-sig", errors="replace")


def parse_gazetteer(raw_bytes, filename="gazetteer.zip"):
    """Census 'places' gazetteer -> {(STATE, normalized city): (lat, lng)}.

    Tab-delimited through 2024, pipe-delimited from 2025, so the delimiter is sniffed.
    """
    text = _open_gazetteer_text(raw_bytes, filename)
    header = text.split("\n", 1)[0]
    delim = "|" if header.count("|") > header.count("\t") else "\t"
    reader = csv.DictReader(io.StringIO(text), delimiter=delim)
    reader.fieldnames = [f.strip() for f in reader.fieldnames]
    primary, secondary, area, aliases = {}, {}, {}, {}
    for row in reader:
        row = {k: (v or "").strip() for k, v in row.items() if k}
        state, name = row["USPS"], row["NAME"]
        lat, lng = float(row["INTPTLAT"]), float(row["INTPTLONG"])
        land = float(row.get("ALAND") or 0)
        toks = norm_tokens(name)
        one = toks[:-1] if toks and toks[-1] in PLACE_SUFFIXES else toks
        full = list(toks)
        while full and full[-1] in PLACE_SUFFIXES:
            full.pop()
        for table, t in ((primary, one), (secondary, full)):
            key = (state, " ".join(t))
            if t and land >= area.get((id(table), key), -1):  # prefer the larger place on name clashes
                table[key] = (lat, lng)
                area[(id(table), key)] = land
        if "-" in name:  # "Nashville-Davidson ..." is listed as plain "Nashville" in fuel data
            alias = " ".join(norm_tokens(name.split("-")[0]))
            if alias:
                aliases.setdefault((state, alias), (lat, lng))
    for key, val in aliases.items():
        secondary.setdefault(key, val)
    return primary, secondary


def match_city(primary, secondary, state, city):
    key = (state, norm_city(city))
    return primary.get(key) or secondary.get(key)
