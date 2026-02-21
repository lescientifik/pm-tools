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
from typing import Literal

@dataclass
class PmcResult:
    url: str
    format: Literal["pdf", "tgz"]
```

**Pourquoi un dataclass plutôt qu'un tuple/dict** : type-safe, extensible, autodocumenté.
Le dataclass est interne au module — pas un breaking change pour les users de `find_pdf_sources()`.

**Pourquoi `Literal` plutôt que `str`** : type-safe, empêche les valeurs invalides,
meilleur support IDE/pyright.

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
MAX_PDF_MEMBER_SIZE = 200 * 1024 * 1024  # 200 MB

def _extract_pdf_from_tgz(content: bytes, pmcid: str = "") -> bytes | None:
    """Extract the PDF file from a PMC tar.gz archive.

    Returns the PDF content or None if no PDF found in the archive.
    Prefers PDF files whose name contains the PMCID pattern.
    Skips members larger than MAX_PDF_MEMBER_SIZE to guard against
    decompression bombs.
    """
```

Utilise `tarfile.open(fileobj=io.BytesIO(content))` pour lire en mémoire.
Cherche le fichier `.pdf` dans l'archive, en préférant celui dont le nom
contient le PMCID. Retourne son contenu.

**Pourquoi en mémoire** : les archives PMC font typiquement < 20 Mo. Le download
est déjà en mémoire (`response.content`). Pas besoin de streaming ici.
C'est une divergence délibérée par rapport à CLAUDE.md ("prefer streaming")
car le download amont est déjà en mémoire et la complexité du streaming
ne se justifie pas pour < 20 Mo.

**Sécurité tarfile** : on utilise `extractfile()` qui retourne un file-like objet
en mémoire **sans écrire sur le disque**. Aucun appel à `extract()` ou `extractall()`
n'est fait, ce qui évite les vulnérabilités de path traversal (CVE-2007-4559).
Un guard `member.size > MAX_PDF_MEMBER_SIZE` protège contre les decompression bombs.

### Heuristique pour choisir le bon PDF dans l'archive

Les archives PMC peuvent contenir plusieurs PDFs (article principal + suppléments).
Stratégie de sélection :

1. Collecter tous les membres `.pdf` avec `member.isfile()` et `member.size <= MAX_PDF_MEMBER_SIZE`
2. Si un seul → le retourner
3. Si plusieurs → préférer celui dont le nom contient le PMCID (ex: `PMC12345` dans le chemin)
4. Si aucun match PMCID → prendre le plus gros (heuristique : l'article principal est
   généralement plus volumineux que les suppléments)

### Dans `download_pdfs()` : branchement sur le format

```python
content = response.content
if not content:
    ...

# Handle tgz archives: extract PDF from archive
if source.get("pmc_format") == "tgz":
    pdf_content = _extract_pdf_from_tgz(content, source.get("pmcid", ""))
    if not pdf_content:  # None ou b"" — pas de PDF exploitable
        logger.warning("PMID %s: no PDF found in tgz archive from %s", pmid, url)
        result["failed"] += 1
        if progress_callback:
            progress_callback({"pmid": pmid, "status": "failed", "reason": "tgz_no_pdf", "url": url})
        continue
    content = pdf_content

out_file.write_bytes(content)
```

