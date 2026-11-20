"""
Модуль анализа повторяющихся операций, циклов и вариантов (Rework Analysis).

Согласно лекции, цикл возникает, когда процесс возвращается к ранее
выполненному действию или группе действий. Не все циклы свидетельствуют
о проблемах, однако частое повторение одних и тех же операций увеличивает
продолжительность процесса, создаёт дополнительную нагрузку на сотрудников
и повышает риски ошибок.

Process Mining позволяет:
  • Выявлять циклы и определять частоту их возникновения.
  • Оценивать, насколько циклы увеличивают время выполнения.
  • Находить «пинг-понги» — возвраты между ролями или этапами.
  • Выделять варианты процесса (Process Variants) и сравнивать их
    по длительности, частоте и эффективности.

Рассчитываемые метрики:
  • Rework rate — доля кейсов, содержащих повторы активностей.
  • Cycle frequency — частота каждого циклического паттерна.
  • Variant statistics — частота, средняя длительность и доля каждого
    варианта от общего числа кейсов.
"""
from pathlib import Path
import pandas as pd
import numpy as np
import common


def main() -> None:
    """
    Анализирует лог на наличие повторов, циклов и вариантов,
    сохраняет результаты в таблицы.
    """
    events_path = common.TABLES / "events_all.csv"
    if not events_path.exists():
        raise FileNotFoundError(f"Файл не найден: {events_path}")

    print("[rework] Анализ циклов, повторов и вариантов...")
    df = pd.read_csv(events_path)
    case_col = common.PARAMS["case_column"]
    act_col = common.PARAMS["activity_column"]
    time_col = common.PARAMS["timestamp_column"]
    df[time_col] = pd.to_datetime(df[time_col], format="ISO8601", utc=True)
    df = df.sort_values(by=[case_col, time_col])

    # ── 1. Варианты процесса ────────────────────────────────────────────────
    # Вариант = последовательность активностей в кейсе.
    variants = (
        df.groupby(case_col)[act_col]
        .apply(lambda x: " → ".join(x.astype(str)))
        .reset_index(name="variant")
    )
    variant_counts = variants["variant"].value_counts().reset_index()
    variant_counts.columns = ["variant", "case_count"]
    variant_counts["case_share_pct"] = (
        variant_counts["case_count"] / variant_counts["case_count"].sum() * 100
    )

    # ── 2. Средняя длительность по вариантам ────────────────────────────────
    case_durations = (
        df.groupby(case_col)[time_col]
        .agg(lambda x: (x.max() - x.min()).total_seconds())
        .reset_index(name="duration_sec")
    )
    case_durations["duration_days"] = case_durations["duration_sec"] / (24 * 3600)

    variant_cases = variants.merge(case_durations, on=case_col)
    variant_perf = (
        variant_cases.groupby("variant")
        .agg(
            case_count=("duration_sec", "size"),
            mean_duration_sec=("duration_sec", "mean"),
            median_duration_sec=("duration_sec", "median"),
            max_duration_sec=("duration_sec", "max"),
        )
        .reset_index()
    )
    variant_perf = variant_perf.sort_values(by="case_count", ascending=False)
    variant_perf["mean_duration_days"] = variant_perf["mean_duration_sec"] / (24 * 3600)
    variant_perf.to_csv(common.TABLES / "variants.csv", index=False, encoding="utf-8")

    # ── 3. Обнаружение повторов (rework) внутри кейсов ──────────────────────
    # Считаем, сколько раз каждая активность встречается в кейсе.
    activity_counts = (
        df.groupby([case_col, act_col]).size()
        .reset_index(name="activity_occurrences")
    )
    repeated = activity_counts[activity_counts["activity_occurrences"] > 1].copy()
    repeated["rework_events"] = repeated["activity_occurrences"] - 1

    rework_summary = (
        repeated.groupby(act_col)
        .agg(
            cases_with_rework=(case_col, "nunique"),
            total_rework_events=("rework_events", "sum"),
        )
        .reset_index()
        .sort_values(by="total_rework_events", ascending=False)
    )
    rework_summary.to_csv(common.TABLES / "rework_activities.csv", index=False, encoding="utf-8")

    # ── 4. Rework rate ──────────────────────────────────────────────────────
    total_cases = df[case_col].nunique()
    cases_with_rework = repeated[case_col].nunique()
    rework_rate = cases_with_rework / total_cases * 100 if total_cases > 0 else 0

    # ── 5. Обнаружение циклов (пинг-понгов) ─────────────────────────────────
    # Цикл = возврат к предыдущей активности: A → B → A.
    # Ищем паттерны длины 2, которые повторяются внутри кейса.
    df["next_activity"] = df.groupby(case_col)[act_col].shift(-1)
    df["next_next_activity"] = df.groupby(case_col)[act_col].shift(-2)

    cycles = df.dropna(subset=["next_activity", "next_next_activity"]).copy()
    cycle_mask = cycles[act_col] == cycles["next_next_activity"]
    cycle_cases = cycles[cycle_mask].copy()

    if not cycle_cases.empty:
        cycle_patterns = (
            cycle_cases.groupby([act_col, "next_activity"])
            .size()
            .reset_index(name="cycle_count")
            .sort_values(by="cycle_count", ascending=False)
        )
        cycle_patterns.columns = ["activity_a", "activity_b", "cycle_count"]
        cycle_patterns.to_csv(
            common.TABLES / "cycle_patterns.csv", index=False, encoding="utf-8"
        )
        top_cycle = cycle_patterns.iloc[0] if len(cycle_patterns) > 0 else None
    else:
        top_cycle = None

    # ── 6. Сводная статистика ───────────────────────────────────────────────
    summary = pd.DataFrame({
        "metric": [
            "total_cases",
            "total_variants",
            "cases_with_rework",
            "rework_rate_pct",
            "most_frequent_variant_cases",
            "most_frequent_variant_share_pct",
        ],
        "value": [
            total_cases,
            len(variant_counts),
            cases_with_rework,
            round(rework_rate, 2),
            int(variant_perf.iloc[0]["case_count"]) if not variant_perf.empty else 0,
            round(variant_counts.iloc[0]["case_share_pct"], 2) if not variant_counts.empty else 0,
        ]
    })
    summary.to_csv(common.TABLES / "rework_summary.csv", index=False, encoding="utf-8")

    print(f"[rework] Всего кейсов: {total_cases:,}")
    print(f"[rework] Уникальных вариантов: {len(variant_counts):,}")
    print(f"[rework] Rework rate: {rework_rate:.2f}% ({cases_with_rework} кейсов)")
    if top_cycle is not None:
        print(f"[rework] Топ цикл: {top_cycle['activity_a']} → {top_cycle['activity_b']} → "
              f"{top_cycle['activity_a']} ({top_cycle['cycle_count']} раз)")
    print("[rework] Анализ завершён!")


if __name__ == "__main__":
    main()
