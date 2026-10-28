"""Modèle SQLAlchemy de la table ``grandeurs_metier``.

Table de fabrication éditoriale Kuma. Stocke les grandeurs F1
``strategie_calcul='stockee'`` calculées par Kuma à partir des mesures
brutes.

Identité métier étendue : 7-uplet ``(grandeur_code, localite_id,
periode_type, annee_debut, annee_fin, COALESCE(mois, 0),
version_formule)`` avec versioning temporel
``tstzrange(valide_du, valide_au)`` + opérateur de chevauchement strict
``&&``. Permet la coexistence des lignes v1 et v2 d'une même formule
après upgrade ``version_formule_actuelle`` dans
``grandeurs_referentiel``.

Superpose les 3 mécaniques transverses + ``version_formule`` :

- Statut éditorial 5 valeurs : ``brut``, ``valide_auto``,
  ``valide_humain``, ``publie``, ``deprecie``.
- Versioning temporel ``valide_du``/``valide_au`` TIMESTAMPTZ + EXCLUDE
  BTree-GiST.
- Niveau de confiance A/B/C dérivé par règles R1-R4 + override éditorial
  avec justification obligatoire.

Helper SQLAlchemy :

- ``@hybrid_property niveau_effectif`` : renvoie l'override si non NULL,
  sinon le dérive. Équivalent Python de la vue SQL
  ``v_grandeurs_metier_courantes``.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column, relationship

from kuma_data_core.db.base import Base
from kuma_data_core.db.models.series_metadonnees import SerieMetadonnees


class GrandeurMetier(Base):
    """Grandeur Kuma F1 stockée calculée à partir de mesures brutes."""

    __tablename__ = "grandeurs_metier"

    # === Identifiant ===
    id: Mapped[int] = mapped_column(BigInteger, Identity(start=1, increment=1), primary_key=True)

    # === Identité métier ===
    grandeur_code: Mapped[str] = mapped_column(
        String(80),
        ForeignKey(
            "grandeurs_referentiel.code",
            name="fk_grandeurs_metier_grandeur_code__grandeurs_referentiel",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    localite_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "localites.id",
            name="fk_grandeurs_metier_localite_id__localites",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    series_metadonnees_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "series_metadonnees.id",
            name="fk_grandeurs_metier_series_metadonnees_id__series_metadonnees",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    periode_type: Mapped[str] = mapped_column(
        String(8),
        nullable=False,
        comment=(
            "Granularité temporelle de l'agrégat : annuel (une ligne par localité, grandeur, année"
            " et version de formule ; mois NULL), mensuel (12 lignes par année, mois 1 à 12) ou "
            "statique (une valeur sans période, mois NULL)."
        ),
    )
    annee_debut: Mapped[int] = mapped_column(Integer, nullable=False)
    annee_fin: Mapped[int] = mapped_column(Integer, nullable=False)
    mois: Mapped[int | None] = mapped_column(Integer, nullable=True)
    version_formule: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment=(
            "Version de la formule de calcul en vigueur à l'insertion, liée à "
            "grandeurs_referentiel.version_formule_actuelle de la grandeur et incrémentée à chaque"
            " révision méthodologique. Incluse dans la contrainte EXCLUDE pour que deux versions "
            "coexistent après une révision."
        ),
    )

    # === Valeur ===
    # Nullable : permet de stocker NULL pour les écarts relatifs dont la
    # valeur SARAH-3 mensuelle est en dessous du seuil SEUIL_SARAH3_MIN_DEFAUT
    # (donnée amont dégradée, ratio non calculable sans amplification
    # mathématique absurde). Voir
    # services/grandeurs/referentiels.py:_calcul_ecart_relatif_avec_seuil.
    # Si une grandeur veut imposer NOT NULL sur son sous-périmètre, c'est
    # une CHECK CONSTRAINT conditionnelle qui le porte, pas la nullabilité
    # de colonne.
    valeur: Mapped[float | None] = mapped_column(Float(precision=53), nullable=True)

    # === Versioning temporel ===
    valide_du: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    valide_au: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # === Statut éditorial ===
    statut: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=text("'brut'"),
        comment=(
            "Statut editorial Kuma : brut (calcule non valide), valide_auto "
            "(controle qualite automatique passe), valide_humain (validation "
            "editoriale humaine), publie (publie publiquement), deprecie "
            "(retire du circuit editorial). Transitions encadrees par la "
            "couche service Python (cf. kuma_data_core.editorial.statuts)."
        ),
    )

    # === Niveau de confiance ===
    niveau_confiance_derive: Mapped[str] = mapped_column(
        String(1),
        nullable=False,
        comment=(
            "Niveau de confiance dérivé par la couche de service à partir des règles R1 à R4 "
            "(docs/contribution/confiance-et-statuts.md), selon la méthode de collecte et la "
            "source de la série. A = haute, B = moyenne, C = basse."
        ),
    )
    niveau_confiance_override: Mapped[str | None] = mapped_column(
        String(1),
        nullable=True,
        comment=(
            "Override editorial du niveau derive. NULL = pas override (valeur "
            "effective = derive). Sinon valeur effective = override. Pose par "
            "la fonction service overrider_niveau_confiance avec justification "
            "obligatoire dans commentaire_editorial."
        ),
    )

    # === Commentaire éditorial ===
    commentaire_editorial: Mapped[str | None] = mapped_column(Text, nullable=True)

    # === Audit applicatif ===
    cree_le: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    cree_par: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            "contributeurs.id",
            name="fk_grandeurs_metier_cree_par__contributeurs",
            ondelete="SET NULL",
        ),
        nullable=True,
    )
    modifie_le: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    modifie_par: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            "contributeurs.id",
            name="fk_grandeurs_metier_modifie_par__contributeurs",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    # === Relations ===
    serie: Mapped[SerieMetadonnees] = relationship(
        SerieMetadonnees,
        lazy="select",
        foreign_keys=[series_metadonnees_id],
    )

    # === Hybrid properties ===
    @hybrid_property
    def niveau_effectif(self) -> str:
        """Renvoie ``niveau_confiance_override`` si non NULL, sinon ``niveau_confiance_derive``.

        Équivalent Python de la vue SQL ``v_grandeurs_metier_courantes``. Permet aux
        callers d'obtenir le niveau consommable sans logique conditionnelle
        dispersée.
        """
        return (
            self.niveau_confiance_override
            if self.niveau_confiance_override is not None
            else self.niveau_confiance_derive
        )

    # === Contraintes et index ===
    __table_args__ = (
        CheckConstraint(
            "periode_type IN ('mensuel', 'annuel', 'statique')",
            name="ck_grandeurs_metier_periode_type_valide",
        ),
        CheckConstraint(
            "(periode_type = 'annuel' AND mois IS NULL) "
            "OR (periode_type = 'mensuel' AND mois IS NOT NULL AND mois BETWEEN 1 AND 12) "
            "OR (periode_type = 'statique' AND mois IS NULL)",
            name="ck_grandeurs_metier_periode_coherente",
        ),
        CheckConstraint(
            "annee_fin >= annee_debut",
            name="ck_grandeurs_metier_annees_coherentes",
        ),
        CheckConstraint(
            "version_formule >= 1",
            name="ck_grandeurs_metier_version_formule_positive",
        ),
        CheckConstraint(
            "statut IN ('brut', 'valide_auto', 'valide_humain', 'publie', 'deprecie')",
            name="ck_grandeurs_metier_statut_valide",
        ),
        CheckConstraint(
            "niveau_confiance_derive IN ('A', 'B', 'C')",
            name="ck_grandeurs_metier_niveau_confiance_derive_valide",
        ),
        CheckConstraint(
            "niveau_confiance_override IS NULL OR niveau_confiance_override IN ('A', 'B', 'C')",
            name="ck_grandeurs_metier_niveau_confiance_override_valide",
        ),
        CheckConstraint(
            "valide_au IS NULL OR valide_au > valide_du",
            name="ck_grandeurs_metier_periode_validite_coherente",
        ),
        # Index partiel sur lignes courantes (usage dominant en lecture).
        # Pattern symétrique à idx_mesures_ressource_courantes.
        Index(
            "idx_grandeurs_metier_courantes",
            "grandeur_code",
            "localite_id",
            "periode_type",
            "annee_debut",
            "annee_fin",
            "mois",
            "version_formule",
            postgresql_where=text("valide_au IS NULL"),
        ),
        # Commentaire de table porté sur l'ORM pour cohérence avec la base
        # (migration 0024, alembic check).
        {
            "comment": (
                "Grandeurs métier calculées par Kuma à partir des mesures brutes : agrégats "
                "annuels et mensuels des grandeurs F1 stockées, et valeurs statiques "
                "(dégénérescence de pixel). Versionnement temporel par (valide_du, valide_au) et "
                "contrainte EXCLUDE BTree-GiST sur l'identité métier étendue à version_formule. "
                "Statut éditorial et niveau de confiance dérivé ou forcé par la couche de service "
                "éditoriale."
            ),
        },
    )

    def __repr__(self) -> str:
        return (
            f"<GrandeurMetier(id={self.id}, grandeur_code={self.grandeur_code!r}, "
            f"localite_id={self.localite_id}, periode_type={self.periode_type!r}, "
            f"annee_debut={self.annee_debut}, mois={self.mois}, "
            f"version_formule={self.version_formule}, valeur={self.valeur})>"
        )
