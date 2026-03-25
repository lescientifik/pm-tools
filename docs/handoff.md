---
description: Handoff briefing for the simplification refactoring of pm-tools, ready to execute.
---

# Handoff: pm-tools Simplification Refactoring

## Contexte

pm-tools est un CLI Python (3,502 SLOC, 1 dep runtime `httpx`) pour interroger PubMed : `pm search | pm fetch | pm parse | pm filter`. Pipeline Unix-style, JSONL natif.

Une **adversarial review** a identifié 3 CRITICAL + 9 MAJOR findings autour de : code dupliqué, faux streaming, types non exploités, arg parsing copié-collé 10 fois.

## Quoi faire

Exécuter le roadmap : **`docs/roadmap/simplification-roadmap.md`**

6 phases, 3 review gates, objectif -250 SLOC net + meilleure clarté types + vrai streaming XML.

### Phases en résumé

| Phase | Quoi | Méthode | Effort |
|-------|------|---------|--------|
| 0 | Supprimer `fetch_stream()` (dead code) | Refactoring-under-green | Trivial |
| 1 | Fusionner `cache_dir`/`pm_dir` en un seul param | Refactoring-under-green | ~28 tests à renommer |
| 2 | Extraire : HTTP client partagé, JSONL util, `cached_batch_fetch()` | TDD (nouveau code) | 3 sous-phases |
| 3 | TypedDicts pour schemas implicites + suppr. `PmcResult` | TDD (nouveau code) | 3 agents parallèles |
| 4 | Remplacer 10 arg parsers hand-rolled par `argparse` | Refactoring-under-green | Le plus gros volume |
| 5 | Vrai streaming `ET.iterparse` dans `parse_xml_stream()` | Refactoring-under-green | Le plus risqué |

Review gates (`/adversarial-review`) après phases 2, 4, et en final.

## Fichiers clés à lire

| Fichier | Rôle |
|---------|------|
| `docs/roadmap/simplification-roadmap.md` | **Le plan détaillé à suivre** — TDD steps, critères de complétion, parallélisation |
| `docs/research/adversarial-review-r1.md` | Les findings qui motivent chaque phase |
| `docs/research/sloc-baseline.md` | Baseline SLOC (3,502 src / 8,445 tests) pour mesurer le gain |
| `spec.md` | Spécifications du projet |
| `CLAUDE.md` | Conventions du projet (TDD, ruff, uv, git commits) |

## Points d'attention

1. **Phases 0, 1, 4, 5 = refactoring-under-green** — pas de faux tests RED, les tests existants sont le filet de sécurité.
2. **Phases 2, 3 = vrai TDD** — écrire les tests d'abord (RED), implémenter (GREEN).
3. **Phase 1** : ~28 call sites dans les tests utilisent `cache_dir=` → renommer en `pm_dir=`.
4. **Phase 4** : `argparse` change le format des erreurs. Accepter le format argparse, updater ~16 assertions dans les tests.
5. **Phase 5** : `parse_article(elem)` n'accède qu'au sous-arbre → compatible `iterparse` + `elem.clear()`. Golden files = filet de sécurité.
6. **`count_matching()`** : garder (2 tests existants), contrairement à ce que la review initiale suggérait.
7. **M9 (double-parse cache)** et **M1 (streaming fetch→parse)** : explicitement hors scope, documenté.

## Commandes de base

```bash
uv run pytest              # tous les tests
uv run ruff check src/ tests/  # lint
uv run ruff format src/ tests/ # format
```

## Pour démarrer

```
1. Lire docs/roadmap/simplification-roadmap.md
2. git status (vérifier branche propre)
3. Commencer Phase 0
```
