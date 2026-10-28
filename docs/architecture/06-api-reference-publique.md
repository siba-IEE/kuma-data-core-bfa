# Référence de l'API Kuma Data Core

> Référence technique de l'API, dérivée du code (routeurs, schémas
> Pydantic, règles de confiance) et des seeds. Le catalogue et les
> volumes se découvrent via l'API elle-même (listing `/v1/series`, doc
> interactive `/docs`), pas via des compteurs figés dans ce document :
> ils dépendent du mode d'ingestion du déploiement.
>
> Aucun secret n'est exposé : les clés API, URL internes et chemins
> d'infrastructure sont décrits en termes de mécanismes, jamais en
> valeurs.

## 1. Vue d'ensemble de l'API

Kuma Data Core expose une API HTTP qui sert de source de vérité aux
outils Kuma (média éditorial, scripts de synchronisation, Solar Bridge,
autres outils dérivés) et, sur le profil serveur public (édition
publiée, ADR-0003), aux consommateurs tiers munis d'une clé
self-service. Elle n'est pas destinée à un accès anonyme : tous les
endpoints métier exigent une clé API (administrative ou self-service).

| Aspect | Choix |
|---|---|
| Style | REST, JSON par défaut, CSV optionnel sur `series/{code}`, `grandeurs/*` (F2) et `horaire/*` |
| Framework | FastAPI (Python 3.12) |
| Base de données | PostgreSQL 16 |
| Versioning | Préfixe `/v1`. Contrat stable une fois publié, breaking changes documentés par décision d'architecture |
| Authentification | Header `Authorization: Bearer <cle>` |
| Format d'erreur | Enveloppe normalisée `{"erreur": {"code": ..., "message": ..., "details": ...}}` |
| Documentation interactive | OpenAPI à `/docs` et `/redoc` (dev/intégration uniquement, désactivée en production par validateur de configuration) |
| Schéma OpenAPI brut | `/openapi.json` (mêmes conditions) |

Base URL : les exemples utilisent l'hôte placeholder `<base-url>`.
Toutes les routes métier vivent sous `/v1/...`.

Structure des routes :

```
/v1/health                                        santé publique (non authentifié)
/v1/health/db                                     santé infrastructure (authentifié)
/v1/edition                                       édition publiée servie (non authentifié)
/v1/cles                POST                      émission self-service d'une clé (non authentifié)
/v1/cles/{prefixe}      DELETE                    révocation d'une clé (administrateur)
/v1/licence/bail        POST                      bail signé d'usage de SolClim-3 (clé porteuse d'une licence)
/v1/contributions/{uid} POST                      dépôt de la fiche d'une étude SolClim-3 (clé porteuse d'une licence)
/v1/contributions/{uid}/retrait POST              retrait de cette fiche (clé)
/v1/series                                        catalogue des séries
/v1/series/{code_serie}                           détail d'une série + ses mesures
/v1/localites                                     référentiel géographique
/v1/localites/resolution                          localité qui échantillonne un point
/v1/localites/{code}                              détail d'une localité
/v1/grandeurs/<code>                              11 routes grandeurs (F1 calculées, F2 paramétrables)
/v1/horaire/{localite}/{grandeur}                 horaire stocké validé, repli passe-plat
/v1/horaire/{localite}/{grandeur}/disponibilite   plage temporelle disponible
/v1/calage                                        référentiels de calage publiés
/v1/calage/{localite}/{grandeur}                  détail d'un référentiel de calage
/v1/etudes/capsule                                ressource d'étude au point
```

29 endpoints en tout : santé (2), édition (1), clés (2), licence (1),
contributions (2), séries (2), localités (3), grandeurs (11), horaire (2),
calage (2), études (1). Le préfixe `/v1/grandeurs/` n'agrège pas
dynamiquement, il expose 11 routes distinctes (détail en 3.7).

## 2. Authentification et accès

### 2.1 Mécanisme

Toute requête autre que les endpoints publics (`GET /v1/health`,
`GET /v1/edition`, `POST /v1/cles`) doit présenter le header HTTP :

```
Authorization: Bearer <cle>
```

La validation se fait en 4 étapes (`api/dependencies.py:verifier_cle_api`) :

1. Présence du header, sinon `401 AUTH_HEADER_MANQUANT`
2. Préfixe `Bearer `, sinon `401 AUTH_FORMAT_INVALIDE`
3. Comparaison aux clés d'environnement (administrative, Bridge)
4. À défaut, et si une base de service est configurée : recherche de
   l'empreinte SHA-256 de la clé parmi les clés self-service actives ;
   sinon `401 AUTH_CLE_INVALIDE`

Les clés self-service actives sont soumises à un quota journalier
(section 3.11) quand le rate limiting est activé ; les clés
d'environnement ne sont jamais limitées.

### 2.2 Modèle d'accès

Deux régimes coexistent :

- **Régime local / interne** (historique) : aucun compte, aucun flux
  d'inscription. Les clés sont attribuées par l'éditeur de Kuma Data
  Core aux consommateurs autorisés, en variables d'environnement.
- **Régime serveur public** (édition publiée, ADR-0003) : inscription
  self-service légère via `POST /v1/cles` (une adresse de contact
  suffit). La clé est gratuite, montrée une seule fois, révocable, et
  porte un quota journalier. Les données servies restent publiques : la
  clé n'est pas une barrière mais une signature (traçabilité, limitation
  par consommateur, révocation ciblée).

### 2.3 Garanties techniques sans exposition de secret

- Les clés sont stockées en `SecretStr` (jamais loggées en clair).
- Les logs d'erreur ne contiennent aucune PII ni clé.
- Le filet de sécurité `handler_exception_generique` retourne un 500
  normalisé sans fuite de stack trace, de chemin interne ni de version
  de dépendance.
- L'OpenAPI est désactivée en production par validateur de
  configuration (toute incohérence bloque le démarrage de
  l'application).
- L'origine CORS est restreinte à une liste close. Aucune origine
  publique n'est autorisée par défaut.

## 3. Endpoints (détail)

### 3.1 `GET /v1/health` : santé publique

- Auth : non requise
- Réponse 200 :

```json
{
  "statut": "operationnel",
  "edition": "edition_AAAAMMJJ"
}
```

- Indique que l'API répond. `edition` est lu en best-effort (identifiant
  de l'édition publiée servie, `null` hors régime édition ou si la
  lecture échoue) : le health ne dépend de rien et ne renvoie jamais de
  5xx. Le détail de l'édition vit sur `GET /v1/edition` (3.10).
- Ni la version ni l'environnement ne figurent dans cette réponse non
  authentifiée : ils sont servis par `GET /v1/health/db` (3.2).

### 3.2 `GET /v1/health/db` : santé détaillée

- Auth : Bearer requise
- Réponse 200 :

```json
{
  "statut": "operationnel",
  "version": "<x.y.z>",
  "environnement": "<dev|integration|prod>",
  "composants": [{"nom": "postgresql", "statut": "operationnel"}]
}
```

- Erreurs : `503 INFRASTRUCTURE_BASE_INDISPONIBLE` si la base ne répond
  pas (avec détail `composants`).
- La vérification Redis n'est pas branchée dans cet endpoint (la forme
  de réponse est prête à recevoir un second composant). Redis est
  consommé par les compteurs de quota (3.11) en mode fail-open : son
  indisponibilité n'affecte pas la santé de l'API.

### 3.3 `GET /v1/series` : listing des séries

- Auth : Bearer requise
- Pagination : offset-based, `limit` défaut 100, max 1000.
- Tri : `ORDER BY code ASC` (stable).
- Paramètres query :

| Paramètre | Type | Défaut | Description |
|---|---|---|---|
| `localite` | `str` | | Filtre par code localité (ex. `bfa_com_ouagadougou`) |
| `grandeur` | `str` | | Filtre par code grandeur (ex. `ghi`, `fraction_diffuse`) |
| `source` | `str` | | Filtre par code source (ex. `nasa_power`, `kuma_calculs`) |
| `actif` | `bool` | `true` | `false` renvoie seulement les séries désactivées (soft-deleted) |
| `limit` | `int [1, 1000]` | `100` | Pagination |
| `offset` | `int >= 0` | `0` | Pagination |

- Réponse 200 (envelope paginée), pour
  `?localite=bfa_com_ouagadougou&grandeur=ghi&source=nasa_power` ; des trois
  séries (horaire, journalière, mensuelle), seule la journalière est
  reproduite :

```json
{
  "items": [
    {
      "id": 36594,
      "code": "nasa_power_ghi_journalier_bfa_com_ouagadougou",
      "libelle": "GHI journalier NASA POWER, Ouagadougou (2005-2025)",
      "localite_id": 205,
      "localite_code": "bfa_com_ouagadougou",
      "localite_nom": "Ouagadougou",
      "localite_iso3": "BFA",
      "grandeur_code": "ghi",
      "grandeur_label": "Irradiation globale horizontale",
      "grandeur_unit": "kWh/m²/jour",
      "source_id": 1,
      "source_code": "nasa_power",
      "source_label": "NASA POWER - Prediction Of Worldwide Energy Resources : Solar and Meteorological Data Archive",
      "source_url": "https://power.larc.nasa.gov/",
      "periode_debut": "2005-01-01",
      "periode_fin": "2025-12-31",
      "methode_collecte": "modele_satellitaire",
      "notes_fr": "Rayonnement global horizontal (GHI) : série journalière NASA POWER (total du jour, en kWh/m²), 2005-2025, maille de 1° de NASA POWER (CERES SYN1deg). Lot « communes », stockage dense (ADR-0017). Confiance B. ...",
      "created_at": "2026-10-27T16:18:20.111566Z",
      "updated_at": "2026-10-27T16:18:20.111566Z",
      "actif": true
    }
  ],
  "total": 3,
  "limit": 100,
  "offset": 0
}
```

- 21 champs par item, dénormalisés (localité, grandeur, source) pour
  éviter au consommateur de chaîner les appels. Le champ `total` reflète
  le nombre de séries matchant les filtres dans le déploiement interrogé.
