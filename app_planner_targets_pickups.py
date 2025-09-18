import streamlit as st
import pandas as pd
import re, math
from bs4 import BeautifulSoup

st.set_page_config(page_title="Travian Artefact Planner", layout="wide")

# ==============================
# Session init (clean defaults)
# ==============================
def _df(cols): return pd.DataFrame(columns=cols)

if "OFFS" not in st.session_state:
    st.session_state.OFFS = _df(["Name","coord_x","coord_y","Speed","TS","Type"])
if "CATTAS" not in st.session_state:
    st.session_state.CATTAS = _df(["Name","coord_x","coord_y","Speed","TS","UsesLeft"])
if "PICKUPS" not in st.session_state:
    st.session_state.PICKUPS = _df(["Name","coord_x","coord_y","Treasury","Speed","TS"])
if "TARGETS" not in st.session_state:
    st.session_state.TARGETS = _df(["Artefact","Type","coord_x","coord_y"])
if "PLANNED" not in st.session_state:
    st.session_state.PLANNED = pd.DataFrame()
if "UNPLANNED" not in st.session_state:
    st.session_state.UNPLANNED = pd.DataFrame()

VALID_TYPES = {"small","large","unique"}
COORD_RE = re.compile(r"\(\s*([−-]?\d+)\s*\|\s*([−-]?\d+)\s*\)")

def nminus(s:str) -> str:
    return s.replace("−","-") if isinstance(s,str) else s

# ==================================
# Data editor w/ per-row delete UX
# ==================================
def editor_with_delete(df: pd.DataFrame, cols: list, key: str, title: str):
    st.markdown(f"### {title}")
    # add a temporary delete checkbox column (never persisted outside this session render)
    tmp = df.copy()
    tmp["_DELETE"] = False
    edited = st.data_editor(
        tmp, num_rows="dynamic", use_container_width=True,
        column_config={"_DELETE": st.column_config.CheckboxColumn("Delete")},
        key=f"editor_{key}"
    )
    # delete selected
    if st.button(f"Delete selected in {title}", key=f"delbtn_{key}"):
        edited = edited[~edited["_DELETE"]].drop(columns=["_DELETE"])
        st.success("Selected rows deleted.")
    # clear all
    if st.button(f"Clear all {title}", key=f"clearbtn_{key}"):
        edited = _df(cols)
        st.warning("All rows cleared.")
    # normalize cols & types
    for c in cols:
        if c not in edited.columns: edited[c] = pd.NA
    edited = edited[cols]
    st.session_state[key] = edited
    return edited

# ==========================
# Upload helpers (optional)
# ==========================
def upload_excel(file, expected_cols, key_for_state):
    try:
        df = pd.read_excel(file)
        # map common aliases
        lower_map = {c.lower(): c for c in df.columns}
        aliases = {
            "name": ["village","dorf","spieler","player"],
            "coord_x": ["x","coord x","koordinate x"],
            "coord_y": ["y","coord y","koordinate y"],
            "speed": ["geschwindigkeit","tempo"],
            "ts": ["tournament square","turnierplatz","tp"],
            "type": ["typ","art","category"],
            "treasury": ["treasury level","schatzkammer","kammer","level"],
            "usesleft": ["uses","left","rest"]
        }
        out = pd.DataFrame()
        for col in expected_cols:
            if col in df.columns:
                out[col] = df[col]
                continue
            if col.lower() in lower_map:
                out[col] = df[lower_map[col.lower()]]
                continue
            matched = None
            for a in aliases.get(col.lower(), []):
                if a in lower_map:
                    matched = lower_map[a]
                    break
            out[col] = df.get(matched, pd.NA)
        # also support legacy "Coords" -> split
        if "Coords" in df.columns and ("coord_x" in expected_cols or "coord_y" in expected_cols):
            for i, val in df["Coords"].fillna("").items():
                m = COORD_RE.search(nminus(str(val)))
                if m:
                    if "coord_x" in expected_cols:
                        out.at[i,"coord_x"] = int(nminus(m.group(1)))
                    if "coord_y" in expected_cols:
                        out.at[i,"coord_y"] = int(nminus(m.group(2)))
        # defaults
        if "UsesLeft" in out.columns:
            out["UsesLeft"] = pd.to_numeric(out["UsesLeft"], errors="coerce").fillna(2).astype(int)
        st.session_state[key_for_state] = out[expected_cols]
        st.success(f"Loaded {len(out)} rows into {key_for_state}.")
    except Exception as e:
        st.error(f"Upload failed: {e}")

