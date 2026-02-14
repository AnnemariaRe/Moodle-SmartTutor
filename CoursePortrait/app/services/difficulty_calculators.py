from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class DifficultyMetric:
    name: str
    value: float
    normalized_value: float
    weight: float
    contribution: float          # Вклад в итоговый скор (normalized * weight)
    interpretation: str          # Пояснение для преподавателя


@dataclass
class DifficultyResult:
    module_type: str
    difficulty_score: float
    difficulty_level: str        # easy/medium/hard
    metrics: List[DifficultyMetric]  # Детализация по метрикам
    explanation: str             # Общее пояснение
    suggestions: List[str]       # Рекомендации по улучшению


class BaseDifficultyCalculator(ABC):
    
    @abstractmethod
    def calculate(self, module_data: Dict[str, Any]) -> DifficultyResult:
        pass
    
    @staticmethod
    def _get_difficulty_level(score: float) -> str:
        if score < 0.4:
            return "easy"
        elif score < 0.7:
            return "medium"
        return "hard"
    
    @staticmethod
    def _clamp(value: float, min_val: float = 0.0, max_val: float = 1.0) -> float:
        return max(min_val, min(max_val, value))


class QuizDifficultyCalculator(BaseDifficultyCalculator):
    WEIGHT_AVG_SCORE = 0.35
    WEIGHT_ATTEMPTS = 0.25
    WEIGHT_COMPLETION = 0.20
    WEIGHT_TIME = 0.20
    
    def calculate(self, module_data: Dict[str, Any]) -> DifficultyResult:
        metrics = []
        
        avg_score = module_data.get("avgScore", 70.0)
        score_normalized = self._clamp(1.0 - avg_score / 100.0)
        score_contribution = score_normalized * self.WEIGHT_AVG_SCORE
        
        interpretation = "Хороший результат" if avg_score >= 70 else \
                        "Средний результат" if avg_score >= 50 else \
                        "Низкий результат — студенты испытывают трудности"
        
        metrics.append(DifficultyMetric(
            name="Средний балл",
            value=avg_score,
            normalized_value=score_normalized,
            weight=self.WEIGHT_AVG_SCORE,
            contribution=score_contribution,
            interpretation=interpretation
        ))
        
        attempt_count = module_data.get("attemptCount", 1.0)
        attempts_normalized = self._clamp((attempt_count - 1) / 2.0)
        attempts_contribution = attempts_normalized * self.WEIGHT_ATTEMPTS
        
        interpretation = "Одна попытка — материал понятен" if attempt_count <= 1.2 else \
                        "Несколько попыток — требуется повторение" if attempt_count <= 2 else \
                        "Много попыток — материал сложный"
        
        metrics.append(DifficultyMetric(
            name="Среднее кол-во попыток",
            value=attempt_count,
            normalized_value=attempts_normalized,
            weight=self.WEIGHT_ATTEMPTS,
            contribution=attempts_contribution,
            interpretation=interpretation
        ))
        
        completion_rate = module_data.get("completionRate", 0.8)
        completion_normalized = self._clamp(1.0 - completion_rate)
        completion_contribution = completion_normalized * self.WEIGHT_COMPLETION
        
        interpretation = "Большинство завершили тест" if completion_rate >= 0.8 else \
                        "Часть студентов не завершила" if completion_rate >= 0.6 else \
                        "Много незавершенных — возможно, слишком сложный"
        
        metrics.append(DifficultyMetric(
            name="Процент завершивших",
            value=completion_rate * 100,
            normalized_value=completion_normalized,
            weight=self.WEIGHT_COMPLETION,
            contribution=completion_contribution,
            interpretation=interpretation
        ))
        
        avg_time = module_data.get("avgTimeSpent", 0)
        expected_time = module_data.get("expectedTime", 600)
        
        if expected_time > 0:
            time_ratio = avg_time / expected_time
            time_normalized = self._clamp(min(time_ratio, 1.5) / 1.5)
        else:
            time_normalized = 0.5
            time_ratio = 1.0
        
        time_contribution = time_normalized * self.WEIGHT_TIME
        
        interpretation = "Время в норме" if time_ratio <= 1.2 else \
                        "Немного дольше ожидаемого" if time_ratio <= 1.5 else \
                        "Значительно дольше — вопросы сложные"
        
        metrics.append(DifficultyMetric(
            name="Время выполнения",
            value=avg_time,
            normalized_value=time_normalized,
            weight=self.WEIGHT_TIME,
            contribution=time_contribution,
            interpretation=interpretation
        ))
        
        total_score = sum(m.contribution for m in metrics)
        total_score = self._clamp(total_score)
        difficulty_level = self._get_difficulty_level(total_score)
        
        explanation = self._generate_explanation(avg_score, attempt_count, completion_rate, difficulty_level)
        suggestions = self._generate_suggestions(avg_score, attempt_count, completion_rate)
        
        return DifficultyResult(
            module_type="quiz",
            difficulty_score=total_score,
            difficulty_level=difficulty_level,
            metrics=metrics,
            explanation=explanation,
            suggestions=suggestions
        )
    
    def _generate_explanation(self, avg_score: float, attempts: float, 
                             completion: float, level: str) -> str:
        level_ru = {"easy": "Легкий", "medium": "Средний", "hard": "Сложный"}[level]
        parts = [f"Тест: {level_ru}"]
        
        if avg_score < 60:
            parts.append(f"низкий средний балл ({avg_score:.0f}%)")
        if attempts > 2:
            parts.append(f"много попыток ({attempts:.1f} в среднем)")
        if completion < 0.7:
            parts.append(f"низкий процент завершения ({completion*100:.0f}%)")
        
        return " — ".join(parts) if len(parts) > 1 else parts[0]
    
    def _generate_suggestions(self, avg_score: float, attempts: float, 
                             completion: float) -> List[str]:
        # TODO: upgrade suggestions using LLM
        suggestions = []
        
        if avg_score < 60:
            suggestions.append("Упростить формулировки вопросов")
            suggestions.append("Добавить подсказки к сложным вопросам")
        
        if attempts > 2:
            suggestions.append("Разбить тест на несколько меньших")
            suggestions.append("Добавить обучающий материал перед тестом")
        
        if completion < 0.7:
            suggestions.append("Уменьшить количество вопросов")
            suggestions.append("Увеличить время на прохождение")
        
        return suggestions[:3]


