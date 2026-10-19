"""Download the Docling weights used by PDF conversion.

The backend image runs this during the build and points
`DOCLING_ARTIFACTS_PATH` at the result, so the first upload does not fetch
models. Local development can run `python -m backend.download_models` or let
Docling download them on the first PDF.
"""

import os
from pathlib import Path


def main() -> None:
    output = Path(os.environ.get("DOCLING_ARTIFACTS_PATH", "/opt/docling/models"))
    output.mkdir(parents=True, exist_ok=True)
    from docling.utils.model_downloader import download_models

    # The PDF pipeline loads layout and table weights. OCR and the optional
    # picture and formula models stay off, so those checkpoints are skipped.
    download_models(
        output_dir=output,
        progress=True,
        with_layout=True,
        with_tableformer=True,
        with_code_formula=False,
        with_picture_classifier=False,
        with_rapidocr=False,
    )
    print(f"Docling models saved under {output}")


if __name__ == "__main__":
    main()