# ==========================
# HTML parsing (Targets)
# ==========================
def classify_type(group_hint:str, name:str) -> str:
    n = (name or "").lower()
    if "unique" in n or "einzig" in n: return "unique"
    if group_hint == "large": return "large"
    return "small"

def parse_artefacts_html(html: str, group_hint: str) -> pd.DataFrame:
    """
    Parse Travian artefact 'overview' HTML. These tables have headers like Name/Spieler/Allianz/Entfernung.
    Coordinates are usually NOT present there -> we leave coord_x/y empty (you can fill manually or attach later).
    """
    soup = BeautifulSoup(html, "html.parser")
    rows = []
    for tbl in soup.find_all("table"):
        headers = " ".join(th.get_text(strip=True).lower() for th in tbl.find_all("th"))
        if "name" in headers and ("entfernung" in headers or "distance" in headers):
            for tr in tbl.find_all("tr"):
                tds = tr.find_all("td")
                if not tds: continue
                name = tds[0].get_text(" ", strip=True)
                if not name: continue
                typ = classify_type(group_hint, name)
                rows.append({"Artefact": name, "Type": typ, "coord_x": pd.NA, "coord_y": pd.NA})
    return pd.DataFrame(rows)

def parse_coords_from_any_text(text: str) -> list[tuple[int,int]]:
    coords = []
    for m in COORD_RE.finditer(nminus(text)):
        x = int(nminus(m.group(1))); y = int(nminus(m.group(2)))
        coords.append((x,y))
    return coords

def attach_coords_in_order(targets_df: pd.DataFrame, coords: list[tuple[int,int]]) -> pd.DataFrame:
    df = targets_df.copy()
    j = 0
    for i in df.index:
        if (pd.isna(df.at[i,"coord_x"]) or pd.isna(df.at[i,"coord_y"])) and j < len(coords):
            df.at[i,"coord_x"], df.at[i,"coord_y"] = coords[j]
            j += 1
    return df

# ==========================
# Planner utilities
# ==========================
def normalize_off_type(s):
    if not isinstance(s,str): return ""
    s = s.strip().lower().replace("ß","ss")
    if "uni" in s or "einzig" in s: return "unique"
    if any(w in s for w in ["gross","groß","large","big"]): return "large"
    if "small" in s or "klein" in s: return "small"
    return s

def off_compat(off_type, arti_type):
    off_type = normalize_off_type(off_type)
    if off_type == "small":  return arti_type == "small"
    if off_type == "large":  return arti_type in {"large","small"}
    if off_type == "unique": return True
    return False

def pickup_compat(treasury, arti_type):
    try: t = int(treasury)
    except: return False
    if t < 20: return arti_type == "small"
    return True

def priority_key(name, typ):
    name = (name or "").lower()
    typ  = (typ or "").lower()
    if typ == "unique" or "unique" in name or "einzig" in name: return (1,0)
    if any(k in name for k in ["trainer","ausbilder"]): return (2,0)
    if any(k in name for k in ["diet","getreide","hunger"]): return (2,1)
    if any(k in name for k in ["boots","stiefel","schnellere truppen"]): return (2,2)
    if any(k in name for k in ["eyes","auge","späher","scout","spaeher"]): return (2,3)
    if any(k in name for k in ["plan","bauplan","great warehouse","lager","granary","blueprint","weltwunder"]): return (3,0)
    return (4,0)

def ts_travel_hours(x1,y1,x2,y2,speed,ts_level):
    # first 20 tiles at base speed, remainder with TS bonus (+10% per level)
    try:
        speed = float(speed); ts = float(ts_level) if ts_level not in (None,"") else 0.0
    except: return float("inf")
    d = math.hypot((x1-x2),(y1-y2))
    if d <= 20: return d/speed
    first = 20/speed
    rest  = (d-20)/(speed*(1.0+0.1*ts))
    return first+rest

