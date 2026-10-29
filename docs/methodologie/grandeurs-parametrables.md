# Grandeurs paramétrables

Méthodes des grandeurs que l'API calcule à la volée à partir des séries
stockées et de paramètres techniques fournis par l'appelant : POA
mono-plan et bifacial, productible avec correction thermique, productible
à PR fourni, énergie utile ECS et degrés-jours de climatisation
(`/v1/grandeurs/*`). Les décisions qui les rendent calculables au Burkina
Faso sont l'ADR-0013 (météo journalière, séries compagnes, repli du POA),
l'ADR-0014 (intégration horaire) et l'ADR-0020 (biais du POA journalier).

Les chiffres d'exemple viennent de la commune de Ouagadougou en 2024,
calculés par l'API sur les séries du dépôt, plan à 15° plein sud et
albédo de 0,2 sauf mention contraire.

## 1. Principes communs

- Famille F2 du référentiel, stratégie `calculee_volee` : rien n'est
  stocké. Chaque appel recalcule à partir des séries courantes ; deux
  appels identiques peuvent différer si une série source a été réingérée
  ou requalifiée entre-temps.
- Un module par grandeur dans `services/grandeurs/`, en fonctions pures
  sans SQL ; la route lit les séries et assemble la réponse.
- Paramètres communs : `code_serie_source`, `periode_debut` et
  `periode_fin` (bornes incluses), `format` (`json` par défaut, ou `csv`)
  et `methode` (`moyenne_journaliere` par défaut, ou
  `integration_horaire`).
- La série source porte le GHI, sauf pour les degrés-jours, qui partent
  du T2M. Les séries compagnes (DNI, DHI, T2M) sont cherchées à la même
  localité, dans la même source et à la même granularité, sur une
  période qui recouvre celle de la source (ADR-0013). Sans la compagne
  requise, la route répond 400 `INCOMPATIBILITE_SOURCE_GRANDEUR`, sauf le
  POA mono-plan horaire, qui répond 400 `VALIDATION_VALEUR_INVALIDE` sans
  DHI horaire.
- Les productibles et l'énergie ECS appliquent leur modèle au GHI de la
  série source, sur le plan horizontal : ils ne passent pas par le POA.
- Les résultats sont en confiance B au Burkina Faso : leurs entrées sont des
  séries satellite ou de réanalyse de confiance B, et la justesse des
  paramètres techniques relève de l'appelant. Ce B est un plafond (règle de
  propagation P, ADR-0025) : une entrée qu'un override a descendue en C met
  en C les seuls résultats de sa période, et des mesures au sol A laisseraient
  ces grandeurs en B.

## 2. Séries utilisables

| Pas | Source | Grandeurs | Localités | Période |
|---|---|---|---|---|
| journalier | NASA POWER | GHI, T2M | 47 provinces | 1991-2025 |
| journalier | NASA POWER | DNI, DHI | 47 provinces | 2001-2025 |
| journalier | NASA POWER | GHI, DNI, DHI, T2M | 351 communes | 2005-2025 |
| journalier | CAMS Radiation | GHI, DNI, DHI | 398 | 2005-2025 |
| journalier | SARAH-3 (PVGIS) | GHI, DNI, DHI | 398 | 2005-2023 |
| journalier | ERA5-Land | GHI, T2M | 398 | 2005-2025 |
| horaire | NASA POWER | GHI, DNI, DHI, T2M | 398 | 2021-2025 |
| horaire | CAMS Radiation | GHI, DNI, DHI | 5 points pilotes | 2021-2025 |

Les cinq points pilotes sont la commune de Ouagadougou et les
départements de Dédougou, Dori, Kaya et Koupéla (ADR-0014). L'horaire
NASA POWER des 398 localités a une série par maille de la source, que
lisent les autres localités de la maille (ADR-0026). Il en découle :

