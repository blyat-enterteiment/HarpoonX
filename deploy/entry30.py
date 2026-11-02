"""Initialize the dedicated persistent directory and drop root before serving."""
import os
from pathlib import Path

root = Path(os.environ.get('HARPOON_DATA', '/var/data'))
root.mkdir(parents=True, exist_ok=True)
if os.getuid() == 0:
    for entry in [root, *root.rglob('*')]:
        if not entry.is_symlink():
            os.chown(entry, 1000, 1000)
    os.setgroups([])
    os.setgid(1000)
    os.setuid(1000)
os.execvp('node', ['node', 'runtime30/server.js'])
