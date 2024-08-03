# SK's Super Stealthy Subnautica Save Saver (SSSSSS)

## Overview

SSSSSS is a Python application designed to automatically backup save files for Subnautica and Subnautica: Below Zero. It runs quietly in the system tray, providing peace of mind for your underwater adventures.

## Features

- Automatic backup of save files when changes are detected
- Manual save and restore options
- Easy-to-use system tray interface
- Detailed status window for information and settings

## Installation

1. Ensure Python 3.6 or later is installed on your system.
2. Place `SubnauticaSaveSaver.py` and `autoSSSSSS.bat` in your desired location.
3. Run `autoSSSSSS.bat` to start the application silently in the background.

## Usage

- The application runs in the system tray. Right-click the icon for options.
- On first run, it will search for Subnautica save folders and set up necessary backup directories.
- Use the status window (accessible via the tray icon) to adjust settings and view backup information.

## File Management

- Backup folders are created in the same directory as the script.
- The application only modifies files within these backup folders and the game's save directories.
- A `settings.json` file is created in the application directory to store configuration.

## Logging

- A log file (`subnautica_save_saver.log`) is maintained in the application directory for troubleshooting.

## Note

Ensure the application has appropriate permissions to read from and write to the game save directories and its own directory.

## autoSSSSSS.bat

This batch file is included to run the application silently on startup. It:

1. Changes to the directory where the script is located.
2. Creates a 'logs' folder if it doesn't exist.
3. Runs the Python script in the background, redirecting output to a log file.

To use it for automatic startup:

1. Press `Win + R`, type `shell:startup`, and press Enter.
2. Create a shortcut to `autoSSSSSS.bat` in this folder.

This will ensure SSSSSS starts automatically when you log in to Windows.

## License

[MIT License](LICENSE)

## Contributing

Contributions, issues, and feature requests are welcome. Feel free to check [issues page](https://github.com/yourusername/SSSSSS/issues) if you want to contribute.

## Author

- **SK4Ssman** - [GitHub Profile](https://github.com/yourusername)

## Acknowledgments

- Thanks to the Subnautica community for inspiring this project.
- Special thanks to Sk for requesting it.