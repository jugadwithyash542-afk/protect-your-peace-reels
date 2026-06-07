# PAST: There was no automated script to render PDF pages to PNG. The PNG page previews in Doc/rendered_premium_guide/ were generated manually or by a previous untracked workflow.
# ISSUE: When the DOCX is updated and recompiled to PDF, the PNG previews in Doc/rendered_premium_guide/ become stale and out of sync with the new page count and layout.
# PRESENT: A Python script that uses pdftoppm to render the PDF pages as PNG images and automatically renames them to remove zero-padding (matching the app's expectation of page-1.png, page-2.png, etc.).
# RATIONALE: This ensures the web application preview images are completely up to date with the latest PDF layout and page count automatically.

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PDF_PATH = ROOT / "Doc" / "protect_your_peace_premium_guide_19_99_value.pdf"
RENDER_DIR = ROOT / "Doc" / "rendered_premium_guide"

def main():
    # 1. Clean the render directory of old PNGs
    if RENDER_DIR.exists():
        for f in RENDER_DIR.glob("page-*.png"):
            f.unlink()
    else:
        RENDER_DIR.mkdir(parents=True, exist_ok=True)

    # 2. Run pdftoppm to generate PNGs
    # By default, pdftoppm adds leading zeros to page numbers (e.g., page-01.png)
    cmd = [
        "pdftoppm",
        "-png",
        "-r", "150",
        str(PDF_PATH),
        str(RENDER_DIR / "page")
    ]
    print(f"Running: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)

    # 3. Rename zero-padded files to unpadded format (page-01.png -> page-1.png)
    for path in RENDER_DIR.glob("page-*.png"):
        name = path.name
        # Match page-01.png, page-02.png etc.
        # But do not match page-10.png, page-11.png
        # Let's extract the page number
        parts = name.split("-")
        if len(parts) == 2:
            num_part = parts[1].replace(".png", "")
            # Convert to int and format back to remove leading zeros
            try:
                page_num = int(num_part)
                new_name = f"page-{page_num}.png"
                new_path = path.with_name(new_name)
                if path != new_path:
                    path.rename(new_path)
            except ValueError:
                pass

    print("Successfully rendered and renamed PDF pages to unpadded PNG previews!")

if __name__ == "__main__":
    main()
