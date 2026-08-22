# MCP Capability Bridge 0.5.2

## Français

Cette version ajoute les sessions Web isolées et les outils MCP en lecture seule du Lot 3B.

Après installation ou mise à jour :

1. créez ou conservez un client sous **Clients MCP** ;
2. sous **Cibles**, ajoutez une cible SSH, scannez sa clé d’hôte, vérifiez son adresse et son empreinte, puis confirmez explicitement l’enrôlement ;
3. choisissez une authentification par mot de passe ou clé privée dédiée à un compte distant restreint ;
4. sous **Capacités SSH**, définissez un exécutable absolu, un template JSON de tokens littéraux/paramètres, un schéma d’entrée scalaire strict, un timeout et les limites stdout/stderr ;
5. sous **Accès MCP**, publiez explicitement la capacité vers chaque client autorisé.

Pour le Web, créez une cible avec authentification aucune, HTTP Basic ou formulaire configuré, testez la connexion, puis publiez séparément ses outils `open`, `snapshot`, `wait` et `close`. Les identifiants restent administratifs et ne figurent jamais dans les arguments MCP. La page **Sessions** montre uniquement les métadonnées sûres des sessions actives.

Le Bridge ne fournit aucune commande SSH libre. Chaque appel ouvre une nouvelle connexion vérifiée par la clé d’hôte épinglée, sans PTY, agent, forwarding, stdin ni environnement fourni par l’appelant. Les droits effectifs restent ceux du compte SSH configuré : utilisez un compte dédié appliquant le moindre privilège.

Pour la recette HAOS, enrôlez une cible de test restreinte et une capacité inoffensive. Appelez-la deux fois avec un client MCP générique puis via ACP/AEP, vérifiez l’isolation entre deux clients, les limites de sortie, le refus après changement de clé, l’absence de secret et de refus AppArmor dans les logs, puis testez désactivation et redémarrage. Le changement de clé hôte doit toujours passer par un nouveau scan et une confirmation explicite.

Pour le Lot 3B, utilisez un compte Web strictement en lecture seule. Vérifiez `open → snapshot → wait → close`, l’impossibilité d’utiliser le handle depuis un second client, la fermeture lors d’une rotation/révocation, l’absence de cookies entre deux sessions et l’absence de mot de passe dans les résultats et journaux.

## English

This release adds isolated Web sessions and the read-only MCP tools from Lot 3B.

After installation or update:

1. create or retain a client under **MCP clients**;
2. under **Targets**, add an SSH target, scan its host key, verify the address and fingerprint, and explicitly confirm enrollment;
3. select password or private-key authentication for a dedicated restricted remote account;
4. under **SSH capabilities**, define an absolute executable, a JSON literal/parameter token template, a strict scalar input schema, timeout, and stdout/stderr limits;
5. under **MCP access**, explicitly publish the capability to each authorized client.

For Web access, create a target using none, HTTP Basic, or configured form authentication, test the connection, then separately publish its `open`, `snapshot`, `wait`, and `close` tools. Credentials remain administrative and never appear in MCP arguments. The **Sessions** page exposes safe active-session metadata only.

The Bridge exposes no free-form SSH command. Every call opens a fresh connection verified against the pinned host key, without PTY, agent, forwarding, stdin, or caller-provided environment. Effective authority remains exactly that of the configured SSH account, so use a dedicated least-privilege account.

For HAOS acceptance, enroll a restricted test target and a harmless capability. Call it twice through a generic MCP client and once through ACP/AEP, verify isolation between two clients, output bounds, refusal after a host-key change, absence of secrets and AppArmor denials in logs, then test disable and restart. Host-key rotation must always require a new scan and explicit confirmation.

For Lot 3B, use a strictly read-only Web account. Verify `open → snapshot → wait → close`, cross-client handle rejection, cleanup on credential rotation/revocation, absence of shared cookies between consecutive sessions, and absence of passwords from results and logs.
