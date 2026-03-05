import os
import json
import base64
import re
import nodes
from aiohttp import web
#from .prompt_preset import PromptPresetRandom,TextBuilderNako
from nako_nodes.py import wildcards
from server import PromptServer

max_seed = 2**32 - 1

def getPresetFile(nodeTitle):
    preset_file = os.path.join(os.path.dirname(__file__), f"../Presets/node_presets/{nodeTitle}.json")
    return preset_file

def getTbPresetFile(idx):
    return os.path.join(os.path.dirname(__file__), f"../Presets/LoraPreset{idx}.json")

def getPprPresetFile(idx):
    return os.path.join(os.path.dirname(__file__), f"../Presets/Preset{idx}.json")

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

@PromptServer.instance.routes.get("/nako/get_lbw_presets")
async def get_lbw_presets(request):
    preset_path = os.path.join(os.path.dirname(__file__), "..", "Presets", "lbw-preset.txt")
    presets = {}
    if os.path.exists(preset_path):
        with open(preset_path, "r", encoding="utf-8") as f:
            for line in f:
                if ":" in line:
                    parts = line.strip().split(":", 1)
                    if len(parts) == 2: presets[parts[0]] = parts[1]
    return web.json_response(presets)

@PromptServer.instance.routes.get("/nako/tb_preset_data")
async def get_sll_preset_data(request):
    idx = int(request.rel_url.query.get('idx', '1'))
    node_class_name = f"TextBuilderNako{idx}"
    node_class = nodes.NODE_CLASS_MAPPINGS.get(node_class_name)
    if node_class:
        temp_instance = node_class()
        return web.json_response({
            "preset_data": temp_instance.preset_data,
        })
    else:
        return web.json_response({"preset_data": []}, status=404)

@PromptServer.instance.routes.get("/nako/ppr_item_preset_data")
async def get_ppr_preset_data(request):
    idx = int(request.rel_url.query.get('idx', '1'))
    node_class_name = f"PPR{idx}"
    node_class = nodes.NODE_CLASS_MAPPINGS.get(node_class_name)
    if node_class:
        #temp_instance = node_class()
        return web.json_response(node_class.preset_data)
    else:
        return web.json_response([], status=404)

# ppr측에서 refresh버튼을 눌렀을때 파이썬쪽 노드 업데이트 함수를 실행
@PromptServer.instance.routes.post("/nako/ppr_item_refresh_preset")
async def ppr_refresh_preset(request):
    try:
        # 요청에서 idx 추출
        data = await request.json()
        idx = data.get("idx", "1")
        node_class_name = f"PPR{idx}"
        node_class = nodes.NODE_CLASS_MAPPINGS.get(node_class_name)

        node_class.INPUT_TYPES()

        return web.json_response(node_class.preset_data)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


# ==== 버튼 프리셋 ====
@PromptServer.instance.routes.get("/nako/button_preset_titles")
async def get_preset_titles(request):
    nodeTitle = request.query.get("nodeTitle")
    if not nodeTitle:
        return web.json_response({"error": "nodeTitle is required"}, status=400)
    titles = []
    preset_file = getPresetFile(nodeTitle)
    if os.path.exists(preset_file):
        with open(preset_file, "r",encoding="utf-8") as file:
            try:
                data = json.load(file)
                titles = list(data.keys())
            except json.JSONDecodeError:
                pass
    return web.json_response(titles)

@PromptServer.instance.routes.get("/nako/button_preset_content/{nodeTitle}")
async def get_preset_content(request):
    # 경로 파라미터에서 nodeTitle 추출
    nodeTitle = request.match_info.get("nodeTitle")
    presetTitle = request.rel_url.query['presetTitle']

    # 필수 파라미터 검증
    if not nodeTitle or not presetTitle:
        return web.json_response({"error": "nodeTitle and title are required"}, status=400)

    content = ""
    preset_file = getPresetFile(nodeTitle)

    if os.path.exists(preset_file):
        with open(preset_file, "r",encoding="utf-8") as file:
            try:
                data = json.load(file)
                content = data.get(presetTitle, "")
            except json.JSONDecodeError:
                pass
    return web.json_response({"content": content})

