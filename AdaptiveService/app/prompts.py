"""
Prompt constants for AdaptiveService LLM calls.
"""

CONCEPT_EXTRACTION_PROMPT = """\
You are an assistant for analyzing educational content{course_hint}.

Below are {num_activities} learning activities. For each one, extract 3-7 key learning concepts (topics) that are explained or assessed in it.

Requirements for concepts:
- Brief (2-5 words), as in a syllabus: "циклы for", "условия if/else", "списки Python".
- All concept names must be in Russian.
- Ordered from most important to least important for the given activity.
- The first concept is the main topic, the rest are supporting topics.

{items_text}

Respond strictly in JSON without explanations or markdown blocks. Return results for exactly these cmids: {cmid_list}.
{{"results": [{{"cmid": <number>, "concepts": ["главная тема", "вторая тема", "третья тема"]}}]}}"""
