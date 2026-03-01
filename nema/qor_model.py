"""QoR dataset extraction and baseline cost-model fitting utilities."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path
from typing import Any

CSV_CORE_COLUMNS: tuple[str, ...] = (
    "N",
    "E",
    "qformat",
    "P_N",
    "P_S",
    "ii",
    "latency",
    "lut",
    "ff",
    "bram",
    "dsp",
)
CSV_METADATA_COLUMNS: tuple[str, ...] = (
    "benchmarkId",
    "seed",
    "modelId",
)
CSV_COLUMNS: tuple[str, ...] = CSV_CORE_COLUMNS + CSV_METADATA_COLUMNS

_MODEL_BENCH_RE = re.compile(r"(?:^|[_-])(B\d+)(?:[_-]|$)", re.IGNORECASE)
_SEED_RE = re.compile(r"(?:^|[_-])s(\d+)(?:[_-]|$)", re.IGNORECASE)


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if text and (text.isdigit() or (text.startswith("-") and text[1:].isdigit())):
            try:
                return int(text)
            except ValueError:
                return None
    return None


def _as_number(value: Any) -> int | float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.isdigit() or (text.startswith("-") and text[1:].isdigit()):
            try:
                return int(text)
            except ValueError:
                return None
        try:
            parsed = float(text)
        except ValueError:
            return None
        return int(parsed) if parsed.is_integer() else parsed
    return None


def _csv_value(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _parse_qformat(report: dict[str, Any]) -> str:
    config = report.get("config")
    if not isinstance(config, dict):
        return ""
    qformats = config.get("qformats")
    if isinstance(qformats, dict):
        for key in ("voltage", "stateTypeId", "activation", "accum"):
            value = qformats.get(key)
            if isinstance(value, str) and value:
                return value
    return ""


def _parse_benchmark_id(report: dict[str, Any], model_id: str) -> str:
    bench = report.get("bench")
    target_id = bench.get("targetId") if isinstance(bench, dict) else None
    if isinstance(target_id, str) and target_id.strip():
        token = target_id.split("/", 1)[0].strip()
        if token:
            return token

    if model_id:
        match = _MODEL_BENCH_RE.search(model_id)
        if match:
            return match.group(1).upper()
        lowered = model_id.lower()
        if lowered.startswith("example_b1"):
            return "B1"
        if lowered.startswith("example_b2"):
            return "B2"
        if lowered.startswith("example_b3"):
            return "B3"
        if lowered.startswith("example_b4"):
            return "B4"
        if lowered.startswith("example_b5"):
            return "B5"
        if lowered.startswith("fixture_"):
            return "FIXTURE"
        first = model_id.split("_", 1)[0].strip()
        if first:
            return first
    return ""


def _parse_seed(report: dict[str, Any], *, model_id: str, report_path: str) -> int | None:
    for candidate in (
        report.get("seed"),
        report.get("provenance", {}).get("seed") if isinstance(report.get("provenance"), dict) else None,
        report.get("config", {}).get("seed") if isinstance(report.get("config"), dict) else None,
        report.get("bench", {}).get("seed") if isinstance(report.get("bench"), dict) else None,
    ):
        value = _as_int(candidate)
        if isinstance(value, int):
            return value

    for text in (model_id, report_path):
        if not text:
            continue
        match = _SEED_RE.search(text)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                continue
    return None


def _parse_schedule_lanes(report: dict[str, Any]) -> tuple[int, int]:
    config = report.get("config")
    schedule = config.get("schedule") if isinstance(config, dict) else None
    synapse = _as_int(schedule.get("synapseLanes")) if isinstance(schedule, dict) else None
    neuron = _as_int(schedule.get("neuronLanes")) if isinstance(schedule, dict) else None
    return (
        synapse if isinstance(synapse, int) and synapse > 0 else 1,
        neuron if isinstance(neuron, int) and neuron > 0 else 1,
    )


def _parse_qor(report: dict[str, Any]) -> tuple[int | None, int | None, dict[str, int | float | None]]:
    hardware = report.get("hardware")
    qor = hardware.get("qor") if isinstance(hardware, dict) else None
    if not isinstance(qor, dict):
        return None, None, {"lut": None, "ff": None, "bram": None, "dsp": None}

    ii = _as_int(qor.get("ii"))
    latency = _as_int(qor.get("latencyCycles"))
    timing = qor.get("timingOrLatency")
    if isinstance(timing, dict):
        if ii is None:
            ii = _as_int(timing.get("ii"))
        if latency is None:
            latency = _as_int(timing.get("latencyCycles"))

    util = qor.get("utilization")
    util_dict: dict[str, int | float | None] = {"lut": None, "ff": None, "bram": None, "dsp": None}
    if isinstance(util, dict):
        for key in ("lut", "ff", "bram", "dsp"):
            util_dict[key] = _as_number(util.get(key))
    return ii, latency, util_dict


def extract_row(report: dict[str, Any], *, report_path: str = "") -> dict[str, Any]:
    config = report.get("config")
    graph = config.get("graph") if isinstance(config, dict) else None
    n_count = _as_int(graph.get("nodeCount")) if isinstance(graph, dict) else None
    e_count = _as_int(graph.get("chemicalEdgeCount")) if isinstance(graph, dict) else None
    synapse_lanes, neuron_lanes = _parse_schedule_lanes(report)
    ii, latency, util = _parse_qor(report)

    model_id = report.get("modelId")
    if not isinstance(model_id, str):
        model_id = ""
    benchmark_id = _parse_benchmark_id(report, model_id)
    seed = _parse_seed(report, model_id=model_id, report_path=report_path)

    row: dict[str, Any] = {
        "N": n_count,
        "E": e_count,
        "qformat": _parse_qformat(report),
        "P_N": neuron_lanes,
        "P_S": synapse_lanes,
        "ii": ii,
        "latency": latency,
        "lut": util["lut"],
        "ff": util["ff"],
        "bram": util["bram"],
        "dsp": util["dsp"],
        "benchmarkId": benchmark_id,
        "seed": seed,
        "modelId": model_id,
        "reportPath": report_path,
        "_reportPath": report_path,
        "_modelId": model_id,
    }
    return row


def discover_bench_reports(roots: list[Path], glob_pattern: str = "**/bench_report.json") -> list[Path]:
    found: set[Path] = set()
    for root in roots:
        if not root.exists():
            continue
        for path in root.glob(glob_pattern):
            if path.is_file():
                found.add(path.resolve())
    return sorted(found)


def extract_rows_from_paths(paths: list[Path]) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    for path in sorted(path.resolve() for path in paths):
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{path}: {exc}")
            continue
        if not isinstance(report, dict):
            errors.append(f"{path}: bench_report must be a JSON object")
            continue
        rows.append(extract_row(report, report_path=str(path)))
    return rows, errors


def write_dataset_csv(rows: list[dict[str, Any]], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sorted_rows = sorted(rows, key=lambda row: str(row.get("_reportPath", "")))
    with out_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(CSV_COLUMNS))
        writer.writeheader()
        for row in sorted_rows:
            writer.writerow({key: _csv_value(row.get(key)) for key in CSV_COLUMNS})


def load_dataset_csv(csv_path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for raw in reader:
            row: dict[str, Any] = {}
            for key in CSV_CORE_COLUMNS:
                value = raw.get(key, "")
                if key == "qformat":
                    row[key] = value or ""
                    continue
                parsed = _as_number(value)
                row[key] = parsed
            row["benchmarkId"] = (raw.get("benchmarkId", "") or "").strip()
            row["modelId"] = (raw.get("modelId", "") or "").strip()
            row["reportPath"] = (raw.get("reportPath", "") or "").strip()
            row["seed"] = _as_int(raw.get("seed", ""))
            row["_reportPath"] = row["reportPath"] or None
            row["_modelId"] = row["modelId"] or None
            rows.append(row)
    return rows


def _solve_linear_system(matrix: list[list[float]], vector: list[float]) -> list[float] | None:
    n = len(vector)
    if n == 0:
        return None
    aug = [row[:] + [vector[idx]] for idx, row in enumerate(matrix)]

    for pivot in range(n):
        max_row = max(range(pivot, n), key=lambda idx: abs(aug[idx][pivot]))
        if abs(aug[max_row][pivot]) < 1e-12:
            return None
        if max_row != pivot:
            aug[pivot], aug[max_row] = aug[max_row], aug[pivot]

        pivot_value = aug[pivot][pivot]
        for col in range(pivot, n + 1):
            aug[pivot][col] = aug[pivot][col] / pivot_value

        for row in range(n):
            if row == pivot:
                continue
            factor = aug[row][pivot]
            if abs(factor) < 1e-15:
                continue
            for col in range(pivot, n + 1):
                aug[row][col] = aug[row][col] - factor * aug[pivot][col]

    return [aug[row][n] for row in range(n)]


def _fit_linear(features: list[list[float]], targets: list[float]) -> list[float] | None:
    if not features or len(features) != len(targets):
        return None
    width = len(features[0])
    xtx = [[0.0 for _ in range(width)] for _ in range(width)]
    xty = [0.0 for _ in range(width)]

    for row, target in zip(features, targets):
        if len(row) != width:
            return None
        for i in range(width):
            xty[i] += row[i] * target
            for j in range(width):
                xtx[i][j] += row[i] * row[j]
    return _solve_linear_system(xtx, xty)


def _round_float(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 12)


def _row_target(row: dict[str, Any]) -> float | None:
    latency = row.get("latency")
    if isinstance(latency, (int, float)):
        return float(latency)
    ii = row.get("ii")
    if isinstance(ii, (int, float)):
        return float(ii)
    return None


def _row_split_key(row: dict[str, Any], split_by: str) -> str | None:
    if split_by == "none":
        return "__ALL__"
    if split_by == "benchmark":
        benchmark_id = row.get("benchmarkId")
        if isinstance(benchmark_id, str):
            text = benchmark_id.strip()
            return text if text else None
        return None
    if split_by == "seed":
        seed = row.get("seed")
        if isinstance(seed, int):
            return str(seed)
        if isinstance(seed, float) and float(seed).is_integer():
            return str(int(seed))
        return None
    return None


def _stable_group_order(groups: set[str], *, split_seed: int) -> list[str]:
    def _hash_key(value: str) -> str:
        blob = f"{split_seed}:{value}".encode("utf-8")
        return hashlib.sha256(blob).hexdigest()

    return sorted(groups, key=lambda value: (_hash_key(value), value))


def _evaluate_subset(
    entries: list[dict[str, Any]],
    coefficients: list[float] | None,
    *,
    split: str,
) -> tuple[list[dict[str, Any]], float | None, float | None]:
    rows: list[dict[str, Any]] = []
    rel_errors: list[float] = []
    if coefficients is None:
        return rows, None, None

    for entry in entries:
        feat = entry["feature"]
        target = entry["target"]
        row = entry["row"]
        predicted = coefficients[0] + coefficients[1] * feat[1] + coefficients[2] * feat[2]
        rel_error = None
        if target != 0.0:
            rel_error = abs(predicted - target) / abs(target)
            rel_errors.append(rel_error)
        elif abs(predicted) < 1e-12:
            rel_error = 0.0
            rel_errors.append(0.0)
        rows.append(
            {
                "split": split,
                "benchmarkId": row.get("benchmarkId"),
                "seed": row.get("seed"),
                "reportPath": row.get("_reportPath"),
                "modelId": row.get("_modelId"),
                "observedCycles": _round_float(target),
                "predictedCycles": _round_float(predicted),
                "relativeError": _round_float(rel_error),
            }
        )

    mean_rel_error = None
    max_rel_error = None
    if rel_errors:
        mean_rel_error = sum(rel_errors) / float(len(rel_errors))
        max_rel_error = max(rel_errors)
    return rows, mean_rel_error, max_rel_error


def _dataset_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    tuples: set[tuple[int | None, int | None, int | None, int | None, int | None, int | None]] = set()
    benchmarks: set[str] = set()
    seeds: set[int] = set()
    rows_with_seed = 0

    for row in rows:
        tup = (
            _as_int(row.get("N")),
            _as_int(row.get("E")),
            _as_int(row.get("P_N")),
            _as_int(row.get("P_S")),
            _as_int(row.get("ii")),
            _as_int(row.get("latency")),
        )
        tuples.add(tup)

        benchmark = row.get("benchmarkId")
        if isinstance(benchmark, str):
            text = benchmark.strip()
            if text:
                benchmarks.add(text)

        seed = _as_int(row.get("seed"))
        if isinstance(seed, int):
            seeds.add(seed)
            rows_with_seed += 1

    return {
        "uniqueTuples": len(tuples),
        "benchmarks": sorted(benchmarks),
        "benchmarkCount": len(benchmarks),
        "seeds": sorted(seeds),
        "seedCount": len(seeds),
        "rowsWithSeed": rows_with_seed,
    }


def fit_cost_model(
    rows: list[dict[str, Any]],
    *,
    min_points: int = 3,
    mean_relative_error_max: float = 1.0,
    split_by: str = "none",
    test_fraction: float = 0.34,
    split_seed: int = 0,
) -> dict[str, Any]:
    if split_by not in {"none", "benchmark", "seed"}:
        raise ValueError(f"unsupported split_by: {split_by}")
    if not (0.0 < float(test_fraction) < 1.0):
        raise ValueError("test_fraction must be in (0,1)")

    valid_entries: list[dict[str, Any]] = []
    split_missing_key = 0

    for row in rows:
        n_value = row.get("N")
        e_value = row.get("E")
        p_n = row.get("P_N")
        p_s = row.get("P_S")
        if not isinstance(n_value, (int, float)) or not isinstance(e_value, (int, float)):
            continue
        if not isinstance(p_n, (int, float)) or not isinstance(p_s, (int, float)):
            continue
        if float(p_n) <= 0.0 or float(p_s) <= 0.0:
            continue
        target = _row_target(row)
        if target is None:
            continue
        x_n = float(n_value) / float(p_n)
        x_e = float(e_value) / float(p_s)
        split_key = _row_split_key(row, split_by)
        if split_by != "none" and split_key is None:
            split_missing_key += 1
            continue
        valid_entries.append(
            {
                "row": row,
                "feature": [1.0, x_n, x_e],
                "target": target,
                "splitKey": split_key,
            }
        )

    points_total = len(rows)
    points_with_actual = len(valid_entries)

    split_applied = split_by != "none"
    split_requirement_met = True
    split_groups_total = 1
    train_group_count = 1
    test_group_count = 0
    train_entries: list[dict[str, Any]]
    test_entries: list[dict[str, Any]]
    train_groups: list[str] = []
    test_groups: list[str] = []

    if split_by == "none":
        train_entries = list(valid_entries)
        test_entries = []
    else:
        groups = {entry["splitKey"] for entry in valid_entries if isinstance(entry.get("splitKey"), str)}
        split_groups_total = len(groups)
        if len(groups) < 2:
            split_requirement_met = False
            train_group_count = 0
            test_group_count = 0
            train_entries = []
            test_entries = []
        else:
            ordered_groups = _stable_group_order(groups, split_seed=split_seed)
            proposed_test = int(round(float(len(ordered_groups)) * float(test_fraction)))
            test_count = max(1, min(len(ordered_groups) - 1, proposed_test))
            test_groups = ordered_groups[:test_count]
            test_group_set = set(test_groups)
            train_entries = [entry for entry in valid_entries if entry["splitKey"] not in test_group_set]
            test_entries = [entry for entry in valid_entries if entry["splitKey"] in test_group_set]
            train_groups = sorted({str(entry["splitKey"]) for entry in train_entries})
            test_groups = sorted({str(entry["splitKey"]) for entry in test_entries})
            train_group_count = len(train_groups)
            test_group_count = len(test_groups)
            split_requirement_met = bool(train_entries) and bool(test_entries)

    points_train = len(train_entries)
    points_test = len(test_entries)
    k_met = bool(points_train >= min_points and (split_by == "none" or split_requirement_met))
    solved = False
    coefficients: list[float] | None = None
    if k_met:
        coefficients = _fit_linear(
            [entry["feature"] for entry in train_entries],
            [entry["target"] for entry in train_entries],
        )
        solved = coefficients is not None

    train_rows, train_mean, train_max = _evaluate_subset(train_entries, coefficients, split="train")
    test_rows, test_mean, test_max = _evaluate_subset(test_entries, coefficients, split="test")
    all_rows, all_mean, all_max = _evaluate_subset(valid_entries, coefficients, split="all")

    within_threshold_train = bool(
        solved
        and train_mean is not None
        and float(train_mean) < float(mean_relative_error_max)
    )
    within_threshold_test = bool(
        solved
        and test_mean is not None
        and float(test_mean) < float(mean_relative_error_max)
    )
    within_threshold = within_threshold_test if split_by != "none" else within_threshold_train

    payload = {
        "modelVersion": "nema.cost.fit.v0",
        "pointsTotal": points_total,
        "pointsWithActualQor": points_with_actual,
        "pointsTrain": points_train,
        "pointsTest": points_test,
        "minPointsRequired": min_points,
        "splitBy": split_by,
        "split": {
            "mode": split_by,
            "applied": split_applied,
            "testFraction": _round_float(float(test_fraction)),
            "splitSeed": split_seed,
            "groupsTotal": split_groups_total,
            "trainGroupCount": train_group_count,
            "testGroupCount": test_group_count,
            "trainGroups": train_groups,
            "testGroups": test_groups,
            "missingSplitKeyRows": split_missing_key,
            "splitRequirementMet": split_requirement_met,
        },
        "datasetStats": _dataset_stats(rows),
        "kRequirementMet": k_met,
        "coefficients": {
            "bias": _round_float(coefficients[0]) if solved and coefficients is not None else None,
            "n_over_pn": _round_float(coefficients[1]) if solved and coefficients is not None else None,
            "e_over_ps": _round_float(coefficients[2]) if solved and coefficients is not None else None,
        },
        "meanRelativeErrorThreshold": mean_relative_error_max,
        "meanRelativeError": _round_float(all_mean),
        "maxRelativeError": _round_float(all_max),
        "meanRelativeError_train": _round_float(train_mean),
        "maxRelativeError_train": _round_float(train_max),
        "meanRelativeError_test": _round_float(test_mean),
        "maxRelativeError_test": _round_float(test_max),
        "train": {
            "points": points_train,
            "meanRelativeError": _round_float(train_mean),
            "maxRelativeError": _round_float(train_max),
            "withinThreshold": within_threshold_train,
            "rows": train_rows,
        },
        "test": {
            "points": points_test,
            "meanRelativeError": _round_float(test_mean),
            "maxRelativeError": _round_float(test_max),
            "withinThreshold": within_threshold_test,
            "rows": test_rows,
        },
        "withinThreshold": within_threshold,
        "fitSolved": solved,
        "ok": bool(k_met and within_threshold),
        "rows": all_rows,
    }
    return payload
