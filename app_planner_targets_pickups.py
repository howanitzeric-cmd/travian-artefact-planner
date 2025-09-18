import streamlit as st
import pandas as pd
import re
import math

st.set_page_config(page_title="Travian Artifact Planner", layout="wide")

# -----------------------------
# Init session state
# -----------------------------
for key in ["OFFS", "CATTAS", "PICKUPS", "TARGETS", "PLANS"]:
    if key not in st.session_state:
        st.session_state[key] = pd.DataFrame()

# -----------------------------
# Artifact parsers
# -----------------------------
def parse_small_artifacts(html: str):
    section = re.split(r"Große Artefakte", html)[0]
    rows = []
    for line in section.splitlines():
        if "\t" in line:
            parts = line.split("\t")
            if len(parts) >= 3:
                name = parts[0].strip()
                player = parts[1].strip()
                alliance = parts[2].strip()
                distance = None
                m = re.search(r"\d+$", line)
                if m: distance = int(m.group(0))
                rows.append({
                    "Name": name,
                    "Player": player,
                    "Alliance": alliance,
                    "Distance": distance,
                    "Type": "small",
                    "Delete": False
                })
    return pd.DataFrame(rows)

def parse_large_artifacts(html: str):
    if "Große Artefakte" not in html:
        return pd.DataFrame()
    section = re.split(r"Große Artefakte", html)[1]
    rows = []
    for line in section.splitlines():
        if "\t" in line:
            parts = line.split("\t")
            if len(parts) >= 3:
                name = parts[0].strip()
                player = parts[1].strip()
                alliance = parts[2].strip()
                distance = None
                m = re.search(r"\d+$", line)
                if m: distance = int(m.group(0))
                rows.append({
                    "Name": name,
                    "Player": player,
                    "Alliance": alliance,
                    "Distance": distance,
                    "Type": "large",
                    "Delete": False
                })
    return pd.DataFrame(rows)

# -----------------------------
# Helper: Calculate travel time
# -----------------------------
def travel_time(x1, y1, x2, y2, speed, ts_level=0):
    dist = math.sqrt((x1 - x2)*2 + (y1 - y2)*2)
    bonus = 1 + (ts_level * 0.1)  # TS Bonus ~10% per level
    effective_speed = speed * bonus
    return dist / effective_speed if effective_speed > 0 else 9999

# -----------------------------
# Planner Logic
# -----------------------------
def create_plan():
    offs = st.session_state.OFFS.copy()
    cattas = st.session_state.CATTAS.copy()
    pickups = st.session_state.PICKUPS.copy()
    targets = st.session_state.TARGETS.copy()

    offs["used"] = False
    cattas["used"] = 0
    pickups["used"] = False

    plans = []

    # Priority: unique > large > small
    type_order = {"unique": 0, "large": 1, "small": 2}
    targets = targets.sort_values(by="Type", key=lambda col: col.map(type_order))

    for _, t in targets.iterrows():
        best = None
        for oi, o in offs[~offs["used"]].iterrows():
            for ci, c in cattas[cattas["used"] < 2].iterrows():
                for pi, p in pickups[~pickups["used"]].iterrows():
                    off_time = travel_time(o.X, o.Y, t.Distance, 0, o.Speed, o.TS)
                    cata_time = travel_time(c.X, c.Y, t.Distance, 0, c.Speed, c.TS)
                    pickup_time = travel_time(p.X, p.Y, t.Distance, 0, p.Speed, p.TS)
                    longest = max(off_time, cata_time, pickup_time)

                    if (best is None) or (longest < best["Time"]):
                        best = {
                            "Target": t["Name"],
                            "Type": t["Type"],
                            "Off": o["Name"],
                            "Catta": c["Name"],
                            "Pickup": p["Name"],
                            "Time": longest,
                            "off_i": oi,
                            "c_i": ci,
                            "p_i": pi
                        }

        if best:
            plans.append(best)
            offs.at[best["off_i"], "used"] = True
            cattas.at[best["c_i"], "used"] += 1
            pickups.at[best["p_i"], "used"] = True

    st.session_state.PLANS = pd.DataFrame(plans)

