import os,pathlib
root=pathlib.Path('/var/data');root.mkdir(exist_ok=True)
# Render disk initialization only; application runs as uid 1000.
for path in [root,*root.rglob('*')]:
 if not path.is_symlink():os.chown(path,1000,1000)
os.setgroups([]);os.setgid(1000);os.setuid(1000)
os.execvp('node',['node','deploy/managed.cjs'])
