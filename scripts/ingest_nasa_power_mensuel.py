#!/usr/bin/env python3
"""Ingesteur reproductible : irradiation mensuelle NASA POWER, Burkina Faso.

Récupère, aux coordonnées des localités d'un lot (``provinces`` ou ``communes``,
ADR-0009), les moyennes mensuelles NASA POWER (communauté ``RE``) et écrit un
CSV gzip par grandeur sous ``src/kuma_data_core/db/seeds/donnees/``. Les
migrations relisent ces fichiers et n'accèdent jamais au réseau.

Grandeurs, en une requête par point :

- ``ghi`` (``ALLSKY_SFC_SW_DWN``), 1991-2025 ;
- ``dni`` (``ALLSKY_SFC_SW_DNI``), 2001-2025, NASA POWER ne servant pas le DNI
  avant 2001 (valeurs de remplissage -999) ;
- ``dhi`` (``ALLSKY_SFC_SW_DIFF``), 2001-2025, la série étant en rupture avant
  2001.

La valeur d'un mois est la moyenne journalière du mois, en kWh/m²/jour. La clé
``AAAA13`` (moyenne annuelle) n'est pas stockée. Une valeur de remplissage dans
la période d'un contrat fait échouer l'ingestion. Le script affiche le nom et la
version de l'API, à reporter dans l'attribution (README).

Usage : ``uv run python scripts/ingest_nasa_power_mensuel.py --lot communes``
(``--cache DOSSIER`` pour reprendre après une interruption : réponses brutes
complètes, une par localité).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import httpx

from kuma_data_core.db.seeds.lots_bfa import CONTRATS_NASA, LOTS, PARAMETRES_NASA, points_lot
from kuma_data_core.db.seeds.series_csv import ecrire_series
from kuma_data_core.external._http_retry import executer_get_avec_retry

URL = "https://power.larc.nasa.gov/api/temporal/monthly/point"
DELAI = 120.0
ANNEE_DEBUT = min(c.annee_debut for c in CONTRATS_NASA.values())
ANNEE_FIN = max(c.annee_fin for c in CONTRATS_NASA.values())


def _fetch(
    client: httpx.Client, lat: float, lon: float, cache: Path | None, code: str
) -> dict[str, Any]:
    fichier = cache / f"nasa_power_{code}.json" if cache else None
    if fichier and fichier.exists():
        en_cache: dict[str, Any] = json.loads(fichier.read_text())
        return en_cache
    reponse = executer_get_avec_retry(
        client=client,
        url=URL,
        query_params={
            "parameters": ",".join(PARAMETRES_NASA.values()),
            "community": "RE",
            "longitude": str(lon),
            "latitude": str(lat),
            "start": str(ANNEE_DEBUT),
            "end": str(ANNEE_FIN),
            "format": "JSON",
        },
        timeout=DELAI,
    )
    reponse.raise_for_status()
    data: dict[str, Any] = reponse.json()
    if fichier:
        fichier.write_text(json.dumps(data))
    return data


def _mesures(brut: dict[str, float], debut: int, fin: int) -> list[tuple[int, int, float]]:
    mesures: list[tuple[int, int, float]] = []
    for cle, valeur in brut.items():
        annee, mois = int(cle[:4]), int(cle[4:6])
        if mois == 13 or not debut <= annee <= fin:
            continue
        if valeur <= -900:
            raise SystemExit(f"Valeur de remplissage NASA POWER à {annee}-{mois:02d}")
        mesures.append((annee, mois, round(float(valeur), 4)))
    mesures.sort()
    attendu = (fin - debut + 1) * 12
    if len(mesures) != attendu:
        raise SystemExit(f"Attendu {attendu} mois, obtenu {len(mesures)}")
    return mesures


def main(lot: str, cache: Path | None) -> None:
    if cache:
        cache.mkdir(parents=True, exist_ok=True)
    points = points_lot(lot)
    bruts: dict[str, dict[str, Any]] = {}
    with httpx.Client(timeout=DELAI) as client:
        for i, (code, _, lat, lon) in enumerate(points, 1):
            bruts[code] = _fetch(client, lat, lon, cache, code)
            if i % 50 == 0:
                print(f"{i}/{len(points)} points")
    api = bruts[points[0][0]].get("header", {}).get("api")
    if api:
        print(f"API : {api['name']} {api['version']}")
    for grandeur, contrat in CONTRATS_NASA.items():
        parametre = PARAMETRES_NASA[grandeur]
        series = [
            (
                code,
                lat,
                lon,
                _mesures(
                    bruts[code]["properties"]["parameter"][parametre],
                    contrat.annee_debut,
                    contrat.annee_fin,
                ),
            )
            for code, _, lat, lon in points
        ]
        cible = ecrire_series(contrat, lot, series)
        print(f"{grandeur}: {len(series)} séries -> {cible.name}")


if __name__ == "__main__":
    parseur = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parseur.add_argument("--lot", required=True, choices=LOTS)
    parseur.add_argument("--cache", type=Path, help="dossier de cache des réponses brutes")
    args = parseur.parse_args()
    main(args.lot, args.cache)
