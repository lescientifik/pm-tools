---
description: Comprehensive analysis of all data formats, schemas, and representations used for storing, caching, and representing PubMed data in pm-tools.
---

# Data Structures Analysis: pm-tools

## 1. Formats Used

Le codebase utilise **six formats distincts** :

| Format | Role | Usage |
|--------|------|-------|
| **PubMed XML** | Input / Intermediate / Cache | `pm fetch` output, `pm parse` input, `.pm/cache/fetch/{pmid}.xml` |
| **JSONL (ArticleRecord)** | Output principal | `pm parse` output, `pm filter` I/O, `pm diff` I/O, `pm collect` output |
| **CSL-JSON** | Output (citations) | `pm cite` output, `.pm/cache/cite/{pmid}.json` |
| **Plain text (PMIDs)** | Intermediate | `pm search` output, `pm fetch` input, `pm refs` output |
| **JSON (search cache)** | Cache only | `.pm/cache/search/{hash}.json` |
| **JSONL (audit log)** | Log opérationnel | `.pm/audit.jsonl` |
| **NXML (JATS)** | Input (full-text) | `pm refs` input, extrait depuis archives PMC tgz |

## 2. Schemas et clés par format

### 2.1 ArticleRecord (schema principal, `types.py`)

Le schema canonique, défini comme `TypedDict` avec `total=False` (tous les champs optionnels sauf `pmid`) :

```python
class ArticleRecord(TypedDict, total=False):
    pmid: Required[str]           # Identifiant PubMed (toujours présent)
    title: str                    # Titre de l'article
    authors: list[AuthorName]     # Auteurs au format CSL-JSON-style
    journal: str                  # Nom complet du journal
    year: int                     # Année de publication (entier)
    date: str                     # Date ISO 8601 (YYYY, YYYY-MM, ou YYYY-MM-DD)
    abstract: str                 # Abstract en texte brut
    abstract_sections: list[AbstractSection]  # Sections labellisées
    doi: str                      # DOI
    pmcid: str                    # Identifiant PMC (ex: PMC1234567)
```

**AuthorName** (`TypedDict, total=False`) :
```python
class AuthorName(TypedDict, total=False):
    family: str    # Nom de famille
    given: str     # Prénom(s)
    suffix: str    # Ex: "Jr", "III"
    literal: str   # Noms collectifs (ex: "WHO Consortium")
```

**AbstractSection** (`TypedDict`, tous champs requis) :
```python
class AbstractSection(TypedDict):
    label: str    # Ex: "BACKGROUND", "METHODS", "RESULTS"
    text: str     # Contenu de la section
```

### 2.2 CSL-JSON (depuis NCBI Citation Exporter API)

Récupéré par `pm cite` depuis `https://pmc.ncbi.nlm.nih.gov/api/ctxp/v1/pubmed/`. Schema **opaque externe** -- pm-tools ne définit pas sa structure et le traite comme `dict`. Le seul champ accédé est `item.get("PMID", "")` pour le cache.

Cache : `.pm/cache/cite/{pmid}.json`

### 2.3 Search Cache JSON

Défini dans `search.py` :

```python
{
    "query": str,          # Requête de recherche
    "max_results": int,    # Max résultats demandés
    "pmids": list[str],    # PMIDs résultats
    "count": int,          # Nombre de PMIDs
    "timestamp": str       # ISO 8601 (YYYY-MM-DDTHH:MM:SSZ)
}
```

Clé de cache : SHA-256 de `{"query": normalized_query, "max": max_results}` + `.json`

### 2.4 Audit Log Events (6 variantes)

Tous partagent un champ `ts` (ajouté automatiquement), discriminés par `op` :

| Event | Champs spécifiques |
|-------|-------------------|
| **init** | `op: "init"` |
| **search** | `op, db, query, max, count, cached, refreshed, original_ts?` |
| **fetch** | `op, db, requested, cached, fetched, refreshed` |
| **cite** | `op, requested, cached, fetched, refreshed` |
| **filter** | `op, input, output, excluded, criteria` |
| **download** | `op, total, downloaded, skipped, failed` |

Aucun n'a de `TypedDict` -- ce sont des dicts ad-hoc.

### 2.5 Download Source Records (3 variantes, dicts ad-hoc)

```python
# Source PMC trouvée :
{"pmid": str, "source": "pmc", "url": str, "pmcid": str, "pmc_format": "pdf"|"tgz"}

# Source Unpaywall trouvée :
{"pmid": str, "source": "unpaywall", "url": str, "doi": str}

# Aucune source :
{"pmid": str, "source": None, "url": None}
```

### 2.6 Download Manifest

Écrit dans `{output_dir}/manifest.jsonl` :
```python
{"pmid": str, "source": str, "path": str}
```

### 2.7 Diff Output Records (3 variantes, dicts ad-hoc)

```python
{"pmid": str, "status": "added", "article": dict}
{"pmid": str, "status": "removed", "article": dict}
{"pmid": str, "status": "changed", "old": dict, "new": dict, "changed_fields": list[str]}
```

### 2.8 PmcResult (seul dataclass du codebase)

```python
@dataclass
class PmcResult:
    url: str
    format: Literal["pdf", "tgz"]
```

## 3. Combien de représentations distinctes ?

