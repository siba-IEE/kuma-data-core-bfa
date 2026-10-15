"""Seeds des séries mensuelles en CSV compressé (ADR-0009).

Les séries solaires des lots (provinces, communes) sont stockées en **CSV gzip
committés** sous ``seeds/donnees/``, lus hors ligne par les migrations : aucune
migration n'accède au réseau et chaque valeur gravée est versionnée.

Un fichier par source, grandeur et lot. Colonnes :
``localite_code, latitude, longitude, annee, mois, valeur`` (valeur en
kWh/m²/jour, moyenne journalière du mois, arrondie à 4 décimales).

L'écriture est **déterministe** (lignes triées, horodatage gzip nul) : régénérer
un fichier depuis les mêmes données produit les mêmes octets. Elle passe par un
fichier temporaire, validé avant de remplacer le fichier versionné. La lecture
**valide** tout : complétude (12 mois × années du contrat, par localité), bornes
de plausibilité, doublons, coordonnées constantes par localité, localités
connues du référentiel.
"""

from __future__ import annotations

import csv
import gzip
import io
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from kuma_data_core.db.seeds.localites_bfa_departements_seed_data import (
    LOCALITES_SEED as _COMMUNES,
)
from kuma_data_core.db.seeds.localites_bfa_seed_data import LOCALITES_SEED as _LOCALITES

DOSSIER_DONNEES: Path = Path(__file__).resolve().parent / "donnees"
COLONNES: tuple[str, ...] = ("localite_code", "latitude", "longitude", "annee", "mois", "valeur")

NOMS_LOCALITES: dict[str, str] = {e["code"]: e["nom"] for e in (*_LOCALITES, *_COMMUNES)}


@dataclass(frozen=True)
class ContratSerie:
    """Contrat d'une famille de séries (une source × une grandeur)."""

    source_code: str
    source_id: int
    source_libelle: str  # pour les libellés de série, ex. "NASA POWER"
    prefixe_code: str  # préfixe du code de série, ex. "nasa_power_ghi_mensuel"
    grandeur_code: str
    methode_collecte: str
    annee_debut: int
    annee_fin: int
    borne_max: float  # kWh/m²/jour, borne de plausibilité
    niveau_confiance: str = "B"
    granularite: str = "mensuel"

    @property
    def periode_debut(self) -> str:
        return f"{self.annee_debut}-01-01"

    @property
    def periode_fin(self) -> str:
        return f"{self.annee_fin}-12-31"

    @property
    def nb_mois(self) -> int:
        return (self.annee_fin - self.annee_debut + 1) * 12

    def nom_fichier(self, lot: str) -> str:
        return f"{self.prefixe_code}_{lot}.csv.gz"

    def code_serie(self, localite_code: str) -> str:
        return f"{self.prefixe_code}_{localite_code}"


def ecrire_series(
    contrat: ContratSerie,
    lot: str,
    series: list[tuple[str, float, float, list[tuple[int, int, float]]]],
) -> Path:
    """Écrit ``(localite_code, lat, lon, mesures)`` en CSV gzip déterministe."""
    lignes: list[tuple[Any, ...]] = []
    for code, lat, lon, mesures in series:
        for annee, mois, valeur in mesures:
            lignes.append((code, lat, lon, annee, mois, round(valeur, 4)))
    lignes.sort(key=lambda r: (r[0], r[3], r[4]))
    tampon = io.StringIO()
    ecrivain = csv.writer(tampon, lineterminator="\n")
    ecrivain.writerow(COLONNES)
    ecrivain.writerows(lignes)
    DOSSIER_DONNEES.mkdir(parents=True, exist_ok=True)
    cible = DOSSIER_DONNEES / contrat.nom_fichier(lot)
    provisoire = cible.with_name(f"{cible.name}.tmp")
    with (
        provisoire.open("wb") as brut,
        gzip.GzipFile(filename="", mode="wb", fileobj=brut, mtime=0, compresslevel=9) as gz,
    ):
        gz.write(tampon.getvalue().encode("utf-8"))
    try:
        _lire(contrat, provisoire)
    except ValueError:
        provisoire.unlink()
        raise
    provisoire.replace(cible)
    return cible


def lire_series(contrat: ContratSerie, lot: str) -> list[dict[str, Any]]:
    """Relit un lot : une entrée par série, triée par localité.

    Chaque série : ``code``, ``libelle``, ``localite_code``, ``latitude``,
    ``longitude``, ``mesures`` [(annee, mois, valeur)]. Lève ``ValueError`` si le
    fichier viole le contrat.
    """
    return _lire(contrat, DOSSIER_DONNEES / contrat.nom_fichier(lot))


def _lire(contrat: ContratSerie, chemin: Path) -> list[dict[str, Any]]:
    with gzip.open(chemin, "rt", encoding="utf-8", newline="") as f:
        lecteur = csv.reader(f)
        entete = tuple(next(lecteur))
        if entete != COLONNES:
            raise ValueError(f"{chemin.name} : en-tête {entete!r}, {COLONNES!r} attendu.")
        par_loc: dict[str, dict[str, Any]] = {}
        for code, lat, lon, annee_s, mois_s, valeur_s in lecteur:
            annee, mois, valeur = int(annee_s), int(mois_s), float(valeur_s)
            if not (contrat.annee_debut <= annee <= contrat.annee_fin and 1 <= mois <= 12):
                raise ValueError(f"{chemin.name} : période hors contrat {code} {annee}-{mois}.")
            if not (0.0 < valeur <= contrat.borne_max):
                raise ValueError(f"{chemin.name} : valeur hors bornes {code} {annee}-{mois}.")
            serie = par_loc.setdefault(
                code,
                {"latitude": float(lat), "longitude": float(lon), "mesures": {}},
            )
            if (serie["latitude"], serie["longitude"]) != (float(lat), float(lon)):
                raise ValueError(f"{chemin.name} : coordonnées incohérentes pour {code}.")
            if (annee, mois) in serie["mesures"]:
                raise ValueError(f"{chemin.name} : doublon {code} {annee}-{mois}.")
            serie["mesures"][(annee, mois)] = valeur

    sortie: list[dict[str, Any]] = []
    for code in sorted(par_loc):
        if code not in NOMS_LOCALITES:
            raise ValueError(f"{chemin.name} : localité inconnue {code!r}.")
        mesures = sorted((a, m, v) for (a, m), v in par_loc[code]["mesures"].items())
        if len(mesures) != contrat.nb_mois:
            raise ValueError(
                f"{chemin.name} : {code} a {len(mesures)} mois, {contrat.nb_mois} attendus."
            )
        sortie.append(
            {
                "code": contrat.code_serie(code),
                "libelle": (
                    f"{contrat.grandeur_code.upper()} mensuel {contrat.source_libelle}, "
                    f"{NOMS_LOCALITES[code]} ({contrat.annee_debut}-{contrat.annee_fin})"
                ),
                "localite_code": code,
                "latitude": par_loc[code]["latitude"],
                "longitude": par_loc[code]["longitude"],
                "mesures": mesures,
            }
        )
    return sortie
