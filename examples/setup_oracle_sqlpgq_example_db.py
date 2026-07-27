"""
Create and populate the example Oracle SQL/PGQ graph used for corpus generation.

Required environment variables:
- ORACLE_DSN
- ORACLE_USER
- ORACLE_PASSWORD

Size can be controlled with CLI flags or matching environment variables, for example:

ORACLE_SQLPGQ_USERS=100 ORACLE_SQLPGQ_MOVIES=500 ORACLE_SQLPGQ_RATINGS=2000 \
  python examples/setup_oracle_sqlpgq_example_db.py
"""

import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta
import os
from pathlib import Path
import random
from typing import Any

from app.core.validator.db_client import QueryStatus
from app.impl.oracle_sqlpgq.db_client.oracle_db_client import OracleDBClient


GRAPH_NAME = "TEXT2GQL_GRAPH"
ARTIFACT_DIR = Path("examples/Oracle_SQLPGQ_Instance")
TABLE_DDL_PATH = ARTIFACT_DIR / "TEXT2GQL_GRAPH_oracle_tables.sql"
GRAPH_DDL_PATH = ARTIFACT_DIR / "TEXT2GQL_GRAPH_oracle_property_graph.sql"
Row = tuple[Any, ...]

TABLE_DROP_ORDER = [
    "USER_FRIENDS_WITH_USER",
    "MOVIE_SIMILAR_TO_MOVIE",
    "TAG_TAGS_MOVIE",
    "USER_TAGS_TAG",
    "MOVIE_BELONGS_TO_GENRE",
    "RATING_RATES_MOVIE",
    "USER_RATES_RATING",
    "TAG",
    "RATING",
    "GENRE",
    "MOVIE",
    "USER",
]

BASE_MOVIES = [
    ("Inception", 2010, 148, "A thief enters dreams to steal secrets.", "English"),
    ("The Matrix", 1999, 136, "A hacker discovers a simulated reality.", "English"),
    ("Arrival", 2016, 116, "A linguist communicates with alien visitors.", "English"),
    ("Spirited Away", 2001, 125, "A girl enters a world of spirits.", "Japanese"),
]
BASE_GENRES = [
    ("Science Fiction", "Speculative stories about science and technology"),
    ("Action", "Fast-paced stories with intense conflict"),
    ("Drama", "Character-driven serious stories"),
    ("Animation", "Animated feature films"),
    ("Comedy", "Humorous stories and situations"),
    ("Thriller", "Suspenseful stories with tension"),
    ("Fantasy", "Stories with magic or imaginary worlds"),
    ("Documentary", "Non-fiction film storytelling"),
    ("Romance", "Stories centered on relationships"),
    ("Horror", "Stories intended to frighten or unsettle"),
    ("Adventure", "Journeys, exploration, and discovery"),
]
BASE_TAGS = [
    "mind-bending",
    "classic",
    "time travel",
    "animated",
    "Sci-Fi",
    "action-packed",
    "thoughtful",
    "dystopian",
    "alien contact",
    "dream logic",
    "cyberpunk",
    "family",
    "award-winning",
    "cult favorite",
    "visual effects",
    "slow burn",
]


@dataclass(frozen=True)
class DataConfig:
    users: int
    movies: int
    genres: int
    tags: int
    ratings: int
    genre_edges: int
    tag_edges: int
    friend_edges: int
    similarity_edges: int
    seed: int
    batch_size: int


