import { app } from "../../scripts/app.js";
import { ComfyDialog, $el } from "../../scripts/ui.js";
import { ComfyApp } from "../../scripts/app.js";

// Cache-bust local editor when poseEditorNako.html changes.
const LOCAL_EDITOR_SRC = new URL("./poseEditorNako.html?v=pose_groups_20260225_face_neck_bg_off_thumb_fix", import.meta.url).toString();
const EDITOR_CANDIDATE_SRCS = [LOCAL_EDITOR_SRC];

// ── Toolbar 상수 ─────────────────────────────────────────────────────────────
const NAKO_POSE_TB_SIZE   = 13;
const NAKO_POSE_TB_MARGIN = 4;
const NAKO_POSE_TB_GAP    = 2;
const NAKO_POSE_TB_Y      = NAKO_POSE_TB_SIZE - 34;
const NAKO_POSE_TB_BUTTONS = [
    { name: "settings", label: "⚙" },
    { name: "help",     label: "?" },
];

// 노드 색상 (코어 청록 기본 / CN On 시 타이틀 흐린 노란색)
const NAKO_POSE_COLOR        = "#2a363b";
const NAKO_POSE_BGCOLOR      = "#3f5159";
const NAKO_POSE_CN_ON_COLOR  = "#b89820";  // CN 활성 시 타이틀 오버레이

// 노드에서 숨길 CN 위젯 목록 (설정 팝업에서 관리)
const NAKO_POSE_CN_HIDDEN_WIDGETS = [
    "controlnet_model",
    "controlnet_strength",
    "controlnet_start_percent",
    "controlnet_end_percent",
];

// ── 위젯 숨김 유틸 ────────────────────────────────────────────────────────────
function nakoPoseHideWidget(node, name) {
    const w = node?.widgets?.find((x) => x.name === name);
    if (!w || w._nakoHidden) return;
    if (!node._nakoHiddenProps) node._nakoHiddenProps = {};
    if (!node._nakoHiddenProps[name]) {
        node._nakoHiddenProps[name] = {
            hidden: w.hidden,
            computeSize: w.computeSize,
        };
    }
    w._nakoHidden = true;
    w.hidden = true;
    w.computeSize = () => [0, -4];
    if (w.inputEl?.style) w.inputEl.style.display = "none";
    if (w.element?.style) w.element.style.display = "none";
    if (Array.isArray(w.linkedWidgets)) {
        for (const linked of w.linkedWidgets) {
            linked.hidden = true;
            if (linked.inputEl?.style) linked.inputEl.style.display = "none";
            if (linked.element?.style) linked.element.style.display = "none";
        }
    }
}

function nakoPoseShowWidget(node, name) {
    const w = node?.widgets?.find((x) => x.name === name);
    if (!w) return;
    const orig = node._nakoHiddenProps?.[name];
    if (!orig) return;
    w._nakoHidden = false;
    w.hidden = orig.hidden ?? false;
    w.computeSize = orig.computeSize;
    if (w.inputEl?.style) w.inputEl.style.display = "";
    if (w.element?.style) w.element.style.display = "";
    if (Array.isArray(w.linkedWidgets)) {
        for (const linked of w.linkedWidgets) {
            linked.hidden = false;
            if (linked.inputEl?.style) linked.inputEl.style.display = "";
            if (linked.element?.style) linked.element.style.display = "";
        }
    }
}

function applyCnWidgetHiding(node) {
    for (const name of NAKO_POSE_CN_HIDDEN_WIDGETS) {
        nakoPoseHideWidget(node, name);
    }
    node.setSize?.([node.size[0], node.computeSize()[1]]);
    node.setDirtyCanvas?.(true);
}

function applyPoseJsonVisibility(node) {
    const show = node._nakoPoseJsonVisible !== false;
    const w = node?.widgets?.find((x) => x.name === "POSE_JSON");
    if (!w) return;
    const isHidden = Boolean(w._nakoHidden);
    if (show && isHidden) {
        nakoPoseShowWidget(node, "POSE_JSON");
    } else if (!show && !isHidden) {
        nakoPoseHideWidget(node, "POSE_JSON");
    }
    node.setSize?.([node.size[0], node.computeSize()[1]]);
    node.setDirtyCanvas?.(true, true);
    app?.graph?.setDirtyCanvas?.(true, true);
}

// ── 위젯 값 읽기/쓰기 ──────────────────────────────────────────────────────────
function getNakoPoseWVal(node, name, fallback) {
    const w = node?.widgets?.find((x) => x.name === name);
    return w !== undefined ? w.value : fallback;
}

function setNakoPoseWVal(node, name, value) {
    const w = node?.widgets?.find((x) => x.name === name);
    if (!w) return;
    w.value = value;
    w.callback?.(value);
    node?.setDirtyCanvas?.(true, true);
}

// ── 팝업 인프라 ───────────────────────────────────────────────────────────────
function closeNakoPosePopup(node, key) {
    const entry = node._nakoPosePopups?.[key];
    if (!entry) return;
    entry.el.remove();
    entry.abort?.abort();
    delete node._nakoPosePopups[key];
}

function closeAllNakoPosePopups(node) {
    for (const key of Object.keys(node._nakoPosePopups || {})) {
        closeNakoPosePopup(node, key);
    }
}

