"""
Lista paczek OSM (Geofabrik) dla kontynentu: kraje/regiony z indeksu Geofabrik.
Uzycie: python regiony.py europe  -> wypisuje adresy .osm.pbf (po jednym w linii)
"""
import json
import sys
import urllib.request

kontynent = sys.argv[1]
idx = json.load(urllib.request.urlopen("https://download.geofabrik.de/index-v1-nogeom.json", timeout=120))
regiony = [f["properties"] for f in idx["features"]]
# paczki zbiorcze dublujace kraje (te same dane bylyby pobierane 2-3 razy)
ZBIORCZE = {"alps", "dach", "britain-and-ireland", "united-kingdom", "sea", "south-africa-and-lesotho"}
dzieci = [r for r in regiony if r.get("parent") == kontynent and "pbf" in r.get("urls", {})
          and r["id"] not in ZBIORCZE and "/" not in r["id"] and not r["id"].startswith("us-")]
if not dzieci:  # kontynent bez podzialu (np. antarctica)
    dzieci = [r for r in regiony if r["id"] == kontynent]
for r in dzieci:
    print(r["urls"]["pbf"])
