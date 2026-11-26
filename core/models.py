from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Material(models.Model):
    CATEGORY_CHOICES = [
        ("masonry", "Masonry & Concrete"),
        ("insulation", "Insulation"),
        ("sheet", "Metal & Sheet"),
        ("natural", "Natural / Vernacular"),
        ("finish", "Plaster & Finish"),
        ("glazing", "Glazing"),
    ]

    name = models.CharField(max_length=120, unique=True)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default="masonry")
    conductivity = models.FloatField(
        help_text="Thermal conductivity k in W/(m·K)",
        validators=[MinValueValidator(0.005), MaxValueValidator(500.0)],
    )
    density = models.FloatField(
        help_text="Density in kg/m³",
        validators=[MinValueValidator(1.0), MaxValueValidator(20000.0)],
    )
    specific_heat = models.FloatField(
        help_text="Specific heat capacity in J/(kg·K)",
        validators=[MinValueValidator(100.0), MaxValueValidator(5000.0)],
    )
    absorptance = models.FloatField(
        help_text="Solar absorptance (0.0 to 1.0)",
        validators=[MinValueValidator(0.01), MaxValueValidator(1.0)],
    )
    emissivity = models.FloatField(
        default=0.90,
        help_text="Surface long-wave emissivity (0.0 to 1.0)",
        validators=[MinValueValidator(0.05), MaxValueValidator(1.0)],
    )
    source = models.CharField(
        max_length=200,
        default="ECBC 2017 / Typical handbook value",
        help_text="Reference source for material properties",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["category", "name"]

    def __str__(self):
        return f"{self.name} (k={self.conductivity} W/m·K)"


class ClimateLocation(models.Model):
    ZONE_CHOICES = [
        ("Hot & Dry", "Hot & Dry"),
        ("Warm & Humid", "Warm & Humid"),
        ("Composite", "Composite"),
        ("Temperate", "Temperate"),
        ("Cold", "Cold"),
    ]

    name = models.CharField(max_length=120, unique=True)
    state = models.CharField(max_length=80)
    climate_zone = models.CharField(max_length=30, choices=ZONE_CHOICES)
    design_day_type = models.CharField(
        max_length=20,
        choices=[("Summer", "Summer (Hot Day)"), ("Winter", "Winter (Cold Day)")],
        default="Summer",
    )
    t_max = models.FloatField(
        help_text="Peak outdoor temperature (°C)",
        validators=[MinValueValidator(-30.0), MaxValueValidator(55.0)],
    )
    t_min = models.FloatField(
        help_text="Minimum outdoor temperature (°C)",
        validators=[MinValueValidator(-40.0), MaxValueValidator(45.0)],
    )
    peak_solar = models.FloatField(
        help_text="Peak horizontal solar irradiance (W/m²)",
        validators=[MinValueValidator(0.0), MaxValueValidator(1300.0)],
    )
    wind_speed = models.FloatField(
        help_text="Average wind speed (m/s)",
        validators=[MinValueValidator(0.0), MaxValueValidator(30.0)],
    )
    ground_temp = models.FloatField(
        help_text="Steady ground temperature (°C)",
        validators=[MinValueValidator(-10.0), MaxValueValidator(45.0)],
    )
    source = models.CharField(
        max_length=200,
        default="NBC 2016 / Typical Indian design-day estimate",
    )

    class Meta:
        ordering = ["name"]

    def clean(self):
        if self.t_min is not None and self.t_max is not None and self.t_min > self.t_max:
            raise ValidationError("Minimum temperature cannot exceed maximum temperature.")

    def __str__(self):
        return f"{self.name}, {self.state} ({self.climate_zone})"


class ShelterDesign(models.Model):
    COMFORT_CHOICES = [
        ("imac", "IMAC Adaptive Comfort (India)"),
        ("fixed", "Fixed Comfort Band (20–26 °C)"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="shelter_designs")
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    location = models.ForeignKey(ClimateLocation, on_delete=models.PROTECT, related_name="designs")

    # Optional design-specific climate overrides
    override_t_max = models.FloatField(
        null=True, blank=True,
        validators=[MinValueValidator(-30.0), MaxValueValidator(55.0)],
        help_text="Optional override for peak outdoor temp (°C)",
    )
    override_t_min = models.FloatField(
        null=True, blank=True,
        validators=[MinValueValidator(-40.0), MaxValueValidator(45.0)],
        help_text="Optional override for minimum outdoor temp (°C)",
    )
    override_peak_solar = models.FloatField(
        null=True, blank=True,
        validators=[MinValueValidator(0.0), MaxValueValidator(1300.0)],
        help_text="Optional override for peak solar irradiance (W/m²)",
    )
    override_wind_speed = models.FloatField(
        null=True, blank=True,
        validators=[MinValueValidator(0.0), MaxValueValidator(30.0)],
        help_text="Optional override for wind speed (m/s)",
    )
    override_ground_temp = models.FloatField(
        null=True, blank=True,
        validators=[MinValueValidator(-10.0), MaxValueValidator(45.0)],
        help_text="Optional override for ground temp (°C)",
    )

    # Geometry (metres & square metres)
    length_m = models.FloatField(default=4.0, validators=[MinValueValidator(1.0), MaxValueValidator(50.0)])
    width_m = models.FloatField(default=3.0, validators=[MinValueValidator(1.0), MaxValueValidator(50.0)])
    height_m = models.FloatField(default=2.7, validators=[MinValueValidator(1.8), MaxValueValidator(10.0)])

    window_n_m2 = models.FloatField(default=0.5, validators=[MinValueValidator(0.0), MaxValueValidator(100.0)])
    window_s_m2 = models.FloatField(default=0.5, validators=[MinValueValidator(0.0), MaxValueValidator(100.0)])
    window_e_m2 = models.FloatField(default=0.5, validators=[MinValueValidator(0.0), MaxValueValidator(100.0)])
    window_w_m2 = models.FloatField(default=0.5, validators=[MinValueValidator(0.0), MaxValueValidator(100.0)])
    door_area_m2 = models.FloatField(default=1.8, validators=[MinValueValidator(0.0), MaxValueValidator(20.0)])
    window_shgc = models.FloatField(
        default=0.65,
        validators=[MinValueValidator(0.10), MaxValueValidator(0.95)],
        help_text="Effective window Solar Heat Gain Coefficient (0.25 = well shaded, 0.70 = unshaded)",
    )

    # Ventilation & internal gains
    day_ach = models.FloatField(
        default=2.0,
        validators=[MinValueValidator(0.1), MaxValueValidator(30.0)],
        help_text="Daytime air changes per hour (06:00–20:00)",
    )
    night_ach = models.FloatField(
        default=2.0,
        validators=[MinValueValidator(0.1), MaxValueValidator(30.0)],
        help_text="Night-time air changes per hour (20:00–06:00)",
    )
    occupants = models.PositiveIntegerField(
        default=3,
        validators=[MaxValueValidator(100)],
        help_text="Number of people inside (~100 W each)",
    )
    equipment_w = models.FloatField(
        default=100.0,
        validators=[MinValueValidator(0.0), MaxValueValidator(10000.0)],
        help_text="Internal lighting / equipment heat gain (W)",
    )

    # Comfort & roof finish options
    comfort_model = models.CharField(max_length=15, choices=COMFORT_CHOICES, default="imac")
    cool_roof_finish = models.BooleanField(
        default=False,
        help_text="Apply white / reflective cool-roof coating (lowers roof solar absorption to 0.25)",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def effective_climate(self):
        return {
            "t_max": self.override_t_max if self.override_t_max is not None else self.location.t_max,
            "t_min": self.override_t_min if self.override_t_min is not None else self.location.t_min,
            "peak_solar": self.override_peak_solar if self.override_peak_solar is not None else self.location.peak_solar,
            "wind_speed": self.override_wind_speed if self.override_wind_speed is not None else self.location.wind_speed,
            "ground_temp": self.override_ground_temp if self.override_ground_temp is not None else self.location.ground_temp,
        }

    def clean(self):
        clim = self.effective_climate() if self.location_id else None
        if clim and clim["t_min"] > clim["t_max"]:
            raise ValidationError("Minimum outdoor temperature cannot exceed maximum temperature.")

        if self.length_m and self.width_m and self.height_m:
            ns_wall = self.length_m * self.height_m
            ew_wall = self.width_m * self.height_m
            if self.window_n_m2 > ns_wall:
                raise ValidationError("North window area exceeds North wall area.")
            if self.window_s_m2 > ns_wall:
                raise ValidationError("South window area exceeds South wall area.")
            if self.window_e_m2 > ew_wall:
                raise ValidationError("East window area exceeds East wall area.")
            if self.window_w_m2 > ew_wall:
                raise ValidationError("West window area exceeds West wall area.")
            total_wall = 2 * (ns_wall + ew_wall)
            total_openings = (
                self.window_n_m2 + self.window_s_m2 + self.window_e_m2
                + self.window_w_m2 + self.door_area_m2
            )
            if total_openings >= total_wall:
                raise ValidationError("Total window and door areas must be smaller than total wall area.")

    def __str__(self):
        return f"{self.name} ({self.location.name})"


class AssemblyLayer(models.Model):
    ELEMENT_CHOICES = [
        ("wall", "Wall"),
        ("roof", "Roof"),
        ("floor", "Floor"),
    ]

    design = models.ForeignKey(ShelterDesign, on_delete=models.CASCADE, related_name="layers")
    element = models.CharField(max_length=10, choices=ELEMENT_CHOICES)
    order = models.PositiveIntegerField(
        default=1,
        help_text="Layer order from outside (1) to inside",
    )
    material = models.ForeignKey(Material, on_delete=models.PROTECT, related_name="used_in_layers")
    thickness_mm = models.FloatField(
        validators=[MinValueValidator(0.3), MaxValueValidator(1000.0)],
        help_text="Layer thickness in millimetres (mm)",
    )

    class Meta:
        ordering = ["element", "order"]

    def __str__(self):
        return f"{self.get_element_display()} #{self.order}: {self.material.name} ({self.thickness_mm} mm)"


class SimulationResult(models.Model):
    design = models.OneToOneField(ShelterDesign, on_delete=models.CASCADE, related_name="result")

    u_wall = models.FloatField()
    u_roof = models.FloatField()
    u_floor = models.FloatField()

    t_in_max = models.FloatField()
    t_in_min = models.FloatField()
    t_in_avg = models.FloatField()
    peak_hour = models.FloatField()

    comfort_low = models.FloatField()
    comfort_high = models.FloatField()
    comfort_warning = models.TextField(blank=True)

    comfortable_hours = models.FloatField()
    overheating_dh = models.FloatField()
    overcooling_dh = models.FloatField()
    total_discomfort_dh = models.FloatField()

    peak_cooling_w = models.FloatField()
    peak_heating_w = models.FloatField()
    daily_cooling_kwh = models.FloatField()
    daily_heating_kwh = models.FloatField()

    verdict = models.CharField(max_length=20)
    ua_breakdown = models.JSONField(default=dict)
    suggestions = models.JSONField(default=list)
    time_series = models.JSONField(default=dict)

    simulated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Result for {self.design.name}: {self.verdict} (Max {self.t_in_max}°C)"
