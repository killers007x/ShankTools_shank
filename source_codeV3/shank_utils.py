"""
Shank Game Utilities Plugin
"""
from plugin_system import tool
import os


@tool(
    name="TEX Info",
    description="Display TEX file information",
    icon="ℹ",
    category="Shank Tools"
)
def tex_info(input_file: str):
    """Read and display TEX file header info."""
    if not os.path.exists(input_file):
        return f"File not found: {input_file}"
    
    with open(input_file, 'rb') as f:
        magic = f.read(4)
        version = int.from_bytes(f.read(4), 'little')
        width = int.from_bytes(f.read(4), 'little')
        height = int.from_bytes(f.read(4), 'little')
    
    return f"""TEX File Info:
    
Magic: {magic}
Version: {version}
Size: {width} x {height}
File: {os.path.basename(input_file)}"""


@tool(
    name="Batch Backup",
    description="Create backup of game files",
    icon="{[P]}",
    category="Shank Tools"
)
def batch_backup(source_folder: str, backup_suffix: str = "_backup"):
    """Create backup copies of files."""
    import shutil
    from pathlib import Path
    
    src = Path(source_folder)
    if not src.exists():
        return "Folder not found!"
    
    backup_folder = src.parent / f"{src.name}{backup_suffix}"
    
    if backup_folder.exists():
        return f"Backup already exists: {backup_folder}"
    
    shutil.copytree(src, backup_folder)
    
    file_count = len(list(backup_folder.rglob('*')))
    return f"Backup created!\n\nLocation: {backup_folder}\nFiles: {file_count}"