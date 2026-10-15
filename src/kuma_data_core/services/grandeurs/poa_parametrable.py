"""Calcul à la volée du POA paramétrable (grandeur F2).

Plane-of-Array (POA) calculé pour un plan d'inclinaison ``beta`` et
d'orientation ``gamma`` (azimut) à partir des composantes d'irradiance
mesurées en plan horizontal (GHI, et si disponible DNI / DHI).

Modèles retenus en v1 :

- **Modèle primaire Perez 1990** [1] : décomposition diffus du ciel en
  3 zones (isotropique de fond, circumsolaire, horizon). Utilisé
  lorsque les composantes DNI et DHI sont disponibles dans la série
  source F1.

- **Modèle fallback Liu-Jordan 1963** [2] (isotrope) : utilisé
  lorsque seul le GHI est disponible (par exemple les jours d'une série
  journalière NASA POWER antérieurs au DNI et au DHI, servis depuis
  2001). Le total du jour est décomposé par la corrélation journalière
  d'Erbs et al. 1982 [3] : indice de clarté ``KT = H / H0`` (``H0``
  irradiation extraterrestre du jour sur le plan horizontal), fraction
  diffuse ``Hd / H``, puis DNI ramené au midi solaire
  ``(H - Hd) / cos(z)``, cohérent avec la transposition au midi solaire.

Implémentation via la bibliothèque ``pvlib`` (v0.15+) pour la position
solaire et la transposition POA ; la décomposition journalière du repli est
codée ici. ``pvlib`` est citée par
PVsyst et NREL SAM comme référence industrielle. Approche midi solaire
local (jour représentatif) pour la granularité journalière - biais de
moyennage acté.

Niveau de confiance dérivé uniforme ``'B'``.

Pattern fonction publique pure ``calculer_poa_parametrable`` +
fonctions privées. Aucune dépendance SQL, testable unitairement.

Limitations documentées :

- coefficients Perez non recalibrés Afrique de l'Ouest.
- fallback Liu-Jordan dégrade la précision 10-15% sous ciel
  partiellement couvert.
- pas de prise en compte d'ombrage local.

Références bibliographiques :

[1] Perez R., Ineichen P., Seals R., Michalsky J., Stewart R. 1990.
    "Modeling daylight availability and irradiance components from
    direct and global irradiance." Solar Energy 44(5), 271-289.
    DOI : 10.1016/0038-092X(90)90055-H.

[2] Liu B.Y.H., Jordan R.C. 1963. "The long-term average performance
    of flat-plate solar-energy collectors." Solar Energy 7, 53-74.
    DOI : 10.1016/0038-092X(63)90006-9.

[3] Erbs D.G., Klein S.A., Duffie J.A. 1982. "Estimation of the diffuse
    radiation fraction for hourly, daily and monthly-average global
    radiation." Solar Energy 28(4), 293-302.
    DOI : 10.1016/0038-092X(82)90302-4.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Literal, TypedDict

import pandas as pd  # type: ignore[import-untyped]
import pvlib  # type: ignore[import-untyped]

from kuma_data_core.api.v1.schemas.grandeurs import (
    ParametresPOA,
    ResultatJournalier,
)
from kuma_data_core.services.horaire import DECALAGE_MILIEU_HEURE

# === Constantes module ====================================================

UNITE_POA: str = "kWh/m²/jour"
"""Unité de sortie POA en granularité journalière."""

NIVEAU_CONFIANCE_DERIVE_F2_V1: Literal["B"] = "B"
"""Niveau de confiance uniforme v1."""

MODELE_PEREZ: Literal["perez"] = "perez"
"""Identifiant pvlib du modèle Perez 1990."""

MODELE_ISOTROPE: Literal["isotropic"] = "isotropic"
"""Identifiant pvlib du modèle isotrope Liu-Jordan 1963."""

CONSTANTE_SOLAIRE_KW: float = 1.367
"""Constante solaire (kW/m²) des corrélations journalières (Duffie et Beckman)."""


# === TypedDict d'entree ===================================================


class MesureJourPOA(TypedDict):
    """Mesure d'irradiance journalière consommée par le calcul POA.

    ``ghi`` est obligatoire ; ``dni`` et ``dhi`` sont optionnels. Si
    ces deux derniers sont ``None``, le fallback Liu-Jordan est
    déclenché pour ce jour. Valeurs en totaux du jour (kWh/m²/jour) :
    l'indice de clarté du repli en dépend.
    """

    instant_mesure: date
    ghi: float
    dni: float | None
    dhi: float | None


class MesureHeurePOA(TypedDict):
    """Mesure d'irradiance horaire consommée par le POA en intégration horaire.

    GHI et DHI obligatoires (l'appelant n'aligne que les instants complets) ;
    le direct est reconstruit (cf. :func:`geometrie_et_direct_horaires`).
    """

    instant_mesure: datetime
    ghi: float
    dhi: float


# === Fonctions privees pures ==============================================


def _midi_solaire_utc(jour: date, longitude_deg: float) -> datetime:
    """Renvoie l'instant de midi solaire approximatif (UTC) pour un jour donné.

    Approximation pragmatique : midi solaire ≈ 12:00 UTC - longitude/15.
    Suffisant pour application du modèle POA à granularité journalière
    (biais de moyennage acté).
    """
    decalage_heures = -longitude_deg / 15.0
    return datetime(jour.year, jour.month, jour.day, 12, 0, 0, tzinfo=UTC) + timedelta(
        hours=decalage_heures
    )


def _irradiation_extraterrestre_jour(latitude_deg: float, jour: date) -> tuple[float, float]:
    """Irradiation extraterrestre du jour sur le plan horizontal.

    Renvoie ``(H0, omega_s)`` : ``H0`` en kWh/m²/jour et l'angle horaire du
    coucher du soleil ``omega_s`` en degrés (Duffie et Beckman, éq. 1.10.3).
    """
    n = jour.timetuple().tm_yday
    phi = math.radians(latitude_deg)
    delta = math.radians(23.45 * math.sin(math.radians(360.0 * (284 + n) / 365.0)))
    omega_s = math.acos(max(-1.0, min(1.0, -math.tan(phi) * math.tan(delta))))
    excentricite = 1.0 + 0.033 * math.cos(math.radians(360.0 * n / 365.0))
    h0 = (
        24.0
        / math.pi
        * CONSTANTE_SOLAIRE_KW
        * excentricite
        * (
            math.cos(phi) * math.cos(delta) * math.sin(omega_s)
            + omega_s * math.sin(phi) * math.sin(delta)
        )
    )
    return h0, math.degrees(omega_s)


def _fraction_diffuse_erbs_journaliere(kt: float, omega_s_deg: float) -> float:
    """Fraction diffuse journalière ``Hd / H`` d'Erbs et al. 1982 [3]."""
    if omega_s_deg <= 81.4:
        if kt < 0.715:
            return 1.0 - 0.2727 * kt + 2.4495 * kt**2 - 11.9514 * kt**3 + 9.3879 * kt**4
        return 0.143
    if kt < 0.722:
        return 1.0 + 0.2832 * kt - 2.5557 * kt**2 + 0.8448 * kt**3
    return 0.175


