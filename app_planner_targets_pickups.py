import streamlit as st
import pandas as pd
import re
import math

st.set_page_config(page_title="Travian Artefact Planner", layout="wide")

# ------------------ Hilfsfunktionen ------------------

def distance(coord1, coord2):
    """Berechnet Distanz zwischen zwei Koordinaten."""
    return math.sqrt((coord1[0] - coord2[0])*2 + (coord1[1] - coord2[1])*2)

def travel_time(coord1, coord2, speed):
    """Berechnet Laufzeit (Stunden)."""
    dist = distance(coord1, coord2)
    return round(dist / speed, 2)

def editable_table(name, columns):
    """Editierbare Tabellen mit Delete-Option."""
    if name not in st.session_state:
        st.session_state[name] = pd.DataFrame(columns=columns)

    df = st.session_state[name]

    if "Delete" not in df.columns:
        df["Delete"] = False
    else:
        df["Delete"] = df["Delete"].fillna(False).astype(bool)

    st.markdown(f"### {name}")
    edited = st.data_editor(
        df,
        num_rows="dynamic",
        use_container_width=True,
        key=f"editor_{name}"
    )

    if not edited.empty and "Delete" in edited.columns:
        edited = edited[~edited["Delete"]].drop(columns=["Delete"], errors="ignore")

    st.session_state[name] = edited

    col1, col2 = st.columns([1, 5])
    with col1:
        if st.button(f"Clear all {name}", key=f"clear_{name}"):
            st.session_state[name] = pd.DataFrame(columns=columns)

    return st.session_state[name]

def parse_artifacts(text, arte_type):
    """Parser für Artefakt-Koordinaten (kleine/große)."""
    pattern = r"\(([-]?\d+)\|([-]?\d+)\)"
    coords = re.findall(pattern, text)
    df = pd.DataFrame(coords, columns=["x", "y"])
    df["x"] = df["x"].astype(int)
    df["y"] = df["y"].astype(int)
    df["Type"] = arte_type
    return df

def match_artefacts(offs, catas, pickups, targets):
    """Erstellt Plan: Offs, Catas, Pickups -> Targets."""
    plan = []
    used_offs, used_pickups = set(), set()

    # Priorität: Unique -> Great -> Small
    priority = {"Unique": 1, "Great": 2, "Small": 3}

    targets_sorted = targets.sort_values(by="Type", key=lambda x: x.map(priority))

    for _, target in targets_sorted.iterrows():
        tx, ty, ttype = target["x"], target["y"], target["Type"]

        # Passendes Off suchen
        available_offs = offs[~offs["Name"].isin(used_offs)]
        if available_offs.empty:
            continue
        best_off = None
        best_time = float("inf")

        for _, off in available_offs.iterrows():
            try:
                ox, oy = map(int, off["Coords"].split(","))
                time = travel_time((ox, oy), (tx, ty), speed=10)
                if time < best_time:
                    best_time = time
                    best_off = off
            except:
                continue

        if best_off is None:
            continue

        # Pickup suchen
        available_pickups = pickups[~pickups["Village"].isin(used_pickups)]
        best_pickup = None
        for _, pu in available_pickups.iterrows():
            if ttype == "Unique" and pu["TreasuryLevel"] >= 20:
                best_pickup = pu
                break
            elif ttype == "Great" and pu["TreasuryLevel"] >= 20:
                best_pickup = pu
                break
            elif ttype == "Small" and pu["TreasuryLevel"] >= 10:
                best_pickup = pu
                break

        if best_pickup is None:
            continue

        # Kata als Dummy anhängen (1. freie nehmen)
        best_cata = catas.iloc[0] if not catas.empty else None

        plan.append({
            "Target": f"{ttype} ({tx}|{ty})",
            "Off": best_off["Name"],
            "Pickup": best_pickup["Village"],
            "Cata": best_cata["Name"] if best_cata is not None else "-",
            "TravelTime(h)": best_time
        })

        used_offs.add(best_off["Name"])
        used_pickups.add(best_pickup["Village"])

    return pd.DataFrame(plan)

# ------------------ UI ------------------

st.title("🏺 Travian Artefact Planner")

# Uploads
st.sidebar.header("📤 Upload Data")
uploaded_offs = st.sidebar.file_uploader("Upload Offs Excel", type=["xlsx"])
uploaded_catas = st.sidebar.file_uploader("Upload Catas Excel", type=["xlsx"])
uploaded_pickups = st.sidebar.file_uploader("Upload Pickups Excel", type=["xlsx"])

if uploaded_offs:
    st.session_state["Offs"] = pd.read_excel(uploaded_offs)
if uploaded_catas:
    st.session_state["Catas"] = pd.read_excel(uploaded_catas)
if uploaded_pickups:
    st.session_state["Pickups"] = pd.read_excel(uploaded_pickups)

# Artefakt Input
st.sidebar.header("📋 Artefacts")
arte_text_small = st.sidebar.text_area("Paste small artefacts overview")
arte_text_large = st.sidebar.text_area("Paste large artefacts overview")

if st.sidebar.button("Parse Artefacts"):
    small_df = parse_artifacts(arte_text_small, "Small") if arte_text_small else pd.DataFrame()
    large_df = parse_artifacts(arte_text_large, "Unique") if arte_text_large else pd.DataFrame()
    st.session_state["Targets"] = pd.concat([small_df, large_df], ignore_index=True)

# Tabellen
offs = editable_table("Offs", ["Name", "Coords", "Strength"])
catas = editable_table("Catas", ["Name", "Coords", "Count"])
pickups = editable_table("Pickups", ["Village", "Coords", "TreasuryLevel"])
targets = editable_table("Targets", ["x", "y", "Type"])

# Planung
if st.button("Create Plan"):
    if offs.empty or catas.empty or pickups.empty or targets.empty:
        st.warning("Bitte alle Daten (Offs, Catas, Pickups, Targets) hochladen oder einfügen.")
    else:
        plan_df = match_artefacts(offs, catas, pickups, targets)
        if plan_df.empty:
            st.error("❌ Kein gültiger Plan gefunden!")
        else:
            st.success("✅ Plan erstellt!")
            st.dataframe(plan_df, use_container_width=True)