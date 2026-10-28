"""Rotation versionnée des lignes versionnées temporellement.

Périmètre : ``mesures_ressource``. Les autres tables versionnées suivent la
même règle (``docs/conventions/02-migrations.md``) sans fonction dédiée.

La rotation versionnée est l'opération **atomique** qui révise la valeur
d'une donnée versionnée tout en préservant son historique. Algorithme
canonique :

1. Capture du timestamp PostgreSQL ``now()`` (un seul appel SQL par
   rotation → ``valide_au`` ancienne et ``valide_du`` nouvelle
   strictement égales).
2. Fermeture de la ligne courante : pose ``valide_au = instant`` +
   ``modifie_le = instant`` + ``modifie_par = auteur_id``.
3. Insertion de la remplaçante : mêmes colonnes d'identité métier,
   nouvelles valeurs, ``valide_du = instant``, ``valide_au = None``,
   ``statut = 'brut'`` sauf statut fourni par l'appelant.

L'atomicité est garantie par la transaction unique : si la contrainte
EXCLUDE refuse l'INSERT (cas de concurrence imprévue), la transaction
est rollback et l'ancienne ligne reste courante. ``now()`` étant l'heure de
début de la transaction, une même mesure ne se révise qu'une fois par
transaction : une seconde rotation donnerait une version de durée nulle, que
la base refuse.

Identité métier de ``mesures_ressource`` : 2-uplet
``(serie_id, instant_mesure)``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from kuma_data_core.db.models.mesures_ressource import MesureRessource

# Colonnes d'identité métier de ``mesures_ressource`` :
# 2-uplet ``(serie_id, instant_mesure)``. Conservé sur la nouvelle ligne lors
# d'une rotation pour préserver l'identité versionnée.
COLONNES_IDENTITE_MESURES_RESSOURCE: tuple[str, ...] = ("serie_id", "instant_mesure")


def roter_ligne_versionnee(
    ligne_courante: MesureRessource,
    nouvelles_valeurs: dict[str, Any],
    auteur_id: int | None,
    session: Session,
) -> MesureRessource:
    """Ferme la ligne courante et insère une remplaçante avec nouvelles valeurs.

    Args:
        ligne_courante : instance ``MesureRessource`` actuellement
            courante (``valide_au IS NULL``).
        nouvelles_valeurs : dict des colonnes mutables à mettre à jour
            sur la nouvelle ligne. Typiquement ``{'valeur': 5.42}``.
            Les colonnes d'identité métier (``serie_id``, ``instant_mesure``)
            sont **conservées** de la ligne courante et ne doivent pas
            figurer dans ce dict (sinon `ValueError`).
        auteur_id : id du contributeur responsable de la rotation
            (``contributeurs.id``). ``None`` pour les rotations
            automatiques sans auteur applicatif.
        session : session SQLAlchemy active. La fonction ajoute la
            nouvelle ligne via ``session.add()`` et flush ; le caller
            est responsable du commit.

    Returns:
        La nouvelle ligne ``MesureRessource`` insérée et flushée.

    Raises:
        ValueError : si ``nouvelles_valeurs`` contient une colonne
            d'identité métier (``serie_id``, ``instant_mesure``).

    Side-effects :
        - Mute ``ligne_courante.valide_au``, ``modifie_le``, ``modifie_par``
        - Ajoute une nouvelle ligne en session et flush

    Notes:
        Le pattern utilise ``SELECT now()`` côté PostgreSQL pour capturer
        le timestamp de début de transaction (un seul appel), réutilisé
        pour les deux opérations. Cela garantit l'égalité stricte entre
        ``valide_au`` (ancienne) et ``valide_du`` (nouvelle) - la
        sémantique ``tstzrange [)`` (lower inclusive, upper exclusive)
        est ainsi respectée sans micro-trou temporel.

        La nouvelle ligne reçoit ``statut='brut'`` si ``nouvelles_valeurs``
        n'en fixe pas (défaut aussi posé par la base). Un passage direct
        vers ``valide_humain`` ou autre est possible par appel séparé à
        ``transition_statut`` dans la même transaction.
    """
    # Garde-fou : pas de modification d'identité métier dans une rotation
    intersection = set(nouvelles_valeurs) & set(COLONNES_IDENTITE_MESURES_RESSOURCE)
    if intersection:
        raise ValueError(
            f"Colonnes d'identité métier interdites dans nouvelles_valeurs : "
            f"{sorted(intersection)}. La rotation versionnée préserve l'identité."
        )

    # 1. Capture un seul timestamp PostgreSQL (start-of-transaction)
    instant: datetime = session.execute(text("SELECT now()")).scalar_one()

    # 2. Fermer la ligne courante
    ligne_courante.valide_au = instant
    ligne_courante.modifie_le = instant
    ligne_courante.modifie_par = auteur_id

    # 3. Insérer la remplaçante (mêmes colonnes d'identité, nouvelles valeurs)
    payload: dict[str, Any] = {
        col: getattr(ligne_courante, col) for col in COLONNES_IDENTITE_MESURES_RESSOURCE
    }
    payload.update(nouvelles_valeurs)
    # Valeurs éditoriales par défaut sur la nouvelle ligne
    payload.setdefault("statut", "brut")
    # Sans niveau fourni, la remplaçante garde celui de la ligne courante :
    # même série, donc même méthode et même source, donc même niveau R1-R4.
    if "niveau_confiance_derive" not in payload:
        payload["niveau_confiance_derive"] = ligne_courante.niveau_confiance_derive

    nouvelle_ligne = MesureRessource(
        **payload,
        valide_du=instant,
        valide_au=None,
        cree_le=instant,
        cree_par=auteur_id,
        modifie_le=instant,
        modifie_par=auteur_id,
    )
    session.add(nouvelle_ligne)
    session.flush()
    return nouvelle_ligne
