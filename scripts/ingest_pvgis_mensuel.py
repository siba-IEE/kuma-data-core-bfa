#!/usr/bin/env python3
"""Ingesteur reproductible : GHI et DNI mensuels PVGIS (SARAH-3, ERA5), Burkina Faso.

Récupère, en une requête par point, l'irradiation globale horizontale (GHI,
``H(h)_m``) et l'irradiation directe normale (DNI, ``Hb(n)_m``, option
``mr_dni=1``) mensuelles de PVGIS (JRC, API v5_3 ``MRcalc``), pour la base
``PVGIS-SARAH3`` (satellite, source ``sarah3_monthly``) ou ``PVGIS-ERA5``
(réanalyse, source ``era5_pvgis``), aux localités d'un lot (ADR-0009). Écrit un
CSV gzip par grandeur sous ``src/kuma_data_core/db/seeds/donnees/`` ; les
migrations n'accèdent jamais au réseau.

PVGIS renvoie des irradiations mensuelles totales (kWh/m²/mois), ramenées en
moyenne journalière (division par le nombre de jours du mois) pour l'unité des
grandeurs ``ghi`` et ``dni`` (kWh/m²/jour). Période : 2005-2023, dernière
année servie par l'API.

Usage : ``uv run python scripts/ingest_pvgis_mensuel.py --base sarah3 --lot communes``
(``--cache DOSSIER`` pour reprendre après une interruption : réponses brutes,
une par base et par localité).
"""

from __future__ import annotations

import argparse
import calendar
import json
from pathlib import Path
from typing import Any

import httpx

from kuma_data_core.db.seeds.lots_bfa import CONTRATS_ERA5, CONTRATS_SARAH3, LOTS, points_lot
from kuma_data_core.db.seeds.series_csv import ContratSerie, ecrire_series
from kuma_data_core.external._http_retry import executer_get_avec_retry

URL = "https://re.jrc.ec.europa.eu/api/v5_3/MRcalc"
DELAI = 120.0
BASES: dict[str, tuple[str, dict[str, ContratSerie]]] = {
    "sarah3": ("PVGIS-SARAH3", CONTRATS_SARAH3),
    "era5": ("PVGIS-ERA5", CONTRATS_ERA5),
}
COLONNES: dict[str, str] = {"ghi": "H(h)_m", "dni": "Hb(n)_m"}


def _fetch(
    client: httpx.Client,
    raddatabase: str,
    debut: int,
    fin: int,
    point: tuple[str, float, float],
    cache: Path | None,
) -> list[dict[str, Any]]:
    code, lat, lon = point
    fichier = cache / f"{raddatabase}_{code}.json" if cache else None
    if fichier and fichier.exists():
        donnees: list[dict[str, Any]] = json.loads(fichier.read_text())
        return donnees
    reponse = executer_get_avec_retry(
        client=client,
        url=URL,
        query_params={
            "lat": str(lat),
            "lon": str(lon),
            "raddatabase": raddatabase,
            "horirrad": "1",
            "mr_dni": "1",
            "startyear": str(debut),
            "endyear": str(fin),
            "outputformat": "json",
        },
        timeout=DELAI,
    )
    reponse.raise_for_status()
    mensuel: list[dict[str, Any]] = reponse.json()["outputs"]["monthly"]
    if fichier:
        fichier.write_text(json.dumps(mensuel))
    return mensuel


def _mesures(
    brut: list[dict[str, Any]], colonne: str, contrat: ContratSerie
) -> list[tuple[int, int, float]]:
    mesures: list[tuple[int, int, float]] = []
    for ligne in brut:
        annee, mois = int(ligne["year"]), int(ligne["month"])
        total = ligne.get(colonne)
        if total is None or float(total) <= 0:
            raise SystemExit(f"Valeur {colonne} absente ou non physique à {annee}-{mois:02d}")
        mesures.append((annee, mois, round(float(total) / calendar.monthrange(annee, mois)[1], 4)))
    mesures.sort()
    if len(mesures) != contrat.nb_mois:
        raise SystemExit(f"Attendu {contrat.nb_mois} mois, obtenu {len(mesures)}")
    return mesures


def main(base: str, lot: str, cache: Path | None) -> None:
    raddatabase, contrats = BASES[base]
    if cache:
        cache.mkdir(parents=True, exist_ok=True)
    debut = min(c.annee_debut for c in contrats.values())
    fin = max(c.annee_fin for c in contrats.values())
    points = points_lot(lot)
    bruts: dict[str, list[dict[str, Any]]] = {}
    with httpx.Client(timeout=DELAI) as client:
        for i, (code, _, lat, lon) in enumerate(points, 1):
            bruts[code] = _fetch(client, raddatabase, debut, fin, (code, lat, lon), cache)
            if i % 50 == 0:
                print(f"{i}/{len(points)} points")
    for grandeur, contrat in contrats.items():
        series = [
            (code, lat, lon, _mesures(bruts[code], COLONNES[grandeur], contrat))
            for code, _, lat, lon in points
        ]
        cible = ecrire_series(contrat, lot, series)
        print(f"{base} {grandeur}: {len(series)} séries -> {cible.name}")


if __name__ == "__main__":
    parseur = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parseur.add_argument("--base", required=True, choices=sorted(BASES))
    parseur.add_argument("--lot", required=True, choices=LOTS)
    parseur.add_argument("--cache", type=Path, help="dossier de cache des réponses brutes")
    args = parseur.parse_args()
    main(args.base, args.lot, args.cache)
