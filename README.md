# Routing Optimization

A **Capacitated Vehicle Routing Problem (CVRP)** solver built for real-world field-service dispatching.

Originally deployed to route **1,200+ agents** across Bogotá and Medellín under a **$110 k+ monthly
operations budget**, replacing manual spreadsheet planning and reducing total daily driving distance by ~30%.

## Live Demo

▶ **[Try it on Streamlit Cloud](https://routing-optimization.streamlit.app)**  _(link after deploy)_

Upload a CSV of stop coordinates → get optimized routes on an interactive map, with real road geometry.

---

## Stack

| Layer | Technology |
|-------|-----------|
| Distance matrix | [OSRM Table API](http://project-osrm.org) — one request for the full N×N matrix |
| CVRP solver | [Google OR-Tools](https://developers.google.com/optimization) — Guided Local Search |
| Road geometry | OSRM Route API — actual street polylines per route |
| Frontend | [Streamlit](https://streamlit.io) + [Folium](https://python-visualization.github.io/folium/) |

---

## Quick start

```bash
git clone https://github.com/nicoaspace/routing-optimization.git
cd routing-optimization
pip install -r requirements.txt
streamlit run app.py
```

Open http://localhost:8501, load the sample data, and click **Optimize Routes**.

---

## CSV format

Upload a file with at least `lat` and `long` (or `lon`) columns:

```csv
id,name,lat,long
1,Kennedy Centro,4.6282,-74.1520
2,Autopista Sur,4.6350,-74.1420
...
```

A sample file is included at `data/sample_stops.csv` (15 stops around Bogotá).

---

## Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| Depot | Starting/ending point for all vehicles | Kennedy, Bogotá |
| Stops per vehicle | Maximum stops a single vehicle can visit | 4 |
| Max route distance | Maximum driving km per route | 30 km |
| Solver time limit | OR-Tools wall-clock limit | 15 s |

---

## Project structure

```
routing-optimization/
├── app.py                   # Streamlit entry point
├── core/
│   ├── osrm.py              # OSRM Table API + Route geometry client
│   └── solver.py            # OR-Tools CVRP wrapper
├── viz/
│   └── map_builder.py       # Folium map with colour-coded routes + legend
├── data/
│   └── sample_stops.csv     # 15-stop Bogotá demo dataset
├── .streamlit/
│   └── config.toml          # Theme + server settings
├── requirements.txt
│
│   ── original CLI scripts ──
├── RoutingModel.py          # Original OR-Tools script
├── matrixRoutes.py          # Original OSRM matrix builder
└── routesStr.py             # Original Excel coordinate parser
```

---

## How the algorithm works

```
CSV stops
    │
    ▼
OSRM Table API ──► N×N distance matrix (single HTTP request)
    │
    ▼
OR-Tools CVRP
  • PATH_CHEAPEST_ARC first solution
  • GUIDED_LOCAL_SEARCH metaheuristic
  • Capacity constraint (stops per vehicle)
  • Distance constraint (max km per route)
    │
    ▼
Route geometry ──► OSRM Route API (per route, real road polylines)
    │
    ▼
Folium map ──► colour-coded routes + metrics + downloadable CSV
```

---

## License

MIT — Juan Nicolás Alonso Alzate, 2024
