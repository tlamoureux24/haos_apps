# Agent Gateway

[Français](#français) | [English](#english)

## Français

Agent Gateway relie des agents authentifiés à des outils choisis dans un ou
plusieurs serveurs MCP. Commencez par ajouter un connecteur dans
**Connecteurs**, composez une tâche dans **Tâches**, puis créez une identité
Client MCP dans **Identités**. Son identifiant n’est affiché qu’une fois.

Dans le panneau d’une nouvelle tâche, chaque outil reste **Standard** par
défaut. Le volet facultatif **Restreindre cet outil** permet de partir d’un
appel exemple valide : les propriétés fixes ordinaires ou sensibles sont
retirées du schéma visible par l’agent et réinjectées par la passerelle. Les
valeurs sensibles sont protégées au repos et ne sont jamais réaffichées.
Les schémas d’entrée MCP admis suivent JSON Schema Draft 2020-12, avec
références locales uniquement. Une contrainte, un format ou un dialecte non
pris en charge est refusé explicitement avant tout appel au serveur MCP.

Le port `8098` dessert MCP et l’API d’événements authentifiée. Ne le publier que
sur un réseau local ou VPN de confiance. L’administration reste confinée à
l’Ingress Home Assistant.

L’interface détecte le français ou l’anglais du navigateur, utilise le français
comme repli et propose un bouton **FR/EN** mémorisé localement.

Un déclencheur avec délai de grâce peut corréler tout le déclencheur ou agréger
plusieurs sujets stables dans un incident unique. En mode agrégé, chaque alerte
et rétablissement doit fournir un objet `subject` non vide ; l’échéance initiale
ne se prolonge pas et un seul travail contient les sujets encore actifs.

Guide complet : [documentation française](README.fr.md).

## English

Agent Gateway connects authenticated agents to selected tools from one or more
MCP servers. First add a connector under **Connectors**, compose a task under
**Tasks**, then create an MCP client identity from **Identities**. Its credential
is displayed only once.

In the new-task drawer every tool remains **Standard** by default. The optional
**Restrict this tool** section starts from a valid example call: ordinary or
sensitive fixed properties are removed from the agent-visible schema and
injected by the gateway. Sensitive values are protected at rest and never
displayed again.
Admitted MCP input schemas follow JSON Schema Draft 2020-12 with local
references only. An unsupported constraint, format or dialect is rejected
explicitly before any MCP server call.

Port `8098` serves MCP and the authenticated event API. Publish it only on a
trusted LAN or VPN. Administration remains confined to Home Assistant Ingress.

The interface detects the browser’s French or English preference, falls back to
French, and provides a locally remembered **FR/EN** button.

A trigger with a grace period can correlate the whole trigger or aggregate
several stable subjects into one incident. In aggregated mode every alert and
recovery must provide a non-empty `subject` object; the initial deadline never
extends and one job contains the subjects that remain active.

Full guide: [English documentation](README.md).
