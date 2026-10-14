import argparse
import shutil
from pathlib import Path


STATIC_LINKS = {
    "{{ url_for('static', filename='style.css') }}": "/static/style.css",
    "{{ url_for('static', filename='rules.js') }}": "/static/rules.js",
    "{{ url_for('static', filename='script.js') }}": "/static/script.js",
}


def build_assets(project_root, output_dir):
    project_root = Path(project_root)
    output_dir = Path(output_dir)
    html = (project_root / "templates" / "index.html").read_text(encoding="utf-8")
    for template_link, asset_link in STATIC_LINKS.items():
        html = html.replace(template_link, asset_link)
    if "{{" in html or "}}" in html:
        raise ValueError("The frontend template contains an unhandled Jinja expression.")

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "index.html").write_text(html, encoding="utf-8", newline="\n")
    shutil.copytree(
        project_root / "static",
        output_dir / "static",
        dirs_exist_ok=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Build Cloudflare Workers Static Assets from the existing frontend."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "public",
        help="Output directory (defaults to the project's public directory).",
    )
    arguments = parser.parse_args()
    build_assets(Path(__file__).resolve().parents[1], arguments.output)
