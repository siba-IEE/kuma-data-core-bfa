"""cams_radiation_horaire

Revision ID: 0022
Revises: 0021
Create Date: 2026-10-28

Rayonnement horaire CAMS Radiation (ADR-0023) aux cinq points pilotes
(Ouagadougou, Dédougou, Dori, Kaya, Koupéla), 2021 à 2025 : GHI, DNI et DHI
tous temps et GHI par ciel clair, irradiation intégrée sur l'heure UTC en
Wh/m², soit la moyenne de l'heure en W/m². Chaque valeur est datée du début
de l'heure, comme les séries horaires NASA POWER (ADR-0014). Méthode
``modele_satellitaire``, confiance B.

Soit 20 séries (5 points, 4 grandeurs) de 43 824 heures, dans
``mesures_ressource_horaires``. Valeurs lues dans les CSV gzip de
``seeds/donnees/`` (produits hors ligne par
``scripts/ingest_cams_radiation_horaire.py``) et validées par
``series_csv.lire_series_horaires`` ; la migration n'accède jamais au réseau.

Le contrôle qualité horaire, doctrine v1 (ADR-0014), s'applique dans la même
migration : plausibilité BSRN, fermeture et ratio diffus pour le GHI, le DNI
et le DHI de chaque point ; plausibilité du GHI pour le GHI par ciel clair.
Une ligne qui passe les tests durs devient ``valide_auto``. La fiche de la
source ``cams_radiation`` ajoute l'horaire. Mesures chargées et requalifiées
trigger d'audit suspendu (``docs/architecture/03-audit.md``). ``downgrade``
supprime les mesures et les séries, et rend sa fiche à la source.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from collections.abc import Sequence
from datetime import date
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.orm import Session

from kuma_data_core.db.seeds.lots_bfa import CONTRATS_CAMS_HORAIRES, LOT_HORAIRE, points_pilotes
from kuma_data_core.db.seeds.series_csv import ContratSerie, lire_series_horaires
from kuma_data_core.editorial.statuts import transition_autorisee
from kuma_data_core.services.horaire import DECALAGE_MILIEU_HEURE
from kuma_data_core.services.qualite.qc_horaire import VERSION_DOCTRINE_QC, executer_qc_horaire

# revision identifiers, used by Alembic.
revision: str = "0022"
down_revision: str | Sequence[str] | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NB_POINTS: int = 5
NB_SERIES_ATTENDU: int = 20
NB_MESURES_ATTENDU: int = 876_480  # 5 × 4 × 43 824
ID_SOURCE: int = 13
TABLE_MESURES: str = "mesures_ressource_horaires"
TRIGGER_AUDIT: str = "trg_audit_mesures_ressource_horaires"

NOMS: dict[str, str] = {
    "ghi": "GHI",
    "dni": "DNI",
    "dhi": "DHI",
    "ghi_ciel_clair": "GHI par ciel clair",
}


def _journalier(moyen: str, clair: str, couvert: str) -> str:
    """Accord d'une série tous temps avec le journalier CAMS (ADR-0020), en kWh/m²/jour."""
    return (
        f" Cumulées par jour UTC, les heures redonnent la série journalière CAMS à {moyen} "
        f"kWh/m²/jour près en moyenne : {clair} les jours clairs (indice de ciel clair d'au "
        f"moins 0,9), {couvert} les jours couverts (sous 0,6), quand le ciel clair s'y retrouve "
        "à l'arrondi près. L'indice de fiabilité de CAMS n'est pas repris."
    )


MISES_EN_GARDE: dict[str, str] = {
    "ghi": _journalier("0,02", "0,007", "0,08"),
    "dni": _journalier("0,03", "0,02", "0,08")
    + (
        " Aux heures du lever et du coucher, des DNI dépassent le seuil « extrêmement rare » "
        "du contrôle qualité : le soleil est sous l'horizon au milieu de l'heure, où le "
        "contrôle prend sa géométrie."
    ),
    "dhi": _journalier("0,01", "0,008", "0,03"),
    "ghi_ciel_clair": (
        " Contrôlé avec les seules bornes de plausibilité du GHI, sans test de fermeture. "
        "Cumulé par jour UTC, il redonne la série journalière CAMS à l'arrondi près."
    ),
}