- La granularité n'est ni un filtre ni un champ du listing : elle se lit
  dans le code de la série (`_horaire_`, `_journalier_`, `_mensuel_`, voir
  5.4). `grandeur_unit` est l'unité de la grandeur au référentiel, sauf
  pour les séries horaires, où c'est celle des valeurs servies par
  `/v1/horaire` (Wh/m² sur l'heure pour le rayonnement, 3.8).
- Note de stabilité : le contrat de cet endpoint est figé. Les
  renommages publics `cree_le` vers `created_at`, `modifie_le` vers
  `updated_at`, `note_publique` vers `notes_fr`, `sources.titre`
  vers `source_label` sont assumés et ne dérivent pas du nom de colonne DB.
  Seul le sens de `grandeur_unit` a changé, pour les séries horaires
  (version 0.20.0).

### 3.4 `GET /v1/series/{code_serie}` : détail d'une série + mesures

- Auth : Bearer requise
- Paramètres path : `code_serie` (convention de nommage en 5.4)
- Paramètres query :

| Paramètre | Type | Défaut | Description |
|---|---|---|---|
| `from` | `YYYY-MM-DD` ou `YYYY-MM` | | Borne basse temporelle inclusive |
| `to` | `YYYY-MM-DD` ou `YYYY-MM` | | Borne haute temporelle inclusive |
| `format` | `json` ou `csv` | `json` | Format de réponse |
| `limit` | `int [1, 10000]` | `1000` | Pagination des mesures |
| `offset` | `int >= 0` | `0` | Pagination |

- Résolution de la table-cible (`api/services/serie_lecture.py`) : une
  série `kuma_calculs` lit `grandeurs_metier` (vue
  `v_grandeurs_metier_courantes`) ; les autres sont routées par leur
  granularité : journalier par la vue `v_mesures_journalieres`, qui réunit
  `mesures_ressource` et le stockage dense de l'ADR-0017, mensuel par
  `mesures_ressource_mensuelles`. Une série horaire n'est pas servie ici :
  404 `RESSOURCE_INTROUVABLE`, l'horaire passe par `/v1/horaire` (3.8).

- Réponse 200 JSON, exemple série journalière NASA POWER
  (`?from=2024-06-15&to=2024-06-16`) :

```json
{
  "id": 36594,
  "code": "nasa_power_ghi_journalier_bfa_com_ouagadougou",
  "libelle": "GHI journalier NASA POWER, Ouagadougou (2005-2025)",
  "grandeur_code": "ghi",
  "grandeur_unit": "kWh/m²/jour",
  "source_code": "nasa_power",
  "periode_debut": "2005-01-01",
  "periode_fin": "2025-12-31",
  "unite_code": "kwh_par_m2_jour",
  "mesures": [
    {
      "type": "journalier",
      "instant_mesure": "2024-06-15",
      "valeur": 5.2207,
      "niveau_confiance_derive": "B",
      "niveau_confiance_override": null,
      "niveau_effectif": "B",
      "statut": "brut"
    },
    {
      "type": "journalier",
      "instant_mesure": "2024-06-16",
      "valeur": 5.7499,
      "niveau_confiance_derive": "B",
      "niveau_confiance_override": null,
      "niveau_effectif": "B",
      "statut": "brut"
    }
  ]
}
```

(Les champs d'en-tête dénormalisés sont identiques à ceux du listing,
omis ici pour la lisibilité.)

- Trois formes de mesures discriminées (champ `type`) :

  - `journalier` : `instant_mesure: date`, `valeur: float`
  - `mensuel` : `annee: int`, `mois: int`, `valeur: float`
  - `grandeur_metier` : `periode_type` (`mensuel`, `annuel`, `statique`),
    `annee_debut`, `annee_fin`, `mois` (nullable), `version_formule: int`,
    `valeur: float`

  Tous portent en plus `niveau_confiance_derive`,
  `niveau_confiance_override`, `niveau_effectif` (résolu) et `statut`
  (voir 5.2 et 5.3).

- Format CSV (`format=csv`) : header générique `code_serie, type, annee,
  mois, instant_mesure, periode_type, annee_debut, annee_fin,
  version_formule, valeur, niveau_effectif, statut`, une ligne par mesure.

- Erreur 404 : `RESSOURCE_SERIE_INCONNUE` si le code de série n'existe pas.

### 3.5 `GET /v1/localites` : référentiel géographique (listing)

- Auth : Bearer requise
- Pagination : offset-based, `limit` défaut 100, max 1000.
- Tri : `ORDER BY code ASC`.
- Paramètres query :

| Paramètre | Type | Défaut | Description |
|---|---|---|---|
| `pays_iso3` | `str` | | Filtre ISO 3166-1 alpha-3 (ex. `BFA`) |
| `type_localite` | `str` | | `continent`, `region_supranationale`, `pays`, `region_administrative`, `prefecture`, `commune`, `site` |
| `parent_code` | `str` | | Filtre par code de la localité parente |
| `actif` | `bool` | `true` | `false` renvoie seulement les localités désactivées (soft-deleted) |
| `limit` | `int [1, 1000]` | `100` | Pagination |
| `offset` | `int >= 0` | `0` | Pagination |

Au Burkina Faso, `region_administrative` porte les 17 régions, `prefecture`
les 47 provinces et `commune` les 350 départements et la commune de
Ouagadougou (ADR-0007).

- Réponse 200, pour `?parent_code=bfa_prov_kadiogo&limit=1` (les sept
  localités de la province du Kadiogo, dont la première est reproduite) :

```json
{
  "items": [
    {
      "id": 205,
      "code": "bfa_com_ouagadougou",
      "nom": "Ouagadougou",
      "type_localite": "commune",
      "parent_id": 32,
      "parent_code": "bfa_prov_kadiogo",
      "pays_iso3": "BFA",
      "latitude": 12.35,
      "longitude": -1.51666667,
      "altitude_metres": null,
      "population_estimee": 2415266,
      "annee_population": 2019,
      "fuseau_horaire": "Africa/Ouagadougou",
      "created_at": "2026-10-15T16:19:23.991092Z",
      "updated_at": "2026-10-15T16:19:23.991092Z",
      "actif": true
    }
  ],
  "total": 7,
  "limit": 1,
  "offset": 0
}
```

- 16 champs par item. `parent_code` dénormalisé via self-JOIN : un appel
  suffit pour reconstruire la hiérarchie ligne par ligne. La hiérarchie
  récursive complète (chaîne `pays > région > province > département`)
  n'est pas exposée v1.

### 3.6 `GET /v1/localites/{code}` : détail d'une localité

- Auth : Bearer requise
- Paramètres path : `code` (slug ASCII pour le continent, code ISO pour le
  pays, `bfa_...` pour les entités administratives, voir 5.5).
- Réponse 200 : identique à un item du listing (16 champs).
- Erreur 404 : `RESSOURCE_LOCALITE_INCONNUE`.
- Pas de filtre `actif` sur le détail : qui appelle un code précis assume
  la ressource ciblée.

### 3.7 Les 11 routes `GET /v1/grandeurs/<code>`

Le préfixe `/v1/grandeurs/` expose 11 routes : 6 grandeurs F2
paramétrables (calcul à la volée piloté par des paramètres physiques
utilisateur) et 5 routes F1 calculées à la volée (dérivations sans
paramètre libre, path-based).

| Route | Famille | Sortie |
|---|---|---|
| `GET /v1/grandeurs/poa_parametrable` | F2 | journalier |
| `GET /v1/grandeurs/poa_bifacial` | F2 | journalier |
| `GET /v1/grandeurs/productible_correction_thermique` | F2 | journalier |
| `GET /v1/grandeurs/productible_pr_fourni` | F2 | journalier ou mensuel |
| `GET /v1/grandeurs/energie_utile_ecs` | F2 | journalier |
| `GET /v1/grandeurs/degre_jour_climatisation` | F2 | mensuel |
| `GET /v1/grandeurs/ghi_exceedance/{code_localite}` | F1 | fiche P50/P90 |
| `GET /v1/grandeurs/taux_salissure_proxy/{code_serie_source}` | F1 | journalier |
| `GET /v1/grandeurs/pr_realiste/{code_serie_source}` | F1 | journalier + mensuel |
| `GET /v1/grandeurs/incertitude_inter_source/{code_localite}` | F1 | fiche |
| `GET /v1/grandeurs/incertitude_inter_source` | F1 | collection paginée |

#### 3.7.1 Modèles physiques (F2)

| Route | Modèle de référence |
|---|---|
| `poa_parametrable` | Perez 1990 si DNI+DHI disponibles, sinon fallback Liu-Jordan isotrope (décomposition Erbs 1982) |
| `poa_bifacial` | Infinite-sheds row-aware (pvlib), face arrière : DNI+DHI obligatoires, pas de fallback |
| `productible_correction_thermique` | NOCT simple (Ross 1980) |
| `productible_pr_fourni` | PR brut (Marion 2005) ou PR_T corrigé température (Dierauf 2013) |
| `energie_utile_ecs` | Hottel-Whillier-Bliss bord-capteur (η = η₀ − a₁·ΔT/G − a₂·ΔT²/G) |
| `degre_jour_climatisation` | Moyenne journalière (défaut) ou intégration horaire (Erbs 1983), agrégation mensuelle |

#### 3.7.2 Paramètres communs des routes F2

| Paramètre | Type | Obligatoire | Description |
|---|---|---|---|
| `code_serie_source` | `str (1..80)` | oui | Code d'une série F1 source (ex. `nasa_power_ghi_journalier_bfa_com_ouagadougou`) |
| `periode_debut` | `YYYY-MM-DD` | oui | Borne basse inclusive |
| `periode_fin` | `YYYY-MM-DD` | oui | Borne haute inclusive, `>= periode_debut` |
| `format` | `json` / `csv` | non | `json` par défaut |

#### 3.7.3 Paramètres spécifiques par route F2

| Route | Paramètres techniques |
|---|---|
| `poa_parametrable` | `inclinaison_deg` `[0..90]`, `orientation_deg` `[0..360[` (0=N, 90=E, 180=S, 270=O), `albedo_sol` `[0..1]` (défaut 0.2), `methode` `moyenne_journaliere` (défaut) ou `integration_horaire` |
| `poa_bifacial` | `inclinaison_deg` `[0..90]`, `orientation_deg` `[0..360[`, `gcr` `]0..1]`, `hauteur_m > 0`, `pitch_m > 0`, `bifacialite` `[0..1]` (défaut 0.8), `albedo_sol` `[0..1]` (repli si série `albedo_surface` absente), `methode` |
| `productible_correction_thermique` | `noct_degc` `[40..50]`, `coeff_temp_pourcent_par_degc` `[-0.6..-0.1]`, `puissance_stc_wc > 0`, `methode` |
| `productible_pr_fourni` | `pr_fourni` `[0..1]`, `correction` `aucune` ou `temperature`, `puissance_stc_wc > 0`, `noct_degc` et `coeff_temp_pourcent_par_degc` (obligatoires si `correction=temperature`), `methode` |
| `energie_utile_ecs` | `rendement_optique_eta0` `[0.5..0.9]`, `pertes_lineaires_a1` `[1..8]` W/(m²·K), `pertes_quadratiques_a2` `[0..0.05]` W/(m²·K²), `temperature_fluide_entree_degc` `[10..90]`, `methode` |
| `degre_jour_climatisation` | `base_temperature_degc` `[10..35]`, `methode` |

`methode=integration_horaire` exige une série source de granularité
`horaire` (plus les compagnes horaires requises) ; elle lève le biais de
moyennage journalier. Les heures sont sommées par jour UTC : les résultats
restent journaliers (mensuels pour les degrés-jours). Une série non horaire
avec ce mode renvoie `400 VALIDATION_VALEUR_INVALIDE`.

En `moyenne_journaliere`, `poa_parametrable` et `poa_bifacial` projettent le
DNI du jour avec la géométrie du midi solaire, ce qui surestime le POA : sur
un plan horizontal, en 2024, de 6,2 % avec NASA POWER au Kadiogo comme à Fô,
de 18,8 % au Kadiogo et 18,5 % à Fô avec CAMS Radiation ; autant ou plus sur
un plan incliné (ADR-0013, ADR-0020). La réponse le signale par son champ
`limite` (§3.7.5). Le mode horaire n'existe qu'aux cinq points pilotes, depuis une série horaire NASA
POWER ou CAMS Radiation ; CAMS ne sert pas de température, et les routes qui
demandent une compagne T2M horaire partent de la série NASA POWER (ADR-0023).

#### 3.7.4 Pattern auto-compagne (F2)

Plusieurs routes F2 ont besoin de plusieurs séries d'entrée. Le routeur
cherche automatiquement les séries compagnes sur la même `localite_id` +
`source_id` + granularité + fenêtre temporelle. Le consommateur fournit
uniquement la série principale.

| Route | Série principale | Compagnes auto | Si compagne manquante |
|---|---|---|---|
| `poa_parametrable` | `grandeur_code=ghi` | DNI, DHI | Fallback Liu-Jordan (précision dégradée en ciel partiellement couvert) |
| `poa_bifacial` | `ghi` | DNI, DHI (albédo via `albedo_surface`, sinon `albedo_sol`) | `400 INCOMPATIBILITE_SOURCE_GRANDEUR` (pas de fallback) |
| `productible_correction_thermique` | `ghi` | T2M | `400 INCOMPATIBILITE_SOURCE_GRANDEUR` |
| `productible_pr_fourni` (`correction=aucune`) | `ghi` | | |
| `productible_pr_fourni` (`correction=temperature`) | `ghi` | T2M | `400 INCOMPATIBILITE_SOURCE_GRANDEUR` |
| `energie_utile_ecs` | `ghi` | T2M | `400 INCOMPATIBILITE_SOURCE_GRANDEUR` |
| `degre_jour_climatisation` | `t2m` | aucune | |

Aucune série `albedo_surface` n'existe au Burkina Faso : `poa_bifacial` y
applique toujours `albedo_sol`.

Pour `productible_pr_fourni`, la table-cible est dispatchée selon la
source : une série mensuelle n'accepte que `correction=aucune` ; une série
calculée Kuma (`kuma_calculs`) est rejetée en
`400 INCOMPATIBILITE_SOURCE_GRANDEUR` (une F1 calculée n'est pas admissible
comme source brute d'un calcul F2).

#### 3.7.5 Format de réponse F2 (JSON)

Exemple : `poa_parametrable` à Ouagadougou le 1er janvier 2024, plan à 15°
plein sud, depuis le GHI journalier de NASA POWER (`limite` abrégé) :

```json
{
  "code_grandeur": "poa_parametrable",
  "code_serie_source": "nasa_power_ghi_journalier_bfa_com_ouagadougou",
  "parametres_appliques": {
    "inclinaison_deg": 15.0,
    "orientation_deg": 180.0,
    "albedo_sol": 0.2,
    "methode": "moyenne_journaliere"
  },
  "resultats": [
    {
      "granularite": "journalier",
      "instant": "2024-01-01",
      "valeur": 7.636218686199406,
      "unite": "kWh/m²/jour",
      "niveau_confiance": "B"
    }
  ],
  "limite": "Méthode journalière : le direct du jour est projeté avec la géométrie du midi solaire, où le soleil est le plus haut, ce qui surestime le POA. Sur un plan horizontal, le direct et le diffus ainsi projetés s'écartent ici de +12,9 % du GHI de la série. ..."
}
```

Résultats discriminés par `granularite` : `journalier` (`instant: date`)
ou `mensuel` (`instant` au format `YYYY-MM`). `degre_jour_climatisation`
sort en mensuel. Le niveau de confiance des sorties F2 est `B`.

Le champ `limite` vaut `null`, sauf pour `poa_parametrable` et
`poa_bifacial` en `moyenne_journaliere` : il dit alors le biais du midi
solaire et donne l'écart au GHI, sur un plan horizontal, des jours calculés
(« s'écartent ici de +12,9 % du GHI de la série » dans l'exemple).

Format CSV (`format=csv`) : header `granularite, instant, valeur, unite,
niveau_confiance`. Le CSV ne porte pas le champ `limite`.

#### 3.7.6 Routes F1 calculées à la volée

Ces routes dérivent une grandeur éditoriale à partir de séries déjà
ingérées ou déjà matérialisées, sans paramètre physique libre. Toutes
portent un champ `limite` : un avertissement éditorial explicite sur la
portée du résultat.

`ghi_exceedance/{code_localite}` : exceedance inter-annuelle P50/P90 de
l'irradiation annuelle, dérivée des années 1991-2020 de la série GHI
mensuelle NASA POWER de la localité (1991-2025 aux 398 localités). P50 =
médiane, P90 = percentile 10 (scénario conservateur, P90 < P50 par
construction). Réponse : `code_serie_source`, `periode`, `p50`, `p90` en
kWh/m²/an, `base_annees`, `methode_percentile`, `niveau_confiance`,
`limite`. 404 `RESSOURCE_LOCALITE_INCONNUE` si la localité n'a pas de série
GHI mensuelle NASA POWER commençant en 1991. Le `limite` signale que c'est de
la variabilité inter-annuelle, pas un P90 bancable propageant l'incertitude
de modèle, et que les localités d'une même maille de NASA POWER ont les
mêmes P50 et P90 (à Ouagadougou : 2 140 et 2 096 kWh/m²/an).

`taux_salissure_proxy/{code_serie_source}` : perte de transmission par
salissure (`% = (1 − ratio HSU) × 100`, modèle HSU pvlib), à partir
d'une série PM2.5 (source `cams_eac4`). Compagnes automatiques : PM10
(même source) et précipitation journalière (source `nasa_power`,
résolveur cross-source dédié). Alignement par intersection des dates,
garde-fou de contiguïté (le modèle HSU est path-dependant). Pas de
paramètre de période : la route couvre toute la série (2005-2025 au
Burkina Faso). Réponse : `periode`, `mesures` (perte par jour),
`surface_tilt_deg`, `cleaning_threshold_mm`, `limite`.
400 `INCOMPATIBILITE_SOURCE_GRANDEUR` si la série n'est pas une PM2.5 ou si
une compagne manque.

`pr_realiste/{code_serie_source}` : PR effectif site-spécifique = `PR
fourni × ratio thermique × (1 − salissure)` selon le mode `correction`
(`aucune`, `temperature`, `salissure`, `temperature_salissure`, défaut
`temperature_salissure`). Série source = GHI ; compagnes selon le mode
(T2M et pluie même source, PM cross-source `cams_eac4`). Paramètres
query : `pr_fourni` `[0..1]`, `correction`, `noct_degc` et
`coeff_temp_pourcent_par_degc` (obligatoires si la correction inclut la
température, sinon `422 VALIDATION_CHAMP_MANQUANT`). Pas de paramètre de
période : la route lit la série depuis le 1er janvier 2000. Une série de
province (1991-2025) répond donc sur 2000-2025, et sur 2005-2025 dès que la
correction inclut la salissure, la réponse étant alors bornée aux jours
couverts par les PM. Un trou dans la série répond 422
`PLAGE_TEMPORELLE_NON_DISPONIBLE` : c'est le cas des séries journalières CAMS
Radiation et SARAH-3, qui ont des jours sans valeur. Avec elles,
`correction=aucune` répond 422, et les autres modes 400
`INCOMPATIBILITE_SOURCE_GRANDEUR`, faute de T2M ou de pluie de même source.
Réponse : `periode`, `mesures_journalier` et `mesures_mensuel` (la courbe
mensuelle est la PR saisonnière), `limite`.

`incertitude_inter_source/{code_localite}` : fiche d'incertitude
inter-source d'une localité, en lecture/assemblage de grandeurs déjà
matérialisées (aucun calcul de substrat). Deux axes distincts, non
fusionnés : `ecarts` (écart à NASA POWER de SARAH-3, ERA5 et CAMS pour le
GHI et le DNI, de CAMS pour le DHI, fenêtre commune 2005-2023, ADR-0016)
et `degenerescence` (nombre d'autres localités qui lisent la même maille
CERES de NASA POWER). `ecart_abs_pct` (médiane des écarts absolus mensuels) est
le signal primaire ; `ecart_signe_pct` est orientationnel, jamais une
correction de biais. `niveau_confiance` : B, lu et vérifié (jamais A :
inter-source, pas terrain). 404 `RESSOURCE_LOCALITE_INCONNUE` si la
localité n'est pas couverte par l'atlas.

`incertitude_inter_source` (collection) : toutes les fiches des points
de l'atlas, paginées, enveloppe identique à `/v1/series` (`items`,
`total`, `limit`, `offset`). Chaque item est la fiche par-localité
augmentée de `latitude_deg`/`longitude_deg`, pour poser chaque point sur
une carte sans second appel. Le périmètre est data-driven (les localités
portant un écart sur la fenêtre, 398 au Burkina Faso), robuste à une
densification.

#### 3.7.7 Erreurs des routes grandeurs

| Code | HTTP | Condition |
|---|---|---|
| `RESSOURCE_SERIE_INCONNUE` | 404 | `code_serie_source` introuvable |
| `RESSOURCE_LOCALITE_INCONNUE` | 404 | localité hors périmètre de la route F1 |
| `INCOMPATIBILITE_SOURCE_GRANDEUR` | 400 | série de mauvaise grandeur, source non admissible, ou compagne requise absente |
| `VALIDATION_VALEUR_INVALIDE` | 422 ou 400 | 422 : paramètre absent ou hors plage, date mal formée ou format inconnu, `periode_fin` antérieure à `periode_debut`, `noct_degc` ou `coeff_temp_pourcent_par_degc` absent avec `correction=temperature` (`productible_pr_fourni`) ; 400 : `integration_horaire` sur série non horaire, ou `poa_parametrable` horaire sans DHI horaire |
| `VALIDATION_CHAMP_MANQUANT` | 422 | `noct_degc` ou `coeff_temp_pourcent_par_degc` absent quand la correction de `pr_realiste` inclut la température |
| `PLAGE_TEMPORELLE_NON_DISPONIBLE` | 422 | trou dans la série lue par `taux_salissure_proxy` ou `pr_realiste` (contrôle de continuité) |

Une grandeur hors catalogue (`/v1/grandeurs/hep`, par exemple) n'a pas de
route : la réponse est un 404 de FastAPI, `{"detail": "Not Found"}`, hors de
l'enveloppe d'erreur Kuma.

### 3.8 `GET /v1/horaire/{localite}/{grandeur}`

Localités : toute localité du référentiel par son **code complet**
(ex. `bfa_com_ouagadougou`). Un code inconnu répond 404
`RESSOURCE_LOCALITE_INCONNUE`.

Cet endpoint sert d'abord l'horaire stocké et validé par contrôle
qualité, avec repli passe-plat sur la source amont sinon. Au Burkina Faso,
l'horaire stocké couvre 2021-2025 aux cinq points pilotes (Ouagadougou,
Dédougou, Dori, Kaya, Koupéla) : GHI, DNI, DHI et T2M de NASA POWER, GHI,
DNI, DHI et GHI par ciel clair de CAMS Radiation (ADR-0014, ADR-0023).
Ailleurs, ou pour les autres grandeurs, la requête est relayée.

