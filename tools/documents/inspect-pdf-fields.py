#!/usr/bin/env python3

import sys
from pypdf import PdfReader

pdf_path = sys.argv[1] if len(sys.argv) > 1 else "templates/PDF Templates/LAA Notice of Issue -.pdf"

reader = PdfReader(pdf_path)

print(f"PDF: {pdf_path}")
print(f"Pages: {len(reader.pages)}")

if reader.get_fields():
    print("\nForm fields found:")
    for field_name, field_data in reader.get_fields().items():
        print(f"  - {field_name}: {field_data.get('/FT', 'Unknown type')}")
else:
    print("\nNo form fields found (static PDF)")

if "/AcroForm" in reader.trailer.get("/Root", {}):
    print("\nAcroForm dictionary: EXISTS")
else:
    print("\nAcroForm dictionary: NOT FOUND")
