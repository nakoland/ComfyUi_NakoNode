import os
import json
import base64
import re
from aiohttp import web
from server import PromptServer


def getPosePresetFile():
    return os.path.join(os.path.dirname(__file__), "../Presets/openpose-preset.json")

def getPosePresetAssetDir():
    return os.path.join(os.path.dirname(__file__), "../Presets/openpose-preset.json.assets")

def getPosePresetThumbIndexFile():
    return os.path.join(getPosePresetAssetDir(), "thumb_index.json")

def ensure_pose_preset_file():
    preset_file = getPosePresetFile()
    preset_dir = os.path.dirname(preset_file)
    os.makedirs(preset_dir, exist_ok=True)

    defaults = {"OpenPose(refresh)": ""}
    if not os.path.exists(preset_file):
        with open(preset_file, "w", encoding="utf-8") as f:
            json.dump(defaults, f, indent=4, ensure_ascii=False)
        return preset_file, defaults

    with open(preset_file, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
            if not isinstance(data, dict):
                data = {}
        except json.JSONDecodeError:
            data = {}

    if "OpenPose(refresh)" not in data:
        merged = {"OpenPose(refresh)": ""}
        for k, v in data.items():
            merged[k] = v
        data = merged
        with open(preset_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

    return preset_file, data

def ensure_pose_thumb_index():
    asset_dir = getPosePresetAssetDir()
    os.makedirs(asset_dir, exist_ok=True)
    index_file = getPosePresetThumbIndexFile()
    if not os.path.exists(index_file):
        with open(index_file, "w", encoding="utf-8") as f:
            json.dump({}, f, indent=4, ensure_ascii=False)
        return {}
    with open(index_file, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}

def write_pose_thumb_index(index_data):
    os.makedirs(getPosePresetAssetDir(), exist_ok=True)
    with open(getPosePresetThumbIndexFile(), "w", encoding="utf-8") as f:
        json.dump(index_data, f, indent=4, ensure_ascii=False)

def safe_filename(text):
    s = re.sub(r"[^\w\-가-힣]+", "_", (text or "").strip())
    s = s.strip("_")
    return s[:80] if s else "preset"

def save_pose_thumbnail_data_url(title, data_url):
    if not data_url or not isinstance(data_url, str) or not data_url.startswith("data:image/"):
        return None
    try:
        header, b64 = data_url.split(",", 1)
        mime = header.split(";", 1)[0].replace("data:", "").strip().lower()
        ext_map = {
            "image/png": ".png",
            "image/webp": ".webp",
            "image/jpeg": ".jpg",
            "image/jpg": ".jpg",
        }
        ext = ext_map.get(mime, ".png")
        raw = base64.b64decode(b64)
    except Exception:
        return None
    asset_dir = getPosePresetAssetDir()
    os.makedirs(asset_dir, exist_ok=True)
    name = f"{safe_filename(title)}{ext}"
    path = os.path.join(asset_dir, name)
    with open(path, "wb") as f:
        f.write(raw)
    return name

def thumbnail_to_data_url(filename):
    if not filename:
        return ""
    path = os.path.join(getPosePresetAssetDir(), filename)
    if not os.path.exists(path):
        return ""
    try:
        with open(path, "rb") as f:
            raw = f.read()
        b64 = base64.b64encode(raw).decode("ascii")
        ext = os.path.splitext(filename)[1].lower()
        mime = "image/png"
        if ext == ".webp":
            mime = "image/webp"
        elif ext in (".jpg", ".jpeg"):
            mime = "image/jpeg"
        return f"data:{mime};base64,{b64}"
    except Exception:
        return ""


@PromptServer.instance.routes.get("/nako_openpose/pose_preset_titles")
async def get_pose_preset_titles(request):
    try:
        _, data = ensure_pose_preset_file()
        return web.json_response(list(data.keys()))
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

@PromptServer.instance.routes.get("/nako_openpose/pose_preset_content")
async def get_pose_preset_content(request):
    try:
        title = (request.rel_url.query.get("presetTitle") or "").strip()
        if not title:
            return web.json_response({"error": "presetTitle is required"}, status=400)
        _, data = ensure_pose_preset_file()
        return web.json_response({"content": data.get(title, "")})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

@PromptServer.instance.routes.get("/nako_openpose/pose_preset_thumbnails")
async def get_pose_preset_thumbnails(request):
    try:
        _, preset_data = ensure_pose_preset_file()
        idx = ensure_pose_thumb_index()
        out = {}
        for title in preset_data.keys():
            out[title] = thumbnail_to_data_url(idx.get(title, ""))
        return web.json_response(out)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

@PromptServer.instance.routes.post("/nako_openpose/pose_save_preset")
async def pose_save_preset(request):
    try:
        payload = await request.json()
        title = (payload.get("title") or "").strip()
        content = payload.get("content", "")
        insert_before = (payload.get("insertBefore") or "__TOP__").strip()
        thumbnail_data_url = payload.get("thumbnailDataUrl", "")
        if not title:
            return web.json_response({"error": "title is required"}, status=400)
        if title == "OpenPose(refresh)":
            return web.json_response({"error": "'OpenPose(refresh)' is reserved"}, status=400)

        preset_file, presets = ensure_pose_preset_file()
        if title in presets:
            del presets[title]

        # Keep symbolic header out of insertion list; it must always remain first.
        symbolic_value = presets.get("OpenPose(refresh)", "")
        body_items = [(k, v) for k, v in presets.items() if k != "OpenPose(refresh)"]
        new_presets = {}
        inserted = False

        # Never allow insertion before symbolic header.
        if insert_before == "OpenPose(refresh)":
            insert_before = "__TOP__"

        if insert_before == "__BOTTOM__":
            new_presets = dict(body_items)
            new_presets[title] = content
            inserted = True
        elif insert_before == "__TOP__":
            # "__TOP__" means top of actual presets, i.e. just below "OpenPose(refresh)".
            new_presets[title] = content
            for k, v in body_items:
                new_presets[k] = v
            inserted = True
        else:
            for k, v in body_items:
                if (not inserted) and k == insert_before:
                    new_presets[title] = content
                    inserted = True
                new_presets[k] = v
            if not inserted:
                new_presets[title] = content

        # Rebuild with symbolic first.
        merged = {"OpenPose(refresh)": symbolic_value}
        for k, v in new_presets.items():
            merged[k] = v

        with open(preset_file, "w", encoding="utf-8") as f:
            json.dump(merged, f, indent=4, ensure_ascii=False)

        thumb_idx = ensure_pose_thumb_index()
        saved_thumb = save_pose_thumbnail_data_url(title, thumbnail_data_url)
        if saved_thumb:
            thumb_idx[title] = saved_thumb
            write_pose_thumb_index(thumb_idx)

        return web.json_response({"message": "saved"})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

@PromptServer.instance.routes.delete("/nako_openpose/pose_delete_preset")
async def pose_delete_preset(request):
    try:
        title = (request.rel_url.query.get("presetTitle") or "").strip()
        if not title:
            return web.json_response({"error": "presetTitle is required"}, status=400)
        if title == "OpenPose(refresh)":
            return web.json_response({"error": "'OpenPose(refresh)' cannot be deleted"}, status=400)

        preset_file, presets = ensure_pose_preset_file()
        if title not in presets:
            return web.json_response({"error": f"'{title}' not found"}, status=404)

        del presets[title]
        with open(preset_file, "w", encoding="utf-8") as f:
            json.dump(presets, f, indent=4, ensure_ascii=False)

        thumb_idx = ensure_pose_thumb_index()
        thumb_name = thumb_idx.pop(title, None)
        if thumb_name:
            thumb_path = os.path.join(getPosePresetAssetDir(), thumb_name)
            if os.path.exists(thumb_path):
                try:
                    os.remove(thumb_path)
                except OSError:
                    pass
            write_pose_thumb_index(thumb_idx)

        return web.json_response({"message": "deleted"})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}