# ==========================
# Planner (assignment)
# ==========================
def create_plan():
    offs = st.session_state.OFFS.copy()
    cats = st.session_state.CATTAS.copy()
    pics = st.session_state.PICKUPS.copy()
    tars = st.session_state.TARGETS.copy()

    # normalize types/defaults
    offs["Type"] = offs["Type"].map(normalize_off_type).fillna("")
    cats["UsesLeft"] = pd.to_numeric(cats.get("UsesLeft", 2), errors="coerce").fillna(2).astype(int)
    pics["Treasury"] = pd.to_numeric(pics.get("Treasury", 0), errors="coerce").fillna(0).astype(int)

    # sort targets by priority
    if not tars.empty:
        p1, p2 = zip(*tars.apply(lambda r: priority_key(r["Artefact"], r["Type"]), axis=1))
        tars["_p1"], tars["_p2"] = p1, p2
        tars = tars.sort_values(by=["_p1","_p2"]).drop(columns=["_p1","_p2"])

    planned, unplanned = [], []
    used_off, used_pick = set(), set()

    for _, t in tars.iterrows():
        name = t.get("Artefact",""); typ = (t.get("Type","") or "").lower()
        tx, ty = t.get("coord_x"), t.get("coord_y")

        # basic validations
        if typ not in VALID_TYPES:
            unplanned.append({"Artefact": name, "Reason":"Invalid type"}); continue
        if pd.isna(tx) or pd.isna(ty):
            unplanned.append({"Artefact": name, "Reason":"Missing coordinates"}); continue
        tx, ty = float(tx), float(ty)

        # OFF match (usable once, type compat, fastest ETA)
        best_off=None; best_off_eta=float("inf"); best_off_idx=None
        for idx, o in offs.iterrows():
            if idx in used_off: continue
            if not off_compat(o.get("Type",""), typ): continue
            if pd.isna(o.get("coord_x")) or pd.isna(o.get("coord_y")): continue
            eta = ts_travel_hours(float(o["coord_x"]),float(o["coord_y"]),tx,ty,o.get("Speed",0),o.get("TS",0))
            if eta < best_off_eta:
                best_off_eta=eta; best_off=o; best_off_idx=idx
        if best_off is None:
            unplanned.append({"Artefact": name, "Reason":"No compatible OFF"}); continue

        # CATA match (max 2 uses; fastest ETA)
        best_cat=None; best_cat_eta=float("inf"); best_cat_idx=None
        for idx, c in cats.iterrows():
            if c.get("UsesLeft",0) <= 0: continue
            if pd.isna(c.get("coord_x")) or pd.isna(c.get("coord_y")): continue
            eta = ts_travel_hours(float(c["coord_x"]),float(c["coord_y"]),tx,ty,c.get("Speed",0),c.get("TS",0))
            if eta < best_cat_eta:
                best_cat_eta=eta; best_cat=c; best_cat_idx=idx
        if best_cat is None:
            unplanned.append({"Artefact": name, "Reason":"No CATA with uses left"}); continue

        # PICKUP match (treasury compat; usable once; fastest ETA)
        best_pick=None; best_pick_eta=float("inf"); best_pick_idx=None
        for idx, p in pics.iterrows():
            if idx in used_pick: continue
            if not pickup_compat(p.get("Treasury",0), typ): continue
            if pd.isna(p.get("coord_x")) or pd.isna(p.get("coord_y")): continue
            eta = ts_travel_hours(float(p["coord_x"]),float(p["coord_y"]),tx,ty,p.get("Speed",0),p.get("TS",0))
            if eta < best_pick_eta:
                best_pick_eta=eta; best_pick=p; best_pick_idx=idx
        if best_pick is None:
            unplanned.append({"Artefact": name, "Reason":"No compatible PICKUP (treasury)"}); continue

        # reserve resources
        used_off.add(best_off_idx)
        used_pick.add(best_pick_idx)
        cats.at[best_cat_idx,"UsesLeft"] = int(cats.at[best_cat_idx,"UsesLeft"]) - 1

        arrival = max(best_off_eta, best_cat_eta, best_pick_eta)
        planned.append({
            "Artefact": name,
            "Type": typ,
            "Target (x|y)": f"({int(tx)}|{int(ty)})",
            "Off": best_off.get("Name",""),
            "Off ETA (h)": round(best_off_eta,2),
            "Cata": best_cat.get("Name",""),
            "Cata ETA (h)": round(best_cat_eta,2),
            "Pickup": best_pick.get("Name",""),
            "Pickup ETA (h)": round(best_pick_eta,2),
            "Arrival (h)": round(arrival,2)
        })

    st.session_state.PLANNED = pd.DataFrame(planned)
    st.session_state.UNPLANNED = pd.DataFrame(unplanned)

# ==========================
# UI (Tabs)
# ==========================
st.title("🏺 Travian Artefact Planner")

tab_offs, tab_cats, tab_pics, tab_tars, tab_plan = st.tabs([
    "⚔️ Offs", "🏹 Catas", "🏛️ Pickups", "🎯 Targets (HTML)", "📑 Plan"
])

