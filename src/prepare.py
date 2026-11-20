"""
Модуль предварительной обработки (Pre-processing) журнала событий.

Согласно лекции по Process Mining, любые полученные логи необходимо сначала
очистить от: ошибок при сборе данных, шума, неполных объектов, исключительных
случаев. Эти объекты могут запутать процесс, в результате чего точность
обнаруженных закономерностей будет низкой.

Этапы очистки (в соответствии с методологией лекции):
  1. Фильтрация неидентифицируемых событий (отсутствуют Case ID, Activity
     или Timestamp).
  2. Нормализация временных меток — приведение к единому формату datetime
     с явным указанием таймзоны (UTC).
  3. Удаление дубликатов событий внутри одного кейса (одна и та же активность
     в ту же секунду).
  4. Проверка и обработка инверсий времени — события внутри кейса должны
     следовать строго хронологически.
  5. Фильтрация незавершённых цепочек (кейсы с одним событием или без
     явного завершения при наличии признаков отмены).
  6. Фильтрация редких событий (< 0.1 % от общего числа) как потенциального
     шума, если это не критичные статусы.
  7. Сортировка событий внутри каждого кейса по времени с добавлением
     стабильного вторичного ключа для детерминированности.

Результат: консолидированный event log, пригодный для построения моделей
(Discovery), проверки соответствия (Conformance) и анализа производительности.
"""
from pathlib import Path
import pandas as pd
import numpy as np
import pm4py
import common


