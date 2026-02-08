#!/bin/bash

set -ex

SCRIPT_DIR=$(echo "$0" | sed 's|/[^/]*$||')
cd "$SCRIPT_DIR"
./Fuji.app/Contents/MacOS/Fuji
