import numpy as np
from typing import List, Optional
from pathlib import Path
import logging

# Попытка импорта ONNX Runtime
try:
    import onnxruntime as ort
    ONNX_AVAILABLE = True
except ImportError:
    ONNX_AVAILABLE = False
    ort = None

# Импорт XGBoost для pickle fallback
try:
    import xgboost as xgb
    XGBOOST_AVAILABLE = True
except ImportError:
    XGBOOST_AVAILABLE = False
    xgb = None

logger = logging.getLogger(__name__)


class MLPredictor:
    """
    Класс для ML предсказаний dropout и сложности модулей.
    
    Загружает модели из папки models/ и использует их для предсказаний.
    Поддерживает ONNX (быстрее) и pickle (fallback) форматы.
    """
    
    def __init__(self, models_dir: str = "models"):
        """
        Инициализация предиктора.
        
        Args:
            models_dir: Директория с ONNX или pickle моделями
        """
        self.models_dir = Path(models_dir)
        # ONNX сессии (быстрее)
        self.dropout_sess: Optional[object] = None
        self.difficulty_sess: Optional[object] = None
        # Pickle модели (fallback)
        self.dropout_model: Optional[object] = None
        self.difficulty_model: Optional[object] = None
        self._load_models()
    
    def _load_models(self):
        """Загрузка моделей (ONNX или pickle)."""
        dropout_onnx = self.models_dir / "dropout_predictor.onnx"
        difficulty_onnx = self.models_dir / "difficulty_predictor.onnx"
        dropout_pickle = self.models_dir / "dropout_predictor.pkl"
        difficulty_pickle = self.models_dir / "difficulty_predictor.pkl"
        
        if ONNX_AVAILABLE and dropout_onnx.exists():
            try:
                self.dropout_sess = ort.InferenceSession(str(dropout_onnx))
                logger.info(f"Loaded dropout model from {dropout_onnx} (ONNX)")
            except Exception as e:
                logger.warning(f"Error loading ONNX dropout model: {e}, trying pickle...")
                self._load_pickle_model("dropout", dropout_pickle)
        elif dropout_pickle.exists():
            self._load_pickle_model("dropout", dropout_pickle)
        else:
            logger.warning(f"Dropout model not found (checked ONNX and pickle)")
        
        if ONNX_AVAILABLE and difficulty_onnx.exists():
            try:
                self.difficulty_sess = ort.InferenceSession(str(difficulty_onnx))
                logger.info(f"Loaded difficulty model from {difficulty_onnx} (ONNX)")
            except Exception as e:
                logger.warning(f"Error loading ONNX difficulty model: {e}, trying pickle...")
                self._load_pickle_model("difficulty", difficulty_pickle)
        elif difficulty_pickle.exists():
            self._load_pickle_model("difficulty", difficulty_pickle)
        else:
            logger.warning(f"Difficulty model not found (checked ONNX and pickle)")
    
    def _load_pickle_model(self, name: str, path: Path):
        if not XGBOOST_AVAILABLE:
            logger.error(f"Cannot load pickle model: xgboost not available")
            return
        
        try:
            import pickle
            with open(path, "rb") as f:
                model = pickle.load(f)
            
            if name == "dropout":
                self.dropout_model = model
            else:
                self.difficulty_model = model
            
            logger.info(f"Loaded {name} model from {path} (pickle)")
        except Exception as e:
            logger.error(f"Error loading pickle {name} model: {e}")
    
    def predict_dropout(self, features: List[float]) -> float:
        """
        Предсказание риска отвала студента.
        
        Использует обученную XGBoost модель для предсказания вероятности того,
        что студент прекратит обучение после текущего модуля.
        
        Args:
            features: [durationMs/1000, watchPercent, step]
                - durationMs/1000: длительность сессии в секундах
                - watchPercent: процент просмотра (0-1)
                - step: порядковый номер модуля

        Returns:
            Вероятность отвала (0-1), где 1 = высокий риск отвала
        """
        if self.dropout_sess is not None:
            try:
                input_name = self.dropout_sess.get_inputs()[0].name
                features_array = np.array([features], dtype=np.float32)
                result = self.dropout_sess.run(None, {input_name: features_array})[0]
                if result.shape[1] > 1:
                    return float(result[0][1])
                return float(result[0][0])
            except Exception as e:
                logger.error(f"Error in ONNX dropout prediction: {e}")
        
        if self.dropout_model is not None:
            try:
                features_array = np.array([features], dtype=np.float32)
                result = self.dropout_model.predict_proba(features_array)[0]
                if len(result) > 1:
                    return float(result[1])
                return float(result[0])
            except Exception as e:
                logger.error(f"Error in pickle dropout prediction: {e}")
        
        # Финальный fallback: простая эвристика
        watch_percent = features[1] if len(features) > 1 else 0.5
        return max(0.0, min(1.0, 1.0 - watch_percent))
    
    def predict_difficulty(self, features: List[float]) -> str:
        """
        Предсказание сложности модуля.
        
        Использует обученную XGBoost модель для классификации сложности модуля
        на основе поведения студентов.
        
        Args:
            features: [durationMs/1000, watchPercent, step]
                - durationMs/1000: длительность сессии в секундах
                - watchPercent: процент просмотра (0-1)
                - step: порядковый номер модуля

        Returns:
            "easy", "medium" или "hard"
        """
        if self.difficulty_sess is not None:
            try:
                input_name = self.difficulty_sess.get_inputs()[0].name
                features_array = np.array([features], dtype=np.float32)
                result = self.difficulty_sess.run(None, {input_name: features_array})[0]
                predicted_class = int(np.argmax(result[0]))
                difficulty_map = {0: "easy", 1: "medium", 2: "hard"}
                return difficulty_map.get(predicted_class, "medium")
            except Exception as e:
                logger.error(f"Error in ONNX difficulty prediction: {e}")
        
        if self.difficulty_model is not None:
            try:
                features_array = np.array([features], dtype=np.float32)
                predicted_class = int(self.difficulty_model.predict(features_array)[0])
                difficulty_map = {0: "easy", 1: "medium", 2: "hard"}
                return difficulty_map.get(predicted_class, "medium")
            except Exception as e:
                logger.error(f"Error in pickle difficulty prediction: {e}")
        
        watch_percent = features[1] if len(features) > 1 else 0.5
        if watch_percent < 0.3:
            return "hard"
        elif watch_percent < 0.7:
            return "medium"
        return "easy"
    
    def calculate_difficulty_score(
        self,
        avg_duration_ms: float,
        median_duration_ms: float,
        watch_percent: float,
        dropout_after_module: float
    ) -> float:
        """
        Вычисление композитного индекса сложности по формуле:
        Difficulty = 0.4 * (avg_duration / median) + 0.3 * (1 - watchPercent) + 0.3 * dropout_after_module
        
        Args:
            avg_duration_ms: Средняя длительность сессии в модуле
            median_duration_ms: Медианная длительность по курсу
            watch_percent: Процент просмотра (0-1)
            dropout_after_module: Процент отвала после модуля (0-1)
        
        Returns:
            Индекс сложности (0-1)
        """
        if median_duration_ms == 0:
            duration_ratio = 1.0
        else:
            duration_ratio = min(avg_duration_ms / median_duration_ms, 2.0)
        
        difficulty = (
            0.4 * duration_ratio +
            0.3 * (1.0 - watch_percent) +
            0.3 * dropout_after_module
        )
        return max(0.0, min(1.0, difficulty))


_predictor: Optional[MLPredictor] = None


def get_predictor() -> MLPredictor:
    global _predictor
    if _predictor is None:
        _predictor = MLPredictor()
    return _predictor
