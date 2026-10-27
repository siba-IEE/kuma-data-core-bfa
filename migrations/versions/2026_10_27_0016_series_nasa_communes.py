"""series_nasa_communes

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-27

Séries journalières brutes NASA POWER aux 351 communes, 2005 à 2025, en
stockage dense (ADR-0017) :

| Grandeur | Valeur | Mailles distinctes |
|---|---|---|
| GHI, DNI, DHI | total du jour en kWh/m²/jour (CERES SYN1deg, 1°) | 33 |
| T2M | moyenne du jour en °C (MERRA-2, 0,5° × 0,625°) | 82 |
| RH2M | moyenne du jour en % (MERRA-2) | 82 |
| Pluie | cumul du jour en mm (MERRA-2 corrigé) | 82 |

Soit 2 106 séries (351 communes, 6 grandeurs) de 7 670 jours, confiance B,
statut ``brut``. Une commune reçoit la série de sa maille : fichier et base ne
stockent chaque série distincte qu'une fois (345 séries porteuses, 7 245
lignes annuelles et 2 646 149 valeurs dans ``mesures_journalieres_denses``),
les 1 761 autres séries lisent les mesures de leur porteuse
(``serie_porteuse_id``), et la note publique dit combien de communes
partagent la série.

Pluie de décembre 2025 : de 2005 à 2024, aucun jour de décembre ne dépasse
3 mm sur les 398 localités ; en décembre 2025, la source sert un épisode de
l'ouest et du sud-ouest, jusqu'à 514,64 mm le 2. Les deux valeurs au-delà de
la borne de 500 mm (Sidéradougou et Tiéfora), seuls écarts admis par le
contrat, sont écartées ; les autres valeurs au-dessus de 3 mm sont gardées et
signalées dans la note de la série, aux communes comme aux 13 provinces
touchées (notes de la migration 0010 complétées, rendues au ``downgrade``).
Les valeurs au-dessus du record national de 263 mm (ADR-0013) sont aussi
signalées.

Valeurs lues dans les fichiers Parquet de ``seeds/donnees/denses/`` (produits
hors ligne par ``scripts/ingest_nasa_power_journalier.py --lot communes``) et
validées par ``series_denses.lire_series_denses``, points interrogés comparés
aux coordonnées des communes en base ; la migration n'accède jamais au
réseau. Garde-fous : identité de la source, couverture exacte des communes,
nombre de séries, de lignes et de valeurs. ``downgrade`` supprime les
mesures, puis les séries, et rend leurs notes aux provinces.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from datetime import date, timedelta

import numpy as np
import sqlalchemy as sa
from alembic import op

from kuma_data_core.db.seeds.lots_bfa import (
    CONTRATS_METEO_JOURNALIERS_COMMUNES,
    CONTRATS_NASA_JOURNALIERS_COMMUNES,
    points_lot,
)
from kuma_data_core.db.seeds.series_csv import ContratSerie
from kuma_data_core.db.seeds.series_denses import (
    SeriesDenses,
    charger_series_denses,
    lire_series_denses,
)

# revision identifiers, used by Alembic.
revision: str = "0016"
down_revision: str | Sequence[str] | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LOT: str = "communes"
NB_POINTS: int = 351
NB_SERIES_ATTENDU: int = 2_106
NB_LIGNES_ATTENDU: int = 7_245  # (3 × 33 + 3 × 82) porteuses × 21 années
NB_VALEURS_ATTENDU: int = 2_646_149  # porteuses × 7 670 jours, moins 1 écartée
NB_PROVINCES_DECEMBRE: int = 13
CONTRATS: tuple[ContratSerie, ...] = (
    *CONTRATS_NASA_JOURNALIERS_COMMUNES.values(),
    *CONTRATS_METEO_JOURNALIERS_COMMUNES.values(),
)

# Grandeur : (nom, valeur du jour, unité, produit et maille).
GRANDEURS: dict[str, tuple[str, str, str, str]] = {
    "ghi": (
        "Rayonnement global horizontal (GHI)",
        "total du jour",
        "kWh/m²",
        "maille de 1° de NASA POWER (CERES SYN1deg)",
    ),
    "dni": (
        "Rayonnement direct normal (DNI)",
        "total du jour",
        "kWh/m²",
        "maille de 1° de NASA POWER (CERES SYN1deg)",
    ),
    "dhi": (
        "Rayonnement diffus horizontal (DHI)",
        "total du jour",
        "kWh/m²",
        "maille de 1° de NASA POWER (CERES SYN1deg)",
    ),
    "t2m": (
        "Température de l'air à 2 m",
        "moyenne du jour",
        "°C",
        "réanalyse MERRA-2, maille de 0,5° × 0,625°",
    ),
    "rh2m": (
        "Humidité relative à 2 m",
        "moyenne du jour",
        "%",
        "réanalyse MERRA-2, maille de 0,5° × 0,625°",
    ),
    "precipitation": (
        "Pluie",
        "cumul du jour",
        "mm",
        "réanalyse MERRA-2 corrigée, maille de 0,5° × 0,625°",
    ),
}
FERMETURE: str = (
    " GHI, DNI et DHI ne ferment pas : GHI - DHI dépasse le DNI un jour sur quatre, "
    "surtout par ciel couvert ou chargé en poussières."
)
MISES_EN_GARDE: dict[str, str] = {
    "ghi": FERMETURE,
    "dni": FERMETURE,
    "dhi": FERMETURE,
    "t2m": "",
    "rh2m": "",
    "precipitation": (
        " Série non homogène pour les extrêmes et les tendances : les fortes pluies "
        "sont bien plus fréquentes à partir de 2015 ; avant 2015, les extrêmes sont "
        "lissés et les petites pluies trop fréquentes."
    ),
}
# De 2005 à 2024, aucun jour de décembre ne dépasse 3 mm sur les 398 localités
# (2,9 mm au plus) : au-delà, une pluie de décembre 2025 est hors de l'enveloppe.
SEUIL_DECEMBRE_MM: float = 3.0
DECEMBRE_2025: tuple[date, date] = (date(2025, 12, 1), date(2025, 12, 31))
RECORD_NATIONAL_MM: float = 263.0  # Ouagadougou, 1er septembre 2009 (ADR-0013)
# Phrase de la migration 0010, en fin de note de ces deux provinces, que remplace
# la mention de décembre 2025.
NOTE_PROVINCE_0010: str = (
    " Valeur suspecte servie par la source : 321,8 mm le 2 décembre 2025, en saison "
    "sèche ; non corrigée."
)
PROVINCES_0010: tuple[str, ...] = (
    "nasa_power_precipitation_journalier_bfa_prov_comoe",
    "nasa_power_precipitation_journalier_bfa_prov_leraba",
)


def _nombre(valeur: float) -> str:
    return f"{valeur:.1f}".replace(".", ",")


def _gardees(n: int, suspectes: bool = False) -> str:
    if n == 1:
        return (
            "valeur suspecte, gardée telle que servie"
            if suspectes
            else "valeur gardée telle que servie"
        )
    return (
        "valeurs suspectes, gardées telles que servies"
        if suspectes
        else "valeurs gardées telles que servies"
    )


def _decembre(valeurs: list[tuple[date, float]]) -> str:
    """Mention des jours de décembre 2025 hors de l'enveloppe 2005-2024, vide s'il n'y en a pas."""
    jours = [
        (j, v)
        for j, v in valeurs
        if DECEMBRE_2025[0] <= j <= DECEMBRE_2025[1] and v > SEUIL_DECEMBRE_MM
    ]
    if not jours:
        return ""
    liste = ", ".join(f"{_nombre(v)} mm le {j.day}" for j, v in jours)
    return (
        " Décembre 2025 sort de l'enveloppe 2005-2024, où aucun jour de décembre ne "
        f"dépasse 3 mm sur les 398 localités : {liste} ; {_gardees(len(jours), True)}."
    )


