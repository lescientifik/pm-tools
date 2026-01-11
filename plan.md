# Plan d'implémentation TDD - PubMed CLI Tools

## Framework de test : `bats-core`
- Bash Automated Testing System
- Syntaxe simple, intégration CI facile
- Install : `apt install bats` ou `brew install bats-core`

## Structure du projet
```
pubmed_parser/
├── bin/
│   ├── pm-search
│   ├── pm-fetch
│   └── pm-parse
├── lib/
│   └── pm-common.sh           # fonctions partagées (logging, etc.)
├── scripts/
│   ├── dtd-to-xpath.sh        # DTD → liste XPaths
│   ├── generate-dtd-tests.sh  # mapping → tests bats
│   └── extract-fixtures.sh    # baseline → fixtures edge cases
├── generated/
│   ├── all-xpaths.txt         # tous les XPaths possibles (depuis DTD)
│   ├── mapping.json           # XPaths sélectionnés → champs JSON
│   └── dtd-coverage.bats      # tests générés depuis DTD
├── test/
│   ├── test_helper.bash       # fixtures, mocks
│   ├── pm-common.bats
│   ├── pm-search.bats
│   ├── pm-fetch.bats
│   ├── pm-parse.bats
│   └── integration.bats
├── fixtures/
│   ├── random/                # articles extraits aléatoirement
│   ├── edge-cases/            # articles edge case par catégorie
│   │   ├── no-doi.xml
│   │   ├── no-abstract.xml
│   │   ├── structured-abstract.xml
│   │   ├── unicode.xml
│   │   └── ...
│   └── expected/              # outputs JSONL attendus (golden files)
├── data/
│   └── pubmed24n0001.xml.gz   # baseline sample (gitignore)
├── spec.md
└── plan.md
```

## Méthodologie TDD adaptée au shell

**Red-Green-Refactor :**
1. **Red** : écrire un test `.bats` qui échoue
2. **Green** : implémenter le minimum pour passer
3. **Refactor** : nettoyer en gardant les tests verts

**Structure Given-When-Then en bats :**
```bash
@test "pm-parse extrait le PMID correctement" {
    # Given: un XML minimal
    local xml='<PubmedArticle><MedlineCitation><PMID>12345</PMID></MedlineCitation></PubmedArticle>'

    # When: on parse
    result=$(echo "$xml" | pm-parse)

    # Then: le PMID est extrait
    [[ $(echo "$result" | jq -r '.pmid') == "12345" ]]
}
```

---

## Phase 0 : DTD-Driven Development

### 0.1 Téléchargement des ressources
- [x] Télécharger la DTD : pubmed_250101.dtd (also kept pubmed_240101.dtd)
- [x] Télécharger un fichier baseline sample : pubmed25n0001.xml.gz (19MB, 30k articles)
- [x] Valider que le baseline est conforme à la DTD (well-formed XML validated)

### 0.2 Parser la DTD → Générer le mapping complet
- [x] Créer un script `scripts/dtd-to-xpath.sh` qui :
  - Parse la DTD (format SGML)
  - Extrait tous les éléments et attributs
  - Génère la liste exhaustive des XPaths possibles
- [x] Output : `generated/all-xpaths.txt` (138 éléments)
- [x] Sélectionner les XPaths qu'on veut extraire → `mapping.json`

### 0.3 DTD → Générer les tests de couverture
- [x] Créer un script `scripts/generate-dtd-tests.sh` qui :
  - Lit `mapping.json`
  - Génère des tests bats pour chaque champ
  - Vérifie que le parser extrait bien chaque XPath mappé
- [x] Output : `test/generated/dtd-coverage.bats` (7 tests, fail until pm-parse implemented)

### 0.4 Baseline → Extraction intelligente de fixtures
- [x] Créer un script `scripts/extract-fixtures.sh` qui :
  - Extrait N articles aléatoires du baseline
  - Trouve des articles représentatifs des edge cases :
    - Sans DOI
    - Sans abstract
    - Abstract structuré (Background/Methods/Results)
    - Auteurs avec affiliations multiples
    - Caractères spéciaux / unicode
    - MeSH terms multiples
    - Article avec corrections/errata
  - Utilise `awk` pour détecter ces patterns (optimisé pour 30k articles)
- [x] Output : `fixtures/` avec articles classés par edge case

### 0.5 Baseline → Tests de non-régression
- [x] Test : `pm-parse` ne crash sur aucun article du baseline
- [x] Méthode : `zcat baseline.xml.gz | pm-parse | wc -l` == nombre d'articles attendu (30000)
- [x] Mesurer la performance (articles/seconde) : ~1700-2200 articles/sec, seuil minimum 1000

### 0.6 Golden files via EDirect (oracle officiel)

**Stratégie** : Utiliser `xtract` (outil officiel NCBI) comme référence.

- [x] Installer EDirect : `sh -c "$(curl -fsSL https://ftp.ncbi.nlm.nih.gov/entrez/entrezdirect/install-edirect.sh)"`
- [x] Créer un script `scripts/generate-golden.sh` qui :
  - Prend des articles XML en entrée
  - Utilise `xtract` pour extraire les champs
  - Convertit le TSV en JSONL (notre format cible)
  - Sauvegarde dans `fixtures/expected/`
  - Gère MedlineDate en plus de PubDate/Year

