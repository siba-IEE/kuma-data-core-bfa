# ADR-0021 : météo complémentaire NASA POWER

Date : 2026-10-27. Statut : accepté.

## Contexte

NASA POWER sert déjà la température moyenne, l'humidité relative et la pluie
journalières (ADR-0013, ADR-0017). Le jalon 5 étoffe le brut satellite et de
réanalyse. La même API sert, aux mêmes points, les températures extrêmes du
jour, le point de rosée, le vent à 10 et 50 m, la pression de surface et la
nébulosité :
- le maximum de température commande l'échauffement des modules ;
- le point de rosée mesure la vapeur d'eau de l'air, très faible sous
  l'harmattan ;
- le vent refroidit les modules, soulève les poussières et sert l'éolien ;
- la pression donne la densité de l'air ;
- la nébulosité aide à lire le rayonnement.

## Décision

- Neuf grandeurs journalières de NASA POWER (communauté RE), 2005-2025, aux
  398 localités (lot `localites`), en stockage dense (ADR-0017) :

  | Grandeur | Paramètre | Valeur du jour | Unité |
  |---|---|---|---|
  | `t2m_min` | `T2M_MIN` | plus basse température horaire | °C |
  | `t2m_max` | `T2M_MAX` | plus haute température horaire | °C |
  | `point_rosee_2m` | `T2MDEW` | point de rosée moyen (de givre sous 0 °C) | °C |
  | `vent_10m` | `WS10M` | moyenne des vitesses horaires | m/s |
  | `vent_10m_max` | `WS10M_MAX` | plus forte vitesse horaire | m/s |
  | `direction_vent_10m` | `WD10M` | direction d'où souffle le vent moyen vectoriel | degrés depuis le nord |
  | `vent_50m` | `WS50M` | moyenne des vitesses horaires | m/s |
  | `pression_surface` | `PS` | pression moyenne, à l'altitude de la maille | kPa |
  | `nebulosite` | `CLOUD_AMT` | part de la maille couverte de nuages, vue par satellite | % |

  Toutes viennent de la réanalyse MERRA-2 du GMAO (maille de 0,5° × 0,625°,
  méthode `reanalyse`), sauf la nébulosité, qui vient de CERES SYN1deg
  (maille de 1°, méthode `modele_satellitaire`). Confiance B.
- **Référentiel :** huit grandeurs ajoutées. `vent_10m` y figurait, sans
  série ; sa description, qui la disait hors périmètre, est mise à jour. Deux
  unités ajoutées pour la direction du vent : le degré, et le radian, son
  unité SI.
- **Bornes,** au-dessus des extrêmes servis :

  | Grandeur | Extrêmes servis | Bornes |
  |---|---|---|
  | Température minimale | 8,06 à 33,77 °C | 0 à 45 °C |
  | Température maximale | 21,44 à 46,22 °C | 5 à 55 °C |
  | Point de rosée | -16,57 à 25,05 °C | -30 à 35 °C |
  | Vent moyen à 10 m | 9,21 m/s au plus | 0 à 15 m/s |
  | Vent maximal à 10 m | 12,81 m/s au plus | 0 à 20 m/s |
  | Vent à 50 m | 11,14 m/s au plus | 0 à 20 m/s |
  | Direction | 0 à 360° | 0 à 360° |
  | Pression | 95,87 à 99,39 kPa | 85 à 105 kPa |
  | Nébulosité | 0 à 99,98 % | 0 à 100 % |

  Les bornes du vent, de 1,6 à 1,8 fois les maxima servis, arrêteraient une
  vitesse servie en nœuds ou en km/h. Aucun écart admis.
- **Ingesteur :** famille `meteo_complementaire` de
  `scripts/ingest_nasa_power_journalier.py --lot localites`, une requête par
  localité, POWER Daily API v2.10.1. Migration 0020.
- **Fiche de la source :** la migration 0020 met au Burkina Faso la fiche de
  `nasa_power`, restée celle du dépôt d'origine, et la lui rend au
  `downgrade`.

## Conséquences

- **Volume :** 3 582 séries, dont 697 porteuses : 83 mailles MERRA-2 pour
  chacune des huit grandeurs de réanalyse, 33 mailles CERES pour la
  nébulosité. 14 637 lignes annuelles et 5 345 990 valeurs, toutes servies.
  Environ 28 Mo en base, dont 22 Mo de valeurs, et 12 Mo de fichiers ; la
  migration dure une dizaine de secondes.
