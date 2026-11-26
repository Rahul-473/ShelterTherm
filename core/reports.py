import csv
import io
from django.http import HttpResponse
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def generate_csv_response(design, result):
    """Return an HttpResponse containing the 10-minute time-series CSV."""
    safe_name = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in design.name)
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="sheltertherm_{safe_name}.csv"'

    writer = csv.writer(response)
    writer.writerow(["ShelterTherm 24-Hour Thermal Simulation Export"])
    writer.writerow(["Design", design.name, "Location", str(design.location), "Verdict", result.verdict])
    writer.writerow([
        "Hour of Day",
        "Outdoor Temp (C)",
        "Indoor Temp (C)",
        "Comfort Low (C)",
        "Comfort High (C)",
        "Cooling Load (W)",
        "Heating Load (W)",
    ])

    ts = result.time_series or {}
    hours = ts.get("hours", [])
    t_out = ts.get("t_out", [])
    t_in = ts.get("t_in", [])
    cool = ts.get("cooling_w", [])
    heat = ts.get("heating_w", [])

    for h, to, ti, cw, hw in zip(hours, t_out, t_in, cool, heat):
        writer.writerow([h, to, ti, result.comfort_low, result.comfort_high, cw, hw])

    return response


def generate_pdf_response(design, result):
    """Return an HttpResponse containing a formatted ReportLab PDF summary."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=1.8 * cm,
        leftMargin=1.8 * cm,
        topMargin=1.8 * cm,
        bottomMargin=1.8 * cm,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "STTitle", parent=styles["Heading1"], fontSize=16, textColor=colors.HexColor("#1b365d")
    )
    h2_style = ParagraphStyle(
        "STH2", parent=styles["Heading2"], fontSize=12, textColor=colors.HexColor("#1b365d"), spaceBefore=10
    )
    body = styles["BodyText"]
    small_italic = ParagraphStyle(
        "STDisclaimer", parent=styles["BodyText"], fontSize=8.5, textColor=colors.HexColor("#555555")
    )

    story = []
    story.append(Paragraph(f"ShelterTherm Thermal Comfort Report: {design.name}", title_style))
    story.append(Paragraph(
        f"<b>Location:</b> {design.location} &nbsp;|&nbsp; "
        f"<b>Verdict:</b> {result.verdict} &nbsp;|&nbsp; "
        f"<b>Simulated:</b> {result.simulated_at.strftime('%d %b %Y %H:%M')}",
        body,
    ))
    story.append(Spacer(1, 0.3 * cm))

    # Key Results Table
    story.append(Paragraph("1. Thermal Comfort & Load Summary", h2_style))
    clim = design.effective_climate()
    summary_data = [
        ["Metric", "Value", "Metric", "Value"],
        ["Verdict", result.verdict, "Outdoor Range", f"{clim['t_min']:.1f} – {clim['t_max']:.1f} °C"],
        ["Peak Indoor Temp", f"{result.t_in_max:.1f} °C (at {result.peak_hour:.1f} h)", "Min / Avg Indoor", f"{result.t_in_min:.1f} / {result.t_in_avg:.1f} °C"],
        ["Comfort Band", f"{result.comfort_low:.1f} – {result.comfort_high:.1f} °C", "Comfortable Hours", f"{result.comfortable_hours:.1f} / 24 h"],
        ["Overheating Score", f"{result.overheating_dh:.1f} deg-hr", "Overcooling Score", f"{result.overcooling_dh:.1f} deg-hr"],
        ["Peak Cooling Needed", f"{result.peak_cooling_w:.0f} W", "Daily Cooling Energy", f"{result.daily_cooling_kwh:.2f} kWh"],
        ["Peak Heating Needed", f"{result.peak_heating_w:.0f} W", "Daily Heating Energy", f"{result.daily_heating_kwh:.2f} kWh"],
    ]
    t1 = Table(summary_data, colWidths=[4.2 * cm, 4.5 * cm, 4.2 * cm, 4.5 * cm])
    t1.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1b365d")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f7fa")]),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("PADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(t1)

    # Envelope & U-Values
    story.append(Paragraph("2. Shelter Geometry & Envelope U-Values", h2_style))
    geo_data = [
        ["Dimensions (L x W x H)", f"{design.length_m} m x {design.width_m} m x {design.height_m} m"],
        ["Windows (N / S / E / W)", f"{design.window_n_m2} / {design.window_s_m2} / {design.window_e_m2} / {design.window_w_m2} m² (SHGC {design.window_shgc})"],
        ["Ventilation (Day / Night)", f"{design.day_ach} ACH / {design.night_ach} ACH"],
        ["Occupants & Equipment", f"{design.occupants} people, {design.equipment_w:.0f} W"],
        ["Wall / Roof / Floor U-values", f"{result.u_wall:.2f} / {result.u_roof:.2f} / {result.u_floor:.2f} W/(m²·K)"],
        ["Cool Roof White Finish", "Yes" if design.cool_roof_finish else "No"],
    ]
    t2 = Table(geo_data, colWidths=[6.0 * cm, 11.4 * cm])
    t2.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f0f4f8")),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("PADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(t2)

    # Assembly Layers
    story.append(Paragraph("3. Material Layers (Outside to Inside)", h2_style))
    layer_rows = [["Element", "Order", "Material", "Thickness (mm)", "k (W/m·K)"]]
    for lyr in design.layers.select_related("material").all():
        layer_rows.append([
            lyr.get_element_display(),
            str(lyr.order),
            lyr.material.name,
            f"{lyr.thickness_mm:.1f}",
            f"{lyr.material.conductivity:.3f}",
        ])
    t3 = Table(layer_rows, colWidths=[2.8 * cm, 1.8 * cm, 7.3 * cm, 3.0 * cm, 2.5 * cm])
    t3.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c5282")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("PADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(t3)

    # Suggestions
    story.append(Paragraph("4. Design Improvement Suggestions", h2_style))
    for s in (result.suggestions or []):
        story.append(Paragraph(f"• {s}", body))

    # Disclaimer (mandatory per SRS 3.9)
    story.append(Spacer(1, 0.5 * cm))
    story.append(Paragraph(
        "<b>Disclaimer:</b> These results are early-stage engineering estimates produced by a simplified "
        "1D single-zone design-day thermal model (ShelterTherm). Humidity, detailed CFD airflow, structural "
        "loads, and full-year weather variations are not modelled. This report is not a certified building "
        "energy calculation.",
        small_italic,
    ))

    doc.build(story)
    buffer.seek(0)
    safe_name = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in design.name)
    response = HttpResponse(buffer.read(), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="sheltertherm_{safe_name}.pdf"'
    return response