```bash
# Exemple de génération de golden file
cat fixtures/edge-cases/complete.xml | \
  xtract -pattern PubmedArticle \
         -element MedlineCitation/PMID \
         -element ArticleTitle \
         -first Author/LastName \
         ... | \
  scripts/tsv-to-jsonl.sh > fixtures/expected/complete.jsonl
```

**Avantage** : On compare notre implémentation à l'outil officiel NCBI.

### 0.7 Valider la conversion TSV→JSONL dans generate-golden.sh

#### Investigation Findings (2026-01-11)

**Critical Bug Discovered:** The current awk-based TSV→JSONL parser is fundamentally broken
when xtract outputs data containing embedded tabs or newlines.

**Root Cause Analysis:**
1. xtract uses TAB as field separator and NEWLINE as record separator
2. xtract does NOT escape tabs/newlines that appear within the XML data
3. If XML contains `&#9;` (tab) or `&#10;` (newline), xtract decodes them literally
4. This corrupts TSV field boundaries, making awk parsing impossible

**Demonstrated Failures:**
```bash
# Input: <ArticleTitle>Title with embedded&#9;tab</ArticleTitle>
# xtract output: 999<TAB>Title with embedded<TAB>tab<TAB>...
# Result: fields are shifted, authors array contains journal name, etc.

# Input: <ArticleTitle>Line1&#10;Line2</ArticleTitle>
# xtract output: Two lines instead of one
# Result: Two corrupted JSON objects instead of one valid object
```

