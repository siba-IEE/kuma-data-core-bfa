# Changelog

Le format suit [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/) et
le projet suit le versionnement sémantique.

## 0.18.0

- Météo et rayonnement journaliers ERA5-Land aux 398 localités, 2005-2025
  (ADR-0024, migration 0023) : température moyenne, minimale et maximale,
  point de rosée, pression de surface, vent à 10 m et sa direction, pluie et
  GHI, agrégés du jour UTC à partir des valeurs horaires de la réanalyse
  (maille de 0,1°), en stockage dense ; 3 582 séries et 25 610 130 valeurs.
  `scripts/ingest_era5_land_journalier.py`.
- Les notes disent l'origine de chaque famille (température, humidité et
  pression ramenées à l'altitude de la maille ; pluie, rayonnement et vent
  du forçage ERA5 interpolé) et les écarts à NASA POWER, dont un tiers de
  pluie en moins ; le GHI, celui d'ERA5, reste une source de comparaison.
  Fiche de la source `ecmwf_era5_land` réécrite pour le Burkina Faso.
- La capsule d'étude prend ses records de température chez NASA POWER
  seulement (`SOURCE_TEMPERATURES`).

## 0.17.0

- Rayonnement horaire CAMS Radiation aux cinq points pilotes, 2021-2025
  (ADR-0023, migration 0022) : GHI, DNI et DHI tous temps et GHI par ciel
  clair, irradiation de l'heure UTC datée du début de l'heure ; 20 séries et
  876 480 mesures, toutes `valide_auto` au contrôle qualité v1, avec
  0,3 % des heures de jour hors tolérance de fermeture.
  `scripts/ingest_cams_radiation_horaire.py`.
- `/v1/horaire` : paramètre `source` (`nasa_power` ou `cams_radiation`),
  champ `source` dans la réponse JSON et grandeur `ghi_ciel_clair`. Sans
  source, la série de NASA POWER, source du relais, reste servie ; une série
  CAMS ne se relaie pas hors de la plage stockée, et le refus donne la plage
  de la série.
- La capsule d'étude retient la série horaire de NASA POWER, source du
  relais, quand CAMS couvre la même période.

## 0.16.0

- Rayonnement journalier SARAH-3 aux 398 localités, 2005-2023 (ADR-0022,
  migration 0021) : GHI, DNI et DHI, totaux du jour UTC des valeurs horaires
  de PVGIS, en stockage dense ; 1 194 séries et 8 178 425 valeurs. Les heures
  que SARAH-3 ne sert pas, rendues nulles par PVGIS, sont complétées au
  prorata du ciel clair, comme le fait le CM SAF ; un jour reste sans valeur
  quand les heures manquantes d'affilée couvrent plus de la moitié de son
  ciel clair (14 dates, les mêmes partout). Les notes signalent l'effet des
  aérosols, que la climatologie de SARAH-3 ne suit pas.
  `scripts/ingest_pvgis_sarah3_journalier.py`.
- Le mensuel SARAH-3 compte comme nulles les heures non servies : les notes
  des séries mensuelles et des écarts mensuels à NASA POWER donnent la liste
  mesurée des huit mois sous-estimés, août 2009 et décembre 2014 compris.
  Fiche de la source `sarah3_monthly` réécrite pour le Burkina Faso.

## 0.15.0

- Météo complémentaire NASA POWER aux 398 localités, 2005-2025 (ADR-0021,
  migration 0020) : températures minimale et maximale, point de rosée, vent
  moyen et maximal à 10 m, direction du vent, vent à 50 m, pression de
  surface et nébulosité, en stockage dense ; huit grandeurs et deux unités
  d'angle ajoutées au référentiel, 3 582 séries et 5 345 990 valeurs.
  `scripts/ingest_nasa_power_journalier.py --famille meteo_complementaire
  --lot localites`.
- Fiche de la source `nasa_power` mise au Burkina Faso.
- Feuille de route : le jalon 5 porte le brut satellite et de réanalyse
  (SARAH-3, ERA5-Land, météo NASA POWER, CAMS horaire) ; le terrain et la
  confiance A passent au jalon 6.

## 0.14.0

- Rayonnement journalier CAMS Radiation aux 398 localités, 2005-2025
  (ADR-0020, migration 0019) : GHI, DNI et DHI tous temps, GHI et DNI par ciel
  clair, en stockage dense ; deux grandeurs de ciel clair ajoutées au
  référentiel, 1 990 séries et 15 104 026 valeurs. Les jours non servis de
  2005-2006 restent sans valeur. Fiche de la source `cams_radiation` mise au
  Burkina Faso. `scripts/ingest_cams_radiation_journalier.py`.
