#!/bin/bash

cd "$(dirname "$0")"
osascript -e 'do shell script "sudo ./Fuji.bin" with prompt "Fuji needs root access." with administrator privileges' &