function createNakoPosePopup(node, key, title) {
    closeNakoPosePopup(node, key);
    node._nakoPosePopups = node._nakoPosePopups || {};

    const abort = new AbortController();

    const popup = document.createElement("div");
    Object.assign(popup.style, {
        position:        "fixed",
        zIndex:          "9999",
        minWidth:        "270px",
        maxWidth:        "370px",
        background:      "rgba(18,22,30,0.96)",
        border:          "1px solid rgba(108,132,170,0.44)",
        borderRadius:    "10px",
        boxShadow:       "0 8px 24px rgba(0,0,0,0.38)",
        color:           "#dbe5f5",
        fontSize:        "12px",
        lineHeight:      "1.4",
        overflow:        "hidden",
        display:         "flex",
        flexDirection:   "column",
    });

    const header = document.createElement("div");
    Object.assign(header.style, {
        display:         "flex",
        alignItems:      "center",
        justifyContent:  "space-between",
        padding:         "8px 10px",
        background:      "rgba(42,58,84,0.55)",
        borderBottom:    "1px solid rgba(118,143,184,0.28)",
        fontWeight:      "600",
        flexShrink:      "0",
    });
    const titleSpan = document.createElement("span");
    titleSpan.textContent = title;
    header.appendChild(titleSpan);

    const closeBtn = document.createElement("button");
    closeBtn.type = "button";
    closeBtn.textContent = "×";
    Object.assign(closeBtn.style, {
        marginLeft:  "8px",
        border:      "none",
        background:  "transparent",
        color:       "#e9effa",
        cursor:      "pointer",
        fontSize:    "14px",
        lineHeight:  "1",
        padding:     "2px 4px",
    });
    header.appendChild(closeBtn);

    const body = document.createElement("div");
    Object.assign(body.style, {
        padding:    "10px",
        overflowY:  "auto",
        flex:       "1",
    });

    popup.appendChild(header);
    popup.appendChild(body);
    document.body.appendChild(popup);

    node._nakoPosePopups[key] = { el: popup, body, abort };

    closeBtn.addEventListener("mousedown", (e) => {
        e.preventDefault();
        e.stopPropagation();
        closeNakoPosePopup(node, key);
    }, { signal: abort.signal });
}

function updateNakoPosePopupPosition(node, ctx, popup) {
    if (!popup) return;
    const rect   = ctx.canvas.getBoundingClientRect();
    const scaleX = rect.width  / ctx.canvas.width;
    const scaleY = rect.height / ctx.canvas.height;
    const transform = new DOMMatrix()
        .scaleSelf(scaleX, scaleY)
        .multiplySelf(ctx.getTransform())
        .translateSelf(node.size[0], 0)
        .translateSelf(12, -30);
    const scale = new DOMMatrix().scaleSelf(transform.a, transform.d);
    const bcr = app.canvas.canvas.getBoundingClientRect();
    Object.assign(popup.style, {
        transformOrigin: "0 0",
        transform:       scale,
        left:            `${transform.a + bcr.x + transform.e}px`,
        top:             `${transform.d + bcr.y + transform.f}px`,
        maxHeight:       `${Math.max(260, Math.min(window.innerHeight - 24, Math.round(node.size[1] + 260)))}px`,
    });
}

