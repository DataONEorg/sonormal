from dynaconf import Dynaconf
import os

settings = Dynaconf(
    environments=True,
    envvar_prefix="SONORMAL",
    settings_files=[
        "/etc/sonormal/sonormal.toml",
        "/usr/local/etc/sonormal/sonormal.toml",
        os.path.expanduser("~/.local/sonormal/sonormal.toml"),
        "settings.toml",
    ],
)

# `envvar_prefix` = export envvars with `export DYNACONF_FOO=bar`.
# `settings_files` = Load this files in the order.
