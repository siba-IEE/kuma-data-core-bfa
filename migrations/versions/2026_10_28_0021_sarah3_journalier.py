"""sarah3_journalier

Revision ID: 0021
Revises: 0020
Create Date: 2026-10-28

Rayonnement journalier SARAH-3 (ADR-0022) aux 398 localités (47 provinces et
351 communes), 2005 à 2023, en stockage dense : GHI, DNI et DHI, total du jour
UTC des valeurs horaires servies par PVGIS (base PVGIS-SARAH3, plan
horizontal), en kWh/m²/jour. Méthode ``modele_satellitaire``, confiance B.
Les heures que SARAH-3 ne sert pas sont complétées au prorata du ciel clair ;
un jour reste sans valeur quand les heures manquantes d'affilée couvrent plus
de la moitié de son ciel clair.

1 194 séries (398 localités, 3 grandeurs) de 6 939 jours ; les localités d'un
même pixel partagent la série de leur porteuse. La fiche de la source
``sarah3_monthly`` passe au Burkina Faso. La note des séries mensuelles
SARAH-3 (0006) et celle des écarts mensuels qui en dérivent (0009) donnent la
liste mesurée des mois sous-estimés. Le ``downgrade`` rend la fiche et les
notes.

Valeurs lues dans les fichiers Parquet de ``seeds/donnees/denses/`` (produits
hors ligne par ``scripts/ingest_pvgis_sarah3_journalier.py``) et validées par
``series_denses.lire_series_denses``, points interrogés comparés aux
coordonnées en base ; la migration n'accède jamais au réseau. Garde-fous :
identité de la source, couverture exacte des localités, nombre de séries, de
lignes et de valeurs, nombre de notes mises à jour.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from datetime import date
from typing import Any

import sqlalchemy as sa
from alembic import op

from kuma_data_core.db.seeds.lots_bfa import CONTRATS_SARAH3_JOURNALIERS, LOT_LOCALITES, points_lot
from kuma_data_core.db.seeds.series_csv import ContratSerie
from kuma_data_core.db.seeds.series_denses import (
    SeriesDenses,
    charger_series_denses,
    lire_series_denses,
)

# revision identifiers, used by Alembic.
revision: str = "0021"
down_revision: str | Sequence[str] | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NB_POINTS: int = 398
NB_SERIES_ATTENDU: int = 1_194
NB_LIGNES_ATTENDU: int = 22_439  # (393 + 395 + 393) porteuses × 19 années
NB_VALEURS_ATTENDU: int = 8_178_425  # porteuses × (6 939 jours - 14 jours sans valeur)
NB_NOTES_MENSUELLES: int = 796  # GHI et DNI mensuels SARAH-3 aux 398 localités
NB_NOTES_ECARTS: int = 796  # écarts mensuels du GHI et du DNI SARAH-3 à NASA POWER
ID_SOURCE: int = 11
ID_SOURCE_CALCULS: int = 10

NOMS: dict[str, str] = {
    "ghi": "Rayonnement global horizontal (GHI)",
    "dni": "Rayonnement direct normal (DNI)",
    "dhi": "Rayonnement diffus horizontal (DHI)",
}
HEURES: str = (
    " PVGIS sert, pour chaque heure, la valeur instantanée datée de hh:07 UTC, qu'il tient "
    "pour la moyenne de l'heure. Une heure que SARAH-3 ne sert pas, PVGIS la rend nulle sans "
    "la signaler : le total du jour est alors complété au prorata du ciel clair, comme le "
    "fait le CM SAF pour ses moyennes journalières. Un jour reste sans valeur quand les "
    "heures manquantes d'affilée couvrent plus de la moitié de son ciel clair. Du 2 au 11 "
    "janvier 2009, SARAH-3 ne sert qu'une heure sur deux : ces jours sont complétés. Sur "
    "les 398 localités, 125 385 jours-localités sont complétés, dont 44 443 de plus de 10 %."
)
AEROSOLS: str = (
    " Le ciel clair de SARAH-3 repose sur une climatologie d'aérosols (MACC) et ne suit pas "
    "la poussière du jour ; l'imagerie n'en saisit qu'une partie, comme un nuage."
)
MISES_EN_GARDE: dict[str, str] = {
    "ghi": (
        AEROSOLS + " Par ciel clair, son GHI égale celui de CAMS quand l'épaisseur optique des "
        "aérosols reste sous 0,2, et le dépasse de 7 % vers 0,5 et de 15 % entre 1 et 1,5. Sur "
        "les 398 localités, 2005-2023, il dépasse CAMS de 4,3 % et NASA POWER de 7,9 %."
    ),
    "dni": (
        AEROSOLS + " Par ciel clair, son DNI égale celui de CAMS quand l'épaisseur optique "
        "reste sous 0,2, le dépasse de 35 % vers 0,5 et vaut 1,9 fois le sien entre 1 et "
        "1,5. Sur les 398 localités, 2005-2023, il dépasse CAMS de 18 %, de 27 à 37 % de mars "
        "à mai, de 3 % en août. Le DNI de SARAH-3 n'a pas été évalué au sol en Afrique de "
        "l'Ouest. Il est calculé heure par heure du direct horizontal et de la hauteur du "
        "soleil : sur les mois sans heure manquante, sa moyenne mensuelle redonne le DNI "
        "mensuel de PVGIS à 1e-4 près."
    ),
    "dhi": (
        AEROSOLS + " La poussière diffuse le rayonnement direct, ce que cette climatologie "
        "ne rend pas : par ciel clair, le DHI de SARAH-3 vaut 0,75 fois celui de CAMS vers "
        "une épaisseur optique de 0,5 et 0,71 fois entre 1 et 1,5, et le dépasse de 8 % sous "
        "0,2. Sur les 398 localités, 2005-2023, il est plus faible que CAMS de 13 % et que "
        "NASA POWER de 15 %."
    ),
}
JOUR_UTC: str = (
    " Jour compté en temps universel, comme CAMS et, au Burkina Faso, NASA POWER (ADR-0021)."
)
ABSENTS: str = "Sans valeur (heures non servies d'affilée sur plus de la moitié du jour)"

# Note des séries mensuelles SARAH-3 (0006) : phrase d'origine et liste mesurée.
LACUNES_0006: str = (
    " Mois sous-estimés par des journées satellite manquantes ou partielles dans la source : "
    "janvier, mars et mai 2008, janvier et avril 2009, octobre 2016 (jusqu'à 20 % environ en "
    "janvier 2009). Valeurs non corrigées."
)
LACUNES_0021: str = (
    " Mois sous-estimés par des heures et des journées que SARAH-3 ne sert pas, comptées "
    "nulles par PVGIS : janvier 2009 (16 % environ), mai 2008 (9 %), mars 2008, avril 2009, "
    "octobre 2016, août 2009 et janvier 2008 (6 à 7 %), décembre 2014 (4 %) ; les autres "
    "mois perdent moins de 3 %. Valeurs non corrigées ; jours détaillés à l'ADR-0022."
)
# Note des écarts mensuels SARAH-3 à NASA POWER (0009) : phrase d'origine et liste
# mesurée.
ECARTS_0009: str = (
    " Six mois SARAH-3 sont abaissés par des journées satellite manquantes (janvier, mars et "
    "mai 2008, janvier et avril 2009, octobre 2016) : l'écart y est tiré vers le bas."
)
ECARTS_0021: str = (
    " Huit mois SARAH-3 sont abaissés par des heures et des journées que SARAH-3 ne sert "
    "pas (janvier, mars et mai 2008, janvier, avril et août 2009, décembre 2014, octobre "
    "2016 ; ADR-0022) : l'écart y est tiré vers le bas."
)

# Fiche de la source : état d'origine, rendu au ``downgrade``, et état du
# Burkina Faso.
FICHE_ORIGINE: dict[str, Any] = {
    "date_consultation": None,
    "url": "https://re.jrc.ec.europa.eu/api/v5_3/MRcalc",
    "titre": (
        "PVGIS-SARAH3 ICDR : Surface Solar Radiation Data Set - Heliosat, chaine MAGICSOL CM "
        "SAF / EUMETSAT (Edition 3)"
    ),
    "organisation": (
        "Satellite Application Facility on Climate Monitoring (CM SAF), EUMETSAT ; portage "
        "applicatif PVGIS par le Joint Research Centre (JRC) de la Commission europeenne."
    ),
    "notes": (
        "Chaine de retrieval MAGICSOL (Heliosat modifie Hammer et al. 2003 + gnu-MAGIC "
        "Mueller et al. 2009 + SPECMAGIC Mueller et al. 2012). Validee Afrique de l'Ouest par"
        " Sawadogo et al. 2023 (Renewable Energy 216:119066) et Kakou et al. 2025 (Remote "
        "Sensing 17(6):998). Validation Europe par Urraca et al. 2017, 2018. Edition 3 "
        "deployee depuis 2024 ; ICDR (Interim CDR) couvre 2021-present, complement de CDR "
        "(Climate Data Record) 1983-2020. Retenue en 1-7a comme source de reference "
        "inter-source pour ecart_relatif_referentiel (cf. note methodologique amont PR #53)."
    ),
}
FICHE_0021: dict[str, Any] = {
    "date_consultation": date(2026, 10, 27),
    "url": "https://re.jrc.ec.europa.eu/api/v5_3/",
    "titre": (
        "SARAH-3 : Surface Solar Radiation Data Set - Heliosat, édition 3 (CM SAF, "
        "EUMETSAT), servi par PVGIS (JRC)"
    ),
    "organisation": (
        "Satellite Application Facility on Climate Monitoring (CM SAF), EUMETSAT ; diffusion "
        "PVGIS par le Joint Research Centre (JRC) de la Commission européenne."
    ),
    "notes": (
        "Base de rayonnement SARAH-3 du CM SAF (EUMETSAT), édition 3 : méthode Heliosat sur "
        "l'imagerie Meteosat, avec HelSnow et SPECMAGIC, pixel de 0,05° ; CDR jusqu'en 2020, "
        "prolongé par l'ICDR depuis 2021, transition dont l'étude des tendances doit tenir "
        "compte (Pfeifroth et al. 2024, ESSD 16:5243 ; DOI du jeu : "
        "10.5676/EUM_SAF_CM/SARAH/V003). Le ciel clair repose sur une climatologie "
        "d'aérosols (MACC) et ne suit pas la poussière du jour, que l'imagerie ne saisit "
        "qu'en partie. Servie par PVGIS (Joint Research Centre de la Commission "
        "européenne, API v5_3, base PVGIS-SARAH3). Évaluée en Afrique de l'Ouest sur le GHI "
        "seul : Sawadogo et al. 2023 (SARAH-2, Burkina Faso et Ghana, Renewable Energy "
        "216:119066), Kakou et al. 2025 (SARAH-3, Côte d'Ivoire, Remote Sensing 17(6):998). "
        "Au Burkina Faso, 2005-2023, aux 398 localités : GHI et DNI mensuels (MRcalc, "
        "ADR-0009), consultés le 15 octobre 2026 ; GHI, DNI et DHI journaliers, totaux du "
        "jour UTC des valeurs horaires, complétés des heures que SARAH-3 ne sert pas "
        "(seriescalc, ADR-0022), consultés le 27 octobre 2026. Confiance B (modèle "
        "satellitaire). Attribution : « PVGIS © Union européenne, 2001-2026 » ; données "
        "SARAH-3 « © 2005-2023 EUMETSAT »."
    ),
}


def _fiche(bind: sa.Connection, fiche: dict[str, Any], depuis: dict[str, Any]) -> int:
    """Remplace la fiche ``depuis`` par ``fiche`` ; une fiche modifiée entre-temps reste."""
    return bind.execute(
        sa.text(
            "UPDATE sources SET date_consultation = :d, url = :url, titre = :titre, "
            "organisation = :organisation, notes = :notes, modifie_le = now() "
            "WHERE id = :id AND notes = :notes_depuis"
        ),
        {
            "d": fiche["date_consultation"],
            "url": fiche["url"],
            "titre": fiche["titre"],
            "organisation": fiche["organisation"],
            "notes": fiche["notes"],
            "id": ID_SOURCE,
            "notes_depuis": depuis["notes"],
        },
    ).rowcount


def _remplacer(
    bind: sa.Connection, motif: str, source_id: int, ancienne: str, nouvelle: str
) -> int:
    """Remplace ``ancienne`` par ``nouvelle`` dans les notes des séries ``motif`` d'une source."""
    return bind.execute(
        sa.text(
            "UPDATE series_metadonnees SET note_publique = replace(note_publique, :a, :n), "
            "modifie_le = now() "
            "WHERE code LIKE :motif AND source_id = :id AND strpos(note_publique, :a) > 0"
        ),
        {"a": ancienne, "n": nouvelle, "motif": motif, "id": source_id},
    ).rowcount


