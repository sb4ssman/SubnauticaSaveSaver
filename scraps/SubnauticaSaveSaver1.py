# -*- coding: utf-8 -*-
"""
Created on Sat Jun 29 22:07:11 2024

@author: sb4ssman

SK's Super Stealthy Subnautica Save Saver
Runs in your system tray and copies your Subnautica saves to a separate folder appending timestamps to the name.
Uses a Windows observer to trigger events so it's not chewing through CPU.
The presence in the tray is so you know it's running, and to interact with the saves it manages.
"""

import os
import shutil
import time
import json
import tkinter as tk
from tkinter import filedialog, messagebox
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import pystray
from pystray import MenuItem as item
from PIL import Image, ImageDraw
import logging
import winreg
import string
from pathlib import Path


VERSION = "1.0"

# Set up logging
logging.basicConfig(filename='subnautica_save_saver.log', level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

class SaveManager:
    def __init__(self):
        # Set up directory paths
        self.app_directory = os.path.dirname(os.path.abspath(__file__))
        self.settings_file = os.path.join(self.app_directory, 'settings.json')
        self.saves_dir = os.path.join(self.app_directory, "Saves")
        
        # Load settings and initialize variables
        self.settings = self.load_settings()
        self.observer = None
        self.icon = None
        self.status = False

        # Create saves directory if it doesn't exist
        if not os.path.exists(self.saves_dir):
            os.makedirs(self.saves_dir)
            logging.info(f"Created saves directory: {self.saves_dir}")
        
        if not self.settings['game_save_folder']:
            self.prompt_for_manual_path_setting()


    def find_subnautica_saves(self):
        potential_paths = []

        # Check default locations
        default_paths = [
            os.path.expandvars(r"%AppData%\..\LocalLow\Unknown Worlds\Subnautica\Subnautica\SavedGames"),
            r"C:\Program Files\Steam\steamapps\common\Subnautica\SNAppData\SavedGames",
            r"C:\Program Files (x86)\Steam\steamapps\common\Subnautica\SNAppData\SavedGames"
        ]
        potential_paths.extend(default_paths)

        # Enumerate all drives
        drives = [f"{d}:\\" for d in string.ascii_uppercase if os.path.exists(f"{d}:")]

        for drive in drives:
            for root, dirs, files in os.walk(drive):
                # Check if the current directory contains "Games" or "games"
                if any(game_dir in root.lower() for game_dir in ["games", "steam"]):
                    subnautica_path = os.path.join(root, "Subnautica")
                    if os.path.exists(subnautica_path):
                        saved_games_path = os.path.join(subnautica_path, "SNAppData", "SavedGames")
                        if os.path.exists(saved_games_path):
                            potential_paths.append(saved_games_path)

                # Limit depth to avoid excessive searching
                if root.count(os.sep) - drive.count(os.sep) > 5:
                    dirs[:] = []  # Don't recurse any deeper

        # Check if paths exist and return valid ones
        valid_paths = [path for path in potential_paths if os.path.exists(path)]
        return valid_paths

    def detect_save_path(self):
        """Detect the Subnautica save path for different installations."""
        save_paths = self.find_subnautica_saves()
        if save_paths:
            if len(save_paths) == 1:
                logging.info(f"Detected Subnautica save path: {save_paths[0]}")
                return save_paths[0]
            else:
                logging.info(f"Multiple Subnautica save paths detected: {save_paths}")
                # Here you might want to prompt the user to choose
                # For now, we'll return the first one
                return save_paths[0]
        logging.warning("No valid Subnautica save path detected")
        return None

    def load_settings(self):
        """Load settings from file or create default settings."""
        default_settings = {
            'game_save_folder': self.detect_save_path(),
            'target_folder': self.saves_dir
        }

        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, 'r') as f:
                    loaded_settings = json.load(f)
                    # Handle case where game_save_folder is None or doesn't exist
                    if not loaded_settings.get('game_save_folder') or not os.path.exists(loaded_settings.get('game_save_folder')):
                        loaded_settings['game_save_folder'] = self.detect_save_path()
                    
                    # Normalize paths
                    loaded_settings['game_save_folder'] = os.path.normpath(loaded_settings['game_save_folder']) if loaded_settings['game_save_folder'] else None
                    loaded_settings['target_folder'] = os.path.normpath(loaded_settings.get('target_folder', default_settings['target_folder']))
                    logging.info("Settings loaded and normalized successfully")
                    return loaded_settings
            except json.JSONDecodeError:
                logging.error("Error decoding settings file. Using default settings.")
                return default_settings
        else:
            logging.info("Settings file not found. Using default settings.")
            return default_settings
            
    def prompt_for_manual_path_setting(self):
        """Prompt the user to manually set the game save folder path."""
        messagebox.showinfo("Game Save Folder Not Found", 
                            "The Subnautica save folder couldn't be automatically detected. "
                            "Please select it manually in the next dialog.")
        folder_path = filedialog.askdirectory(title="Select Subnautica Save Folder")
        if folder_path:
            self.settings['game_save_folder'] = os.path.normpath(folder_path)
            self.save_settings()
            logging.info(f"Game save folder manually set to: {folder_path}")
        else:
            logging.warning("User cancelled manual game save folder selection")
            messagebox.showwarning("Warning", "No game save folder selected. Some features may not work correctly.")

    def save_settings(self):
        """Save current settings to file."""
        try:
            # Normalize paths before saving
            if self.settings['game_save_folder']:
                self.settings['game_save_folder'] = os.path.normpath(self.settings['game_save_folder'])
            self.settings['target_folder'] = os.path.normpath(self.settings['target_folder'])
            with open(self.settings_file, 'w') as f:
                json.dump(self.settings, f, indent=4)
            logging.info("Settings saved successfully")
        except IOError:
            logging.error("Error saving settings file")
            messagebox.showerror("Error", "Failed to save settings")

    def verify_paths(self):
        """Verify that both game save folder and target folder exist."""
        game_save_folder = self.settings.get('game_save_folder')
        target_folder = self.settings.get('target_folder')
        
        if game_save_folder is None or not os.path.exists(game_save_folder):
            logging.warning(f"Game save folder does not exist: {game_save_folder}")
            return False
        if target_folder is None or not os.path.exists(target_folder):
            logging.warning(f"Target folder does not exist: {target_folder}")
            return False
        return True

    def start(self):
        """Start the application."""
        self.verify_and_start_observer()
        self.create_tray_icon()
        self.icon.run()

    def verify_and_start_observer(self):
        """Verify paths and start the observer if valid."""
        if self.verify_paths():
            self.observer = Observer()
            event_handler = SaveHandler(self)
            self.observer.schedule(event_handler, self.settings['game_save_folder'], recursive=False)
            self.observer.start()
            self.status = True
            logging.info("Observer started successfully")
        else:
            self.status = False
            logging.warning("Paths are not set or invalid")
            messagebox.showinfo("Failure!", "Paths are not set or invalid.\nPlease set the paths using the Settings menu.")

    def create_tray_icon(self):
        """Create the system tray icon and menu."""
        menu = (
            item('Duplicate Save Now!', self.on_duplicate_save_now),
            item('Open both Folders...', self.on_open_folders),
            item('Restore from List...', self.on_restore_from_list),
            item('Settings...', self.on_settings),
            item('About...', self.on_about),
            item('Quit', self.on_quit)
        )
        self.icon = pystray.Icon("subnautica_save_manager", self.create_image(), "SK's Super Stealthy\nSubnautica Save Saver", menu)

    def create_image(self):
            """Create the tray icon image with status indicator."""
            width = 64
            height = 64
            image = Image.new('RGB', (width, height), (64, 224, 208))  # Turquoise blue color
            draw = ImageDraw.Draw(image)
            
            # Define the points for each segment of the 'S' with corrected coordinates
            segments = [
                [(49, 15), (19, 15), (19, 25), (49, 25)],  # Segment 1 (top horizontal bar)
                [(9, 25), (19, 25), (19, 35), (9, 35)],    # Segment 2 (top-left vertical bar)
                [(19, 35), (49, 35), (49, 45), (19, 45)],  # Segment 3 (middle horizontal bar)
                [(49, 45), (39, 45), (39, 55), (49, 55)],  # Segment 4 (bottom-right vertical bar)
                [(39, 55), (9, 55), (9, 65), (39, 65)],    # Segment 5 (bottom horizontal bar)
            ]
            
            # Draw each segment of the 'S' filled with purple color
            for segment in segments:
                draw.polygon(segment, fill=(128, 0, 128))
            
            # Add status indicator in the upper right corner
            indicator_color = (0, 255, 0) if self.status else (255, 0, 0)
            draw.rectangle([width-15, 0, width, 15], fill=indicator_color)
            
            return image

    def on_duplicate_save_now(self, icon, item):
        """Manually trigger a save duplication."""
        self.duplicate_latest_save()

    def on_open_folders(self, icon, item):
        """Open both the game save folder and the target folder."""
        try:
            os.startfile(self.settings['game_save_folder'])
            os.startfile(self.settings['target_folder'])
            logging.info("Opened both folders")
        except Exception as e:
            logging.error(f"Error opening folders: {str(e)}")
            messagebox.showerror("Error", f"Failed to open folders: {str(e)}")

    def on_restore_from_list(self, icon, item):
        """Open the restore window to select a save to restore."""
        self.open_restore_window()

    def on_settings(self, icon, item):
        """Open the settings window."""
        self.open_settings_window()

    def on_about(self, icon, item):
        """Display the About dialog with current status."""
        game_folder_status = "Connected" if os.path.exists(self.settings.get('game_save_folder', '')) else "Not Found"
        target_folder_status = "Connected" if os.path.exists(self.settings.get('target_folder', '')) else "Not Found"
        observer_status = "Active" if self.observer and self.observer.is_alive() else "Inactive"
        
        messagebox.showinfo(
            "About",
            f"""
            SK's Super Stealthy Subnautica Save Saver
            Version {VERSION}

            Because Subnautica does not save the saves enough.

            Status:
            Game Save Folder: {game_folder_status}
            Target Folder: {target_folder_status}
            Observer: {observer_status}

            Set the Subnautica Save Folder and the backup directory in the settings.

            SK's Saver leaves a callback in the system to be notified of
            changes to player.log, and copies it when Subnautica saves it.
            """
        )

    def on_quit(self, icon, item):
        """Quit the application."""
        if self.observer:
            self.observer.stop()
            self.observer.join()
        logging.info("Application shutting down")
        icon.stop()

    def duplicate_latest_save(self):
        """Duplicate the latest save file."""
        try:
            game_save_folder = self.settings['game_save_folder']
            target_folder = self.settings['target_folder']
            if not game_save_folder or not target_folder:
                raise ValueError("Game or Target folder(s) not found!")

            latest_save = max(
                (os.path.join(game_save_folder, f) for f in os.listdir(game_save_folder)),
                key=os.path.getctime
            )
            timestamp = time.strftime('%Y%m%d%H%M%S')
            new_save_path = os.path.join(target_folder, f"{os.path.basename(latest_save)}_{timestamp}")
            shutil.copy(latest_save, new_save_path)
            logging.info(f"Duplicated save: {new_save_path}")
        except Exception as e:
            logging.error(f"Error duplicating save: {str(e)}")
            messagebox.showerror("Error", f"Failed to duplicate save: {str(e)}")

    def open_settings_window(self):
        """Open the settings window to configure paths."""
        settings_window = tk.Toplevel()
        settings_window.title("Subnautica Save Saver Settings")
        
        tk.Label(settings_window, text="Game Save Folder:").pack(anchor="w")
        game_save_folder_var = tk.StringVar(value=self.settings['game_save_folder'])
        tk.Entry(settings_window, textvariable=game_save_folder_var, width=100).pack()
        tk.Button(settings_window, text="Browse", command=lambda: game_save_folder_var.set(filedialog.askdirectory())).pack()

        tk.Label(settings_window, text="Target Folder:").pack(anchor="w")
        target_folder_var = tk.StringVar(value=self.settings['target_folder'])
        tk.Entry(settings_window, textvariable=target_folder_var, width=100).pack()
        tk.Button(settings_window, text="Browse", command=lambda: target_folder_var.set(filedialog.askdirectory())).pack(pady=(0,5))

        def save_settings():
            self.settings['game_save_folder'] = os.path.normpath(game_save_folder_var.get())
            self.settings['target_folder'] = os.path.normpath(target_folder_var.get())
            self.save_settings()
            settings_window.destroy()
            self.verify_and_start_observer()
            self.icon.icon = self.create_image()

        tk.Button(settings_window, text="Save", command=save_settings).pack(pady=(0, 5))

    def open_restore_window(self):
        """Open the restore window to select a save to restore."""
        restore_window = tk.Toplevel()
        restore_window.title("Restore from List")

        save_listbox = tk.Listbox(restore_window, width=50)
        save_listbox.pack()
        
        for save_file in os.listdir(self.saves_dir):
            save_listbox.insert(tk.END, save_file)

        def restore_save():
            try:
                selected_save = save_listbox.get(save_listbox.curselection())
                restore_file = os.path.join(self.saves_dir, selected_save)
                original_name = '_'.join(selected_save.split('_')[:-1])
                shutil.copy(restore_file, os.path.join(self.settings['game_save_folder'], original_name))
                logging.info(f"Restored save: {original_name}")
                restore_window.destroy()
            except Exception as e:
                logging.error(f"Error restoring save: {str(e)}")
                messagebox.showerror("Error", f"Failed to restore save: {str(e)}")

        tk.Button(restore_window, text="Restore Selected to Live Game Folder", command=restore_save).pack()

class SaveHandler(FileSystemEventHandler):
    """Handler for file system events."""
    def __init__(self, manager):
        self.manager = manager

    def on_modified(self, event):
        """Handle file modification events."""
        if event.is_directory:
            return
        if self.manager.settings['game_save_folder'] in event.src_path:
            self.manager.duplicate_latest_save()

if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()
    manager = SaveManager()
    try:
        manager.start()
    except KeyboardInterrupt:
        manager.on_quit(manager.icon, None)
    except Exception as e:
        logging.error(f"Unexpected error: {str(e)}")
        messagebox.showerror("Error", f"An unexpected error occurred: {str(e)}")