def _records(valeurs: list[tuple[date, float]]) -> str:
    jours = [
        (j, v)
        for j, v in valeurs
        if v > RECORD_NATIONAL_MM and not DECEMBRE_2025[0] <= j <= DECEMBRE_2025[1]
    ]
    if not jours:
        return ""
    liste = ", ".join(f"{_nombre(v)} mm le {j.isoformat()}" for j, v in jours)
    return (
        f" Au-dessus du record national de 263 mm (Ouagadougou, 2009) : {liste} ; "
        f"{_gardees(len(jours))}."
    )


def _signalements(denses: SeriesDenses, rep: str) -> str:
    """Décembre 2025 et records d'une série de pluie, sur ses seuls jours au-dessus de 3 mm."""
    valeurs = denses.valeurs[rep]
    jours = [
        (denses.debut + timedelta(days=int(k)), float(valeurs[k]))
        for k in np.flatnonzero(valeurs > SEUIL_DECEMBRE_MM)
    ]
    return _decembre(jours) + _records(jours)


def _notes(contrat: ContratSerie, denses: SeriesDenses) -> dict[str, str]:
    nom, valeur, unite, produit = GRANDEURS[contrat.grandeur_code]
    partage = Counter(denses.representantes.values())
    signalements = (
        {rep: _signalements(denses, rep) for rep in denses.valeurs}
        if contrat.grandeur_code == "precipitation"
        else dict.fromkeys(denses.valeurs, "")
    )
    notes: dict[str, str] = {}
    for code in denses.codes:
        rep = denses.representantes[code]
        maille = (
            "propre à la commune dans le lot"
            if partage[rep] == 1
            else f"identique pour les {partage[rep]} communes de la même maille"
        )
        notes[code] = (
            f"{nom} : série journalière {contrat.source_libelle} ({valeur}, en {unite}), "
            f"{contrat.annee_debut}-{contrat.annee_fin}, {produit}. Lot « {LOT} », stockage "
            f"dense (ADR-0017). Confiance {contrat.niveau_confiance}. Série {maille}."
            f"{MISES_EN_GARDE[contrat.grandeur_code]}{signalements[rep]}"
        )
    return notes


