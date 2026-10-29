#!/usr/bin/env python3
"""Ingesteur reproductible : séries horaires NASA POWER, Burkina Faso.

Récupère les valeurs horaires NASA POWER 2021-2025 (communauté ``RE``, temps
UTC) du GHI, du DNI, du DHI (``ALLSKY_SFC_SW_DWN``, ``ALLSKY_SFC_SW_DNI``,
``ALLSKY_SFC_SW_DIFF``, en Wh/m² par heure, soit la moyenne de l'heure en W/m²)
et de la température à 2 m (``T2M``, °C), et écrit un CSV gzip par grandeur
sous ``src/kuma_data_core/db/seeds/donnees/``. Les migrations relisent ces
fichiers et n'accèdent jamais au réseau.

Deux lots :

- ``pilotes`` (ADR-0014) : les cinq points pilotes ;
- ``localites`` (ADR-0026) : les 398 localités, une série par maille. Le
  script interroge chaque localité, regroupe celles dont les séries sont
  identiques (rayonnement d'un côté, température de l'autre), vérifie que
  NASA POWER sert toujours aux pilotes les valeurs de leur fichier, écrit les
  porteuses de chaque localité (``mailles_horaires``) et les séries des
  porteuses autres que les pilotes, déjà stockés.

NASA POWER date chaque valeur du début de l'heure qu'elle moyenne : la clé
``AAAAMMJJHH`` devient l'instant ``HH:00`` UTC. Une valeur de remplissage fait
échouer l'ingestion. Le script affiche le nom et la version de l'API.

Usage : ``uv run python scripts/ingest_nasa_power_horaire.py [--lot localites]``
(``--cache DOSSIER`` pour reprendre après une interruption : réponses brutes
complètes, une par point, compressées).
"""

from __future__ import annotations

import argparse
import gzip
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import numpy as np

from kuma_data_core.db.seeds.lots_bfa import (
    CONTRATS_HORAIRES,
    HORAIRE_NASA,
    LOT_HORAIRE,
    LOT_LOCALITES,
    PILOTES_HORAIRES,
    points_lot,
    points_pilotes,
)
from kuma_data_core.db.seeds.mailles_horaires import (
    GRANDEURS_RAYONNEMENT,
    ecrire_mailles,
    porteuses_par_maille,
)
from kuma_data_core.db.seeds.series_csv import (
    ContratSerie,
    ecrire_series_horaires,
    lire_series_horaires,
)
from kuma_data_core.external._http_retry import executer_get_avec_retry

URL = "https://power.larc.nasa.gov/api/temporal/hourly/point"
DELAI = 300.0
ANNEE_DEBUT = min(c.annee_debut for c in CONTRATS_HORAIRES.values())
ANNEE_FIN = max(c.annee_fin for c in CONTRATS_HORAIRES.values())


def _fetch(
    client: httpx.Client, point: tuple[str, float, float], cache: Path | None
) -> dict[str, Any]:
    code, lat, lon = point
    fichier = cache / f"nasa_power_horaire_{code}.json.gz" if cache else None
    if fichier and fichier.exists():
        en_cache: dict[str, Any] = json.loads(gzip.decompress(fichier.read_bytes()))
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
        fichier.write_bytes(gzip.compress(json.dumps(data).encode("utf-8")))
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


def _valeurs(brut: dict[str, float], cles: list[str]) -> np.ndarray:
    """Valeurs d'un paramètre aux heures ``cles``, dans leur ordre, telles que servies."""
    try:
        valeurs = np.array([brut[cle] for cle in cles], dtype=float)
    except KeyError as exc:
        raise SystemExit(f"Heure {exc.args[0]} absente de la réponse NASA POWER") from None
    if (valeurs <= -900).any():
        raise SystemExit(
            f"Valeur de remplissage NASA POWER à {cles[int(np.argmax(valeurs <= -900))]}"
        )
    return valeurs


def _pilotes(cache: Path | None) -> None:
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


