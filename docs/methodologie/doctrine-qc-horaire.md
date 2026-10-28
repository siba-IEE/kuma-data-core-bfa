# Note méthodologique - doctrine de contrôle qualité algorithmique des séries horaires

> Note méthodologique sur la validation horaire.
>
> Objet : fixer la **doctrine versionnée** de contrôle qualité (QC)
> algorithmique des séries horaires stockées, qui attribue
> automatiquement un statut éditorial et un niveau de confiance à
> chaque heure.
>
> **Statut des seuils numériques** : les limites de plausibilité et les
> tolérances de comparaison sont **sourcées verbatim** du document
> *BSRN Global Network recommended QC tests V2.0* (Long & Dutton, source
> officielle BSRN/AWI). S₀ vaut 1 366,1 W/m², valeur par défaut de
> pvlib retenue par le code (§3). Les seuils des tests temporels
> (§4.4), hors du jeu BSRN canonique, restent à fixer.
>
> **Hypothèses structurantes** : stockage `TIMESTAMPTZ` UTC ;
> discriminant de granularité côté `series_metadonnees`.

## 1. Contexte et objet

Une heure non stockée est relayée en direct depuis NASA POWER, non
validée, sous le statut `passe_plat_non_valide`. La présente doctrine
fait passer l'horaire stocké au statut de **donnée validée
éditorialement en confiance B**.

Au Burkina Faso, l'horaire stocké couvre les cinq points pilotes sur
2021-2025 : GHI, DNI, DHI et température de NASA POWER (ADR-0014), GHI,
DNI, DHI et GHI par ciel clair de CAMS Radiation (ADR-0023), soit
1 752 960 heures. La volumétrie interdit la relecture humaine qui
valide les séries basse fréquence : la validation est
**algorithmique**, d'où une doctrine explicite, versionnée et
traçable.

Cette note fixe : les familles de tests QC, leur ordre d'application,
les pré-requis géométriques, et la règle d'attribution automatique du
statut éditorial et du niveau de confiance.

## 2. Principe directeur et plafond de confiance

- Le QC algorithmique **automatise la plausibilité physique**, il ne
  constitue **pas** une vérité terrain. Plafond de confiance **B**. Le
  niveau **A** reste réservé à la mesure sol
  ([`calage-terrain-solaire.md`](calage-terrain-solaire.md)) : aucun test
  QC ne produit un A.
- La donnée horaire QC-passée prend le statut DB **`valide_auto`** (déjà
  présent dans le CHECK `statut` des tables `mesures_ressource*`, aucun
  nouvel enum requis) et `niveau_confiance_derive = 'B'`. Côté surface
  API, le service horaire sert la donnée stockée validée ;
  `passe_plat_non_valide` n'est plus émis pour la plage couverte.
- La doctrine est **versionnée** (`v1`, `v2`…). Toute exécution QC trace
  la version de doctrine appliquée, pour que le verdict de chaque point
  soit reproductible et auditable.

## 3. Pré-requis géométriques

Les tests radiatifs reposent sur la position solaire, d'où l'ancrage
**UTC tz-aware** de la colonne instant. Conventions
alignées verbatim sur BSRN (Long & Dutton) :

- **Angle zénithal solaire SZA**, et **μ₀ = cos(SZA)**, calculés par
  `pvlib` (`solarposition.get_solarposition`) à partir de (latitude,
  longitude, instant **UTC**). **Convention BSRN** : si SZA > 90°, μ₀
  est forcé à **0,0** dans les formules.
- Une valeur moyenne de l'heure se juge au **milieu de l'heure** : NASA
  POWER date chaque valeur du début de l'heure qu'elle moyenne ; CAMS
  Radiation sert la période `HH:00/HH+1:00` et l'ingestion la date de même
  au début de l'heure ; la géométrie est donc calculée 30 min après
  l'instant stocké (ADR-0014, ADR-0023).
- **Constante solaire ajustée distance Terre-Soleil** :
  **Sₐ = S₀ / AU²** (S₀ = constante solaire à distance moyenne Terre-
  Soleil ; AU = distance Terre-Soleil en unités astronomiques). Obtenue
  via `pvlib.irradiance.get_extra_radiation` (S₀ = 1 366,1 W/m², défaut
  pvlib, `S0_W_PAR_M2` dans `services/qualite/qc_horaire.py`).
- **Somme SW** (pour la fermeture, §4.2) :
  **Sum SW = DHI + DNI · μ₀**.

Le QC distingue **jour** (μ₀ > 0) et **nuit** (SZA > 90° → μ₀ = 0), les
bornes radiatives différant fondamentalement entre les deux régimes.

