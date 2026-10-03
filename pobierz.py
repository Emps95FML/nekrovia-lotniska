"""
Szczegoly lotnisk swiata z OpenStreetMap (drogi kolowania, plyty, stanowiska, terminale, miejsca oczekiwania...)
dla aplikacji Nekrovia Aviation. Wynik: osm/<ICAO>.json.gz (GeoJSON, skompresowany).

Uruchamiane przez GitHub Actions w paczkach (LIMIT_S sekund na raz). Swiat jest dzielony na kwadraty 5x5 stopni
(tylko te z lotniskami); kwadrat to jedno zapytanie do Overpass API, zbyt duzy dzieli sie na 4.
Zrobione kwadraty sa zapisane w postep/ - kolejne uruchomienie zaczyna tam, gdzie skonczylo poprzednie.

Dane: (c) OpenStreetMap contributors, licencja ODbL (zob. LICENCJA-DANYCH.md).
"""
import gzip
import json
import math
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

KAT = os.path.dirname(os.path.abspath(__file__))
OSM = os.path.join(KAT, "osm")
POSTEP = os.path.join(KAT, "postep")
LIMIT_S = float(os.environ.get("LIMIT_S", "18000"))
SERWERY = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]
PRZERWA = 3.0           # sekundy miedzy zapytaniami (grzecznosc wobec Overpass)
MAX_ODL_M = 8000        # obiekt nalezy do lotniska, jesli lezy blizej niz 8 km

WAYS = ("runway|taxiway|taxilane|apron|terminal|hangar|helipad|aerodrome|tower|control_tower|deicing_pad|stopway|"
        "blast_pad|parking_position|gate|holding_position")
NODES = "parking_position|gate|holding_position|windsock|threshold|helipad"
RELS = "aerodrome|apron|terminal|runway|taxiway|hangar"
# zamkniete linie tych rodzajow to powierzchnie (jak w aplikacji, SzczegolyLotnisk.kt)
POWIERZCHNIE = {"aerodrome", "apron", "terminal", "hangar", "helipad", "deicing_pad", "baggage_claim",
                "runway", "tower", "control_tower", "stopway", "blast_pad"}


def zapytanie(s, w, n, e):
    b = f"{s},{w},{n},{e}"
    return (f'[out:json][timeout:240][maxsize:1073741824];('
            f'way["aeroway"~"^({WAYS})$"]({b});'
            f'node["aeroway"~"^({NODES})$"]({b});'
            f'relation["aeroway"~"^({RELS})$"]({b}););out geom;')


def pobierz(s, w, n, e, nr=[0]):
    """Elementy OSM z kwadratu albo None (za duzy - trzeba podzielic)."""
    for proba in range(8):
        url = SERWERY[nr[0] % len(SERWERY)]
        req = urllib.request.Request(url, data=urllib.parse.urlencode({"data": zapytanie(s, w, n, e)}).encode(),
                                     headers={"User-Agent": "NekroviaAviation/1.0 (prebuild lotnisk, github.com/Emps95FML/nekrovia-lotniska)"})
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                dane = json.load(r)
            uwaga = dane.get("remark", "").lower()
            if "runtime error" in uwaga or "out of memory" in uwaga or "timed out" in uwaga:
                return None
            return dane["elements"]
        except urllib.error.HTTPError as ex:
            if ex.code in (429, 502, 503, 504):
                nr[0] += 1; time.sleep(15 * (proba + 1)); continue
            if ex.code == 400:
                return None
            nr[0] += 1; time.sleep(15)
        except Exception as ex:  # siec, timeout, zly JSON
            print("   blad:", ex, "- ponawiam", flush=True)
            nr[0] += 1; time.sleep(15 * (proba + 1))
    return None


def na_geojson(e):
    t = e.get("tags", {})
    rodzaj = t.get("aeroway")
    if not rodzaj:
        return None
    wl = {"rodzaj": rodzaj, "ref": t.get("ref", ""), "nazwa": t.get("name", "")}
    if e["type"] == "node":
        geo = {"type": "Point", "coordinates": [round(e["lon"], 6), round(e["lat"], 6)]}
    elif e["type"] == "way" and "geometry" in e:
        wsp = [[round(p["lon"], 6), round(p["lat"], 6)] for p in e["geometry"]]
        zamkniety = len(wsp) > 3 and wsp[0] == wsp[-1]
        powierzchnia = rodzaj in POWIERZCHNIE or t.get("area") == "yes"
        geo = {"type": "Polygon", "coordinates": [wsp]} if zamkniety and powierzchnia else {"type": "LineString", "coordinates": wsp}
    elif e["type"] == "relation":
        pier = [[[round(p["lon"], 6), round(p["lat"], 6)] for p in c["geometry"]] for c in e.get("members", [])
                if c.get("role") == "outer" and c.get("geometry")]
        pier = [r for r in pier if len(r) > 3 and r[0] == r[-1]]
        if not pier:
            return None
        geo = {"type": "MultiPolygon", "coordinates": [[r] for r in pier]}
    else:
        return None
    return {"type": "Feature", "geometry": geo, "properties": wl}


