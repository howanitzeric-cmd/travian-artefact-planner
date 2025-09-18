import streamlit as st
import pandas as pd
import re, math

st.set_page_config(page_title="Travian Artefact Planner", layout="wide")

# -----------------------------
# Init session state
# -----------------------------
if "OFFS" not in st.session_state:
    st.session_state.OFFS = pd.DataFrame(columns=["Name","X","Y","Speed","TS","Type"])
if "CATTAS" not in st.session_state:
    st.session_state.CATTAS = pd.DataFrame(columns=["Name","X","Y","Speed","TS","Count","UsesLeft"])
if "PICKUPS" not in st.session_state:
    st.session_state.PICKUPS = pd.DataFrame(columns=["Name","X","Y","Speed","TS","Treasury"])
if "TARGETS" not in st.session_state:
    st.session_state.TARGETS = pd.DataFrame(columns=["Name","Type","X","Y","Treasury","Distance"])

MAP_SIZE = 401

# -----------------------------
# Helpers
# -----------------------------
def wrap_distance(x1, y1, x2, y2, map_size=401):
    def d(a,b): return min(abs(a-b), map_size-abs(a-b))
    return math.hypot(d(x1,x2), d(y1,y2))

def travel_time(distance, speed, ts_level):
    if distance <= 20: return distance/speed
    first = 20/speed
    rest_speed = speed*(1+0.2*ts_level)
    rest = (distance-20)/rest_speed
    return first+rest

def fmt_hms(h):
    if h==float("inf"): return "-"
    tot = int(round(h*3600))
    H = tot//3600; M=(tot%3600)//60; S=tot%60
    return f"{H:02d}:{M:02d}:{S:02d}"

# -----------------------------
# Parse artefact overview text
# -----------------------------
COORD_RE = re.compile(r"\((-?\d+)\|(-?\d+)\)")
def parse_overview(text):
    rows=[]
    lines=[l.strip() for l in text.split("\n") if l.strip()]
    for i,line in enumerate(lines):
        if "Schatzkammer" in line or "treasure" in line.lower():
            name=lines[i-1]
            tre=None
            m=re.search(r"(\d+)", line)
            if m: tre=int(m.group(1))
            m2=COORD_RE.search("\n".join(lines[i:i+30]))
            x=y=None
            if m2: x=int(m2.group(1)); y=int(m2.group(2))
            rows.append(dict(Name=name,Type=name,X=x,Y=y,Treasury=tre))
    return pd.DataFrame(rows)

# -----------------------------
# Priority logic
# -----------------------------
def arti_priority(name, typ):
    n=(name or "").lower()
    if "unique" in n or "einzig" in n: return 1
    if "trainer" in n or "ausbilder" in n: return 2
    if "diet" in n or "getreide" in n: return 3
    if "boots" in n or "stiefel" in n: return 4
    if "eyes" in n or "auge" in n or "scout" in n: return 5
    if "plan" in n or "lager" in n or "granary" in n: return 6
    return 7

