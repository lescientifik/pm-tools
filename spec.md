# PubMed CLI Tool - Spécifications

## Pourquoi ce projet ?

**EDirect/xtract existe** (outil officiel NCBI), mais :

| Besoin | EDirect | pm-tools |
|--------|---------|----------|
| Gros volumes (35M articles) | ❌ Charge en mémoire (Perl) | ✅ Streaming (xml2 + awk) |
| Workflow fréquent | ❌ Syntaxe XPath à mémoriser | ✅ Zéro config |
| Pipeline data | ❌ Output TSV | ✅ JSONL natif (jq-ready) |
| Lisibilité | ❌ Perl obfusqué | ✅ Shell simple |

**Notre outil** : interface simplifiée + streaming + JSONL, en réutilisant EDirect comme oracle de test.

## Philosophie
- Outil Unix : fait une chose et la fait bien
- Compatible pipes (`|`)
- Performance : I/O bound (réseau/disque comme seul goulot d'étranglement)
- Réutilisation maximale des outils Unix existants

## Décisions prises

### Cas d'usage
- [x] Pipeline complet : recherche → téléchargement → parsing → extraction

### Langage / Implémentation
- [x] Shell + outils Unix existants (curl, jq, xmlstarlet, parallel, etc.)
- Avantages : simplicité, composabilité native, pas de compilation
- Le script orchestre, les outils spécialisés font le travail

### Format de sortie
- [x] JSON Lines (JSONL) - un objet JSON par ligne
- Compatible avec `jq` pour le post-traitement
- Streamable, pas besoin de charger tout en mémoire

### API
- [x] Sans clé API (3 requêtes/seconde max)
- Rate limiting à gérer dans le script

### Architecture
- [x] Plusieurs outils indépendants, composables via pipes :
  - `pubmed-search` : requête → liste de PMIDs (un par ligne)
  - `pubmed-fetch` : PMIDs → XML PubMed (streaming)
  - `pubmed-parse` : XML → JSONL (un article par ligne)

### Champs extraits
- [x] PMID, titre, auteurs, journal, date, DOI + abstract complet

### Stratégie de volume
- [x] Hybride :
  - Fetch : batching (jusqu'à 10k PMIDs par requête API)
  - Parse : streaming article par article

### Cache
- [x] Pas de cache local (simplicité)

### Gestion des erreurs
- [x] Pas de retry automatique (fail immédiat, l'utilisateur relance)
- Simple et prévisible

### Logging
- [x] Silencieux par défaut, `--verbose` pour les logs sur stderr

### Parser XML
- [x] `xml2` : convertit XML en format path=value, streaming natif
- Pipeline : `xml2 | awk/grep | jq` pour construire le JSONL
- Dépendance : package `xml2` (Debian/Ubuntu : `apt install xml2`)

### Nommage
- [x] Préfixe `pm-` (court, rapide à taper)
- `pm-search`, `pm-fetch`, `pm-parse`

## Décisions finalisées ✓

---

## Exemples d'usage

```bash
# Recherche simple → liste de PMIDs
pm-search "CRISPR cancer therapy" > pmids.txt

# Pipeline complet : recherche → fetch → parse → filtrer
pm-search "CRISPR 2024" | pm-fetch | pm-parse | jq 'select(.journal == "Nature")'

# Depuis un fichier de PMIDs
cat pmids.txt | pm-fetch | pm-parse > articles.jsonl

# Compter les articles par journal
pm-search "machine learning" | pm-fetch | pm-parse | jq -r '.journal' | sort | uniq -c | sort -rn

# Extraire juste les titres
pm-search "covid vaccine" | pm-fetch | pm-parse | jq -r '.title'

# Verbose pour debug
pm-search --verbose "rare disease" 2>debug.log | pm-fetch | pm-parse
```

---

## Spécifications techniques

### `pm-search`
- **Entrée** : requête PubMed (argument ou stdin)
- **Sortie** : un PMID par ligne sur stdout
- **API** : E-utilities esearch
- **Options** :
  - `--max N` : limite le nombre de résultats (défaut: 10000)
  - `--verbose` : logs sur stderr

### `pm-fetch`
- **Entrée** : PMIDs (un par ligne sur stdin)
- **Sortie** : XML PubMed brut sur stdout
- **API** : E-utilities efetch (format=xml, rettype=abstract)
- **Batching** : groupe jusqu'à 200 PMIDs par requête
- **Rate limit** : 3 req/sec (sans API key)
- **Options** :
  - `--verbose` : logs sur stderr

### `pm-parse`
- **Entrée** : XML PubMed sur stdin
- **Sortie** : JSONL (un objet JSON par article)
- **Parser** : `xml2` + awk + jq
- **Champs extraits** :
  ```json
  {
    "pmid": "12345678",
    "title": "Article title",
    "authors": ["Smith J", "Doe A"],
    "journal": "Nature",
    "year": "2024",
    "doi": "10.1234/example",
    "abstract": "Full abstract text..."
  }
  ```

---

## Dépendances

- `curl` : requêtes HTTP
- `jq` : construction/manipulation JSON
- `xml2` : parsing XML streaming
- `awk` : transformation texte
- Optionnel : `parallel` pour paralléliser les fetches

---

## Ressources PubMed

### DTD (Document Type Definition)
- URL : https://dtd.nlm.nih.gov/ncbi/pubmed/
- DTD actuelle : `pubmed_240101.dtd`
- Définit la structure exacte du XML PubMed
- À utiliser pour établir le mapping XPath → JSON

### Fichiers Baseline (corpus complet)
- URL : https://ftp.ncbi.nlm.nih.gov/pubmed/baseline/
- Format : XML compressé (`.xml.gz`)
- ~1200 fichiers, ~35M articles au total
- Mis à jour annuellement
- Usage : `zcat pubmed24n0001.xml.gz | pm-parse`

### Fichiers Update (mises à jour quotidiennes)
- URL : https://ftp.ncbi.nlm.nih.gov/pubmed/updatefiles/
- Nouveaux articles et corrections
- Même format que baseline

### API E-utilities
- Documentation : https://www.ncbi.nlm.nih.gov/books/NBK25500/
- `esearch` : recherche → WebEnv/QueryKey ou liste d'IDs
- `efetch` : IDs → XML complet (seul moyen d'avoir l'abstract)
- `esummary` : IDs → JSON natif (métadonnées sans abstract)

### Comparaison efetch XML vs esummary JSON

| Champ              | efetch XML | esummary JSON |
|--------------------|------------|---------------|
| PMID               | ✓          | ✓             |
| Titre              | ✓          | ✓             |
| Auteurs            | ✓          | ✓             |
| Journal            | ✓          | ✓             |
| Date               | ✓          | ✓             |
| DOI                | ✓          | ✓             |
| **Abstract**       | ✓          | ✗             |
| MeSH terms         | ✓          | ✗             |
| Affiliations       | ✓          | ✗             |
| Références         | ✓          | ✗             |

---

## Modes d'utilisation

### Mode API (recherche dynamique)
```bash
pm-search "cancer BRCA1" | pm-fetch | pm-parse > results.jsonl
```

### Mode Baseline (corpus local)
```bash
# Tout le corpus
zcat /data/pubmed/baseline/*.xml.gz | pm-parse > all_pubmed.jsonl

# Filtré à la volée
zcat pubmed24n0001.xml.gz | pm-parse | jq 'select(.year >= "2020")'
```

---

## Plan d'implémentation

Voir [plan.md](plan.md) pour le plan TDD détaillé.
