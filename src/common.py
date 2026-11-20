"""
Модуль общих конфигураций, путей и вспомогательных функций.

Process Mining (интеллектуальный анализ процессов) — это аналитический подход,
направленный на объективное восстановление, визуализацию и анализ фактического
исполнения бизнес-процессов на основе цифровых следов (журналов событий),
которые остаются в информационных системах (ERP, CRM, SCM и др.).

Для успешного анализа необходимы три ключевых атрибута в журнале событий:
  • Case ID — идентификатор экземпляра процесса (например, ID заявки).
  • Activity — выполняемое действие (событие/статус).
  • Timestamp — временная метка наступления события.
"""
from pathlib import Path
import hashlib
import json

# ── Пути проекта ─────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RESULTS = ROOT / "results"
TABLES = RESULTS / "tables"
FIGURES = RESULTS / "figures"

# ── Конфигурация колонок ─────────────────────────────────────────────────────
# В формате XES стандартные названия полей имеют префиксы пространства имён.
PARAMS = {
    "timestamp_column": "time:timestamp",
    "case_column": "case:concept:name",
    "activity_column": "concept:name",
    "resource_column": "org:resource",  # опционально, если есть в логе
}

# ── Исключения ───────────────────────────────────────────────────────────────
class ConfigError(Exception):
    """Исключение при ошибках конфигурации или параметров обработки."""
    pass


class DataQualityError(Exception):
    """Исключение при обнаружении критических проблем с качеством данных."""
    pass


# ── Вспомогательные функции ──────────────────────────────────────────────────
def sha256(file_path: Path) -> str:
    """
    Вычисляет контрольную сумму SHA-256 для указанного файла.
    
    Контрольные суммы позволяют проверять воспроизводимость расчётов:
    при повторном запуске пайплайна на тех же исходных данных
    хэши результирующих файлов должны совпадать.
    """
    sha = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(8192):
            sha.update(chunk)
    return sha.hexdigest()


def validate(params: dict) -> None:
    """
    Проверяет корректность инициализации рабочих директорий и параметров.
    
    Вызывается перед началом пайплайна, чтобы гарантировать,
    что все необходимые пути существуют, а обязательные параметры заданы.
    """
    TABLES.mkdir(parents=True, exist_ok=True)
    FIGURES.mkdir(parents=True, exist_ok=True)
    if not params.get("case_column"):
        raise ConfigError("Не задан обязательный параметр идентификатора кейса (case_column).")
    if not params.get("activity_column"):
        raise ConfigError("Не задан обязательный параметр активности (activity_column).")
    if not params.get("timestamp_column"):
        raise ConfigError("Не задан обязательный параметр временной метки (timestamp_column).")


def write_manifest() -> None:
    """
    Формирует файл manifest.json с контрольными суммами всех таблиц результатов.
    
    Манифест фиксирует состояние артефактов анализа и позволяет:
      • подтвердить воспроизводимость расчётов;
      • отследить изменения между запусками;
      • предоставить преподавателю доказательство целостности результатов.
    """
    manifest_data = {}
    if TABLES.exists():
        for p in sorted(TABLES.iterdir()):
            if p.is_file():
                manifest_data[p.name] = sha256(p)
    manifest_path = RESULTS / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n"
    )
