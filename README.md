# SmartLife Tray

Indicateur systray GTK pour piloter des appareils Tuya (SmartLife) et une TV Samsung **en local**.

Testé sous Linux Mint / Cinnamon, avec des climatiseurs et une ampoule connectée.

## Principe

Les appareils Tuya acceptent les commandes directement sur le LAN (port 6668, protocole 3.3), à condition
de connaître leur *local key*. Cette clé ne s'obtient que via l'API cloud Tuya, mais **une seule fois** :
une fois `devices.json` généré, le pilotage des appareils Tuya fonctionne sans Internet.

Le cloud Tuya est requis pour ajouter un nouvel appareil.
La TV est allumée par Wake-on-LAN et éteinte par l'API de télécommande Samsung sur le réseau local.

Les adresses IP ne sont jamais codées en dur : les appareils sont redécouverts à chaque démarrage en
écoutant les broadcasts UDP qu'ils émettent sur le port 6667. Un changement de bail DHCP est sans effet.

## Fonctionnalités

- Marche/arrêt, température, mode et vitesse de ventilation des climatiseurs
- Position du panneau (louvre) : positions fixes, oscillation, arrêt
- Unité de température (Celsius ou Fahrenheit) et minuterie restante
- Éco, sommeil, affichage, séchage et santé
- Marche/arrêt, luminosité et température de couleur des ampoules
- Couleur, scènes et minuterie d'extinction des ampoules, mode ne pas déranger
- Préréglages par appareil : capture de l'état courant, rejeu en un clic
- Rafraîchissement automatique adaptatif, détection des appareils hors ligne
- TV Samsung : allumage par Wake-on-LAN, extinction et lecture de l'état par l'API locale
- Télécommande TV complète, en fenêtre de bureau ou en page web servie sur le réseau local

Les commandes couvrent tous les points de données que les appareils acceptent réellement.
Les fonctions déclarées par le cloud Tuya mais ignorées par le matériel sont volontairement absentes : mode musique, programmations horaires et mémoire d'état côté ampoule.

Le séchage, lui, est bien mémorisé par le climatiseur tant qu'il fonctionne, mais il n'a produit aucune ventilation après extinction et le point de données retombe à `false` au cycle marche/arrêt suivant.

Deux points de données du climatiseur sont en revanche absents, car l'appareil les acquitte d'un bip sans rien en faire.
`cleaning` ne lance aucun cycle et ne remonte jamais à `true`.
`heat` n'a pas d'effet propre, l'appareil le traite comme un alias du séchage, alors que le chauffage se règle par le mode.

## Installation

```bash
git clone https://github.com/EricBlanquer/smartlife-tray.git
cd smartlife-tray
python3 -m venv --system-site-packages venv
venv/bin/pip install -r requirements.txt
```

Le `--system-site-packages` est nécessaire : PyGObject (GTK) vient des paquets système, pas de pip.

Dépendances système (Debian / Ubuntu / Mint) :

```bash
sudo apt install gir1.2-ayatanaappindicator3-0.1 python3-gi iproute2
```

## Récupérer ses local keys