// ── 설정 팝업 내용 ─────────────────────────────────────────────────────────────
function toggleNakoPoseSettingsPopup(node) {
    if (node._nakoPosePopups?.settings) {
        closeNakoPosePopup(node, "settings");
        return;
    }
    createNakoPosePopup(node, "settings", "Pose Editor 설정");
    const body = node._nakoPosePopups?.settings?.body;
    if (!body) return;

    const makeSmallLabel = (text) => {
        const el = document.createElement("div");
        el.textContent = text;
        Object.assign(el.style, {
            fontSize:     "11px",
            color:        "#8da0c0",
            marginBottom: "4px",
            marginTop:    "10px",
        });
        return el;
    };

    // ── ControlNet Model 선택 ──
    body.appendChild(makeSmallLabel("ControlNet Model"));

    const modelWidget = node?.widgets?.find((x) => x.name === "controlnet_model");
    const modelSelect = document.createElement("select");
    Object.assign(modelSelect.style, {
        width:        "100%",
        boxSizing:    "border-box",
        background:   "rgba(10,14,20,0.82)",
        color:        "#e7edf8",
        border:       "1px solid rgba(126,144,178,0.35)",
        borderRadius: "6px",
        padding:      "5px 7px",
        fontSize:     "11px",
        marginBottom: "4px",
    });
    const modelList = modelWidget?.options?.values || [];
    if (modelList.length === 0) {
        const opt = document.createElement("option");
        opt.value = "none";
        opt.textContent = "(설치된 모델 없음)";
        modelSelect.appendChild(opt);
    } else {
        for (const m of modelList) {
            const opt = document.createElement("option");
            opt.value = m;
            opt.textContent = m;
            opt.selected = (m === modelWidget?.value);
            modelSelect.appendChild(opt);
        }
    }
    modelSelect.addEventListener("change", () => {
        setNakoPoseWVal(node, "controlnet_model", modelSelect.value);
    });
    body.appendChild(modelSelect);

    // ── 슬라이더 헬퍼 ──
    const makeSlider = (label, widgetName, min, max, step, toFixed = 1) => {
        const wrap = document.createElement("div");
        Object.assign(wrap.style, { marginBottom: "6px" });

        const topRow = document.createElement("div");
        Object.assign(topRow.style, {
            display:        "flex",
            justifyContent: "space-between",
            fontSize:       "11px",
            color:          "#8da0c0",
            marginBottom:   "3px",
        });
        const labelEl = document.createElement("span");
        labelEl.textContent = label;
        const valueEl = document.createElement("span");
        const curVal = getNakoPoseWVal(node, widgetName, min);
        valueEl.textContent = Number(curVal).toFixed(toFixed);
        topRow.appendChild(labelEl);
        topRow.appendChild(valueEl);

        const slider = document.createElement("input");
        slider.type  = "range";
        slider.min   = String(min);
        slider.max   = String(max);
        slider.step  = String(step);
        slider.value = String(curVal);
        Object.assign(slider.style, {
            width:       "100%",
            accentColor: "#6c82b0",
            cursor:      "pointer",
        });
        slider.addEventListener("input", () => {
            const v = parseFloat(slider.value);
            valueEl.textContent = v.toFixed(toFixed);
            setNakoPoseWVal(node, widgetName, v);
        });

        wrap.appendChild(topRow);
        wrap.appendChild(slider);
        return wrap;
    };

    body.appendChild(makeSmallLabel("강도 / 시작 % / 종료 %"));
    body.appendChild(makeSlider("Strength",  "controlnet_strength",       0,   2, 0.05, 2));
    body.appendChild(makeSlider("Start %",   "controlnet_start_percent",  0, 100, 5,   0));
    body.appendChild(makeSlider("End %",     "controlnet_end_percent",    0, 100, 5,   0));

    // ── 구분선 ──
    const hr = document.createElement("hr");
    Object.assign(hr.style, {
        border:    "none",
        borderTop: "1px solid rgba(118,143,184,0.18)",
        margin:    "12px 0 8px",
    });
    body.appendChild(hr);

    // ── POSE_JSON 위젯 토글 ──
    const jsonRow = document.createElement("label");
    Object.assign(jsonRow.style, {
        display:    "flex",
        alignItems: "center",
        gap:        "8px",
        cursor:     "pointer",
        fontSize:   "12px",
        userSelect: "none",
    });
    const jsonCb = document.createElement("input");
    jsonCb.type    = "checkbox";
    jsonCb.checked = node._nakoPoseJsonVisible !== false;
    Object.assign(jsonCb.style, { cursor: "pointer" });
    jsonCb.addEventListener("change", () => {
        node._nakoPoseJsonVisible = jsonCb.checked;
        // 새로고침 후에도 상태 유지를 위해 properties에 저장
        if (!node.properties) node.properties = {};
        node.properties.nakoPoseJsonVisible = jsonCb.checked;
        applyPoseJsonVisibility(node);
        node.setSize?.([node.size[0], node.computeSize()[1]]);
        node.setDirtyCanvas?.(true, true);
    });
    const jsonLabel = document.createElement("span");
    jsonLabel.textContent = "POSE_JSON 위젯 표시";
    jsonRow.appendChild(jsonCb);
    jsonRow.appendChild(jsonLabel);
    body.appendChild(jsonRow);
}

// ── 도움말 팝업 ────────────────────────────────────────────────────────────────
function toggleNakoPoseHelpPopup(node) {
    if (node._nakoPosePopups?.help) {
        closeNakoPosePopup(node, "help");
        return;
    }
    createNakoPosePopup(node, "help", "Pose Editor 도움말");
    const body = node._nakoPosePopups?.help?.body;
    if (!body) return;

    const sections = [
        ["⚙ 설정 패널",          "ControlNet 모델·강도·시작%·끝% 조절\nPOSE_JSON 위젯 표시 여부 토글"],
        ["Preset 콤보",           "'오픈포즈' 선택 시 목록 새로고침\n프리셋 선택 시 해당 포즈 JSON 로드"],
        ["On / Off",        "ControlNet 적용 여부\nOFF 시 conditioning 그대로 바이패스"],
        ["Open Pose Editor",      "인터랙티브 포즈 편집기 열기"],
        ["pose_tag_input (연결)", "<pose-프리셋명:강도:시작%:종료%>\n태그를 파싱해 노드를 자동 제어\n생략된 파라미터는 노드 위젯값 사용"],
        ["positive / negative 출력", "CN 적용된 conditioning 출력\nOff 또는 입력 미연결 시 바이패스"],
    ];

    for (const [title, desc] of sections) {
        const wrap = document.createElement("div");
        Object.assign(wrap.style, { marginBottom: "10px" });

        const t = document.createElement("div");
        t.textContent = title;
        Object.assign(t.style, { fontWeight: "600", color: "#9ab0d0", marginBottom: "3px" });

        const d = document.createElement("div");
        d.textContent = desc;
        Object.assign(d.style, { color: "#c0cfe8", whiteSpace: "pre-line", lineHeight: "1.5" });

        wrap.appendChild(t);
        wrap.appendChild(d);
        body.appendChild(wrap);
    }
}

// ── 툴바 액션 ─────────────────────────────────────────────────────────────────
function handleNakoPoseToolbarAction(node, name) {
    if (name === "settings") {
        const wasOpen = Boolean(node._nakoPosePopups?.settings);
        closeAllNakoPosePopups(node);
        if (!wasOpen) toggleNakoPoseSettingsPopup(node);
    } else if (name === "help") {
        const wasOpen = Boolean(node._nakoPosePopups?.help);
        closeAllNakoPosePopups(node);
        if (!wasOpen) toggleNakoPoseHelpPopup(node);
    }
}

