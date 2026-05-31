# KM Document Audit — Récapitulatif fonctionnel pour le métier

Ce document est destiné aux interlocuteurs métier (KM Auditors, sponsors
Domino, relecteurs qualité). Il ne contient pas de code. Il décrit
**ce que fait l'outil aujourd'hui** et **comment chaque demande métier
formulée pendant le projet a été traduite dans le code**.

Pour la documentation technique (architecture, contribution, code
source), voir `README.md` et `CERTIFICATION.md`.

---

## 1. À quoi sert l'outil

Application Streamlit **locale et offline** permettant d'auditer la
qualité « IA-Readiness » d'un ou plusieurs documents avant intégration
dans la base KM.

Formats acceptés : **DOCX, PPTX, XLSX, PDF**.

Pour chaque document :

1. L'outil **parse** le fichier sans appeler aucun service externe.
2. Il **applique une checklist** de règles regroupées par catégories
   (typologie officielle « Permettre l'identification du document »,
   « Mise en forme du texte », « Gestion des tableaux »…).
3. Il calcule un **score sur 100** et un **verdict tricolore**
   (Feu Vert / Feu Orange / Feu Rouge).
4. Il génère un **rapport PDF** détaillé.
5. Il propose, le cas échéant, un **plan de remédiation**
   (renommage, masquage de données sensibles, etc.) qui peut être
   appliqué automatiquement sur les DOCX.

### Lecture rapide des feux

| Verdict | Fourchette de score | Sens |
| --- | --- | --- |
| 🟢 Feu Vert | ≥ 80 et aucun bloquant en échec | Le document peut être intégré tel quel. |
| 🟠 Feu Orange | 50 à 79 | Le document est utilisable mais quelques règles bloquantes sont en alerte. |
| 🔴 Feu Rouge | Au moins un bloquant en FAIL, ou score < 50 | Le document doit être corrigé avant intégration. |

Quatre statuts par règle :

- ✅ **PASS** : conforme.
- ⚠️ **WARN** : alerte, à vérifier.
- ❌ **FAIL** : non conforme.
- ❔ **N/V** : non vérifiable automatiquement, à revoir manuellement.

---

## 2. Périmètre de la checklist (état actuel)

Après prise en compte du retour métier (cf. §4), la checklist se présente
ainsi. **Les règles bloquantes sont celles qui peuvent à elles seules
faire passer le document en Feu Rouge.**

### A — Permettre l'identification du document

| ID | Règle | Bloquante | Remédiable auto |
| --- | --- | --- | --- |
| A1 | Nom du document conforme (AAAAMMJJ_Sujet_Type_Infos) | **Oui** | Oui |

> **A2, A3 et A4 ont été retirés** : la cartouche, la description de
> l'objectif dans les métadonnées et le glossaire centralisé sont désormais
> gérés par l'interface Domino.

### B — Mise en forme du document et sa structure

| ID | Règle | Bloquante |
| --- | --- | --- |
| B5 | Titres descriptifs, hiérarchisés et correctement formatés | Non |
| B6 | Titres et sous-titres suffisants | Non |

> Limite documentée : seuls les titres balisés par les styles `Heading 1/2/3`
> ou les titres de slide sont détectés. Des titres ajoutés via un style
> personnalisé peuvent passer inaperçus. La notion de titre n'est pas
> pertinente pour tous les types de documents (mémo court, slide-deck).

### C — Mise en forme du texte

| ID | Règle | Bloquante |
| --- | --- | --- |
| C7 | Acronymes / abréviations expliqués à leur 1re apparition | Non |
| C8 | Texte hors boîtes / cadres (textbox) inutiles | Non |
| C9 | Pas de logos / symboles / icônes dans les phrases | Non |

> C7 dispose d'une **liste blanche** de plusieurs centaines de mots
> tout-en-majuscules courants (ACCOUNT, ANNEX, BUSINESS, COMPANY,
> DETAILS, NOTE, etc.) qui sont **ignorés** pour éviter les faux positifs.

### D — Gestion des images

| ID | Règle | Bloquante |
| --- | --- | --- |
| D10 | Légende sous chaque image informative | Non |
| D11 | Qualité des images (résolution, netteté) | Non |

### E — Gestion des tableaux

| ID | Règle | Bloquante |
| --- | --- | --- |
| E12 | Pas de cellules fusionnées | Non |
| E13 | Bordures visibles (idéalement noires sur fond blanc) | Non |
| E14 | En-têtes de colonnes clairs et mis en valeur | Non |
| E15 | Titre explicite au-dessus du tableau | Non |
| E16 | Légende décrivant le contenu du tableau | Non |
| E17 | Symboles / codes couleurs remplacés par des mots | Non |
| E18 | Pagination / en-têtes répétés sur plusieurs pages | Non |
| E19 | Tableau au format natif (pas image / capture) | Non |

