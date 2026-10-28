"""textes_publics_burkina

Revision ID: 0024
Revises: 0023
Create Date: 2026-10-28

Textes publics du référentiel ramenés au Burkina Faso. Neuf fiches de sources,
treize descriptions de grandeurs, sept notes d'unités et vingt et un
commentaires du schéma venaient du dépôt d'origine : contexte guinéen (stations
de Kankan et de Tarambaly, barrages et bassins de Guinée, villes pilotes, franc
guinéen comme devise de référence, exemples de codes guinéens) et vocabulaire de
ses chantiers (phases, vagues, dettes, conventions DT et GF, documents absents
du dépôt). La fiche de ``esmap_wapp`` décrit maintenant le jeu burkinabè de la
campagne, dont les stations ne sont pas intégrées.

Les notes des séries ERA5 de PVGIS (0006) et des écarts ERA5 à NASA POWER
(0009) prêtaient au produit PVGIS la hausse de 2021-2023 : le GHI d'ERA5-Land,
qui est celui d'ERA5, la montre aussi (ADR-0024). ERA5-Land ne sert pas de DNI :
les notes du DNI le disent.

Les textes de la révision 0023 sont figés dans ``seeds/donnees/textes_0023.json`` :
chaque mise à jour ne touche qu'un texte resté celui de 0023, et le
``downgrade`` les rend. La migration n'accède jamais au réseau.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import date
from typing import Any

import sqlalchemy as sa
from alembic import op

from kuma_data_core.db.seeds.series_csv import DOSSIER_DONNEES

# revision identifiers, used by Alembic.
revision: str = "0024"
down_revision: str | Sequence[str] | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TEXTES_0023 = DOSSIER_DONNEES / "textes_0023.json"

HYDRO: str = " Référence pour un volet hydrologique non engagé : aucune série au Burkina Faso."

# Colonnes des fiches que la migration peut réécrire.
COLONNES_SOURCES: tuple[str, ...] = (
    "notes",
    "metadonnees",
    "url",
    "organisation",
    "date_consultation",
    "annee_publication",
)

SOURCES: dict[str, dict[str, Any]] = {
    "ecmwf_era5": {
        "notes": (
            "Réanalyse atmosphérique ERA5 du CEPMMT (ECMWF), cinquième génération, produite "
            "pour le Copernicus Climate Change Service (C3S) et distribuée par le Climate "
            "Data Store : valeurs horaires depuis 1940, maille de 0,25°. Référence : "
            "Hersbach H. et al. (2020), « The ERA5 global reanalysis », Q. J. R. Meteorol. "
            "Soc. 146, 1999-2049, DOI 10.1002/qj.3803. Au Burkina Faso, aucune série ne "
            "vient directement de cette fiche : le GHI et le DNI mensuels d'ERA5 sont ceux "
            "que sert PVGIS (source era5_pvgis, ADR-0009) ; la météo et le GHI journaliers "
            "viennent d'ERA5-Land, sa composante terrestre (source ecmwf_era5_land, "
            "ADR-0024). Licence CC BY 4.0 ; attribution : « Generated using Copernicus "
            "Climate Change Service information [année] »."
        ),
        "metadonnees": {
            "acces": (
                "Copernicus Climate Data Store (CDS) API + portail web, gratuit avec "
                "inscription, licence CC BY 4.0 (attribution requise)"
            ),
            "granularite_spatiale": (
                "0.25° × 0.25° (CDS regridded) ; 31 km natif (grille gaussienne réduite "
                "TCo639) ; 137 niveaux verticaux jusqu'à 0.01 hPa (80 km)"
            ),
            "granularite_temporelle": (
                "horaire (native) | journalier (statistiques pré-calculées) | mensuel "
                "(moyennes pré-calculées)"
            ),
            "couverture_temporelle_fin": (
                "ongoing (latence 5 jours ; release préliminaire ERA5T pouvant différer de "
                "la version finale 2-3 mois plus tard)"
            ),
            "couverture_temporelle_debut": "1940-01-01",
        },
    },
    "iec_61724_1_2021": {
        "notes": (
            "Norme IEC 61724-1:2021, « Photovoltaic system performance - Part 1: "
            "Monitoring », édition 2.0 de juillet 2021 (comité technique IEC TC 82), qui "
            "remplace l'édition 1.0 de 2017. Elle définit la terminologie, les équipements "
            "et les méthodes du suivi de la performance des systèmes photovoltaïques, avec "
            "deux classes d'exactitude du suivi (A et B), le suivi des systèmes bifaciaux "
            "et la mesure de la salissure. Texte intégral payant (IEC Webstore) ; "
            "métadonnées publiques sur la page de la publication. Référence de définitions "
            "(ratio de performance, classes de suivi) : aucune série n'en vient. "
            "Citation : « IEC 61724-1:2021, Photovoltaic system performance - Part 1: "
            "Monitoring, International Electrotechnical Commission, Edition 2.0, July "
            "2021 »."
        ),
    },
    "wmo_8_2024": {
        "notes": (
            "Guide des instruments et des méthodes d'observation de l'OMM (WMO-No. 8, "
            "« CIMO Guide »), volume I, « Measurement of Meteorological Variables », "
            "édition 2024 : mesure de la température, de la pression, de l'humidité, du "
            "vent de surface, des précipitations et du rayonnement, entre autres. Accès "
            "libre sur la bibliothèque de l'OMM. Référence des conventions de mesure "
            "météorologique : aucune série n'en vient. Citation : "
            "« WMO, 2024 : Guide to Instruments and Methods of Observation (WMO-No. 8), "
            "2024 edition. World Meteorological Organization, Geneva. ISBN "
            "978-92-63-10008-5. DOI : 10.59327/WMO/CIMO/1 »."
        ),
        "metadonnees": {
            "editeur": "World Meteorological Organization (WMO)",
            "comite_technique": (
                "INFCOM/SC-MINT (Standing Committee on Measurements, Instrumentation and "
                "Traceability) ; anciennement CIMO (Commission for Instruments and Methods "
                "of Observation)"
            ),
            "edition_millesimee": "2024 edition, volume I",
        },
    },
    "wmo_grdc": {
        "notes": (
            "Global Runoff Data Centre (GRDC) : base des débits des cours d'eau mesurés aux "
            "stations hydrométriques du monde, opérée par l'Institut fédéral d'hydrologie "
            "allemand (BfG, Coblence) sous mandat de l'OMM. Débits journaliers et "
            "mensuels. Accès sur demande par le portail de données ; usage non commercial, "
            "sans redistribution, citation requise : « Global Runoff Data Centre of WMO. "
            "56068 Koblenz, Germany: Federal Institute of Hydrology (BfG), [date de "
            "récupération] »." + HYDRO
        ),
        "metadonnees": {
            "acces": (
                "demande via Data Portal `grdc.bafg.de/data/data_portal/` (formulaire + "
                "agreement Terms of Use + Data Sharing Conditions) ; download link envoyé "
                "sous 24h par mail ; usage non-commercial uniquement ; non-redistribution ; "
                "format WaterML2 (standard WMO/OGC) parmi autres formats"
            ),
            "granularite_spatiale": "ponctuelle (stations hydrométriques)",
            "granularite_temporelle": (
                "journalier (mean daily discharge) | mensuel (mean monthly discharge)"
            ),
            "couverture_temporelle_fin": (
                "ongoing (mises à jour continues, lag inhérent à la soumission par services "
                "hydrologiques nationaux)"
            ),
            "couverture_temporelle_debut": "variable selon la station",
        },
    },
    "wwf_hydrosheds": {
        "notes": (
            "HydroSHEDS (WWF) : réseaux fluviaux, bassins versants et modèle numérique de "
            "terrain hydrologiquement conditionné, dérivés de l'altimétrie radar SRTM de "
            "février 2000, de 3 secondes d'arc (90 m) à 5 minutes ; produits HydroBASINS, "
            "HydroRIVERS, HydroLAKES et HydroATLAS. Version 1.1 (documentation technique "
            "v1.4, avril 2022). Usage libre, commercial ou non. Référence : Lehner B., "
            "Verdin K., Jarvis A. (2008), « New global hydrography derived from spaceborne "
            "elevation data », Eos 89(10), 93-94, DOI 10.1029/2008EO100001." + HYDRO
        ),
        "metadonnees": {
            "acces": (
                "libre (free for both non-commercial and commercial use) ; download direct "
                "via data.hydrosheds.org ; alternative programmatique via Google Earth "
                "Engine (catalogue `WWF/HydroSHEDS/...` : 03VFDEM, 03CONDEM, 03DIR à 3 "
                "arc-sec ; 30CONDEM, 30DIR à 30 arc-sec ; HydroBASINS niveaux 9 et 12) ; "
                "License Agreement annexée à la Technical Documentation v1.4"
            ),
            "granularite_spatiale": (
                "raster et vecteur, de 3 secondes d'arc (90 m à l'équateur) à 5 minutes "
                "(10 km) ; qualité dégradée au nord de 60° N, faute de données SRTM"
            ),
            "granularite_temporelle": (
                "snapshot non temporel (référentiel topologique-hydrologique dérivé du DEM "
                "SRTM 2000-02-11/22, donc topologie représentative de l'état observé en "
                "février 2000)"
            ),
            "couverture_temporelle_fin": (
                "2000-02-22 (acquisition SRTM ; les aménagements postérieurs, barrages "
                "compris, n'y figurent pas)"
            ),
            "couverture_temporelle_debut": "2000-02-11 (acquisition SRTM)",
        },
    },
    "iec_60041_1991": {
        "notes": (
            "Norme IEC 60041:1991, « Field acceptance tests to determine the hydraulic "
            "performance of hydraulic turbines, storage pumps and pump-turbines », "
            "édition 3.0 avec le corrigendum 1 de mars 1996 : méthodes des essais de "
            "réception sur site des machines hydrauliques. Texte intégral payant (IEC "
            "Webstore). Citation : « IEC 60041:1991, Field acceptance tests to determine "
            "the hydraulic performance of hydraulic turbines, storage pumps and "
            "pump-turbines, International Electrotechnical Commission, Edition 3.0, "
            "November 1991, with Corrigendum 1 of March 1996 »." + HYDRO
        ),
        "metadonnees": {
            "editeur": "International Electrotechnical Commission (IEC)",
            "comite_technique": "TC 4 - Hydraulic turbines",
            "edition_millesimee": "3.0 (1991-11-30) avec Corrigendum 1 (mars 1996)",
        },
    },
    "wmo_168_2008": {
        "notes": (
            "Guide des pratiques hydrologiques de l'OMM (WMO-No. 168), volume I, "
            "« Hydrology: From Measurement to Hydrological Information », sixième "
            "édition, 2008 : mesure des débits et des niveaux, précipitations, "
            "évapotranspiration, traitement et analyse hydrologiques. Accès libre sur la "
            "bibliothèque de l'OMM. Citation : « WMO, 2008: Guide to Hydrological "
            "Practices. Volume I - Hydrology: From Measurement to Hydrological "
            "Information. WMO-No. 168, sixth edition, World Meteorological Organization, "
            "Geneva. ISBN 978-92-63-10168-6 »." + HYDRO
        ),
        "metadonnees": {
            "editeur": "World Meteorological Organization (WMO)",
            "comite_technique": (
                "Standing Committee on Hydrological Services (SC-HYD) de la Services "
                "Commission (SERCOM) ; anciennement Commission for Hydrology (CHy)"
            ),
            "edition_millesimee": (
                "6e édition (volume I 2008, volume II 2009) ; fiche limitée au volume I"
            ),
        },
    },
    "kuma_calculs": {
        "notes": (
            "Source des grandeurs que Kuma calcule à partir des séries du dépôt (méthode "
            "calcul_derive). Au Burkina Faso : fraction diffuse et écarts mensuels entre "
            "sources aux 398 localités (ADR-0012). La note publique de chaque série "
            "calculée nomme ses sources et ses grandeurs d'entrée."
        ),
    },
    "esmap_wapp": {
        "url": "https://energydata.info/dataset/burkina-faso-solar-radiation-measurement-data",
        "organisation": "World Bank / ESMAP / WAPP (EEEOA) ; opérateur CSP Services GmbH",
        "date_consultation": "2026-10-28",
        "annee_publication": 2024,
        "notes": (
            "Campagne de mesure du rayonnement solaire au sol du WAPP (Système d'échanges "
            "d'énergie électrique ouest-africain), « Solar Development in Sub-Saharan "
            "Africa - Solar resource measurement campaign in West Africa », financée par "
            "la Banque mondiale, stations opérées par CSP Services GmbH. Jeu « Burkina Faso "
            "- Solar Radiation Measurement Data » du portail energydata.info, daté de 2024 "
            "par le portail : quatre stations, Dédougou (27 octobre 2021 au 26 octobre "
            "2023), Dori (12 octobre 2021 au 11 octobre 2023), Kaya (28 avril 2021 au "
            "27 avril 2023) et Koupéla (29 avril 2021 au 28 avril 2023), avec fichiers "
            "contrôlés, en-têtes et rapports de mesure. Licence CC BY 4.0 ; attribution : "
            "« World Bank / ESMAP / WAPP - Solar resource measurement campaign in West "
            "Africa (CC-BY-4.0) ». Aucune série au Burkina Faso : les stations ne sont pas "
            "intégrées (feuille de route, jalon 6). Une série de mesure directe de cette "
            "source serait en confiance A (règle R3)."
        ),
        "metadonnees": {
            "store": "energydata.info (World Bank Group)",
            "licence": "CC-BY-4.0",
            "campagne": (
                "Solar Development in Sub-Saharan Africa - Solar resource measurement "
                "campaign in West Africa (WAPP)"
            ),
            "operateur": "CSP Services GmbH",
            "stations_burkina_faso": ["Dédougou", "Dori", "Kaya", "Koupéla"],
            "niveaux_qc_source": "données contrôlées du fournisseur (fichiers QC)",
        },
    },
}

AUCUNE_VALEUR: str = " Aucune valeur au Burkina Faso."

GRANDEURS: dict[str, str] = {
    "ghi": (
        "Irradiation globale horizontale (Global Horizontal Irradiance). Au Burkina Faso : "
        "NASA POWER (ALLSKY_SFC_SW_DWN : CERES SYN1deg depuis 2001, SRB avant), CAMS "
        "Radiation, SARAH-3 et ERA5 via PVGIS, ERA5-Land, aux pas horaire, journalier ou "
        "mensuel selon la source. Les séries horaires sont servies en Wh/m² sur l'heure."
    ),
    "ghi_exceedance": (
        "Exceedance inter-annuelle de l'irradiation annuelle dérivée de la série GHI "
        "mensuelle 1991-2020 (NASA POWER, climatologie OMM). Pour une localité donnée, le "
        "calcul reconstruit les 30 totaux annuels (somme des 12 mensuels pondérée par le "
        "nombre de jours du mois, années bissextiles incluses) puis extrait deux "
        "percentiles : P50 (médiane) et P90 (valeur dépassée 90 % des années, soit le 10ᵉ "
        "percentile, scénario conservateur). Calculée à la volée à chaque appel, jamais "
        "stockée. Indicateur de variabilité inter-annuelle, qui ne propage pas "
        "l'incertitude de modèle : ce n'est pas un P90 bancable complet."
    ),
    "ecart_relatif_dni_cams": (
        "Écart relatif du DNI de NASA POWER à celui de CAMS Radiation, (nasa - cams) / cams "
        "× 100, en pourcent signé. Famille F1, calculée à la volée. Aucune valeur au "
        "Burkina Faso, où les écarts entre sources sont les grandeurs ecart_relatif_*_nasa, "
        "rapportées à NASA POWER (ADR-0012)."
    ),
    "albedo_surface": (
        "Albédo de surface (réflectivité du sol, sans dimension, de 0 à 1), paramètre "
        "ALLSKY_SRF_ALB de NASA POWER. Entrée de la composante réfléchie des modèles de POA "
        "et du bifacial. Aucune série au Burkina Faso : le POA prend l'albédo de la requête "
        "(albedo_sol, 0,2 par défaut)."
    ),
    "precipitation": (
        "Hauteur de précipitation journalière (mm/jour). Au Burkina Faso : NASA POWER "
        "(PRECTOTCORR, MERRA-2 corrigé par des observations) et ERA5-Land. Entrée pluie du "
        "modèle de salissure HSU (pvlib.soiling.hsu) de la grandeur taux_salissure_proxy. "
        "Confiance B."
    ),
    "pm2_5": (
        "Concentration massique journalière des particules fines de diamètre inférieur ou "
        "égal à 2,5 µm (µg/m³), réanalyse CAMS EAC4 (ADS Copernicus), moyenne journalière "
        "du pas de 3 heures. Entrée particules du modèle de salissure HSU "
        "(pvlib.soiling.hsu) de la grandeur taux_salissure_proxy. Confiance B."
    ),
    "pm10": (
        "Concentration massique journalière des particules de diamètre inférieur ou égal à "
        "10 µm (µg/m³), réanalyse CAMS EAC4 (ADS Copernicus), moyenne journalière du pas "
        "de 3 heures. Entrée particules du modèle de salissure HSU (pvlib.soiling.hsu) de "
        "la grandeur taux_salissure_proxy. Inclut les PM2,5 (PM10 ≥ PM2,5). Confiance B."
    ),
    "vent_2m": (
        "Vitesse moyenne journalière du vent à 2 mètres au-dessus de la surface, paramètre "
        "WS2M de NASA POWER (MERRA-2). Entrée possible du modèle de Faiman (2008), qui "
        "demanderait un calage au sol, pour la température des cellules ; le productible "
        "avec correction thermique utilise le modèle NOCT, sans le vent. Aucune série au "
        "Burkina Faso."
    ),
    "taux_salissure_proxy": (
        "Proxy de salissure des modules PV : perte de transmission par salissure, en %, "
        "soit (1 - ratio HSU) × 100. Modèle HSU (pvlib.soiling.hsu, Coello et Boyle 2019) à partir "
        "des PM2,5 et PM10 de CAMS EAC4 (convertis de µg/m³ en g/m³, unité attendue par "
        "pvlib) et de la pluie de NASA POWER (mm). Calculé à la volée, confiance B. "
        "Inclinaison et seuil de nettoyage par défaut : 10° et 1 mm. Limites : c'est un "
        "modèle, non une mesure de salissure ; il démarre sur des modules propres, ce qui "
        "sous-estime les premiers jours de la fenêtre ; la grille d'EAC4 est de 0,75°."
    ),
    "pr_realiste": (
        "PR effectif propre au site = PR_fourni × ratio_T × (1 - salissure), sans dimension. "
        "Corrections au choix : aucune, température, salissure, ou température et "
        "salissure. Compose le facteur thermique NOCT (Ross 1980, "
        "productible_correction_thermique) et le proxy de salissure HSU "
        "(taux_salissure_proxy). La courbe mensuelle donne le PR saisonnier, avec le creux "
        "de l'Harmattan. Calculé à la volée, confiance B. Le PR_fourni est supposé hors "
        "salissure et hors température, les corrections étant multiplicatives et "
        "séparables : un PR qui les inclut déjà les compterait deux fois."
    ),
    "rang_referentiel": (
        "Rang dans le référentiel : position ordinale d'une série dans le classement des "
        "localités pour une grandeur donnée, calculé à la volée. Grandeur désactivée, "
        "remplacée par rang_referentiel_temporel et rang_referentiel_spatial." + AUCUNE_VALEUR
    ),
    "rang_referentiel_temporel": (
        "Rang temporel dans la climatologie de référence : percentile, par mois calendaire, "
        "de la valeur dans la distribution NASA POWER 1991-2020 de la localité. Formule de "
        "type 7 (numpy, R) : p = (rang - 1) / (n - 1) × 100, bornée à [0, 100]." + AUCUNE_VALEUR
    ),
    "rang_referentiel_spatial": (
        "Rang spatial : rang ordinal d'une localité parmi les localités du périmètre pour "
        "le même mois, calculé à la volée à partir des valeurs mensuelles NASA POWER."
        + AUCUNE_VALEUR
    ),
}

UNITES: dict[str, str] = {
    "gnf_par_kwh": (
        "Devise de la Guinée. Code ISO 4217 : GNF. Émetteur : Banque Centrale de la "
        "République de Guinée (BCRG), change flottant. Unité du catalogue commun ; la "
        "devise du Burkina Faso est le franc CFA UEMOA (xof_par_kwh)."
    ),
    "gnf_par_mwh": "Multiple échelle MWh. 1 GNF/MWh = 0,001 GNF/kWh.",
    "gnf_par_kw": "CAPEX en GNF/kW. Famille A.",
    "gnf_par_wc": "CAPEX PV en GNF/Wc. Famille B (puissance crête PV STC).",
    "gnf_par_kwc": "Multiple échelle kWc pour CAPEX PV en GNF.",
    "tco2_par_habitant_an": (
        "Unité usuelle de l'empreinte carbone individuelle (GIEC, AIE, CCNUCC, Banque "
        "mondiale), sans équivalent SI strict : la personne n'est pas une unité "
        "métrologique du BIPM. Distinction CO2 et CO2eq comme pour intensite_carbone. Ordres "
        "de grandeur : 0,1 tCO2/hab/an au Tchad et au Niger, 14,4 aux États-Unis, 4,7 en "
        "moyenne mondiale."
    ),
    "xof_par_kwh": (
        "Devise officielle des 8 pays UEMOA (Bénin, Burkina Faso, Côte d'Ivoire, "
        "Guinée-Bissau, Mali, Niger, Sénégal, Togo). Code ISO 4217 : XOF. Émetteur : BCEAO "
        "(Banque Centrale des États de l'Afrique de l'Ouest). Parité fixe avec l'euro "
        "depuis 1999 : 1 EUR = 655,957 XOF. Devise de référence au Burkina Faso, sans "
        "conversion automatique vers d'autres devises. Exemples 2024 : tarif BT Sénégal "
        "110 XOF/kWh, Côte d'Ivoire 85 XOF/kWh, Mali 115 XOF/kWh."
    ),
}

# Commentaires de schéma (tables, colonnes et vues), mêmes textes que les modèles.
COMMENTAIRES: dict[str, str] = {
    "grandeurs_metier": (
        "Grandeurs métier calculées par Kuma à partir des mesures brutes : agrégats annuels "
        "et mensuels des grandeurs F1 stockées, et valeurs statiques (dégénérescence de "
        "pixel). Versionnement temporel par (valide_du, valide_au) et contrainte EXCLUDE "
        "BTree-GiST sur l'identité métier étendue à version_formule. Statut éditorial et "
        "niveau de confiance dérivé ou forcé par la couche de service éditoriale."
    ),
    "grandeurs_metier.periode_type": (
        "Granularité temporelle de l'agrégat : annuel (une ligne par localité, grandeur, "
        "année et version de formule ; mois NULL), mensuel (12 lignes par année, mois 1 à 12)"
        " ou statique (une valeur sans période, mois NULL)."
    ),
    "grandeurs_metier.version_formule": (
        "Version de la formule de calcul en vigueur à l'insertion, liée à "
        "grandeurs_referentiel.version_formule_actuelle de la grandeur et incrémentée à "
        "chaque révision méthodologique. Incluse dans la contrainte EXCLUDE pour que deux "
        "versions coexistent après une révision."
    ),
    "grandeurs_referentiel": (
        "Référentiel des grandeurs Kuma : brutes, stockées par Kuma ou calculées à la volée. "
        "La table qui porte les mesures d'une série suit sa source (kuma_calculs : "
        "grandeurs_metier) puis sa granularité et son stockage (series_metadonnees)."
    ),
    "grandeurs_referentiel.code": (
        "Clé naturelle métier (ASCII pur, snake_case, citée par les FK aval). Voir "
        "docs/conventions/01-naming.md."
    ),
    "localites.code_administratif_national": (
        "Code administratif officiel externe. Au Burkina Faso : sous-code ISO 3166-2:BF à "
        "trois lettres des provinces (ex. KAD pour le Kadiogo, ADR-0007). Nullable. "
        "Convention d'identifiant externe, comme sources.doi et sources.isbn."
    ),
    "localites.type_localite": (
        "7 valeurs : continent, region_supranationale, pays, region_administrative, "
        "prefecture, commune, site. Au Burkina Faso, prefecture porte les provinces, commune "
        "les départements et la commune de Ouagadougou (ADR-0007)."
    ),
    "mesures_ressource": (
        "Mesures journalières ingérées depuis les sources externes, en stockage versionné "
        "(les séries denses sont dans mesures_journalieres_denses, ADR-0017). Versionnement "
        "temporel par (valide_du, valide_au) et contrainte EXCLUDE BTree-GiST sur l'identité "
        "métier (serie_id, instant_mesure). Statut éditorial et niveau de confiance dérivé ou"
        " forcé par la couche de service éditoriale."
    ),
    "mesures_ressource_horaires": (
        "Mesures horaires ingérées depuis les sources externes (NASA POWER et CAMS Radiation "
        "aux points pilotes). Pendant horaire de mesures_ressource (journalier) et de "
        "mesures_ressource_mensuelles (mensuel). instant_mesure en TIMESTAMPTZ (UTC), début "
        "de l'heure moyennée, pour le contrôle qualité horaire (position solaire sans "
        "ambiguïté de fuseau). Versionnement temporel par (valide_du, valide_au) et "
        "contrainte EXCLUDE BTree-GiST sur l'identité métier (serie_id, instant_mesure). "
        "Statut éditorial et niveau de confiance dérivé ou forcé par la couche de service "
        "éditoriale."
    ),
    "mesures_ressource_mensuelles": (
        "Mesures mensuelles ingérées depuis les sources externes (NASA POWER, SARAH-3 et ERA5"
        " via PVGIS, CAMS Radiation). Pendant mensuel de mesures_ressource. Versionnement "
        "temporel par (valide_du, valide_au) et contrainte EXCLUDE BTree-GiST sur l'identité "
        "métier (serie_id, annee, mois). Statut éditorial et niveau de confiance dérivé ou "
        "forcé par la couche de service éditoriale."
    ),
    "series_metadonnees.code": (
        "Clé naturelle métier (ASCII pur, snake_case), ex. "
        "nasa_power_ghi_journalier_bfa_com_ouagadougou. Convention : "
        "docs/conventions/01-naming.md."
    ),
    "series_metadonnees.granularite": (
        "Discriminant de granularité temporelle pour le routage vers la table cible "
        "(journalier, mensuel, horaire). NULL pour les séries kuma_calculs, routées par "
        "source vers grandeurs_metier, dont la temporalité est portée par "
        "grandeurs_metier.periode_type."
    ),
    "series_metadonnees.methode_collecte": (
        "Méthode dominante de collecte de la série : mesure_directe, modele_satellitaire, "
        "reanalyse, interpolation_geographique, extrapolation_temporelle, calcul_derive ou "
        "expertise_humaine (CHECK). Elle entre dans le niveau de confiance dérivé "
        "(docs/contribution/confiance-et-statuts.md)."
    ),
    "sources.fiabilite": (
        "Qualification éditoriale Kuma de la source : haute, moyenne ou faible. Elle entre "
        "dans le niveau de confiance dérivé (docs/contribution/confiance-et-statuts.md)."
    ),
    "sources.type_source": (
        "11 valeurs autorisées : rapport, article_scientifique, texte_legal, communique, "
        "page_web, base_donnees, livre, chapitre_livre, these, norme_technique (sources "
        "documentaires externes) et auteur_kuma (couche éditoriale interne, source "
        "kuma_calculs)."
    ),
    "grandeurs_metier.niveau_confiance_derive": (
        "Niveau de confiance dérivé par la couche de service à partir des règles R1 à R4 "
        "(docs/contribution/confiance-et-statuts.md), selon la méthode de collecte et la "
        "source de la série. A = haute, B = moyenne, C = basse."
    ),
    "mesures_ressource.niveau_confiance_derive": (
        "Niveau de confiance dérivé par la couche de service à partir des règles R1 à R4 "
        "(docs/contribution/confiance-et-statuts.md), selon la méthode de collecte et la "
        "source de la série. A = haute, B = moyenne, C = basse."
    ),
    "sources.code": (
        "Identifiant court unique. Convention : <organisme>_<theme>[_<annee>], ex. "
        "ecmwf_era5_land, cams_radiation, wmo_8_2024. Pour les publications récurrentes ou "
        "éditées, inclure l'année."
    ),
    "unites": (
        "Référentiel des unités de mesure de Kuma Data Core : 162 unités sur 38 grandeurs, "
        "validées contre plus de 20 organismes normatifs internationaux (BIPM, AIE, ONU, "
        "NIST, IUPAC, IEC, DIN, ISO, IPCC, IRENA, UNECE, etc.)."
    ),
    "v_grandeurs_metier_courantes": (
        "Vue des lignes courantes de grandeurs_metier (valide_au IS NULL), en version de "
        "formule actuelle (version_formule = grandeurs_referentiel.version_formule_actuelle) "
        "et hors statut deprecie. Ajoute niveau_effectif = "
        "COALESCE(niveau_confiance_override, niveau_confiance_derive), équivalent SQL de "
        "l'hybrid_property GrandeurMetier.niveau_effectif."
    ),
    "v_mesures_avec_niveau_effectif": (
        "Vue de mesures_ressource avec la colonne calculée niveau_effectif = "
        "COALESCE(niveau_confiance_override, niveau_confiance_derive), équivalent SQL de "
        "l'hybrid_property MesureRessource.niveau_effectif, pour les lectures en masse."
    ),
}

# Séries ERA5 de PVGIS (0006) et écarts ERA5 à NASA POWER (0009).
MENSUELLES_AVANT: str = (
    "plus que les autres sources : changement probable du produit PVGIS-ERA5, non établi."
)
ECARTS_AVANT: str = "son niveau monte en 2021-2023 (changement probable du produit PVGIS-ERA5)."
CAUSE: str = (
    "La hausse du GHI se retrouve dans ERA5-Land : elle vient d'ERA5 lui-même, non du "
    "traitement de PVGIS (ADR-0024)."
)
DNI_NON_VERIFIE: str = " Celle du DNI n'est pas vérifiée : ERA5-Land ne sert pas de DNI."

# (motif des codes, source, texte de 0023, texte de 0024).
NOTES_ERA5: tuple[tuple[str, str, str, str], ...] = (
    (
        "era5\\_ghi\\_mensuel\\_bfa\\_%",
        "era5_pvgis",
        MENSUELLES_AVANT,
        "plus que les autres sources. " + CAUSE,
    ),
    (
        "era5\\_dni\\_mensuel\\_bfa\\_%",
        "era5_pvgis",
        MENSUELLES_AVANT,
        "plus que les autres sources. " + CAUSE + DNI_NON_VERIFIE,
    ),
    (
        "ecart\\_ghi\\_era5\\_nasa\\_bfa\\_%",
        "kuma_calculs",
        ECARTS_AVANT,
        "son niveau monte en 2021-2023. " + CAUSE,
    ),
    (
        "ecart\\_dni\\_era5\\_nasa\\_bfa\\_%",
        "kuma_calculs",
        ECARTS_AVANT,
        "son niveau monte en 2021-2023. " + CAUSE + DNI_NON_VERIFIE,
    ),
)
NB_NOTES_ATTENDU: int = 398  # une note par localité, pour chaque motif


def _textes_0023() -> dict[str, dict[str, Any]]:
    textes: dict[str, dict[str, Any]] = json.loads(TEXTES_0023.read_text(encoding="utf-8"))
    for code, fiche in SOURCES.items():
        if set(fiche) != set(textes["sources"][code]):
            raise RuntimeError(f"Migration 0024 : champs de la fiche {code!r} incohérents.")
    if (
        set(GRANDEURS) != set(textes["grandeurs"])
        or set(UNITES) != set(textes["unites"])
        or set(COMMENTAIRES) != set(textes["commentaires"])
    ):
        raise RuntimeError("Migration 0024 : grandeurs, unités ou commentaires incohérents.")
    return textes


def _valeur(colonne: str, valeur: Any) -> Any:
    if colonne == "metadonnees":
        return json.dumps(valeur, ensure_ascii=False)
    if colonne == "date_consultation":
        return date.fromisoformat(valeur)
    return valeur


def _fiche(bind: sa.Connection, code: str, cible: dict[str, Any], depuis: dict[str, Any]) -> int:
    """Passe la fiche ``code`` de ``depuis`` à ``cible`` ; une fiche modifiée entre-temps reste."""
    colonnes = [c for c in COLONNES_SOURCES if c in cible]
    affectations = ", ".join(
        f"{c} = CAST(:n_{c} AS jsonb)" if c == "metadonnees" else f"{c} = :n_{c}" for c in colonnes
    )
    # IS NOT DISTINCT FROM : un champ vide à 0023 (annee_publication) se compare aussi.
    gardes = " AND ".join(
        f"{c} IS NOT DISTINCT FROM CAST(:a_{c} AS jsonb)"
        if c == "metadonnees"
        else f"{c} IS NOT DISTINCT FROM :a_{c}"
        for c in colonnes
    )
    parametres: dict[str, Any] = {"code": code}
    for c in colonnes:
        parametres[f"n_{c}"] = _valeur(c, cible[c])
        parametres[f"a_{c}"] = _valeur(c, depuis[c])
    return bind.execute(
        sa.text(
            f"UPDATE sources SET {affectations}, modifie_le = now() WHERE code = :code AND {gardes}"
        ),
        parametres,
    ).rowcount


def _texte(
    bind: sa.Connection, table: str, colonne: str, code: str, cible: str, depuis: str
) -> int:
    return bind.execute(
        sa.text(
            f"UPDATE {table} SET {colonne} = :n, modifie_le = now() "
            f"WHERE code = :code AND {colonne} = :a"
        ),
        {"n": cible, "a": depuis, "code": code},
    ).rowcount


def _remplacer(bind: sa.Connection, motif: str, source: str, ancienne: str, nouvelle: str) -> int:
    """Remplace ``ancienne`` par ``nouvelle`` dans les notes des séries ``motif`` d'une source."""
    return bind.execute(
        sa.text(
            "UPDATE series_metadonnees SET note_publique = replace(note_publique, :a, :n), "
            "modifie_le = now() "
            "WHERE code LIKE :motif AND strpos(note_publique, :a) > 0 "
            "AND source_id = (SELECT id FROM sources WHERE code = :source)"
        ),
        {"a": ancienne, "n": nouvelle, "motif": motif, "source": source},
    ).rowcount


