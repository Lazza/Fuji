# Fuji: Forensic Unattended Juicy Imaging

Fuji is a free, open source software for performing forensic acquisition of Mac
computer. It should work on any modern Intel or M1 device, as it leverages
standard executable provided by macOS.

Fuji performs a so-called *live acquisition* (the computer must be turned on) of
*logical* nature, i.e. it includes an archive of existing files. The software
generates a DMG file that can be imported in several digital forensics programs.


## Drive preparation

Please carefully follow the installation procedure:

1. Partition your destination drive using the **exFAT** file system
2. Set the volume label as `Fuji`
3. Download and copy the universal Fuji DMG in the drive


## Usage
