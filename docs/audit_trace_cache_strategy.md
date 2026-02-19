# Audit Trail & Cache Strategy

## Problème

Chaque appel `pm search`, `pm fetch`, `pm cite`, `pm download` fait un appel
réseau à l'API NCBI. Aucun résultat n'est conservé localement. Conséquences :

1. **Doublons réseau** : relancer la même recherche refait les mêmes appels
2. **Pas de traçabilité** : impossible de reconstituer quelles recherches ont
   produit quels articles (requis pour la méthodologie PRISMA)
3. **Pas de reproductibilité** : les résultats d'une recherche PubMed changent
   chaque jour (nouveaux articles indexés)

## Objectifs

| # | Objectif | Mesure de succès |
|---|----------|------------------|
| 1 | Zéro appel réseau redondant | Même pipeline relancé 2x → 0 appels API au 2e run |
| 2 | Audit trail PRISMA-compatible | Un fichier lisible suffit pour écrire la section méthodologie |
| 3 | Transparent pour l'agent | Aucun flag supplémentaire nécessaire après `pm init` |
| 4 | `--refresh` pour forcer un re-fetch | Sans casser l'audit trail (append-only) |

## Architecture

### Vue d'ensemble

```
pm init                          ← crée .pm/ (comme git init)
    ↓
pm search "CRISPR" --max 100     ← cache + audit automatiques si .pm/ existe
    ↓
pm fetch                         ← ne fetch que les PMIDs non cachés
    ↓
pm parse                         ← pas de cache (CPU-only, pas d'API)
    ↓
pm filter --year 2024            ← pas de cache, mais audit (PRISMA screening)
    ↓
pm cite                          ← cache CSL-JSON par PMID
    ↓
pm download                      ← les PDFs eux-mêmes sont le cache
```

### Principe de transparence

```
Sans .pm/  →  comportement identique à aujourd'hui (aucun changement)
Avec .pm/  →  cache + audit automatiques, invisible pour l'appelant
```

Le seul flag ajouté est `--refresh` (opt-in, pour forcer un re-fetch).

## Structure `.pm/`

```
.pm/
├── cache/
│   ├── search/              # Un fichier par requête
│   │   └── <sha256>.json    # {query, max, pmids[], timestamp}
│   ├── fetch/               # Un fichier par article
│   │   └── <pmid>.xml       # Fragment XML <PubmedArticle>...</PubmedArticle>
│   ├── cite/                # Un fichier par article
│   │   └── <pmid>.json      # CSL-JSON d'un seul article
│   └── download/            # Métadonnées des téléchargements
│       └── <pmid>.json      # {source, url, path, status, timestamp}
├── audit.jsonl              # Log append-only de toutes les opérations
└── .gitignore               # Ignore cache/, garde audit.jsonl
```

### Contenu de `.pm/.gitignore`

```
cache/
```

Cela permet de versionner `audit.jsonl` (léger, critique pour la traçabilité)
sans versionner le cache (potentiellement volumineux).

## Cache par couche

### 1. Search cache

**Clé** : SHA-256 de `f"{query_normalisée}|{max_results}"`

**Normalisation** : strip + collapse whitespace (pas de lowercase — PubMed
a ses propres règles de case-sensitivity selon les champs)

**Valeur** (JSON) :
```json
{
  "query": "CRISPR cancer therapy",
  "max_results": 10000,
  "pmids": ["39876543", "39876542", "..."],
  "count": 1523,
  "timestamp": "2026-02-19T14:30:00Z"
}
```

**Comportement** :
- Cache hit → retourne les PMIDs stockés, log audit `"cached": true`
- Cache miss → appel API, stocke résultat, log audit `"cached": false`
- `--refresh` → ignore le cache, refait l'appel, met à jour le fichier

**Note PRISMA** : la date du cache est la date de la recherche originale.
Avec `--refresh`, c'est la nouvelle date. L'audit trail conserve les deux.

### 2. Fetch cache

**Clé** : PMID (un fichier XML par article)

**Valeur** : fragment XML `<PubmedArticle>...</PubmedArticle>`

**Comportement smart-batch** :
1. Reçoit la liste de PMIDs à fetcher
2. Vérifie lesquels sont déjà dans `.pm/cache/fetch/`
3. N'appelle l'API que pour les PMIDs manquants
4. Parse la réponse XML pour extraire chaque `<PubmedArticle>`
5. Cache chaque article individuellement
6. Reassemble tous les articles (cachés + frais) dans un `<PubmedArticleSet>`

