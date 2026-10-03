"""
Zlozenie plikow lotnisk z obiektow lotniskowych OSM wycietych z paczek Geofabrik (osmium export, GeoJSON Seq).
Kazdy obiekt trafia do najblizszego lotniska (do 8 km) z lotniska.json -> osm/<ICAO>.json.gz.

Uzycie: python zloz.py wyciete/*.geojsonseq
Dane: (c) OpenStreetMap contributors, ODbL.
"""
import glob
import gzip
import json
import math
import os
import sys

KAT = os.path.dirname(os.path.abspath(__file__))
OSM = os.path.join(KAT, "osm")
MAX_ODL_M = 8000
RODZAJE = {"runway", "taxiway", "taxilane", "apron", "terminal", "hangar", "helipad", "aerodrome", "tower", "control_tower",
           "deicing_pad", "stopway", "blast_pad", "parking_position", "gate", "holding_position", "windsock", "threshold"}


def dystans_m(a1, o1, a2, o2):
    p1, p2 = math.radians(a1), math.radians(a2)
    x = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(o2 - o1) / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(min(1.0, x)))


def zaokraglij(c):
    return [round(c[0], 6), round(c[1], 6)] if isinstance(c[0], (int, float)) else [zaokraglij(x) for x in c]


def punkt(geo):
    c = geo["coordinates"]
    while isinstance(c[0], list):
        c = c[0] if not isinstance(c[0][0], (int, float)) else c[len(c) // 2]
    return c[1], c[0]


def main():
    lotniska = json.load(open(os.path.join(KAT, "lotniska.json"), encoding="utf-8"))
    siatka = {}
    for i, (_, la, lo) in enumerate(lotniska):
        siatka.setdefault((math.floor(la), math.floor(lo)), []).append(i)

    def najblizsze(lat, lon):
        naj, odl = None, MAX_ODL_M + 1
        for dla in (-1, 0, 1):
            for dlo in (-1, 0, 1):
                for i in siatka.get((math.floor(lat) + dla, math.floor(lon) + dlo), []):
                    d = dystans_m(lat, lon, lotniska[i][1], lotniska[i][2])
                    if d < odl:
                        naj, odl = lotniska[i][0], d
        return naj if odl <= MAX_ODL_M else None

    wg_lotniska = {}
    widziane = set()
    pliki = [p for a in sys.argv[1:] for p in glob.glob(a)]
    obiekty = 0
    for p in pliki:
        with open(p, encoding="utf-8") as fh:
            for linia in fh:
                linia = linia.strip().lstrip("\x1e")
                if not linia:
                    continue
                f = json.loads(linia)
                t = f.get("properties") or {}
                rodzaj = t.get("aeroway")
                g = f.get("geometry")
                if rodzaj not in RODZAJE or not g or g["type"] not in ("Point", "LineString", "Polygon", "MultiPolygon"):
                    continue
                cecha = {"type": "Feature", "geometry": {"type": g["type"], "coordinates": zaokraglij(g["coordinates"])},
                         "properties": {"rodzaj": rodzaj, "ref": t.get("ref", ""), "nazwa": t.get("name", "")}}
                klucz = json.dumps(cecha, sort_keys=True)
                if klucz in widziane:          # obiekty z granic krajow sa w dwoch paczkach
                    continue
                widziane.add(klucz)
                ic = najblizsze(*punkt(cecha["geometry"]))
                if ic:
                    wg_lotniska.setdefault(ic, []).append(cecha)
                    obiekty += 1

    os.makedirs(OSM, exist_ok=True)
    for stary in glob.glob(os.path.join(OSM, "*.json.gz")):
        os.remove(stary)
    rozmiar = 0
    for ic, cechy in wg_lotniska.items():
        plik = os.path.join(OSM, f"{ic}.json.gz")
        with open(plik, "wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as gz:
            gz.write(json.dumps({"type": "FeatureCollection", "features": cechy}, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        rozmiar += os.path.getsize(plik)
    json.dump({"lotnisk": len(wg_lotniska), "obiektow": obiekty, "gotowe": True, "zrodlo": "geofabrik", "mb": round(rozmiar / 1e6)},
              open(os.path.join(OSM, "_postep.json"), "w"))
    print(f"GOTOWE: {len(wg_lotniska)} lotnisk, {obiekty} obiektow, {rozmiar / 1e6:.0f} MB")


if __name__ == "__main__":
    main()
