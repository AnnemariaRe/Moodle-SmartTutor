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

BANK_TASK_PROMPT = """
Generate {variants} unique learning tasks on the concept "{concept_name}".

IMPORTANT: ALL tasks MUST be ENTIRELY IN RUSSIAN!
The task, question, answer options, correct answer, and explanation — ALL IN RUSSIAN!

Target difficulty: {difficulty}
{teacher_instructions_block}
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
