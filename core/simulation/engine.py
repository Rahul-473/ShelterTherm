"""
Pure Python + NumPy thermal simulation engine for ShelterTherm.

Decoupled from Django so it can be tested and reused independently.
Uses SI units throughout (metres, watts, degrees Celsius, seconds).
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional
import math
import numpy as np

# Fixed ISO 6946 & physical constants
R_SE = 0.04          # Exterior surface thermal resistance (m^2 K / W)
R_SI_WALL = 0.13     # Interior wall surface resistance (m^2 K / W)
R_SI_ROOF = 0.10     # Interior roof surface resistance (m^2 K / W)
R_SI_FLOOR = 0.17    # Interior floor surface resistance (m^2 K / W)

AIR_DENSITY = 1.2    # kg / m^3
AIR_CP = 1005.0      # J / (kg K)
OCCUPANT_HEAT_W = 100.0  # Sensible heat gain per person (W)

DEFAULT_WINDOW_U = 5.0   # Single-glazed window U-value (W / m^2 K)
DEFAULT_DOOR_U = 2.5     # Standard wooden/metal door U-value (W / m^2 K)

DT_SECONDS = 600.0   # 10-minute time step
STEPS_PER_DAY = 144  # 24 * 60 / 10
WARMUP_DAYS = 5      # Repeat design day to reach periodic steady state


@dataclass
class LayerSpec:
    name: str
    thickness_m: float      # Thickness in metres
    conductivity: float     # W / (m K)
    density: float          # kg / m^3
    specific_heat: float    # J / (kg K)
    absorptance: float      # Solar absorptance (0 - 1)
    emissivity: float = 0.9


@dataclass
class ClimateSpec:
    location_name: str
    t_max: float            # Peak outdoor temperature (deg C)
    t_min: float            # Minimum outdoor temperature (deg C)
    peak_solar: float       # Peak horizontal solar irradiance (W / m^2)
    wind_speed: float       # m / s
    ground_temp: float      # Steady ground temperature (deg C)


@dataclass
class ShelterSpec:
    name: str
    length_m: float
    width_m: float
    height_m: float
    window_n_m2: float
    window_s_m2: float
    window_e_m2: float
    window_w_m2: float
    door_area_m2: float
    window_shgc: float      # Effective solar heat gain coefficient (0.1 - 0.9)
    day_ach: float          # Daytime air changes per hour (06:00 - 20:00)
    night_ach: float        # Nighttime air changes per hour (20:00 - 06:00)
    occupants: int
    equipment_w: float
    comfort_model: str      # "imac" or "fixed"
    cool_roof_finish: bool = False
    wall_layers: List[LayerSpec] = field(default_factory=list)
    roof_layers: List[LayerSpec] = field(default_factory=list)
    floor_layers: List[LayerSpec] = field(default_factory=list)


def compute_assembly_u_value(layers: List[LayerSpec], r_se: float, r_si: float) -> float:
    """Compute ISO 6946 thermal transmittance U (W / m^2 K) for a layered assembly."""
    if not layers:
        raise ValueError("Assembly must contain at least one material layer.")
    r_total = r_se + r_si
    for layer in layers:
        if layer.thickness_m <= 0 or layer.conductivity <= 0:
            raise ValueError(f"Invalid thickness or conductivity in layer '{layer.name}'.")
        r_total += layer.thickness_m / layer.conductivity
    return 1.0 / r_total


def compute_comfort_band(t_out_mean: float, comfort_model: str) -> Dict:
    """
    Compute indoor thermal comfort band (deg C).
    IMAC naturally ventilated (80% acceptability):
        T_neutral = 0.54 * T_out_mean + 12.83
        Band = T_neutral +/- 3.5 deg C
    """
    warning = ""
    if comfort_model == "imac":
        t_neutral = 0.54 * t_out_mean + 12.83
        t_low = t_neutral - 3.5
        t_high = t_neutral + 3.5
        if t_out_mean < 12.5 or t_out_mean > 33.5:
            warning = (
                f"Outdoor daily mean ({t_out_mean:.1f} °C) is outside the typical "
                "IMAC adaptive model range (12.5–33.5 °C). Treat comfort limits as approximate."
            )
    else:
        t_neutral = 23.0
        t_low = 20.0
        t_high = 26.0
    return {
        "t_neutral": round(t_neutral, 2),
        "t_low": round(t_low, 2),
        "t_high": round(t_high, 2),
        "warning": warning,
    }


def _build_slices(layers: List[LayerSpec], slices_per_layer: int = 3):
    """Split an assembly (outside -> inside) into finite-volume thermal slices."""
    slices = []
    for layer in layers:
        n = slices_per_layer
        dx = layer.thickness_m / n
        r_slice = dx / layer.conductivity
        c_slice = layer.density * layer.specific_heat * dx  # J / (m^2 K)
        for _ in range(n):
            slices.append((r_slice, max(c_slice, 1.0)))
    return slices


def _outdoor_temp(hour: float, t_min: float, t_max: float) -> float:
    """Smooth diurnal outdoor air temperature peaking at 15:00, minimum at 03:00."""
    t_mean = 0.5 * (t_max + t_min)
    amp = 0.5 * (t_max - t_min)
    return t_mean - amp * math.cos(2.0 * math.pi * (hour - 3.0) / 24.0)


def _solar_irradiance(hour: float, peak_solar: float) -> Dict[str, float]:
    """
    Smooth clear-sky solar irradiance profiles (W / m^2) between 06:00 and 18:00
    for horizontal roof and N/S/E/W vertical surfaces.
    """
    if hour <= 6.0 or hour >= 18.0 or peak_solar <= 0:
        return {"roof": 0.0, "north": 0.0, "south": 0.0, "east": 0.0, "west": 0.0}

    sin_elev = math.sin(math.pi * (hour - 6.0) / 12.0)
    roof = peak_solar * sin_elev
    # Diffuse + directional approximations for vertical facades
    diffuse = 0.15 * roof
    east = diffuse + (0.65 * peak_solar * math.sin(math.pi * (hour - 6.0) / 6.0) if hour < 12.0 else 0.0)
    west = diffuse + (0.65 * peak_solar * math.sin(math.pi * (hour - 12.0) / 6.0) if hour > 12.0 else 0.0)
    south = diffuse + 0.35 * roof
    north = diffuse
    return {"roof": roof, "north": north, "south": south, "east": east, "west": west}


def _generate_suggestions(
    shelter: ShelterSpec,
    climate: ClimateSpec,
    u_wall: float,
    u_roof: float,
    overheating_dh: float,
    overcooling_dh: float,
    roof_alpha: float,
) -> List[str]:
    """Plain-language improvement suggestions based on simple engineering rules."""
    suggestions = []

    if overheating_dh > 5.0:
        if u_roof > 1.0:
            suggestions.append(
                f"Add roof insulation (e.g., 50 mm EPS, XPS, or PUF): your roof U-value is high "
                f"({u_roof:.2f} W/m²K), allowing heavy solar heat gain."
            )
        if roof_alpha > 0.40 and not shelter.cool_roof_finish:
            suggestions.append(
                "Apply a white/reflective cool-roof coating to reduce roof solar absorption and lower peak indoor temperatures."
            )
        if u_wall > 1.5:
            suggestions.append(
                f"Use lower-conductivity wall materials (such as AAC blocks or insulated masonry): "
                f"current wall U-value is {u_wall:.2f} W/m²K."
            )
        if shelter.night_ach < 6.0 and climate.t_min < 30.0:
            suggestions.append(
                f"Increase night-time ventilation (currently {shelter.night_ach:.1f} ACH) to 8–12 ACH "
                "to flush out stored daytime heat when outdoor air cools."
            )
        ew_windows = shelter.window_e_m2 + shelter.window_w_m2
        if ew_windows > 0.5 and shelter.window_shgc > 0.45:
            suggestions.append(
                f"Shade or reduce East and West windows ({ew_windows:.1f} m² total) using overhangs or external louvers "
                "to block low-angle morning and afternoon sun."
            )

    if overcooling_dh > 5.0:
        if u_wall > 1.0 or u_roof > 0.8:
            suggestions.append(
                "Improve wall and roof insulation to retain indoor warmth during cold periods."
            )
        if shelter.night_ach > 1.5:
            suggestions.append(
                f"Reduce night-time ventilation/infiltration (currently {shelter.night_ach:.1f} ACH) "
                "to prevent excessive heat loss at night."
            )

    if not suggestions:
        suggestions.append(
            "This shelter performs well for the selected climate. Fine-tune shading or night ventilation for marginal gains."
        )
    return suggestions


def run_simulation(shelter: ShelterSpec, climate: ClimateSpec) -> Dict:
    """
    Execute a full 24-hour transient thermal simulation (after warm-up days)
    using an implicit finite-volume thermal network.
    """
    # Validate basic geometry
    if shelter.length_m <= 0 or shelter.width_m <= 0 or shelter.height_m <= 0:
        raise ValueError("Shelter dimensions must be strictly positive.")
    if climate.t_min > climate.t_max:
        raise ValueError("Minimum outdoor temperature cannot exceed maximum temperature.")

    floor_area = shelter.length_m * shelter.width_m
    roof_area = floor_area
    volume = floor_area * shelter.height_m

    gross_wall_n = shelter.length_m * shelter.height_m
    gross_wall_s = shelter.length_m * shelter.height_m
    gross_wall_e = shelter.width_m * shelter.height_m
    gross_wall_w = shelter.width_m * shelter.height_m

    # Allocate door to South wall by convention if it fits, else proportionally
    net_wall_n = gross_wall_n - shelter.window_n_m2
    net_wall_s = gross_wall_s - shelter.window_s_m2 - shelter.door_area_m2
    net_wall_e = gross_wall_e - shelter.window_e_m2
    net_wall_w = gross_wall_w - shelter.window_w_m2

    if min(net_wall_n, net_wall_e, net_wall_w) < 0 or (gross_wall_s - shelter.window_s_m2) < 0:
        raise ValueError("Window area exceeds gross area on one or more walls.")
    if net_wall_s < 0:
        # Spread door area across total opaque walls if south wall is small
        total_gross_walls = gross_wall_n + gross_wall_s + gross_wall_e + gross_wall_w
        total_openings = (
            shelter.window_n_m2 + shelter.window_s_m2 + shelter.window_e_m2
            + shelter.window_w_m2 + shelter.door_area_m2
        )
        if total_openings >= total_gross_walls:
            raise ValueError("Total windows and door exceed total wall area.")
        net_wall_s = max(gross_wall_s - shelter.window_s_m2, 0.0)
        scale = (total_gross_walls - total_openings) / max(net_wall_n + net_wall_s + net_wall_e + net_wall_w, 1e-6)
        net_wall_n *= scale
        net_wall_s *= scale
        net_wall_e *= scale
        net_wall_w *= scale

    total_wall_area = net_wall_n + net_wall_s + net_wall_e + net_wall_w
    total_window_area = (
        shelter.window_n_m2 + shelter.window_s_m2 + shelter.window_e_m2 + shelter.window_w_m2
    )

    # U-values (W / m^2 K)
    u_wall = compute_assembly_u_value(shelter.wall_layers, R_SE, R_SI_WALL)
    u_roof = compute_assembly_u_value(shelter.roof_layers, R_SE, R_SI_ROOF)
    u_floor = compute_assembly_u_value(shelter.floor_layers, 0.0, R_SI_FLOOR)

    # UA breakdown (W / K)
    ua_wall = u_wall * total_wall_area
    ua_roof = u_roof * roof_area
    ua_floor = u_floor * floor_area
    ua_windows = DEFAULT_WINDOW_U * total_window_area
    ua_door = DEFAULT_DOOR_U * shelter.door_area_m2
    avg_ach = (14.0 * shelter.day_ach + 10.0 * shelter.night_ach) / 24.0
    ua_vent_avg = (avg_ach * volume / 3600.0) * AIR_DENSITY * AIR_CP

    # Exterior solar absorptance from outermost layer
    wall_alpha = shelter.wall_layers[0].absorptance
    roof_alpha = 0.25 if shelter.cool_roof_finish else shelter.roof_layers[0].absorptance

    # Build thermal network components:
    # Each component: (name, area, slices, r_ext, r_int, boundary_type, orientation)
    wall_slices = _build_slices(shelter.wall_layers, slices_per_layer=3)
    roof_slices = _build_slices(shelter.roof_layers, slices_per_layer=3)
    floor_slices = _build_slices(shelter.floor_layers, slices_per_layer=3)

    components = [
        ("wall_n", net_wall_n, wall_slices, R_SE, R_SI_WALL, "solair", "north"),
        ("wall_s", net_wall_s, wall_slices, R_SE, R_SI_WALL, "solair", "south"),
        ("wall_e", net_wall_e, wall_slices, R_SE, R_SI_WALL, "solair", "east"),
        ("wall_w", net_wall_w, wall_slices, R_SE, R_SI_WALL, "solair", "west"),
        ("roof", roof_area, roof_slices, R_SE, R_SI_ROOF, "solair", "roof"),
        ("floor", floor_area, floor_slices, 0.0, R_SI_FLOOR, "ground", "floor"),
    ]
    components = [c for c in components if c[1] > 1e-6]

    # Node indexing: 0 is indoor air, followed by slice nodes of each component
    offsets = []
    idx = 1
    for comp in components:
        offsets.append(idx)
        idx += len(comp[2])
    n_nodes = idx

    # Effective indoor air + furniture thermal capacitance (3x air mass for light furnishings)
    c_air = 3.0 * volume * AIR_DENSITY * AIR_CP

    # Initial temperature state
    t_out_mean = 0.5 * (climate.t_max + climate.t_min)
    T = np.full(n_nodes, t_out_mean, dtype=float)

    # Precompute static conductance terms for solid layers
    A_base = np.zeros((n_nodes, n_nodes), dtype=float)
    C_vec = np.zeros(n_nodes, dtype=float)
    C_vec[0] = c_air

    ext_conductances = []  # (node_idx, G_ext, boundary_type, orientation)

    for comp, start_i in zip(components, offsets):
        _, area, slices, r_ext, r_int, btype, orient = comp
        m = len(slices)
        for j, (r_s, c_s) in enumerate(slices):
            node = start_i + j
            C_vec[node] = c_s * area

            # Connection to outer side
            if j == 0:
                r_to_ext = r_ext + 0.5 * r_s
                g_ext = area / r_to_ext
                A_base[node, node] += g_ext
                ext_conductances.append((node, g_ext, btype, orient))
            else:
                r_prev = slices[j - 1][0]
                g_link = area / (0.5 * r_prev + 0.5 * r_s)
                A_base[node, node] += g_link
                A_base[node, node - 1] -= g_link
                A_base[node - 1, node - 1] += g_link
                A_base[node - 1, node] -= g_link

            # Connection of innermost slice to indoor air (node 0)
            if j == m - 1:
                g_int = area / (0.5 * r_s + r_int)
                A_base[node, node] += g_int
                A_base[node, 0] -= g_int
                A_base[0, 0] += g_int
                A_base[0, node] -= g_int

    # Add steady indoor-outdoor conductance for windows and door
    g_openings = ua_windows + ua_door
    A_base[0, 0] += g_openings

    # Comfort band
    comfort = compute_comfort_band(t_out_mean, shelter.comfort_model)
    t_comf_low = comfort["t_low"]
    t_comf_high = comfort["t_high"]

    total_steps = (WARMUP_DAYS + 1) * STEPS_PER_DAY
    final_day_start = WARMUP_DAYS * STEPS_PER_DAY

    hours_out = []
    t_in_series = []
    t_out_series = []
    cooling_w_series = []
    heating_w_series = []

    q_internal = shelter.occupants * OCCUPANT_HEAT_W + shelter.equipment_w

    for step in range(total_steps):
        step_in_day = step % STEPS_PER_DAY
        hour = (step_in_day + 0.5) * (24.0 / STEPS_PER_DAY)

        t_out = _outdoor_temp(hour, climate.t_min, climate.t_max)
        solar = _solar_irradiance(hour, climate.peak_solar)

        # Ventilation conductance (W / K)
        ach = shelter.day_ach if (6.0 <= hour < 20.0) else shelter.night_ach
        g_vent = (ach * volume / 3600.0) * AIR_DENSITY * AIR_CP

        # Solar heat gain through windows (W)
        q_solar_win = shelter.window_shgc * (
            shelter.window_n_m2 * solar["north"]
            + shelter.window_s_m2 * solar["south"]
            + shelter.window_e_m2 * solar["east"]
            + shelter.window_w_m2 * solar["west"]
        )

        # Build linear system: (C/dt + A) T_new = (C/dt) T_old + b
        A = A_base.copy()
        A[0, 0] += g_vent
        diag_cap = C_vec / DT_SECONDS
        A[np.arange(n_nodes), np.arange(n_nodes)] += diag_cap

        b = diag_cap * T
        b[0] += (g_openings + g_vent) * t_out + q_solar_win + q_internal

        for node, g_ext, btype, orient in ext_conductances:
            if btype == "ground":
                b[node] += g_ext * climate.ground_temp
            else:
                alpha = roof_alpha if orient == "roof" else wall_alpha
                # Sol-air temperature: T_out + alpha * I * R_se (- longwave sky correction for roof)
                sky_corr = 3.5 if orient == "roof" else 0.0
                t_solair = t_out + alpha * solar[orient] * R_SE - sky_corr
                b[node] += g_ext * t_solair

        T = np.linalg.solve(A, b)
        t_in = float(T[0])

        if step >= final_day_start:
            hours_out.append(round(hour, 2))
            t_in_series.append(round(t_in, 2))
            t_out_series.append(round(t_out, 2))

            # Estimate instantaneous cooling / heating power required to hold comfort boundary
            # Total indoor coupling conductance = sum of interior surface + openings + ventilation
            g_total_in = float(A_base[0, 0] + g_vent)
            if t_in > t_comf_high:
                q_cool = g_total_in * (t_in - t_comf_high)
                q_heat = 0.0
            elif t_in < t_comf_low:
                q_cool = 0.0
                q_heat = g_total_in * (t_comf_low - t_in)
            else:
                q_cool = 0.0
                q_heat = 0.0
            cooling_w_series.append(round(q_cool, 1))
            heating_w_series.append(round(q_heat, 1))

    # Summary statistics
    t_in_arr = np.array(t_in_series)
    dt_hr = DT_SECONDS / 3600.0

    t_in_max = float(np.max(t_in_arr))
    t_in_min = float(np.min(t_in_arr))
    t_in_avg = float(np.mean(t_in_arr))
    peak_idx = int(np.argmax(t_in_arr))
    peak_hour = hours_out[peak_idx]

    comfortable_steps = int(np.sum((t_in_arr >= t_comf_low) & (t_in_arr <= t_comf_high)))
    comfortable_hours = round(comfortable_steps * dt_hr, 1)

    overheating_dh = round(float(np.sum(np.maximum(t_in_arr - t_comf_high, 0.0)) * dt_hr), 1)
    overcooling_dh = round(float(np.sum(np.maximum(t_comf_low - t_in_arr, 0.0)) * dt_hr), 1)
    total_discomfort_dh = round(overheating_dh + overcooling_dh, 1)

    peak_cooling_w = round(float(np.max(cooling_w_series)), 0)
    peak_heating_w = round(float(np.max(heating_w_series)), 0)
    daily_cooling_kwh = round(float(np.sum(cooling_w_series) * dt_hr / 1000.0), 2)
    daily_heating_kwh = round(float(np.sum(heating_w_series) * dt_hr / 1000.0), 2)

    # Clear textual verdict (Good / Marginal / Poor)
    if total_discomfort_dh <= 15.0 and comfortable_hours >= 14.0:
        verdict = "Good"
    elif total_discomfort_dh <= 45.0 and t_in_max <= t_comf_high + 5.0:
        verdict = "Marginal"
    else:
        verdict = "Poor"

    suggestions = _generate_suggestions(
        shelter=shelter,
        climate=climate,
        u_wall=u_wall,
        u_roof=u_roof,
        overheating_dh=overheating_dh,
        overcooling_dh=overcooling_dh,
        roof_alpha=roof_alpha,
    )

    return {
        "u_values": {
            "wall": round(u_wall, 3),
            "roof": round(u_roof, 3),
            "floor": round(u_floor, 3),
            "window": DEFAULT_WINDOW_U,
            "door": DEFAULT_DOOR_U,
        },
        "ua_breakdown": {
            "Walls": round(ua_wall, 2),
            "Roof": round(ua_roof, 2),
            "Floor": round(ua_floor, 2),
            "Windows": round(ua_windows, 2),
            "Door": round(ua_door, 2),
            "Ventilation (avg)": round(ua_vent_avg, 2),
        },
        "summary": {
            "t_in_max": round(t_in_max, 2),
            "t_in_min": round(t_in_min, 2),
            "t_in_avg": round(t_in_avg, 2),
            "peak_hour": peak_hour,
            "t_out_max": climate.t_max,
            "t_out_min": climate.t_min,
            "t_out_mean": round(t_out_mean, 2),
            "comfort_low": comfort["t_low"],
            "comfort_high": comfort["t_high"],
            "comfort_neutral": comfort["t_neutral"],
            "comfort_warning": comfort["warning"],
            "comfortable_hours": comfortable_hours,
            "overheating_dh": overheating_dh,
            "overcooling_dh": overcooling_dh,
            "total_discomfort_dh": total_discomfort_dh,
            "peak_cooling_w": peak_cooling_w,
            "peak_heating_w": peak_heating_w,
            "daily_cooling_kwh": daily_cooling_kwh,
            "daily_heating_kwh": daily_heating_kwh,
            "verdict": verdict,
        },
        "suggestions": suggestions,
        "series": {
            "hours": hours_out,
            "t_in": t_in_series,
            "t_out": t_out_series,
            "cooling_w": cooling_w_series,
            "heating_w": heating_w_series,
        },
    }
