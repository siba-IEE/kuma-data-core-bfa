#!/usr/bin/env python3
"""Ingesteur reproductible : séries journalières NASA POWER, Burkina Faso.

Récupère, aux coordonnées des 47 provinces (lot ``provinces``), les valeurs
journalières NASA POWER (communauté ``RE``) d'une famille de grandeurs et écrit
un CSV gzip par grandeur sous ``src/kuma_data_core/db/seeds/donnees/``. Les
migrations relisent ces fichiers et n'accèdent jamais au réseau.

Familles, en une requête par point :

- ``rayonnement`` (ADR-0010), total du jour en kWh/m²/jour : ``ghi``
  (``ALLSKY_SFC_SW_DWN``) 1991-2025, ``dni`` (``ALLSKY_SFC_SW_DNI``) et ``dhi``
  (``ALLSKY_SFC_SW_DIFF``) 2001-2025 ;
- ``meteo`` (ADR-0013), 1991-2025 : ``t2m`` (``T2M``, moyenne du jour en °C),
  ``rh2m`` (``RH2M``, %) et ``precipitation`` (``PRECTOTCORR``, mm/jour).

Une valeur de remplissage dans la période d'un contrat fait échouer
l'ingestion. Le script affiche le nom et la version de l'API, à reporter dans
l'attribution (README).

Usage : ``uv run python scripts/ingest_nasa_power_journalier.py --famille meteo
--lot provinces`` (``--cache DOSSIER`` pour reprendre après une interruption :
réponses brutes complètes, une par localité et par famille).
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import httpx

from kuma_data_core.db.seeds.lots_bfa import (
    CONTRATS_METEO_JOURNALIERS,
    CONTRATS_NASA_JOURNALIERS,
    LOTS_JOURNALIERS,
    METEO_NASA,
    PARAMETRES_NASA,
    points_lot,
)
from kuma_data_core.db.seeds.series_csv import ContratSerie, ecrire_series_journalieres
from kuma_data_core.external._http_retry import executer_get_avec_retry

URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
DELAI = 120.0


@dataclass(frozen=True)
class Famille:
    contrats: dict[str, ContratSerie]
    parametres: dict[str, str]  # grandeur -> paramètre NASA POWER
    cache: str  # préfixe des réponses brutes en cache

    @property
    def annee_debut(self) -> int:
        return min(c.annee_debut for c in self.contrats.values())

    @property
    def annee_fin(self) -> int:
        return max(c.annee_fin for c in self.contrats.values())


FAMILLES: dict[str, Famille] = {
    "rayonnement": Famille(CONTRATS_NASA_JOURNALIERS, PARAMETRES_NASA, "nasa_power_journalier"),
    "meteo": Famille(
        CONTRATS_METEO_JOURNALIERS,
        {grandeur: parametre for grandeur, (parametre, *_) in METEO_NASA.items()},
        "nasa_power_meteo_journalier",
    ),
}


def _fetch(
    client: httpx.Client,
    famille: Famille,
    point: tuple[str, float, float],
    cache: Path | None,
) -> dict[str, Any]:
    code, lat, lon = point
    fichier = cache / f"{famille.cache}_{code}.json" if cache else None
    if fichier and fichier.exists():
        en_cache: dict[str, Any] = json.loads(fichier.read_text())
        return en_cache
    reponse = executer_get_avec_retry(
        client=client,
        url=URL,
        query_params={
            "parameters": ",".join(famille.parametres.values()),
            "community": "RE",
            "longitude": str(lon),
            "latitude": str(lat),
            "start": f"{famille.annee_debut}0101",
            "end": f"{famille.annee_fin}1231",
            "format": "JSON",
        },
        timeout=DELAI,
    )
    reponse.raise_for_status()
    data: dict[str, Any] = reponse.json()
    if fichier:
        fichier.write_text(json.dumps(data))
    return data


def _mesures(brut: dict[str, float], contrat: ContratSerie) -> list[tuple[date, float]]:
    mesures: list[tuple[date, float]] = []
    for cle, valeur in brut.items():
        jour = date(int(cle[:4]), int(cle[4:6]), int(cle[6:8]))
        if not contrat.annee_debut <= jour.year <= contrat.annee_fin:
            continue
        if valeur <= -900:
            raise SystemExit(f"Valeur de remplissage NASA POWER le {jour.isoformat()}")
        mesures.append((jour, round(float(valeur), 4)))
    mesures.sort()
    if len(mesures) != contrat.nb_jours:
        raise SystemExit(f"Attendu {contrat.nb_jours} jours, obtenu {len(mesures)}")
    return mesures


def main(nom_famille: str, lot: str, cache: Path | None) -> None:
    famille = FAMILLES[nom_famille]
    if cache:
        cache.mkdir(parents=True, exist_ok=True)
    points = points_lot(lot)
    bruts: dict[str, dict[str, Any]] = {}
    with httpx.Client(timeout=DELAI) as client:
        for i, (code, _, lat, lon) in enumerate(points, 1):
            bruts[code] = _fetch(client, famille, (code, lat, lon), cache)
            if i % 10 == 0:
                print(f"{i}/{len(points)} points")
    api = bruts[points[0][0]].get("header", {}).get("api")
    if api:
        print(f"API : {api['name']} {api['version']}")
    for grandeur, contrat in famille.contrats.items():
        parametre = famille.parametres[grandeur]
        series = [
            (code, lat, lon, _mesures(bruts[code]["properties"]["parameter"][parametre], contrat))
            for code, _, lat, lon in points
        ]
        cible = ecrire_series_journalieres(contrat, lot, series)
        print(f"{grandeur}: {len(series)} séries -> {cible.name}")


if __name__ == "__main__":
    parseur = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parseur.add_argument("--famille", required=True, choices=sorted(FAMILLES))
    parseur.add_argument("--lot", required=True, choices=LOTS_JOURNALIERS)
    parseur.add_argument("--cache", type=Path, help="dossier de cache des réponses brutes")
    args = parseur.parse_args()
    main(args.famille, args.lot, args.cache)
