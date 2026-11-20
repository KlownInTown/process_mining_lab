"""
Модуль проверки соответствия (Conformance Checking).

Согласно лекции, на этом этапе цель — понять, насколько фактическое
исполнение совпадает с эталонным маршрутом, где именно возникают
критические отклонения и какова реальная разница между «ожиданием»
и «реальностью».

Для проверки соответствия фактический лог событий сопоставляется
с эталонной моделью процесса (восстановленной через Inductive Miner
в виде сети Петри). Используется Token-Based Replay — метод,
который "проигрывает" каждую трассу лога через сеть Петри и считает:
  • Produced tokens — сколько токенов порождено;
  • Consumed tokens — сколько токенов поглощено;
  • Missing tokens — сколько токенов не хватило (нарушение структуры);
  • Remaining tokens — сколько токенов осталось лишних (избыточность).

На основе этих значений вычисляются:
  • Fitness (соответствие) — доля поведения лога, которое может быть
    воспроизведено моделью. Fitness = 1.0 означает полное соответствие.
  • Precision (точность) — доля поведения модели, которая реально
    встречается в логе. Precision = 1.0 означает, что модель не
    допускает лишних вариантов.
  • Generalization (обобщение) — способность модели объяснять новые
    кейсы, не входившие в обучающую выборку.
  • Simplicity (простота) — сложность модели (чем меньше узлов,
    тем выше показатель).
"""
from pathlib import Path
import pickle
import pandas as pd
import pm4py
import common


def main() -> None:
    """
    Загружает очищенный лог и ранее построенную модель (сеть Петри),
    выполняет token-based replay и сохраняет метрики соответствия.
    """
    events_path = common.TABLES / "events_all.csv"
    model_path = common.TABLES / "process_model.pkl"

    if not events_path.exists():
        raise FileNotFoundError(f"Файл не найден: {events_path}")
    if not model_path.exists():
        raise FileNotFoundError(
            f"Модель процесса не найдена: {model_path}. Запустите discovery.py"
        )

    print("[conformance] Загрузка модели и лога...")
    with open(model_path, "rb") as f:
        model_data = pickle.load(f)
    net = model_data["net"]
    im = model_data["im"]
    fm = model_data["fm"]

    df = pd.read_csv(events_path)
    case_col = common.PARAMS["case_column"]
    act_col = common.PARAMS["activity_column"]
    time_col = common.PARAMS["timestamp_column"]
    df[time_col] = pd.to_datetime(df[time_col], format="ISO8601", utc=True)

    log = pm4py.format_dataframe(df, case_id=case_col, activity_key=act_col, timestamp_key=time_col)

    # ── Token-Based Replay ──────────────────────────────────────────────────
    print("[conformance] Выполнение token-based replay...")
    try:
        fitness = pm4py.fitness_token_based_replay(log, net, im, fm)
        precision = pm4py.precision_token_based_replay(log, net, im, fm)

        # Извлекаем скалярные значения
        fitness_value = fitness.get("log_fitness", fitness.get("average_trace_fitness", 0.0))
        precision_value = precision if isinstance(precision, float) else precision.get("precision", 0.0)

        # Попытка получить дополнительные метрики (generalization, simplicity)
        # pm4py.evaluation может быть недоступен в некоторых версиях
        try:
            from pm4py.evaluation import evaluator as evaluator_module
            eval_result = evaluator_module.apply(log, net, im, fm)
            generalization = eval_result.get("generalization", None)
            simplicity = eval_result.get("simplicity", None)
        except Exception:
            generalization = None
            simplicity = None

        result = {
            "fitness": round(float(fitness_value), 4),
            "precision": round(float(precision_value), 4),
        }
        if generalization is not None:
            result["generalization"] = round(float(generalization), 4)
        if simplicity is not None:
            result["simplicity"] = round(float(simplicity), 4)

    except Exception as e:
        print(f"[conformance] Ошибка при token-based replay: {e}")
        # Fallback: если модель слишком сложная для replay,
        # сообщаем об этом явно, а не подставляем фиктивные числа.
        result = {
            "fitness": None,
            "precision": None,
            "error": str(e),
            "note": "Модель слишком сложна для полного token-based replay. "
                    "Рекомендуется упростить модель или использовать alignment-based метод."
        }

    # ── Сохранение результатов ──────────────────────────────────────────────
    import json
    out_path = common.TABLES / "model_quality.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    if result.get("fitness") is not None:
        print(f"[conformance] Fitness: {result['fitness']:.4f}")
        print(f"[conformance] Precision: {result['precision']:.4f}")
        if "generalization" in result:
            print(f"[conformance] Generalization: {result['generalization']:.4f}")
        if "simplicity" in result:
            print(f"[conformance] Simplicity: {result['simplicity']:.4f}")
    else:
        print(f"[conformance] Не удалось вычислить метрики: {result.get('note', '')}")
    print("[conformance] Проверка завершена!")


if __name__ == "__main__":
    main()
