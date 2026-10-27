"""Seeds des séries en CSV compressé (ADR-0009, ADR-0010, ADR-0013, ADR-0014).

Les séries des lots (provinces, communes) sont stockées en **CSV gzip
committés** sous ``seeds/donnees/``, lus hors ligne par les migrations : aucune
migration n'accède au réseau et chaque valeur gravée est versionnée.

Un fichier par source, grandeur, granularité et lot. Colonnes :

- séries mensuelles : ``localite_code, latitude, longitude, annee, mois, valeur``
  (moyenne journalière du mois) ;
- séries journalières : ``localite_code, latitude, longitude, date, valeur``
  (date ISO 8601, total du jour) ;
- séries horaires : ``localite_code, latitude, longitude, instant, valeur``
  (début de l'heure en UTC, ``AAAA-MM-JJTHH:00Z`` ; moyenne de l'heure).

Valeurs dans l'unité de la grandeur (kWh/m²/jour pour le rayonnement mensuel
et journalier, W/m² pour le rayonnement horaire, °C, % et mm/jour pour la
météo), arrondies à 4 décimales.

L'écriture est **déterministe** (lignes triées, horodatage gzip nul) : régénérer
un fichier depuis les mêmes données produit les mêmes octets. Elle passe par un
fichier temporaire, validé avant de remplacer le fichier versionné. La lecture
**valide** tout : complétude (tous les mois, jours civils ou heures de la
période du contrat, par localité), bornes de plausibilité, doublons,
coordonnées constantes par localité, localités connues du référentiel.
"""

from __future__ import annotations

import csv
import gzip
import io
from collections.abc import Callable, Hashable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Literal

from kuma_data_core.db.seeds.localites_bfa_departements_seed_data import (
    LOCALITES_SEED as _COMMUNES,
)
from kuma_data_core.db.seeds.localites_bfa_seed_data import LOCALITES_SEED as _LOCALITES

DOSSIER_DONNEES: Path = Path(__file__).resolve().parent / "donnees"
COLONNES: tuple[str, ...] = ("localite_code", "latitude", "longitude", "annee", "mois", "valeur")
COLONNES_JOURNALIERES: tuple[str, ...] = (
    "localite_code",
    "latitude",
    "longitude",
    "date",
    "valeur",
)

COLONNES_HORAIRES: tuple[str, ...] = (
    "localite_code",
    "latitude",
    "longitude",
    "instant",
    "valeur",
)
FORMAT_INSTANT: str = "%Y-%m-%dT%H:00Z"

NOMS_LOCALITES: dict[str, str] = {e["code"]: e["nom"] for e in (*_LOCALITES, *_COMMUNES)}
# Nom d'une grandeur dans les libellés de série, quand son code en majuscules ne convient pas.
LIBELLES_GRANDEURS: dict[str, str] = {
    "pm2_5": "PM2.5",
    "aod550": "AOD 550 nm",
    "aod550_poussiere": "AOD 550 nm des poussières",
    "aod550_organique": "AOD 550 nm de la matière organique",
    "ghi_ciel_clair": "GHI ciel clair",
    "dni_ciel_clair": "DNI ciel clair",
    "t2m_min": "T2M minimale",
    "t2m_max": "T2M maximale",
    "point_rosee_2m": "Point de rosée",
    "vent_10m": "Vent à 10 m",
    "vent_10m_max": "Vent maximal à 10 m",
    "direction_vent_10m": "Direction du vent à 10 m",
    "vent_50m": "Vent à 50 m",
    "pression_surface": "Pression de surface",
    "nebulosite": "Nébulosité",
}