- Le POA en moyenne journalière surestime le direct avec la géométrie du midi
  solaire : 18,5 % de trop sur un plan horizontal avec CAMS à Fô, 6 % avec
  NASA POWER, dont le DNI trop faible compense en partie le biais (ADR-0020).
  En ce mode, la réponse de `poa_parametrable` et de `poa_bifacial` porte un
  champ `limite` qui donne l'écart au GHI, sur un plan horizontal, des jours
  demandés ; la correction de la méthode est inscrite à la feuille de route.

## 0.13.0

- Épaisseur optique des aérosols à 550 nm, CAMS EAC4, aux 398 localités
  (ADR-0019, migration 0018) : totale, des poussières et de la matière
  organique, journalière 2005-2025 en stockage dense ; trois grandeurs
  ajoutées au référentiel, 1 194 séries sur 51 mailles. Le partage entre
  espèces est modélisé : la matière organique n'indique les fumées qu'au sud,
  de novembre à mars. Fiche de la source `cams_eac4` mise à jour.
  `scripts/ingest_cams_eac4_journalier.py --famille aod --lot localites`.
- L'ingesteur EAC4 sert deux familles (`--famille pm` ou `aod`) : même forme
  de requête, mêmes fonctions de cache et même recette, fichiers de cache
  propres à chaque famille.

## 0.12.0

- Particules fines CAMS EAC4 aux 351 communes (ADR-0018, migration 0017) :
  PM2.5 et PM10 journaliers 2005-2025 en stockage dense, 702 séries sur
  51 mailles. `scripts/ingest_cams_eac4_journalier.py --lot communes`.
- Bornes hautes du PM2.5 et du PM10 relevées à 2 000 et 3 000 µg/m³ : le
  panache de feux de brousse servi à Madjoari le 13 novembre 2013
  (1 143 µg/m³ de PM2.5) est gardé.
- Proxy de salissure et PR réaliste corrigé de la salissure aux communes ; un
  jour de pluie sans valeur y compte 0 mm et la réponse le signale (dix jours
  au plus, au-delà la série est refusée).

## 0.11.0

- Stockage dense des séries journalières (ADR-0017, migration 0015) : table
  `mesures_journalieres_denses`, une ligne par série et par année, sans
  versionnement ni audit ligne à ligne ; partage des mesures entre séries
  d'une même maille (`serie_porteuse_id`) ; vue `v_mesures_journalieres` lue
  par l'API et les services de grandeurs ; garde-fous par triggers. Fichiers
  Parquet versionnés sous `seeds/donnees/denses/`, avec points interrogés,
  version de la source et valeurs écartées.
- NASA POWER journalier aux 351 communes, 2005-2025 (migration 0016) : GHI,
  DNI, DHI, température, humidité et pluie, soit 2 106 séries et
  2 646 149 valeurs. `scripts/ingest_nasa_power_journalier.py --lot communes`.
- Pluie de décembre 2025 : les deux valeurs servies au-delà de 500 mm le
  2 décembre (Sidéradougou, Tiéfora) sont écartées ; les autres jours de
  décembre 2025 au-dessus de 3 mm, hors de l'enveloppe 2005-2024, sont
  signalés dans la note de 125 communes et de 13 provinces, comme les valeurs
  au-dessus du record national de 263 mm (Kpuéré, Sidéradougou, Tiéfora).

## 0.10.0

- Fiche d'incertitude inter-source (ADR-0016) :
  `/v1/grandeurs/incertitude_inter_source` lit les sept écarts mensuels à NASA
  POWER de l'ADR-0012 sur la fenêtre commune 2005-2023, au lieu des grandeurs
  guinéennes, pour les 398 localités ; la collection lit une page en deux
  requêtes.
- Dégénérescence de pixel aux 398 localités (migration 0014) : nombre d'autres
  localités dont la série mensuelle GHI NASA POWER est identique.

## 0.9.0

- Particules fines CAMS EAC4 aux 47 provinces (ADR-0015) : PM2.5 et PM10
  journaliers 2005-2025, moyenne des pas de 3 h de la réanalyse à la maille
  la plus proche, soit 94 séries et 720 980 mesures relues dans des CSV
  versionnés (migration 0013). Ingesteur
  `scripts/ingest_cams_eac4_journalier.py`. Fiche de la source `cams_eac4`
  mise à la période servie au Burkina Faso.
- Le proxy de salissure et le PR réaliste corrigé de la salissure répondent
  désormais aux provinces ; tests d'intégration au Kadiogo.

## 0.8.0

- Séries horaires NASA POWER aux cinq points pilotes (ADR-0014) : Ouagadougou,
  Dédougou, Dori, Kaya et Koupéla, GHI, DNI, DHI et température 2021-2025,
  soit 20 séries et 876 480 mesures relues dans des CSV versionnés (migration
  0011). Ingesteur `scripts/ingest_nasa_power_horaire.py`.
- Contrôle qualité horaire, doctrine v1 (migration 0012) : toutes les lignes
  passent en `valide_auto`, drapeaux en commentaire ; géométrie solaire au
  milieu de l'heure. `/v1/horaire` sert ces séries validées.
