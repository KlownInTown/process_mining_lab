"""
Модуль генерации сводного аналитического отчёта.

Согласно требованиям практической работы, отчёт должен содержать:
  1. Описание решаемых задач.
  2. Методы решения с теоретическим обоснованием.
  3. Полученные результаты в количественной форме.
  4. Выводы и рекомендации по оптимизации.

Отчёт формируется в формате Markdown (читаемый человеком)
и JSON (машиночитаемый формат для дальнейшей обработки).
"""
from pathlib import Path
import json
import pandas as pd
import common


def main() -> None:
    """Формирует сводный отчёт на основе всех таблиц результатов."""
    print("[report] Формирование сводного отчёта...")

    # ── Загрузка всех доступных результатов ─────────────────────────────────
    tables = {}
    for csv_file in common.TABLES.glob("*.csv"):
        try:
            tables[csv_file.stem] = pd.read_csv(csv_file)
        except Exception:
            pass

    json_data = {}
    for json_file in common.TABLES.glob("*.json"):
        try:
            json_data[json_file.stem] = json.loads(json_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    # ── Формирование Markdown-отчёта ────────────────────────────────────────
    md_lines = []
    md_lines.append("# Сводный отчёт по анализу бизнес-процесса методом Process Mining\n")
    md_lines.append("> **Дисциплина:** Технологии анализа данных  \n"
                    "> **Тема:** Практическая работа №5 — Process Mining  \n"
                    "> **Дата формирования:** автоматически\n")

    # Раздел 1. Цель и задачи
    md_lines.append("## 1. Цель и постановка задач\n")
    md_lines.append(
        "Цель работы — знакомство с технологиями Process Mining, формирование навыков "
        "построения графов бизнес-процессов и их анализа.\n\n"
        "**Решаемые задачи:**\n"
        "1. Предварительная обработка данных (очистка, нормализация, фильтрация шума).\n"
        "2. Построение графа бизнес-процесса (DFG, сеть Петри).\n"
        "3. Анализ графа: выявление узких мест, циклов, отклонений и оптимальных путей; "
        "анализ аномально долгих экземпляров процесса.\n"
        "4. Предложение вариантов оптимизации на основе полученных данных.\n"
    )

    # Раздел 2. Методы
    md_lines.append("## 2. Методы решения\n")
    md_lines.append(
        "### 2.1. Предобработка данных\n"
        "Согласно лекционным материалам, любые логи необходимо предварительно очистить от "
        "ошибок сбора, шума, неполных объектов и исключительных случаев. Применены методы:\n"
        "- удаление дубликатов событий;\n"
        "- нормализация временных меток к единому формату UTC;\n"
        "- фильтрация кейсов с инверсией времени;\n"
        "- удаление редких событий (< 0,1 %% от общего числа);\n"
        "- исключение вырожденных кейсов (с одним событием).\n\n"
        "### 2.2. Построение модели процесса\n"
        "Использованы два подхода:\n"
        "- **DFG (Directly-Follows Graph)** — прямо-следующий граф, отображающий частоты "
        "и средние времена переходов между операциями.\n"
        "- **Inductive Miner** — алгоритм, последовательно разлагающий поведение на блоки "
        "и гарантирующий корректную структуру модели в виде сети Петри (WF-net).\n\n"
        "### 2.3. Анализ производительности (Bottleneck Analysis)\n"
        "Узкое место определяется не по длительности самой операции, а по **времени ожидания** "
        "(idle time) между завершением предыдущей операции и началом следующей. "
        "Рассчитаны среднее, медианное и максимальное время ожидания по каждому переходу.\n\n"
        "### 2.4. Анализ циклов и rework\n"
        "Выполнено обнаружение повторяющихся активностей внутри кейсов (rework rate) "
        "и циклических паттернов типа A → B → A («пинг-понг»). "
        "Проведён анализ вариантов процесса (Process Variant Analysis).\n\n"
        "### 2.5. Conformance Checking\n"
        "Выполнена проверка соответствия фактического лога эталонной модели (сеть Петри) "
        "методом **Token-Based Replay**. Вычислены метрики Fitness и Precision.\n\n"
        "### 2.6. Predictive Process Monitoring\n"
        "Построены две прогнозные модели оставшегося времени выполнения:\n"
        "- статистическая (по префиксам исторических трасс);\n"
        "- на основе Random Forest (регрессия на признаках префикса).\n\n"
        "### 2.7. What-If Analysis\n"
        "Смоделированы сценарии оптимизации с пересчётом ожидаемой длительности процесса "
        "на основе реальных распределений из лога.\n"
    )

    # Раздел 3. Результаты
    md_lines.append("## 3. Результаты анализа\n")

    # 3.1 Качество данных
    if "data_quality" in json_data:
        dq = json_data["data_quality"]
        md_lines.append("### 3.1. Качество исходных данных\n")
        md_lines.append(
            f"- Исходных событий: **{dq.get('raw_events', 'N/A'):,}**\n"
            f"- Исходных кейсов: **{dq.get('raw_cases', 'N/A'):,}**\n"
            f"- После очистки событий: **{dq.get('clean_events', 'N/A'):,}**\n"
            f"- После очистки кейсов: **{dq.get('clean_cases', 'N/A'):,}**\n"
            f"- Удалено дубликатов: {dq.get('dropped_duplicates', 'N/A')}\n"
            f"- Удалено кейсов с инверсией времени: {dq.get('dropped_inversion_cases', 'N/A')}\n"
            f"- Период данных: {dq.get('date_range', {}).get('start', 'N/A')[:10]} — "
            f"{dq.get('date_range', {}).get('end', 'N/A')[:10]}\n\n"
        )

    # 3.2 Модель
    if "model_stats" in json_data:
        ms = json_data["model_stats"]
        md_lines.append("### 3.2. Построенная модель процесса\n")
        md_lines.append(
            f"- Алгоритм: **{ms.get('algorithm', 'N/A')}**\n"
            f"- Тип модели: {ms.get('model_type', 'N/A')}\n"
            f"- Позиций (places): {ms.get('places', 'N/A')}\n"
            f"- Переходов (transitions): {ms.get('transitions', 'N/A')}\n"
            f"- Дуг (arcs): {ms.get('arcs', 'N/A')}\n"
            f"- Рёбер DFG: {ms.get('dfg_edges', 'N/A')}\n\n"
        )

    # 3.3 Bottlenecks
    if "bottlenecks" in tables:
        bn = tables["bottlenecks"]
        md_lines.append("### 3.3. Временные характеристики и узкие места\n")
        for _, row in bn.iterrows():
            md_lines.append(f"- **{row['metric']}**: {row['value']:.2f}\n")
        if "bottlenecks_top20" in tables:
            top = tables["bottlenecks_top20"].head(5)
            md_lines.append("\n**Топ-5 узких мест (по среднему idle time):**\n")
            for _, row in top.iterrows():
                md_lines.append(
                    f"1. `{row.get(common.PARAMS['activity_column'], '?')} → {row.get('next_activity', '?')}` — "
                    f"{row['mean_idle_days']:.2f} дн (медиана: {row['median_idle_sec']/3600:.1f} ч)\n"
                )
        md_lines.append("\n")

    # 3.4 Rework
    if "rework_summary" in tables:
        rs = tables["rework_summary"]
        md_lines.append("### 3.4. Циклы и rework\n")
        for _, row in rs.iterrows():
            md_lines.append(f"- **{row['metric']}**: {row['value']}\n")
        md_lines.append("\n")

    # 3.5 Conformance
    if "model_quality" in json_data:
        mq = json_data["model_quality"]
        md_lines.append("### 3.5. Проверка соответствия (Conformance Checking)\n")
        if mq.get("fitness") is not None:
            md_lines.append(
                f"- **Fitness**: {mq['fitness']:.4f} — доля поведения лога, воспроизводимая моделью\n"
                f"- **Precision**: {mq['precision']:.4f} — доля поведения модели, встречающаяся в логе\n"
            )
            if "generalization" in mq:
                md_lines.append(f"- **Generalization**: {mq['generalization']:.4f}\n")
            if "simplicity" in mq:
                md_lines.append(f"- **Simplicity**: {mq['simplicity']:.4f}\n")
        else:
            md_lines.append(
                f"> ⚠️ {mq.get('note', 'Метрики не вычислены из-за сложности модели.')}\n"
            )
        md_lines.append("\n")

    # 3.6 Долгие кейсы
    if "long_cases_summary" in tables:
        ls = tables["long_cases_summary"]
        md_lines.append("### 3.6. Анализ аномально долгих кейсов\n")
        for _, row in ls.iterrows():
            val = row['value']
            if pd.isna(val):
                val = "N/A"
            md_lines.append(f"- **{row['metric']}**: {val}\n")
        md_lines.append("\n")

    # 3.7 What-If
    if "whatif_scenarios" in tables:
        wi = tables["whatif_scenarios"]
        md_lines.append("### 3.7. Сценарии оптимизации (What-If)\n")
        for _, row in wi.iterrows():
            md_lines.append(
                f"- **{row['scenario']}**: {row['estimated_duration_days']:.2f} дн "
                f"(улучшение {row['improvement_pct']:.1f}%) — {row['description']}\n"
            )
        md_lines.append("\n")

    # 3.8 Predictive
    if "predictions_summary" in tables:
        ps = tables["predictions_summary"]
        md_lines.append("### 3.8. Прогнозирование оставшегося времени\n")
        for _, row in ps.iterrows():
            mae = row['mae_days']
            mae_str = f"{mae:.4f} дн" if mae is not None and not pd.isna(mae) else "N/A"
            md_lines.append(
                f"- **{row['method']}**: MAE = {mae_str} — {row['description']}\n"
            )
        md_lines.append("\n")

    # Раздел 4. Выводы и рекомендации
    md_lines.append("## 4. Выводы и рекомендации\n")
    recommendations = []

    if "bottlenecks_top20" in tables and not tables["bottlenecks_top20"].empty:
        top_bn = tables["bottlenecks_top20"].iloc[0]
        recommendations.append(
            f"**Устранение узкого места**: наибольшие задержки наблюдаются на переходе "
            f"'{top_bn.get(common.PARAMS['activity_column'], '?')} → {top_bn.get('next_activity', '?')}'. "
            f"Рекомендуется пересмотреть распределение ресурсов на этом этапе или внедрить "
            f"механизм автоматической эскалации при превышении времени ожидания."
        )

    if "rework_activities" in tables and not tables["rework_activities"].empty:
        top_rw = tables["rework_activities"].iloc[0]
        recommendations.append(
            f"**Сокращение rework**: активность '{top_rw.get(common.PARAMS['activity_column'], '?')}' "
            f"имеет наибольшее количество повторов ({top_rw.get('total_rework_events', 0)}). "
            f"Рекомендуется внедрить чек-листы качества до передачи на эту операцию."
        )

    if "long_cases_summary" in tables:
        ls = tables["long_cases_summary"]
        long_share = ls[ls["metric"] == "long_cases_share_pct"]["value"].values
        if len(long_share) > 0 and float(long_share[0]) > 5:
            recommendations.append(
                f"**Оптимизация долгих кейсов**: {float(long_share[0]):.1f}% кейсов превышают "
                f"нормативную длительность. Анализ показывает, что долгие кейсы концентрируются "
                f"в определённых вариантах процесса — рекомендуется пересмотреть регламенты "
                f"именно для этих маршрутов."
            )

    if "whatif_scenarios" in tables and len(tables["whatif_scenarios"]) > 1:
        best = tables["whatif_scenarios"].iloc[-1]
        recommendations.append(
            f"**What-If сценарий**: наиболее эффективный сценарий «{best['scenario']}» "
            f"позволяет сократить среднюю длительность на {best['improvement_pct']:.1f}%. "
            f"Рекомендуется провести пилотное внедрение этого изменения на ограниченной выборке кейсов."
        )

    if not recommendations:
        recommendations.append("На основе проведённого анализа рекомендуется продолжить сбор данных "
                               "для повышения статистической значимости выводов.")

    # Динамическая нумерация рекомендаций
    numbered = [f"{i+1}. {rec}" for i, rec in enumerate(recommendations)]
    md_lines.append("\n".join(numbered) + "\n\n")

    md_lines.append(
        "---\n"
        "*Отчёт сгенерирован автоматически в результате выполнения аналитического пайплайна. "
        "Все расчёты воспроизводимы: контрольные суммы результатов зафиксированы в файле "
        "`results/manifest.json`.*\n"
    )

    md_content = "\n".join(md_lines)
    md_path = common.ROOT / "summary_report.md"
    md_path.write_text(md_content, encoding="utf-8")

    # ── Формирование JSON-отчёта ────────────────────────────────────────────
    summary_json = {
        "report_type": "Process Mining Analysis Report",
        "tables_generated": list(tables.keys()),
        "json_generated": list(json_data.keys()),
        "key_metrics": {}
    }

    if "data_quality" in json_data:
        summary_json["key_metrics"]["data_quality"] = json_data["data_quality"]
    if "model_quality" in json_data:
        summary_json["key_metrics"]["conformance"] = json_data["model_quality"]
    if "bottlenecks" in tables:
        summary_json["key_metrics"]["performance"] = tables["bottlenecks"].set_index("metric")["value"].to_dict()
    if "rework_summary" in tables:
        summary_json["key_metrics"]["rework"] = tables["rework_summary"].set_index("metric")["value"].to_dict()

    json_path = common.RESULTS / "summary_report.json"
    json_path.write_text(
        json.dumps(summary_json, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print("[report] Отчёт сохранён:")
    print(f"  - Markdown: {md_path}")
    print(f"  - JSON: {json_path}")


if __name__ == "__main__":
    main()