**Reassemblage** :
```xml
<?xml version="1.0" ?>
<!DOCTYPE PubmedArticleSet PUBLIC "-//NLM//DTD PubMedArticle, 1st January 2024//EN"
  "https://dtd.nlm.nih.gov/ncbi/pubmed/out/pubmed_240101.dtd">
<PubmedArticleSet>
  <!-- articles cachés + articles frais, dans l'ordre des PMIDs demandés -->
</PubmedArticleSet>
```

**Pourquoi par PMID** : une recherche pour "CRISPR" et une pour "gene therapy"
peuvent retourner des PMIDs en commun. Le cache par PMID évite de re-fetcher
ces articles partagés.

**Stabilité** : une fois publié, le XML d'un article PubMed ne change
quasiment jamais (sauf errata). Le cache est donc fiable sans TTL.

### 3. Cite cache

**Clé** : PMID

**Valeur** : CSL-JSON (un objet JSON par fichier)

**Comportement** : identique au fetch cache (smart-batch, ne fetch que les
PMIDs non cachés).

### 4. Download cache

**Clé** : PMID

**Valeur** : métadonnées (le PDF lui-même est déjà sur disque)
```json
{
  "pmid": "12345678",
  "source": "pmc",
  "url": "https://...",
  "path": "./pdfs/12345678.pdf",
  "status": "downloaded",
  "timestamp": "2026-02-19T15:00:00Z"
}
```

Le fichier PDF dans `output_dir/` sert de cache naturel (logique de skip
si le fichier existe déjà, déjà implémentée).

### 5. Parse / Filter — pas de cache

