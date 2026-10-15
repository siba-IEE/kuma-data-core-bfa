#!/usr/bin/env python3
"""Ingesteur reproductible : séries horaires NASA POWER, Burkina Faso.

Récupère, aux coordonnées des cinq points pilotes (ADR-0014), les valeurs
horaires NASA POWER 2021-2025 (communauté ``RE``, temps UTC) du GHI, du DNI,
du DHI (``ALLSKY_SFC_SW_DWN``, ``ALLSKY_SFC_SW_DNI``, ``ALLSKY_SFC_SW_DIFF``,
en Wh/m² par heure, soit la moyenne de l'heure en W/m²) et de la température à
2 m (``T2M``, °C), et écrit un CSV gzip par grandeur sous
``src/kuma_data_core/db/seeds/donnees/``. Les migrations relisent ces fichiers
et n'accèdent jamais au réseau.

NASA POWER date chaque valeur du début de l'heure qu'elle moyenne : la clé
``AAAAMMJJHH`` devient l'instant ``HH:00`` UTC. Une valeur de remplissage fait
échouer l'ingestion. Le script affiche le nom et la version de l'API.

Usage : ``uv run python scripts/ingest_nasa_power_horaire.py`` (``--cache
DOSSIER`` pour reprendre après une interruption : réponses brutes complètes,
une par point).
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from kuma_data_core.db.seeds.lots_bfa import (
    CONTRATS_HORAIRES,
    HORAIRE_NASA,
    LOT_HORAIRE,
    points_pilotes,
)
from kuma_data_core.db.seeds.series_csv import ContratSerie, ecrire_series_horaires
from kuma_data_core.external._http_retry import executer_get_avec_retry

URL = "https://power.larc.nasa.gov/api/temporal/hourly/point"
DELAI = 300.0
ANNEE_DEBUT = min(c.annee_debut for c in CONTRATS_HORAIRES.values())
ANNEE_FIN = max(c.annee_fin for c in CONTRATS_HORAIRES.values())


def _fetch(
    client: httpx.Client, point: tuple[str, float, float], cache: Path | None
) -> dict[str, Any]:
    code, lat, lon = point
    fichier = cache / f"nasa_power_horaire_{code}.json" if cache else None
    if fichier and fichier.exists():
        en_cache: dict[str, Any] = json.loads(fichier.read_text())
        return en_cache
    reponse = executer_get_avec_retry(
        client=client,
        url=URL,
        query_params={
            "parameters": ",".join(parametre for parametre, *_ in HORAIRE_NASA.values()),
            "community": "RE",
            "longitude": str(lon),
            "latitude": str(lat),
            "start": f"{ANNEE_DEBUT}0101",
            "end": f"{ANNEE_FIN}1231",
            "format": "JSON",
            "time-standard": "UTC",
        },
        timeout=DELAI,
    )
    reponse.raise_for_status()
    data: dict[str, Any] = reponse.json()
    if fichier:
        fichier.write_text(json.dumps(data))
    return data


def _mesures(brut: dict[str, float], contrat: ContratSerie) -> list[tuple[datetime, float]]:
    mesures: list[tuple[datetime, float]] = []
    for cle, valeur in brut.items():
        instant = datetime.strptime(cle, "%Y%m%d%H").replace(tzinfo=UTC)
        if not contrat.annee_debut <= instant.year <= contrat.annee_fin:
            continue
        if valeur <= -900:
            raise SystemExit(f"Valeur de remplissage NASA POWER à {instant.isoformat()}")
        mesures.append((instant, round(float(valeur), 4)))
    mesures.sort()
    if len(mesures) != contrat.nb_heures:
        raise SystemExit(f"Attendu {contrat.nb_heures} heures, obtenu {len(mesures)}")
    return mesures


def main(cache: Path | None) -> None:
    if cache:
        cache.mkdir(parents=True, exist_ok=True)
    points = points_pilotes()
    with httpx.Client(timeout=DELAI) as client:
        bruts = {code: _fetch(client, (code, lat, lon), cache) for code, _, lat, lon in points}
    premier = bruts[points[0][0]]
    api = premier.get("header", {}).get("api")
    if api:
        print(f"API : {api['name']} {api['version']}, temps {premier['header']['time_standard']}")
    for grandeur, contrat in CONTRATS_HORAIRES.items():
        parametre = HORAIRE_NASA[grandeur][0]
        series = [
            (code, lat, lon, _mesures(bruts[code]["properties"]["parameter"][parametre], contrat))
            for code, _, lat, lon in points
        ]
        cible = ecrire_series_horaires(contrat, LOT_HORAIRE, series)
        print(f"{grandeur}: {len(series)} séries -> {cible.name}")


if __name__ == "__main__":
    parseur = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parseur.add_argument("--cache", type=Path, help="dossier de cache des réponses brutes")
    main(parseur.parse_args().cache)