def _provinces_decembre(bind: sa.Connection) -> dict[int, tuple[str, str, str]]:
    """Séries de pluie des provinces touchées en décembre 2025 : id -> (code, note, mention)."""
    lignes = bind.execute(
        sa.text(
            """
            SELECT s.id, s.code, s.note_publique, m.instant_mesure, m.valeur
            FROM series_metadonnees s
            JOIN mesures_ressource m ON m.serie_id = s.id
            WHERE s.grandeur_code = 'precipitation' AND s.granularite = 'journalier'
              AND s.stockage = 'versionne' AND m.valide_au IS NULL
              AND m.instant_mesure BETWEEN :debut AND :fin AND m.valeur > :seuil
            ORDER BY s.id, m.instant_mesure
            """
        ),
        {"debut": DECEMBRE_2025[0], "fin": DECEMBRE_2025[1], "seuil": SEUIL_DECEMBRE_MM},
    ).all()
    par_serie: dict[int, tuple[str, str, list[tuple[date, float]]]] = {}
    for r in lignes:
        par_serie.setdefault(int(r.id), (r.code, r.note_publique, []))[2].append(
            (r.instant_mesure, float(r.valeur))
        )
    return {i: (code, note, _decembre(v)) for i, (code, note, v) in par_serie.items()}


def _codes_series() -> list[str]:
    return [c.code_serie(code) for c in CONTRATS for code, *_ in points_lot(LOT)]


def upgrade() -> None:
    bind = op.get_bind()

    code_source = bind.execute(
        sa.text("SELECT code FROM sources WHERE id = 1")
    ).scalar_one_or_none()
    if code_source != "nasa_power":
        raise RuntimeError(
            f"Migration 0016 : source id 1 = {code_source!r}, 'nasa_power' attendue."
        )

    codes_loc = sorted(code for code, *_ in points_lot(LOT))
    if len(codes_loc) != NB_POINTS:
        raise RuntimeError(f"Migration 0016 : {len(codes_loc)} communes, {NB_POINTS} attendues.")
    loc = {
        row.code: int(row.id)
        for row in bind.execute(
            sa.text("SELECT code, id FROM localites WHERE code = ANY(:c)"), {"c": codes_loc}
        ).all()
    }
    manquants = [c for c in codes_loc if c not in loc]
    if manquants:
        raise RuntimeError(f"Migration 0016 : localité(s) introuvable(s) : {manquants!r}.")

    totaux = np.zeros(3, dtype=np.int64)
    for contrat in CONTRATS:
        notes = _notes(contrat, lire_series_denses(contrat, LOT))
        unite = GRANDEURS[contrat.grandeur_code][2]
        totaux += charger_series_denses(bind, contrat, LOT, loc, notes.__getitem__, unite)
    attendus = (NB_SERIES_ATTENDU, NB_LIGNES_ATTENDU, NB_VALEURS_ATTENDU)
    if tuple(int(t) for t in totaux) != attendus:
        raise RuntimeError(
            f"Migration 0016 : séries, lignes et valeurs {tuple(totaux)!r}, {attendus!r} attendues."
        )

    provinces = _provinces_decembre(bind)
    if len(provinces) != NB_PROVINCES_DECEMBRE:
        raise RuntimeError(
            f"Migration 0016 : {len(provinces)} provinces touchées en décembre 2025, "
            f"{NB_PROVINCES_DECEMBRE} attendues."
        )
    for serie_id, (code, note, mention) in provinces.items():
        if (code in PROVINCES_0010) != note.endswith(NOTE_PROVINCE_0010) or (
            "Décembre 2025" in note
        ):
            raise RuntimeError(f"Migration 0016 : note de {code} modifiée depuis la 0010.")
        base = note.removesuffix(NOTE_PROVINCE_0010)
        bind.execute(
            sa.text("UPDATE series_metadonnees SET note_publique = :n WHERE id = :id"),
            {"n": base + mention, "id": serie_id},
        )
    op.execute("ANALYZE series_metadonnees")
    op.execute("ANALYZE mesures_journalieres_denses")


def downgrade() -> None:
    bind = op.get_bind()
    for serie_id, (code, note, mention) in _provinces_decembre(bind).items():
        if note.endswith(mention):
            fin = NOTE_PROVINCE_0010 if code in PROVINCES_0010 else ""
            bind.execute(
                sa.text("UPDATE series_metadonnees SET note_publique = :n WHERE id = :id"),
                {"n": note.removesuffix(mention) + fin, "id": serie_id},
            )
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
