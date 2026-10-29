"""Mailles des séries horaires NASA POWER aux 398 localités (ADR-0026).

NASA POWER sert la même série horaire à toutes les localités d'une maille :
CERES SYN1deg (1°) pour le rayonnement, MERRA-2 (0,5° × 0,625°) pour la
température. Chaque maille a une série porteuse, qui porte les mesures ; les
autres localités de la maille ont une série alias, qui lit celles de sa
porteuse (``series_metadonnees.serie_porteuse_id``).

Les mailles se constatent sur les valeurs : deux localités sont de la même
maille quand leurs séries horaires 2021-2025 sont identiques, rayonnement
(GHI, DNI et DHI ensemble) d'un côté, température de l'autre. La porteuse est
le point pilote de la maille s'il y en a un, sa série étant déjà stockée
(ADR-0014), sinon la première localité de la maille dans l'ordre des codes,
comme pour les séries denses (ADR-0017).

Le fichier ``nasa_power_horaire_mailles_localites.csv`` donne, pour chaque
localité, la porteuse de son rayonnement et celle de sa température.
"""

from __future__ import annotations

import csv
from collections.abc import Collection, Hashable, Mapping
from pathlib import Path
from typing import NamedTuple

from kuma_data_core.db.seeds.series_csv import DOSSIER_DONNEES, NOMS_LOCALITES

FICHIER_MAILLES: Path = DOSSIER_DONNEES / "nasa_power_horaire_mailles_localites.csv"
COLONNES_MAILLES: tuple[str, ...] = (
    "localite_code",
    "porteuse_rayonnement",
    "porteuse_temperature",
)
GRANDEURS_RAYONNEMENT: tuple[str, ...] = ("ghi", "dni", "dhi")
GRANDEURS_TEMPERATURE: tuple[str, ...] = ("t2m",)


class MailleLocalite(NamedTuple):
    """Porteuses des séries horaires d'une localité (elle-même si elle porte)."""

    localite_code: str
    porteuse_rayonnement: str
    porteuse_temperature: str

    def porteuse(self, grandeur: str) -> str:
        """Localité porteuse de la série ``grandeur`` de cette localité."""
        if grandeur in GRANDEURS_RAYONNEMENT:
            return self.porteuse_rayonnement
        if grandeur in GRANDEURS_TEMPERATURE:
            return self.porteuse_temperature
        raise ValueError(f"Grandeur horaire sans maille : {grandeur!r}.")


def porteuses_par_maille(
    valeurs: Mapping[str, Hashable], prioritaires: Collection[str] = ()
) -> dict[str, str]:
    """Regroupe les localités de valeurs identiques et désigne la porteuse de chaque groupe.

    ``valeurs`` associe à chaque localité une clé de ses valeurs (par exemple
    les octets de ses séries). La porteuse d'un groupe est sa première localité
    ``prioritaire`` dans l'ordre des codes, sinon sa première localité.
    Renvoie, pour chaque localité, le code de sa porteuse.
    """
    groupes: dict[Hashable, list[str]] = {}
    for code in sorted(valeurs):
        groupes.setdefault(valeurs[code], []).append(code)
    porteuses: dict[str, str] = {}
    for membres in groupes.values():
        porteuse = next((c for c in membres if c in prioritaires), membres[0])
        porteuses.update(dict.fromkeys(membres, porteuse))
    return porteuses


def ecrire_mailles(rayonnement: Mapping[str, str], temperature: Mapping[str, str]) -> Path:
    """Écrit les porteuses de chaque localité, triées par code, et relit le fichier."""
    if set(rayonnement) != set(temperature):
        raise ValueError("Porteuses du rayonnement et de la température : localités différentes.")
    provisoire = FICHIER_MAILLES.with_name(f"{FICHIER_MAILLES.name}.tmp")
    try:
        with provisoire.open("w", encoding="utf-8", newline="") as f:
            ecrivain = csv.writer(f, lineterminator="\n")
            ecrivain.writerow(COLONNES_MAILLES)
            ecrivain.writerows(
                (code, rayonnement[code], temperature[code]) for code in sorted(rayonnement)
            )
        _lire(provisoire)
    except BaseException:
        provisoire.unlink(missing_ok=True)
        raise
    provisoire.replace(FICHIER_MAILLES)
    return FICHIER_MAILLES


def lire_mailles() -> list[MailleLocalite]:
    """Relit les porteuses des localités, triées par code ; ``ValueError`` si incohérent."""
    return _lire(FICHIER_MAILLES)


def _lire(chemin: Path) -> list[MailleLocalite]:
    with chemin.open(encoding="utf-8", newline="") as f:
        lecteur = csv.reader(f)
        if tuple(next(lecteur)) != COLONNES_MAILLES:
            raise ValueError(f"{chemin.name} : en-tête, {COLONNES_MAILLES!r} attendu.")
        mailles = [MailleLocalite(*ligne) for ligne in lecteur]
    codes = [m.localite_code for m in mailles]
    if codes != sorted(set(codes)):
        raise ValueError(f"{chemin.name} : localités non triées ou en double.")
    inconnues = sorted({c for m in mailles for c in m} - set(NOMS_LOCALITES))
    if inconnues:
        raise ValueError(f"{chemin.name} : localités inconnues {inconnues!r}.")
    par_code = {m.localite_code: m for m in mailles}
    for m in mailles:
        for champ in ("porteuse_rayonnement", "porteuse_temperature"):
            porteuse = getattr(m, champ)
            if porteuse not in par_code or getattr(par_code[porteuse], champ) != porteuse:
                raise ValueError(
                    f"{chemin.name} : {m.localite_code} lit {porteuse}, qui ne porte pas "
                    f"elle-même sa série ({champ})."
                )
    return mailles
