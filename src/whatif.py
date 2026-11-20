"""
Модуль сценарного анализа оптимизации (What-If Analysis).

Согласно лекции, на этапе улучшения результаты анализа приводятся
в наглядный вид, формулируются экспертные рекомендации, а затем
оценивается ожидаемый эффект: как изменится длительность цикла,
доля нарушений SLA и загрузка ресурсов.

What-If анализ позволяет «в песочнице» промоделировать влияние
конкретных изменений на процесс без их фактического внедрения.

Моделируемые сценарии:
  1. Базовый — текущее состояние процесса (точка отсчёта).
  2. Устранение топ-узкого места — сокращение времени ожидания
     на самом «горячем» переходе на 50 %.
  3. Сокращение rework — устранение 80 % повторов активности,
     которая чаще всего возвращается на доработку.
  4. Автоматизация проверки — исключение ручной операции,
     занимающей значительную долю времени, замена её на автоматическую
     (сокращение processing time на 90 %).

Для каждого сценария пересчитывается ожидаемая средняя длительность
процесса на основе реальных распределений из лога.
"""
from pathlib import Path
import pandas as pd
import numpy as np
import common


def main() -> None:
    """
    Загружает результаты анализа bottleneck и rework,
    строит сценарии оптимизации и сохраняет их в таблицу.
    """
    events_path = common.TABLES / "events_all.csv"
    trans_path = common.TABLES / "transition_times.csv"
    rework_path = common.TABLES / "rework_activities.csv"

    if not events_path.exists():
        raise FileNotFoundError(f"Файл не найден: {events_path}")

    print("[whatif] Моделирование сценариев оптимизации...")
    df = pd.read_csv(events_path)
    case_col = common.PARAMS["case_column"]
    act_col = common.PARAMS["activity_column"]
    time_col = common.PARAMS["timestamp_column"]
    df[time_col] = pd.to_datetime(df[time_col], format="ISO8601", utc=True)
    df = df.sort_values(by=[case_col, time_col])

    # ── 1. Базовая статистика ───────────────────────────────────────────────
    case_durations = (
        df.groupby(case_col)[time_col]
        .agg(lambda x: (x.max() - x.min()).total_seconds())
        .reset_index(name="duration_sec")
    )
    base_mean_sec = case_durations["duration_sec"].mean()
    base_mean_days = base_mean_sec / (24 * 3600)

    scenarios = []

    # ── Сценарий 1: Базовый ─────────────────────────────────────────────────
    scenarios.append({
        "scenario": "Базовый (текущее состояние)",
        "description": "Средняя длительность процесса без изменений",
        "estimated_duration_days": round(base_mean_days, 2),
        "estimated_duration_sec": round(base_mean_sec, 2),
        "improvement_pct": 0.0,
        "assumptions": "Нет",
    })

    # ── Сценарий 2: Устранение топ-узкого места ─────────────────────────────
    # Загружаем статистику переходов и находим самый долгий
    if trans_path.exists():
        trans_stats = pd.read_csv(trans_path)
        if not trans_stats.empty:
            top_bottleneck = trans_stats.iloc[0]
            bottleneck_mean_sec = top_bottleneck["mean_idle_sec"]
            bottleneck_share = bottleneck_mean_sec / base_mean_sec if base_mean_sec > 0 else 0
            # Сокращаем idle time на этом переходе на 50 %
            reduction = bottleneck_mean_sec * 0.5 * bottleneck_share
            new_mean_sec = base_mean_sec - reduction
            scenarios.append({
                "scenario": "Устранение топ-узкого места",
                "description": f"Сокращение ожидания на переходе "
                               f"'{top_bottleneck[act_col]} → {top_bottleneck['next_activity']}' на 50%",
                "estimated_duration_days": round(new_mean_sec / (24 * 3600), 2),
                "estimated_duration_sec": round(new_mean_sec, 2),
                "improvement_pct": round((base_mean_sec - new_mean_sec) / base_mean_sec * 100, 2),
                "assumptions": "Idle time снижается за счёт перераспределения ресурсов или автоматизации эскалации",
            })

    # ── Сценарий 3: Сокращение rework ───────────────────────────────────────
    # Загружаем статистику повторов и моделируем устранение 80 % rework
    if rework_path.exists():
        rework_stats = pd.read_csv(rework_path)
        if not rework_stats.empty:
            top_rework = rework_stats.iloc[0]
            rework_act = top_rework[act_col]
            # Находим среднее время обработки этой активности
            df["next_time"] = df.groupby(case_col)[time_col].shift(-1)
            act_times = df[df[act_col] == rework_act].copy()
            act_times = act_times.dropna(subset=["next_time"])
            act_times["processing_sec"] = (act_times["next_time"] - act_times[time_col]).dt.total_seconds()
            mean_proc = act_times["processing_sec"].mean() if not act_times.empty else 0

            total_rework_events = top_rework["total_rework_events"]
            # Устраняем 80 % rework → экономим 80 % времени на повторных проходах
            saved_sec = total_rework_events * 0.8 * mean_proc
            # Распределяем экономию на все кейсы (консервативная оценка)
            saved_per_case = saved_sec / len(case_durations) if len(case_durations) > 0 else 0
            new_mean_sec = base_mean_sec - saved_per_case
            scenarios.append({
                "scenario": "Сокращение rework",
                "description": f"Устранение 80% повторов активности '{rework_act}'",
                "estimated_duration_days": round(new_mean_sec / (24 * 3600), 2),
                "estimated_duration_sec": round(new_mean_sec, 2),
                "improvement_pct": round((base_mean_sec - new_mean_sec) / base_mean_sec * 100, 2),
                "assumptions": "Внедрение чек-листов и автоматической проверки до передачи на согласование",
            })

    # ── Сценарий 4: Автоматизация ручной операции ───────────────────────────
    # Находим активность с наибольшим средним processing time и моделируем
    # её автоматизацию (сокращение на 90 %).
    act_dur_path = common.TABLES / "activity_durations.csv"
    if act_dur_path.exists():
        act_dur = pd.read_csv(act_dur_path)
        if not act_dur.empty:
            top_manual = act_dur.iloc[0]
            manual_act = top_manual[act_col]
            manual_time = top_manual["mean_processing_sec"]
            # Считаем, сколько раз эта активность встречается в среднем на кейс
            act_per_case = df.groupby(case_col)[act_col].apply(
                lambda x: (x == manual_act).sum()
            ).mean()
            saved_per_case = act_per_case * manual_time * 0.9
            new_mean_sec = base_mean_sec - saved_per_case
            scenarios.append({
                "scenario": "Автоматизация проверки",
                "description": f"Автоматизация активности '{manual_act}' (сокращение на 90%)",
                "estimated_duration_days": round(new_mean_sec / (24 * 3600), 2),
                "estimated_duration_sec": round(new_mean_sec, 2),
                "improvement_pct": round((base_mean_sec - new_mean_sec) / base_mean_sec * 100, 2),
                "assumptions": "RPA-бот или интеграция с внешними системами для автоматической проверки",
            })

    # ── Сохранение ──────────────────────────────────────────────────────────
    scenarios_df = pd.DataFrame(scenarios)
    scenarios_df.to_csv(
        common.TABLES / "whatif_scenarios.csv", index=False, encoding="utf-8"
    )

    print("[whatif] Смоделировано сценариев:", len(scenarios_df))
    for _, row in scenarios_df.iterrows():
        print(f"  • {row['scenario']}: {row['estimated_duration_days']:.2f} дн "
              f"(улучшение {row['improvement_pct']:.1f}%)")
    print("[whatif] Моделирование завершено!")


if __name__ == "__main__":
    main()