Comportement :

1. Si une série horaire stockée couvre la plage demandée, l'endpoint
   renvoie les points validés (`mesures_ressource_horaires`, statut
   `valide_auto`, confiance B). Les lignes rejetées par le contrôle
   qualité (statut `brut`) sont exclues.
2. Sinon, l'API relaie la requête vers le service amont (NASA POWER),
   convertit la réponse au format Kuma et l'étiquète
   `passe_plat_non_valide`.

Une localité peut porter plusieurs séries horaires de la même grandeur
(NASA POWER et CAMS Radiation aux points pilotes, ADR-0023). Le
paramètre `source` choisit la série ; sans lui, la série de NASA POWER,
source du relais, est servie. Le champ `source` de la réponse JSON nomme
la série servie. Avec `source=cams_radiation`, ou pour `ghi_ciel_clair`,
que seul CAMS Radiation sert, il n'y a pas de relais : une plage non
couverte répond 400 `PLAGE_TEMPORELLE_NON_DISPONIBLE`, avec dans les
détails la plage de la série stockée (`plage_disponible`) quand elle
existe.

Le champ `statut_editorial` de chaque point vaut donc `valide_auto`
(stocké validé) ou `passe_plat_non_valide` (relais non validé).

- Auth : Bearer requise
- Paramètres path :

