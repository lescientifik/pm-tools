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
- [ ] Télécharger la DTD : https://dtd.nlm.nih.gov/ncbi/pubmed/out/pubmed_240101.dtd
- [ ] Télécharger un fichier baseline sample : pubmed24n0001.xml.gz (~300MB)
- [ ] Valider que le baseline est conforme à la DTD

### 0.2 Parser la DTD → Générer le mapping complet
- [ ] Créer un script `scripts/dtd-to-xpath.sh` qui :
  - Parse la DTD (format SGML)
  - Extrait tous les éléments et attributs
  - Génère la liste exhaustive des XPaths possibles
- [ ] Output : `generated/all-xpaths.txt`
- [ ] Sélectionner les XPaths qu'on veut extraire → `mapping.json`

### 0.3 DTD → Générer les tests de couverture
- [ ] Créer un script `scripts/generate-dtd-tests.sh` qui :
  - Lit `mapping.json`
  - Génère des tests bats pour chaque champ
  - Vérifie que le parser extrait bien chaque XPath mappé
- [ ] Output : `test/generated/dtd-coverage.bats`

### 0.4 Baseline → Extraction intelligente de fixtures
- [ ] Créer un script `scripts/extract-fixtures.sh` qui :
  - Extrait N articles aléatoires du baseline
  - Trouve des articles représentatifs des edge cases :
    - Sans DOI
    - Sans abstract
    - Abstract structuré (Background/Methods/Results)
    - Auteurs avec affiliations multiples
    - Caractères spéciaux / unicode
    - MeSH terms multiples
    - Article avec corrections/errata
  - Utilise `grep` / `xml2` pour détecter ces patterns
- [ ] Output : `fixtures/` avec articles classés par edge case

### 0.5 Baseline → Tests de non-régression
- [ ] Test : `pm-parse` ne crash sur aucun article du baseline
- [ ] Méthode : `zcat baseline.xml.gz | pm-parse | wc -l` == nombre d'articles attendu
- [ ] Mesurer la performance (articles/seconde)

### 0.6 Golden files via EDirect (oracle officiel)

**Stratégie** : Utiliser `xtract` (outil officiel NCBI) comme référence.

- [ ] Installer EDirect : `sh -c "$(curl -fsSL https://ftp.ncbi.nlm.nih.gov/entrez/entrezdirect/install-edirect.sh)"`
- [ ] Créer un script `scripts/generate-golden.sh` qui :
  - Prend des articles XML en entrée
  - Utilise `xtract` pour extraire les champs
  - Convertit le TSV en JSONL (notre format cible)
  - Sauvegarde dans `fixtures/expected/`

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

### 0.7 Mapping final documenté
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
- [ ] Créer la structure de dossiers
- [ ] Installer/vérifier bats-core
- [ ] Créer `test_helper.bash` avec fonctions utilitaires

### 1.2 Tests pour `pm-common.sh`
- [ ] Test : `log_verbose` écrit sur stderr seulement si --verbose
- [ ] Test : `die` affiche erreur et exit 1
- [ ] Implémenter `lib/pm-common.sh`

---

## Phase 2 : `pm-parse` (commencer par la fin du pipeline)

**Pourquoi commencer par parse ?** On peut tester offline avec des fixtures XML extraites du baseline.

### 2.1 Tests unitaires pm-parse
- [ ] Test : input vide → output vide
- [ ] Test : un article minimal → JSONL avec pmid
- [ ] Test : article complet (extrait baseline) → tous les champs extraits
- [ ] Test : multiple articles → une ligne JSONL par article
- [ ] Test : caractères spéciaux (accents, &amp;, unicode) → échappés correctement
- [ ] Test : fichier .xml.gz → décompression à la volée (zcat | pm-parse)

### 2.2 Implémentation pm-parse
- [ ] Script de base qui lit stdin
- [ ] Pipeline `xml2 | awk` pour découper par article
- [ ] Extraction des champs selon mapping DTD
- [ ] Construction JSON avec jq
- [ ] Gestion --verbose

### 2.3 Fixtures (depuis baseline)
- [ ] Télécharger un fichier baseline
- [ ] Extraire 5-10 articles représentatifs
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
