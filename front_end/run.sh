#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

node -e "const v=process.versions.node.split('.').map(Number); if (v[0] < 20 || (v[0] === 20 && v[1] < 19)) { console.error('Node.js 20.19+ or 22.12+ is required. Current: ' + process.versions.node); process.exit(1); }"

if [ ! -d "node_modules" ]; then
  npm install
fi

npm run dev -- --host 0.0.0.0