| Paramètre | Valeurs autorisées |
|---|---|
| `{localite}` | code complet d'une localité du référentiel (ex. `bfa_dep_dori`) |
| `{grandeur}` | `ghi`, `dni`, `dhi`, `ghi_ciel_clair`, `t2m`, `rh2m`, `kt`, `vent_2m`, `vent_10m`, `precipitation` |

- Paramètres query :

| Paramètre | Type | Plage | Obligatoire |
|---|---|---|---|
| `periode_debut` | `YYYY-MM-DD` | `>= 2001-01-01` | oui |
| `periode_fin` | `YYYY-MM-DD` | `>= periode_debut`, plage `<= 366` jours | oui |
| `format` | `json` / `csv` | | non (`json` défaut) |
| `source` | `nasa_power` / `cams_radiation` | | non (`nasa_power`, source du relais) |

Une `periode_fin` antérieure à `periode_debut` ou une plage de plus de
366 jours répond 422 `VALIDATION_VALEUR_INVALIDE`.

- Réponse 200 JSON, pour
  `/v1/horaire/bfa_dep_dori/ghi?periode_debut=2024-06-01&periode_fin=2024-06-01&source=cams_radiation`
  (deux des 24 points reproduits) :

```json
{
  "localite": "bfa_dep_dori",
  "grandeur": "ghi",
  "source": "cams_radiation",
  "periode_demandee": {
    "debut": "2024-06-01",
    "fin": "2024-06-01"
  },
  "resultats": [
    {
      "instant": "2024-06-01T00:00:00",
      "valeur": 0.0,
      "unite": "Wh/m²",
      "statut_editorial": "valide_auto"
    },
    {
      "instant": "2024-06-01T12:00:00",
      "valeur": 910.7354,
      "unite": "Wh/m²",
      "statut_editorial": "valide_auto"
    }
  ]
}
```

- 24 points par jour, instant en UTC, au début de l'heure : la valeur est
  l'irradiation de l'heure qui commence à l'instant (Wh/m², soit sa
  moyenne en W/m²).
- `valeur: null` pour les heures où l'indice n'est pas physiquement
  défini (cas `kt` la nuit) ou une donnée manquante amont en mode repli.
- Format CSV : header `instant, valeur, unite, statut_editorial` (sans le
  champ `source`).

### 3.9 `GET /v1/horaire/{localite}/{grandeur}/disponibilite`

Retourne la plage temporelle de la série que sert `/v1/horaire` pour les
mêmes `localite`, `grandeur` et `source` (ADR-0023).

- Auth : Bearer requise
- Paramètre : `source` (`nasa_power` ou `cams_radiation`), facultatif,
  comme pour `/v1/horaire`.
- Réponse 200, sans `source` (relais NASA POWER) :

```json
{
  "localite": "bfa_dep_dori",
  "grandeur": "ghi",
  "source": "nasa_power",
  "plage_disponible": {
    "debut": "2001-01-01",
    "fin": "2026-05-30"
  },
  "statut_editorial": "passe_plat_non_valide"
}
```

- Pour la source du relais et une grandeur qu'il sert (GHI, DNI, DHI,
  T2M…), la plage est celle du relais : `debut` est fixé à `2001-01-01`
  (borne historique du substrat solaire amont), `fin` est la date du jour
  moins 151 jours (cinq mois de 30 jours et un jour), pour la latence du
  service amont. L'exemple date du 28 octobre 2026. Le couple
  `(localite, grandeur)` n'est alors pas vérifié : une localité inconnue
  reçoit aussi cette plage.
- Avec `source=cams_radiation`, ou pour `ghi_ciel_clair`, que seul CAMS
  sert et qui ne se relaie pas, la plage est celle de la série stockée,
  avec `statut_editorial` à `valide_auto` : par exemple
  `{"debut": "2021-01-01", "fin": "2025-12-31"}` et `"source":
  "cams_radiation"` à Dori. Sans `source`, la série de NASA POWER passe
  avant les autres.
- En profil édition figée, celui du serveur public, il n'y a pas de
  relais : la plage est toujours celle de la série stockée, en
  `valide_auto` (2021-01-01 à 2025-12-31 aux cinq points pilotes, avec
  `"source": "nasa_power"` sans paramètre `source`) ; ailleurs, 404.
- La plage d'une série stockée est recoupée avec la fenêtre du relais, que
  `/v1/horaire` impose à toute requête : elle est donc toujours acceptée
  par `/v1/horaire`.
