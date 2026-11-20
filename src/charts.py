"""
Модуль генерации аналитических графиков и диаграмм.

Визуализация — ключевой элемент Process Mining, поскольку позволяет
наглядно представить структуру процесса, распределение показателей
и аномалии. Согласно лекции, восстановленная модель процесса может
показать неожиданные последовательности операций, нехарактерные
маршруты и различия между подразделениями.

Создаваемые диаграммы:
  1. Гистограмма распределения длительности кейсов — позволяет увидеть
     форму распределения и выявить «хвост» долгих кейсов.
  2. Boxplot длительности по топ-вариантам — сравнивает варианты
     процесса и выявляет те, которые систематически длятся дольше.
  3. Heatmap среднего idle time между активностями — наглядно показывает
     «горячие» переходы (узкие места) в матричной форме.
  4. Столбчатая диаграмма rework rate по активностям — демонстрирует,
     какие операции чаще всего возвращаются на доработку.
  5. Сравнение сценариев What-If — столбчатая диаграмма ожидаемой
     длительности процесса по оптимизационным сценариям.
"""
from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")  # Неинтерактивный бэкенд для серверного рендеринга
import matplotlib.pyplot as plt
import seaborn as sns
import common


def main() -> None:
    """Формирует и сохраняет аналитические диаграммы в results/figures/."""
    common.FIGURES.mkdir(parents=True, exist_ok=True)
    print("[charts] Генерация визуализаций...")

    # Общие настройки стиля
    sns.set_style("whitegrid")
    plt.rcParams["figure.dpi"] = 150
    plt.rcParams["savefig.dpi"] = 150
    plt.rcParams["figure.figsize"] = (10, 6)

    # ── 1. Гистограмма длительности кейсов ──────────────────────────────────
    _plot_case_duration_histogram()

    # ── 2. Boxplot по топ-вариантам ─────────────────────────────────────────
    _plot_variant_boxplot()

    # ── 3. Heatmap idle time ────────────────────────────────────────────────
    _plot_idle_time_heatmap()

    # ── 4. Rework rate по активностям ───────────────────────────────────────
    _plot_rework_bar()

    # ── 5. Сравнение What-If сценариев ──────────────────────────────────────
    _plot_whatif_comparison()

    print("[charts] Все графики сохранены в results/figures/")


def _plot_case_duration_histogram():
    """Гистограмма распределения длительности кейсов (в днях)."""
    events_path = common.TABLES / "events_all.csv"
    if not events_path.exists():
        return
    df = pd.read_csv(events_path)
    case_col = common.PARAMS["case_column"]
    time_col = common.PARAMS["timestamp_column"]
    df[time_col] = pd.to_datetime(df[time_col], format="ISO8601", utc=True)
    durations = (
        df.groupby(case_col)[time_col]
        .agg(lambda x: (x.max() - x.min()).total_seconds() / (24 * 3600))
    )
    # Отсекаем экстремальные выбросы для наглядности (99-й перцентиль)
    cap = durations.quantile(0.99)
    plot_data = durations[durations <= cap]

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.hist(plot_data, bins=50, color="steelblue", edgecolor="white", alpha=0.8)
    ax.axvline(durations.median(), color="red", linestyle="--", linewidth=2, label=f"Медиана: {durations.median():.1f} дн")
    ax.axvline(durations.mean(), color="green", linestyle="--", linewidth=2, label=f"Среднее: {durations.mean():.1f} дн")
    ax.set_xlabel("Длительность кейса, дни")
    ax.set_ylabel("Количество кейсов")
    ax.set_title("Распределение длительности выполнения процесса")
    ax.legend()
    fig.tight_layout()
    fig.savefig(common.FIGURES / "duration_histogram.png")
    plt.close(fig)