1. Créer un compte sur [platform.tuya.com](https://platform.tuya.com), puis un *Cloud Project*
   (Development Method : **Smart Home**, data center correspondant à votre région).
2. Onglet *Service API* : souscrire **IoT Core**, **Authorization Token Management** et
   **Smart Home Basic Service**.
3. Onglet *Devices* → *Link App Account* → *Add App Account* : scanner le QR code depuis l'app
   SmartLife (onglet *Me*, bouton QR). Le data center doit correspondre à celui du compte SmartLife,
   sinon aucun appareil n'apparaît.
4. Générer `devices.json` :

```bash
venv/bin/python -m tinytuya wizard
```

L'Access ID et l'Access Secret se trouvent dans l'onglet *Overview* du projet.

`devices.json` contient les local keys : il est dans le `.gitignore` et doit rester en `chmod 600`.

L'abonnement IoT Core expire au bout d'un mois (renouvelable gratuitement). **Cela n'affecte pas
l'application**, qui fonctionne hors ligne. Seul l'ajout de nouveaux appareils est concerné.

## Lancement

```bash
./smartlife-tray
```

Le lanceur retrouve le venv et le script à côté de lui, le dépôt peut donc être cloné n'importe où.

Pour un démarrage automatique, créer `~/.config/autostart/smartlife-tray.desktop` :

```ini
[Desktop Entry]
Type=Application
Name=SmartLife
Exec=/chemin/vers/smartlife-tray
Icon=/chemin/vers/icons/smartlife-tray.svg
Terminal=false
```

## Télévision Samsung

Le sous-menu **Télévision** propose **Allumer** et **Éteindre**.
L'état est lu sur l'API locale Samsung et rafraîchi avec les autres appareils.
Quand la TV est allumée, le menu propose l'extinction.
Quand elle annonce sa veille, il propose l'allumage.
Si elle ne répond pas, l'état est inconnu et les deux actions restent disponibles.

Créer `~/.config/smartlife-tray/tv.json` (ou sous `$XDG_CONFIG_HOME`) :

```json
{
  "host": "192.0.2.10",
  "mac": "02:11:22:33:44:55"
}
```

Remplacer l'adresse et la MAC par celles de la TV, puis relancer l'application.
Une réservation DHCP permet de conserver son adresse.
Sans configuration valide, les commandes TV sont désactivées et les appareils Tuya restent utilisables.

L'allumage envoie des rafales de dix paquets Wake-on-LAN sur chacun des ports UDP 9 et 7,
depuis l'interface choisie par la route vers la TV et vers son adresse de broadcast réelle.
Les rafales sont répétées jusqu'à confirmation de l'état allumé, pendant un maximum de 45 secondes.
Activer l'allumage par un appareil mobile dans les paramètres réseau de la TV.
L'extinction utilise la touche `KEY_POWER` via
[samsungtvws](https://github.com/xchwarze/samsung-tv-ws-api), sur le port TLS 8002.
L'état est vérifié avant la connexion et juste avant l'envoi : la touche n'est envoyée que si la TV est allumée.
Lors de la première connexion, accepter **SmartLife** sur la TV si elle demande une autorisation.
Le jeton d'appairage reste dans `~/.config/smartlife-tray/tv_token.txt`, avec les permissions `600`.

Les commandes tournent en arrière-plan et leur résultat apparaît dans le menu.
« Commande envoyée » confirme l'envoi, tandis que le titre du sous-menu affiche l'état lu sur la TV.
Un échec affiche un message et permet de réessayer.

## Télécommande

**Télévision → Télécommande…** ouvre une fenêtre qui reproduit la télécommande : marche/arrêt, source,
accueil, menu, guide, infos, flèches et OK, retour, quitter, volume, muet, chaînes, lecture, chiffres, mode
Ambiant, micro, Netflix, Prime Video et Rakuten TV.
Elle s'ouvre collée au coin inférieur droit de la zone de travail de l'écran principal, au-dessus du panneau,
et y reste ancrée quand elle s'agrandit.
Les touches sont décrites une seule fois dans `remote_layout.py`, partagé avec la page web.

Les touches partent sur une connexion WebSocket gardée ouverte, pour réagir sans délai.
La TV y envoie un ping toutes les 6 s : avant chaque touche, les messages en attente sont lus et les pings
reçoivent leur pong, sans attendre de message de données.
La connexion est rouverte si la TV l'a fermée ou après 60 s d'inactivité, et la touche est renvoyée une fois
sur une nouvelle connexion si l'envoi échoue.
Le bouton marche/arrêt relit l'état de la TV puis allume par Wake-on-LAN ou éteint, comme le menu.
Maintenir une flèche ou le volume répète la touche ; un échec s'affiche et vide les touches en attente.

### Photo de la télécommande

La fenêtre et la page web affichent la photo entière d'une Samsung BN59-01311B, la télécommande de la série Q
de 2019 : `images/remote-skin.png`, versionnée avec ses sources.
Ses touches sont cliquables : marche/arrêt, anneau directionnel et OK, retour, accueil, lecture/pause,
bascules VOL et CH.
Comme sur la vraie télécommande, chaque bascule a trois zones : au-dessus de la barre pour monter,
au-dessous pour descendre, et la barre elle-même pour l'appui, qui coupe ou rétablit le son (VOL) ou ouvre
le guide des programmes (CH) ; la molette de la souris règle le volume ou change de chaîne.
**123** ouvre à côté un pavé assorti, en aluminium brossé, avec les autres touches et les chiffres.
Ambient envoie `KEY_AMBIENT` et le micro `KEY_MIC`.
Netflix, Prime Video et Rakuten TV lancent leur application par son identifiant (`*_APP_ID` dans
`remote_layout.py`) sur la même connexion WebSocket, après avoir vérifié sur l'API de la TV qu'elle est
installée ; sinon le bandeau d'état l'indique.
Ce pavé est dessiné en SVG par `remote_keypad.py` d'après `KEYPAD_FUNCTION_ROWS` et `DIGIT_ROWS`, et la page web
le reçoit sur `/remote-keypad.svg`.

La fenêtre affiche la photo réduite de moitié (`SKIN_DISPLAY_SCALE`), sans marge ni barre de titre, sur un fond
transparent quand le bureau est composité.
Un clic maintenu hors des touches suivi d'un glisser la déplace ; le clic droit propose de la fermer, comme Alt+F4.
L'état (connexion, échec, commande marche/arrêt) apparaît dans un bandeau sur le bas de la photo, qui laisse
passer les clics et disparaît 5 s après un message final ; la page web ajuste la photo à la hauteur de l'écran.

`prepare_remote_skin.py` reconstruit cette image à partir des photos de `images/` (Pillow et NumPy requis,
voir `requirements-dev.txt`) :

- `remote-detail.jpg` (fiche idealo) donne les détails : redressée par sa perspective, elle fixe la géométrie
  sur laquelle les zones de `remote_skin.py` sont calibrées ;
- `remote-tones.png` (fiche matelecommandetv.com, AVIF décodé sans perte) donne les tons gris neutres : ses
  variations lentes remplacent les reflets et la teinte bleue de la première ;
- `remote-ring.png` et `remote-rocker.png` (photo produit Amazon de la One Remote) donnent l'anneau
  directionnel et la bascule VOL/CH, incrustés à leur place ;
- la tache de la fenêtre infrarouge est reconstruite d'après son voisinage, et la silhouette prend un bord
  supérieur droit et des coins arrondis.

```bash
venv/bin/pip install -r requirements-dev.txt
venv/bin/python prepare_remote_skin.py
```

Les dimensions de chaque photo sont vérifiées, puisque les positions sont calibrées sur elles.
Si l'image manque ou n'a pas les dimensions attendues, la grille de boutons est affichée.

### Raccourcis clavier

Identiques dans la fenêtre et la page web :

| Touche | Action |
|--------|--------|
| Veille | Marche/arrêt |
| Flèches | Navigation (répétée tant que la touche est enfoncée) |
| Entrée | OK |
| Retour arrière | Retour |
| Échap | Quitter |
| Origine | Accueil |
| Maison (page d'accueil) | Menu |
| Espace | Lecture/pause |
| `+` / `-` | Volume |
| `m` | Muet |
| Page haut / Page bas | Chaîne + / Chaîne − |
| `c` | Liste des chaînes |
| `s`, `g`, `i` | Source, guide, infos |
| `0` à `9` | Chiffres |

La touche veille n'atteint la fenêtre que si le bureau ne l'intercepte pas : sous Cinnamon, le raccourci
« Mettre en veille » doit rester vide.
Dans un navigateur, la touche maison peut être réservée à la page d'accueil du navigateur.

## Télécommande web

`tv_remote_server.py` sert la même télécommande en page web, utilisable depuis un téléphone sur le réseau local.
Il n'a besoin que de `samsungtvws` et de la même configuration `tv.json` :

```bash
python3 -m venv venv
venv/bin/pip install -r requirements-server.txt
venv/bin/python tv_remote_server.py --bind 192.0.2.20 --port 8095
```

`--bind` prend l'adresse IP de la machine sur le LAN (127.0.0.1 par défaut).
Ne pas écouter sur toutes les interfaces d'une machine dotée d'une IPv6 publique, ni rediriger ce port depuis la box :
la page n'a pas d'authentification, tout appareil qui l'atteint commande la TV.
La page refuse les requêtes intersites : en-tête `Host` limité aux adresses IP et aux noms passés par
`--allowed-host`, `Origin` identique à la page, corps JSON obligatoire et liste blanche des touches.

Exemple de service systemd (`/etc/systemd/system/tv-remote.service`) :

```ini
[Unit]
Description=Samsung TV web remote
After=network-online.target
Wants=network-online.target

[Service]
User=utilisateur
ExecStart=/chemin/vers/venv/bin/python /chemin/vers/tv_remote_server.py --bind 192.0.2.20
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

La configuration et le jeton se trouvent dans `~/.config/smartlife-tray/` de l'utilisateur du service.
Le premier envoi de touche déclenche la demande d'autorisation **SmartLife** sur la TV, comme pour l'extinction.

## Tests

```bash
xvfb-run -a venv/bin/python -m unittest -v
```

Les tests vérifient les menus GTK, les erreurs réseau, les états inconnus, les permissions
du jeton, les paquets WoL reçus par des sockets UDP locales, la fenêtre de télécommande,
la reprise de connexion et les protections du serveur web.
Ils ne commandent aucun appareil réel.

## Préréglages

Chaque appareil a son sous-menu **Préréglages**.
« Enregistrer l'état actuel… » demande un nom et mémorise les réglages en cours, un préréglage
existant peut être remplacé.
Cliquer sur un préréglage le rejoue : l'appareil est allumé au besoin, puis tous ses points de données
partent en une seule commande.

Les préréglages sont stockés hors du dépôt, dans `~/.config/smartlife-tray/presets.json`
(ou sous `$XDG_CONFIG_HOME`), écrit de façon atomique.

| Appareil | Points de données mémorisés |
|----------|-----------------------------|
| Climatiseur | marche, unité, mode, consigne, ventilation, panneau, éco, sommeil, affichage, séchage, santé |
| Ampoule | marche, mode, luminosité, température de couleur, couleur, scène, ne pas déranger |

La température ambiante et les minuteries restent de côté : ce sont des états transitoires, pas des réglages.
Au rejeu d'un préréglage d'ampoule, seul le point de données du mode mémorisé est renvoyé (température de
couleur, couleur ou scène), pour que la lampe ne rebascule pas dans un autre mode.

## Rafraîchissement adaptatif

L'état des appareils n'est pas poussé par les appareils : il faut les interroger. Comme l'état n'est
visible que menu ouvert, la fréquence d'interrogation suit l'ouverture du menu :

| Situation | Intervalle |
|-----------|-----------|
| Pendant les 60 s qui suivent une interaction avec le menu | 4 s, plus un rafraîchissement immédiat |
| Au repos | 180 s |
| Avant toute interaction avec le menu | 15 s |

Un changement fait depuis l'application SmartLife ou depuis un assistant vocal est donc visible en
4 s au pire pendant que le menu est ouvert.

Sous AppIndicator, le menu est dessiné par le shell via D-Bus : le `GtkMenu` local n'est jamais
affiché et ses signaux `show` / `hide` ne se déclenchent pas à l'ouverture. La détection passe donc
par une connexion D-Bus en mode moniteur, qui observe les appels `com.canonical.dbusmenu` adressés à
l'application : `AboutToShowGroup` à l'ouverture du menu racine, `EventGroup` lors de la navigation
dans les sous-menus.

Il n'existe pas de signal de fermeture du menu racine : sous Cinnamon, ouvrir le menu, le laisser
ouvert puis le refermer ne produit qu'un seul message, `AboutToShowGroup` à l'ouverture. La cadence
rapide fonctionne donc par fenêtre glissante de 60 s, réarmée à chaque interaction, plutôt que par
détection d'ouverture et de fermeture.

Pour contrôler la cadence réellement appliquée, passer `SHOW_POLL_COUNTDOWN` à `True` en tête de
`smartlife_tray.py` : la ligne d'état affiche alors le nombre de secondes restantes avant la
prochaine interrogation. Désactivé par défaut.

Garde-fou : tant qu'aucune interaction avec le menu n'a été observée, l'intervalle reste à 15 s. Si
le bureau n'émet pas ces appels ou si le mode moniteur est refusé, l'application ne se retrouve
jamais bloquée à 180 s.

## DPS

Relevés depuis les spécifications officielles du cloud, pas devinés.

### Climatiseurs (`kt`)

| DP | Code | Type | Valeurs |
|---|---|---|---|
| 1 | `switch` | Boolean | |
| 2 | `temp_set` | Integer | **scale 1** : `260` = 26 °C, pas de 1 °C |
| 3 | `temp_current` | Integer | scale 1, lecture seule |
| 4 | `mode` | Enum | `auto`, `cold`, `wet`, `heat`, `fan` |
| 5 | `fan_speed_enum` | Enum | `auto`, `low`, `low_mid`, `mid`, `mid_high`, `high`, `mute`, `turbo` |
| 8 | `eco` | Boolean | |
| 109 | `sleep` | Boolean | |
| 107 | *(non documenté)* | String | Panneau (voir ci-dessous) |

### Ampoules (`dj`)

| DP | Code | Type | Valeurs |
|---|---|---|---|
| 20 | `switch_led` | Boolean | |
| 21 | `work_mode` | Enum | `white`, `colour`, `scene`, `music` |
| 22 | `bright_value_v2` | Integer | 10 → 1000 |
| 23 | `temp_value_v2` | Integer | 0 → 1000 (température de couleur) |
| 24 | `colour_data_v2` | Json | TSV (**non exposé dans l'UI actuelle**) |

### Panneau (`dp107`) : DPS propriétaire

Le contrôle du panneau (louvre) **n'existe dans aucune API cloud** : `getdps`, `getfunctions`,
`getproperties` et `getstatus` l'ignorent tous. Il n'est exposé qu'en local par le fabricant.

Sa sémantique a été établie **empiriquement**, en observant les DPS pendant une manipulation depuis
l'app SmartLife, puis vérifiée par écriture directe :

| Valeur écrite | Effet |
|---|---|
| `"1"` … `"5"` | Position fixe du panneau |
| `"15"` | Oscillation |
| `"off"` | Panneau éteint |

Le type est **String**, pas Integer : `"3"` et non `3`.

`dp15` (`un_down` / `off`) est un **miroir en lecture seule** : le device le met à jour tout seul quand
`dp107` change. Il ne faut pas l'écrire : `dp107` seul suffit dans tous les cas, extinction comprise.

Ces DPS sont propres au modèle testé. Sur un autre climatiseur, relever les valeurs réelles avec le
script de découverte plutôt que de reprendre celles-ci telles quelles.

### Découvrir les DPS d'un appareil inconnu

Pour identifier un DPS non documenté, surveiller l'état local pendant une manipulation depuis l'app
SmartLife : le DP qui change est le bon, et sa valeur donne le format attendu.

```bash
venv/bin/python -m tinytuya scan
```

## Limitations connues

- **Plage de température bornée à 16 à 30 °C dans l'UI.** La spec Tuya annonce 16 à 88 °C, mais c'est le
  gabarit générique du profil, pas la plage réelle des appareils.
- **Couleur RVB non exposée.** Les ampoules la supportent (`colour_data_v2`), seuls le blanc et la
  température de couleur sont pilotables depuis le menu.
- Un seul data center est autorisé par la Trial Edition Tuya.
- Les protocoles Tuya 3.4 et 3.5 ne sont pas testés (seul 3.3 l'est).

## Licence

MIT pour le code.
Les photos de `images/` sont des photos produit Samsung reprises de fiches commerciales : elles ne sont pas
couvertes par cette licence.
