"""Create a synthetic technical catalog PDF for testing catalog2md."""
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
)

def create_test_catalog():
    doc = SimpleDocTemplate(
        "/home/user/workspace/catalog2md/test_catalog.pdf",
        pagesize=letter,
        title="AH-Series Air Handler Technical Catalog",
        author="Perplexity Computer",
    )
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'CatalogTitle', parent=styles['Title'], fontSize=24, spaceAfter=30
    )
    h1_style = ParagraphStyle(
        'H1', parent=styles['Heading1'], fontSize=18, spaceAfter=12, spaceBefore=20
    )
    h2_style = ParagraphStyle(
        'H2', parent=styles['Heading2'], fontSize=14, spaceAfter=8, spaceBefore=14
    )
    body_style = styles['Normal']
    
    story = []
    
    # === Page 1: Title and Overview ===
    story.append(Paragraph("AH-Series Air Handler Technical Catalog", title_style))
    story.append(Spacer(1, 20))
    story.append(Paragraph("Product Overview", h1_style))
    story.append(Paragraph(
        "The AH-Series air handlers are designed for commercial HVAC applications. "
        "Available in models AH-350, AH-500, AH-750, and AH-1000, these units provide "
        "reliable climate control for spaces ranging from 3,500 to 10,000 square feet. "
        "All models comply with ASHRAE Standard 62.1 and are ETL listed to UL 1995.",
        body_style,
    ))
    story.append(Spacer(1, 12))
    story.append(Paragraph("Key Features", h2_style))
    story.append(Paragraph(
        "High-efficiency ECM blower motors (part number MTR-ECM-350 through MTR-ECM-1000). "
        "Factory-installed filter racks accepting standard MERV-13 filters. "
        "Hot water or chilled water coil options (CW-series and HW-series). "
        "Insulated cabinet with thermal break construction. "
        "Integrated DDC controls with BACnet MS/TP protocol.",
        body_style,
    ))
    
    story.append(PageBreak())
    
    # === Page 2: Performance Data Table ===
    story.append(Paragraph("Performance Specifications", h1_style))
    story.append(Paragraph(
        "The following table provides rated performance data for all AH-Series models "
        "at standard air conditions (70F DB, 50% RH).",
        body_style,
    ))
    story.append(Spacer(1, 12))
    
    perf_data = [
        ["Model", "CFM", "External Static\nPressure (in. WG)", "Motor HP",
         "Sound Level\n(dBA)", "Weight\n(lbs)", "Part Number"],
        ["AH-350", "3,500", "0.5 - 2.0", "3.0", "65", "345", "AH-350-CW"],
        ["AH-500", "5,000", "0.5 - 2.5", "5.0", "68", "485", "AH-500-CW"],
        ["AH-750", "7,500", "0.5 - 3.0", "7.5", "72", "620", "AH-750-CW"],
        ["AH-1000", "10,000", "0.5 - 3.5", "10.0", "75", "810", "AH-1000-CW"],
    ]
    
    perf_table = Table(perf_data, colWidths=[70, 55, 100, 60, 70, 60, 90])
    perf_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#003366')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f0f0f0')]),
    ]))
    story.append(perf_table)
    
    story.append(PageBreak())
    
    # === Page 3: Dimensional Data ===
    story.append(Paragraph("Dimensional Data", h1_style))
    story.append(Paragraph(
        "All dimensions in inches unless otherwise noted. Refer to certified drawings "
        "for exact connection locations. Drawing package available as DWG-AH-SERIES-R3.",
        body_style,
    ))
    story.append(Spacer(1, 12))
    
    dim_data = [
        ["Model", "Length (in)", "Width (in)", "Height (in)",
         "Supply Duct\n(in)", "Return Duct\n(in)", "Drain\nConnection"],
        ["AH-350", "48", "30", "24", "16 x 12", "18 x 14", '3/4" FPT'],
        ["AH-500", "60", "36", "28", "20 x 14", "22 x 16", '3/4" FPT'],
        ["AH-750", "72", "42", "32", "24 x 16", "26 x 18", '1" FPT'],
        ["AH-1000", "84", "48", "36", "28 x 18", "30 x 20", '1" FPT'],
    ]
    
    dim_table = Table(dim_data, colWidths=[65, 65, 65, 65, 75, 75, 75])
    dim_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#003366')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f0f0f0')]),
    ]))
    story.append(dim_table)
    
    story.append(Spacer(1, 20))
    
    story.append(Paragraph("Coil Pressure and Temperature Ratings", h2_style))
    story.append(Paragraph(
        "Maximum operating conditions for factory-installed coils. "
        "Exceeding these ratings will void the warranty.",
        body_style,
    ))
    story.append(Spacer(1, 12))
    
    pt_data = [
        ["Coil Type", "Part Number", "Max Pressure\n(PSI)", "Max Temp\n(F)",
         "Connection\nSize", "GPM Rating"],
        ["Chilled Water", "CW-350-4R", "150", "200", '1"', "12"],
        ["Chilled Water", "CW-500-4R", "150", "200", '1-1/4"', "18"],
        ["Chilled Water", "CW-750-6R", "150", "200", '1-1/2"', "24"],
        ["Hot Water", "HW-350-2R", "200", "250", '3/4"', "8"],
        ["Hot Water", "HW-500-2R", "200", "250", '1"', "12"],
        ["Hot Water", "HW-750-4R", "200", "250", '1-1/4"', "16"],
        ["Steam", "STM-500-1R", "15", "250", '1"', "N/A"],
        ["Steam", "STM-750-1R", "15", "250", '1-1/4"', "N/A"],
    ]
    
    pt_table = Table(pt_data, colWidths=[80, 80, 75, 70, 75, 70])
    pt_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#003366')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f0f0f0')]),
    ]))
    story.append(pt_table)
    
    story.append(PageBreak())
    
    # === Page 4: Electrical Specifications ===
    story.append(Paragraph("Electrical Specifications", h1_style))
    story.append(Paragraph("Motor Data", h2_style))
    story.append(Paragraph(
        "All AH-Series units use premium efficiency ECM motors manufactured by "
        "Regal Rexnord (formerly Marathon). Replacement motors are available through "
        "authorized distributors using the part numbers listed below.",
        body_style,
    ))
    story.append(Spacer(1, 12))
    
    elec_data = [
        ["Part Number", "HP", "Voltage", "Phase", "FLA", "LRA", "RPM", "Frame"],
        ["MTR-ECM-350", "3.0", "208-230/460", "3", "8.4/4.2", "52/26", "1750", "182T"],
        ["MTR-ECM-500", "5.0", "208-230/460", "3", "13.6/6.8", "82/41", "1750", "184T"],
        ["MTR-ECM-750", "7.5", "208-230/460", "3", "20.0/10.0", "116/58", "1750", "213T"],
        ["MTR-ECM-1000", "10.0", "208-230/460", "3", "26.4/13.2", "145/72.5", "1750", "215T"],
    ]
    
    elec_table = Table(elec_data, colWidths=[85, 40, 80, 40, 60, 60, 45, 50])
    elec_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#003366')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f0f0f0')]),
    ]))
    story.append(elec_table)
    
    story.append(Spacer(1, 20))
    story.append(Paragraph("Control Wiring", h2_style))
    story.append(Paragraph(
        "All units ship with factory-installed DDC controller (part number CTL-DDC-AH). "
        "The controller accepts 24VAC Class 2 control signals and supports BACnet MS/TP "
        "communication over RS-485. Terminal designations follow ASHRAE Standard 135. "
        "Minimum wire gauge for control circuits is 18 AWG shielded twisted pair. "
        "Maximum run length from controller to BACnet router is 4,000 feet.",
        body_style,
    ))
    
    story.append(Spacer(1, 12))
    story.append(Paragraph("Ordering Guide", h1_style))
    story.append(Paragraph(
        "Build your model number using the following matrix. Example: "
        "AH-750-CW-460-L-BN = 7,500 CFM unit with chilled water coil, "
        "460V power, left-hand configuration, with BACnet.",
        body_style,
    ))
    story.append(Spacer(1, 12))
    
    order_data = [
        ["Position", "Code", "Description"],
        ["Series", "AH", "Air Handler"],
        ["Size", "350 / 500 / 750 / 1000", "Nominal CFM (x100)"],
        ["Coil", "CW / HW / STM / NC", "Chilled Water / Hot Water / Steam / No Coil"],
        ["Voltage", "208 / 230 / 460 / 575", "Supply Voltage"],
        ["Hand", "L / R", "Left or Right hand (facing supply)"],
        ["Controls", "BN / LN / MN / NC", "BACnet / LonWorks / Modbus / No Controls"],
    ]
    
    order_table = Table(order_data, colWidths=[70, 130, 250])
    order_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#003366')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f0f0f0')]),
    ]))
    story.append(order_table)
    
    doc.build(story)
    print("Test catalog created: test_catalog.pdf")

if __name__ == "__main__":
    create_test_catalog()
