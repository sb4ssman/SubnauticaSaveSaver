# -*- coding: utf-8 -*-
"""
Created on Sat Jun 29 22:07:11 2024

@author: sb4ssman

SK's Super Stealthy Subnautica Save Saver
Runs in your system tray and copies your Subnautica saves to a separate folder appending timestamps to the name.
Uses a Windows observer to trigger events so it's not chewing through CPU.
The presence in the tray is so you know it's running, and to interact with the saves it manages.
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
import pystray
from pystray import MenuItem as item
from PIL import Image, ImageDraw
import threading
import logging
import winreg
import string
from pathlib import Path


VERSION = "1.0"

# Set up logging
logging.basicConfig(filename='subnautica_save_saver.log', level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

class TrayHelper:
    def __init__(self, manager):
        self.manager = manager
        self.icon = None

    def create_menu(self):
        subnautica_enabled = self.manager.verify_path('subnautica_save_folder')
        subnautica_zero_enabled = self.manager.verify_path('subnautica_zero_save_folder')

        return (
            item('Subnautica', pystray.Menu(
                item('Save Now', self.manager.on_save_now_subnautica, enabled=subnautica_enabled),
                item('Restore', self.manager.on_restore_subnautica, enabled=subnautica_enabled),
                item('Open Folders', self.manager.on_open_folders_subnautica, enabled=subnautica_enabled)
            )),
            item('Subnautica: Below Zero', pystray.Menu(
                item('Save Now', self.manager.on_save_now_subnautica_zero, enabled=subnautica_zero_enabled),
                item('Restore', self.manager.on_restore_subnautica_zero, enabled=subnautica_zero_enabled),
                item('Open Folders', self.manager.on_open_folders_subnautica_zero, enabled=subnautica_zero_enabled)
            )),
            item('Settings...', self.manager.on_settings),
            item('About...', self.manager.on_about),
            item('Quit', self.manager.on_quit)
        )

    def create_tray_icon(self):
        menu = self.create_menu()
        self.icon = pystray.Icon("sk_subnautica_save_saver", self.manager.create_image(), "SK's Super Stealthy\nSubnautica Save Saver", menu)

    def run_tray_icon(self):
        self.icon.run()

    def update_tray_icon(self):
        if self.icon:
            self.icon.icon = self.manager.create_image()
            self.icon.update_menu()

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
        self.tray_helper = None
        self.settings_window = None  # Initialize settings_window attribute

        for directory in [self.saves_dir, self.saves_dir_bz]:
            if not os.path.exists(directory):
                os.makedirs(directory)
                logging.info(f"Created saves directory: {directory}")

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

    def create_menu_items(self):
        self.menu_items = [
            item('Save Now - Subnautica', self.on_save_now_subnautica, enabled=False),
            item('Open Subnautica Folders', self.on_open_folders_subnautica, enabled=False),
            item('Save Now - Subnautica Below Zero', self.on_save_now_subnautica_zero, enabled=False),
            item('Open Subnautica Below Zero Folders', self.on_open_folders_subnautica_zero, enabled=False),
            item('Settings...', self.on_settings),
            item('About...', self.on_about),
            item('Quit', self.on_quit)
        ]

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
            self.tray_helper.create_tray_icon()
            threading.Thread(target=self.tray_helper.run_tray_icon, daemon=True).start()
            logging.info("Tray icon thread started")
            
            if not self.settings_are_valid():
                if not self.silent_mode:
                    messagebox.showinfo("Subnautica Save Saver", "Welcome! The application will now search for Subnautica save folders. Please wait...")
                self.search_and_set_paths()
            
            self.verify_and_start_observer()
            logging.info("Startup complete")
            self.root.mainloop()
        except Exception as e:
            logging.error(f"Error during startup: {str(e)}")
            if self.tray_helper and self.tray_helper.icon:
                self.tray_helper.icon.stop()
            raise

    def create_tray_icon(self):
        self.icon = pystray.Icon("sk_subnautica_save_saver", self.create_image(), "SK's Super Stealthy\nSubnautica Save Saver", tuple(self.menu_items))

    def run_tray_icon(self):
        try:
            logging.info("Running tray icon")
            self.icon.run()
        except Exception as e:
            logging.error(f"Tray icon error: {str(e)}")
            messagebox.showerror("Error", f"An error occurred with the tray icon: {str(e)}")

    def on_quit(self, icon, item):
        logging.info("Quitting application")
        if self.observer:
            self.observer.stop()
        if self.observer_bz:
            self.observer_bz.stop()
        if icon:
            icon.stop()
        self.root.quit()  # This will stop the Tkinter event loop
        self.root.destroy()  # This will destroy the root window

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
            except json.JSONDecodeError:
                logging.error("Error decoding settings file. Using default settings.")
        
        return default_settings

    def save_settings(self):
        try:
            with open(self.settings_file, 'w') as f:
                json.dump(self.settings, f, indent=4)
            logging.info("Settings saved successfully")
        except IOError:
            logging.error("Error saving settings file")
            messagebox.showerror("Error", "Failed to save settings")

        
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
                os.path.expandvars(r"%AppData%\..\LocalLow\Unknown Worlds\Subnautica\Subnautica\SavedGames"),
                r"C:\Program Files\Steam\steamapps\common\Subnautica\SNAppData\SavedGames",
                r"C:\Program Files (x86)\Steam\steamapps\common\Subnautica\SNAppData\SavedGames"
            ]
        elif game_name == "SubnauticaZero":
            default_paths = [
                os.path.expandvars(r"%AppData%\..\LocalLow\Unknown Worlds\SubnauticaZero\SubnauticaZero\SavedGames"),
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
        self.subnautica_enabled = self.verify_path('subnautica_save_folder')
        self.subnautica_zero_enabled = self.verify_path('subnautica_zero_save_folder')

        if self.subnautica_enabled:
            self.start_observer('Subnautica')
        if self.subnautica_zero_enabled:
            self.start_observer('SubnauticaZero')

        if self.subnautica_enabled or self.subnautica_zero_enabled:
            self.status = True
            logging.info("Observers started for available game folders")
            if not self.silent_mode:
                messagebox.showinfo("Success", "Monitoring started for available Subnautica save folders.")
        else:
            self.status = False
            logging.warning("No valid save folders found")
            if not self.silent_mode:
                messagebox.showinfo("Notice", "No valid Subnautica save folders found.\nUse the Settings menu to set paths.")

        self.tray_helper.update_tray_icon()

    def start_observer(self, game_name):
        folder_key = 'subnautica_save_folder' if game_name == 'Subnautica' else 'subnautica_zero_save_folder'
        target_key = 'target_folder' if game_name == 'Subnautica' else 'target_folder_bz'
        
        observer = Observer()
        event_handler = SaveHandler(self, self.settings[folder_key], self.settings[target_key])
        observer.schedule(event_handler, self.settings[folder_key], recursive=True)
        observer.start()
        
        if game_name == 'Subnautica':
            self.observer = observer
        else:
            self.observer_bz = observer

    def backup_slot(self, slot_path, source_folder, target_folder, timestamp):
        rel_path = os.path.relpath(slot_path, source_folder)
        dest_path = os.path.join(target_folder, f"{rel_path}_{timestamp}")
        
        shutil.copytree(slot_path, dest_path)
        logging.info(f"Backed up: {slot_path} to {dest_path}")

    def save_now(self, game_name):
        folder_key = 'subnautica_save_folder' if game_name == 'Subnautica' else 'subnautica_zero_save_folder'
        target_key = 'target_folder' if game_name == 'Subnautica' else 'target_folder_bz'
        source_folder = self.settings[folder_key]
        target_folder = self.settings[target_key]

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        for root, dirs, files in os.walk(source_folder):
            for dir in dirs:
                if dir.startswith("slot"):
                    slot_path = os.path.join(root, dir)
                    self.backup_slot(slot_path, source_folder, target_folder, timestamp)

        messagebox.showinfo("Backup Complete", f"{game_name} save files have been backed up.")

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


    def on_quit(self, icon, item):
        logging.info("Quitting application")
        if self.observer:
            self.observer.stop()
        if self.observer_bz:
            self.observer_bz.stop()
        if icon:
            icon.stop()
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

    def open_restore_window(self, game_name):
        restore_window = tk.Toplevel(self.root)
        restore_window.title(f"Restore {game_name} Save")
        restore_window.geometry("600x400")

        # Current file info
        current_file_frame = ttk.LabelFrame(restore_window, text="Current Save File")
        current_file_frame.pack(fill="x", padx=10, pady=10)

        game_folder_key = 'subnautica_save_folder' if game_name == 'Subnautica' else 'subnautica_zero_save_folder'
        current_save_folder = self.settings[game_folder_key]
        current_slot = self.get_latest_slot(current_save_folder)

        if current_slot:
            current_slot_path = os.path.join(current_save_folder, current_slot)
            mod_time = os.path.getmtime(current_slot_path)
            mod_time_str = datetime.datetime.fromtimestamp(mod_time).strftime('%Y-%m-%d %H:%M:%S')
            ttk.Label(current_file_frame, text=f"File: {current_slot}").pack(anchor="w")
            ttk.Label(current_file_frame, text=f"Last Modified: {mod_time_str}").pack(anchor="w")
            ttk.Button(current_file_frame, text="Save Now", command=lambda: self.save_now(game_name)).pack(anchor="e", padx=5)
        else:
            ttk.Label(current_file_frame, text="No current save file found.").pack(anchor="w")

        # Backup files list
        backup_frame = ttk.Frame(restore_window)
        backup_frame.pack(fill="both", expand=True, padx=10, pady=10)

        columns = ("file", "date")
        tree = ttk.Treeview(backup_frame, columns=columns, show="headings")
        tree.heading("file", text="File")
        tree.heading("date", text="Date and Time")
        tree.column("file", width=200)
        tree.column("date", width=200)
        tree.pack(side="left", fill="both", expand=True)

        scrollbar = ttk.Scrollbar(backup_frame, orient="vertical", command=tree.yview)
        scrollbar.pack(side="right", fill="y")
        tree.configure(yscrollcommand=scrollbar.set)

        backup_folder = self.saves_dir if game_name == 'Subnautica' else self.saves_dir_bz
        for save_file in os.listdir(backup_folder):
            if save_file.startswith("slot"):
                file_path = os.path.join(backup_folder, save_file)
                mod_time = os.path.getmtime(file_path)
                date_str = datetime.datetime.fromtimestamp(mod_time).strftime('%Y-%m-%d %H:%M:%S')
                tree.insert("", "end", values=(save_file, date_str))

        def restore_save():
            try:
                selected_item = tree.selection()[0]
                selected_save = tree.item(selected_item)['values'][0]
                restore_file = os.path.join(backup_folder, selected_save)
                original_name = selected_save.split('_')[0]  # Get the original slot name
                destination_folder = self.settings[game_folder_key]
                shutil.copytree(restore_file, os.path.join(destination_folder, original_name), dirs_exist_ok=True)
                logging.info(f"Restored save: {original_name}")
                restore_window.destroy()
                messagebox.showinfo("Restore Complete", f"{game_name} save file has been restored.")
            except Exception as e:
                logging.error(f"Error restoring save: {str(e)}")
                messagebox.showerror("Error", f"Failed to restore save: {str(e)}")

        button_frame = ttk.Frame(restore_window)
        button_frame.pack(fill="x", padx=10, pady=10)
        ttk.Button(button_frame, text="Restore Selected Save", command=restore_save).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Cancel", command=restore_window.destroy).pack(side=tk.RIGHT, padx=5)


    def get_latest_slot(self, folder):
        slots = [d for d in os.listdir(folder) if d.startswith("slot")]
        if not slots:
            return None
        return max(slots, key=lambda x: os.path.getmtime(os.path.join(folder, x)))

    def open_settings_window(self):
        if self.settings_window is not None and self.settings_window.winfo_exists():
            self.settings_window.lift()
            return

        self.settings_window = tk.Toplevel(self.root)
        self.settings_window.title("Subnautica Save Saver Settings")
        self.settings_window.geometry("600x200")
        
        self.settings_window.columnconfigure(0, weight=1)
        self.settings_window.columnconfigure(1, weight=0)
        self.settings_window.rowconfigure(0, weight=1)

        left_frame = tk.Frame(self.settings_window)
        left_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        left_frame.columnconfigure(0, weight=1)

        right_frame = tk.LabelFrame(self.settings_window, text="Status")
        right_frame.grid(row=0, column=1, padx=10, pady=10, sticky="nsew")

        subnautica_folder_var = tk.StringVar(value=self.settings.get('subnautica_save_folder', ''))
        subnautica_zero_folder_var = tk.StringVar(value=self.settings.get('subnautica_zero_save_folder', ''))

        tk.Label(left_frame, text="Subnautica Save Folder:").grid(row=0, column=0, sticky="w")
        tk.Entry(left_frame, textvariable=subnautica_folder_var).grid(row=1, column=0, sticky="ew")
        tk.Button(left_frame, text="Browse", command=lambda: subnautica_folder_var.set(filedialog.askdirectory())).grid(row=1, column=1)

        tk.Label(left_frame, text="Subnautica Below Zero Save Folder:").grid(row=2, column=0, sticky="w")
        tk.Entry(left_frame, textvariable=subnautica_zero_folder_var).grid(row=3, column=0, sticky="ew")
        tk.Button(left_frame, text="Browse", command=lambda: subnautica_zero_folder_var.set(filedialog.askdirectory())).grid(row=3, column=1)

        # Status information
        tk.Label(right_frame, text="Subnautica:").pack(anchor="w")
        tk.Label(right_frame, text=f"    {'Watching' if self.subnautica_enabled else 'Not watching'}", font=("TkDefaultFont", 8)).pack(anchor="w")
        tk.Label(right_frame, text="Subnautica Below Zero:").pack(anchor="w")
        tk.Label(right_frame, text=f"    {'Watching' if self.subnautica_zero_enabled else 'Not watching'}", font=("TkDefaultFont", 8)).pack(anchor="w")
        
        tk.Label(right_frame, text="").pack()  # Spacer
        tk.Label(right_frame, text="Note: Remove path").pack(anchor="w")
        tk.Label(right_frame, text="to stop watching").pack(anchor="w")

        def save_settings():
            self.settings['subnautica_save_folder'] = os.path.normpath(subnautica_folder_var.get()) if subnautica_folder_var.get() else None
            self.settings['subnautica_zero_save_folder'] = os.path.normpath(subnautica_zero_folder_var.get()) if subnautica_zero_folder_var.get() else None
            self.save_settings()
            self.settings_window.destroy()
            self.settings_window = None
            self.verify_and_start_observer()

        button_frame = tk.Frame(left_frame)
        button_frame.grid(row=4, column=0, columnspan=2, pady=(10, 5))
        tk.Button(button_frame, text="Save", command=save_settings).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="Cancel", command=lambda: self.settings_window.destroy()).pack(side=tk.LEFT, padx=5)





class SaveHandler(FileSystemEventHandler):
    def __init__(self, manager, source_folder, target_folder):
        self.manager = manager
        self.source_folder = source_folder
        self.target_folder = target_folder

    def on_modified(self, event):
        if event.is_directory:
            return
        if event.src_path.startswith(self.source_folder):
            self.backup_save(event.src_path)

    def backup_save(self, src_path):
        rel_path = os.path.relpath(src_path, self.source_folder)
        if rel_path.split(os.path.sep)[0].startswith("slot"):
            dest_path = os.path.join(self.target_folder, rel_path)
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            shutil.copy2(src_path, dest_path)
            logging.info(f"Backed up: {src_path} to {dest_path}")

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