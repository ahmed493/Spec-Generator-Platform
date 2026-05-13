# ── System prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """Tu es un expert en documentation technique et data engineering.
Tu analyses des repositories de code et génères des spécifications techniques et fonctionnelles complètes.
Tu dois identifier:
- La couche de données (Bronze/Silver/Gold)
- Les sources et destinations de données
- Les transformations appliquées
- Le data lineage
- Les technologies utilisées

Réponds toujours en français et de manière structurée."""


# ── User prompt ───────────────────────────────────────────────────────────────

SPEC_GENERATION_PROMPT = """Analyse les métadonnées suivantes d'un repository et génère une spécification complète.

## Métadonnées du repository:
{metadata}

## Template de spécification à suivre:

# Spécification: {repo_name}

## 1. Vue d'ensemble
### 1.1 Description du projet
[Description basée sur le README et le code]

### 1.2 Couche de données
- **Type de couche**: [Bronze/Silver/Gold]
- **Objectif**: [Objectif de cette couche]

## 2. Sources de données
### 2.1 Sources d'entrée
[Liste des sources d'entrée identifiées dans le code]

### 2.2 Destinations de sortie
[Liste des destinations identifiées]

## 3. Schéma de données
### 3.1 Tables/Fichiers
[Tables ou fichiers manipulés]

### 3.2 Champs clés
[Champs importants identifiés]

## 4. Transformations
### 4.1 Processus ETL
[Description des transformations]

### 4.2 Règles métier
[Règles métier identifiées dans le code]

## 5. Data Lineage
[Diagramme de flux de données en ASCII]

## 6. Dépendances
### 6.1 Dépendances upstream
[Ce dont ce repo dépend]

### 6.2 Dépendances downstream
[Ce qui dépend de ce repo]

## 7. Détails techniques
### 7.1 Technologies utilisées
[Liste des technologies]

### 7.2 Configuration
[Configurations importantes]

---
Génère maintenant la spécification complète en analysant le code fourni.
"""
