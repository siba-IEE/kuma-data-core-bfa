"""series_pm_eac4

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-16

Séries journalières brutes de particules fines CAMS EAC4 (ADR-0015) aux
47 provinces, 2005 à 2025 : PM2.5 (``pm2_5``) et PM10 (``pm10``), en µg/m³,
moyenne du jour UTC des huit pas de 3 h de la réanalyse, à la maille de 0,75°
la plus proche. Méthode ``reanalyse``, confiance B.

Soit 94 séries (47 provinces, 2 grandeurs) de 7 670 jours, statut ``brut``,
dans la table journalière ``mesures_ressource``. Elles servent au proxy de
salissure (modèle HSU) et au PR réaliste corrigé de la salissure, avec la pluie
journalière NASA POWER (0010). Valeurs lues dans les CSV gzip de
``seeds/donnees/`` (produits hors ligne par
``scripts/ingest_cams_eac4_journalier.py``) et validées par
``series_csv.lire_series_journalieres`` ; la migration n'accède jamais au
réseau. Mesures chargées par ``COPY``, trigger d'audit des mesures suspendu le
temps du déversement et de sa suppression (``docs/architecture/03-audit.md``,
migrations de masse). La fiche de la source ``cams_eac4``, reprise du dépôt
d'origine, prend la période servie au Burkina Faso. Garde-fous : identité de la
source, couverture exacte des provinces, nombre de mesures par grandeur et
total. ``downgrade`` supprime les mesures puis les séries et rend sa fiche à la
source.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import date
from typing import Any

import sqlalchemy as sa
from alembic import op

from kuma_data_core.db.seeds.lots_bfa import CONTRATS_PM, points_lot
from kuma_data_core.db.seeds.series_csv import ContratSerie, lire_series_journalieres

# revision identifiers, used by Alembic.
revision: str = "0013"
down_revision: str | Sequence[str] | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LOT: str = "provinces"
NB_POINTS: int = 47
NB_SERIES_ATTENDU: int = 94
NB_MESURES_ATTENDU: int = 720_980  # 47 × 2 × 7 670
TABLE_MESURES: str = "mesures_ressource"
TRIGGER_AUDIT: str = "trg_audit_mesures_ressource"
ID_SOURCE: int = 15

# Fiche de la source : valeurs du Burkina Faso, et celles du dépôt d'origine,
# rendues par ``downgrade``.
FICHE_SOURCE: dict[str, Any] = {
    "date_consultation": date(2026, 10, 16),
    "doi": "10.24381/d58bbf47",
    "notes": (
        "Réanalyse de composition atmosphérique EAC4 (ECMWF Atmospheric Composition "
        "Reanalysis 4, CAMS), servie par l'ADS Copernicus depuis 2003. Fournit les PM2.5 et "
        "PM10 de surface (kg/m³, convertis en µg/m³) au pas de 3 h, ramenés par Kuma à la "
        "moyenne du jour UTC. Entrée du proxy de salissure HSU (taux_salissure_proxy), qui "
        "consomme les PM, pas l'AOD. Confiance B (réanalyse, pas mesure directe). Maille de "
        "0,75°. Au Burkina Faso : 2005-01-01 à 2025-12-31, aux 47 provinces (ADR-0015). "
        "Licence CC BY 4.0 ; attribution : « Contains modified Copernicus Atmosphere "
        "Monitoring Service information 2005-2025 ». Référence méthodologique : Inness et "
        "al. (2019), doi:10.5194/acp-19-3515-2019."
    ),
    "metadonnees": {
        "periode_reelle": "2005-01-01 a 2025-12-31",
        "latence_reanalyse": "EAC4 servi jusqu'au 31 decembre 2025 en octobre 2026",
    },
}
FICHE_ORIGINE: dict[str, Any] = {
    "date_consultation": date(2026, 6, 18),
    "doi": None,
    "notes": (
        "Reanalyse de composition atmospherique EAC4 (ECMWF Atmospheric Composition "
        "Reanalysis 4, CAMS), servie par l'ADS Copernicus. Fournit PM2.5 et PM10 de "
        "surface (kg/m3 natif, converti ug/m3) au pas 3-horaire, agreges en moyenne "
        "journaliere par Kuma. Entree particules du modele de salissure HSU (proxy "
        "taux_salissure_proxy, Vague 5 Lot C) : le HSU consomme les PM, pas l'AOD. "
        "Confiance B derivee (modele satellitaire, pas mesure directe -> R3 ne donne pas "
        "A). Grille grossiere 0,75 deg (caveat L-SOIL-4). Couverture reelle 2021-01-01 a "
        "2025-08-31 (latence de reanalyse 10 mois). Licence Copernicus (CC-BY) ; "
        "attribution : Generated using Copernicus Atmosphere Monitoring Service "
        "Information 2026. DOI dataset et annee de publication non confirmes (non "
        "inventes) ; reference methodologique Inness et al. 2019 "
        "(doi:10.5194/acp-19-3515-2019)."
    ),
    "metadonnees": {
        "periode_reelle": "2021-01-01 a 2025-08-31",
        "latence_reanalyse": "10 mois (juin 2026 : EAC4 borne a aout 2025)",
    },
}

LIBELLES: dict[str, str] = {"pm2_5": "PM2.5", "pm10": "PM10"}
MISES_EN_GARDE: str = (
    " Pics en février et mars (harmattan) ; au sud et à l'est, en novembre et décembre,"
    " saison des feux de brousse. Sur l'ensemble des provinces, 1 % des pas de 3 h, surtout"
    " celui de 12 h UTC, sont servis à zéro par la réanalyse et gardés tels quels : 5,6 %"
    " des jours en comptent au moins un, ce qui abaisse leur moyenne, et la moyenne de"
    " l'année perd 1,5 % au plus."
)


def _note(contrat: ContratSerie) -> str:
    return (
        f"{LIBELLES[contrat.grandeur_code]} journalier {contrat.source_libelle} (moyenne du "
        f"jour UTC des huit pas de 3 h, en µg/m³), {contrat.annee_debut}-{contrat.annee_fin}, "
        f"réanalyse de composition atmosphérique de l'ECMWF. Lot « {LOT} » (ADR-0015). "
        f"Confiance {contrat.niveau_confiance}. Maille de 0,75° la plus proche, parfois "
        f"partagée par deux ou trois provinces voisines (34 mailles pour 47 provinces)."
        f"{MISES_EN_GARDE}"
    )


def _codes_series() -> list[str]:
    return [c.code_serie(code) for c in CONTRATS_PM.values() for code, *_ in points_lot(LOT)]


def _fiche(bind: sa.Connection, fiche: dict[str, Any], depuis: dict[str, Any]) -> int:
    """Remplace la fiche ``depuis`` par ``fiche`` ; une fiche modifiée entre-temps reste."""
    return bind.execute(
        sa.text(
            "UPDATE sources SET date_consultation = :d, doi = :doi, notes = :notes, "
            "metadonnees = metadonnees || CAST(:m AS jsonb), modifie_le = now() "
            "WHERE id = :id AND notes = :notes_depuis"
        ),
        {
            "d": fiche["date_consultation"],
            "doi": fiche["doi"],
            "notes": fiche["notes"],
            "m": json.dumps(fiche["metadonnees"]),
            "id": ID_SOURCE,
            "notes_depuis": depuis["notes"],
        },
    ).rowcount


def upgrade() -> None:
    bind = op.get_bind()

    code_source = bind.execute(
        sa.text("SELECT code FROM sources WHERE id = :id"), {"id": ID_SOURCE}
    ).scalar_one_or_none()
    if code_source != "cams_eac4":
        raise RuntimeError(
            f"Migration 0013 : source id {ID_SOURCE} = {code_source!r}, 'cams_eac4' attendue."
        )

    codes_loc = sorted(code for code, *_ in points_lot(LOT))
    if len(codes_loc) != NB_POINTS:
        raise RuntimeError(f"Migration 0013 : {len(codes_loc)} provinces, {NB_POINTS} attendues.")
    loc = {
        row.code: row.id
        for row in bind.execute(
            sa.text("SELECT code, id FROM localites WHERE code = ANY(:c)"), {"c": codes_loc}
        ).all()
    }
    manquants = [c for c in codes_loc if c not in loc]
    if manquants:
        raise RuntimeError(f"Migration 0013 : localité(s) introuvable(s) : {manquants!r}.")

    series_table = sa.table(
        "series_metadonnees",
        sa.column("code", sa.String),
        sa.column("libelle", sa.Text),
        sa.column("localite_id", sa.BigInteger),
        sa.column("grandeur_code", sa.String),
        sa.column("source_id", sa.BigInteger),
        sa.column("periode_debut", sa.Date),
        sa.column("periode_fin", sa.Date),
        sa.column("methode_collecte", sa.String),
        sa.column("granularite", sa.String),
        sa.column("note_publique", sa.Text),
    )
    copie = (
        f"COPY {TABLE_MESURES} "
        "(serie_id, instant_mesure, valeur, statut, niveau_confiance_derive) FROM STDIN"
    )

    op.execute(f"ALTER TABLE {TABLE_MESURES} DISABLE TRIGGER {TRIGGER_AUDIT}")
    nb_series = 0
    nb_mesures = 0
    for contrat in CONTRATS_PM.values():
        series = lire_series_journalieres(contrat, LOT)
        if [s["localite_code"] for s in series] != codes_loc:
            raise RuntimeError(
                f"Migration 0013 : {contrat.nom_fichier(LOT)} ne couvre pas exactement le lot."
            )
        op.bulk_insert(
            series_table,
            [
                {
                    "code": s["code"],
                    "libelle": s["libelle"],
                    "localite_id": loc[s["localite_code"]],
                    "grandeur_code": contrat.grandeur_code,
                    "source_id": contrat.source_id,
                    "periode_debut": contrat.periode_debut,
                    "periode_fin": contrat.periode_fin,
                    "methode_collecte": contrat.methode_collecte,
                    "granularite": contrat.granularite,
                    "note_publique": _note(contrat),
                }
                for s in series
            ],
        )
        serie_id = {
            row.code: row.id
            for row in bind.execute(
                sa.text("SELECT code, id FROM series_metadonnees WHERE code = ANY(:c)"),
                {"c": [s["code"] for s in series]},
            ).all()
        }
        lignes = [
            (serie_id[s["code"]], jour, valeur, "brut", contrat.niveau_confiance)
            for s in series
            for jour, valeur in s["mesures"]
        ]
        if len(lignes) != NB_POINTS * contrat.nb_jours:
            raise RuntimeError(
                f"Migration 0013 : {contrat.prefixe_code} : {len(lignes)} mesures, "
                f"{NB_POINTS * contrat.nb_jours} attendues."
            )
        pilote = bind.connection.driver_connection
        with pilote.cursor() as curseur, curseur.copy(copie) as flux:  # type: ignore[union-attr]
            for ligne in lignes:
                flux.write_row(ligne)
        nb_series += len(series)
        nb_mesures += len(lignes)
    op.execute(f"ALTER TABLE {TABLE_MESURES} ENABLE TRIGGER {TRIGGER_AUDIT}")

    if (nb_series, nb_mesures) != (NB_SERIES_ATTENDU, NB_MESURES_ATTENDU):
        raise RuntimeError(
            f"Migration 0013 : {nb_series} séries et {nb_mesures} mesures, "
            f"{NB_SERIES_ATTENDU} et {NB_MESURES_ATTENDU} attendues."
        )
    if _fiche(bind, FICHE_SOURCE, FICHE_ORIGINE) != 1:
        raise RuntimeError("Migration 0013 : fiche de la source cams_eac4 inattendue.")
    op.execute("ANALYZE series_metadonnees")
    op.execute(f"ANALYZE {TABLE_MESURES}")


def downgrade() -> None:
    bind = op.get_bind()
    ids = [
        row.id
        for row in bind.execute(
            sa.text("SELECT id FROM series_metadonnees WHERE code = ANY(:c)"),
            {"c": _codes_series()},
        ).all()
    ]
    if ids:
        op.execute(f"ALTER TABLE {TABLE_MESURES} DISABLE TRIGGER {TRIGGER_AUDIT}")
        bind.execute(
            sa.text(f"DELETE FROM {TABLE_MESURES} WHERE serie_id = ANY(:ids)"), {"ids": ids}
        )
        op.execute(f"ALTER TABLE {TABLE_MESURES} ENABLE TRIGGER {TRIGGER_AUDIT}")
        bind.execute(sa.text("DELETE FROM series_metadonnees WHERE id = ANY(:ids)"), {"ids": ids})
    _fiche(bind, FICHE_ORIGINE, FICHE_SOURCE)
