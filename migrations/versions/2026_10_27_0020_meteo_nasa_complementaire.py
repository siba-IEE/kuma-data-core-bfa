"""meteo_nasa_complementaire

Revision ID: 0020
Revises: 0019
Create Date: 2026-10-27

Météo complémentaire NASA POWER (ADR-0021) aux 398 localités (47 provinces et
351 communes), 2005 à 2025, en stockage dense : températures minimale et
maximale du jour (``t2m_min``, ``t2m_max``), point de rosée
(``point_rosee_2m``), vent moyen et maximal à 10 m (``vent_10m``,
``vent_10m_max``), direction du vent à 10 m (``direction_vent_10m``), vent
moyen à 50 m (``vent_50m``), pression de surface (``pression_surface``), de la
réanalyse MERRA-2, méthode ``reanalyse`` ; nébulosité (``nebulosite``) de CERES,
méthode ``modele_satellitaire``. Confiance B.

Deux unités ajoutées (``radian`` et ``degre``, pour la direction du vent) et
huit grandeurs au référentiel (``vent_10m`` y figurait, sa description est mise
à jour), retirées au ``downgrade``. La fiche de la source ``nasa_power``, restée
celle du dépôt d'origine, passe au Burkina Faso ; le ``downgrade`` rend la
fiche et la description d'origine.
3 582 séries (398 localités, 9 grandeurs) de 7 670 jours ; les localités d'une
même maille partagent la série de leur porteuse.

Valeurs lues dans les fichiers Parquet de ``seeds/donnees/denses/`` (produits
hors ligne par ``scripts/ingest_nasa_power_journalier.py --famille
meteo_complementaire --lot localites``) et validées par
``series_denses.lire_series_denses``, points interrogés comparés aux
coordonnées en base ; la migration n'accède jamais au réseau. Garde-fous :
identité de la source, couverture exacte des localités, nombre de séries, de
lignes et de valeurs. ``downgrade`` supprime les mesures, les séries, puis les
grandeurs et les unités, et rend sa fiche à la source.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from collections.abc import Sequence
from datetime import date
from typing import Any

import sqlalchemy as sa
from alembic import op

from kuma_data_core.db.seeds.lots_bfa import (
    CONTRATS_METEO_COMPLEMENTAIRE,
    LOT_LOCALITES,
    points_lot,
)
from kuma_data_core.db.seeds.series_csv import ContratSerie
from kuma_data_core.db.seeds.series_denses import (
    SeriesDenses,
    charger_series_denses,
    lire_series_denses,
)

# revision identifiers, used by Alembic.
revision: str = "0020"
down_revision: str | Sequence[str] | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NB_POINTS: int = 398
NB_SERIES_ATTENDU: int = 3_582
NB_LIGNES_ATTENDU: int = 14_637  # (8 × 83 + 33) porteuses × 21 années
NB_VALEURS_ATTENDU: int = 5_345_990  # 697 porteuses × 7 670 jours
ID_SOURCE: int = 1
MERRA2: str = "réanalyse MERRA-2, maille de 0,5° × 0,625°"

UNITES: list[dict[str, Any]] = [
    {
        "code": "radian",
        "libelle": "radian",
        "symbole": "rad",
        "grandeur": "angle",
        "systeme": "SI",
        "est_unite_de_base": False,
        "facteur_conversion_si": 1,
        "decalage_conversion_si": 0,
        "code_unite_si": "radian",
        "note_methodologique": "Unité SI dérivée de l'angle plan, sans dimension (m/m).",
        "references_normatives": ["BIPM SI Brochure 9ème édition (2019), Tableau 4"],
    },
    {
        "code": "degre",
        "libelle": "degré (angle)",
        "symbole": "°",
        "grandeur": "angle",
        "systeme": "non_SI_acceptee",
        "est_unite_de_base": False,
        "facteur_conversion_si": math.pi / 180,
        "decalage_conversion_si": 0,
        "code_unite_si": "radian",
        "note_methodologique": "Unité d'angle plan en usage avec le SI : 1° = π/180 rad.",
        "references_normatives": ["BIPM SI Brochure 9ème édition (2019), Tableau 8"],
    },
]

# Grandeur : (libellé du référentiel, unité, description) pour les grandeurs
# ajoutées ; ``vent_10m`` figure déjà au référentiel.
NOUVELLES_GRANDEURS: dict[str, tuple[str, str, str]] = {
    "t2m_min": (
        "Température minimale à 2 mètres",
        "degree_celsius",
        "Plus basse température horaire de l'air à 2 m sur le jour, en °C.",
    ),
    "t2m_max": (
        "Température maximale à 2 mètres",
        "degree_celsius",
        "Plus haute température horaire de l'air à 2 m sur le jour, en °C.",
    ),
    "point_rosee_2m": (
        "Point de rosée à 2 mètres",
        "degree_celsius",
        "Température de rosée de l'air à 2 m (de givre sous 0 °C selon la source), moyenne "
        "du jour, en °C : mesure de la vapeur d'eau de l'air.",
    ),
    "vent_10m_max": (
        "Vent maximal à 10 mètres",
        "metre_par_seconde",
        "Plus forte vitesse horaire du vent à 10 m sur le jour, en m/s.",
    ),
    "direction_vent_10m": (
        "Direction du vent à 10 mètres",
        "degre",
        "Direction d'où souffle le vent moyen du jour à 10 m (moyenne vectorielle des "
        "vents horaires), en degrés depuis le nord dans le sens horaire (90° : vent d'est).",
    ),
    "vent_50m": (
        "Vent à 50 mètres",
        "metre_par_seconde",
        "Vitesse du vent à 50 m, moyenne du jour des vitesses horaires, en m/s.",
    ),
    "pression_surface": (
        "Pression de surface",
        "kilopascal",
        "Pression atmosphérique à la surface, moyenne du jour, en kPa.",
    ),
    "nebulosite": (
        "Nébulosité",
        "pourcent",
        "Part de la maille couverte de nuages vue par satellite, moyenne du jour, en %.",
    ),
}
# Description de ``vent_10m`` au référentiel : état de la 0002, rendu au
# ``downgrade``, et état de la 0020.
DESCRIPTION_VENT_0002: str = (
    "Vitesse moyenne journalière du vent à 10 mètres au-dessus de la surface. Donnée brute "
    "ingérée depuis NASA POWER paramètre WS10M (source MERRA-2 GMAO). Cohorte vent "
    "complémentaire pour usages potentiels éoliens ; hors périmètre Phase 2 (solaire "
    "uniquement)."
)
DESCRIPTION_VENT_0020: str = (
    "Vitesse moyenne journalière du vent à 10 mètres au-dessus de la surface, en m/s : "
    "moyenne des vitesses horaires du jour."
)

# Grandeur : (nom, valeur du jour, unité, produit et maille).
GRANDEURS: dict[str, tuple[str, str, str, str]] = {
    "t2m_min": ("Température minimale de l'air à 2 m", "minimum horaire du jour", "°C", MERRA2),
    "t2m_max": ("Température maximale de l'air à 2 m", "maximum horaire du jour", "°C", MERRA2),
    "point_rosee_2m": ("Point de rosée à 2 m", "moyenne du jour", "°C", MERRA2),
    "vent_10m": ("Vent à 10 m", "moyenne du jour des vitesses horaires", "m/s", MERRA2),
    "vent_10m_max": ("Vent maximal à 10 m", "maximum horaire du jour", "m/s", MERRA2),
    "direction_vent_10m": (
        "Direction du vent à 10 m",
        "direction d'où souffle le vent moyen vectoriel du jour, depuis le nord",
        "degrés",
        MERRA2,
    ),
    "vent_50m": ("Vent à 50 m", "moyenne du jour des vitesses horaires", "m/s", MERRA2),
    "pression_surface": ("Pression de surface", "moyenne du jour", "kPa", MERRA2),
    "nebulosite": (
        "Nébulosité",
        "moyenne du jour",
        "%",
        "nébulosité CERES SYN1deg, maille de 1°",
    ),
}
MISES_EN_GARDE: dict[str, str] = {
    "t2m_min": "",
    "t2m_max": "",
    "point_rosee_2m": (
        " Sous 0 °C, NASA POWER sert le point de givre (saturation sur la glace), plus haut "
        "que le point de rosée d'environ 0,7 °C à -5 °C et de 2 °C à -16,6 °C, valeur la "
        "plus basse servie. Sous 0 °C pour 41 % des jours-localités de décembre à février : "
        "air très sec de l'harmattan."
    ),
    "vent_10m": "",
    "vent_10m_max": (
        " Plus forte des moyennes horaires de la maille, non la rafale : ni les rafales, de "
        "quelques secondes, ni les coups de vent des lignes de grains, de quelques minutes, "
        "n'y figurent."
    ),
    "direction_vent_10m": (
        " Moyenne vectorielle : par vents tournants, la direction du vent moyen peut "
        "s'écarter de la direction la plus fréquente ; plusieurs jours se moyennent par "
        "composantes, non par angles. Sur les 398 localités : nord-est (51 à 55°) de "
        "décembre à février, harmattan ; sud à sud-ouest (194 à 221°) de mai à septembre, "
        "mousson. La bascule de mars-avril remonte du sud au nord : en avril, le vent vient "
        "du sud 93 % des jours au sud de 10,5 °N, 42 % au nord de 13,5 °N."
    ),
    "vent_50m": (
        " Vent du modèle à 50 m, non mesuré. Une puissance éolienne, qui suit le cube de la "
        "vitesse, ne se calcule pas sur des moyennes du jour."
    ),
    "pression_surface": (
        " Pression à l'altitude moyenne de la maille (de 199 à 409 m selon la maille), non à "
        "celle de la localité : environ 1,1 kPa de moins par 100 m de plus."
    ),
    "nebulosite": (
        " Fraction nuageuse vue par satellite, nuages fins compris : 23 % en décembre et "
        "77 % en août en moyenne sur les 398 localités. Elle ne mesure pas l'atténuation : "
        "les jours couverts à 90 % ou plus, CAMS sert en moyenne 59 % du rayonnement par "
        "ciel clair de juin à septembre, 69 % de novembre à mars."
    ),
}
# Le jour de NASA POWER, compté en heure solaire locale arrondie à l'heure, est au
# Burkina Faso le jour UTC (vérifié sur l'API horaire).
JOUR_SOLAIRE: str = (
    " Jour de 0 h à 24 h UTC : l'heure solaire locale de NASA POWER s'y confond au Burkina Faso."
)

# Fiche de la source : état d'origine, rendu au ``downgrade``, et état du
# Burkina Faso. Seules les clés de métadonnées modifiées y figurent.
FICHE_ORIGINE: dict[str, Any] = {
    "date_consultation": date(2026, 5, 10),
    "notes": (
        "Source primaire du substrat physique guinéen. Objet calibré au sens des 3 couches "
        "Kuma (couche A - calibration). NASA Langley Research Center (LaRC) opérateur, "
        "programme NASA Earth Science Division. Version actuelle : POWER Data v10. "
        "Bifurcation des couvertures temporelles selon la communauté de paramètres : (a) "
        "Météorologie 1981-01-01 → présent (source amont : NASA GMAO MERRA-2) ; (b) Solaire "
        "1984-01-01 → présent (sources amont : NASA SRB 4.0-IP 1984-2000, puis CERES SYN1deg "
        "+ FLASHFlux à partir de 2001). La valeur couverture_temporelle_debut du JSONB "
        "retient 1984-01-01, valeur effective pour la communauté Kuma phase 1 = RE (Renewable"
        " Energy, focus solaire). Communautés exposées par NASA POWER : AG (Agroclimatology),"
        " RE (Renewable Energy), SB (Sustainable Buildings). Convention de communauté Kuma à "
        "acter en spec préparatoire 1-2a. Méthodologie publique documentée sur "
        "`power.larc.nasa.gov/docs/methodology/`. Convention de code DT-1 : `nasa_power` "
        "retient l'organisme producteur scientifique (NASA LaRC) + thème (POWER, nom du "
        "projet). Pas d'année dans le code : la base évolue par versions glissantes (v10 "
        "actuelle), sans rupture éditoriale justifiant un nouveau code par millésime. "
        "Acknowledgement officiel (cf. `power.larc.nasa.gov/docs/referencing/`) à inclure "
        "dans toute publication exploitant les données : « The data was obtained from "
        "National Aeronautics and Space Administration (NASA) Langley Research Center's "
        "Prediction Of Worldwide Energy Resources (POWER) project funded through the NASA "
        "Earth Science Division. » NASA POWER demande également de spécifier le triplet "
        "service name + version number + date accessed (exemple : « obtained from the POWER "
        "Project's Hourly 2.x.x version on 2026-05-10 »). Cette exigence se traduira en "
        "convention applicative phase 1-2b pour les réponses API Kuma qui exposent des "
        "données dérivées de NASA POWER. Pas de mention β2 normée DT-8 (source primaire phase"
        " 1 du substrat physique guinéen, opérationnelle phase 1 pour solaire + climat, hors "
        "liste des 4 sources hydro structurelles). Consulté le 2026-05-10."
    ),
    "metadonnees": {},
}
FICHE_0020: dict[str, Any] = {
    "date_consultation": date(2026, 10, 27),
    "notes": (
        "Projet POWER (Prediction Of Worldwide Energy Resources) du Langley Research Center "
        "de la NASA, financé par la NASA Earth Science Division. Rayonnement de CERES "
        "SYN1deg (maille de 1°), du produit SRB avant 2001 ; météo de la réanalyse MERRA-2 "
        "du GMAO (maille de 0,5° × 0,625°) ; nébulosité de CERES SYN1deg ; communauté RE, "
        "jour compté en heure solaire locale (le jour UTC au Burkina Faso), horaire en UTC. "
        "Au Burkina Faso : GHI mensuel 1991-2025, DNI et DHI mensuels 2001-2025, aux "
        "398 localités (POWER Monthly and Annual API, ADR-0009) ; GHI journalier "
        "1991-2025, DNI et DHI 2001-2025, température, humidité et pluie 1991-2025 aux "
        "47 provinces (POWER Daily API v2.10.0, ADR-0010 et ADR-0013), et les mêmes "
        "grandeurs sur 2005-2025 aux 351 communes (v2.10.1, ADR-0017) ; GHI, DNI, DHI et "
        "température horaires 2021-2025 aux cinq points pilotes (POWER Hourly API "
        "v2.10.2, ADR-0014) ; températures minimale et maximale, point de rosée, vent à 10 "
        "et 50 m, direction du vent, pression et nébulosité journaliers 2005-2025 aux "
        "398 localités (v2.10.1, ADR-0021). Consultée les 15 et 27 octobre 2026. Confiance "
        "B (modèle satellitaire et réanalyse). Attribution : « The data was obtained from "
        "National Aeronautics and Space Administration (NASA) Langley Research Center's "
        "Prediction Of Worldwide Energy Resources (POWER) project funded through the NASA "
        "Earth Science Division. »"
    ),
    "metadonnees": {},
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


def _description_vent(bind: sa.Connection, description: str, depuis: str) -> int:
    """Remplace la description ``depuis`` de ``vent_10m`` ; une description modifiée reste."""
    return bind.execute(
        sa.text(
            "UPDATE grandeurs_referentiel SET description = :d, modifie_le = now() "
            "WHERE code = 'vent_10m' AND description = :depuis"
        ),
        {"d": description, "depuis": depuis},
    ).rowcount


def _notes(contrat: ContratSerie, denses: SeriesDenses) -> dict[str, str]:
    nom, valeur, unite, produit = GRANDEURS[contrat.grandeur_code]
    partage = Counter(denses.representantes.values())
    notes: dict[str, str] = {}
    for code in denses.codes:
        n = partage[denses.representantes[code]]
        maille = (
            "propre à la localité dans le lot"
            if n == 1
            else f"identique pour les {n} localités de la même maille"
        )
        notes[code] = (
            f"{nom} : série journalière {contrat.source_libelle} ({valeur}, en {unite}), "
            f"{contrat.annee_debut}-{contrat.annee_fin}, {produit}. Lot des 398 localités "
            "(provinces et communes), stockage dense (ADR-0017). Confiance "
            f"{contrat.niveau_confiance}. Série {maille}."
            f"{MISES_EN_GARDE[contrat.grandeur_code]}{JOUR_SOLAIRE}"
        )
    return notes


def _codes_series() -> list[str]:
    return [
        c.code_serie(code)
        for c in CONTRATS_METEO_COMPLEMENTAIRE.values()
        for code, *_ in points_lot(LOT_LOCALITES)
    ]


def upgrade() -> None:
    bind = op.get_bind()

    code_source = bind.execute(
        sa.text("SELECT code FROM sources WHERE id = :id"), {"id": ID_SOURCE}
    ).scalar_one_or_none()
    if code_source != "nasa_power":
        raise RuntimeError(
            f"Migration 0020 : source id {ID_SOURCE} = {code_source!r}, 'nasa_power' attendue."
        )
    op.bulk_insert(
        sa.table(
            "unites",
            sa.column("code", sa.String),
            sa.column("libelle", sa.Text),
            sa.column("symbole", sa.String),
            sa.column("grandeur", sa.String),
            sa.column("systeme", sa.String),
            sa.column("est_unite_de_base", sa.Boolean),
            sa.column("facteur_conversion_si", sa.Numeric),
            sa.column("decalage_conversion_si", sa.Numeric),
            sa.column("code_unite_si", sa.String),
            sa.column("note_methodologique", sa.Text),
            sa.column("references_normatives", sa.ARRAY(sa.Text)),
        ),
        UNITES,
    )
    unites = {
        row.code: int(row.id)
        for row in bind.execute(
            sa.text("SELECT code, id FROM unites WHERE code = ANY(:c)"),
            {"c": sorted({u for _, u, _ in NOUVELLES_GRANDEURS.values()})},
        ).all()
    }
    op.bulk_insert(
        sa.table(
            "grandeurs_referentiel",
            sa.column("code", sa.String),
            sa.column("libelle", sa.Text),
            sa.column("unite_id", sa.BigInteger),
            sa.column("famille", sa.String),
            sa.column("strategie_calcul", sa.String),
            sa.column("version_formule_actuelle", sa.Integer),
            sa.column("description", sa.Text),
        ),
        [
            {
                "code": code,
                "libelle": libelle,
                "unite_id": unites[unite],
                "famille": "F1",
                "strategie_calcul": "stockee",
                "version_formule_actuelle": 1,
                "description": description,
            }
            for code, (libelle, unite, description) in NOUVELLES_GRANDEURS.items()
        ],
    )

    codes_loc = sorted(code for code, *_ in points_lot(LOT_LOCALITES))
    if len(codes_loc) != NB_POINTS:
        raise RuntimeError(f"Migration 0020 : {len(codes_loc)} localités, {NB_POINTS} attendues.")
    loc = {
        row.code: int(row.id)
        for row in bind.execute(
            sa.text("SELECT code, id FROM localites WHERE code = ANY(:c)"), {"c": codes_loc}
        ).all()
    }
    manquants = [c for c in codes_loc if c not in loc]
    if manquants:
        raise RuntimeError(f"Migration 0020 : localité(s) introuvable(s) : {manquants!r}.")

    totaux = [0, 0, 0]
    for contrat in CONTRATS_METEO_COMPLEMENTAIRE.values():
        notes = _notes(contrat, lire_series_denses(contrat, LOT_LOCALITES))
        unite = GRANDEURS[contrat.grandeur_code][2]
        charges = charger_series_denses(bind, contrat, LOT_LOCALITES, loc, notes.__getitem__, unite)
        totaux = [t + c for t, c in zip(totaux, charges, strict=True)]
    attendus = [NB_SERIES_ATTENDU, NB_LIGNES_ATTENDU, NB_VALEURS_ATTENDU]
    if totaux != attendus:
        raise RuntimeError(
            f"Migration 0020 : séries, lignes et valeurs {totaux!r}, {attendus!r} attendues."
        )
    if _fiche(bind, FICHE_0020, FICHE_ORIGINE) != 1:
        raise RuntimeError("Migration 0020 : fiche de nasa_power modifiée depuis l'origine.")
    if _description_vent(bind, DESCRIPTION_VENT_0020, DESCRIPTION_VENT_0002) != 1:
        raise RuntimeError("Migration 0020 : description de vent_10m modifiée depuis la 0002.")
    op.execute("ANALYZE series_metadonnees")
    op.execute("ANALYZE mesures_journalieres_denses")


def downgrade() -> None:
    bind = op.get_bind()
    _description_vent(bind, DESCRIPTION_VENT_0002, DESCRIPTION_VENT_0020)
    _fiche(bind, FICHE_ORIGINE, FICHE_0020)
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
    bind.execute(
        sa.text("DELETE FROM grandeurs_referentiel WHERE code = ANY(:c)"),
        {"c": list(NOUVELLES_GRANDEURS)},
    )
    bind.execute(
        sa.text("DELETE FROM unites WHERE code = ANY(:c)"), {"c": [u["code"] for u in UNITES]}
    )