- CAMS Radiation et SARAH-3 ne servent pas de température : le
  productible avec correction thermique, le PR corrigé de la température
  et l'énergie ECS répondent 400 avec leurs séries, et les degrés-jours
  demandent un T2M de NASA POWER ou d'ERA5-Land.
- ERA5-Land ne sert ni DNI ni DHI : le POA mono-plan passe par le repli
  (section 3), le bifacial répond 400.
- L'intégration horaire existe en 2021-2025 aux 398 localités avec
  NASA POWER, aux cinq points pilotes avec CAMS Radiation, et seulement
  avec NASA POWER pour les grandeurs qui demandent la température
  (ADR-0023, ADR-0026). Une commune prend sa propre géométrie solaire et
  le rayonnement de sa maille. Seuls les jours UTC dont les
  24 heures sont présentes et validées entrent dans le calcul
  (ADR-0014).
- Une série horaire passée sans `methode=integration_horaire` donne une
  réponse vide, sauf une série CAMS sur les routes qui demandent la
  température : faute de T2M chez CAMS, elles répondent 400
  `INCOMPATIBILITE_SOURCE_GRANDEUR`. `integration_horaire` sur une série
  qui n'est pas horaire répond 400 `VALIDATION_VALEUR_INVALIDE`.

## 3. POA mono-plan (`poa_parametrable`)

Éclairement dans le plan du panneau, transposé depuis le plan horizontal
selon l'inclinaison et l'orientation du plan. Position solaire et
transposition par `pvlib`.

| Paramètre | Unité | Plage | Défaut |
|---|---|---|---|
| `inclinaison_deg` | degrés | 0 à 90 | obligatoire |
| `orientation_deg` | degrés, azimut (0 nord, 180 sud) | 0 à 360 exclu | obligatoire |
| `albedo_sol` | sans dimension | 0 à 1 | 0,2 |

En moyenne journalière, chaque jour est traité au midi solaire,
approché par 12 h UTC moins la longitude divisée par 15 :

- si la source sert le DNI et le DHI du jour, modèle de Perez et al.
  (1990) appliqué aux totaux du jour ;
- sinon, repli : le total du jour est décomposé par la corrélation
  journalière d'Erbs et al. (1982), indice de clarté `KT = H / H0`
  (`H0` irradiation extraterrestre du jour sur le plan horizontal), puis
  fraction diffuse `Hd / H` ; le direct horizontal `H - Hd` est ramené au
  midi solaire par `cos z`, et la transposition est isotrope (Liu et
  Jordan 1963). Le repli joue pour ERA5-Land et pour les provinces avant
  2001.

Projeter le direct du jour avec la géométrie du midi, où le soleil est le
plus haut, surestime le POA (ADR-0013, ADR-0020). La réponse en porte
l'avertissement chiffré, champ `limite`, qui donne l'écart au GHI des
jours demandés sur un plan horizontal. À Ouagadougou en 2024, en
kWh/m²/jour :

| Série | GHI | POA horizontal, journalier | POA 15° sud, journalier | POA 15° sud, horaire |
|---|---|---|---|---|
| NASA POWER | 5,78 | 6,13 | 6,46 | 5,98 |
| CAMS Radiation | 6,04 | 7,18 | 7,54 | 6,25 |
| ERA5-Land (repli) | 5,99 | 5,99 | 6,12 | |

Le repli redonne le GHI sur un plan horizontal ; la méthode de Perez au
midi le dépasse de 6 % avec NASA POWER et de 19 % avec CAMS, dont les
composantes se referment exactement : l'écart vient de la méthode, non de
la donnée (ADR-0020). Sur le plan à 15° sud, la méthode journalière
dépasse l'intégration horaire de 8 % avec NASA POWER et de 21 % avec
CAMS. Une série de province 1991-2025 change de méthode le 1er janvier
2001 : ne pas moyenner un POA à cheval sur cette date (ADR-0013). La
correction de la méthode journalière est inscrite à la feuille de route.

