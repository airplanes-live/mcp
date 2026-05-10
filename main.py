import asyncio
import csv
import math
from pathlib import Path
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP


mcp = FastMCP('airplanes-live')

API_BASE_URL = 'https://api.airplanes.live/v2'
USER_AGENT = 'apl-mcp/1.0'
MAX_QUERY_LENGTH = 1000
MAX_POINT_RADIUS = 250

DATA_DIR = Path(__file__).parent / 'data'
EARTH_RADIUS_NM = 3440.065

_airports_by_ident: dict[str, dict] = {}
_airports_by_iata: dict[str, dict] = {}
_runways_by_ident: dict[str, list[dict]] = {}
_frequencies_by_ident: dict[str, list[dict]] = {}


async def make_apl_request(url: str) -> dict[str, Any] | None:
    headers = {'User-Agent': USER_AGENT, 'Accept': 'application/json'}
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers, timeout=30.0)
            response.raise_for_status()
            return response.json()
        except Exception:
            return None


def extract_aircraft(data: dict[str, Any] | None, label: str) -> list[dict] | str:
    if not data or 'ac' not in data:
        return f'Unable to fetch {label} or no {label} found'
    if not data['ac']:
        return f'No active {label}'
    return data['ac']


def _project(row: dict, fields: list[str] | None) -> dict:
    if fields is None:
        return row
    return {k: row[k] for k in fields if k in row}


def _haversine_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_NM * math.asin(math.sqrt(a))


