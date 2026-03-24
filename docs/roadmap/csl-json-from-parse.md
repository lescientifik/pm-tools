---
description: Roadmap pour étendre pm parse avec un flag --csl qui produit du CSL-JSON directement depuis le XML PubMed, éliminant le besoin de l'API Citation Exporter.
---

# Roadmap : CSL-JSON natif depuis pm parse

## Objectif

Ajouter un flag `--csl` à `pm parse` (et `pm collect`) pour produire du CSL-JSON complet
directement depuis le XML PubMed, sans appel réseau supplémentaire. `pm cite` reste intact
pour la rétrocompatibilité.

**Specs :** `spec.md` | **Recherche :** `docs/research/data-structures-analysis.md`

## Contexte

Notre recherche a montré que les champs CSL-JSON produits par l'API NCBI Citation
Exporter sont **tous disponibles** dans le XML PubMed que `pm fetch` récupère déjà.
Le tableau ci-dessous liste les 20 champs disponibles dans le XML
(16 extraits + 4 dérivés/constants : `id`, `type`, `source`, `accessed`).
La sortie `--csl` en émettra **19** (`abstract` est exclu pour parité avec l'API NCBI) :

| Champ CSL-JSON | Source XML | Standard CSL ? | Actuellement extrait ? |
|---|---|---|---|
| `PMID` | `<PMID>` | Non (extension NCBI) | Oui (`pmid`) |
| `title` | `<ArticleTitle>` | Oui | Oui |
| `author` | `<AuthorList>` | Oui | Oui (`authors`) |
| `container-title` | `<Journal><Title>` | Oui | Oui (`journal`) |
| `DOI` | `<ELocationID>` | Oui | Oui (`doi`) |
| `issued` | `<PubDate>` | Oui | Partiellement (`year`, `date`) |
| `abstract` | `<AbstractText>` | Oui | Oui |
| `PMCID` | `<ArticleId IdType="pmc">` | Non (extension NCBI) | Oui (`pmcid`) |
| `volume` | `<Volume>` | Oui | **Non** |
| `issue` | `<Issue>` | Oui | **Non** |
| `page` | `<MedlinePgn>` / `<StartPage>` | Oui | **Non** |
| `ISSN` | `<ISSN>` | Oui | **Non** |
| `container-title-short` | `<ISOAbbreviation>` | Oui | **Non** |
| `epub-date` | `<ArticleDate>` | **Non** (extension NCBI) | **Non** |
| `type` | hardcodé `"article-journal"` | Oui | **Non** |
| `publisher-place` | `<Country>` | Oui | **Non** |
| `status` | `<PublicationStatus>` | Non (extension NCBI) | **Non** |
| `id` | dérivé : `pmid:{PMID}` | Oui | **Non** |
| `source` | constante : `"PubMed"` | Oui (catalogue) | **Non** |
| `accessed` | date du jour | Oui | **Non** |

**Note sur les extensions NCBI :** Les champs `epub-date`, `status`, `PMID`, `PMCID` ne
font pas partie du standard CSL-JSON. Ils sont produits par l'API NCBI Citation Exporter
et passés opaquement par csl-tools. Notre implémentation les inclut pour parité avec
`pm cite`. `status` est utilisé par certains styles (APA "ahead-of-print"). Le champ
`source` est un champ CSL standard (catalogue/base de données d'origine), utilisé ici
avec la valeur `"PubMed"` — conforme au standard.

**Note sur `type` :** L'API NCBI hardcode `"article-journal"` pour tout le contenu PubMed,
indépendamment du `<PublicationType>` XML (qui contient des types MeSH comme "Review",
"Clinical Trial", "Meta-Analysis"). Nous faisons de même. Vérifié sur données réelles
(retractions, lettres, éditoriaux, preprints, essais cliniques : tous `article-journal`).

**Note sur `abstract` :** Bien que `abstract` soit un champ CSL-JSON valide (utilisé par
certains styles comme les bibliographies annotées), l'API NCBI Citation Exporter l'**exclut**
de sa sortie. Nous l'excluons aussi pour parité. L'abstract reste disponible via la sortie
ArticleRecord par défaut (sans `--csl`).

**Articulation avec MedInk :** MedInk appelle `pm_cite()` (Python API) pour obtenir du
CSL-JSON stocké dans `references.json`, ensuite consommé par `csl-tools`. Il supporte aussi
`medink ref add --from-jsonl` via stdin. Le flag `--csl` permettra les deux workflows
sans appel réseau supplémentaire.

---

## Décision architecturale clé : ArticleRecord = single source of truth

**Principe :** `ArticleRecord` est enrichi avec les nouveaux champs (volume, issue, page,
etc.) et devient la source de vérité unique. `article_to_csl()` est une pure transformation
dict→dict (ArticleRecord → CSL-JSON), sans retour au XML.

**Gestion de la rétrocompatibilité :** La sortie par défaut de `pm parse` (sans `--csl`)
est **filtrée** pour n'émettre que les 10 champs historiques. Ceci garantit la
non-régression pour les consommateurs existants (filter, diff, MedInk, golden files).

```python
# Pseudo-code de l'architecture

# Champs historiques émis par défaut (sans --csl)
LEGACY_FIELDS = frozenset({
    "pmid", "title", "authors", "journal", "year", "date",
    "abstract", "abstract_sections", "doi", "pmcid",
})

def parse_article(article: ET.Element) -> ArticleRecord:
    """Enrichi — extrait TOUS les champs depuis le XML."""
    result = {}
    # ... 10 champs existants (inchangés) ...
    # ... + nouveaux champs : volume, issue, page, issn,
    #     journal_abbrev, epub_date, publisher_place, pub_status ...
    return result

def article_to_csl(record: ArticleRecord) -> CslJsonRecord:
    """Pure transformation dict→dict. Pas d'accès au XML."""
    csl = {}
    csl["id"] = f"pmid:{record['pmid']}"
    csl["type"] = "article-journal"
    csl["source"] = "PubMed"
    csl["PMID"] = record["pmid"]
    csl["title"] = record.get("title")
    csl["author"] = record.get("authors")  # renommage de clé
    csl["container-title"] = record.get("journal")
    csl["container-title-short"] = record.get("journal_abbrev")
    csl["DOI"] = record.get("doi")
    # ... etc, mapping pur ...
    return {k: v for k, v in csl.items() if v is not None}

# Sortie CLI
def output_article(record: ArticleRecord, csl_mode: bool) -> dict:
    if csl_mode:
        return article_to_csl(record)
    else:
        return {k: v for k, v in record.items() if k in LEGACY_FIELDS}
```

**Avantages :**
- ArticleRecord est la single source of truth (toutes les données extraites)
- `article_to_csl()` est une pure transformation sans I/O ni XML
- Les consommateurs Python accèdent à tous les champs via ArticleRecord
- La sortie CLI par défaut reste rétrocompatible via filtrage

---

## Phase 1 — Enrichir ArticleRecord + `article_to_csl()` (séquentiel)

### Objectif
Ajouter les nouveaux champs à ArticleRecord, les extraire dans `parse_article()`,
et créer `article_to_csl()` comme pure transformation dict→dict.

### TDD Steps

**RED :**

*Extraction des nouveaux champs dans parse_article() :*
- Test : `parse_article()` extrait `volume` depuis `<Volume>48</Volume>`
- Test : `parse_article()` extrait `issue` depuis `<Issue>2</Issue>`
- Test : `parse_article()` extrait `page` depuis `<MedlinePgn>100-105</MedlinePgn>`
- Test : `parse_article()` extrait `page` depuis `<StartPage>` + `<EndPage>` (`"100-105"`) quand pas de `<MedlinePgn>`
- Test : `parse_article()` extrait `page` depuis `<StartPage>` seul quand pas de `<EndPage>` ni `<MedlinePgn>`
- Test : `parse_article()` préfère `<MedlinePgn>` quand les deux sources sont présentes
- Test : `parse_article()` extrait `issn` depuis `<ISSN>` (préférence : Print > Electronic)
- Test : quand Print et Electronic ISSN coexistent, Print est préféré
- Test : quand seul Electronic ISSN existe, il est utilisé
- Test : `parse_article()` extrait `journal_abbrev` depuis `<ISOAbbreviation>`
- Test : `parse_article()` extrait `epub_date` depuis `<ArticleDate DateType="Electronic">` comme string ISO (`"2024-01-15"`)
- Test : `parse_article()` extrait `publisher_place` depuis `<MedlineJournalInfo><Country>`
- Test : `parse_article()` extrait `pub_status` depuis `<PublicationStatus>`
- Test : champs absents → clés omises (cohérent avec le pattern existant)

*Conversion article_to_csl() :*
- Test : `article_to_csl()` produit `id` = `"pmid:{pmid}"`
- Test : `article_to_csl()` produit `type` = `"article-journal"` (toujours)
- Test : `article_to_csl()` produit `source` = `"PubMed"`
- Test : `article_to_csl()` produit `accessed` = `{"date-parts": [[year, month, day]]}` (date du jour)
- Test : `pmid` → `PMID`, `doi` → `DOI`, `pmcid` → `PMCID` (clés majuscules)
- Test : `authors` → `author` (renommage, même structure)
- Test : `journal` → `container-title`
- Test : `journal_abbrev` → `container-title-short`
- Test : `year` + `date` → `issued` au format `{"date-parts": [[2024, 1, 15]]}` (ints)
- Test : date partielle (année seule) → `{"date-parts": [[2024]]}`
- Test : date année-mois → `{"date-parts": [[2024, 3]]}`
- Test : date saisonnière (Spring 1976) → `{"date-parts": [[1976, 3]]}`
- Test : `epub_date` → `epub-date` au format `{"date-parts": [[y, m, d]]}`
- Test : `publisher_place` → `publisher-place`
- Test : `pub_status` → `status`
- Test : `volume`, `issue`, `page` passés tels quels (même nom de clé)
- Test : `issn` → `ISSN` (renommage majuscule, comme `doi` → `DOI`)
- Test : `abstract` et `abstract_sections` **exclus** du CSL-JSON
- Test : champs absents dans ArticleRecord → absents dans CSL-JSON (pas de clés nulles)
- Test : `article_to_csl()` ne prend qu'un `ArticleRecord` en entrée (pas d'`ET.Element`)

*Non-régression de la sortie CLI par défaut :*
- Test : `pm parse` (sans `--csl`) n'émet que les 10 champs historiques (LEGACY_FIELDS)
- Test : `pm collect` (sans `--csl`) n'émet que les 10 champs historiques (LEGACY_FIELDS)
- Test : golden files existantes passent toujours

**GREEN :**
- Étendre `ArticleRecord` dans `types.py` avec les nouveaux champs optionnels
- Mettre à jour `test_types.py` : ajuster les assertions sur le nombre de champs
- Étendre `parse_article()` dans `parse.py` pour extraire les nouveaux champs
- Note : `<Country>` est sous `<MedlineJournalInfo>`, pas sous `<Article>`
- Implémenter `article_to_csl(record: ArticleRecord) -> CslJsonRecord` dans `parse.py` (pure transformation dict→dict)
- Définir `CslJsonRecord` TypedDict dans `types.py`
- Ajouter le filtrage `LEGACY_FIELDS` dans `parse.main()` pour la sortie par défaut
- Ajouter le même filtrage dans `collect_main()` de `cli.py`
- Pour `accessed` dans `article_to_csl()` : utiliser `datetime.date.today()`

**REFACTOR :**
- Grouper l'extraction par zone XML (Journal, MedlineJournalInfo, PubmedData)

### Critères de complétion
- [ ] Tous les tests passent (`uv run pytest`)
- [ ] `ruff check` clean
- [ ] `parse_article()` extrait tous les champs (anciens + nouveaux)
- [ ] `article_to_csl()` est une pure transformation dict→dict (pas d'accès XML)
- [ ] La sortie par défaut de `pm parse` n'émet que les 10 champs historiques
- [ ] Golden files existantes inchangées (non-régression)
- [ ] `test_types.py` mis à jour et passe

---

## Phase 2 — Flag `--csl` sur `pm parse` CLI + exports (séquentiel)

### Objectif
Exposer la conversion CSL-JSON via le CLI avec `pm parse --csl`.
Mettre à jour les exports et la documentation.

### Dépendances
Phase 1.

### TDD Steps

**RED :**
- Test : `pm parse --csl` produit du JSONL avec des clés CSL-JSON (`container-title`, `DOI`, etc.)
- Test : `pm parse` (sans flag) produit toujours de l'ArticleRecord filtré (non-régression)
- Test : `pm parse --csl --help` affiche l'aide mentionnant le format CSL-JSON
- Test : `pm parse --csl` sur XML vide → sortie vide, exit 0
- Test : `pm parse --csl` chaque ligne est du JSON valide

**GREEN :**
- Ajouter parsing du flag `--csl` dans `parse.main()`
- Quand `--csl` : appeler `article_to_csl()` sur chaque article avant output
- Créer `parse_xml_csl()` et `parse_xml_stream_csl()` (wrappers : `parse_xml()` + `article_to_csl()` sur chaque record)
- Mettre à jour `HELP_TEXT` (mentionner `--csl`, avertir que la sortie CSL-JSON n'est pas compatible avec `pm filter`/`pm diff`)
- Mettre à jour `__init__.py` : exporter `CslJsonRecord`, `article_to_csl`, `parse_xml_csl`, `parse_xml_stream_csl`, `LEGACY_FIELDS`

**REFACTOR :**
- Factoriser la boucle output si duplication

### Critères de complétion
- [ ] `pm parse --csl < fixtures/random/pmid-3341.xml` produit du CSL-JSON valide
- [ ] `pm parse < fixtures/random/pmid-3341.xml` produit de l'ArticleRecord filtré (identique à avant)
- [ ] `CslJsonRecord` et `article_to_csl` importables depuis `pm_tools`
- [ ] `parse_xml_stream_csl()` disponible pour les consommateurs Python (streaming)
- [ ] Tous les tests passent
- [ ] `ruff check` clean

---

## Phase 3 — Flag `--csl` sur `pm collect` (séquentiel)

### Objectif
Propager le flag `--csl` à `pm collect` pour le workflow tout-en-un.

### Dépendances
Phase 2.

### TDD Steps

**RED :**
- Test : `collect_main(["query", "--csl"])` produit du CSL-JSON
- Test : `collect_main(["query"])` produit toujours de l'ArticleRecord filtré (non-régression)
- Test : `--csl` apparaît dans `COLLECT_HELP`

**GREEN :**
- Ajouter parsing de `--csl` dans `collect_main()`
- Quand `--csl` : appeler `article_to_csl()` sur chaque article avant output
- Sans `--csl` : filtrer avec `LEGACY_FIELDS` (déjà en place depuis Phase 1)
- Mettre à jour `COLLECT_HELP`

**REFACTOR :**
- Rien de spécial attendu.

### Critères de complétion
- [ ] Tous les tests passent
- [ ] `ruff check` clean
- [ ] `pm collect --help` mentionne `--csl`

---

## Phase 4 — Validation live et golden files CSL-JSON (parallélisable)

### Objectif
Valider que `pm parse --csl` produit un output équivalent à `pm cite` sur des articles réels.

### Dépendances
Phase 2.

### TDD Steps

**RED :**
- Test : pour N PMIDs de fixtures, `pm parse --csl` et `pm cite` produisent les mêmes
  champs communs (title, DOI, author families, year, volume, issue, page)
- Test : les champs dérivés (`id`, `source`) sont corrects
- Test : comparaison exclut `accessed` (non-déterministe : date du jour vs date passée)
- Test : les golden files CSL-JSON matchent la sortie de `pm parse --csl`

**GREEN (parallélisable — 2 agents) :**

*Agent A :* Créer des golden files CSL-JSON
- Prendre les fixtures XML existantes (`fixtures/random/`, `fixtures/edge-cases/`)
- Générer les sorties attendues CSL-JSON → `fixtures/expected/csl/`
- Le champ `accessed` est exclu des golden files (ou fixé à une date sentinel)
- Valider manuellement les 2-3 premiers

*Agent B :* Tests de comparaison pm parse --csl vs pm cite
- Script de test qui compare les sorties sur les mêmes PMIDs
- Comparaison champ par champ, **en excluant `accessed`**
- Documenter les différences attendues

### Critères de complétion
- [ ] Golden files CSL-JSON créées pour toutes les fixtures existantes
- [ ] Tests de comparaison avec pm cite passent (hors `accessed`)
- [ ] Différences documentées et justifiées

---

## Phase 5 — Documentation (séquentiel)

### Objectif
Mettre à jour la documentation projet.

### Dépendances
Phase 3 + 4.

### Steps
- Mettre à jour `spec.md` : documenter le flag `--csl`, le format CSL-JSON, et l'enrichissement d'ArticleRecord
- Mettre à jour `plan.md` : ajouter cette phase avec checkboxes
- Mettre à jour `README.md` si pertinent

### Critères de complétion
- [ ] `spec.md` mentionne `--csl` et les nouveaux champs ArticleRecord
- [ ] `plan.md` contient les phases avec checkboxes

---

## Gate — Adversarial Review

**Exécuter `/adversarial-review` sur l'ensemble du code modifié (types.py, parse.py, cli.py, tests).**

Axes de review :
1. **Correction :** le CSL-JSON produit est-il conforme au standard (+ extensions NCBI documentées) ?
2. **Non-régression :** la sortie par défaut (10 champs filtrés) est-elle strictement identique à avant ?
3. **Complétude :** tous les champs sont-ils couverts ? Exports Python corrects ? article_to_csl() est-elle pure (pas d'accès XML) ?

---

## Out of scope

- **Supprimer `pm cite`** — rétrocompatibilité maintenue, `pm cite` reste fonctionnel
- **Modifier MedInk** — c'est un projet séparé ; il pourra migrer de `pm_cite()` vers `article_to_csl()` plus tard
- **Format CSL-JSON pour `pm filter`/`pm diff`** — ces commandes continuent à consommer de l'ArticleRecord. La sortie `--csl` est terminale (pas destinée à être re-pipée dans filter/diff)
- **Performance baseline** — pas de test de performance sur le parsing CSL-JSON (overhead négligeable)
- **Validation contre le schéma CSL-JSON formel** — on valide par comparaison avec `pm cite` (proxy suffisant)

---

## Résumé des phases

| Phase | Quoi | Dépend de | Parallélisable |
|-------|------|-----------|----------------|
| 1 | Enrichir ArticleRecord + `article_to_csl()` + filtrage legacy | — | Non |
| 2 | Flag `--csl` sur pm parse + exports + streaming | Phase 1 | Non |
| 3 | Flag `--csl` sur pm collect | Phase 2 | Non |
| 4 | Validation live + golden files CSL-JSON | Phase 2 | **Oui (2 agents)** |
| 5 | Documentation (spec.md, plan.md) | Phase 3+4 | Non |
| Gate | `/adversarial-review` | Phase 5 | Non |
