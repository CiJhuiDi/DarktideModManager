# -*- coding: utf-8 -*-
"""方案预设（APIRouter 路由）。"""
import json
import re
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import patch
import state
from load_order import enabled_names, read_load_order, set_load_order

router = APIRouter()


class ProfileBody(BaseModel):
    name: str = ""


def profile_path(name: str) -> Path:
    safe = re.sub(r'[\\/:*?"<>|]', "_", name.strip())
    if not safe:
        raise HTTPException(400, "预设名不能为空")
    return state.PROFILES_DIR / f"{safe}.json"


@router.get("/api/profiles")
def api_profiles():
    if not state.PROFILES_DIR.is_dir():
        return {"profiles": []}
    profiles = []
    for f in sorted(state.PROFILES_DIR.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            profiles.append({
                "name": data.get("name", f.stem),
                "mods": data.get("mods", []),
                "count": len(data.get("mods", [])),
                "created": data.get("created", ""),
            })
        except Exception:
            continue
    return {"profiles": profiles}


@router.post("/api/profiles")
def api_profile_save(body: ProfileBody):
    entries = read_load_order()
    mods = enabled_names(entries)
    state.PROFILES_DIR.mkdir(exist_ok=True)
    data = {"name": body.name.strip(), "mods": mods, "created": datetime.now().isoformat(timespec="seconds")}
    profile_path(body.name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "profile": data}


@router.post("/api/profiles/{name}/apply")
def api_profile_apply(name: str):
    g = patch.guard_game_running("应用预设")
    if g:
        return g
    p = profile_path(name)
    if not p.exists():
        raise HTTPException(404, "预设不存在")
    data = json.loads(p.read_text(encoding="utf-8"))
    return set_load_order(data.get("mods", []))


@router.delete("/api/profiles/{name}")
def api_profile_delete(name: str):
    p = profile_path(name)
    if p.exists():
        p.unlink()
    return {"ok": True}