**Note** : `if not pdf_content:` couvre à la fois `None` et `b""` (PDF vide dans l'archive).

### Comportement quand pdf ET tgz sont disponibles

Priorité : `pdf` > `tgz`. Le code cherche d'abord `format="pdf"` (pas de changement).
Le `tgz` n'est utilisé que comme fallback quand aucun lien `pdf` n'est disponible.

---

## Plan TDD par phase

### Règle transversale : à chaque fin de phase

Après chaque phase GREEN :
1. `uv run pytest` — vérifier la non-régression de TOUS les tests
2. `uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/` — lint + format
3. Phase REFACTOR si besoin
4. **Commit** avec message approprié (un commit par phase)

### Phase 9.0 — `PmcResult` + refactoring `pmc_lookup()` + migration `find_pdf_sources()` (atomique)

> **Pourquoi atomique** : changer le type de retour de `pmc_lookup()` sans adapter
> `find_pdf_sources()` en même temps casserait les tests entre les deux phases
> (l'ancien code stocke le résultat directement comme URL string dans le dict source).
> Les 3 reviewers (correctness, completeness, TDD) convergent sur cette fusion.

**Micro-étape 9.0a — Créer `PmcResult` dataclass :**
- [ ] Test : `PmcResult` peut être importé et instancié avec `url` et `format`

**Micro-étape 9.0b — Refactorer `pmc_lookup()` + migrer tests existants :**
- [ ] Test : `pmc_lookup()` XML avec `format="pdf"` → `PmcResult(url=..., format="pdf")`
- [ ] Test : `pmc_lookup()` XML avec `format="tgz"` seulement → `PmcResult(url=..., format="tgz")`
- [ ] Test : `pmc_lookup()` XML avec pdf + tgz → retourne le PDF (priorité)
- [ ] Test : `pmc_lookup()` sans aucun lien → `None`
- [ ] Test : FTP→HTTPS conversion sur URL pdf (existant, adapté pour PmcResult.url)
- [ ] Test : FTP→HTTPS conversion sur URL tgz
- [ ] Test : `pmc_lookup()` log DEBUG indiquant le format trouvé

**Tests existants à migrer :**
- `TestPmcLookupFtpUrls.test_ftp_url_converted_to_https` : `result.startswith("https://")` → `result.url.startswith("https://")`
- Import de `PmcResult` ajouté en haut du fichier test

**Micro-étape 9.0c — Adapter `find_pdf_sources()` :**
- [ ] Test : source dict contient `pmc_format: "pdf"` quand PDF direct
- [ ] Test : source dict contient `pmc_format: "tgz"` quand tgz seulement
- [ ] Test : pas de `pmc_format` quand source est unpaywall
- [ ] Test : pas de `pmc_format` quand source est None

**Changement dans `find_pdf_sources()` :**
```python
# Avant :
pdf_url = pmc_lookup(pmcid)
if pdf_url:
    sources.append({"url": pdf_url, ...})

# Après :
pmc_result = pmc_lookup(pmcid)
if pmc_result is not None:  # PmcResult est toujours truthy — il faut tester is not None
    sources.append({
        "url": pmc_result.url,
        "pmc_format": pmc_result.format,
        ...
    })
```

**Attention truthiness** : un dataclass est toujours truthy (`bool(PmcResult(url="", format="pdf"))` → True).
Le test `if pmc_result:` serait toujours True, même avec une URL vide.
On utilise `if pmc_result is not None:` explicitement.

**Vérification** : `uv run pytest` + `uv run ruff check` + `uv run ruff format --check`

**Commit** : `refactor: change pmc_lookup return type to PmcResult, support tgz links`

### Phase 9.1 — `_extract_pdf_from_tgz()` (TDD, fonction pure)

**Tests d'abord :**
- [ ] Test : archive avec PDF dans sous-répertoire (`PMC12345/paper.pdf`) → retourne le contenu
- [ ] Test : archive avec plusieurs PDFs → préfère celui contenant le PMCID dans le nom
- [ ] Test : archive avec plusieurs PDFs sans match PMCID → retourne le plus gros
- [ ] Test : archive sans .pdf (que des .xml, .jpg) → retourne None
- [ ] Test : données invalides (pas un tgz : HTML, bytes aléatoires) → retourne None
- [ ] Test : archive tgz vide → retourne None
- [ ] Test : PDF vide (0 bytes) dans l'archive → retourne None (pas `b""`)
- [ ] Test : membre tgz > MAX_PDF_MEMBER_SIZE → ignoré (guard decompression bomb)

**Implémentation :**
```python
import io
import tarfile

MAX_PDF_MEMBER_SIZE = 200 * 1024 * 1024  # 200 MB

def _extract_pdf_from_tgz(content: bytes, pmcid: str = "") -> bytes | None:
    try:
        with tarfile.open(fileobj=io.BytesIO(content), mode="r:gz") as tar:
            pdf_members = [
                m for m in tar.getmembers()
                if m.name.lower().endswith(".pdf")
                and m.isfile()
                and 0 < m.size <= MAX_PDF_MEMBER_SIZE
            ]
            if not pdf_members:
                return None
            # Prefer member whose name contains the PMCID
            if pmcid:
                pmcid_lower = pmcid.lower()
                matching = [m for m in pdf_members if pmcid_lower in m.name.lower()]
                if matching:
                    pdf_members = matching
            # Among remaining, pick the largest (main article vs supplement)
            best = max(pdf_members, key=lambda m: m.size)
            f = tar.extractfile(best)
            if f is None:
                return None
            data = f.read()
            return data if data else None
    except (tarfile.TarError, OSError):
        return None
```

**Création des fixtures** : helper module-level `_make_tgz(files: dict[str, bytes]) -> bytes`
dans le fichier test (à côté de `_art()`, `_make_transport()`).

```python
def _make_tgz(files: dict[str, bytes]) -> bytes:
    """Create an in-memory tar.gz archive from a dict of {name: content}."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, data in files.items():
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()
```

**Vérification** : `uv run pytest` + `uv run ruff check` + `uv run ruff format --check`

**Commit** : `feat: add _extract_pdf_from_tgz with PMCID-aware selection`

### Phase 9.2 — Extraction tgz dans `download_pdfs()` (TDD)

**Tests d'abord :**
- [ ] Test : `pmc_format="tgz"` + archive avec PDF → extrait et sauvegarde le PDF
- [ ] Test : `pmc_format="tgz"` + archive sans PDF → failed + log WARNING
- [ ] Test : `pmc_format="tgz"` + HTML response (soft 404, bytes `b"<html>..."`) → failed + log WARNING
- [ ] Test : `pmc_format="tgz"` + PDF vide dans archive → failed + log WARNING
- [ ] Test : `pmc_format="pdf"` → comportement direct inchangé
- [ ] Test : source sans `pmc_format` (unpaywall) → comportement direct inchangé
- [ ] Test : log DEBUG "extracting PDF from tgz archive" quand format est tgz
- [ ] Test : `progress_callback` reçoit `{"status": "failed", "reason": "tgz_no_pdf"}` quand extraction échoue
- [ ] Test : `progress_callback` reçoit `{"status": "downloaded"}` quand extraction réussit

**Implémentation :**
- Ajouter le branchement tgz dans `download_pdfs()` après le check `content` vide
- `if not pdf_content:` (couvre None ET b"")
- Logger WARNING si extraction échoue
- Fire `progress_callback` avec `reason: "tgz_no_pdf"` si applicable

**Vérification** : `uv run pytest` + `uv run ruff check` + `uv run ruff format --check`

**Commit** : `feat: handle tgz archive extraction in download_pdfs`

### Phase 9.3 — Tests d'intégration end-to-end (TDD)

**Tests d'abord :**
- [ ] Test E2E : JSONL input avec PMCID → API retourne tgz seulement → PDF extrait et sauvegardé
- [ ] Test E2E : deux articles, un avec pdf direct, un avec tgz → les deux téléchargés
- [ ] Test E2E : article avec tgz mais archive corrompue → failed avec diagnostic
- [ ] Test : dry-run affiche "PDF available via pmc" même quand c'est un tgz (même message, transparent pour l'utilisateur)
- [ ] Test : le résumé final compte correctement les tgz extraits comme "downloaded"

**Note dry-run** : on garde le même message "PDF available via pmc" sans mentionner tgz.
L'extraction est un détail d'implémentation transparent pour l'utilisateur.
En mode verbose, le logger affiche les détails (format, extraction).

**Implémentation :**
- Mock complet : PMC OA API → tgz URL → tgz content → PDF extrait
- Utiliser le helper `_make_tgz()` pour créer les fixtures

**Vérification** : `uv run pytest` + `uv run ruff check` + `uv run ruff format --check`

**Commit** : `test: add end-to-end tests for tgz extraction pipeline`

### Phase 9.4 — Quality gate et commit final

- [ ] Tous les tests passent (`uv run pytest`)
- [ ] Lint passe (`uv run ruff check src/ tests/`)
- [ ] Format passe (`uv run ruff format --check src/ tests/`)
- [ ] Code review via `/reviewing-code`

---

## Fichiers à modifier

| Fichier | Changement |
|---------|------------|
| `src/pm_tools/download.py` | `PmcResult` dataclass, refactor `pmc_lookup()`, `_extract_pdf_from_tgz()`, modifier `find_pdf_sources()` et `download_pdfs()` |
| `tests/test_download.py` | Nouveaux tests + fixtures tgz + helper `_make_tgz()` + migration test FTP existant |

## Fichiers NON modifiés

- `spec.md` — pas de changement de spécification
- `plan.md` — mise à jour des checkboxes seulement après implémentation
- API publique de `find_pdf_sources()` et `download_pdfs()` — inchangée (backward-compatible)

## Tests existants à migrer

| Test | Changement | Phase |
|------|-----------|-------|
| `TestPmcLookupFtpUrls.test_ftp_url_converted_to_https` | `result.startswith(...)` → `result.url.startswith(...)` | 9.0b |
| Import en haut de `test_download.py` | Ajouter `PmcResult` à l'import | 9.0a |

## Risques et mitigations

| Risque | Mitigation |
|--------|------------|
| Archives > 100 Mo en mémoire | Archives PMC typiquement < 20 Mo. Divergence délibérée vs CLAUDE.md "prefer streaming" — justifiée car download déjà en mémoire. |
| Archive sans PDF | `_extract_pdf_from_tgz()` retourne None → failed avec log WARNING |
| Decompression bomb | Guard `member.size > MAX_PDF_MEMBER_SIZE` (200 Mo) — skip les membres trop gros |
| Path traversal dans tarfile | On utilise `extractfile()` uniquement (lecture mémoire). Aucun `extract()`/`extractall()`. |
| Multiple PDFs dans archive | Heuristique : préférer le PDF dont le nom contient le PMCID, sinon le plus gros |
| PDF vide dans archive | `if not pdf_content:` couvre None et `b""` |
| Soft 404 (HTML au lieu de tgz) | `tarfile.open()` échoue sur HTML → `TarError` → retourne None |
| PmcResult truthiness | `if pmc_result is not None:` au lieu de `if pmc_result:` dans `find_pdf_sources()` |
| Régression tests existants | Migration explicite de `TestPmcLookupFtpUrls` en phase 9.0b |
| `PmcResult` breaking change | Interne au module. API publique (`find_pdf_sources`, `download_pdfs`) inchangée |

## Principes

- TDD strict : tests d'abord, refactor après chaque GREEN
- Un commit par phase (conformité CLAUDE.md)
- Phase 9.0 atomique (type change + caller migration ensemble)
- Fonction pure `_extract_pdf_from_tgz()` facile à tester isolément
- Backward-compatible : l'API publique ne change pas
- Les articles avec `format="pdf"` direct continuent de fonctionner comme avant
- Le tgz est un fallback, pas le chemin principal
- Progress callback enrichi pour les nouveaux failure modes
