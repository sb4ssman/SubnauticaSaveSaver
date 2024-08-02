# -*- coding: utf-8 -*-
"""
Created on Sat Jun 29 22:07:11 2024

@author: sb4ssman
"""
VERSION = "1.0"

# SK's Super Stealthy Subnautica Save Saver
# Runs in your system tray and copies your Subnautica saves to a separate folder appending timestamps to the name.
# Uses a Windows observer to trigger events so it's not chewing through CPU.
# The presence in the tray is so you know it's running, and to interact with the saves it manages.


"""
Usage and Development Notes:

1. Application Overview:
   - This application runs in the system tray and automatically backs up Subnautica and Subnautica: Below Zero save files.
   - It uses a watchdog observer to detect changes in the game's save directories and create backups with timestamps.
   - Manual saves and restorations can be initiated through the tray icon menu or the status window.

2. Key Components:
   - SkSubnauticaSaveSaver: Main application class that manages the overall functionality.
   - TrayHelper: Manages the system tray icon and its menu.
   - SaveHandler: Handles file system events for backing up save files.
   - Win32PystrayIcon: Custom pystray Icon class for Windows to support double-click events.

3. Event Handling:
   - The application uses an event queue system to handle updates to the UI.
   - Events are processed in the main thread to avoid threading issues with Tkinter.

4. File Operations:
   - Save backups are created using shutil.copy2 to preserve metadata.
   - A retry mechanism is implemented to handle potential file access issues.

5. User Interface:
   - The main interface is a system tray icon with a context menu.
   - A status window can be opened to view detailed information and perform actions.

6. Logging:
   - Comprehensive logging is implemented, writing to both a log file and the status window.
   - A global exception handler catches and logs uncaught exceptions.

7. Settings:
   - Application settings are stored in a JSON file for persistence across runs.
   - Save and backup folder paths can be configured through the status window.

8. Development Considerations:
   - The application is designed to work on Windows due to specific system tray implementations.
   - Tkinter is used for the GUI, which runs in the main thread.
   - Watchdog observers run in separate threads to monitor file system events.
   - Care should be taken when modifying the event handling system to avoid race conditions.

9. Known Limitations:
   - The application may occasionally fail to backup files if they are locked by the game process.
   - Large save files may cause a brief delay during backup operations.

10. Future Improvements:
    - Implement a more robust file locking mechanism for backups.
    - Add support for compressing older backups to save disk space.
    - Extend platform support to other operating systems.

11. Testing:
    - Thorough testing should be performed after any modifications, especially regarding file operations and UI updates.
    - Edge cases, such as rapid save operations or disk full scenarios, should be considered.

For more detailed information on specific components, refer to the inline documentation throughout the code.
"""

import argparse
import sys
import os
import datetime
import shutil
import time
import json
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import queue
import pystray
from pystray import MenuItem as item
from PIL import Image, ImageDraw
import threading
import logging
import string
import win32api
import win32gui
import win32con




