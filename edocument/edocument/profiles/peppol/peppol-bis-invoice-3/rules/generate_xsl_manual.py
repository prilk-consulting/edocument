#!/usr/bin/env python3
"""
Manual XSL generation from PEPPOL schematron files using saxonche.
Run this script in the rules directory to generate XSL files.
"""

import os
import urllib.request
import zipfile
from pathlib import Path

# Download schxslt pipeline
pipeline_dir = Path("pipeline")
if not pipeline_dir.exists():
    pipeline_dir.mkdir()
    print("Downloading schxslt pipeline...")

    zip_path = pipeline_dir / "schxslt-pipeline.zip"
    url = "https://github.com/schxslt/schxslt/releases/download/v1.10.1/schxslt-1.10.1-xslt-only.zip"

    with urllib.request.urlopen(url) as response:
        with open(zip_path, 'wb') as f:
            f.write(response.read())

    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(pipeline_dir)

pipeline_file = pipeline_dir / "schxslt-1.10.1" / "2.0" / "pipeline-for-svrl.xsl"
print(f"Pipeline file: {pipeline_file}")

# Schematron files to compile
SCHEMATRON_FILES = [
    "sch/CEN-EN16931-UBL.sch",
    "sch/PEPPOL-EN16931-UBL.sch",
    "sch/CEN-EN16931-CII.sch",
    "sch/PEPPOL-EN16931-CII.sch",
]

SCHEMATRON_PIPELINE = str(pipeline_file)

print("Starting XSL generation...")
print(f"Pipeline: {SCHEMATRON_PIPELINE}")

try:
    from saxonche import PySaxonProcessor

    with PySaxonProcessor(license=False) as proc:
        xslt30_processor = proc.new_xslt30_processor()
        xslt30_processor.set_cwd(".")

        for sch_file in SCHEMATRON_FILES:
            xsl_file = sch_file[:-4] + ".xsl"  # Remove .sch and add .xsl
            print(f"Converting {sch_file} -> {xsl_file}")

            xslt30_processor.transform_to_file(
                source_file=sch_file,
                stylesheet_file=SCHEMATRON_PIPELINE,
                output_file=xsl_file
            )

            if os.path.exists(xsl_file):
                size = os.path.getsize(xsl_file)
                print(f"✅ Generated {xsl_file} ({size} bytes)")
            else:
                print(f"❌ Failed to generate {xsl_file}")

    # Create combined UBL validation
    print("\nCreating combined CEN+PEPPOL UBL schematron...")

    with open("sch/CEN-EN16931-UBL.sch", 'r') as f:
        cen_content = f.read()

    with open("sch/PEPPOL-EN16931-UBL.sch", 'r') as f:
        peppol_content = f.read()

    # Simple combination
    peppol_lines = peppol_content.split('\n')
    peppol_start = next((i for i, line in enumerate(peppol_lines) if '<schema' in line), 1)
    peppol_extensions = '\n'.join(peppol_lines[peppol_start + 1:]).replace('</schema>', '')

    combined_content = cen_content.replace('</schema>', f'\n<!-- PEPPOL Extensions -->\n{peppol_extensions}\n</schema>')

    with open("PEPPOL-combined-UBL.sch", 'w') as f:
        f.write(combined_content)

    print("Converting combined schematron to XSL...")
    with PySaxonProcessor(license=False) as proc:
        xslt30_processor = proc.new_xslt30_processor()
        xslt30_processor.set_cwd(".")

        xslt30_processor.transform_to_file(
            source_file="PEPPOL-combined-UBL.sch",
            stylesheet_file=SCHEMATRON_PIPELINE,
            output_file="PEPPOL-UBL-validation.xsl"
        )

        if os.path.exists("PEPPOL-UBL-validation.xsl"):
            size = os.path.getsize("PEPPOL-UBL-validation.xsl")
            print(f"✅ Generated PEPPOL-UBL-validation.xsl ({size} bytes)")
        else:
            print("❌ Failed to generate PEPPOL-UBL-validation.xsl")

    print("XSL generation completed!")

except ImportError as e:
    print(f"❌ Import error: {e}")
    print("Make sure saxonche and schxslt are installed:")
    print("pip install saxonche schxslt")
except Exception as e:
    print(f"❌ Error: {e}")
