# Plan correctif — Issue #8: pm download silent failures

## Résumé de l'issue

`pm download` échoue silencieusement sans fournir de diagnostic quand les téléchargements PDF échouent. Le flag `--verbose` n'apporte aucune information utile.

## Vérification de l'issue

**5 points signalés, 5 confirmés dans le code :**

| # | Claim | Vérifié | Localisation |
|---|-------|---------|--------------|
| 1 | `pmc_lookup()` — `except ET.ParseError: pass` silencieux | **OUI** | `download.py:78-79` |
| 2 | `unpaywall_lookup()` — pas de logging des erreurs HTTP/JSON | **OUI** (handling existe, logging absent) | `download.py:89-95` |
| 3 | `find_pdf_sources()` — retourne `source: None` sans raison | **OUI** + `except Exception: pass` silencieux | `download.py:159-169` |
| 4 | `download_pdfs()` — erreurs uniquement via `progress_callback` | **OUI** — sans callback, échecs comptés mais pas expliqués | `download.py:238-269` |
| 5 | `--verbose` ineffectif dans les fonctions core | **OUI** — aucune des 3 fonctions lookup n'a de paramètre verbose | `download.py:55-101, 104-171` |

**Problème supplémentaire identifié :**
- Le `progress_callback` envoie `reason: "http_error"` sans le code HTTP réel (`download.py:243`)
- `download_pdfs()` catch `(httpx.HTTPError, OSError)` à la ligne 260 sans logger l'exception

## Architecture de la solution

### Approche : `logging` stdlib avec niveaux DEBUG/WARNING

Utiliser le module `logging` de Python plutôt que de passer `verbose: bool` partout.
- `logging.getLogger("pm_tools.download")` dans le module
- `main()` configure le niveau : `WARNING` par défaut, `DEBUG` avec `--verbose`
- Chaque fonction core log ses erreurs à `WARNING` et ses détails à `DEBUG`
- Pas besoin de modifier les signatures de fonctions

