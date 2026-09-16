from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable


@dataclass(frozen=True, slots=True)
class Grade:
    id: int
    subject: str
    value: int
    note: str
    created_at: datetime


def average(grades: Iterable[Grade]) -> float:
    values = [g.value for g in grades]
    return sum(values) / len(values) if values else 0.0


def group_by_subject(grades: Iterable[Grade]) -> dict[str, list[Grade]]:
    grouped: dict[str, list[Grade]] = {}
    for grade in grades:
        grouped.setdefault(grade.subject, []).append(grade)
    for subject_grades in grouped.values():
        subject_grades.sort(key=lambda g: g.created_at)
    return grouped


def format_grades(grades: Iterable[Grade]) -> str:
    grouped = group_by_subject(grades)
    if not grouped:
        return "Оценок пока нет."
    lines = []
    for subject in sorted(grouped, key=str.lower):
        subject_grades = grouped[subject]
        values = " ".join(str(g.value) for g in subject_grades)
        lines.append(f"{subject}: {values} (среднее {average(subject_grades):.2f})")
    overall = average([g for gs in grouped.values() for g in gs])
    lines.append(f"\nОбщий средний балл: {overall:.2f}")
    return "\n".join(lines)