def _objet(bind: sa.Connection, cle: str) -> str:
    table, _, colonne = cle.partition(".")
    if colonne:
        return f"COLUMN public.{table}.{colonne}"
    genre = bind.execute(
        sa.text("SELECT relkind FROM pg_class WHERE oid = CAST(:t AS regclass)"),
        {"t": f"public.{table}"},
    ).scalar_one()
    return f"{'VIEW' if genre == 'v' else 'TABLE'} public.{table}"


def _commentaire(bind: sa.Connection, cle: str) -> str | None:
    table, _, colonne = cle.partition(".")
    if colonne:
        return bind.execute(
            sa.text(
                "SELECT col_description(attrelid, attnum) FROM pg_attribute "
                "WHERE attrelid = CAST(:t AS regclass) AND attname = :c"
            ),
            {"t": f"public.{table}", "c": colonne},
        ).scalar_one_or_none()
    return bind.execute(
        sa.text("SELECT obj_description(CAST(:t AS regclass), 'pg_class')"),
        {"t": f"public.{table}"},
    ).scalar_one_or_none()


def _commenter(bind: sa.Connection, cle: str, cible: str, depuis: str) -> bool:
    """Passe le commentaire ``cle`` de ``depuis`` à ``cible`` ; un commentaire modifié reste."""
    if _commentaire(bind, cle) != depuis:
        return False
    litteral = bind.execute(sa.text("SELECT quote_literal(:t)"), {"t": cible}).scalar_one()
    # COMMENT ON n'accepte pas de paramètre lié : le texte, échappé par quote_literal, est
    # inséré tel quel. exec_driver_sql évite que sa.text lise « :BF » (ISO 3166-2:BF) comme
    # un paramètre, et no_parameters que le pilote lise un « % » comme un marqueur.
    # L'option vaut pour cette seule instruction : posée sur la connexion, elle resterait
    # active pour les migrations suivantes du même upgrade.
    bind.exec_driver_sql(
        f"COMMENT ON {_objet(bind, cle)} IS {litteral}",
        execution_options={"no_parameters": True},
    )
    return True


