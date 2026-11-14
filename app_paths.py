import os

APP_ID = "smartlife-tray"
CONFIG_HOME = os.environ.get("XDG_CONFIG_HOME") or os.path.join(
    os.path.expanduser("~"), ".config"
)
CONFIG_DIR = os.path.join(CONFIG_HOME, APP_ID)
