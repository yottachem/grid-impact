"""Stage the control variables: CPI (inflation) and county degree days (weather)."""
import json

import pandas as pd

from transform.common import STAGED, latest, write

# NOAA nClimDiv state codes (alphabetical, contiguous US) -> Census state FIPS
NOAA_TO_FIPS = {
    "01": "01", "02": "04", "03": "05", "04": "06", "05": "08", "06": "09", "07": "10", "08": "12", "09": "13",
    "10": "16", "11": "17", "12": "18", "13": "19", "14": "20", "15": "21", "16": "22", "17": "23", "18": "24",
    "19": "25", "20": "26", "21": "27", "22": "28", "23": "29", "24": "30", "25": "31", "26": "32", "27": "33",
    "28": "34", "29": "35", "30": "36", "31": "37", "32": "38", "33": "39", "34": "40", "35": "41", "36": "42",
    "37": "44", "38": "45", "39": "46", "40": "47", "41": "48", "42": "49", "43": "50", "44": "51", "45": "53",
    "46": "54", "47": "55", "48": "56",
}
# Census regions, matching the BLS CPI regional areas
REGION = {**{s: "0100" for s in "CT ME MA NH NJ NY PA RI VT".split()},
          **{s: "0200" for s in "IL IN IA KS MI MN MO NE ND OH SD WI".split()},
          **{s: "0300" for s in "AL AR DE DC FL GA KY LA MD MS NC OK SC TN TX VA WV".split()},
          **{s: "0400" for s in "AK AZ CA CO HI ID MT NV NM OR UT WA WY".split()}}


def cpi() -> pd.DataFrame:
    d = json.load(open(latest("bls_cpi", "cpi.json")))
    df = pd.DataFrame(d["data"])
    df["area_code"] = df.series_id.str[4:8]
    df["item"] = df.series_id.str[8:].map({"SA0": "all_items", "SEHF01": "electricity"})
    df["area_name"] = df.area_code.map(d["meta"]["areas"])
    df["period"] = pd.to_datetime(dict(year=df.year, month=df.month, day=1))
    return df[["series_id", "area_code", "area_name", "item", "period", "value"]]


def degree_days() -> pd.DataFrame:
    frames = []
    for kind in ("hdd", "cdd"):
        rows = []
        for line in open(latest("noaa_degree_days", f"{kind}ccy.txt")):
            head, vals = line[:11], line[11:].split()
            fips = NOAA_TO_FIPS.get(head[:2])
            if fips is None:
                continue
            year = int(head[7:11])
            if year < 2010:
                continue
            for m, v in enumerate(vals[:12], start=1):
                v = float(v)
                if v > -9999:
                    rows.append((fips + head[2:5], year, m, v))
        frames.append(pd.DataFrame(rows, columns=["county_fips", "year", "month", kind]).set_index(["county_fips", "year", "month"]))
    df = frames[0].join(frames[1], how="outer").reset_index()
    df["period"] = pd.to_datetime(dict(year=df.year, month=df.month, day=1))
    return df[["county_fips", "period", "hdd", "cdd"]]


def run() -> None:
    write(cpi(), STAGED, "cpi")
    write(degree_days(), STAGED, "degree_days_county")


if __name__ == "__main__":
    run()