def _localites(cache: Path | None) -> None:
    points = points_lot(LOT_LOCALITES)
    contrat = next(iter(CONTRATS_HORAIRES.values()))
    debut = datetime(contrat.annee_debut, 1, 1, tzinfo=UTC)
    instants = [debut + timedelta(hours=h) for h in range(contrat.nb_heures)]
    cles = [instant.strftime("%Y%m%d%H") for instant in instants]
    valeurs: dict[str, dict[str, np.ndarray]] = {}
    api: dict[str, str] | None = None
    with httpx.Client(timeout=DELAI) as client:
        for rang, (code, _, lat, lon) in enumerate(points, start=1):
            brut = _fetch(client, (code, lat, lon), cache)
            api = api or brut.get("header", {}).get("api")
            parametres = brut["properties"]["parameter"]
            valeurs[code] = {
                grandeur: _valeurs(parametres[HORAIRE_NASA[grandeur][0]], cles)
                for grandeur in CONTRATS_HORAIRES
            }
            if rang % 50 == 0:
                print(f"{rang}/{len(points)} localités")
    if api:
        print(f"API : {api['name']} {api['version']}")

    # Les pilotes portent déjà leurs séries (migration 0011) : NASA POWER doit
    # leur servir les valeurs de leur fichier, sans quoi leurs mailles
    # mêleraient deux éditions.
    for grandeur, contrat in CONTRATS_HORAIRES.items():
        for serie in lire_series_horaires(contrat, LOT_HORAIRE):
            servies = [round(float(v), 4) for v in valeurs[serie["localite_code"]][grandeur]]
            if [v for _, v in serie["mesures"]] != servies:
                raise SystemExit(
                    f"{serie['code']} : NASA POWER ne sert plus les valeurs du fichier"
                )

    rayonnement = porteuses_par_maille(
        {
            code: b"".join(series[g].tobytes() for g in GRANDEURS_RAYONNEMENT)
            for code, series in valeurs.items()
        },
        PILOTES_HORAIRES,
    )
    temperature = porteuses_par_maille(
        {code: series["t2m"].tobytes() for code, series in valeurs.items()}, PILOTES_HORAIRES
    )
    for nom, porteuses in (("rayonnement", rayonnement), ("température", temperature)):
        pilotes_lus = sorted(p for p in PILOTES_HORAIRES if porteuses[p] != p)
        if pilotes_lus:
            raise SystemExit(f"Pilotes de même maille ({nom}) : {pilotes_lus!r}")
        print(f"{nom} : {len(set(porteuses.values()))} mailles pour {len(porteuses)} localités")
    print(f"porteuses -> {ecrire_mailles(rayonnement, temperature).name}")

    coordonnees = {code: (lat, lon) for code, _, lat, lon in points}
    for grandeur, contrat in CONTRATS_HORAIRES.items():
        porteuses = rayonnement if grandeur in GRANDEURS_RAYONNEMENT else temperature
        codes = sorted(set(porteuses.values()) - set(PILOTES_HORAIRES))
        series = [
            (
                code,
                *coordonnees[code],
                [
                    (i, round(float(v), 4))
                    for i, v in zip(instants, valeurs[code][grandeur], strict=True)
                ],
            )
            for code in codes
        ]
        cible = ecrire_series_horaires(contrat, LOT_LOCALITES, series)
        print(f"{grandeur}: {len(series)} séries -> {cible.name}")


def main(lot: str, cache: Path | None) -> None:
    if cache:
        cache.mkdir(parents=True, exist_ok=True)
    if lot == LOT_HORAIRE:
        _pilotes(cache)
    else:
        _localites(cache)


if __name__ == "__main__":
    parseur = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parseur.add_argument("--lot", choices=(LOT_HORAIRE, LOT_LOCALITES), default=LOT_HORAIRE)
    parseur.add_argument("--cache", type=Path, help="dossier de cache des réponses brutes")
    arguments = parseur.parse_args()
    main(arguments.lot, arguments.cache)
