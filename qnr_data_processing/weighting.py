"""Generate or load survey weights from explicit benchmark rules."""

from __future__ import annotations

from typing import Any

import pandas as pd

from .dataset import SurveyDataset
from .errors import ConfigError, DataValidationError
from .rules import RuleEvaluator


def resolve_weights(
    dataset: SurveyDataset,
    questions: list[dict[str, Any]],
    config: dict[str, Any] | None,
) -> tuple[pd.Series, dict[str, Any]]:
    if not config:
        weights = pd.Series(1.0, index=dataset.text.index)
        return weights, {"mode": "none", "output_column": None}

    if config.get("targets"):
        return _rake_weights(dataset, questions, config)

    weights = _load_weight_column(dataset, config)
    return weights, {
        "mode": "existing_column",
        "source": config.get("source", "numeric"),
        "column": config.get("column"),
        "output_column": config.get("output_column", "final_weight"),
    }


def _rake_weights(
    dataset: SurveyDataset,
    questions: list[dict[str, Any]],
    config: dict[str, Any],
) -> tuple[pd.Series, dict[str, Any]]:
    targets = config["targets"]
    evaluator = RuleEvaluator(dataset, questions)
    masks = []
    for target in targets:
        target_mask = evaluator.evaluate(target["rule"])
        base_rule = target.get("base")
        base_mask = (
            evaluator.evaluate(base_rule)
            if isinstance(base_rule, dict)
            else pd.Series(True, index=dataset.text.index)
        )
        outside_base = target_mask & ~base_mask
        if outside_base.any():
            raise DataValidationError(
                f"权重目标“{target['name']}”有 {int(outside_base.sum())} 个样本不在其 base 内"
            )
        masks.append((target, target_mask, base_mask))
    _validate_target_feasibility(masks)
    weights = _initial_weights(dataset, config)
    if float(weights.sum()) <= 0:
        raise DataValidationError("初始权重合计必须大于 0")

    tolerance = float(config.get("tolerance", 0.0001))
    max_iterations = int(config.get("max_iterations", 200))
    trim = config.get("trim", {})
    trim_min = float(trim.get("min", 0.0))
    trim_max = float(trim.get("max", float("inf")))
    if trim_min < 0 or trim_max <= 0 or trim_min > trim_max:
        raise ConfigError("weight.trim 必须满足 0 <= min <= max")

    initial = _target_results(weights, masks)
    converged = False
    iterations = 0
    for iterations in range(1, max_iterations + 1):
        for target, mask, base_mask in masks:
            desired = _target_share(target)
            base_total = float(weights[base_mask].sum())
            if base_total <= 0:
                raise DataValidationError(
                    f"权重目标“{target['name']}”的 base 权重合计为 0"
                )
            current = float(weights[mask].sum()) / base_total
            if current <= 0:
                raise DataValidationError(
                    f"权重目标“{target['name']}”当前样本为 0，无法调整到正比例"
                )
            if current >= 1:
                raise DataValidationError(
                    f"权重目标“{target['name']}”覆盖全部样本，无法调整到小于 100%"
                )
            complement = base_mask & ~mask
            weights.loc[mask] *= desired / current
            weights.loc[complement] *= (1.0 - desired) / (1.0 - current)

        if trim_min > 0 or trim_max != float("inf"):
            weights = _bounded_normalize(weights, trim_min, trim_max)
        else:
            weights = _normalize_mean_one(weights)

        results = _target_results(weights, masks)
        if max(item["absolute_deviation"] for item in results) <= tolerance:
            converged = True
            break

    final = _target_results(weights, masks)
    if not converged and not config.get("allow_non_convergence", False):
        worst = max(final, key=lambda item: item["absolute_deviation"])
        raise DataValidationError(
            "权重迭代未收敛: "
            f"{iterations} 次后“{worst['name']}”偏差 "
            f"{worst['absolute_deviation']:.4%}；请检查目标是否冲突、样本是否不足或截尾是否过严"
        )

    return weights, {
        "mode": "raking",
        "converged": converged,
        "iterations": iterations,
        "max_iterations": max_iterations,
        "tolerance": tolerance,
        "trim_min": trim_min,
        "trim_max": None if trim_max == float("inf") else trim_max,
        "output_column": config.get("output_column", "final_weight"),
        "targets": [
            {
                **after,
                "initial_share": before["achieved_share"],
                "source": target.get("source", ""),
                "notes": target.get("notes", ""),
            }
            for target, before, after in zip(targets, initial, final)
        ],
    }