En intégration horaire, Perez est appliqué heure par heure, avec la
géométrie au milieu de l'heure (les instants désignent le début de
l'heure, ADR-0014), puis sommé par jour UTC. Le direct est reconstruit
sur le GHI et le DHI, `(GHI - DHI) / cos z` (`pvlib.irradiance.dni`), nul
au-delà de 88° de zénith et borné à l'éclairement extraterrestre ; seule
la compagne DHI est requise. Un plan horizontal retrouve le GHI : 5,78
kWh/m²/jour avec NASA POWER. Le plan à 15° sud gagne 3,5 % sur le GHI,
avec NASA POWER comme avec CAMS.

Limites :

- les coefficients de Perez ont été établis sur des sites d'Amérique du
  Nord et d'Europe, et ne sont pas recalés pour le Sahel et ses épisodes
  de poussière ;
- plan fixe et dégagé : ni ombrage, ni relief proche, ni suiveur ;
- les modèles intermédiaires de Hay et Davies et de Reindl (HDKR) ne
  sont pas proposés.

## 4. POA bifacial (`poa_bifacial`)

POA global d'un champ de rangées, face avant et gain de la face arrière,
par le modèle `infinite_sheds` de `pvlib` (Mikofski et al. 2019 ; Marion
et al. 2017 pour l'éclairement de la face arrière), diffus du ciel
isotrope. La bifacialité est appliquée par le modèle.

| Paramètre | Unité | Plage | Défaut |
|---|---|---|---|
| `inclinaison_deg`, `orientation_deg` | degrés | comme le POA mono-plan | obligatoires |
| `gcr` | largeur du module / pas | ]0, 1] | obligatoire |
| `hauteur_m` | m, centre de rangée | > 0 | obligatoire |
| `pitch_m` | m, pas entre rangées | > 0 | obligatoire |
| `bifacialite` | face arrière / face avant | 0 à 1 | 0,8 |
| `albedo_sol` | sans dimension | 0 à 1 | 0,2 |

L'albédo est lu dans une série `albedo_surface` journalière de la même
source quand elle existe. Aucune n'est gravée au Burkina Faso : l'albédo
est celui du paramètre.

En moyenne journalière, le modèle est appliqué au midi solaire et
demande les compagnes DNI et DHI, sans repli ; il porte le même biais
que le POA mono-plan et le même champ `limite`. En intégration horaire,
seule la compagne DHI est requise, le direct étant reconstruit comme
pour le mono-plan. À Ouagadougou en 2024, en intégration horaire avec
NASA POWER, `gcr` de 0,4, bifacialité de 0,7 et albédo de 0,25, le
bifacial dépasse le monofacial de 7,7 % (ADR-0014).

Limites : rangées infinies et uniformes (effets de bord ignorés) ;
albédo d'un jour appliqué à toutes ses heures ; géométrie et bifacialité
non calées sur site.

## 5. Productible avec correction thermique (`productible_correction_thermique`)

Modèle NOCT de Ross (1980) :

```
T_cell = T_amb + (NOCT - 20) · G / 800
E      = P_STC · H / G_STC · [1 + γ / 100 · (T_cell - 25)]
```

`G` est l'éclairement en W/m², `H` l'irradiation correspondante en
kWh/m², `G_STC` l'éclairement de référence de 1 kW/m², `P_STC` la
puissance crête en kWc, `T_amb` le T2M compagne et `γ` le coefficient de
température de la puissance en %/°C. En moyenne journalière, `G` est la
moyenne des 24 heures, `H_jour × 1000 / 24`, et `E` le productible du
jour en kWh ; en intégration horaire, le calcul est fait pour chaque
heure, puis sommé par jour.

| Paramètre | Unité | Plage |
|---|---|---|
| `noct_degc` | °C | 40 à 50 |
| `coeff_temp_pourcent_par_degc` | %/°C | -0,6 à -0,1 |
| `puissance_stc_wc` | Wc | > 0 |