def env_int(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


def env_int_optional(name: str) -> int | None:
    value = os.getenv(name)
    return int(value) if value not in (None, "") else None


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return parsed


def parse_args() -> DataConfig:
    default_users = env_int("ORACLE_SQLPGQ_USERS", 4)
    default_movies = env_int("ORACLE_SQLPGQ_MOVIES", 4)
    default_genres = env_int("ORACLE_SQLPGQ_GENRES", 4)
    default_tags = env_int("ORACLE_SQLPGQ_TAGS", 6)
    default_ratings = env_int("ORACLE_SQLPGQ_RATINGS", 4)
    default_genre_edges = env_int_optional("ORACLE_SQLPGQ_GENRE_EDGES")
    default_tag_edges = env_int_optional("ORACLE_SQLPGQ_TAG_EDGES")

    parser = argparse.ArgumentParser()
    parser.add_argument("--users", type=positive_int, default=default_users)
    parser.add_argument("--movies", type=positive_int, default=default_movies)
    parser.add_argument("--genres", type=positive_int, default=default_genres)
    parser.add_argument("--tags", type=positive_int, default=default_tags)
    parser.add_argument("--ratings", type=positive_int, default=default_ratings)
    parser.add_argument(
        "--genre-edges",
        type=positive_int,
        default=default_genre_edges,
        help="MOVIE->GENRE BELONGS_TO edges; default is max(movies + 1, 5)",
    )
    parser.add_argument(
        "--tag-edges",
        type=positive_int,
        default=default_tag_edges,
        help="USER->TAG and TAG->MOVIE edge pairs; default is max(tags, 6)",
    )
    parser.add_argument(
        "--friend-edges",
        type=positive_int,
        default=env_int("ORACLE_SQLPGQ_FRIEND_EDGES", 3),
    )
    parser.add_argument(
        "--similarity-edges",
        type=positive_int,
        default=env_int("ORACLE_SQLPGQ_SIMILARITY_EDGES", 3),
    )
    parser.add_argument("--seed", type=int, default=env_int("ORACLE_SQLPGQ_DATA_SEED", 7))
    parser.add_argument(
        "--batch-size",
        type=positive_int,
        default=env_int("ORACLE_SQLPGQ_INSERT_BATCH_SIZE", 1000),
    )
    args = parser.parse_args()

    config = DataConfig(
        users=args.users,
        movies=args.movies,
        genres=args.genres,
        tags=args.tags,
        ratings=args.ratings,
        genre_edges=args.genre_edges or max(args.movies + 1, 5),
        tag_edges=args.tag_edges or max(args.tags, 6),
        friend_edges=args.friend_edges,
        similarity_edges=args.similarity_edges,
        seed=args.seed,
        batch_size=args.batch_size,
    )
    validate_config(config)
    return config


def validate_config(config: DataConfig) -> None:
    minimums = {
        "users": 4,
        "movies": 4,
        "genres": 4,
        "tags": 6,
        "ratings": 4,
        "genre_edges": 5,
        "tag_edges": 6,
        "friend_edges": 3,
        "similarity_edges": 3,
    }
    values = config.__dict__
    too_small = [
        f"{name}>={minimum} (got {values[name]})"
        for name, minimum in minimums.items()
        if values[name] < minimum
    ]
    if too_small:
        raise ValueError(
            "The example corpus seed queries require these minimum sizes: "
            + ", ".join(too_small)
        )


def timestamp(month: int, day_offset: int, hour: int = 9) -> datetime:
    return datetime(2025, month, 1, hour, 0, 0) + timedelta(days=day_offset)


def safe_execute(client: OracleDBClient, sql: str, ignore_errors: tuple[str, ...] = ()) -> None:
    result = client.execute_query(sql)
    if result.status_code == QueryStatus.SUCCESS:
        return
    if result.error and any(token in result.error for token in ignore_errors):
        return
    raise RuntimeError(f"Failed SQL:\n{sql}\n\nError:\n{result.error}")


def reset_objects(client: OracleDBClient) -> None:
    safe_execute(
        client,
        f'DROP PROPERTY GRAPH "{GRAPH_NAME}"',
        ignore_errors=("ORA-42421", "ORA-04043", "ORA-00942"),
    )
    for table_name in TABLE_DROP_ORDER:
        safe_execute(
            client,
            f'DROP TABLE "{table_name}" CASCADE CONSTRAINTS PURGE',
            ignore_errors=("ORA-00942",),
        )


def run_script(client: OracleDBClient, script_path: Path) -> None:
    for result in client.execute_script(script_path.read_text(encoding="utf-8")):
        if result.status_code != QueryStatus.SUCCESS:
            raise RuntimeError(f"Failed script {script_path}: {result.error}")


def insert_rows(
    client: OracleDBClient,
    statement: str,
    rows: list[Row],
    label: str,
    batch_size: int,
) -> None:
    for start in range(0, len(rows), batch_size):
        result = client.executemany(statement, rows[start : start + batch_size])
        if result.status_code != QueryStatus.SUCCESS:
            raise RuntimeError(f"Failed loading {label}: {result.error}")
    print(f"Loaded {len(rows)} rows into {label}")


def generate_users(config: DataConfig) -> list[Row]:
    base = [
        (1, 34, "F", "data scientist", "10001", datetime(2024, 1, 10, 9, 0, 0)),
        (2, 41, "M", "teacher", "94105", datetime(2024, 2, 12, 12, 30, 0)),
        (3, 28, "F", "designer", "60601", datetime(2024, 3, 3, 16, 45, 0)),
        (4, 52, "M", "Engineer", "02139", datetime(2024, 4, 22, 8, 15, 0)),
    ]
    occupations = ["analyst", "writer", "doctor", "artist", "developer", "researcher"]
    rows = base[: config.users]
    for user_id in range(len(rows) + 1, config.users + 1):
        rows.append(
            (
                user_id,
                18 + (user_id * 7) % 55,
                "F" if user_id % 2 else "M",
                occupations[user_id % len(occupations)],
                f"{10000 + user_id:05d}",
                datetime(2024, 1, 1, 8, 0, 0) + timedelta(days=user_id),
            )
        )
    return rows


def generate_movies(config: DataConfig) -> list[Row]:
    adjectives = ["Hidden", "Silent", "Neon", "Lost", "Quantum", "Midnight", "Parallel"]
    nouns = ["Signal", "Journey", "Archive", "Horizon", "City", "Memory", "Protocol"]
    rows = [
        (10 + index, title, year, duration, summary, language)
        for index, (title, year, duration, summary, language) in enumerate(BASE_MOVIES)
    ][: config.movies]
    for index in range(len(rows), config.movies):
        title = f"{adjectives[index % len(adjectives)]} {nouns[index % len(nouns)]} {index + 1}"
        rows.append(
            (
                10 + index,
                title,
                1980 + (index * 3) % 45,
                85 + (index * 11) % 70,
                f"Synthetic plot summary for {title}.",
                "English" if index % 5 else "Spanish",
            )
        )
    return rows


def generate_genres(config: DataConfig) -> list[Row]:
    rows = [
        (20 + index, name, description)
        for index, (name, description) in enumerate(BASE_GENRES)
    ][: config.genres]
    for index in range(len(rows), config.genres):
        rows.append((20 + index, f"Genre {index + 1}", "Synthetic generated genre"))
    return rows


def generate_tags(config: DataConfig) -> list[Row]:
    rows = [
        (200 + index, tag, timestamp(2, index), round(0.96 - index * 0.01, 3))
        for index, tag in enumerate(BASE_TAGS)
    ][: config.tags]
    for index in range(len(rows), config.tags):
        rows.append((200 + index, f"tag-{index + 1}", timestamp(2, index), 0.5))
    return rows


def generate_ratings(config: DataConfig) -> tuple[list[Row], list[Row], list[Row]]:
    score_cycle = [4.8, 4.6, 4.4, 4.9, 3.9, 4.2, 4.7, 3.5, 4.1, 4.0]
    review_cycle = [
        "Inventive and visually impressive",
        "A defining cyberpunk classic",
        "Quiet and thoughtful science fiction",
        "Beautiful and imaginative",
        "Good pacing and strong performances",
    ]
    ratings = []
    user_rating_edges = []
    rating_movie_edges = []
    for index in range(config.ratings):
        rating_id = 100 + index
        user_id = 1 + index % config.users
        movie_id = 10 + index % config.movies
        score = score_cycle[index % len(score_cycle)]
        rated_at = timestamp(1, index, hour=10 + index % 10)
        ratings.append((rating_id, score, rated_at, review_cycle[index % len(review_cycle)]))
        user_rating_edges.append(
            (user_id, rating_id, rated_at, score, round(0.75 + (index % 20) / 100, 3))
        )
        rating_movie_edges.append(
            (rating_id, movie_id, rated_at, score, round(0.75 + (index % 20) / 100, 3))
        )
    return ratings, user_rating_edges, rating_movie_edges


def generate_genre_edges(config: DataConfig, rng: random.Random) -> list[Row]:
    rows = [
        (10, 20, 1, 0.99),
        (11, 20, 1, 0.94),
        (11, 21, 0, 0.88),
        (12, 22, 1, 0.91),
        (13, 23, 1, 0.99),
    ]
    for _ in range(len(rows), config.genre_edges):
        rows.append(
            (
                10 + rng.randrange(config.movies),
                20 + rng.randrange(config.genres),
                1 if rng.random() > 0.35 else 0,
                round(0.55 + rng.random() * 0.44, 3),
            )
        )
    return rows


def generate_tag_edges(config: DataConfig, rng: random.Random) -> tuple[list[Row], list[Row]]:
    base = [
        (1, 200, 10),
        (2, 201, 11),
        (3, 202, 12),
        (4, 203, 13),
        (1, 204, 11),
        (2, 205, 11),
    ]
    user_tag_edges = []
    tag_movie_edges = []
    for index in range(config.tag_edges):
        if index < len(base):
            user_id, tag_id, movie_id = base[index]
        else:
            user_id = 1 + rng.randrange(config.users)
            tag_id = 200 + rng.randrange(config.tags)
            movie_id = 10 + rng.randrange(config.movies)
        tagged_at = timestamp(2, index, hour=9 + index % 8)
        confidence = round(0.6 + rng.random() * 0.39, 3)
        visibility = 1 if rng.random() > 0.2 else 0
        user_tag_edges.append((user_id, tag_id, tagged_at, confidence, visibility))
        tag_movie_edges.append((tag_id, movie_id, tagged_at, confidence, visibility))
    return user_tag_edges, tag_movie_edges


def generate_similarity_edges(config: DataConfig, rng: random.Random) -> list[Row]:
    rows = [
        (10, 11, 0.87, "v1", timestamp(3, 0, hour=0)),
        (10, 12, 0.76, "v1", timestamp(3, 0, hour=0)),
        (11, 10, 0.87, "v1", timestamp(3, 0, hour=0)),
    ]
    for index in range(len(rows), config.similarity_edges):
        src = 10 + rng.randrange(config.movies)
        dst = 10 + rng.randrange(config.movies)
        if config.movies > 1:
            while dst == src:
                dst = 10 + rng.randrange(config.movies)
        rows.append((src, dst, round(0.45 + rng.random() * 0.5, 3), "v1", timestamp(3, index)))
    return rows


def generate_friend_edges(config: DataConfig, rng: random.Random) -> list[Row]:
    rows = [
        (1, 2, 0.72, 3, timestamp(3, 9, hour=18)),
        (2, 3, 0.64, 2, timestamp(3, 10, hour=18)),
        (3, 4, 0.68, 4, timestamp(3, 11, hour=18)),
    ]
    for index in range(len(rows), config.friend_edges):
        src = 1 + rng.randrange(config.users)
        dst = 1 + rng.randrange(config.users)
        if config.users > 1:
            while dst == src:
                dst = 1 + rng.randrange(config.users)
        rows.append(
            (
                src,
                dst,
                round(0.3 + rng.random() * 0.69, 3),
                1 + rng.randrange(8),
                timestamp(3, 12 + index, hour=18),
            )
        )
    return rows


def load_data(client: OracleDBClient, config: DataConfig) -> None:
    rng = random.Random(config.seed)
    users = generate_users(config)
    movies = generate_movies(config)
    genres = generate_genres(config)
    tags = generate_tags(config)
    ratings, user_rating_edges, rating_movie_edges = generate_ratings(config)
    genre_edges = generate_genre_edges(config, rng)
    user_tag_edges, tag_movie_edges = generate_tag_edges(config, rng)
    similarity_edges = generate_similarity_edges(config, rng)
    friend_edges = generate_friend_edges(config, rng)

    inserts: list[tuple[str, str, list[Row]]] = [
        (
            "USER",
            'INSERT INTO "USER" ("USER_id", "age", "gender", "occupation", "zip_code", "registration_date") VALUES (:1, :2, :3, :4, :5, :6)',
            users,
        ),
        (
            "MOVIE",
            'INSERT INTO "MOVIE" ("MOVIE_id", "title", "release_year", "duration", "plot_summary", "language") VALUES (:1, :2, :3, :4, :5, :6)',
            movies,
        ),
        (
            "GENRE",
            'INSERT INTO "GENRE" ("GENRE_id", "name", "description") VALUES (:1, :2, :3)',
            genres,
        ),
        (
            "RATING",
            'INSERT INTO "RATING" ("RATING_id", "score", "timestamp", "review_text") VALUES (:1, :2, :3, :4)',
            ratings,
        ),
        (
            "TAG",
            'INSERT INTO "TAG" ("TAG_id", "text_content", "timestamp", "relevance_score") VALUES (:1, :2, :3, :4)',
            tags,
        ),
        (
            "USER_RATES_RATING",
            'INSERT INTO "USER_RATES_RATING" ("SRC_ID", "DST_ID", "rating_timestamp", "rating_value", "confidence_weight") VALUES (:1, :2, :3, :4, :5)',
            user_rating_edges,
        ),
        (
            "RATING_RATES_MOVIE",
            'INSERT INTO "RATING_RATES_MOVIE" ("SRC_ID", "DST_ID", "rating_timestamp", "rating_value", "confidence_weight") VALUES (:1, :2, :3, :4, :5)',
            rating_movie_edges,
        ),
        (
            "MOVIE_BELONGS_TO_GENRE",
            'INSERT INTO "MOVIE_BELONGS_TO_GENRE" ("SRC_ID", "DST_ID", "primary_classification", "strength_score") VALUES (:1, :2, :3, :4)',
            genre_edges,
        ),
        (
            "USER_TAGS_TAG",
            'INSERT INTO "USER_TAGS_TAG" ("SRC_ID", "DST_ID", "tag_timestamp", "user_confidence", "public_visibility") VALUES (:1, :2, :3, :4, :5)',
            user_tag_edges,
        ),
        (
            "TAG_TAGS_MOVIE",
            'INSERT INTO "TAG_TAGS_MOVIE" ("SRC_ID", "DST_ID", "tag_timestamp", "user_confidence", "public_visibility") VALUES (:1, :2, :3, :4, :5)',
            tag_movie_edges,
        ),
        (
            "MOVIE_SIMILAR_TO_MOVIE",
            'INSERT INTO "MOVIE_SIMILAR_TO_MOVIE" ("SRC_ID", "DST_ID", "similarity_score", "algorithm_version", "update_timestamp") VALUES (:1, :2, :3, :4, :5)',
            similarity_edges,
        ),
        (
            "USER_FRIENDS_WITH_USER",
            'INSERT INTO "USER_FRIENDS_WITH_USER" ("SRC_ID", "DST_ID", "connection_strength", "mutual_interests_count", "last_interaction") VALUES (:1, :2, :3, :4, :5)',
            friend_edges,
        ),
    ]
    for label, statement, rows in inserts:
        insert_rows(client, statement, rows, label, config.batch_size)
    safe_execute(client, "COMMIT")


def print_config(config: DataConfig) -> None:
    print("Data size configuration:")
    for name, value in config.__dict__.items():
        print(f"  {name}: {value}")


def main() -> None:
    config = parse_args()
    client = OracleDBClient(
        {
            "dsn": os.environ["ORACLE_DSN"],
            "user": os.environ["ORACLE_USER"],
            "password": os.environ["ORACLE_PASSWORD"],
        }
    )
    if not client.connection:
        raise RuntimeError("Oracle connection failed.")

    try:
        print_config(config)
        print(f"Resetting Oracle objects for {GRAPH_NAME}")
        reset_objects(client)
        print("Creating Oracle tables")
        run_script(client, TABLE_DDL_PATH)
        print("Inserting generated sample rows")
        load_data(client, config)
        print("Creating Oracle SQL property graph")
        run_script(client, GRAPH_DDL_PATH)
        print(f"Ready: {GRAPH_NAME}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