def _initial_weights(
    dataset: SurveyDataset, config: dict[str, Any]
) -> pd.Series:
    base = config.get("base_weight")
    if base is None:
        return pd.Series(1.0, index=dataset.text.index)
    if not isinstance(base, dict):
        raise ConfigError("weight.base_weight 必须是对象")
    return _load_weight_column(dataset, base)


def _load_weight_column(
    dataset: SurveyDataset, config: dict[str, Any]
) -> pd.Series:
    source = config.get("source", "numeric")
    column = config.get("column")
    if not column:
        raise ConfigError("weight.column 不能为空")
    frame = dataset.frame(source)
    if column not in frame.columns:
        raise DataValidationError(f"找不到权重列: {column}")
    weights = pd.to_numeric(frame[column], errors="coerce")
    if weights.isna().any() or (weights < 0).any():
        raise DataValidationError("权重列必须全部为非负数字且不能有空值")
    weights = weights.astype(float)
    if float(weights.sum()) <= 0:
        raise DataValidationError("权重列合计必须大于 0")
    return weights


def _target_share(target: dict[str, Any]) -> float:
    if "target" in target:
        return float(target["target"])
    return float(target["percent"]) / 100.0


def _target_results(
    weights: pd.Series,
    masks: list[tuple[dict[str, Any], pd.Series, pd.Series]],
) -> list[dict[str, Any]]:
    results = []
    for target, mask, base_mask in masks:
        desired = _target_share(target)
        base_total = float(weights[base_mask].sum())
        achieved = float(weights[mask].sum()) / base_total if base_total else 0.0
        results.append(
            {
                "name": target["name"],
                "target_share": desired,
                "achieved_share": achieved,
                "absolute_deviation": abs(achieved - desired),
                "unweighted_n": int(mask.sum()),
                "base_n": int(base_mask.sum()),
                "weighted_base": base_total,
            }
        )
    return results


def _normalize_mean_one(weights: pd.Series) -> pd.Series:
    mean = float(weights.mean())
    if mean <= 0:
        raise DataValidationError("权重均值必须大于 0")
    return weights / mean


def _bounded_normalize(
    weights: pd.Series, lower: float, upper: float
) -> pd.Series:
    if lower > 1 or upper < 1:
        raise ConfigError("权重截尾范围必须包含 1，才能保持最终权重均值为 1")
    target_sum = float(len(weights))
    if not len(weights):
        return weights

    def clipped_sum(scale: float) -> float:
        return float((weights * scale).clip(lower=lower, upper=upper).sum())

    low = 0.0
    high = 1.0
    while clipped_sum(high) < target_sum:
        high *= 2.0
        if high > 1e12:
            raise DataValidationError("无法在当前截尾范围内归一化权重")

    for _ in range(100):
        middle = (low + high) / 2.0
        if clipped_sum(middle) < target_sum:
            low = middle
        else:
            high = middle
    normalized = (weights * high).clip(lower=lower, upper=upper)
    if abs(float(normalized.sum()) - target_sum) > 1e-8:
        raise DataValidationError("截尾后权重无法稳定归一化到均值 1")
    return normalized


def _validate_target_feasibility(
    masks: list[tuple[dict[str, Any], pd.Series, pd.Series]],
) -> None:
    for index, (left, left_mask, left_base) in enumerate(masks):
        left_share = _target_share(left)
        if not left_mask.any():
            raise DataValidationError(
                f"权重目标“{left['name']}”当前样本为 0，无法调整到正比例"
            )
        if left_mask.equals(left_base):
            raise DataValidationError(
                f"权重目标“{left['name']}”覆盖其全部 base，无法调整到小于 100%"
            )
        for right, right_mask, right_base in masks[index + 1 :]:
            right_share = _target_share(right)
            if left_base.equals(right_base):
                if left_mask.equals(right_mask) and left_share != right_share:
                    raise DataValidationError(
                        f"权重目标“{left['name']}”和“{right['name']}”指向同一人群但目标比例不同"
                    )
                if (left_mask & ~right_mask).sum() == 0 and left_share > right_share:
                    raise DataValidationError(
                        f"权重子集“{left['name']}”的目标比例不能高于“{right['name']}”"
                    )
                if (right_mask & ~left_mask).sum() == 0 and right_share > left_share:
                    raise DataValidationError(
                        f"权重子集“{right['name']}”的目标比例不能高于“{left['name']}”"
                    )
                if not (left_mask & right_mask).any() and left_share + right_share > 1:
                    raise DataValidationError(
                        f"互斥权重目标“{left['name']}”和“{right['name']}”的比例合计超过 100%"
                    )
