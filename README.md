# SK's Super Stealthy Subnautica Save Saver

## Introduction
"SK's Super Stealthy Subnautica Save Saver" is a Python application designed to monitor and back up Subnautica save files automatically. This ensures that your progress is always safe, even if something goes wrong, and removes the tediousness of digging around in the folders and copying stuff yourself.

## Features
- **Automatic Backup**: Monitors the Subnautica save folder and automatically backs up your saves.
- **System Tray Integration**: Runs in the background with an icon in the system tray for easy access.
- **Customizable Folders**: Easily set the Subnautica save folder and the backup target folder.

## Installation

### Prerequisites
- Python 3.6 or later
- `pip` (Python package installer)

### Steps
1. Clone the repository:
    ```sh
    git clone https://github.com/yourusername/SubnauticaSaveSaver.git
    cd SubnauticaSaveSaver
    ```
2. Create and activate a virtual environment:
    ```sh
    python -m venv venv
    venv\Scripts\activate
    ```
3. Install the required packages:
    ```sh
    pip install -r requirements.txt
    ```

4. Run the application:
    ```sh
    python SubnauticaSaveSaver.py
    ```

## Usage

### Running on Startup

1. Create a batch file (`run_app.bat`) with the following content (included):

    ```batch
    @echo off

    rem Change directory to where your Python script is located
    cd /d "%USERPROFILE%\Documents\GitHub\SubnauticaSaveSaver"

    rem Ensure the log directory exists
    if not exist logs mkdir logs

    rem Run Python script in the background and redirect output to a log file
    start /B "" pythonw SubnauticaSaveSaver.py > logs\app.log 2>&1

    rem Exit the batch script without waiting for the Python script to finish
    exit /b
    ```

2. Place the batch file in your startup folder (or anywhere as a proxy to run the Saver):
    - Press `Win + R`, type `shell:startup`, and press Enter.
    - Copy the `run_app.bat` file into this folder.

### Configuring the Application

1. When you run the application for the first time, it will create a default settings file and backup directory.
2. Edit the settings file (`settings.json`) in the application directory to specify your Subnautica save folder and the target backup folder.

## Contribution

Feel free to fork this repository, create new features, fix bugs, or improve documentation. Pull requests are welcome.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
