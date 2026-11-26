import json
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from .forms import AssemblyLayerFormSet, RegisterForm, ShelterDesignForm
from .models import AssemblyLayer, ClimateLocation, Material, ShelterDesign, SimulationResult
from .reports import generate_csv_response, generate_pdf_response
from .simulation.engine import ClimateSpec, LayerSpec, ShelterSpec, run_simulation


def _execute_and_save_simulation(design: ShelterDesign) -> SimulationResult:
    """Convert Django model objects to pure-Python specs, run simulation, and persist result."""
    layers = list(design.layers.select_related("material").order_by("element", "order"))
    by_el = {"wall": [], "roof": [], "floor": []}
    for lyr in layers:
        m = lyr.material
        by_el[lyr.element].append(
            LayerSpec(
                name=m.name,
                thickness_m=lyr.thickness_mm / 1000.0,
                conductivity=m.conductivity,
                density=m.density,
                specific_heat=m.specific_heat,
                absorptance=m.absorptance,
                emissivity=m.emissivity,
            )
        )

    for el_name in ("wall", "roof", "floor"):
        if not by_el[el_name]:
            raise ValueError(f"At least one {el_name} layer is required before running a simulation.")

    clim_data = design.effective_climate()
    climate_spec = ClimateSpec(
        location_name=design.location.name,
        t_max=clim_data["t_max"],
        t_min=clim_data["t_min"],
        peak_solar=clim_data["peak_solar"],
        wind_speed=clim_data["wind_speed"],
        ground_temp=clim_data["ground_temp"],
    )
    shelter_spec = ShelterSpec(
        name=design.name,
        length_m=design.length_m,
        width_m=design.width_m,
        height_m=design.height_m,
        window_n_m2=design.window_n_m2,
        window_s_m2=design.window_s_m2,
        window_e_m2=design.window_e_m2,
        window_w_m2=design.window_w_m2,
        door_area_m2=design.door_area_m2,
        window_shgc=design.window_shgc,
        day_ach=design.day_ach,
        night_ach=design.night_ach,
        occupants=design.occupants,
        equipment_w=design.equipment_w,
        comfort_model=design.comfort_model,
        cool_roof_finish=design.cool_roof_finish,
        wall_layers=by_el["wall"],
        roof_layers=by_el["roof"],
        floor_layers=by_el["floor"],
    )

    output = run_simulation(shelter_spec, climate_spec)
    sm = output["summary"]
    uv = output["u_values"]

    result, _ = SimulationResult.objects.update_or_create(
        design=design,
        defaults={
            "u_wall": uv["wall"],
            "u_roof": uv["roof"],
            "u_floor": uv["floor"],
            "t_in_max": sm["t_in_max"],
            "t_in_min": sm["t_in_min"],
            "t_in_avg": sm["t_in_avg"],
            "peak_hour": sm["peak_hour"],
            "comfort_low": sm["comfort_low"],
            "comfort_high": sm["comfort_high"],
            "comfort_warning": sm["comfort_warning"],
            "comfortable_hours": sm["comfortable_hours"],
            "overheating_dh": sm["overheating_dh"],
            "overcooling_dh": sm["overcooling_dh"],
            "total_discomfort_dh": sm["total_discomfort_dh"],
            "peak_cooling_w": sm["peak_cooling_w"],
            "peak_heating_w": sm["peak_heating_w"],
            "daily_cooling_kwh": sm["daily_cooling_kwh"],
            "daily_heating_kwh": sm["daily_heating_kwh"],
            "verdict": sm["verdict"],
            "ua_breakdown": output["ua_breakdown"],
            "suggestions": output["suggestions"],
            "time_series": output["series"],
        },
    )
    return result


def home(request):
    context = {
        "material_count": Material.objects.count(),
        "location_count": ClimateLocation.objects.count(),
        "design_count": ShelterDesign.objects.count(),
    }
    return render(request, "core/home.html", context)


