"""
Модуль визуализации графовых моделей процессов.

Обеспечивает построение и сохранение графических схем в формате PNG
на основе DOT-описаний с использованием библиотеки graphviz.

В Process Mining визуализация играет ключевую роль: восстановленная модель
процесса должна быть не только математически корректной, но и наглядной
для аналитика. DFG (Directly-Follows Graph) позволяет на одном полотне
увидеть, как реально ходят кейсы, где возникают развилки, возвраты и задержки.
"""
from pathlib import Path
import graphviz
from common import FIGURES

FONT = "Arial"
DAY_COLORS = ["#2e7d32", "#f9a825", "#ef6c00", "#c62828"]
DAY_LIMITS = (0.1, 1, 3)


def render_dot(source: str, name: str, dpi: int = 150) -> None:
    """
    Выполняет рендеринг строки описания графа в формате DOT
    и сохраняет результат в файл PNG.
    """
    FIGURES.mkdir(parents=True, exist_ok=True)
    if "graph [" in source:
        source = source.replace("graph [", f"graph [dpi={dpi}, ")
    else:
        source = source.replace("digraph G {", f"digraph G {{\ngraph [dpi={dpi}];")

    src = graphviz.Source(source)
    src.render(filename=name, directory=str(FIGURES), format="png", cleanup=True)


def render_gviz(gviz, name: str, dpi: int = 150, rankdir: str = None) -> None:
    """Преобразует объект графа pm4py в графическое изображение PNG."""
    source = gviz.source
    if rankdir:
        source = source.replace("rankdir=LR", f"rankdir={rankdir}")
    render_dot(source, name, dpi)


def wrap(text: str) -> str:
    """
    Выполняет перенос длинного наименования события на две строки
    для компактности отображения на графе.
    """
    words = text.split()
    if len(text) < 16 or len(words) < 2:
        return text
    cut = min(range(1, len(words)), key=lambda i: abs(len(" ".join(words[:i])) - len(text) / 2))
    return " ".join(words[:cut]) + "\\n" + " ".join(words[cut:])


def edge_color(days: float) -> str:
    """
    Определяет цветовую маркировку ребра в зависимости от длительности перехода.
    
    Шкала:
      < 0.1 дн (2.4 ч) — зелёный (норма)
      < 1 дн — жёлтый (внимание)
      < 3 дн — оранжевый (задержка)
      >= 3 дн — красный (критическое узкое место)
    """
    for color, limit in zip(DAY_COLORS, DAY_LIMITS):
        if days < limit:
            return color
    return DAY_COLORS[-1]


def fmt_days(d: float) -> str:
    """Форматирует числовое значение дней в удобочитаемый временной интервал."""
    if d < 1 / 24:
        return f"{d * 1440:.0f} мин"
    if d < 1:
        return f"{d * 24:.1f} ч".replace(".", ",")
    return f"{d:.1f} дн".replace(".", ",")


def dfg_dot(nodes: dict, edges, mode: str, starts: dict, ends: dict) -> str:
    """
    Формирует текстовое DOT-описание графа прямого следования (DFG).
    
    Args:
        nodes: словарь {activity: frequency} для размера узлов.
        edges: список кортежей (from, to, frequency, days).
        mode: "freq" — частотный режим, "perf" — временной режим.
        starts: словарь начальных активностей {activity: count}.
        ends: словарь конечных активностей {activity: count}.
    
    Returns:
        Строка с описанием графа в формате DOT.
    """
    top = max(e[2] for e in edges) if edges else 1
    node_max = max(nodes.values()) if nodes else 1
    lines = [
        'digraph G { rankdir=TB; nodesep=0.35; ranksep=0.5; bgcolor="white";',
        f'node [shape=box, style="rounded,filled", fontname="{FONT}", fontsize=12, margin="0.12,0.06"];',
        f'edge [fontname="{FONT}", fontsize=11, arrowsize=0.75];',
        'start [label="", shape=circle, width=0.25, style=filled, fillcolor="#2e7d32"];',
        'finish [label="", shape=doublecircle, width=0.2, style=filled, fillcolor="#c62828"];'
    ]
    ids = {a: f"n{i}" for i, a in enumerate(nodes)}
    for a, n in nodes.items():
        tone = int(235 - 95 * n / node_max) if node_max > 0 else 235
        lines.append(
            f'{ids[a]} [label="{wrap(a)}\\n({n})", fillcolor="#{tone:02x}{tone:02x}ff"];'
        )
    for a, n in starts.items():
        if a in ids:
            lines.append(f'start -> {ids[a]} [label=" {n}", color="#2e7d32"];')
    for a, n in ends.items():
        if a in ids:
            lines.append(f'{ids[a]} -> finish [label=" {n}", color="#c62828"];')
    for a, b, n, days in edges:
        if a in ids and b in ids:
            width = 0.7 + 4.5 * (n / top) ** 0.6 if top > 0 else 1.0
            if mode == "freq":
                lines.append(
                    f'{ids[a]} -> {ids[b]} [label=" {n}", penwidth={width:.2f}];'
                )
            else:
                color = edge_color(days)
                lines.append(
                    f'{ids[a]} -> {ids[b]} [label=" {fmt_days(days)}", '
                    f'penwidth={width:.2f}, color="{color}", fontcolor="{color}"];'
                )
    lines.append("}")
    return "\n".join(lines)
