# Fuji: Forensic Unattended Juicy Imaging

Fuji is a free, open source software for performing forensic acquisition of Mac
computer. It should work on any modern Intel or M1 device, as it leverages
standard executable provided by macOS.

Fuji performs a so-called *live acquisition* (the computer must be turned on) of
*logical* nature, i.e. it includes only existing files. The software generates a
DMG file that can be imported in several digital forensics programs.

It is released under the terms of the GNU General Public License (version 3).


## Drive preparation

Please carefully follow the installation procedure:

1. Partition your destination drive using the **exFAT** file system
2. Set the volume label as `Fuji`
3. Download and copy the universal Fuji DMG in the drive


## How to use Fuji

1. Connect the destination drive to the target Mac computer
2. Open the Fuji DMG and click on _Full Disk Access Settings.url_
3. If the window has a "lock" icon, unlock it
4. Drag the _Fuji.app_ file on the list of authorized apps **and ensure the
   toggle is enabled**
5. Now you can run _Fuji.app_
6. When prompted, insert the password for the administrator user

**Important:** before starting the acquisition, you must specify on what drive
you want to store the temporary sparseimage and the final DMG file. Both values
are `/Volumes/Fuji` by default and the _image name_ parameter will be used to
make a new directory inside those locations.

You must not save the disk images on the same drive you are acquiring!


## Development

Fuji is developed as a Universal2 application using the **3.10 release** of
Python from [Python.org][python].

You can create a virtual environment with:

    /usr/local/bin/python3.10 -m venv env

The DMG file can be built by using the included Pyinstaller script:

    pip install -r requirements.txt
    pyinstaller Fuji.spec

The build process must be executed from a computer running macOS.

The following is a list of prerequisites if you want to modify the source code
or run Fuji from source:

- macOS version 11 or later
- Python version 3.10 (tested with [3.10.11][python310])


[python]: https://python.org
[python310]: https://www.python.org/downloads/release/python-31011/
