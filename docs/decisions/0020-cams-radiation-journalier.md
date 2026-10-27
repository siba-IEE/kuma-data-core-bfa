# ADR-0020 : rayonnement journalier CAMS Radiation

Date : 2026-10-27. Statut : accepté.

## Contexte

CAMS Radiation sert déjà le GHI, le DNI et le DHI mensuels aux 398 localités
(ADR-0011). Le jalon 4 demande le pas journalier, et le ciel clair : le
rapport entre le GHI tous temps et le GHI par ciel clair mesure la nébulosité,
et le ciel clair de CAMS (McClear) tient compte des aérosols et de la vapeur
d'eau du jour. Contrairement à NASA POWER et à EAC4, le service est interrogé
au point : chaque localité a sa série.

## Décision

- Cinq grandeurs journalières, total du jour UTC en kWh/m²/jour : `ghi`,
  `dni` et `dhi` tous temps, `ghi_ciel_clair` et `dni_ciel_clair`, ces deux
  dernières ajoutées au référentiel (stockées). Le DNI est l'irradiation
  normale (BNI) ; le GHI est la somme exacte du direct horizontal et du
  diffus.
- Séries 2005-2025 aux 398 localités (lot `localites`), en stockage dense
  (ADR-0017), méthode `modele_satellitaire`, confiance B. Seules quatre
  provinces, au même point que leur commune chef-lieu, lisent la série de
  celle-ci.
- Bornes : GHI 9, DNI 11, DHI 6,5, ciel clair 9 et 11 kWh/m²/jour, au-dessus
  des maxima servis (8,34, 10,14, 4,61, 8,36 et 10,17) ; borne basse
  strictement positive, sauf pour le DNI, qui peut être nul un jour couvert.
  Aucun écart admis.
- Les jours que le service ne sert pas tous temps (`nan`, en 2005 et 2006
  seulement) restent sans valeur et sont listés dans la note de la série ;
  le ciel clair n'en a aucun.
- Ingesteur `scripts/ingest_cams_radiation_journalier.py` : une requête par
  localité au pas d'un jour, version du service et date de génération lues
  dans l'en-tête de la réponse, point de l'en-tête comparé au point demandé ;
  migration 0019, qui met aussi à jour la fiche de la source
  `cams_radiation`, restée celle du dépôt d'origine.

## Conséquences

- 1 990 séries, dont 1 970 porteuses ; 41 370 lignes annuelles et
  15 104 026 valeurs, 63 Mo en base ; 33 Mo de fichiers ; la migration dure
  une trentaine de secondes. 1 978 jours-localités sans valeur par grandeur
  tous temps (0,06 %), tous en 2005 et 2006.
- Sur les mois complets, la moyenne des jours redonne la série mensuelle CAMS
  de l'ADR-0011 à 0,0001 kWh/m²/jour près.
- Moyennes sur 2005-2025 : GHI de 6,0 kWh/m²/jour (6,1 au nord de 13,5 °N,
  5,8 au sud de 10,5 °N ; 6,45 en mars, 5,4 en août), DNI de 4,9 (3,7 en
  août), DHI de 2,5 ; GHI par ciel clair de 6,7. Le GHI vaut 89 % du GHI par
  ciel clair en moyenne ; un jour sur cinq, sans nuage détecté, il l'égale.
- Aux 351 communes, le GHI de CAMS dépasse celui de NASA POWER de 3,6 % en
  moyenne, avec une corrélation journalière de 0,91 ; CAMS compte ses jours
  en temps universel, NASA POWER en heure solaire locale.
- Le POA en moyenne journalière (ADR-0013) projette le DNI du jour avec la
  géométrie du midi solaire. Sur un plan horizontal, il rend 18,5 % de plus
  que le GHI avec les séries CAMS de Fô en 2024, contre 6 % avec NASA POWER,
  dont le DNI est plus faible (3,8 contre 5,0 kWh/m²/jour). La fermeture
  exacte de CAMS montre que l'écart vient de la méthode, non de la donnée :
  une méthode qui part du direct horizontal (GHI moins DHI) et de la
  géométrie intégrée sur le jour le corrigerait. À traiter dans un lot du
  moteur ; d'ici là, l'intégration horaire reste la référence pour le POA.
