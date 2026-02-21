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

**Problèmes supplémentaires identifiés :**
- Le `progress_callback` envoie `reason: "http_error"` sans le code HTTP réel (`download.py:243`)
- `download_pdfs()` catch `(httpx.HTTPError, OSError)` à la ligne 260 sans logger l'exception
- Réponse vide (ligne 250-254) : aucun diagnostic
- Retry exhaustion (3x 503) : aucun log spécifique

## Architecture de la solution

### Approche : `logging` stdlib avec niveaux DEBUG/WARNING

Utiliser le module `logging` de Python plutôt que de passer `verbose: bool` partout.
- `logging.getLogger("pm_tools.download")` dans le module
- `main()` configure le logger directement (pas `basicConfig` — voir note ci-dessous)
- Chaque fonction core log ses erreurs à `WARNING` et ses détails à `DEBUG`
- Pas besoin de modifier les signatures de fonctions

**Avantages :**
- Minimal invasif (pas de changement d'API)
- Diagnostic complet en mode verbose
- Les erreurs critiques (failures) toujours visibles sur stderr
- Compatible avec le `progress_callback` existant

### Note architecturale : divergence avec le reste du codebase

Ce sera le premier module du projet à utiliser `logging` stdlib. Les autres modules
(`fetch.py`, `search.py`, etc.) utilisent `print(..., file=sys.stderr)` avec un bool
`verbose`. Ce choix est **délibéré** : `logging` est supérieur pour le diagnostic
multi-niveau (WARNING toujours visible, DEBUG en mode verbose) et évite de propager
des paramètres `verbose: bool` dans toutes les fonctions core. Ce pattern pourra
servir de modèle pour migrer les autres modules dans un futur refactoring.

### Stratégie logging vs progress_callback (dé-duplication)

**Problème :** En mode `--verbose`, le `logger.warning(...)` et le `_verbose_progress`
callback afficheraient chaque échec deux fois sur stderr.

**Solution :** Rôles séparés :
- **`logger`** : diagnostic technique (WARNING/DEBUG) → toujours actif sur stderr
- **`progress_callback`** : données structurées pour usage programmatique uniquement
- **`_verbose_progress`** dans `main()` : **supprimé** — le logger le remplace

Concrètement, dans `main()`, le `progress_callback` ne sera plus connecté à
`_verbose_progress`. Le logger se charge de l'affichage stderr. Le callback est
passé à `None` dans `main()` (l'audit est déjà géré par `download_pdfs()` via
`pm_dir`, pas par le callback). Le callback reste disponible pour les appels
programmatiques (bibliothèque) mais `main()` ne l'utilise plus.

### Configuration du logger (pas de `basicConfig`)

**Piège connu :** `logging.basicConfig()` ne fait rien si des handlers existent déjà
(cas fréquent avec pytest, IDE, etc.).

**Solution :** Configurer le logger nommé directement dans `main()` :
```python
logger = logging.getLogger("pm_tools.download")
if not logger.handlers:  # Guard against handler accumulation (multiple main() calls in tests)
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
logger.setLevel(logging.DEBUG if verbose else logging.WARNING)
```

**Note :** Le guard `if not logger.handlers` évite l'accumulation de handlers quand
`main()` est appelé plusieurs fois (fréquent dans les tests pytest).

---

## Plan TDD par phase

### Règle transversale : à chaque fin de phase

Après chaque phase GREEN :
1. `uv run pytest` — vérifier la non-régression de TOUS les tests
2. `uv run ruff check src/ tests/` — linting
3. Phase REFACTOR : si des patterns de logging se répètent, extraire un helper

### Phase 8.0 — Setup : introduire le logger (TDD)

**Tests d'abord :**
- [ ] Test : le logger `"pm_tools.download"` existe et est correctement nommé
- [ ] Test trivial avec `caplog` pour valider le setup (exemple pattern pour le projet)

**Implémentation :**
- Ajouter `import logging` et `logger = logging.getLogger(__name__)` en haut de `download.py`
- Pas de changement de comportement — juste poser l'infrastructure

**Pattern `caplog` pour le projet** (première utilisation) :
```python
import logging

def test_example_caplog_pattern(caplog):
    """Squelette montrant comment capturer les logs dans ce projet."""
    with caplog.at_level(logging.DEBUG, logger="pm_tools.download"):
        # ... appeler la fonction ...
        pass
    # Vérifier les logs
    assert any("expected message" in r.message for r in caplog.records)
    # Ou vérifier le niveau
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
```

**Vérification :** `uv run pytest` — tous les tests existants passent toujours.

### Phase 8.1 — Ajouter logging à `pmc_lookup()` (TDD)

**Tests d'abord :**
- [ ] Test : log WARNING quand HTTP status != 200 (inclut le status code)
- [ ] Test : log WARNING quand `<error` trouvé dans la réponse
- [ ] Test : log WARNING quand `ET.ParseError` (inclut le message d'erreur)
- [ ] Test : log DEBUG avec l'URL requêtée
- [ ] Test : log WARNING quand `httpx.HTTPError` (réseau)

**Implémentation :**
- Remplacer `except ET.ParseError: pass` par un log WARNING avec le message d'erreur
- Ajouter `logger.debug("PMC lookup: %s", url)` avant la requête
- Ajouter `logger.warning("PMC lookup %s: HTTP %d", pmcid, status)` pour les erreurs HTTP
- Ajouter `logger.warning("PMC lookup %s: API error in response", pmcid)` pour `<error`
- Ajouter `logger.warning("PMC lookup %s: %s", pmcid, e)` pour les erreurs réseau

**Vérification :** `uv run pytest` + `uv run ruff check`

### Phase 8.2 — Ajouter logging à `unpaywall_lookup()` (TDD)

**Tests d'abord :**
- [ ] Test : log WARNING quand HTTP status != 200 (inclut status)
- [ ] Test : log WARNING quand `JSONDecodeError`
- [ ] Test : log WARNING quand `httpx.HTTPError` (réseau)
- [ ] Test : log DEBUG avec l'URL requêtée
- [ ] Test : log DEBUG "not open access" quand `is_oa` est False

**Implémentation :**
- Séparer le `except (httpx.HTTPError, json.JSONDecodeError)` en deux clauses distinctes
- Logger le type d'erreur et le message dans chaque clause
- Ajouter log DEBUG pour les cas non-OA (ce n'est pas une erreur, c'est attendu)

**Vérification :** `uv run pytest` + `uv run ruff check`

### Phase 8.3 — Ajouter logging à `find_pdf_sources()` (TDD)

**Tests d'abord :**
- [ ] Test : log WARNING quand `except Exception` attrapé (avec traceback)
- [ ] Test : log DEBUG avec la raison du "no source" (pas de PMCID, pas de DOI, API a retourné None, etc.)

**Implémentation :**
- Remplacer `except Exception: pass` par un log WARNING avec `exc_info=True`
- Ajouter des logs DEBUG pour chaque branche de décision

**Note :** Pas de log INFO pour le résumé ici (serait invisible avec le niveau
WARNING par défaut). Le résumé reste dans `main()` via `print(file=sys.stderr)`,
qui est une sortie utilisateur, pas un log.

**Vérification :** `uv run pytest` + `uv run ruff check`

### Phase 8.4 — Enrichir `download_pdfs()` avec diagnostics (TDD)

**Tests d'abord :**
- [ ] Test : log WARNING avec le **code HTTP réel** quand le download échoue
- [ ] Test : log WARNING avec l'**URL** et le **PMID** pour chaque échec
- [ ] Test : log WARNING avec le message d'exception pour `httpx.HTTPError` / `OSError`
- [ ] Test : log WARNING quand la réponse est vide (contenu vide)
- [ ] Test : log WARNING quand les retries sont épuisés (3x 503) avec nombre de tentatives
- [ ] Test : `progress_callback` inclut `status_code` et `url` dans l'event dict
- [ ] Test : le résumé final `print(file=sys.stderr)` s'affiche toujours (même sans `--verbose`)

**Implémentation :**
- Ajouter `logger.warning(...)` dans chaque branche d'échec
- Inclure le code HTTP réel : `logger.warning("PMID %s: HTTP %d from %s", pmid, response.status_code, url)`
- Enrichir le dict passé à `progress_callback` : ajouter `status_code` et `url`
- Le résumé "Downloaded: X, Failed: Y" utilise `print(file=sys.stderr)` (pas le logger) — c'est une sortie utilisateur
- Modifier la condition du résumé dans `main()` : remplacer `if verbose or total > 0`
  par un affichage inconditionnel (le résumé doit toujours apparaître quand il y a des sources)

**Note :** L'ajout de clés dans le dict du callback est backward-compatible
(ajout, pas modification). Les tests existants ne vérifient que `pmid` et `status`,
ils ne casseront pas.

**Vérification :** `uv run pytest` + `uv run ruff check`

### Phase 8.5 — Configurer logging dans `main()` + test d'intégration (TDD)

**Tests d'abord :**
- [ ] Test : sans `--verbose`, les WARNING s'affichent sur stderr (raisons des échecs)
- [ ] Test : sans `--verbose`, les DEBUG ne s'affichent PAS (mode silencieux propre)
- [ ] Test : avec `--verbose`, les DEBUG s'affichent aussi (URLs, détails API)
- [ ] Test : le résumé final s'affiche toujours sur stderr
- [ ] Test : dry-run avec verbose montre les URLs qui seraient utilisées
- [ ] **Test d'intégration du repro case** : deux PMIDs, un échoue HTTP 403, l'autre sans source → stderr contient les diagnostics attendus (format vérifié)

**Implémentation :**
- Configurer le logger nommé directement (pas `basicConfig`) — voir section Architecture
- Supprimer `_verbose_progress` : le logger remplace l'affichage stderr
- Le `progress_callback` dans `main()` devient `None` (l'audit est géré par `pm_dir`, pas le callback)
- Format des messages WARNING : `"PMID 30623617: failed — HTTP 403 from https://..."`

**Migration du test existant :** Le test `test_verbose_shows_per_article_status`
(ligne 431 de `test_download.py`) cassera car il vérifie la sortie de `_verbose_progress`
via `capsys`. Ce test doit être adapté pour vérifier la sortie du logger via `caplog`
(ou via `capsys` si le handler stderr est actif). Ajouter un commentaire inline
expliquant la migration.

**Test d'intégration (repro case de l'issue) :**
```python
def test_issue_8_repro_diagnostics(tmp_path, monkeypatch, capsys, caplog):
    """Repro case from issue #8: two failing PMIDs must produce diagnostics."""
    import logging
    with caplog.at_level(logging.WARNING, logger="pm_tools.download"):
        # Setup: one PMID returns 403, one has no PMC source
        # ...
        exit_code = download_main(["--input", str(input_file), "--output-dir", str(output_dir), "--pmc-only"])

    # stderr must explain WHY each PMID failed
    captured = capsys.readouterr()
    assert "HTTP 403" in captured.err or "HTTP 403" in caplog.text
    assert "Downloaded: 0" in captured.err
    assert "Failed: 2" in captured.err
```

**Vérification :** `uv run pytest` + `uv run ruff check`

### Phase 8.6 — Review et commit

- [ ] Tous les tests passent (`uv run pytest`)
- [ ] ruff check passe (`uv run ruff check src/ tests/`)
- [ ] Code review via `/reviewing-code`
- [ ] Commit : `fix: add diagnostic output for download failures (closes #8)`
- [ ] Comportement attendu après correction :
  ```
  # Sans --verbose :
  #   PMID 30623617: failed — HTTP 403 from https://ftp.ncbi.nlm.nih.gov/...
  #   PMID 35350465: failed — no PDF URL found (no PMCID available)
  #   Downloaded: 0, Skipped: 0, Failed: 2

  # Avec --verbose :
  #   PMC lookup: https://www.ncbi.nlm.nih.gov/pmc/utils/oa/oa.fcgi?id=PMC...
  #   PMC lookup PMC12345: HTTP 403
  #   Unpaywall lookup: https://api.unpaywall.org/v2/10.1234%2Ftest?email=...
  #   Unpaywall lookup 10.1234/test: not open access
  #   PMID 30623617: failed — HTTP 403 from https://...
  #   PMID 35350465: failed — no PDF URL found (no PMCID available)
  #   Downloaded: 0, Skipped: 0, Failed: 2
  ```

---

## Fichiers à modifier

| Fichier | Changement |
|---------|------------|
| `src/pm_tools/download.py` | Ajouter `logging`, enrichir les messages d'erreur, supprimer `_verbose_progress` |
| `tests/test_download.py` | Ajouter tests pour les logs (`caplog` fixture pytest) + test d'intégration repro case |

## Fichiers NON modifiés

- `spec.md` — pas de changement de spécification
- `plan.md` — mise à jour des checkboxes seulement après implémentation
- API publique des fonctions — inchangée (pas de breaking change)

## Principes

- TDD strict : tests d'abord, refactor après chaque GREEN
- `logging` stdlib avec logger nommé (pas `basicConfig`)
- Les messages d'erreur sont concrets : PMID + URL + code HTTP + raison
- Le résumé utilisateur reste un `print(file=sys.stderr)`, pas un log
- Mode silencieux par défaut : WARNING visibles, DEBUG masqués
- Mode verbose (`--verbose`) : DEBUG aussi visibles
- Pas de duplication : le logger remplace `_verbose_progress`
- Non-régression vérifiée après chaque phase
