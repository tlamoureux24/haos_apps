# MCP Capability Bridge

Guide complet des namespaces, templates SSH JSON, schémas d’entrée, cibles Web et intégrations ACP/AEP : [français](README.fr.md) | [English](README.md).

The runtime, persistence, backup/restore, MCP, Web, SSH, ACP/AEP, TLS, and
AppArmor paths have passed real-HAOS acceptance. SQLite generation 1 is the
production-data compatibility cutoff.

## Français

### TLS

Le listener MCP `8098` utilise HTTPS autogénéré par défaut. HTTP reste
disponible avec avertissement. Un certificat externe se configure avec des noms
relatifs à `/ssl`, sans préfixe `/ssl/`. Consultez le
[guide TLS bilingue](../TLS.md) pour les exemples OpenSSL, l’épinglage entrant
et sortant, les permissions, la rotation et le dépannage.

### Installation et surfaces

L’administration est disponible uniquement par Ingress sur le port interne
8099. Le port 8098 expose seulement `/health/live`, `/health/ready` et le
serveur MCP authentifié `/mcp`. Publiez 8098 sur l’hôte uniquement lorsqu’un
client externe doit joindre le Bridge.

Chaque client MCP possède un namespace et un credential Bearer distinct. Le
secret est affiché uniquement à sa création ou à son renouvellement. Il n’est
jamais récupérable ensuite. Une rotation invalide immédiatement l’ancien secret
et ferme uniquement les sessions Web de ce client ; une révocation bloque tout
son accès et doit précéder son archivage.

### Utilisation autonome

1. Créez un client dans **Clients MCP** et copiez son credential.
2. Créez une cible SSH ou Web avec un compte dédié appliquant le moindre
   privilège.
3. Pour SSH, confirmez explicitement la clé d’hôte puis définissez une capacité
   avec exécutable absolu, arguments typés et limites de temps/sortie.
4. Pour Web, confirmez l’origine et les adresses résolues, configurez le compte,
   les durées de session et testez le navigateur.
5. Dans **Accès MCP**, publiez uniquement les capacités nécessaires au client.
6. Configurez le client MCP avec l’URL
   `http://<hôte>:<port-publié>/mcp` et `Authorization: Bearer <credential>`.

Le Bridge n’expose ni commande SSH libre, ni URL/sélecteur/JavaScript arbitraire
pour le Web. Les sessions Web sont temporaires. Les droits réels correspondent
strictement au compte configuré sur la cible.

### Intégration ACP/AEP

ACP se connecte comme n’importe quel autre client MCP : créez-lui un namespace
dédié dans le Bridge, publiez les outils autorisés, puis créez dans ACP un
connecteur Streamable HTTP vers `/mcp` avec ce credential. ACP ne découvre que
ce namespace et restreint ensuite les outils par tâche. AEP ne reçoit que cette
enveloppe via la frontière MCP générique d’ACP. Aucun endpoint ou secret
spécifique à ACP/AEP n’existe dans le Bridge.

Un AEP autonome ou un autre client MCP peut également utiliser son propre
namespace directement, sans ACP.

### Résultats ambigus et capacité

Le Bridge ne rejoue jamais automatiquement une commande SSH ou une action Web.
Après une perte de réponse, `effect_possible: true` signifie que la cible a pu
appliquer l’effet : le client ne doit pas relancer automatiquement l’appel.

Les limites globales, par client, adaptateur et cible refusent immédiatement la
charge excédentaire avec un code `*_busy`; il n’existe aucune file d’exécution
cachée. Les requêtes MCP supérieures à 256 Kio sont refusées avant leur mise en
mémoire par la pile protocolaire.

### Sauvegarde, restauration et mise à niveau

L’App utilise une sauvegarde HAOS à froid (`backup: cold`). Une sauvegarde
cohérente doit contenir ensemble tout `/data`, notamment :

- `mcp_capability_bridge.db` ;
- `private/credential-pepper` ;
- `private/target-secret-key`.

Ne restaurez jamais la base sans les deux clés privées : les credentials et les
secrets de cible deviendraient inutilisables. Les profils Chromium et sessions
Web résident sous `/tmp`, ne font pas partie d’une sauvegarde et ne sont jamais
restaurés.

Pour tester une restauration : arrêtez l’App, créez une sauvegarde HAOS,
restaurez-la, redémarrez, vérifiez la readiness, les clients/cibles/publications,
puis appelez une capacité inoffensive. Une session Web ouverte avant sauvegarde
doit avoir disparu.

La génération SQLite `1` est le cutoff de compatibilité de production : toute
modification durable ultérieure exige une
migration versionnée, transactionnelle et testée depuis chaque version prise en
charge. Une génération inconnue est toujours refusée au démarrage.

