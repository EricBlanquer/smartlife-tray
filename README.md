# SmartLife Tray

Indicateur systray GTK pour piloter des appareils Tuya (SmartLife) **en local** et allumer la TV via Alexa.

Testé sous Linux Mint / Cinnamon, avec des climatiseurs et une ampoule connectée.

## Principe

Les appareils Tuya acceptent les commandes directement sur le LAN (port 6668, protocole 3.3), à condition
de connaître leur *local key*. Cette clé ne s'obtient que via l'API cloud Tuya, mais **une seule fois** :
une fois `devices.json` généré, le pilotage des appareils Tuya fonctionne sans Internet.

Le cloud Tuya est requis pour ajouter un nouvel appareil.
L'allumage de la TV via Alexa utilise Internet et le compte Amazon configuré dans `alexa-cmd`.

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
- Allumage de la TV depuis **Télévision → Allumer avec Alexa**

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
venv/bin/pip install tinytuya
```

Le `--system-site-packages` est nécessaire : PyGObject (GTK) vient des paquets système, pas de pip.

Dépendances système (Debian / Ubuntu / Mint) :

```bash
sudo apt install gir1.2-ayatanaappindicator3-0.1 python3-gi
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

## Télévision via Alexa

Le menu **Télévision → Allumer avec Alexa** envoie la commande « allume la télé »
avec [alexa-cmd](https://github.com/EricBlanquer/alexa-cmd), sur l'appareil Alexa
par défaut configuré dans cet outil.
La TV doit déjà être pilotable par cette commande dans Alexa.

L'exécutable `alexa` est recherché dans le `PATH`, puis dans `~/alexa-cmd/alexa`,
ce qui couvre aussi le démarrage automatique depuis le bureau.
Les commandes Tuya restent disponibles si `alexa-cmd` n'est pas installé.

Si Amazon demande une reconnexion, `alexa-cmd` ouvre le navigateur pour s'authentifier.
La commande tourne en arrière-plan, avec un délai maximal de six minutes, et le menu
indique son envoi ou son échec.
« Commande envoyée à Alexa » confirme l'envoi à Alexa, sans lecture de l'état réel de la TV.
Une erreur affiche un message et permet de réessayer.

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

MIT
