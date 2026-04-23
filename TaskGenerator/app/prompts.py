"""
Prompt constants for TaskGenerator LLM calls.
"""

TASK_GENERATION_PROMPT = """
Generate {variants} unique learning tasks on the concept "{concept_name}".

IMPORTANT: ALL tasks MUST be ENTIRELY IN RUSSIAN!
The task, question, answer options, correct answer, and explanation — ALL IN RUSSIAN!

Student context:
- Mastery (long-term): {mastery:.2f}
- BKT P(knows concept): {p_success:.2f}
- Target difficulty: {difficulty}

Rules:
- Type: mcq (3-4 answer options) or open (short text answer)
- Anti-cheating: use different numbers, contexts, examples in each task
- Each task must include a correct answer and explanation
- For "easy" difficulty — test basic definitions
- For "medium" — application through examples
- For "hard" — analysis, edge cases

Return a JSON array of objects with strictly the following fields:
- type: "mcq" or "open"
- difficulty: "{difficulty}"
- question: question text (IN RUSSIAN)
- options: list of options (only for mcq, otherwise null; ALL IN RUSSIAN)
- correct_index: 0-based index of the correct option (only for mcq, otherwise null)
- correct_answer: correct answer as text (only for open, otherwise null; IN RUSSIAN)
- explanation: explanation of the correct answer (IN RUSSIAN)

Only a JSON array, no markdown, no comments.
"""

_DIFFICULTY_RULES = """ТРЕБОВАНИЯ К СЛОЖНОСТИ (ОБЯЗАТЕЛЬНО):
- easy: определение или простой факт (1 шаг мышления)
- medium: практический пример — зашифруй/расшифруй конкретное слово
- hard: сравнение, анализ, или сложный пример с рассуждением
Сложности ДОЛЖНЫ отличаться по содержанию, не только по формулировке."""


_HINT_RULES = """HINT RULES (field `hint` — shown after the student's FIRST wrong attempt):
- MUST NOT reveal the correct answer — neither verbatim nor descriptively.
- MUST NOT list or exclude answer options ("it's not X and not Y").
- Steer the student toward the right principle / property / area to look at.
- Short: 1-3 sentences, max 200 characters.
- Friendly tone: "Подумай о…", "Вспомни про…", "Обрати внимание, что…".
- Leaves the actual reasoning to the student — hint narrows the search, not gives the answer.
- IN RUSSIAN.

HINT EXAMPLES:

Example 1 — MCQ:
  Question: «Какой шифр заменяет каждую букву на букву, стоящую на противоположном месте алфавита?»
  Correct answer: «Атбаш»
  GOOD hint: «Этот шифр известен с древних времён и упоминается в библейских текстах. Его название — короткое слово из двух слогов.»
  BAD hint: «Правильный ответ — Атбаш» (reveals)
  BAD hint: «Это не Цезарь и не Виженер» (excludes, doesn't help)
  BAD hint: «Подумай ещё раз» (no signal)

Example 2 — open:
  Question: «Зашифруй слово КОТ шифром Атбаш»
  Correct answer: «ЧЛЕ»
  GOOD hint: «Принцип Атбаш: А↔Я, Б↔Ю. Для каждой буквы слова посчитай её позицию от начала и возьми букву на той же позиции с конца.»"""


BANK_TASK_PROMPT = """You create learning tasks STRICTLY based on the provided course materials.

COURSE MATERIALS ON "{concept_name}":
═══════════════════════════════════════════
{course_context}
═══════════════════════════════════════════

TARGET DIFFICULTY: {difficulty}
NUMBER OF TASKS: {variants}
{teacher_instructions_block}
CRITICAL RULES:
1. Tasks MUST be grounded in the provided materials. Do not introduce topics missing from the context.
2. Use the same terminology, same examples and same style as the materials.
3. If materials mention specific algorithms/ciphers — use EXACTLY those. Do not substitute them with better-known ones.
4. If materials contain no math formulas or advanced concepts — do not introduce them into tasks.

""" + _DIFFICULTY_RULES + """

FORMAT:
- Type "mcq": question + 3-4 answer options + correct_index. Options must be plausible, not obvious.
- Type "open": question with short textual answer (1-3 words or a number).

ANTI-CHEATING: if multiple tasks — use different numbers, words, contexts. No near-duplicates.

""" + _HINT_RULES + """

IMPORTANT: ALL task texts (question, options, correct answer, hint, explanation) MUST be ENTIRELY IN RUSSIAN.

Return STRICTLY a JSON array of objects with fields:
- type: "mcq" or "open"
- difficulty: "{difficulty}"
- question: question text (IN RUSSIAN)
- options: list of options (only for mcq, otherwise null; ALL IN RUSSIAN)
- correct_index: 0-based index of the correct option (only for mcq, otherwise null)
- correct_answer: correct answer as text (only for open, otherwise null; IN RUSSIAN)
- hint: a gentle hint that does NOT reveal the answer (IN RUSSIAN, 1-3 sentences)
- explanation: full explanation with reference to the material (IN RUSSIAN)

Only a JSON array, no markdown, no comments.
"""

BANK_TASK_PROMPT_NO_CONTEXT = """
[COURSE CONTEXT UNAVAILABLE — fall back to general knowledge]

Generate {variants} unique learning tasks on the concept "{concept_name}".

IMPORTANT: ALL tasks MUST be ENTIRELY IN RUSSIAN!
The task, question, answer options, correct answer, hint, and explanation — ALL IN RUSSIAN!

Target difficulty: {difficulty}
{teacher_instructions_block}
Rules:
- Type: mcq (3-4 answer options) or open (short text answer)
- Anti-cheating: use different numbers, contexts, examples in each task
- Each task must include a correct answer, a hint, and an explanation

""" + _DIFFICULTY_RULES + """

""" + _HINT_RULES + """

Return a JSON array of objects with strictly the following fields:
- type: "mcq" or "open"
- difficulty: "{difficulty}"
- question: question text (IN RUSSIAN)
- options: list of options (only for mcq, otherwise null; ALL IN RUSSIAN)
- correct_index: 0-based index of the correct option (only for mcq, otherwise null)
- correct_answer: correct answer as text (only for open, otherwise null; IN RUSSIAN)
- hint: a gentle hint that does NOT reveal the answer (IN RUSSIAN, 1-3 sentences)
- explanation: explanation of the correct answer (IN RUSSIAN)

Only a JSON array, no markdown, no comments.
"""

CHECK_ANSWER_PROMPT = """
Check the student's answer to a learning task.

Task: {task_spec}
Student's answer: {student_answer}

Return strictly a JSON object:
{{"score": 0.8, "correct": true, "explanation": "Brief explanation of the score IN RUSSIAN"}}

Where score is a number from 0 to 1, correct is true if score >= 0.7.
The explanation must be IN RUSSIAN!
Only JSON, no markdown.
"""