def _plot_variant_boxplot():
    """Boxplot длительности по топ-10 вариантам процесса."""
    variants_path = common.TABLES / "variants.csv"
    if not variants_path.exists():
        return
    var_df = pd.read_csv(variants_path)
    if var_df.empty or "mean_duration_sec" not in var_df.columns:
        return
    top10 = var_df.head(10).copy()
    top10["mean_duration_days"] = top10["mean_duration_sec"] / (24 * 3600)

    fig, ax = plt.subplots(figsize=(12, 7))
    # Используем столбчатую диаграмму с error bars (max-min) для наглядности
    x = np.arange(len(top10))
    ax.bar(x, top10["mean_duration_days"], color="coral", alpha=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels([v[:30] + "..." if len(v) > 30 else v for v in top10["variant"]], rotation=45, ha="right")
    ax.set_ylabel("Средняя длительность, дни")
    ax.set_title("Средняя длительность по топ-10 вариантам процесса")
    fig.tight_layout()
    fig.savefig(common.FIGURES / "variant_duration.png")
    plt.close(fig)


def _plot_idle_time_heatmap():
    """Heatmap среднего idle time между активностями (топ-15 активностей)."""
    trans_path = common.TABLES / "transition_times.csv"
    if not trans_path.exists():
        return
    trans = pd.read_csv(trans_path)
    if trans.empty:
        return

    act_col = common.PARAMS["activity_column"]
    # Берём топ-15 активностей по частоте для компактности
    top_acts = pd.concat([trans[act_col], trans["next_activity"]]).value_counts().head(15).index.tolist()
    trans_sub = trans[
        trans[act_col].isin(top_acts) & trans["next_activity"].isin(top_acts)
    ].copy()
    if trans_sub.empty:
        return

    # Формируем матрицу
    trans_sub["mean_idle_hours"] = trans_sub["mean_idle_sec"] / 3600
    pivot = trans_sub.pivot_table(
        index=act_col,
        columns="next_activity",
        values="mean_idle_hours",
        aggfunc="mean"
    )
    # Оставляем только пересечение top_acts
    pivot = pivot.reindex(index=top_acts, columns=top_acts)

    fig, ax = plt.subplots(figsize=(12, 10))
    sns.heatmap(
        pivot,
        annot=True,
        fmt=".1f",
        cmap="YlOrRd",
        linewidths=0.5,
        ax=ax,
        cbar_kws={"label": "Среднее idle time, часы"}
    )
    ax.set_title("Матрица среднего времени ожидания между активностями")
    ax.set_xlabel("Следующая активность")
    ax.set_ylabel("Текущая активность")
    fig.tight_layout()
    fig.savefig(common.FIGURES / "idle_time_heatmap.png")
    plt.close(fig)


def _plot_rework_bar():
    """Столбчатая диаграмма rework rate по активностям."""
    rework_path = common.TABLES / "rework_activities.csv"
    if not rework_path.exists():
        return
    rework = pd.read_csv(rework_path)
    if rework.empty:
        return
    act_col = common.PARAMS["activity_column"]
    top_rework = rework.head(15).copy()

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.barh(top_rework[act_col], top_rework["total_rework_events"], color="indianred", alpha=0.8)
    ax.set_xlabel("Количество повторных событий (rework)")
    ax.set_title("Топ активностей по количеству повторов (rework)")
    ax.invert_yaxis()
    fig.tight_layout()
    fig.savefig(common.FIGURES / "rework_activities.png")
    plt.close(fig)


def _plot_whatif_comparison():
    """Сравнение сценариев What-If по ожидаемой длительности."""
    whatif_path = common.TABLES / "whatif_scenarios.csv"
    if not whatif_path.exists():
        return
    whatif = pd.read_csv(whatif_path)
    if whatif.empty:
        return

    fig, ax = plt.subplots(figsize=(10, 6))
    colors = ["gray" if i == 0 else "forestgreen" for i in range(len(whatif))]
    ax.bar(whatif["scenario"], whatif["estimated_duration_days"], color=colors, alpha=0.8)
    ax.set_ylabel("Ожидаемая длительность, дни")
    ax.set_title("Сравнение сценариев оптимизации (What-If Analysis)")
    ax.tick_params(axis="x", rotation=30)
    # Добавляем процент улучшения на столбцы
    for i, (idx, row) in enumerate(whatif.iterrows()):
        ax.text(i, row["estimated_duration_days"] + 0.1,
                f"{row['improvement_pct']:.1f}%",
                ha="center", va="bottom", fontsize=9)
    fig.tight_layout()
    fig.savefig(common.FIGURES / "whatif_comparison.png")
    plt.close(fig)


if __name__ == "__main__":
    main()
