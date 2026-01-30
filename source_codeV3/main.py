#!/usr/bin/env python3
"""
Shank 2 Multi-Tool Converter
TEX/PNG Converter + Lua Decompiler/Compiler + Advanced Plugins
"""

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path
import threading
import importlib.util
import sys
import os
import ctypes

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# تحميل محول TEX
try:
    from shank2_ktex_v4 import KTEXConverter
except:
    KTEXConverter = None

# تحميل أدوات Lua
try:
    from luaq_tool import (
        decompile_file, compile_lua_file,
        LuaDecompiler, parse_lua_file, LuaCompiler
    )
except:
    def decompile_file(*args): return False
    def compile_lua_file(*args): return False

# تحميل PIL للصور
try:
    from PIL import Image, ImageTk, ImageEnhance
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

# تحميل نظام الإضافات المتقدم
try:
    from plugin_system import tool, AdvancedPluginLoader
    from auto_ui_builder import ToolWindow
    ADVANCED_PLUGINS = True
except ImportError:
    ADVANCED_PLUGINS = False
    print("Note: Advanced plugin system not available")


def set_title_bar_color(window, color):
    """Change title bar color on Windows 10/11"""
    if sys.platform != "win32":
        return False
    
    try:
        if isinstance(color, str):
            color = color.lstrip('#')
            r, g, b = tuple(int(color[i:i+2], 16) for i in (0, 2, 4))
        else:
            r, g, b = color
        
        color_value = r | (g << 8) | (b << 16)
        window.update()
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        
        DWMWA_CAPTION_COLOR = 35
        DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        
        dwmapi = ctypes.windll.dwmapi
        color_ref = ctypes.c_int(color_value)
        dwmapi.DwmSetWindowAttribute(hwnd, DWMWA_CAPTION_COLOR, 
                                      ctypes.byref(color_ref), ctypes.sizeof(color_ref))
        
        luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
        dark_mode = ctypes.c_int(1 if luminance < 0.5 else 0)
        dwmapi.DwmSetWindowAttribute(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE,
                                      ctypes.byref(dark_mode), ctypes.sizeof(dark_mode))
        return True
    except:
        return False


def get_average_color(image):
    """Get average color from an image"""
    try:
        small = image.resize((50, 50))
        pixels = list(small.getdata())
        if len(pixels[0]) >= 3:
            avg_r = sum(p[0] for p in pixels) // len(pixels)
            avg_g = sum(p[1] for p in pixels) // len(pixels)
            avg_b = sum(p[2] for p in pixels) // len(pixels)
            return (avg_r, avg_g, avg_b)
    except:
        pass
    return None


class ThemeManager:
    """Theme Manager - Purple Theme"""
    THEME = {
        "bg": "#1a0a2e",
        "fg": "#e8d5f2",
        "button_bg": "#5c2a7e",
        "button_fg": "#ffffff",
        "button_active": "#8b45b5",
        "frame_bg": "#2d1448",
        "accent": "#bf5af2",
        "success": "#32d74b",
        "warning": "#ff9f0a",
        "titlebar": "#1a0a2e",
        "flash_color": "#bf5af2",
        "progress_bg": "#2d1448",
        "progress_fg": "#bf5af2"
    }
    
    @classmethod
    def get_theme(cls):
        return cls.THEME


