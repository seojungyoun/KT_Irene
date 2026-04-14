# #!/usr/bin/env bash
# set -euo pipefail

# FILES=(
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

# echo "Resolving conflicts by keeping CURRENT branch changes (--ours)..."
# for f in "${FILES[@]}"; do
#   if git ls-files --unmerged -- "$f" | rg . >/dev/null; then
#     git checkout --ours -- "$f"
#     git add "$f"
#     echo "resolved: $f"
#   fi
# done

# echo "Done. Review diff and commit."
