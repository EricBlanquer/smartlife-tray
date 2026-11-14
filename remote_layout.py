POWER_ACTION = "power"
PANEL_ACTION = "panel"
STYLE_POWER = "power"
STYLE_ACCENT = "accent"
PLAY_PAUSE_KEY = "KEY_PLAY_BACK"


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


KEYS = {
    cell["key"]: cell
    for cell in (
        button(POWER_ACTION, "⏻", "Marche/Arrêt", ("XF86Sleep",), ("Standby",), style=STYLE_POWER),
        button(PANEL_ACTION, "123", "Chiffres et autres touches"),
        button("KEY_SOURCE", "Source", "Source", ("s",), ("s",)),
        button("KEY_HOME", "Accueil", "Accueil", ("Home",), ("Home",)),
        button("KEY_MENU", "Menu", "Menu", ("XF86HomePage",), ("BrowserHome",)),
        button("KEY_GUIDE", "Guide", "Guide des programmes", ("g",), ("g",)),
        button("KEY_INFO", "Infos", "Informations", ("i",), ("i",)),
        button("KEY_UP", "▲", "Haut", ("Up", "KP_Up"), ("ArrowUp",), repeat=True),
        button("KEY_LEFT", "◀", "Gauche", ("Left", "KP_Left"), ("ArrowLeft",), repeat=True),
        button("KEY_ENTER", "OK", "Valider", ("Return", "KP_Enter"), ("Enter",), style=STYLE_ACCENT),
        button("KEY_RIGHT", "▶", "Droite", ("Right", "KP_Right"), ("ArrowRight",), repeat=True),
        button("KEY_DOWN", "▼", "Bas", ("Down", "KP_Down"), ("ArrowDown",), repeat=True),
        button("KEY_RETURN", "Retour", "Retour", ("BackSpace",), ("Backspace",)),
        button("KEY_MUTE", "Muet", "Couper le son", ("m",), ("m",)),
        button("KEY_EXIT", "Quitter", "Quitter", ("Escape",), ("Escape",)),
        button("KEY_VOLUP", "Vol +", "Volume plus", ("plus", "KP_Add"), ("+",), repeat=True),
        button("KEY_VOLDOWN", "Vol −", "Volume moins", ("minus", "KP_Subtract"), ("-",), repeat=True),
        button("KEY_CH_LIST", "Chaînes", "Liste des chaînes", ("c",), ("c",)),
        button("KEY_CHUP", "Ch +", "Chaîne suivante", ("Page_Up",), ("PageUp",)),
        button("KEY_CHDOWN", "Ch −", "Chaîne précédente", ("Page_Down",), ("PageDown",)),
        button(PLAY_PAUSE_KEY, "⏯", "Lecture/Pause", ("space",), (" ",)),
        button("KEY_REWIND", "◀◀", "Retour rapide"),
        button("KEY_PLAY", "Lecture", "Lecture"),
        button("KEY_FF", "▶▶", "Avance rapide"),
        button("KEY_STOP", "Stop", "Stop"),
        button("KEY_PAUSE", "Pause", "Pause"),
        *(digit(value) for value in range(10)),
    )
}


def row(*keys):
    return [KEYS[key] if key else None for key in keys]


DIGIT_ROWS = [
    row("KEY_1", "KEY_2", "KEY_3"),
    row("KEY_4", "KEY_5", "KEY_6"),
    row("KEY_7", "KEY_8", "KEY_9"),
    row(None, "KEY_0", None),
]

REMOTE_LAYOUT = [
    row(POWER_ACTION, "KEY_SOURCE", "KEY_HOME"),
    row("KEY_MENU", "KEY_GUIDE", "KEY_INFO"),
    row(None, "KEY_UP", None),
    row("KEY_LEFT", "KEY_ENTER", "KEY_RIGHT"),
    row(None, "KEY_DOWN", None),
    row("KEY_RETURN", "KEY_MUTE", "KEY_EXIT"),
    row("KEY_VOLUP", "KEY_CH_LIST", "KEY_CHUP"),
    row("KEY_VOLDOWN", None, "KEY_CHDOWN"),
    row("KEY_REWIND", "KEY_PLAY", "KEY_FF"),
    row("KEY_STOP", "KEY_PAUSE", PLAY_PAUSE_KEY),
    *DIGIT_ROWS,
]

EXTRA_LAYOUT = [
    row("KEY_SOURCE", "KEY_MENU", "KEY_GUIDE"),
    row("KEY_INFO", "KEY_CH_LIST", "KEY_EXIT"),
    row("KEY_REWIND", "KEY_PLAY", "KEY_FF"),
    row("KEY_STOP", "KEY_PAUSE", "KEY_MUTE"),
    *DIGIT_ROWS,
]

LAYOUT_COLUMNS = 3
ACTIONS = frozenset((POWER_ACTION, PANEL_ACTION))
REMOTE_KEYS = frozenset(key for key in KEYS if key not in ACTIONS)