### F — Gestion des diagrammes / schémas

| ID | Règle | Bloquante |
| --- | --- | --- |
| F20 | Éléments des diagrammes nommés précisément (pas « Étape 1 ») | Non |
| F21 | Structures allégées (pas de surcharge) | Non |
| F22 | Diagrammes découpés en sous-diagrammes thématiques | Non |
| F23 | Texte structuré privilégié si plus accessible | Non |
| F24 | Légende explicative décrivant la logique | Non |

> F20 fonctionne sur **tous les formats** (DOCX, PPTX, XLSX, PDF) : il
> détecte les libellés génériques type « Étape N » dans le texte.
> F21-F24 utilisent l'analyse des formes (PPTX uniquement) ; sur les
> autres formats, ils renvoient « Non vérifiable » avec une invitation à
> la revue manuelle.

### G — Gestion des URLs

| ID | Règle | Bloquante | Remédiable auto |
| --- | --- | --- | --- |
| G25 | URLs introduites par un texte clair (contexte) | Non | Non |
| G26 | URLs nettoyées (paramètres session / tracking retirés) | **Oui** (MAJOR FAIL) | Oui |
| G27 | URLs affichées en clair (pas masquées par un lien) | Non | Non |

### H — Données sensibles (extension KM)

| ID | Règle | Bloquante | Remédiable auto |
| --- | --- | --- | --- |
| H28 | Aucune donnée client / personnelle détectée | **Oui** | Oui |
| H29 | Étiquette de confidentialité compatible KM (Public ou Interne) | **Oui** | Non |

> H29 nouvelle règle ajoutée à la demande du métier (cf. §4).

### I — Bonnes pratiques générales (extension)

| ID | Règle | Bloquante |
| --- | --- | --- |
| I29 | Pas de coupures de mots / paragraphes | Non |
| I30 | Format DOCX privilégié | Non |
| I31 | Document de longueur raisonnable (≤ 20 pages) | Non |
| I32 | Pas d'en-têtes / pieds de page superflus | Non |
| I33 | Phrases courtes et simples | Non |
| I34 | Alignement à gauche (PPT / PDF) | Non |
| I35 | Paragraphes de longueur raisonnable | Non |

---

## 3. Ce que produit l'outil

Pour chaque document audité, l'utilisateur peut :

1. **Voir le résumé** dans l'interface Streamlit : verdict, score,
   nombre de bloquants, nombre d'alertes, légende des feux et statuts,
   détail des règles avec **localisation** (« Slide 3 », « § 5 — Glossaire »,
   « Page 2 », « Feuille : Données »).
2. **Télécharger le rapport d'audit en PDF** :
   - cartouche du document audité avec bandeau verdict coloré,
   - légende des fourchettes de feux et des quatre statuts,
   - synthèse des non-conformités bloquantes,
   - détail par catégorie, avec colonnes Règle / Statut / Sévérité /
     Localisation / Constat / Recommandation,
   - annexe métriques (pages, titres, tableaux, images, URLs…).
3. **Télécharger un ZIP** regroupant tous les rapports PDF si plusieurs
   documents ont été audités.
4. **Générer un plan de remédiation** :
   - **rename_file** : renommage au format AAAAMMJJ_Sujet_Type ;
   - **replace_symbols** : ✓ → « oui », ✗ → « non », ➜ → « -> » ;
   - **clean_urls** : suppression des paramètres `utm_*`, `gclid`,
     `fbclid`, `session*`, `token`, `auth`, `tracking` ;
   - **redact_sensitive** : masquage des emails / téléphones / IBAN /
     adresses / identifiants client détectés.
   - Les actions sélectionnées sont **appliquées au document DOCX** ;
     la version corrigée est téléchargeable directement depuis l'interface.
   - Une **re-audit** automatique compare le score avant / après.
   - Pour les formats non-DOCX, l'outil produit un **guide de remédiation
     en Markdown** listant les actions à faire à la main.
5. **Régler les paramètres** depuis la barre latérale : seuils de
   résolution image, longueur maximale de paragraphe, densité de titres,
   pondération bloquantes / pratiques, seuils des feux Vert et Orange.

Le rapport PDF est nommé `<nom_source>__KM_AUDIT__YYYYMMDD.pdf`.