# Fiche de la source : état laissé par la 0019, rendu au ``downgrade``, et état
# après l'horaire.
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
        "grandeur_ingeree": "GHI, BNI (DNI), DHI ; Clear sky GHI et Clear sky BNI au journalier",
        "pas_temporel_ingere": "1month (ADR-0011) et 1day (ADR-0020)",
    },
}
FICHE_0022: dict[str, Any] = {
    "date_consultation": date(2026, 10, 28),
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
        "consultés le 27 octobre 2026. GHI, DNI, DHI et GHI par ciel clair horaires "
        "2021-2025 aux cinq points pilotes (ADR-0023), consultés les 27 et 28 octobre 2026. "
        "Confiance B (modèle satellitaire). Licence CC BY 4.0 ; attribution : « Contains "
        "modified Copernicus Atmosphere Monitoring Service information 2005-2025 »."
    ),
    "metadonnees": {
        "grandeur_ingeree": (
            "GHI, BNI (DNI), DHI ; Clear sky GHI et Clear sky BNI au journalier, Clear sky GHI "
            "à l'horaire"
        ),
        "pas_temporel_ingere": "1month (ADR-0011), 1day (ADR-0020) et 1hour (ADR-0023)",
    },
}


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


def _note(contrat: ContratSerie) -> str:
    return (
        f"{NOMS[contrat.grandeur_code]} horaire {contrat.source_libelle} (Wh/m² sur l'heure, "
        "soit sa moyenne en W/m² ; heure commençant à l'instant indiqué, UTC), "
        f"{contrat.annee_debut}-{contrat.annee_fin}, CAMS Radiation Service v4.6 "
        "(Heliosat-4 sur imagerie Meteosat, McClear pour le ciel clair), interrogé au point. "
        f"Points pilotes (ADR-0014, ADR-0023). Confiance {contrat.niveau_confiance}."
        f"{MISES_EN_GARDE[contrat.grandeur_code]}"
    )


def _codes_series() -> list[str]:
    return [
        c.code_serie(code) for c in CONTRATS_CAMS_HORAIRES.values() for code, *_ in points_pilotes()
    ]


def _charger(bind: sa.Connection, loc: dict[str, int]) -> tuple[int, int]:
    """Insère les séries et verse leurs mesures en statut ``brut`` ; renvoie (séries, mesures)."""
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
    nb_series = nb_mesures = 0
    for contrat in CONTRATS_CAMS_HORAIRES.values():
        series = lire_series_horaires(contrat, LOT_HORAIRE)
        if [s["localite_code"] for s in series] != sorted(loc):
            raise RuntimeError(
                f"Migration 0022 : {contrat.nom_fichier(LOT_HORAIRE)} ne couvre pas exactement "
                "les points pilotes."
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
            (serie_id[s["code"]], instant, valeur, "brut", contrat.niveau_confiance)
            for s in series
            for instant, valeur in s["mesures"]
        ]
        pilote = bind.connection.driver_connection
        with pilote.cursor() as curseur, curseur.copy(copie) as flux:  # type: ignore[union-attr]
            for ligne in lignes:
                flux.write_row(ligne)
        nb_series += len(series)
        nb_mesures += len(lignes)
    return nb_series, nb_mesures