### Acceptation HAOS finale

La recette finale a validé :

- installation propre, démarrage, FR/EN, clair/sombre, desktop/mobile et statut
  réel ;
- mise à niveau depuis 0.6.2 avec conservation de la configuration et du
  journal Activité ;
- sauvegarde/restauration à froid avec configuration conservée et aucune
  session restaurée ;
- deux clients isolés, rotation/révocation et publication différente ;
- appels SSH répétés avec connexions fraîches et limites de sortie ;
- comptes Web Reader/Admin, actions bornées, nettoyage et aucune reprise de
  session après redémarrage ;
- appel autonome puis appel Bridge → ACP → AEP sans adaptation spécifique ;
- redémarrage pendant une opération : aucune reprise/relecture automatique ;
- absence d’erreur applicative, fuite de secret et `apparmor="DENIED"` ;
- consommation stable après les bancs externes Lot 3B/3C répétés.

Ces preuves valident le socle de production et la génération SQLite `1` comme
cutoff de conservation des données.

## English

### TLS

The MCP listener on `8098` defaults to self-generated HTTPS. HTTP remains
available with a warning. Configure an external certificate with filenames
relative to `/ssl`, without the `/ssl/` prefix. See the
[bilingual TLS guide](../TLS.md) for OpenSSL examples, inbound and outbound
pinning, permissions, rotation, and troubleshooting.

### Installation and surfaces

Administration is Ingress-only on internal port 8099. Port 8098 exposes only
`/health/live`, `/health/ready`, and authenticated MCP `/mcp`. Publish 8098 to
the host only when an external client needs to reach the Bridge.

Each MCP client owns a separate namespace and Bearer credential. The clear
secret is displayed only at creation or rotation and cannot be recovered.
Rotation immediately invalidates the previous secret and closes only that
client's Web sessions; revocation blocks all access and must precede archive.

### Standalone use

1. Create a client under **MCP clients** and copy its credential.
2. Create an SSH or Web target using a dedicated least-privilege account.
3. For SSH, explicitly confirm the host key and define a capability with an
   absolute executable, typed arguments, and time/output limits.
4. For Web, confirm the origin and resolved addresses, configure the account
   and session limits, then test the browser.
5. Under **MCP access**, publish only the capabilities required by the client.
6. Configure the MCP client with
   `http://<host>:<published-port>/mcp` and
   `Authorization: Bearer <credential>`.

The Bridge exposes neither a free-form SSH command nor arbitrary Web URLs,
selectors, JavaScript, uploads, or downloads. Web sessions are disposable, and
their actual authority is exactly that of the configured target account.

### ACP/AEP integration

ACP connects as an ordinary MCP client: create a dedicated Bridge namespace,
publish its tools, then create an ACP Streamable HTTP connector for `/mcp` with
that credential. ACP discovers only that namespace and narrows tools per task.
AEP receives that envelope through ACP's existing generic MCP boundary. The
Bridge has no ACP/AEP-specific endpoint, secret, or back channel.

Standalone AEP and other MCP clients may instead use their own namespace
directly without ACP.

### Ambiguous outcomes and capacity

The Bridge never automatically replays an SSH command or Web action. After a
lost response, `effect_possible: true` means the target may have applied the
effect and the client must not retry automatically.

Global, client, adapter, and target limits reject excess load immediately with
a `*_busy` code; there is no hidden execution queue. MCP bodies above 256 KiB
are rejected before the protocol stack buffers them.

### Backup, restore, and upgrades

The App uses HAOS cold backup (`backup: cold`). A consistent backup must retain
all of `/data` together, especially:

- `mcp_capability_bridge.db`;
- `private/credential-pepper`;
- `private/target-secret-key`.

Never restore the database without both private keys. Chromium profiles and
Web sessions live under `/tmp`, are excluded from backup, and are never
restored.

To test restore, stop the App, create and restore a HAOS backup, restart, verify
readiness and all clients/targets/publications, then call one harmless
capability. A Web session open before backup must be gone.

SQLite generation `1` is the production compatibility cutoff: every later
durable change requires a versioned,
transactional migration tested from every supported version. Unknown
generations always fail startup.

### Final HAOS acceptance

Final acceptance validated clean install; UI; upgrade from 0.6.2; cold backup/restore; two-client
isolation; rotation/revocation; repeated fresh SSH calls; Reader/Admin Web
authority; cleanup; standalone and Bridge → ACP → AEP calls; restart during an
operation without replay; stable resources; and clean application/AppArmor
logs. Repeat the external Lot 3B/3C benches where appropriate.

This evidence accepts Lot 4 and authorizes stable 1.0.0 as the production-data
preservation cutoff.
