"""
Модуль выявления и анализа аномально долгих экземпляров процесса.

Согласно заданию практической работы, необходимо не просто найти кейсы
с максимальной длительностью, но и проанализировать, почему они длятся
дольше остальных. Для этого выполняется:

  1. Определение порога «долгих» кейсов через статистический метод
     (межквартильный размах IQR: значения выше Q3 + 1.5·IQR считаются
     выбросами / аномально долгими).
  2. Для каждого долгого кейса извлекается его вариант (trace variant).
  3. Анализ распределения долгих кейсов по вариантам — позволяет понять,
     связана ли задержка с конкретным маршрутом (например, наличием
     дополнительных согласований или возвратов).
  4. Сравнение средней длительности «долгих» и «нормальных» кейсов
     по каждому варианту.
  5. Выявление активностей, которые чаще всего повторяются в долгих кейсах
     (признак rework, удлиняющего процесс).

Такой подход позволяет сформулировать обоснованные гипотезы
о причинах задержек и предложить целевые меры оптимизации.
"""
from pathlib import Path
import pandas as pd
import numpy as np
import common


def main() -> None:
    """
    Выявляет долгие кейсы, анализирует их варианты и паттерны rework,
    сохраняет результаты в таблицы.
    """
    events_path = common.TABLES / "events_all.csv"
    if not events_path.exists():
        raise FileNotFoundError(f"Файл не найден: {events_path}")

    print("[long_cases] Анализ аномально долгих кейсов...")
    df = pd.read_csv(events_path)
    case_col = common.PARAMS["case_column"]
    act_col = common.PARAMS["activity_column"]
    time_col = common.PARAMS["timestamp_column"]
    df[time_col] = pd.to_datetime(df[time_col], format="ISO8601", utc=True)
    df = df.sort_values(by=[case_col, time_col])

    # ── 1. Длительность всех кейсов ─────────────────────────────────────────
    case_stats = (
        df.groupby(case_col)[time_col]
        .agg(lambda x: (x.max() - x.min()).total_seconds())
        .reset_index(name="duration_sec")
    )
    case_stats["duration_days"] = case_stats["duration_sec"] / (24 * 3600)

    # ── 2. Определение порога «долгих» через IQR ────────────────────────────
    # Метод межквартильного размаха (Tukey's fences) — стандартный способ
    # выявления статистических выбросов в непрерывных данных.
    q1 = case_stats["duration_sec"].quantile(0.25)
    q3 = case_stats["duration_sec"].quantile(0.75)
    iqr = q3 - q1
    threshold_sec = q3 + 1.5 * iqr
    threshold_days = threshold_sec / (24 * 3600)

    long_mask = case_stats["duration_sec"] > threshold_sec
    long_cases_df = case_stats[long_mask].copy()
    normal_cases_df = case_stats[~long_mask].copy()

    # ── 3. Варианты для всех кейсов ─────────────────────────────────────────
    variants = (
        df.groupby(case_col)[act_col]
        .apply(lambda x: " → ".join(x.astype(str)))
        .reset_index(name="variant")
    )
    case_stats = case_stats.merge(variants, on=case_col)

    # ── 4. Распределение долгих кейсов по вариантам ─────────────────────────
    long_with_variants = long_cases_df.merge(variants, on=case_col)
    variant_long_dist = (
        long_with_variants.groupby("variant")
        .agg(
            long_case_count=(case_col, "count"),
            mean_duration_sec=("duration_sec", "mean"),
            max_duration_sec=("duration_sec", "max"),
        )
        .reset_index()
        .sort_values(by="long_case_count", ascending=False)
    )
    variant_long_dist["mean_duration_days"] = (
        variant_long_dist["mean_duration_sec"] / (24 * 3600)
    )
    variant_long_dist.to_csv(
        common.TABLES / "long_cases_by_variant.csv", index=False, encoding="utf-8"
    )

    # ── 5. Сравнение долгих vs нормальных по вариантам ──────────────────────
    all_variant_stats = (
        case_stats.groupby("variant")
        .agg(
            total_cases=(case_col, "count"),
            mean_duration_sec=("duration_sec", "mean"),
        )
        .reset_index()
    )
    all_variant_stats["long_cases"] = all_variant_stats["variant"].map(
        variant_long_dist.set_index("variant")["long_case_count"].to_dict()
    ).fillna(0).astype(int)
    all_variant_stats["long_case_rate_pct"] = (
        all_variant_stats["long_cases"] / all_variant_stats["total_cases"] * 100
    )
    all_variant_stats = all_variant_stats.sort_values(
        by="long_case_rate_pct", ascending=False
    )
    all_variant_stats.to_csv(
        common.TABLES / "variant_long_analysis.csv", index=False, encoding="utf-8"
    )

    # ── 6. Rework в долгих кейсах ───────────────────────────────────────────
    # Считаем, какие активности чаще повторяются именно в долгих кейсах.
    long_case_ids = set(long_cases_df[case_col].tolist())
    long_events = df[df[case_col].isin(long_case_ids)].copy()

    activity_occurrences = (
        long_events.groupby([case_col, act_col]).size()
        .reset_index(name="occurrences")
    )
    rework_in_long = activity_occurrences[activity_occurrences["occurrences"] > 1].copy()
    rework_in_long["rework_count"] = rework_in_long["occurrences"] - 1

    if not rework_in_long.empty:
        rework_summary = (
            rework_in_long.groupby(act_col)
            .agg(
                long_cases_with_rework=(case_col, "nunique"),
                total_rework_events=("rework_count", "sum"),
            )
            .reset_index()
            .sort_values(by="total_rework_events", ascending=False)
        )
        rework_summary.to_csv(
            common.TABLES / "long_cases_rework.csv", index=False, encoding="utf-8"
        )
    else:
        rework_summary = pd.DataFrame(columns=[act_col, "long_cases_with_rework", "total_rework_events"])
        rework_summary.to_csv(
            common.TABLES / "long_cases_rework.csv", index=False, encoding="utf-8"
        )

    # ── 7. Сохранение списка долгих кейсов ──────────────────────────────────
    long_cases_df = long_cases_df.sort_values(by="duration_sec", ascending=False)
    long_cases_df["duration_days"] = long_cases_df["duration_sec"] / (24 * 3600)
    # Добавляем вариант к каждому кейсу
    long_cases_df = long_cases_df.merge(variants, on=case_col)
    long_cases_df.to_csv(
        common.TABLES / "long_cases.csv", index=False, encoding="utf-8"
    )

    # ── 8. Сводная статистика ───────────────────────────────────────────────
    mean_long_days = round(long_cases_df["duration_sec"].mean() / (24 * 3600), 2) if not long_cases_df.empty else 0.0
    top_variant = variant_long_dist.iloc[0]["variant"] if not variant_long_dist.empty else "N/A"

    summary = pd.DataFrame({
        "metric": [
            "total_cases",
            "long_cases_count",
            "long_cases_threshold_days",
            "long_cases_share_pct",
            "mean_normal_duration_days",
            "mean_long_duration_days",
            "top_variant_long_cases",
        ],
        "value": [
            len(case_stats),
            len(long_cases_df),
            round(threshold_days, 2),
            round(len(long_cases_df) / len(case_stats) * 100, 2),
            round(normal_cases_df["duration_sec"].mean() / (24 * 3600), 2),
            mean_long_days,
            top_variant,
        ]
    })
    summary.to_csv(common.TABLES / "long_cases_summary.csv", index=False, encoding="utf-8")

    print(f"[long_cases] Всего кейсов: {len(case_stats):,}")
    print(f"[long_cases] Долгих кейсов (> {threshold_days:.2f} дн): {len(long_cases_df):,} "
          f"({len(long_cases_df)/len(case_stats)*100:.1f}%)")
    print(f"[long_cases] Средняя длительность нормальных: {normal_cases_df['duration_sec'].mean()/(24*3600):.2f} дн")
    if not long_cases_df.empty:
        print(f"[long_cases] Средняя длительность долгих: {long_cases_df['duration_sec'].mean()/(24*3600):.2f} дн")
    else:
        print("[long_cases] Долгих кейсов не выявлено")
    print("[long_cases] Анализ завершён!")


if __name__ == "__main__":
    main()
