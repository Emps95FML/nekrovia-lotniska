# Nekrovia Aviation – szczegóły lotnisk

Gotowe pliki szczegółów lotnisk (drogi kołowania, płyty, stanowiska, terminale) dla aplikacji **Nekrovia Aviation**
(towarzysz do Aerofly FS Global).

- `osm/<ICAO>.json.gz` – GeoJSON jednego lotniska (gzip), np. `osm/EPGD.json.gz`
- `osm/_postep.json` – ile lotnisk jest już gotowych
- `pobierz.py` – skrypt pobierający (Overpass API, kwadraty 5×5°, wznawiany)
- `.github/workflows/pobierz.yml` – GitHub Actions: paczka co 3 godziny, aż cały świat będzie pobrany

Pliki są udostępniane przez GitHub Pages: `https://emps95fml.github.io/nekrovia-lotniska/osm/<ICAO>.json.gz`

Dane: © OpenStreetMap contributors, ODbL – zob. [LICENCJA-DANYCH.md](LICENCJA-DANYCH.md).