- POA horaire, mono-plan et bifacial : géométrie au milieu de l'heure et
  direct reconstruit sur le GHI et le DHI, borné à l'éclairement
  extraterrestre ; seule la compagne DHI horaire est requise.
- Intégration horaire : seuls les jours UTC complets (24 heures présentes et
  validées) entrent dans le calcul.

## 0.7.0

- Météo journalière NASA POWER aux 47 provinces (ADR-0013) : température,
  humidité relative et précipitations 1991-2025, réanalyse MERRA-2, soit
  141 séries et 1 802 544 mesures relues dans des CSV versionnés (migration
  0010). Les contrats de séries gagnent une borne basse incluse ; l'ingesteur
  journalier exige désormais `--famille rayonnement` ou `--famille meteo`.
- Grandeurs calculées : séries compagnes trouvées par recouvrement de
  périodes ; P50/P90 limité à la série mensuelle et à la normale 1991-2020 ;
  repli du POA par la corrélation journalière d'Erbs. Tests d'intégration de
  chaque grandeur sur une province.

## 0.6.0

- Grandeurs dérivées stockées aux 47 provinces et aux 351 communes (ADR-0012) :
  sept écarts relatifs mensuels à NASA POWER (GHI SARAH-3, ERA5 et CAMS ; DNI
  SARAH-3, ERA5 et CAMS ; DHI CAMS), nouvelles grandeurs 35 à 41, et fraction
  diffuse NASA POWER mensuelle et annuelle, soit 3 184 séries `kuma_calculs`
  et 793 214 valeurs calculées en SQL par la migration 0009.

## 0.5.0

- CAMS Radiation : 1 194 séries mensuelles GHI, DNI et DHI aux 47 provinces et
  aux 351 communes, 2005-2025, en confiance B, soit 300 888 mesures relues dans
  des CSV versionnés (ADR-0011).
- Mise en garde dans la note publique des séries GHI et DNI : CAMS et SARAH-3
  exploitent tous deux l'imagerie Meteosat.
- Ingesteur `scripts/ingest_cams_radiation_mensuel.py` (clé `ADS_API_KEY`) ;
  attribution CAMS dans le README et NOTICE.

## 0.4.0

- Séries journalières NASA POWER aux 47 provinces, en confiance B : GHI
  1991-2025, DNI et DHI 2001-2025, soit 141 séries et 1 459 162 mesures relues
  dans des CSV versionnés (ADR-0010).
- Ingesteur `scripts/ingest_nasa_power_journalier.py` ; lecture et écriture des
  CSV journaliers dans `series_csv.py`.

## 0.3.0

- Donnée solaire brute : 2 786 séries mensuelles aux 47 provinces et aux
  351 communes, en confiance B. NASA POWER (GHI 1991-2025, DNI et DHI
  2001-2025), SARAH-3 et ERA5 via PVGIS (GHI et DNI 2005-2023), soit 768 936
  mesures relues dans des CSV versionnés (ADR-0009).
- Mises en garde dans la note publique des séries : maille de 1° de NASA POWER,
  six mois SARAH-3 abaissés par des journées satellite manquantes, niveau ERA5
  plus élevé après 2020.
- Source `era5_pvgis` et méthode de collecte `reanalyse`.
- Ingesteurs `scripts/ingest_nasa_power_mensuel.py` et
  `scripts/ingest_pvgis_mensuel.py`.

## 0.2.0

- Localités : les 351 communes (niveau `commune`), soit les 350 départements de
  l'annexe II du décret n°2025-1012 et la commune de Ouagadougou, rattachées à
  leur province, avec coordonnées Wikidata (deux centroïdes de contour COD-AB,
  ADR-0008) et population RGPH 2019 (INSD).

## 0.1.0

Amorçage de l'instance Burkina Faso, à partir d'un socle propre.

- Schéma : baseline unique regroupant le schéma complet du moteur (tables, vues,
  contraintes, index, fonctions PL/pgSQL, triggers d'audit et de validation
  hiérarchique, extension `btree_gist`), sans donnée.
- Référentiels génériques : unités, catalogue des grandeurs, sources amont (NASA
  POWER, ERA5 et ERA5-Land, SARAH-3 via PVGIS, CAMS, ESMAP/WAPP, normes IEC et
  WMO).
- Localités : le pays `bfa` (ISO 3166-1 alpha-3 : BFA), les 17 régions
  (`region_administrative`) et les 47 provinces (`prefecture`) du découpage de
  2025 (décrets n°2025-1012 et n°2025-1003), avec coordonnées Wikidata et
  population RGPH 2019 (INSD). Mapping de la hiérarchie et règle de sélection
  des coordonnées : ADR-0007 et ADR-0008. Départements à venir.
- Ingestion en mode direct (appel des sources amont), sans repli hors-ligne sur
  seed.
