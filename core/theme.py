# -*- coding: utf-8 -*-
"""主题设置 / 自定义主题（APIRouter 路由）。"""
import json
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from core import state
from core.state import load_config

router = APIRouter()

CUSTOM_THEME_DIR = state.BASE_DIR / "custom_theme"
CUSTOM_THEME_MAX_BYTES = 8 * 1024 * 1024  # 8MB
CUSTOM_THEME_EXT = (".jpg", ".jpeg", ".png", ".webp", ".bmp")


class ThemeBody(BaseModel):
    theme: str = ""      # abyss/dawn/pleasure/plague/rage/mystic/emperor/random
    grad: str = ""       # diag/hori/vert/radial


def custom_theme_img():
    """返回已存在的自定义主题图片路径（任意 bg.*），无则 None"""
    if CUSTOM_THEME_DIR.exists():
        for p in CUSTOM_THEME_DIR.glob("bg.*"):
            return p
    return None


def custom_theme_state() -> dict:
    """自定义主题状态：是否存在图片 + 亮/暗模式"""
    cfg = load_config()
    return {
        "exists": custom_theme_img() is not None,
        "mode": cfg.get("custom_theme_mode", "dark"),
    }


@router.post("/api/theme")
def api_theme(body: ThemeBody):
    """保存主题设置（theme + 渐变方向）到 config.json"""
    valid_themes = ("abyss", "dawn", "pleasure", "plague", "rage", "mystic", "emperor", "random")
    valid_grads = ("diag", "hori", "vert", "radial")
    cfg = load_config()
    if body.theme in valid_themes:
        cfg["theme"] = body.theme
    if body.grad in valid_grads:
        cfg["grad"] = body.grad
    try:
        state.CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        return {"ok": False, "error": f"写入配置失败: {e}"}
    return {"ok": True, "theme": cfg.get("theme", "abyss"), "grad": cfg.get("grad", "diag")}


@router.post("/api/theme/custom")
async def api_theme_custom_upload(mode: str = Form("dark"), file: UploadFile = File(...)):
    """上传自定义主题背景图（jpg/png/webp/bmp，≤8MB），mode=dark/light"""
    if mode not in ("dark", "light"):
        return {"ok": False, "error": "模式只能是 dark 或 light"}
    ext = Path(file.filename or "").suffix.lower()
    if ext not in CUSTOM_THEME_EXT:
        return {"ok": False, "error": f"仅支持 {'/'.join(e.lstrip('.') for e in CUSTOM_THEME_EXT)} 格式"}
    try:
        data = await file.read()
    except Exception as e:
        return {"ok": False, "error": f"读取文件失败: {e}"}
    if not data:
        return {"ok": False, "error": "文件内容为空"}
    if len(data) > CUSTOM_THEME_MAX_BYTES:
        return {"ok": False, "error": "图片超过 8MB 限制"}
    try:
        CUSTOM_THEME_DIR.mkdir(parents=True, exist_ok=True)
        ext = ".jpg" if ext in (".jpg", ".jpeg") else ext
        target = CUSTOM_THEME_DIR / ("bg" + ext)
        target.write_bytes(data)
        for old in CUSTOM_THEME_DIR.glob("bg.*"):
            if old.name != target.name:
                old.unlink(missing_ok=True)
        cfg = load_config()
        cfg["theme"] = "custom"
        cfg["custom_theme_mode"] = mode
        state.CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        return {"ok": False, "error": f"保存失败: {e}"}
    return {"ok": True, "mode": mode}


@router.get("/api/theme/custom/image")
def api_theme_custom_image():
    """返回自定义主题背景图"""
    img = custom_theme_img()
    if img is None:
        raise HTTPException(404, "自定义主题图片不存在")
    return FileResponse(img)


@router.post("/api/theme/custom/remove")
def api_theme_custom_remove():
    """移除自定义主题图片，恢复默认主题"""
    removed = False
    for old in (CUSTOM_THEME_DIR.glob("bg.*") if CUSTOM_THEME_DIR.exists() else []):
        old.unlink(missing_ok=True)
        removed = True
    cfg = load_config()
    cfg.pop("custom_theme_mode", None)
    if cfg.get("theme") == "custom":
        cfg["theme"] = "abyss"
    try:
        state.CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        return {"ok": False, "error": f"写入配置失败: {e}"}
    return {"ok": True, "removed": removed}
