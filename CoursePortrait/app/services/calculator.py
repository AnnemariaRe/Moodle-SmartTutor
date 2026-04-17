from typing import List, Dict
import numpy as np
import logging

from app.services.difficulty_calculators import DifficultyCalculatorFactory

logger = logging.getLogger(__name__)


class MetricsCalculator:
    
    @staticmethod
    def calculate_difficulty_scores(
        modules: List[Dict],
        predictor,
        use_type_aware: bool = True
    ) -> List[Dict]:
        if not modules:
            return []
        
        durations = [m.get("avgDurationMs", 0) for m in modules if m.get("avgDurationMs", 0) > 0]
        median_duration = np.median(durations) if durations else 1.0
        
        for module in modules:
            avg_duration = module.get("avgDurationMs", 0)
            watch_percent = module.get("watchPercent")
            dropout_rate = module.get("dropoutRate", 0.0)
            pause_count = module.get("pauseCount", 0)
            step = module.get("step", 1)
            module_type = module.get("moduleType", "unknown")
            
            has_video_metrics = watch_percent is not None and watch_percent > 0
            
            if not has_video_metrics:
                if avg_duration > 0:
                    watch_percent = min(1.0, avg_duration / 60000.0)
                else:
                    watch_percent = 0.5
            
            event_count = module.get("studentCount", 1)
            features = [
                avg_duration / 1000.0,
                watch_percent if watch_percent is not None else 0.5,
                event_count,
            ]
            
            dropout_risk = predictor.predict_dropout(features)
            
            if use_type_aware:
                module_data = {
                    "moduleType": module_type,
                    "avgDurationMs": avg_duration,
                    "medianDurationMs": median_duration,
                    "watchPercent": watch_percent,
                    "pauseCount": pause_count,
                    "dropoutRate": dropout_rate,
                    "engagementScore": watch_percent if watch_percent is not None else 0.5,
                    "seekBackwardCount": module.get("seekBackwardCount", 0),
                    "avgReadTime": avg_duration,
                    "expectedReadTime": 60000,
                    "scrollDepth": module.get("scrollDepth", 0.8),
                    "returnVisits": module.get("returnVisits", 0),
                    "avgScore": module.get("avgScore", 70.0),
                    "attemptCount": module.get("attemptCount", 1.0),
                    "completionRate": module.get("completionRate", 0.8),
                    "avgTimeSpent": avg_duration / 1000,
                    "expectedTime": 600,
                    "submissionRate": module.get("submissionRate", 0.8),
                    "avgGrade": module.get("avgGrade", 70.0),
                    "lateSubmissions": module.get("lateSubmissions", 0.1),
                    "resubmissions": module.get("resubmissions", 0.1),
                }
                
                difficulty_result = DifficultyCalculatorFactory.calculate_difficulty(module_data)
                difficulty_score = difficulty_result.difficulty_score
                module["difficultyLevel"] = difficulty_result.difficulty_level

                module["difficultyDetails"] = {
                    "metrics": [
                        {
                            "name": m.name,
                            "value": m.value,
                            "normalizedValue": m.normalized_value,
                            "weight": m.weight,
                            "contribution": m.contribution,
                            "interpretation": m.interpretation
                        }
                        for m in difficulty_result.metrics
                    ],
                    "explanation": difficulty_result.explanation,
                    "suggestions": difficulty_result.suggestions
                }
            else:
                difficulty_score = predictor.calculate_difficulty_score(
                    avg_duration,
                    median_duration,
                    watch_percent if watch_percent is not None else 0.5,
                    dropout_rate
                )
                if difficulty_score < 0.4:
                    module["difficultyLevel"] = "easy"
                elif difficulty_score < 0.7:
                    module["difficultyLevel"] = "medium"
                else:
                    module["difficultyLevel"] = "hard"
                module["difficultyDetails"] = None
            
            module["dropoutRisk"] = dropout_risk
            module["difficultyScore"] = difficulty_score
            
            module["engagementScore"] = watch_percent
        
        return modules
    
    @staticmethod
    def identify_bottlenecks(modules: List[Dict], threshold: float = 0.35) -> List[int]:
        bottlenecks = []
        max_students = max((m.get("studentCount", 0) for m in modules), default=0)

        for module in modules:
            difficulty_score = module.get("difficultyScore", 0.0)
            student_count = module.get("studentCount", 0)
            traffic_ratio = student_count / max_students if max_students > 0 else 0

            logger.debug(
                f"Bottleneck check: module={module.get('moduleId')}, "
                f"difficultyScore={difficulty_score:.3f}, "
                f"studentCount={student_count}/{max_students}, traffic_ratio={traffic_ratio:.3f}, "
                f"threshold={threshold}"
            )

            if difficulty_score > threshold and traffic_ratio > 0.1:
                bottlenecks.append(module.get("moduleId"))
                logger.info(f"Bottleneck found: module={module.get('moduleId')}, difficultyScore={difficulty_score:.3f}")

        if not bottlenecks:
            logger.info(f"No bottlenecks found. Max difficultyScore={max((m.get('difficultyScore', 0) for m in modules), default=0):.3f}, threshold={threshold}")

        return bottlenecks
    
    @staticmethod
    def analyze_dropoff_chains(sequences: List[List[int]]) -> List[List[int]]:
        if not sequences:
            return []
        
        dropoff_sequences = [seq for seq in sequences if len(seq) < 5]
        last_three_patterns = {}
        for seq in dropoff_sequences:
            if len(seq) >= 3:
                pattern = tuple(seq[-3:])
                last_three_patterns[pattern] = last_three_patterns.get(pattern, 0) + 1
        
        sorted_patterns = sorted(
            last_three_patterns.items(),
            key=lambda x: x[1],
            reverse=True
        )[:5]
        
        return [list(pattern) for pattern, _ in sorted_patterns]
    
    @staticmethod
    def calculate_section_engagement(
        modules: List[Dict]
    ) -> Dict[int, Dict]:
        section_data = {}
        for module in modules:
            section_id = module.get("sectionId")
            if section_id is None:
                continue
            
            if section_id not in section_data:
                section_data[section_id] = {
                    "totalTimePercent": 0.0,
                    "transitionsCount": 0,
                    "modules": []
                }
            
            watch_percent = module.get("watchPercent", 0.0)
            section_data[section_id]["totalTimePercent"] += watch_percent
            section_data[section_id]["modules"].append(module.get("moduleId"))
        
        for section_id, data in section_data.items():
            data["transitionsCount"] = max(0, len(data["modules"]) - 1)
        
        return section_data
    
    @staticmethod
    def generate_recommendations(modules: List[Dict]) -> List[Dict]:
        recommendations = []
        
        for module in modules:
            module_id = module.get("moduleId")
            difficulty_score = module.get("difficultyScore", 0.0)
            dropout_rate = module.get("dropoutRate", 0.0)
            watch_percent = module.get("watchPercent", 0.5)
            dropout_risk = module.get("dropoutRisk", 0.0)
            
            issues = []
            recs = []
            priority = "low"
            
            if dropout_rate > 0.5 or dropout_risk > 0.7:
                issues.append(f"High dropout ({dropout_rate:.0%})")
                recs.append("Add intermediate quizzes to check understanding")
                recs.append("Simplify content or break into smaller parts")
                priority = "high"
            
            if watch_percent < 0.3:
                issues.append(f"Low watch rate ({watch_percent:.0%})")
                recs.append("Add interactive elements (polls, assignments)")
                recs.append("Review module duration and structure")
                if priority != "high":
                    priority = "medium"
            
            if difficulty_score > 0.7:
                issues.append(f"High difficulty (score: {difficulty_score:.2f})")
                recs.append("Add additional explanations and examples")
                recs.append("Provide supplementary learning materials")
                if priority != "high":
                    priority = "medium"
            
            if issues:
                recommendations.append({
                    "moduleId": module_id,
                    "moduleName": module.get("moduleName"),
                    "issue": "; ".join(issues),
                    "recommendation": " | ".join(recs),
                    "priority": priority
                })
        
        priority_order = {"high": 0, "medium": 1, "low": 2}
        recommendations.sort(key=lambda x: priority_order.get(x["priority"], 3))
        
        return recommendations
