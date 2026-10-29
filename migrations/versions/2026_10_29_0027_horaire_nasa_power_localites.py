"""horaire_nasa_power_localites

Revision ID: 0027
Revises: 0026
Create Date: 2026-10-29

Séries horaires NASA POWER (ADR-0026) aux 393 localités qui n'en avaient pas,
les cinq points pilotes ayant les leurs (migration 0011) : GHI, DNI et DHI
(moyenne de l'heure en W/m²) et température à 2 m (°C), 2021 à 2025, chaque
valeur datée du début de l'heure qu'elle moyenne, en UTC.

Une série par maille de NASA POWER : CERES SYN1deg de 1° pour le
rayonnement, MERRA-2 de 0,5° × 0,625° pour la température. La porteuse d'une
maille est son point pilote s'il y en a un, sinon sa première localité dans
l'ordre des codes ; les autres localités ont une série qui lit les mesures de
sa porteuse (``serie_porteuse_id``, migration 0026). Porteuses lues dans
``nasa_power_horaire_mailles_localites.csv`` et valeurs des porteuses dans
les CSV gzip du lot ``localites`` de ``seeds/donnees/`` (produits hors ligne
par ``scripts/ingest_nasa_power_horaire.py --lot localites``) ; la migration
n'accède jamais au réseau.

Le contrôle qualité horaire, doctrine v1 (ADR-0014), s'applique avant le
chargement, aux coordonnées de la porteuse, par ``qualifier_series_horaires``
(mêmes verdicts que ``executer_qc_horaire``) : chaque mesure entre avec le
statut et le commentaire du contrôle, sans requalification après coup, qui
doublerait la table. Confiance B. Les notes des séries pilotes qui portent une
maille le disent. La fiche de la source ``nasa_power`` ajoute l'horaire des
localités (POWER Hourly API v2.10.3, consultée le 29 octobre 2026), et le
commentaire de ``mesures_ressource_horaires`` le dit. Mesures chargées trigger
d'audit suspendu (``docs/architecture/03-audit.md``). ``downgrade`` rend leurs
textes à la source, à la table et aux pilotes, et supprime les mesures, les
séries alias puis les porteuses.
"""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Sequence
from datetime import date
from typing import Any

import sqlalchemy as sa
from alembic import op

from kuma_data_core.db.seeds.lots_bfa import (
    CONTRATS_HORAIRES,
    LOT_LOCALITES,
    PILOTES_HORAIRES,
    points_lot,
)
from kuma_data_core.db.seeds.mailles_horaires import (
    GRANDEURS_RAYONNEMENT,
    GRANDEURS_TEMPERATURE,
    MailleLocalite,
    lire_mailles,
)
from kuma_data_core.db.seeds.series_csv import (
    ContratSerie,
    lire_series_horaires,
    verifier_source,
)
from kuma_data_core.editorial.statuts import transition_autorisee
from kuma_data_core.services.horaire import DECALAGE_MILIEU_HEURE
from kuma_data_core.services.qualite.qc_horaire import (
    VERSION_DOCTRINE_QC,
    qualifier_series_horaires,
)

# revision identifiers, used by Alembic.
revision: str = "0027"
down_revision: str | Sequence[str] | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NB_LOCALITES: int = 398
NB_NOUVELLES_LOCALITES: int = 393
NB_HEURES: int = 43_824
TABLE_MESURES: str = "mesures_ressource_horaires"
TRIGGER_AUDIT: str = "trg_audit_mesures_ressource_horaires"

RAYONNEMENT: str = "Wh/m² sur l'heure, soit sa moyenne en W/m²"
VALEURS: dict[str, str] = {
    "ghi": RAYONNEMENT,
    "dni": RAYONNEMENT,
    "dhi": RAYONNEMENT,
    "t2m": "moyenne de l'heure en °C",
}
MAILLES: dict[str, str] = {
    "ghi": "CERES SYN1deg de 1°",
    "dni": "CERES SYN1deg de 1°",
    "dhi": "CERES SYN1deg de 1°",
    "t2m": "MERRA-2 de 0,5° × 0,625°",
}
MISES_EN_GARDE: dict[str, str] = {
    "ghi": "",
    "dni": (
        " Ce DNI ne referme pas le GHI (aux points pilotes, DHI + DNI·cos z reste de 5,9 à"
        " 6,9 % sous le GHI sur 2021-2025) : le POA horaire calculé par l'API reconstruit le"
        " direct à partir du GHI et du DHI."
    ),
    "dhi": "",
    "t2m": "",
}
FAMILLES: tuple[tuple[str, ...], ...] = (GRANDEURS_RAYONNEMENT, GRANDEURS_TEMPERATURE)