# Set up logging
logging.basicConfig(filename='subnautica_save_saver.log', level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

# Global exception handling
def global_exception_handler(exctype, value, traceback):
    logging.error("Uncaught exception", exc_info=(exctype, value, traceback))

# This class to enable double-click to restore
class Win32PystrayIcon(pystray.Icon):
    WM_LBUTTONDBLCLK = 0x0203

    def __init__(self, *args, **kwargs):
        self.on_double_click = kwargs.pop('on_double_click', None)
        super().__init__(*args, **kwargs)

    def _on_notify(self, wparam, lparam):
        if lparam == self.WM_LBUTTONDBLCLK:
            if self.on_double_click:
                self.on_double_click(self, None)
        return super()._on_notify(wparam, lparam)

if sys.platform == 'win32':
    pystray.Icon = Win32PystrayIcon


# Tray helper - pystray doesn't like to redraw menus so the tray must be killed and restarted
###################


class TrayHelper:
    def __init__(self, manager):
        self.manager = manager
        self.icon = None

    def create_menu(self):
        menu_items = [
            item('Open Status Window', self.manager.show_status_window, default=True),
            item('Quit', self.manager.on_quit)
        ]
        
        if self.manager.subnautica_enabled:
            menu_items.insert(-1, item('Subnautica', pystray.Menu(
                item('Save Now', self.manager.on_save_now_subnautica),
                item('Restore', self.manager.on_restore_subnautica),
                item('Open Folders', self.manager.on_open_folders_subnautica)
            )))
        
        if self.manager.subnautica_zero_enabled:
            menu_items.insert(-1, item('Subnautica: Below Zero', pystray.Menu(
                item('Save Now', self.manager.on_save_now_subnautica_zero),
                item('Restore', self.manager.on_restore_subnautica_zero),
                item('Open Folders', self.manager.on_open_folders_subnautica_zero)
            )))
        
        return pystray.Menu(*menu_items)

    def create_tray_icon(self):
        menu = self.create_menu()
        icon_image = self.manager.create_image()
        
        icon_params = {
            'name': "sk_subnautica_save_saver",
            'icon': icon_image,
            'title': "SK's Super Stealthy\nSubnautica Save Saver",
            'menu': menu,
        }
        
        if sys.platform == 'win32':
            icon_params['on_double_click'] = self.manager.show_status_window
        
        self.icon = pystray.Icon(**icon_params)


    def recreate_tray_icon(self):
        self.stop_tray_icon()
        self.create_tray_icon()
        threading.Thread(target=self.run_tray_icon, daemon=True).start()

    def run_tray_icon(self):
        self.icon.run()

    def stop_tray_icon(self):
        if self.icon:
            self.icon.stop()

    def update_menu(self):
        if self.icon:
            self.icon.menu = self.create_menu()

    def update_icon(self):
        if self.icon:
            self.icon.icon = self.manager.create_image()



################################################
#                                              #
#   Sk's Super Stealthy Subautica Save Saver   #
#                                              #
################################################


class SkSubnauticaSaveSaver:
    def __init__(self, silent_mode=False):
        self.silent_mode = silent_mode
        self.app_directory = os.path.dirname(os.path.abspath(__file__))
        self.settings_file = os.path.join(self.app_directory, 'settings.json')
        self.saves_dir = os.path.join(self.app_directory, "Subnautica-SavedGames-Backup")
        self.saves_dir_bz = os.path.join(self.app_directory, "SubnauticaBelowZero-SavedGames-Backup")
        self.settings = None
        self.observer = None
        self.observer_bz = None
        self.status = False
        self.subnautica_enabled = False
        self.subnautica_zero_enabled = False
        self.root = tk.Tk()
        self.root.withdraw()
        self.status_window = None
        self.tray_helper = None
        self.event_queue = queue.Queue()
        self.root.after(100, self.process_events)


        for directory in [self.saves_dir, self.saves_dir_bz]:
            if not os.path.exists(directory):
                os.makedirs(directory)
                logging.info(f"Created saves directory: {directory}")

        self.style = ttk.Style()
        self.style.theme_use('xpnative')

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

    def update_icon_status(self):
        self.status = bool(self.observer or self.observer_bz)
        if self.tray_helper:
            self.tray_helper.update_icon()
            
    def process_events(self):
        try:
            while True:
                event = self.event_queue.get_nowait()
                self.handle_event(event)
        except queue.Empty:
            pass
        finally:
            self.root.after(100, self.process_events)

    def update_save_info(self, game_name):
        self.update_current_save_info(game_name)
        if hasattr(self, f'{game_name.lower()}_tree'):
            tree = getattr(self, f'{game_name.lower()}_tree')
            self.populate_restore_treeview(tree, game_name)

    def handle_event(self, event):
        event_type, message = event
        if event_type == 'log':
            self.update_log(message)
        elif event_type == 'save':
            self.update_save_info(message)

    def update_log(self, message):
        if hasattr(self, 'log_text') and self.log_text.winfo_exists():
            self.log_text.insert(tk.END, message + '\n')
            self.log_text.see(tk.END)

    def run(self):
        try:
            self.start()
            # Start Tkinter event loop
            self.root.mainloop()
        except KeyboardInterrupt:
            self.on_quit(self.tray_helper.icon, None)
        except Exception as e:
            logging.error(f"Unexpected error in main loop: {str(e)}")
            if self.tray_helper.icon:
                self.tray_helper.icon.stop()
            raise


    def start(self):
        try:
            logging.info("Starting SkSubnauticaSaveSaver")
            self.settings = self.load_settings()
            self.tray_helper = TrayHelper(self)
            
            if not self.settings_are_valid():
                self.create_initial_tray_icon()
                self.show_first_run_warning()
                self.search_and_set_paths()
            
            self.verify_and_start_observer()
            self.tray_helper.create_tray_icon()
            
            threading.Thread(target=self.tray_helper.run_tray_icon, daemon=True).start()
            
            logging.info("Startup complete")
            if not self.silent_mode:
                self.create_status_window()
            self.root.withdraw()
            self.root.mainloop()
        except Exception as e:
            logging.error(f"Error during startup: {str(e)}")
            if self.tray_helper:
                self.tray_helper.stop_tray_icon()
            raise

    def show_first_run_warning(self):
        if not self.silent_mode or not self.settings_are_valid():
            messagebox.showinfo("Subnautica Save Saver", "Welcome! The application will now search for Subnautica save folders. Please wait...")
            
    def create_initial_tray_icon(self):
        self.tray_helper.create_tray_icon()
        threading.Thread(target=self.tray_helper.run_tray_icon, daemon=True).start()

    def create_tray_icon(self):
        self.icon = pystray.Icon("sk_subnautica_save_saver", self.create_image(), "SK's Super Stealthy\nSubnautica Save Saver", tuple(self.menu_items))

    def run_tray_icon(self):
        try:
            logging.info("Running tray icon")
            self.icon.run()
        except Exception as e:
            logging.error(f"Tray icon error: {str(e)}")
            messagebox.showerror("Error", f"An error occurred with the tray icon: {str(e)}")

    def update_tray_icon(self):
        if self.tray_helper:
            self.tray_helper.update_icon()
            self.tray_helper.update_menu()

    def cleanup(self):
        logging.info("Cleaning up observers")
        self.stop_observer('Subnautica')
        self.stop_observer('SubnauticaZero')
        logging.info("Cleanup complete")
        
    def on_quit(self, icon, item):
        logging.info("Quitting application")
        self.cleanup()
        if self.observer:
            self.observer.stop()
        if self.observer_bz:
            self.observer_bz.stop()
        if self.tray_helper:
            self.tray_helper.stop_tray_icon()
        self.root.quit()
        self.root.destroy()

    def update_menu_items(self):
        self.menu_items[0].enabled = self.subnautica_enabled
        self.menu_items[1].enabled = self.subnautica_enabled
        self.menu_items[2].enabled = self.subnautica_zero_enabled
        self.menu_items[3].enabled = self.subnautica_zero_enabled
        if self.icon:
            self.icon.update_menu()

    def settings_are_valid(self):
        return (self.settings.get('subnautica_save_folder') and os.path.exists(self.settings['subnautica_save_folder'])) or \
               (self.settings.get('subnautica_zero_save_folder') and os.path.exists(self.settings['subnautica_zero_save_folder']))

    def search_and_set_paths(self):
        self.settings['subnautica_save_folder'] = self.detect_save_path('Subnautica')
        self.settings['subnautica_zero_save_folder'] = self.detect_save_path('SubnauticaZero')
        self.save_settings()
        
        if self.settings['subnautica_save_folder'] or self.settings['subnautica_zero_save_folder']:
            messagebox.showinfo("Search Complete", "Subnautica save folders have been found and set.")
        else:
            messagebox.showwarning("Search Complete", "No Subnautica save folders were found. Please set them manually in the Settings.")



    def load_settings(self):
        default_settings = {
            'subnautica_save_folder': None,
            'subnautica_zero_save_folder': None,
            'target_folder': self.saves_dir,
            'target_folder_bz': self.saves_dir_bz
        }

        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, 'r') as f:
                    loaded_settings = json.load(f)
                for key in loaded_settings:
                    if loaded_settings[key]:
                        loaded_settings[key] = os.path.normpath(loaded_settings[key])
                return loaded_settings
            except (json.JSONDecodeError, FileNotFoundError) as e:
                logging.error(f"Error loading settings file: {str(e)}. Using default settings.")
        
        # If the file doesn't exist or there was an error, create it with default settings
        self.save_settings(default_settings)
        return default_settings

    def save_settings(self, settings=None):
        if settings is None:
            settings = self.settings
        try:
            with open(self.settings_file, 'w') as f:
                json.dump(settings, f, indent=4)
            logging.info("Settings saved successfully")
        except IOError as e:
            logging.error(f"Error saving settings file: {str(e)}")
            messagebox.showerror("Error", f"Failed to save settings: {str(e)}")

    def save_game_settings(self, game, folder, target):
        folder_key = 'subnautica_save_folder' if game == 'Subnautica' else 'subnautica_zero_save_folder'
        target_key = 'target_folder' if game == 'Subnautica' else 'target_folder_bz'
        
        old_folder = self.settings.get(folder_key)
        self.settings[folder_key] = folder
        self.settings[target_key] = target
        self.save_settings()
        
        if old_folder != folder:
            self.stop_observer(game)
        
        self.verify_and_start_observer()
        self.tray_helper.recreate_tray_icon()
        self.update_observer_status()
        messagebox.showinfo("Settings Saved", f"{game} settings have been saved and applied.")
        
    def detect_save_path(self, game_name):
        save_paths = self.find_subnautica_saves(game_name)
        if save_paths:
            if len(save_paths) == 1:
                logging.info(f"Detected {game_name} save path: {save_paths[0]}")
                return save_paths[0]
            else:
                logging.info(f"Multiple {game_name} save paths detected: {save_paths}")
                return self.prompt_user_for_path_selection(save_paths, game_name)
        logging.warning(f"No valid {game_name} save path detected")
        return self.prompt_manual_folder_selection(game_name)


    def find_subnautica_saves(self, game_name):
        potential_paths = []
        default_paths = []

        if game_name == "Subnautica":
            default_paths = [
                # os.path.expandvars(r"%AppData%\..\LocalLow\Unknown Worlds\Subnautica\Subnautica\SavedGames"),
                r"C:\Program Files\Steam\steamapps\common\Subnautica\SNAppData\SavedGames",
                r"C:\Program Files (x86)\Steam\steamapps\common\Subnautica\SNAppData\SavedGames"
            ]
        elif game_name == "SubnauticaZero":
            default_paths = [
                # os.path.expandvars(r"%AppData%\..\LocalLow\Unknown Worlds\SubnauticaZero\SubnauticaZero\SavedGames"),
                r"C:\Program Files\Steam\steamapps\common\SubnauticaZero\SNAppData\SavedGames",
                r"C:\Program Files (x86)\Steam\steamapps\common\SubnauticaZero\SNAppData\SavedGames"
            ]

        potential_paths.extend(default_paths)

        drives = [f"{d}:\\" for d in string.ascii_uppercase if os.path.exists(f"{d}:")]

        for drive in drives:
            for root, dirs, files in os.walk(drive):
                if any(game_dir in root.lower() for game_dir in ["games", "steam"]):
                    subnautica_path = os.path.join(root, game_name)
                    if os.path.exists(subnautica_path):
                        saved_games_path = os.path.join(subnautica_path, "SNAppData", "SavedGames")
                        if os.path.exists(saved_games_path):
                            potential_paths.append(saved_games_path)

                if root.count(os.sep) - drive.count(os.sep) > 5:
                    dirs[:] = []

        valid_paths = [path for path in potential_paths if os.path.exists(path)]
        return valid_paths


    def prompt_user_for_path_selection(self, paths, game_name):
        root = tk.Tk()
        root.withdraw()
        result = messagebox.askquestion("Multiple Save Paths", 
                                        f"Multiple {game_name} save paths were found. Would you like to choose one?")
        if result == 'yes':
            choice = filedialog.askdirectory(title=f"Select {game_name} Save Folder", 
                                             initialdir=os.path.dirname(paths[0]))
            if choice:
                return choice
        return paths[0]

    def prompt_manual_folder_selection(self, game_name):
        root = tk.Tk()
        root.withdraw()
        messagebox.showinfo("Save Folder Not Found", 
                            f"The {game_name} save folder couldn't be automatically detected. "
                            "Please select it manually in the next dialog.")
        folder_path = filedialog.askdirectory(title=f"Select {game_name} Save Folder")
        if folder_path:
            return os.path.normpath(folder_path)
        return None

    def verify_path(self, key):
        path = self.settings.get(key)
        return path is not None and os.path.exists(path)

    def verify_and_start_observer(self):
        subnautica_enabled = self.verify_path('subnautica_save_folder')
        subnautica_zero_enabled = self.verify_path('subnautica_zero_save_folder')

        if subnautica_enabled:
            if not self.observer:
                self.start_observer('Subnautica')
        else:
            self.stop_observer('Subnautica')

        if subnautica_zero_enabled:
            if not self.observer_bz:
                self.start_observer('SubnauticaZero')
        else:
            self.stop_observer('SubnauticaZero')

        self.subnautica_enabled = subnautica_enabled
        self.subnautica_zero_enabled = subnautica_zero_enabled

        self.update_observer_status()
        self.update_tray_icon()

    def stop_observer(self, game):
        if game == 'Subnautica' and self.observer:
            self.observer.stop()
            self.observer.join()
            self.observer = None
            logging.info("Stopped Subnautica observer")
        elif game == 'SubnauticaZero' and self.observer_bz:
            self.observer_bz.stop()
            self.observer_bz.join()
            self.observer_bz = None
            logging.info("Stopped Subnautica: Below Zero observer")

    def update_observer_status(self):
        subnautica_status = 'Active' if self.observer else 'Inactive'
        subnautica_zero_status = 'Active' if self.observer_bz else 'Inactive'
        
        if hasattr(self, 'subnautica_observer_label'):
            self.subnautica_observer_label.config(text=f"Observer: {subnautica_status}")
        if hasattr(self, 'subnautica_zero_observer_label'):
            self.subnautica_zero_observer_label.config(text=f"Observer: {subnautica_zero_status}")



    def start_observer(self, game_name):
        folder_key = 'subnautica_save_folder' if game_name == 'Subnautica' else 'subnautica_zero_save_folder'
        target_key = 'target_folder' if game_name == 'Subnautica' else 'target_folder_bz'
        
        observer = Observer()
        event_handler = SaveHandler(self, self.settings[folder_key], self.settings[target_key], game_name)
        
        for dirpath, dirnames, filenames in os.walk(self.settings[folder_key]):
            observer.schedule(event_handler, dirpath, recursive=False)
        
        observer.start()
        
        if game_name == 'Subnautica':
            self.observer = observer
        else:
            self.observer_bz = observer

        self.update_icon_status()

    def start_watching_directory(self, directory):
        for observer in [self.observer, self.observer_bz]:
            if observer and os.path.commonpath([directory, observer.schedule._directory]) == observer.schedule._directory:
                event_handler = observer.schedule._handlers[0]
                observer.schedule(event_handler, directory, recursive=False)
                logging.info(f"Started watching new directory: {directory}")
                break


    def save_now(self, game_name):
        logging.info(f"Manual save initiated for {game_name}")
        folder_key = 'subnautica_save_folder' if game_name == 'Subnautica' else 'subnautica_zero_save_folder'
        target_key = 'target_folder' if game_name == 'Subnautica' else 'target_folder_bz'
        source_folder = self.settings[folder_key]
        target_folder = self.settings[target_key]

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        saved_slots = []
        for root, dirs, files in os.walk(source_folder):
            for dir in dirs:
                if dir.startswith("slot"):
                    slot_path = os.path.join(root, dir)
                    self.backup_slot(slot_path, source_folder, target_folder, timestamp)
                    saved_slots.append(dir)

        logging.info(f"Manual save completed for {game_name}. Saved slots: {', '.join(saved_slots)}")

        # Update the treeview
        tree = getattr(self, f"{game_name.lower().replace(' ', '_')}_tree", None)
        if tree:
            self.populate_restore_treeview(tree, game_name)
        
        self.update_backup_size()
        self.update_current_save_info(game_name)
        
        messagebox.showinfo("Backup Complete", f"{game_name} save files have been backed up.")

        # Add event to queue for updating log in status window
        if hasattr(self, 'event_queue'):
            self.event_queue.put(('log', f"Manual save completed for {game_name}. Saved slots: {', '.join(saved_slots)}"))

    def restore_save(self, game, save_file):
        logging.info(f"Restore initiated for {game}: {save_file}")
        source_folder = self.saves_dir if game == "Subnautica" else self.saves_dir_bz
        game_folder_key = 'subnautica_save_folder' if game == "Subnautica" else 'subnautica_zero_save_folder'
        
        try:
            restore_file = os.path.join(source_folder, save_file)
            original_name = save_file.split('_')[0]  # Get the original slot name
            destination_folder = self.settings[game_folder_key]
            shutil.copytree(restore_file, os.path.join(destination_folder, original_name), dirs_exist_ok=True)
            logging.info(f"Restored save: {original_name}")
            self.update_current_save_info(game)
            messagebox.showinfo("Restore Complete", f"{game} save file has been restored.")
        except Exception as e:
            logging.error(f"Error restoring save: {str(e)}")
            messagebox.showerror("Error", f"Failed to restore save: {str(e)}")

    def get_latest_slot(self, folder):
        slots = [d for d in os.listdir(folder) if d.startswith("slot")]
        if not slots:
            return None
        return max(slots, key=lambda x: os.path.getmtime(os.path.join(folder, x)))


    def on_double_click_restore(self, event):
        tree = event.widget
        item = tree.selection()[0]
        game, save_file, _ = tree.item(item, "values")
        
        if messagebox.askyesno("Confirm Restore", f"Are you sure you want to restore this save?\n{game}: {save_file}"):
            self.restore_save(game, save_file)
            
    def on_save_now_subnautica(self, icon, item):
        self.root.after(0, lambda: self.save_now('Subnautica'))

    def on_save_now_subnautica_zero(self, icon, item):
        self.root.after(0, lambda: self.save_now('SubnauticaZero'))

    def on_open_folders_subnautica(self, icon, item):
        self.root.after(0, lambda: self.open_folders('Subnautica'))

    def on_open_folders_subnautica_zero(self, icon, item):
        self.root.after(0, lambda: self.open_folders('SubnauticaZero'))

    def open_folders(self, game_name):
        folder_key = 'subnautica_save_folder' if game_name == 'Subnautica' else 'subnautica_zero_save_folder'
        target_key = 'target_folder' if game_name == 'Subnautica' else 'target_folder_bz'
        
        os.startfile(self.settings[folder_key])
        os.startfile(self.settings[target_key])

    def on_restore_from_list(self, icon, item):
        """Open the restore window to select a save to restore."""
        self.open_restore_window()

    def on_restore_subnautica(self, icon, item):
        self.root.after(0, lambda: self.open_restore_window('Subnautica'))

    def on_restore_subnautica_zero(self, icon, item):
        self.root.after(0, lambda: self.open_restore_window('SubnauticaZero'))

    def on_settings(self, icon, item):
        # Ensure we're on the main thread
        self.root.after(0, self.open_settings_window)
    
    def on_about(self, icon, item):
        # Ensure we're on the main thread
        self.root.after(0, self.show_about_dialog)

    def show_status_window(self):
        if self.status_window is None or not self.status_window.winfo_exists():
            self.create_status_window()
        self.status_window.deiconify()
        self.status_window.lift()

    def hide_status_window(self):
        if self.status_window:
            self.status_window.withdraw()

    def on_quit(self, icon, item):
        logging.info("Quitting application")
        if self.observer:
            self.observer.stop()
        if self.observer_bz:
            self.observer_bz.stop()
        if self.tray_helper:
            self.tray_helper.stop_tray_icon()
        self.root.quit()
        self.root.destroy()

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

    def show_about_dialog(self):
        about_text = f"""
SK's Super Stealthy Subnautica Save Saver
Version {VERSION}

Because Subnautica does not save the saves enough.

Status:
Subnautica Save Folder: {'Connected' if self.subnautica_enabled else 'Not Found'}
Subnautica Below Zero Save Folder: {'Connected' if self.subnautica_zero_enabled else 'Not Found'}
Observer: {'Active' if self.observer or self.observer_bz else 'Inactive'}

Set the Subnautica Save Folder and the backup directory in the settings.

SK's Saver leaves a callback in the system to be notified of
changes to player.log, and copies it when Subnautica saves it.
"""
        messagebox.showinfo("About", about_text)




    def update_backup_size(self):
        total_size = self.get_folder_size(self.saves_dir) + self.get_folder_size(self.saves_dir_bz)
        size_str = self.format_size(total_size)
        self.backup_size_label.config(text=f"Backup Cache Size: {size_str}")

    def get_folder_size(self, folder):
        total_size = 0
        for dirpath, dirnames, filenames in os.walk(folder):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                total_size += os.path.getsize(fp)
        return total_size

    def format_size(self, size):
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024.0:
                return f"{size:.2f} {unit}"
            size /= 1024.0
            

    def update_current_save_info(self, game_name):
        game_folder_key = 'subnautica_save_folder' if game_name == 'Subnautica' else 'subnautica_zero_save_folder'
        current_save_folder = self.settings[game_folder_key]
        current_slot = self.get_latest_slot(current_save_folder)

        current_file_frame = getattr(self, f"{game_name.lower().replace(' ', '_')}_current_file_frame", None)
        if current_file_frame:
            for child in current_file_frame.winfo_children():
                child.destroy()
            
            if current_slot:
                current_slot_path = os.path.join(current_save_folder, current_slot)
                mod_time = os.path.getmtime(current_slot_path)
                mod_time_str = datetime.datetime.fromtimestamp(mod_time).strftime('%Y-%m-%d %H:%M:%S')
                ttk.Label(current_file_frame, text=f"Current: {current_slot} ({mod_time_str})").pack(side=tk.RIGHT)
            else:
                ttk.Label(current_file_frame, text="No current save file found.").pack(side=tk.RIGHT)

    # Update the create_current_save_info method to store the frame
    def create_current_save_info(self, parent, game):
        game_folder_key = 'subnautica_save_folder' if game == 'Subnautica' else 'subnautica_zero_save_folder'
        current_save_folder = self.settings[game_folder_key]
        current_slot = self.get_latest_slot(current_save_folder)

        current_file_frame = ttk.Frame(parent)
        current_file_frame.pack(side=tk.RIGHT)

        # Store the frame for later updates
        setattr(self, f"{game.lower().replace(' ', '_')}_current_file_frame", current_file_frame)

        if current_slot:
            current_slot_path = os.path.join(current_save_folder, current_slot)
            mod_time = os.path.getmtime(current_slot_path)
            mod_time_str = datetime.datetime.fromtimestamp(mod_time).strftime('%Y-%m-%d %H:%M:%S')
            ttk.Label(current_file_frame, text=f"Current: {current_slot} ({mod_time_str})").pack(side=tk.RIGHT)
        else:
            ttk.Label(current_file_frame, text="No current save file found.").pack(side=tk.RIGHT)

    def create_restore_treeview(self, parent, game, row, column):
        columns = ("file", "date")
        tree = ttk.Treeview(parent, columns=columns, show="headings")
        tree.heading("file", text="File", anchor="center")
        tree.heading("date", text="Date and Time", anchor="center")
        tree.column("file", width=200, anchor="center")
        tree.column("date", width=200, anchor="center")
        tree.grid(row=row, column=column, sticky="nsew", padx=(0, 5))

        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=tree.yview)
        scrollbar.grid(row=row, column=column+1, sticky="ns")
        tree.configure(yscrollcommand=scrollbar.set)

        self.populate_restore_treeview(tree, game)
        tree.bind("<Double-1>", self.on_double_click_restore)

        setattr(self, f"{game.lower()}_tree", tree)

    def populate_restore_treeview(self, tree, game):
        tree.delete(*tree.get_children())
        folder = self.saves_dir if game == 'Subnautica' else self.saves_dir_bz
        save_files = []
        for save_file in os.listdir(folder):
            if save_file.startswith("slot"):
                file_path = os.path.join(folder, save_file)
                mod_time = os.path.getmtime(file_path)
                save_files.append((save_file, mod_time))
        
        # Sort save files by modification time (most recent first)
        save_files.sort(key=lambda x: x[1], reverse=True)
        
        for save_file, mod_time in save_files:
            date_str = datetime.datetime.fromtimestamp(mod_time).strftime('%Y-%m-%d %H:%M:%S')
            tree.insert("", "end", values=(save_file, date_str))

    def restore_selected(self, game):
        tree = getattr(self, f"{game.lower()}_tree")
        selection = tree.selection()
        if selection:
            item = selection[0]
            save_file = tree.item(item, "values")[0]
            if messagebox.askyesno("Confirm Restore", f"Are you sure you want to restore this save?\n{game}: {save_file}"):
                self.restore_save(game, save_file)
        else:
            messagebox.showinfo("No Selection", "Please select a save file to restore.")

    # Update these methods in the SkSubnauticaSaveSaver class
    def show_status_window(self):
        if self.status_window is None or not self.status_window.winfo_exists():
            self.create_status_window()
        self.status_window.deiconify()
        self.status_window.lift()

    def hide_status_window(self):
        if self.status_window:
            self.status_window.withdraw()



    def create_status_window(self):
        if self.status_window is not None and self.status_window.winfo_exists():
            self.status_window.lift()
            return

        self.status_window = tk.Toplevel(self.root)
        self.status_window.title("SK's Super Stealthy Subnautica Save Saver Status")
        self.status_window.geometry("800x600")
        self.status_window.protocol("WM_DELETE_WINDOW", self.hide_status_window)

        # Configure grid
        self.status_window.grid_columnconfigure(0, weight=1)
        self.status_window.grid_columnconfigure(1, weight=1)
        self.status_window.grid_rowconfigure(2, weight=1)  # Make the restore/log row expandable

        # Row 0: About and Status
        about_frame = ttk.LabelFrame(self.status_window, text="About")
        about_frame.grid(row=0, column=0, padx=5, pady=(5, 2), sticky="nsew")
        
        status_frame = ttk.LabelFrame(self.status_window, text="Status")
        status_frame.grid(row=0, column=1, padx=5, pady=(5, 2), sticky="nsew")

        self.populate_about_frame(about_frame)
        self.populate_status_frame(status_frame)

        # Row 1: Subnautica and Subnautica Below Zero settings
        subnautica_frame = ttk.LabelFrame(self.status_window, text="Subnautica")
        subnautica_frame.grid(row=1, column=0, padx=5, pady=2, sticky="nsew")

        subnautica_zero_frame = ttk.LabelFrame(self.status_window, text="Subnautica Below Zero")
        subnautica_zero_frame.grid(row=1, column=1, padx=5, pady=2, sticky="nsew")

        self.create_game_settings(subnautica_frame, 'Subnautica')
        self.create_game_settings(subnautica_zero_frame, 'SubnauticaZero')

        # Row 2: Restore and Log
        paned_window = ttk.PanedWindow(self.status_window, orient=tk.VERTICAL)
        paned_window.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=5, pady=2)

        restore_frame = ttk.Frame(paned_window)
        log_frame = ttk.LabelFrame(paned_window, text="Log")

        paned_window.add(restore_frame, weight=3)
        paned_window.add(log_frame, weight=1)

        # Configure restore_frame
        restore_frame.grid_columnconfigure(0, weight=1)
        restore_frame.grid_columnconfigure(1, weight=1)
        restore_frame.grid_rowconfigure(0, weight=1)

        self.create_restore_section(restore_frame, 'Subnautica', 0, 0)
        self.create_restore_section(restore_frame, 'SubnauticaZero', 0, 1)

        self.create_log_section(log_frame)

    def populate_about_frame(self, frame):
        ttk.Label(frame, text=f"Version: {VERSION}").pack(anchor="w")
        ttk.Label(frame, text="SK's Super Stealthy Subnautica Save Saver").pack(anchor="w")
        ttk.Label(frame, text="Because Subnautica does not save the saves enough.").pack(anchor="w")

    def populate_status_frame(self, frame):
        ttk.Label(frame, text=f"Subnautica: {'Connected' if self.subnautica_enabled else 'Not Found'}").pack(anchor="w")
        ttk.Label(frame, text=f"Subnautica Below Zero: {'Connected' if self.subnautica_zero_enabled else 'Not Found'}").pack(anchor="w")
        self.backup_size_label = ttk.Label(frame, text="")
        self.backup_size_label.pack(anchor="w")
        self.update_backup_size()

    def create_game_settings(self, parent, game):
        parent.columnconfigure(1, weight=1)
        folder_key = 'subnautica_save_folder' if game == 'Subnautica' else 'subnautica_zero_save_folder'
        target_key = 'target_folder' if game == 'Subnautica' else 'target_folder_bz'

        folder_var = tk.StringVar(value=self.settings.get(folder_key, ''))
        target_var = tk.StringVar(value=self.settings.get(target_key, ''))

        ttk.Label(parent, text="Save Folder:").grid(row=0, column=0, sticky="w")
        folder_entry = ttk.Entry(parent, textvariable=folder_var)
        folder_entry.grid(row=0, column=1, sticky="ew")
        ttk.Button(parent, text="Browse", width=7, command=lambda: self.browse_folder(folder_var, folder_entry)).grid(row=0, column=2)
        ttk.Button(parent, text="Open", width=5, command=lambda: os.startfile(folder_var.get())).grid(row=0, column=3)

        ttk.Label(parent, text="Backup Folder:").grid(row=1, column=0, sticky="w")
        target_entry = ttk.Entry(parent, textvariable=target_var)
        target_entry.grid(row=1, column=1, sticky="ew")
        ttk.Button(parent, text="Browse", width=7, command=lambda: self.browse_folder(target_var, target_entry)).grid(row=1, column=2)
        ttk.Button(parent, text="Open", width=5, command=lambda: os.startfile(target_var.get())).grid(row=1, column=3)

        button_frame = ttk.Frame(parent)
        button_frame.grid(row=2, column=0, columnspan=4, sticky="w")

        observer_status = 'Active' if (game == 'Subnautica' and self.observer) or (game == 'SubnauticaZero' and self.observer_bz) else 'Inactive'
        observer_label = ttk.Label(button_frame, text=f"Observer: {observer_status}")
        observer_label.pack(side=tk.LEFT)

        ttk.Button(button_frame, text="Save Settings", command=lambda: self.save_game_settings(game, folder_var.get(), target_var.get())).pack(side=tk.LEFT, padx=(0, 5))

        if game == 'Subnautica':
            self.subnautica_observer_label = observer_label
        else:
            self.subnautica_zero_observer_label = observer_label

    def browse_folder(self, var, entry):
        current_path = entry.get()
        initial_dir = current_path if os.path.exists(current_path) else os.path.expanduser("~")
        folder = filedialog.askdirectory(initialdir=initial_dir)
        if folder:
            var.set(folder)

    def create_restore_section(self, parent, game, row, column):
        frame = ttk.Frame(parent)
        frame.grid(row=row, column=column, sticky="nsew", padx=5, pady=5)
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(1, weight=1)

        header_frame = ttk.Frame(frame)
        header_frame.grid(row=0, column=0, sticky="ew")

        ttk.Label(header_frame, text=game).pack(side=tk.LEFT)
        self.create_current_save_info(header_frame, game)
        
        tree_frame = ttk.Frame(frame)
        tree_frame.grid(row=1, column=0, sticky="nsew")
        tree_frame.grid_columnconfigure(0, weight=1)
        tree_frame.grid_rowconfigure(0, weight=1)

        self.create_restore_treeview(tree_frame, game, row=0, column=0)
        
        button_frame = ttk.Frame(frame)
        button_frame.grid(row=2, column=0, sticky="w")
        ttk.Button(button_frame, text="Save Now", command=lambda: self.save_now(game)).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(button_frame, text="Restore", command=lambda: self.restore_selected(game)).pack(side=tk.LEFT)


    def create_log_section(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(0, weight=1)

        self.log_text = tk.Text(parent, wrap="word", height=10)
        self.log_text.grid(row=0, column=0, sticky="nsew", padx=(0, 5), pady=(0, 5))
        
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=self.log_text.yview)
        scrollbar.grid(row=0, column=1, sticky="ns", pady=(0, 5))
        self.log_text.config(yscrollcommand=scrollbar.set)

        # Load initial log content
        log_file_path = 'subnautica_save_saver.log'
        if os.path.exists(log_file_path):
            with open(log_file_path, 'r') as log_file:
                log_content = log_file.read()
                self.log_text.insert(tk.END, log_content)
        else:
            self.log_text.insert(tk.END, "Log file not found.")

        self.log_text.see(tk.END)
    

        ####################
        #



