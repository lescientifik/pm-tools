---
description: Ideas and future improvements to explore, not yet planned or specced.
---

# TODOs / Ideas

## Publication types in ArticleRecord

Explorer l'extraction des `<PublicationType>` MeSH depuis le XML PubMed et les exposer
dans l'ArticleRecord (nouveau champ optionnel `publication_types: list[str]`).

**Contexte :** Le XML contient des tags riches :
```xml
<PublicationTypeList>
  <PublicationType UI="D016428">Journal Article</PublicationType>
  <PublicationType UI="D016454">Review</PublicationType>
  <PublicationType UI="D016449">Randomized Controlled Trial</PublicationType>
</PublicationTypeList>
```

**Intérêt :**
- Permettre à `pm filter` de filtrer par type (reviews, essais cliniques, méta-analyses...)
- Information utile pour MedInk (distinguer review vs article original)
- Données déjà disponibles dans le XML, pas d'appel réseau supplémentaire

**Note :** Ceci est distinct du champ CSL-JSON `type` qui est hardcodé `"article-journal"`
pour tout le contenu PubMed (vérifié sur données réelles). Les `PublicationType` MeSH
sont une classification plus fine et complémentaire.

**À considérer :**
- Impact sur les golden files existantes (nouveau champ dans la sortie)
- Compatibilité avec les consommateurs downstream (filter, diff, MedInk)
- Faut-il aussi exposer le `UI` (identifiant MeSH) en plus du texte ?
