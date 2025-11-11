thonimport argparse
import json
import logging
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional

from extractors.google_play_parser import GooglePlayParser
from extractors.data_cleaner import normalize_app_data
from outputs.exporter import export_to_json, export_to_csv

def configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )

def load_settings(config_path: Path) -> Dict[str, Any]:
    """
    Load settings from JSON file, falling back to sensible defaults.
    """
    defaults: Dict[str, Any] = {
        "locale": "en",
        "country": "us",
        "timeout": 15,
        "output": {
            "directory": "data",
            "json_filename": "sample_output.json",
            "csv_filename": "sample_output.csv",
        },
    }

    if not config_path.is_file():
        logging.info("Config file %s not found, using built-in defaults", config_path)
        return defaults

    try:
        with config_path.open("r", encoding="utf-8") as f:
            user_settings = json.load(f)
        # Deep-merge user settings into defaults
        for key, value in user_settings.items():
            if (
                isinstance(value, dict)
                and key in defaults
                and isinstance(defaults[key], dict)
            ):
                defaults[key].update(value)
            else:
                defaults[key] = value
        logging.debug("Loaded settings: %s", defaults)
    except Exception as exc:
        logging.warning("Failed to load config %s: %s. Using defaults.", config_path, exc)

    return defaults

def load_app_ids(input_file: Path) -> List[str]:
    if not input_file.is_file():
        raise FileNotFoundError(f"Input file not found: {input_file}")

    app_ids: List[str] = []
    with input_file.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            app_ids.append(line)

    if not app_ids:
        raise ValueError(f"No app IDs found in {input_file}")

    return app_ids

def resolve_project_root() -> Path:
    # src/main.py -> src -> project root
    return Path(__file__).resolve().parents[1]

def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Google Play Data Extractor - scrape metadata for given app IDs."
    )
    parser.add_argument(
        "--input-file",
        type=str,
        help="Path to file containing Google Play app IDs (one per line). "
        "Defaults to data/sample_inputs.txt under the project root.",
    )
    parser.add_argument(
        "--config",
        type=str,
        help="Path to configuration JSON. Defaults to src/config/settings.example.json.",
    )
    parser.add_argument(
        "--output-json",
        type=str,
        help="Path to JSON output file. Overrides config file value if provided.",
    )
    parser.add_argument(
        "--output-csv",
        type=str,
        help="Path to CSV output file. Overrides config file value if provided.",
    )
    parser.add_argument(
        "--locale",
        type=str,
        help="Locale (hl) to use for Google Play, e.g., en, fr. Overrides config.",
    )
    parser.add_argument(
        "--country",
        type=str,
        help="Country (gl) to use for Google Play, e.g., us, gb, de. Overrides config.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        help="HTTP request timeout in seconds. Overrides config.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging.",
    )
    return parser.parse_args(argv)

def main(argv: Optional[List[str]] = None) -> None:
    args = parse_args(argv)
    configure_logging(args.verbose)

    project_root = resolve_project_root()

    # Resolve config path
    config_path = (
        Path(args.config)
        if args.config
        else project_root / "src" / "config" / "settings.example.json"
    )
    settings = load_settings(config_path)

    # Apply CLI overrides
    if args.locale:
        settings["locale"] = args.locale
    if args.country:
        settings["country"] = args.country
    if args.timeout:
        settings["timeout"] = args.timeout

    # Resolve input file path
    if args.input_file:
        input_path = Path(args.input_file)
        if not input_path.is_absolute():
            input_path = project_root / input_path
    else:
        input_path = project_root / "data" / "sample_inputs.txt"

    # Resolve output paths
    output_dir_setting = settings.get("output", {}).get("directory", "data")
    default_json_name = settings.get("output", {}).get(
        "json_filename", "sample_output.json"
    )
    default_csv_name = settings.get("output", {}).get(
        "csv_filename", "sample_output.csv"
    )

    if args.output_json:
        json_output_path = Path(args.output_json)
        if not json_output_path.is_absolute():
            json_output_path = project_root / json_output_path
    else:
        json_output_path = project_root / output_dir_setting / default_json_name

    if args.output_csv:
        csv_output_path = Path(args.output_csv)
        if not csv_output_path.is_absolute():
            csv_output_path = project_root / csv_output_path
    else:
        csv_output_path = project_root / output_dir_setting / default_csv_name

    try:
        app_ids = load_app_ids(input_path)
    except Exception as exc:
        logging.error("Failed to load app IDs: %s", exc)
        sys.exit(1)

    logging.info("Loaded %d app IDs from %s", len(app_ids), input_path)

    parser = GooglePlayParser(timeout=settings["timeout"])
    results: List[Dict[str, Any]] = []

    for app_id in app_ids:
        try:
            logging.info("Processing app ID: %s", app_id)
            raw_data = parser.get_app_data(
                app_id=app_id,
                locale=settings["locale"],
                country=settings["country"],
            )
            cleaned = normalize_app_data(raw_data)
            results.append(cleaned)
            logging.debug("Cleaned data for %s: %s", app_id, cleaned)
        except Exception as exc:
            logging.error("Failed to process app %s: %s", app_id, exc, exc_info=args.verbose)

    if not results:
        logging.error("No app data was successfully extracted. Exiting.")
        sys.exit(1)

    try:
        export_to_json(results, json_output_path)
        logging.info("JSON output written to %s", json_output_path)
    except Exception as exc:
        logging.error("Failed to write JSON output: %s", exc)

    try:
        export_to_csv(results, csv_output_path)
        logging.info("CSV output written to %s", csv_output_path)
    except Exception as exc:
        logging.error("Failed to write CSV output: %s", exc)

    logging.info("Completed processing %d apps.", len(results))

if __name__ == "__main__":
    main()