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

1. Connect the destination drive to the target Mac computer
2. Open the Fuji DMG and click on _Full Disk Access Settings.url_
3. Drag the _Fuji.app_ file on the list of authorized apps and ensure the toggle
   is enabled
4. Run _Fuji.app_
5. When prompted, insert the password for the administrator user


## Development

Fuji is developed as a Universal2 application using the **3.11.7 release** of
Python from <https://python.org>.

The DMG file can be built by using the included Pyinstaller script:

    pyinstaller Fuji.spec