**Avantages :**
- Minimal invasif (pas de changement d'API)
- Diagnostic complet en mode verbose
- Les erreurs critiques (failures) toujours visibles sur stderr
- Compatible avec le `progress_callback` existant

---

## Plan TDD par phase

### Phase 8.1 — Ajouter logging à `pmc_lookup()` (TDD)

**Tests d'abord :**
- [ ] Test : `pmc_lookup()` log WARNING quand HTTP status != 200 (inclut le status code)
- [ ] Test : `pmc_lookup()` log WARNING quand `<error` trouvé dans la réponse
- [ ] Test : `pmc_lookup()` log WARNING quand `ET.ParseError` (inclut le message d'erreur)
- [ ] Test : `pmc_lookup()` log DEBUG avec l'URL requêtée
- [ ] Test : `pmc_lookup()` log WARNING quand `httpx.HTTPError` (réseau)

**Implémentation :**
- Ajouter `logger = logging.getLogger("pm_tools.download")` en haut du module
- Remplacer `except ET.ParseError: pass` par un log WARNING avec le message d'erreur
- Ajouter `logger.debug("PMC lookup: %s", url)` avant la requête
- Ajouter `logger.warning("PMC lookup %s: HTTP %d", pmcid, status)` pour les erreurs HTTP
- Ajouter `logger.warning("PMC lookup %s: API error in response", pmcid)` pour `<error`

### Phase 8.2 — Ajouter logging à `unpaywall_lookup()` (TDD)

**Tests d'abord :**
- [ ] Test : `unpaywall_lookup()` log WARNING quand HTTP status != 200 (inclut status)
- [ ] Test : `unpaywall_lookup()` log WARNING quand `JSONDecodeError`
- [ ] Test : `unpaywall_lookup()` log WARNING quand `httpx.HTTPError` (réseau)
- [ ] Test : `unpaywall_lookup()` log DEBUG avec l'URL requêtée
- [ ] Test : `unpaywall_lookup()` log DEBUG "not open access" quand `is_oa` est False

**Implémentation :**
- Séparer le `except (httpx.HTTPError, json.JSONDecodeError)` en deux clauses distinctes
- Logger le type d'erreur et le message dans chaque clause
- Ajouter log DEBUG pour les cas non-OA (ce n'est pas une erreur, c'est attendu)

### Phase 8.3 — Ajouter logging à `find_pdf_sources()` (TDD)

**Tests d'abord :**
- [ ] Test : log WARNING quand `except Exception` attrapé (avec traceback)
- [ ] Test : log DEBUG avec la raison du "no source" (pas de PMCID, pas de DOI, API a retourné None, etc.)
- [ ] Test : log INFO résumé en fin de boucle ("N sources found, M failed")

**Implémentation :**
- Remplacer `except Exception: pass` par un log WARNING avec `exc_info=True`
- Ajouter des logs DEBUG pour chaque branche de décision
- Ajouter un résumé à la fin

### Phase 8.4 — Enrichir `download_pdfs()` avec diagnostics (TDD)

**Tests d'abord :**
- [ ] Test : log WARNING avec le **code HTTP réel** quand le download échoue (pas juste "http_error")
- [ ] Test : log WARNING avec l'**URL** et le **PMID** pour chaque échec
- [ ] Test : log WARNING avec le message d'exception pour `httpx.HTTPError` / `OSError`
- [ ] Test : `progress_callback` inclut le `status_code` dans l'event dict pour les erreurs HTTP
- [ ] Test : le résumé final s'affiche toujours sur stderr (même sans `--verbose`)

**Implémentation :**
- Ajouter `logger.warning(...)` dans chaque branche d'échec
- Enrichir le dict passé à `progress_callback` : ajouter `status_code` et `url`
- Le résumé "Downloaded: X, Failed: Y" doit **toujours** s'afficher (pas seulement en verbose)

### Phase 8.5 — Configurer logging dans `main()` + stderr toujours utile (TDD)

**Tests d'abord :**
- [ ] Test : sans `--verbose`, les WARNING s'affichent sur stderr (raisons des échecs)
- [ ] Test : avec `--verbose`, les DEBUG s'affichent aussi (URLs, détails API)
- [ ] Test : le résumé final s'affiche toujours sur stderr
- [ ] Test : format des messages stderr : `"PMID 30623617: failed — HTTP 403 from https://..."`
- [ ] Test : dry-run avec verbose montre les URLs qui seraient utilisées

**Implémentation :**
- `logging.basicConfig(level=logging.WARNING, stream=sys.stderr, format="%(message)s")`
- Si `--verbose` : `logger.setLevel(logging.DEBUG)`
- Modifier `_verbose_progress` pour inclure le status_code et l'URL

### Phase 8.6 — Review et commit

- [ ] Tous les tests passent (`uv run pytest`)
- [ ] ruff check passe (`uv run ruff check src/ tests/`)
- [ ] Code review via `/reviewing-code`
- [ ] Commit : `fix: add diagnostic output for download failures (closes #8)`
- [ ] Vérifier que le scénario de l'issue fonctionne :
  ```
  # Avant : "Downloaded: 0, Failed: 2" (aucune explication)
  # Après :
  #   PMID 30623617: failed — HTTP 403 from https://...
  #   PMID 35350465: failed — no PDF URL found (PMCID: PMC1234, PMC OA returned None)
  #   Downloaded: 0, Skipped: 0, Failed: 2
  ```

---

## Fichiers à modifier

| Fichier | Changement |
|---------|------------|
| `src/pm_tools/download.py` | Ajouter `logging`, enrichir les messages d'erreur |
| `tests/test_download.py` | Ajouter tests pour les logs (caplog fixture pytest) |

## Fichiers NON modifiés

- `spec.md` — pas de changement de spécification
- `plan.md` — mise à jour des checkboxes seulement après implémentation
- API publique des fonctions — inchangée (pas de breaking change)

## Principes

- TDD strict : tests d'abord
- `logging` stdlib, pas de print debug
- Les messages d'erreur sont concrets : PMID + URL + code HTTP + raison
- Mode silencieux par défaut mais les **échecs** sont toujours signalés sur stderr
- Mode verbose ajoute les détails de diagnostic (URLs requêtées, réponses API)
