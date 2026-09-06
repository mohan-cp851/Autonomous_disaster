import requests

OSRM_BASE_URL = "https://router.project-osrm.org/route/v1/driving"


def get_driving_route(source_lat, source_lng, dest_lat, dest_lng):
    """
    Get an actual driving route between two coordinates using OSRM.

    Returns:
        {
            "distance_km": float,
            "duration_min": float,
            "geometry": [[lat, lng], ...]
        }

    Returns None if the routing service cannot provide a route.
    """

    url = (
        f"{OSRM_BASE_URL}/"
        f"{source_lng},{source_lat};"
        f"{dest_lng},{dest_lat}"
        "?overview=full&geometries=geojson"
    )

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()

        data = response.json()

        if data.get("code") != "Ok" or not data.get("routes"):
            return None

        route = data["routes"][0]

        geometry = [
            [lat, lng]
            for lng, lat in route["geometry"]["coordinates"]
        ]

        return {
            "distance_km": round(route["distance"] / 1000, 2),
            "duration_min": round(route["duration"] / 60, 1),
            "geometry": geometry
        }

    except (requests.RequestException, ValueError, KeyError, IndexError):
        return None
