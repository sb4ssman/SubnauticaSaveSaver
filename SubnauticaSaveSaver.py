# -*- coding: utf-8 -*-
"""
Created on Sat Jun 29 22:07:11 2024

@author: Thomas
"""

# Stacey's Super Stealthy Subnautica Save Saver
# Runs in your system tray and copies your Subnautica saves to a separate folder appending timestamps to the name.
# Uses a Windows observer to trigger events so it's not chewing through cpu.
# The presence in the tray is so you know it's running, and to interact with the saves it manages. 



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





# Directories setup
app_directory = os.path.dirname(os.path.abspath(__file__))
settings_path = os.path.join(app_directory, 'settings.json')
saves_dir = os.path.join(app_directory, "Saves")

if not os.path.exists(saves_dir):
    os.makedirs(saves_dir)

# Default Settings
default_settings = {
    'game_save_folder': os.path.join(os.getenv('APPDATA'), 'Unknown Worlds', 'Subnautica'),
    'target_folder': os.path.join(app_directory, 'Saves')
}
settings = {}

# Load settings from file
if os.path.exists(settings_path):
    with open(settings_path, 'r') as f:
        settings.update(json.load(f))
else:
    settings = default_settings

# Verify paths
def verify_paths():
    if not os.path.exists(settings['game_save_folder']):
        return False
    if not os.path.exists(settings['target_folder']):
        return False
    return True

# System tray menu actions
def on_open_folders(icon, item):
    os.startfile(settings['game_save_folder'])
    os.startfile(settings['target_folder'])

def on_settings(icon, item):
    open_settings_window()

def on_about(icon, item):
    messagebox.showinfo(
        "About",
        """
        Stacey's Super Stealthy
        Subnautica Save Saver
        Version 1.0

        Because Subnautica does not
        save the saves enough.

        Set the Subnautica Save Folder
        and the target save directory
        in the settings.

        Stacey's Saver leaves a callback
        in the system to be notified of
        changes, and copies files when
        Subnautica saves them.
        """
    )


def on_duplicate_save_now(icon, item):
    duplicate_latest_save()

def on_restore_from_list(icon, item):
    open_restore_window()

def on_quit(icon, item):
    global observer
    if observer:
        observer.stop()
        observer.join()
    icon.stop()



# Create an icon for the system tray
def create_image():
    width = 64
    height = 64
    # Create a turquoise blue background
    image = Image.new('RGB', (width, height), (64, 224, 208))  # Turquoise blue color
    
    # Draw a bold purple 'S' using polygons
    draw = ImageDraw.Draw(image)
    
    # Define the points for each segment of the 'S' with corrected coordinates
    segments = [
        # Segment 1 (top horizontal bar)
        [(15, 15), (45, 15), (45, 25), (15, 25)],
        
        # Segment 2 (top-right vertical bar)
        [(45, 25), (55, 25), (55, 35), (45, 35)],
        
        # Segment 3 (middle horizontal bar)
        [(15, 35), (45, 35), (45, 45), (15, 45)],
        
        # Segment 4 (bottom-left vertical bar)
        [(15, 45), (25, 45), (25, 55), (15, 55)],
        
        # Segment 5 (bottom horizontal bar)
        [(25, 55), (55, 55), (55, 65), (25, 65)],
    ]
    
    # Draw each segment of the 'S' filled with purple color
    for segment in segments:
        draw.polygon(segment, fill=(128, 0, 128))
    
        # Create a new image for flipped 'S'
    flipped_image = Image.new('RGB', (width, height))
    
    # Copy pixels from original image to flipped image horizontally
    for y in range(height):
        for x in range(width):
            flipped_image.putpixel((width - x - 1, y), image.getpixel((x, y)))
    
    return flipped_image
    # return image



# Define menu items
menu = (
    item('Open both Folders...', on_open_folders),
    item('Settings...', on_settings),
    item('About...', on_about),
    item('Duplicate Save Now!', on_duplicate_save_now),
    item('Restore from List...', on_restore_from_list),
    item('Quit', on_quit)
)

# Create the system tray icon
icon = pystray.Icon("subnautica_save_manager", create_image(), "Stacey's Super Stealthy\nSubnautica Save Saver", menu)



# File system event handler
class SaveHandler(FileSystemEventHandler):
    def on_modified(self, event):
        if event.is_directory:
            return
        if settings['game_save_folder'] in event.src_path:
            duplicate_latest_save()

def duplicate_latest_save():
    game_save_folder = settings['game_save_folder']
    target_folder = saves_dir  # Ensure saves go into the 'Saves' folder
    if not game_save_folder or not target_folder:
        messagebox.showinfo("Failure!", "Game or Target folder(s) not found!")
        return

    latest_save = max(
        (os.path.join(game_save_folder, f) for f in os.listdir(game_save_folder)),
        key=os.path.getctime
    )
    timestamp = time.strftime('%Y%m%d%H%M%S')
    shutil.copy(latest_save, os.path.join(target_folder, f"{os.path.basename(latest_save)}_{timestamp}"))

# Open settings window
def open_settings_window():
    def save_settings():
        settings['game_save_folder'] = game_save_folder_var.get()
        settings['target_folder'] = target_folder_var.get()
        with open(settings_path, 'w') as f:
            json.dump(settings, f)
        settings_window.destroy()

    settings_window = tk.Tk()
    settings_window.title("Subnautica Save Saver Settings")
    
    tk.Label(settings_window, text="Game Save Folder:").pack(anchor="w")
    game_save_folder_var = tk.StringVar(value=settings['game_save_folder'])
    tk.Entry(settings_window, textvariable=game_save_folder_var, width=100).pack()
    tk.Button(settings_window, text="Browse", command=lambda: game_save_folder_var.set(filedialog.askdirectory())).pack()

    tk.Label(settings_window, text="Target Folder:").pack(anchor="w")
    target_folder_var = tk.StringVar(value=settings['target_folder'])
    tk.Entry(settings_window, textvariable=target_folder_var, width=100).pack()
    tk.Button(settings_window, text="Browse", command=lambda: target_folder_var.set(filedialog.askdirectory())).pack(pady=(0,5))

    tk.Button(settings_window, text="Save", command=save_settings).pack(pady=(0, 5))
    settings_window.mainloop()

# Open restore window
def open_restore_window():
    def restore_save():
        selected_save = save_listbox.get(save_listbox.curselection())
        restore_file = os.path.join(saves_dir, selected_save)
        original_name = '_'.join(selected_save.split('_')[:-1])
        shutil.copy(restore_file, os.path.join(settings['game_save_folder'], original_name))
        restore_window.destroy()

    restore_window = tk.Tk()
    restore_window.title("Restore from List")

    save_listbox = tk.Listbox(restore_window, width=50)
    save_listbox.pack()
    
    for save_file in os.listdir(saves_dir):
        save_listbox.insert(tk.END, save_file)

    tk.Button(restore_window, text="Restore", command=restore_save).pack()
    restore_window.mainloop()

# Initialize observer globally
observer = None

# Verify paths and start observer
if verify_paths():
    observer = Observer()
    event_handler = SaveHandler()
    observer.schedule(event_handler, settings['game_save_folder'], recursive=False)
    observer.start()
else:
    messagebox.showinfo("Failure!", "Paths are not set or invalid.\nPlease set the paths using the Settings menu.")



# Start the Icon; stop the observer
if __name__ == "__main__":
    try:
        icon.run()
    except KeyboardInterrupt:
        if observer:
            observer.stop()
            observer.join()