# Séries mensuelles SARAH-3 (0006) et écarts mensuels SARAH-3 à NASA POWER (0009).
MOTIF_MENSUELLES: str = "sarah3\\_%\\_mensuel\\_bfa\\_%"
MOTIF_ECARTS: str = "ecart\\_%\\_sarah3\\_nasa\\_bfa\\_%"


def _notes(contrat: ContratSerie, denses: SeriesDenses) -> dict[str, str]:
    partage = Counter(denses.representantes.values())
    notes: dict[str, str] = {}
    for code in denses.codes:
        n = partage[denses.representantes[code]]
        pixel = (
            "propre à la localité" if n == 1 else f"identique pour les {n} localités du même pixel"
        )
        notes[code] = (
            f"{NOMS[contrat.grandeur_code]} : série journalière, total du jour UTC des "
            f"valeurs horaires en kWh/m², {contrat.annee_debut}-{contrat.annee_fin}, base "
            "SARAH-3 du CM SAF (imagerie Meteosat, pixel de 0,05°) servie par PVGIS au point de "
            "la localité. Lot des 398 localités (provinces et communes), stockage dense "
            f"(ADR-0017). Confiance {contrat.niveau_confiance}. Série {pixel}."
            f"{HEURES}{MISES_EN_GARDE[contrat.grandeur_code]}{JOUR_UTC}"
        )
    return notes


