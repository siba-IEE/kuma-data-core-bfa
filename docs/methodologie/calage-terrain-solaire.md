# Calage terrain du rayonnement satellite

> Note de méthode du jalon 6 de la feuille de route (terrain, confiance A),
> reporté : aucune mesure sol n'est encore ingérée. Elle pose le principe
> du passage de la confiance B à la confiance A, ce que les stations ESMAP/WAPP
> du Burkina Faso peuvent apporter et ce qu'elles ne peuvent pas apporter.

## 1. Principe

Toutes les séries du dépôt sont en confiance B : modèles satellitaires et
réanalyses (règle R4, voir
[confiance et statuts](../contribution/confiance-et-statuts.md)). La
confiance A est réservée à la mesure sol (règle R3) ; la couche A est vide.

Le terrain sert à caler le satellite. Une station donne une vérité de
point sur sa période de mesure ; le satellite et la réanalyse donnent la
couverture dans l'espace et dans le temps. La mesure est en A au point de
la station et sur sa période ; le champ satellite corrigé par la station
n'est pas une mesure. La qualité du résultat dépend donc de celle du
satellite qu'on corrige.

## 2. Les stations ESMAP/WAPP du Burkina Faso

Le jeu « Burkina Faso - Solar Radiation Measurement Data » du portail
energydata.info (World Bank Group, auteur CSP Services GmbH) publie quatre
stations de la campagne « Solar Development in Sub-Saharan Africa - Solar
resource measurement campaign in West Africa » du WAPP, financée par la
Banque mondiale. Licence CC BY 4.0.

| Station | Point pilote | Période de mesure |
|---|---|---|
| Dédougou | `bfa_dep_dedougou` | 27 octobre 2021 au 26 octobre 2023 |
| Dori | `bfa_dep_dori` | 12 octobre 2021 au 11 octobre 2023 |
| Kaya | `bfa_dep_kaya` | 28 avril 2021 au 27 avril 2023 |
| Koupéla | `bfa_dep_koupela` | 29 avril 2021 au 28 avril 2023 |

Chaque station a deux fichiers CSV contrôlés (un par année de mesure), un
fichier d'en-tête (xlsx) et ses rapports de mesure ; Dédougou et Dori ont en
plus leur rapport d'installation. Le portail filtre les téléchargements
automatisés : les fichiers se récupèrent depuis un navigateur.

Les quatre départements sont des points pilotes : NASA POWER (ADR-0014) et
CAMS Radiation (ADR-0023) y ont des séries horaires sur 2021-2025, qui
recouvrent toute la période des stations. Les stations vont de 12,2 °N
(Koupéla) à 14,0 °N (Dori). Coordonnées exactes, cadence, instruments et
grandeurs mesurées sont à lire dans les en-têtes et les rapports avant
l'ingestion.

## 3. Méthode

### 3.1 Décomposition de l'erreur satellite

Le biais du satellite en un site a deux composantes :

- une erreur régionale, partagée par une zone de climat homogène (aérosols
  et poussières de saison sèche mal suivis, biais de calibration de la chaîne
  satellite), qui se transfère par analogie climatique ;
- une erreur locale, propre au pixel (relief, microclimat), qui ne se
  transfère pas.

Une correction se transfère d'autant mieux que la part régionale domine et
que la zone visée est homogène.

### 3.2 Familles de correction

Au pixel de la station, sur la période de recouvrement, par raffinement
croissant (revue de Polo et al. 2016) :

1. Correction de biais : facteur additif ou multiplicatif sur le biais
   moyen. Simple et robuste, suffisante en première approche pour le GHI.
2. Correction de distribution (quantile mapping) : la fonction de
   répartition du satellite est alignée sur celle du sol. Elle corrige la
   forme de la distribution, ce qui compte pour le DNI.
3. Régression : le sol régressé sur le satellite avec des covariables
   physiques (indice de clarté, élévation solaire, épaisseur optique des
   aérosols). L'épaisseur optique CAMS EAC4 est déjà en base aux
   398 localités (ADR-0019).

### 3.3 Transfert dans l'espace

Avec une seule station, la correction se transfère aux localités voisines
par analogie climatique, sans pouvoir être validée : il n'y a pas de second
point. Avec quatre stations, et celles de la même campagne dans les pays
voisins, on peut modéliser la variation de l'erreur avec la latitude, les
aérosols ou l'altitude, et valider le transfert en retirant tour à tour
chaque station (validation croisée).

### 3.4 Confiance résultante

- A : la mesure de la station, sur sa période.
- B calé : le champ satellite corrigé sur la zone homogène, avec un résiduel
  documenté qui croît avec la distance climatique à la station.
- B : hors de cette zone.

Le schéma n'a pas de niveau « B calé » : un niveau de plus, un champ de
résiduel ou un override éditorial restent à arbitrer.

## 4. Ce que les stations débloquent

- Le rayonnement au sol départage les sources : le DNI de NASA POWER est
  trop faible (ADR-0014, ADR-0020), celui de CAMS le dépasse de 22 % en
  horaire (ADR-0023), et SARAH-3, ERA5 et CAMS s'écartent de NASA POWER dans
  la fiche d'incertitude (ADR-0016).
- La météo au sol départage NASA POWER et ERA5-Land, si les stations la
  mesurent : ERA5-Land sert un tiers de pluie de moins que NASA POWER, et un
  vent plus faible de 0,7 m/s (ADR-0024).
- Elles ne calent pas seules un modèle thermique de module (Faiman 2008),
  qui demande la température de module, ni la salissure, qui demande un
  équipement dédié. Les stations de la même campagne en Guinée portaient deux
  modules de référence et leurs températures ; l'équipement des stations
  burkinabè est à vérifier dans les en-têtes.