def punkt(geo):
    c = geo["coordinates"]
    while isinstance(c[0], list):
        c = c[0] if not isinstance(c[0][0], (int, float)) else c[len(c) // 2]
    return c[1], c[0]


def dystans_m(a1, o1, a2, o2):
    p1, p2 = math.radians(a1), math.radians(a2)
    x = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(o2 - o1) / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(min(1.0, x)))


def zapisz_lotnisko(icao, nowe):
    """Dopisuje obiekty do osm/<ICAO>.json.gz (bez powtorzen z granic kwadratow)."""
    plik = os.path.join(OSM, f"{icao}.json.gz")
    cechy = []
    if os.path.exists(plik):
        with gzip.open(plik, "rt", encoding="utf-8") as fh:
            cechy = json.load(fh)["features"]
    widziane = {json.dumps(c, sort_keys=True) for c in cechy}
    for c in nowe:
        k = json.dumps(c, sort_keys=True)
        if k not in widziane:
            widziane.add(k); cechy.append(c)
    with open(plik, "wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as gz:
        gz.write(json.dumps({"type": "FeatureCollection", "features": cechy}, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def main():
    os.makedirs(OSM, exist_ok=True); os.makedirs(POSTEP, exist_ok=True)
    start = time.time()
    lotniska = json.load(open(os.path.join(KAT, "lotniska.json"), encoding="utf-8"))   # [[icao, lat, lon], ...]
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

    # kwadraty 5x5 z lotniskami; podzielone kwadraty pamietane w postep/podzielone.json
    plik_podz = os.path.join(POSTEP, "podzielone.json")
    podzielone = set(map(tuple, json.load(open(plik_podz)))) if os.path.exists(plik_podz) else set()
    kolejka = sorted({(math.floor(la / 5) * 5, math.floor(lo / 5) * 5) for _, la, lo in lotniska})
    kolejka = [(float(s), float(w), float(s + 5), float(w + 5)) for s, w in kolejka]
    wszystkie = len(kolejka)
    zrobione = 0
    while kolejka:
        if time.time() - start > LIMIT_S:
            print(f"Limit czasu - koniec paczki. Zostalo {len(kolejka)} kwadratow w kolejce.", flush=True)
            break
        s, w, n, e = kolejka.pop(0)
        if (s, w, n, e) in podzielone:
            h = (n - s) / 2
            kolejka[:0] = [(s, w, s + h, w + h), (s, w + h, s + h, e), (s + h, w, n, w + h), (s + h, w + h, n, e)]
            continue
        znacznik = os.path.join(POSTEP, f"{s}_{w}_{n}_{e}.ok")
        if os.path.exists(znacznik):
            zrobione += 1
            continue
        t0 = time.time()
        elementy = pobierz(s, w, n, e)
        if elementy is None:
            if n - s <= 0.3125:
                print(f"!! kwadrat {s},{w} ({n - s} st.) nie do pobrania - pomijam", flush=True)
                open(znacznik, "w").write("pominiety")
                continue
            podzielone.add((s, w, n, e))
            json.dump(sorted(podzielone), open(plik_podz, "w"))
            h = (n - s) / 2
            kolejka[:0] = [(s, w, s + h, w + h), (s, w + h, s + h, e), (s + h, w, n, w + h), (s + h, w + h, n, e)]
            print(f"   kwadrat {s},{w} ({n - s} st.) za duzy - dziele na 4", flush=True)
            continue
        przypisane = {}
        for el in elementy:
            f = na_geojson(el)
            if not f:
                continue
            ic = najblizsze(*punkt(f["geometry"]))
            if ic:
                przypisane.setdefault(ic, []).append(f)
        for ic, cechy in przypisane.items():
            zapisz_lotnisko(ic, cechy)
        open(znacznik, "w").close()
        zrobione += 1
        print(f"[{zrobione}] {s},{w} ({n - s} st.): {len(elementy)} obiektow, {len(przypisane)} lotnisk "
              f"({time.time() - t0:.0f} s), w kolejce {len(kolejka)}", flush=True)
        time.sleep(PRZERWA)

    pliki = [p for p in os.listdir(OSM) if p.endswith(".json.gz")]
    gotowe = not kolejka
    json.dump({"lotnisk": len(pliki), "gotowe": gotowe, "kwadraty_5st": wszystkie, "czas": int(time.time())},
              open(os.path.join(OSM, "_postep.json"), "w"))
    print(f"Lotnisk ze szczegolami: {len(pliki)}{' - SWIAT GOTOWY' if gotowe else ''}", flush=True)


if __name__ == "__main__":
    sys.exit(main())
