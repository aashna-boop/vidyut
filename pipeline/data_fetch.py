"""
VIDYUT — REAL DATA ACQUISITION (checkpointed; every step skips work already on disk)
====================================================================================
Sources actually used (all real, recorded / satellite-reanalysis data, nothing synthetic):

  1. Open Power System Data (OPSD) hourly time series, 2015-2020, Germany:
       DE_solar_generation_actual   (ENTSO-E transparency, MW, hourly)
       DE_solar_capacity            (installed MW, so we can normalise to capacity factor)
       DE_load_actual_entsoe_transparency (MW, hourly)
     -> data/de_hourly_2015_2020.csv

  2. INDIAN solar, hourly, 2015-2020, at a Rajasthan site (Bhadla solar park area,
     27.54N 71.92E) from NASA POWER (satellite/reanalysis-derived hourly all-sky
     irradiance, no API key needed) -> data/in_solar_nasapower_hourly.csv
     and PVGIS-ERA5 hourly PV output per kWp (EU JRC, no key) -> data/in_solar_pvgis_hourly.csv
     (PVGIS is used as a cross-check of NASA POWER, not fed to the models.)

What could NOT be obtained (see README):
  * NREL NSRDB   - developer.nrel.gov does not resolve from this machine and the API needs a key.
  * Renewables.ninja - API needs an account token (creating accounts is not something this
                        build can do on the user's behalf).
  * Grid-India / POSOCO hourly demand - only reachable as daily PDF/Excel report files behind an
                        undocumented, authenticated CMS API; no bulk hourly history is obtainable.
"""
import os, sys, json, time, urllib.request
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(HERE, "data")
RAW = os.path.join(DATA, "raw")
os.makedirs(RAW, exist_ok=True)

OPSD_URL = "https://data.open-power-system-data.org/time_series/2020-10-06/time_series_60min_singleindex.csv"
OPSD_RAW = os.path.join(RAW, "opsd_time_series_60min.csv")
DE_OUT = os.path.join(DATA, "de_hourly_2015_2020.csv")
IN_NASA = os.path.join(DATA, "in_solar_nasapower_hourly.csv")
IN_PVGIS = os.path.join(DATA, "in_solar_pvgis_hourly.csv")

IN_LAT, IN_LON = 27.54, 71.92   # Bhadla solar park area, Rajasthan


def get(url, tries=4, timeout=180):
    last = None
    for k in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as r:
                return r.read()
        except Exception as e:
            last = e
            time.sleep(3 * (k + 1))
    raise RuntimeError(f"failed after {tries} tries: {url}: {last}")


def build_de():
    if os.path.exists(DE_OUT):
        return
    if not os.path.exists(OPSD_RAW) or os.path.getsize(OPSD_RAW) < 1e8:
        print("downloading OPSD 60-min file (130 MB)...")
        with urllib.request.urlopen(OPSD_URL, timeout=600) as r, open(OPSD_RAW, "wb") as f:
            while True:
                b = r.read(1 << 20)
                if not b:
                    break
                f.write(b)
    cols = ["utc_timestamp", "DE_solar_generation_actual", "DE_solar_capacity",
            "DE_load_actual_entsoe_transparency", "DE_wind_generation_actual"]
    df = pd.read_csv(OPSD_RAW, usecols=cols, parse_dates=["utc_timestamp"])[cols]  # usecols does NOT preserve order
    df = df[(df.utc_timestamp >= "2015-01-01") & (df.utc_timestamp < "2021-01-01")].copy()
    df.columns = ["utc", "solar_mw", "solar_cap_mw", "load_mw", "wind_mw"]
    df["solar_cf"] = df.solar_mw / df.solar_cap_mw          # capacity factor 0..1
    df.to_csv(DE_OUT, index=False)
    print(f"wrote {DE_OUT}: {len(df)} hourly rows, solar non-null {df.solar_cf.notna().sum()}, load non-null {df.load_mw.notna().sum()}")


def build_in_nasa():
    if os.path.exists(IN_NASA):
        return
    parts = []
    for yr in range(2015, 2021):
        cache = os.path.join(RAW, f"nasa_{yr}.json")
        if not os.path.exists(cache):
            url = ("https://power.larc.nasa.gov/api/temporal/hourly/point?parameters=ALLSKY_SFC_SW_DWN,CLRSKY_SFC_SW_DWN,T2M"
                   f"&community=RE&longitude={IN_LON}&latitude={IN_LAT}&start={yr}0101&end={yr}1231&format=JSON&time-standard=UTC")
            open(cache, "wb").write(get(url))
            print("  NASA POWER", yr, "ok")
        j = json.load(open(cache))["properties"]["parameter"]
        d = pd.DataFrame({k: pd.Series(v) for k, v in j.items()})
        parts.append(d)
    d = pd.concat(parts)
    d.index = pd.to_datetime(d.index, format="%Y%m%d%H")
    d = d.replace(-999, np.nan)
    d.index.name = "utc"
    d.columns = ["ghi_wm2", "ghi_clear_wm2", "t2m_c"]
    d.reset_index().to_csv(IN_NASA, index=False)
    print(f"wrote {IN_NASA}: {len(d)} rows, ghi non-null {d.ghi_wm2.notna().sum()}")


def build_in_pvgis():
    if os.path.exists(IN_PVGIS):
        return
    cache = os.path.join(RAW, "pvgis_india.json")
    if not os.path.exists(cache):
        url = (f"https://re.jrc.ec.europa.eu/api/v5_2/seriescalc?lat={IN_LAT}&lon={IN_LON}"
               "&startyear=2015&endyear=2020&pvcalculation=1&peakpower=1&loss=14&outputformat=json")
        open(cache, "wb").write(get(url, timeout=300))
        print("  PVGIS ok")
    j = json.load(open(cache))["outputs"]["hourly"]
    d = pd.DataFrame(j)
    d["utc"] = pd.to_datetime(d.time, format="%Y%m%d:%H%M").dt.floor("h")
    d["pv_cf"] = d.P / 1000.0     # W per 1 kWp -> capacity factor
    d[["utc", "pv_cf", "G(i)", "T2m"]].to_csv(IN_PVGIS, index=False)
    print(f"wrote {IN_PVGIS}: {len(d)} rows")


if __name__ == "__main__":
    build_de()
    for f in (build_in_nasa, build_in_pvgis):
        try:
            f()
        except Exception as e:
            print(f"[{f.__name__} FAILED: {e}] — India solar variant will be unavailable")
    print("data ready.")
