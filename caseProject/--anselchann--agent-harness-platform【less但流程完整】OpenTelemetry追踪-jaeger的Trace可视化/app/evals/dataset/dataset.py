"""
Dataset loader - loads evaluation datasets from JSON/YAML files.
"""

import json
from pathlib import Path
from app.schemas.evals import DatasetCase
def load_dataset(name: str, datasets_dir: str = "datasets") -> list[DatasetCase]:
    """Load a dataset by name from the datasets directory."""
    path = Path(datasets_dir) / f"{name}.json"
    if not path.exists():
        from app.exceptions import DatasetNotFoundError
        raise DatasetNotFoundError(name)

    with open(path) as f:
        raw = json.load(f)

    return [DatasetCase(**item) for item in raw]


def list_datasets(datasets_dir: str = "datasets") -> list[str]:
    """List available dataset names."""
    p = Path(datasets_dir)
    if not p.exists():
        return []
    return [f.stem for f in p.glob("*.json")]

