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
| 5 | Crash-safe | Pas de corruption de données si le process est interrompu |

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

**Clé** : SHA-256 de `json.dumps({"query": q, "max": n}, sort_keys=True)`

Le format JSON structuré (plutôt que concaténation de strings) rend la clé
extensible : si on ajoute `--sort` ou `--date-range` plus tard, il suffit
d'ajouter un champ au dict sans risque de collision.

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
- Cache hit → retourne les PMIDs stockés, **affiche un avertissement sur
  stderr** avec la date du cache, log audit `"cached": true`
- Cache miss → appel API, stocke résultat, log audit `"cached": false`
- `--refresh` → ignore le cache, refait l'appel, met à jour le fichier

**Avertissement stderr lors d'un cache hit** :
```
pm: using cached search from 2026-02-12 (7 days ago). Use --refresh to update.
```

**Note PRISMA** : la date du cache est la date de la recherche originale.
Avec `--refresh`, c'est la nouvelle date. L'audit trail conserve les deux.

### 2. Fetch cache

**Clé** : PMID (un fichier XML par article)

**Valeur** : fragment XML `<PubmedArticle>...</PubmedArticle>` ou
`<PubmedBookArticle>...</PubmedBookArticle>` (les deux types existent
dans `PubmedArticleSet`)

**Comportement smart-batch** :
1. Reçoit la liste de PMIDs à fetcher
2. Vérifie lesquels sont déjà dans `.pm/cache/fetch/`
3. N'appelle l'API que pour les PMIDs manquants
4. Parse la réponse XML pour extraire chaque élément enfant de
   `<PubmedArticleSet>` (article ou book article)
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

**Stabilité des articles** : une fois publié, le XML d'un article PubMed
change rarement. Cependant, des changements arrivent :

| Type de changement | Fréquence | Impact |
|-------------------|-----------|--------|
| Rétractions | ~4000/an | Critique — article rétracté traité comme valide |
| Errata/Corrections | ~30-50k/an | Modéré — section CommentsCorrections ajoutée |
| Indexation MeSH | Chaque article | Faible — les champs extraits par pm parse ne changent pas |
| Corrections d'auteurs | Fréquent | Faible — nom, affiliation |

Pour une revue systématique finale, un `pm fetch --refresh` est recommandé
avant la soumission pour détecter les rétractions. Le cache permanent sans TTL
reste le bon défaut (reproductibilité > fraîcheur).

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

### Ordre d'écriture

**L'audit est écrit AVANT le cache.** Si le process crash entre les deux,
l'audit reflète l'opération tentée (correct) et le cache est absent (le
prochain run re-fetche — correct aussi). L'inverse (cache écrit, audit absent)
serait pire : des données sans trace.

### Événements

```jsonl
{"ts":"2026-02-19T14:30:00Z","op":"init","version":"0.2.0"}
{"ts":"2026-02-19T14:30:05Z","op":"search","db":"pubmed","query":"CRISPR cancer","max":10000,"count":1523,"cached":false}
{"ts":"2026-02-19T14:30:10Z","op":"fetch","requested":1523,"cached":0,"fetched":1523}
{"ts":"2026-02-19T14:31:00Z","op":"search","db":"pubmed","query":"gene therapy","max":10000,"count":2000,"cached":false}
{"ts":"2026-02-19T14:31:05Z","op":"fetch","requested":2000,"cached":150,"fetched":1850}
{"ts":"2026-02-19T14:32:00Z","op":"filter","input":3373,"output":1200,"criteria":{"year":"2024","has_abstract":true},"excluded":{"year":1500,"has_abstract":673}}
{"ts":"2026-02-19T14:33:00Z","op":"cite","requested":1200,"cached":0,"fetched":1200}
{"ts":"2026-02-19T14:34:00Z","op":"download","requested":1200,"downloaded":800,"skipped":0,"failed":400}
{"ts":"2026-02-20T10:00:00Z","op":"search","db":"pubmed","query":"CRISPR cancer","max":10000,"count":1530,"cached":false,"refreshed":true}
{"ts":"2026-02-21T09:00:00Z","op":"search","db":"pubmed","query":"CRISPR cancer","max":10000,"count":1530,"cached":true,"original_ts":"2026-02-20T10:00:00Z"}
```

### Champs communs

| Champ | Type | Description |
|-------|------|-------------|
| `ts` | ISO 8601 | Timestamp UTC |
| `op` | string | Opération (init, search, fetch, filter, cite, download) |
| `cached` | bool | Si les données viennent du cache |
| `refreshed` | bool | Si l'opération a été forcée avec --refresh |
| `original_ts` | ISO 8601 | Quand les données cachées ont été obtenues (cache hits seulement) |

