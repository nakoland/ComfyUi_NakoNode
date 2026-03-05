"""
@title: Nako Pose
@nickname: Nako Pose
@description: NakoPose Editor node for ComfyUI
"""

import os
import importlib
from os.path import join, isdir

version_code = [0, 1, 0]
print(f"### Loading: NakoPose Editor")

node_list = ["nako_server", "pose_editor"]

NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}

for module_name in node_list:
    imported_module = importlib.import_module(f"ComfyUi_NakoNode.py.{module_name}")
    NODE_CLASS_MAPPINGS.update(imported_module.NODE_CLASS_MAPPINGS)
    NODE_DISPLAY_NAME_MAPPINGS.update(imported_module.NODE_DISPLAY_NAME_MAPPINGS)

PRESETS_PATH = os.path.join(os.path.dirname(__file__), "./Presets")
os.makedirs(PRESETS_PATH, exist_ok=True)

WEB_DIRECTORY = "./js"
__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]

try:
    import cm_global
    cm_global.register_extension('Nako-Pose',
                                 {'version': version_code,
                                  'name': 'Nako Pose',
                                  'nodes': set(NODE_CLASS_MAPPINGS.keys()),
                                  'description': 'NakoPose Editor node for ComfyUI'})
except:
    pass