// ── 툴바 설치 ─────────────────────────────────────────────────────────────────
function installNakoPoseToolbar(node) {
    if (node._nakoPoseToolbarInstalled) return;
    node._nakoPoseToolbarInstalled = true;

    const prevDrawTitle = node.onDrawTitle;
    node.onDrawTitle = function (ctx) {
        const r = prevDrawTitle ? prevDrawTitle.apply(this, arguments) : undefined;
        const cnEnabled = getWidget(node, "controlnet_enabled")?.value;
        if (cnEnabled) {
            const h = LiteGraph.NODE_TITLE_HEIGHT || 30;
            ctx.save();
            ctx.globalAlpha = 0.5;
            ctx.fillStyle = NAKO_POSE_CN_ON_COLOR;
            ctx.fillRect(0, -h, node.size[0], h);
            ctx.restore();
        }
        return r;
    };

    const prevDraw = node.onDrawForeground;
    node.onDrawForeground = function (ctx) {
        const result = prevDraw ? prevDraw.apply(this, arguments) : undefined;
        if (!node.flags?.collapsed) {
            const btnW   = NAKO_POSE_TB_SIZE + 2;
            const totalW = NAKO_POSE_TB_BUTTONS.length * btnW
                         + (NAKO_POSE_TB_BUTTONS.length - 1) * NAKO_POSE_TB_GAP;
            let x = node.size[0] - NAKO_POSE_TB_MARGIN - totalW;
            node._nakoPoseToolbarHitboxes = [];

            for (const btn of NAKO_POSE_TB_BUTTONS) {
                const y           = NAKO_POSE_TB_Y;
                const h           = NAKO_POSE_TB_SIZE + 2;
                const settingsOpen = Boolean(node._nakoPosePopups?.settings);
                const helpOpen     = Boolean(node._nakoPosePopups?.help);
                const active = (btn.name === "settings" && settingsOpen)
                            || (btn.name === "help"     && helpOpen);
                const bg = active ? "rgba(93,74,141,0.9)" : "rgba(60,65,75,0.85)";

                ctx.save();
                ctx.fillStyle   = bg;
                ctx.strokeStyle = "rgba(255,255,255,0.18)";
                ctx.lineWidth   = 1;
                ctx.beginPath();
                ctx.rect(x, y, btnW, h);
                ctx.fill();
                ctx.stroke();
                ctx.fillStyle    = "#d9e0ec";
                ctx.font         = "12px sans-serif";
                ctx.textAlign    = "center";
                ctx.textBaseline = "middle";
                ctx.fillText(btn.label, x + btnW / 2, y + h / 2 + 0.5);
                ctx.restore();

                node._nakoPoseToolbarHitboxes.push({ name: btn.name, x, y, w: btnW, h });
                x += btnW + NAKO_POSE_TB_GAP;
            }

            updateNakoPosePopupPosition(node, ctx, node._nakoPosePopups?.settings?.el);
            updateNakoPosePopupPosition(node, ctx, node._nakoPosePopups?.help?.el);
        }
        return result;
    };

    const prevMouseDown = node.onMouseDown;
    node.onMouseDown = function (e, localPos, _canvas) {
        const hitboxes = node._nakoPoseToolbarHitboxes || [];
        if (localPos && !node.flags?.collapsed) {
            for (const box of hitboxes) {
                if (
                    localPos[0] > box.x && localPos[0] < box.x + box.w &&
                    localPos[1] > box.y && localPos[1] < box.y + box.h
                ) {
                    handleNakoPoseToolbarAction(node, box.name);
                    return true;
                }
            }
        }
        return prevMouseDown ? prevMouseDown.apply(this, arguments) : undefined;
    };

    const prevRemoved = node.onRemoved;
    node.onRemoved = function () {
        closeAllNakoPosePopups(node);
        return prevRemoved ? prevRemoved.apply(this, arguments) : undefined;
    };
}

// ── 기존 유틸 함수들 ──────────────────────────────────────────────────────────
function ensureNumericWidgetDefaults(node) {
    if (!node?.widgets) return;
    const defaults = {
        hands_scale:      1.0,
        body_scale:       1.0,
        head_scale:       1.0,
        overall_scale:    1.0,
        pose_marker_size: 4,
        face_marker_size: 3,
        hand_marker_size: 2,
        resolution_x:     -1,
        controlnet_strength: 1.0,
        controlnet_start_percent: 0.0,
        controlnet_end_percent: 100.0,
    };
    for (const [name, fallback] of Object.entries(defaults)) {
        const w = node.widgets.find((x) => x.name === name);
        if (!w) continue;
        const n = Number(w.value);
        if (w.value === null || w.value === undefined || Number.isNaN(n)) {
            w.value = fallback;
            w.callback?.(fallback);
        }
    }
}

function getNodeBackgroundImage(node) {
    const v = node?._nakoPoseBgImage;
    return (typeof v === "string" && v.startsWith("data:image/")) ? v : "";
}

async function fetchPosePresetTitles() {
    const response = await fetch("/nako/pose_preset_titles");
    if (!response.ok) throw new Error("Failed to fetch pose preset titles");
    return await response.json();
}

async function fetchPosePresetContent(title) {
    const response = await fetch(`/nako/pose_preset_content?presetTitle=${encodeURIComponent(title)}`);
    if (!response.ok) throw new Error("Failed to fetch pose preset content");
    const data = await response.json();
    return data?.content ?? "";
}

async function fetchPosePresetThumbnails() {
    const response = await fetch("/nako/pose_preset_thumbnails");
    if (!response.ok) throw new Error("Failed to fetch pose preset thumbnails");
    return await response.json();
}

