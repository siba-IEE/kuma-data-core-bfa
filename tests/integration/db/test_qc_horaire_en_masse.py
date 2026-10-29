"""Tests d'intégration de la qualification horaire en masse (ADR-0026).

``qualifier_series_horaires`` doit redonner, ligne par ligne, le statut et le
commentaire que le contrôle qualité v1 a écrits en base pour les séries
horaires des cinq points pilotes : NASA POWER (migration 0012) et CAMS
Radiation (migration 0022).
"""

from __future__ import annotations

from collections import Counter

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from kuma_data_core.db.seeds.lots_bfa import points_pilotes
from kuma_data_core.services.horaire import DECALAGE_MILIEU_HEURE
from kuma_data_core.services.qualite.qc_horaire import qualifier_series_horaires

pytestmark = pytest.mark.integration

# Jeux de séries contrôlés ensemble par les migrations : préfixe des codes,
# puis, pour chaque jeu, {grandeur du contrôle: grandeur de la série}.
JEUX: dict[str, list[dict[str, str]]] = {
    "nasa_power": [{"ghi": "ghi", "dni": "dni", "dhi": "dhi", "t2m": "t2m"}],
    "cams": [{"ghi": "ghi", "dni": "dni", "dhi": "dhi"}, {"ghi": "ghi_ciel_clair"}],
}


def _lignes(session: Session, code_serie: str) -> list[tuple[object, float, str, str]]:
    return [
        (r.instant_mesure, float(r.valeur), r.statut, r.commentaire_editorial)
        for r in session.execute(
            text(
                "SELECT m.instant_mesure, m.valeur, m.statut, m.commentaire_editorial "
                "FROM mesures_ressource_horaires m "
                "JOIN series_metadonnees s ON s.id = m.serie_id "
                "WHERE s.code = :code AND m.valide_au IS NULL ORDER BY m.instant_mesure"
            ),
            {"code": code_serie},
        )
    ]


@pytest.mark.parametrize("prefixe", sorted(JEUX))
def test_qualification_en_masse_redonne_les_verdicts_stockes(
    db_session: Session, prefixe: str
) -> None:
    """Statuts et commentaires identiques aux verdicts du QC v1 en base, pour chaque ligne."""
    bilan: Counter[str] = Counter()
    for code, _, latitude, longitude in points_pilotes():
        for jeu in JEUX[prefixe]:
            lignes = {
                g: _lignes(db_session, f"{prefixe}_{grandeur}_horaire_{code}")
                for g, grandeur in jeu.items()
            }
            instants = [ligne[0] for ligne in next(iter(lignes.values()))]
            assert len(instants) == 43_824
            assert all([ligne[0] for ligne in serie] == instants for serie in lignes.values())
            verdicts = qualifier_series_horaires(
                instants,  # type: ignore[arg-type]
                {g: [ligne[1] for ligne in serie] for g, serie in lignes.items()},
                latitude,
                longitude,
                decalage=DECALAGE_MILIEU_HEURE,
            )
            for g, serie in lignes.items():
                assert verdicts[g] == [(ligne[2], ligne[3]) for ligne in serie], (code, g)
                bilan.update(commentaire for _, commentaire in verdicts[g])
    # Des milliers de lignes portent des drapeaux : la comparaison n'est pas triviale.
    assert sum(n for commentaire, n in bilan.items() if "flags" in commentaire) > 1_000
