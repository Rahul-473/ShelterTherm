from django.contrib import admin
from .models import AssemblyLayer, ClimateLocation, Material, ShelterDesign, SimulationResult


@admin.register(Material)
class MaterialAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "conductivity", "density", "specific_heat", "absorptance", "emissivity")
    list_filter = ("category",)
    search_fields = ("name", "source")


@admin.register(ClimateLocation)
class ClimateLocationAdmin(admin.ModelAdmin):
    list_display = ("name", "state", "climate_zone", "design_day_type", "t_max", "t_min", "peak_solar")
    list_filter = ("climate_zone", "design_day_type")
    search_fields = ("name", "state")


class AssemblyLayerInline(admin.TabularInline):
    model = AssemblyLayer
    extra = 1


@admin.register(ShelterDesign)
class ShelterDesignAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "location", "length_m", "width_m", "height_m", "updated_at")
    list_filter = ("comfort_model", "cool_roof_finish", "location__climate_zone")
    search_fields = ("name", "user__username")
    inlines = [AssemblyLayerInline]


@admin.register(SimulationResult)
class SimulationResultAdmin(admin.ModelAdmin):
    list_display = ("design", "verdict", "t_in_max", "comfortable_hours", "overheating_dh", "peak_cooling_w", "simulated_at")
    list_filter = ("verdict",)