---

## 4. Comment chaque demande métier a été prise en compte

Le projet a évolué à travers plusieurs vagues de relecture. Cette
section retrace les demandes formulées dans la conversation et leur
traduction concrète.

### 4.1. Spécification initiale

Demande initiale : application offline Streamlit, audit DOCX/PPTX/XLSX/PDF,
checklist, rapport PDF, ZIP, masquage des données sensibles, score 70/30,
verdict tricolore, self-check.

➜ Toutes ces exigences sont implémentées dès la première version et
sont **vérifiées en continu** par le harnais `certify.py`
(scénario 6 « Spec initiale »).

### 4.2. Réorganisation architecturale

Demande : architecture professionnelle et option de remédiation avec
recommandations.

➜ Refactorisation en package modulaire `km_audit/` :

```
km_audit/
├── audit.py               # orchestrateur audit_document()
├── config.py              # Settings, regex, constantes
├── loaders.py             # parsers DOCX / PPTX / XLSX / PDF
├── models.py              # Status, Severity, RuleResult, ParsedDoc
├── remediation.py         # plan + patcher DOCX + guide Markdown
├── reporting.py           # PDF ReportLab + ZIP
├── rules/                 # une règle par fonction, registry @register
│   ├── identification.py  ├── structure.py  ├── text_formatting.py
│   ├── images.py          ├── tables.py     ├── diagrams.py
│   ├── urls.py            ├── sensitive.py  └── practices.py
├── scoring.py             # score pondéré + verdict
└── sensitive.py           # détection + masquage email / phone / IBAN
```

Le moteur de remédiation `km_audit/remediation.py` fournit :

- `build_plan(result)` → plan d'actions à partir de l'audit ;
- `patch_document(...)` → applique le patch sur le DOCX et renvoie
  les octets corrigés + le statut des actions ;
- `render_markdown_guide(...)` → guide manuel pour les autres formats.

### 4.3. Documentation

Demande : ajouter une documentation qui explique tout.

➜ Création de `README.md` (technique) et de `CERTIFICATION.md` (preuve
qualité avec mapping ancienne / nouvelle numérotation).

### 4.4. Document de référence et certification

Demande : générer un document qui passe tous les contrôles et certifier
le code.

➜ Création des générateurs `samples/generate_reference.py` (document
exemplaire) et `samples/generate_bad.py` (anti-exemple) plus du
harnais `certify.py`.

À chaque modification ultérieure, `certify.py` est ré-exécuté ; il
contient désormais **72 contrôles automatisés** regroupés en 8
scénarios couvrant tous les points qui ont été demandés.

### 4.5. Alignement sur la typologie officielle

Demande : utiliser exactement la typologie de la checklist normes-
connaissances ; A4 = glossaire, C7 = acronymes 1re occurrence,
8 contrôles tableaux distincts, 5 contrôles diagrammes distincts.

➜ Catégories renommées avec les libellés officiels. Renumérotation
complète des règles (A1-A4, B5-B6, C7-C9, D10-D11, E12-E19, F20-F24,
G25-G27, H28, I29-I35). Séparation E15 (titre) / E16 (légende) du
tableau. Éclatement du contrôle diagramme unique en 5 règles F20-F24.

### 4.6. Rendu PDF corrigé

Demande (deux passes) : le texte sort des cases dans le PDF.

➜ Cause 1 : les cellules de tableau passées en chaînes brutes ne
wrappaient pas. Toutes les cellules sont désormais wrappées dans un
`Paragraph` ReportLab avec mode CJK qui sait casser même les tokens
insécables (URL, IBAN longs).

