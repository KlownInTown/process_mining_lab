# Process Mining Lab — Практическая работа №5

Аналитический пайплайн для выполнения практической работы по дисциплине **«Технологии анализа данных»** на тему **Process Mining**.

## Структура проекта

```
process_mining_lab/
├── data/                       # Исходные данные (XES-логи)
│   └── financial_log.xes       # Пример финансового лога
├── src/                        # Исходный код пайплайна
│   ├── run_all.py              # Главный скрипт запуска
│   ├── common.py               # Общие конфигурации и утилиты
│   ├── prepare.py              # Предобработка данных
│   ├── discovery.py            # Построение моделей (DFG, сеть Петри)
│   ├── performance.py          # Анализ узких мест (Bottleneck Analysis)
│   ├── rework.py               # Анализ циклов и вариантов (Rework Analysis)
│   ├── conformance.py          # Проверка соответствия (Conformance Checking)
│   ├── long_cases.py           # Анализ долгих кейсов
│   ├── whatif.py               # Сценарное моделирование (What-If)
│   ├── predictive.py           # Прогнозирование оставшегося времени
│   ├── charts.py               # Визуализации (matplotlib / seaborn)
│   ├── graphs.py               # Визуализация DFG (graphviz)
│   └── report.py               # Генерация сводного отчёта
├── results/                    # Результаты анализа
│   ├── tables/                 # Таблицы CSV / JSON
│   └── figures/                # Графики и диаграммы PNG
├── requirements.txt            # Зависимости Python
├── summary_report.md           # Сводный отчёт (генерируется автоматически)
└── README.md                   # Этот файл
```

## Установка зависимостей

```bash
pip install -r requirements.txt
```

> **Примечание:** для рендеринга графов DFG и сетей Петри в PNG требуется системный пакет **Graphviz**.
> - **Ubuntu/Debian:** `sudo apt-get install graphviz`
> - **macOS:** `brew install graphviz`
> - **Windows:** скачайте установщик с [graphviz.org](https://graphviz.org/download/)
>
> Если Graphviz недоступен, пайплайн сохранит DOT-файлы, которые можно открыть
> в онлайн-редакторах (например, [Edotor](https://edotor.net/)).

## Запуск

### Полный пайплайн

```bash
python src/run_all.py
```

После выполнения в папке `results/` появятся:
- `tables/` — CSV-таблицы с результатами каждого этапа;
- `figures/` — PNG-графики и DOT-файлы;
- `manifest.json` — контрольные суммы SHA-256 для проверки воспроизводимости.

### Запуск отдельных модулей

```bash
python src/prepare.py        # Только предобработка
python src/discovery.py      # Только построение моделей
python src/performance.py    # Только анализ производительности
# и т.д.
```

## Реализованные задачи практической работы

| Задача | Модуль | Описание |
|--------|--------|----------|
| **1. Предобработка** | `prepare.py` | Очистка от дубликатов, нормализация таймзон, фильтрация инверсий времени, удаление редких событий и вырожденных кейсов |
| **2. Построение графа** | `discovery.py` | DFG (частотный + временной), сеть Петри через Inductive Miner, BPMN-экспорт |
| **3a. Узкие места** | `performance.py` | Idle time по переходам, топ-20 bottleneck, SLA compliance |
| **3б. Циклы / rework** | `rework.py` | Обнаружение повторов, циклические паттерны (A→B→A), варианты процесса |
| **3в. Отклонения** | `conformance.py` | Token-Based Replay: Fitness, Precision, Generalization, Simplicity |
| **3г. Долгие кейсы** | `long_cases.py` | IQR-метод выявления выбросов, анализ вариантов долгих кейсов |
| **4. Оптимизация** | `whatif.py` | Сценарии на основе реальных данных: устранение bottleneck, сокращение rework, автоматизация |
| **Доп. Прогнозирование** | `predictive.py` | Prefix-based прогноз + Random Forest регрессия оставшегося времени |
| **Доп. Визуализация** | `charts.py` | Гистограммы, heatmap idle time, сравнение вариантов, What-If диаграммы |
| **Отчёт** | `report.md` | Полноценный Markdown-отчёт с теорией, методами, результатами и рекомендациями |

## Воспроизводимость

Все результаты фиксируются в `results/manifest.json` с контрольными суммами SHA-256.
При повторном запуске на тех же исходных данных хэши должны совпадать
(при условии детерминированного порядка обработки).

## Источники

- Лекция 7: «Process Mining» (Михалев)
- Практическая работа №5: «Process Mining»
- Библиотека: [pm4py](https://pm4py.fit.fraunhofer.de/)
