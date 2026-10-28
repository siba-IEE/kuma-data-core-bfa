# ADR-0022 : rayonnement journalier SARAH-3

Date : 2026-10-28. Statut : accepté.

## Contexte

SARAH-3, la base de rayonnement satellite du CM SAF (EUMETSAT), sert déjà le
GHI et le DNI mensuels aux 398 localités, par l'API `MRcalc` de PVGIS
(ADR-0009). Au pas journalier, elle devient une troisième source de
rayonnement, à côté de CAMS (ADR-0020) et de NASA POWER, avec un pixel de
0,05°, contre une maille de 1° pour NASA POWER.

Le CM SAF diffuse ses propres moyennes journalières SARAH-3, en fichiers
NetCDF sur tout le disque Meteosat, sur commande après inscription. PVGIS ne
sert pas de série journalière, mais sert sans clé, par `seriescalc`, les
valeurs horaires du direct et du diffus en un point, avec la hauteur du
soleil, sur 2005-2023. C'est la voie retenue : une requête par localité,
reproductible par l'ingesteur. Les fichiers du CM SAF pourront servir à
recouper ces séries.

PVGIS sert, pour chaque heure UTC, la valeur instantanée de SARAH-3 datée
de hh:07 (minute identique aux 398 localités), qu'il tient pour la moyenne de
l'heure. Une heure que SARAH-3 ne sert pas, PVGIS la rend nulle, hauteur du
soleil comprise, sans la signaler : aucune valeur n'est marquée comme
reconstruite (`Int` nul). `MRcalc` compte ces heures comme nulles dans ses
moyennes mensuelles.

## Décision

- **Grandeurs :** GHI, DNI et DHI journaliers, total du jour UTC en
  kWh/m²/jour, 2005-2023, aux 398 localités (lot `localites`), en stockage
  dense (ADR-0017), méthode `modele_satellitaire`, confiance B. Les séries
  sont rattachées à la source `sarah3_monthly`, qui décrit le jeu SARAH-3
  servi par PVGIS, quel que soit le pas.
- **Calcul du jour :** une requête `seriescalc` par localité (plan
  horizontal, composantes séparées) ;
  - le GHI est la somme du direct et du diffus horizontaux, le DHI celle du
    diffus ;
  - le DNI est la somme du direct horizontal divisé par le sinus de la
    hauteur du soleil, heure par heure.
- **Heures manquantes :** est manquante toute heure où PVGIS sert une
  hauteur du soleil nulle alors que le soleil, calculé par pvlib à hh:07, est
  à plus de 3°. Au-dessus de 3°, PVGIS et pvlib s'accordent sur la hauteur
  du soleil à 0,5° près ; les heures nulles où le soleil est entre 0 et 3° ne
  pèsent que 0,02 % du ciel clair. Le total du jour est complété au prorata
  du ciel clair (GHI du modèle Solis simplifié de pvlib) : total servi × ciel
  clair du jour / ciel clair des heures servies. C'est la formule de Diekmann
  et al. (1988) qu'applique le CM SAF à ses propres moyennes journalières, de
  la même façon pour toutes les grandeurs (Pfeifroth et al. 2024, ESSD 16:5243,
  § 2.6). Le lot applique aux trois grandeurs le facteur du GHI, ce qui garde
  le direct horizontal sous le DNI.
- **Jours sans valeur :** la complétion suppose que les heures servies
  encadrent les heures manquantes. Un jour reste donc sans valeur quand des
  heures manquantes d'affilée couvrent plus de la moitié de son ciel clair.
  Le seuil tombe dans un creux des données : sur 2005-2023, ces suites
  couvrent au plus 46 % du ciel clair d'un jour complété, et au moins 54 %
  d'un jour laissé sans valeur. Un jour reste aussi sans valeur quand moins
  du quart de son ciel clair est servi. Ce seuil s'inspire de celui du
  CM SAF, qui compte des créneaux ; il ne joue sur aucun jour de la période.
