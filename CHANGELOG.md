# Changelog

Le format suit [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/) et
le projet suit le versionnement sémantique.

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
