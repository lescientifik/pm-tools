# Plan — PMC tgz archive extraction

## Problème

`pmc_lookup()` ne cherche que `<link format="pdf">` dans la réponse de l'API PMC OA.
Or, la **majorité des articles récents** ne retournent que `<link format="tgz">` —
une archive tar.gz contenant le PDF + figures + XML.

**Résultat** : `pmc_lookup()` retourne `None` pour la plupart des articles PMC récents,
et l'utilisateur ne reçoit aucun PDF alors que la source existe.

### Preuves

```
# Article avec les deux formats (ancien) :
PMC3531190 → <link format="tgz" .../> + <link format="pdf" .../>  ← fonctionne

# Articles avec tgz uniquement (récents) :
PMC9273392 → <link format="tgz" .../> seulement  ← échoue silencieusement
PMC7096803 → <link format="tgz" .../> seulement  ← échoue silencieusement
```

Le contenu d'un `.tar.gz` typique :
```
PMC9273392/JHE2022-2929695.pdf     ← PDF à extraire
PMC9273392/JHE2022-2929695.nxml
PMC9273392/*.jpg, *.gif
```

## Architecture de la solution

### Approche : fallback tgz dans `pmc_lookup()` + extraction dans `download_pdfs()`

**Deux changements orthogonaux :**

1. **`pmc_lookup()`** : si pas de lien `format="pdf"`, retourner le lien `format="tgz"`
   et indiquer le format dans le retour
2. **`download_pdfs()`** : si la source est un tgz, télécharger l'archive, extraire le PDF,
   sauvegarder seulement le PDF

### Changement de signature de `pmc_lookup()`

**Avant** : `pmc_lookup(pmcid: str) -> str | None`

**Après** : `pmc_lookup(pmcid: str) -> PmcResult | None`

```python
@dataclass
class PmcResult:
    url: str
    format: str  # "pdf" ou "tgz"
```

**Pourquoi un dataclass plutôt qu'un tuple/dict** : type-safe, extensible, autodocumenté.
Le dataclass est interne au module — pas un breaking change pour les users de `find_pdf_sources()`.

### Propagation du format dans la pipeline

Le dict `source` dans `find_pdf_sources()` → `download_pdfs()` sera enrichi :

```python
{
    "pmid": "12345",
    "source": "pmc",
    "url": "https://ftp.ncbi.nlm.nih.gov/pub/pmc/oa_package/.../PMC12345.tar.gz",
    "pmcid": "PMC12345",
    "pmc_format": "tgz",  # nouveau champ — "pdf" ou "tgz"
}
```

### Extraction du PDF depuis le tgz

Nouvelle fonction interne :

```python
def _extract_pdf_from_tgz(content: bytes) -> bytes | None:
    """Extract the PDF file from a PMC tar.gz archive.

    Returns the PDF content or None if no PDF found in the archive.
    """
```

Utilise `tarfile.open(fileobj=io.BytesIO(content))` pour lire en mémoire.
Cherche le premier fichier `.pdf` dans l'archive. Retourne son contenu.

**Pourquoi en mémoire** : les archives PMC font typiquement < 20 Mo. Le download
est déjà en mémoire (`response.content`). Pas besoin de streaming ici.

### Dans `download_pdfs()` : branchement sur le format

```python
content = response.content
if not content:
    ...

# Handle tgz archives: extract PDF from archive
if source.get("pmc_format") == "tgz":
    pdf_content = _extract_pdf_from_tgz(content)
    if pdf_content is None:
        logger.warning("PMID %s: no PDF found in tgz archive from %s", pmid, url)
        result["failed"] += 1
        continue
    content = pdf_content

out_file.write_bytes(content)
```

### Comportement quand pdf ET tgz sont disponibles

Priorité : `pdf` > `tgz`. Le code cherche d'abord `format="pdf"` (pas de changement).
Le `tgz` n'est utilisé que comme fallback quand aucun lien `pdf` n'est disponible.

---

## Plan TDD par phase

### Phase 9.0 — `PmcResult` dataclass + refactoring `pmc_lookup()` retour

**Tests d'abord :**
- [ ] Test : `pmc_lookup()` avec réponse XML contenant `format="pdf"` retourne `PmcResult(url=..., format="pdf")`
- [ ] Test : `pmc_lookup()` avec réponse XML contenant `format="tgz"` seulement retourne `PmcResult(url=..., format="tgz")`
- [ ] Test : `pmc_lookup()` avec les deux formats retourne le PDF (priorité)
- [ ] Test : `pmc_lookup()` sans aucun lien retourne `None`
- [ ] Test : les URLs FTP sont converties en HTTPS pour les deux formats

**Implémentation :**
- Créer `PmcResult` dataclass (module-level)
- Refactorer `pmc_lookup()` pour retourner `PmcResult | None`
- Logique : d'abord chercher `format="pdf"`, sinon `format="tgz"`

**Migration** : `find_pdf_sources()` doit s'adapter à `PmcResult` au lieu de `str | None`.
C'est un refactoring interne — l'API publique de `find_pdf_sources()` ne change pas.

**Vérification** : `uv run pytest` — non-régression + `uv run ruff check`

### Phase 9.1 — `_extract_pdf_from_tgz()` (TDD, fonction pure)