- Sans série stockée pour la source demandée (l'horaire CAMS n'existe
  qu'aux cinq points pilotes), ou si le recoupement est vide : 404
  `RESSOURCE_SERIE_INCONNUE`. Hors du cas du relais, une localité inconnue
  répond 404 `RESSOURCE_LOCALITE_INCONNUE`. Une `source` hors des deux
  valeurs répond 422 `VALIDATION_VALEUR_INVALIDE`.

### 3.10 `GET /v1/edition` : édition publiée servie

Fraîcheur affichée (ADR-0003, D7) : chaque déploiement public sert une
édition datée de la base de référence, et l'API dit laquelle.

- Auth : non requise (même statut public que `/v1/health`)
- Réponse 200 :

```json
{
  "edition_id": "edition_AAAAMMJJ",
  "date_publication": "AAAA-MM-JJ",
  "revision_source": "<hash git court>",
  "couverture_resumee": {
    "localites": 417,
    "series": 21930
  }
}
```

- `revision_source` désigne la révision du dépôt public au moment de
  l'export de l'édition. Les métadonnées sont injectées par le script
  d'export dans l'édition elle-même, jamais devinées côté serveur.
- `couverture_resumee` est comptée à la lecture : localités et séries
  actives. Les chiffres de l'exemple sont ceux de la base à la migration
  0023 (417 localités, du continent aux départements ; 21 930 séries).
- Erreurs : `404 RESSOURCE_INTROUVABLE` si le déploiement ne sert pas
  une édition publiée (base de développement) - c'est l'état normal du
  régime local.

### 3.11 `POST /v1/cles` et `DELETE /v1/cles/{prefixe}` : clés self-service

Cycle de vie des clés self-service (ADR-0003, D3). Disponible sur le
profil serveur public uniquement : sans base de service configurée,
l'émission renvoie `404 CLES_EMISSION_NON_ACTIVEE`.

**Émission** - `POST /v1/cles`, non authentifié (c'est l'inscription) :

```json
{"email": "dev@exemple.org", "usage_prevu": "outil de dimensionnement"}
```

- Réponse 201 :

```json
{
  "cle": "kuma_<43 caractères URL-safe>",
  "prefixe": "kuma_xxxxxxxx",
  "quota_journalier": 5000
}
```

- La clé est montrée **une seule fois** : le serveur n'en conserve que
  l'empreinte SHA-256. Le `prefixe` est l'identifiant public de la clé
  (support, révocation).
- L'émission est bornée par adresse IP (3 par 24 h glissantes) :
  `429 CLES_LIMITE_EMISSION_ATTEINTE` au-delà. C'est la seule surface
  d'écriture publique du serveur.

**Quota journalier** : chaque requête authentifiée par une clé
self-service consomme son quota du jour (fenêtre calendaire UTC,
compteur Redis indexé sur l'empreinte). Dépassement :
`429 CLES_QUOTA_JOURNALIER_DEPASSE`. Le compteur est fail-open : une
panne du cache ne rend pas les données indisponibles. Les clés
d'environnement ne sont jamais limitées.

**Révocation** - `DELETE /v1/cles/{prefixe}`, réservé à la clé
administrateur. Révoque (soft delete) toutes les clés actives du
préfixe ; `404 RESSOURCE_INTROUVABLE` si aucune. Une clé valide mais
non administrative reçoit le même `401 AUTH_CLE_INVALIDE` qu'une clé
inconnue.

### 3.11 bis `GET /v1/localites/resolution` : résolution d'un point quelconque

Authentifié. Paramètres : `lat` (`[-90, 90]`), `lon` (`[-180, 180]`),
`grandeur` (optionnel, `ghi` seul admis à ce stade).

Pour un point WGS84 quelconque, retourne la localité du référentiel
dont la climatologie mensuelle (période de référence 1991-2020)
échantillonne la **cellule de grille** contenant le point. Les
candidates sont les localités portant une série mensuelle active de la
grandeur qui va exactement du 1er janvier 1991 au 31 décembre 2020. La
cellule est celle de la grille de la source de climatologie, de 1 degré
x 1 degré, frontières aux degrés entiers.

Le plus-proche-voisin naïf est faux et c'est la raison d'être de
l'endpoint : la localité la plus proche d'un point peut appartenir à
une autre cellule. La résolution est un savoir éditorial du Core, pas
des consommateurs (ADR-0004).

Réponse : `point`, `grandeur`, `cellule` (bornes de la cellule),
`localite` (`code`, `nom`, coordonnées), `distance_km`,
`meme_cellule`, et `serie_climatologie` : le code de la série de
climatologie mensuelle de la localité retenue - le Core dit quelle
série consommer pour ce point, les clients ne le reconstruisent
jamais par convention de nommage (généricité pays). Quand aucune
candidate ne partage la cellule, `meme_cellule` vaut `false` et la
candidate la plus proche est renvoyée : le consommateur affiche alors
l'hypothèse de transport. 404 `RESSOURCE_INTROUVABLE` si le référentiel
ne porte aucun point d'ingestion pour la grandeur.

Au Burkina Faso, aucune série ne remplit cette condition : le GHI mensuel
de NASA POWER va de 1991 à 2025. L'endpoint y répond donc 404
`RESSOURCE_INTROUVABLE` pour tout point.

### 3.11 ter `GET /v1/calage/{localite}/{grandeur}` : référentiel de calage satellite/sol

Authentifié. Codes localité complets (`bfa_dep_dori`), alignés sur
`/v1/series` et `/v1/localites`.

Sert les biais saisonniers satellite moins sol mesurés aux stations
de référence, publiés comme donnée éditoriale de l'édition (table
`referentiels_calage`, ADR-0004) : pour chaque saison, le nom, les
mois couverts, le biais relatif mesuré et le facteur dérivé
`k = 1 / (1 + biais)`. La réponse porte la provenance (note de
calage, script reproductible, série sol de référence) et la portée
de transport : jamais un nombre nu. 404 `RESSOURCE_INTROUVABLE` pour un
couple sans référentiel publié.

`GET /v1/calage` (sans paramètre) liste les référentiels publiés :
une entrée par référentiel avec station, grandeur, version, **série
sol de fondation** (`serie_sol` : la séquence horaire de référence à
utiliser avec ce calage) et localités couvertes. C'est l'endpoint de
découverte des consommateurs d'étude : ajouter une station = publier
son référentiel, aucun changement côté consommateurs. Le détail
porte aussi `serie_sol`.

La réponse porte aussi le **domaine de couverture** du transport
(`localites_couvertes`, `justification_couverture`, table
`calage_couverture`) : les codes des localités qualifiées pour appliquer
ce calage (couverture progressive, ADR-0004). Un consommateur d'étude
calée doit vérifier que la localité résolue de son site en fait partie ;
l'extension du domaine passe par la recherche et les éditions, jamais par
les consommateurs.

Au Burkina Faso, aucun référentiel n'est publié : `GET /v1/calage` répond
`{"items": [], "total": 0}` et le détail répond 404. Un référentiel
demande une série sol ; les stations ESMAP/WAPP de Dédougou, Dori, Kaya
et Koupéla ne sont pas intégrées (ROADMAP, jalon 6).

### 3.11 quater `POST /v1/licence/bail` : bail d'usage de SolClim-3

Authentifié. Remet un **bail signé** à une clé porteuse d'une licence
SolClim-3 active (table `licences_solclim`, ADR-0005). Une clé d'API
publique seule, la clé d'environnement partagée ou la clé
administrateur n'y donnent pas droit : `403 LICENCE_ABSENTE`. Sans base
de service ou sans graine de signature configurée :
`404 LICENCE_NON_ACTIVEE`.

- Réponse 200 :

```json
{
  "charge": "<JSON canonique en base64url>",
  "signature": "<Ed25519 des octets de la charge, base64url>",
  "titulaire": "Prénom Nom",
  "expire_le": "2026-10-31T12:30:45Z"
}
```

- La charge décodée porte `version`, `produit` (`solclim3`),
  `prefixe_cle`, `titulaire`, `organisation`, `emis_le`, `expire_le` et
  `version_minimale`. Le bail vaut 30 jours (`LICENCE_DUREE_JOURS`),
  sans dépasser le terme de la licence.
- La signature porte sur les **octets** transportés : le vérificateur
  décode la charge, vérifie la signature avec la clé publique, puis lit
  le JSON. L'expiration est jugée par le lecteur (logiciel, calage).
- Chaque émission note la date du dernier bail de la licence.

Les licences s'administrent sur le serveur, par
`python -m kuma_data_core.services.licences` (accorder, lister,
prolonger, retirer). Retirer la licence laisse la clé ouvrir l'API
publique ; révoquer la clé coupe tout.

### 3.11 quinquies `POST /v1/contributions/{etude_uid}` : fiche d'une étude SolClim-3

Authentifié, clé porteuse d'une licence SolClim-3 active (sinon
`403 LICENCE_ABSENTE`). Dépose la fiche d'une étude, ou remplace celle que
la même clé avait déposée pour cette étude (ADR-0006). `etude_uid` est un
UUID tiré par le logiciel, jamais le nom de l'étude. Sans base de
service : `404 CONTRIBUTIONS_NON_ACTIVEES`.

