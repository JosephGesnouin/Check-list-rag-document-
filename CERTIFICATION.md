# Rapport de certification

Certification end-to-end exécutée par `certify.py`. Elle couvre :

1. **Chemin vert** – le document de référence
   `samples/20260506_Guidelines_KMDoc_Reference.docx` doit obtenir
   Feu Vert et zéro non-conformité bloquante.
2. **Chemin rouge** – le document `samples/guidelines.docx`,
   volontairement non conforme, doit déclencher Feu Rouge avec un
   set de bloquants attendu.
3. **Remédiation** – le plan généré sur le chemin rouge doit être
   appliquable, faire baisser le nombre de bloquants, augmenter le
   score, et être idempotent.
4. **Sorties** – PDF (magic `%PDF`), ZIP (magic `PK`), guide
   Markdown non vide et nominatif.
5. **Registry** – les 30 règles attendues sont enregistrées et
   exécutables.

## Reproduction

```bash
pip install -r requirements.txt
python3 certify.py
```

Le script :

- régénère les deux échantillons `samples/*.docx` ;
- exécute les 22 assertions ci-dessous ;
- affiche un récapitulatif et renvoie le nombre d'échecs comme code
  de sortie.

## Dernier résultat

```
Certification: 22/22 checks passed.
```

| # | Scénario     | Assertion                                           | Mesure                                      |
|---|--------------|-----------------------------------------------------|---------------------------------------------|
| 1 | Vert         | Reference doc parses without warning                | parse_warning is None                       |
| 2 | Vert         | Reference doc → Feu Vert                            | verdict=Feu Vert, score=98.6, blockers KO=0 |
| 3 | Vert         | Reference doc has zero blocking failures            | blocking_failures=[]                        |
| 4 | Vert         | Reference doc score >= threshold (80)               | 98.6 ≥ 80                                   |
| 5 | Vert         | All explicit-blocker rules return PASS              | 11/11 BLOCKER rules PASS                    |
| 6 | Vert         | H34 cartouche email correctly classified as author  | jane.doe@interne.example masquée             |
| 7 | Rouge        | Bad doc → Feu Rouge                                 | verdict=Feu Rouge, score=44.2               |
| 8 | Rouge        | Bad doc raises the expected blocker set             | A1, A3, A4, A5, B6, B7, B9, F26, H34        |
| 9 | Remédiation  | Plan is non-empty                                   | 7 actions générées                          |
| 10| Remédiation  | Patch produced bytes                                | DOCX corrigé exporté                        |
| 11| Remédiation  | Patch applied at least the expected actions         | rename, cartouche, objectif, glossaire,     |
|   |              |                                                     | symbols, clean_urls, redact_sensitive       |
| 12| Remédiation  | Re-audit improves score                             | 44.2 → 86.5                                 |
| 13| Remédiation  | Re-audit reduces blocker count                      | 8 → 1                                       |
| 14| Remédiation  | Auto-remediable failures are resolved               | Aucune des règles auto-corrigibles ne reste |
|   |              |                                                     | en FAIL (A4 reste car non-automatisable)    |
| 15| Remédiation  | Patcher is idempotent (score stable on 2nd pass)    | 86.5 → 86.5                                 |
| 16| Sorties      | PDF starts with %PDF magic header                   | b'%PDF'                                     |
| 17| Sorties      | PDF size > 4 KB                                     | 8328 octets                                 |
| 18| Sorties      | ZIP starts with PK magic header                     | b'PK'                                       |
| 19| Sorties      | Markdown guide is non-empty                         | len > 0                                     |
| 20| Sorties      | Markdown guide mentions filename                    | nom du fichier source présent               |
| 21| Registry     | Registry has 30 rules                               | count=30                                    |
| 22| Registry     | All expected rule IDs are present                   | A1..A5, B6..B9, C10..C11, D12..D18, E19,    |
|   |              |                                                     | F25..F27, G28..G34, H34                     |

## Détail du chemin vert

Audit complet du document de référence (30 règles) :

