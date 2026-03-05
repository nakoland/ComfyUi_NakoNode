# ComfyUi_NakoNode

Custom node package for ComfyUI that provides an interactive OpenPose editor node with optional ControlNet conditioning.

## Features

- Interactive pose editor UI inside ComfyUI
- Outputs pose image, keypoints, and pose JSON
- Optional ControlNet apply flow from the same node
- Preset-based pose loading
- `pose_tag_input` parser: `<pose-PRESET:STRENGTH:START%:END%>`
- ex - <pose-standing:0.7:0:70>

## Requirements

- ComfyUI
- Python packages from `requirements.txt`:
  - `numpy`
  - `opencv-python`
  - `torch`
  - `matplotlib`

## Installation

1. Clone or copy this repository into your ComfyUI custom nodes directory:
   - `ComfyUI/custom_nodes/ComfyUi_NakoNode`
2. Install dependencies in your ComfyUI environment:
   - `pip install -r ComfyUI/custom_nodes/ComfyUi_NakoNode/requirements.txt`
3. Restart ComfyUI.

## Node

- Class name: `NakoOpenPoseEditor`
- Display name in UI: `OpenPose Editor(nako)`
- Category: `Nako/Pose`

## Basic Usage

1. Add `OpenPose Editor(nako)` to your workflow.
2. Open the editor from the node UI and build or adjust a pose.
3. Click **Send To Node** in the editor.
4. Use outputs:
   - `POSE_IMAGE` for ControlNet or preview pipelines
   - `POSE_KEYPOINT` to pass pose data between nodes
   - `POSE_JSON` for text-based pose workflows
5. If needed, connect `positive` and `negative` conditioning to let this node apply ControlNet directly.

## Inputs and Outputs

### Main optional inputs

- `background_image`: reference image in editor
- `POSE_JSON`: pose JSON text
- `POSE_KEYPOINT`: pose keypoint object
- `pose_json_input`: external JSON string input
- `pose_input_enabled`: switch for external pose input handling
- `positive`, `negative`: conditioning inputs for ControlNet apply
- `controlnet_enabled`, `controlnet_model`, `controlnet_strength`, `controlnet_start_percent`, `controlnet_end_percent`
- `pose_tag_input`: tag parser input

### Outputs

- `POSE_IMAGE`
- `POSE_KEYPOINT`
- `POSE_JSON`
- `positive`
- `negative`
- `cnet_info`

## pose_tag_input Syntax

Format:

```text
<pose-PRESET_NAME:STRENGTH:START_PERCENT:END_PERCENT>
```

Examples:

```text
<pose-standing>
<pose-standing:1.0>
<pose-standing:0.9:0:70>
```

Notes:

- `PRESET_NAME` is loaded from `Presets/openpose-preset.json`.
- If a valid pose tag is provided, preset pose data is prioritized.
- Numeric values are optional; omitted fields keep node widget values.

## Preset Files

- Pose preset file:
  - `Presets/openpose-preset.json`
- Pose preset thumbnail assets:
  - `Presets/openpose-preset.json.assets/`

## Editor Controls (Quick)

- `Space + Drag`: pan
- `Mouse Wheel`: zoom
- `Shift + Click`: multi-select points
- `Drag empty area`: rectangle select
- `Ctrl + Z`: undo
- `Delete`: hide selected point/group

## Notes

- If `controlnet_model` is `none` (or missing), ControlNet is not applied.
- When pose input is empty or invalid, the node falls back to a default pose.

## Support

If this project helps your workflow, thank you for using Nako Pose.
Your support helps ongoing maintenance and future updates.

- USDT (TRON / TRC20): `THdCx981bTQtnJ98dFyhmmspFNwxo9Uv2D`

Thank you so much for your support.