def _codes_series() -> list[str]:
    return [
        c.code_serie(code)
        for c in CONTRATS_SARAH3_JOURNALIERS.values()
        for code, *_ in points_lot(LOT_LOCALITES)
    ]


def upgrade() -> None:
    bind = op.get_bind()

    code_source = bind.execute(
        sa.text("SELECT code FROM sources WHERE id = :id"), {"id": ID_SOURCE}
    ).scalar_one_or_none()
    if code_source != "sarah3_monthly":
        raise RuntimeError(
            f"Migration 0021 : source id {ID_SOURCE} = {code_source!r}, 'sarah3_monthly' attendue."
        )
    codes_loc = sorted(code for code, *_ in points_lot(LOT_LOCALITES))
    if len(codes_loc) != NB_POINTS:
        raise RuntimeError(f"Migration 0021 : {len(codes_loc)} localités, {NB_POINTS} attendues.")
    loc = {
        row.code: int(row.id)
        for row in bind.execute(
            sa.text("SELECT code, id FROM localites WHERE code = ANY(:c)"), {"c": codes_loc}
        ).all()
    }
    manquants = [c for c in codes_loc if c not in loc]
    if manquants:
        raise RuntimeError(f"Migration 0021 : localité(s) introuvable(s) : {manquants!r}.")

    totaux = [0, 0, 0]
    for contrat in CONTRATS_SARAH3_JOURNALIERS.values():
        notes = _notes(contrat, lire_series_denses(contrat, LOT_LOCALITES))
        charges = charger_series_denses(
            bind,
            contrat,
            LOT_LOCALITES,
            loc,
            notes.__getitem__,
            "kWh/m²",
            absents=ABSENTS,
            jours_cites=31,
        )
        totaux = [t + c for t, c in zip(totaux, charges, strict=True)]
    attendus = [NB_SERIES_ATTENDU, NB_LIGNES_ATTENDU, NB_VALEURS_ATTENDU]
    if totaux != attendus:
        raise RuntimeError(
            f"Migration 0021 : séries, lignes et valeurs {totaux!r}, {attendus!r} attendues."
        )
    if _fiche(bind, FICHE_0021, FICHE_ORIGINE) != 1:
        raise RuntimeError("Migration 0021 : fiche de sarah3_monthly modifiée depuis l'origine.")
    mensuelles = _remplacer(bind, MOTIF_MENSUELLES, ID_SOURCE, LACUNES_0006, LACUNES_0021)
    ecarts = _remplacer(bind, MOTIF_ECARTS, ID_SOURCE_CALCULS, ECARTS_0009, ECARTS_0021)
    if (mensuelles, ecarts) != (NB_NOTES_MENSUELLES, NB_NOTES_ECARTS):
        raise RuntimeError(
            f"Migration 0021 : {mensuelles} notes mensuelles et {ecarts} notes d'écarts mises à "
            f"jour, {NB_NOTES_MENSUELLES} et {NB_NOTES_ECARTS} attendues."
        )
    op.execute("ANALYZE series_metadonnees")
    op.execute("ANALYZE mesures_journalieres_denses")


def downgrade() -> None:
    bind = op.get_bind()
    _remplacer(bind, MOTIF_ECARTS, ID_SOURCE_CALCULS, ECARTS_0021, ECARTS_0009)
    _remplacer(bind, MOTIF_MENSUELLES, ID_SOURCE, LACUNES_0021, LACUNES_0006)
    _fiche(bind, FICHE_ORIGINE, FICHE_0021)
    ids = [
        row.id
        for row in bind.execute(
            sa.text("SELECT id FROM series_metadonnees WHERE code = ANY(:c)"),
            {"c": _codes_series()},
        ).all()
    ]
    if ids:
        bind.execute(
            sa.text("DELETE FROM mesures_journalieres_denses WHERE serie_id = ANY(:ids)"),
            {"ids": ids},
        )
        # Les séries qui lisent une porteuse d'abord, puis les porteuses.
        bind.execute(
            sa.text(
                "DELETE FROM series_metadonnees "
                "WHERE id = ANY(:ids) AND serie_porteuse_id IS NOT NULL"
            ),
            {"ids": ids},
        )
        bind.execute(sa.text("DELETE FROM series_metadonnees WHERE id = ANY(:ids)"), {"ids": ids})