### Champs par opération

| Op | Champs spécifiques |
|----|-------------------|
| search | db, query, max, count |
| fetch | requested, cached, fetched |
| filter | input, output, criteria, excluded |
| cite | requested, cached, fetched |
| download | requested, downloaded, skipped, failed |

Le champ `db` dans search est systématiquement `"pubmed"` aujourd'hui mais
permet l'extension future à d'autres bases (Embase, Cochrane, etc.) — requis
par PRISMA qui exige de lister toutes les bases interrogées.

Le champ `excluded` dans filter détaille les exclusions par critère. Chaque
article est compté dans le premier critère qui l'exclut (évaluation séquentielle).
Ceci est requis par PRISMA pour le diagramme de flux.

### PMIDs dans l'audit

Les PMIDs sont stockés dans les fichiers **cache search** (qui les ont déjà).
L'audit ne garde que le `count` + la clé du cache (`cache_key`). L'utilitaire
`pm audit` croise les deux pour reconstituer les listes complètes quand c'est
nécessaire (déduplication, rapport PRISMA).

## `--refresh` et audit trail

Le `--refresh` et l'audit trail ne se contredisent pas :

- **L'audit trail est l'historique** : chaque opération est enregistrée, même
  les anciennes. C'est un log append-only.
- **Le cache est l'état courant** : il contient les données les plus récentes.
  `--refresh` le met à jour.

Exemple :
```
14:30  search "CRISPR" → 1523 résultats (cache miss, stocké)
14:35  search "CRISPR" → 1523 résultats (cache hit, original_ts=14:30)
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

1. Crée `.pm/` via `os.mkdir()` (atomique — échoue si le dossier existe déjà,
   ce qui évite les race conditions entre deux agents)
2. Crée les sous-répertoires `cache/{search,fetch,cite,download}/`
3. Crée `.pm/.gitignore` (ignore `cache/`)
4. Crée `.pm/audit.jsonl` vide
5. Log l'événement `init` dans l'audit trail

### Help

```
pm init - Initialize audit trail and cache for the current directory

Usage: pm init

Creates a .pm/ directory with:
  - audit.jsonl  : append-only log of all pm operations (git-trackable)
  - cache/       : local cache of API responses (gitignored)

Use 'pm audit' to view the audit trail.
```

## `pm audit` — Rapport PRISMA

### Commande

```bash
pm audit                    # Résumé des opérations
pm audit --searches         # Liste des recherches avec dates et counts
pm audit --prisma           # Rapport PRISMA-style (identification → inclusion)
pm audit --dedup            # Analyse de déduplication entre recherches
```

### Sortie de `pm audit --prisma`

```
PRISMA 2020 Flow Summary
========================

IDENTIFICATION
  Database searches:
    PubMed "CRISPR cancer therapy" (2026-02-19)     n = 1,523
    PubMed "gene therapy oncology" (2026-02-19)     n = 2,000
  Records from databases                            n = 3,523
  Duplicates removed                                n =   150
  Records after deduplication                       n = 3,373

SCREENING
  Records screened                                  n = 3,373
  Records excluded:
    Year filter (2024)                              n = 1,500
    No abstract                                     n =   673
  Records after screening                           n = 1,200

RETRIEVAL
  Full-text articles sought                         n = 1,200
  Full-text articles obtained                       n =   800
  Not available                                     n =   400

INCLUDED
  Studies included in review                        n =   800
```

Cette sortie est calculée à partir de l'audit trail uniquement. Les nombres
sont extraits des événements search/filter/download.

### Déduplication

La déduplication est calculée en croisant les listes de PMIDs des différentes
recherches (stockées dans les fichiers cache search). `pm audit --dedup`
affiche le détail :

```
Deduplication analysis
======================
Search 1: "CRISPR cancer therapy"       1,523 PMIDs
Search 2: "gene therapy oncology"        2,000 PMIDs
                                        ------
Total (all searches)                     3,523
Unique PMIDs                             3,373
Duplicates removed                         150

Overlap matrix:
              Search 1  Search 2
Search 1          -        150
Search 2        150          -
```

## Concurrence et crash-safety

### Stratégie : pas de locks, primitives atomiques

Deux agents (ou deux terminaux) peuvent utiliser `pm` en parallèle dans le
même dossier. Plutôt qu'un mécanisme de lock (complexe, risque de deadlock,
stale locks), on s'appuie sur deux primitives POSIX atomiques :

### 1. Écritures cache : write-to-temp + `os.replace()`

```python
import os
import tempfile

