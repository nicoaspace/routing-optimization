"""
Folium map builder — takes solver output and renders colour-coded routes
with real road geometry (from OSRM) and interactive stop markers.
"""

import folium

ROUTE_COLORS = [
    "#E74C3C", "#3498DB", "#2ECC71", "#F39C12", "#9B59B6",
    "#1ABC9C", "#E67E22", "#34495E", "#E91E63", "#00BCD4",
    "#FF5722", "#8BC34A", "#795548", "#FF9800", "#607D8B",
    "#673AB7", "#009688", "#F44336", "#2196F3", "#4CAF50",
]


def _color(idx: int) -> str:
    return ROUTE_COLORS[idx % len(ROUTE_COLORS)]


def build_map(
    depot: dict,
    stops: list[dict],
    routes: list[dict],
    geometries: dict,
) -> folium.Map:
    """
    Parameters
    ----------
    depot      : {"name": str, "lat": float, "lon": float}
    stops      : [{"id": str, "name": str, "lat": float, "lon": float}, ...]
                 Indexed from 1 (index 0 in distance matrix = depot).
    routes     : list of route dicts from solve_cvrp()
    geometries : vehicle_id -> [(lat, lon), ...] road polylines

    Returns
    -------
    folium.Map ready to render with st_folium()
    """
    # Map centre
    all_lats = [s["lat"] for s in stops] + [depot["lat"]]
    all_lons = [s["lon"] for s in stops] + [depot["lon"]]
    center = [sum(all_lats) / len(all_lats), sum(all_lons) / len(all_lons)]

    m = folium.Map(
        location=center,
        zoom_start=13,
        tiles="CartoDB positron",
    )

    # Map stop index -> route
    stop_to_route: dict[int, int] = {}
    for route in routes:
        for si in route["stops"]:
            stop_to_route[si] = route["vehicle_id"]

    # Draw route polylines
    for route in routes:
        vid = route["vehicle_id"]
        color = _color(vid)
        geo = geometries.get(vid, [])
        if geo and len(geo) >= 2:
            folium.PolyLine(
                locations=geo,
                color=color,
                weight=4,
                opacity=0.85,
                tooltip=(
                    f"<b>Route {vid + 1}</b><br>"
                    f"{route['num_stops']} stops · {route['distance_km']} km"
                ),
            ).add_to(m)

    # Depot marker
    folium.Marker(
        location=[depot["lat"], depot["lon"]],
        icon=folium.Icon(color="red", icon="home", prefix="glyphicon"),
        tooltip=f"<b>Depot</b>: {depot['name']}",
        popup=folium.Popup(
            f"<b>Depot</b><br>{depot['name']}<br>"
            f"({depot['lat']:.5f}, {depot['lon']:.5f})",
            max_width=220,
        ),
    ).add_to(m)

    # Stop markers
    for i, stop in enumerate(stops, start=1):
        vid = stop_to_route.get(i, -1)
        color = _color(vid) if vid >= 0 else "#95A5A6"
        route_label = f"Route {vid + 1}" if vid >= 0 else "Unassigned"

        folium.CircleMarker(
            location=[stop["lat"], stop["lon"]],
            radius=8,
            color="white",
            weight=1.5,
            fill=True,
            fill_color=color,
            fill_opacity=0.9,
            tooltip=(
                f"<b>{stop['name']}</b><br>"
                f"ID: {stop['id']}<br>{route_label}"
            ),
            popup=folium.Popup(
                f"<b>{stop['name']}</b><br>"
                f"ID: {stop['id']}<br>"
                f"{route_label}<br>"
                f"({stop['lat']:.5f}, {stop['lon']:.5f})",
                max_width=220,
            ),
        ).add_to(m)

        # Small number label
        folium.Marker(
            location=[stop["lat"], stop["lon"]],
            icon=folium.DivIcon(
                html=f'<div style="font-size:9px;font-weight:700;color:#fff;'
                     f'background:{color};border-radius:50%;width:16px;'
                     f'height:16px;line-height:16px;text-align:center;'
                     f'margin-top:-8px;margin-left:-8px;">{i}</div>',
                icon_size=(0, 0),
            ),
        ).add_to(m)

    # Legend
    legend_html = "<div style='position:fixed;bottom:30px;left:30px;z-index:1000;" \
                  "background:white;padding:10px 14px;border-radius:8px;" \
                  "box-shadow:0 2px 8px rgba(0,0,0,.2);font-size:12px;'>" \
                  "<b>Routes</b><br>"
    for route in routes:
        vid = route["vehicle_id"]
        legend_html += (
            f"<span style='display:inline-block;width:12px;height:12px;"
            f"background:{_color(vid)};border-radius:2px;margin-right:4px;"
            f"vertical-align:middle;'></span>"
            f"Route {vid+1} — {route['num_stops']} stops, {route['distance_km']} km<br>"
        )
    legend_html += (
        "<span style='display:inline-block;width:12px;height:12px;"
        "background:#E74C3C;border-radius:2px;margin-right:4px;"
        "vertical-align:middle;'></span>🏠 Depot"
    )
    legend_html += "</div>"

    m.get_root().html.add_child(folium.Element(legend_html))

    return m