| Statut | Sévérité | Règle                                                    |
|--------|----------|----------------------------------------------------------|
| PASS   | BLOCKER  | A1 Nommage du fichier                                    |
| PASS   | BLOCKER  | A2 Cartouche renseigné (10 champs détectés)              |
| PASS   | BLOCKER  | A3 Objectif/description en début                         |
| PASS   | BLOCKER  | A4 Acronymes développés (KM, IA)                         |
| PASS   | BLOCKER  | A5 Glossaire présent                                     |
| PASS   | BLOCKER  | B6 Titres descriptifs et hiérarchisés (niveaux 1+2)      |
| PASS   | BLOCKER  | B7 Densité de titres suffisante (8 titres / 1 page)      |
| NV     | MAJOR    | B8 Pas de boîtes/cadres inutiles (réservé PPTX)          |
| PASS   | BLOCKER  | B9 Pas de symboles dans les phrases                      |
| PASS   | MAJOR    | C10 Légendes d'images (aucune image)                     |
| PASS   | MAJOR    | C11 Qualité d'image (aucune image)                       |
| PASS   | BLOCKER  | D12 Pas de cellules fusionnées (aucun tableau)           |
| PASS   | MINOR    | D13 Bordures de tableaux                                 |
| PASS   | MAJOR    | D14 En-têtes de tableau                                  |
| PASS   | MAJOR    | D15 Titres de tableau                                    |
| PASS   | MAJOR    | D16 Pas de symboles dans les cellules                    |
| PASS   | MINOR    | D17 Pagination de tableaux                               |
| PASS   | BLOCKER  | D18 Tableau natif (pas image)                            |
| NV     | MINOR    | E19 Diagrammes (réservé PPTX)                            |
| PASS   | MAJOR    | F25 URLs avec contexte                                   |
| PASS   | MAJOR    | F26 URLs nettoyées                                       |
| PASS   | MAJOR    | F27 URLs en clair                                        |
| PASS   | MINOR    | G28 Pas de coupures de mots                              |
| PASS   | MINOR    | G29 Format DOCX                                          |
| PASS   | MINOR    | G30 Document de longueur raisonnable                     |
| PASS   | MINOR    | G31 Pas d'en-têtes/pieds                                 |
| PASS   | MINOR    | G32 Phrases courtes                                      |
| NV     | MINOR    | G33 Alignement (réservé PPTX/PDF)                        |
| PASS   | MINOR    | G34 Paragraphes de longueur raisonnable                  |
| PASS   | BLOCKER  | H34 Aucune donnée client/personnelle                     |

Les 1.4 points manquants pour atteindre 100/100 viennent des trois
règles `NOT_VERIFIABLE` (B8, E19, G33) : ce sont des contrôles
intrinsèquement réservés à PPTX/PDF, pondérés à 0.7 pour ne pas
pénaliser injustement un format DOCX bien formé.

## Améliorations livrées dans cette itération

- **G34 Paragraphes de longueur raisonnable** – nouvelle règle qui
  utilise enfin le paramètre `max_paragraph_chars` exposé dans l'UI
  mais auparavant inutilisé dans le moteur d'audit.
- **A4 forme étendue** – la détection accepte désormais aussi la
  forme `Expansion (ACR)` en plus de `ACR (Expansion)` et
  `ACR : Expansion`.
- **Loader DOCX – URLs en texte brut** – les URLs présentes dans le
  texte (sans hyperlien Word) sont désormais extraites et
  contrôlées par F25/F26.
- **Heuristique H34 plus stricte** – un email n'est considéré comme
  email d'auteur que si le label `Auteur` apparaît dans la zone
  cartouche. Sans cartouche, tous les emails sont signalés.
- **Patcher remédiation étendu** – le masquage couvre maintenant les
  adresses postales (`[adresse retirée]`) et les identifiants
  client (`[id client retiré]`), pas seulement emails / téléphones /
  IBAN.

## Limites connues (par conception)

- **A4 non automatisable** – développer un acronyme inconnu nécessite
  une connaissance métier ; le patcher se contente donc de signaler
  l'écart et le bad doc conserve A4 en FAIL après patching.
- **`NOT_VERIFIABLE` sur DOCX** – B8, E19 et G33 sont par nature des
  contrôles spécifiques aux formats présentation ou flux PDF.
- **PDF scannés** – `PyPDF2` n'effectue pas d'OCR ; un PDF
  image-only produira un `parse_warning` explicite et la plupart
  des règles textuelles seront `NOT_VERIFIABLE`.
