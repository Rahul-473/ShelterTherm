from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from core.models import AssemblyLayer, ClimateLocation, Material, ShelterDesign
from core.views import _execute_and_save_simulation


MATERIALS = [
    ("Cement plaster", "finish", 0.72, 1860, 840, 0.60, 0.90),
    ("Burnt clay brick", "masonry", 0.81, 1800, 880, 0.70, 0.90),
    ("RCC / dense concrete", "masonry", 1.63, 2400, 880, 0.65, 0.90),
    ("AAC block", "masonry", 0.16, 600, 1050, 0.60, 0.90),
    ("Adobe / mud wall", "natural", 0.60, 1700, 880, 0.70, 0.90),
    ("Timber (softwood)", "natural", 0.12, 500, 1600, 0.60, 0.90),
    ("Bamboo", "natural", 0.17, 700, 1400, 0.65, 0.90),
    ("Thatch", "natural", 0.07, 250, 1200, 0.70, 0.90),
    ("GI sheet", "sheet", 45.0, 7800, 480, 0.65, 0.25),
    ("Fibre-cement sheet", "sheet", 0.35, 1500, 1000, 0.65, 0.90),
    ("EPS insulation", "insulation", 0.035, 20, 1400, 0.60, 0.90),
    ("XPS insulation", "insulation", 0.034, 35, 1400, 0.60, 0.90),
    ("Mineral wool", "insulation", 0.040, 30, 840, 0.60, 0.90),
    ("PUF insulation", "insulation", 0.025, 35, 1400, 0.60, 0.90),
    ("Glass", "glazing", 1.05, 2500, 840, 0.10, 0.84),
]

LOCATIONS = [
    ("New Delhi", "Delhi", "Composite", "Summer", 42.0, 28.0, 950.0, 2.5, 28.0),
    ("Phagwara / Jalandhar", "Punjab", "Composite", "Summer", 41.0, 26.0, 940.0, 2.2, 27.0),
    ("Jaipur", "Rajasthan", "Hot & Dry", "Summer", 43.0, 27.0, 1000.0, 3.0, 29.0),
    ("Ahmedabad", "Gujarat", "Hot & Dry", "Summer", 43.5, 28.0, 980.0, 2.8, 29.0),
    ("Mumbai", "Maharashtra", "Warm & Humid", "Summer", 34.5, 26.5, 850.0, 3.5, 28.0),
    ("Chennai", "Tamil Nadu", "Warm & Humid", "Summer", 38.0, 28.0, 900.0, 3.2, 29.0),
    ("Kolkata", "West Bengal", "Warm & Humid", "Summer", 37.5, 27.0, 860.0, 2.6, 28.0),
    ("Bengaluru", "Karnataka", "Temperate", "Summer", 33.5, 21.5, 920.0, 2.4, 24.0),
    ("Pune", "Maharashtra", "Temperate", "Summer", 37.0, 22.0, 940.0, 2.5, 25.0),
    ("Hyderabad", "Telangana", "Composite", "Summer", 40.0, 26.0, 950.0, 2.7, 27.5),
    ("Shimla (Winter)", "Himachal Pradesh", "Cold", "Winter", 10.0, 1.0, 580.0, 2.0, 8.0),
    ("Leh (Winter)", "Ladakh", "Cold", "Winter", 2.0, -12.0, 680.0, 2.5, 2.0),
]