class VideoDifficultyCalculator(BaseDifficultyCalculator):
    WEIGHT_WATCH = 0.30
    WEIGHT_SEEK_BACK = 0.25
    WEIGHT_PAUSE = 0.20
    WEIGHT_DROPOUT = 0.25
    
    def calculate(self, module_data: Dict[str, Any]) -> DifficultyResult:
        metrics = []
        
        watch_percent = module_data.get("watchPercent", 0.7)
        watch_normalized = self._clamp(1.0 - watch_percent)
        watch_contribution = watch_normalized * self.WEIGHT_WATCH
        
        interpretation = "Большинство досматривают" if watch_percent >= 0.8 else \
                        "Часть не досматривает" if watch_percent >= 0.6 else \
                        "Много не досматривают — возможно, слишком длинное"
        
        metrics.append(DifficultyMetric(
            name="Процент просмотра",
            value=watch_percent * 100,
            normalized_value=watch_normalized,
            weight=self.WEIGHT_WATCH,
            contribution=watch_contribution,
            interpretation=interpretation
        ))
        
        seek_back = module_data.get("seekBackwardCount", 0)
        seek_normalized = self._clamp(seek_back / 5.0)
        seek_contribution = seek_normalized * self.WEIGHT_SEEK_BACK
        
        interpretation = "Мало перемоток — материал понятен" if seek_back <= 1 else \
                        "Умеренное количество перемоток" if seek_back <= 3 else \
                        "Много перемоток — сложные моменты"
        
        metrics.append(DifficultyMetric(
            name="Перемотки назад",
            value=seek_back,
            normalized_value=seek_normalized,
            weight=self.WEIGHT_SEEK_BACK,
            contribution=seek_contribution,
            interpretation=interpretation
        ))
        
        pause_count = module_data.get("pauseCount", 0)
        pause_normalized = self._clamp(pause_count / 10.0)
        pause_contribution = pause_normalized * self.WEIGHT_PAUSE
        
        interpretation = "Мало пауз — смотрят непрерывно" if pause_count <= 2 else \
                        "Умеренное количество пауз" if pause_count <= 5 else \
                        "Много пауз — требуется время на осмысление"
        
        metrics.append(DifficultyMetric(
            name="Количество пауз",
            value=pause_count,
            normalized_value=pause_normalized,
            weight=self.WEIGHT_PAUSE,
            contribution=pause_contribution,
            interpretation=interpretation
        ))
        
        dropout_rate = module_data.get("dropoutRate", 0.1)
        dropout_normalized = self._clamp(dropout_rate)
        dropout_contribution = dropout_normalized * self.WEIGHT_DROPOUT
        interpretation = "Низкий отвал" if dropout_rate <= 0.1 else \
                        "Умеренный отвал" if dropout_rate <= 0.3 else \
                        "Высокий отвал — видео может отпугивать"
        
        metrics.append(DifficultyMetric(
            name="Отвал после видео",
            value=dropout_rate * 100,
            normalized_value=dropout_normalized,
            weight=self.WEIGHT_DROPOUT,
            contribution=dropout_contribution,
            interpretation=interpretation
        ))
        
        total_score = sum(m.contribution for m in metrics)
        total_score = self._clamp(total_score)
        difficulty_level = self._get_difficulty_level(total_score)
        
        explanation = self._generate_explanation(watch_percent, seek_back, pause_count, 
                                                 dropout_rate, difficulty_level)
        suggestions = self._generate_suggestions(watch_percent, seek_back, pause_count, dropout_rate)
        
        return DifficultyResult(
            module_type="video",
            difficulty_score=total_score,
            difficulty_level=difficulty_level,
            metrics=metrics,
            explanation=explanation,
            suggestions=suggestions
        )
    
    def _generate_explanation(self, watch: float, seek: int, pause: int, 
                             dropout: float, level: str) -> str:
        level_ru = {"easy": "Легкое", "medium": "Среднее", "hard": "Сложное"}[level]
        parts = [f"Видео: {level_ru}"]
        
        if watch < 0.7:
            parts.append(f"низкий просмотр ({watch*100:.0f}%)")
        if seek > 3:
            parts.append(f"много перемоток ({seek})")
        if dropout > 0.2:
            parts.append(f"высокий отвал ({dropout*100:.0f}%)")
        
        return " — ".join(parts) if len(parts) > 1 else parts[0]
    
    def _generate_suggestions(self, watch: float, seek: int, pause: int, 
                             dropout: float) -> List[str]:
        # TODO: upgrade suggestions using LLM
        suggestions = []
        
        if watch < 0.7:
            suggestions.append("Сократить длительность видео")
            suggestions.append("Разбить на несколько коротких видео")
        
        if seek > 3:
            suggestions.append("Добавить субтитры или конспект")
            suggestions.append("Замедлить темп объяснения в сложных местах")
        
        if pause > 5:
            suggestions.append("Добавить паузы для осмысления в видео")
        
        if dropout > 0.2:
            suggestions.append("Добавить интерактивные элементы")
            suggestions.append("Проверить качество звука и изображения")
        
        return suggestions[:3]