def register_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, f"Welcome to ShelterTherm, {user.username}!")
            return redirect("dashboard")
    else:
        form = RegisterForm()
    return render(request, "registration/register.html", {"form": form})


@login_required
def dashboard(request):
    designs = (
        ShelterDesign.objects.filter(user=request.user)
        .select_related("location", "result")
        .order_by("-updated_at")
    )
    return render(request, "core/dashboard.html", {"designs": designs})


def material_list(request):
    q = request.GET.get("q", "").strip()
    cat = request.GET.get("category", "").strip()
    materials = Material.objects.all()
    if q:
        materials = materials.filter(Q(name__icontains=q) | Q(source__icontains=q))
    if cat:
        materials = materials.filter(category=cat)
    return render(
        request,
        "core/material_list.html",
        {
            "materials": materials,
            "q": q,
            "selected_category": cat,
            "categories": Material.CATEGORY_CHOICES,
        },
    )


def location_list(request):
    q = request.GET.get("q", "").strip()
    zone = request.GET.get("zone", "").strip()
    locations = ClimateLocation.objects.all()
    if q:
        locations = locations.filter(Q(name__icontains=q) | Q(state__icontains=q))
    if zone:
        locations = locations.filter(climate_zone=zone)
    return render(
        request,
        "core/location_list.html",
        {
            "locations": locations,
            "q": q,
            "selected_zone": zone,
            "zones": ClimateLocation.ZONE_CHOICES,
        },
    )


@login_required
def design_create(request):
    if request.method == "POST":
        form = ShelterDesignForm(request.POST)
        formset = AssemblyLayerFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            design = form.save(commit=False)
            design.user = request.user
            design.save()
            formset.instance = design
            formset.save()
            try:
                _execute_and_save_simulation(design)
                messages.success(request, f"Design '{design.name}' saved and simulated!")
                return redirect("design_detail", pk=design.pk)
            except ValueError as exc:
                design.delete()
                messages.error(request, f"Simulation failed: {exc}")
    else:
        form = ShelterDesignForm()
        # Provide helpful initial rows for 1 wall, 1 roof, 1 floor layer
        default_brick = Material.objects.filter(name__icontains="brick").first()
        default_rcc = Material.objects.filter(name__icontains="RCC").first()
        initial_layers = [
            {"element": "wall", "order": 1, "material": default_brick, "thickness_mm": 230},
            {"element": "roof", "order": 1, "material": default_rcc, "thickness_mm": 120},
            {"element": "floor", "order": 1, "material": default_rcc, "thickness_mm": 100},
        ]
        formset = AssemblyLayerFormSet(initial=initial_layers)
    return render(
        request,
        "core/design_form.html",
        {"form": form, "formset": formset, "is_edit": False},
    )


@login_required
def design_edit(request, pk):
    design = get_object_or_404(ShelterDesign, pk=pk, user=request.user)
    if request.method == "POST":
        form = ShelterDesignForm(request.POST, instance=design)
        formset = AssemblyLayerFormSet(request.POST, instance=design)
        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            try:
                _execute_and_save_simulation(design)
                messages.success(request, f"Design '{design.name}' updated and re-simulated!")
                return redirect("design_detail", pk=design.pk)
            except ValueError as exc:
                messages.error(request, f"Simulation error: {exc}")
    else:
        form = ShelterDesignForm(instance=design)
        formset = AssemblyLayerFormSet(instance=design)
    return render(
        request,
        "core/design_form.html",
        {"form": form, "formset": formset, "design": design, "is_edit": True},
    )


@login_required
def design_duplicate(request, pk):
    original = get_object_or_404(ShelterDesign, pk=pk, user=request.user)
    if request.method == "POST":
        layers = list(original.layers.all())
        copy_design = ShelterDesign.objects.get(pk=original.pk)
        copy_design.pk = None
        copy_design.name = f"{original.name} (Copy)"
        copy_design.save()
        for lyr in layers:
            AssemblyLayer.objects.create(
                design=copy_design,
                element=lyr.element,
                order=lyr.order,
                material=lyr.material,
                thickness_mm=lyr.thickness_mm,
            )
        try:
            _execute_and_save_simulation(copy_design)
            messages.success(request, f"Created copy '{copy_design.name}'.")
        except ValueError as exc:
            messages.warning(request, f"Copy created, but simulation needs review: {exc}")
        return redirect("design_edit", pk=copy_design.pk)
    return redirect("dashboard")