// pysssss 자동완성 연동: <pose-프리셋명> 단어 목록 등록
async function registerNakoPoseWordsWithPysssss() {
    try {
        const mod = await import("/extensions/ComfyUI-Custom-Scripts/js/common/autocomplete.js");
        const { TextAreaAutoComplete } = mod;
        if (!TextAreaAutoComplete?.updateWords) return;

        const titles = await fetchPosePresetTitles();
        if (!titles?.length) return;

        const words = {};
        for (const name of titles) {
            if (name === "오픈포즈") continue;
            const tag = `<pose-${name}>`;
            words[tag] = { text: tag, hint: "pose" };
        }
        TextAreaAutoComplete.updateWords("nako.pose_presets", words, true);
    } catch {
        // pysssss 미설치 또는 모듈 경로 변경 시 조용히 무시
    }
}

function normalizePresetTitle(title) {
    return String(title || "")
        .replace(/^\s*\d+\s*[\.\)]\s*/u, "")
        .replace(/\s+/g, " ")
        .replace(/^[^\p{L}\p{N}가-힣]+/u, "")
        .replace(/\s+$/, "")
        .split("\t")[0]
        .trim();
}

function getWidget(node, name) {
    return node?.widgets?.find((w) => w.name === name);
}

function ensurePoseInputToggleDefault(node) {
    const w = getWidget(node, "pose_input_enabled");
    if (!w) return;
    if (w.value === null || w.value === undefined) {
        w.value = true;
        w.callback?.(true);
    }
}

function clampNumber(value, min, max) {
    return Math.max(min, Math.min(max, value));
}

function repairLegacyShiftedPoseWidgets(node) {
    const poseJsonWidget = getWidget(node, "POSE_JSON");
    const cnEnabledWidget = getWidget(node, "controlnet_enabled");
    const cnModelWidget = getWidget(node, "controlnet_model");
    const strengthWidget = getWidget(node, "controlnet_strength");
    const startWidget = getWidget(node, "controlnet_start_percent");
    const endWidget = getWidget(node, "controlnet_end_percent");

    if (!poseJsonWidget || !cnEnabledWidget || !cnModelWidget || !strengthWidget || !startWidget || !endWidget) {
        return;
    }

    const poseJsonVal = poseJsonWidget.value;
    // enabledVal: 토글 위젯은 문자열을 받았더라도 boolean으로 변환할 수 있으므로
    // 직접 widgets array에서 raw 값을 읽거나, 이미 변환된 값 그대로 사용
    const enabledVal = cnEnabledWidget.value;
    const modelVal = cnModelWidget.value;
    const strengthVal = strengthWidget.value;
    const startVal = startWidget.value;

    // poseJsonVal이 boolean이거나 "false"/"true" 문자열이면 밀림 패턴으로 판단
    const poseJsonIsBoolean =
        typeof poseJsonVal === "boolean" ||
        poseJsonVal === "false" ||
        poseJsonVal === "true";

    // modelVal이 숫자(strength 값이 밀려온 것)이면 밀림 패턴
    const modelLooksLikeNumber =
        typeof modelVal === "number" && Number.isFinite(modelVal);

    // strengthVal이 percent 범위 숫자(start% 값이 밀려온 것)이면 밀림 패턴
    const strengthLooksLikePercent =
        typeof strengthVal === "number" &&
        Number.isFinite(strengthVal) &&
        strengthVal > 0 &&
        strengthVal <= 100;

    const shiftedPattern = poseJsonIsBoolean && modelLooksLikeNumber && strengthLooksLikePercent;
    if (!shiftedPattern) return;

    // poseJsonVal → ce의 원래 값 (boolean 복원)
    const recoveredEnabled =
        poseJsonVal === "false" ? false :
        poseJsonVal === "true"  ? true  :
        Boolean(poseJsonVal);

    // enabledVal → cm의 원래 값 (string이면 그대로, boolean으로 변환됐으면 복구 불가)
    const modelOptions = cnModelWidget.options?.values || [];
    const recoveredModel = typeof enabledVal === "string" && modelOptions.includes(enabledVal)
        ? enabledVal
        : null;

    const recoveredStrength = Number(modelVal);          // modelVal 슬롯에 있던 strength
    const recoveredStart    = Number(strengthVal);       // strengthVal 슬롯에 있던 start%
    const recoveredEnd      = Number(startVal);          // startVal 슬롯에 있던 end%

    cnEnabledWidget.value = recoveredEnabled;
    cnEnabledWidget.callback?.(recoveredEnabled);

    if (recoveredModel !== null) {
        cnModelWidget.value = recoveredModel;
        cnModelWidget.callback?.(recoveredModel);
    }
    if (Number.isFinite(recoveredStrength)) {
        const v = clampNumber(recoveredStrength, 0.0, 2.0);
        strengthWidget.value = v;
        strengthWidget.callback?.(v);
    }
    if (Number.isFinite(recoveredStart)) {
        const v = clampNumber(recoveredStart, 0.0, 100.0);
        startWidget.value = v;
        startWidget.callback?.(v);
    }
    if (Number.isFinite(recoveredEnd)) {
        const v = clampNumber(recoveredEnd, 0.0, 100.0);
        endWidget.value = v;
        endWidget.callback?.(v);
    }

    poseJsonWidget.value = "";
    poseJsonWidget.callback?.("");

    node?.setDirtyCanvas?.(true, true);
    app?.graph?.setDirtyCanvas?.(true, true);
    console.warn("NakoPoseEditor: repaired legacy shifted widget values after reload.");
}

