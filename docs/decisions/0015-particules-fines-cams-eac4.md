# ADR-0015 : particules fines CAMS EAC4 et salissure

Date : 2026-10-16. Statut : accepté.

## Contexte

Le proxy de salissure du moteur (`/v1/grandeurs/taux_salissure_proxy`, modèle
HSU de pvlib) et le PR réaliste corrigé de la salissure
(`/v1/grandeurs/pr_realiste`, modes `salissure` et `temperature_salissure`)
lisent les concentrations journalières de PM2.5 et de PM10 de la source
`cams_eac4`, avec la pluie journalière NASA POWER (ADR-0013). Aucune série de
particules n'était gravée au Burkina Faso : ces grandeurs répondaient 400. La
fiche de la source, reprise du dépôt d'origine, décrivait encore la période
servie en Guinée (2021 à août 2025).

## Décision

- Réanalyse CAMS EAC4 de l'ECMWF (jeu `cams-global-reanalysis-eac4` de l'ADS
  Copernicus, DOI 10.24381/d58bbf47), variables `particulate_matter_2.5um`
  et `particulate_matter_10um`, huit pas de 3 h par jour (00 à 21 h UTC),
  zone demandée de 15,5 à 9 °N et de -6 à 3 °E, servie de 15 à 9 °N
  (9 × 13 mailles) : les provinces et une maille de marge. Une requête par
  année ou par bloc d'années consécutives, découpé en fichiers annuels à
  réception (2005 à 2008 et 2025 année par année, 2009 à 2024 en un bloc) ;
  chaque année est gardée en cache et les CSV se régénèrent à l'octet près.
- Recette du dépôt d'origine : maille de 0,75° la plus proche de chaque
  province, sans interpolation ; moyenne des huit pas du jour civil UTC ;
  conversion de kg/m³ en µg/m³ (× 10⁹) ; arrondi à 4 décimales.
- Les pas servis à zéro par la réanalyse sont gardés tels quels. Le zéro
  reflète l'état de l'analyse, dont les pas suivants restent bas : écarter
  les seuls zéros ne corrigerait qu'une partie du creux. Ils sont signalés,
  chiffrés, dans la note publique de chaque série.
- Lot `provinces`, 2005-2025 : EAC4 est servi depuis 2003, mais la période
  reste celle de CAMS Radiation (ADR-0011), seule autre source CAMS de
  l'instance. Méthode `reanalyse`, confiance B. Valeurs strictement
  positives, au plus 1 000 µg/m³ pour le PM2.5 et 1 500 µg/m³ pour le PM10,
  au-dessus des maxima servis (bornes relevées par l'ADR-0018).
- Ingesteur `scripts/ingest_cams_eac4_journalier.py` (clé `ADS_API_KEY`) ;
  migration 0013 (`COPY` dans `mesures_ressource`, trigger d'audit suspendu),
  qui récrit aussi la fiche de la source `cams_eac4` (date de consultation,
  DOI, notes, période réelle) et la rend à son état d'origine au
  `downgrade`.

## Conséquences

- 94 séries et 720 980 mesures, 5 Mo de CSV ; la migration 0013 dure une
  minute. 34 mailles EAC4 distinctes pour 47 provinces : 11 mailles servent
  deux ou trois provinces voisines ; la maille retenue est à 31 km du point
  en médiane, 52 km au plus.
- L'ADS fait passer les requêtes EAC4 par la file de son archive MARS, limitée
  à 60 requêtes en cours, et n'admet que cinq requêtes en file par compte et
  par jeu. En octobre 2026, chaque requête annuelle a attendu plus de dix
  heures pour trois minutes d'exécution ; les années 2009 à 2024, demandées en
  une seule requête (93 504 champs, sous la limite de 100 000), ont attendu
  5 h 24 et tourné une heure.
- Sur les provinces et sur 2005-2025 : PM2.5 de 39,6 µg/m³ en moyenne (médiane
  28,4), PM10 de 51,6 (médiane 37,7) ; le PM2.5 ne dépasse jamais le PM10, dont
  il fait 75 % en médiane. Le PM10 annuel va de 40,3 µg/m³ (2013) à 60,6
  (2015).
- Saisons : 79,9 µg/m³ de PM10 de décembre à mars contre 21,5 de juillet à
  septembre, soit 3,7 fois plus. Le pic mensuel du PM10 tombe en février ou
  en mars, saison de l'harmattan, pour 38 provinces ; en novembre ou en
  décembre pour les 9 du sud et de l'est (Kompienga, Gobnangou, Nahouri,
  Sissili, Ziro, Poni, Noumbiel, Ioba, Bougouriba), saison des feux de
  brousse. Les maxima tombent dans cette saison : 744 µg/m³ de PM2.5 et
  1 017 de PM10 le 13 novembre 2013 dans la Gobnangou. Le rapport PM2.5/PM10
  ne départage pas fumées et poussière : 0,79 en janvier et février, 0,755
  en novembre.
- Pas nuls : 0,97 % des pas de 3 h (de 0,50 % en 2005 à 1,46 % en 2023), aux
  deux grandeurs à la fois, surtout à 12 h UTC (71 %), puis à 15, 18 et 21 h ;
  jamais avant 12 h, sauf 44 pas en 2025. Ils touchent 5,6 % des jours, dont
  la moyenne baisse de 12,5 % en médiane ; 629 jours-province en comptent
  quatre sur huit, ce qui divise leur moyenne par deux. Le PM10 annuel en
  perd de 0,4 % (zéros remplacés par la moyenne des autres pas du jour) à
  0,9 % (zéros écartés de la moyenne de l'année), et jusqu'à 1,4 % en 2023.
  La page des problèmes connus d'EAC4 ne les mentionne pas.
- Salissure HSU sur 2005-2025 (plan de 10°, nettoyage à partir de 1 mm de
  pluie, défauts du moteur) : perte moyenne de 2,2 % au Kadiogo, de 6,6 % en
  février et quasi nulle de juin à septembre (0,4 % au plus) ; 3,3 % dans
  l'Oudalan, au nord, où
  elle atteint 15 % en fin de saison sèche ; 1,1 % dans le Poni, au sud-ouest.
- PR réaliste au Kadiogo, PR fourni de 0,8, sur les jours communs de
  2005-2025 : 0,772 corrigé de la température, 0,782 de la salissure, 0,755 des
  deux.
- Ni l'inclinaison ni la pluie ne déplacent beaucoup ces pertes. Le défaut
  de 10°, choisi pour la Guinée, reste sous la latitude des provinces (9,8 à
  14,5 °N), mais à 15° la perte du Kadiogo ne baisse que de 1,6 % en relatif
  (2,20 % contre 2,24 %). La rupture de la pluie NASA POWER en 2015
  (ADR-0013) laisse inchangée la perte moyenne des provinces : 2,00 % sur
  2006-2014, 2,01 % sur 2015-2025.
- Limites : maille de 0,75° ; proxy de modèle, pas une mesure de salissure ;
  premiers jours de 2005 sous-estimés (le modèle part d'un panneau propre).
  Seules des mesures sur site diront ce que vaut le proxy.