# Fiche de la source : passages des notes remplacés, et date de consultation.
NOTES_SOURCE: tuple[tuple[str, str], ...] = (
    (
        "GHI, DNI, DHI et température horaires 2021-2025 aux cinq points pilotes (POWER "
        "Hourly API v2.10.2, ADR-0014)",
        "GHI, DNI, DHI et température horaires 2021-2025 aux 398 localités, une série par "
        "maille (POWER Hourly API v2.10.2 aux cinq points pilotes, ADR-0014 ; v2.10.3 "
        "ailleurs, ADR-0026)",
    ),
    ("Consultée les 15 et 27 octobre 2026.", "Consultée les 15, 27 et 29 octobre 2026."),
)
CONSULTATION_AVANT: date = date(2026, 10, 27)
CONSULTATION: date = date(2026, 10, 29)

COMMENTAIRE_TABLE_AVANT: str = (
    "Mesures horaires ingérées depuis les sources externes (NASA POWER et CAMS "
    "Radiation aux points pilotes). Pendant horaire de mesures_ressource (journalier) "
    "et de mesures_ressource_mensuelles (mensuel). instant_mesure en TIMESTAMPTZ "
    "(UTC), début de l'heure moyennée, pour le contrôle qualité horaire (position "
    "solaire sans ambiguïté de fuseau). Versionnement temporel par (valide_du, "
    "valide_au) et contrainte EXCLUDE BTree-GiST sur l'identité métier (serie_id, "
    "instant_mesure). Statut éditorial et niveau de confiance dérivé ou forcé par la "
    "couche de service éditoriale."
)
COMMENTAIRE_TABLE: str = (
    "Mesures horaires ingérées depuis les sources externes (NASA POWER aux 398 "
    "localités, une série par maille, lue par la vue v_mesures_horaires ; CAMS "
    "Radiation aux points pilotes). Pendant horaire de mesures_ressource (journalier) "
    "et de mesures_ressource_mensuelles (mensuel). instant_mesure en TIMESTAMPTZ "
    "(UTC), début de l'heure moyennée, pour le contrôle qualité horaire (position "
    "solaire sans ambiguïté de fuseau). Versionnement temporel par (valide_du, "
    "valide_au) et contrainte EXCLUDE BTree-GiST sur l'identité métier (serie_id, "
    "instant_mesure). Statut éditorial et niveau de confiance dérivé ou forcé par la "
    "couche de service éditoriale."
)

_SERIES = sa.table(
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
    sa.column("serie_porteuse_id", sa.BigInteger),
    sa.column("note_publique", sa.Text),
)


def _autres(n: int) -> str:
    """Sujet et verbe accordés : « 1 autre localité lit », « 9 autres localités lisent »."""
    return "1 autre localité lit" if n == 1 else f"{n} autres localités lisent"


def _note(contrat: ContratSerie, porteuse: str | None, lecteurs: int) -> str:
    """Note publique d'une série : porteuse (``porteuse`` vide) ou lue sur sa porteuse."""
    g = contrat.grandeur_code
    if porteuse is not None:
        maille = f" Valeurs de la maille, portées par la série {porteuse} (ADR-0026)."
    elif lecteurs:
        maille = f" Porte sa maille : {_autres(lecteurs)} cette série (ADR-0026)."
    else:
        maille = " Seule localité de sa maille (ADR-0026)."
    return (
        f"{g.upper()} horaire {contrat.source_libelle} ({VALEURS[g]} ; heure commençant à "
        f"l'instant indiqué, UTC), {contrat.annee_debut}-{contrat.annee_fin}, maille "
        f"{MAILLES[g]}.{maille} Confiance {contrat.niveau_confiance}.{MISES_EN_GARDE[g]}"
    )


