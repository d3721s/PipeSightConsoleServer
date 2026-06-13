#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

# Require a Vite 7 / Vue 3 compatible Node.
node -e "const v=process.versions.node.split('.').map(Number); if (v[0] < 20 || (v[0] === 20 && v[1] < 19)) { console.error('Node.js 20.19+ or 22.12+ is required. Current: ' + process.versions.node); process.exit(1); }"

# Install dependencies when they're missing OR out of sync with package.json.
# The previous version only installed when node_modules was entirely absent, so
# an existing checkout never picked up newly-added deps (@carbon/vue,
# @carbon/icons-vue, vue-router) and Vite failed with "Failed to resolve
# @carbon/vue". We install if node_modules is missing, if any required dep is
# absent, or if package.json is newer than the last install.
needs_install=0
if [ ! -d "node_modules" ]; then
  needs_install=1
else
  for dep in @carbon/vue @carbon/icons-vue vue-router vue vite; do
    if [ ! -d "node_modules/$dep" ]; then
      echo "Dependency '$dep' is missing from node_modules."
      needs_install=1
      break
    fi
  done
  # package.json edited after node_modules was last written => reinstall.
  if [ "$needs_install" -eq 0 ] && [ "package.json" -nt "node_modules" ]; then
    echo "package.json is newer than node_modules."
    needs_install=1
  fi
fi

if [ "$needs_install" -eq 1 ]; then
  echo "Installing front-end dependencies..."
  npm install
fi

npm run dev -- --host 0.0.0.0
