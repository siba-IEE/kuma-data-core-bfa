"""Tests d'intégration de la rotation versionnée (``editorial.versioning``).

Réviser une mesure ferme la ligne courante et insère la remplaçante au même
instant ; l'historique reste en base et une seule ligne est courante.
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from kuma_data_core.db.models.mesures_ressource import MesureRessource
from kuma_data_core.editorial.niveaux_confiance import calculer_niveau_confiance_derive
from kuma_data_core.editorial.versioning import roter_ligne_versionnee

pytestmark = pytest.mark.integration


def _ligne_courante(session: Session) -> MesureRessource:
    return session.scalars(
        select(MesureRessource)
        .where(MesureRessource.valide_au.is_(None))
        .order_by(MesureRessource.id)
        .limit(1)
    ).one()


def _versions(session: Session, ligne: MesureRessource) -> list[MesureRessource]:
    return list(
        session.scalars(
            select(MesureRessource)
            .where(
                MesureRessource.serie_id == ligne.serie_id,
                MesureRessource.instant_mesure == ligne.instant_mesure,
            )
            .order_by(MesureRessource.valide_du)
        )
    )


def test_rotation_ferme_et_remplace(db_session: Session) -> None:
    """L'ancienne ligne est bornée à l'instant où la remplaçante commence."""
    ancienne = _ligne_courante(db_session)
    valeur_initiale = ancienne.valeur

    nouvelle = roter_ligne_versionnee(ancienne, {"valeur": valeur_initiale + 1.0}, None, db_session)

    assert ancienne.valide_au is not None
    assert nouvelle.valide_du == ancienne.valide_au
    assert nouvelle.valide_au is None
    assert (nouvelle.serie_id, nouvelle.instant_mesure) == (
        ancienne.serie_id,
        ancienne.instant_mesure,
    )
    assert nouvelle.valeur == valeur_initiale + 1.0
    assert nouvelle.statut == "brut"
    methode, fiabilite = db_session.execute(
        text(
            "SELECT s.methode_collecte, so.fiabilite FROM series_metadonnees s "
            "JOIN sources so ON so.id = s.source_id WHERE s.id = :id"
        ),
        {"id": ancienne.serie_id},
    ).one()
    assert nouvelle.niveau_confiance_derive == calculer_niveau_confiance_derive(methode, fiabilite)

    # Relecture en base : bornes jointives, une seule ligne courante.
    db_session.expire_all()
    versions = _versions(db_session, ancienne)
    assert [v.id for v in versions] == [ancienne.id, nouvelle.id]
    assert versions[0].valeur == valeur_initiale
    assert versions[0].valide_au == versions[1].valide_du
    assert [v.valide_au is None for v in versions] == [False, True]


def test_rotation_remplacante_repart_en_brut(db_session: Session) -> None:
    """Une ligne validée révisée laisse place à une remplaçante au statut brut."""
    ancienne = _ligne_courante(db_session)
    ancienne.statut = "valide_auto"
    db_session.flush()

    nouvelle = roter_ligne_versionnee(ancienne, {"valeur": ancienne.valeur}, None, db_session)

    assert ancienne.statut == "valide_auto"
    assert nouvelle.statut == "brut"


def test_rotation_refuse_de_changer_l_identite(db_session: Session) -> None:
    """La série et le jour d'une mesure ne changent pas dans une rotation."""
    ancienne = _ligne_courante(db_session)
    courantes_avant = db_session.scalar(
        select(func.count()).where(
            MesureRessource.serie_id == ancienne.serie_id,
            MesureRessource.valide_au.is_(None),
        )
    )

    with pytest.raises(ValueError, match="identité métier"):
        roter_ligne_versionnee(
            ancienne, {"instant_mesure": ancienne.instant_mesure}, None, db_session
        )

    assert ancienne.valide_au is None
    assert (
        db_session.scalar(
            select(func.count()).where(
                MesureRessource.serie_id == ancienne.serie_id,
                MesureRessource.valide_au.is_(None),
            )
        )
        == courantes_avant
    )
