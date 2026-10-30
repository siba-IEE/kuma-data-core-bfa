# Démarrage rapide - API publique Kuma Data Core

Interroger les données solaires et météorologiques du Burkina Faso en quelques
minutes. L'API sert des **séries situées** : chaque valeur arrive avec sa
source, son unité, son niveau de confiance et ses mises en garde, jamais un
nombre nu.

- **Adresse** : celle du déploiement interrogé, notée `<base-url>` dans les
  exemples.
- **Format** : JSON par défaut, CSV en option (`?format=csv`) sur les séries,
  les grandeurs paramétrables et l'horaire.
- **Authentification** : `Authorization: Bearer <cle>` (clé gratuite, voir
  ci-dessous). Seuls `GET /v1/health`, `GET /v1/edition` et `POST /v1/cles`
  sont accessibles sans clé.

## 1. Vérifier que l'API répond (sans clé)

```bash
API="<base-url>"

curl "$API/v1/health"
# {"statut":"operationnel","edition":"edition_AAAAMMJJ"}

curl "$API/v1/edition"
# édition servie, date de publication, révision source, couverture
```

`edition` vaut `null`, et `/v1/edition` répond 404, sur un déploiement qui ne
sert pas d'édition publiée.

## 2. Obtenir une clé (une seule fois, gratuite)

```bash
curl -X POST "$API/v1/cles" \
  -H "Content-Type: application/json" \
  -d '{"email":"vous@exemple.org","usage_prevu":"outil de dimensionnement"}'
# {"cle":"kuma_...","prefixe":"kuma_xxxxxxxx","quota_journalier":5000}
```

La clé n'est **montrée qu'une seule fois** : conservez-la. Le `prefixe` est
son identifiant public (support, révocation). Quota par défaut :
5000 requêtes/jour.

## 3. Première requête authentifiée

```bash
CLE="kuma_..."   # votre clé

# Les séries GHI de NASA POWER à Ouagadougou (horaire, journalier, mensuel)
curl "$API/v1/series?localite=bfa_com_ouagadougou&grandeur=ghi&source=nasa_power" \
  -H "Authorization: Bearer $CLE"

# Le détail d'une série et ses mesures de 2024
curl "$API/v1/series/nasa_power_ghi_journalier_bfa_com_ouagadougou?from=2024-01-01&to=2024-12-31" \
  -H "Authorization: Bearer $CLE"
```

Cette série journalière couvre 2005-2025, soit 7 670 valeurs : sans `from`
ni `to`, la réponse s'arrête aux 1 000 premières (`limit`, au plus 10 000).

## 4. Exemples par langage

### Python

```python
import requests

API = "<base-url>"
CLE = "kuma_..."
h = {"Authorization": f"Bearer {CLE}"}

# Découvrir les séries GHI de NASA POWER à Ouagadougou
cat = requests.get(f"{API}/v1/series",
                   params={"localite": "bfa_com_ouagadougou", "grandeur": "ghi",
                           "source": "nasa_power"},
                   headers=h).json()
code = next(s["code"] for s in cat["items"] if "_journalier_" in s["code"])

# Récupérer la série et ses mesures de 2024 (chaque mesure porte son passeport)
serie = requests.get(f"{API}/v1/series/{code}",
                     params={"from": "2024-01-01", "to": "2024-12-31"},
                     headers=h).json()
print("Source :", serie["source_label"], "| unité :", serie["grandeur_unit"])
valeurs = [m["valeur"] for m in serie["mesures"]]
print("GHI moyen :", round(sum(valeurs) / len(valeurs), 2), serie["grandeur_unit"])
```

### JavaScript (navigateur ou Node)

```javascript
const API = "<base-url>";
const h = { Authorization: `Bearer ${CLE}` };

const code = "nasa_power_ghi_journalier_bfa_com_ouagadougou";
const serie = await (await fetch(`${API}/v1/series/${code}?from=2024-01-01&to=2024-12-31`, { headers: h })).json();
console.log(serie.source_label, serie.grandeur_unit, serie.mesures.length);
```

### CSV (Excel, pandas, R)

```bash
curl "$API/v1/series/nasa_power_ghi_journalier_bfa_com_ouagadougou?from=2024-01-01&to=2024-12-31&format=csv" \
  -H "Authorization: Bearer $CLE" -o ouagadougou_ghi_2024.csv
```

## 5. Endpoints principaux

| Endpoint | Rôle | Auth |
|---|---|---|
| `GET /v1/health` | Santé de l'API et édition servie | non |
| `GET /v1/edition` | Édition publiée (date, révision, couverture) | non |
| `POST /v1/cles` | Émettre une clé | non |
| `GET /v1/series` | Catalogue paginé (`localite`, `grandeur`, `source`, `limit`, `offset`) | oui |
| `GET /v1/series/{code}` | Détail d'une série et ses mesures (JSON/CSV), sauf horaire | oui |
| `GET /v1/localites` | Référentiel géographique | oui |
| `GET /v1/localites/{code}` | Détail d'une localité | oui |
| `GET /v1/grandeurs/incertitude_inter_source/{localite}` | Écarts entre sources et dégénérescence de pixel | oui |
| `GET /v1/grandeurs/<code>` | Grandeurs calculées et paramétrables (POA, productible...) | oui |
| `GET /v1/horaire/{localite}/{grandeur}` | Horaire stocké 2021-2025 (NASA POWER aux 398 localités, CAMS Radiation aux cinq points pilotes), relais NASA POWER hors de cette période et pour les autres grandeurs | oui |

Référence complète des paramètres et des réponses :
[`docs/architecture/06-api-reference-publique.md`](../architecture/06-api-reference-publique.md).

## 6. Le passeport d'une mesure

Chaque mesure d'une série porte :

- `valeur` - la valeur numérique,
- `instant_mesure` (journalier), `annee`/`mois` (mensuel) ou la période
  (`periode_type`, `annee_debut`, `annee_fin`, `mois`) d'une grandeur
  calculée - le repère temporel,
- `niveau_effectif` - le niveau de confiance (A pour une mesure sol, B pour un
  modèle satellitaire ou une réanalyse, C pour une source faible ou une
  expertise) ; toutes les séries du Burkina Faso sont en B,
- `statut` - le statut éditorial (`brut`, `valide_auto`, `publie`...).

Au niveau de la série : `source_label`, `source_url`, `grandeur_unit`,
`methode_collecte`, `periode_debut`/`periode_fin`, et un champ `notes_fr`
qui documente confiance, résolution et mises en garde.

## 7. Format d'erreur

Toutes les erreurs suivent la même enveloppe :

```json
{"erreur": {"code": "AUTH_CLE_INVALIDE", "message": "...", "details": {}}}
```

Codes stables (un code publié ne change jamais de sens) : `AUTH_*`,
`VALIDATION_*`, `RESSOURCE_*`, `CLES_*`, etc. Détail dans la référence.

## 8. Limites et bon usage

- Quota journalier par clé (défaut 5000 requêtes/jour).
- Les données sont **publiques** : la clé sert à vous identifier et à
  réguler l'usage, pas à restreindre l'accès.
- L'édition servie est datée (`GET /v1/edition`) : citez la date et la
  révision pour la reproductibilité.

## 9. Citer les données

Citez le dépôt selon son fichier [`CITATION.cff`](../../CITATION.cff), avec
l'`edition_id` et la `date_publication` renvoyés par `GET /v1/edition` pour
préciser l'état des données consultées. Les sources amont (NASA POWER,
Copernicus, PVGIS) demandent leur propre attribution : voir la section
« Sources des données » du [`README`](../../README.md).
