"""Modèle SQLAlchemy de la table ``mesures_journalieres_denses`` (ADR-0017).

Mesures journalières brutes en masse : une ligne par série porteuse et par
année, les valeurs du 1er janvier au 31 décembre dans un tableau d'entiers en
dix-millièmes (``NULL`` pour un jour sans valeur). Sans versionnement, sans
statut éditorial ni audit ligne à ligne : les données viennent de fichiers
versionnés relus par les migrations, et une correction réédite la série
(suppression puis rechargement), jamais une ligne ; un trigger refuse toute
mise à jour. Le statut est ``brut`` par construction.

Identité métier : 2-uplet ``(serie_id, annee)``, clé primaire. Seules les
séries ``stockage = 'dense'`` sans ``serie_porteuse_id`` portent des lignes
(trigger) ; une série identique à une autre (même maille de la source) lit
celles de sa porteuse. La vue ``v_mesures_journalieres`` déplie les tableaux,
rend à chaque série ses mesures, porteuse ou non, et y joint les mesures
journalières courantes de ``mesures_ressource`` pour les lectures de l'API.

Une année pèse environ 1,6 ko (366 entiers de 4 octets, en ligne, sans
compression), contre 84 octets par jour pour une ligne par jour.
"""

from __future__ import annotations

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Integer, SmallInteger, String
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from kuma_data_core.db.base import Base
from kuma_data_core.db.models.series_metadonnees import SerieMetadonnees


class MesureJournaliereDense(Base):
    """Valeurs journalières brutes d'une année, pour une série porteuse dense."""

    __tablename__ = "mesures_journalieres_denses"

    serie_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "series_metadonnees.id",
            name="fk_mesures_journalieres_denses_serie_id__series_metadonnees",
            ondelete="RESTRICT",
        ),
        primary_key=True,
    )
    annee: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    niveau_confiance_derive: Mapped[str] = mapped_column(String(1), nullable=False)
    valeurs_e4: Mapped[list[int | None]] = mapped_column(
        ARRAY(Integer),
        nullable=False,
        comment=(
            "Valeur de chaque jour de l'annee, du 1er janvier au 31 decembre, en "
            "dix-milliemes de l'unite de la grandeur ; NULL pour un jour sans valeur."
        ),
    )

    serie: Mapped[SerieMetadonnees] = relationship(
        SerieMetadonnees,
        lazy="select",
        foreign_keys=[serie_id],
    )

    __table_args__ = (
        CheckConstraint(
            "niveau_confiance_derive IN ('A', 'B', 'C')",
            name="ck_mesures_journalieres_denses_niveau_confiance_derive_valide",
        ),
        CheckConstraint(
            "annee BETWEEN 1900 AND 2100",
            name="ck_mesures_journalieres_denses_annee_plausible",
        ),
        CheckConstraint(
            "array_ndims(valeurs_e4) = 1 AND array_lower(valeurs_e4, 1) = 1 "
            "AND array_length(valeurs_e4, 1) = make_date(annee + 1, 1, 1) - make_date(annee, 1, 1)",
            name="ck_mesures_journalieres_denses_un_jour_par_jour",
        ),
    )
