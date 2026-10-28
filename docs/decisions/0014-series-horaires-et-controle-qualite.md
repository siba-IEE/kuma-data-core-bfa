# ADR-0014 : séries horaires des points pilotes et contrôle qualité

Date : 2026-10-15. Statut : accepté.

## Contexte

Le moteur sait servir une série horaire stockée et validée
(`/v1/horaire/{localite}/{grandeur}`) et calculer les grandeurs métier par
intégration horaire (`methode=integration_horaire`). Au Burkina Faso, aucune
série horaire n'était gravée : l'endpoint relayait NASA POWER à la volée, sans
validation, et l'intégration horaire n'avait pas de données. La doctrine de
contrôle qualité horaire (`docs/methodologie/doctrine-qc-horaire.md`, v1,
socle BSRN) n'avait jamais été appliquée.

Le jalon 4 calera le satellite sur les stations sol ESMAP/WAPP de Dédougou,
Dori, Kaya et Koupéla, qui mesurent à un pas plus fin que l'heure : il lui
faut le satellite horaire aux mêmes points.

## Décision

- Cinq points pilotes : la commune de Ouagadougou et les départements de
  Dédougou, Dori, Kaya et Koupéla, chacun dans sa propre maille de 1°.
  Période 2021-2025.
- Quatre grandeurs NASA POWER horaires (POWER Hourly API v2.10.2,
  `time-standard=UTC`) : GHI, DNI et DHI (`ALLSKY_SFC_SW_DWN`,
  `ALLSKY_SFC_SW_DNI`, `ALLSKY_SFC_SW_DIFF`, CERES SYN1deg, méthode
  `modele_satellitaire`) et T2M (MERRA-2, méthode `reanalyse`), confiance B.
  Bornes : 0 à 1 400 W/m² (GHI, DNI), 0 à 900 W/m² (DHI), -5 à 55 °C.
  Ingesteur `scripts/ingest_nasa_power_horaire.py`, une requête par point ;
  migration 0011 (`COPY` dans `mesures_ressource_horaires`, trigger d'audit
  suspendu), lignes en statut `brut`.
- Convention de stockage : l'instant d'une mesure horaire désigne le début
  de l'heure dont la valeur est la moyenne, comme chez NASA POWER. Le
  contrôle qualité et le POA horaire calculent donc la géométrie solaire
  30 minutes plus tard, au milieu de l'heure, par une seule constante
  (`services.horaire.DECALAGE_MILIEU_HEURE`). Une autre source horaire, les
  stations du jalon 4 par exemple, s'y ramène à l'ingestion.
- Contrôle qualité, doctrine v1, en migration 0012 : plausibilité BSRN
  (« physiquement possible », test dur ; « extrêmement rare », drapeau),
  fermeture `GHI / (DHI + DNI·cos z)` et ratio diffus `DHI / GHI`
  (drapeaux). Une ligne qui passe les tests durs devient `valide_auto`, avec
  ses drapeaux dans `commentaire_editorial` (`[QC v1] ...`) ; une ligne
  rejetée resterait `brut` avec son motif. Le niveau reste B. Le trigger
  d'audit est suspendu le temps de cette requalification algorithmique de
  masse (`docs/architecture/03-audit.md`).
- POA horaire, mono-plan et bifacial : direct reconstruit sur le GHI et le
  DHI, `(GHI - DHI) / cos z`, nul au-delà de 88° de zénith et borné à
  l'éclairement extraterrestre (`pvlib.irradiance.dni`). Seule la compagne
  DHI horaire est requise. La méthode journalière ne change pas.
- Intégration horaire de toutes les grandeurs (POA, productibles, ECS,
  degrés-jours) : seuls les jours UTC dont les 24 heures sont présentes et
  validées entrent dans le calcul. Une heure absente ou rejetée retire son
  jour du résultat au lieu de l'amputer : une heure de midi pèse 15 % du POA
  du jour.

## Conséquences

- 20 séries et 876 480 mesures, 4 Mo de CSV ; les migrations 0011 et 0012
  durent un peu plus d'une minute chacune. Les valeurs retéléchargées
  redonnent les CSV à l'octet près.