def _decomposer_jour(
    ghi_jour: float, latitude_deg: float, jour: date, zenith_midi_deg: float
) -> tuple[float, float]:
    """Décompose un total journalier GHI en ``(DNI, DHI)`` ramenés au midi solaire.

    Le DHI est le total diffus du jour ; le DNI est le direct horizontal
    du jour divisé par ``cos(z)`` au midi solaire, ce qui redonne le direct
    horizontal par la transposition au midi solaire.
    """
    h0, omega_s_deg = _irradiation_extraterrestre_jour(latitude_deg, jour)
    kt = min(max(ghi_jour / h0, 0.0), 1.0) if h0 > 0 else 0.0
    dhi = ghi_jour * min(max(_fraction_diffuse_erbs_journaliere(kt, omega_s_deg), 0.0), 1.0)
    cos_z = math.cos(math.radians(zenith_midi_deg))
    dni = (ghi_jour - dhi) / cos_z if cos_z > 0.05 else 0.0
    return dni, dhi


def _calculer_poa_jour(
    mesure: MesureJourPOA,
    latitude_deg: float,
    longitude_deg: float,
    parametres: ParametresPOA,
) -> float:
    """Calcule le POA journalier pour une mesure unique.

    Choisit dynamiquement le modèle Perez ou Liu-Jordan selon la
    disponibilité de DNI / DHI dans la mesure :

    - DNI ET DHI disponibles -> Perez 1990 [1]
    - DNI OU DHI manquant -> Liu-Jordan isotrope avec décomposition
      GHI -> (DNI estimé, DHI estimé) via Erbs 1982 [3]

    Renvoie la valeur POA dans la même unité que la GHI d'entrée
    (typiquement kWh/m²/jour pour séries journalières NASA POWER).
    """
    instant_utc = _midi_solaire_utc(mesure["instant_mesure"], longitude_deg)
    times = pd.DatetimeIndex([instant_utc])
    solpos = pvlib.solarposition.get_solarposition(times, latitude_deg, longitude_deg)

    dni_a_utiliser: float
    dhi_a_utiliser: float
    modele: str
    if mesure["dni"] is not None and mesure["dhi"] is not None:
        dni_a_utiliser = mesure["dni"]
        dhi_a_utiliser = mesure["dhi"]
        modele = MODELE_PEREZ
    else:
        # Fallback Liu-Jordan : décomposition du total journalier par la
        # corrélation journalière d'Erbs 1982 (KT = H / H0 du jour).
        dni_a_utiliser, dhi_a_utiliser = _decomposer_jour(
            mesure["ghi"],
            latitude_deg,
            mesure["instant_mesure"],
            float(solpos["zenith"].iloc[0]),
        )
        modele = MODELE_ISOTROPE

    # dni_extra (irradiance extra-atmosphérique) requise par Perez
    # (pvlib lève ValueError sans). Calculée via pvlib.irradiance.get_extra_radiation.
    dni_extra = float(pvlib.irradiance.get_extra_radiation(instant_utc))

    resultat_poa = pvlib.irradiance.get_total_irradiance(
        surface_tilt=parametres.inclinaison_deg,
        surface_azimuth=parametres.orientation_deg,
        solar_zenith=solpos["zenith"].iloc[0],
        solar_azimuth=solpos["azimuth"].iloc[0],
        dni=dni_a_utiliser,
        ghi=mesure["ghi"],
        dhi=dhi_a_utiliser,
        dni_extra=dni_extra,
        albedo=parametres.albedo_sol,
        model=modele,
    )

    poa_global = float(resultat_poa["poa_global"])
    # Garde-fou : pvlib peut retourner NaN si position solaire dégénérée
    # (nuit, polaire). Sous les tropiques, à midi solaire, sans risque.
    if pd.isna(poa_global) or poa_global < 0:
        return 0.0
    return poa_global