La moyenne des 24 heures écrase le pic de midi, donc la température de
cellule. À Ouagadougou en 2024 (NASA POWER, NOCT de 45 °C, -0,35 %/°C,
1 kWc), la température retire 3,6 % du productible en moyenne
journalière et 10,0 % en intégration horaire : 2 038 kWh contre 1 903,
soit 7 % de trop pour la méthode journalière.

Limites :

- le vent n'intervient pas. Le modèle de Faiman (2008), qui en tient
  compte, n'est pas exposé : ses coefficients demandent un calage local ;
  les modèles de Sandia (King et al. 2004) et de PVsyst demandent plus
  de paramètres ;
- la température dépend de la source. NASA POWER sert celle de MERRA-2,
  sur une maille de 0,5° × 0,625° ; ERA5-Land la ramène à l'altitude de
  sa maille de 0,1°, et la donne plus chaude de 0,8 °C en moyenne aux
  communes (ADR-0024).

## 6. Productible à PR fourni (`productible_pr_fourni`)

Le Performance Ratio fourni par l'appelant résume les pertes du système
par rapport à la production plaque (Marion et al. 2005) :

```
correction = aucune      : E = P_STC · H / G_STC · PR
correction = temperature : E = P_STC · H / G_STC · PR · [1 + γ / 100 · (T_cell - 25)]
```

La correction de température reprend le modèle NOCT de la section 5
(PR corrigé de la température, Dierauf et al. 2013) ; `noct_degc` et
`coeff_temp_pourcent_par_degc` sont alors obligatoires.

| Paramètre | Unité | Plage | Défaut |
|---|---|---|---|
| `pr_fourni` | sans dimension | 0 à 1 | obligatoire |
| `correction` | `aucune` ou `temperature` | | `aucune` |
| `puissance_stc_wc` | Wc | > 0 | obligatoire |

Sans correction, une série GHI mensuelle est aussi acceptée : la réponse
donne alors, par mois (`AAAA-MM`), le productible quotidien moyen. Une
série calculée (`kuma_calculs`) est refusée. Sans correction,
l'intégration horaire redonne le journalier, le calcul étant linéaire ;
avec correction, elle lève le même biais qu'en section 5 : à Ouagadougou
en 2024, avec un PR de 0,8, 1 630 kWh en moyenne journalière contre
1 522 en intégration horaire.

Limites : les PR corrigés de la météo ou du climat (PR_W, PR_C) de
Dierauf et al. (2013) ne sont pas exposés, faute d'année météorologique
type ; la plage de 0 à 1 ne signale pas un PR irréaliste, et le choix
reste à l'appelant (Reich et al. 2012 pour les PR supérieurs à 90 %).
Le PR réaliste corrigé de la température ou de la salissure est une
autre grandeur (section 9).

## 7. Énergie utile ECS (`energie_utile_ecs`)

Rendement instantané d'un capteur solaire thermique, équation de
Hottel-Whillier-Bliss (Hottel et Whillier 1958 ; Duffie et al. 2020) :

```
η = η0 - a1 · ΔT / G - a2 · ΔT² / G,  η ≥ 0
Q = η · H
```

`ΔT` est l'écart entre la température d'entrée du fluide et le T2M
compagne ; la température moyenne du fluide est prise égale à celle
d'entrée, le débit n'étant pas modélisé. En moyenne journalière, `G` est
la moyenne des 24 heures et `Q` l'énergie du jour en kWh/m² de capteur ;
en intégration horaire, le rendement est calculé pour chaque heure.

| Paramètre | Unité | Plage |
|---|---|---|
| `rendement_optique_eta0` | sans dimension | 0,5 à 0,9 |
| `pertes_lineaires_a1` | W/(m²·K) | 1 à 8 |
| `pertes_quadratiques_a2` | W/(m²·K²) | 0 à 0,05 |
| `temperature_fluide_entree_degc` | °C | 10 à 90 |

