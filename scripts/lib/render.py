import argparse
import json
import sys
from pathlib import Path

try:
    import jinja2
except ImportError:
    print("jinja2 required: pip install jinja2", file=sys.stderr)
    sys.exit(1)


def collect_raw(run_dir: Path) -> dict:
    raw_dir = run_dir / "raw"
    experiments = {}
    for p in sorted(raw_dir.glob("ab_*.json")):
        name = p.stem[len("ab_"):]
        experiments[name] = {"ab": json.loads(p.read_text(encoding="utf-8"))}
    for p in sorted(raw_dir.glob("seo_*.json")):
        name = p.stem[len("seo_"):]
        experiments.setdefault(name, {})["seo"] = json.loads(p.read_text(encoding="utf-8"))
    for p in sorted(raw_dir.glob("deal_*.json")):
        name = p.stem[len("deal_"):]
        experiments.setdefault(name, {})["deal"] = json.loads(p.read_text(encoding="utf-8"))
    return experiments


def render(run_dir: Path, out_path: Path) -> None:
    plugin_root = Path(__file__).resolve().parent.parent.parent
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(plugin_root / "templates")),
        autoescape=jinja2.select_autoescape(["html"]),
        keep_trailing_newline=True,
    )
    template = env.get_template("report.html.j2")
    experiments = collect_raw(run_dir)
    payload = json.dumps(experiments, sort_keys=True, separators=(",", ":"))
    html = template.render(experiments=experiments, payload_json=payload)
    out_path.write_text(html, encoding="utf-8", newline="\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    render(Path(args.run_dir), Path(args.out))


if __name__ == "__main__":
    main()
