# SmartLife Tray

Indicateur systray GTK pour piloter des appareils Tuya (SmartLife) **en local**, sans passer par le cloud.

Testé sous Linux Mint / Cinnamon, avec des climatiseurs et une ampoule connectée.

## Principe

Les appareils Tuya acceptent les commandes directement sur le LAN (port 6668, protocole 3.3), à condition
de connaître leur *local key*. Cette clé ne s'obtient que via l'API cloud Tuya, mais **une seule fois** :
une fois `devices.json` généré, l'application ne contacte plus jamais Internet.

Le cloud n'est donc requis que pour ajouter un nouvel appareil.

Les adresses IP ne sont jamais codées en dur : les appareils sont redécouverts à chaque démarrage en
écoutant les broadcasts UDP qu'ils émettent sur le port 6667. Un changement de bail DHCP est sans effet.

## Fonctionnalités

- Marche/arrêt, température, mode et vitesse de ventilation des climatiseurs
- Position du panneau (louvre) : positions fixes, oscillation, arrêt
- Éco et sommeil
- Marche/arrêt, luminosité et température de couleur des ampoules
- Rafraîchissement automatique, détection des appareils hors ligne

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
venv/bin/python smartlife_tray.py
```

Pour un démarrage automatique, créer `~/.config/autostart/smartlife-tray.desktop` :

```ini
[Desktop Entry]
Type=Application
Name=SmartLife
Exec=/chemin/vers/venv/bin/python /chemin/vers/smartlife_tray.py
Icon=/chemin/vers/icons/smartlife-tray.svg
Terminal=false
```

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