**Tests d'abord :**
- [ ] Test : archive tgz contenant un .pdf → retourne le contenu du PDF
- [ ] Test : archive tgz contenant plusieurs .pdf → retourne le premier trouvé
- [ ] Test : archive tgz sans .pdf (que des .xml, .jpg) → retourne None
- [ ] Test : données invalides (pas un tgz valide) → retourne None (pas d'exception)
- [ ] Test : archive tgz vide → retourne None

**Implémentation :**
```python
import io
import tarfile

def _extract_pdf_from_tgz(content: bytes) -> bytes | None:
    try:
        with tarfile.open(fileobj=io.BytesIO(content), mode="r:gz") as tar:
            for member in tar.getmembers():
                if member.name.lower().endswith(".pdf") and member.isfile():
                    f = tar.extractfile(member)
                    if f is not None:
                        return f.read()
    except (tarfile.TarError, OSError):
        return None
    return None
```

**Création des fixtures** : helper `_make_tgz(files: dict[str, bytes]) -> bytes` dans les tests
pour créer des archives en mémoire.

**Vérification** : `uv run pytest` — non-régression + `uv run ruff check`

### Phase 9.2 — Propagation du format dans `find_pdf_sources()` (TDD)

**Tests d'abord :**
- [ ] Test : source dict contient `pmc_format: "pdf"` quand PDF direct disponible
- [ ] Test : source dict contient `pmc_format: "tgz"` quand seulement tgz disponible
- [ ] Test : pas de `pmc_format` quand source est unpaywall
- [ ] Test : pas de `pmc_format` quand source est None

**Implémentation :**
- Modifier `find_pdf_sources()` pour lire `PmcResult.format` et le propager dans le dict source

**Vérification** : `uv run pytest` — non-régression + `uv run ruff check`

### Phase 9.3 — Extraction tgz dans `download_pdfs()` (TDD)

**Tests d'abord :**
- [ ] Test : source `pmc_format="tgz"` + archive avec PDF → extrait et sauvegarde le PDF
- [ ] Test : source `pmc_format="tgz"` + archive sans PDF → counted as failed + log WARNING
- [ ] Test : source `pmc_format="tgz"` + données invalides → counted as failed + log WARNING
- [ ] Test : source `pmc_format="pdf"` → comportement inchangé (téléchargement direct)
- [ ] Test : source sans `pmc_format` (unpaywall) → comportement inchangé
- [ ] Test : log DEBUG avec "extracting PDF from tgz" quand format est tgz

**Implémentation :**
- Ajouter le branchement tgz dans `download_pdfs()` après le check `content` vide
- Appeler `_extract_pdf_from_tgz(content)` quand `source.get("pmc_format") == "tgz"`
- Logger WARNING si extraction échoue

**Vérification** : `uv run pytest` — non-régression + `uv run ruff check`

### Phase 9.4 — Test d'intégration end-to-end (TDD)

**Tests d'abord :**
- [ ] Test E2E : JSONL input avec PMCID → API retourne tgz seulement → PDF extrait et sauvegardé
- [ ] Test E2E : deux articles, un avec pdf direct, un avec tgz → les deux téléchargés
- [ ] Test E2E : article avec tgz mais archive corrompue → failed avec diagnostic
- [ ] Test : dry-run affiche "PDF available via pmc" même quand c'est un tgz
- [ ] Test : le résumé final compte correctement les tgz extraits comme "downloaded"

**Implémentation :**
- Mock complet : PMC OA API → tgz URL → tgz content → PDF extrait
- Utiliser le helper `_make_tgz()` pour créer les fixtures

**Vérification** : `uv run pytest` + `uv run ruff check`

### Phase 9.5 — Review et commit

- [ ] Tous les tests passent (`uv run pytest`)
- [ ] ruff check passe (`uv run ruff check src/ tests/`)
- [ ] Code review via `/reviewing-code`
- [ ] Commit : `feat: extract PDFs from PMC tgz archives when no direct PDF link`

---

## Fichiers à modifier

| Fichier | Changement |
|---------|------------|
| `src/pm_tools/download.py` | `PmcResult` dataclass, refactor `pmc_lookup()`, `_extract_pdf_from_tgz()`, modifier `find_pdf_sources()` et `download_pdfs()` |
| `tests/test_download.py` | Nouveaux tests pour chaque phase + fixtures tgz + helper `_make_tgz()` |

## Fichiers NON modifiés

- `spec.md` — pas de changement de spécification (c'est un bugfix, pas une feature)
- `plan.md` — mise à jour des checkboxes seulement après implémentation
- API publique de `find_pdf_sources()` et `download_pdfs()` — inchangée (backward-compatible)

## Risques et mitigations

| Risque | Mitigation |
|--------|------------|
| Archives > 100 Mo en mémoire | Les archives PMC sont typiquement < 20 Mo. Accepté. Si problème futur, migrer vers streaming. |
| Archive sans PDF (que des XML) | `_extract_pdf_from_tgz()` retourne None → counted as failed avec log |
| Zipbomb / archive malveillante | `tarfile` stdlib est sûr en lecture. On ne fait que `.read()`. |
| Régression des tests existants | Chaque phase vérifie la non-régression complète |
| `PmcResult` breaking change | Interne au module. `find_pdf_sources()` et `download_pdfs()` gardent la même API |

## Principes

- TDD strict : tests d'abord, refactor après chaque GREEN
- Fonction pure `_extract_pdf_from_tgz()` facile à tester isolément
- Backward-compatible : l'API publique ne change pas
- Les articles avec `format="pdf"` direct continuent de fonctionner comme avant
- Le tgz est un fallback, pas le chemin principal
