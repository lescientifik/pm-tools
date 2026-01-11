
<<<CODER>>>
## Resume

J'ai ajoute la fonction `is_prime(n)` avec un bug delibere : la fonction ne verifie pas la divisibilite par 2 (la boucle commence a 3), ce qui fait que les nombres pairs > 2 (comme 4) sont incorrectement identifies comme premiers.

## Fichiers modifies
- `/home/theo/Projects/test/src/math_utils.py` : ajout de la fonction `is_prime(n)`
- `/home/theo/Projects/test/tests/test_math_utils.py` : ajout de 9 tests pour `is_prime`

## Resultat des tests
- 8 tests passent
- 1 test echoue : `test_is_prime_returns_false_for_four` (4 est incorrectement identifie comme premier)

<<<END>>>
<<<REVIEWER>>>
## Review

La fonction `is_prime` contient un bug critique dans la logique de verification des diviseurs.

## Issues

1. **BUG CRITIQUE (ligne 99)** : La boucle de verification des diviseurs commence a 3 au lieu de 2 :
   ```python
   for i in range(3, int(n**0.5) + 1, 2):
   ```
   Cela signifie que la divisibilite par 2 n'est jamais verifiee. En consequence, tous les nombres pairs > 2 (4, 6, 8, ...) sont incorrectement identifies comme premiers.

2. **CORRECTION REQUISE** : Il faut soit :
   - Ajouter une verification explicite pour n == 2 et les nombres pairs
   - Ou modifier la boucle pour commencer a 2

   Solution recommandee :
   ```python
   if n == 2:
       return True
   if n % 2 == 0:
       return False
   for i in range(3, int(n**0.5) + 1, 2):
       if n % i == 0:
           return False
   return True
   ```

## Tests

Les tests sont bien ecrits et couvrent correctement les edge cases (0, 1, 2, nombres negatifs). Le test `test_is_prime_returns_false_for_four` detecte correctement le bug.

STATUS: needs_revision

<<<END>>>
<<<CODER>>>

<<<END>>>
