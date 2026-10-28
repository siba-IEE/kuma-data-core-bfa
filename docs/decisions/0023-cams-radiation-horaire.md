# ADR-0023 : rayonnement horaire CAMS Radiation aux points pilotes

Date : 2026-10-28. Statut : accepté.

## Contexte

Les cinq points pilotes (Ouagadougou et les départements de Dédougou, Dori,
Kaya et Koupéla, ADR-0014) portent les seules séries horaires du dépôt : celles
de NASA POWER, dont les composantes ne se referment pas (`DHI + DNI·cos z`
reste de 6 à 7 % sous le GHI) et dont le DNI est trop faible (ADR-0020). CAMS
Radiation sert déjà le mensuel (ADR-0011) et le journalier (ADR-0020) aux
398 localités ; le même service sert l'horaire, avec le ciel clair de McClear.
Le POA en moyenne journalière souffre du biais du midi solaire (ADR-0020) : une
seconde série horaire, aux composantes cohérentes entre elles, permet
l'intégration horaire avec une autre source que NASA POWER.

## Décision

- **Grandeurs :** GHI, DNI et DHI tous temps et GHI par ciel clair horaires de
  CAMS Radiation (service v4.6, jeu `cams-solar-radiation-timeseries` de
  l'ADS Copernicus), 2021-2025, aux cinq points pilotes, méthode
  `modele_satellitaire`, confiance B. Bornes : 0 à 1 400 W/m² (GHI, DNI, GHI
  par ciel clair), 0 à 900 W/m² (DHI), celles de l'ADR-0014.
- **Valeur et instant :** le CSV de l'ADS donne l'irradiation intégrée sur
  l'heure UTC en Wh/m², soit la moyenne de l'heure en W/m². La période
  `HH:00/HH+1:00` devient l'instant `HH:00`, début de l'heure, convention des
  séries horaires (ADR-0014). Une heure non servie (`nan`) arrête l'ingesteur ;
  aucune ne l'est sur 2021-2025.
- **Stockage :** `mesures_ressource_horaires`, comme NASA POWER. Les séries se
  rattachent à la source `cams_radiation`, dont la fiche ajoute l'horaire.
- **Contrôle qualité :** doctrine v1 (ADR-0014) dans la migration 0022 :
  plausibilité BSRN, fermeture et ratio diffus pour le GHI, le DNI et le DHI de
  chaque point ; plausibilité du GHI seule pour le GHI par ciel clair, faute
  de composantes associées. Trigger d'audit suspendu le temps de la
  requalification.
- **API :** `/v1/horaire` prend un paramètre `source` (`nasa_power` ou
  `cams_radiation`), et sa réponse JSON un champ `source` qui nomme la série
  servie : les codes de source sont désormais exposés. Sans `source`, la
  série de NASA POWER, source du relais, reste servie, comme avant : une même
  requête reste homogène entre heures stockées et heures relayées. Le choix
  est écrit en clair (`services.horaire.SOURCE_RELAIS`), et ne dépend pas de
  l'ordre d'insertion des séries. Une série CAMS, ou le GHI par ciel clair,
  que seul CAMS sert, ne se relaie pas : une plage non couverte répond 400
  `PLAGE_TEMPORELLE_NON_DISPONIBLE`, avec la plage de la série stockée dans
  les détails. La capsule d'étude retient aussi la série de NASA POWER.
  Depuis la version 0.20.0, `/v1/horaire/.../disponibilite` prend aussi
  `source` et donne la plage de la série que sert `/v1/horaire`.
- **Ingesteur :** `scripts/ingest_cams_radiation_horaire.py`, une requête
  par point, réponses brutes en cache. Il contrôle le pas d'une heure, la
  référence au temps universel, le point rappelé par l'en-tête et la version
  du service (v4.6, citée par les notes). Les requêtes partent une à une,
  l'ADS limitant les demandes en file.

## Conséquences

- **Volume :** 20 séries et 876 480 mesures, 4,8 Mo de CSV ; la migration
  dure deux minutes. Réponses générées les 27 et 28 octobre 2026.
- **Convention :** le centroïde du GHI tombe de 0,48 à 0,52 h avant le midi
  solaire aux cinq points, ce que donne une moyenne datée du début de l'heure.
- **Accord avec le journalier :** cumulé par jour UTC, le GHI par ciel clair
  redonne la série journalière de l'ADR-0020 à l'arrondi près
  (5e-5 kWh/m²/jour). Tous temps, l'écart moyen est de 0,02 kWh/m²/jour pour
  le GHI, 0,03 pour le DNI et 0,01 pour le DHI, 0,25 au plus. Il tient aux
  nuages : pour le GHI, 0,007 les jours clairs (indice de ciel clair du jour
  d'au moins 0,9), 0,04 les jours mi-couverts, 0,08 les jours couverts (sous
  0,6). Le service ne cumule donc pas les nuages tout à fait de la même façon
  à l'heure et au jour ; le dépôt n'en connaît pas le détail.
- **Fiabilité :** CAMS sert pour chaque heure la part des données satellite
  fiables. Elle est inférieure à 1 pour 19 % des heures de jour, presque
  toutes au lever et au coucher, jamais sous 0,5, et ces heures portent 1,8 %
  du GHI. Elle n'est pas reprise en base ; les notes le disent.
- **Contrôle qualité :** aucune ligne rejetée, les 876 480 lignes passent en
  `valide_auto`. CAMS sert un GHI égal au direct horizontal plus le diffus :
  la fermeture tient par construction, et ne dit rien de l'exactitude. Seules
  359 heures portent un drapeau de fermeture, 0,3 % des heures de jour (27 à
  32 % pour NASA POWER), aux premières et dernières heures du jour (6-7 h et
  16-17 h UTC, soleil à plus de 63° du zénith), où la géométrie prise au
  milieu de l'heure s'écarte de l'heure intégrée. S'y ajoutent 1 628 DNI
  « extrêmement rares », tous à 5, 6, 17 ou 18 h UTC, quand le soleil est
  sous l'horizon au milieu de l'heure : effet déjà relevé pour NASA POWER
  (ADR-0014). Le GHI tous temps ne dépasse jamais le GHI par ciel clair.
- **Écarts à NASA POWER, mêmes heures, 2021-2025 :**

  | Grandeur | Écart de CAMS | Selon le point | Corrélation horaire |
  |---|---|---|---|
  | GHI | +2,7 % | +1,1 à +4,3 % | 0,987 |
  | DNI | +22 % | +14 à +30 % | 0,922 |
  | DHI | -1,1 % | -3,6 à +3,3 % | 0,935 |

  La corrélation horaire tient pour beaucoup au cycle du jour. L'écart sur le
  DNI va dans le sens de celui du journalier (+27 % aux communes, ADR-0020).
- **POA horaire :** le POA (mono-plan et bifacial) et le productible à PR
  fourni sans correction de température partent aussi d'une série CAMS, dont
  la compagne DHI est trouvée dans la même source. À Ouagadougou en 2024, sur
  un plan horizontal, le POA redonne le GHI de l'année à 0,1 % près (0,6 % au
  plus sur un jour) ; à 15° plein sud, il le dépasse de 3,5 %, comme avec
  NASA POWER (ADR-0014). Le GHI de CAMS y vaut 6,04 kWh/m²/jour, contre 5,78
  pour NASA POWER.
- **Limites :**
  - l'horaire CAMS ne couvre que les cinq points pilotes et 2021-2025 ;
  - CAMS ne sert pas de température : les grandeurs qui demandent la
    température horaire (productible corrigé de la température, énergie utile
    ECS, productible à PR fourni avec correction de température) restent
    liées à la série NASA POWER ;
  - le choix entre les deux séries reste à l'appelant : le calage sur les
    stations sol dira laquelle s'écarte (ADR-0014).
