"""cams_radiation_journalier

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-27

Rayonnement journalier CAMS Radiation (ADR-0020) aux 398 localités (47
provinces et 351 communes), 2005 à 2025, en stockage dense : GHI, DNI et DHI
tous temps, GHI et DNI par ciel clair, total du jour UTC en kWh/m²/jour.
Méthode ``modele_satellitaire``, confiance B.

Deux grandeurs ajoutées au référentiel (``ghi_ciel_clair``,
``dni_ciel_clair``, stockées), retirées au ``downgrade``. 1 990 séries
(398 localités, 5 grandeurs) de 7 670 jours. Le service est au point : seules
quatre provinces, au même point que leur commune chef-lieu, lisent la série de
celle-ci ; 1 970 séries porteuses, 41 370 lignes annuelles et 15 104 026
valeurs dans ``mesures_journalieres_denses``. Les jours de 2005 et 2006 que
le service ne sert pas tous temps (GHI, DNI, DHI : 1 978 jours-localités par
grandeur, 0,06 %) restent sans valeur et sont listés dans les notes. La fiche de la source ``cams_radiation``, reprise
du dépôt d'origine, prend les séries du Burkina Faso (mensuelles et
journalières) et leurs dates de consultation ; le ``downgrade`` la rend à son
état d'origine.

Valeurs lues dans les fichiers Parquet de ``seeds/donnees/denses/`` (produits
hors ligne par ``scripts/ingest_cams_radiation_journalier.py``) et validées
par ``series_denses.lire_series_denses``, points interrogés comparés aux
coordonnées en base ; la migration n'accède jamais au réseau. Garde-fous :
identité de la source, couverture exacte des localités, nombre de séries, de
lignes et de valeurs. ``downgrade`` supprime les mesures, les séries, puis
les grandeurs, et rend sa fiche à la source.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Sequence
from datetime import date
from typing import Any

import sqlalchemy as sa
from alembic import op

from kuma_data_core.db.seeds.lots_bfa import CONTRATS_CAMS_JOURNALIERS, LOT_LOCALITES, points_lot
from kuma_data_core.db.seeds.series_csv import ContratSerie
from kuma_data_core.db.seeds.series_denses import (
    SeriesDenses,
    charger_series_denses,
    lire_series_denses,
)

# revision identifiers, used by Alembic.
revision: str = "0019"
down_revision: str | Sequence[str] | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NB_POINTS: int = 398
NB_SERIES_ATTENDU: int = 1_990
NB_LIGNES_ATTENDU: int = 41_370  # 5 grandeurs × 394 porteuses × 21 années
NB_VALEURS_ATTENDU: int = 15_104_026  # 5 × 394 × 7 670, moins 3 × 1 958 jours non servis
ID_SOURCE: int = 13

# Grandeurs ajoutées au référentiel : (libellé, description).
NOUVELLES_GRANDEURS: dict[str, tuple[str, str]] = {
    "ghi_ciel_clair": (
        "Irradiation globale horizontale par ciel clair",
        "Irradiation globale horizontale qu'on recevrait sans nuage, avec les aérosols "
        "et la vapeur d'eau du jour (modèle McClear), en kWh/m²/jour. Plafond du GHI "
        "tous temps ; leur rapport mesure la nébulosité. Donnée brute CAMS Radiation "
        "(ADR-0020).",
    ),
    "dni_ciel_clair": (
        "Irradiation directe normale par ciel clair",
        "Irradiation directe normale qu'on recevrait sans nuage, avec les aérosols et "
        "la vapeur d'eau du jour (modèle McClear), en kWh/m²/jour. Donnée brute CAMS "
        "Radiation (ADR-0020).",
    ),
}
# Grandeur : nom dans la note publique.
NOMS: dict[str, str] = {
    "ghi": "Rayonnement global horizontal (GHI)",
    "dni": "Rayonnement direct normal (DNI)",
    "dhi": "Rayonnement diffus horizontal (DHI)",
    "ghi_ciel_clair": "Rayonnement global horizontal par ciel clair",
    "dni_ciel_clair": "Rayonnement direct normal par ciel clair",
}
MISES_EN_GARDE: dict[str, str] = {
    "ghi": (
        " Le GHI est la somme exacte du direct horizontal et du diffus ; un jour sur "
        "cinq, sans nuage détecté, il égale le GHI par ciel clair."
    ),
    "dni": " Un jour très couvert, le DNI peut être presque nul.",
    "dhi": "",
    "ghi_ciel_clair": " Calculé tous les jours, nuages exclus ; aucun jour sans valeur.",
    "dni_ciel_clair": " Calculé tous les jours, nuages exclus ; aucun jour sans valeur.",
}
# Fiche de la source : état d'origine, rendu au ``downgrade``, et état du
# Burkina Faso. Seules les clés de métadonnées modifiées y figurent.
FICHE_ORIGINE: dict[str, Any] = {
    "date_consultation": date(2026, 6, 16),
    "notes": (
        "Service de rayonnement solaire CAMS (Copernicus Atmosphere Monitoring Service) : "
        "méthode Heliosat-4 pour le ciel réel (all-sky) et McClear pour le ciel clair, à "
        "partir des images Meteosat (MSG/IODC) et des champs d'aérosols / vapeur d'eau CAMS. "
        "Référence méthode : Qu et al. (2017), « Fast radiative transfer parameterisation "
        "for assessing the surface solar irradiance: the Heliosat-4 method », "
        "Meteorologische Zeitschrift 26(1), 33-57. DOI du dataset : 10.24381/5cab0912 "
        "(catalogue ADS Copernicus, section citation de la page dataset). Distribution ADS "
        "Copernicus. Attribution requise (CC-BY) : « Generated using Copernicus Atmosphere "
        "Monitoring Service Information 2026 ». Vague 4 Lot B : DNI all-sky aérosol-corrigé "
        "(BNI), 3ᵉ référence d'écart inter-source (enjeu Harmattan). Consulté le 2026-06-16."
    ),
    "metadonnees": {
        "sky_type_ingere": "observed_cloud (all-sky)",
        "grandeur_ingeree": "BNI (DNI all-sky, aerosol-corrige)",
        "pas_temporel_ingere": "1month (agregat mensuel natif)",
    },
}
FICHE_0019: dict[str, Any] = {
    "date_consultation": date(2026, 10, 27),
    "notes": (
        "Service de rayonnement solaire CAMS (Copernicus Atmosphere Monitoring Service), "
        "version 4.6 : méthode Heliosat-4 pour le ciel réel et McClear pour le ciel clair, à "
        "partir des images Meteosat et des champs d'aérosols et de vapeur d'eau CAMS, "
        "interrogé au point de chaque localité. Référence méthode : Qu et al. (2017), « Fast "
        "radiative transfer parameterisation for assessing the surface solar irradiance: the "
        "Heliosat-4 method », Meteorologische Zeitschrift 26(1), 33-57. DOI du dataset : "
        "10.24381/5cab0912. Distribution ADS Copernicus. Au Burkina Faso, 2005-2025, aux "
        "398 localités : GHI, DNI et DHI mensuels (ADR-0011), consultés le 15 octobre 2026 ; "
        "GHI, DNI et DHI journaliers, avec le GHI et le DNI par ciel clair (ADR-0020), "
        "consultés le 27 octobre 2026. Confiance B (modèle satellitaire). Licence CC BY 4.0 ; "
        "attribution : « Contains modified Copernicus Atmosphere Monitoring Service "
        "information 2005-2025 »."
    ),
    "metadonnees": {
        "sky_type_ingere": "observed_cloud (tous temps, colonnes Clear sky pour le ciel clair)",
        "grandeur_ingeree": "GHI, BNI (DNI), DHI ; Clear sky GHI et Clear sky BNI au journalier",
        "pas_temporel_ingere": "1month (ADR-0011) et 1day (ADR-0020)",
    },
}
JOUR_UTC: str = (
    " Jour compté en temps universel, de 0 h à 24 h UTC, quand NASA POWER compte en "
    "heure solaire locale."
)


def _notes(contrat: ContratSerie, denses: SeriesDenses) -> dict[str, str]:
    partage = Counter(denses.representantes.values())
    notes: dict[str, str] = {}
    for code in denses.codes:
        n = partage[denses.representantes[code]]
        point = (
            "propre à la localité" if n == 1 else f"identique pour les {n} localités du même point"
        )
        notes[code] = (
            f"{NOMS[contrat.grandeur_code]} : série journalière {contrat.source_libelle} "
            f"(total du jour UTC, en kWh/m²), {contrat.annee_debut}-{contrat.annee_fin}, "
            f"CAMS Radiation Service {denses.source['version']} (Heliosat-4 sur imagerie "
            "Meteosat, McClear pour le ciel clair), interrogé au point de la localité. "
            "Lot des 398 localités (provinces et communes), stockage dense (ADR-0017). "
            f"Confiance {contrat.niveau_confiance}. Série {point}."
            f"{MISES_EN_GARDE[contrat.grandeur_code]}{JOUR_UTC}"
        )
    return notes


def _fiche(bind: sa.Connection, fiche: dict[str, Any], depuis: dict[str, Any]) -> int:
    """Remplace la fiche ``depuis`` par ``fiche`` ; une fiche modifiée entre-temps reste."""
    return bind.execute(
        sa.text(
            "UPDATE sources SET date_consultation = :d, notes = :notes, "
            "metadonnees = metadonnees || CAST(:m AS jsonb), modifie_le = now() "
            "WHERE id = :id AND notes = :notes_depuis"
        ),
        {
            "d": fiche["date_consultation"],
            "notes": fiche["notes"],
            "m": json.dumps(fiche["metadonnees"]),
            "id": ID_SOURCE,
            "notes_depuis": depuis["notes"],
        },
    ).rowcount


def _codes_series() -> list[str]:
    return [
        c.code_serie(code)
        for c in CONTRATS_CAMS_JOURNALIERS.values()
        for code, *_ in points_lot(LOT_LOCALITES)
    ]


def upgrade() -> None:
    bind = op.get_bind()

    code_source = bind.execute(
        sa.text("SELECT code FROM sources WHERE id = :id"), {"id": ID_SOURCE}
    ).scalar_one_or_none()
    if code_source != "cams_radiation":
        raise RuntimeError(
            f"Migration 0019 : source id {ID_SOURCE} = {code_source!r}, 'cams_radiation' attendue."
        )
    unite = bind.execute(
        sa.text("SELECT id FROM unites WHERE code = 'kwh_par_m2_jour'")
    ).scalar_one()
    op.bulk_insert(
        sa.table(
            "grandeurs_referentiel",
            sa.column("code", sa.String),
            sa.column("libelle", sa.Text),
            sa.column("unite_id", sa.BigInteger),
            sa.column("famille", sa.String),
            sa.column("strategie_calcul", sa.String),
            sa.column("version_formule_actuelle", sa.Integer),
            sa.column("description", sa.Text),
        ),
        [
            {
                "code": code,
                "libelle": libelle,
                "unite_id": unite,
                "famille": "F1",
                "strategie_calcul": "stockee",
                "version_formule_actuelle": 1,
                "description": description,
            }
            for code, (libelle, description) in NOUVELLES_GRANDEURS.items()
        ],
    )

    codes_loc = sorted(code for code, *_ in points_lot(LOT_LOCALITES))
    if len(codes_loc) != NB_POINTS:
        raise RuntimeError(f"Migration 0019 : {len(codes_loc)} localités, {NB_POINTS} attendues.")
    loc = {
        row.code: int(row.id)
        for row in bind.execute(
            sa.text("SELECT code, id FROM localites WHERE code = ANY(:c)"), {"c": codes_loc}
        ).all()
    }
    manquants = [c for c in codes_loc if c not in loc]
    if manquants:
        raise RuntimeError(f"Migration 0019 : localité(s) introuvable(s) : {manquants!r}.")

    totaux = [0, 0, 0]
    for contrat in CONTRATS_CAMS_JOURNALIERS.values():
        notes = _notes(contrat, lire_series_denses(contrat, LOT_LOCALITES))
        charges = charger_series_denses(
            bind, contrat, LOT_LOCALITES, loc, notes.__getitem__, "kWh/m²"
        )
        totaux = [t + c for t, c in zip(totaux, charges, strict=True)]
    attendus = [NB_SERIES_ATTENDU, NB_LIGNES_ATTENDU, NB_VALEURS_ATTENDU]
    if totaux != attendus:
        raise RuntimeError(
            f"Migration 0019 : séries, lignes et valeurs {totaux!r}, {attendus!r} attendues."
        )
    if _fiche(bind, FICHE_0019, FICHE_ORIGINE) != 1:
        raise RuntimeError("Migration 0019 : fiche de cams_radiation modifiée depuis l'origine.")
    op.execute("ANALYZE series_metadonnees")
    op.execute("ANALYZE mesures_journalieres_denses")


def downgrade() -> None:
    bind = op.get_bind()
    _fiche(bind, FICHE_ORIGINE, FICHE_0019)
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
    bind.execute(
        sa.text("DELETE FROM grandeurs_referentiel WHERE code = ANY(:c)"),
        {"c": list(NOUVELLES_GRANDEURS)},
    )
