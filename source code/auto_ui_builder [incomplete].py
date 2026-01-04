import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from typing import Dict, List, Any, Callable


class AutoUIBuilder:
    """Auto UI builder based on tool definitions."""

    # Mapping Python types to UI widget types
    TYPE_WIDGETS = {
        str: 'entry',
        int: 'spinbox',
        float: 'spinbox',
        bool: 'checkbox',
        list: 'combobox',
    }

    def __init__(self, parent: tk.Widget):
        self.parent = parent
        self.input_widgets = {}  # Store input widgets

    def build_tool_frame(self, tool_info: Dict) -> ttk.Frame:
        """Build a complete frame for a tool."""
        frame = ttk.Frame(self.parent)

        # Header section
        header = ttk.Frame(frame)
        header.pack(fill='x', pady=(0, 15))

        icon_label = ttk.Label(header, text=tool_info['icon'], font=('Arial', 24))
        icon_label.pack(side='left')

        title_frame = ttk.Frame(header)
        title_frame.pack(side='left', padx=10)

        ttk.Label(title_frame, text=tool_info['name'],
                  font=('Arial', 16, 'bold')).pack(anchor='w')
        ttk.Label(title_frame, text=tool_info['description'],
                  font=('Arial', 10)).pack(anchor='w')

        # Separator line
        ttk.Separator(frame, orient='horizontal').pack(fill='x', pady=10)

        # Input section
        inputs_frame = ttk.LabelFrame(frame, text="⚙️ Settings", padding=10)
        inputs_frame.pack(fill='x', padx=10, pady=5)

        self.input_widgets[tool_info['name']] = {}

        for param in tool_info['parameters']:
            self._create_input_widget(inputs_frame, param, tool_info['name'])

        # Execute button
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill='x', padx=10, pady=20)

        execute_btn = ttk.Button(
            btn_frame,
            text=f"Run {tool_info['name']}",
            command=lambda: self._execute_tool(tool_info)
        )
        execute_btn.pack(side='left')

        # Results section
        result_frame = ttk.LabelFrame(frame, text="Results", padding=10)
        result_frame.pack(fill='both', expand=True, padx=10, pady=5)

        self.result_text = tk.Text(result_frame, height=8, wrap='word')
        self.result_text.pack(fill='both', expand=True)

        return frame

    def _create_input_widget(self, parent: ttk.Frame, param: Dict, tool_name: str):
        """Create an input widget based on the parameter type."""
        row = ttk.Frame(parent)
        row.pack(fill='x', pady=5)

        # Label
        label_text = param['name'].replace('_', ' ').title()
        if param['required']:
            label_text += " *"
        ttk.Label(row, text=label_text, width=20).pack(side='left')

        param_type = param['type']
        default = param.get('default', None)

        # Determine widget type
        if param_type == bool:
            var = tk.BooleanVar(value=default if default is not None else False)
            widget = ttk.Checkbutton(row, variable=var)
            widget.pack(side='left')
            self.input_widgets[tool_name][param['name']] = var

        elif param_type == int:
            var = tk.IntVar(value=default if default is not None else 0)
            widget = ttk.Spinbox(row, from_=-9999, to=9999, textvariable=var, width=15)
            widget.pack(side='left')
            self.input_widgets[tool_name][param['name']] = var

        elif param_type == float:
            var = tk.DoubleVar(value=default if default is not None else 0.0)
            widget = ttk.Spinbox(row, from_=-9999.0, to=9999.0, increment=0.1,
                                 textvariable=var, width=15)
            widget.pack(side='left')
            self.input_widgets[tool_name][param['name']] = var

        elif param_type == list or (hasattr(param_type, '__origin__') and param_type.__origin__ == list):
            options = default if isinstance(default, list) else []
            var = tk.StringVar(value=options[0] if options else "")
            widget = ttk.Combobox(row, textvariable=var, values=options, width=20)
            widget.pack(side='left')
            self.input_widgets[tool_name][param['name']] = var

        else:  # str or any other type
            var = tk.StringVar(value=default if default is not None else "")

            # If parameter name suggests a file/path, add a browse button
            if any(x in param['name'].lower() for x in ['file', 'path', 'input', 'output']):
                entry = ttk.Entry(row, textvariable=var, width=40)
                entry.pack(side='left', padx=(0, 5))

                ttk.Button(row, text="Browse", width=8,
                           command=lambda v=var: self._browse_file(v)).pack(side='left')
            else:
                entry = ttk.Entry(row, textvariable=var, width=45)
                entry.pack(side='left')

            self.input_widgets[tool_name][param['name']] = var

    def _browse_file(self, var: tk.StringVar):
        """Open file selection dialog."""
        filename = filedialog.askopenfilename()
        if filename:
            var.set(filename)

    def _execute_tool(self, tool_info: Dict):
        """Execute the tool with the provided inputs."""
        try:
            # Gather input values
            kwargs = {}
            for param in tool_info['parameters']:
                var = self.input_widgets[tool_info['name']].get(param['name'])
                if var is not None:
                    value = var.get()
                    # Check required fields
                    if param['required'] and (value is None or value == "" or (isinstance(value, str) and not value.strip())):
                        messagebox.showerror("Error", f"Field '{param['name']}' is required!")
                        return
                    kwargs[param['name']] = value

            # Call the tool function
            result = tool_info['function'](**kwargs)

            # Display result
            self.result_text.delete(1.0, tk.END)
            self.result_text.insert(tk.END, f"Execution succeeded!\n\n{result}")

        except Exception as e:
            self.result_text.delete(1.0, tk.END)
            self.result_text.insert(tk.END, f"Error: {str(e)}")
            messagebox.showerror("Error", str(e))