Le rendement n'est pas linéaire en `G`, et la moyenne des 24 heures, de
l'ordre de 240 W/m² à Ouagadougou, place le capteur loin de ses heures
utiles. En 2024 (NASA POWER, `η0` de 0,8, `a1` de 3,5, `a2` de 0,01,
entrée à 50 °C), la méthode journalière donne 956 kWh/m² sur l'année et
l'intégration horaire 1 418 : un tiers de moins. Pour l'ECS, préférer
l'intégration horaire là où elle existe.

Limites : pas de modificateur d'angle d'incidence ; pas de calcul du
système (stockage, puisage, fraction solaire, méthode f-chart de Klein et
al. 1976) ; coefficients du capteur sous la responsabilité de l'appelant
(fiche Solar Keymark ou équivalent) ; température ambiante selon la
source, comme en section 5.

## 8. Degrés-jours de climatisation (`degre_jour_climatisation`)

Somme mensuelle des écarts positifs à une base `T_b` fournie par
l'appelant (Erbs et al. 1983 ; Schoenau et Kehrig 1990), en °C·j :

```
moyenne journalière : DJC_mois = Σ_jours  max(0, T_moy_jour - T_b)
intégration horaire : DJC_mois = Σ_heures max(0, T_h - T_b) / 24
```

La série source est un T2M ; `base_temperature_degc` va de 10 à 35 °C.
Bases d'usage, à titre indicatif : 18,3 °C (ASHRAE, Amérique du Nord),
24 °C (RTAA DOM, outre-mer français tropical), 24 à 26 °C (directive de
la CEDEAO sur l'efficacité énergétique des bâtiments), 26 °C (climat
tropical, Butera et al. 2014). Aucune base n'est fixée pour le Burkina
Faso ; le choix revient à l'appelant.

La moyenne du jour efface les heures chaudes au-dessus de la base quand
la moyenne reste dessous. À Ouagadougou en 2024, en base 26 °C :
965 °C·j en moyenne journalière avec NASA POWER, 1 282 en intégration
horaire, soit 25 % de moins (Krese et al. 2012 pour cette limite) ;
1 094 en moyenne journalière avec ERA5-Land, plus chaud.

La méthode du point d'équilibre, qui ajuste la base à chaque bâtiment
(manuel ASHRAE), n'est pas proposée.

## 9. Autres grandeurs calculées à la volée

- `ghi_exceedance/{code_localite}` : P50 et P90 inter-annuels de
  l'irradiation annuelle, sur la série GHI mensuelle NASA POWER
  1991-2020 (ADR-0013). Ce n'est pas un P90 bancable : l'erreur du modèle
  satellite n'y est pas propagée.
- `taux_salissure_proxy/{code_serie_source}` et
  `pr_realiste/{code_serie_source}` : salissure par le modèle HSU de
  `pvlib`, à partir des PM2.5 et PM10 de CAMS EAC4 et de la pluie NASA
  POWER, et PR réaliste corrigé de la température, de la salissure ou
  des deux (ADR-0013, ADR-0015, ADR-0018).
- `incertitude_inter_source` : écarts entre sources et dégénérescence de
  pixel (ADR-0016).

## 10. Limites communes

- Aucune de ces grandeurs n'est calée sur une mesure au sol : les
  stations ESMAP/WAPP du Burkina Faso ne sont pas intégrées (feuille de
  route).
- L'incertitude des paramètres de l'appelant n'est pas propagée ; le
  plafond B de la confiance est qualitatif.
- Les grandeurs solaires ne tiennent compte ni de l'ombrage, ni du relief
  proche, ni de la salissure, traitée à part (section 9).

## 11. Références

- Butera F.M., Adhikari R., Aste N. 2014. *Sustainable Building Design for
  Tropical Climates: Principles and Applications for Eastern Africa*.
  UN-Habitat. ISBN 978-92-1-132599-7.