async function refreshPosePresetCombo(node) {
    const presetWidget = getWidget(node, "Preset");
    if (!presetWidget) return;
    try {
        const titles = await fetchPosePresetTitles();
        presetWidget.options = presetWidget.options || {};
        presetWidget.options.values = titles;
        if (!titles.includes(presetWidget.value)) {
            presetWidget.value = titles[0] || "오픈포즈";
        }
        node?.setDirtyCanvas?.(true, true);
        app?.graph?.setDirtyCanvas?.(true, true);
    } catch (e) {
        console.error("NakoPoseEditor: preset title load failed", e);
    }
}

function ensurePosePresetWidgets(node) {
    if (!node?.widgets || typeof node.addWidget !== "function") return;

    let presetWidget = getWidget(node, "Preset");
    if (!presetWidget) {
        presetWidget = node.addWidget("combo", "Preset", "오픈포즈", async (value) => {
            node.selectedPreset = value;
            if (!value || value === "오픈포즈") {
                await node._nakoRefreshPosePresetTitles?.();
                return;
            }
            try {
                const content = await fetchPosePresetContent(value);
                if (!content || !String(content).trim()) return;
                const poseJsonWidget = getWidget(node, "POSE_JSON");
                if (!poseJsonWidget) return;
                poseJsonWidget.value = content;
                poseJsonWidget.callback?.(content);
                node?.setDirtyCanvas?.(true, true);
                app?.graph?.setDirtyCanvas?.(true, true);
            } catch (e) {
                console.error("NakoPoseEditor: preset content load failed", e);
            }
        }, { values: ["오픈포즈"], serialize: false });
    }

    node._nakoRefreshPosePresetTitles = async () => {
        await refreshPosePresetCombo(node);
        try {
            const thumbs = await fetchPosePresetThumbnails();
            node._nakoPosePresetThumbs = thumbs || {};
            const normalized = {};
            for (const [k, v] of Object.entries(node._nakoPosePresetThumbs)) {
                normalized[normalizePresetTitle(k)] = v;
            }
            node._nakoPosePresetThumbsNormalized = normalized;
        } catch (e) {
            node._nakoPosePresetThumbs = {};
            node._nakoPosePresetThumbsNormalized = {};
            console.error("NakoPoseEditor: preset thumbnail load failed", e);
        }
    };
    node._nakoRefreshPosePresetTitles();
    installPosePresetHoverPreview(node);
}

function installPosePresetHoverPreview(node) {
    if (node._nakoPosePreviewInstalled) return;
    node._nakoPosePreviewInstalled = true;

    const preview = document.createElement("div");
    Object.assign(preview.style, {
        position:     "fixed",
        zIndex:       "500000",
        display:      "none",
        pointerEvents:"none",
        border:       "1px solid rgba(120,140,170,0.6)",
        background:   "rgba(8,12,18,0.95)",
        borderRadius: "8px",
        padding:      "6px",
        boxShadow:    "0 10px 20px rgba(0,0,0,0.35)",
    });
    const img = document.createElement("img");
    Object.assign(img.style, {
        width:       "120px",
        height:      "120px",
        objectFit:   "contain",
        display:     "block",
        background:  "#000",
        borderRadius:"4px",
    });
    preview.appendChild(img);
    document.body.appendChild(preview);

    const getThumb = (title) => {
        const exact = (node._nakoPosePresetThumbs || {})[title];
        if (exact) return exact;
        const norm = normalizePresetTitle(title);
        return (node._nakoPosePresetThumbsNormalized || {})[norm] || "";
    };
    const hide = () => { preview.style.display = "none"; img.src = ""; };
    let refreshPending = false;
    let lastRefreshAt = 0;
    const missingThumbTitles = new Set();
    let lastHoverTitle = "";
    const ensureThumbsLoaded = async () => {
        if (refreshPending) return;
        const now = Date.now();
        if (now - lastRefreshAt < 1500) return;
        lastRefreshAt = now;
        refreshPending = true;
        try {
            await node._nakoRefreshPosePresetTitles?.();
            missingThumbTitles.clear();
        } finally {
            refreshPending = false;
        }
    };
    const resolveMenuEntry = (target) => {
        if (!(target instanceof HTMLElement)) return null;
        const menu = target.closest(".litecontextmenu, [role='menu']");
        if (menu) {
            let cur = target;
            while (cur && cur !== menu) {
                if (
                    cur.classList?.contains("litemenu-entry") ||
                    cur.classList?.contains("menu-entry") ||
                    cur.getAttribute?.("role") === "menuitem" ||
                    (cur.tagName === "LI" && cur.parentElement?.closest(".litecontextmenu, [role='menu']"))
                ) return cur;
                cur = cur.parentElement;
            }
        }
        return null;
    };
    document.addEventListener("mousemove", (e) => {
        let entry = resolveMenuEntry(e.target);
        if (!entry && typeof document.elementsFromPoint === "function") {
            const stack = document.elementsFromPoint(e.clientX, e.clientY) || [];
            for (const elAt of stack) {
                entry = resolveMenuEntry(elAt);
                if (entry) break;
            }
        }
        if (!entry) { hide(); return; }
        const title = normalizePresetTitle(entry.textContent || "");
        if (!title) { hide(); return; }
        const thumb = getThumb(title);
        if (!thumb) {
            hide();
            if (title !== "오픈포즈" && !missingThumbTitles.has(title)) {
                missingThumbTitles.add(title);
                void ensureThumbsLoaded();
            }
            lastHoverTitle = title;
            return;
        }
        if (lastHoverTitle !== title) lastHoverTitle = title;
        if (img.src !== thumb) img.src = thumb;
        const r = entry.getBoundingClientRect();
        preview.style.left    = `${r.right + 8}px`;
        preview.style.top     = `${Math.max(8, r.top)}px`;
        preview.style.display = "block";
    }, true);

    document.addEventListener("click",   hide);
    document.addEventListener("keydown",  hide);
}