# -----------------------------
# Utility: editor with delete option
# -----------------------------
def editable_table(name, columns):
    if st.session_state[name].empty:
        st.session_state[name] = pd.DataFrame(columns=columns + ["Delete"])

    if "Delete" not in st.session_state[name].columns:
        st.session_state[name]["Delete"] = False

    st.session_state[name] = st.data_editor(
        st.session_state[name],
        num_rows="dynamic",
        use_container_width=True
    )

    col1, col2 = st.columns(2)
    with col1:
        if st.button(f"Delete selected {name}"):
            st.session_state[name] = st.session_state[name][~st.session_state[name]["Delete"]].drop(columns=["Delete"])
    with col2:
        if st.button(f"Clear all {name}"):
            st.session_state[name] = pd.DataFrame(columns=columns + ["Delete"])

    st.write(st.session_state[name])

# -----------------------------
# Tabs
# -----------------------------
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "⚔️ Offs", "🏹 Cattas", "🏛 Pickups", "🎯 Targets", "📑 Planner"
])

# -----------------------------
# OFFS Tab
# -----------------------------
with tab1:
    st.subheader("⚔️ Manage Offs")
    uploaded = st.file_uploader("Upload Offs (Excel)", type=["xlsx"])
    if uploaded:
        st.session_state.OFFS = pd.read_excel(uploaded)
    editable_table("OFFS", ["Name", "X", "Y", "Speed", "TS"])

# -----------------------------
# CATTAS Tab
# -----------------------------
with tab2:
    st.subheader("🏹 Manage Cattas")
    uploaded = st.file_uploader("Upload Cattas (Excel)", type=["xlsx"])
    if uploaded:
        st.session_state.CATTAS = pd.read_excel(uploaded)
    editable_table("CATTAS", ["Name", "X", "Y", "Speed", "TS"])

# -----------------------------
# PICKUPS Tab
# -----------------------------
with tab3:
    st.subheader("🏛 Manage Pickups / Treasuries")
    uploaded = st.file_uploader("Upload Pickups (Excel)", type=["xlsx"])
    if uploaded:
        st.session_state.PICKUPS = pd.read_excel(uploaded)
    editable_table("PICKUPS", ["Name", "X", "Y", "Treasury", "Speed", "TS"])

# -----------------------------
# TARGETS Tab
# -----------------------------
with tab4:
    st.subheader("🎯 Parse Targets from Travian HTML Source")
    text = st.text_area("Paste Travian artefact HTML here")

    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("Parse Small Artifacts"):
            df = parse_small_artifacts(text)
            if not df.empty:
                st.session_state.TARGETS = pd.concat([st.session_state.TARGETS, df], ignore_index=True)
                st.success(f"Added {len(df)} small artifacts")
    with col2:
        if st.button("Parse Large Artifacts"):
            df = parse_large_artifacts(text)
            if not df.empty:
                st.session_state.TARGETS = pd.concat([st.session_state.TARGETS, df], ignore_index=True)
                st.success(f"Added {len(df)} large artifacts")
    with col3:
        if st.button("Clear all Targets"):
            st.session_state.TARGETS = pd.DataFrame(columns=["Name", "Player", "Alliance", "Distance", "Type", "Delete"])

    # Targets table with delete option
    editable_table("TARGETS", ["Name", "Player", "Alliance", "Distance", "Type"])

# -----------------------------
# PLANNER Tab
# -----------------------------
with tab5:
    st.subheader("📑 Plan Runs")
    if st.button("Create Plan"):
        create_plan()

    if not st.session_state.PLANS.empty:
        st.success("Plan created!")
        st.dataframe(st.session_state.PLANS)
    else:
        st.info("No plan yet.")