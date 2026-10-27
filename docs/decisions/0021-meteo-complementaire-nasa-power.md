# ADR-0021 : météo complémentaire NASA POWER

Date : 2026-10-27. Statut : accepté.

## Contexte

NASA POWER sert déjà la température moyenne, l'humidité relative et la pluie
journalières (ADR-0013, ADR-0017). Le jalon 5 étoffe le brut satellite et de
réanalyse. La même API sert, aux mêmes points, les températures extrêmes du
jour, le point de rosée, le vent à 10 et 50 m, la pression de surface et la
nébulosité :
- le maximum de température commande l'échauffement des modules ;
- le point de rosée mesure l'humidité absolue de l'air sec de l'harmattan ;
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
  | `point_rosee_2m` | `T2MDEW` | point de rosée moyen | °C |
  | `vent_10m` | `WS10M` | vitesse moyenne | m/s |
  | `vent_10m_max` | `WS10M_MAX` | plus forte vitesse horaire | m/s |
  | `direction_vent_10m` | `WD10M` | direction d'où souffle le vent moyen, en moyenne vectorielle | degrés depuis le nord |
  | `vent_50m` | `WS50M` | vitesse moyenne | m/s |
  | `pression_surface` | `PS` | pression moyenne | kPa |
  | `nebulosite` | `CLOUD_AMT` | part du ciel couverte | % |

  Toutes viennent de la réanalyse MERRA-2 du GMAO (maille de 0,5° × 0,625°,
  méthode `reanalyse`), sauf la nébulosité, qui vient de CERES (maille de 1°,
  méthode `modele_satellitaire`). Confiance B.
- **Référentiel :** huit grandeurs ajoutées (`vent_10m` y figurait, sans
  série). Deux unités ajoutées pour la direction du vent : le radian et le
  degré.
- **Bornes :**
  - températures : 0 à 45 °C pour le minimum, 5 à 55 °C pour le maximum ;
  - point de rosée : -30 à 35 °C ;
  - vent : 0 à 30 m/s pour le vent moyen à 10 m, 0 à 40 m/s pour le
    maximum et pour le vent à 50 m ;
  - direction : 0 à 360° ;
  - pression : 85 à 105 kPa ;
  - nébulosité : 0 à 100 %.

  Aucun écart admis.
- **Ingesteur :** famille `meteo_complementaire` de
  `scripts/ingest_nasa_power_journalier.py --lot localites`, une requête par
  localité, POWER Daily API v2.10.1. Migration 0020.
- **Fiche de la source :** la migration 0020 met au Burkina Faso la fiche de
  `nasa_power`, restée celle du dépôt d'origine, et la lui rend au
  `downgrade`.

## Conséquences

- 3 582 séries, dont 697 porteuses : 83 mailles MERRA-2 pour chacune des
  huit grandeurs de réanalyse, 33 mailles CERES pour la nébulosité.
  14 637 lignes annuelles et 5 345 990 valeurs, toutes servies ; 21 Mo en
  base, 12 Mo de fichiers ; la migration dure une trentaine de secondes.
- **Agrégats du jour :** l'API horaire, à Ouagadougou en janvier 2024, permet
  de vérifier le calcul de NASA POWER.
  - La vitesse du jour est la moyenne des vitesses horaires, le maximum la
    plus forte d'entre elles.
  - La direction est celle du vent moyen vectoriel. Par vents tournants, elle
    peut s'écarter de la direction dominante.
  - Le maximum de vent n'est pas la rafale : les rafales des lignes de
    grains, de quelques minutes, n'y figurent pas.
- **Moyennes sur les 398 localités, 2005-2025 :**
  - températures : minimum de 21,7 °C (15,8 en janvier, 26,2 en mai),
    maximum de 34,7 °C (39,8 en avril, 30,1 en août) ; 46,2 °C au plus, le
    13 mai 2025 à Tin-Akoff ;
  - point de rosée : de 0,1 °C en janvier à 22,5 °C en août ; il passe sous
    0 °C pour 41 % des jours-localités de décembre à février ;
  - vent à 10 m : 3,2 m/s (3,8 au nord de 13,5 °N, 3,0 au sud de 10,5 °N), de
    4,2 m/s en janvier à 2,1 en septembre ; le vent à 50 m vaut 1,52 fois
    le vent à 10 m ;
  - direction en moyenne vectorielle : de nord-est à est-nord-est de novembre
    à mars (51 à 75°, harmattan), de sud à sud-ouest d'avril à septembre (189
    à 221°, mousson) ;
  - pression : 97,6 kPa ;
  - nébulosité : 51 %, de 23 % en décembre à 77 % en août.
- **Cohérence :** chaque jour, le minimum reste sous le maximum, le point de
  rosée sous le maximum, et le vent moyen à 10 m sous son maximum et sous le
  vent à 50 m.
- **Heure du jour :** le jour de NASA POWER est compté en heure solaire
  locale, celui de CAMS en temps universel ; l'écart reste sous 22 minutes au
  Burkina Faso.
- **Usage :** aucune grandeur calculée ne lit encore ces séries. Le
  productible corrigé de la température utilise la température moyenne
  (ADR-0013). Un modèle thermique qui dépend du vent, Faiman par exemple,
  demanderait un calage au sol.