Ces commandes sont CPU-only (pas d'appel réseau). Pas de cache nécessaire.
Mais elles sont logguées dans l'audit trail pour la traçabilité PRISMA.

## Audit Trail

### Format

Fichier `.pm/audit.jsonl` — append-only, un événement JSON par ligne.

### Événements

```jsonl
{"ts":"2026-02-19T14:30:00Z","op":"init","version":"0.2.0"}
{"ts":"2026-02-19T14:30:05Z","op":"search","query":"CRISPR cancer","max":10000,"count":1523,"cached":false}
{"ts":"2026-02-19T14:30:10Z","op":"fetch","requested":1523,"cached":0,"fetched":1523}
{"ts":"2026-02-19T14:31:00Z","op":"search","query":"gene therapy","max":10000,"count":2000,"cached":false}
{"ts":"2026-02-19T14:31:05Z","op":"fetch","requested":2000,"cached":150,"fetched":1850}
{"ts":"2026-02-19T14:32:00Z","op":"filter","input":3373,"output":1200,"criteria":{"year":"2024","has_abstract":true}}
{"ts":"2026-02-19T14:33:00Z","op":"cite","requested":1200,"cached":0,"fetched":1200}
{"ts":"2026-02-19T14:34:00Z","op":"download","requested":1200,"downloaded":800,"skipped":0,"failed":400}
{"ts":"2026-02-20T10:00:00Z","op":"search","query":"CRISPR cancer","max":10000,"count":1530,"cached":false,"refreshed":true}
```

### Champs communs

| Champ | Type | Description |
|-------|------|-------------|
| `ts` | ISO 8601 | Timestamp UTC |
| `op` | string | Opération (init, search, fetch, filter, cite, download) |
| `cached` | bool | Si les données viennent du cache |
| `refreshed` | bool | Si l'opération a été forcée avec --refresh |

### Champs par opération

| Op | Champs spécifiques |
|----|-------------------|
| search | query, max, count, pmids (optionnel, peut être gros) |
| fetch | requested, cached, fetched |
| filter | input, output, criteria |
| cite | requested, cached, fetched |
| download | requested, downloaded, skipped, failed |

### PRISMA : reconstitution de la méthodologie

L'audit trail permet de reconstituer le flow PRISMA avec `jq` :

```bash
# Date et résultats de chaque recherche
jq 'select(.op=="search")' .pm/audit.jsonl

# Nombre total d'articles identifiés (toutes recherches)
jq -s '[.[] | select(.op=="search")] | map(.count) | add' .pm/audit.jsonl

# Résultats après filtrage
jq 'select(.op=="filter") | {input, output, criteria}' .pm/audit.jsonl

# Taux de téléchargement
jq 'select(.op=="download")' .pm/audit.jsonl
```

### Question ouverte : stocker les PMIDs dans l'audit ?

Pour PRISMA, on pourrait vouloir la liste exacte de PMIDs retournés par chaque
recherche (pour calculer la déduplication entre recherches). Mais ça alourdit
le fichier.

**Proposition** : stocker les PMIDs dans le fichier cache search (qui les a
déjà), et dans l'audit ne garder que le count + un hash de la liste. Un
utilitaire `pm audit --detail` pourrait croiser les deux pour le rapport final.

## `--refresh` et audit trail

Le `--refresh` et l'audit trail ne se contredisent pas :

- **L'audit trail est l'historique** : chaque opération est enregistrée, même
  les anciennes. C'est un log append-only.
- **Le cache est l'état courant** : il contient les données les plus récentes.
  `--refresh` le met à jour.

Exemple :
```
14:30  search "CRISPR" → 1523 résultats (cache miss, stocké)
14:35  search "CRISPR" → 1523 résultats (cache hit)
...3 mois plus tard...
14:30  search "CRISPR" --refresh → 1580 résultats (cache mis à jour)
```

L'audit trail contient les 3 événements. Le cache ne contient que 1580.
Pour PRISMA, la date pertinente est celle du `--refresh` (ou de la première
recherche si pas de refresh).

## `pm init`

### Comportement

```bash
$ pm init
Initialized .pm/ in /home/user/my-review/
Audit trail: .pm/audit.jsonl
Cache: .pm/cache/

$ pm init
Error: .pm/ already exists in /home/user/my-review/
```

### Ce qu'il fait

1. Crée `.pm/` et ses sous-répertoires
2. Crée `.pm/.gitignore` (ignore `cache/`)
3. Crée `.pm/audit.jsonl` vide
4. Log l'événement `init` dans l'audit trail

### Help

```
pm init - Initialize audit trail and cache for the current directory

Usage: pm init

Creates a .pm/ directory with:
  - audit.jsonl  : append-only log of all pm operations (git-trackable)
  - cache/       : local cache of API responses (gitignored)

Use 'pm audit' to view the audit trail.
```

## `pm audit` (optionnel, phase tardive)

Un utilitaire pour consulter l'audit trail sans `jq` :

```bash
pm audit                    # Résumé des opérations
pm audit --searches         # Liste des recherches avec dates et counts
pm audit --prisma           # Rapport PRISMA-style
pm audit --dedup            # Analyse de déduplication entre recherches
```

Peut être implémenté en dernier ou pas du tout (jq suffit).

## Impact sur les tests existants qui fail

### Test `TestCiteCache` (test_cite.py)

Ce test attend un paramètre `cache_dir` sur `cite()`. Notre design utilise
la détection de `.pm/` au niveau CLI, pas un paramètre explicite.

**Décision** : adapter le test pour refléter le design réel. Le `cite()`
acceptera un `cache_dir: Path | None = None` optionnel. Le CLI le peuplera
automatiquement si `.pm/` existe.

### Tests download (manifest, verify_pdf, concurrent)

- **Manifest** : supersédé par l'audit trail (`.pm/audit.jsonl` tracke déjà
  les downloads). Peut être supprimé ou réécrit pour tester l'audit.
- **Verify PDF** : feature indépendante du cache/audit, à évaluer séparément.
- **Concurrent downloads** : feature indépendante du cache/audit, à évaluer
  séparément.

## Plan d'implémentation TDD

### Phase 0 : Nettoyage

- [ ] Supprimer les tests `TestCiteBibtex` et `TestCiteRIS` de test_cite.py
- [ ] Supprimer `docs/pm-skill-plan.md`
- [ ] Vérifier que les 163 tests restants passent (3 download tests restent en
  échec — features indépendantes)

### Phase 1 : Infrastructure cache + audit

#### 1.1 — `pm init` et structure `.pm/`

**Tests** :
- `pm init` crée `.pm/cache/{search,fetch,cite,download}/` et `audit.jsonl`
- `pm init` dans un dossier avec `.pm/` existant → erreur
- `pm init` crée `.pm/.gitignore` avec `cache/`
- `pm init` log un événement `init` dans audit.jsonl