@PromptServer.instance.routes.post("/nako/button_save_preset/{nodeTitle}")
async def save_preset(request):
    try:
        nodeTitle = request.match_info.get("nodeTitle")
        data = await request.json()
        
        title = data['title']
        content = data['content']
        
        preset_file = getPresetFile(nodeTitle)

        if os.path.exists(preset_file):
            with open(preset_file, "r", encoding="utf-8") as file:
                try:
                    presets = json.load(file)
                except json.JSONDecodeError as e:
                    print(f"JSON decode error: {e}, resetting presets")
                    presets = {}
        else:
            print(f"Preset file does not exist, creating new: {preset_file}")
            presets = {}

        if title in presets:
            print(f"Removing existing preset with title: {title}")
            del presets[title]

        new_presets = {title: content}
        new_presets.update(presets)
        print(f"Saving new presets: {new_presets}")

        with open(preset_file, "w", encoding="utf-8") as file:
            json.dump(new_presets, file, indent=4, ensure_ascii=False)
            print(f"Successfully saved to {preset_file}")

        return web.Response(status=200)
    except Exception as e:
        print(f"Error saving preset: {e}")
        return web.Response(status=500, text=str(e))
@PromptServer.instance.routes.delete("/nako/button_delete_preset/{node_class}")
async def delete_preset(request):
    try:
        node_class = request.match_info.get("node_class")
        preset_title = request.query.get("presetTitle")

        if not node_class or not preset_title:
            return web.json_response({"error": "Missing node_class or presetTitle"}, status=400)

        preset_file = getPresetFile(node_class)

        if not os.path.exists(preset_file):
            return web.json_response({"error": "Preset file does not exist"}, status=404)

        with open(preset_file, "r", encoding="utf-8") as f:
            try:
                presets = json.load(f)
            except json.JSONDecodeError:
                return web.json_response({"error": "Invalid preset file"}, status=500)

        if preset_title not in presets:
            return web.json_response({"error": f"'{preset_title}' not found"}, status=404)

        # 삭제 수행
        del presets[preset_title]

        with open(preset_file, "w", encoding="utf-8") as f:
            json.dump(presets, f, indent=4, ensure_ascii=False)

        return web.json_response({"message": f"Preset '{preset_title}' deleted."})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

@PromptServer.instance.routes.get("/nako/ppr_preset_titles")
async def get_ppr_preset_titles(request):
    try:
        idx = int(request.rel_url.query.get("idx", "1"))
        preset_file = getPprPresetFile(idx)
        titles = []
        if os.path.exists(preset_file):
            with open(preset_file, "r", encoding="utf-8") as f:
                try:
                    data = json.load(f)
                    titles = list(data.keys())
                except json.JSONDecodeError:
                    titles = []
        return web.json_response(titles)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

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

@PromptServer.instance.routes.post("/nako/ppr_save_preset/{idx}")
async def ppr_save_preset(request):
    try:
        idx = int(request.match_info.get("idx"))
        data = await request.json()
        title = (data.get("title") or "").strip()
        content = data.get("content", "")
        insert_before = (data.get("insertBefore") or "__TOP__").strip()
        if not title:
            return web.json_response({"error": "title is required"}, status=400)

        preset_file = getPprPresetFile(idx)
        presets = {}
        if os.path.exists(preset_file):
            with open(preset_file, "r", encoding="utf-8") as f:
                try:
                    presets = json.load(f)
                except json.JSONDecodeError:
                    presets = {}

        if title in presets:
            del presets[title]

        items = list(presets.items())
        new_presets = {}
        inserted = False

        if insert_before == "__BOTTOM__":
            new_presets = dict(items)
            new_presets[title] = content
            inserted = True
        elif insert_before == "__TOP__":
            new_presets[title] = content
            for k, v in items:
                new_presets[k] = v
            inserted = True
        else:
            for k, v in items:
                if (not inserted) and k == insert_before:
                    new_presets[title] = content
                    inserted = True
                new_presets[k] = v
            if not inserted:
                new_presets[title] = content

        with open(preset_file, "w", encoding="utf-8") as f:
            json.dump(new_presets, f, indent=4, ensure_ascii=False)

        node_class_name = f"PPR{idx}"
        node_class = nodes.NODE_CLASS_MAPPINGS.get(node_class_name)
        if node_class:
            node_class.INPUT_TYPES()

        return web.json_response({"message": "saved"})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