# === Fonction publique ====================================================


def calculer_poa_parametrable(
    mesures: Sequence[MesureJourPOA],
    latitude_deg: float,
    longitude_deg: float,
    parametres: ParametresPOA,
) -> list[ResultatJournalier]:
    """Calcule le POA paramétrable pour une série F1 source journalière.

    Itère sur les mesures journalières dans la fenêtre demandée et
    applique le modèle Perez (DNI+DHI disponibles) ou Liu-Jordan
    fallback (GHI seul). Retourne une liste ordonnée de
    :class:`ResultatJournalier`.

    Paramètres :
        mesures : séquence de mesures journalières GHI (+ DNI / DHI
            optionnels). Filtrés en amont sur la fenêtre temporelle.
        latitude_deg : latitude de la localité (degrés, plage [-90, 90]).
        longitude_deg : longitude de la localité (degrés, plage [-180, 180]).
        parametres : paramètres techniques POA fournis par l'appelant
            (inclinaison, orientation, albedo).

    Renvoie :
        Liste de :class:`ResultatJournalier` ordonnée par
        ``instant_mesure`` croissante. Liste vide si ``mesures`` est
        vide.

    Aucune dépendance SQL, idempotent, pur. Le niveau de confiance
    dérivé est uniformément ``'B'``.
    """
    resultats: list[ResultatJournalier] = []
    for mesure in mesures:
        poa_valeur = _calculer_poa_jour(
            mesure=mesure,
            latitude_deg=latitude_deg,
            longitude_deg=longitude_deg,
            parametres=parametres,
        )
        resultats.append(
            ResultatJournalier(
                instant=mesure["instant_mesure"],
                valeur=poa_valeur,
                unite=UNITE_POA,
                niveau_confiance=NIVEAU_CONFIANCE_DERIVE_F2_V1,
            )
        )
    return resultats