def _load_csvs() -> None:
    with (DATA_DIR / 'airports.csv').open(newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            _airports_by_ident[row['ident']] = row
            if row.get('iata_code'):
                _airports_by_iata[row['iata_code']] = row
    with (DATA_DIR / 'runways.csv').open(newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            _runways_by_ident.setdefault(row['airport_ident'], []).append(row)
    with (DATA_DIR / 'airport-frequencies.csv').open(newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            _frequencies_by_ident.setdefault(row['airport_ident'], []).append(row)


@mcp.tool()
async def get_military() -> list[dict] | str:
    """Get active military aircraft"""
    data = await make_apl_request(f'{API_BASE_URL}/mil')
    return extract_aircraft(data, 'military aircraft')


@mcp.tool()
async def get_ladd() -> list[dict] | str:
    """Get active LADD (Limiting Aircraft Data Displayed) aircraft"""
    data = await make_apl_request(f'{API_BASE_URL}/ladd')
    return extract_aircraft(data, 'LADD aircraft')


@mcp.tool()
async def get_pia() -> list[dict] | str:
    """Get active PIA (Privacy ICAO Address) aircraft"""
    data = await make_apl_request(f'{API_BASE_URL}/pia')
    return extract_aircraft(data, 'PIA aircraft')


@mcp.tool()
async def get_aircraft_hex(hex: str) -> list[dict] | str:
    """Search for aircraft by Mode S hex code(s).

    Args:
        hex: One or more comma-separated Mode S hex codes (max 1000 characters).
    """
    if len(hex) > MAX_QUERY_LENGTH:
        return f'Query exceeds {MAX_QUERY_LENGTH} characters'
    data = await make_apl_request(f'{API_BASE_URL}/hex/{hex}')
    return extract_aircraft(data, 'aircraft')


@mcp.tool()
async def get_aircraft_callsign(callsign: str) -> list[dict] | str:
    """Search for aircraft by callsign(s).

    Args:
        callsign: One or more comma-separated callsigns (max 1000 characters).
    """
    if len(callsign) > MAX_QUERY_LENGTH:
        return f'Query exceeds {MAX_QUERY_LENGTH} characters'
    data = await make_apl_request(f'{API_BASE_URL}/callsign/{callsign}')
    return extract_aircraft(data, 'aircraft')


@mcp.tool()
async def get_aircraft_reg(reg: str) -> list[dict] | str:
    """Search for aircraft by registration(s).

    Args:
        reg: One or more comma-separated registrations (max 1000 characters).
    """
    if len(reg) > MAX_QUERY_LENGTH:
        return f'Query exceeds {MAX_QUERY_LENGTH} characters'
    data = await make_apl_request(f'{API_BASE_URL}/reg/{reg}')
    return extract_aircraft(data, 'aircraft')


@mcp.tool()
async def get_aircraft_type(type: str) -> list[dict] | str:
    """Search for aircraft by ICAO type designator(s).

    Args:
        type: One or more comma-separated ICAO type codes (max 1000 characters).
    """
    if len(type) > MAX_QUERY_LENGTH:
        return f'Query exceeds {MAX_QUERY_LENGTH} characters'
    data = await make_apl_request(f'{API_BASE_URL}/type/{type}')
    return extract_aircraft(data, 'aircraft')


@mcp.tool()
async def get_aircraft_squawk(squawk: str) -> list[dict] | str:
    """Search for aircraft by squawk code.

    Args:
        squawk: 4-digit octal transponder code.
    """
    data = await make_apl_request(f'{API_BASE_URL}/squawk/{squawk}')
    return extract_aircraft(data, 'aircraft')


@mcp.tool()
async def get_emergency_aircraft() -> list[dict] | str:
    """Get aircraft squawking emergency codes (7500 hijack, 7600 radio failure, 7700 general emergency)."""
    results = await asyncio.gather(
        make_apl_request(f'{API_BASE_URL}/squawk/7500,7600,7700'),
    )
    aircraft = [ac for data in results if data and data.get('ac') for ac in data['ac']]
    if not aircraft:
        return 'No active emergency aircraft'
    return aircraft


@mcp.tool()
async def get_aircraft_point(lat: float, lon: float, radius: int) -> list[dict] | str:
    """Search for aircraft within a radius of a point.

    Args:
        lat: Latitude in decimal degrees.
        lon: Longitude in decimal degrees.
        radius: Search radius in nautical miles (max 250).
    """
    if radius > MAX_POINT_RADIUS:
        return f'Radius exceeds {MAX_POINT_RADIUS} nautical miles'
    data = await make_apl_request(f'{API_BASE_URL}/point/{lat}/{lon}/{radius}')
    return extract_aircraft(data, 'aircraft')


@mcp.tool()
async def get_airport(ident: str, fields: list[str] | None = None) -> dict | str:
    """Look up an airport by ICAO (e.g., KJFK) or IATA (e.g., JFK) code.

    Args:
        ident: ICAO or IATA code.
        fields: Optional column subset. Common columns: ident, type, name, iata_code,
            iso_country, iso_region, municipality, latitude_deg, longitude_deg,
            elevation_ft. Omit for full row.
    """
    key = ident.upper()
    airport = _airports_by_ident.get(key) or _airports_by_iata.get(key)
    if not airport:
        return f'Airport {ident} not found'
    return _project(airport, fields)


@mcp.tool()
async def get_airports_near(
    lat: float,
    lon: float,
    radius: int,
    fields: list[str] | None = None,
) -> list[dict] | str:
    """Find airports within a radius of a point, sorted by distance.

    Args:
        lat: Latitude in decimal degrees.
        lon: Longitude in decimal degrees.
        radius: Search radius in nautical miles (max 250).
        fields: Optional column subset. Includes 'distance_nm' plus any airport
            columns (ident, name, iata_code, iso_country, latitude_deg,
            longitude_deg, elevation_ft, type, ...). Omit for full rows.
    """
    if radius > MAX_POINT_RADIUS:
        return f'Radius exceeds {MAX_POINT_RADIUS} nautical miles'
    lat_pad = radius / 60.0
    lon_pad = lat_pad / max(math.cos(math.radians(lat)), 0.01)
    results = []
    for ap in _airports_by_ident.values():
        try:
            a_lat = float(ap['latitude_deg'])
            a_lon = float(ap['longitude_deg'])
        except (ValueError, KeyError):
            continue
        if abs(a_lat - lat) > lat_pad or abs(a_lon - lon) > lon_pad:
            continue
        d = _haversine_nm(lat, lon, a_lat, a_lon)
        if d <= radius:
            results.append({**ap, 'distance_nm': round(d, 2)})
    if not results:
        return 'No airports found'
    results.sort(key=lambda x: x['distance_nm'])
    return [_project(r, fields) for r in results]


@mcp.tool()
async def get_runways(ident: str, fields: list[str] | None = None) -> list[dict] | str:
    """Get runway information for an airport by ICAO code.

    Args:
        ident: ICAO code.
        fields: Optional column subset. Common columns: length_ft, width_ft, surface,
            lighted, closed, le_ident, le_heading_degT, he_ident, he_heading_degT.
            Omit for full rows.
    """
    runways = _runways_by_ident.get(ident.upper())
    if not runways:
        return f'No runways found for {ident}'
    return [_project(r, fields) for r in runways]


@mcp.tool()
async def get_frequencies(ident: str, fields: list[str] | None = None) -> list[dict] | str:
    """Get communication frequencies for an airport by ICAO code.

    Args:
        ident: ICAO code.
        fields: Optional column subset. Common columns: type, description,
            frequency_mhz. Omit for full rows.
    """
    freqs = _frequencies_by_ident.get(ident.upper())
    if not freqs:
        return f'No frequencies found for {ident}'
    return [_project(r, fields) for r in freqs]


def main():
    _load_csvs()
    mcp.run(transport='stdio')


if __name__ == '__main__':
    main()
