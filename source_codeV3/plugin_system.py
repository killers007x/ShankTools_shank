"""
Advanced Plugin System with @tool decorator
"""
import os
import inspect
import importlib.util
from typing import Callable, Dict, List, Any


def tool(name: str = None, description: str = "", icon: str = "<#>", category: str = "General"): # this code is for regist your tool to app as plugin
    """
    Decorator to register a function as a tool.
    
    Usage: 
        @tool(name="My Tool", description="Does something", category="Utils")
        def my_tool(input_file: str, option: bool = False):
            pass
    """ # end regist here
    def decorator(func: Callable):
        func._tool_info = {
            'name': name or func.__name__.replace('_', ' ').title(),
            'description': description or func.__doc__ or "No description",
            'icon': icon,
            'category': category,
            'function': func,
            'parameters': _extract_parameters(func)
        }
        return func
    return decorator


def _extract_parameters(func: Callable) -> List[Dict]:
    """Extract parameter info from function signature."""
    params = []
    sig = inspect.signature(func)
    type_hints = getattr(func, '__annotations__', {})

    for param_name, param in sig.parameters.items():
        if param_name in ('app', 'self'):
            continue
            
        param_type = type_hints.get(param_name, str)
        default = None if param.default == inspect.Parameter.empty else param.default
        required = param.default == inspect.Parameter.empty

        params.append({
            'name': param_name,
            'type': param_type,
            'default': default,
            'required': required
        })

    return params


class AdvancedPluginLoader:
    """Loader for @tool decorated plugins."""

    def __init__(self, plugins_folder: str = "plugins"):
        self.plugins_folder = plugins_folder
        self.loaded_tools = {}  # {plugin_name: [tool_info, ...]}

    def discover_and_load(self) -> Dict[str, List[Dict]]:
        """Load all plugins and extract @tool functions."""
        if not os.path.exists(self.plugins_folder):
            os.makedirs(self.plugins_folder)

        self.loaded_tools.clear()

        for filename in os.listdir(self.plugins_folder):
            if filename.endswith('.py') and not filename.startswith('_'):
                plugin_name = filename[:-3]
                tools = self._load_plugin(plugin_name)
                if tools:
                    self.loaded_tools[plugin_name] = tools

        return self.loaded_tools

    def _load_plugin(self, plugin_name: str) -> List[Dict]:
        """Load single plugin and extract tools."""
        try:
            plugin_path = os.path.join(self.plugins_folder, f"{plugin_name}.py")
            spec = importlib.util.spec_from_file_location(plugin_name, plugin_path)
            
            if spec is None or spec.loader is None:
                return []

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            tools = []
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if callable(attr) and hasattr(attr, '_tool_info'):
                    tools.append(attr._tool_info)

            return tools

        except Exception as e:
            print(f"Error loading '{plugin_name}': {e}")
            return []

    def get_all_tools(self) -> List[Dict]:
        """Get flat list of all tools."""
        all_tools = []
        for tools in self.loaded_tools.values():
            all_tools.extend(tools)
        return all_tools

    def get_tools_by_category(self) -> Dict[str, List[Dict]]:
        """Get tools grouped by category."""
        categories = {}
        for tools in self.loaded_tools.values():
            for tool_info in tools:
                cat = tool_info.get('category', 'General')
                if cat not in categories:
                    categories[cat] = []
                categories[cat].append(tool_info)
        return categories