def _controler(bind: sa.Connection) -> int:
    """Applique le contrôle qualité v1 aux séries du lot ; renvoie le nombre de lignes requalifiées."""
    verdicts = []
    with Session(bind=bind) as session:
        for code, _, latitude, longitude in points_pilotes():
            series = {
                row.grandeur_code: row.id
                for row in bind.execute(
                    sa.text(
                        "SELECT s.grandeur_code, s.id FROM series_metadonnees s "
                        "JOIN localites l ON l.id = s.localite_id "
                        "WHERE l.code = :c AND s.code = ANY(:codes)"
                    ),
                    {"c": code, "codes": _codes_series()},
                ).all()
            }
            if set(series) != set(CONTRATS_CAMS_HORAIRES):
                raise RuntimeError(
                    f"Migration 0022 : séries horaires de {code} : {sorted(series)!r}."
                )
            # Tous temps : plausibilité et tests croisés ; ciel clair : plausibilité du GHI.
            tous_temps = {g: series[g] for g in ("ghi", "dni", "dhi")}
            for jeu in (tous_temps, {"ghi": series["ghi_ciel_clair"]}):
                verdicts += executer_qc_horaire(
                    session, jeu, latitude, longitude, decalage=DECALAGE_MILIEU_HEURE
                )
    if len(verdicts) != NB_MESURES_ATTENDU:
        raise RuntimeError(
            f"Migration 0022 : {len(verdicts)} verdicts, {NB_MESURES_ATTENDU} attendus."
        )
    bilan = Counter(v.statut_cible for v in verdicts)
    logging.getLogger("alembic.runtime.migration").info(
        "QC horaire %s : %d lignes, %d valide_auto (dont %d avec drapeaux), %d rejetées",
        VERSION_DOCTRINE_QC,
        len(verdicts),
        bilan["valide_auto"],
        sum(1 for v in verdicts if v.statut_cible == "valide_auto" and v.flags),
        len(verdicts) - bilan["valide_auto"],
    )
    bind.execute(
        sa.text(
            "CREATE TEMPORARY TABLE qc_verdicts "
            "(id bigint PRIMARY KEY, statut varchar(16) NOT NULL, commentaire text NOT NULL)"
        )
    )
    pilote = bind.connection.driver_connection
    with (
        pilote.cursor() as curseur,  # type: ignore[union-attr]
        curseur.copy("COPY qc_verdicts (id, statut, commentaire) FROM STDIN") as flux,
    ):
        for verdict in verdicts:
            flux.write_row((verdict.row_id, verdict.statut_cible, verdict.commentaire()))
    mises_a_jour = bind.execute(
        sa.text(
            f"UPDATE {TABLE_MESURES} m SET statut = v.statut, "
            "commentaire_editorial = v.commentaire, modifie_le = now() "
            "FROM qc_verdicts v WHERE m.id = v.id AND m.statut = 'brut'"
        )
    ).rowcount
    bind.execute(sa.text("DROP TABLE qc_verdicts"))
    return int(mises_a_jour)


def upgrade() -> None:
    bind = op.get_bind()
    if VERSION_DOCTRINE_QC != "v1" or not transition_autorisee("brut", "valide_auto"):
        raise RuntimeError("Migration 0022 : doctrine QC v1 et transition brut -> valide_auto.")
    code_source = bind.execute(
        sa.text("SELECT code FROM sources WHERE id = :id"), {"id": ID_SOURCE}
    ).scalar_one_or_none()
    if code_source != "cams_radiation":
        raise RuntimeError(
            f"Migration 0022 : source id {ID_SOURCE} = {code_source!r}, 'cams_radiation' attendue."
        )
    codes_loc = sorted(code for code, *_ in points_pilotes())
    if len(codes_loc) != NB_POINTS:
        raise RuntimeError(
            f"Migration 0022 : {len(codes_loc)} points pilotes, {NB_POINTS} attendus."
        )
    loc = {
        row.code: int(row.id)
        for row in bind.execute(
            sa.text("SELECT code, id FROM localites WHERE code = ANY(:c)"), {"c": codes_loc}
        ).all()
    }
    manquants = [c for c in codes_loc if c not in loc]
    if manquants:
        raise RuntimeError(f"Migration 0022 : localité(s) introuvable(s) : {manquants!r}.")

    op.execute(f"ALTER TABLE {TABLE_MESURES} DISABLE TRIGGER {TRIGGER_AUDIT}")
    nb_series, nb_mesures = _charger(bind, loc)
    if (nb_series, nb_mesures) != (NB_SERIES_ATTENDU, NB_MESURES_ATTENDU):
        raise RuntimeError(
            f"Migration 0022 : {nb_series} séries et {nb_mesures} mesures, "
            f"{NB_SERIES_ATTENDU} et {NB_MESURES_ATTENDU} attendues."
        )
    requalifiees = _controler(bind)
    op.execute(f"ALTER TABLE {TABLE_MESURES} ENABLE TRIGGER {TRIGGER_AUDIT}")
    if requalifiees != NB_MESURES_ATTENDU:
        raise RuntimeError(
            f"Migration 0022 : {requalifiees} lignes requalifiées, {NB_MESURES_ATTENDU} attendues."
        )
    if _fiche(bind, FICHE_0022, FICHE_0019) != 1:
        raise RuntimeError("Migration 0022 : fiche de cams_radiation modifiée depuis la 0019.")
    op.execute("ANALYZE series_metadonnees")
    op.execute(f"ANALYZE {TABLE_MESURES}")


def downgrade() -> None:
    bind = op.get_bind()
    _fiche(bind, FICHE_0019, FICHE_0022)
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