def cache_write_atomic(path: Path, data: str) -> None:
    """Écriture atomique : le fichier est soit complet, soit absent."""
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        os.write(fd, data.encode())
        os.close(fd)
        os.replace(tmp, path)  # atomique sur POSIX (même filesystem)
    except BaseException:
        os.close(fd)
        os.unlink(tmp)
        raise
```

**Garantie** : un `cache_read()` concurrent voit soit l'ancien fichier complet,
soit le nouveau fichier complet. Jamais un fichier tronqué.

**Si deux agents écrivent le même fichier** : le dernier `os.replace()` gagne.
Les deux écrivent les mêmes données (même PMID → même XML), donc le résultat
est correct. Au pire, un appel API est dupliqué — acceptable.

### 2. Append audit : `O_APPEND` + `os.write()` unique

```python
import os
import json

def audit_log(pm_dir: Path, event: dict) -> None:
    """Append atomique : une ligne JSON complète ou rien."""
    if pm_dir is None:
        return
    event["ts"] = datetime.utcnow().isoformat() + "Z"
    line = json.dumps(event, ensure_ascii=False) + "\n"
    data = line.encode()
    # os.write() avec O_APPEND est atomique sur POSIX pour < PIPE_BUF (4096)
    fd = os.open(pm_dir / "audit.jsonl", os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        os.write(fd, data)
    finally:
        os.close(fd)
```

**Garantie POSIX** : `write()` avec `O_APPEND` est atomique si la taille
est ≤ `PIPE_BUF` (4096 bytes sur Linux). Nos événements font ~200-500 bytes.
Deux agents qui loggent simultanément produisent deux lignes complètes et
non-entrelacées.

### 3. Gestion des fichiers corrompus

Malgré les écritures atomiques, un crash dur (kill -9, coupure courant) peut
laisser un fichier corrompu. Politique : **cache miss gracieux**.

```python
def cache_read(pm_dir: Path, category: str, key: str) -> str | None:
    """Lecture tolérante : fichier corrompu = cache miss."""
    path = pm_dir / "cache" / category / key
    if not path.exists():
        return None
    try:
        data = path.read_text()
        # Validation minimale selon le type
        if category == "search":
            json.loads(data)  # doit être du JSON valide
        elif category == "fetch":
            ET.fromstring(data)  # doit être du XML valide
        return data
    except (json.JSONDecodeError, ET.ParseError, OSError):
        # Fichier corrompu → traiter comme cache miss, log warning
        return None
```

Pour l'audit trail, les lignes tronquées (crash mid-write) sont ignorées
silencieusement par le lecteur. Le fichier reste valide sauf la dernière ligne.

### 4. Scénarios concurrents

| Scénario | Comportement | Conséquence |
|----------|-------------|-------------|
| 2 agents font la même recherche | Les deux appellent l'API, le dernier écrit gagne | Résultat correct, un appel API dupliqué |
| 2 agents fetchent les mêmes PMIDs | Smart-batch indépendant, certains XMLs écrits 2x | Correct, quelques doublons réseau |
| 2 agents appendant l'audit | `O_APPEND` garantit pas d'entrelacement | Deux lignes correctes |
| 1 agent lit, 1 agent écrit le cache | `os.replace()` est atomique : ancien ou nouveau complet | Correct |
| `pm init` concurrent | `os.mkdir()` est atomique : un seul réussit | Le perdant voit l'erreur "already exists" |

**Philosophie** : on accepte des appels API dupliqués (rares, bénins) plutôt
que d'introduire un système de locks (complexe, fragile, stale locks).

## Bug pré-existant : fetch multi-batch

**Découvert lors de la review.** La fonction `fetch()` actuelle join les
réponses de batches multiples avec `"\n".join(results)` (fetch.py:60). Chaque
réponse est un document XML complet avec `<?xml ...>` et `<PubmedArticleSet>`.
Le résultat concaténé n'est **pas du XML valide** (plusieurs éléments racine).

`ET.fromstring()` échoue avec "junk after document element" sur les résultats
multi-batch. Cela signifie que pour toute recherche retournant >200 PMIDs,
le pipeline `pm search | pm fetch | pm parse` **perd silencieusement les
données** au-delà du premier batch.

**Ce bug doit être corrigé indépendamment du cache**, probablement en phase 0
ou au début de la phase 3. Le cache le corrige naturellement (reassemblage en
un seul `<PubmedArticleSet>`), mais le fix doit aussi marcher sans `.pm/`.

## XML splitting : points d'attention

### PubmedBookArticle

`PubmedArticleSet` peut contenir deux types d'éléments :
- `<PubmedArticle>` (articles de journaux — 99%+ des cas)
- `<PubmedBookArticle>` (GeneReviews, NCBI Bookshelf — rare mais réel)

Le splitter doit itérer sur **tous les enfants** de `<PubmedArticleSet>`,
pas seulement chercher `PubmedArticle`. L'extraction du PMID fonctionne
identiquement pour les deux types (`MedlineCitation/PMID`).

### Sérialisation des fragments

- `ET.tostring(element, encoding='unicode')` produit un fragment XML valide
- Effacer `element.tail = None` avant sérialisation (évite l'accumulation
  de whitespace inter-éléments)
- Les namespaces (`xlink:` etc.) sont rares dans PubMed XML mais seront
  propagés correctement par ElementTree (renommés en `ns0:` — sémantiquement
  équivalent)

### Round-trip test obligatoire

Test d'intégrité critique : pour chaque fixture XML existante :
```
original XML → parse → résultat A
original XML → split → cache → reassemble → parse → résultat B
assert A == B
```

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

### Phase 0 : Nettoyage et fix pré-requis

- [ ] Supprimer les tests `TestCiteBibtex` et `TestCiteRIS` de test_cite.py
- [ ] Supprimer `docs/pm-skill-plan.md`
- [ ] Fix du bug multi-batch dans `fetch()` : assembler les réponses en un
  seul `<PubmedArticleSet>` valide (TDD : écrire le test d'abord)
- [ ] Vérifier que les tests passent (3 download tests restent en échec —
  features indépendantes, 1 cite cache test — sera implémenté phase 4)

### Phase 1 : Infrastructure cache + audit

#### 1.1 — `pm init` et structure `.pm/`

**Tests** :
- `pm init` crée `.pm/cache/{search,fetch,cite,download}/` et `audit.jsonl`
- `pm init` dans un dossier avec `.pm/` existant → erreur
- `pm init` crée `.pm/.gitignore` avec `cache/`
- `pm init` log un événement `init` dans audit.jsonl
- `pm init` concurrent → un seul réussit (test avec `os.mkdir` atomique)

**Implémentation** :
- Nouveau fichier `src/pm_tools/init.py`
- Ajouter `"init"` à `SUBCOMMANDS` dans `cli.py`

#### 1.2 — Module cache store

**Tests** :
- `cache_read(pm_dir, category, key)` → None si pas de cache
- `cache_write_atomic(pm_dir, category, key, data)` → écrit le fichier
- `cache_read` après write → retourne les données
- `cache_read` sur fichier JSON corrompu → None (cache miss gracieux)
- `cache_read` sur fichier XML corrompu → None
- Catégories : "search", "fetch", "cite", "download"

**Implémentation** :
- Nouveau fichier `src/pm_tools/cache.py`
- Écritures atomiques via write-to-temp + `os.replace()`

#### 1.3 — Module audit logger

**Tests** :
- `audit_log(pm_dir, event)` append une ligne JSONL
- L'événement a automatiquement un champ `ts` (timestamp UTC)
- Fichier reste valide après plusieurs appels (une ligne JSON par append)
- `audit_log` est un no-op si `pm_dir` est None
- Append atomique : `O_APPEND` + `os.write()` single-call

**Implémentation** :
- Fonction dans `src/pm_tools/cache.py` (même module)

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
- Cache hit → avertissement stderr avec date du cache

**Implémentation** :
- Ajouter `cache_dir: Path | None = None, refresh: bool = False` à `search()`
- Normaliser la requête pour le hash
- Stocker : query, max_results, pmids, count, timestamp

#### 2.2 — Audit search

**Tests** :
- `search()` avec `pm_dir` → log dans audit.jsonl
- Événement contient : op, db, query, max, count, cached
- Cache hit → événement contient `original_ts` (date des données cachées)
- Avec `--refresh` → événement contient `refreshed: true`

**Implémentation** :
- Écrire l'audit AVANT le cache (ordre important pour crash-safety)
- Appeler `audit_log()` depuis `search()` après l'opération API/cache

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
- Gère `<PubmedBookArticle>` en plus de `<PubmedArticle>`
- Gère les cas : un seul article, plusieurs articles, XML vide
- `element.tail` est effacé avant sérialisation

**Implémentation** :
- Fonction dans `cache.py`
- Parse avec ElementTree, sérialise chaque élément enfant de PubmedArticleSet
- Itère sur TOUS les enfants (pas seulement PubmedArticle)

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
- **Round-trip test** : pour chaque fixture XML existante,
  `split → cache → reassemble → parse == parse original`

**Implémentation** :
- Wrapper `<PubmedArticleSet>` autour des fragments concaténés

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
- Événement contient `excluded` : dict des compteurs par critère d'exclusion
- Évaluation séquentielle : chaque article compté dans le premier critère
  qui l'exclut

**Implémentation** :
- `filter.main()` compte les lignes in/out par critère et log l'événement
- Pas de cache (opération locale)

### Phase 7 : Quick integration

#### 7.1 — pm quick utilise le cache

**Tests** :
- `pm quick "CRISPR"` avec `.pm/` → cache search + fetch + audit
- Deuxième appel → 0 appels réseau

**Implémentation** :
- `quick_main()` passe `cache_dir` aux fonctions sous-jacentes

### Phase 8 : `pm audit`

#### 8.1 — Commande pm audit

**Tests** :
- `pm audit` → résumé lisible des opérations
- `pm audit --searches` → liste des recherches avec dates et counts
- `pm audit --dedup` → analyse de déduplication entre recherches
- `pm audit --prisma` → rapport PRISMA 2020 complet (voir format ci-dessus)
- Lignes audit corrompues (crash) → ignorées silencieusement

**Implémentation** :
- Nouveau fichier `src/pm_tools/audit.py`
- Parse `.pm/audit.jsonl` et formate le rapport
- Croise avec les fichiers cache search pour la déduplication

## Risques et mitigations

| Risque | Impact | Mitigation |
|--------|--------|------------|
| Concurrence : 2 agents en parallèle | Appels API dupliqués | Atomicité POSIX (`os.replace`, `O_APPEND`) — pas de corruption |
| Concurrence : stale lock file | Blocage permanent | Pas de locks → pas de stale locks |
| Cache fetch : XML splitting complexe | Bugs de parsing | Tests round-trip exhaustifs sur toutes les fixtures |
| Cache fetch : PubmedBookArticle | Perte silencieuse de données | Itérer sur tous les enfants de PubmedArticleSet |
| Cache search : résultats obsolètes | Mauvaise méthodologie | Avertissement stderr + `original_ts` dans audit |
| Crash mid-write | Fichier corrompu | Écritures atomiques (temp+replace), lecture tolérante |
| Crash entre audit et cache | Inconsistance | Audit écrit AVANT le cache (audit = source de vérité) |
| Articles rétractés dans le cache | Revue systématique compromise | `--refresh` avant soumission, documentation du risque |
| .pm/ dans un repo git | Pollution du repo | `.gitignore` dans `.pm/` (cache ignoré, audit versionné) |
| Gros volume de fichiers cache | Lenteur filesystem | Acceptable pour <100k fichiers |
| Audit trail avec lignes corrompues | Crash de jq | Lecteur tolérant, skip lignes invalides |
| Bug multi-batch fetch (pré-existant) | Perte de données >200 PMIDs | Fix en phase 0 (priorité haute) |

## Fichiers à créer/modifier

| Fichier | Action | Phase |
|---------|--------|-------|
| `src/pm_tools/cache.py` | Créer — store + audit logger + split XML | 1, 3 |
| `src/pm_tools/init.py` | Créer — pm init | 1 |
| `src/pm_tools/audit.py` | Créer — pm audit | 8 |
| `src/pm_tools/cli.py` | Modifier — ajouter init et audit | 1, 8 |
| `src/pm_tools/search.py` | Modifier — cache_dir + audit | 2 |
| `src/pm_tools/fetch.py` | Modifier — fix multi-batch + cache + smart batch + audit | 0, 3 |
| `src/pm_tools/cite.py` | Modifier — cache + audit | 4 |
| `src/pm_tools/download.py` | Modifier — audit | 5 |
| `src/pm_tools/filter.py` | Modifier — audit + excluded counts | 6 |
| `tests/test_cache.py` | Créer — tests cache store + audit + split XML | 1, 3 |
| `tests/test_init.py` | Créer — tests pm init | 1 |
| `tests/test_audit.py` | Créer — tests pm audit | 8 |
| `tests/test_search.py` | Modifier — tests cache search | 2 |
| `tests/test_fetch.py` | Modifier — tests fix multi-batch + smart batch | 0, 3 |
| `tests/test_cite.py` | Modifier — tests cache cite | 4 |
| `tests/test_download.py` | Modifier — tests audit download | 5 |
| `tests/test_filter.py` | Modifier — tests audit filter + excluded | 6 |
