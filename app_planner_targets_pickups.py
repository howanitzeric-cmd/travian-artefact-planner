import streamlit as st
import pandas as pd
import math

# -----------------------------
# Config
# -----------------------------
PRIORITY_ORDER = [
    "Unique",       # Unique artefacts first
    "Trainer",      # then Trainer
    "Diet",
    "Boots",
    "Eyes",
    "Plans",        # Great Warehouse/Lager plans
    "Others"
]

# -----------------------------
# Helper functions
# -----------------------------
def travel_time(distance, speed, ts_level):
    """
    Calculate travel time considering tournament square.
    Travian TS bonus applies after 20 tiles.
    """
    if distance <= 20:
        return distance / speed
    else:
        normal = 20 / speed
        bonus = (distance - 20) / (speed * (1 + 0.2 * ts_level))
        return normal + bonus


def assign_offs_and_cattas(targets, offs, cattas, pickups):
    """
    Core logic: assign best offs and cattas to artefacts
    while respecting priorities and usage constraints.
    """

    plans = []
    used_offs = set()
    used_cattas = {}

    for priority in PRIORITY_ORDER:
        for _, arti in targets[targets["Type"].str.contains(priority, case=False, na=False)].iterrows():
            arti_name = arti["Name"]
            arti_dist = arti["Distance"]

            # find best Off not yet used
            best_off = None
            best_time = float("inf")

            for _, off in offs.iterrows():
                if off["Name"] in used_offs:
                    continue
                time = travel_time(arti_dist, off["Speed"], off["TS"])
                if time < best_time:
                    best_time = time
                    best_off = off

            if best_off is None:
                continue

            # find best Catta (max 2 uses)
            best_catta = None
            best_catta_time = float("inf")

            for _, cat in cattas.iterrows():
                count = used_cattas.get(cat["Name"], 0)
                if count >= 2:
                    continue
                time = travel_time(arti_dist, cat["Speed"], cat["TS"])
                if time < best_catta_time:
                    best_catta_time = time
                    best_catta = cat

            # assign pickup (treasury)
            best_pickup = None
            if not pickups.empty:
                if "Unique" in arti["Type"]:
                    best_pickup = pickups[pickups["Treasury"] >= 20].head(1)
                elif "Great" in arti["Type"]:
                    best_pickup = pickups[pickups["Treasury"] >= 10].head(1)
                else:
                    best_pickup = pickups[pickups["Treasury"] >= 5].head(1)

                if not best_pickup.empty:
                    pickups = pickups.drop(best_pickup.index)

            # record plan
            plans.append({
                "Artefact": arti_name,
                "Priority": priority,
                "Off": best_off["Name"],
                "Off time (h)": round(best_time, 2),
                "Cattas": best_catta["Name"] if best_catta is not None else "-",
                "Catta time (h)": round(best_catta_time, 2) if best_catta is not None else "-",
                "Pickup": best_pickup["Name"].values[0] if best_pickup is not None and not best_pickup.empty else "-"
            })

            used_offs.add(best_off["Name"])
            if best_catta is not None:
                used_cattas[best_catta["Name"]] = used_cattas.get(best_catta["Name"], 0) + 1

    return pd.DataFrame(plans)

# -----------------------------
# Streamlit UI
# -----------------------------
st.set_page_config(page_title="Travian Artefact Planner", layout="wide")
st.title("🏺 Travian Artefact Planner")

st.sidebar.header("Upload Data")
offs_file = st.sidebar.file_uploader("Upload Offs Excel", type=["xlsx"], key="offs")
cattas_file = st.sidebar.file_uploader("Upload Cattas Excel", type=["xlsx"], key="cattas")
pickups_file = st.sidebar.file_uploader("Upload Pickups Excel", type=["xlsx"], key="pickups")
targets_file = st.sidebar.file_uploader("Upload Targets Excel", type=["xlsx"], key="targets")

if all([offs_file, cattas_file, pickups_file, targets_file]):
    offs = pd.read_excel(offs_file)
    cattas = pd.read_excel(cattas_file)
    pickups = pd.read_excel(pickups_file)
    targets = pd.read_excel(targets_file)

    st.success("✅ All files uploaded successfully")

    if st.button("Create Plan"):
        plan = assign_offs_and_cattas(targets, offs, cattas, pickups)

        st.subheader("📜 Planned Runs")
        st.dataframe(plan)

        st.download_button(
            label="💾 Download Plan as Excel",
            data=plan.to_csv(index=False).encode("utf-8"),
            file_name="artefact_plan.csv",
            mime="text/csv"
        )
else:
    st.info("Please upload all four Excel files to start planning.")
