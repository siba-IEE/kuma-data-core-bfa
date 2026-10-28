# Conventions transverses projet

**Statut** : fichier méthodologie consolidé, mis à jour lorsqu'une nouvelle convention transverse apparaît ou que le statut d'une convention existante change.

## 1. Scope et finalité

Ce fichier consolide les **conventions transverses** identifiées au fil du projet. Une convention transverse est un pattern observé empiriquement sur plusieurs cas, candidat à devenir une règle projet, mais sans engagement de promotion automatique.

Les conventions transverses complètent les autres registres méthodologie : les garde-fous (règles de processus obligatoires, issues d'erreurs empiriques payées ou de patterns confirmés) et les décisions techniques (règles de codage ou de structure spécifiques à un type de source ou de schéma de données).

| Registre | Nature | Mode d'enforcement |
|---|---|---|
| Garde-fou | Méthodologique (règle de processus) | Vérification systématique avant figement |
| Décision technique | Technique-décisionnelle (règle de codage ou structure) | Application en écriture seed et fiches sources |
| Convention transverse | Pattern observé sans portée généralisable confirmée | Aucun enforcement systématique, registre descriptif |

---

## 2. Distinction des sous-cas pérennes

Les conventions du présent registre sont classées en deux sous-cas selon leur nature :

### Sous-cas descriptif

Pattern observé sur un cas singulier sans portée généralisable, **ou** observation factuelle dépendante d'un comportement éditeur tiers (sans engagement projet à formaliser une règle). Trace historique projet, sans application systématique attendue.

### Sous-cas d'application

Trace empirique de l'application concrète d'un garde-fou ou d'une décision technique existante sur un ensemble de cas, à valeur de confirmation transverse. Confirme l'opérationnalité d'une règle existante sans en introduire une nouvelle.

---

## 3. Politique de promotion

Une convention transverse peut suivre trois trajectoires possibles :

- **Promotion en garde-fou** : si la convention est méthodologique et confirmée par un second cas.
- **Promotion en décision technique** : si la convention est technique-décisionnelle.
- **Conservation pérenne** : si la convention n'est ni méthodologique généralisable ni technique-décisionnelle (sous-cas descriptif ou d'application).

---

## 4. Conventions actées sur le premier lot de sources

### Ordre de tutelle dans le code des sources

**Sous-cas** : d'application

**Énoncé** : *Le code d'une source retient la tutelle internationale lorsqu'elle existe, sinon le producteur scientifique ou administratif national.*

**Cas testés** (énumération exhaustive) :
- Tutelle internationale (organisation intergouvernementale) : WMO sur `wmo_8_2024`, `wmo_grdc`, `wmo_168_2008` ; IEC sur `iec_61724_1_2021`, `iec_60041_1991` ; ECMWF sur `ecmwf_era5` (organisation intergouvernementale européenne, 32 États membres et coopérants)
- ONG internationale (sans mandat intergouvernemental) : WWF sur `wwf_hydrosheds` (n'est pas une organisation intergouvernementale au sens strict)
- Producteur national : NASA sur `nasa_power` (agence fédérale américaine)
- Opérateur technique masqué au profit de la tutelle : BfG sur `wmo_grdc` (opérateur technique sous mandat WMO, non retenu dans le code au profit de la tutelle WMO)

### Observation factuelle sur les DOI WMO post-2018

**Sous-cas** : descriptive

**Énoncé** : *L'éditeur WMO a adopté une pratique de DOIfication systématique de ses publications-guides à partir de 2018. Les guides récents portent un DOI canonique (ex. WMO-No.8 CIMO Guide 2024 : DOI `10.59327/WMO/CIMO/1`). Les éditions antérieures à 2018 ne portent généralement pas de DOI (ex. WMO-No.168 Vol I 2008 : DOI NULL). Les bases de données opérationnelles WMO (ex. GRDC) ne portent pas non plus de DOI (la base elle-même n'est pas une publication-guide).*

**Cas testés** (énumération exhaustive) :
- DOI présent (publication-guide post-2018) : `wmo_8_2024` (DOI `10.59327/WMO/CIMO/1`)
- DOI NULL (édition antérieure à 2018) : `wmo_168_2008` (Volume I 2008, antérieur à la pratique DOI)
- DOI NULL (base opérationnelle, pas publication-guide) : `wmo_grdc`

**Statut** : cette convention dépend d'un comportement éditeur tiers (WMO) qui peut évoluer.

### Couverture bifurquée NASA POWER

**Sous-cas** : descriptive

**Énoncé** : *La source NASA POWER a une couverture temporelle bifurquée selon la communauté de paramètres : météorologie 1981-01-01 -> présent (source amont MERRA-2), solaire 1984-01-01 -> présent (sources amont SRB 4.0-IP puis CERES SYN1deg + FLASHFlux). La valeur retenue dans le champ JSONB `couverture_temporelle_debut` est 1984-01-01 (valeur effective pour le focus solaire), la bifurcation est documentée en notes.*

