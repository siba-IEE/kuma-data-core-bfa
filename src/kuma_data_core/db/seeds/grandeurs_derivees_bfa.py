"""Grandeurs dérivées stockées du Burkina Faso (ADR-0012).

Deux familles, calculées par la migration 0009 depuis les séries mensuelles
brutes (ADR-0009, ADR-0011) et rangées dans ``grandeurs_metier`` :

- les **écarts relatifs inter-sources** : ``(x - nasa) / nasa × 100``, en %, par
  mois, sur la fenêtre commune de la source comparée et de NASA POWER. NASA
  POWER est au dénominateur de tous les écarts, ce qui les rend comparables
  entre eux ; c'est une référence de comparaison, pas une valeur vraie ;
- la **fraction diffuse NASA POWER** : ``DHI / GHI`` par mois, et
  ``Σ DHI_m·n_m / Σ GHI_m·n_m`` par année complète (``n_m`` jours du mois).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EcartInterSource:
    """Écart relatif mensuel d'une source à NASA POWER pour une grandeur brute."""

    grandeur_id: int
    grandeur_brute: str  # ghi, dni ou dhi
    source_code: str
    source_libelle: str
    prefixe: str  # préfixe court de la source dans les codes
    annee_debut: int
    annee_fin: int

    @property
    def grandeur_code(self) -> str:
        return f"ecart_relatif_{self.grandeur_brute}_{self.prefixe}_nasa"

    @property
    def prefixe_serie(self) -> str:
        return f"ecart_{self.grandeur_brute}_{self.prefixe}_nasa"

    @property
    def nb_mois(self) -> int:
        return (self.annee_fin - self.annee_debut + 1) * 12

    def code_serie(self, localite_code: str) -> str:
        return f"{self.prefixe_serie}_{localite_code}"


ECARTS: tuple[EcartInterSource, ...] = (
    EcartInterSource(35, "ghi", "sarah3_monthly", "SARAH-3 (PVGIS)", "sarah3", 2005, 2023),
    EcartInterSource(36, "ghi", "era5_pvgis", "ERA5 (PVGIS)", "era5", 2005, 2023),
    EcartInterSource(37, "ghi", "cams_radiation", "CAMS Radiation", "cams", 2005, 2025),
    EcartInterSource(38, "dni", "cams_radiation", "CAMS Radiation", "cams", 2005, 2025),
    EcartInterSource(39, "dni", "sarah3_monthly", "SARAH-3 (PVGIS)", "sarah3", 2005, 2023),
    EcartInterSource(40, "dni", "era5_pvgis", "ERA5 (PVGIS)", "era5", 2005, 2023),
    EcartInterSource(41, "dhi", "cams_radiation", "CAMS Radiation", "cams", 2005, 2025),
)

# Fraction diffuse NASA POWER : DHI servi depuis 2001 (ADR-0009).
FRACTION_DIFFUSE_CODE: str = "fraction_diffuse"
FRACTION_DIFFUSE_DEBUT: int = 2001
FRACTION_DIFFUSE_FIN: int = 2025


def code_serie_fraction_diffuse(localite_code: str) -> str:
    return f"fraction_diffuse_nasa_power_{localite_code}"