- Corps : `{"module": ..., "format": ..., "fiche": {...}}`, trois formats :
  - `pv-autonome` / `pv-autonome@1` : `logiciel` (version, jour), `lieu`
    (code de sous-préfecture **ou** point), `panneaux`, `ressource` (brut
    ou calé, version de la base), `appareils`, `systeme`, `prix` (monnaie
    de l'étude) et `resultats` (valeurs de synthèse du dimensionnement) ;
  - `minireseau` / `minireseau@1` : `logiciel`, `lieu`, `ressource`,
    `champ` (ratio de performance, inclinaison, plan), `charge` (postes
    avec leur énergie par jour et leur **profil sur 24 heures**, facteurs
    mensuels, croissance année par année), `stockage`, `groupe`
    (puissance, consommations, prix du litre, facteur d'émission),
    `dimensionnement` (horizon, cible de délestage, plages balayées),
    `prix` (coûts unitaires et paramètres économiques) et `resultats`
    (configuration retenue, délestage, groupe, carburant, CO2, LCOE et
    ses parts). Ni nom de site, ni textes du rapport, ni séries de la
    ressource ;
  - `pv-champ` / `pv-champ@1` : `logiciel`, `lieu`, `ressource`, `plan`,
    `conditions` (puissance visée, températures, ensoleillement saisi),
    `module` et `onduleur` (caractéristiques, **sans marque ni
    référence**), `pertes` (poste par poste), `cablage` (longueurs, chutes
    de tension, matériau, tension AC, dératage, dimensions du module) et
    `resultats` (strings, onduleurs, modules, puissance DC, ratio DC/AC,
    vérifications électriques, température de cellule, PR et productible,
    sections de câbles, calibres de protections). Ni nom d'étude, ni
    coordonnées exactes, ni nomenclature chiffrée.

  Le module et le format vont ensemble : une fiche d'un module sous
  l'autre est refusée.
- Contrat **fermé** : un champ non prévu est refusé (422). Le point est
  arrondi à 0,1° et le nom d'un appareil ou d'un poste coupé à 40
  caractères, côté serveur.
- `lieu.sous_prefecture` n'accepte qu'un code de la forme `GN` suivi de
  huit chiffres, qui ne désigne aucune localité du Burkina Faso : le lieu
  s'y donne par le point.
- Réponse **201** au premier envoi, **200** ensuite :

```json
{
  "etude_uid": "6f1c…",
  "recue_le": "2026-10-02T10:12:03Z",
  "mise_a_jour_le": "2026-10-02T11:40:27Z",
  "nombre_envois": 2
}
```

`POST /v1/contributions/{etude_uid}/retrait` supprime la fiche que la
clé avait déposée : **204**, ou `404 CONTRIBUTION_INCONNUE` si elle n'en
a pas déposé. La clé suffit, licence ou non. Les deux routes sont en
`POST` : le CORS n'ouvre aux vues web que `GET` et `POST`.

Le bilan et l'export (sans les clés) se font sur le serveur, par
`python -m kuma_data_core.services.contributions` (bilan, exporter).

### 3.11 sexies `GET /v1/etudes/capsule` : ressource d'étude au point

Authentifié. Assemble, pour un point (`lat`, `lon`), la ressource du moteur
au format texte `kuma-ressource-1`, lu par le moteur de dimensionnement
des mini-réseaux : localité résolue (3.11 bis), climatologie mensuelle
1991-2020 et séquence horaire satellite.

| Paramètre | Type | Défaut | Description |
|---|---|---|---|
| `lat` | `float [-90, 90]` | | Latitude WGS84 |
| `lon` | `float [-180, 180]` | | Longitude WGS84 |
| `calage` | `bool` | `false` | `true` : ressource calibrée en ligne, par appel serveur à serveur au service de calage |
| `annee_min`, `annee_max` | `int [2001, 2025]` | | Fenêtre de la séquence horaire |

- Réponse 200 : `text/plain`.
- Erreurs : 400 `VALIDATION_VALEUR_INVALIDE` si `annee_min > annee_max` ;
  404 `RESSOURCE_INTROUVABLE` si le point ne se résout sur aucune localité ;
  503 `CALAGE_INDISPONIBLE` si `calage=true` et que le service de calage
  n'est pas configuré ou ne répond pas.

La capsule repose sur la même climatologie 1991-2020 que la résolution :
au Burkina Faso, elle répond 404 `RESSOURCE_INTROUVABLE` pour tout point.

### 3.12 Codes d'erreur exposés par l'API

| Code | Statut HTTP type | Sens |
|---|---|---|
| `AUTH_HEADER_MANQUANT` | 401 | header `Authorization` absent |
| `AUTH_FORMAT_INVALIDE` | 401 | préfixe `Bearer ` manquant |
| `AUTH_CLE_INVALIDE` | 401 | clé absente du jeu valide |
| `VALIDATION_CHAMP_MANQUANT` | 422 | paramètre conditionnel absent sur `pr_realiste`, seule route qui l'émet (3.7.7) |
| `VALIDATION_VALEUR_INVALIDE` | 422 / 400 | 422 : champ requis absent, valeur hors plage (dont `limit` hors `[1, 1000]` sur les listings, hors `[1, 10000]` sur `/v1/series/{code}`), date mal formée ou format inconnu hors `/v1/series/{code}`, période incohérente ou plage horaire de plus de 366 jours ; 400 : mode horaire sur série non horaire, `poa_parametrable` horaire sans DHI horaire, capsule avec `annee_min` supérieure à `annee_max` |
| `VALIDATION_FORMAT_DATE_INVALIDE` | 400 | date pas `YYYY-MM-DD` ni `YYYY-MM`, sur `/v1/series/{code}` seulement |
| `VALIDATION_FORMAT_NON_SUPPORTE` | 400 | format autre que `json` ou `csv`, sur `/v1/series/{code}` seulement |
| `VALIDATION_LIMIT_HORS_BORNES` | 400 | réservé, non émis : un `limit` hors bornes répond 422 `VALIDATION_VALEUR_INVALIDE` |
| `RESSOURCE_INTROUVABLE` | 404 | code générique de ressource manquante |
| `CALAGE_INDISPONIBLE` | 503 | calage en ligne de la capsule non configuré ou injoignable |
| `RESSOURCE_SERIE_INCONNUE` | 404 | série introuvable |
| `RESSOURCE_LOCALITE_INCONNUE` | 404 | localité introuvable |
| `GRANDEUR_F2_INCONNUE` | 404 | réservé, non émis : une grandeur hors catalogue n'a pas de route (404 `{"detail": "Not Found"}`, 3.7.7) |
| `INCOMPATIBILITE_SOURCE_GRANDEUR` | 400 | série incompatible ou compagne manquante |
| `PLAGE_TEMPORELLE_NON_DISPONIBLE` | 400 / 422 | 400 : requête horaire hors plage utilisable ; hors stocké en profil édition figée, pour `source=cams_radiation` ou pour `ghi_ciel_clair` (sans relais). 422 : trou dans la série de `taux_salissure_proxy` ou `pr_realiste` |
| `PASSE_PLAT_INDISPONIBLE` | 503 | service amont temporairement indisponible |
| `CLES_EMISSION_NON_ACTIVEE` | 404 | self-service de clés non disponible sur ce déploiement |
| `CLES_LIMITE_EMISSION_ATTEINTE` | 429 | limite d'émission de clés par IP atteinte |
| `CLES_QUOTA_JOURNALIER_DEPASSE` | 429 | quota journalier de la clé self-service dépassé |
| `LICENCE_NON_ACTIVEE` | 404 | émission de bail SolClim-3 non disponible sur ce déploiement |
| `LICENCE_ABSENTE` | 403 | aucune licence SolClim-3 active n'est attachée à la clé |
| `CONTRIBUTIONS_NON_ACTIVEES` | 404 | réception des fiches d'études non disponible sur ce déploiement |
| `CONTRIBUTION_INCONNUE` | 404 | aucune fiche de cette étude n'a été déposée avec cette clé |
| `INFRASTRUCTURE_BASE_INDISPONIBLE` | 503 | PostgreSQL injoignable |
| `INFRASTRUCTURE_CACHE_INDISPONIBLE` | 503 | cache (Redis) indisponible (déclaré, non levé : les compteurs sont fail-open) |
| `SERVEUR_ERREUR_INTERNE` | 500 | filet de sécurité, aucune fuite technique |

Le contrat des codes est stable : un code publié ne change pas de sens,
ne disparaît pas. Pour faire évoluer, un nouveau code est créé.

## 4. Les grandeurs disponibles

Le catalogue des grandeurs vit dans la table `grandeurs_referentiel`. Aucune
route ne le liste : chaque série porte le code, le libellé et l'unité de sa
grandeur (`/v1/series`). Chaque grandeur a :

- `code` : identifiant ASCII stable, snake_case (ex. `ghi`,
  `fraction_diffuse`).
- `libelle` : titre humain (ex. Irradiation globale horizontale).
- `unite` : code et symbole d'unité issus de la table `unites`.
- `famille` : `F1` (ontologique) ou `F2` (paramétrable, calcul
  nécessitant des paramètres utilisateur).
- `strategie_calcul` : `stockee` (persistée) ou `calculee_volee`
  (recalculée à chaque consultation).
- `version_formule_actuelle` : compteur applicatif, incrémenté à chaque
  révision méthodologique.

Le référentiel est celui du moteur : il déclare aussi des grandeurs sans
série ni route au Burkina Faso (4.3).

### 4.1 Grandeurs brutes ingérées depuis sources externes (F1 stockée)

Granularités : H horaire (cinq points pilotes, 2021-2025), J journalier,
M mensuel. Hors horaire, chaque série existe aux 398 localités (47 provinces
et 351 communes).

| Code | Libellé | Unité | Sources (granularités) |
|---|---|---|---|
| `ghi` | Irradiation globale horizontale | kWh/m²/jour | NASA POWER (H, J, M), CAMS Radiation (H, J, M), SARAH-3 (J, M), ERA5 via PVGIS (M), ERA5-Land (J) |
| `dni` | Irradiation normale directe | kWh/m²/jour | NASA POWER (H, J, M), CAMS Radiation (H, J, M), SARAH-3 (J, M), ERA5 via PVGIS (M) |
| `dhi` | Irradiation diffuse horizontale | kWh/m²/jour | NASA POWER (H, J, M), CAMS Radiation (H, J, M), SARAH-3 (J) |
| `ghi_ciel_clair`, `dni_ciel_clair` | GHI et DNI par ciel clair | kWh/m²/jour | CAMS Radiation (GHI : H, J ; DNI : J) |
| `t2m` | Température à 2 mètres | °C | NASA POWER (H, J), ERA5-Land (J) |
| `t2m_min`, `t2m_max` | Températures minimale et maximale à 2 mètres | °C | NASA POWER (J), ERA5-Land (J) |
| `point_rosee_2m` | Point de rosée à 2 mètres | °C | NASA POWER (J), ERA5-Land (J) |
| `rh2m` | Humidité relative à 2 mètres | % | NASA POWER (J) |
| `pression_surface` | Pression de surface | kPa | NASA POWER (J), ERA5-Land (J) |
| `vent_10m`, `direction_vent_10m` | Vent à 10 mètres et sa direction | m/s, ° | NASA POWER (J), ERA5-Land (J) |
| `vent_10m_max`, `vent_50m` | Vent maximal à 10 mètres, vent à 50 mètres | m/s | NASA POWER (J) |
| `nebulosite` | Nébulosité | % | NASA POWER (J) |
| `precipitation` | Précipitation | mm/jour | NASA POWER (J), ERA5-Land (J) |
| `pm2_5`, `pm10` | Particules fines PM2.5 et PM10 | µg/m³ | CAMS EAC4 (J) |
| `aod550`, `aod550_poussiere`, `aod550_organique` | Épaisseur optique des aérosols à 550 nm (totale, poussières, matière organique) | sans dimension | CAMS EAC4 (J) |

L'unité est celle de la grandeur au référentiel ; les valeurs horaires sont
servies en Wh/m² sur l'heure (3.8).

Périodes : le journalier couvre 2005-2025 (SARAH-3 : 2005-2023) ; aux 47
provinces, le journalier NASA POWER remonte à 1991 pour le GHI, la
température, l'humidité et la pluie, à 2001 pour le DNI et le DHI
(ADR-0010). Le mensuel couvre 1991-2025 pour le GHI de NASA POWER, 2001-2025
pour son DNI et son DHI, 2005-2025 pour CAMS Radiation, 2005-2023 pour
SARAH-3 et ERA5 (ADR-0009, ADR-0011). Les fenêtres exactes se lisent via
`/v1/series`.

### 4.2 Grandeurs F1 stockées calculées par Kuma (couche éditoriale)

Calculées à partir des grandeurs brutes, persistées dans
`grandeurs_metier`, exposées via la vue `v_grandeurs_metier_courantes`,
confiance B. La fraction diffuse et les écarts ont leurs séries dans la
source `kuma_calculs` ; la dégénérescence de pixel, déclarée
`calculee_volee` au référentiel, est rattachée aux séries
`nasa_power_ghi_mensuel_<localité>` (source `nasa_power`) et ne se lit que
par la fiche d'incertitude.

| Code | Libellé | Unité | Calcul | Fenêtre |
|---|---|---|---|---|
| `fraction_diffuse` | Fraction diffuse | sans dimension | `DHI / GHI` mensuels NASA POWER, par mois et par année complète (ADR-0012) | 2001-2025 |
| `ecart_relatif_ghi_sarah3_nasa`, `ecart_relatif_ghi_era5_nasa`, `ecart_relatif_ghi_cams_nasa` | Écart relatif du GHI à NASA POWER | % | `(x - nasa) / nasa × 100` par mois (ADR-0012) | 2005-2023, CAMS 2005-2025 |
| `ecart_relatif_dni_sarah3_nasa`, `ecart_relatif_dni_era5_nasa`, `ecart_relatif_dni_cams_nasa` | Écart relatif du DNI à NASA POWER | % | idem | 2005-2023, CAMS 2005-2025 |
| `ecart_relatif_dhi_cams_nasa` | Écart relatif du DHI de CAMS à NASA POWER | % | idem | 2005-2025 |
| `degenerescence_pixel` | Dégénérescence de pixel | sans dimension | Nombre d'autres localités qui lisent la même maille de 1° de NASA POWER (ADR-0016) | valeur statique |

Ces grandeurs se lisent par `/v1/series/{code}` (séries
`fraction_diffuse_nasa_power_<localité>` et
`ecart_<grandeur>_<source>_nasa_<localité>`) et, assemblées, par la fiche
`incertitude_inter_source` (3.7.6).

### 4.3 Grandeurs du référentiel sans valeur au Burkina Faso

Le référentiel déclare des grandeurs du moteur qui n'ont ici ni série ni
route : `kt`, `vent_2m`, `albedo_surface`, `hep`, `humidex`,
`productible_specifique_theorique`, `productible_mensuel`,
`variabilite_journaliere`, `indicateur_qualite_donnees`,
`ecart_relatif_referentiel`, `ecart_relatif_dni_cams`, `rang_referentiel`,
`rang_referentiel_temporel` et `rang_referentiel_spatial`. Les écarts
stockés de 4.2 tiennent lieu des grandeurs référentielles.
`/v1/horaire` accepte `kt` et `vent_2m`, servis par le relais NASA POWER
seulement.

### 4.4 Grandeurs F2 paramétrables

Voir 3.7 pour les routes, modèles physiques et paramètres.

| Code | Libellé | Unité | Modèle physique |
|---|---|---|---|
| `poa_parametrable` | POA paramétrable | kWh/m²/jour | Perez 1990 + fallback Liu-Jordan (Erbs 1982) |
| `poa_bifacial` | POA bifacial | kWh/m²/jour | Infinite-sheds row-aware (pvlib) |
| `productible_correction_thermique` | Productible corrigé thermique | kWh par jour, pour la puissance `puissance_stc_wc` | NOCT simple (Ross 1980) |
| `productible_pr_fourni` | Productible avec PR fourni | kWh par jour, pour `puissance_stc_wc` ; depuis une série mensuelle, productible quotidien moyen du mois | PR brut (Marion 2005) ou PR_T (Dierauf 2013) |
| `energie_utile_ecs` | Énergie utile ECS bord-capteur | kWh/m² par jour | Hottel-Whillier-Bliss 1958 |
| `degre_jour_climatisation` | Degrés-jours de climatisation | °C·j | Moyenne journalière ou Erbs 1983 |

### 4.5 Grandeurs horaires

Une partie du substrat solaire existe en granularité horaire, stockée dans
`mesures_ressource_horaires` avec passage par contrôle qualité (statut
`valide_auto`, confiance B). Aux cinq points pilotes, NASA POWER et CAMS
Radiation servent chacun le GHI, le DNI et le DHI horaires de 2021 à
2025 ; NASA POWER y ajoute la température et CAMS le GHI par ciel clair
(ADR-0014, ADR-0023). Ces séries alimentent l'endpoint horaire (3.8) et le
mode `integration_horaire` des routes F2. CAMS ne sert pas de température :
les grandeurs qui demandent la température horaire partent de la série
NASA POWER. Les séries horaires se repèrent dans `/v1/series` à leur code
(`nasa_power_ghi_horaire_bfa_dep_dori`, `cams_ghi_horaire_bfa_dep_dori`) ;
leurs mesures se lisent par `/v1/horaire`.

### 4.6 Détails méthodologiques

Chaque grandeur ingérée ou calculée au Burkina Faso a son ADR sous
`docs/decisions/` (ADR-0009 à ADR-0024). Les modèles des grandeurs
paramétrables sont décrits dans
[`docs/methodologie/grandeurs-parametrables.md`](../methodologie/grandeurs-parametrables.md),
la fraction diffuse dans
[`docs/methodologie/grandeurs/fraction_diffuse.md`](../methodologie/grandeurs/fraction_diffuse.md),
le contrôle qualité horaire dans
[`docs/methodologie/doctrine-qc-horaire.md`](../methodologie/doctrine-qc-horaire.md).

## 5. Structure des données et doctrine

### 5.1 Doctrine des 3 couches de sources

La doctrine éditoriale classe chaque source dans une des 3 couches.

- Couche A, calibration terrain : mesures sol locales. Aucune n'est encore
  au dépôt : la source `esmap_wapp` est déclarée sans série (7.3).
- Couche B, substrat modélisé et cross-check inter-source : données
  satellitaires et de réanalyse (NASA POWER en source primaire, SARAH-3 et
  ERA5 via PVGIS, CAMS Radiation, CAMS EAC4, ERA5-Land).
- Couche C, post-traitement éditorial et conventions normatives :
  grandeurs dérivées Kuma (`kuma_calculs`) et conventions
  méthodologiques internationales appliquées aux données (IEC 61724-1:2021
  pour le PV, WMO-No.8 / CIMO Guide pour la météo).

### 5.2 Niveaux de confiance par mesure

Chaque mesure porte :

- `niveau_confiance_derive` : `A` / `B` / `C`, dérivé automatiquement par
  les règles R1-R4 à partir de la `methode_collecte` de la série et de la
  `fiabilite` de la source.
- `niveau_confiance_override` : `A` / `B` / `C` ou `null`. Override
  éditorial avec justification obligatoire.
- `niveau_effectif` (calculé) : `override` si non null, sinon `derive`.

Règles de dérivation (`editorial/niveaux_confiance.py`), évaluées dans
l'ordre, la première qui matche l'emporte :

| Ordre | Condition | Résultat |
|---|---|---|
| R1 | `source.fiabilite = 'faible'` | `C` |
| R2 | `methode_collecte = 'expertise_humaine'` (R1 négative) | `C` |
| R3 | `methode_collecte = 'mesure_directe'` ET `source.fiabilite = 'haute'` | `A` |
| R4 | tous les autres cas (catch-all) | `B` |

Interprétation :

- `A` : haute confiance, réservée aux mesures terrain. Seule une source à
  méthode `mesure_directe` et `fiabilite=haute` (une station sol) satisfait
  R3. Aucune série n'est en confiance A au Burkina Faso.
- `B` : confiance moyenne (modèle satellitaire ou réanalyse, source haute
  fiabilité), niveau dominant du substrat modélisé.
- `C` : confiance basse (source faible, ou expertise sans validation
  instrumentale).

La confiance A n'est pas un champ de `sources` : elle est dérivée. Une
source ne porte que sa `fiabilite` ; le A émerge de la combinaison R3 sur
une mesure directe terrain.

### 5.3 Statut éditorial

Chaque mesure et chaque ligne de `grandeurs_metier` porte un statut parmi
5 valeurs (CHECK constraint) :

| Statut | Sens |
|---|---|
| `brut` | Importé/calculé non validé (défaut à l'ingestion) |
| `valide_auto` | Contrôle qualité automatique passé |
| `valide_humain` | Validation éditoriale humaine confirmée |
| `publie` | Publié publiquement |
| `deprecie` | Retiré du circuit éditorial |

Les transitions sont encadrées par la couche service Python ; l'API les
expose en lecture. La vue `v_grandeurs_metier_courantes` filtre
nativement les lignes `deprecie` et les versions de formule non
actuelles.

### 5.4 Convention de nommage des codes de série

Format des séries brutes :

```
<prefixe_source>_<grandeur>_<granularite>_<code_localite>
```

Le préfixe abrège la source : `nasa_power`, `cams` (`cams_radiation`),
`cams_eac4`, `sarah3` (`sarah3_monthly`), `era5` (`era5_pvgis`),
`era5_land` (`ecmwf_era5_land`). Les séries calculées par Kuma suivent
`<grandeur>_<source amont>_<code_localite>` (ADR-0012).

Exemples :

| Code | Décomposition |
|---|---|
| `nasa_power_ghi_journalier_bfa_com_ouagadougou` | source `nasa_power`, grandeur `ghi`, journalier, localité `bfa_com_ouagadougou` |
| `cams_ghi_horaire_bfa_dep_dori` | source `cams_radiation`, horaire, département de Dori |
| `sarah3_ghi_mensuel_bfa_prov_kadiogo` | source `sarah3_monthly`, mensuel, province du Kadiogo |
| `fraction_diffuse_nasa_power_bfa_com_ouagadougou` | grandeur `fraction_diffuse` calculée depuis NASA POWER (`kuma_calculs`) |
| `ecart_ghi_cams_nasa_bfa_com_ouagadougou` | écart du GHI de CAMS à NASA POWER (`ecart_relatif_ghi_cams_nasa`, `kuma_calculs`) |

Règles :

- Le code de localité est le code complet de la table `localites` (5.5).
- Caractères : ASCII pur, snake_case.

### 5.5 Convention de nommage des codes de localité

Codes du Burkina Faso (ADR-0007) :

| Type | Format | Exemples |
|---|---|---|
| `continent` | slug ASCII | `afrique` |
| `pays` | ISO 3166-1 alpha-3 minuscule | `bfa` |
| `region_administrative` (région) | `bfa_<slug>` | `bfa_bankui`, `bfa_yaadga` |
| `prefecture` (province) | `bfa_prov_<slug>` | `bfa_prov_kadiogo`, `bfa_prov_seno` |
| `commune` (département) | `bfa_dep_<slug>` | `bfa_dep_dori`, `bfa_dep_koupela` |
| `commune` (Ouagadougou) | `bfa_com_ouagadougou` | |

Le slug est le nom en ASCII minuscule. Un nom porté par deux départements
reçoit en suffixe le slug de sa province
(`bfa_dep_boussouma_sandbondtenga`).

### 5.6 Données stockées vs calculées à la volée

| Stockage | Quoi |
|---|---|
| `mesures_ressource` (journalier) | Séries journalières des 47 provinces : rayonnement et météo NASA POWER depuis 1991 ou 2001 (ADR-0010, ADR-0013), PM2.5 et PM10 depuis 2005 (ADR-0015) |
| `mesures_journalieres_denses` (journalier) | Toutes les autres séries journalières, une ligne par série et par année (ADR-0017) ; la vue `v_mesures_journalieres` réunit les deux tables |
| `mesures_ressource_mensuelles` | Mensuel NASA POWER, SARAH-3, ERA5 (PVGIS) et CAMS Radiation |
| `mesures_ressource_horaires` | Horaire stocké validé par contrôle qualité (statut `valide_auto`, confiance B) |
| `grandeurs_metier` | Grandeurs F1 calculées Kuma : fraction diffuse, écarts entre sources, dégénérescence de pixel |
| Calculé à la volée | Routes F1 (`ghi_exceedance`, `taux_salissure_proxy`, `pr_realiste`, `incertitude_inter_source`) et F2 paramétrables |
| Passe-plat à la volée | Horaire non couvert par le stocké (relais amont) |

## 6. Versioning temporel des données

### 6.1 Versioning non destructif des mesures

Toute mesure est temporellement versionnée par un couple :

- `valide_du` `TIMESTAMPTZ NOT NULL` : début de la fenêtre de validité.
- `valide_au` `TIMESTAMPTZ NULL` : fin de validité, `NULL` signifiant
  encore courante.

Une contrainte EXCLUDE BTree-GiST garantit qu'au plus une ligne est
courante (`valide_au IS NULL`) pour une identité métier donnée. Une
révision crée une nouvelle ligne courante après avoir clôturé la
précédente.

### 6.2 Versioning des formules de calcul

Pour les grandeurs calculées Kuma, chaque ligne porte aussi
`version_formule` (entier `>= 1`). L'identité métier inclut ce champ :
les valeurs v1 et v2 coexistent après une révision méthodologique, et la
vue `v_grandeurs_metier_courantes` expose la version en vigueur.

### 6.3 Ce que l'API expose en lecture

En v1, `/v1/series/{code}` ne lit que les lignes courantes
(`valide_au IS NULL`) des tables éparses (journalier des provinces et
mensuel) ; les grandeurs calculées passent par la vue
`v_grandeurs_metier_courantes`, qui écarte aussi les lignes `deprecie` et
les versions de formule non courantes. Le stockage dense ne garde qu'une
version des valeurs. L'horaire se lit par `/v1/horaire`, qui ne sert que
les lignes courantes validées (`valide_auto`, `valide_humain`, `publie`).
Le ciblage explicite d'une version antérieure n'est pas exposé publiquement
v1 (l'historique reste en base pour audit interne).

### 6.4 Audit

Une table `audit_log` capture les opérations INSERT / UPDATE / DELETE sur
toutes les tables auditées via trigger PL/pgSQL `kuma_log_audit()`.
L'identifiant applicatif est propagé via
`current_setting('kuma.auteur_applicatif', true)`. Cette table n'est pas
exposée par l'API publique.

## 7. Sources de données

Chaque série pointe vers exactement une source via `source_id`. Le
listing `/v1/series` expose `source_code`, `source_label` et `source_url`
directement. La liste des sources effectivement porteuses de séries dans
un déploiement se lit via `/v1/series` (filtre `source`).

### 7.1 Sources du substrat et de la couche éditoriale

| Code | Organisme | Rôle Kuma | Couche |
|---|---|---|---|
| `nasa_power` | NASA Langley Research Center | Source primaire du substrat : rayonnement et météo, mensuel, journalier et horaire (ADR-0009, ADR-0010, ADR-0013, ADR-0014, ADR-0021) | B |
| `sarah3_monthly` | CM SAF / EUMETSAT (via PVGIS, JRC) | Rayonnement SARAH-3 mensuel et journalier, 2005-2023 (ADR-0009, ADR-0022) | B |
| `era5_pvgis` | ECMWF (via PVGIS, JRC) | GHI et DNI mensuels ERA5, 2005-2023 (ADR-0009) | B |
| `cams_radiation` | Copernicus Atmosphere Monitoring Service / ECMWF | Rayonnement tous temps et par ciel clair, mensuel et journalier 2005-2025, horaire aux points pilotes 2021-2025 (ADR-0011, ADR-0020, ADR-0023) | B |
| `cams_eac4` | Copernicus Atmosphere Monitoring Service / ECMWF | PM2.5, PM10 (proxy salissure) et épaisseur optique des aérosols, journaliers (ADR-0015, ADR-0018, ADR-0019) | B |
| `ecmwf_era5_land` | ECMWF (Copernicus C3S) | Météo et GHI journaliers ERA5-Land, 2005-2025 (ADR-0024) | B |
| `kuma_calculs` | Kuma | Couche éditoriale : fraction diffuse et écarts entre sources (ADR-0012) | C |

Toutes ces sources portent `fiabilite=haute` ; leurs méthodes de collecte
(`modele_satellitaire`, `reanalyse`, `calcul_derive`) donnent la confiance B
par la règle R4.

### 7.2 Normes techniques mobilisées (couche C)

| Code | Norme | Rôle |
|---|---|---|
| `iec_61724_1_2021` | IEC 61724-1:2021 PV system performance - Monitoring | Conventions PV Kuma |
| `wmo_8_2024` | WMO-No.8 (CIMO Guide) Vol I 2024 | Conventions météo Kuma |

### 7.3 Sources de référence et structurelles au catalogue

Déclarées au référentiel pour la traçabilité ou l'ingestion future, sans
série au Burkina Faso :

| Code | Organisme | Rôle |
|---|---|---|
| `esmap_wapp` | World Bank / ESMAP / WAPP (opérateur CSP Services) | Mesures sol de la campagne de mesure solaire en Afrique de l'Ouest ; ses stations de Dédougou, Dori, Kaya et Koupéla ne sont pas intégrées (ROADMAP, jalon 6) |
| `ecmwf_era5` | ECMWF (Copernicus C3S) | Réanalyse ERA5 au référentiel ; l'ERA5 servi ici passe par PVGIS (`era5_pvgis`) |
| `wmo_grdc`, `wwf_hydrosheds`, `iec_60041_1991`, `wmo_168_2008` | divers | Vecteur hydro structurel (schéma prévu, ingestion différée) |

`esmap_wapp` porte `fiabilite=haute` : une série `mesure_directe` de cette
source serait la première en confiance A (règle R3).

## 8. Découvrir la couverture

Les volumes (nombre de séries, de mesures) et la liste exacte des
localités couvertes dépendent du mode d'ingestion du déploiement et se
découvrent via l'API, pas via des compteurs figés dans ce document :

- `GET /v1/series` : catalogue des séries (filtres `localite`,
  `grandeur`, `source`) ; le champ `total` donne le nombre matchant les
  filtres.
- `GET /v1/localites` : référentiel géographique et hiérarchie.
- `GET /v1/grandeurs/incertitude_inter_source` : périmètre de l'atlas
  d'incertitude (points portant l'écart inter-source).
- `/docs` (OpenAPI, hors production) : schémas complets et essai
  interactif.

Faits de couverture durables (indépendants du volume ingéré) :

- Localités porteuses de séries : les 47 provinces et les 351 communes
  (350 départements et la commune de Ouagadougou).
- Granularités : journalier, mensuel, horaire.
- Mensuel : GHI NASA POWER 1991-2025, DNI et DHI 2001-2025 ; CAMS
  Radiation 2005-2025 ; SARAH-3 et ERA5 (PVGIS) 2005-2023.
- Journalier : 2005-2025 (SARAH-3 2005-2023) ; NASA POWER aux provinces
  depuis 1991 (GHI, température, humidité, pluie) ou 2001 (DNI, DHI).
- Horaire stocké : 2021-2025 aux cinq points pilotes ; relais NASA POWER
  depuis 2001.
- Atlas d'incertitude inter-source : 2005-2023.