## 5. Évaluations publiées

Les comparaisons publiées entre produits satellitaires, réanalyses et
stations sol, en Afrique de l'Ouest surtout, donnent l'ordre de grandeur
des écarts que le calage aura à corriger :

- Sawadogo et al. (2023) évaluent le GHI horaire d'ERA5, de MERRA-2, de
  CAMS et de SARAH-2 sur 37 stations contrôlées du Burkina Faso et du
  Ghana. SARAH-2 a la plus faible erreur : RMSE de 15,2 % tous temps et de
  10,7 % par ciel clair. L'étude porte sur SARAH-2, le prédécesseur de
  SARAH-3.
- Kakou et al. (2025) valident le GHI de plusieurs produits satellitaires,
  dont CAMS et SARAH-3, sur 52 stations de la SODEXAM en Côte d'Ivoire.
  CAMS et SARAH-3 sont comparables par ciel clair ; par ciel nuageux, tous
  surestiment fortement, jusqu'à 39,7 % de biais relatif pour SARAH-3 et
  35,9 % pour CAMS.
- Quansah et al. (2022) valident NASA POWER sur 22 stations synoptiques
  du Ghana : l'erreur est plus forte en saison sèche qu'en saison humide.
- Ouhechou et al. (2023) relèvent en Afrique centrale un écart
  systématique entre CM SAF (SARAH-2 et SARAH-3), plus haut, et CERES, dont
  vient le rayonnement de NASA POWER.
- À l'échelle mondiale, Yang et Bright (2020) comparent huit produits
  satellitaires et de réanalyse à 57 stations BSRN sur 27 ans : au sens de
  l'erreur quadratique, le satellite y fait mieux que la réanalyse.

## 6. Ce que le moteur a déjà

- La table `referentiels_calage` (biais saisonnier satellite moins sol, par
  station et par grandeur), la table `calage_couverture` (localités où le
  transport d'un référentiel est défendable) et l'endpoint `/v1/calage`
  (ADR-0004). Les deux tables sont vides : `/v1/calage` répond une liste
  vide.
- La source `esmap_wapp` au référentiel des sources, sans série.
- La doctrine de contrôle qualité horaire v1
  ([doctrine-qc-horaire.md](doctrine-qc-horaire.md)), fondée sur les tests
  BSRN de Long et Dutton (l'algorithme de Long et Shi 2008 en est une piste
  d'enrichissement), qui s'applique aux mesures sol une fois agrégées à
  l'heure, et la convention de stockage de l'horaire (instant au début de
  l'heure moyennée, ADR-0014).

## 7. Hypothèses et risques

1. Stationnarité du biais : une correction tirée de deux ans de recouvrement
   ne vaut pour la série satellite longue que si le biais ne dérive pas dans
   le temps. À tester sur la fenêtre de recouvrement.
2. Deux ans de mesure suffisent à caler, pas à fonder seuls un P50/P90.
3. Au-delà de la zone homogène, le résiduel n'est plus borné.
4. Classe instrumentale : un DNI mesuré au pyrhéliomètre (thermopile) vaut
   mieux qu'un DNI dérivé d'un radiomètre à bande d'ombre.
5. Dori est au coin de quatre mailles CERES de NASA POWER (ADR-0014).

## 8. Références

- Faiman D. 2008. *Assessing the outdoor operating temperature of
  photovoltaic modules*. Progress in Photovoltaics 16(4), 307-315. DOI :
  10.1002/pip.813.
- Kakou P.-C.K., Laouali D., Aka B., Osei J.A., Ette N.F.K., Frey G.
  2025. *Multi-Timescale Validation of Satellite-Derived Global
  Horizontal Irradiance in Côte d'Ivoire*. Remote Sensing 17(6), 998. DOI :
  10.3390/rs17060998.
- Long C.N., Dutton E.G. *BSRN Global Network recommended QC tests, V2.0*.
- Long C.N., Shi Y. 2008. *An Automated Quality Assessment and Control
  Algorithm for Surface Radiation Measurements*. The Open Atmospheric
  Science Journal 2, 23-37.
- Ouhechou A., Philippon N., Morel B., Trentmann J., Graillet A.,
  Mariscal A., Nouvellon Y. 2023. *Inter-comparison and validation against
  in-situ measurements of satellite estimates of incoming solar radiation
  for Central Africa*. Atmospheric Research 287, 106711.
- Polo J. et al. 2016. *Preliminary survey on site-adaptation techniques
  for satellite-derived and reanalysis solar radiation datasets*. Solar
  Energy 132, 25-37. DOI : 10.1016/j.solener.2016.03.001.
- Quansah J.E. et al. 2022. *Assessment of solar radiation resource from
  the NASA-POWER reanalysis products for tropical climates in Ghana*.
  Scientific Reports 12, 10684. DOI : 10.1038/s41598-022-14126-9.
- Sawadogo W., Bliefernicht J., Fersch B., Salack S., Guug S., Diallo B.,
  Ogunjobi K.O., Nakoulma G., Tanu M., Meilinger S., Kunstmann H. 2023.
  *Hourly global horizontal irradiance over West Africa: A case study of
  one-year satellite- and reanalysis-derived estimates vs. in situ
  measurements*. Renewable Energy 216, 119066. DOI :
  10.1016/j.renene.2023.119066.
- Yang D., Bright J.M. 2020. *Worldwide validation of 8 satellite-derived
  and reanalysis solar radiation products*. Solar Energy 210, 3-19.
