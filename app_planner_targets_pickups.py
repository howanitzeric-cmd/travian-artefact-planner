import streamlit as st
import pandas as pd
import re, math
from bs4 import BeautifulSoup

st.set_page_config(page_title="Travian Artefact Planner", layout="wide")

# -----------------------------
# Session init
# -----------------------------
def _init_df(cols):
    return pd.DataFrame(columns=cols)

if "OFFS" not in st.session_state:
    st.session_state.OFFS = _init_df(["Village","Coords","Speed","TS","Type","Delete"])
if "CATTAS" not in st.session_state:
    st.session_state.CATTAS = _init_df(["Village","Coords","Speed","TS","UsesLeft","Delete"])
if "PICKUPS" not in st.session_state:
    st.session_state.PICKUPS = _init_df(["Village","Coords","Treasury","Speed","TS","Delete"])
if "TARGETS" not in st.session_state:
    st.session_state.TARGETS = _init_df(["Artefact","Coords","Type","Delete"])
if "PLANNED" not in st.session_state:
    st.session_state.PLANNED = pd.DataFrame()
if "UNPLANNED" not in st.session_state:
    st.session_state.UNPLANNED = pd.DataFrame()

VALID_TYPES = {"small","large","unique"}

# -----------------------------
# Helpers
# -----------------------------
COORD_RE = re.compile(r"\(\s*([−-]?\d+)\s*\|\s*([−-]?\d+)\s*\)")

def norm_minus(s: str) -> str:
    return s.replace("−","-") if isinstance(s,str) else s

def coords_to_xy(coord_str):
    if not isinstance(coord_str,str): return None
    m = COORD_RE.search(norm_minus(coord_str))
    if not m: return None
    x = int(norm_minus(m.group(1))); y = int(norm_minus(m.group(2)))
    return x, y

def ensure_delete_bool(df: pd.DataFrame):
    if "Delete" not in df.columns:
        df["Delete"] = False
    else:
        df["Delete"] = df["Delete"].fillna(False).astype(bool)
    return df

def editable_table(name: str, base_cols: list):
    """Edit table with Delete checkboxes + delete selected + clear all."""
    df = st.session_state[name].copy()
    df = ensure_delete_bool(df)
    df = st.data_editor(df, num_rows="dynamic", use_container_width=True, key=f"edit_{name}")
    df = ensure_delete_bool(df)
    # Delete selected
    if st.button(f"Delete selected in {name}", key=f"del_{name}"):
        df = df[~df["Delete"]].drop(columns=["Delete"], errors="ignore")
        df = ensure_delete_bool(df)
        st.session_state[name] = df
        st.success("Deleted selected rows.")
    # Clear all
    if st.button(f"Clear all {name}", key=f"clear_{name}"):
        st.session_state[name] = ensure_delete_bool(_init_df(base_cols))
        st.warning("Cleared.")
        df = st.session_state[name]
    st.session_state[name] = df
    return df

def normalize_off_type(s):
    if not isinstance(s,str): return ""
    s = s.strip().lower().replace("ß","ss")
    if "uni" in s: return "unique"
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
    if typ == "unique" or "unique" in name: return (1,0)
    if any(k in name for k in ["trainer","ausbilder"]): return (2,0)
    if any(k in name for k in ["diet","getreide","hunger"]): return (2,1)
    if any(k in name for k in ["boots","stiefel","schnellere truppen"]): return (2,2)
    if any(k in name for k in ["eyes","auge","späher","scout","spaeher"]): return (2,3)
    if any(k in name for k in ["plan","bauplan","great warehouse","lager","granary","blueprint"]): return (3,0)
    return (4,0)

def ts_travel_hours(x1,y1,x2,y2,speed,ts_level):
    """First 20 tiles base speed, remainder at speed*(1+0.1*TS)."""
    if speed is None: return float("inf")
    try:
        speed = float(speed); ts = float(ts_level) if ts_level not in (None,"") else 0.0
    except: return float("inf")
    dx = (x1-x2); dy=(y1-y2)
    d = math.hypot(dx,dy)
    if d <= 20: return d/speed
    first = 20/speed
    rest  = (d-20)/(speed*(1.0+0.1*ts))
    return first+rest

