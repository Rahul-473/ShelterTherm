from django.contrib.auth.models import User
from django.db.models import ProtectedError
from django.test import TestCase
from django.urls import reverse

from .models import AssemblyLayer, ClimateLocation, Material, ShelterDesign
from .simulation.engine import (
    ClimateSpec,
    LayerSpec,
    R_SE,
    R_SI_WALL,
    ShelterSpec,
    compute_assembly_u_value,
    run_simulation,
)


class ThermalEngineTests(TestCase):
    def test_plastered_brick_wall_u_value(self):
        """Verify 230 mm brick + 12 mm plaster on both sides matches hand calc (~2.05 W/m^2K)."""
        plaster = LayerSpec("Cement plaster", 0.012, 0.72, 1860, 840, 0.60)
        brick = LayerSpec("Burnt clay brick", 0.230, 0.81, 1800, 880, 0.70)
        u = compute_assembly_u_value([plaster, brick, plaster], R_SE, R_SI_WALL)
        self.assertAlmostEqual(u, 2.052, places=2)

    def test_gi_sheet_overheats_more_than_insulated_aac(self):
        climate = ClimateSpec("Hot Day", t_max=40.0, t_min=26.0, peak_solar=950.0, wind_speed=2.5, ground_temp=28.0)
        gi = LayerSpec("GI sheet", 0.001, 45.0, 7800, 480, 0.65)
        rcc = LayerSpec("RCC", 0.120, 1.63, 2400, 880, 0.65)
        aac = LayerSpec("AAC", 0.200, 0.16, 600, 1050, 0.60)
        eps = LayerSpec("EPS", 0.050, 0.035, 20, 1400, 0.60)

        tin_shelter = ShelterSpec(
            name="GI", length_m=4, width_m=3, height_m=2.7,
            window_n_m2=0.5, window_s_m2=0.5, window_e_m2=0.5, window_w_m2=0.5,
            door_area_m2=1.8, window_shgc=0.7, day_ach=2, night_ach=2,
            occupants=3, equipment_w=100, comfort_model="imac", cool_roof_finish=False,
            wall_layers=[gi], roof_layers=[gi], floor_layers=[rcc],
        )
        cool_shelter = ShelterSpec(
            name="AAC+Cool", length_m=4, width_m=3, height_m=2.7,
            window_n_m2=0.5, window_s_m2=0.5, window_e_m2=0.5, window_w_m2=0.5,
            door_area_m2=1.8, window_shgc=0.25, day_ach=1, night_ach=12,
            occupants=3, equipment_w=100, comfort_model="imac", cool_roof_finish=True,
            wall_layers=[aac], roof_layers=[eps, rcc], floor_layers=[rcc],
        )
        res_tin = run_simulation(tin_shelter, climate)
        res_cool = run_simulation(cool_shelter, climate)
        self.assertGreater(res_tin["summary"]["t_in_max"], res_cool["summary"]["t_in_max"] + 8.0)
        self.assertGreater(res_tin["summary"]["overheating_dh"], res_cool["summary"]["overheating_dh"])


class ShelterThermWebTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="tester", password="password123")
        self.mat = Material.objects.create(
            name="Test Brick", category="masonry", conductivity=0.81,
            density=1800, specific_heat=880, absorptance=0.7,
        )
        self.loc = ClimateLocation.objects.create(
            name="Test City", state="Punjab", climate_zone="Composite",
            t_max=40, t_min=26, peak_solar=900, wind_speed=2.0, ground_temp=27,
        )

    def test_public_pages_load(self):
        for url_name in ("home", "material_list", "location_list", "help"):
            resp = self.client.get(reverse(url_name))
            self.assertEqual(resp.status_code, 200)

    def test_material_in_use_cannot_be_deleted(self):
        design = ShelterDesign.objects.create(user=self.user, name="D1", location=self.loc)
        AssemblyLayer.objects.create(design=design, element="wall", order=1, material=self.mat, thickness_mm=230)
        with self.assertRaises(ProtectedError):
            self.mat.delete()
