"""Tests d'intégration du niveau de confiance des séries chargées.

Chaque valeur porte le niveau que les règles R1 à R4 donnent pour la méthode de
collecte de sa série et la fiabilité de sa source
(``docs/contribution/confiance-et-statuts.md``). Les contrats de chargement
recopient la fiabilité de la fiche de leur source : ``verifier_source`` refuse
un contrat qui ne la recopie plus.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from kuma_data_core.db.seeds.lots_bfa import CONTRATS_ERA5_LAND_JOURNALIERS, LOT_LOCALITES
from kuma_data_core.db.seeds.series_csv import verifier_source
from kuma_data_core.db.seeds.series_denses import charger_series_denses
from kuma_data_core.editorial.niveaux_confiance import calculer_niveau_confiance_derive
from tests.unit.db.test_lots_bfa import contrats_bfa

pytestmark = pytest.mark.integration

# Niveau stocké d'une valeur courante de chaque série, lu dans la table qui la
# porte : une ligne suffit, le chargement donne le même niveau à toute la série.
_NIVEAU_STOCKE: str = """
SELECT s.code, s.methode_collecte, so.fiabilite, CASE
    WHEN s.stockage = 'dense' THEN (
        SELECT d.niveau_confiance_derive FROM mesures_journalieres_denses d
        WHERE d.serie_id = coalesce(s.serie_porteuse_id, s.id) ORDER BY d.annee LIMIT 1)
    WHEN s.granularite = 'journalier' THEN (
        SELECT m.niveau_confiance_derive FROM mesures_ressource m
        WHERE m.serie_id = s.id AND m.valide_au IS NULL ORDER BY m.instant_mesure LIMIT 1)
    WHEN s.granularite = 'mensuel' THEN (
        SELECT m.niveau_confiance_derive FROM mesures_ressource_mensuelles m
        WHERE m.serie_id = s.id AND m.valide_au IS NULL ORDER BY m.annee, m.mois LIMIT 1)
    WHEN s.granularite = 'horaire' THEN (
        SELECT m.niveau_confiance_derive FROM mesures_ressource_horaires m
        WHERE m.serie_id = s.id AND m.valide_au IS NULL ORDER BY m.instant_mesure LIMIT 1)
    ELSE (
        SELECT g.niveau_confiance_derive FROM grandeurs_metier g
        WHERE g.grandeur_code = s.grandeur_code AND g.localite_id = s.localite_id
          AND g.series_metadonnees_id = s.id AND g.valide_au IS NULL LIMIT 1)
    END AS niveau
FROM series_metadonnees s JOIN sources so ON so.id = s.source_id
"""


def test_niveau_des_series_suit_les_regles(db_session: Session) -> None:
    """Toute série porte le niveau que R1 à R4 donnent pour sa méthode et sa source."""
    lignes = db_session.execute(text(_NIVEAU_STOCKE)).all()
    assert len(lignes) > 20_000
    sans_valeur = [r.code for r in lignes if r.niveau is None]
    assert sans_valeur == []
    ecarts = [
        (r.code, r.niveau)
        for r in lignes
        if r.niveau != calculer_niveau_confiance_derive(r.methode_collecte, r.fiabilite)
    ]
    assert ecarts == []


def test_series_du_burkina_en_confiance_b(db_session: Session) -> None:
    """Satellite, réanalyse et calculs de sources de fiabilité haute : B partout (R4)."""
    niveaux = {r.niveau for r in db_session.execute(text(_NIVEAU_STOCKE)).all()}
    assert niveaux == {"B"}


def test_contrats_conformes_aux_fiches(db_session: Session) -> None:
    """Chaque contrat recopie le code et la fiabilité de la fiche de sa source."""
    bind = db_session.connection()
    for contrat in contrats_bfa():
        verifier_source(bind, contrat)


def test_chargement_dense_refuse_un_contrat_non_conforme(db_session: Session) -> None:
    """Un contrat dont la fiabilité diffère de la fiche est refusé avant toute insertion."""
    contrat = replace(CONTRATS_ERA5_LAND_JOURNALIERS["t2m"], fiabilite_source="moyenne")
    with pytest.raises(ValueError, match="attendue"):
        charger_series_denses(db_session.connection(), contrat, LOT_LOCALITES, {}, str, "°C")