class TextDifficultyCalculator(BaseDifficultyCalculator):
    WEIGHT_READ_TIME = 0.35
    WEIGHT_SCROLL = 0.25
    WEIGHT_RETURNS = 0.20
    WEIGHT_DROPOUT = 0.20
    
    def calculate(self, module_data: Dict[str, Any]) -> DifficultyResult:
        metrics = []
        
        avg_read_time = module_data.get("avgReadTime", 60000)
        expected_time = module_data.get("expectedReadTime", 60000)
        
        if expected_time > 0:
            time_ratio = avg_read_time / expected_time
            time_normalized = self._clamp(min(time_ratio, 2.0) / 2.0)
        else:
            time_normalized = 0.5
            time_ratio = 1.0
        
        time_contribution = time_normalized * self.WEIGHT_READ_TIME
        
        interpretation = "Время чтения в норме" if time_ratio <= 1.2 else \
                        "Читают дольше ожидаемого" if time_ratio <= 1.5 else \
                        "Значительно дольше — сложный текст"
        
        metrics.append(DifficultyMetric(
            name="Время чтения",
            value=avg_read_time / 1000,
            normalized_value=time_normalized,
            weight=self.WEIGHT_READ_TIME,
            contribution=time_contribution,
            interpretation=interpretation
        ))
        
        scroll_depth = module_data.get("scrollDepth", 0.8)
        scroll_normalized = self._clamp(1.0 - scroll_depth)
        scroll_contribution = scroll_normalized * self.WEIGHT_SCROLL
        interpretation = "Большинство дочитывают" if scroll_depth >= 0.8 else \
                        "Часть не дочитывает" if scroll_depth >= 0.6 else \
                        "Много не дочитывают — текст слишком длинный"
        
        metrics.append(DifficultyMetric(
            name="Глубина прокрутки",
            value=scroll_depth * 100,
            normalized_value=scroll_normalized,
            weight=self.WEIGHT_SCROLL,
            contribution=scroll_contribution,
            interpretation=interpretation
        ))
        
        return_visits = module_data.get("returnVisits", 0)
        returns_normalized = self._clamp(return_visits / 3.0)
        returns_contribution = returns_normalized * self.WEIGHT_RETURNS
        
        interpretation = "Читают один раз — материал понятен" if return_visits < 0.5 else \
                        "Иногда возвращаются" if return_visits < 1.5 else \
                        "Часто возвращаются — требует повторения"
        
        metrics.append(DifficultyMetric(
            name="Повторные посещения",
            value=return_visits,
            normalized_value=returns_normalized,
            weight=self.WEIGHT_RETURNS,
            contribution=returns_contribution,
            interpretation=interpretation
        ))
        
        dropout_rate = module_data.get("dropoutRate", 0.1)
        dropout_normalized = self._clamp(dropout_rate)
        dropout_contribution = dropout_normalized * self.WEIGHT_DROPOUT
        interpretation = "Низкий отвал" if dropout_rate <= 0.1 else \
                        "Умеренный отвал" if dropout_rate <= 0.3 else \
                        "Высокий отвал"
        
        metrics.append(DifficultyMetric(
            name="Отвал после страницы",
            value=dropout_rate * 100,
            normalized_value=dropout_normalized,
            weight=self.WEIGHT_DROPOUT,
            contribution=dropout_contribution,
            interpretation=interpretation
        ))
        
        total_score = sum(m.contribution for m in metrics)
        total_score = self._clamp(total_score)
        difficulty_level = self._get_difficulty_level(total_score)
        
        explanation = self._generate_explanation(time_ratio, scroll_depth, return_visits, 
                                                 dropout_rate, difficulty_level)
        suggestions = self._generate_suggestions(time_ratio, scroll_depth, return_visits)
        
        return DifficultyResult(
            module_type="text",
            difficulty_score=total_score,
            difficulty_level=difficulty_level,
            metrics=metrics,
            explanation=explanation,
            suggestions=suggestions
        )
    
    def _generate_explanation(self, time_ratio: float, scroll: float, returns: float, 
                             dropout: float, level: str) -> str:
        level_ru = {"easy": "Легкий", "medium": "Средний", "hard": "Сложный"}[level]
        parts = [f"Текст: {level_ru}"]
        
        if time_ratio > 1.5:
            parts.append(f"долгое чтение (x{time_ratio:.1f})")
        if scroll < 0.7:
            parts.append(f"низкая прокрутка ({scroll*100:.0f}%)")
        if returns > 1:
            parts.append(f"частые возвраты ({returns:.1f})")
        
        return " — ".join(parts) if len(parts) > 1 else parts[0]
    
    def _generate_suggestions(self, time_ratio: float, scroll: float, 
                             returns: float) -> List[str]:
        # TODO: upgrade suggestions using LLM
        suggestions = []
        
        if time_ratio > 1.5:
            suggestions.append("Упростить язык изложения")
            suggestions.append("Добавить иллюстрации и примеры")
        
        if scroll < 0.7:
            suggestions.append("Сократить объем текста")
            suggestions.append("Разбить на несколько страниц")
        
        if returns > 1:
            suggestions.append("Добавить краткое резюме в начале")
            suggestions.append("Выделить ключевые моменты")
        
        return suggestions[:3]