with tab_offs:
    st.subheader("Offs (Type: small / large / unique; OFF usable once)")
    up = st.file_uploader("Upload Offs (Excel)", type=["xlsx","xls"], key="upl_offs")
    if up:
        upload_excel(up, ["Name","coord_x","coord_y","Speed","TS","Type"], "OFFS")
    editor_with_delete(st.session_state.OFFS, ["Name","coord_x","coord_y","Speed","TS","Type"], "OFFS", "Offs")

with tab_cats:
    st.subheader("Catas (each row usable up to 2×)")
    up = st.file_uploader("Upload Catas (Excel)", type=["xlsx","xls"], key="upl_cats")
    if up:
        upload_excel(up, ["Name","coord_x","coord_y","Speed","TS","UsesLeft"], "CATTAS")
        if st.session_state.CATTAS["UsesLeft"].isna().all():
            st.session_state.CATTAS["UsesLeft"] = 2
    editor_with_delete(st.session_state.CATTAS, ["Name","coord_x","coord_y","Speed","TS","UsesLeft"], "CATTAS", "Catas")

with tab_pics:
    st.subheader("Pickups / Treasuries (usable once; Treasury<20 = small only, ≥20 = any)")
    up = st.file_uploader("Upload Pickups (Excel)", type=["xlsx","xls"], key="upl_pics")
    if up:
        upload_excel(up, ["Name","coord_x","coord_y","Treasury","Speed","TS"], "PICKUPS")
    editor_with_delete(st.session_state.PICKUPS, ["Name","coord_x","coord_y","Treasury","Speed","TS"], "PICKUPS", "Pickups")

with tab_tars:
    st.subheader("Targets from Travian HTML")
    st.caption("1) Paste artefact page *HTML* (Small or Large/Unique) → Parse names & types. "
               "2) (Optional) Paste any text/HTML that contains coordinates like (x|y) → attach by order. "
               "You can also edit coord_x/coord_y manually below.")
    colA, colB = st.columns(2)
    with colA:
        mode = st.radio("This HTML is for:", ["Small","Large/Unique"], horizontal=True, key="mode_art")
        html_art = st.text_area("Paste artefact page HTML", height=220, key="html_art")
        if st.button("Parse artefacts", key="parse_art"):
            if html_art.strip():
                hint = "small" if st.session_state.mode_art == "Small" else "large"
                df = parse_artefacts_html(html_art, hint)
                if df.empty:
                    st.warning("No artefacts found in this HTML.")
                else:
                    st.session_state.TARGETS = pd.concat([st.session_state.TARGETS, df], ignore_index=True)
                    st.success(f"Added {len(df)} targets. Fill in coordinates below or attach via right box.")
            else:
                st.warning("Please paste artefact HTML.")
    with colB:
        html_coords = st.text_area("Paste ANY text/HTML that contains coordinates (x|y)", height=220, key="html_coords")
        if st.button("Attach coords by order", key="attach_coords"):
            coords = parse_coords_from_any_text(html_coords)
            if not coords:
                st.warning("No coordinates found.")
            else:
                st.session_state.TARGETS = attach_coords_in_order(st.session_state.TARGETS, coords)
                st.success("Coordinates attached (by order).")
    editor_with_delete(st.session_state.TARGETS, ["Artefact","Type","coord_x","coord_y"], "TARGETS", "Targets")

with tab_plan:
    st.subheader("Create Plan")
    st.caption("Rules: OFF=1×, CATA=2×/row, PICKUP=1×; Type & Treasury compatibility; priority applied; TS travel time.")
    if st.button("Create / Update Plan", type="primary"):
        if st.session_state.OFFS.empty or st.session_state.CATTAS.empty or st.session_state.PICKUPS.empty or st.session_state.TARGETS.empty:
            st.error("Please provide OFFS, CATTAS, PICKUPS and TARGETS first.")
        else:
            create_plan()
            st.success("Plan created.")
    if not st.session_state.PLANNED.empty:
        st.markdown("### ✅ Planned")
        st.dataframe(st.session_state.PLANNED, use_container_width=True)
        st.download_button("Download Planned (CSV)", st.session_state.PLANNED.to_csv(index=False).encode("utf-8"),
                           file_name="planned.csv", mime="text/csv")
    if not st.session_state.UNPLANNED.empty:
        st.markdown("### ❗ Unplanned")
        st.dataframe(st.session_state.UNPLANNED, use_container_width=True)
        st.download_button("Download Unplanned (CSV)", st.session_state.UNPLANNED.to_csv(index=False).encode("utf-8"),
                           file_name="unplanned.csv", mime="text/csv")