# #!/usr/bin/env bash
# set -euo pipefail

# TARGETS=(
#   README.md
#   app/main.py
#   app/models.py
#   app/schemas.py
#   app/services/renderer.py
#   app/services/tts.py
#   app/services/video.py
#   app/static/app.js
#   app/static/index.html
#   app/static/style.css
# )

# found=0
# for f in "${TARGETS[@]}"; do
#   if [[ -f "$f" ]]; then
#     if rg -n "^(<<<<<<<|=======|>>>>>>>)" "$f" >/dev/null; then
#       echo "[CONFLICT] $f"
#       rg -n "^(<<<<<<<|=======|>>>>>>>)" "$f"
#       found=1
#     fi
#   fi
# done

# if [[ "$found" -eq 0 ]]; then
#   echo "No conflict markers found in tracked target files."
# fi
