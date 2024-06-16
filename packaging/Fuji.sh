#!/bin/bash

cd "$(dirname "$0")"

if [ $(id -u) -eq 0 ]; then
    ./Fuji.bin
else
    security execute-with-privileges "./Fuji.bin"
fi