@dataclass(frozen=True)
class ContratSerie:
    """Contrat d'une famille de séries (une source × une grandeur × une granularité)."""

    source_code: str
    source_id: int
    source_libelle: str  # pour les libellés de série, ex. "NASA POWER"
    prefixe_code: str  # préfixe du code de série, ex. "nasa_power_ghi_mensuel"
    grandeur_code: str
    methode_collecte: str
    annee_debut: int
    annee_fin: int
    borne_max: float  # borne de plausibilité, dans l'unité de la grandeur
    niveau_confiance: str = "B"
    granularite: Literal["mensuel", "journalier", "horaire"] = "mensuel"
    # Borne basse incluse ; sans elle, la valeur doit être strictement positive
    # (rayonnement). La pluie, par exemple, vaut souvent zéro.
    borne_min: float | None = None
    # Valeurs hors bornes que l'ingestion d'un lot dense peut écarter :
    # (localité, jour ISO). Toute autre valeur hors bornes arrête l'ingestion
    # (ADR-0017) ; les CSV n'en admettent aucune.
    ecarts_admis: frozenset[tuple[str, str]] = frozenset()

    @property
    def periode_debut(self) -> str:
        return f"{self.annee_debut}-01-01"

    @property
    def periode_fin(self) -> str:
        return f"{self.annee_fin}-12-31"

    @property
    def nb_mois(self) -> int:
        return (self.annee_fin - self.annee_debut + 1) * 12

    @property
    def nb_jours(self) -> int:
        return (date(self.annee_fin, 12, 31) - date(self.annee_debut, 1, 1)).days + 1

    @property
    def nb_heures(self) -> int:
        return self.nb_jours * 24

    def nom_fichier(self, lot: str) -> str:
        return f"{self.prefixe_code}_{lot}.csv.gz"

    def code_serie(self, localite_code: str) -> str:
        return f"{self.prefixe_code}_{localite_code}"

    def libelle_serie(self, localite_code: str) -> str:
        """Libellé public d'une série, ex. « GHI journalier NASA POWER, Fô (2019-2020) »."""
        grandeur = LIBELLES_GRANDEURS.get(self.grandeur_code, self.grandeur_code.upper())
        return (
            f"{grandeur} {self.granularite} {self.source_libelle}, "
            f"{NOMS_LOCALITES[localite_code]} ({self.annee_debut}-{self.annee_fin})"
        )


def ecrire_series(
    contrat: ContratSerie,
    lot: str,
    series: list[tuple[str, float, float, list[tuple[int, int, float]]]],
) -> Path:
    """Écrit des séries mensuelles ``(localite_code, lat, lon, mesures)`` en CSV gzip."""
    lignes: list[tuple[Any, ...]] = [
        (code, lat, lon, annee, mois, round(valeur, 4))
        for code, lat, lon, mesures in series
        for annee, mois, valeur in mesures
    ]
    lignes.sort(key=lambda r: (r[0], r[3], r[4]))
    return _ecrire(contrat, lot, COLONNES, lignes, _lire_mensuel)


def ecrire_series_horaires(
    contrat: ContratSerie,
    lot: str,
    series: list[tuple[str, float, float, list[tuple[datetime, float]]]],
) -> Path:
    """Écrit des séries horaires ``(localite_code, lat, lon, mesures)`` en CSV gzip."""
    lignes: list[tuple[Any, ...]] = [
        (code, lat, lon, _format_instant(instant), round(valeur, 4))
        for code, lat, lon, mesures in series
        for instant, valeur in mesures
    ]
    lignes.sort(key=lambda r: (r[0], r[3]))
    return _ecrire(contrat, lot, COLONNES_HORAIRES, lignes, _lire_horaire)


def ecrire_series_journalieres(
    contrat: ContratSerie,
    lot: str,
    series: list[tuple[str, float, float, list[tuple[date, float]]]],
) -> Path:
    """Écrit des séries journalières ``(localite_code, lat, lon, mesures)`` en CSV gzip."""
    lignes: list[tuple[Any, ...]] = [
        (code, lat, lon, jour.isoformat(), round(valeur, 4))
        for code, lat, lon, mesures in series
        for jour, valeur in mesures
    ]
    lignes.sort(key=lambda r: (r[0], r[3]))
    return _ecrire(contrat, lot, COLONNES_JOURNALIERES, lignes, _lire_journalier)


