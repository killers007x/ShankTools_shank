import os
import ast
import importlib.util
import inspect
from tkinter import ttk, filedialog, messagebox
from typing import Callable, Dict, List, Any

# Store registered tool metadata
_registered_tools = {}


def tool(name: str = None, description: str = "", icon: str = "Tool", category: str = "General"):
    """
    Decorator to register a function as a tool.

    Usage:
    @tool(name="Image Converter", description="Converts PNG to KTEX", category="Media")
    def convert_image(input_file: str, output_format: str = "ktex"):
        pass
    """
    def decorator(func: Callable):
        func._tool_info = {
            'name': name or func.__name__.replace('_', ' ').title(),
            'description': description or func.__doc__ or "No description available.",
            'icon': icon,
            'category': category,
            'function': func,
            'parameters': _extract_parameters(func)
        }
        return func
    return decorator


def _extract_parameters(func: Callable) -> List[Dict]:
    """Extract parameter metadata from a function signature."""
    params = []
    sig = inspect.signature(func)
    type_hints = getattr(func, '__annotations__', {})
    
    for param_name, param in sig.parameters.items():
        param_type = type_hints.get(param_name, str)
        default_value = None if param.default == inspect.Parameter.empty else param.default
        is_required = param.default == inspect.Parameter.empty
        
        param_info = {
            'name': param_name,
            'type': param_type,
            'default': default_value,
            'required': is_required
        }
        params.append(param_info)
    
    return params


class PluginLoader:
    """Automatic plugin loader for tool-based extensions."""

    def __init__(self, plugins_folder: str = "plugins"):
        self.plugins_folder = plugins_folder
        self.loaded_plugins = {}  # {plugin_name: [tool_info_dict, ...]}
        
    def discover_and_load(self) -> Dict[str, List[Dict]]:
        """Discover and load all plugin files from the plugins folder."""
        if not os.path.exists(self.plugins_folder):
            os.makedirs(self.plugins_folder)
            self._create_example_plugin()
            
        self.loaded_plugins.clear()
        
        for filename in os.listdir(self.plugins_folder):
            if filename.endswith('.py') and not filename.startswith('_'):
                plugin_name = filename[:-3]
                tools = self._load_plugin(plugin_name)
                if tools:
                    self.loaded_plugins[plugin_name] = tools
                    
        return self.loaded_plugins
    
    def _load_plugin(self, plugin_name: str) -> List[Dict]:
        """Load a single plugin module and extract its registered tools."""
        try:
            plugin_path = os.path.join(self.plugins_folder, f"{plugin_name}.py")
            
            # Load the module dynamically
            spec = importlib.util.spec_from_file_location(plugin_name, plugin_path)
            if spec is None or spec.loader is None:
                print(f"Skipping invalid plugin: {plugin_name}")
                return []
                
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # Find all functions decorated with @tool
            tools = []
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if callable(attr) and hasattr(attr, '_tool_info'):
                    tools.append(attr._tool_info)
                    
            return tools
            
        except Exception as e:
            print(f"Error loading plugin '{plugin_name}': {e}")
            return []
    
    def _create_example_plugin(self):
        """Generate a sample plugin file to guide users."""
        example_content = '''"""
            Example plugin - you may modify or delete this file.
            Place your own .py files in this folder to register tools.
            """
            from plugin_system import tool

            @tool(name="Sample Tool", description="A demonstration tool", category="Examples")
            def sample_tool(input_file: str, mode: str = "default"):
                """
                A simple example tool.
                In a real plugin, this would perform some useful operation.
                """
                print(f"Running sample tool on: {input_file} | Mode: {mode}")
                return {"status": "success", "input": input_file, "mode": mode}
                '''
        example_path = os.path.join(self.plugins_folder, "_example.py.txt")
        with open(example_path, 'w', encoding='utf-8') as f:
            f.write(example_content)