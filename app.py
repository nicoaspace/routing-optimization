"""
Route Optimizer — Streamlit frontend for the CVRP solver.

Business context:
  Built to dispatch 1,200+ field agents across Bogotá and Medellín under a
  $110 k+ monthly operations budget.  Replacing manual route planning cut
  total daily driving distance by ~30 %.

Stack: OSRM Table API (real road distances) · Google OR-Tools CVRP · Folium
"""

import io
import time
import traceback

import folium
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

from core.osrm import get_distance_matrix, get_route_geometry
from core.solver import solve_cvrp
from viz.map_builder import build_map


def _log(msg: str) -> None:
    """Append a timestamped line to the session-state debug log."""
    ts = time.strftime("%H:%M:%S")
    st.session_state.setdefault("debug_log", []).append(f"[{ts}] {msg}")


def _log_exc(label: str, exc: Exception) -> None:
    _log(f"❌ {label}: {exc}")
    _log(traceback.format_exc())

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Route Optimizer | Nico Alonso",
    page_icon="🗺️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ─────────────────────────────────────────────────────────────────
st.markdown(
    """
    <style>
    /* hide default Streamlit chrome */
    #MainMenu, footer { visibility: hidden; }

    /* header */
    .app-title  { font-size: 2rem; font-weight: 800; color: #0f172a; margin: 0; }
    .app-sub    { color: #64748b; font-size: .95rem; margin: .3rem 0 1.4rem; }

    /* metrics */
    div[data-testid="stMetric"] {
        background: #f8fafc;
        border-radius: 10px;
        padding: .9rem 1rem;
        border-left: 4px solid #3b82f6;
    }
    div[data-testid="stMetricValue"] { font-size: 1.5rem; font-weight: 700; }

    /* primary button */
    div[data-testid="stButton"] > button[kind="primary"] {
        background: #3b82f6;
        color: #fff;
        font-weight: 600;
        border-radius: 8px;
        border: none;
        padding: .6rem 1.2rem;
        transition: background .2s;
    }
    div[data-testid="stButton"] > button[kind="primary"]:hover {
        background: #2563eb;
    }

    /* section divider */
    hr { border-color: #e2e8f0; }

    /* sidebar */
    section[data-testid="stSidebar"] {
        background: #f1f5f9;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Constants ──────────────────────────────────────────────────────────────────
PRESET_DEPOTS = {
    "Bogotá — Kennedy (cnt)":     {"lat": 4.684755,  "lon": -74.119482},
    "Bogotá — Tunjuelito (txt)":  {"lat": 4.625910,  "lon": -74.113023},
    "Medellín — Centro (mdn)":    {"lat": 6.219800,  "lon": -75.569532},
}

SAMPLE_CSV = (
    "id,name,lat,long\n"
    "1,Kennedy Centro,4.6282,-74.1520\n"
    "2,Autopista Sur,4.6350,-74.1420\n"
    "3,Corabastos,4.6198,-74.1485\n"
    "4,Patio Bonito,4.6154,-74.1609\n"
    "5,Britalia,4.6463,-74.1398\n"
    "6,Castilla,4.6601,-74.1303\n"
    "7,Marsella,4.6695,-74.1045\n"
    "8,Alquería,4.6417,-74.1242\n"
    "9,Tintal,4.6534,-74.1610\n"
    "10,Villa Nueva,4.6632,-74.1482\n"
    "11,Techo,4.6740,-74.1289\n"
    "12,Fontibón,4.6828,-74.1432\n"
    "13,Puente Aranda,4.6312,-74.1013\n"
    "14,Bosa,4.5989,-74.1765\n"
    "15,Calle 13,4.6578,-74.1112\n"
)

# ── Header ─────────────────────────────────────────────────────────────────────
st.markdown('<p class="app-title">🗺️ Route Optimizer</p>', unsafe_allow_html=True)
st.markdown(
    '<p class="app-sub">'
    "Upload a CSV of stop coordinates and get optimized vehicle routes using "
    "<strong>Google OR-Tools CVRP</strong> + <strong>OSRM</strong> real driving distances."
    "</p>",
    unsafe_allow_html=True,
)

with st.expander("ℹ️ About this project", expanded=False):
    st.markdown(
        """
        This tool solves the **Capacitated Vehicle Routing Problem (CVRP)** — the math behind
        efficient last-mile delivery and field-service dispatching.

        It was originally built to route **1,200+ field agents** across Bogotá and Medellín
        under a **\$110 k+ monthly operations budget**, replacing a manual spreadsheet process
        and reducing total daily driving distance by roughly **30 %**.

        **How it works:**
        1. Your CSV stops are sent to the **OSRM Table API** — a single HTTP request returns
           a real-world N×N driving-distance matrix (way faster than the original O(N²) loop).
        2. **Google OR-Tools** solves the CVRP with capacity and distance-per-route constraints
           using Guided Local Search.
        3. Each route is fetched from OSRM again to draw the **actual road geometry** on the map.

        Source: [github.com/nicoaspace/routing-optimization](https://github.com/nicoaspace/routing-optimization)
        """
    )

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️  Configuration")

    # 1. Stops
    st.subheader("1 · Stops")
    uploaded = st.file_uploader(
        "Upload CSV",
        type=["csv"],
        help="Required columns: **lat**, **long** (or **lon**).  "
             "Optional: **id**, **name**.",
    )

    c1, c2 = st.columns(2)
    with c1:
        if st.button("📋 Sample data", use_container_width=True):
            st.session_state["use_sample"] = True
    with c2:
        st.download_button(
            "⬇️ Download",
            SAMPLE_CSV.encode(),
            "sample_stops.csv",
            "text/csv",
            use_container_width=True,
        )

    st.markdown(
        "<small>CSV must include <code>lat</code> and <code>long</code> (or <code>lon</code>) columns.</small>",
        unsafe_allow_html=True,
    )

    st.divider()

    # 2. Depot
    st.subheader("2 · Depot")
    depot_mode = st.radio(
        "Source",
        ["Preset location", "Custom coordinates"],
        label_visibility="collapsed",
    )

    if depot_mode == "Preset location":
        depot_name = st.selectbox("Location", list(PRESET_DEPOTS.keys()))
        depot_lat = PRESET_DEPOTS[depot_name]["lat"]
        depot_lon = PRESET_DEPOTS[depot_name]["lon"]
    else:
        depot_lat = st.number_input("Latitude",  value=4.684755,  format="%.6f")
        depot_lon = st.number_input("Longitude", value=-74.119482, format="%.6f")
        depot_name = "Custom depot"

    st.divider()

    # 3. Solver parameters
    st.subheader("3 · Parameters")
    vehicle_cap = st.slider("Stops per vehicle (capacity)", 1, 20, 4)
    max_km      = st.slider("Max route distance (km)", 5, 100, 50)
    time_limit  = st.slider("Solver time limit (s)", 5, 300, 60, step=5,
                            help="Más paradas = más tiempo. Para 50+ paradas prueba 60–120 s.")

    st.divider()

    optimize_btn = st.button(
        "🚀  Optimize Routes",
        use_container_width=True,
        type="primary",
    )

    st.caption(
        "Powered by [OSRM](http://project-osrm.org) · "
        "[OR-Tools](https://developers.google.com/optimization) · "
        "[Folium](https://python-visualization.github.io/folium/)"
    )

# ── Load stops data ────────────────────────────────────────────────────────────
df: pd.DataFrame | None = None

if st.session_state.get("use_sample"):
    df = pd.read_csv(io.StringIO(SAMPLE_CSV))
    st.info("📋 Showing sample data — 15 stops in Bogotá.  Upload your own CSV to use real addresses.")
elif uploaded is not None:
    df = pd.read_csv(uploaded)
    st.session_state.pop("use_sample", None)

if df is not None:
    df.columns = [c.lower().strip() for c in df.columns]
    if "long" in df.columns and "lon" not in df.columns:
        df = df.rename(columns={"long": "lon"})
    missing = [c for c in ("lat", "lon") if c not in df.columns]
    if missing:
        st.error(f"CSV is missing required columns: {missing}")
        df = None

# ── Run optimisation ───────────────────────────────────────────────────────────
if optimize_btn:
    if df is None:
        st.warning("Please upload a CSV file or load the sample data first.")
        st.stop()

    st.session_state["debug_log"] = []

    stops_coords = list(zip(df["lat"].astype(float), df["lon"].astype(float)))
    all_coords   = [(depot_lat, depot_lon)] + stops_coords
    n_stops      = len(stops_coords)
    n_nodes      = n_stops + 1
    _log(f"Stops: {n_stops} · Depot: ({depot_lat}, {depot_lon})")

    # ── Step 1: Distance matrix ─────────────────────────────────────────────
    with st.status(f"📡 Step 1/3 — Fetching real driving distances", expanded=True) as s1:
        st.markdown(
            f"Sending **{n_nodes} coordinates** to the OSRM routing engine.  \n"
            f"A single API call will return a **{n_nodes}×{n_nodes} = {n_nodes**2} distance pairs** matrix "
            f"(all real driving distances, in metres)."
        )
        _log(f"OSRM Table API → {n_nodes}×{n_nodes} matrix ({n_nodes**2} pairs)…")
        try:
            dist_matrix = get_distance_matrix(all_coords)
            _log(f"Matrix received: {len(dist_matrix)}×{len(dist_matrix[0])}")

            # Quick stats for the user
            depot_dists = [dist_matrix[0][i] / 1000 for i in range(1, n_nodes)]
            avg_d  = round(sum(depot_dists) / len(depot_dists), 1)
            max_d  = round(max(depot_dists), 1)
            min_d  = round(min(depot_dists), 1)
            min_rt = round(min(depot_dists[i] + dist_matrix[i+1][0]/1000 for i in range(n_stops)), 1)
            max_rt = round(max(depot_dists[i] + dist_matrix[i+1][0]/1000 for i in range(n_stops)), 1)
            _log(f"Depot distances → min={min_d} km  avg={avg_d} km  max={max_d} km")
            _log(f"Round-trips     → min={min_rt} km  max={max_rt} km  (limit={max_km} km)")

            st.success(
                f"✅ Matrix ready — {n_nodes}×{n_nodes}  \n"
                f"Distance from depot: min **{min_d} km** · avg **{avg_d} km** · max **{max_d} km**  \n"
                f"Shortest round-trip: **{min_rt} km** · Longest: **{max_rt} km**"
            )
            s1.update(label=f"✅ Step 1/3 — Distance matrix ({n_nodes}×{n_nodes})", state="complete")
        except Exception as exc:
            _log_exc("OSRM", exc)
            s1.update(label="❌ Step 1/3 — OSRM failed", state="error")
            st.error(f"OSRM error: {exc}")
            st.stop()

    # ── Pre-solve feasibility check ─────────────────────────────────────────
    infeasible = []
    for i in range(n_stops):
        rt = (dist_matrix[0][i+1] + dist_matrix[i+1][0]) / 1000
        if rt > max_km:
            name = df.iloc[i].get("name", f"Stop {i+1}") if "name" in df.columns else f"Stop {i+1}"
            infeasible.append({
                "Stop": str(name),
                "From depot (km)": round(dist_matrix[0][i+1]/1000, 1),
                "Return to depot (km)": round(dist_matrix[i+1][0]/1000, 1),
                "Min round-trip (km)": round(rt, 1),
            })

    if infeasible:
        needed_km = max(r["Min round-trip (km)"] for r in infeasible)
        _log(f"Infeasible stops ({len(infeasible)}): need max_km ≥ {needed_km} km")
        st.error(
            f"**{len(infeasible)} stop(s) cannot be visited** within the current "
            f"**{max_km} km** route limit — their round-trip from the depot alone exceeds it.  \n"
            f"👉 Set **Max route distance ≥ {needed_km} km** to make the problem feasible."
        )
        st.dataframe(
            pd.DataFrame(infeasible),
            use_container_width=True,
            hide_index=True,
            column_config={
                "Min round-trip (km)": st.column_config.ProgressColumn(
                    min_value=0, max_value=needed_km * 1.2, format="%.1f km"
                )
            },
        )
        st.stop()

    # ── Step 2: CVRP solver ─────────────────────────────────────────────────
    min_vehicles = -(-n_stops // vehicle_cap)   # ceiling division
    with st.status(f"🧮 Step 2/3 — Running CVRP solver (up to {time_limit} s)", expanded=True) as s2:
        st.markdown(
            f"**OR-Tools Guided Local Search** is exploring route combinations.  \n"
            f"Problem: **{n_stops} stops** · **{vehicle_cap} stops/vehicle** · "
            f"**{max_km} km max/route** · minimum **{min_vehicles} vehicles** needed  \n"
            f"The solver runs for up to **{time_limit} seconds** and returns the best solution found."
        )
        _log(f"OR-Tools CVRP · cap={vehicle_cap} · max_km={max_km} · time={time_limit}s · min_vehicles={min_vehicles}")
        try:
            result = solve_cvrp(
                distance_matrix=dist_matrix,
                num_vehicles=n_stops,
                vehicle_capacity=vehicle_cap,
                max_distance_m=max_km * 1000,
                time_limit_s=time_limit,
            )
        except Exception as exc:
            _log_exc("OR-Tools", exc)
            s2.update(label="❌ Step 2/3 — Solver crashed", state="error")
            st.error(f"Solver crashed: {exc}")
            st.stop()

        _log(f"Result: success={result['success']} · routes={result.get('num_routes',0)}")

        if not result["success"]:
            s2.update(label="❌ Step 2/3 — No solution found", state="error")
            # Show per-stop depot distances as a diagnostic table
            rows = []
            for i in range(n_stops):
                name = df.iloc[i].get("name", f"Stop {i+1}") if "name" in df.columns else f"Stop {i+1}"
                rt = round((dist_matrix[0][i+1] + dist_matrix[i+1][0]) / 1000, 1)
                rows.append({"Stop": str(name), "Round-trip (km)": rt})
            rows.sort(key=lambda r: r["Round-trip (km)"], reverse=True)
            suggested_km = max(r["Round-trip (km)"] for r in rows)
            st.error(
                f"**No feasible solution found** after {time_limit} s.  \n"
                f"The hardest constraint is usually **max route distance**. "
                f"For this dataset the longest round-trip is **{suggested_km} km** — "
                f"try setting max distance to **≥ {int(suggested_km) + 5} km**."
            )
            st.dataframe(
                pd.DataFrame(rows),
                use_container_width=True, hide_index=True,
                column_config={
                    "Round-trip (km)": st.column_config.ProgressColumn(
                        min_value=0, max_value=suggested_km * 1.1, format="%.1f km"
                    )
                },
            )
            st.stop()

        s2.update(
            label=(
                f"✅ Step 2/3 — Solved: {result['num_routes']} routes · "
                f"{result['total_distance_km']} km total"
            ),
            state="complete",
        )
        st.success(
            f"Found **{result['num_routes']} routes** covering all {n_stops} stops  \n"
            f"Total driving distance: **{result['total_distance_km']} km**  \n"
            f"Fleet utilization: **{result['vehicle_utilization']} %**"
        )

    # ── Build stop info ─────────────────────────────────────────────────────
    stop_info: list[dict] = []
    for i, (_, row) in enumerate(df.iterrows()):
        stop_info.append({
            "id":   str(row.get("id", i + 1)),
            "name": str(row.get("name", f"Stop {i + 1}")),
            "lat":  float(row["lat"]),
            "lon":  float(row["lon"]),
        })

    # ── Step 3: Road geometry ───────────────────────────────────────────────
    geometries: dict[int, list] = {}
    total_routes = len(result["routes"])
    with st.status(f"🗺️ Step 3/3 — Fetching road geometry for {total_routes} routes", expanded=True) as s3:
        _log(f"Fetching geometry for {total_routes} routes…")
        for j, route in enumerate(result["routes"]):
            vid = route["vehicle_id"]
            st.write(
                f"Route {j+1}/{total_routes} — {route['num_stops']} stops · "
                f"{route['distance_km']} km"
            )
            waypoints = [(depot_lat, depot_lon)]
            for idx in route["stops"]:
                s = stop_info[idx - 1]
                waypoints.append((s["lat"], s["lon"]))
            waypoints.append((depot_lat, depot_lon))

            time.sleep(0.15)
            try:
                geo = get_route_geometry(waypoints)
                geometries[vid] = geo
                _log(f"  Route {j+1}: {route['num_stops']} stops · {route['distance_km']} km · {len(geo)} pts")
            except Exception as exc:
                _log_exc(f"Route {j+1} geometry", exc)
                geometries[vid] = waypoints

        _log(f"All done · {result['total_distance_km']} km total · {result['num_routes']} routes")
        s3.update(label=f"✅ Step 3/3 — Map ready", state="complete")

    # Persist
    st.session_state.update({
        "result":     result,
        "stop_info":  stop_info,
        "geometries": geometries,
        "depot":      {"name": depot_name, "lat": depot_lat, "lon": depot_lon},
        "df":         df,
    })

# ── Results display ────────────────────────────────────────────────────────────
if "result" in st.session_state:
    result     = st.session_state["result"]
    stop_info  = st.session_state["stop_info"]
    geometries = st.session_state["geometries"]
    depot      = st.session_state["depot"]

    # Metric cards
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🚗 Routes created",       result["num_routes"])
    c2.metric("📍 Stops optimized",      len(stop_info))
    c3.metric("📏 Total distance",        f"{result['total_distance_km']} km")
    c4.metric("⚡ Fleet utilization",     f"{result['vehicle_utilization']} %")

    st.divider()

    map_col, tbl_col = st.columns([3, 2], gap="large")

    with map_col:
        st.subheader("🗺️  Route Map")
        fmap = build_map(depot, stop_info, result["routes"], geometries)
        st_folium(fmap, width=None, height=520, returned_objects=[], use_container_width=True)

    with tbl_col:
        st.subheader("📋  Route Details")

        # Build display table
        rows = []
        for route in result["routes"]:
            names = " → ".join(stop_info[i - 1]["name"] for i in route["stops"])
            rows.append(
                {
                    "Route":     f"Route {route['vehicle_id'] + 1}",
                    "Stops":     route["num_stops"],
                    "Dist (km)": route["distance_km"],
                    "Sequence":  names,
                }
            )
        st.dataframe(
            pd.DataFrame(rows),
            use_container_width=True,
            hide_index=True,
            column_config={
                "Route":     st.column_config.TextColumn(width="small"),
                "Stops":     st.column_config.NumberColumn(width="small"),
                "Dist (km)": st.column_config.NumberColumn(width="small"),
                "Sequence":  st.column_config.TextColumn(width="large"),
            },
        )

        # Download
        csv_rows = []
        for route in result["routes"]:
            for order, idx in enumerate(route["stops"], start=1):
                s = stop_info[idx - 1]
                csv_rows.append(
                    {
                        "route":      f"Route {route['vehicle_id'] + 1}",
                        "stop_order": order,
                        "id":         s["id"],
                        "name":       s["name"],
                        "lat":        s["lat"],
                        "lon":        s["lon"],
                        "route_km":   route["distance_km"],
                    }
                )
        st.download_button(
            "⬇️  Download results CSV",
            pd.DataFrame(csv_rows).to_csv(index=False).encode(),
            "optimized_routes.csv",
            "text/csv",
            use_container_width=True,
        )

# ── Preview (data loaded but not yet optimised) ────────────────────────────────
elif df is not None:
    st.subheader("📋  Stops preview")
    prev_map, prev_tbl = st.columns([2, 3], gap="large")

    with prev_tbl:
        st.dataframe(df.head(30), use_container_width=True, hide_index=True)
        st.caption(f"{len(df)} stops loaded — click **🚀 Optimize Routes** in the sidebar.")

    with prev_map:
        lon_col = "lon" if "lon" in df.columns else "long"
        pm = folium.Map(
            location=[df["lat"].mean(), df[lon_col].mean()],
            zoom_start=12,
            tiles="CartoDB positron",
        )
        for _, row in df.iterrows():
            folium.CircleMarker(
                [row["lat"], row[lon_col]],
                radius=6, color="#3b82f6", fill=True, fill_opacity=0.7,
            ).add_to(pm)
        folium.Marker(
            [depot_lat, depot_lon],
            icon=folium.Icon(color="red", icon="home", prefix="glyphicon"),
            tooltip="Depot",
        ).add_to(pm)
        st_folium(pm, width=None, height=380, returned_objects=[], use_container_width=True)

# ── Landing state ──────────────────────────────────────────────────────────────
else:
    st.markdown("---")
    c1, c2, c3 = st.columns(3)
    c1.info(
        "**① Upload stops**\n\n"
        "CSV with `lat` / `long` columns, one row per stop. "
        "Or click **📋 Sample data** to try immediately."
    )
    c2.info(
        "**② Configure parameters**\n\n"
        "Set depot location, vehicle capacity, and max route distance in the sidebar."
    )
    c3.info(
        "**③ Optimize & explore**\n\n"
        "One click fetches real driving distances and solves the routing. "
        "Download results as CSV."
    )

    st.markdown("---")
    st.markdown(
        "#### How the algorithm works\n"
        "| Step | What happens |\n"
        "|------|--------------|\n"
        "| 1 | Your stops + depot coordinates are sent to the **OSRM Table API** — "
        "one HTTP request returns the full N×N driving-distance matrix |\n"
        "| 2 | **Google OR-Tools** solves the Capacitated VRP with your constraints "
        "(capacity per vehicle, max km per route) using Guided Local Search |\n"
        "| 3 | Each optimised route is sent back to OSRM to retrieve real road geometry |\n"
        "| 4 | The map renders colour-coded polylines following actual streets |\n"
    )

# ── Debug log panel ────────────────────────────────────────────────────────────
if st.session_state.get("debug_log"):
    with st.expander("🔍 Debug log", expanded=False):
        st.code("\n".join(st.session_state["debug_log"]), language="text")
        st.download_button(
            "⬇️ Download log",
            "\n".join(st.session_state["debug_log"]).encode(),
            "debug_log.txt",
            "text/plain",
        )