- Dierauf T., Growitz A., Kurtz S., Cruz J.L.B., Riley E., Hansen C. 2013.
  *Weather-Corrected Performance Ratio*. NREL/TP-5200-57991. DOI :
  10.2172/1078057.
- Duffie J.A., Beckman W.A., Blair N. 2020. *Solar Engineering of Thermal
  Processes, Photovoltaics and Wind*, 5e édition. Wiley. ISBN
  978-1-119-54028-1.
- ECREEE. *Directive régionale CEDEAO sur l'efficacité énergétique des
  bâtiments*.
- Erbs D.G., Klein S.A., Beckman W.A. 1983. *Estimation of degree-days and
  ambient temperature bin data from monthly-average temperatures*. ASHRAE
  Journal 25(6), 60-65.
- Erbs D.G., Klein S.A., Duffie J.A. 1982. *Estimation of the diffuse
  radiation fraction for hourly, daily and monthly-average global
  radiation*. Solar Energy 28(4), 293-302. DOI :
  10.1016/0038-092X(82)90302-4.
- Faiman D. 2008. *Assessing the outdoor operating temperature of
  photovoltaic modules*. Progress in Photovoltaics 16(4), 307-315. DOI :
  10.1002/pip.813.
- France. *Réglementation thermique, acoustique et aération des
  départements d'outre-mer (RTAA DOM)*. Décret n° 2009-424 du 17 avril
  2009 et arrêté du même jour modifié ; décret n° 2016-13 du 11 janvier
  2016.
- Hottel H.C., Whillier A. 1958. *Evaluation of flat-plate solar collector
  performance*. Transactions of the Conference on the Use of Solar Energy,
  vol. 2, part 1, p. 74. University of Arizona Press.
- King D.L., Boyson W.E., Kratochvil J.A. 2004. *Photovoltaic Array
  Performance Model*. Sandia, SAND2004-3535.
- Klein S.A., Beckman W.A., Duffie J.A. 1976. *A design procedure for
  solar heating systems*. Solar Energy 18(2), 113-127. DOI :
  10.1016/0038-092X(76)90044-X.
- Krese G., Prek M., Butala V. 2012. *Analysis of building electric
  energy consumption data using an improved cooling degree day method*.
  Strojniški vestnik 58(2), 107-114. DOI : 10.5545/sv-jme.2011.160.
- Liu B.Y.H., Jordan R.C. 1963. *The long-term average performance of
  flat-plate solar-energy collectors*. Solar Energy 7, 53-74. DOI :
  10.1016/0038-092X(63)90006-9.
- Marion B. et al. 2005. *Performance parameters for grid-connected PV
  systems*. NREL/CP-520-37358, 31st IEEE PVSC.
- Marion B. et al. 2017. *A Practical Irradiance Model for Bifacial PV
  Modules*. 44th IEEE PVSC. DOI : 10.1109/PVSC.2017.8366263.
- Mikofski M., Darawali R., Hamer M., Neubert A., Newmiller J. 2019.
  *Bifacial Performance Modeling in Large Arrays*. 46th IEEE PVSC.
- Perez R., Ineichen P., Seals R., Michalsky J., Stewart R. 1990.
  *Modeling daylight availability and irradiance components from direct
  and global irradiance*. Solar Energy 44(5), 271-289. DOI :
  10.1016/0038-092X(90)90055-H.
- Reich N.H., Müller B., Armbruster A., van Sark W.G.J.H.M., Kiefer K.,
  Reise C. 2012. *Performance ratio revisited: is PR > 90% realistic?*.
  Progress in Photovoltaics 20(6), 717-726. DOI : 10.1002/pip.1219.
- Ross R.G. Jr. 1980. *Flat-plate photovoltaic array design
  optimization*. 14th IEEE Photovoltaic Specialists Conference,
  p. 1126-1132.
- Schoenau G.J., Kehrig R.A. 1990. *Method for calculating degree-days to
  any base temperature*. Energy and Buildings 14(4), 299-302. DOI :
  10.1016/0378-7788(90)90092-W.