def lire_series(contrat: ContratSerie, lot: str) -> list[dict[str, Any]]:
    """Relit un lot mensuel : une entrée par série, triée par localité.

    Chaque série : ``code``, ``libelle``, ``localite_code``, ``latitude``,
    ``longitude``, ``mesures`` [(annee, mois, valeur)]. Lève ``ValueError`` si le
    fichier viole le contrat.
    """
    return _lire_mensuel(contrat, DOSSIER_DONNEES / contrat.nom_fichier(lot))


def lire_series_journalieres(contrat: ContratSerie, lot: str) -> list[dict[str, Any]]:
    """Relit un lot journalier : comme ``lire_series``, ``mesures`` [(date, valeur)]."""
    return _lire_journalier(contrat, DOSSIER_DONNEES / contrat.nom_fichier(lot))


def lire_series_horaires(contrat: ContratSerie, lot: str) -> list[dict[str, Any]]:
    """Relit un lot horaire : comme ``lire_series``, ``mesures`` [(instant UTC, valeur)]."""
    return _lire_horaire(contrat, DOSSIER_DONNEES / contrat.nom_fichier(lot))


def _format_instant(instant: datetime) -> str:
    utc = instant.astimezone(UTC)
    if (utc.minute, utc.second, utc.microsecond) != (0, 0, 0):
        raise ValueError(f"Instant horaire non aligné sur l'heure : {instant.isoformat()}.")
    return utc.strftime(FORMAT_INSTANT)


def _ecrire(
    contrat: ContratSerie,
    lot: str,
    entete: tuple[str, ...],
    lignes: list[tuple[Any, ...]],
    relire: Callable[[ContratSerie, Path], object],
) -> Path:
    tampon = io.StringIO()
    ecrivain = csv.writer(tampon, lineterminator="\n")
    ecrivain.writerow(entete)
    ecrivain.writerows(lignes)
    DOSSIER_DONNEES.mkdir(parents=True, exist_ok=True)
    cible = DOSSIER_DONNEES / contrat.nom_fichier(lot)
    provisoire = cible.with_name(f"{cible.name}.tmp")
    try:
        with (
            provisoire.open("wb") as brut,
            gzip.GzipFile(filename="", mode="wb", fileobj=brut, mtime=0, compresslevel=9) as gz,
        ):
            gz.write(tampon.getvalue().encode("utf-8"))
        relire(contrat, provisoire)
    except BaseException:
        provisoire.unlink(missing_ok=True)
        raise
    provisoire.replace(cible)
    return cible


def _lire_mensuel(contrat: ContratSerie, chemin: Path) -> list[dict[str, Any]]:
    def cle(champs: list[str]) -> tuple[int, int] | None:
        annee, mois = int(champs[0]), int(champs[1])
        if contrat.annee_debut <= annee <= contrat.annee_fin and 1 <= mois <= 12:
            return annee, mois
        return None

    par_loc = _lire_lignes(contrat, chemin, COLONNES, cle)
    return _series(
        contrat,
        chemin,
        par_loc,
        nombre=contrat.nb_mois,
        unite="mois",
        trier=lambda mesures: sorted((a, m, v) for (a, m), v in mesures.items()),
    )


def _lire_journalier(contrat: ContratSerie, chemin: Path) -> list[dict[str, Any]]:
    debut, fin = date(contrat.annee_debut, 1, 1), date(contrat.annee_fin, 12, 31)

    def cle(champs: list[str]) -> date | None:
        try:
            jour = date.fromisoformat(champs[0])
        except ValueError:
            jour = None
        if jour is None or jour.isoformat() != champs[0]:
            raise ValueError(f"{chemin.name} : date invalide {champs[0]!r}.")
        return jour if debut <= jour <= fin else None

    par_loc = _lire_lignes(contrat, chemin, COLONNES_JOURNALIERES, cle)
    return _series(
        contrat,
        chemin,
        par_loc,
        nombre=contrat.nb_jours,
        unite="jours",
        trier=lambda mesures: sorted(mesures.items()),
    )


