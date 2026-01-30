"""
Auto UI Builder - Creates tool windows automatically
"""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from typing import Dict, List, Any


class ToolWindow:
    """Popup window for a tool with auto-generated UI."""

    def __init__(self, parent, tool_info: Dict, theme: Dict, on_success=None):
        self.tool_info = tool_info
        self.theme = theme
        self.on_success = on_success
        self.input_vars = {}

        self.window = tk.Toplevel(parent)
        self.window.title(f"{tool_info['icon']} {tool_info['name']}")
        self.window.geometry("500x450")
        self.window.configure(bg=theme["bg"])
        self.window.resizable(True, True)
        
        self._build_ui()

    def _build_ui(self):
        t = self.theme
        
        # Header
        header = tk.Frame(self.window, bg=t["bg"])
        header.pack(fill="x", padx=20, pady=15)

        tk.Label(
            header,
            text=f"{self.tool_info['icon']} {self.tool_info['name']}",
            font=("Arial", 16, "bold"),
            bg=t["bg"], fg=t["accent"]
        ).pack(anchor="w")

        tk.Label(
            header,
            text=self.tool_info['description'],
            font=("Arial", 10),
            bg=t["bg"], fg=t["fg"]
        ).pack(anchor="w", pady=(5, 0))

        # Separator
        ttk.Separator(self.window, orient="horizontal").pack(fill="x", padx=20, pady=10)

        # Parameters Frame
        params_frame = tk.LabelFrame(
            self.window,
            text=" Parameters ",
            font=("Arial", 11, "bold"),
            bg=t["frame_bg"], fg=t["fg"],
            padx=15, pady=10
        )
        params_frame.pack(fill="x", padx=20, pady=10)

        for param in self.tool_info['parameters']:
            self._create_param_widget(params_frame, param)

        # Execute Button
        btn_frame = tk.Frame(self.window, bg=t["bg"])
        btn_frame.pack(fill="x", padx=20, pady=15)

        self.run_btn = tk.Button(
            btn_frame,
            text=f"▶ Run {self.tool_info['name']}",
            font=("Arial", 12, "bold"),
            bg=t["button_bg"], fg=t["button_fg"],
            activebackground=t["button_active"],
            command=self._execute,
            height=2, width=20
        )
        self.run_btn.pack()

        # Result Frame
        result_frame = tk.LabelFrame(
            self.window,
            text=" Result ",
            font=("Arial", 11, "bold"),
            bg=t["frame_bg"], fg=t["fg"],
            padx=10, pady=10
        )
        result_frame.pack(fill="both", expand=True, padx=20, pady=(0, 20))

        self.result_text = tk.Text(
            result_frame,
            height=6,
            font=("Consolas", 10),
            bg="#0f0f1a", fg="#00ff41",
            wrap="word"
        )
        self.result_text.pack(fill="both", expand=True)

    def _create_param_widget(self, parent, param: Dict):
        """Create input widget based on parameter type."""
        t = self.theme
        
        row = tk.Frame(parent, bg=t["frame_bg"])
        row.pack(fill="x", pady=8)

        # Label
        label_text = param['name'].replace('_', ' ').title()
        if param['required']:
            label_text += " *"

        tk.Label(
            row,
            text=label_text,
            font=("Arial", 10),
            bg=t["frame_bg"], fg=t["fg"],
            width=15, anchor="w"
        ).pack(side="left")

        param_type = param['type']
        default = param.get('default')

        # Boolean -> Checkbox
        if param_type == bool:
            var = tk.BooleanVar(value=default if default is not None else False)
            cb = tk.Checkbutton(
                row, variable=var,
                bg=t["frame_bg"], fg=t["fg"],
                selectcolor=t["button_bg"],
                activebackground=t["frame_bg"]
            )
            cb.pack(side="left")
            self.input_vars[param['name']] = var

        # Int -> Spinbox
        elif param_type == int:
            var = tk.IntVar(value=default if default is not None else 0)
            sb = tk.Spinbox(
                row, from_=-9999, to=9999,
                textvariable=var, width=15,
                bg="#1a1a2e", fg=t["fg"]
            )
            sb.pack(side="left")
            self.input_vars[param['name']] = var

        # Float -> Spinbox
        elif param_type == float:
            var = tk.DoubleVar(value=default if default is not None else 0.0)
            sb = tk.Spinbox(
                row, from_=-9999, to=9999,
                increment=0.1, textvariable=var, width=15,
                bg="#1a1a2e", fg=t["fg"]
            )
            sb.pack(side="left")
            self.input_vars[param['name']] = var

        # String (with file browser if needed)
        else:
            var = tk.StringVar(value=default if default is not None else "")
            
            is_file_param = any(x in param['name'].lower() for x in 
                               ['file', 'path', 'input', 'output', 'folder', 'dir'])

            if is_file_param:
                entry = tk.Entry(row, textvariable=var, width=30, bg="#1a1a2e", fg=t["fg"])
                entry.pack(side="left", padx=(0, 5))

                browse_btn = tk.Button(
                    row, text="{[F]}",
                    bg=t["button_bg"], fg=t["button_fg"],
                    command=lambda v=var, n=param['name']: self._browse(v, n)
                )
                browse_btn.pack(side="left")
            else:
                entry = tk.Entry(row, textvariable=var, width=35, bg="#1a1a2e", fg=t["fg"])
                entry.pack(side="left")

            self.input_vars[param['name']] = var

    def _browse(self, var: tk.StringVar, param_name: str):
        """Open file/folder dialog."""
        if 'folder' in param_name.lower() or 'dir' in param_name.lower():
            path = filedialog.askdirectory()
        elif 'output' in param_name.lower():
            path = filedialog.asksaveasfilename()
        else:
            path = filedialog.askopenfilename()
        
        if path:
            var.set(path)

    def _execute(self):
        """Execute the tool function."""
        try:
            kwargs = {}
            for param in self.tool_info['parameters']:
                var = self.input_vars.get(param['name'])
                if var:
                    value = var.get()
                    
                    if param['required'] and (value is None or value == ""):
                        messagebox.showerror("Error", f"'{param['name']}' is required!")
                        return
                    
                    kwargs[param['name']] = value

            # Execute
            result = self.tool_info['function'](**kwargs)

            # Show result
            self.result_text.delete(1.0, tk.END)
            self.result_text.insert(tk.END, f"Success!\n\n{result}")

            if self.on_success:
                self.on_success()

        except Exception as e:
            self.result_text.delete(1.0, tk.END)
            self.result_text.insert(tk.END, f"Error:\n\n{str(e)}")
            messagebox.showerror("Error", str(e))