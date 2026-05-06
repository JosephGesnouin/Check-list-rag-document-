# Rapport de certification

Certification end-to-end exécutée par `certify.py` après alignement
sur la **typologie officielle KM Initiative readiness** (catégories
A à G de la checklist source, plus H *Données sensibles* et I
*Bonnes pratiques générales* en extension).

Elle couvre :

1. **Chemin vert** – le document de référence
   `samples/20260506_Guidelines_KMDoc_Reference.docx` doit obtenir
   Feu Vert et zéro non-conformité bloquante.
2. **Chemin rouge** – le document `samples/guidelines.docx`,
   volontairement non conforme, doit déclencher Feu Rouge avec un
   set de règles en échec attendu.
3. **Remédiation** – le plan généré sur le chemin rouge doit être
   appliquable, faire baisser le nombre de bloquants, augmenter le
   score, et être idempotent.
4. **Sorties** – PDF (magic `%PDF`), ZIP (magic `PK`), guide
   Markdown non vide et nominatif.
5. **Registry** – les 35 règles attendues (alignées sur la typologie)
   sont enregistrées et exécutables.

## Reproduction

```bash
pip install -r requirements.txt
python3 certify.py
```

## Dernier résultat

```
Certification: 23/23 checks passed.
```

| # | Scénario     | Assertion                                           | Mesure                                        |
|---|--------------|-----------------------------------------------------|-----------------------------------------------|
| 1 | Vert         | Reference doc parses without warning                | parse_warning is None                         |
| 2 | Vert         | Reference doc → Feu Vert                            | verdict=Feu Vert, score=97.4, blockers KO=0   |
| 3 | Vert         | Reference doc has zero blocking failures            | blocking_failures=[]                          |
| 4 | Vert         | Reference doc score >= threshold (80)               | 97.4 ≥ 80                                     |
| 5 | Vert         | All explicit-blocker rules return PASS              | tous les BLOCKER PASS                         |
| 6 | Vert         | H28 cartouche email correctly classified as author  | jane.doe@interne.example blanchie              |
| 7 | Rouge        | Bad doc → Feu Rouge                                 | verdict=Feu Rouge, score=43.3, blockers KO=8  |
| 8 | Rouge        | Bad doc raises the expected blocker set             | A1, A3, A4, B5, B6, C7, C9, G26, H28          |
| 9 | Remédiation  | Plan is non-empty                                   | 7 actions générées                            |
| 10| Remédiation  | Patch produced bytes                                | DOCX corrigé exporté                          |
| 11| Remédiation  | Patch applied at least the expected actions         | rename, cartouche, objectif, glossaire,       |
|   |              |                                                     | symbols, clean_urls, redact_sensitive         |
| 12| Remédiation  | Re-audit improves score                             | 43.3 → 85.2                                   |
| 13| Remédiation  | Re-audit reduces blocker count                      | 8 → 1                                         |
| 14| Remédiation  | Auto-remediable failures are resolved               | aucune des règles auto-corrigibles ne reste   |
|   |              |                                                     | en FAIL (C7 reste car non-automatisable)      |
| 15| Remédiation  | Patcher is idempotent (score stable on 2nd pass)    | 85.2 → 85.2                                   |
| 16| Sorties      | PDF starts with %PDF magic header                   | b'%PDF'                                       |
| 17| Sorties      | PDF size > 4 KB                                     | 9438 octets                                   |
| 18| Sorties      | ZIP starts with PK magic header                     | b'PK'                                         |
| 19| Sorties      | Markdown guide is non-empty                         | len > 0                                       |
| 20| Sorties      | Markdown guide mentions filename                    | nom du fichier source présent                 |
| 21| Registry     | Registry has 35 rules                               | count=35                                      |
| 22| Registry     | All expected rule IDs are present                   | set complet A1..A4, B5..B6, C7..C9, D10..D11, |
|   |              |                                                     | E12..E19, F20..F24, G25..G27, H28, I29..I35   |
| 23| Registry     | No unexpected rule IDs                              | aucun ID hors typologie                       |

## Détail du chemin vert (typologie officielle)

