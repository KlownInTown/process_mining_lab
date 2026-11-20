"""
Главный скрипт пайплайна Process Mining.

Выполняет полный цикл аналитической обработки бизнес-процесса:
  1. Предобработка данных (очистка, нормализация).
  2. Построение моделей процесса (DFG, сеть Петри).
  3. Анализ производительности и узких мест (Bottleneck Analysis).
  4. Анализ циклов, rework и вариантов (Rework Analysis).
  5. Проверка соответствия модели логу (Conformance Checking).
  6. Выявление аномально долгих кейсов.
  7. Сценарное моделирование оптимизаций (What-If Analysis).
  8. Генерация аналитических графиков.
  9. Прогнозирование оставшегося времени (Predictive Monitoring).
  10. Формирование сводного отчёта.

По завершении формируется файл results/manifest.json с контрольными суммами
SHA-256 всех результирующих таблиц, что обеспечивает воспроизводимость расчётов.
"""
import json
import sys
import time
from pathlib import Path

# Корректная настройка пути: скрипт находится в src/, импортируем модули отсюда
sys.path.insert(0, str(Path(__file__).resolve().parent))

import common

# Импорт всех модулей пайплайна
import charts
import conformance
import discovery
import long_cases
import performance
import prepare
import predictive
import report
import rework
import whatif

# Определение этапов пайплайна: (название, функция_main)
STEPS = [
    ("1. Предварительная обработка журнала событий", prepare.main),
    ("2. Генерация графовых моделей процесса", discovery.main),
    ("3. Оценка временных характеристик и узких мест", performance.main),
    ("4. Исследование циклов, вариантов и переделок", rework.main),
    ("5. Верификация соответствия фактического процесса эталонному", conformance.main),
    ("6. Выявление затянутых экземпляров процесса", long_cases.main),
    ("7. Моделирование оптимизационных сценариев", whatif.main),
    ("8. Построение графических визуализаций", charts.main),
    ("9. Прогнозирование оставшегося времени незавершённых кейсов", predictive.main),
    ("10. Генерация сводного аналитического отчёта", report.main),
]


def main() -> int:
    """
    Запускает последовательное исполнение всех аналитических этапов.
    
    Returns:
        0 при успешном завершении, 1 при критической ошибке.
    """
    try:
        # Валидация параметров и директорий
        common.validate(common.PARAMS)
        
        began = time.perf_counter()
        print("=" * 60)
        print("Process Mining Pipeline — Практическая работа №5")
        print("=" * 60)

        for title, step in STEPS:
            print(f"\n{'─' * 60}")
            print(title)
            print("─" * 60)
            step()

        # Формирование манифеста с контрольными суммами
        common.write_manifest()

        elapsed = time.perf_counter() - began
        print(f"\n{'=' * 60}")
        print(f"Обработка завершена за {elapsed:.0f} сек.")
        print(f"Результаты:  tables  → {common.TABLES}")
        print(f"            figures → {common.FIGURES}")
        print(f"            report  → {common.ROOT / 'summary_report.md'}")
        print("=" * 60)
        return 0

    except (common.ConfigError, FileNotFoundError, ValueError) as err:
        print(f"\n[ERROR] Критический сбой выполнения: {err}", file=sys.stderr)
        return 1
    except Exception as err:
        print(f"\n[ERROR] Неожиданная ошибка: {err}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
