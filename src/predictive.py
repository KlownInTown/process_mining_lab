"""
Модуль прогнозного мониторинга (Predictive Process Monitoring).

Согласно лекции, Predictive Process Monitoring — это направление Process Mining,
при котором на основе исторических журналов событий и текущего состояния
процесса прогнозные модели оценивают оставшееся время выполнения,
вероятность нарушения установленного срока или риск возникновения
нежелательного события.

В данном модуле реализованы два подхода:
  1. Статистический (Prefix-Based): для каждого незавершённого кейса
     берётся его префикс (выполненные активности), и по историческим
     данным находится среднее оставшееся время для кейсов с таким же
     префиксом. Это baseline-метод, не требующий ML.
  2. Машинное обучение (Random Forest): строится регрессионная модель,
     предсказывающая оставшееся время на основе признаков префикса:
       • длина префикса (сколько шагов выполнено);
       • текущая длительность (время от начала кейса);
       • частота текущей активности в истории;
       • энтропия распределения активностей в префиксе.

Оба метода сравниваются по метрике MAE (Mean Absolute Error)
на отложенной выборке (train/test split 80/20).
"""
from pathlib import Path
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error
import common


def main() -> None:
    """
    Строит прогнозные модели оставшегося времени выполнения кейсов
    и сохраняет результаты сравнения.
    """
    events_path = common.TABLES / "events_all.csv"
    if not events_path.exists():
        raise FileNotFoundError(f"Файл не найден: {events_path}")

    print("[predictive] Построение прогнозных моделей...")
    df = pd.read_csv(events_path)
    case_col = common.PARAMS["case_column"]
    act_col = common.PARAMS["activity_column"]
    time_col = common.PARAMS["timestamp_column"]
    df[time_col] = pd.to_datetime(df[time_col], format="ISO8601", utc=True)
    df = df.sort_values(by=[case_col, time_col])

    # ── 1. Подготовка данных: каждый кейс → префиксы ────────────────────────
    # Для каждого события (кроме последнего) формируем префикс и
    # вычисляем оставшееся время до конца кейса.
    case_groups = df.groupby(case_col)
    records = []

    for case_id, group in case_groups:
        group = group.reset_index(drop=True)
        total_duration = (group[time_col].max() - group[time_col].min()).total_seconds()
        for i in range(len(group)):
            prefix = group.iloc[:i+1]
            current_time = prefix[time_col].iloc[-1]
            start_time = prefix[time_col].iloc[0]
            remaining_time = (group[time_col].max() - current_time).total_seconds()
            records.append({
                case_col: case_id,
                "prefix_length": i + 1,
                "current_activity": prefix[act_col].iloc[-1],
                "elapsed_sec": (current_time - start_time).total_seconds(),
                "remaining_sec": remaining_time,
                "prefix_activities": " → ".join(prefix[act_col].astype(str).tolist()),
                "total_duration_sec": total_duration,
            })

    data = pd.DataFrame(records)

    # ── 2. Статистический прогноз (Prefix-Based) ────────────────────────────
    # Для каждого уникального префикса вычисляем среднее оставшееся время.
    prefix_means = (
        data.groupby("prefix_activities")["remaining_sec"]
        .mean()
        .reset_index(name="pred_remaining_stat_sec")
    )
    data = data.merge(prefix_means, on="prefix_activities", how="left")

    # ── 3. ML-модель (Random Forest) ────────────────────────────────────────
    # Инженерия признаков
    data["current_activity_freq"] = data.groupby("current_activity")["current_activity"].transform("count")
    # Энтропия распределения активностей в префиксе (степень неопределённости)
    def entropy(activities_str):
        acts = activities_str.split(" → ")
        counts = pd.Series(acts).value_counts(normalize=True)
        return -np.sum(counts * np.log2(counts + 1e-10))

    data["prefix_entropy"] = data["prefix_activities"].apply(entropy)

    # Признаки
    feature_cols = [
        "prefix_length",
        "elapsed_sec",
        "current_activity_freq",
        "prefix_entropy",
    ]
    # One-hot encoding для текущей активности
    activity_dummies = pd.get_dummies(data["current_activity"], prefix="act")
    X = pd.concat([data[feature_cols], activity_dummies], axis=1)
    y = data["remaining_sec"].values

    # Разделение на обучение и тест
    if len(data) < 50:
        print("[predictive] Недостаточно данных для ML-модели (< 50 префиксов).")
        ml_mae = None
        data["pred_remaining_ml_sec"] = np.nan
    else:
        X_train, X_test, y_train, y_test, idx_train, idx_test = train_test_split(
            X, y, np.arange(len(X)), test_size=0.2, random_state=42
        )
        model = RandomForestRegressor(n_estimators=100, random_state=42, n_jobs=-1)
        model.fit(X_train, y_train)
        y_pred = model.predict(X_test)
        ml_mae = mean_absolute_error(y_test, y_pred)

        # Предсказания для всех данных
        data["pred_remaining_ml_sec"] = model.predict(X)

    # ── 4. Оценка статистического метода ────────────────────────────────────
    stat_mae = mean_absolute_error(
        data["remaining_sec"], data["pred_remaining_stat_sec"]
    )

    # ── 5. Пример прогнозов для незавершённых кейсов ────────────────────────
    # Берём последнее событие каждого кейса как «текущее состояние»
    last_events = data.drop_duplicates(subset=[case_col], keep="last").copy()
    last_events["remaining_days"] = last_events["remaining_sec"] / (24 * 3600)
    last_events["pred_stat_days"] = last_events["pred_remaining_stat_sec"] / (24 * 3600)
    if ml_mae is not None:
        last_events["pred_ml_days"] = last_events["pred_remaining_ml_sec"] / (24 * 3600)

    predictions = last_events[[
        case_col,
        "prefix_length",
        "current_activity",
        "elapsed_sec",
        "remaining_sec",
        "remaining_days",
        "pred_remaining_stat_sec",
        "pred_stat_days",
    ]].copy()
    if ml_mae is not None:
        predictions["pred_remaining_ml_sec"] = last_events["pred_remaining_ml_sec"]
        predictions["pred_ml_days"] = last_events["pred_ml_days"]

    predictions.to_csv(common.TABLES / "predictions.csv", index=False, encoding="utf-8")

    # ── 6. Сводная статистика ───────────────────────────────────────────────
    summary = {
        "method": ["Statistical (Prefix-Based)", "Machine Learning (Random Forest)"],
        "mae_sec": [round(stat_mae, 2), round(ml_mae, 2) if ml_mae is not None else None],
        "mae_days": [
            round(stat_mae / (24 * 3600), 4),
            round(ml_mae / (24 * 3600), 4) if ml_mae is not None else None,
        ],
        "description": [
            "Среднее оставшееся время по историческим кейсам с идентичным префиксом",
            "Случайный лес на признаках префикса (длина, энтропия, elapsed time)",
        ]
    }
    summary_df = pd.DataFrame(summary)
    summary_df.to_csv(
        common.TABLES / "predictions_summary.csv", index=False, encoding="utf-8"
    )

    print(f"[predictive] Префиксов для обучения: {len(data):,}")
    print(f"[predictive] MAE (статистический): {stat_mae/3600:.2f} часов")
    if ml_mae is not None:
        print(f"[predictive] MAE (Random Forest): {ml_mae/3600:.2f} часов")
    print("[predictive] Прогнозирование завершено!")


if __name__ == "__main__":
    main()
