"""Scratch script to perform complete codebase inventory and import analysis."""

import os
import glob
import ast

project_root = r"C:\Users\lovsh\Desktop\FieldSense"
python_files = glob.glob(os.path.join(project_root, "**", "*.py"), recursive=True)

print(f"Total Python files found: {len(python_files)}")

imports_map = {}
for file_path in python_files:
    rel_path = os.path.relpath(file_path, project_root)
    with open(file_path, "r", encoding="utf-8") as f:
        try:
            tree = ast.parse(f.read(), filename=file_path)
        except Exception as e:
            print(f"Error parsing {rel_path}: {e}")
            continue

    file_imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                file_imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                file_imports.append(node.module)
    imports_map[rel_path] = file_imports

print("\n--- Package Import References ---")
for path, imps in imports_map.items():
    fs_imps = [i for i in imps if "fieldsense" in i]
    if fs_imps:
        print(f"{path}: {fs_imps}")