➜ Cause 2 : double-`escape()` des balises `<b>` qui les rendait
visibles en texte littéral. Deux helpers distincts `_cell` (texte
brut, escape automatique) et `_cell_html` (markup, escape à la
charge de l'appelant) ont été introduits.

➜ Largeurs de colonnes recalculées pour A4. Sévérités affichées en
3 lettres (BLOC / MAJ / MIN). Footer paginé.

### 4.7. Retour de relecture détaillé

Demande (email Nuria) : 12 ajustements de libellés et de
comportement.

| Demande | Traitement |
| --- | --- |
| « readiness » → « Readiness » | Titre UI + PDF |
| Diagrammes pas réservés au PPT | F20 universel, F21-F24 message N/V clair |
| I30 reco adoucie | « Si possible, privilégier DOCX… » |
| Seuil long_doc 10 → **20** pages + reco adoucie | Settings mis à jour |
| Mot « RAG » à supprimer partout | Remplacé par « outil » |
| Numéro de page dans les preuves | Nouveau tracking de localisation |
| « Preuve » → « **Localisation** » | Colonne dédiée dans PDF + UI |
| « Détail des règles » → « **Détails de l'analyse** » | UI + PDF |
| Confusion bouton PDF sur PPT | Libellé « Télécharger le rapport d'audit (PDF) » + tooltip |
| Fourchettes des feux à afficher | Légende dédiée en haut du PDF et expander dans l'UI |
| « Avertissements » → « **Alertes** » | UI |
| Légende des trois symboles | Ajoutée dans UI + PDF |

Bonus : seuil `score_orange_floor = 50`. Un score sous 50 sans
bloquant FAIL est désormais classé Feu Rouge (cohérent avec la
fourchette « Rouge < 50 » affichée dans la légende).

### 4.8. Retour de relecture catégorie par catégorie

Demande (tableur Excel) : ajustement de chaque règle suivant le
contexte Domino + SharePoint.

| Règle | Demande | Traitement |
| --- | --- | --- |
| A2 / A3 / A4 | À retirer (interface Domino) | **Règles désinscrites** de la registry |
| B5, B6 | Non bloquant, signaler que la détection ne couvre pas tous les styles | Sévérité **MAJOR**, note explicative dans la preuve |
| C7 | Non bloquant + filtrer ACCOUNT/ANNEX/BUSINESS… | Sévérité **MAJOR**, **stop-list** de plusieurs centaines de mots intégrée |
| C8 | Non bloquant | Sévérité **MAJOR** |
| C9 | Non bloquant | Sévérité **MAJOR** |
| D10 | Non bloquant | Sévérité **MAJOR** |
| E12 | Non bloquant | Sévérité **MAJOR** |
| E19 | Non bloquant | Sévérité **MAJOR** |
| H28 | Trop de faux positifs sur les téléphones | Détection téléphone resserrée : exige un **mot-clé** « Tél », « Téléphone », « Phone », « Mobile »… dans les 30 caractères qui précèdent. URLs **retirées du texte** avant détection. Les filtres « ≥ 8 chiffres » conservés. |
| H29 | Nouvelle règle souhaitée : étiquette Public / Interne | **Nouvelle règle** H29 implémentée. PASS si étiquette « Public » ou « Interne » trouvée dans l'en-tête. FAIL si étiquette « Confidentiel », « Privé », « Secret », « Restricted ». FAIL aussi en l'absence d'étiquette. |

### 4.9. Récap des règles bloquantes après prise en compte

Seules 3 règles peuvent désormais déclencher un Feu Rouge :

- **A1** — Nom du document conforme.
- **H28** — Aucune donnée client / personnelle.
- **H29** — Étiquette de confidentialité Public ou Interne.

Toutes les autres règles continuent d'être évaluées mais en sévérité
MAJOR ou MINOR : elles influencent le score sans bloquer l'intégration
du document.

---

## 5. Limites assumées

- **Heuristiques** : les contrôles s'appuient sur des motifs textuels
  et des extractions de structure simples. Certains documents
  atypiques peuvent ne pas être correctement analysés (par exemple un
  PDF scanné sans OCR, ou un DOCX dont les titres utilisent des
  styles personnalisés non détectés).
- **N/V** : utilisé chaque fois qu'un contrôle ne peut pas être
  vérifié automatiquement pour le format en question. Le rapport
  PDF rappelle qu'une revue manuelle est nécessaire pour ces points.
- **Données sensibles masquées dans le rapport** : les valeurs brutes
  ne figurent jamais en clair dans le PDF, uniquement leurs versions
  masquées (`j***@domaine.com`, `***12`, `FR***0123`).
- **Aucun appel réseau** : tout est traité en local. Cela permet
  d'auditer des documents internes / sensibles sans risque de fuite,
  mais cela limite les contrôles à ce qui peut être déduit du
  contenu lui-même (pas de croisement avec une base d'acronymes
  externe, par exemple).
- **H29** : à terme, cette règle pourra être déléguée à SharePoint /
  Microsoft Purview. Tant que ce n'est pas le cas, le filet de
  sécurité au niveau document tel qu'implémenté reste utile.

---

## 6. Comment lancer l'outil

```bash
pip install -r requirements.txt
streamlit run app.py
```

Pour relancer la **certification** automatisée (72 contrôles) :

```bash
python3 certify.py
```

Pour les contrôles de sanité rapide (regex de nommage, masquage,
nettoyage d'URL, etc.) :

```bash
python3 app.py --self-check
```
