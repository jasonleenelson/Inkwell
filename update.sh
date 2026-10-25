#!/bin/sh
# Update Inkwell: pull the latest code from GitHub and reinstall it.
# Your notes are never touched. Run it from anywhere: ./update.sh
# Inkwell's Check for Updates runs this too, with INKWELL_PREFIX set to
# where it was installed (~/.local unless you chose otherwise).
set -e

cd "$(dirname "$0")"

git checkout main
git pull --ff-only origin main

prefix="${INKWELL_PREFIX:-$HOME/.local}"
commit="$(git rev-parse HEAD)"

# Can we write to the install folder (or the nearest folder above it)?
dir="$prefix/share/inkwell"
while [ ! -e "$dir" ]; do dir="$(dirname "$dir")"; done

if [ -w "$dir" ]; then
    make install PREFIX="$prefix" COMMIT="$commit"
elif [ -n "$DISPLAY$WAYLAND_DISPLAY" ] && command -v pkexec >/dev/null; then
    echo "Installing into $prefix needs administrator rights."
    pkexec "$(command -v make)" -C "$PWD" install PREFIX="$prefix" COMMIT="$commit"
else
    echo "Installing into $prefix needs administrator rights."
    sudo make install PREFIX="$prefix" COMMIT="$commit"
fi

echo "Inkwell is up to date. Restart it to use the new version."
