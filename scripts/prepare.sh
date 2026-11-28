#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mkdir -p "$ROOT/target/deploy"
cp "$ROOT/keys/stokvel-keypair.json" "$ROOT/target/deploy/stokvel-keypair.json"
echo "Prepared the included local-development program keypair."
echo "For a public deployment, replace it with a keypair you control and update the program ID in Anchor.toml and lib.rs."
