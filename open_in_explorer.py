import os
import shutil
import subprocess
from pathlib import Path

def open_in_explorer(file_paths, base_dir):
    """
    Erstellt einen Sammelordner mit Windows-Shortcuts (.lnk)
    zu allen übergebenen Dateien und öffnet ihn im Explorer.
    """

    base_dir = Path(base_dir)
    explorer_dir = base_dir / "_metaExplorer_selection"

    # Ordner neu aufbauen
    if explorer_dir.exists():
        shutil.rmtree(explorer_dir)
    explorer_dir.mkdir(parents=True, exist_ok=True)

    name_counter = {}

    for file_path in file_paths:
        target = Path(file_path)

        if not target.exists():
            continue

        stem = target.stem
        suffix = target.suffix

        # Kollisionen vermeiden
        count = name_counter.get(stem, 0)
        name_counter[stem] = count + 1

        if count == 0:
            link_name = f"{stem}{suffix}.lnk"
        else:
            link_name = f"{stem} ({count}){suffix}.lnk"

        link_path = explorer_dir / link_name

        create_windows_shortcut(link_path, target)

    # Explorer öffnen
    subprocess.Popen(["explorer", str(explorer_dir)])

def create_windows_shortcut(link_path: Path, target_path: Path):
    """
    Erstellt eine Windows-Verknüpfung (.lnk) per PowerShell.
    """

    ps_script = f"""
    $WshShell = New-Object -ComObject WScript.Shell
    $Shortcut = $WshShell.CreateShortcut("{link_path}")
    $Shortcut.TargetPath = "{target_path}"
    $Shortcut.WorkingDirectory = "{target_path.parent}"
    $Shortcut.Save()
    """

    subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps_script],
        capture_output=True
    )