def geometrie_et_direct_horaires(
    index: pd.DatetimeIndex,
    ghi: pd.Series,
    dhi: pd.Series,
    latitude_deg: float,
    longitude_deg: float,
) -> tuple[pd.DataFrame, pd.Series]:
    """Position solaire au milieu de chaque heure et DNI refermé sur GHI et DHI.

    Le DNI horaire de NASA POWER ne referme pas ``GHI = DHI + DNI·cos z`` :
    aux cinq points pilotes, sur 2021-2025, ``DHI + DNI·cos z`` reste de 5,9 à
    6,9 % sous le GHI (ADR-0014). Le direct est donc reconstruit,
    ``(GHI - DHI) / cos z``, par ``pvlib.irradiance.dni`` : nul au-delà de 88°
    de zénith ou si le DHI dépasse le GHI, borné à l'éclairement
    extraterrestre. Un plan horizontal retrouve ainsi le GHI.

    Les instants suivent la convention de stockage horaire
    (``services.horaire.DECALAGE_MILIEU_HEURE``) : la géométrie est celle du
    milieu de l'heure. Renvoie la position solaire (indexée sur ``index``) et
    le DNI en W/m².
    """
    solpos = pvlib.solarposition.get_solarposition(
        index + DECALAGE_MILIEU_HEURE, latitude_deg, longitude_deg
    )
    solpos.index = index
    dni = pvlib.irradiance.dni(ghi, dhi, solpos["zenith"]).fillna(0.0)
    return solpos, dni.clip(upper=pvlib.irradiance.get_extra_radiation(index))


def calculer_poa_parametrable_horaire(
    mesures: Sequence[MesureHeurePOA],
    latitude_deg: float,
    longitude_deg: float,
    parametres: ParametresPOA,
) -> list[ResultatJournalier]:
    """Calcule le POA journalier par **intégration horaire** (modèle Perez 1990).

    Applique Perez heure par heure (géométrie solaire réelle de chaque
    heure) puis somme sur la journée calendaire (UTC) pour obtenir un POA
    journalier. Contrairement à la méthode journalière (Perez au midi
    solaire appliqué au total du jour), l'intégration horaire ne surestime
    pas le gain d'un plan incliné : elle lève le biais de moyennage
    (+16 % mesuré pour un plan incliné).

    Vectorisé via ``pvlib`` (position solaire + transposition sur tous les
    instants en une passe). Géométrie au milieu de l'heure et direct
    reconstruit sur GHI et DHI (:func:`geometrie_et_direct_horaires`) : un
    plan horizontal retrouve le GHI. Sortie : un :class:`ResultatJournalier`
    par jour présent (unité ``kWh/m²/jour``, identique à la méthode
    journalière).

    Pure (pandas/pvlib, aucune dépendance SQL), idempotente. Niveau de
    confiance dérivé uniforme ``'B'``.
    """
    if not mesures:
        return []

    index = pd.DatetimeIndex([m["instant_mesure"] for m in mesures])
    ghi = pd.Series([m["ghi"] for m in mesures], index=index, dtype=float)
    dhi = pd.Series([m["dhi"] for m in mesures], index=index, dtype=float)

    solpos, dni = geometrie_et_direct_horaires(index, ghi, dhi, latitude_deg, longitude_deg)
    dni_extra = pvlib.irradiance.get_extra_radiation(index)
    poa_global = pvlib.irradiance.get_total_irradiance(
        surface_tilt=parametres.inclinaison_deg,
        surface_azimuth=parametres.orientation_deg,
        solar_zenith=solpos["zenith"],
        solar_azimuth=solpos["azimuth"],
        dni=dni,
        ghi=ghi,
        dhi=dhi,
        dni_extra=dni_extra,
        albedo=parametres.albedo_sol,
        model=MODELE_PEREZ,
    )["poa_global"]

    # W/m² horaires (≈ Wh/m² par heure ; nuit/horizon -> NaN ou négatif clampé
    # à 0) sommés par jour -> Wh/m²/jour ; /1000 -> kWh/m²/jour.
    poa_horaire = poa_global.clip(lower=0).fillna(0.0)
    poa_par_jour = poa_horaire.groupby(poa_horaire.index.date).sum() / 1000.0

    return [
        ResultatJournalier(
            instant=jour,
            valeur=float(valeur),
            unite=UNITE_POA,
            niveau_confiance=NIVEAU_CONFIANCE_DERIVE_F2_V1,
        )
        for jour, valeur in poa_par_jour.items()
    ]
