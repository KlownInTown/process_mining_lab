"""
Модуль анализа производительности и выявления узких мест (Bottleneck Analysis).

Согласно лекции, узкое место (Bottleneck) — это операция, ресурс или участок
процесса, ограничивающий его общую пропускную способность и приводящий
к накоплению очередей или увеличению времени выполнения.

Ключевой инсайт Process Mining: отдельная операция может выполняться всего
несколько минут, но ожидание её начала занимает несколько часов. Поэтому
узкое место определяется не по длительности самой операции, а по времени
ожидания (idle time) между завершением предыдущей операции и началом
следующей.

Рассчитываемые метрики (KPI Process Performance Analysis):
  • Средняя и медианная продолжительность кейса (case duration).
  • Время выполнения отдельных операций (processing time).
  • Время ожидания между операциями (idle time / waiting time).
  • Пропускная способность по каждому переходу (throughput).
  • Доля процессов, завершённых в установленный срок (SLA compliance).

Результат сохраняется в таблицы:
  • bottlenecks.csv — топ узких мест по среднему времени ожидания.
  • activity_durations.csv — статистика по длительности каждой активности.
  • transition_times.csv — детальная статистика по всем переходам.
"""
from pathlib import Path
import pandas as pd
import numpy as np
import common


def main() -> None:
    """
    Анализирует временные характеристики процесса, выявляет узкие места
    и сохраняет результаты в виде структурированных таблиц.
    """
    events_path = common.TABLES / "events_all.csv"
    if not events_path.exists():
        raise FileNotFoundError(f"Файл не найден: {events_path}. Запустите prepare.py")

    print("[performance] Анализ временных характеристик...")
    df = pd.read_csv(events_path)
    time_col = common.PARAMS["timestamp_column"]
    case_col = common.PARAMS["case_column"]
    act_col = common.PARAMS["activity_column"]
    df[time_col] = pd.to_datetime(df[time_col], format="ISO8601", utc=True)

    # Сортируем события внутри каждого кейса
    df = df.sort_values(by=[case_col, time_col])

    # ── 1. Общая статистика по кейсам ───────────────────────────────────────
    case_stats = df.groupby(case_col)[time_col].agg(["min", "max", "count"])
    case_stats["duration_sec"] = (case_stats["max"] - case_stats["min"]).dt.total_seconds()
    case_stats["duration_days"] = case_stats["duration_sec"] / (24 * 3600)

    summary = pd.DataFrame({
        "metric": [
            "case_count",
            "mean_duration_sec",
            "median_duration_sec",
            "max_duration_sec",
            "mean_duration_days",
            "median_duration_days",
            "max_duration_days",
            "mean_events_per_case",
        ],
        "value": [
            len(case_stats),
            case_stats["duration_sec"].mean(),
            case_stats["duration_sec"].median(),
            case_stats["duration_sec"].max(),
            case_stats["duration_days"].mean(),
            case_stats["duration_days"].median(),
            case_stats["duration_days"].max(),
            case_stats["count"].mean(),
        ]
    })
    summary.to_csv(common.TABLES / "bottlenecks.csv", index=False, encoding="utf-8")

    # ── 2. Время ожидания (Idle Time) между операциями ──────────────────────
    # Для каждого события в кейсе вычисляем время до следующего события.
    # Это и есть ключевой показатель bottleneck: чем дольше объект "стоит"
    # между двумя активностями, тем сильнее узкое место.
    df["next_time"] = df.groupby(case_col)[time_col].shift(-1)
    df["next_activity"] = df.groupby(case_col)[act_col].shift(-1)

    transitions = df.dropna(subset=["next_time", "next_activity"]).copy()
    transitions["idle_sec"] = (transitions["next_time"] - transitions[time_col]).dt.total_seconds()
    transitions["idle_days"] = transitions["idle_sec"] / (24 * 3600)

    # Группировка по парам активностей (переходам)
    trans_stats = transitions.groupby([act_col, "next_activity"]).agg(
        count=("idle_sec", "size"),
        mean_idle_sec=("idle_sec", "mean"),
        median_idle_sec=("idle_sec", "median"),
        max_idle_sec=("idle_sec", "max"),
        std_idle_sec=("idle_sec", "std"),
        total_idle_sec=("idle_sec", "sum"),
    ).reset_index()
    trans_stats = trans_stats.sort_values(by="mean_idle_sec", ascending=False)
    trans_stats.to_csv(common.TABLES / "transition_times.csv", index=False, encoding="utf-8")

    # ── 3. Узкие места (топ-переходы по среднему idle time) ─────────────────
    # Выбираем топ-20 переходов с наибольшим средним временем ожидания.
    top_bottlenecks = trans_stats.head(20).copy()
    top_bottlenecks["mean_idle_hours"] = top_bottlenecks["mean_idle_sec"] / 3600
    top_bottlenecks["mean_idle_days"] = top_bottlenecks["mean_idle_sec"] / (24 * 3600)
    top_bottlenecks.to_csv(
        common.TABLES / "bottlenecks_top20.csv", index=False, encoding="utf-8"
    )

    # ── 4. Статистика по длительности каждой активности ─────────────────────
    # Processing time = время от начала активности до начала следующей
    # (в данном логе нет отдельных start/end, поэтому используем приближение:
    # среднее время до следующего события как оценку processing time).
    act_stats = transitions.groupby(act_col).agg(
        count=("idle_sec", "size"),
        mean_processing_sec=("idle_sec", "mean"),
        median_processing_sec=("idle_sec", "median"),
        max_processing_sec=("idle_sec", "max"),
    ).reset_index()
    act_stats = act_stats.sort_values(by="mean_processing_sec", ascending=False)
    act_stats.to_csv(common.TABLES / "activity_durations.csv", index=False, encoding="utf-8")

    # ── 5. SLA compliance (для информации) ──────────────────────────────────
    # Допустим, SLA = 95-й перцентиль длительности завершённых кейсов.
    sla_threshold = case_stats["duration_sec"].quantile(0.95)
    sla_compliance = (case_stats["duration_sec"] <= sla_threshold).mean() * 100

    print(f"[performance] Кейсов: {len(case_stats):,}")
    print(f"[performance] Средняя длительность: {case_stats['duration_days'].mean():.2f} дн")
    print(f"[performance] Медианная длительность: {case_stats['duration_days'].median():.2f} дн")
    print(f"[performance] SLA compliance (95%%): {sla_compliance:.1f}%")
    print(f"[performance] Топ узкое место: {top_bottlenecks.iloc[0][act_col]} → "
          f"{top_bottlenecks.iloc[0]['next_activity']} "
          f"({top_bottlenecks.iloc[0]['mean_idle_days']:.2f} дн в среднем)")
    print("[performance] Анализ завершён!")


if __name__ == "__main__":
    main()
