# Agent Gateway

[Français](#français) | [English](#english)

## Français

Agent Gateway relie des agents authentifiés à des outils choisis dans un ou
plusieurs serveurs MCP. Commencez par ajouter un connecteur dans
**Connecteurs**, composez une tâche dans **Tâches**, puis créez une identité
Client MCP dans **Vue d’ensemble**. Son identifiant n’est affiché qu’une fois.

Le port `8098` dessert MCP et l’API d’événements authentifiée. Ne le publier que
sur un réseau local ou VPN de confiance. L’administration reste confinée à
l’Ingress Home Assistant.

L’interface détecte le français ou l’anglais du navigateur, utilise le français
comme repli et propose un bouton **FR/EN** mémorisé localement.

Guide complet : [documentation française](README.fr.md).

## English

Agent Gateway connects authenticated agents to selected tools from one or more
MCP servers. First add a connector under **Connectors**, compose a task under
**Tasks**, then create an MCP client identity from **Overview**. Its credential
is displayed only once.

Port `8098` serves MCP and the authenticated event API. Publish it only on a
trusted LAN or VPN. Administration remains confined to Home Assistant Ingress.

The interface detects the browser’s French or English preference, falls back to
French, and provides a locally remembered **FR/EN** button.

Full guide: [English documentation](README.md).