# -----------------------------
# Parse Travian HTML for artefacts
# -----------------------------
def parse_artifacts_html(html: str, arte_type_hint: str) -> pd.DataFrame:
    """
    Parse Travian artefact page HTML (page source) into targets.
    We try to extract rows (Name/Player/Alliance/Distance). If coords like (x|y) appear anywhere in the HTML,
    we associate them to the found artefacts in order; otherwise coords stay None and can be edited manually.
    """
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n")
    # Collect table-like lines in order
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    # Extract artefact name lines: they typically look like "Baumeister I (...)" etc., followed by Schatzkammer...
    arte_rows = []
    for i, line in enumerate(lines):
        low = line.lower()
        if ("schatzkammer" in low or "treasure" in low) and i >= 1:
            name = lines[i-1].strip()
            # classify type from name + hint
            typ = arte_type_hint
            lowname = name.lower()
            if "unique" in lowname or "einzig" in lowname:
                typ = "unique"
            elif arte_type_hint == "large" and typ != "unique":
                typ = "large"
            elif arte_type_hint == "small":
                typ = "small"
            arte_rows.append({"Artefact": name, "Type": typ})

    # Pull all coords present in HTML text (order preserved)
    coords = []
    for m in COORD_RE.finditer(norm_minus(text)):
        x = int(norm_minus(m.group(1))); y = int(norm_minus(m.group(2)))
        coords.append((x,y))

    # Attach coords in order (best-effort; user can edit)
    out = []
    for idx, row in enumerate(arte_rows):
        x=y=None
        if idx < len(coords):
            x,y = coords[idx]
        coord_str = f"({x}|{y})" if x is not None else ""
        out.append({"Artefact": row["Artefact"], "Coords": coord_str, "Type": row["Type"], "Delete": False})
    return pd.DataFrame(out)

# -----------------------------
# Upload helpers
# -----------------------------
def upload_excel(file, expected_cols):
    try:
        df = pd.read_excel(file)
        # keep only expected + try to map common aliases
        colmap = {c.lower(): c for c in df.columns}
        out = pd.DataFrame()
        for col in expected_cols:
            # attempt loose matching
            key = col.lower()
            if key in colmap:
                out[col] = df[colmap[key]]
            else:
                # try simple aliases
                aliases = {
                    "village": ["name","spieler","player","dorf"],
                    "coords":  ["coord","koords","x|y","x,y","coordinate"],
                    "speed":   ["geschwindigkeit","tempo"],
                    "ts":      ["tournament square","turnierplatz","tp"],
                    "type":    ["typ","art","category"],
                    "treasury":["schatzkammer","level","treasury level","kammer"],
                    "usesleft":["uses","left","rest"]
                }
                matched = None
                for a in aliases.get(key, []):
                    if a in colmap: matched = colmap[a]; break
                out[col] = df.get(matched, None)
        out["Delete"] = False
        return ensure_delete_bool(out)
    except Exception as e:
        st.error(f"Upload failed: {e}")
        return ensure_delete_bool(_init_df(expected_cols))