- **Bornes :** les bornes journalières communes (GHI 9, DNI 11,
  DHI 6,5 kWh/m²/jour), au-dessus des maxima servis (8,31, 9,06 et 3,95). Le
  DNI peut être nul un jour couvert (195 jours-localités) ; le GHI et le DHI
  restent strictement positifs (minima 0,73). Aucun écart admis.
- **Ingesteur :** `scripts/ingest_pvgis_sarah3_journalier.py`, réponses
  brutes en cache compressé. Migration 0021, qui met aussi à jour :
  - la fiche de `sarah3_monthly`, restée celle du dépôt d'origine (titre,
    organisation, adresse, notes) ;
  - la note des 796 séries mensuelles SARAH-3 (ADR-0009) et celle des 796
    écarts mensuels SARAH-3 à NASA POWER qui en dérivent (ADR-0012), avec la
    liste mesurée des mois sous-estimés (voir plus bas).

## Conséquences

- **Volume :** 1 194 séries, dont 1 181 porteuses (393 pour le GHI et le DHI,
  395 pour le DNI). Cinq provinces partagent le pixel de leur commune
  chef-lieu ; leur DNI diffère parfois, la hauteur du soleil étant calculée
  au point exact. 22 439 lignes annuelles et 8 178 425 valeurs ; 17 Mo de
  fichiers ; la migration dure une douzaine de secondes.
- **Heures complétées :** 125 385 jours-localités, dont 44 443 de plus de
  10 %.
  - Du 2 au 11 janvier 2009, SARAH-3 ne sert qu'une heure sur deux, partout.
    Ces jours perdent la moitié de leur ciel clair (55 % le 2 janvier), mais
    jamais plus de 19 % d'affilée : ils sont complétés. Leur moyenne
    nationale vaut 1,056 fois celle de CAMS, contre 1,043 sur les 22 jours
    voisins (du 20 décembre 2008 au 20 janvier 2009).
  - En 2005, SARAH-3 ne sert presque jamais l'heure de 6 h UTC. Le soleil y
    est bas : ces heures manquantes pèsent 0,14 % du ciel clair de l'année
    en moyenne aux 398 localités, 0,31 % au plus.
- **Jours sans valeur :** 5 572 jours-localités par grandeur, à 14 dates,
  les mêmes partout : 18 avril 2005 ; 22 et 23 janvier, 1er et 6 mars, 17 et
  18 mai 2008 ; 18 et 19 avril, 15 et 16 août 2009 ; 2 décembre 2014 ; 16 et
  17 octobre 2016. La note de chaque série les nomme.

  Le 18 avril 2005, CAMS tombe lui aussi sous 1 kWh/m²/jour à 20 localités
  (ADR-0020) : les deux produits partent des images Meteosat, ce qui appuie
  l'hypothèse d'un défaut d'imagerie ce jour-là.
- **Contrôle :** après complétion, aucun jour ne reste sous 0,8 fois les
  moyennes nationales de CAMS et de NASA POWER à la fois. Le 23 septembre
  2006, seul CAMS paraît haut : il ne sert ce jour-là que 12 localités, à son
  ciel clair (7,16 kWh/m²/jour, contre 3,58 pour SARAH-3 et 4,29 pour
  NASA POWER aux mêmes localités).
- **Accord avec le mensuel :** sur les 42 075 mois-localités sans aucune
  heure manquante, la moyenne des jours redonne le GHI et le DNI mensuels de
  `MRcalc` (ADR-0009) à 1e-4 près : le DNI journalier se calcule comme celui
  de PVGIS. Sur les autres mois, `MRcalc` compte nulles les heures non
  servies : hors des mois sous-estimés, la moyenne des jours le dépasse de
  0,6 % en moyenne.
