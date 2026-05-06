# KM Document Audit

Outil **offline** d'audit qualité « KM / IA-readiness » pour documents
DOCX, PPTX, XLSX, PDF. Applique une checklist de règles bloquantes et
non bloquantes, calcule un score, génère un rapport PDF et propose
un plan de remédiation (auto-application sur DOCX, guide Markdown
sinon).

Aucun appel réseau, aucune API externe. Tout le traitement se fait
localement à partir des fichiers chargés dans l'UI Streamlit.

---

## Sommaire

1. [Installation et exécution](#installation-et-exécution)
2. [Interface utilisateur](#interface-utilisateur)
3. [Architecture du code](#architecture-du-code)
4. [Modèle de données](#modèle-de-données)
5. [Checklist – règles évaluées](#checklist--règles-évaluées)
6. [Score et verdict](#score-et-verdict)
7. [Moteur de remédiation](#moteur-de-remédiation)
8. [Étendre l'outil](#étendre-loutil)
9. [Limites et garanties](#limites-et-garanties)
10. [Self-check et tests](#self-check-et-tests)

---

## Installation et exécution

```bash
pip install -r requirements.txt
streamlit run app.py
# Ou, sans UI : python3 app.py --self-check
```

Dépendances : `streamlit`, `python-docx`, `python-pptx`, `openpyxl`,
`PyPDF2`, `Pillow`, `numpy`, `reportlab`. Toutes les dépendances de
parsing sont importées de manière défensive : si une lib manque, le
chargeur correspondant signale `parse_warning` au lieu de crasher.

---

## Interface utilisateur

L'UI Streamlit se compose de trois onglets et d'une barre latérale
**Paramètres**.

### Barre latérale – Paramètres

| Paramètre                        | Effet                                                       |
|----------------------------------|-------------------------------------------------------------|
| `max_paragraph_chars`            | Longueur max d'un paragraphe (réservé à des règles futures) |
| `max_avg_sentence_words`         | Cible pour la longueur moyenne des phrases (G32)            |
| `min_image_width` / `_height`    | Résolution minimale acceptée pour les images (C11)          |
| `blur_variance_threshold`        | Seuil de variance Laplacien sous lequel l'image est floue   |
| `long_doc_pages`                 | Au-dessus, le document est jugé trop long (G30)             |
| `min_headings_per_pages`         | Densité minimale de titres (B7)                             |
| `score_pass_threshold`           | Score requis pour Feu Vert                                  |
| `weight_blocking` / `_practices` | Pondération bloquantes vs bonnes pratiques (somme = 100)    |

Les paramètres sont injectés dans les règles via la dataclass
`Settings` (frozen, donc hashable et utilisable comme clé de cache).

### Onglet « Audit »

Upload multi-fichiers → pour chaque document :

- carte de synthèse : verdict (Feu Vert / Orange / Rouge), score /100,
  nb bloquants KO, nb avertissements ;
- bloc « Points bloquants » s'il y en a ;
- expander « Détail des règles » par catégorie ;
- bouton **Générer PDF** par document ;
- bouton **Tout télécharger (ZIP)** si plusieurs documents.

### Onglet « Remédiation »

Pour chaque document chargé :

- résumé identique à l'onglet Audit ;
- liste cochable des **actions correctives** détectées par
  `build_plan()` ;
- bouton **Appliquer & re-auditer** : applique les actions cochées
  (DOCX → patch in-place ; autres formats → rename suggéré
  uniquement) puis ré-exécute l'audit sur les bytes corrigés et
  affiche le delta de score ;
- bouton **Générer guide Markdown** : produit un `.md` détaillant
  chaque action, sa faisabilité automatique et les points résiduels
  qui demandent une intervention manuelle.

### Onglet « Règles / Checklist »

Affiche le nombre de règles enregistrées dans la registry et un
résumé par catégorie (A à H) du périmètre couvert.

---

## Architecture du code

```
app.py                          UI Streamlit (couche fine)
requirements.txt
km_audit/                       Package métier (offline, sans I/O réseau)
├── __init__.py                 Surface API publique
├── config.py                   Settings, regex, constantes (champs cartouche, symboles…)
├── models.py                   Status / Severity (Enum), RuleResult, ParsedDoc, DocumentAuditResult
├── loaders.py                  Parsing DOCX / PPTX / XLSX / PDF, variance Laplacien
├── sensitive.py                Détection + masquage email / phone / IBAN / adresse / id client
├── scoring.py                  Calcul score pondéré et verdict
├── audit.py                    Orchestrateur audit_document(name, raw, settings)
├── reporting.py                Rapport PDF (ReportLab) + bundle ZIP
├── remediation.py              Plan + patcher DOCX + guide Markdown
└── rules/                      Registry de règles (un module par catégorie)
    ├── __init__.py             Registry + décorateur @register + run_all
    ├── _helpers.py             truncate, full_text
    ├── identification.py       A1–A5
    ├── structure.py            B6–B9
    ├── images.py               C10–C11
    ├── tables.py               D12–D18
    ├── diagrams.py             E19
    ├── urls.py                 F25–F27 + helper clean_url()
    ├── practices.py            G28–G33
    └── sensitive.py            H34
```

### Flux d'exécution

```
upload (bytes)
    │
    ▼
loaders.load(name, raw) ────► ParsedDoc
                                 │
                                 ▼
                        rules.run_all(parsed, settings)
                                 │
                                 ▼
                          List[RuleResult]
                                 │
                  ┌──────────────┼──────────────┐
                  ▼              ▼              ▼
            scoring.compute  reporting       remediation
              (score,         .generate_     .build_plan
               verdict)        pdf_report     .patch_document
                                              .render_markdown_guide
```

### Choix d'architecture

- **Registry par décorateur** (`@register`) : ajouter une règle =
  écrire une fonction et la décorer ; `rules/__init__.py` importe
  tous les sous-modules pour amorcer la registry. Pas de plug-in
  loader dynamique, mais la séparation par catégorie évite
  l'explosion d'un fichier monolithique.
- **`Settings` frozen dataclass** : passé à chaque règle en deuxième
  argument. Hash-friendly, donc utilisable dans la clé de
  `st.cache_data` (`Settings.cache_key()`).
- **Loaders défensifs** : chaque parser tolère l'absence de la lib
  associée et l'erreur d'extraction (mis dans `parse_warning`).
- **Couche UI fine** : `app.py` ne contient ni regex métier ni logique
  d'audit — uniquement la composition Streamlit et le rendu.

---

## Modèle de données

```python
class Status(Enum):
    PASS, FAIL, WARN, NOT_VERIFIABLE

class Severity(Enum):
    BLOCKER, MAJOR, MINOR

@dataclass
class RuleResult:
    rule_id: str          # ex: "A1", "F26"
    category: str         # "A".."H"
    title: str
    status: Status
    severity: Severity
    evidence: str         # extrait court / métrique
    location: str         # page/slide approx (souvent vide)
    recommendation: str   # action textuelle pour l'utilisateur
    remediable: bool      # True si une action automatique existe

@dataclass
class ParsedDoc:
    file_name: str; file_type: str; raw_bytes: bytes
    text_blocks: List[str]
    headings: List[Tuple[int, str]]            # (level, text)
    tables: List[Dict[str, Any]]               # rows, merged, header_bold, …
    images: List[Dict[str, Any]]               # width, height, blur, slide
    urls: List[str]
    hyperlinks: List[Tuple[str, str]]          # (display, target)
    pages: int
    extra: Dict[str, Any]                      # specifics par format
    parse_warning: Optional[str]

@dataclass
class DocumentAuditResult:
    file_name: str; file_type: str; file_size: int; audit_date: str
    rules: List[RuleResult]
    metrics: Dict[str, Any]
    score: float; verdict: str
    parse_error: Optional[str]
    # propriétés: blocking_failures, failures, warnings
```

---

## Checklist – règles évaluées

35 règles regroupées en 9 catégories alignées sur la typologie officielle
*KM Initiative readiness*. Sévérité **BLOQUANT** (B) marque les normes ;
un seul échec bloquant ⇒ verdict **Feu Rouge** quel que soit le score.

| ID  | Catégorie                                | Règle                                                                      | Sévérité | Remédiable |
|-----|------------------------------------------|----------------------------------------------------------------------------|----------|------------|
| A1  | Permettre l'identification du document   | Nom du document conforme (AAAAMMJJ_Sujet_Type_Infos)                       | B        | oui        |
| A2  | Permettre l'identification du document   | Informations renseignées (cartouche / métadonnées)                         | B        | oui        |
| A3  | Permettre l'identification du document   | Description claire de l'objectif dans les métadonnées                      | B        | oui        |
| A4  | Permettre l'identification du document   | Acronymes/termes ajoutés (ou vérifiés) au glossaire centralisé             | B        | oui        |
| B5  | Mise en forme du document et sa structure| Titres descriptifs, hiérarchisés et correctement formatés                  | B        | non        |
| B6  | Mise en forme du document et sa structure| Titres et sous-titres suffisants                                           | B        | non        |
| C7  | Mise en forme du texte                   | Acronymes/abréviations expliqués à leur 1re apparition                     | B        | non        |
| C8  | Mise en forme du texte                   | Texte hors boîtes/cadres (textbox) inutiles                                | B / MAJ  | non        |
| C9  | Mise en forme du texte                   | Pas de logos/symboles/icônes dans les phrases                              | B        | oui        |
| D10 | Gestion des images                       | Légende sous chaque image informative                                      | B / MAJ  | non        |
| D11 | Gestion des images                       | Qualité des images (résolution, netteté)                                   | MAJ      | non        |
| E12 | Gestion des tableaux                     | Pas de cellules fusionnées                                                 | B        | non        |
| E13 | Gestion des tableaux                     | Bordures visibles (idéalement noires sur fond blanc)                       | MAJ/MIN  | non        |
| E14 | Gestion des tableaux                     | En-têtes de colonnes clairs et mis en valeur                               | MAJ      | non        |
| E15 | Gestion des tableaux                     | Titre explicite au-dessus du tableau                                       | MAJ      | non        |
| E16 | Gestion des tableaux                     | Légende décrivant le contenu du tableau                                    | MAJ      | non        |
| E17 | Gestion des tableaux                     | Symboles / codes couleurs remplacés par des mots                           | MAJ      | oui        |
| E18 | Gestion des tableaux                     | Pagination / en-têtes répétés sur plusieurs pages                          | MIN      | non        |
| E19 | Gestion des tableaux                     | Tableau au format natif (pas image / capture)                              | B        | non        |
| F20 | Gestion des diagrammes / schémas         | Éléments des diagrammes nommés précisément (pas « Étape 1 »)               | MIN      | non        |
| F21 | Gestion des diagrammes / schémas         | Structures allégées (pas de surcharge)                                     | MIN      | non        |
| F22 | Gestion des diagrammes / schémas         | Diagrammes découpés en sous-diagrammes thématiques                         | MIN      | non        |
| F23 | Gestion des diagrammes / schémas         | Texte structuré privilégié si plus accessible                              | MIN      | non        |
| F24 | Gestion des diagrammes / schémas         | Légende explicative décrivant la logique                                   | MIN      | non        |
| G25 | Gestion des URLs                         | URLs introduites par un texte clair (contexte)                             | MAJ      | non        |
| G26 | Gestion des URLs                         | URLs nettoyées (paramètres session/tracking retirés)                       | MAJ      | oui        |
| G27 | Gestion des URLs                         | URLs affichées en clair (pas masquées)                                     | MAJ      | non        |
| H28 | Données sensibles                        | Aucune donnée client / personnelle détectée                                | B        | oui        |
| I29 | Bonnes pratiques générales               | Pas de coupures de mots/paragraphes                                        | MIN      | non        |
| I30 | Bonnes pratiques générales               | Format DOCX privilégié                                                     | MIN      | non        |
| I31 | Bonnes pratiques générales               | Document de longueur raisonnable                                           | MIN      | non        |
| I32 | Bonnes pratiques générales               | Pas d'en-têtes/pieds de page superflus                                     | MIN      | non        |
| I33 | Bonnes pratiques générales               | Phrases courtes et simples                                                 | MIN      | non        |
| I34 | Bonnes pratiques générales               | Alignement à gauche (PPT/PDF)                                              | MIN      | non        |
| I35 | Bonnes pratiques générales               | Paragraphes ≤ `max_paragraph_chars`                                        | MIN      | non        |

Catégories **A à G** correspondent à la typologie officielle ; **H** et
**I** sont des extensions imposées par le dispositif KM (sécurité data
+ bonnes pratiques générales).

### Détection des données sensibles (H28)

`km_audit/sensitive.py` repère :

- **emails** (hors auteur — un email apparu dans la zone cartouche
  près du label « Auteur/Email/Contact » est ignoré),
- **téléphones** (≥ 8 chiffres pour limiter les faux positifs),
- **IBAN** (`[A-Z]{2}\d{2}…` 14 à 34 caractères),
- **adresses postales** (motif numéro + voie),
- **identifiants client / customer / account / compte**.

Les valeurs détectées sont **masquées** dans le rapport PDF
(`j***@domaine.com`, `***12`, `FR***0123`).

### Heuristiques notables

- **Hiérarchie de titres (B5)** : DOCX via styles `Heading N`, PPTX via
  titres de slide, PDF via heuristique sur lignes courtes/numérotées.
- **Qualité image (D11)** : variance d'un noyau Laplacien 3×3 appliqué
  via PIL, comparée à `blur_variance_threshold`.
- **Acronymes (C7)** : `\b[A-Z]{2,10}\b` puis recherche de
  `ACR (Définition)`, `ACR : Définition`, ou `Définition (ACR)` autour
  de la première occurrence.
- **Diagrammes (F20-F24)** : heuristiques PPTX sur le nombre de shapes
  par slide (≥15 surchargé, ≥20 candidat texte alternatif, ≥25
  hyper-dense) et la présence de libellés génériques type « Étape N ».

---

## Score et verdict

`scoring.compute(rules, settings)` :

```
ratio_blocking  = moyenne(weight[status]) sur les règles BLOCKER
ratio_practices = moyenne(weight[status]) sur les autres
score           = ratio_blocking  * settings.weight_blocking
                + ratio_practices * settings.weight_practices

weight = { PASS: 1.0, WARN: 0.5, NOT_VERIFIABLE: 0.7, FAIL: 0.0 }

if any rule.is_blocker_fail():     verdict = "Feu Rouge"
elif score >= score_pass_threshold: verdict = "Feu Vert"
else:                               verdict = "Feu Orange"
```

Le score est **explicable** : le rapport PDF contient un tableau
`Règle / Statut / Sévérité / Preuve / Recommandation` par catégorie
plus la liste des bloquants en synthèse.

---

## Moteur de remédiation

`km_audit/remediation.py` traduit les règles en échec en `ActionKind`
typés et applique celles que l'utilisateur sélectionne.

### Actions disponibles

| `ActionKind`        | Déclenchée par | Effet (DOCX)                                                                |
|---------------------|----------------|-----------------------------------------------------------------------------|
| `RENAME_FILE`       | A1 FAIL        | Suggère `AAAAMMJJ_<Sujet>_KMDoc[_Extra].ext`                                |
| `INJECT_CARTOUCHE`  | A2 FAIL/NV     | Insère un titre + paragraphes pour les 10 champs obligatoires               |
| `INJECT_OBJECTIVE`  | A3 FAIL        | Insère une section Objectif à compléter après le cartouche                  |
| `INJECT_GLOSSARY`   | A4 FAIL        | Ajoute une section Glossaire + tableau acronyme/définition en fin           |
| `REPLACE_SYMBOLS`   | C9/E17 FAIL    | Substitue ✓ → oui, ✗ → non, ➜ → ->, … dans paragraphes et cellules          |
| `CLEAN_URLS`        | G26 FAIL       | Retire `utm_*`, `gclid`, `fbclid`, `session*`, `token`, `auth`, `tracking`  |
| `REDACT_SENSITIVE`  | H28 FAIL       | Remplace les emails/téléphones/IBAN/adresses par leur version masquée       |

### API

```python
from km_audit import (
    audit_document,
    build_plan,
    patch_document,
    render_markdown_guide,
    DEFAULT_SETTINGS,
)

result   = audit_document("notes.docx", raw_bytes, DEFAULT_SETTINGS)
plan     = build_plan(result)              # RemediationPlan
outcome  = patch_document(                  # PatchOutcome
    "notes.docx", raw_bytes, plan,
    enabled_kinds=[a.kind for a in plan.actions],
)
# outcome.patched_bytes : DOCX corrigé (None pour non-DOCX hors rename)
# outcome.applied / .skipped / .error / .file_name

guide_md = render_markdown_guide(result, plan)   # str
```

### Comportement par format

- **DOCX** : patch in-place complet (toutes les actions ci-dessus).
- **PPTX / XLSX / PDF** : seul `RENAME_FILE` est appliqué (rebaptise
  le téléchargement). Le reste est listé dans `outcome.skipped` ; le
  guide Markdown détaille la procédure manuelle équivalente.

### Idempotence

Les injections (`INJECT_CARTOUCHE`, `INJECT_OBJECTIVE`,
`INJECT_GLOSSARY`) déposent des marqueurs (`[CARTOUCHE]`,
`[OBJECTIF]`, `[GLOSSAIRE]`) et sont no-op si le marqueur est déjà
présent : on peut ré-appliquer le plan sans dupliquer les sections.

### Test d'intégration de référence

DOCX volontairement non conforme (✓ dans phrase, IBAN, URL avec
`utm_source` + `token`, pas de cartouche/objectif/glossaire) :

| Étape           | Verdict     | Score   | Bloquants KO                                  |
|-----------------|-------------|---------|-----------------------------------------------|
| Avant patch     | Feu Rouge   | 43.3    | A1, A3, A4, B5, B6, C7, C9, G26 (FAIL), H28   |
| Après patch     | Feu Rouge   | 85.2    | C7 (acronymes — manuel)                       |

C7 reste KO car développer un acronyme sans en connaître la
signification métier ne peut pas être automatisé.

---

## Étendre l'outil

### Ajouter une nouvelle règle

1. Choisir la catégorie (`km_audit/rules/<cat>.py`).
2. Écrire une fonction `(parsed: ParsedDoc, settings: Settings) -> RuleResult`.
3. La décorer avec `@register`.
4. Documenter brièvement dans `app.py::_RULES_DOC` (résumé onglet
   Règles).

```python
from . import register
from ..models import RuleResult, Status, Severity

@register
def rule_my_check(parsed, settings) -> RuleResult:
    if condition_ok:
        return RuleResult("X99", "X", "Mon contrôle",
                          Status.PASS, Severity.MAJOR)
    return RuleResult(
        "X99", "X", "Mon contrôle",
        Status.FAIL, Severity.MAJOR,
        evidence="…", recommendation="…",
        remediable=False,
    )
```

Aucune autre modification n'est nécessaire :
`rules/__init__.py::run_all()` itère sur la registry et le
scoring/reporting consomment les `RuleResult` indifféremment.

### Ajouter une action de remédiation

1. Étendre l'enum `ActionKind` dans `km_audit/remediation.py`.
2. Ajouter un constructeur `_action_<name>(...)` et le brancher dans
   `build_plan()` selon les règles concernées.
3. Si l'action s'applique au DOCX, écrire un helper
   `_docx_<name>(doc)` et l'invoquer dans la dispatch
   `patch_document()`.
4. Documenter dans le tableau ci-dessus et dans le guide Markdown
   (le rendu utilise déjà `action.title` / `description`).

### Ajouter un format

1. Implémenter `_load_<ext>(parsed)` dans `km_audit/loaders.py` et
   l'enregistrer dans `_LOADERS`.
2. Ajouter le format dans `app.py` (`type=[…]` du `file_uploader`)
   et `_mime_for()`.

---

## Limites et garanties

- **Aucun trafic réseau** : le code n'importe ni `requests`, ni
  `urllib`, ni de SDK. Toutes les libs sont de la lecture/écriture
  locale. Le `requirements.txt` ne contient que des libs de parsing
  et de rendu.
- **Heuristiques** : certains contrôles (B6 hiérarchie, C10 légendes,
  D15 titres, G33 alignement, F25 contexte URL) reposent sur des
  motifs textuels et peuvent produire des faux positifs/négatifs.
  Ils sont étiquetés `WARN` plutôt que `FAIL` quand l'ambiguïté est
  intrinsèque.
- **`NOT_VERIFIABLE`** : utilisé quand le format ne permet pas
  l'extraction automatique (ex : bordures de tableau hors XLSX,
  hyperliens PDF). Le rapport PDF rappelle qu'une revue manuelle
  est nécessaire pour ces points.
- **PDF scannés** : `PyPDF2` n'effectue pas d'OCR ; un PDF image-only
  produit un `parse_warning` explicite.
- **Données sensibles dans le rapport** : les valeurs brutes ne sont
  jamais inscrites dans le PDF — toujours masquées par
  `mask_email/phone/iban`.

---

## Self-check et tests

### Self-check (rapide, sans I/O)

```bash
python3 app.py --self-check
```

Vérifie regex de nommage, nettoyage d'URL, masquage email/IBAN et
intégrité de la dataclass `Settings`.

### Certification end-to-end

```bash
python3 certify.py
```

Régénère deux échantillons (`samples/20260506_Guidelines_KMDoc_Reference.docx`
et `samples/guidelines.docx`) puis exécute 22 assertions couvrant le
chemin vert, le chemin rouge, la remédiation (avec idempotence), la
génération PDF/ZIP/Markdown et la registry.

Voir [CERTIFICATION.md](CERTIFICATION.md) pour le détail du dernier
résultat (22/22 PASS, score Feu Vert 98.6 sur la référence, score
44.2 → 86.5 après remédiation automatique du document non conforme).

### Document de référence

```bash
python3 samples/generate_reference.py     # crée le DOCX vert
python3 samples/generate_bad.py           # crée le DOCX rouge
```

Les générateurs sont idempotents et chaque structure (cartouche,
glossaire, anti-patterns) est annotée avec la règle qu'elle vise à
satisfaire ou à enfreindre.
