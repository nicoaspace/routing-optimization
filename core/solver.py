"""
CVRP solver wrapper around Google OR-Tools.
Refactored from the original RoutingModel.py into a pure function.
"""

from ortools.constraint_solver import pywrapcp, routing_enums_pb2


def solve_cvrp(
    distance_matrix: list[list[float]],
    num_vehicles: int,
    vehicle_capacity: int,
    max_distance_m: int,
    time_limit_s: int = 15,
) -> dict:
    """
    Solve the Capacitated Vehicle Routing Problem.

    Parameters
    ----------
    distance_matrix : N×N list of distances in metres (index 0 = depot).
    num_vehicles    : Fleet size upper bound.  Set to len(matrix) to let the
                      solver use the minimum required.
    vehicle_capacity: Max stops per vehicle.
    max_distance_m  : Max driving distance per route in metres.
    time_limit_s    : OR-Tools wall-clock time limit.

    Returns
    -------
    dict with keys:
        success           bool
        routes            list[dict]  — each route has vehicle_id, stops,
                                       stop_indices, distance_m, distance_km,
                                       num_stops
        total_distance_km float
        num_routes        int
        vehicle_utilization float (%)
    """
    n = len(distance_matrix)
    # OR-Tools needs integer distances
    dm = [[int(d) for d in row] for row in distance_matrix]

    # Demand: 0 for depot (node 0), 1 for every stop
    demands = [0] + [1] * (n - 1)
    vehicle_capacities = [vehicle_capacity] * num_vehicles

    manager = pywrapcp.RoutingIndexManager(n, num_vehicles, 0)
    routing = pywrapcp.RoutingModel(manager)

    # --- Distance callback ---
    def distance_callback(from_idx: int, to_idx: int) -> int:
        return dm[manager.IndexToNode(from_idx)][manager.IndexToNode(to_idx)]

    transit_cb = routing.RegisterTransitCallback(distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_cb)

    # --- Capacity constraint ---
    def demand_callback(from_idx: int) -> int:
        return demands[manager.IndexToNode(from_idx)]

    demand_cb = routing.RegisterUnaryTransitCallback(demand_callback)
    routing.AddDimensionWithVehicleCapacity(
        demand_cb, 0, vehicle_capacities, True, "Capacity"
    )

    # --- Distance constraint ---
    routing.AddDimension(transit_cb, 0, max_distance_m, True, "Distance")
    dist_dim = routing.GetDimensionOrDie("Distance")
    dist_dim.SetGlobalSpanCostCoefficient(100)

    # --- Search parameters ---
    params = pywrapcp.DefaultRoutingSearchParameters()
    params.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    )
    params.local_search_metaheuristic = (
        routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    )
    params.time_limit.FromSeconds(time_limit_s)

    solution = routing.SolveWithParameters(params)

    if not solution:
        return {
            "success": False,
            "routes": [],
            "total_distance_km": 0.0,
            "num_routes": 0,
            "vehicle_utilization": 0.0,
        }

    routes = []
    total_dist = 0

    for vid in range(num_vehicles):
        idx = routing.Start(vid)
        stop_indices: list[int] = []
        route_dist = 0

        while not routing.IsEnd(idx):
            node = manager.IndexToNode(idx)
            stop_indices.append(node)
            prev = idx
            idx = solution.Value(routing.NextVar(idx))
            route_dist += routing.GetArcCostForVehicle(prev, idx, vid)

        stops = [s for s in stop_indices if s != 0]
        if stops:
            routes.append(
                {
                    "vehicle_id": vid,
                    "stop_indices": stop_indices,
                    "stops": stops,
                    "distance_m": route_dist,
                    "distance_km": round(route_dist / 1000, 2),
                    "num_stops": len(stops),
                }
            )
        total_dist += route_dist

    return {
        "success": True,
        "routes": routes,
        "total_distance_km": round(total_dist / 1000, 2),
        "num_routes": len(routes),
        "vehicle_utilization": round(
            len(routes) / num_vehicles * 100, 1
        ) if num_vehicles > 0 else 0.0,
    }
