# MCP Capability Bridge 0.6.1

## Français

Cette version ajoute les actions Web interactives bornées du Lot 3C aux sessions isolées validées au Lot 3B.

Après installation ou mise à jour :

1. créez ou conservez un client sous **Clients MCP** ;
2. sous **Cibles**, ajoutez une cible SSH, scannez sa clé d’hôte, vérifiez son adresse et son empreinte, puis confirmez explicitement l’enrôlement ;
3. choisissez une authentification par mot de passe ou clé privée dédiée à un compte distant restreint ;
4. sous **Capacités SSH**, définissez un exécutable absolu, un template JSON de tokens littéraux/paramètres, un schéma d’entrée scalaire strict, un timeout et les limites stdout/stderr ;
5. sous **Accès MCP**, publiez explicitement la capacité vers chaque client autorisé.

Pour le Web, créez une cible avec authentification aucune, HTTP Basic ou formulaire configuré, testez la connexion, puis publiez séparément les outils nécessaires. Les identifiants restent administratifs et ne figurent jamais dans les arguments MCP. La page **Sessions** montre uniquement les métadonnées sûres des sessions actives.

Le Bridge ne fournit aucune commande SSH libre. Chaque appel ouvre une nouvelle connexion vérifiée par la clé d’hôte épinglée, sans PTY, agent, forwarding, stdin ni environnement fourni par l’appelant. Les droits effectifs restent ceux du compte SSH configuré : utilisez un compte dédié appliquant le moindre privilège.

Pour la recette HAOS, enrôlez une cible de test restreinte et une capacité inoffensive. Appelez-la deux fois avec un client MCP générique puis via ACP/AEP, vérifiez l’isolation entre deux clients, les limites de sortie, le refus après changement de clé, l’absence de secret et de refus AppArmor dans les logs, puis testez désactivation et redémarrage. Le changement de clé hôte doit toujours passer par un nouveau scan et une confirmation explicite.

Les outils disponibles sont `open`, `snapshot`, `wait`, `navigate`, `click`, `fill`, `select`, `press` et `close`. Les actions utilisent uniquement un chemin relatif ou une référence opaque issue du dernier snapshot. Une référence devient invalide après toute tentative d’action.

Les droits effectifs sont exactement ceux du compte Web configuré. Utilisez un compte dédié appliquant le moindre privilège. Le Bridge n’ajoute pas d’autorisation métier plus fine que celle du site et ne rejoue jamais une action interactive après une erreur ou une réponse perdue.

## English

This release adds the bounded interactive Web actions from Lot 3C to the isolated sessions accepted in Lot 3B.

After installation or update:

1. create or retain a client under **MCP clients**;
2. under **Targets**, add an SSH target, scan its host key, verify the address and fingerprint, and explicitly confirm enrollment;
3. select password or private-key authentication for a dedicated restricted remote account;
4. under **SSH capabilities**, define an absolute executable, a JSON literal/parameter token template, a strict scalar input schema, timeout, and stdout/stderr limits;
5. under **MCP access**, explicitly publish the capability to each authorized client.

For Web access, create a target using none, HTTP Basic, or configured form authentication, test the connection, then separately publish only the required tools. Credentials remain administrative and never appear in MCP arguments. The **Sessions** page exposes safe active-session metadata only.

The Bridge exposes no free-form SSH command. Every call opens a fresh connection verified against the pinned host key, without PTY, agent, forwarding, stdin, or caller-provided environment. Effective authority remains exactly that of the configured SSH account, so use a dedicated least-privilege account.

For HAOS acceptance, enroll a restricted test target and a harmless capability. Call it twice through a generic MCP client and once through ACP/AEP, verify isolation between two clients, output bounds, refusal after a host-key change, absence of secrets and AppArmor denials in logs, then test disable and restart. Host-key rotation must always require a new scan and explicit confirmation.

The available tools are `open`, `snapshot`, `wait`, `navigate`, `click`, `fill`, `select`, `press` and `close`. Actions accept only a relative path or an opaque reference from the latest snapshot. Every attempted action invalidates that reference generation.

Effective authority is exactly the authority of the configured Web account. Use a dedicated least-privilege account. The Bridge does not claim finer business authorization than the target and never replays an interactive action after an error or lost response.
