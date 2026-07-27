from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List


@dataclass(frozen=True)
class DatabaseUnit:
    split: str
    database: str
    root: Path
    query_path: Path
    import_config_path: Path
    csv_root: Path


def discover_database_units(dataset_root: Path, splits: Iterable[str]) -> List[DatabaseUnit]:
    units: List[DatabaseUnit] = []
    for split in splits:
        split_root = dataset_root / split
        if not split_root.exists():
            continue
        if split == "train":
            units.extend(_discover_train(split_root))
        else:
            units.extend(_discover_split_domains(split_root, split))
    return sorted(units, key=lambda item: (item.split, item.database, str(item.query_path)))


def _discover_train(split_root: Path) -> List[DatabaseUnit]:
    units: List[DatabaseUnit] = []
    for domain_root in split_root.iterdir():
        if not domain_root.is_dir():
            continue
        query_path = domain_root / "4_level_results_ek_results.json"
        config_paths = sorted((domain_root / "cypher").glob("*/import_config.json"))
        if query_path.exists() and config_paths:
            config_path = config_paths[0]
            units.append(
                DatabaseUnit(
                    split="train",
                    database=domain_root.name,
                    root=domain_root,
                    query_path=query_path,
                    import_config_path=config_path,
                    csv_root=config_path.parent,
                )
            )
    return units


def _discover_split_domains(split_root: Path, split: str) -> List[DatabaseUnit]:
    units: List[DatabaseUnit] = []
    for domain_root in split_root.iterdir():
        if not domain_root.is_dir():
            continue
        cypher_root = domain_root / "Cypher"
        if not cypher_root.exists():
            continue
        query_candidates = sorted(
            path for path in cypher_root.glob("*_cypher.json") if path.is_file()
        )
        config_candidates = sorted(cypher_root.glob("**/import_config.json"))
        if not query_candidates or not config_candidates:
            continue
        config_path = config_candidates[0]
        for query_path in query_candidates:
            units.append(
                DatabaseUnit(
                    split=split,
                    database=domain_root.name,
                    root=domain_root,
                    query_path=query_path,
                    import_config_path=config_path,
                    csv_root=config_path.parent,
                )
            )
    return units


def source_query(record: dict) -> tuple[str, str]:
    for key in ("initial_cypher", "cypher", "query", "initial_gql"):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return key, value
    return "", ""
