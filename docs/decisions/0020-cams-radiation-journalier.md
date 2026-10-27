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
- L'indice de fiabilité que le service joint à chaque jour n'est pas repris ;
  les notes le disent.
- Le POA en moyenne journalière, biaisé par la géométrie du midi solaire (voir
  plus bas), n'est pas corrigé dans ce lot : la réponse de `poa_parametrable`
  et de `poa_bifacial` en porte l'avertissement chiffré, champ `limite`.

## Conséquences

- 1 990 séries, dont 1 970 porteuses ; 41 370 lignes annuelles et
  15 104 026 valeurs, 63 Mo en base ; 31 Mo de fichiers ; la migration dure
  une trentaine de secondes. 1 978 jours-localités sans valeur par grandeur
  tous temps (0,06 %), sur cinq dates de 2005 et 2006.
- Sur les mois complets, la moyenne des jours redonne la série mensuelle CAMS
  de l'ADR-0011 à 0,0001 kWh/m²/jour près ; les trois mois qui comptent des
  jours non servis (janvier 2005, janvier 2006, septembre 2006) s'en écartent
  jusqu'à 0,20 kWh/m²/jour.
- Moyennes sur 2005-2025 : GHI de 6,0 kWh/m²/jour (6,1 au nord de 13,5 °N,
  5,8 au sud de 10,5 °N ; 6,45 en mars, 5,4 en août), DNI de 4,9 (3,7 en
  août), DHI de 2,5 ; GHI par ciel clair de 6,7. Le GHI vaut 89 % du GHI par
  ciel clair en moyenne. Les jours sans nuage détecté, il l'égale : 21 % des
  jours, de 38 à 45 % de novembre à février, 1 % en août.
- Aux 351 communes, CAMS dépasse NASA POWER de 3,6 % sur le GHI (corrélation
  journalière de 0,91) et de 27 % sur le DNI (0,88) ; il sert 2,6 % de moins
  sur le DHI (0,75). CAMS compte ses jours en temps universel, NASA POWER en
  heure solaire locale. Le DNI de NASA POWER est trop faible : à Fô en 2024,
  le direct horizontal (GHI moins DHI) le dépasse 101 jours sur 366, ce
  qu'aucun direct réel ne permet ; jamais avec CAMS.
- L'indice de fiabilité passe sous 0,9 pour 0,10 % des jours-localités
  servis, en 2005 et 2006, et le 17 août 2024 partout. Le 18 avril 2005
  (0,84 en moyenne), 20 localités tombent entre 0,5 et 1 kWh/m²/jour, avec un
  DNI presque nul, quand CAMS sert environ 6 la veille et le lendemain et
  NASA POWER de 4,5 à 6,1 le même jour. Artefact probable, mais des valeurs
  aussi basses existent les jours réellement couverts (16 avril 2022, 5 août
  2007) : les valeurs sont gardées.
- Le POA en moyenne journalière (ADR-0013), celui de `poa_parametrable` comme
  celui de `poa_bifacial`, projette le DNI du jour avec la géométrie du midi
  solaire, où le soleil est le plus haut. Sur un plan horizontal, il rend
  18,5 % de plus que le GHI avec les séries CAMS de Fô en 2024. La fermeture
  exacte de CAMS montre que l'écart vient de la méthode, non de la donnée.
  Avec NASA POWER, l'écart n'est que de 6 % parce que deux erreurs se
  compensent, la méthode et un DNI trop faible (3,8 contre
  5,0 kWh/m²/jour) : elle n'y est pas plus juste. Sur un plan à 15° plein
  sud, l'excès est de l'ordre de 20 % avec CAMS.
- Aucune série horaire n'existe pour CAMS : l'intégration horaire de
  l'ADR-0014 ne couvre que les cinq points pilotes, avec NASA POWER, en
  2021-2025. En moyenne journalière, la réponse des deux grandeurs porte donc
  un champ `limite` qui donne l'écart au GHI, sur un plan horizontal, des
  jours demandés. La correction de la méthode, qui partira du direct
  horizontal (GHI moins DHI) et d'une géométrie intégrée sur le jour, est un
  lot du moteur : elle changera aussi les résultats tirés de NASA POWER et
  les chiffres de l'ADR-0013.