def _ajout_pilote(grandeur: str, lecteurs: int) -> str:
    """Phrase ajoutée à la note d'une série pilote qui porte sa maille."""
    return f" Porte la maille {MAILLES[grandeur]} : {_autres(lecteurs)} cette série (ADR-0026)."


def _fiche_source(
    bind: sa.Connection, remplacements: Sequence[tuple[str, str]], depuis: date, vers: date
) -> int:
    """Remplace des passages des notes de ``nasa_power`` ; une fiche modifiée entre-temps reste."""
    notes = "notes"
    gardes = []
    parametres: dict[str, Any] = {"depuis": depuis, "vers": vers}
    for i, (ancien, nouveau) in enumerate(remplacements):
        notes = f"replace({notes}, :a{i}, :n{i})"
        gardes.append(f"strpos(notes, :a{i}) > 0")
        parametres |= {f"a{i}": ancien, f"n{i}": nouveau}
    return bind.execute(
        sa.text(
            f"UPDATE sources SET notes = {notes}, date_consultation = :vers, "
            f"modifie_le = now() WHERE code = 'nasa_power' AND date_consultation = :depuis "
            f"AND {' AND '.join(gardes)}"
        ),
        parametres,
    ).rowcount


def _codes_nouveaux() -> list[str]:
    nouvelles = sorted({code for code, *_ in points_lot(LOT_LOCALITES)} - set(PILOTES_HORAIRES))
    return [c.code_serie(code) for c in CONTRATS_HORAIRES.values() for code in nouvelles]


def _lecteurs(mailles: dict[str, MailleLocalite], grandeur: str) -> Counter[str]:
    """Nombre de localités qui lisent chaque porteuse, elle exceptée."""
    return Counter(
        m.porteuse(grandeur) for m in mailles.values() if m.porteuse(grandeur) != m.localite_code
    )


def _inserer_series(
    bind: sa.Connection,
    contrat: ContratSerie,
    mailles: dict[str, MailleLocalite],
    loc: dict[str, int],
) -> dict[str, int]:
    """Insère les séries des nouvelles localités, porteuses d'abord ; renvoie leurs ids."""
    g = contrat.grandeur_code
    lecteurs = _lecteurs(mailles, g)
    porteuses = sorted(c for c in loc if mailles[c].porteuse(g) == c)
    alias = sorted(c for c in loc if mailles[c].porteuse(g) != c)

    def ligne(code: str, porteuse_id: int | None, porteuse: str | None) -> dict[str, Any]:
        return {
            "code": contrat.code_serie(code),
            "libelle": contrat.libelle_serie(code),
            "localite_id": loc[code],
            "grandeur_code": g,
            "source_id": contrat.source_id,
            "periode_debut": contrat.periode_debut,
            "periode_fin": contrat.periode_fin,
            "methode_collecte": contrat.methode_collecte,
            "granularite": contrat.granularite,
            "serie_porteuse_id": porteuse_id,
            "note_publique": _note(contrat, porteuse, lecteurs[code]),
        }

    op.bulk_insert(_SERIES, [ligne(code, None, None) for code in porteuses])
    ids = _ids(bind, [contrat.code_serie(c) for c in {*porteuses, *PILOTES_HORAIRES}])
    lignes_alias = []
    for code in alias:
        porteuse = contrat.code_serie(mailles[code].porteuse(g))
        lignes_alias.append(ligne(code, ids[porteuse], porteuse))
    op.bulk_insert(_SERIES, lignes_alias)
    return _ids(bind, [contrat.code_serie(c) for c in porteuses])


def _ids(bind: sa.Connection, codes: list[str]) -> dict[str, int]:
    return {
        row.code: int(row.id)
        for row in bind.execute(
            sa.text("SELECT code, id FROM series_metadonnees WHERE code = ANY(:c)"), {"c": codes}
        ).all()
    }