- **Mensuel SARAH-3 :** rapporté au ciel clair des heures manquantes, le
  mois perd en moyenne :
  - 16 % en janvier 2009 ;
  - 9 % en mai 2008 ;
  - 7 % en mars 2008, en avril 2009 et en octobre 2016 ;
  - 6 % en août 2009 et en janvier 2008 ;
  - 4 % en décembre 2014 ;
  - moins de 3 % les autres mois (2,2 % au plus en moyenne, en septembre
    2011).

  L'ADR-0009 avait relevé six de ces mois sur la seule série horaire de
  Ouagadougou ; août 2009 et décembre 2014 lui avaient échappé. Les notes
  des séries mensuelles et des écarts mensuels donnent désormais la liste
  mesurée ; les valeurs mensuelles restent non corrigées.
- **Moyennes sur 2005-2023 :**
  - GHI de 6,25 kWh/m²/jour (6,46 au nord de 13,5 °N, 5,95 au sud de
    10,5 °N ; 6,91 en mars, 5,44 en août) ;
  - DNI de 5,79 (6,18 au nord, 5,23 au sud ; 3,82 en août) ;
  - DHI de 2,19.

  Le direct horizontal (GHI moins DHI) reste chaque jour sous le DNI. Leur
  rapport des sommes, sur les jours servis par les deux sources, vaut 0,70
  pour SARAH-3 et 0,71 pour CAMS.
- **Écarts aux autres sources, aux 398 localités, 2005-2023 :**

  | Grandeur | Écart à CAMS | Corrélation | Écart à NASA POWER | Corrélation |
  |---|---|---|---|---|
  | GHI | +4,3 % | 0,93 | +7,9 % | 0,87 |
  | DNI | +17,8 % | 0,83 | +49,1 % | 0,77 |
  | DHI | -12,7 % | 0,76 | -15,0 % | 0,53 |

  Corrélation des valeurs journalières, toutes localités confondues.

  SARAH-3 sert le DNI le plus fort des trois sources, et le DHI le plus
  faible. Le DNI dépasse celui de CAMS de 27 % en mars, 37 % en avril et
  32 % en mai, de 3 % en août.
- **Aérosols :** le ciel clair de SARAH-3 repose sur une climatologie
  d'aérosols (MACC) et ne suit pas la poussière du jour ; l'imagerie n'en
  saisit qu'une partie, comme un nuage (Pfeifroth et al. 2024, § 2.5). Le
  ciel clair de CAMS (McClear) en tient compte jour par jour. Par ciel clair
  (GHI de CAMS à 97 % au moins de son ciel clair, aux 351 communes), le
  rapport des sommes SARAH-3 / CAMS suit l'épaisseur optique des aérosols à
  550 nm (EAC4, ADR-0019) :

  | Épaisseur optique | GHI | DNI | DHI |
  |---|---|---|---|
  | sous 0,2 | 1,00 | 0,99 | 1,08 |
  | 0,4 à 0,6 | 1,07 | 1,35 | 0,75 |
  | 1 à 1,5 | 1,15 | 1,87 | 0,71 |

  Les 54 jours où la moyenne nationale du GHI SARAH-3 dépasse celle de CAMS
  de plus de 25 % ont une épaisseur optique moyenne de 1,07, contre 0,34 les
  autres jours. Le DNI de SARAH-3 n'a pas été évalué au sol en Afrique de
  l'Ouest ; les évaluations publiées portent sur le GHI (Sawadogo et
  al. 2023 pour SARAH-2 au Burkina Faso et au Ghana, Kakou et al. 2025 pour
  SARAH-3 en Côte d'Ivoire). La pondération des sources, qui ne peut
  s'appuyer que sur le terrain, viendra au jalon 6.
- **Calculs :** le POA et les autres grandeurs calculées peuvent partir d'une
  série SARAH-3 journalière ; les séries DNI et DHI associées sont trouvées
  dans la même source. Le biais du midi solaire en moyenne journalière
  (ADR-0020) vaut pour SARAH-3 comme pour les autres sources, et le champ
  `limite` de la réponse le chiffre. Sur un plan horizontal, à Fô en 2023, le
  POA dépasse le GHI de 21,0 % avec SARAH-3, de 19,9 % avec CAMS et de 7,3 %
  avec NASA POWER : l'écart croît avec la part du direct.