@PromptServer.instance.routes.post("/nako/ppr_rename_preset/{idx}")
async def ppr_rename_preset(request):
    try:
        idx = int(request.match_info.get("idx"))
        data = await request.json()
        old_title = (data.get("oldTitle") or "").strip()
        new_title = (data.get("newTitle") or "").strip()
        if not old_title or not new_title:
            return web.json_response({"error": "oldTitle and newTitle are required"}, status=400)

        preset_file = getPprPresetFile(idx)
        if not os.path.exists(preset_file):
            return web.json_response({"error": "Preset file does not exist"}, status=404)

        with open(preset_file, "r", encoding="utf-8") as f:
            try:
                presets = json.load(f)
            except json.JSONDecodeError:
                return web.json_response({"error": "Invalid preset file"}, status=500)

        if old_title not in presets:
            return web.json_response({"error": f"'{old_title}' not found"}, status=404)

        value = presets[old_title]
        renamed = {}
        for key, val in presets.items():
            if key == old_title:
                renamed[new_title] = value
            elif key != new_title:
                renamed[key] = val

        with open(preset_file, "w", encoding="utf-8") as f:
            json.dump(renamed, f, indent=4, ensure_ascii=False)

        node_class_name = f"PPR{idx}"
        node_class = nodes.NODE_CLASS_MAPPINGS.get(node_class_name)
        if node_class:
            node_class.INPUT_TYPES()

        return web.json_response({"message": "renamed"})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

@PromptServer.instance.routes.post("/nako/ppr_update_preset/{idx}")
async def ppr_update_preset(request):
    try:
        idx = int(request.match_info.get("idx"))
        data = await request.json()
        old_title = (data.get("oldTitle") or "").strip()
        new_title = (data.get("newTitle") or "").strip()
        content = data.get("content", "")
        if not old_title or not new_title:
            return web.json_response({"error": "oldTitle and newTitle are required"}, status=400)

        preset_file = getPprPresetFile(idx)
        if not os.path.exists(preset_file):
            return web.json_response({"error": "Preset file does not exist"}, status=404)

        with open(preset_file, "r", encoding="utf-8") as f:
            try:
                presets = json.load(f)
            except json.JSONDecodeError:
                return web.json_response({"error": "Invalid preset file"}, status=500)

        if old_title not in presets:
            return web.json_response({"error": f"'{old_title}' not found"}, status=404)

        updated = {}
        inserted_new = False
        for key, val in presets.items():
            if key == old_title:
                updated[new_title] = content
                inserted_new = True
            elif key == new_title:
                continue
            else:
                updated[key] = val

        if not inserted_new:
            updated[new_title] = content

        with open(preset_file, "w", encoding="utf-8") as f:
            json.dump(updated, f, indent=4, ensure_ascii=False)

        node_class_name = f"PPR{idx}"
        node_class = nodes.NODE_CLASS_MAPPINGS.get(node_class_name)
        if node_class:
            node_class.INPUT_TYPES()

        return web.json_response({"message": "updated"})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

@PromptServer.instance.routes.delete("/nako/ppr_delete_preset/{idx}")
async def ppr_delete_preset(request):
    try:
        idx = int(request.match_info.get("idx"))
        preset_title = (request.query.get("presetTitle") or "").strip()
        if not preset_title:
            return web.json_response({"error": "presetTitle is required"}, status=400)

        preset_file = getPprPresetFile(idx)
        if not os.path.exists(preset_file):
            return web.json_response({"error": "Preset file does not exist"}, status=404)

        with open(preset_file, "r", encoding="utf-8") as f:
            try:
                presets = json.load(f)
            except json.JSONDecodeError:
                return web.json_response({"error": "Invalid preset file"}, status=500)

        if preset_title not in presets:
            return web.json_response({"error": f"'{preset_title}' not found"}, status=404)

        del presets[preset_title]
        with open(preset_file, "w", encoding="utf-8") as f:
            json.dump(presets, f, indent=4, ensure_ascii=False)

        node_class_name = f"PPR{idx}"
        node_class = nodes.NODE_CLASS_MAPPINGS.get(node_class_name)
        if node_class:
            node_class.INPUT_TYPES()

        return web.json_response({"message": "deleted"})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