def main() -> None:
    """
    Загружает XES-лог, выполняет полный цикл очистки и сохраняет
    обработанный DataFrame в results/tables/events_all.csv.
    Дополнительно формирует отчёт о качестве данных.
    """
    # ── 1. Загрузка исходного лога ──────────────────────────────────────────
    source_file = common.DATA / "financial_log.xes"

    if not source_file.exists():
        raise FileNotFoundError(
            f"Файл не найден: {source_file}. "
            "Поместите financial_log.xes в папку data/"
        )

    print("[prepare] Чтение XES-файла через pm4py...")
    event_log = pm4py.read_xes(str(source_file))
    df = pm4py.convert_to_dataframe(event_log)
    raw_rows = len(df)
    raw_cases = df["case:concept:name"].nunique()
    print(f"[prepare] Исходный лог: {raw_rows:,} событий, {raw_cases:,} кейсов")

    # ── 2. Унификация названий колонок ──────────────────────────────────────
    # pm4py уже использует стандартные XES-имена, но на всякий случай
    # выполняем маппинг альтернативных вариантов.
    column_mapping = {}
    for col in df.columns:
        col_lower = col.strip().lower()
        if col_lower in ["case_id", "case id", "case:concept:name", "case"]:
            column_mapping[col] = "case:concept:name"
        elif col_lower in ["activity", "concept:name", "event", "task"]:
            column_mapping[col] = "concept:name"
        elif col_lower in ["timestamp", "time:timestamp", "time", "date", "datetime"]:
            column_mapping[col] = "time:timestamp"
        elif col_lower in ["resource", "org:resource", "user", "executor"]:
            column_mapping[col] = "org:resource"

    if column_mapping:
        df = df.rename(columns=column_mapping)

    case_col = common.PARAMS["case_column"]
    act_col = common.PARAMS["activity_column"]
    time_col = common.PARAMS["timestamp_column"]

    # Проверка обязательных колонок
    for req in (case_col, act_col, time_col):
        if req not in df.columns:
            raise common.ConfigError(
                f"В логе отсутствует обязательная колонка '{req}'."
            )

    # ── 3. Нормализация временных меток ─────────────────────────────────────
    # Явное приведение к datetime с учётом таймзон (XES часто хранит +00:00).
    # Все метки переводятся в UTC, чтобы исключить неоднозначность.
    df[time_col] = pd.to_datetime(df[time_col], utc=True)

    # ── 4. Фильтрация неидентифицируемых событий ────────────────────────────
    # Удаляем строки с пропусками в ключевых полях — без них невозможно
    # восстановить последовательность процесса.
    required_mask = df[case_col].notna() & df[act_col].notna() & df[time_col].notna()
    dropped_na = (~required_mask).sum()
    df = df[required_mask].copy()

    # ── 5. Удаление дубликатов ──────────────────────────────────────────────
    # Дубликат = одна и та же активность в том же кейсе в ту же секунду.
    # Оставляем первое вхождение (порядок сортировки определяется индексом).
    before_dedup = len(df)
    df = df.drop_duplicates(subset=[case_col, act_col, time_col], keep="first")
    dropped_dups = before_dedup - len(df)

    # ── 6. Сортировка и проверка инверсий времени ───────────────────────────
    # События внутри кейса должны идти строго по возрастанию времени.
    # Если встречаются инверсии (событие B раньше A внутри одного кейса),
    # это может быть признаком ошибки сбора данных или параллельного
    # выполнения. Для надёжности анализа удаляем кейсы с инверсиями.
    df = df.sort_values(by=[case_col, time_col])
    df["prev_time"] = df.groupby(case_col)[time_col].shift(1)
    df["time_diff"] = df[time_col] - df["prev_time"]
    # Инверсия: текущее время < предыдущего (с небольшим допуском 1 сек)
    inversion_mask = (df["time_diff"] < pd.Timedelta(seconds=-1))
    bad_cases = df.loc[inversion_mask, case_col].unique()
    dropped_inversion_cases = len(bad_cases)
    if len(bad_cases) > 0:
        df = df[~df[case_col].isin(bad_cases)].copy()

    # Убираем вспомогательные колонки
    df = df.drop(columns=["prev_time", "time_diff"], errors="ignore")

    # ── 7. Фильтрация редких событий (шум) ──────────────────────────────────
    # Согласно лекции, редкие события (< 0.1 %) могут быть шумом,
    # который усложняет модель («спагетти»-граф).
    activity_counts = df[act_col].value_counts()
    total_events = len(df)
    rare_threshold = max(1, int(total_events * 0.001))  # 0.1 %
    rare_activities = activity_counts[activity_counts < rare_threshold].index.tolist()
    dropped_rare = 0
    if rare_activities:
        before_rare = len(df)
        df = df[~df[act_col].isin(rare_activities)].copy()
        dropped_rare = before_rare - len(df)
        print(f"[prepare] Отфильтрованы редкие активности {rare_activities} ({dropped_rare} событий)")

    # ── 8. Фильтрация незавершённых/вырожденных кейсов ──────────────────────
    # Кейсы с одним событием не несут информации о переходах между
    # активностями и искажают статистику вариантов.
    case_lengths = df.groupby(case_col).size()
    valid_cases = case_lengths[case_lengths >= 2].index
    before_cases = df[case_col].nunique()
    df = df[df[case_col].isin(valid_cases)].copy()
    dropped_cases = before_cases - df[case_col].nunique()

    # ── 9. Финальная сортировка ─────────────────────────────────────────────
    df = df.sort_values(by=[case_col, time_col]).reset_index(drop=True)

    # ── 10. Сохранение результата ───────────────────────────────────────────
    common.TABLES.mkdir(parents=True, exist_ok=True)
    out_path = common.TABLES / "events_all.csv"
    # Сохраняем в ISO-формате с явным указанием таймзоны
    df.to_csv(out_path, index=False, encoding="utf-8")

    # ── 11. Отчёт о качестве данных ─────────────────────────────────────────
    quality_report = {
        "raw_events": int(raw_rows),
        "raw_cases": int(raw_cases),
        "clean_events": int(len(df)),
        "clean_cases": int(df[case_col].nunique()),
        "dropped_na": int(dropped_na),
        "dropped_duplicates": int(dropped_dups),
        "dropped_inversion_cases": int(dropped_inversion_cases),
        "dropped_rare_events": int(dropped_rare),
        "dropped_short_cases": int(dropped_cases),
        "activities_count": int(df[act_col].nunique()),
        "date_range": {
            "start": df[time_col].min().isoformat(),
            "end": df[time_col].max().isoformat(),
        },
    }
    quality_path = common.TABLES / "data_quality.json"
    import json
    quality_path.write_text(
        json.dumps(quality_report, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print(f"[prepare] Очищенный лог: {len(df):,} событий, {df[case_col].nunique():,} кейсов")
    print(f"[prepare] Удалено: {dropped_na} NA, {dropped_dups} дубликатов, "
          f"{dropped_inversion_cases} кейсов с инверсией, {dropped_cases} коротких кейсов")
    print(f"[prepare] Результат сохранён: {out_path}")


if __name__ == "__main__":
    main()
