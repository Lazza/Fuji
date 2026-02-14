#!/bin/bash

SCRIPT_DIR=$(echo "$0" | sed 's|/[^/]*$||')
cd "$SCRIPT_DIR"

if command -v id &>/dev/null; then
    if [ $(id -u) -eq 0 ]; then
        ./Fuji.bin
    else
        security execute-with-privileges "./Fuji.bin"
    fi
else
    # Command "id" not found, run Fuji without checking for root privileges
    ./Fuji.bin
fi
