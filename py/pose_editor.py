import copy
import json
import math
import base64
import re
import os
import inspect

import cv2
import matplotlib
import numpy as np
import torch


class NakoPoseEditorNode:
    @classmethod
    def INPUT_TYPES(cls):
        try:
            import folder_paths
            cn_models = folder_paths.get_filename_list("controlnet") or ["none"]
        except Exception:
            cn_models = ["none"]

        return {
            "optional": {
                "background_image": ("IMAGE",),
                "pose_input_enabled": ("BOOLEAN", {"default": True}),
                "pose_json_input": ("STRING", {"forceInput": True, "multiline": False, "default": "", "tooltip": "Input OpenPose JSON string"}),
                "POSE_JSON": ("STRING", {"multiline": True, "default": ""}),
                "POSE_KEYPOINT": ("POSE_KEYPOINT", {"default": None}),
                "positive": ("CONDITIONING",),
                "negative": ("CONDITIONING",),
                "controlnet_enabled": ("BOOLEAN", {"default": True, "label_on": "On", "label_off": "Off"}),
                "controlnet_model": (cn_models,),
                "controlnet_strength": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 2.0, "step": 0.05, "display": "slider"}),
                "controlnet_start_percent": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 100.0, "step": 5.0, "display": "slider"}),
                "controlnet_end_percent": ("FLOAT", {"default": 100.0, "min": 0.0, "max": 100.0, "step": 5.0, "display": "slider"}),
                "pose_tag_input": ("STRING", {"forceInput": True, "multiline": False, "default": "", "tooltip": "<pose-프리셋명:강도:시작%:종료%> 태그 파서"}),
            }
        }

    RETURN_NAMES = ("POSE_IMAGE", "POSE_KEYPOINT", "POSE_JSON", "positive", "negative", "cnet_info")
    RETURN_TYPES = ("IMAGE", "POSE_KEYPOINT", "STRING", "CONDITIONING", "CONDITIONING", "STRING")
    OUTPUT_NODE = True
    FUNCTION = "load_pose"
    CATEGORY = "Nako/Pose"

    @staticmethod
    def _safe_json_loads(text):
        if not text:
            return None
        normalized = text.replace("'", '"').replace("None", "[]")
        try:
            return json.loads(normalized)
        except Exception:
            return None

    @staticmethod
    def _default_pose():
        w = 512
        h = 768
        return [{
            "people": [{
                "pose_keypoints_2d": [],
                "face_keypoints_2d": [],
                "hand_left_keypoints_2d": [],
                "hand_right_keypoints_2d": [],
            }],
            "canvas_height": h,
            "canvas_width": w,
        }]

    @staticmethod
    def _as_pose_list(obj):
        if obj is None:
            return None
        if isinstance(obj, dict):
            return [obj]
        if isinstance(obj, list):
            return obj
        return None

    @staticmethod
    def _normalize_points(points, w, h):
        if not isinstance(points, list) or not points:
            return []
        out = points[:]
        max_value = max(out)
        if max_value <= 2.0:
            return out
        for i in range(0, len(out), 3):
            out[i] = out[i] / float(w)
            out[i + 1] = out[i + 1] / float(h)
        return out

    @staticmethod
    def _scale_point(x, y, pivot_x, pivot_y, scale):
        return (x - pivot_x) * scale + pivot_x, (y - pivot_y) * scale + pivot_y

    @staticmethod
    def _as_number(value, default, caster=float):
        if value is None:
            return default
        try:
            return caster(value)
        except Exception:
            return default

    @staticmethod
    def _tensor_to_png_data_url(image_tensor):
        if image_tensor is None:
            return ""
        try:
            arr = image_tensor
            if isinstance(arr, torch.Tensor):
                arr = arr.detach().cpu().numpy()
            if isinstance(arr, list):
                arr = np.array(arr)
            if arr is None:
                return ""
            if arr.ndim == 4:
                arr = arr[0]
            if arr.ndim != 3 or arr.shape[2] < 3:
                return ""
            rgb = np.clip(arr[:, :, :3], 0.0, 1.0)
            rgb_u8 = (rgb * 255.0).astype(np.uint8)
            bgr_u8 = cv2.cvtColor(rgb_u8, cv2.COLOR_RGB2BGR)
            ok, encoded = cv2.imencode(".png", bgr_u8)
            if not ok:
                return ""
            b64 = base64.b64encode(encoded.tobytes()).decode("ascii")
            return f"data:image/png;base64,{b64}"
        except Exception:
            return ""

    @staticmethod
    def _parse_pose_tag(text):
        """<pose-프리셋명:강도:시작%:종료%> 태그를 파싱합니다.
        반환: {"preset_name": str, "strength": float|None, "start_pct": float|None, "end_pct": float|None}
        None이면 태그 없음. 오류시 ValueError 발생."""
        if not text:
            return None
        pattern = r'<pose-([^:>]+?)(?::([^:>]*))?(?::([^:>]*))?(?::([^:>]*))?>'
        match = re.search(pattern, text)
        if not match:
            return None

        preset_name = (match.group(1) or "").strip()
        if not preset_name:
            return None

        result = {"preset_name": preset_name, "strength": None, "start_pct": None, "end_pct": None}

        if match.group(2) is not None and match.group(2).strip():
            raw = match.group(2).strip()
            try:
                val = float(raw)
            except ValueError:
                raise ValueError(f"컨트롤넷 강도 값이 잘못되었습니다: '{raw}'")
            if val < 0:
                raise ValueError(f"컨트롤넷 강도는 음수가 될 수 없습니다: {val}")
            result["strength"] = val

        if match.group(3) is not None and match.group(3).strip():
            raw = match.group(3).strip()
            try:
                val = float(raw)
            except ValueError:
                raise ValueError(f"시작 퍼센트 값이 잘못되었습니다: '{raw}'")
            if val < 0:
                raise ValueError(f"시작 퍼센트는 음수가 될 수 없습니다: {val}")
            if val > 100:
                raise ValueError(f"시작 퍼센트는 100을 초과할 수 없습니다: {val}")
            result["start_pct"] = val

        if match.group(4) is not None and match.group(4).strip():
            raw = match.group(4).strip()
            try:
                val = float(raw)
            except ValueError:
                raise ValueError(f"종료 퍼센트 값이 잘못되었습니다: '{raw}'")
            if val < 0:
                raise ValueError(f"종료 퍼센트는 음수가 될 수 없습니다: {val}")
            if val > 100:
                raise ValueError(f"종료 퍼센트는 100을 초과할 수 없습니다: {val}")
            result["end_pct"] = val

        return result

    @staticmethod
    def _load_pose_preset_json(preset_name):
        """프리셋 파일에서 해당 이름의 포즈 JSON 문자열을 불러옵니다."""
        try:
            preset_file = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "../Presets/pose-preset.json"
            )
            if not os.path.exists(preset_file):
                return None
            with open(preset_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            content = data.get(preset_name)
            if content is None:
                lower = preset_name.lower()
                for k, v in data.items():
                    if k.lower() == lower:
                        content = v
                        break
            return content if content and str(content).strip() else None
        except Exception:
            return None

    def _apply_controlnet(self, positive, negative, model_name, pose_image, strength, start_percent, end_percent, vae=None):
        """포즈 이미지로 ControlNet을 컨디셔닝에 적용합니다."""
        try:
            import folder_paths
            import comfy.controlnet
            import nodes as comfy_nodes
        except ImportError as e:
            raise ImportError(f"ComfyUI 모듈을 불러올 수 없습니다: {e}")

        controlnet_path = folder_paths.get_full_path("controlnet", model_name)
        if not controlnet_path:
            raise ValueError(f"컨트롤넷 모델을 찾을 수 없습니다: {model_name}")

        controlnet = comfy.controlnet.load_controlnet(controlnet_path)

        if pose_image.dim() == 3:
            pose_image = pose_image.unsqueeze(0)

        cn_node = comfy_nodes.ControlNetApplyAdvanced()
        apply_fn = cn_node.apply_controlnet
        sig = inspect.signature(apply_fn)

        apply_kwargs = {
            "positive": positive,
            "negative": negative,
            "control_net": controlnet,
            "image": pose_image,
            "strength": strength,
            "start_percent": start_percent / 100.0,
            "end_percent": end_percent / 100.0,
        }
        if "vae" in sig.parameters:
            apply_kwargs["vae"] = vae

        result = apply_fn(**apply_kwargs)
        return result[0], result[1]

    def _transform_person(self, person, body_scale, head_scale, hands_scale, overall_scale):
        body = person.get("pose_keypoints_2d") or []
        face = person.get("face_keypoints_2d") or []
        lhand = person.get("hand_left_keypoints_2d") or []
        rhand = person.get("hand_right_keypoints_2d") or []

        body_out = body[:]
        face_out = face[:]
        lhand_out = lhand[:]
        rhand_out = rhand[:]

        body_pivot = (0.5, 0.5)
        if len(body) >= 3 and body[2] > 0:
            body_pivot = (body[0], body[1])

        for i in range(0, len(body_out), 3):
            if body_out[i + 2] <= 0:
                continue
            x, y = self._scale_point(body_out[i], body_out[i + 1], body_pivot[0], body_pivot[1], body_scale)
            x, y = self._scale_point(x, y, 0.5, 0.5, overall_scale)
            body_out[i] = x
            body_out[i + 1] = y

        face_pivot = body_pivot
        for i in range(0, len(face_out), 3):
            if face_out[i + 2] <= 0:
                continue
            x, y = self._scale_point(face_out[i], face_out[i + 1], face_pivot[0], face_pivot[1], head_scale)
            x, y = self._scale_point(x, y, 0.5, 0.5, overall_scale)
            face_out[i] = x
            face_out[i + 1] = y

        for i in range(0, len(lhand_out), 3):
            if lhand_out[i + 2] <= 0:
                continue
            pivot = (lhand_out[0], lhand_out[1]) if len(lhand_out) >= 3 and lhand_out[2] > 0 else body_pivot
            x, y = self._scale_point(lhand_out[i], lhand_out[i + 1], pivot[0], pivot[1], hands_scale)
            x, y = self._scale_point(x, y, 0.5, 0.5, overall_scale)
            lhand_out[i] = x
            lhand_out[i + 1] = y

        for i in range(0, len(rhand_out), 3):
            if rhand_out[i + 2] <= 0:
                continue
            pivot = (rhand_out[0], rhand_out[1]) if len(rhand_out) >= 3 and rhand_out[2] > 0 else body_pivot
            x, y = self._scale_point(rhand_out[i], rhand_out[i + 1], pivot[0], pivot[1], hands_scale)
            x, y = self._scale_point(x, y, 0.5, 0.5, overall_scale)
            rhand_out[i] = x
            rhand_out[i + 1] = y

        return {
            "pose_keypoints_2d": body_out,
            "face_keypoints_2d": face_out,
            "hand_left_keypoints_2d": lhand_out,
            "hand_right_keypoints_2d": rhand_out,
        }

    @staticmethod
    def _draw_bodypose(canvas, candidate, subset, pose_marker_size):
        if not candidate:
            return canvas

        h, w, _ = canvas.shape
        candidate = np.array(candidate)

        limb_seq = [[2, 3], [2, 6], [3, 4], [4, 5], [6, 7], [7, 8], [2, 9], [9, 10],
                    [10, 11], [2, 12], [12, 13], [13, 14], [2, 1], [1, 15], [15, 17],
                    [1, 16], [16, 18], [3, 17], [6, 18]]
        colors = [[255, 0, 0], [255, 85, 0], [255, 170, 0], [255, 255, 0], [170, 255, 0], [85, 255, 0],
                  [0, 255, 0], [0, 255, 85], [0, 255, 170], [0, 255, 255], [0, 170, 255], [0, 85, 255],
                  [0, 0, 255], [85, 0, 255], [170, 0, 255], [255, 0, 255], [255, 0, 170], [255, 0, 85]]

        for i in range(17):
            for n in range(len(subset)):
                row = subset[n]
                if not isinstance(row, (list, tuple, np.ndarray)):
                    continue
                a, b = limb_seq[i]
                if len(row) < max(a, b):
                    continue
                index = np.array([row[a - 1], row[b - 1]])
                if -1 in index:
                    continue
                if np.max(index) >= len(candidate):
                    continue
                y = candidate[index.astype(int), 0] * float(w)
                x = candidate[index.astype(int), 1] * float(h)
                mx = np.mean(x)
                my = np.mean(y)
                length = ((x[0] - x[1]) ** 2 + (y[0] - y[1]) ** 2) ** 0.5
                angle = math.degrees(math.atan2(x[0] - x[1], y[0] - y[1]))
                polygon = cv2.ellipse2Poly((int(my), int(mx)), (int(length / 2), pose_marker_size), int(angle), 0, 360, 1)
                cv2.fillConvexPoly(canvas, polygon, colors[i])

        canvas = (canvas * 0.6).astype(np.uint8)
        for i in range(18):
            for n in range(len(subset)):
                row = subset[n]
                if not isinstance(row, (list, tuple, np.ndarray)) or len(row) <= i:
                    continue
                index = int(row[i])
                if index == -1:
                    continue
                if index >= len(candidate):
                    continue
                x, y = candidate[index][0:2]
                cv2.circle(canvas, (int(x * w), int(y * h)), pose_marker_size, colors[i], thickness=-1)
        return canvas

    @staticmethod
    def _draw_handpose(canvas, all_hand_peaks, hand_marker_size):
        h, w, _ = canvas.shape
        edges = [[0, 1], [1, 2], [2, 3], [3, 4], [0, 5], [5, 6], [6, 7], [7, 8], [0, 9], [9, 10],
                 [10, 11], [11, 12], [0, 13], [13, 14], [14, 15], [15, 16], [0, 17], [17, 18], [18, 19], [19, 20]]
        eps = 0.01

        for peaks in all_hand_peaks:
            peaks = np.array(peaks)
            if peaks.ndim != 2 or peaks.shape[1] < 2:
                continue
            for ie, edge in enumerate(edges):
                if edge[0] >= len(peaks) or edge[1] >= len(peaks):
                    continue
                x1, y1 = peaks[edge[0]]
                x2, y2 = peaks[edge[1]]
                x1 = int(x1 * w)
                y1 = int(y1 * h)
                x2 = int(x2 * w)
                y2 = int(y2 * h)
                if x1 > eps and y1 > eps and x2 > eps and y2 > eps:
                    cv2.line(canvas, (x1, y1), (x2, y2), matplotlib.colors.hsv_to_rgb([ie / float(len(edges)), 1.0, 1.0]) * 255,
                             thickness=1 if hand_marker_size == 0 else hand_marker_size)

            joint_size = hand_marker_size + 1 if hand_marker_size < 2 else hand_marker_size + 2
            for point in peaks:
                x = int(point[0] * w)
                y = int(point[1] * h)
                if x > eps and y > eps:
                    cv2.circle(canvas, (x, y), joint_size, (0, 0, 255), thickness=-1)

        return canvas

    @staticmethod
    def _draw_facepose(canvas, all_lmks, face_marker_size):
        h, w, _ = canvas.shape
        eps = 0.01
        for lmks in all_lmks:
            lmks = np.array(lmks)
            for lmk in lmks:
                x = int(lmk[0] * w)
                y = int(lmk[1] * h)
                if x > eps and y > eps:
                    cv2.circle(canvas, (x, y), face_marker_size, (255, 255, 255), thickness=-1)
        return canvas

    def _draw_pose(self, pose, h, w, pose_marker_size, face_marker_size, hand_marker_size):
        canvas = np.zeros(shape=(h, w, 3), dtype=np.uint8)
        if pose["bodies"]["candidate"]:
            canvas = self._draw_bodypose(canvas, pose["bodies"]["candidate"], pose["bodies"]["subset"], pose_marker_size)
        if pose["hands"]:
            canvas = self._draw_handpose(canvas, pose["hands"], hand_marker_size)
        if pose["faces"]:
            canvas = self._draw_facepose(canvas, pose["faces"], face_marker_size)
        return canvas

    def _render_pose(self, images, resolution_x, show_body, show_face, show_hands, pose_marker_size, face_marker_size, hand_marker_size,
                     hands_scale, body_scale, head_scale, overall_scale):
        rendered_images = []
        out_json = []

        for image in images:
            h = int(image.get("canvas_height", 768))
            w = int(image.get("canvas_width", 512))
            if w <= 0:
                w = 512
            if h <= 0:
                h = 768

            norm_people = []
            candidate = []
            subset = []
            faces = []
            hands = []

            for person in image.get("people", []):
                person_norm = {
                    "pose_keypoints_2d": self._normalize_points(person.get("pose_keypoints_2d") or [], w, h),
                    "face_keypoints_2d": self._normalize_points(person.get("face_keypoints_2d") or [], w, h),
                    "hand_left_keypoints_2d": self._normalize_points(person.get("hand_left_keypoints_2d") or [], w, h),
                    "hand_right_keypoints_2d": self._normalize_points(person.get("hand_right_keypoints_2d") or [], w, h),
                }
                transformed = self._transform_person(person_norm, body_scale, head_scale, hands_scale, overall_scale)
                norm_people.append(transformed)

                body = transformed["pose_keypoints_2d"]
                row = [-1] * 18
                start_idx = len(candidate)
                for i in range(0, min(len(body), 54), 3):
                    if body[i + 2] > 0:
                        candidate.append([body[i], body[i + 1]])
                        row[i // 3] = start_idx
                        start_idx += 1
                if any(idx != -1 for idx in row):
                    subset.append(row)

                face = transformed["face_keypoints_2d"]
                if face:
                    f = []
                    for i in range(0, len(face), 3):
                        if face[i + 2] > 0:
                            f.append([face[i], face[i + 1]])
                    if f:
                        faces.append(f)

                lhand = transformed["hand_left_keypoints_2d"]
                if lhand:
                    lh = [[0.0, 0.0] for _ in range(21)]
                    valid = False
                    for i in range(0, min(len(lhand), 63), 3):
                        if lhand[i + 2] > 0:
                            lh[i // 3] = [lhand[i], lhand[i + 1]]
                            valid = True
                    if valid:
                        hands.append(lh)

                rhand = transformed["hand_right_keypoints_2d"]
                if rhand:
                    rh = [[0.0, 0.0] for _ in range(21)]
                    valid = False
                    for i in range(0, min(len(rhand), 63), 3):
                        if rhand[i + 2] > 0:
                            rh[i // 3] = [rhand[i], rhand[i + 1]]
                            valid = True
                    if valid:
                        hands.append(rh)

            w_scaled = w if resolution_x < 64 else resolution_x
            h_scaled = int(h * (w_scaled * 1.0 / w))

            pose = {
                "bodies": {"candidate": candidate, "subset": subset} if show_body else {"candidate": [], "subset": []},
                "faces": faces if show_face else [],
                "hands": hands if show_hands else [],
            }
            rendered_images.append(self._draw_pose(pose, h_scaled, w_scaled, pose_marker_size, face_marker_size, hand_marker_size))
            out_json.append({"people": norm_people, "canvas_height": h_scaled, "canvas_width": w_scaled})

        return rendered_images, out_json

    def load_pose(self, POSE_JSON="", POSE_KEYPOINT=None, pose_json_input="", background_image=None, **kwargs):
        # Keep backend defaults and accept legacy workflow values if provided.
        show_body = bool(kwargs.get("show_body", True))
        show_face = bool(kwargs.get("show_face", True))
        show_hands = bool(kwargs.get("show_hands", True))
        resolution_x = self._as_number(kwargs.get("resolution_x", -1), -1, int)
        pose_marker_size = self._as_number(kwargs.get("pose_marker_size", 4), 4, int)
        face_marker_size = self._as_number(kwargs.get("face_marker_size", 3), 3, int)
        hand_marker_size = self._as_number(kwargs.get("hand_marker_size", 2), 2, int)
        hands_scale = self._as_number(kwargs.get("hands_scale", 1.0), 1.0, float)
        body_scale = self._as_number(kwargs.get("body_scale", 1.0), 1.0, float)
        head_scale = self._as_number(kwargs.get("head_scale", 1.0), 1.0, float)
        overall_scale = self._as_number(kwargs.get("overall_scale", 1.0), 1.0, float)
        pose_input_enabled = bool(kwargs.get("pose_input_enabled", True))

        # ControlNet inputs
        positive = kwargs.get("positive", None)
        negative = kwargs.get("negative", None)
        controlnet_enabled = bool(kwargs.get("controlnet_enabled", True))
        controlnet_model = kwargs.get("controlnet_model", None)
        controlnet_strength = float(kwargs.get("controlnet_strength", 1.0))
        controlnet_start_percent = float(kwargs.get("controlnet_start_percent", 0.0))
        controlnet_end_percent = float(kwargs.get("controlnet_end_percent", 100.0))
        pose_tag_input = str(kwargs.get("pose_tag_input", "") or "")

        # Resolved CN params (may be partially overridden by pose_tag_input)
        resolved_cn_enabled = controlnet_enabled
        resolved_cn_strength = controlnet_strength
        resolved_cn_start = controlnet_start_percent
        resolved_cn_end = controlnet_end_percent
        resolved_preset = None
        tag_pose_data = None  # if set, overrides normal pose source

        # === pose_tag_input 파싱 ===
        # 입력이 없으면 기존 노드 설정을 그대로 사용
        if pose_tag_input.strip():
            tag_result = self._parse_pose_tag(pose_tag_input)  # raises ValueError on invalid input
            if tag_result is not None:
                preset_name = tag_result["preset_name"]
                preset_content = self._load_pose_preset_json(preset_name)
                if preset_content:
                    loaded = self._safe_json_loads(preset_content)
                    tag_pose_data = self._as_pose_list(loaded)
                    resolved_preset = preset_name
                # 태그에 명시된 파라미터만 덮어씀; None이면 노드 위젯값 유지
                if tag_result["strength"] is not None:
                    resolved_cn_strength = tag_result["strength"]
                if tag_result["start_pct"] is not None:
                    resolved_cn_start = tag_result["start_pct"]
                if tag_result["end_pct"] is not None:
                    resolved_cn_end = tag_result["end_pct"]

        # === 포즈 데이터 결정 ===
        pose_data = None
        if tag_pose_data is not None:
            # pose_tag_input 프리셋이 우선
            pose_data = tag_pose_data
        elif pose_input_enabled and POSE_KEYPOINT is not None:
            pose_data = self._as_pose_list(copy.deepcopy(POSE_KEYPOINT))
        else:
            if pose_input_enabled:
                incoming = pose_json_input if pose_json_input and pose_json_input.strip() else POSE_JSON
            else:
                incoming = POSE_JSON
            loaded = self._safe_json_loads(incoming)
            pose_data = self._as_pose_list(loaded)

        if not pose_data:
            pose_data = self._default_pose()

        pose_imgs, scaled_pose = self._render_pose(
            pose_data,
            resolution_x,
            show_body,
            show_face,
            show_hands,
            pose_marker_size,
            face_marker_size,
            hand_marker_size,
            hands_scale,
            body_scale,
            head_scale,
            overall_scale,
        )

        if not pose_imgs:
            pose_data = self._default_pose()
            pose_imgs, scaled_pose = self._render_pose(
                pose_data,
                resolution_x,
                show_body,
                show_face,
                show_hands,
                pose_marker_size,
                face_marker_size,
                hand_marker_size,
                hands_scale,
                body_scale,
                head_scale,
                overall_scale,
            )

        pose_imgs_np = np.array(pose_imgs).astype(np.float32) / 255.0
        final_json = json.dumps(scaled_pose, indent=4)
        bg_data_url = self._tensor_to_png_data_url(background_image)

        # === ControlNet 적용 ===
        positive_out = positive
        negative_out = negative

        # 태그로 포즈가 로드되면 스위치 상태와 무관하게 CN 적용
        cn_should_apply = resolved_cn_enabled or (tag_pose_data is not None)

        if cn_should_apply and positive is not None and negative is not None:
            cn_name = controlnet_model
            if cn_name and cn_name != "none":
                try:
                    pose_tensor = torch.from_numpy(pose_imgs_np)
                    positive_out, negative_out = self._apply_controlnet(
                        positive, negative, cn_name,
                        pose_tensor,
                        resolved_cn_strength,
                        resolved_cn_start,
                        resolved_cn_end,
                    )
                except Exception as e:
                    print(f"[NakoPoseEditor] ControlNet 적용 오류: {e}")

        # cnet_info 텍스트 생성
        cn_actually_applied = (
            cn_should_apply
            and positive is not None
            and negative is not None
            and controlnet_model
            and controlnet_model != "none"
        )
        if cn_actually_applied:
            label = resolved_preset if resolved_preset else "on"
            cnet_info = f"controlnet: {label}"
        else:
            cnet_info = "controlnet: off"

        return {
            "ui": {
                "POSE_JSON": [final_json],
                "BG_IMAGE": [bg_data_url],
                "POSE_INPUT_ENABLED": [pose_input_enabled],
                "CN_RESOLVED": [{
                    "enabled": resolved_cn_enabled,
                    "strength": resolved_cn_strength,
                    "start": resolved_cn_start,
                    "end": resolved_cn_end,
                    "preset": resolved_preset,
                }],
            },
            "result": (
                torch.from_numpy(pose_imgs_np),
                scaled_pose,
                final_json,
                positive_out,
                negative_out,
                cnet_info,
            ),
        }


NODE_CLASS_MAPPINGS = {
    "NakoPoseEditorNode": NakoPoseEditorNode,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "NakoPoseEditorNode": "Nako Pose Editor",
}