- La convention est vérifiée sur les données : le centroïde du GHI horaire
  tombe de 0,46 à 0,50 h avant le midi solaire aux cinq points, ce que donne
  une moyenne datée du début de l'heure (une moyenne datée de la fin de
  l'heure le placerait 0,5 h après). Cumulé par jour UTC, le GHI horaire
  redonne la série mensuelle de chaque localité à moins de
  0,01 kWh/m²/jour près sur les 60 mois : unité et complétude sont
  confirmées, pas l'horodatage, la nuit couvrant minuit UTC.
- Contrôle qualité : aucune ligne rejetée, les 876 480 lignes passent en
  `valide_auto`. Calculée au début de l'heure, la géométrie aurait rejeté
  628 lignes de DHI dans les premières heures de la matinée.
- Les composantes de NASA POWER ne se referment pas : sur 2021-2025,
  `DHI + DNI·cos z` reste de 5,9 à 6,9 % sous le GHI selon le point. D'où le
  drapeau de fermeture sur 27 à 32 % des heures de jour, la tolérance BSRN
  étant de 8 %. S'y ajoutent 142 lignes au ratio diffus élevé, 2 DHI et
  166 DNI « extrêmement rares ». Ces DNI tombent tous à des heures où le
  soleil n'est levé qu'une partie de l'heure et se trouve sous l'horizon en
  son milieu : un effet de la géométrie ponctuelle appliquée à une moyenne,
  non de la source.
- Le DNI reste servi tel quel par `/v1/horaire`, avec cette mise en garde
  dans sa note publique. Le direct reconstruit par le moteur le dépasse de
  12 à 14 % en cumul.
- L'ancien POA horaire, avec le DNI de la source et la géométrie au début de
  l'heure, perdait 8 % du GHI sur un plan horizontal (5,32 kWh/m²/jour au
  lieu de 5,78 à Ouagadougou en 2024 ; 5,35 avec la seule géométrie
  corrigée). Avec le direct reconstruit, le plan horizontal retrouve le GHI
  de l'année à 0,01 % près ; l'écart d'un jour reste sous 1 %, dû aux
  heures où le DHI de la source dépasse le GHI ou où le soleil se lève après
  le milieu de l'heure.
- À Ouagadougou en 2024, en intégration horaire : 5,98 kWh/m²/jour sur un
  plan à 15° plein sud, soit 3,5 % de plus que le GHI, quand la méthode
  journalière en ajoute 12 % au Kadiogo (6,46, ADR-0013), soit 8 % de trop ;
  le bifacial (`gcr` 0,4, bifacialité 0,7, albédo 0,25) dépasse le
  monofacial de 7,7 % ; la température coûte 10 % du productible (NOCT
  45 °C, -0,35 %/°C) ; 1 282 degrés-jours de climatisation en base 26 °C.
- `/v1/horaire` sert la série stockée, statut `valide_auto`, quand elle
  couvre la plage demandée ; ailleurs et hors 2021-2025, il relaie toujours
  NASA POWER sans validation. Il exprime le rayonnement en Wh/m² sur
  l'heure, égal à la moyenne en W/m² ; le catalogue `/v1/series` affichait
  l'unité de référence de la grandeur (kWh/m²/jour), qui ne vaut pas pour
  ces séries, et donne Wh/m² depuis la version 0.20.0.
- Une série horaire passée à une grandeur sans `methode=integration_horaire`
  donne une réponse vide, comme avant ce lot ; une période qui déborde
  2021-2025 est réduite aux jours servis.
- Points ouverts pour le jalon 4 : le POA horaire ignore le DNI même quand
  une station le mesurera au pyrhéliomètre ; Dori est au coin de quatre
  mailles CERES, à garder en tête pour le calage ; le QC v1 ne contient pas
  encore les tests temporels de la doctrine (pics, valeurs gelées), et un
  drapeau ne déclasse pas la ligne. Seules les stations sol diront quelle
  composante de NASA POWER s'écarte.