// ── Pose Editor Dialog ────────────────────────────────────────────────────────
class NakoPoseEditorDialog extends ComfyDialog {
    static timeout = 7000;
    static instance = null;

    static getInstance() {
        if (!NakoPoseEditorDialog.instance) {
            NakoPoseEditorDialog.instance = new NakoPoseEditorDialog();
        }
        return NakoPoseEditorDialog.instance;
    }

    constructor() {
        super();
        this.element = $el("div.comfy-modal", {
            parent: document.body,
            style:  { width: "80vw", height: "80vh" },
        }, [
            $el("div.comfy-modal-content", {
                style: { width: "100%", height: "100%" },
            }),
        ]);
        this.layoutReady = false;

        window.addEventListener("message", (event) => {
            if (!this.iframeElement || event.source !== this.iframeElement.contentWindow) return;
            const message = event.data;
            if (message?.modalId !== 0) return;

            if (message?.nakoPosePresetSaved) {
                const targetNode = ComfyApp.clipspace_return_node;
                targetNode?._nakoRefreshPosePresetTitles?.();
                this.close();
                return;
            }

            const targetNode = ComfyApp.clipspace_return_node;
            if (!targetNode?.widgets) return;

            const poseJsonWidget = targetNode.widgets.find((w) => w.name === "POSE_JSON");
            if (poseJsonWidget) {
                poseJsonWidget.value = JSON.stringify(message.poses);
            }
            const poseInputWidget = targetNode.widgets.find((w) => w.name === "pose_input_enabled");
            if (poseInputWidget && typeof message?.poseInputEnabled === "boolean") {
                poseInputWidget.value = message.poseInputEnabled;
                poseInputWidget.callback?.(message.poseInputEnabled);
            }

            ComfyApp.onClipspaceEditorClosed();
            this.close();
        });
    }

    close() { super.close(); }

