#!/usr/bin/env python3

# See https://github.com/microsoft/vscode-python/issues/8372
import json
import subprocess
from pathlib import Path
from os import path

# note if you only just installed poetry, you may need to run;
# source $HOME/.poetry/env
venv_path = subprocess.check_output("poetry env info --path", shell=True)
venv_path = venv_path.decode("UTF-8")

print(f"venv_path = {venv_path}")

settings = dict()

Path(".vscode").mkdir(parents=True, exist_ok=True)

if Path(".vscode/settings.json").exists():
    with open(".vscode/settings.json", "r") as f:
        settings = json.load(f)
        print(f"old settings={settings}")
else:
    Path(".vscode/settings.json").touch()

settings["python.venvPath"] = venv_path
settings["python.pythonPath"] = path.join(venv_path,"Scripts","python.exe")
# Add the settings for linting
settings["python.linting.pycodestyleEnabled"] = False
settings["python.linting.enabled"] = True
settings["python.linting.pylintEnabled"] = True

settings["python.linting.flake8Enabled"] = True
settings["python.formatting.provider"] = "black"
settings["editor.formatOnSave"] = True
settings["python.linting.flake8Args"] = [
    "--max-line-length=120",
    "--ignore=E402,F841,F401,E302,E305,W503",
]
settings["autoDocstring.docstringFormat"] = "google"

with open(".vscode/settings.json", "w") as f:
    json.dump(settings, f, sort_keys=True, indent=4)

print(f"new settings: {json.dumps(settings, sort_keys=True, indent=4)}")
abs_path = str(Path(".vscode/settings.json").resolve())
print(f"written to: {abs_path}")
