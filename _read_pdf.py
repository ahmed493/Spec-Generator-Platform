import pdfplumber

pdf = pdfplumber.open(r"c:\Users\abettaieb\Downloads\Template spécification de flux.pdf")
for i, page in enumerate(pdf.pages):
    print(f"--- PAGE {i+1} ---")
    text = page.extract_text()
    print(text if text else "(empty)")
    
    # Also check for tables
    tables = page.extract_tables()
    if tables:
        for j, table in enumerate(tables):
            print(f"\n  [TABLE {j+1}]")
            for row in table:
                print(f"    {row}")
pdf.close()