# -----------------------------
# Planner
# -----------------------------
def plan_once():
    offs = st.session_state.OFFS.copy()
    catt = st.session_state.CATTAS.copy()
    pick = st.session_state.PICKUPS.copy()
    tars = st.session_state.TARGETS.copy()

    # normalize fields
    offs["Type"] = offs["Type"].map(normalize_off_type).fillna("")
    catt["UsesLeft"] = pd.to_numeric(catt.get("UsesLeft", 2), errors="coerce").fillna(2).astype(int)
    pick["Treasury"] = pd.to_numeric(pick.get("Treasury", 0), errors="coerce").fillna(0).astype(int)

    # sort targets by priority
    tars["_p1"], tars["_p2"] = zip(*tars.apply(lambda r: priority_key(r["Artefact"], r["Type"]), axis=1)) if not tars.empty else ([],[])
    tars = tars.sort_values(by=["_p1","_p2"]).drop(columns=["_p1","_p2"], errors="ignore").reset_index(drop=True)

    planned = []
    unplanned = []

    used_off = set()
    used_pick = set()

    for _, t in tars.iterrows():
        arti = t.get("Artefact","")
        typ  = (t.get("Type","") or "").lower()
        target_xy = coords_to_xy(t.get("Coords",""))
        if typ not in VALID_TYPES:
            unplanned.append({"Artefact": arti, "Reason": f"Invalid type '{typ}'"})
            continue
        if not target_xy:
            unplanned.append({"Artefact": arti, "Reason": "Missing coordinates"})
            continue

        tx, ty = target_xy

        # pick OFF
        best_off = None; best_off_eta = float("inf"); best_off_idx = None
        for idx, o in offs.iterrows():
            if idx in used_off: continue
            if not off_compat(o.get("Type",""), typ): continue
            o_xy = coords_to_xy(o.get("Coords",""))
            if not o_xy: continue
            eta = ts_travel_hours(o_xy[0],o_xy[1],tx,ty,o.get("Speed",0),o.get("TS",0))
            if eta < best_off_eta:
                best_off_eta = eta; best_off = o; best_off_idx = idx
        if best_off is None:
            unplanned.append({"Artefact": arti, "Reason": "No compatible OFF"})
            continue

        # pick CATTAS (fastest with UsesLeft>0)
        best_cat = None; best_cat_eta = float("inf"); best_cat_idx = None
        for idx, c in catt.iterrows():
            if c.get("UsesLeft",0) <= 0: continue
            c_xy = coords_to_xy(c.get("Coords",""))
            if not c_xy: continue
            eta = ts_travel_hours(c_xy[0],c_xy[1],tx,ty,c.get("Speed",0),c.get("TS",0))
            if eta < best_cat_eta:
                best_cat_eta = eta; best_cat = c; best_cat_idx = idx
        if best_cat is None:
            unplanned.append({"Artefact": arti, "Reason": "No CATA with uses left"})
            continue

        # pick PICKUP (treasury compatible)
        best_pick_row=None; best_pick_eta=float("inf"); best_pick_idx=None
        for idx, p in pick.iterrows():
            if idx in used_pick: continue
            if not pickup_compat(p.get("Treasury",0), typ): continue
            p_xy = coords_to_xy(p.get("Coords",""))
            if not p_xy: continue
            eta = ts_travel_hours(p_xy[0],p_xy[1],tx,ty,p.get("Speed",0),p.get("TS",0))
            if eta < best_pick_eta:
                best_pick_eta = eta; best_pick_row=p; best_pick_idx=idx
        if best_pick_row is None:
            unplanned.append({"Artefact": arti, "Reason": "No compatible PICKUP (treasury)"})
            continue

        # reserve
        used_off.add(best_off_idx)
        used_pick.add(best_pick_idx)
        catt.at[best_cat_idx,"UsesLeft"] = int(catt.at[best_cat_idx,"UsesLeft"]) - 1

        arrival = max(best_off_eta, best_cat_eta, best_pick_eta)
        planned.append({
            "Artefact": arti,
            "Type": typ,
            "Target": t.get("Coords",""),
            "Off": best_off.get("Village",""),
            "Off ETA (h)": round(best_off_eta,2),
            "Cata": best_cat.get("Village",""),
            "Cata ETA (h)": round(best_cat_eta,2),
            "Pickup": best_pick_row.get("Village",""),
            "Pickup ETA (h)": round(best_pick_eta,2),
            "Arrival (h)": round(arrival,2)
        })

    st.session_state.PLANNED = pd.DataFrame(planned)
    st.session_state.UNPLANNED = pd.DataFrame(unplanned)

# -----------------------------
# UI — Tabs
# -----------------------------
st.title("🏺 Travian Artefact Planner")

tabs = st.tabs(["⚔️ Offs","🏹 Catas","🏛️ Pickups","🎯 Targets (HTML)","📑 Plan"])

