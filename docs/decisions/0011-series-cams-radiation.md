# ADR-0011 : séries mensuelles CAMS Radiation

Date : 2026-10-15. Statut : accepté.

## Contexte

Le lot mensuel (ADR-0009) laisse le DNI sans arbitrage : NASA POWER, SARAH-3 et
ERA5 donnent de 3,89 à 6,36 kWh/m²/jour en moyenne sur les communes, et le DHI
n'a qu'une source. CAMS Radiation (service v4.6, méthodes Heliosat-4 et
McClear) restitue GHI, DNI et DHI à partir de l'imagerie Meteosat et des
aérosols analysés au jour le jour par CAMS, là où SARAH-3 et ERA5 s'appuient
sur une climatologie d'aérosols. Le service est diffusé par l'ADS Copernicus,
qui demande une clé.

## Décision

- Points : les 47 provinces et les 351 communes, comme le mensuel (ADR-0009).
- Source `cams_radiation` (id 13, déjà au référentiel). Grandeurs `ghi`,
  `dni` (colonne BNI du service) et `dhi`, `modele_satellitaire`, confiance B
  (règle R4), statut `brut`, granularité `mensuel`. Période : 2005 à 2025,
  années complètes servies (CAMS commence en février 2004). Codes
  `cams_<grandeur>_mensuel_<localité>`.
- Valeur : l'ADS sert l'irradiation tous temps (`sky_type=observed_cloud`)
  intégrée sur le mois, en Wh/m² ; elle est ramenée en moyenne journalière du
  mois, en kWh/m²/jour (division par 1 000 et par le nombre de jours). Les
  colonnes sont repérées par leur nom dans l'en-tête.
- Bornes de plausibilité : celles du mensuel (8,5, 10 et 6), au-dessus des
  maxima servis (7,48, 8,23 et 3,67).
- Stockage : six CSV gzip `cams_<grandeur>_mensuel_<lot>.csv.gz`, même contrat
  que l'ADR-0009, produits par `scripts/ingest_cams_radiation_mensuel.py` (clé
  `ADS_API_KEY`). Migration 0008, trigger d'audit des mesures suspendu le temps
  du déversement.
- Accès : l'ADS met chaque requête en file (3 à 5 min) et refuse les requêtes
  au-delà d'un nombre en file par compte. L'ingesteur envoie les requêtes en
  parallèle et reprend les refus ; avec 10 à 16 requêtes simultanées, les 398
  requêtes ont pris un peu moins de 3 h.

## Conséquences

- 1 194 séries et 300 888 mesures ; la migration 0008 dure 25 s environ.
- Qualité déclarée par le service dans ses réponses (colonne non versionnée) :
  part de données fiables d'au moins 0,96 chaque mois, aucune valeur absente.
  GHI, DNI et DHI ferment : DHI ≤ GHI et GHI - DHI ≤ DNI tous les mois, à
  l'inverse de NASA POWER.
- Une série propre à chaque point. Sur 2005-2023, la corrélation entre
  latitude et GHI moyen des communes vaut 0,90, la plus faible des quatre
  sources (0,93 à 0,99 pour les autres). Le DNI CAMS suit peu la latitude
  (0,37, contre 0,83 à 0,99) ; ses écarts locaux suivent l'altitude du point
  retenue par le service. Ainsi Banfora (316 m) et Toussiana (480 m),
  distantes de 26 km, diffèrent de 5,8 % en DNI, contre 0,3 % pour SARAH-3.
- Moyennes 2005-2023 sur les communes, en kWh/m²/jour :

  | Grandeur | CAMS | NASA POWER | SARAH-3 | ERA5 |
  |---|---|---|---|---|
  | GHI | 6,00 | 5,79 | 6,22 | 6,02 |
  | DNI | 4,92 | 3,89 | 5,77 | 6,36 |
  | DHI | 2,51 | 2,58 | | |

- Le DNI CAMS se place entre NASA POWER et SARAH-3. Sur les séries mensuelles
  2005-2023, cycle saisonnier compris, CAMS suit d'abord NASA POWER
  (corrélation médiane par commune de 0,93 pour le GHI comme pour le DNI),
  puis SARAH-3 (0,87 et 0,83) et ERA5 (0,76 et 0,64). Une fois le cycle
  saisonnier retiré, l'ordre reste le même (0,88 et 0,85 ; 0,70 et 0,52 ;
  0,47 et 0,29). Ce lot ne désigne pas de référence ; le contrôle qualité
  s'appuiera sur ces écarts.
- CAMS confirme cinq des six mois SARAH-3 abaissés (ADR-0009) : le rapport
  SARAH-3/CAMS du GHI y perd de 7 à 16 % par rapport aux mêmes mois des autres
  années (écart type de 2,5 % hors de ces mois). Octobre 2016 (-4 %) ne s'en
  distingue pas.
- Pas de rupture après 2020 : 2021-2025 dépasse 2016-2020 de 0,6 % (GHI et
  DNI) et 0,8 % (DHI), dans la variabilité interannuelle.
- CAMS et SARAH-3 exploitent tous deux l'imagerie Meteosat : leur accord ne
  vaut pas deux confirmations indépendantes. La note publique des séries GHI
  et DNI le rappelle.