- **Agrégats du jour :** l'API horaire confirme le calcul de NASA POWER, à
  Ouagadougou, Koutougou, Tin-Akoff et Loumana, en janvier, mars et juillet.
  - La vitesse du jour est la moyenne des vitesses horaires, le maximum la
    plus forte d'entre elles. Ce maximum n'est pas la rafale : ni les
    rafales, de quelques secondes, ni les coups de vent des lignes de grains,
    de quelques minutes, n'y figurent.
  - La direction est celle du vent moyen vectoriel, pondéré par la vitesse.
    Par vents tournants, elle peut s'écarter de la direction la plus
    fréquente. Plusieurs jours se moyennent par composantes, non par angles :
    la moyenne des angles de mars donnerait 115° au lieu de 66°.
  - Les températures minimale et maximale sont le minimum et le maximum
    horaires ; le point de rosée, la pression et la nébulosité, des moyennes
    horaires.
- **Point de givre :** sous 0 °C, NASA POWER sert le point de givre
  (saturation sur la glace), plus haut que le point de rosée d'environ 0,7 °C
  à -5 °C et de 2 °C à -16,6 °C, valeur la plus basse servie. Cela touche
  14 % des jours-localités de l'année, 41 % de décembre à février.
- **Pression :** elle est donnée à l'altitude moyenne de la maille MERRA-2
  (de 199 à 409 m), non à celle de la localité : en moyenne sur 2005-2025,
  elle perd 1,09 kPa par 100 m d'altitude de la maille, à 0,01 kPa près.
- **Nébulosité :** fraction nuageuse vue par satellite, nuages fins compris ;
  elle ne mesure pas l'atténuation. Les jours couverts à 90 % ou plus, CAMS
  sert en moyenne 59 % du rayonnement par ciel clair de juin à septembre, et
  69 % de novembre à mars. Sous 10 % de nébulosité, il sert le rayonnement
  par ciel clair.
- **Moyennes sur les 398 localités, 2005-2025 :**
  - températures : minimum de 21,7 °C (15,8 en janvier, 26,2 en mai),
    maximum de 34,7 °C (39,8 en avril, 30,1 en août) ; 46,2 °C au plus, le
    13 mai 2025 à Tin-Akoff ;
  - point de rosée : de 0,1 °C en janvier à 22,5 °C en août ;
  - vent à 10 m : 3,2 m/s (3,7 au nord de 13,5 °N, 3,0 au sud de 10,5 °N), de
    4,2 m/s en janvier à 2,1 en septembre ; le vent à 50 m vaut 1,52 fois
    le vent à 10 m ;
  - direction en moyenne vectorielle : nord-est (51 à 55°) de décembre à
    février, harmattan ; sud à sud-ouest (194 à 221°) de mai à septembre,
    mousson. La bascule de mars-avril remonte du sud au nord : en avril, le
    vent vient du sud 93 % des jours au sud de 10,5 °N, 42 % au nord de
    13,5 °N ;
  - pression : 97,6 kPa ;
  - nébulosité : 51 %, de 23 % en décembre à 77 % en août.
- **Cohérence :** chaque jour, le minimum reste sous le maximum, le point de
  rosée sous le maximum, et le vent moyen à 10 m sous son maximum et sous le
  vent à 50 m. Aux communes, la température moyenne (ADR-0017) reste entre
  le minimum et le maximum, et le point de rosée sous elle.
- **Heure du jour :** NASA POWER compte ses jours en heure solaire locale,
  arrondie à l'heure. Au Burkina Faso, c'est le jour UTC : la série horaire en
  heure locale y est identique à la série UTC. Ces séries se comparent donc
  sans décalage à celles de CAMS.
- **Usage :** aucune grandeur calculée ne lit encore ces séries. Le
  productible corrigé de la température utilise la température moyenne
  (ADR-0013). Un modèle thermique qui dépend du vent, Faiman par exemple,
  demanderait un calage au sol. La capsule d'étude
  (`services/capsule/acquisition.py`) lit les températures minimale et
  maximale pour le dimensionnement des chaînes de modules ; elle reste
  inopérante au Burkina Faso tant qu'elle exige un GHI mensuel 1991-2020.
  Le vent à 50 m est celui du modèle, non mesuré : une puissance éolienne,
  qui suit le cube de la vitesse, ne se calcule pas sur des moyennes du jour.
