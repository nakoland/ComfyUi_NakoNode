import { app } from "../../scripts/app.js";

let _translations = {};

export async function initNakoI18n() {
    try {
        const locale = app.ui.settings.getSettingValue("Comfy.Locale") || "en";
        const resp = await fetch("/i18n");
        if (!resp.ok) return;
        const data = await resp.json();
        _translations = (data[locale] && data[locale].NakoNode)
                     || (data["en"]     && data["en"].NakoNode)
                     || {};
    } catch (e) {
        console.warn("[NakoNode] i18n load failed, using defaults:", e);
    }
}

export function t(key) {
    const result = key.split(".").reduce(
        (obj, k) => (obj && typeof obj === "object") ? obj[k] : undefined,
        _translations
    );
    return (result !== undefined && result !== null && typeof result !== "object")
        ? result
        : key;
}

export function getTranslations() {
    return _translations;
}
