import os
import requests
import pandas as pd
from typing import Optional

os.environ["amap_api_key"] = "2195d3797b651780acb2b2573179bced"


def search_poi_nearby(
        latitude: float,
        longitude: float,
        radius: int = 500,
        types: Optional[str] = None,
        save_path: Optional[str] = None
) -> str:
    """
    Searches for Points of Interest (POIs) around a given coordinate and saves the results to a CSV file.

    Parameters:
    - latitude (float): Latitude of the central point.
    - longitude (float): Longitude of the central point.
    - radius (int): Search radius in meters. Default is 500.
    - types (Optional[str]): POI category codes. Refer to Amap POI category code table.
    - save_path (Optional[str]): Path to save the CSV file. Defaults to 'C:/poi_results/poi_results.csv'.

    Returns:
    - str: Message indicating the success of the operation and the save location.
    """
    save_path = save_path or "C:/NTL_Agent/report/csv/poi_results.csv"
    os.makedirs(os.path.dirname(save_path), exist_ok=True)

    amap_api_key = os.environ.get("amap_api_key")
    if not amap_api_key:
        return "API key is not set. Please set 'amap_api_key' in environment variables."

    url = "https://restapi.amap.com/v5/place/around"
    all_pois = []
    page = 1

    while True:
        params = {
            "key": amap_api_key,
            "location": f"{longitude},{latitude}",
            "radius": radius,
            "types": types,
            "output": "json",
            "page": page,
            "offset": 20  # Maximum number of results per page
        }

        # Print the request URL for debugging
        request_url = f"{url}?{'&'.join([f'{k}={v}' for k, v in params.items()])}"
        print(f"Requesting: {request_url}")

        response = requests.get(url, params=params)
        if response.status_code != 200:
            return f"Failed to request Amap API. HTTP status code: {response.status_code}"

        data = response.json()
        if data.get("status") != "1":
            return f"Amap API error: {data.get('info')}"

        pois = data.get("pois", [])
        if not pois:
            break

        all_pois.extend(pois)
        if len(pois) < 20:  # If less than 20 results are returned, stop pagination
            break

        page += 1

    # Combine all results into a DataFrame
    if all_pois:
        df = pd.DataFrame(all_pois)
        df.to_csv(save_path, index=False, encoding="utf-8-sig")
        return f"POI search completed. Results saved at: {save_path}\n\nTop rows:\n{df.head().to_string()}"
    else:
        return "No POIs found in the specified range."


# Example usage
result = search_poi_nearby(
    latitude=28.594,
    longitude=87.352,
    radius=300,
    save_path="C:/NTL_Agent/report/csv/poi_results.csv"
)
print(result)
