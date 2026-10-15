"""source_era5_pvgis_methode_reanalyse

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-15

Prépare les séries ERA5 (ADR-0009) :

1. ajout de ``'reanalyse'`` à l'énumération ``methode_collecte`` des séries :
   ERA5 est une réanalyse, aucune des six valeurs existantes ne la décrit ; le
   modèle SQLAlchemy est mis à jour en miroir ;
2. la source ``era5_pvgis`` (id 16), ERA5 servie par PVGIS (JRC), distincte du
   produit CDS ``ecmwf_era5`` (id 2).

``downgrade`` retire la source, recale la séquence des sources et restaure
l'énumération à six valeurs.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SOURCE_ID: int = 16
SOURCE_CODE: str = "era5_pvgis"

_CK_METHODE: str = "ck_series_metadonnees_methode_collecte_valide"
_METHODES_6: str = (
    "'mesure_directe', 'modele_satellitaire', 'interpolation_geographique', "
    "'extrapolation_temporelle', 'calcul_derive', 'expertise_humaine'"
)
_METHODES_7: str = _METHODES_6 + ", 'reanalyse'"


def _remplacer_check_methode(valeurs: str) -> None:
    op.drop_constraint(_CK_METHODE, "series_metadonnees", type_="check")
    op.create_check_constraint(
        _CK_METHODE,
        "series_metadonnees",
        f"methode_collecte IS NULL OR methode_collecte IN ({valeurs})",
    )


def _recaler_sequence() -> None:
    op.execute(
        sa.text(
            "SELECT setval(pg_get_serial_sequence('sources', 'id'), (SELECT max(id) FROM sources))"
        )
    )


def upgrade() -> None:
    _remplacer_check_methode(_METHODES_7)
    op.bulk_insert(
        sa.table(
            "sources",
            sa.column("id", sa.BigInteger),
            sa.column("code", sa.String),
            sa.column("titre", sa.Text),
            sa.column("organisation", sa.Text),
            sa.column("type_source", sa.String),
            sa.column("url", sa.Text),
            sa.column("fiabilite", sa.String),
            sa.column("langue", sa.String),
            sa.column("notes", sa.Text),
        ),
        [
            {
                "id": SOURCE_ID,
                "code": SOURCE_CODE,
                "titre": (
                    "ERA5 (réanalyse ECMWF), irradiation mensuelle servie par PVGIS (JRC), "
                    "API v5_3 MRcalc, raddatabase=PVGIS-ERA5"
                ),
                "organisation": (
                    "European Centre for Medium-Range Weather Forecasts (ECMWF) / "
                    "Copernicus Climate Change Service (C3S) ; diffusion PVGIS par le "
                    "Joint Research Centre (JRC) de la Commission européenne."
                ),
                "type_source": "base_donnees",
                "url": "https://re.jrc.ec.europa.eu/api/v5_3/MRcalc",
                "fiabilite": "haute",
                "langue": "en",
                "notes": (
                    "Réanalyse atmosphérique ERA5 (Hersbach et al. 2020), servie par "
                    "PVGIS/JRC (MRcalc, raddatabase=PVGIS-ERA5), distincte du produit CDS "
                    "ecmwf_era5 (id 2). En Afrique de l'Ouest, le rayonnement de "
                    "réanalyse est moins fiable que le satellite sous ciel nuageux et "
                    "chargé en aérosols : source de comparaison, pas de référence."
                ),
            }
        ],
    )
    _recaler_sequence()


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM sources WHERE id = :i").bindparams(i=SOURCE_ID))
    _recaler_sequence()
    _remplacer_check_methode(_METHODES_6)