def _charger_famille(
    bind: sa.Connection,
    grandeurs: tuple[str, ...],
    mailles: dict[str, MailleLocalite],
    loc: dict[str, int],
    coordonnees: dict[str, tuple[float, float]],
) -> Counter[str]:
    """Insère les séries d'une famille et verse les mesures contrôlées de ses porteuses."""
    serie_id: dict[str, dict[str, int]] = {}
    lues: dict[str, dict[str, dict[str, Any]]] = {}
    for g in grandeurs:
        contrat = CONTRATS_HORAIRES[g]
        ids = _inserer_series(bind, contrat, mailles, loc)
        serie_id[g] = {
            code: ids[contrat.code_serie(code)] for code in loc if contrat.code_serie(code) in ids
        }
        lues[g] = {s["localite_code"]: s for s in lire_series_horaires(contrat, LOT_LOCALITES)}
        if sorted(lues[g]) != sorted(serie_id[g]):
            raise RuntimeError(
                f"Migration 0027 : {contrat.nom_fichier(LOT_LOCALITES)} ne couvre pas exactement "
                "les porteuses de la famille."
            )
        for code, serie in lues[g].items():
            if (serie["latitude"], serie["longitude"]) != coordonnees[code]:
                raise RuntimeError(f"Migration 0027 : coordonnées de {code} différentes en base.")

    copie = (
        f"COPY {TABLE_MESURES} (serie_id, instant_mesure, valeur, statut, "
        "niveau_confiance_derive, commentaire_editorial) FROM STDIN"
    )
    bilan: Counter[str] = Counter()
    pilote = bind.connection.driver_connection
    with pilote.cursor() as curseur, curseur.copy(copie) as flux:  # type: ignore[union-attr]
        for code in sorted(serie_id[grandeurs[0]]):
            mesures = {g: lues[g][code]["mesures"] for g in grandeurs}
            instants = [instant for instant, _ in mesures[grandeurs[0]]]
            if any([i for i, _ in m] != instants for m in mesures.values()):
                raise RuntimeError(
                    f"Migration 0027 : heures différentes d'une grandeur à l'autre, {code}."
                )
            verdicts = qualifier_series_horaires(
                instants,
                {g: [v for _, v in m] for g, m in mesures.items()},
                *coordonnees[code],
                decalage=DECALAGE_MILIEU_HEURE,
            )
            for g in grandeurs:
                niveau = CONTRATS_HORAIRES[g].niveau_confiance
                for (instant, valeur), (statut, commentaire) in zip(
                    mesures[g], verdicts[g], strict=True
                ):
                    flux.write_row(
                        (serie_id[g][code], instant, valeur, statut, niveau, commentaire)
                    )
                    bilan[statut] += 1
                    bilan["flags"] += "flags" in commentaire
    return bilan