**Current awk json_escape() handles:**
- Backslashes (`\` → `\\`) - OK
- Double quotes (`"` → `\"`) - OK
- Newlines in strings (`\n` → `\\n`) - OK, but never reached if xtract breaks records
- Carriage returns (`\r` → `\\r`) - OK
- Tabs (`\t` → `\\t`) - OK, but never reached if xtract breaks fields

**Current awk json_escape() MISSING:**
- Unicode control characters (U+0000 to U+001F except already handled)
- Proper handling when xtract output is already corrupted

**Real-world risk assessment:**
- In 500k lines of pubmed25n0001.xml.gz: No `&#9;` or `&#10;` entities found
- Quotes (`"`) are common (117k+ occurrences) - handled correctly
- Backslashes are rare - handled correctly
- Risk is LOW for current baseline but HIGH for edge cases in other data

#### Recommended Solution: Hybrid Approach

**Strategy:** Keep xtract for extraction but use jq for JSON construction.

**Why jq over awk:**
- jq `-Rs` mode properly escapes all special characters automatically
- jq guarantees valid JSON output
- Eliminates manual escape sequence handling
- Handles Unicode properly

**Implementation Options:**

**Option A: Replace awk entirely with jq (Recommended)**
- Change xtract separator to something rare (e.g., `|` or `$'\x1e'` record separator)
- Use jq to build JSON objects from parsed fields
- Pro: Robust, maintainable, handles all edge cases
- Con: Slight performance overhead (acceptable for golden file generation)

**Option B: Sanitize xtract output before awk**
- Post-process xtract output to escape embedded tabs/newlines
- Keep existing awk parser
- Pro: Minimal code changes
- Con: Fragile, hard to maintain, may miss edge cases

**Option C: Use JSONL output directly from xtract**
- xtract has `-j` flag for JSON output (limited support)
- Pro: No custom parsing needed
- Con: May not support all our fields, less control over format

#### Tasks for Phase 0.7

**0.7.1 Create test fixtures for edge cases**
- [x] Create `fixtures/edge-cases/special-chars/embedded-tab.xml`
- [x] Create `fixtures/edge-cases/special-chars/embedded-newline.xml`
- [x] Create `fixtures/edge-cases/special-chars/quotes-backslash.xml`
- [x] Create `fixtures/edge-cases/special-chars/unicode-control.xml`

**0.7.2 Add bats tests for generate-golden.sh**
- [x] Test: valid JSON output for each edge case fixture
- [x] Test: embedded tabs produce valid JSON (not corrupted fields)
- [x] Test: embedded newlines produce single JSONL line per article
- [x] Test: quotes and backslashes are properly escaped
- [ ] Test: output matches expected golden files

**0.7.3 Implement robust TSV→JSONL conversion**
- [x] Refactor generate-golden.sh to use jq for JSON construction
- [x] Validate output with `jq .` for each record (jq -c does this automatically)
- Note: Removed awk entirely; jq --arg handles all escaping properly

**0.7.4 Update pm-parse to handle same edge cases**
- [x] Verify pm-parse awk json_escape handles all cases
- [x] Fix multi-line value handling (title, journal, abstract) for embedded newlines
- [x] Add corresponding tests to pm-parse.bats (4 new tests)

**0.7.5 Regenerate all golden files**
- [x] Re-run generate-golden.sh on all fixtures
- [x] Generate golden files for new special-chars fixtures
- [x] Verify all tests pass with new golden files

### 0.8 Mapping final documenté
```
generated/mapping.json
{
  "pmid": "/PubmedArticle/MedlineCitation/PMID",
  "title": "/PubmedArticle/MedlineCitation/Article/ArticleTitle",
  "authors": "/PubmedArticle/MedlineCitation/Article/AuthorList/Author",
  "journal": "/PubmedArticle/MedlineCitation/Article/Journal/Title",
  "year": "/PubmedArticle/MedlineCitation/Article/Journal/JournalIssue/PubDate/Year",
  "doi": "/PubmedArticle/PubmedData/ArticleIdList/ArticleId[@IdType='doi']",
  "abstract": "/PubmedArticle/MedlineCitation/Article/Abstract/AbstractText"
}
```

---

## Phase 1 : Infrastructure (tests en premier)

### 1.1 Setup projet + bats
- [x] Créer la structure de dossiers
- [x] Installer/vérifier bats-core
- [x] Créer `test_helper.bash` avec fonctions utilitaires

### 1.2 Tests pour `pm-common.sh`
- [x] Test : `log_verbose` écrit sur stderr seulement si --verbose
- [x] Test : `die` affiche erreur et exit 1
- [x] Implémenter `lib/pm-common.sh`

---

## Phase 2 : `pm-parse` (commencer par la fin du pipeline)

**Pourquoi commencer par parse ?** On peut tester offline avec des fixtures XML extraites du baseline.

### 2.1 Tests unitaires pm-parse
- [x] Test : input vide → output vide
- [x] Test : un article minimal → JSONL avec pmid
- [x] Test : article complet (extrait baseline) → tous les champs extraits
- [x] Test : multiple articles → une ligne JSONL par article
- [x] Test : caractères spéciaux (accents, &amp;, unicode) → échappés correctement
- [ ] Test : fichier .xml.gz → décompression à la volée (zcat | pm-parse)

### 2.2 Implémentation pm-parse
- [x] Script de base qui lit stdin
- [x] Pipeline `xml2 | awk` pour découper par article
- [x] Extraction des champs selon mapping DTD
- [ ] Construction JSON avec jq
- [ ] Gestion --verbose

### 2.3 Fixtures (depuis baseline)
- [x] Télécharger un fichier baseline
- [x] Extraire 5-10 articles représentatifs
- [ ] Créer le JSONL attendu manuellement (golden file)

---

## Phase 3 : `pm-fetch`

### 3.1 Tests pm-fetch (avec mocks)
- [ ] Test : un PMID → appel curl correct
- [ ] Test : multiple PMIDs → batching (≤200 par requête)
- [ ] Test : rate limiting respecté (≤3 req/sec)
- [ ] Test : erreur réseau → exit 1

### 3.2 Implémentation pm-fetch
- [ ] Lecture PMIDs depuis stdin
- [ ] Batching avec awk/split
- [ ] Appels curl à efetch
- [ ] Rate limiting avec sleep
- [ ] Output XML sur stdout

---

## Phase 4 : `pm-search`

### 4.1 Tests pm-search (avec mocks)
- [ ] Test : requête simple → liste de PMIDs
- [ ] Test : --max N → limite respectée
- [ ] Test : requête vide → erreur
- [ ] Test : aucun résultat → output vide (pas d'erreur)

### 4.2 Implémentation pm-search
- [ ] Appel curl à esearch
- [ ] Parsing du XML de réponse (count, ids)
- [ ] Pagination si > 10000 résultats
- [ ] Output PMIDs un par ligne

---

## Phase 5 : Support fichiers baseline (optionnel)

### 5.1 Mode offline avec baseline
- [ ] `pm-baseline-download` : télécharge les fichiers baseline
- [ ] `pm-baseline-parse` : parse les .xml.gz locaux
- [ ] Ou simplement : `zcat pubmed24n*.xml.gz | pm-parse`

### 5.2 Tests
- [ ] Test : parsing d'un fichier .gz complet
- [ ] Test : performance sur gros volume

---

## Phase 6 : Intégration

### 6.1 Tests end-to-end
- [ ] Test : pipeline complet avec fixture locale
- [ ] Test : recherche réelle (optionnel, marqué @skip en CI)
- [ ] Test : baseline → parse → filtre jq

### 6.2 Polish
- [ ] --help pour chaque commande
- [ ] Vérification des dépendances au démarrage
- [ ] README avec exemples

---

## Ordre d'exécution TDD

```
0. Étude DTD + baseline         → mapping.md, fixtures/
1. test/test_helper.bash        → lib/pm-common.sh
2. test/pm-parse.bats           → bin/pm-parse
3. test/pm-fetch.bats           → bin/pm-fetch
4. test/pm-search.bats          → bin/pm-search
5. test/integration.bats        → validation e2e
```

---

## Ressources

- DTD PubMed : https://dtd.nlm.nih.gov/ncbi/pubmed/
- Fichiers baseline : https://ftp.ncbi.nlm.nih.gov/pubmed/baseline/
- Update files : https://ftp.ncbi.nlm.nih.gov/pubmed/updatefiles/
- API E-utilities : https://www.ncbi.nlm.nih.gov/books/NBK25500/