def upgrade() -> None:
    bind = op.get_bind()
    textes = _textes_0023()
    for code, fiche in SOURCES.items():
        if _fiche(bind, code, fiche, textes["sources"][code]) != 1:
            raise RuntimeError(f"Migration 0024 : fiche {code!r} absente ou déjà modifiée.")
    for code, description in GRANDEURS.items():
        avant = textes["grandeurs"][code]
        if _texte(bind, "grandeurs_referentiel", "description", code, description, avant) != 1:
            raise RuntimeError(f"Migration 0024 : grandeur {code!r} absente ou déjà modifiée.")
    for code, note in UNITES.items():
        avant = textes["unites"][code]
        if _texte(bind, "unites", "note_methodologique", code, note, avant) != 1:
            raise RuntimeError(f"Migration 0024 : unité {code!r} absente ou déjà modifiée.")
    for cle, commentaire in COMMENTAIRES.items():
        if not _commenter(bind, cle, commentaire, textes["commentaires"][cle]):
            raise RuntimeError(f"Migration 0024 : commentaire {cle!r} absent ou déjà modifié.")
    for motif, source, ancienne, nouvelle in NOTES_ERA5:
        n = _remplacer(bind, motif, source, ancienne, nouvelle)
        if n != NB_NOTES_ATTENDU:
            raise RuntimeError(
                f"Migration 0024 : {n} notes {motif!r} remplacées, {NB_NOTES_ATTENDU} attendues."
            )


def downgrade() -> None:
    bind = op.get_bind()
    textes = _textes_0023()
    for motif, source, ancienne, nouvelle in NOTES_ERA5:
        _remplacer(bind, motif, source, nouvelle, ancienne)
    for cle, commentaire in COMMENTAIRES.items():
        _commenter(bind, cle, textes["commentaires"][cle], commentaire)
    for code, note in UNITES.items():
        _texte(bind, "unites", "note_methodologique", code, textes["unites"][code], note)
    for code, description in GRANDEURS.items():
        _texte(
            bind,
            "grandeurs_referentiel",
            "description",
            code,
            textes["grandeurs"][code],
            description,
        )
    for code, fiche in SOURCES.items():
        _fiche(bind, code, textes["sources"][code], fiche)