## 4. Familles de tests QC

Quatre familles, appliquées dans l'ordre, du plus dur (rejet physique)
au plus contextuel (cohérence, aberration).

### 4.1 Plausibilité physique par variable (limites BSRN, verbatim)

Tests ponctuels, une variable à la fois, à deux niveaux BSRN :
**« physiquement possible »** (violation = donnée impossible, rejet) et
**« extrêmement rare »** (violation = donnée suspecte, flag sans rejet).
Bornes reproduites verbatim de BSRN V2.0 (Long & Dutton). Unités W/m² ;
μ₀ = 0 si SZA > 90°.

| Variable | Niveau | Min | Max |
|---|---|---|---|
| **GHI** (Global SWdn) | phys. possible | −4 | Sₐ · 1,5 · μ₀^1.2 + 100 |
| GHI | extrêm. rare | −2 | Sₐ · 1,2 · μ₀^1.2 + 50 |
| **DHI** (Diffuse SW) | phys. possible | −4 | Sₐ · 0,95 · μ₀^1.2 + 50 |
| DHI | extrêm. rare | −2 | Sₐ · 0,75 · μ₀^1.2 + 30 |
| **DNI** (Direct Normal) | phys. possible | −4 | Sₐ |
| DNI | extrêm. rare | −2 | Sₐ · 0,95 · μ₀^0.2 + 10 |

Le document BSRN définit aussi SWup et le longwave (LWdn/LWup) : **hors
périmètre**, aucun flux de pyrgéomètre ni d'albédomètre horaire n'est
ingéré (l'albédo de surface est une grandeur brute journalière, pas un
flux horaire).

- **Régime nocturne** (SZA > 90°, μ₀ = 0) : les bornes hautes se
  réduisent à l'offset additif (GHI ≤ 100, DHI ≤ 50, DNI ≤ Sₐ). Une
  sentinelle `-999` reste traitée comme **lacune** (§4.4), pas comme un
  zéro physique.
- **T2M** : la plage de validité BSRN de la température de l'air est
  **170 K < Tₐ < 350 K** ; le code applique -90 à 60 °C. Les bornes du
  contrat d'ingestion, plus serrées (-5 à 55 °C, ADR-0014), arrêtent
  l'ingestion en amont. **RH2M ∈ [0, 100] %.**
- **KT** non défini la nuit : `null` légitime (cohérent avec le
  passe-plat). Aucune série horaire d'humidité ni d'indice de clarté
  n'est stockée au Burkina Faso.

### 4.2 Relation de fermeture radiative (comparaison Global / Somme SW)

Test BSRN « Ratio of Global over Sum SW », verbatim, avec
Sum SW = DHI + DNI · μ₀ :

> (Global) / (Sum SW) à **±8 %** de 1,0 pour **SZA < 75°**,
> Sum SW > 50 W/m².
> (Global) / (Sum SW) à **±15 %** de 1,0 pour **75° < SZA < 93°**,
> Sum SW > 50 W/m².
> Pour Sum SW < 50 W/m², **test non applicable**.

Test conditionnel : non appliqué si une composante est lacune.

### 4.3 Cohérence inter-variables (ratio diffus, BSRN verbatim)

Test BSRN « Diffuse Ratio » :

> (DHI) / (GHI) < **1,05** pour **SZA < 75°**, GHI > 50 W/m².
> (DHI) / (GHI) < **1,10** pour **75° < SZA < 93°**, GHI > 50 W/m².
> Pour GHI < 50 W/m², **test non applicable**.