# OFFS
with tabs[0]:
    st.subheader("⚔️ Offs (Type: small / large / unique — each OFF usable once)")
    up = st.file_uploader("Upload Offs (Excel)", type=["xlsx","xls"], key="upl_offs")
    if up:
        st.session_state.OFFS = upload_excel(up, ["Village","Coords","Speed","TS","Type"])
        st.success(f"Loaded {len(st.session_state.OFFS)} offs from file.")
    st.caption("Columns: Village, Coords like (x|y), Speed, TS (tournament square level), Type (small/large/unique).")
    editable_table("OFFS", ["Village","Coords","Speed","TS","Type"])

# CATTAS
with tabs[1]:
    st.subheader("🏹 Catas (each village usable up to 2×)")
    up = st.file_uploader("Upload Catas (Excel)", type=["xlsx","xls"], key="upl_catas")
    if up:
        df = upload_excel(up, ["Village","Coords","Speed","TS","UsesLeft"])
        if "UsesLeft" not in df.columns or df["UsesLeft"].isna().all():
            df["UsesLeft"] = 2
        st.session_state.CATTAS = df
        st.success(f"Loaded {len(st.session_state.CATTAS)} cata rows.")
    st.caption("Columns: Village, Coords (x|y), Speed, TS, UsesLeft (default 2).")
    # ensure default UsesLeft=2 for empty/new rows
    if "UsesLeft" in st.session_state.CATTAS.columns:
        st.session_state.CATTAS["UsesLeft"] = pd.to_numeric(st.session_state.CATTAS["UsesLeft"], errors="coerce").fillna(2).astype(int)
    editable_table("CATTAS", ["Village","Coords","Speed","TS","UsesLeft"])

# PICKUPS
with tabs[2]:
    st.subheader("🏛️ Pickups / Treasuries (each usable once)")
    up = st.file_uploader("Upload Pickups (Excel)", type=["xlsx","xls"], key="upl_pickups")
    if up:
        st.session_state.PICKUPS = upload_excel(up, ["Village","Coords","Treasury","Speed","TS"])
        st.success(f"Loaded {len(st.session_state.PICKUPS)} pickups.")
    st.caption("Columns: Village, Coords (x|y), Treasury (int), Speed, TS.")
    editable_table("PICKUPS", ["Village","Coords","Treasury","Speed","TS"])

# TARGETS
with tabs[3]:
    st.subheader("🎯 Targets from Travian HTML page source")
    st.caption("Paste the page *source* (HTML) of the artefact list. Parse small and large/unique separately if needed.")
    mode = st.radio("Which list is this HTML for?", ["Small","Large/Unique"], horizontal=True)
    html = st.text_area("Paste HTML source here", height=220)
    col1,col2,col3 = st.columns(3)
    with col1:
        if st.button("Parse from HTML"):
            if html.strip():
                hint = "small" if mode == "Small" else "large"
                df = parse_artifacts_html(html, hint)
                if not df.empty:
                    # normalize types to known set
                    df["Type"] = df["Type"].map(lambda x: "unique" if x=="unique" else ("large" if x=="large" else "small"))
                    cur = st.session_state.TARGETS.copy()
                    cur = pd.concat([cur, df], ignore_index=True)
                    st.session_state.TARGETS = ensure_delete_bool(cur)
                    st.success(f"Added {len(df)} targets.")
                else:
                    st.warning("No targets found in this HTML.")
            else:
                st.warning("Please paste HTML first.")
    with col2:
        if st.button("Clear all Targets"):
            st.session_state.TARGETS = ensure_delete_bool(_init_df(["Artefact","Coords","Type"]))
            st.warning("Targets cleared.")
    with col3:
        st.write("")  # spacer
    st.dataframe(st.session_state.TARGETS, use_container_width=True)

# PLAN
with tabs[4]:
    st.subheader("📑 Create Plan")
    st.caption("Rules: OFF=1×, CATA=2×/village, PICKUP=1×; Type & Treasury compatibility enforced; priority applied.")
    if st.button("Create / Update Plan", type="primary"):
        if st.session_state.OFFS.empty or st.session_state.CATTAS.empty or st.session_state.PICKUPS.empty or st.session_state.TARGETS.empty:
            st.error("Please provide OFFS, CATTAS, PICKUPS and TARGETS first.")
        else:
            plan_once()
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