def upgrade() -> None:
    bind = op.get_bind()
    if VERSION_DOCTRINE_QC != "v1" or not transition_autorisee("brut", "valide_auto"):
        raise RuntimeError("Migration 0027 : doctrine QC v1 et transition brut -> valide_auto.")
    for contrat in CONTRATS_HORAIRES.values():
        verifier_source(bind, contrat)

    mailles = {m.localite_code: m for m in lire_mailles()}
    points = points_lot(LOT_LOCALITES)
    if sorted(mailles) != [code for code, *_ in points] or len(points) != NB_LOCALITES:
        raise RuntimeError("Migration 0027 : les porteuses ne couvrent pas les 398 localités.")
    for pilote in PILOTES_HORAIRES:
        if any(mailles[pilote].porteuse(g) != pilote for g in CONTRATS_HORAIRES):
            raise RuntimeError(f"Migration 0027 : le pilote {pilote} ne porte pas sa maille.")
    nouvelles = sorted({code for code, *_ in points} - set(PILOTES_HORAIRES))
    if len(nouvelles) != NB_NOUVELLES_LOCALITES:
        raise RuntimeError(f"Migration 0027 : {len(nouvelles)} localités, 393 attendues.")
    lignes = bind.execute(
        sa.text("SELECT code, id, latitude, longitude FROM localites WHERE code = ANY(:c)"),
        {"c": nouvelles},
    ).all()
    loc = {r.code: int(r.id) for r in lignes}
    coordonnees = {r.code: (float(r.latitude), float(r.longitude)) for r in lignes}
    if sorted(loc) != nouvelles:
        raise RuntimeError("Migration 0027 : localité(s) introuvable(s) en base.")
    deja = bind.execute(
        sa.text("SELECT count(*) FROM series_metadonnees WHERE code = ANY(:c)"),
        {"c": _codes_nouveaux()},
    ).scalar_one()
    if deja:
        raise RuntimeError(f"Migration 0027 : {deja} série(s) horaire(s) déjà présente(s).")

    op.execute(f"ALTER TABLE {TABLE_MESURES} DISABLE TRIGGER {TRIGGER_AUDIT}")
    bilan: Counter[str] = Counter()
    for grandeurs in FAMILLES:
        bilan += _charger_famille(bind, grandeurs, mailles, loc, coordonnees)
    op.execute(f"ALTER TABLE {TABLE_MESURES} ENABLE TRIGGER {TRIGGER_AUDIT}")

    porteuses = sum(
        1 for g in CONTRATS_HORAIRES for code in nouvelles if mailles[code].porteuse(g) == code
    )
    nb_mesures = bilan["valide_auto"] + bilan["brut"]
    if nb_mesures != porteuses * NB_HEURES:
        raise RuntimeError(
            f"Migration 0027 : {nb_mesures} mesures, {porteuses * NB_HEURES} attendues."
        )
    logging.getLogger("alembic.runtime.migration").info(
        "Horaire NASA POWER : %d séries, dont %d porteuses ; %d mesures, %d valide_auto "
        "(dont %d avec drapeaux), %d rejetées",
        len(nouvelles) * len(CONTRATS_HORAIRES),
        porteuses,
        nb_mesures,
        bilan["valide_auto"],
        bilan["flags"],
        bilan["brut"],
    )

    for g, contrat in CONTRATS_HORAIRES.items():
        lecteurs = _lecteurs(mailles, g)
        for pilote in PILOTES_HORAIRES:
            if lecteurs[pilote]:
                bind.execute(
                    sa.text(
                        "UPDATE series_metadonnees SET note_publique = note_publique || :ajout, "
                        "modifie_le = now() WHERE code = :code"
                    ),
                    {
                        "ajout": _ajout_pilote(g, lecteurs[pilote]),
                        "code": contrat.code_serie(pilote),
                    },
                )
    if _fiche_source(bind, NOTES_SOURCE, CONSULTATION_AVANT, CONSULTATION) != 1:
        raise RuntimeError("Migration 0027 : fiche de nasa_power modifiée depuis la 0020.")
    op.create_table_comment(
        TABLE_MESURES, COMMENTAIRE_TABLE, existing_comment=COMMENTAIRE_TABLE_AVANT
    )
    op.execute("ANALYZE series_metadonnees")
    op.execute(f"ANALYZE {TABLE_MESURES}")


def downgrade() -> None:
    bind = op.get_bind()
    op.create_table_comment(
        TABLE_MESURES, COMMENTAIRE_TABLE_AVANT, existing_comment=COMMENTAIRE_TABLE
    )
    _fiche_source(bind, [(n, a) for a, n in NOTES_SOURCE], CONSULTATION, CONSULTATION_AVANT)
    mailles = {m.localite_code: m for m in lire_mailles()}
    for g, contrat in CONTRATS_HORAIRES.items():
        lecteurs = _lecteurs(mailles, g)
        for pilote in PILOTES_HORAIRES:
            if lecteurs[pilote]:
                bind.execute(
                    sa.text(
                        "UPDATE series_metadonnees SET note_publique = "
                        "replace(note_publique, :ajout, ''), modifie_le = now() WHERE code = :code"
                    ),
                    {
                        "ajout": _ajout_pilote(g, lecteurs[pilote]),
                        "code": contrat.code_serie(pilote),
                    },
                )
    codes = _codes_nouveaux()
    op.execute(f"ALTER TABLE {TABLE_MESURES} DISABLE TRIGGER {TRIGGER_AUDIT}")
    bind.execute(
        sa.text(
            f"DELETE FROM {TABLE_MESURES} WHERE serie_id IN "
            "(SELECT id FROM series_metadonnees WHERE code = ANY(:c))"
        ),
        {"c": codes},
    )
    op.execute(f"ALTER TABLE {TABLE_MESURES} ENABLE TRIGGER {TRIGGER_AUDIT}")
    bind.execute(
        sa.text(
            "DELETE FROM series_metadonnees WHERE code = ANY(:c) AND serie_porteuse_id IS NOT NULL"
        ),
        {"c": codes},
    )
    bind.execute(sa.text("DELETE FROM series_metadonnees WHERE code = ANY(:c)"), {"c": codes})