class FlashEffect:
    """Handles the flash/glow effect on success"""
    
    def __init__(self, app):
        self.app = app
        self.is_flashing = False
        self.flash_step = 0
        self.total_steps = 20
        self.original_bg = None
        self.original_frame_bg = None
        self.flash_type = "success"
    
    def hex_to_rgb(self, hex_color):
        hex_color = hex_color.lstrip('#')
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    
    def rgb_to_hex(self, rgb):
        return "#{:02x}{:02x}{:02x}".format(
            max(0, min(255, int(rgb[0]))),
            max(0, min(255, int(rgb[1]))),
            max(0, min(255, int(rgb[2])))
        )
    
    def blend_colors(self, color1, color2, factor):
        r1, g1, b1 = self.hex_to_rgb(color1)
        r2, g2, b2 = self.hex_to_rgb(color2)
        
        r = r1 + (r2 - r1) * factor
        g = g1 + (g2 - g1) * factor
        b = b1 + (b2 - b1) * factor
        
        return self.rgb_to_hex((r, g, b))
    
    def start_flash(self, flash_type="success"):
        if self.is_flashing:
            return
        
        self.flash_type = flash_type
        self.is_flashing = True
        self.flash_step = 0
        
        theme = ThemeManager.get_theme()
        self.original_bg = theme["bg"]
        self.original_frame_bg = theme["frame_bg"]
        
        self._animate_flash()
    
    def _animate_flash(self):
        if not self.is_flashing:
            return
        
        theme = ThemeManager.get_theme()
        
        if self.flash_type == "success":
            flash_color = theme.get("flash_color", "#00ff88")
        elif self.flash_type == "error":
            flash_color = "#ff4444"
        else:
            flash_color = theme.get("warning", "#ffaa00")
        
        import math
        if self.flash_step < self.total_steps // 2:
            progress = self.flash_step / (self.total_steps // 2)
            intensity = math.sin(progress * math.pi / 2)
        else:
            progress = (self.flash_step - self.total_steps // 2) / (self.total_steps // 2)
            intensity = math.cos(progress * math.pi / 2)
        
        current_bg = self.blend_colors(self.original_bg, flash_color, intensity * 0.4)
        current_frame_bg = self.blend_colors(self.original_frame_bg, flash_color, intensity * 0.3)
        
        self._apply_flash_colors(current_bg, current_frame_bg)
        
        if self.app.bg_image and PIL_AVAILABLE:
            self._flash_background_image(intensity)
        
        self.flash_step += 1
        
        if self.flash_step < self.total_steps:
            self.app.window.after(50, self._animate_flash)
        else:
            self.is_flashing = False
            self.app.apply_theme()
            if self.app.bg_image:
                self.app.update_background()
    
    def _apply_flash_colors(self, bg_color, frame_bg_color):
        try:
            self.app.window.configure(bg=bg_color)
            self.app.main_container.configure(bg=bg_color)
            self.app.canvas.configure(bg=bg_color)
            self.app.content_frame.configure(bg=bg_color)
            
            if not self.app.bg_image:
                self.app.bg_label.configure(bg=bg_color)
            
            self.app.title_label.configure(bg=bg_color)
            self.app.status.configure(bg=bg_color)
            self.app.log_label.configure(bg=bg_color)
            
            for frame in [self.app.tex_frame, self.app.lua_frame, self.app.plugins_frame]:
                frame.configure(bg=frame_bg_color)
            
            inner_frames = [
                self.app.tex_btn_frame1, self.app.tex_btn_frame2,
                self.app.lua_btn_frame1, self.app.lua_btn_frame2,
                self.app.plugins_header_frame, self.app.plugin_buttons_frame,
                self.app.progress_frame, self.app.log_outer_frame
            ]
            for frame in inner_frames:
                frame.configure(bg=frame_bg_color)
            
            self.app.plugins_info_label.configure(bg=frame_bg_color)
        except:
            pass
    
    def _flash_background_image(self, intensity):
        if not PIL_AVAILABLE or self.app.bg_image is None:
            return
        
        try:
            width = self.app.window.winfo_width()
            height = self.app.window.winfo_height()
            
            if width > 1 and height > 1:
                resized = self.app.bg_image.resize((width, height), Image.Resampling.LANCZOS)
                
                enhancer = ImageEnhance.Brightness(resized)
                brightened = enhancer.enhance(1.0 + intensity * 0.5)
                
                if self.flash_type == "success":
                    r, g, b = resized.split()[:3]
                    g = g.point(lambda x: min(255, x + int(intensity * 50)))
                    if resized.mode == 'RGBA':
                        a = resized.split()[3]
                        brightened = Image.merge('RGBA', (r, g, b, a))
                    else:
                        brightened = Image.merge('RGB', (r, g, b))
                    enhancer = ImageEnhance.Brightness(brightened)
                    brightened = enhancer.enhance(1.0 + intensity * 0.3)
                
                self.app.bg_photo = ImageTk.PhotoImage(brightened)
                self.app.bg_label.configure(image=self.app.bg_photo)
        except:
            pass


class PluginManager:
    """Enhanced Plugin Manager - Supports both old and new plugin formats"""
    
    def __init__(self, app):
        self.app = app
        self.plugins = []
        self.plugin_buttons = []
        self.plugins_folder = Path("plugins")
        self.plugins_folder.mkdir(exist_ok=True)
        
        # Advanced plugin system
        if ADVANCED_PLUGINS:
            self.advanced_loader = AdvancedPluginLoader(str(self.plugins_folder))
            self.advanced_tools = []
        else:
            self.advanced_loader = None
            self.advanced_tools = []
        
        self._create_example_plugins()
    
    def _create_example_plugins(self):
        # Old format example
        old_example = self.plugins_folder / "example_plugin.py"
        if not old_example.exists():
            old_example.write_text('''"""
Example Plugin (Old Format)
"""
PLUGIN_INFO = {
    "name": "Example Tool",
    "description": "Simple example",
    "author": "User",
    "version": "1.0"
}

def get_buttons():
    return [{"text": "Say Hello", "command": "say_hello"}]

def say_hello(app):
    from tkinter import messagebox
    messagebox.showinfo("Hello", "Hello from Plugin!")
''', encoding='utf-8')

        # New format example with @tool
        if ADVANCED_PLUGINS:
            new_example = self.plugins_folder / "advanced_tools.py"
            if not new_example.exists():
                new_example.write_text('''"""
Advanced Plugin Example - Using @tool decorator
"""
from plugin_system import tool
import os

@tool(
    name="Text Counter",
    description="Counts characters and words in a text file",
    icon="📝",
    category="Text Tools"
)
def count_text(input_file: str, count_spaces: bool = True):
    """Count characters and words in a file."""
    if not os.path.exists(input_file):
        return f"File not found: {input_file}"
    
    with open(input_file, 'r', encoding='utf-8') as f:
        text = f.read()
    
    chars = len(text) if count_spaces else len(text.replace(' ', ''))
    words = len(text.split())
    lines = len(text.splitlines())
    
    return f"Characters: {chars}\\nWords: {words}\\nLines: {lines}"


@tool(
    name="File Info",
    description="Display file information",
    icon="ℹ️",
    category="File Tools"
)
def file_info(input_file: str):
    """Show file size and info."""
    if not os.path.exists(input_file):
        return f"File not found: {input_file}"
    
    size = os.path.getsize(input_file)
    name = os.path.basename(input_file)
    
    if size < 1024:
        size_str = f"{size} bytes"
    elif size < 1024 * 1024:
        size_str = f"{size / 1024:.2f} KB"
    else:
        size_str = f"{size / (1024*1024):.2f} MB"
    
    return f"File: {name}\\nSize: {size_str}"
''', encoding='utf-8')
    
    def load_plugins(self):
        """Load both old and new format plugins."""
        self.plugins = []
        self.advanced_tools = []
        
        if not self.plugins_folder.exists():
            return
        
        # Load old format plugins
        for py_file in self.plugins_folder.glob("*.py"):
            if py_file.name.startswith("_"):
                continue
            try:
                plugin = self._load_python_plugin(py_file)
                if plugin:
                    self.plugins.append(plugin)
            except Exception as e:
                print(f"Error loading {py_file.name}: {e}")
        
        # Load new format plugins (@tool)
        if self.advanced_loader:
            try:
                self.advanced_loader.discover_and_load()
                self.advanced_tools = self.advanced_loader.get_all_tools()
            except Exception as e:
                print(f"Error loading advanced plugins: {e}")

    def _load_python_plugin(self, path):
        """Load old format plugin."""
        try:
            spec = importlib.util.spec_from_file_location(path.stem, path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            if hasattr(module, 'PLUGIN_INFO') and hasattr(module, 'get_buttons'):
                return {
                    "type": "python",
                    "info": module.PLUGIN_INFO,
                    "module": module,
                    "buttons": module.get_buttons()
                }
        except:
            pass
        return None

    def execute_plugin_command(self, plugin, command):
        """Execute old format plugin command."""
        if plugin["type"] == "python":
            if hasattr(plugin["module"], command):
                func = getattr(plugin["module"], command)
                func(self.app)

    def open_tool_window(self, tool_info):
        """Open advanced tool in popup window."""
        if ADVANCED_PLUGINS:
            theme = ThemeManager.get_theme()
            ToolWindow(
                self.app.window,
                tool_info,
                theme,
                on_success=self.app.trigger_success_flash
            )

    def get_total_count(self):
        """Get total plugins + tools count."""
        old_count = len(self.plugins)
        new_count = len(self.advanced_tools)
        return old_count + new_count


class Shank2ConverterApp:
    def __init__(self):
        self.window = tk.Tk()
        self.window.title("Shank 2 Multi-Tool Converter")
        self.window.geometry("700x850")
        self.window.resizable(True, True)
        self.window.minsize(680, 750)
        
        self.bg_image = None
        self.bg_photo = None
        self.custom_titlebar_color = None
        self.custom_progress_color = None
        
        try:
            if KTEXConverter:
                self.tex_converter = KTEXConverter()
            else:
                self.tex_converter = None
        except:
            self.tex_converter = None
        
        self.plugin_manager = PluginManager(self)
        self.flash_effect = FlashEffect(self)
        
        self.setup_ui()
        self.apply_theme()
        self.plugin_manager.load_plugins()
        self.load_plugin_buttons()
        self.auto_load_background()
    
    def trigger_success_flash(self):
        self.flash_effect.start_flash("success")
    
    def trigger_error_flash(self):
        self.flash_effect.start_flash("error")
    
    def auto_load_background(self):
        if not PIL_AVAILABLE:
            return
        
        images_folder = Path("images")
        if not images_folder.exists():
            images_folder.mkdir(exist_ok=True)
            return
        
        for ext in ["*.png", "*.jpg", "*.jpeg", "*.bmp"]:
            images = list(images_folder.glob(ext))
            if images:
                try:
                    self.set_background(images[0])
                    self.log_message(f"[OK] Background: {images[0].name}")
                    return
                except:
                    continue
    
    def set_background(self, image_path):
        if not PIL_AVAILABLE:
            return
        
        try:
            self.bg_image = Image.open(image_path)
            self.update_background()
            self.auto_adjust_colors()
            self.window.bind("<Configure>", self.on_window_resize)
        except Exception as e:
            print(f"Error: {e}")
    
    def update_background(self):
        if self.bg_image is None:
            return
        
        width = self.window.winfo_width()
        height = self.window.winfo_height()
        
        if width > 1 and height > 1:
            resized = self.bg_image.resize((width, height), Image.Resampling.LANCZOS)
            self.bg_photo = ImageTk.PhotoImage(resized)
            self.bg_label.configure(image=self.bg_photo)
    
    def auto_adjust_colors(self):
        if self.bg_image is None:
            return
        
        avg_color = get_average_color(self.bg_image)
        
        if avg_color:
            avg_r, avg_g, avg_b = avg_color
            brightness = (avg_r + avg_g + avg_b) // 3
            
            self.custom_titlebar_color = "#{:02x}{:02x}{:02x}".format(
                max(0, avg_r - 20),
                max(0, avg_g - 20),
                max(0, avg_b - 20)
            )
            set_title_bar_color(self.window, self.custom_titlebar_color)
            
            if brightness > 128:
                self.custom_progress_color = "#{:02x}{:02x}{:02x}".format(
                    max(0, 255 - avg_r),
                    max(0, min(255, avg_g + 50)),
                    max(0, 255 - avg_b)
                )
            else:
                self.custom_progress_color = "#{:02x}{:02x}{:02x}".format(
                    min(255, avg_r + 100),
                    min(255, avg_g + 150),
                    min(255, avg_b + 100)
                )
            
            self.update_progress_bar_color()
            
            if brightness > 128:
                btn_colors = {
                    "bg": "#2d2d2d",
                    "fg": "#ffffff",
                    "active": "#444444"
                }
            else:
                theme = ThemeManager.get_theme()
                btn_colors = {
                    "bg": theme["button_bg"],
                    "fg": theme["button_fg"],
                    "active": theme["button_active"]
                }
            
            for btn in self.all_buttons:
                try:
                    btn.configure(
                        bg=btn_colors["bg"],
                        fg=btn_colors["fg"],
                        activebackground=btn_colors["active"],
                        activeforeground=btn_colors["fg"]
                    )
                except:
                    pass
    
    def update_progress_bar_color(self):
        theme = ThemeManager.get_theme()
        
        if self.custom_progress_color and self.bg_image:
            fg_color = self.custom_progress_color
        else:
            fg_color = theme["progress_fg"]
        
        bg_color = theme["progress_bg"]
        
        style = ttk.Style()
        style.theme_use('default')
        
        style.configure(
            "Custom.Horizontal.TProgressbar",
            troughcolor=bg_color,
            background=fg_color,
            darkcolor=fg_color,
            lightcolor=fg_color,
            bordercolor=bg_color,
            thickness=20
        )
        
        self.progress.configure(style="Custom.Horizontal.TProgressbar")
    
    def on_window_resize(self, event):
        if event.widget == self.window:
            self.update_background()
    
    def setup_ui(self):
        self.all_buttons = []
        
        self.main_container = tk.Frame(self.window)
        self.main_container.pack(fill="both", expand=True)
        
        self.bg_label = tk.Label(self.main_container)
        self.bg_label.place(x=0, y=0, relwidth=1, relheight=1)
        
        self.canvas = tk.Canvas(self.main_container, highlightthickness=0)
        self.canvas.pack(side="left", fill="both", expand=True)
        
        self.content_frame = tk.Frame(self.canvas)
        self.canvas_window = self.canvas.create_window((0, 0), window=self.content_frame, anchor="n")
        
        self.content_frame.bind("<Configure>", self.on_frame_configure)
        self.canvas.bind("<Configure>", self.on_canvas_configure)
        
        self.canvas.bind_all("<MouseWheel>", self.on_mousewheel)
        self.canvas.bind_all("<Button-4>", self.on_mousewheel_linux)
        self.canvas.bind_all("<Button-5>", self.on_mousewheel_linux)
        
        # Title
        self.title_label = tk.Label(
            self.content_frame,
            text="Shank 2 Multi-Tool Converter",
            font=("Arial", 22, "bold")
        )
        self.title_label.pack(pady=20)
        
        # TEX Converter Section
        self.tex_frame = tk.LabelFrame(
            self.content_frame,
            text="  TEX / PNG Converter  ",
            font=("Arial", 13, "bold"),
            padx=15,
            pady=15
        )
        self.tex_frame.pack(pady=15, padx=30, fill="x")
        
        self.tex_btn_frame1 = tk.Frame(self.tex_frame)
        self.tex_btn_frame1.pack(fill="x", pady=5)
        
        self.btn_tex_extract = tk.Button(
            self.tex_btn_frame1,
            text="Extract TEX -> PNG",
            font=("Arial", 11),
            width=20,
            height=2,
            command=self.extract_tex
        )
        self.btn_tex_extract.pack(side="left", padx=10, pady=5)
        self.all_buttons.append(self.btn_tex_extract)
        
        self.btn_tex_extract_folder = tk.Button(
            self.tex_btn_frame1,
            text="Extract Folder",
            font=("Arial", 11),
            width=16,
            height=2,
            command=self.extract_tex_folder
        )
        self.btn_tex_extract_folder.pack(side="left", padx=10, pady=5)
        self.all_buttons.append(self.btn_tex_extract_folder)
        
        self.tex_btn_frame2 = tk.Frame(self.tex_frame)
        self.tex_btn_frame2.pack(fill="x", pady=5)
        
        self.btn_tex_rebuild = tk.Button(
            self.tex_btn_frame2,
            text="Rebuild PNG -> TEX",
            font=("Arial", 11),
            width=20,
            height=2,
            command=self.rebuild_tex
        )
        self.btn_tex_rebuild.pack(side="left", padx=10, pady=5)
        self.all_buttons.append(self.btn_tex_rebuild)
        
        self.btn_tex_rebuild_folder = tk.Button(
            self.tex_btn_frame2,
            text="Rebuild Folder",
            font=("Arial", 11),
            width=16,
            height=2,
            command=self.rebuild_tex_folder
        )
        self.btn_tex_rebuild_folder.pack(side="left", padx=10, pady=5)
        self.all_buttons.append(self.btn_tex_rebuild_folder)
        
        # Lua Tools Section
        self.lua_frame = tk.LabelFrame(
            self.content_frame,
            text="  Lua Decompiler / Compiler  ",
            font=("Arial", 13, "bold"),
            padx=15,
            pady=15
        )
        self.lua_frame.pack(pady=15, padx=30, fill="x")
        
        self.lua_btn_frame1 = tk.Frame(self.lua_frame)
        self.lua_btn_frame1.pack(fill="x", pady=5)
        
        self.btn_lua_decompile = tk.Button(
            self.lua_btn_frame1,
            text="Decompile Lua",
            font=("Arial", 11),
            width=18,
            height=2,
            command=self.decompile_lua
        )
        self.btn_lua_decompile.pack(side="left", padx=10, pady=5)
        self.all_buttons.append(self.btn_lua_decompile)
        
        self.btn_lua_decompile_folder = tk.Button(
            self.lua_btn_frame1,
            text="Batch Decompile",
            font=("Arial", 11),
            width=16,
            height=2,
            command=self.decompile_lua_folder
        )
        self.btn_lua_decompile_folder.pack(side="left", padx=10, pady=5)
        self.all_buttons.append(self.btn_lua_decompile_folder)
        
        self.lua_btn_frame2 = tk.Frame(self.lua_frame)
        self.lua_btn_frame2.pack(fill="x", pady=5)
        
        self.btn_lua_compile = tk.Button(
            self.lua_btn_frame2,
            text="Compile Lua",
            font=("Arial", 11),
            width=18,
            height=2,
            command=self.compile_lua
        )
        self.btn_lua_compile.pack(side="left", padx=10, pady=5)
        self.all_buttons.append(self.btn_lua_compile)
        
        self.btn_lua_compile_folder = tk.Button(
            self.lua_btn_frame2,
            text="Batch Compile",
            font=("Arial", 11),
            width=16,
            height=2,
            command=self.compile_lua_folder
        )
        self.btn_lua_compile_folder.pack(side="left", padx=10, pady=5)
        self.all_buttons.append(self.btn_lua_compile_folder)
        
        # Plugins Section
        self.plugins_frame = tk.LabelFrame(
            self.content_frame,
            text="  Plugins  ",
            font=("Arial", 13, "bold"),
            padx=15,
            pady=10
        )
        self.plugins_frame.pack(pady=15, padx=30, fill="x")
        
        self.plugins_header_frame = tk.Frame(self.plugins_frame)
        self.plugins_header_frame.pack(fill="x", pady=5)
        
        self.btn_reload_plugins = tk.Button(
            self.plugins_header_frame,
            text="🔄 Reload",
            font=("Arial", 10),
            command=self.reload_plugins
        )
        self.btn_reload_plugins.pack(side="left", padx=10)
        self.all_buttons.append(self.btn_reload_plugins)
        
        self.btn_open_plugins = tk.Button(
            self.plugins_header_frame,
            text="📁 Open Folder",
            font=("Arial", 10),
            command=self.open_plugins_folder
        )
        self.btn_open_plugins.pack(side="left", padx=10)
        self.all_buttons.append(self.btn_open_plugins)
        
        self.plugins_info_label = tk.Label(
            self.plugins_header_frame,
            text="Loaded: 0",
            font=("Arial", 10)
        )
        self.plugins_info_label.pack(side="right", padx=10)
        
        self.plugin_buttons_frame = tk.Frame(self.plugins_frame)
        self.plugin_buttons_frame.pack(fill="x", pady=5)
        
        # Progress Section
        self.progress_frame = tk.Frame(self.content_frame)
        self.progress_frame.pack(pady=10, padx=30, fill="x")
        
        self.progress = ttk.Progressbar(self.progress_frame, length=600, mode='determinate')
        self.progress.pack(fill="x", pady=5)
        
        self.status = tk.Label(self.content_frame, text="Ready", font=("Arial", 11))
        self.status.pack(pady=5)
        
        # Log Section
        self.log_label = tk.Label(
            self.content_frame,
            text="Log:",
            font=("Arial", 11, "bold")
        )
        self.log_label.pack(pady=(10, 5), anchor="w", padx=30)
        
        self.log_outer_frame = tk.Frame(self.content_frame)
        self.log_outer_frame.pack(pady=5, padx=30, fill="both", expand=True)
        
        self.log = tk.Text(self.log_outer_frame, height=8, width=70, font=("Consolas", 10))
        self.log.pack(side="left", fill="both", expand=True)
        
        self.log_scrollbar = tk.Scrollbar(self.log_outer_frame, command=self.log.yview)
        self.log_scrollbar.pack(side="right", fill="y")
        self.log.config(yscrollcommand=self.log_scrollbar.set)
        
        self.btn_clear_log = tk.Button(
            self.content_frame,
            text="Clear Log",
            font=("Arial", 10),
            command=self.clear_log
        )
        self.btn_clear_log.pack(pady=10)
        self.all_buttons.append(self.btn_clear_log)
        
        tk.Label(self.content_frame, text="", height=2).pack()
    
    def on_frame_configure(self, event):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
    
    def on_canvas_configure(self, event):
        self.canvas.itemconfig(self.canvas_window, width=event.width)
    
    def on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")
    
    def on_mousewheel_linux(self, event):
        if event.num == 4:
            self.canvas.yview_scroll(-1, "units")
        elif event.num == 5:
            self.canvas.yview_scroll(1, "units")
    
    def apply_theme(self):
        theme = ThemeManager.get_theme()
        
        if self.custom_titlebar_color and self.bg_image:
            set_title_bar_color(self.window, self.custom_titlebar_color)
        else:
            set_title_bar_color(self.window, theme["titlebar"])
        
        self.window.configure(bg=theme["bg"])
        self.main_container.configure(bg=theme["bg"])
        self.canvas.configure(bg=theme["bg"])
        self.content_frame.configure(bg=theme["bg"])
        self.bg_label.configure(bg=theme["bg"])
        
        self.title_label.configure(bg=theme["bg"], fg=theme["accent"])
        
        for frame in [self.tex_frame, self.lua_frame, self.plugins_frame]:
            frame.configure(bg=theme["frame_bg"], fg=theme["fg"])
        
        inner_frames = [
            self.tex_btn_frame1, self.tex_btn_frame2,
            self.lua_btn_frame1, self.lua_btn_frame2,
            self.plugins_header_frame, self.plugin_buttons_frame,
            self.progress_frame, self.log_outer_frame
        ]
        for frame in inner_frames:
            frame.configure(bg=theme["frame_bg"])
        
        self.status.configure(bg=theme["bg"], fg=theme["success"])
        self.plugins_info_label.configure(bg=theme["frame_bg"], fg=theme["fg"])
        self.log_label.configure(bg=theme["bg"], fg=theme["fg"])
        self.log.configure(bg="#0f0f1a", fg="#00ff41", insertbackground=theme["fg"])
        
        self.update_progress_bar_color()
        
        btn_style = {
            "bg": theme["button_bg"],
            "fg": theme["button_fg"],
            "activebackground": theme["button_active"],
            "activeforeground": theme["button_fg"]
        }
        
        for btn in self.all_buttons:
            try:
                btn.configure(**btn_style)
            except:
                pass
        
        for btn in self.plugin_manager.plugin_buttons:
            try:
                btn.configure(**btn_style)
            except:
                pass
    
    def load_plugin_buttons(self):
        """Load buttons for all plugins (old + new format)."""
        for btn in self.plugin_manager.plugin_buttons:
            btn.destroy()
        self.plugin_manager.plugin_buttons = []

        theme = ThemeManager.get_theme()

        # Old format plugin buttons
        for plugin in self.plugin_manager.plugins:
            for btn_info in plugin.get("buttons", []):
                btn = tk.Button(
                    self.plugin_buttons_frame,
                    text=btn_info.get("text", "Plugin"),
                    font=("Arial", 10),
                    bg=theme["button_bg"],
                    fg=theme["button_fg"],
                    activebackground=theme["button_active"],
                    command=lambda p=plugin, c=btn_info.get("command"): 
                        self.plugin_manager.execute_plugin_command(p, c)
                )
                btn.pack(side="left", padx=5, pady=5)
                self.plugin_manager.plugin_buttons.append(btn)
                self.all_buttons.append(btn)

        # New format tools (@tool decorator)
        for tool_info in self.plugin_manager.advanced_tools:
            btn = tk.Button(
                self.plugin_buttons_frame,
                text=f"{tool_info['icon']} {tool_info['name']}",
                font=("Arial", 10),
                bg=theme["button_bg"],
                fg=theme["button_fg"],
                activebackground=theme["button_active"],
                command=lambda t=tool_info: self.plugin_manager.open_tool_window(t)
            )
            btn.pack(side="left", padx=5, pady=5)
            self.plugin_manager.plugin_buttons.append(btn)
            self.all_buttons.append(btn)

        # Update count label
        total = self.plugin_manager.get_total_count()
        tools_count = len(self.plugin_manager.advanced_tools)
        
        if tools_count > 0:
            self.plugins_info_label.configure(text=f"Loaded: {total} ({tools_count} tools)")
        else:
            self.plugins_info_label.configure(text=f"Loaded: {total}")
    
    def reload_plugins(self):
        self.plugin_manager.load_plugins()
        self.load_plugin_buttons()
        self.apply_theme()
        total = self.plugin_manager.get_total_count()
        self.log_message(f"[OK] Reloaded {total} plugins")
    
    def open_plugins_folder(self):
        folder = Path("plugins")
        folder.mkdir(exist_ok=True)
        if sys.platform == "win32":
            os.startfile(folder)
        elif sys.platform == "darwin":
            os.system(f'open "{folder}"')
        else:
            os.system(f'xdg-open "{folder}"')
    
    def log_message(self, msg):
        self.log.insert(tk.END, msg + "\n")
        self.log.see(tk.END)
    
    def clear_log(self):
        self.log.delete(1.0, tk.END)
    
    def reset_ui(self):
        self.progress['value'] = 0
        self.status.configure(text="Processing...")
    
    # ==================== TEX FUNCTIONS ====================
    
    def extract_tex(self):
        if not self.tex_converter:
            messagebox.showerror("Error", "TEX converter not available!")
            return
        
        file_path = filedialog.askopenfilename(
            title="Select TEX File",
            filetypes=[("TEX files", "*.tex"), ("All", "*.*")]
        )
        
        if file_path:
            self.reset_ui()
            self.progress['value'] = 50
            try:
                result = self.tex_converter.extract(Path(file_path))
                if result.success:
                    self.log_message(f"[OK] Extracted: {result.output_path.name}")
                    self.trigger_success_flash()
                    messagebox.showinfo("Success", "Extraction completed!")
                else:
                    self.log_message(f"[ERROR] {result.error}")
                    self.trigger_error_flash()
            except Exception as e:
                self.log_message(f"[ERROR] {e}")
                self.trigger_error_flash()
            self.progress['value'] = 100
            self.status.configure(text="Done")
    
    def extract_tex_folder(self):
        if not self.tex_converter:
            messagebox.showerror("Error", "TEX converter not available!")
            return
        
        folder_path = filedialog.askdirectory(title="Select Folder")
        if folder_path:
            files = list(Path(folder_path).glob("*.tex"))
            if not files:
                messagebox.showwarning("Warning", "No TEX files found!")
                return
            self.reset_ui()
            thread = threading.Thread(target=self._process_tex_files, args=(files, "extract"))
            thread.start()
    
    def rebuild_tex(self):
        if not self.tex_converter:
            messagebox.showerror("Error", "TEX converter not available!")
            return
        
        file_path = filedialog.askopenfilename(
            title="Select PNG File",
            filetypes=[("PNG files", "*.png"), ("All", "*.*")]
        )
        
        if file_path:
            self.reset_ui()
            self.progress['value'] = 50
            try:
                result = self.tex_converter.rebuild(Path(file_path))
                if result.success:
                    self.log_message(f"[OK] Rebuilt: {result.output_path.name}")
                    self.trigger_success_flash()
                    messagebox.showinfo("Success", "Rebuild completed!")
                else:
                    self.log_message(f"[ERROR] {result.error}")
                    self.trigger_error_flash()
            except Exception as e:
                self.log_message(f"[ERROR] {e}")
                self.trigger_error_flash()
            self.progress['value'] = 100
            self.status.configure(text="Done")
    
    def rebuild_tex_folder(self):
        if not self.tex_converter:
            messagebox.showerror("Error", "TEX converter not available!")
            return
        
        folder_path = filedialog.askdirectory(title="Select Folder")
        if folder_path:
            files = list(Path(folder_path).glob("*.png"))
            if not files:
                messagebox.showwarning("Warning", "No PNG files found!")
                return
            self.reset_ui()
            thread = threading.Thread(target=self._process_tex_files, args=(files, "rebuild"))
            thread.start()
    
    def _process_tex_files(self, files, mode):
        total = len(files)
        success = 0
        for i, file in enumerate(files):
            try:
                if mode == "extract":
                    result = self.tex_converter.extract(file)
                else:
                    result = self.tex_converter.rebuild(file)
                if result.success:
                    self.log_message(f"[OK] {file.name}")
                    success += 1
                else:
                    self.log_message(f"[ERROR] {file.name}")
            except Exception as e:
                self.log_message(f"[ERROR] {file.name}: {e}")
            self.progress['value'] = ((i + 1) / total) * 100
            self.window.update_idletasks()
        
        self.status.configure(text=f"Done ({success}/{total})")
        
        if success > 0:
            self.window.after(100, self.trigger_success_flash)
        
        messagebox.showinfo("Done", f"Processed {success}/{total} files")
    
    # ==================== LUA FUNCTIONS ====================
    
    def decompile_lua(self):
        file_path = filedialog.askopenfilename(
            title="Select Lua File",
            filetypes=[("Lua files", "*.lua"), ("All", "*.*")]
        )
        
        if file_path:
            self.reset_ui()
            self.progress['value'] = 50
            try:
                with open(file_path, 'rb') as f:
                    if f.read(4) != b'\x1bLua':
                        messagebox.showerror("Error", "Not a compiled Lua file!")
                        return
                
                output_path = file_path.rsplit('.', 1)[0] + '_decompiled.lua'
                if decompile_file(file_path, output_path):
                    self.log_message(f"[OK] Decompiled: {Path(output_path).name}")
                    self.trigger_success_flash()
                    messagebox.showinfo("Success", "Decompilation completed!")
                else:
                    self.trigger_error_flash()
            except Exception as e:
                self.log_message(f"[ERROR] {e}")
                self.trigger_error_flash()
            self.progress['value'] = 100
            self.status.configure(text="Done")
    
    def decompile_lua_folder(self):
        folder_path = filedialog.askdirectory(title="Select Folder")
        if folder_path:
            self.reset_ui()
            thread = threading.Thread(target=self._batch_decompile, args=(folder_path,))
            thread.start()
    
    def _batch_decompile(self, folder_path):
        output_folder = os.path.join(folder_path, "decompiled")
        os.makedirs(output_folder, exist_ok=True)
        
        files = [f for f in os.listdir(folder_path) if f.endswith('.lua')]
        success = 0
        
        for i, filename in enumerate(files):
            filepath = os.path.join(folder_path, filename)
            try:
                with open(filepath, 'rb') as f:
                    if f.read(4) == b'\x1bLua':
                        out_path = os.path.join(output_folder, filename.replace('.lua', '_dec.lua'))
                        if decompile_file(filepath, out_path):
                            self.log_message(f"[OK] {filename}")
                            success += 1
            except Exception as e:
                self.log_message(f"[ERROR] {filename}: {e}")
            self.progress['value'] = ((i + 1) / len(files)) * 100
            self.window.update_idletasks()
        
        self.status.configure(text=f"Done ({success})")
        
        if success > 0:
            self.window.after(100, self.trigger_success_flash)
        
        messagebox.showinfo("Done", f"Decompiled {success} files")
    
    def compile_lua(self):
        file_path = filedialog.askopenfilename(
            title="Select Lua File",
            filetypes=[("Lua files", "*.lua"), ("All", "*.*")]
        )
        
        if file_path:
            self.reset_ui()
            self.progress['value'] = 50
            try:
                with open(file_path, 'rb') as f:
                    if f.read(4) == b'\x1bLua':
                        messagebox.showerror("Error", "File already compiled!")
                        return
                
                output_path = file_path.replace('_decompiled', '').rsplit('.', 1)[0] + '_compiled.lua'
                if compile_lua_file(file_path, output_path):
                    self.log_message(f"[OK] Compiled: {Path(output_path).name}")
                    self.trigger_success_flash()
                    messagebox.showinfo("Success", "Compilation completed!")
                else:
                    self.trigger_error_flash()
            except Exception as e:
                self.log_message(f"[ERROR] {e}")
                self.trigger_error_flash()
            self.progress['value'] = 100
            self.status.configure(text="Done")
    
    def compile_lua_folder(self):
        folder_path = filedialog.askdirectory(title="Select Folder")
        if folder_path:
            self.reset_ui()
            thread = threading.Thread(target=self._batch_compile, args=(folder_path,))
            thread.start()
    
    def _batch_compile(self, folder_path):
        output_folder = os.path.join(folder_path, "compiled")
        os.makedirs(output_folder, exist_ok=True)
        
        files = [f for f in os.listdir(folder_path) if f.endswith('.lua')]
        success = 0
        
        for i, filename in enumerate(files):
            filepath = os.path.join(folder_path, filename)
            try:
                with open(filepath, 'rb') as f:
                    if f.read(4) != b'\x1bLua':
                        out_path = os.path.join(output_folder, filename.replace('_decompiled', ''))
                        if compile_lua_file(filepath, out_path):
                            self.log_message(f"[OK] {filename}")
                            success += 1
            except Exception as e:
                self.log_message(f"[ERROR] {filename}: {e}")
            self.progress['value'] = ((i + 1) / len(files)) * 100
            self.window.update_idletasks()
        
        self.status.configure(text=f"Done ({success})")
        
        if success > 0:
            self.window.after(100, self.trigger_success_flash)
        
        messagebox.showinfo("Done", f"Compiled {success} files")
    
    def run(self):
        self.window.mainloop()


if __name__ == "__main__":
    app = Shank2ConverterApp()
    app.run()