**Implémentation** :
- Nouveau fichier `src/pm_tools/init.py`
- Ajouter `"init"` à `SUBCOMMANDS` dans `cli.py`

#### 1.2 — Module cache store

**Tests** :
- `cache_read(category, key)` → None si pas de cache
- `cache_write(category, key, data)` → écrit le fichier
- `cache_read(category, key)` après write → retourne les données
- Catégories : "search", "fetch", "cite", "download"
- Les données sont du texte brut (XML, JSON)

**Implémentation** :
- Nouveau fichier `src/pm_tools/cache.py`
- API simple : `cache_read(pm_dir, category, key) → str | None`
- API simple : `cache_write(pm_dir, category, key, data: str) → Path`

#### 1.3 — Module audit logger

**Tests** :
- `audit_log(pm_dir, event)` append une ligne JSONL
- L'événement a automatiquement un champ `ts` (timestamp UTC)
- Fichier reste valide après plusieurs appels (une ligne JSON par append)
- `audit_log` est un no-op si `pm_dir` est None

**Implémentation** :
- Fonction dans `src/pm_tools/cache.py` (même module)
- Append atomique (open + write + flush)

#### 1.4 — Détection `.pm/` dans le CLI

**Tests** :
- `find_pm_dir()` → Path si `.pm/` existe dans le CWD
- `find_pm_dir()` → None si pas de `.pm/`

**Implémentation** :
- Fonction utilitaire dans `cache.py`
- Chaque commande CLI l'appelle au démarrage

### Phase 2 : Search cache + audit

#### 2.1 — Cache search

**Tests** :
- `search()` avec `cache_dir` → stocke le résultat dans `cache/search/`
- Deuxième appel identique → retourne le cache, 0 appels réseau
- Requêtes différentes → fichiers cache différents
- `--refresh` → bypass le cache, met à jour le fichier

**Implémentation** :
- Ajouter `cache_dir: Path | None = None, refresh: bool = False` à `search()`
- Normaliser la requête pour le hash
- Stocker : query, max_results, pmids, count, timestamp

#### 2.2 — Audit search

**Tests** :
- `search()` avec `pm_dir` → log dans audit.jsonl
- Événement contient : op, query, max, count, cached
- Avec `--refresh` → événement contient `refreshed: true`

**Implémentation** :
- Appeler `audit_log()` depuis `search()` après l'opération

#### 2.3 — CLI search integration

**Tests** :
- `pm search "CRISPR"` avec `.pm/` → utilise le cache automatiquement
- `pm search --refresh "CRISPR"` → force un re-fetch
- `pm search "CRISPR"` sans `.pm/` → comportement inchangé

**Implémentation** :
- `search.main()` détecte `.pm/`, passe `cache_dir` et `refresh` à `search()`
- Ajouter `--refresh` à l'argument parser

### Phase 3 : Fetch cache + audit

#### 3.1 — XML splitting

**Tests** :
- `split_xml_articles(xml_string)` → dict[pmid, xml_fragment]
- Chaque fragment est un `<PubmedArticle>` complet et valide
- Gère les cas : un seul article, plusieurs articles, XML vide

**Implémentation** :
- Fonction dans `fetch.py` ou `cache.py`
- Parse avec ElementTree, sérialise chaque élément

#### 3.2 — Smart batching

**Tests** :
- 10 PMIDs dont 3 déjà cachés → seulement 7 fetchés via API
- Tous cachés → 0 appels API
- Aucun caché → appel API normal

**Implémentation** :
- `fetch()` vérifie le cache avant de constituer les batches
- Ne met dans les batches API que les PMIDs non cachés

#### 3.3 — XML reassembly

**Tests** :
- Articles cachés + articles frais → XML valide combiné
- L'ordre des articles dans le XML correspond à l'ordre des PMIDs demandés
- Le XML résultant est parseable par `pm parse`

**Implémentation** :
- Wrapper `<PubmedArticleSet>` autour des fragments concaténés
- Round-trip test : split → cache → reassemble → parse = mêmes données

#### 3.4 — Audit fetch

**Tests** :
- Fetch avec `.pm/` → log requested, cached, fetched dans audit.jsonl
- 10 demandés, 3 cachés, 7 fetchés → `{"requested":10,"cached":3,"fetched":7}`

#### 3.5 — CLI fetch integration