class AssignmentDifficultyCalculator(BaseDifficultyCalculator):
    WEIGHT_SUBMISSION = 0.30
    WEIGHT_GRADE = 0.30
    WEIGHT_LATE = 0.20
    WEIGHT_RESUB = 0.20
    
    def calculate(self, module_data: Dict[str, Any]) -> DifficultyResult:
        metrics = []
        
        submission_rate = module_data.get("submissionRate", 0.8)
        submission_normalized = self._clamp(1.0 - submission_rate)
        submission_contribution = submission_normalized * self.WEIGHT_SUBMISSION
        
        interpretation = "Большинство сдали" if submission_rate >= 0.8 else \
                        "Часть не сдала" if submission_rate >= 0.6 else \
                        "Много не сдали — возможно, слишком сложное"
        
        metrics.append(DifficultyMetric(
            name="Процент сдавших",
            value=submission_rate * 100,
            normalized_value=submission_normalized,
            weight=self.WEIGHT_SUBMISSION,
            contribution=submission_contribution,
            interpretation=interpretation
        ))
        
        avg_grade = module_data.get("avgGrade", 70.0)
        grade_normalized = self._clamp(1.0 - avg_grade / 100.0)
        grade_contribution = grade_normalized * self.WEIGHT_GRADE
        
        interpretation = "Хорошие оценки" if avg_grade >= 70 else \
                        "Средние оценки" if avg_grade >= 50 else \
                        "Низкие оценки — студенты не справляются"
        
        metrics.append(DifficultyMetric(
            name="Средняя оценка",
            value=avg_grade,
            normalized_value=grade_normalized,
            weight=self.WEIGHT_GRADE,
            contribution=grade_contribution,
            interpretation=interpretation
        ))
        
        late_submissions = module_data.get("lateSubmissions", 0.1)
        late_normalized = self._clamp(late_submissions)
        late_contribution = late_normalized * self.WEIGHT_LATE
        
        interpretation = "Мало опозданий" if late_submissions <= 0.1 else \
                        "Умеренное количество опозданий" if late_submissions <= 0.3 else \
                        "Много опозданий — недостаточно времени"
        
        metrics.append(DifficultyMetric(
            name="Сдали с опозданием",
            value=late_submissions * 100,
            normalized_value=late_normalized,
            weight=self.WEIGHT_LATE,
            contribution=late_contribution,
            interpretation=interpretation
        ))
        
        resubmissions = module_data.get("resubmissions", 0.1)
        resub_normalized = self._clamp(resubmissions * 2)
        resub_contribution = resub_normalized * self.WEIGHT_RESUB
        interpretation = "Мало пересдач" if resubmissions <= 0.1 else \
                        "Умеренное количество пересдач" if resubmissions <= 0.25 else \
                        "Много пересдач — требования неясны"
        
        metrics.append(DifficultyMetric(
            name="Пересдачи",
            value=resubmissions * 100,
            normalized_value=resub_normalized,
            weight=self.WEIGHT_RESUB,
            contribution=resub_contribution,
            interpretation=interpretation
        ))
        
        total_score = sum(m.contribution for m in metrics)
        total_score = self._clamp(total_score)
        difficulty_level = self._get_difficulty_level(total_score)
        
        explanation = self._generate_explanation(submission_rate, avg_grade, 
                                                 late_submissions, resubmissions, difficulty_level)
        suggestions = self._generate_suggestions(submission_rate, avg_grade, 
                                                 late_submissions, resubmissions)
        
        return DifficultyResult(
            module_type="assignment",
            difficulty_score=total_score,
            difficulty_level=difficulty_level,
            metrics=metrics,
            explanation=explanation,
            suggestions=suggestions
        )
    
    def _generate_explanation(self, submission: float, grade: float, late: float, 
                             resub: float, level: str) -> str:
        level_ru = {"easy": "Легкое", "medium": "Среднее", "hard": "Сложное"}[level]
        parts = [f"Задание: {level_ru}"]
        
        if submission < 0.7:
            parts.append(f"низкая сдача ({submission*100:.0f}%)")
        if grade < 60:
            parts.append(f"низкие оценки ({grade:.0f}%)")
        if late > 0.2:
            parts.append(f"много опозданий ({late*100:.0f}%)")
        
        return " — ".join(parts) if len(parts) > 1 else parts[0]
    
    def _generate_suggestions(self, submission: float, grade: float, late: float, 
                             resub: float) -> List[str]:
        # TODO: upgrade suggestions using LLM
        suggestions = []
        
        if submission < 0.7:
            suggestions.append("Упростить требования к заданию")
            suggestions.append("Добавить примеры выполнения")
        
        if grade < 60:
            suggestions.append("Уточнить критерии оценивания")
            suggestions.append("Добавить промежуточную обратную связь")
        
        if late > 0.2:
            suggestions.append("Увеличить срок выполнения")
            suggestions.append("Разбить на несколько этапов")
        
        if resub > 0.2:
            suggestions.append("Добавить чек-лист требований")
        
        return suggestions[:3]


