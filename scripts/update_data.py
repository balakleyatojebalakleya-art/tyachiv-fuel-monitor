#!/usr/bin/env python3
"""Fetch public Pальне UA data for Tyachiv. Prices remain regional estimates."""
import json, os, re, sys
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.parse import urlencode

BASE = "https://20.com.ua/api/v1"
OUT = "data/prices.json"
FUEL_KEYS = {
    "A95": {"a95", "95", "petrol95", "gasoline95", "regular"},
    "A92": {"a92", "92", "petrol92", "gasoline92"},
    "A95_PLUS": {"a95plus", "95plus", "premium95", "a95_plus"},
    "DIESEL": {"diesel", "dp", "dt", "dizel"},
    "DIESEL_PLUS": {"dieselplus", "dpplus", "premiumdiesel", "diesel_plus"},
    "LPG": {"lpg", "gas", "autogas", "gaz"},
}
ALIASES = {alias: fuel for fuel, aliases in FUEL_KEYS.items() for alias in aliases}

def get_json(url):
    req = Request(url, headers={"User-Agent": "TyachivFuelMonitor/1.0 (personal project)", "Accept": "application/json"})
    with urlopen(req, timeout=30) as response:
        if response.status != 200:
            raise RuntimeError(f"HTTP {response.status} for {url}")
        return json.loads(response.read().decode("utf-8"))

def norm_key(value):
    return re.sub(r"[^a-z0-9_+]", "", str(value).lower())

def collect_prices(node, found):
    if isinstance(node, dict):
        # Common shapes: {fuel: "a95", price: 55.5}, or {a95: 55.5}
        fuel_value = node.get("fuel") or node.get("fuel_type") or node.get("code")
        price_value = node.get("price") or node.get("average") or node.get("avg_price") or node.get("value")
        if fuel_value is not None and isinstance(price_value, (int, float)):
            fuel = ALIASES.get(norm_key(fuel_value))
            if fuel and price_value > 0:
                found[fuel] = float(price_value)
        for key, value in node.items():
            alias = ALIASES.get(norm_key(key))
            if alias and isinstance(value, (int, float)) and value > 0:
                found[alias] = float(value)
            elif alias and isinstance(value, dict):
                candidate = value.get("price") or value.get("average") or value.get("avg")
                if isinstance(candidate, (int, float)) and candidate > 0:
                    found[alias] = float(candidate)
            collect_prices(value, found)
    elif isinstance(node, list):
        for item in node:
            collect_prices(item, found)

def collect_stations(node, result):
    if isinstance(node, dict):
        # GeoJSON Feature or a station object
        props = node.get("properties") if isinstance(node.get("properties"), dict) else node
        name = props.get("name") or props.get("brand") or props.get("operator")
        if name:
            geom = node.get("geometry") or {}
            coords = geom.get("coordinates") if isinstance(geom, dict) else None
            address_parts = [props.get(k) for k in ("addr:street", "addr:housenumber", "addr:city")]
            address = ", ".join(str(x) for x in address_parts if x)
            result.append({
                "name": str(name),
                "address": address or "Тячів",
                "latitude": coords[1] if isinstance(coords, list) and len(coords) > 1 else props.get("lat"),
                "longitude": coords[0] if isinstance(coords, list) and len(coords) > 1 else props.get("lon"),
                "source": "OpenStreetMap",
            })
        for value in node.values():
            collect_stations(value, result)
    elif isinstance(node, list):
        for item in node:
            collect_stations(item, result)

def main():
    # Public regional endpoint and a small geographic viewport around Tyachiv.
    regional = get_json(f"{BASE}/regions/zakarpatska")
    bbox = urlencode({"south": 47.90, "west": 23.35, "north": 48.12, "east": 23.82})
    station_data = get_json(f"{BASE}/stations/bbox?{bbox}")
    prices = {}
    collect_prices(regional, prices)
    stations = []
    collect_stations(station_data, stations)
    # Deduplicate by name and coordinates.
    unique = {}
    for station in stations:
        key = (station["name"].strip().lower(), station.get("latitude"), station.get("longitude"))
        unique[key] = station
    stations = sorted(unique.values(), key=lambda x: x["name"].lower())
    payload = {
        "city": "Тячів",
        "region": "Закарпатська область",
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "source": "Пальне UA",
        "sourceUrl": "https://20.com.ua/",
        "sourceStatus": "connected" if prices or stations else "empty",
        "priceScope": "regional_average",
        "regionalPrices": prices,
        "stations": stations,
        "notes": "Ціни є середніми по Закарпатській області, а не підтвердженими цінами конкретних АЗС. Геодані АЗС: OpenStreetMap (ODbL).",
    }
    os.makedirs("data", exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"Saved {len(prices)} regional fuel prices and {len(stations)} station locations.")
    if not prices and not stations:
        raise RuntimeError("API returned no recognized regional prices or station locations; refusing to publish empty data.")

if __name__ == "__main__":
    main()