def _lire_horaire(contrat: ContratSerie, chemin: Path) -> list[dict[str, Any]]:
    debut = datetime(contrat.annee_debut, 1, 1, tzinfo=UTC)
    fin = datetime(contrat.annee_fin, 12, 31, 23, tzinfo=UTC)

    def cle(champs: list[str]) -> datetime | None:
        try:
            instant = datetime.strptime(champs[0], FORMAT_INSTANT).replace(tzinfo=UTC)
        except ValueError:
            instant = None
        if instant is None or instant.strftime(FORMAT_INSTANT) != champs[0]:
            raise ValueError(f"{chemin.name} : instant invalide {champs[0]!r}.")
        return instant if debut <= instant <= fin else None

    par_loc = _lire_lignes(contrat, chemin, COLONNES_HORAIRES, cle)
    return _series(
        contrat,
        chemin,
        par_loc,
        nombre=contrat.nb_heures,
        unite="heures",
        trier=lambda mesures: sorted(mesures.items()),
    )


def _lire_lignes(
    contrat: ContratSerie,
    chemin: Path,
    colonnes: tuple[str, ...],
    cle: Callable[[list[str]], Hashable | None],
) -> dict[str, dict[str, Any]]:
    """Lit un fichier : par localité, coordonnées et mesures ``{clé: valeur}``."""
    with gzip.open(chemin, "rt", encoding="utf-8", newline="") as f:
        lecteur = csv.reader(f)
        entete = tuple(next(lecteur))
        if entete != colonnes:
            raise ValueError(f"{chemin.name} : en-tête {entete!r}, {colonnes!r} attendu.")
        par_loc: dict[str, dict[str, Any]] = {}
        for ligne in lecteur:
            if len(ligne) != len(colonnes):
                raise ValueError(
                    f"{chemin.name} : ligne {lecteur.line_num}, {len(ligne)} champs, "
                    f"{len(colonnes)} attendus."
                )
            code, lat, lon, *champs, valeur_s = ligne
            instant = "-".join(champs)
            k = cle(champs)
            if k is None:
                raise ValueError(f"{chemin.name} : période hors contrat {code} {instant}.")
            valeur = float(valeur_s)
            # Comparaisons positives : une valeur NaN échoue et se trouve refusée.
            au_dessus = valeur > 0.0 if contrat.borne_min is None else valeur >= contrat.borne_min
            if not (au_dessus and valeur <= contrat.borne_max):
                raise ValueError(f"{chemin.name} : valeur hors bornes {code} {instant}.")
            serie = par_loc.setdefault(
                code,
                {"latitude": float(lat), "longitude": float(lon), "mesures": {}},
            )
            if (serie["latitude"], serie["longitude"]) != (float(lat), float(lon)):
                raise ValueError(f"{chemin.name} : coordonnées incohérentes pour {code}.")
            if k in serie["mesures"]:
                raise ValueError(f"{chemin.name} : doublon {code} {instant}.")
            serie["mesures"][k] = valeur
    return par_loc


def _series(
    contrat: ContratSerie,
    chemin: Path,
    par_loc: dict[str, dict[str, Any]],
    *,
    nombre: int,
    unite: str,
    trier: Callable[[dict[Any, float]], list[Any]],
) -> list[dict[str, Any]]:
    """Assemble les séries d'un fichier lu, triées par localité, complètes."""
    sortie: list[dict[str, Any]] = []
    for code in sorted(par_loc):
        if code not in NOMS_LOCALITES:
            raise ValueError(f"{chemin.name} : localité inconnue {code!r}.")
        mesures = trier(par_loc[code]["mesures"])
        if len(mesures) != nombre:
            raise ValueError(f"{chemin.name} : {code} a {len(mesures)} {unite}, {nombre} attendus.")
        sortie.append(
            {
                "code": contrat.code_serie(code),
                "libelle": contrat.libelle_serie(code),
                "localite_code": code,
                "latitude": par_loc[code]["latitude"],
                "longitude": par_loc[code]["longitude"],
                "mesures": mesures,
            }
        )
    return sortie