**Cas testé** : `nasa_power`.

**Statut** : pattern singulier à NASA POWER, mention pour trace si un futur cas similaire émerge (typiquement source multi-vecteurs avec couvertures temporelles distinctes par paramètre).

---

## 5. Séparation calcul et lecture dans `services/grandeurs/`

**Sous-cas** : descriptive - pattern observé sur les neuf modules de calcul à la volée, sans dérogation.

**Énoncé** : Un module `src/kuma_data_core/services/grandeurs/<grandeur>.py` ne contient que des fonctions pures. Elles prennent des séquences de mesures (`TypedDict`), ou des séries pandas pour le calcul horaire, et les paramètres de la requête (modèles Pydantic), et rendent des modèles Pydantic ou des valeurs simples. Aucun argument `Session`, aucun accès à la base. La route de `/v1/grandeurs` lit la série source et ses compagnes, appelle le module et assemble la réponse. Les grandeurs dérivées gardées en base ne passent pas par ces modules : la migration 0009 calcule en SQL la fraction diffuse et les écarts entre sources, la migration 0014 la dégénérescence de pixel.

**Tests attendus** : tests unitaires des fonctions pures, sans base ni mock de session ; tests d'intégration des routes sur la base (`tests/integration/api/test_grandeurs_bfa.py`, `test_horaire_bfa.py`).

**Cas testés** (énumération exhaustive) : `poa_parametrable.py`, `poa_bifacial.py`, `productible_correction_thermique.py`, `productible_pr_fourni.py`, `energie_utile_ecs.py`, `degre_jour_climatisation.py`, `ghi_exceedance.py`, `soiling_hsu.py`, `pr_realiste.py`.

---

## 6. Schéma de réponse Pydantic typé obligatoire

**Sous-cas** : d'application.

**Énoncé** : Tout endpoint FastAPI introduit dans le code source expose un `response_model` Pydantic typé. Les schémas de réponse sont déclaratifs, versionnés et exposés via le snapshot OpenAPI consommé par les clients.

Dix endpoints n'exposent pas de schéma de réponse et constituent une dette technique formalisée : huit en `response_model=None` (catalogue détail `/v1/series/{code_serie}` ; horaire `/v1/horaire/{localite}/{grandeur}` ; six endpoints paramétrables sous `/v1/grandeurs/*` : `poa_parametrable`, `poa_bifacial`, `productible_correction_thermique`, `productible_pr_fourni`, `energie_utile_ecs`, `degre_jour_climatisation`) et deux qui renvoient une `Response` sans schéma (retrait d'une contribution `POST /v1/contributions/{etude_uid}/retrait` ; capsule d'étude `/v1/etudes/capsule`). Le listing `/v1/series` a été typé `SerieListeePaginee` lors de l'enrichissement du contrat, entamant partiellement la résorption ; la convention s'applique strictement à tout nouvel endpoint.

**Cas testés** (énumération exhaustive, dix endpoints sans schéma de réponse à date) :

- `/v1/series/{code_serie}` - dualité format `json|csv` via `JSONResponse` directe.
- `/v1/grandeurs/poa_parametrable` - idem.
- `/v1/grandeurs/poa_bifacial` - idem.
- `/v1/grandeurs/productible_correction_thermique` - idem.
- `/v1/grandeurs/productible_pr_fourni` - idem.
- `/v1/grandeurs/energie_utile_ecs` - idem.
- `/v1/grandeurs/degre_jour_climatisation` - idem.
- `/v1/horaire/{localite}/{grandeur}` - idem.
- `POST /v1/contributions/{etude_uid}/retrait` - réponse 204 sans corps.
- `/v1/etudes/capsule` - texte brut (`Response`, `text/plain`).

**Origine** : un client consommateur avait reconstitué manuellement les schémas runtime pour les endpoints `response_model=None`, créant un couplage permanent non détectable par le snapshot OpenAPI. Le retour empirique acte la nécessité d'une convention explicite d'exposition typée des schémas de réponse, indépendante de la mécanique FastAPI sous-jacente.

---

## 7. Évolution du registre

Le présent fichier est mis à jour lorsqu'une nouvelle convention transverse apparaît ou que le statut d'une convention existante change. Certaines conventions identifiées initialement ont depuis été promues en décision technique et ne figurent plus dans ce registre : l'année dans le code des sources éditées, le scope du Volume I des sources WMO multi-volumes, le traitement de l'ISBN des normes IEC au cas par cas, et la convention d'acknowledgement.

---

**Fin du registre des conventions transverses projet.**
