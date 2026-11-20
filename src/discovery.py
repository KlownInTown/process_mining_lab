"""
Модуль построения моделей процесса (Discovery).

Согласно лекции, на этапе моделирования применяются алгоритмы восстановления
визуальных моделей бизнес-процессов в виде графов переходов между операциями.
Основные алгоритмы:
  • DFG (Directly-Follows Graph) — прямо-следующий граф, наглядная карта
    непосредственных переходов с частотами и средними временами.
  • Inductive Miner — последовательно разлагает поведение на блоки и
    гарантирует корректную, легко интерпретируемую структуру модели.
    Строит сеть Петри (WF-net), которая является строгим математическим
    аппаратом для моделирования динамических дискретных систем.

Сеть Петри задаётся кортежем (P, T, F), где:
  P — множество позиций (состояний);
  T — множество переходов (событий/активностей);
  F — отношение инцидентности (дуги между позициями и переходами).

WF-сеть (сеть потоков работ) — частный случай сети Петри с единственной
исходной и единственной конечной позицией, где каждый узел лежит на пути
от начала к концу.
"""
from pathlib import Path
import pandas as pd
import pm4py
import common
import graphs


def main() -> None:
    """
    Загружает очищенный лог, строит:
      1) DFG по частоте (frequency);
      2) DFG по среднему времени перехода (performance);
      3) Модель процесса через Inductive Miner (сеть Петри + BPMN);
    и сохраняет визуализации.
    """
    events_path = common.TABLES / "events_all.csv"
    if not events_path.exists():
        raise FileNotFoundError(f"Файл не найден: {events_path}. Запустите prepare.py")

    print("[discovery] Загрузка очищенного лога...")
    df = pd.read_csv(events_path)
    # Явный парсинг дат с таймзоной
    df[common.PARAMS["timestamp_column"]] = pd.to_datetime(
        df[common.PARAMS["timestamp_column"]], format="ISO8601", utc=True
    )

    case_col = common.PARAMS["case_column"]
    act_col = common.PARAMS["activity_column"]
    time_col = common.PARAMS["timestamp_column"]

    # Конвертация DataFrame → EventLog для pm4py
    log = pm4py.format_dataframe(
        df,
        case_id=case_col,
        activity_key=act_col,
        timestamp_key=time_col
    )

    # ── 1. DFG по частоте ───────────────────────────────────────────────────
    print("[discovery] Построение DFG (frequency)...")
    dfg_freq, start_activities, end_activities = pm4py.discover_dfg(log)
    nodes = pm4py.get_event_attribute_values(log, act_col)

    dot_freq = graphs.dfg_dot(
        nodes,
        [(k[0], k[1], v, 1.0) for k, v in dfg_freq.items()],
        mode="freq",
        starts=start_activities,
        ends=end_activities
    )
    try:
        graphs.render_dot(dot_freq, "process_dfg_frequency")
    except Exception as e:
        print(f"[discovery] Предупреждение: не удалось отрендерить DFG freq ({e}). Сохранён DOT-файл.")
        (common.FIGURES / "process_dfg_frequency.dot").write_text(dot_freq, encoding="utf-8")

    # ── 2. DFG по среднему времени перехода ─────────────────────────────────
    print("[discovery] Построение DFG (performance)...")
    # Вычисляем среднее время между каждой парой активностей
    perf_edges = compute_performance_dfg(df, case_col, act_col, time_col)
    dot_perf = graphs.dfg_dot(
        nodes,
        perf_edges,
        mode="perf",
        starts=start_activities,
        ends=end_activities
    )
    try:
        graphs.render_dot(dot_perf, "process_dfg_performance")
    except Exception as e:
        print(f"[discovery] Предупреждение: не удалось отрендерить DFG perf ({e}). Сохранён DOT-файл.")
        (common.FIGURES / "process_dfg_performance.dot").write_text(dot_perf, encoding="utf-8")

    # ── 3. Inductive Miner → сеть Петри ─────────────────────────────────────
    print("[discovery] Построение модели через Inductive Miner (Petri net)...")
    net, im, fm = pm4py.discover_petri_net_inductive(log)

    # Визуализация сети Петри
    try:
        gviz_petri = pm4py.visualization.petri_net.visualizer.apply(net, im, fm)
        pm4py.visualization.petri_net.visualizer.save(gviz_petri, str(common.FIGURES / "process_petri_net.png"))
    except Exception as e:
        print(f"[discovery] Предупреждение: не удалось отрендерить сеть Петри ({e}).")

    # Сохраняем модель для conformance checking
    import pickle
    model_path = common.TABLES / "process_model.pkl"
    with open(model_path, "wb") as f:
        pickle.dump({"net": net, "im": im, "fm": fm}, f)

    # ── 4. BPMN для наглядности ─────────────────────────────────────────────
    print("[discovery] Экспорт в BPMN...")
    try:
        bpmn_graph = pm4py.convert_to_bpmn(net, im, fm)
        pm4py.write_bpmn(bpmn_graph, str(common.FIGURES / "process_model.bpmn"))
    except Exception as e:
        print(f"[discovery] Предупреждение: не удалось экспортировать BPMN ({e}).")

    # ── 5. Сохранение статистики модели ─────────────────────────────────────
    model_stats = {
        "algorithm": "Inductive Miner",
        "model_type": "Petri net (WF-net)",
        "places": len(net.places),
        "transitions": len(net.transitions),
        "arcs": len(net.arcs),
        "dfg_edges": len(dfg_freq),
        "start_activities": {str(k): int(v) for k, v in start_activities.items()},
        "end_activities": {str(k): int(v) for k, v in end_activities.items()},
    }
    import json
    (common.TABLES / "model_stats.json").write_text(
        json.dumps(model_stats, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print("[discovery] Модель успешно построена и сохранена!")


def compute_performance_dfg(df, case_col, act_col, time_col):
    """
    Вычисляет среднее время ожидания (idle time) между парами активностей.

    Для каждого кейса рассматриваются соседние события:
    время перехода = timestamp(next) - timestamp(current).
    Затем по каждой паре (activity_a → activity_b) вычисляется среднее.

    Это позволяет визуально выделить на DFG "горячие" рёбра — переходы
    с наибольшей задержкой, которые часто являются узкими местами.
    """
    df_sorted = df.sort_values(by=[case_col, time_col]).copy()
    df_sorted["next_activity"] = df_sorted.groupby(case_col)[act_col].shift(-1)
    df_sorted["next_time"] = df_sorted.groupby(case_col)[time_col].shift(-1)

    # Убираем последние события в кейсах (у них нет next)
    transitions = df_sorted.dropna(subset=["next_activity", "next_time"]).copy()
    transitions["duration_sec"] = (
        transitions["next_time"] - transitions[time_col]
    ).dt.total_seconds()

    # Среднее время по каждой паре
    perf = transitions.groupby([act_col, "next_activity"])["duration_sec"].mean().reset_index()
    perf["duration_days"] = perf["duration_sec"] / (24 * 3600)

    # Формат для dfg_dot: (from, to, frequency, days)
    # frequency берём из общего счёта переходов
    freq = transitions.groupby([act_col, "next_activity"]).size().reset_index(name="freq")
    merged = perf.merge(freq, on=[act_col, "next_activity"])

    edges = []
    for _, row in merged.iterrows():
        edges.append((
            row[act_col],
            row["next_activity"],
            int(row["freq"]),
            float(row["duration_days"])
        ))
    return edges


if __name__ == "__main__":
    main()