@PromptServer.instance.routes.post("/nako/button_rename_preset/{node_class}")
async def rename_preset(request):
    try:
        node_class = request.match_info.get("node_class")
        data = await request.json()
        old_title = (data.get("oldTitle") or "").strip()
        new_title = (data.get("newTitle") or "").strip()

        if not node_class or not old_title or not new_title:
            return web.json_response({"error": "Missing node_class, oldTitle, or newTitle"}, status=400)

        preset_file = getPresetFile(node_class)
        if not os.path.exists(preset_file):
            return web.json_response({"error": "Preset file does not exist"}, status=404)

        with open(preset_file, "r", encoding="utf-8") as f:
            try:
                presets = json.load(f)
            except json.JSONDecodeError:
                return web.json_response({"error": "Invalid preset file"}, status=500)

        if old_title not in presets:
            return web.json_response({"error": f"'{old_title}' not found"}, status=404)

        value = presets[old_title]
        renamed = {}
        for key, val in presets.items():
            if key == old_title:
                renamed[new_title] = value
            elif key != new_title:
                renamed[key] = val

        with open(preset_file, "w", encoding="utf-8") as f:
            json.dump(renamed, f, indent=4, ensure_ascii=False)

        return web.json_response({"message": f"Preset '{old_title}' renamed to '{new_title}'."})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


@PromptServer.instance.routes.post("/nako/tb_save_preset/{idx}")
async def tb_save_preset(request):
    try:
        idx = int(request.match_info.get("idx"))
        data = await request.json()
        title = (data.get("title") or "").strip()
        content = data.get("content", "")

        if not title:
            return web.json_response({"error": "title is required"}, status=400)

        preset_file = getTbPresetFile(idx)
        presets = {}
        if os.path.exists(preset_file):
            with open(preset_file, "r", encoding="utf-8") as f:
                try:
                    presets = json.load(f)
                except json.JSONDecodeError:
                    presets = {}

        if title in presets:
            del presets[title]

        # Insert new preset at 2nd position (keep current first entry as-is).
        if not presets:
            new_presets = {title: content}
        else:
            items = list(presets.items())
            first_key, first_value = items[0]
            new_presets = {first_key: first_value, title: content}
            for key, value in items[1:]:
                new_presets[key] = value

        with open(preset_file, "w", encoding="utf-8") as f:
            json.dump(new_presets, f, indent=4, ensure_ascii=False)

        return web.json_response({"message": "saved"})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


@PromptServer.instance.routes.post("/nako/tb_rename_preset/{idx}")
async def tb_rename_preset(request):
    try:
        idx = int(request.match_info.get("idx"))
        data = await request.json()
        old_title = (data.get("oldTitle") or "").strip()
        new_title = (data.get("newTitle") or "").strip()

        if not old_title or not new_title:
            return web.json_response({"error": "oldTitle and newTitle are required"}, status=400)

        preset_file = getTbPresetFile(idx)
        if not os.path.exists(preset_file):
            return web.json_response({"error": "Preset file does not exist"}, status=404)

        with open(preset_file, "r", encoding="utf-8") as f:
            try:
                presets = json.load(f)
            except json.JSONDecodeError:
                return web.json_response({"error": "Invalid preset file"}, status=500)

        if old_title not in presets:
            return web.json_response({"error": f"'{old_title}' not found"}, status=404)

        value = presets[old_title]
        renamed = {}
        for key, val in presets.items():
            if key == old_title:
                renamed[new_title] = value
            elif key != new_title:
                renamed[key] = val

        with open(preset_file, "w", encoding="utf-8") as f:
            json.dump(renamed, f, indent=4, ensure_ascii=False)

        return web.json_response({"message": "renamed"})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


@PromptServer.instance.routes.delete("/nako/tb_delete_preset/{idx}")
async def tb_delete_preset(request):
    try:
        idx = int(request.match_info.get("idx"))
        preset_title = (request.query.get("presetTitle") or "").strip()

        if not preset_title:
            return web.json_response({"error": "presetTitle is required"}, status=400)

        preset_file = getTbPresetFile(idx)
        if not os.path.exists(preset_file):
            return web.json_response({"error": "Preset file does not exist"}, status=404)

        with open(preset_file, "r", encoding="utf-8") as f:
            try:
                presets = json.load(f)
            except json.JSONDecodeError:
                return web.json_response({"error": "Invalid preset file"}, status=500)

        if preset_title not in presets:
            return web.json_response({"error": f"'{preset_title}' not found"}, status=404)

        del presets[preset_title]
        with open(preset_file, "w", encoding="utf-8") as f:
            json.dump(presets, f, indent=4, ensure_ascii=False)

        return web.json_response({"message": "deleted"})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

def oncontrol_random_preset():
    PromptServer.instance.send_sync("nako-controlnode-randompreset")

# queue Prompt 버튼 클릭 이벤트시 실행되는 리스너
def onprompt(json_data):
    return json_data


PromptServer.instance.add_on_prompt_handler(onprompt)

NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}