    async show() {
        if (!this.layoutReady) {
            await this.createLayout();
            this.layoutReady = true;
        }

        const targetNode       = ComfyApp.clipspace_return_node;
        const poseJsonWidget   = targetNode?.widgets?.find((w) => w.name === "POSE_JSON");
        const resolutionWidget = targetNode?.widgets?.find((w) => w.name === "resolution_x");
        const poseInputWidget  = targetNode?.widgets?.find((w) => w.name === "pose_input_enabled");

        if (!poseJsonWidget) {
            console.error("NakoPoseEditor: 'POSE_JSON' widget missing.");
            return;
        }

        const textValue      = String(poseJsonWidget.value || "");
        const bgImage        = getNodeBackgroundImage(targetNode);
        const poseInputEnabled = poseInputWidget ? !!poseInputWidget.value : true;
        this.element.style.display = "flex";

        if (!textValue) {
            let resolutionX = 512;
            if (resolutionWidget && Number.isFinite(resolutionWidget.value)) {
                resolutionX = resolutionWidget.value;
            }
            let resolutionY = Math.floor(768 * (resolutionX * 1.0 / 512));
            if (resolutionX < 64) { resolutionX = 512; resolutionY = 768; }
            const blankPose = `[{"people":[{"pose_keypoints_2d":[],"face_keypoints_2d":[],"hand_left_keypoints_2d":[],"hand_right_keypoints_2d":[]}],"canvas_height":${resolutionY},"canvas_width":${resolutionX}}]`;
            this.setCanvasJSONString(blankPose, bgImage, poseInputEnabled);
        } else {
            this.setCanvasJSONString(textValue.replace(/'/g, '"'), bgImage, poseInputEnabled);
        }
    }

    async createLayout() {
        const modalContent = this.element.querySelector(".comfy-modal-content");
        while (modalContent.firstChild) modalContent.removeChild(modalContent.firstChild);

        let loaded = false;
        for (const src of EDITOR_CANDIDATE_SRCS) {
            this.iframeElement = $el("iframe", {
                src,
                style: { width: "100%", height: "100%", border: "none" },
            });
            modalContent.appendChild(this.iframeElement);
            try {
                await this.waitIframeReady();
                loaded = true;
                break;
            } catch {
                modalContent.removeChild(this.iframeElement);
                this.iframeElement = null;
            }
        }
        if (!loaded) throw new Error("NakoPoseEditor: local editor UI not found or failed to initialize.");
    }

    waitIframeReady() {
        return new Promise((resolve, reject) => {
            const receiveMessage = (event) => {
                if (!this.iframeElement || event.source !== this.iframeElement.contentWindow) return;
                if (event.data?.ready) {
                    window.removeEventListener("message", receiveMessage);
                    clearTimeout(timeoutHandle);
                    resolve();
                }
            };
            const timeoutHandle = setTimeout(() => {
                window.removeEventListener("message", receiveMessage);
                reject(new Error("Timeout waiting for editor iframe"));
            }, NakoPoseEditorDialog.timeout);
            window.addEventListener("message", receiveMessage);
        });
    }

    setCanvasJSONString(jsonString, bgImage = "", poseInputEnabled = true) {
        if (!this.iframeElement?.contentWindow) return;
        let poses;
        try { poses = JSON.parse(jsonString); } catch { poses = []; }
        this.iframeElement.contentWindow.postMessage({ modalId: 0, poses, bgImage, poseInputEnabled }, "*");
    }
}

async function openEditorForNode(node) {
    ensureNumericWidgetDefaults(node);
    ComfyApp.copyToClipspace(node);
    ComfyApp.clipspace_return_node = node;
    const dialog = NakoPoseEditorDialog.getInstance();
    await dialog.show();
}

// ── Extension 등록 ─────────────────────────────────────────────────────────────
app.registerExtension({
    name: "NakoPoseEditor",

    async setup() {
        registerNakoPoseWordsWithPysssss();
    },

    async beforeRegisterNodeDef(nodeType, nodeData, appRef) {
        if (nodeData.name !== "NakoPoseEditorNode") return;

        // configure() 오버라이드: widgets_values를 이름:값 맵으로 캡처 (위치 기반 오배정 방지)
        const originalConfigure = nodeType.prototype.configure;
        nodeType.prototype.configure = function (info) {
            if (info?.widgets_values?.length && this.widgets?.length) {
                const snap = {};
                let j = 0;
                for (const w of this.widgets) {
                    if (!w || w.options?.serialize === false) continue;
                    if (j < info.widgets_values.length) {
                        snap[w.name] = info.widgets_values[j++];
                    }
                }
                this._nakoWidgetSnapshot = snap;
            } else {
                this._nakoWidgetSnapshot = null;
            }
            return originalConfigure?.apply(this, arguments);
        };

        const originalOnNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const result = originalOnNodeCreated?.apply(this, arguments);

            // 기본 노드 색상 설정 (코어 청록)
            this.color   = NAKO_POSE_COLOR;
            this.bgcolor = NAKO_POSE_BGCOLOR;

            ensureNumericWidgetDefaults(this);
            ensurePoseInputToggleDefault(this);
            ensurePosePresetWidgets(this);

            // CN 위젯 숨김: 워크플로 로드 중(configuringGraph)에는 onConfigure에서 처리
            // 새 노드 생성 시에만 여기서 즉시 숨김 (configure() 이전 실행이 직렬화에 영향 없도록)
            if (!app.configuringGraph) {
                applyCnWidgetHiding(this);
            }

            // 툴바 설치
            installNakoPoseToolbar(this);

            // 포즈 에디터 열기 버튼
            const exists = this.widgets?.some((w) => w.name === "Open Pose Editor");
            if (!exists && typeof this.addWidget === "function") {
                this.addWidget("button", "Open Pose Editor", null, async () => {
                    try { await openEditorForNode(this); }
                    catch (error) { console.error(error); }
                }, { serialize: false });
            }
            return result;
        };

        const originalOnConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function () {
            const result = originalOnConfigure?.apply(this, arguments);
            ensureNumericWidgetDefaults(this);
            ensurePoseInputToggleDefault(this);
            ensurePosePresetWidgets(this);

            // 이름 기반 값 복원: configure()에서 캡처한 스냅샷으로 위치 기반 오배정 덮어쓰기
            const snap = this._nakoWidgetSnapshot;
            if (snap) {
                for (const [name, value] of Object.entries(snap)) {
                    const w = getWidget(this, name);
                    if (w) { w.value = value; w.callback?.(value); }
                }
                this._nakoWidgetSnapshot = null;
            }

            // 스냅샷으로 해결 안 되는 극단적 레거시 파일(위젯 순서 자체가 달랐던 경우) 복구
            repairLegacyShiftedPoseWidgets(this);

            // properties에서 JSON 표시 상태 복원 (새로고침 후에도 유지)
            if (this.properties?.nakoPoseJsonVisible !== undefined) {
                this._nakoPoseJsonVisible = this.properties.nakoPoseJsonVisible;
            }

            // configure() 후 위젯 상태 재적용 (값 로드 이후 숨김 처리)
            applyCnWidgetHiding(this);
            applyPoseJsonVisibility(this);
            return result;
        };

        const originalOnExecuted = nodeType.prototype.onExecuted;
        nodeType.prototype.onExecuted = function (message) {
            originalOnExecuted?.apply(this, arguments);
            if (!message?.POSE_JSON) return;

            const poseJsonWidget = this.widgets?.find((w) => w.name === "POSE_JSON");
            if (!poseJsonWidget) return;
            poseJsonWidget.value = message.POSE_JSON[0];

            const bg = Array.isArray(message.BG_IMAGE) ? message.BG_IMAGE[0] : "";
            this._nakoPoseBgImage = (typeof bg === "string") ? bg : "";

            const poseInputWidget = this.widgets?.find((w) => w.name === "pose_input_enabled");
            if (poseInputWidget) {
                const inputEnabled = Array.isArray(message.POSE_INPUT_ENABLED) ? !!message.POSE_INPUT_ENABLED[0] : true;
                poseInputWidget.value = inputEnabled;
                poseInputWidget.callback?.(inputEnabled);
            }

            // pose_tag_input 파싱 결과로 CN 위젯 값 업데이트
            if (Array.isArray(message.CN_RESOLVED) && message.CN_RESOLVED[0]) {
                const resolved = message.CN_RESOLVED[0];

                // Preset 콤보 표시 업데이트 (POSE_JSON은 이미 위에서 업데이트됨)
                if (resolved.preset) {
                    const presetWidget = getWidget(this, "Preset");
                    if (presetWidget && presetWidget.options?.values?.includes(resolved.preset)) {
                        presetWidget.value = resolved.preset;
                    }
                }


            }

            if (appRef?.graph) {
                appRef.graph.setDirtyCanvas(true, false);
            }
        };
    },
});