# -----------------------------
# Planner
# -----------------------------
def plan_targets(targets, offs, cattas, pickups):
    offs = offs.copy()
    offs["_used"] = False
    cattas = cattas.copy()
    if "UsesLeft" not in cattas.columns: cattas["UsesLeft"] = 2
    pickups = pickups.copy()
    pickups["_used"] = False

    targets = targets.copy()
    targets["priority"] = targets.apply(lambda r: arti_priority(r["Name"], r["Type"]), axis=1)
    targets = targets.sort_values("priority").reset_index(drop=True)

    planned = []
    unplanned = []

    for _, t in targets.iterrows():
        tx, ty = t["X"], t["Y"]

        # find OFF
        best_off = None; best_off_time=float("inf")
        for i,o in offs.iterrows():
            if o["_used"]: continue
            dist=wrap_distance(o["X"],o["Y"],tx,ty,MAP_SIZE)
            ttime=travel_time(dist,o["Speed"],o["TS"])
            if ttime<best_off_time:
                best_off_time=ttime; best_off=(i,o)
        if best_off is None:
            unplanned.append({"Artefact":t["Name"],"Reason":"No free OFF"})
            continue

        # find CATTAS
        best_catta = None; best_catta_time=float("inf")
        for i,c in cattas.iterrows():
            if c["UsesLeft"]<=0: continue
            dist=wrap_distance(c["X"],c["Y"],tx,ty,MAP_SIZE)
            ttime=travel_time(dist,c["Speed"],c["TS"])
            if ttime<best_catta_time:
                best_catta_time=ttime; best_catta=(i,c)
        if best_catta is None:
            unplanned.append({"Artefact":t["Name"],"Reason":"No free CATTAS"})
            continue

        # find PICKUP
        best_pick = None; best_pick_time=float("inf")
        for i,p in pickups.iterrows():
            if p["_used"]: continue
            dist=wrap_distance(p["X"],p["Y"],tx,ty,MAP_SIZE)
            ttime=travel_time(dist,p["Speed"],p["TS"])
            if ttime<best_pick_time:
                best_pick_time=ttime; best_pick=(i,p)
        if best_pick is None:
            unplanned.append({"Artefact":t["Name"],"Reason":"No free Pickup"})
            continue

        # reserve
        offs.at[best_off[0],"_used"]=True
        cattas.at[best_catta[0],"UsesLeft"] -=1
        pickups.at[best_pick[0],"_used"]=True

        # record
        planned.append({
            "Artefact":t["Name"],
            "Off":best_off[1]["Name"], "Off ETA":fmt_hms(best_off_time),
            "Cattas":best_catta[1]["Name"], "Catta ETA":fmt_hms(best_catta_time),
            "Pickup":best_pick[1]["Name"], "Pickup ETA":fmt_hms(best_pick_time),
            "Arrival":fmt_hms(max(best_off_time,best_catta_time,best_pick_time))
        })
    return pd.DataFrame(planned), pd.DataFrame(unplanned)

# -----------------------------
# Tabs
# -----------------------------
tab1, tab2, tab3, tab4, tab5 = st.tabs(["Offs","Cattas","Pickups","Targets","Planner"])

with tab1:
    st.subheader("⚔️ Manage Offs")
    st.session_state.OFFS = st.data_editor(st.session_state.OFFS, num_rows="dynamic")

with tab2:
    st.subheader("🏹 Manage Cattas (each row max 2x)")
    if "UsesLeft" not in st.session_state.CATTAS.columns:
        st.session_state.CATTAS["UsesLeft"]=2
    st.session_state.CATTAS = st.data_editor(st.session_state.CATTAS, num_rows="dynamic")

with tab3:
    st.subheader("🏛 Manage Pickups (Treasuries)")
    st.session_state.PICKUPS = st.data_editor(st.session_state.PICKUPS, num_rows="dynamic")

with tab4:
    st.subheader("📜 Paste Artefact Overview")
    text = st.text_area("Paste Travian artefact overview text/HTML here")
    if st.button("Parse Overview"):
        df = parse_overview(text)
        st.session_state.TARGETS = df
        st.success(f"Parsed {len(df)} targets")
    st.dataframe(st.session_state.TARGETS)

with tab5:
    st.subheader("🗺 Planner")
    if st.session_state.TARGETS.empty:
        st.info("Paste artefacts first.")
    elif st.session_state.OFFS.empty or st.session_state.CATTAS.empty or st.session_state.PICKUPS.empty:
        st.info("Fill Offs, Cattas, and Pickups first.")
    else:
        if st.button("Run Planner"):
            planned, unplanned = plan_targets(
                st.session_state.TARGETS,
                st.session_state.OFFS,
                st.session_state.CATTAS,
                st.session_state.PICKUPS
            )
            st.session_state["PLANNED"]=planned
            st.session_state["UNPLANNED"]=unplanned

        if "PLANNED" in st.session_state:
            if not st.session_state["PLANNED"].empty:
                st.success("Planned Runs")
                st.dataframe(st.session_state["PLANNED"])
            if not st.session_state["UNPLANNED"].empty:
                st.error("Unplanned Artefacts")
                st.dataframe(st.session_state["UNPLANNED"])