- **Indice de clarté** : `qc_horaire.py` ne teste pas Kt = GHI / I₀ₕ sur
  le GHI. Il borne seulement une série `kt` stockée, de 0 à 1,2 (marge
  d'« enhancement » nuageux ponctuel), et le Burkina Faso n'en a pas.

### 4.4 Détection d'aberrations temporelles (complément hors BSRN V2.0)

Ces tests ne figurent **pas** dans le jeu BSRN V2.0 (qui est ponctuel :
limites + comparaisons). Ils constituent un **complément Kuma** dont les
seuils restent à fixer (configurables, documentés) :

- **Spikes** : variation horaire physiquement improbable entre deux pas
  consécutifs *[seuil à fixer]*.
- **Valeurs gelées (persistance)** : N heures consécutives identiques en
  plein jour *[N à fixer]*.
- **Lacunes** : sentinelles `-999` et trous temporels : marquées
  **manquantes**, **non imputées** en v1.

Le QC v1 n'applique encore ni les pics ni les valeurs gelées
(ADR-0014). Long & Shi 2008 (QCRad) ajoute au-dessus du socle BSRN des
**limites configurables d'après la climatologie du site** ; piste
d'enrichissement ultérieure.

## 5. Attribution automatique du statut et du niveau

Attribution **par point horaire** (chaque ligne porte son verdict) :

| Issue des tests | Statut DB | Niveau | Trace |
|---|---|---|---|
| Tous les tests durs passés | `valide_auto` | `B` | version doctrine |
| Échec « extrêmement rare » seul | `valide_auto` + flag | `B` ou `C` *[à arbitrer]* | test flaggé en `commentaire_editorial` |
| Échec « physiquement impossible » | **non `valide_auto`** *(statut à arbitrer : `brut` conservé vs `deprecie`)* | - | test échoué tracé |

- **Décision de conception à acter** : les points qui échouent un test
  dur sont-ils **conservés flaggés** (cohérent avec le versioning non
  destructif `valide_du`/`valide_au`) ou **exclus** ? Recommandation :
  conservation flaggée, jamais de suppression silencieuse.
- Le niveau `B` est uniforme ; le QC ne crée pas de `A`.
- **Tranché pour le Burkina Faso (ADR-0014)** : une ligne rejetée reste
  `brut`, conservée avec son motif ; une ligne seulement signalée reste
  `valide_auto` en niveau `B`.
- **GHI par ciel clair (ADR-0023)** : faute de composantes associées, il ne
  passe que la plausibilité du GHI (§ 4.1), sans fermeture ni ratio diffus.
  Son commentaire `[QC v1] valide_auto` est le même que celui d'une ligne
  passée par tous les tests : la note publique de la série le précise.

## 6. Versionnement et traçabilité

- La doctrine (présente note + module service `services/qualite/`) est un
  **artefact versionné**. La version (`vX`) est inscrite dans chaque
  exécution.
- Chaque batch QC produit un **rapport traçable** : version de doctrine,
  date d'exécution, répartition des verdicts (% `valide_auto`, %
  flaggés, % impossibles) par variable et par localité.

## 7. Limitations et dettes

- Le QC ne lève pas le plafond de confiance B (pas de vérité terrain ;
  A = régime terrain).
- Les lacunes ne sont pas imputées en v1 (marquées manquantes).
  L'imputation est une piste ultérieure.
- Les limites BSRN sont fixées « pour accommoder toutes les latitudes et
  tous les régimes climatiques du programme BSRN » et « peuvent être
  affinées pour une latitude/climat spécifique » (Long & Dutton). Des
  limites tirées de la climatologie sahélienne et soudanienne du pays
  (§4.4) sont une piste ultérieure. Cohérent plafond B.

**À acter** : les seuils des tests temporels (§4.4, complément hors
BSRN). Les coefficients BSRN (§4.1-§4.3) et S₀ (§3) sont fixés.

## 8. Références

- Long C.N., Dutton E.G. *BSRN Global Network recommended QC tests,
  V2.0*. Baseline Surface Radiation Network (BSRN), AWI / WCRP. **Source
  verbatim des limites §4.1-§4.3** :
  `https://bsrn.awi.de/fileadmin/user_upload/bsrn.awi.de/Publications/BSRN_recommended_QC_tests_V2.pdf`
- Long C.N., Shi Y. 2008. *An Automated Quality Assessment and Control
  Algorithm for Surface Radiation Measurements*. The Open Atmospheric
  Science Journal **2**, 23-37 (PNNL / ARM ; algorithme QCRad
  encapsulant les limites BSRN + limites configurables par climatologie).
- pvlib - `solarposition`, `irradiance.get_extra_radiation` (SZA, μ₀,
  Sₐ).
- Cohérence avec la chaîne radiative déjà documentée
  ([`grandeurs-parametrables.md`](grandeurs-parametrables.md) : Perez 1990,
  Erbs 1982).

## 9. Évolution du document

| Date | Modifications |
|---|---|
| 2026-06-14 | Cadre algorithmique des 4 familles de tests + attribution ; coefficients BSRN à sourcer verbatim |
| 2026-06-14 | Limites §4.1-§4.3 remplacées par les valeurs verbatim BSRN V2.0 (Long & Dutton) ; restent à acter : S₀ (§3) et tests temporels (§4.4) |
| 2026-10-15 | Géométrie au milieu de l'heure pour les moyennes horaires (§3) ; arbitrages du §5 tranchés pour le Burkina Faso (ADR-0014) |
| 2026-10-28 | Contexte ramené aux séries horaires du Burkina Faso (§1) ; S₀ fixé à la valeur du code (§3) ; bornes de température appliquées (§4.1) |
