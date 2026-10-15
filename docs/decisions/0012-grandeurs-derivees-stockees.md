# ADR-0012 : grandeurs dérivées stockées

Date : 2026-10-15. Statut : accepté.

## Contexte

Quatre sources mensuelles décrivent le rayonnement aux 398 localités
(ADR-0009, ADR-0011) et divergent nettement sur le DNI. Le jalon 3 rend ces
écarts lisibles comme des grandeurs à part entière, avec la fraction diffuse,
grandeur du référentiel (`fraction_diffuse`, id 3) restée jusqu'ici sans
valeur. Ces calculs sont déterministes et ne dépendent que des séries déjà
gravées.

## Décision

- Écarts relatifs inter-sources : `(x - nasa) / nasa × 100`, en %, par mois.
  NASA POWER est au dénominateur de tous les écarts, parce que c'est la seule
  source présente dans toutes les comparaisons et la plus longue (GHI depuis
  1991, DNI et DHI depuis 2001) ; c'est une convention de comparaison, pas un
  jugement de justesse. Sept grandeurs F1 stockées, ajoutées au référentiel
  sous les ids 35 à 41 : GHI SARAH-3, ERA5 et CAMS (35 à 37), DNI CAMS, SARAH-3
  et ERA5 (38 à 40), DHI CAMS (41). La grandeur héritée
  `ecart_relatif_dni_cams` (id 27) garde l'orientation inverse,
  `(nasa - cams) / cams`, et reste sans valeur. Fenêtre : les mois communs aux
  deux séries (2005-2023 pour SARAH-3 et ERA5, 2005-2025 pour CAMS), obtenus
  par jointure.
- Fraction diffuse NASA POWER : `DHI / GHI` par mois, et
  `Σ DHI_m·n_m / Σ GHI_m·n_m` par année complète (`n_m` jours du mois), sur
  2001-2025. La fiche de la grandeur
  (`docs/methodologie/grandeurs/fraction_diffuse.md`) la définit sur le
  journalier, `Σ DHI / Σ GHI` sur les jours de la période ; c'est le rapport
  des moyennes mensuelles, que sert NASA POWER. Contrôle aux 47 provinces
  contre le journalier (ADR-0010) : 14 100 mois, écart maximal 4,8·10⁻⁵. Les
  sommes annuelles sont faites en `numeric`, pour un résultat indépendant de
  l'ordre d'agrégation.
- Une série `kuma_calculs` par localité et par grandeur (`calcul_derive`,
  granularité nulle) : `ecart_<grandeur>_<source>_nasa_<localité>` et
  `fraction_diffuse_nasa_power_<localité>`. Confiance B : une dérivée ne
  dépasse pas ses entrées, et la règle R4 donne B pour `calcul_derive`.
- Calcul en SQL dans la migration 0009, depuis les mesures mensuelles
  gravées : ni seed ni réseau. Le trigger d'audit de `grandeurs_metier` est
  suspendu le temps du calcul, rejouable à l'identique
  (`docs/architecture/03-audit.md`, migrations de masse).
- Les mises en garde des séries brutes (mois SARAH-3 abaissés, niveau ERA5
  après 2020, imagerie Meteosat commune à CAMS et SARAH-3, maille de 1° de
  NASA POWER) sont reprises dans la note publique des séries dérivées.
- Lecture par l'API générique : `/v1/series?source=kuma_calculs` et
  `/v1/series/{code}`.

## Conséquences

- 3 184 séries ; 663 864 écarts mensuels, 119 400 fractions diffuses
  mensuelles et 9 950 annuelles. La migration 0009 dure 2 min environ ;
  `grandeurs_metier` occupe 480 Mo, l'essentiel dans ses index et sa
  contrainte d'exclusion.
- Écarts mensuels sur les communes, en % (moyenne des écarts mensuels, à ne pas
  confondre avec le rapport des moyennes de l'ADR-0011) :

  | Écart à NASA POWER | Moyenne | Médiane | Mois positifs | Déc.-fév. | Juin-août |
  |---|---|---|---|---|---|
  | GHI SARAH-3 | 7,3 | 6,8 | 96 % | 8,5 | 4,8 |
  | GHI ERA5 | 3,9 | 3,6 | 75 % | 3,7 | 1,8 |
  | GHI CAMS | 3,7 | 3,4 | 91 % | 4,5 | 3,6 |
  | DNI SARAH-3 | 52,6 | 46,3 | > 99,9 % | 53,2 | 47,2 |
  | DNI ERA5 | 70,5 | 64,4 | 100 % | 53,0 | 73,8 |
  | DNI CAMS | 29,2 | 26,7 | 99 % | 29,0 | 33,5 |
  | DHI CAMS | -3,0 | -2,2 | 38 % | -10,8 | 4,0 |

- Sur le DNI, les trois sources dépassent NASA POWER presque tous les mois
  (plus de 99 %). Les écarts extrêmes (jusqu'à +328 %) tombent sur des mois où
  le DNI NASA POWER est très faible, épisodes de poussière que CAMS voit aussi
  (son DNI y baisse de 10 à 33 %) et que SARAH-3 et ERA5, aux aérosols
  climatologiques, manquent : un écart relatif se lit avec la valeur de
  référence.
- Fraction diffuse : 0,44 en moyenne sur les communes, de 0,36 en décembre à
  0,49 en juin ; entre 0,40 et 0,52 selon l'année et la commune. Elle baisse
  vers le nord : la corrélation entre latitude et moyenne de chaque commune
  vaut -0,62.
- Un écart ne dit pas quelle source a raison ; seule une ancre sol (jalon 4)
  le peut.
- L'endpoint `/v1/grandeurs/incertitude_inter_source` lit encore les grandeurs
  héritées (`ecart_relatif_referentiel`, `ecart_relatif_dni_cams`) et ignore
  ces écarts : il reste à adapter.
