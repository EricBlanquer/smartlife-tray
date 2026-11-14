POWER_ACTION = "power"
STYLE_POWER = "power"
STYLE_ACCENT = "accent"
COLUMNS = 3


def button(key, label, title, gtk_keys=(), web_keys=(), repeat=False, style=None):
    return {
        "key": key,
        "label": label,
        "title": title,
        "gtk_keys": list(gtk_keys),
        "web_keys": list(web_keys),
        "repeat": repeat,
        "style": style,
    }


def digit(value):
    name = str(value)
    return button(f"KEY_{value}", name, name, (name, f"KP_{value}"), (name,))


REMOTE_LAYOUT = [
    [
        button(POWER_ACTION, "⏻", "Marche/Arrêt", style=STYLE_POWER),
        button("KEY_SOURCE", "Source", "Source", ("s",), ("s",)),
        button("KEY_HOME", "Accueil", "Accueil", ("Home",), ("Home",)),
    ],
    [
        button("KEY_MENU", "Menu", "Menu"),
        button("KEY_GUIDE", "Guide", "Guide des programmes", ("g",), ("g",)),
        button("KEY_INFO", "Infos", "Informations", ("i",), ("i",)),
    ],
    [
        None,
        button("KEY_UP", "▲", "Haut", ("Up", "KP_Up"), ("ArrowUp",), repeat=True),
        None,
    ],
    [
        button("KEY_LEFT", "◀", "Gauche", ("Left", "KP_Left"), ("ArrowLeft",), repeat=True),
        button("KEY_ENTER", "OK", "Valider", ("Return", "KP_Enter"), ("Enter",), style=STYLE_ACCENT),
        button("KEY_RIGHT", "▶", "Droite", ("Right", "KP_Right"), ("ArrowRight",), repeat=True),
    ],
    [
        None,
        button("KEY_DOWN", "▼", "Bas", ("Down", "KP_Down"), ("ArrowDown",), repeat=True),
        None,
    ],
    [
        button("KEY_RETURN", "Retour", "Retour", ("BackSpace",), ("Backspace",)),
        button("KEY_MUTE", "Muet", "Couper le son", ("m",), ("m",)),
        button("KEY_EXIT", "Quitter", "Quitter", ("Escape",), ("Escape",)),
    ],
    [
        button("KEY_VOLUP", "Vol +", "Volume plus", ("plus", "KP_Add"), ("+",), repeat=True),
        button("KEY_CH_LIST", "Chaînes", "Liste des chaînes"),
        button("KEY_CHUP", "Ch +", "Chaîne suivante", ("Page_Up",), ("PageUp",)),
    ],
    [
        button("KEY_VOLDOWN", "Vol −", "Volume moins", ("minus", "KP_Subtract"), ("-",), repeat=True),
        None,
        button("KEY_CHDOWN", "Ch −", "Chaîne précédente", ("Page_Down",), ("PageDown",)),
    ],
    [
        button("KEY_REWIND", "◀◀", "Retour rapide"),
        button("KEY_PLAY", "Lecture", "Lecture"),
        button("KEY_FF", "▶▶", "Avance rapide"),
    ],
    [
        button("KEY_STOP", "Stop", "Stop"),
        button("KEY_PAUSE", "Pause", "Pause"),
        None,
    ],
    [digit(1), digit(2), digit(3)],
    [digit(4), digit(5), digit(6)],
    [digit(7), digit(8), digit(9)],
    [None, digit(0), None],
]

REMOTE_KEYS = frozenset(
    cell["key"]
    for row in REMOTE_LAYOUT
    for cell in row
    if cell is not None and cell["key"] != POWER_ACTION
)