**Trois entités conceptuelles** ont des représentations multiples :

### 3A. "Article" -- 3 représentations

| Représentation | Source | Définition de type | Différences clés |
|----------------|--------|-------------------|------------------|
| **ArticleRecord** | `pm parse` output | `TypedDict` dans `types.py` | 10 champs, schema custom, `year` est `int` |
| **CSL-JSON** | `pm cite` output | Standard externe (opaque) | Beaucoup plus de champs, clé `PMID` (majuscule), format auteurs différent |
| **Raw PubMed XML** | `pm fetch` output | XML (`PubmedArticle`) | Source de vérité, parsé par `pm parse` |

Le champ `authors` d'ArticleRecord est intentionnellement aligné sur CSL-JSON (clés `family`/`given`/`suffix`/`literal`), mais le record global n'est **pas** du CSL-JSON.

### 3B. "Download source" -- 3 variantes (dicts ad-hoc, non typés)

### 3C. "Audit event" -- 6 variantes (dicts ad-hoc, non typés)

## 4. Opportunités d'unification

### 4.1 ArticleRecord vs CSL-JSON -- **Ne pas fusionner**

Incompatibilités structurelles :
- CSL-JSON utilise `container-title` au lieu de `journal`
- CSL-JSON utilise `issued.date-parts` au lieu de `year`/`date`
- CSL-JSON a `PMID` (majuscule) au lieu de `pmid`
- CSL-JSON n'a pas `abstract_sections`
- Proviennent d'endpoints API différents

**Verdict :** Garder séparés. ArticleRecord est le format de travail minimal (10 champs, pensé pour agents AI). CSL-JSON est un passthrough pour intégration avec des outils bibliographiques. Objectifs différents.

### 4.2 Download Source Records -- **TypedDict recommandé**

Trois variantes ad-hoc sans définition de type. Un `DownloadSource(TypedDict)` avec champs optionnels améliorerait la sécurité de type sans changer le comportement.

### 4.3 Audit Event Records -- **TypedDict recommandé**

Six variantes ad-hoc discriminées par `op`. Union de TypedDicts ou TypedDict unique avec champs optionnels. Utile si `pm audit` doit parser ces events.

### 4.4 Diff Output Records -- **TypedDict recommandé**

Trois variantes ad-hoc discriminées par `status`. Même logique que ci-dessus.

## 5. Pipeline de données

```
                          PubMed E-utilities API
                                   |
                  +----------------+----------------+
                  |                                 |
            esearch.fcgi                      efetch.fcgi
                  |                                 |
                  v                                 v
    +=============+=============+    +==============+==============+
    |         pm search         |    |          pm fetch            |
    | Query -> PMIDs            |    | PMIDs -> PubMed XML          |
    | Cache: .pm/cache/search/  |    | Cache: .pm/cache/fetch/      |
    +=============+=============+    +==============+==============+
                  |                                 |
                  +---> PMIDs (plain text) ---------+
                                                    |
                                                    v
                                  +================+================+
                                  |           pm parse              |
                                  | PubMed XML -> JSONL             |
                                  | (ArticleRecord, 10 champs)     |
                                  +================+================+
                                                    |
                                            ArticleRecord JSONL
                                                    |
                  +----------+---------+------------+----------+
                  |          |         |                        |
                  v          v         v                        v
          pm filter    pm diff   pm download              pm cite
          JSONL->JSONL  JSONL x2  JSONL->files            PMIDs->CSL-JSON
                        ->diffs                           (API séparé)

    pm collect = pm search | pm fetch | pm parse (all-in-one)
    pm refs = NXML -> PMIDs/DOIs (peut être re-pipé vers pm fetch)
```

## 6. Synthèse

| Constat | Détail |
|---------|--------|
| **1 schema bien typé** | `ArticleRecord` (+ `AuthorName`, `AbstractSection`) dans `types.py` |
| **Plusieurs schemas ad-hoc non typés** | Download sources (3), audit events (6), diff records (3), manifest, search cache |
| **2 représentations d'article** | `ArticleRecord` (custom, minimal) et CSL-JSON (standard, opaque) -- pas à fusionner |
| **1 seul dataclass** | `PmcResult` dans `download.py` |
| **Quick wins** | Ajouter des TypedDicts pour download sources, audit events, et diff records |
| **Architecture saine** | Le pipeline Unix-style est propre, chaque outil fait une seule transformation |

## Fichiers pertinents

- `src/pm_tools/types.py` -- ArticleRecord, AuthorName, AbstractSection
- `src/pm_tools/parse.py` -- Transformation XML -> ArticleRecord
- `src/pm_tools/fetch.py` -- Fetch XML, cache, merge
- `src/pm_tools/search.py` -- Search avec cache JSON
- `src/pm_tools/cache.py` -- Cache store et audit logger
- `src/pm_tools/cite.py` -- CSL-JSON citation fetching
- `src/pm_tools/download.py` -- PmcResult, source records, manifest
- `src/pm_tools/diff.py` -- Diff output records
- `src/pm_tools/filter.py` -- JSONL filtering (consomme ArticleRecord)
- `src/pm_tools/refs.py` -- Extraction de références NXML
- `src/pm_tools/cli.py` -- Orchestration pipeline (collect)