| Statut | Sévérité | Règle                                                                |
|--------|----------|----------------------------------------------------------------------|
| PASS   | BLOCKER  | A1 Nom du document conforme                                          |
| PASS   | BLOCKER  | A2 Cartouche / métadonnées renseignées (10 champs)                   |
| PASS   | BLOCKER  | A3 Description claire de l'objectif                                  |
| PASS   | BLOCKER  | A4 Glossaire central des acronymes                                   |
| PASS   | BLOCKER  | B5 Titres descriptifs, hiérarchisés et formatés                      |
| PASS   | BLOCKER  | B6 Titres et sous-titres suffisants                                  |
| PASS   | BLOCKER  | C7 Acronymes développés à 1re apparition (KM, IA)                    |
| NV     | MAJOR    | C8 Pas de boîtes/cadres inutiles (réservé PPTX)                      |
| PASS   | BLOCKER  | C9 Pas de symboles/icônes dans les phrases                           |
| PASS   | MAJOR    | D10 Légendes d'images (aucune image)                                 |
| PASS   | MAJOR    | D11 Qualité d'image (aucune image)                                   |
| PASS   | BLOCKER  | E12 Pas de cellules fusionnées (aucun tableau)                       |
| PASS   | MINOR    | E13 Bordures de tableaux                                             |
| PASS   | MAJOR    | E14 En-têtes de colonnes mis en valeur                               |
| PASS   | MAJOR    | E15 Titre explicite au-dessus du tableau                             |
| PASS   | MAJOR    | E16 Légende décrivant le contenu                                     |
| PASS   | MAJOR    | E17 Pas de symboles dans les cellules                                |
| PASS   | MINOR    | E18 Pagination des tableaux                                          |
| PASS   | BLOCKER  | E19 Tableau au format natif                                          |
| NV     | MINOR    | F20 Éléments précis (réservé PPTX)                                   |
| NV     | MINOR    | F21 Structures allégées (réservé PPTX)                               |
| NV     | MINOR    | F22 Sous-diagrammes (réservé PPTX)                                   |
| NV     | MINOR    | F23 Texte alternatif (réservé PPTX)                                  |
| NV     | MINOR    | F24 Légende explicative (réservé PPTX)                               |
| PASS   | MAJOR    | G25 URLs avec contexte (aucune URL)                                  |
| PASS   | MAJOR    | G26 URLs nettoyées                                                   |
| PASS   | MAJOR    | G27 URLs en clair                                                    |
| PASS   | BLOCKER  | H28 Aucune donnée client/personnelle                                 |
| PASS   | MINOR    | I29 Pas de coupures de mots                                          |
| PASS   | MINOR    | I30 Format DOCX                                                      |
| PASS   | MINOR    | I31 Document de longueur raisonnable                                 |
| PASS   | MINOR    | I32 Pas d'en-têtes/pieds                                             |
| PASS   | MINOR    | I33 Phrases courtes                                                  |
| NV     | MINOR    | I34 Alignement (réservé PPTX/PDF)                                    |
| PASS   | MINOR    | I35 Paragraphes de longueur raisonnable                              |

Les 2.6 points manquants pour atteindre 100/100 viennent des règles
`NOT_VERIFIABLE` (C8, F20-F24, I34) intrinsèquement réservées à PPTX
ou PDF : un DOCX bien formé est pondéré 0.7 sur ces items pour ne pas
être pénalisé injustement.

## Mapping ancienne / nouvelle numérotation

Pour les utilisateurs qui suivaient la numérotation initiale
(catégories A-H de la première implémentation) :

| Ancien ID    | Nouveau ID  | Catégorie officielle                        |
|--------------|-------------|---------------------------------------------|
| A1           | A1          | Permettre l'identification du document      |
| A2           | A2          | Permettre l'identification du document      |
| A3           | A3          | Permettre l'identification du document      |
| A4 acronyme  | C7          | Mise en forme du texte                      |
| A5 glossaire | A4          | Permettre l'identification du document      |
| B6           | B5          | Mise en forme du document et sa structure   |
| B7           | B6          | Mise en forme du document et sa structure   |
| B8           | C8          | Mise en forme du texte                      |
| B9           | C9          | Mise en forme du texte                      |
| C10          | D10         | Gestion des images                          |
| C11          | D11         | Gestion des images                          |
| D12-D14      | E12-E14     | Gestion des tableaux                        |
| D15          | E15 + E16   | Gestion des tableaux (titre + légende)      |
| D16-D18      | E17-E19     | Gestion des tableaux                        |
| E19 unique   | F20..F24    | Gestion des diagrammes / schémas (5 items)  |
| F25-F27      | G25-G27     | Gestion des URLs                            |
| G28-G34      | I29-I35     | Bonnes pratiques générales (extension)      |
| H34          | H28         | Données sensibles (extension)               |

## Améliorations apportées dans cette itération

- **Catégories renommées** pour coller exactement aux libellés de la
  checklist officielle (« Permettre l'identification du document »,
  « Mise en forme du texte », « Gestion des tableaux », etc.).
- **Acronymes à la 1re occurrence** déplacés dans la catégorie
  *Mise en forme du texte* (C7), comme dans la checklist source.
- **Glossaire centralisé** déplacé dans *Permettre l'identification
  du document* (A4) et reformulé selon le libellé officiel.
- **Tableaux** : 8 items distincts au lieu de 7, avec séparation du
  titre (E15) et de la légende (E16) du tableau.
- **Diagrammes** : un unique item E19 a été éclaté en 5 contrôles
  F20–F24 (intitulés précis, structure allégée, sous-diagrammes,
  alternative texte, légende explicative).
- **Numérotation séquentielle** alignée sur la checklist officielle
  (A1-A4, B5-B6, C7-C9, D10-D11, E12-E19, F20-F24, G25-G27).
- **Sécurité data H28** et **bonnes pratiques I29-I35** clairement
  identifiées comme extensions au-delà de la typologie officielle.

## Limites connues (par conception)

- **C7 non automatisable** – développer un acronyme inconnu nécessite
  une connaissance métier ; le patcher se contente de signaler
  l'écart et le bad doc conserve C7 en FAIL après patching.
- **`NOT_VERIFIABLE` sur DOCX** – C8, F20–F24 et I34 sont par nature
  des contrôles spécifiques aux formats présentation ou flux PDF.
- **PDF scannés** – `PyPDF2` n'effectue pas d'OCR ; un PDF
  image-only produira un `parse_warning` explicite et la plupart
  des règles textuelles seront `NOT_VERIFIABLE`.