@login_required
def design_delete(request, pk):
    design = get_object_or_404(ShelterDesign, pk=pk, user=request.user)
    if request.method == "POST":
        name = design.name
        design.delete()
        messages.info(request, f"Deleted design '{name}'.")
    return redirect("dashboard")


@login_required
def design_detail(request, pk):
    design = get_object_or_404(
        ShelterDesign.objects.select_related("location"),
        pk=pk,
        user=request.user,
    )
    result = getattr(design, "result", None)
    if result is None:
        try:
            result = _execute_and_save_simulation(design)
        except ValueError as exc:
            messages.error(request, f"Cannot simulate design: {exc}")
            return redirect("design_edit", pk=design.pk)

    chart_payload = {
        "hours": result.time_series.get("hours", []),
        "t_in": result.time_series.get("t_in", []),
        "t_out": result.time_series.get("t_out", []),
        "comfort_low": result.comfort_low,
        "comfort_high": result.comfort_high,
        "ua_labels": list(result.ua_breakdown.keys()),
        "ua_values": list(result.ua_breakdown.values()),
    }
    return render(
        request,
        "core/design_detail.html",
        {
            "design": design,
            "result": result,
            "effective_climate": design.effective_climate(),
            "layers": design.layers.select_related("material").all(),
            "chart_json": json.dumps(chart_payload),
        },
    )


@login_required
def compare_designs(request):
    user_designs = (
        ShelterDesign.objects.filter(user=request.user, result__isnull=False)
        .select_related("location", "result")
        .order_by("-updated_at")
    )
    selected_ids = request.GET.getlist("ids")
    compared = []
    error_msg = ""
    chart_json = "{}"

    if selected_ids:
        if len(selected_ids) < 2 or len(selected_ids) > 4:
            error_msg = "Please select between 2 and 4 designs to compare."
        else:
            qs = list(user_designs.filter(pk__in=selected_ids))
            if len(qs) < 2:
                error_msg = "Could not find at least 2 valid simulated designs."
            else:
                # Rank by lowest total discomfort degree-hours, then lowest peak indoor temp
                compared = sorted(
                    qs,
                    key=lambda d: (d.result.total_discomfort_dh, d.result.t_in_max),
                )
                hours = compared[0].result.time_series.get("hours", [])
                t_out = compared[0].result.time_series.get("t_out", [])
                datasets = []
                for d in compared:
                    datasets.append({
                        "label": d.name,
                        "data": d.result.time_series.get("t_in", []),
                    })
                chart_json = json.dumps({
                    "hours": hours,
                    "t_out": t_out,
                    "comfort_low": compared[0].result.comfort_low,
                    "comfort_high": compared[0].result.comfort_high,
                    "datasets": datasets,
                })

    return render(
        request,
        "core/compare.html",
        {
            "user_designs": user_designs,
            "selected_ids": [str(i) for i in selected_ids],
            "compared": compared,
            "error_msg": error_msg,
            "chart_json": chart_json,
        },
    )


@login_required
def export_csv(request, pk):
    design = get_object_or_404(ShelterDesign, pk=pk, user=request.user)
    result = get_object_or_404(SimulationResult, design=design)
    return generate_csv_response(design, result)


@login_required
def export_pdf(request, pk):
    design = get_object_or_404(ShelterDesign, pk=pk, user=request.user)
    result = get_object_or_404(SimulationResult, design=design)
    try:
        return generate_pdf_response(design, result)
    except Exception as exc:
        messages.error(request, f"PDF export failed ({exc}). You can still download the CSV report.")
        return redirect("design_detail", pk=design.pk)


def help_page(request):
    return render(request, "core/help.html")