class GenericDifficultyCalculator(BaseDifficultyCalculator):
    WEIGHT_DURATION = 0.40
    WEIGHT_DROPOUT = 0.30
    WEIGHT_ENGAGEMENT = 0.30
    
    def calculate(self, module_data: Dict[str, Any]) -> DifficultyResult:
        metrics = []
        
        avg_duration = module_data.get("avgDurationMs", 60000)
        median_duration = module_data.get("medianDurationMs", 60000)
        
        if median_duration > 0:
            duration_ratio = avg_duration / median_duration
            duration_normalized = self._clamp(min(duration_ratio, 2.0) / 2.0)
        else:
            duration_normalized = 0.5
            duration_ratio = 1.0
        
        duration_contribution = duration_normalized * self.WEIGHT_DURATION
        
        interpretation = "Время в норме" if duration_ratio <= 1.2 else \
                        "Дольше среднего" if duration_ratio <= 1.5 else \
                        "Значительно дольше среднего"
        
        metrics.append(DifficultyMetric(
            name="Время в модуле",
            value=avg_duration / 1000,
            normalized_value=duration_normalized,
            weight=self.WEIGHT_DURATION,
            contribution=duration_contribution,
            interpretation=interpretation
        ))
        
        dropout_rate = module_data.get("dropoutRate", 0.1)
        dropout_normalized = self._clamp(dropout_rate)
        dropout_contribution = dropout_normalized * self.WEIGHT_DROPOUT
        
        interpretation = "Низкий отвал" if dropout_rate <= 0.1 else \
                        "Умеренный отвал" if dropout_rate <= 0.3 else \
                        "Высокий отвал"
        
        metrics.append(DifficultyMetric(
            name="Отвал",
            value=dropout_rate * 100,
            normalized_value=dropout_normalized,
            weight=self.WEIGHT_DROPOUT,
            contribution=dropout_contribution,
            interpretation=interpretation
        ))
        
        engagement = module_data.get("engagementScore", 0.7)
        engagement_normalized = self._clamp(1.0 - engagement)
        engagement_contribution = engagement_normalized * self.WEIGHT_ENGAGEMENT
        
        interpretation = "Высокая вовлеченность" if engagement >= 0.7 else \
                        "Средняя вовлеченность" if engagement >= 0.5 else \
                        "Низкая вовлеченность"
        
        metrics.append(DifficultyMetric(
            name="Вовлеченность",
            value=engagement * 100,
            normalized_value=engagement_normalized,
            weight=self.WEIGHT_ENGAGEMENT,
            contribution=engagement_contribution,
            interpretation=interpretation
        ))
        
        total_score = sum(m.contribution for m in metrics)
        total_score = self._clamp(total_score)
        difficulty_level = self._get_difficulty_level(total_score)
        
        level_ru = {"easy": "Легкий", "medium": "Средний", "hard": "Сложный"}[difficulty_level]
        explanation = f"Модуль: {level_ru}"
        
        suggestions = []
        if dropout_rate > 0.2:
            suggestions.append("Проверить содержимое модуля")
        if engagement < 0.5:
            suggestions.append("Добавить интерактивные элементы")
        
        return DifficultyResult(
            module_type="generic",
            difficulty_score=total_score,
            difficulty_level=difficulty_level,
            metrics=metrics,
            explanation=explanation,
            suggestions=suggestions
        )


class DifficultyCalculatorFactory:    
    _calculators = {
        "quiz": QuizDifficultyCalculator,
        "video": VideoDifficultyCalculator,
        "resource": VideoDifficultyCalculator,
        "page": TextDifficultyCalculator,
        "book": TextDifficultyCalculator,
        "label": TextDifficultyCalculator,
        "assign": AssignmentDifficultyCalculator,
        "workshop": AssignmentDifficultyCalculator,
    }
    
    @classmethod
    def get_calculator(cls, module_type: str) -> BaseDifficultyCalculator:
        calculator_class = cls._calculators.get(module_type.lower(), GenericDifficultyCalculator)
        return calculator_class()
    
    @classmethod
    def calculate_difficulty(cls, module_data: Dict[str, Any]) -> DifficultyResult:
        module_type = module_data.get("moduleType", "unknown").lower()
        
        if module_type in cls._calculators:
            calculator = cls.get_calculator(module_type)
        else:
            has_video = (
                module_data.get("watchPercent") is not None and
                module_data.get("watchPercent", 0) > 0
            )
            
            if has_video:
                calculator = VideoDifficultyCalculator()
            else:
                calculator = GenericDifficultyCalculator()
        
        return calculator.calculate(module_data)