class SaveHandler(FileSystemEventHandler):
    def __init__(self, manager, source_folder, target_folder, game_name):
        self.manager = manager
        self.source_folder = source_folder
        self.target_folder = target_folder
        self.game_name = game_name

    def on_modified(self, event):
        if event.is_directory:
            return
        self.backup_save(event.src_path)

    def on_created(self, event):
        if event.is_directory:
            self.manager.event_queue.put(('log', f"New directory created and being watched: {event.src_path}"))
            self.manager.start_watching_directory(event.src_path)
        else:
            self.backup_save(event.src_path)

    def backup_save(self, src_path):
        rel_path = os.path.relpath(src_path, self.source_folder)
        dir_name, file_name = os.path.split(rel_path)
        if dir_name.startswith("slot"):
            dest_path = os.path.join(self.target_folder, rel_path)
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            
            max_attempts = 5
            for attempt in range(max_attempts):
                try:
                    shutil.copy2(src_path, dest_path)
                    log_message = f"Watchdog triggered backup: {src_path} to {dest_path}"
                    self.manager.event_queue.put(('log', log_message))
                    self.manager.event_queue.put(('save', self.game_name))
                    logging.info(log_message)
                    break
                except PermissionError:
                    if attempt < max_attempts - 1:
                        time.sleep(0.5)  # Wait for 0.5 seconds before retrying
                    else:
                        error_message = f"Failed to backup {src_path} after {max_attempts} attempts"
                        self.manager.event_queue.put(('log', error_message))
                        logging.error(error_message)

    def on_deleted(self, event):
        if not event.is_directory:
            rel_path = os.path.relpath(event.src_path, self.source_folder)
            dest_path = os.path.join(self.target_folder, rel_path)
            if os.path.exists(dest_path):
                try:
                    os.remove(dest_path)
                    log_message = f"Deleted backup file: {dest_path}"
                    self.manager.event_queue.put(('log', log_message))
                    logging.info(log_message)
                except Exception as e:
                    error_message = f"Failed to delete backup file {dest_path}: {str(e)}"
                    self.manager.event_queue.put(('log', error_message))
                    logging.error(error_message)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Subnautica Save Saver")
    parser.add_argument("--silent", action="store_true", help="Run in silent mode without showing startup messages")
    args = parser.parse_args()

    manager = SkSubnauticaSaveSaver(silent_mode=args.silent)
    try:
        manager.start()
    except Exception as e:
        logging.error(f"Fatal error: {str(e)}")
        if not args.silent:
            messagebox.showerror("Fatal Error", f"A fatal error occurred: {str(e)}\nPlease check the log file for details.")
        sys.exit(1)