class Command(BaseCommand):
    help = "Seed initial materials, Indian climate locations, and demo sample designs."

    def handle(self, *args, **options):
        mat_objs = {}
        for name, cat, k, rho, cp, alpha, eps in MATERIALS:
            obj, _ = Material.objects.update_or_create(
                name=name,
                defaults={
                    "category": cat,
                    "conductivity": k,
                    "density": rho,
                    "specific_heat": cp,
                    "absorptance": alpha,
                    "emissivity": eps,
                    "source": "ECBC 2017 / ShelterTherm Appendix A.1",
                },
            )
            mat_objs[name] = obj
        self.stdout.write(self.style.SUCCESS(f"Seeded {len(mat_objs)} materials."))

        loc_objs = {}
        for name, state, zone, dtype, tmax, tmin, solar, wind, gtemp in LOCATIONS:
            obj, _ = ClimateLocation.objects.update_or_create(
                name=name,
                defaults={
                    "state": state,
                    "climate_zone": zone,
                    "design_day_type": dtype,
                    "t_max": tmax,
                    "t_min": tmin,
                    "peak_solar": solar,
                    "wind_speed": wind,
                    "ground_temp": gtemp,
                    "source": "NBC 2016 / Typical design-day profile",
                },
            )
            loc_objs[name] = obj
        self.stdout.write(self.style.SUCCESS(f"Seeded {len(loc_objs)} climate locations."))

        # Create demo user with the 5 sample designs (A-E) from Section 4.3
        demo_user, created = User.objects.get_or_create(
            username="demo",
            defaults={"email": "demo@sheltertherm.local"},
        )
        if created:
            demo_user.set_password("demo1234")
            demo_user.save()

        sample_loc = loc_objs["Hyderabad"]  # 40C / 26C / 950 W/m^2

        samples = [
            (
                "Option A: Brick + RCC Roof",
                "Plastered 230 mm brick wall with plain 120 mm RCC roof.",
                False, 0.70, 2.0, 2.0,
                [("Cement plaster", 12), ("Burnt clay brick", 230), ("Cement plaster", 12)],
                [("RCC / dense concrete", 120)],
                [("RCC / dense concrete", 100)],
            ),
            (
                "Option B: GI Tin Sheet Shelter",
                "Thin GI sheet walls and roof typical of temporary relief shelters.",
                False, 0.70, 2.0, 2.0,
                [("GI sheet", 1.0)],
                [("GI sheet", 1.0)],
                [("RCC / dense concrete", 100)],
            ),
            (
                "Option C: AAC + Insulated Cool Roof",
                "200 mm AAC block walls, 50 mm EPS roof insulation over RCC, white cool roof.",
                True, 0.70, 2.0, 2.0,
                [("Cement plaster", 12), ("AAC block", 200), ("Cement plaster", 12)],
                [("EPS insulation", 50), ("RCC / dense concrete", 120)],
                [("RCC / dense concrete", 100)],
            ),
            (
                "Option D: Vernacular Adobe + Thatch",
                "300 mm adobe mud walls with 150 mm thatch over bamboo roof.",
                False, 0.70, 2.0, 2.0,
                [("Adobe / mud wall", 300)],
                [("Thatch", 150), ("Bamboo", 25)],
                [("Adobe / mud wall", 150)],
            ),
            (
                "Option E: AAC + Cool Roof + Shaded + Night Flush",
                "Same as Option C plus shaded windows (SHGC 0.25) and 12 ACH night ventilation.",
                True, 0.25, 1.0, 12.0,
                [("Cement plaster", 12), ("AAC block", 200), ("Cement plaster", 12)],
                [("EPS insulation", 50), ("RCC / dense concrete", 120)],
                [("RCC / dense concrete", 100)],
            ),
        ]

        for name, desc, cool, shgc, dach, nach, wl, rl, fl in samples:
            design, _ = ShelterDesign.objects.update_or_create(
                user=demo_user,
                name=name,
                defaults={
                    "description": desc,
                    "location": sample_loc,
                    "length_m": 4.0,
                    "width_m": 3.0,
                    "height_m": 2.7,
                    "window_n_m2": 0.5,
                    "window_s_m2": 0.5,
                    "window_e_m2": 0.5,
                    "window_w_m2": 0.5,
                    "door_area_m2": 1.8,
                    "window_shgc": shgc,
                    "day_ach": dach,
                    "night_ach": nach,
                    "occupants": 3,
                    "equipment_w": 100.0,
                    "comfort_model": "imac",
                    "cool_roof_finish": cool,
                },
            )
            design.layers.all().delete()
            for el_key, layer_list in (("wall", wl), ("roof", rl), ("floor", fl)):
                for idx, (m_name, thick_mm) in enumerate(layer_list, start=1):
                    AssemblyLayer.objects.create(
                        design=design,
                        element=el_key,
                        order=idx,
                        material=mat_objs[m_name],
                        thickness_mm=thick_mm,
                    )
            _execute_and_save_simulation(design)

        self.stdout.write(
            self.style.SUCCESS("Seeded demo account (username: demo / password: demo1234) with 5 sample designs.")
        )
