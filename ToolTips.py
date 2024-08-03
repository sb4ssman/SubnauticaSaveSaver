# -*- coding: utf-8 -*-
"""
Created on Sat Jun 6 10:14:14 2024

@author: Thomas
"""



"""
ToolTip Class for Tkinter
-------------------------

This module provides a customizable ToolTip class for Tkinter applications.
It allows you to easily add tooltips to any Tkinter widget.

Features:
- Create tooltips for any Tkinter widget
- Enable/disable tooltips dynamically
- Update tooltip text on the fly
- Two methods of creation: simple and named instance
- Delay: global and per-tip

Usage:
1. Simple Creation:
   createToolTip(widget, "Tooltip text")
   
   This method automatically binds the tooltip to the widget and adds
   tooltip-specific methods to the widget.

2. Named Instance:
   tooltip = createNamedToolTip(widget, "Tooltip text")
   
   This method returns a ToolTip instance, allowing for more direct control.

Tooltip Management:
- For tooltips created with Method 1:
  widget.tt_get_text()  # Get current tooltip text
  widget.tt_set_text("New text")  # Update tooltip text
  widget.tt_enable()  # Enable tooltip
  widget.tt_disable()  # Disable tooltip

- For tooltips created with Method 2:
  tooltip.text  # Get current tooltip text
  tooltip.update_text("New text")  # Update tooltip text
  tooltip.enable()  # Enable tooltip
  tooltip.disable()  # Disable tooltip

Example:
  import tkinter as tk
  from tooltip import createToolTip, createNamedToolTip

  root = tk.Tk()

  # Method 1
  label1 = tk.Label(root, text="Hover me (Method 1)")
  label1.pack()
  createToolTip(label1, "This is a tooltip")

  # Method 2
  label2 = tk.Label(root, text="Hover me (Method 2)")
  label2.pack()
  tooltip2 = createNamedToolTip(label2, "This is another tooltip")

  root.mainloop()

Notes:
- The ToolTip class can be easily integrated into existing Tkinter applications.
- Tooltips are customizable in terms of appearance and behavior.
- The module includes a demo class (TooltipDemo) that showcases various tooltip functionalities.
- Handles the destruction of a widget before a tooltip is drawn

For more detailed examples and advanced usage, refer to the TooltipDemo class in this file.
"""


##############################
#                            #
#   TOOLTIP CLASS TEMPLATE   #
#                            #
##############################

# Stuff this class into an app and you can make tooltips at your lesiure 


# STANDARD IMPORTS
###############################

import tkinter as tk

# Global default delay in milliseconds
DEFAULT_TOOLTIP_DELAY = 500

# ToolTip Class
###########################

class ToolTip:
    def __init__(self, widget, text, delay=DEFAULT_TOOLTIP_DELAY):
        self.widget = widget
        self.text = text
        self.delay = delay
        self.tipwindow = None
        self.id = None
        self.x = self.y = 0
        self.enabled = True
        
        # Bind the destruction of the widget to our cleanup method
        self.bind_id = self.widget.bind("<Destroy>", self.on_destroy, add="+")

    def showtip(self):
        self.hidetip()
        if self.enabled and self.text:
            try:
                self.id = self.widget.after(self.delay, self._show_tip)
            except Exception as e:
                print(f"Error in showtip: {e}")

    def _show_tip(self):
        if not self.enabled or self.tipwindow or not self.widget.winfo_exists():
            return
        try:
            x, y, _, _ = self.widget.bbox("insert")
            x = x + self.widget.winfo_rootx() + 25
            y = y + self.widget.winfo_rooty() + 25
            self.tipwindow = tw = tk.Toplevel(self.widget)
            tw.wm_overrideredirect(1)
            tw.wm_geometry(f"+{x}+{y}")
            label = tk.Label(tw, text=self.text, justify=tk.LEFT,
                            background="#ffffe0", relief=tk.SOLID, borderwidth=1,
                            font=("tahoma", "8", "normal"))
            label.pack(ipadx=1)
            tw.wm_attributes("-topmost", 1)
        except Exception as e:
            print(f"Error in _show_tip: {e}")

    def hidetip(self):
        if self.tipwindow:
            self.tipwindow.destroy()
            self.tipwindow = None
        if self.id:
            self.widget.after_cancel(self.id)
            self.id = None

    def on_destroy(self, event):
        self.hidetip()
        if self.bind_id:
            self.widget.unbind("<Destroy>", self.bind_id)
            self.bind_id = None

    def update_text(self, new_text):
        self.text = new_text
        if self.tipwindow:
            label = self.tipwindow.winfo_children()[0]
            label.config(text=self.text)

    def enable(self):
        self.enabled = True

    def disable(self):
        self.enabled = False
        self.hidetip()

def createToolTip(widget, text, delay=DEFAULT_TOOLTIP_DELAY):
    toolTip = ToolTip(widget, text, delay)
    
    def enter(event):
        toolTip.showtip()
    
    def leave(event):
        toolTip.hidetip()
    
    widget.bind('<Enter>', enter, add="+")
    widget.bind('<Leave>', leave, add="+")

    # Store the tooltip object and related methods as attributes of the widget
    widget.tooltip = toolTip
    widget.tt_get_text = lambda: toolTip.text
    widget.tt_set_text = toolTip.update_text
    widget.tt_enable = toolTip.enable
    widget.tt_disable = toolTip.disable
    widget.tt_enabled = True


def createNamedToolTip(widget, text):
    tooltip = ToolTip(widget, text)
    widget.bind('<Enter>', lambda event: tooltip.showtip())
    widget.bind('<Leave>', lambda event: tooltip.hidetip())
    return tooltip


##########################################################
#   END TEMPLATE   #   END TEMPLATE   #   END TEMPLATE   #


# More notes:

# Have a thing:
# screenshot_checkbox = tk.Checkbutton(root, text="Take Screenshot")
# screenshot_checkbox.pack(side=tk.RIGHT, padx=5)

# Make a tooltip:
# createToolTip(screenshot_checkbox, "Capture the screen when clicking")

# self.screenshot_checkbox_tooltip.update_text("You can update the text of the tip!")

# self.screenshot_checkbox_tooltip.remove()

# SEE test app in TestApps