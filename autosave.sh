#!/bin/sh
# Commit and push anything changed in Alfie's workspace. Runs nightly (systemd
# timer on the LXC); safe to run any time. Pushes his own unpushed commits too.
cd "${PROJECTS:-/config/workspace}" || exit 0
[ -d .git ] || exit 0
git add -A
git diff --cached --quiet || git commit -q -m "Autosave $(date +'%-d %B %Y')"
if git push -q origin HEAD 2>/tmp/autosave-push.err; then
    echo "autosave: pushed $(git rev-parse --short HEAD)"
else
    echo "autosave: push failed, will retry next time: $(cat /tmp/autosave-push.err)"
fi
