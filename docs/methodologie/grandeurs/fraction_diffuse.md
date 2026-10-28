# Fiche de la grandeur `fraction_diffuse`

Fraction diffuse de l'irradiation, calculée par la migration 0009 aux
398 localités. La décision et ses contrôles sont dans l'ADR-0012.

## 1. Identification

| Champ | Valeur |
|---|---|
| Code | `fraction_diffuse` |
| Unité | sans dimension |
| Famille | F1, stockée dans `grandeurs_metier` |
| Version de formule | 1 |
| Pas | mensuel et annuel |
| Période | 2001-2025 |
| Localités | 47 provinces et 351 communes |
| Confiance | B |

## 2. Définition

La fraction diffuse d'une période est le rapport de l'irradiation diffuse
horizontale (DHI) à l'irradiation globale horizontale (GHI), cumulées sur
les jours de la période :

```
fraction_diffuse = Σ DHI / Σ GHI
```

NASA POWER sert pour chaque mois la moyenne journalière du mois, en
kWh/m²/jour. Le rapport des moyennes d'un mois est donc celui de ses
cumuls, et l'année pondère chaque mois par son nombre de jours `n_m` :

```
fraction_diffuse(année, mois) = DHI_m / GHI_m
fraction_diffuse(année)       = Σ DHI_m·n_m / Σ GHI_m·n_m
```

La valeur annuelle n'est calculée que pour une année complète. Les sommes
sont faites en `numeric`, pour un résultat indépendant de l'ordre
d'agrégation.

## 3. Source et calcul

- Entrées : DHI et GHI mensuels NASA POWER (`ALLSKY_SFC_SW_DIFF` et
  `ALLSKY_SFC_SW_DWN`, ADR-0009), produit CERES SYN1deg. Le DHI n'est
  ingéré que depuis 2001, la série de NASA POWER étant en rupture avant.
- Calcul en SQL dans la migration 0009, depuis les séries mensuelles
  gravées, sans seed ni réseau. Une série par localité,
  `fraction_diffuse_nasa_power_<localité>` (source `kuma_calculs`, méthode
  `calcul_derive`, granularité nulle).
- Contrôles : chaque valeur reste dans [0, 1] ; aux 47 provinces, le
  rapport des moyennes mensuelles redonne celui des cumuls journaliers
  NASA POWER (ADR-0010) à 4,8·10⁻⁵ près sur 14 100 mois.
- Aucun mois ne manque sur 2001-2025 : 300 valeurs mensuelles et 25
  valeurs annuelles par localité, soit 119 400 et 9 950 lignes.
- Lecture : `/v1/series?source=kuma_calculs` et `/v1/series/{code}`.

## 4. Limites

- NASA POWER sert le rayonnement sur une maille de 1° : les 351 communes
  tiennent dans 33 mailles, les 47 provinces dans 24. Les localités d'une
  même maille ont la même fraction diffuse ; la note publique de la série
  le dit, et la fiche d'incertitude donne le nombre de ces jumeaux
  (ADR-0016).
- La fraction diffuse dépend directement du DHI de NASA POWER. Ses
  composantes ne se referment pas toujours : en horaire, aux cinq points
  pilotes, `DHI + DNI·cos z` reste de 5,9 à 6,9 % sous le GHI (ADR-0014).
  L'écart mensuel du DHI de CAMS à celui de NASA POWER vaut en moyenne
  -3,0 % aux communes, de -10,8 % en décembre-février à +4,0 % en
  juin-août (ADR-0012).
- Aucune mesure au sol ne la vérifie : la confiance reste B.

## 5. Valeurs observées, 2001-2025

- Moyenne de 0,44 sur les 398 localités ; de 0,25 à 0,64 au pas mensuel,
  de 0,40 à 0,52 au pas annuel.
- Aux communes, la moyenne mensuelle tombe à 0,37 en novembre et 0,36 en
  décembre, et reste au-dessus de 0,47 de mars à août (0,49 en juin).
- Moyenne par commune : de 0,428 pour 15 communes de la même maille,
  dont Dédougou et Nouna (provinces du Mouhoun, du Koosin, du Nayala, du
  Sourou et du Banwa, de 12,07 à 12,98 °N), à 0,492 à Batié et Kpuéré
  (province du Noumbiel, sous 10 °N). Elle vaut 0,462 au sud de 10,5 °N
  et 0,435 au nord de 13,5 °N ; la corrélation entre latitude et moyenne
  de chaque commune vaut -0,62.
- Moyenne annuelle des communes : de 0,408 en 2003 à 0,473 en 2016.
- À Ouagadougou : 0,440 en moyenne, de 0,396 (2003) à 0,476 (2007).

## 6. Références

- NASA POWER, documentation des méthodes :
  `https://power.larc.nasa.gov/docs/methodology/`
- CERES SYN1deg : `https://ceres.larc.nasa.gov/data/`
