#!/bin/sh
# Update Inkwell: pull the latest code from GitHub and reinstall it.
# Your notes are never touched. Run it from anywhere: ./update.sh
set -e

cd "$(dirname "$0")"

git checkout main
git pull --ff-only origin main
make install

echo "Inkwell is up to date. Restart it to use the new version."
