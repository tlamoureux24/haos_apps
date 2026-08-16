# Agent Control Plane

[Français](#français) | [English](#english)

## Français

Agent Control Plane relie des agents authentifiés à des outils choisis dans un ou
plusieurs serveurs MCP. Commencez par ajouter un connecteur dans
**Connecteurs**, composez une tâche dans **Tâches**, puis créez une identité
Client MCP dans **Identités**. Son identifiant n’est affiché qu’une fois.

Agent Control Plane applique un modèle de pare-feu applicatif MCP deny-by-default :
la découverte d’un outil n’accorde aucun droit, et la sélection explicite de cet
outil dans une tâche valide constitue l’autorisation administrative de
l’utiliser dans l’enveloppe exacte configurée. La passerelle n’ajoute pas de
seconde approbation selon qu’un outil est présenté comme lecture, écriture ou
administration ; tout outil ou argument non autorisé par la tâche reste refusé.

Dans le panneau d’une nouvelle tâche, chaque outil reste **Standard** par
défaut. Le volet facultatif **Restreindre cet outil** permet de partir d’un
appel exemple valide : les propriétés fixes ordinaires ou sensibles sont
retirées du schéma visible par l’agent et réinjectées par la passerelle. Les
valeurs sensibles sont protégées au repos et ne sont jamais réaffichées.
Les schémas d’entrée MCP admis suivent JSON Schema Draft 2020-12, avec
références locales uniquement. Une contrainte, un format ou un dialecte non
pris en charge est refusé explicitement avant tout appel au serveur MCP.
Un serveur joignable qui publie un schéma refusé apparaît comme **invalide**
dans **Connecteurs**, avec une explication et le code technique exact. Une
erreur de transport reste distinguée comme connecteur inaccessible.

Un connecteur actif peut être renommé ou recevoir un nouvel endpoint sans être
supprimé. Une édition ordinaire conserve automatiquement son secret. L’action
séparée **Rotation du secret** exige une nouvelle valeur non vide ; le secret
actuel n’est jamais renvoyé ou prérempli. Un nouvel endpoint ou secret est
redécouvert avant que le connecteur redevienne prêt. En cas d’échec, le dernier
inventaire reste consultable mais le connecteur et ses tâches dépendantes
restent indisponibles ; une rotation échouée ne remplace pas le secret stocké.
Après une rotation réussie, Agent Control Plane ne stocke et
n’utilise plus l’ancien secret ; sa révocation côté serveur MCP reste à effectuer
sur ce serveur si nécessaire.

Le port `8098` dessert MCP et l’API d’événements authentifiée. Ne le publier que
sur un réseau local ou VPN de confiance. L’administration reste confinée à
l’Ingress Home Assistant.

Depuis la clôture du développement en 0.46.8, les données persistantes sont
considérées comme non jetables. Toute future évolution incompatible du schéma
doit fournir un chemin de mise à niveau explicite et testé qui préserve les
données ; supprimer les données de l’App et réinstaller proprement n’est plus une
stratégie normale de mise à jour.

L’interface détecte le français ou l’anglais du navigateur, utilise le français
comme repli et propose un bouton **FR/EN** mémorisé localement. Chaque vue
recharge ses propres données dès son ouverture. Les vues opérationnelles se
réactualisent ensuite automatiquement : **Exécutions** toutes les 5 secondes et
**Vue d’ensemble**, **Événements**, **Rapports** et **Audit** toutes les
10 secondes, avec un indicateur « Actualisé il y a… ». Cette actualisation est
suspendue si l’onglet est masqué, si un panneau d’administration est ouvert ou
si un détail est déplié dans **Événements**, **Rapports** ou **Audit** ; elle
reprend automatiquement ensuite et le retour sur un onglet masqué actualise
immédiatement la vue active.

Un déclencheur avec délai de grâce peut corréler tout le déclencheur ou agréger
plusieurs sujets stables dans un incident unique. En mode agrégé, chaque alerte
et rétablissement doit fournir un objet `subject` non vide ; l’échéance initiale
ne se prolonge pas et un seul travail contient les sujets encore actifs.

Guide complet : [documentation française](README.fr.md).
Références de publication : [compatibilité MCP](MCP_COMPATIBILITY.md),
[modèle de menace](THREAT_MODEL.md) et [plan d’implémentation](IMPLEMENTATION_PLAN.md).

## English

Agent Control Plane connects authenticated agents to selected tools from one or more
MCP servers. First add a connector under **Connectors**, compose a task under
**Tasks**, then create an MCP client identity from **Identities**. Its credential
is displayed only once.

Agent Control Plane uses a deny-by-default MCP application-firewall model: discovery
of a tool grants no execution right, and explicitly selecting that tool in a
valid task is the administrator's authorization to use it within the exact
configured capability envelope. The gateway does not add a second approval
step based on whether a tool is presented as read, write, or administrative;
any tool or argument not authorized by the task remains rejected.

In the new-task drawer every tool remains **Standard** by default. The optional
**Restrict this tool** section starts from a valid example call: ordinary or
sensitive fixed properties are removed from the agent-visible schema and
injected by the gateway. Sensitive values are protected at rest and never
displayed again.
Admitted MCP input schemas follow JSON Schema Draft 2020-12 with local
references only. An unsupported constraint, format or dialect is rejected
explicitly before any MCP server call.
A reachable server publishing a rejected schema appears as **invalid** under
**Connectors**, with an explanation and the exact technical code. Transport
failures remain separately identified as unreachable connectors.

An active connector can be renamed or assigned a replacement endpoint without
deleting it. Ordinary edits automatically retain its secret. The separate
**Rotate secret** action requires a non-empty replacement; the current secret
is never returned or prefilled. A new endpoint or secret is rediscovered before
the connector becomes ready again. On failure the last inventory remains
inspectable, while the connector and dependent tasks stay unavailable; a failed
rotation does not replace the stored secret. After a successful rotation Agent
Gateway no longer stores or uses the old secret;
revoking it at the MCP server remains an upstream operation when required.

Port `8098` serves MCP and the authenticated event API. Publish it only on a
trusted LAN or VPN. Administration remains confined to Home Assistant Ingress.

Since development closed at 0.46.8, persisted data is considered non-disposable.
Any future incompatible schema change must provide an explicit, tested upgrade
path that preserves existing data; deleting App data and performing a clean
reinstall is no longer a normal upgrade strategy.

The interface detects the browser’s French or English preference, falls back to
French, and provides a locally remembered **FR/EN** button. Each view reloads
its own data as soon as it is opened. Operational views then refresh
automatically: **Executions** every 5 seconds and **Overview**, **Events**,
**Reports**, and **Audit** every 10 seconds, with an “Updated … ago” indicator.
Automatic refresh is suspended while the browser tab is hidden, an
administration drawer is open, or a detail is expanded in **Events**,
**Reports**, or **Audit**; it resumes automatically afterwards, and returning to
a hidden tab immediately refreshes the active view.

A trigger with a grace period can correlate the whole trigger or aggregate
several stable subjects into one incident. In aggregated mode every alert and
recovery must provide a non-empty `subject` object; the initial deadline never
extends and one job contains the subjects that remain active.

Full guide: [English documentation](README.md).
Public release references: [MCP compatibility](MCP_COMPATIBILITY.md),
[threat model](THREAT_MODEL.md), and [implementation plan](IMPLEMENTATION_PLAN.md).