- `pm fetch` avec `.pm/` → cache transparent
- `pm fetch --refresh` → re-fetch tout
- Sans `.pm/` → inchangé

### Phase 4 : Cite cache + audit

#### 4.1 — Cache cite par PMID

**Tests** :
- `cite()` avec `cache_dir` → stocke chaque CSL-JSON par PMID
- Deuxième appel avec les mêmes PMIDs → 0 appels réseau
- Mix cachés/non cachés → smart batching

**Implémentation** :
- Pattern identique à fetch cache
- Stocker un fichier JSON par PMID dans `cache/cite/`

#### 4.2 — Audit cite + CLI integration

- Événement audit avec requested/cached/fetched
- `--refresh` flag sur `pm cite`

### Phase 5 : Download audit

#### 5.1 — Audit download

**Tests** :
- Download avec `.pm/` → log dans audit.jsonl
- Événement contient : requested, downloaded, skipped, failed
- Métadonnées stockées dans `cache/download/<pmid>.json`

**Implémentation** :
- Le PDF sur disque est le cache (logique skip existante)
- `cache/download/` stocke les métadonnées pour le rapport PRISMA

### Phase 6 : Filter audit (PRISMA screening)

#### 6.1 — Audit filter

**Tests** :
- `pm filter` avec `.pm/` → log input count, output count, critères
- Événement : `{"op":"filter","input":1523,"output":800,"criteria":{...}}`

**Implémentation** :
- `filter.main()` compte les lignes in/out et log l'événement
- Pas de cache (opération locale)

### Phase 7 : Quick integration

#### 7.1 — pm quick utilise le cache

**Tests** :
- `pm quick "CRISPR"` avec `.pm/` → cache search + fetch + audit
- Deuxième appel → 0 appels réseau

**Implémentation** :
- `quick_main()` passe `cache_dir` aux fonctions sous-jacentes

### Phase 8 (optionnelle) : `pm audit`

#### 8.1 — Commande pm audit

**Tests** :
- `pm audit` → résumé lisible des opérations
- `pm audit --searches` → liste des recherches
- `pm audit --prisma` → rapport type PRISMA (identification → screening)

**Implémentation** :
- Nouveau fichier `src/pm_tools/audit.py`
- Parse `.pm/audit.jsonl` et formate le rapport

## Risques et mitigations

| Risque | Impact | Mitigation |
|--------|--------|------------|
| Cache fetch : XML splitting complexe | Peut introduire des bugs de parsing | Tests round-trip exhaustifs (split → reassemble → parse = original) |
| Cache search : même query, résultats différents | Confond la reproductibilité | Le cache freeze le résultat. --refresh pour mettre à jour |
| .pm/ dans un repo git | Pollution du repo | .gitignore dans .pm/ (cache ignoré, audit versionné) |
| Gros volume de fichiers cache | Lenteur filesystem | Acceptable pour <100k fichiers. Si besoin, ajouter des sous-dossiers |
| Audit trail trop verbeux | Fichier illisible | Garder les événements concis, détails dans le cache |

## Fichiers à créer/modifier

| Fichier | Action | Phase |
|---------|--------|-------|
| `src/pm_tools/cache.py` | Créer — store + audit logger | 1 |
| `src/pm_tools/init.py` | Créer — pm init | 1 |
| `src/pm_tools/cli.py` | Modifier — ajouter init (et audit) | 1, 8 |
| `src/pm_tools/search.py` | Modifier — cache_dir + audit | 2 |
| `src/pm_tools/fetch.py` | Modifier — cache + smart batch + audit | 3 |
| `src/pm_tools/cite.py` | Modifier — cache + audit | 4 |
| `src/pm_tools/download.py` | Modifier — audit | 5 |
| `src/pm_tools/filter.py` | Modifier — audit | 6 |
| `src/pm_tools/audit.py` | Créer — pm audit (optionnel) | 8 |
| `tests/test_cache.py` | Créer — tests cache store + audit | 1 |
| `tests/test_init.py` | Créer — tests pm init | 1 |
| `tests/test_search.py` | Modifier — tests cache search | 2 |
| `tests/test_fetch.py` | Modifier — tests smart batch | 3 |
| `tests/test_cite.py` | Modifier — tests cache cite | 4 |
| `tests/test_download.py` | Modifier — tests audit download | 5 |
| `tests/test_filter.py` | Modifier — tests audit filter | 6 |
