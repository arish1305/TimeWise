import json
import logging
import urllib.request
import urllib.error
import os

logger = logging.getLogger(__name__)

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")

def review_timetable_llm(timetable_data: dict, human_score: float, issues: list[str], model: str = "qwen3:4b") -> dict:
    """
    Calls a local Ollama instance to provide a human-like review of the timetable quality.
    This review is strictly observational and MUST NOT modify, save, or trigger regeneration.
    """
    logger.info(f"Initiating optional LLM review using Ollama model '{model}'...")
    
    # Format the payload and context
    timetable_summary = []
    for entry in timetable_data.get("entries", []):
        subj = entry.get("subject_code") or entry.get("subject_name") or "Unknown"
        day = entry.get("day") or "Unknown"
        time_str = entry.get("start_time") or "Unknown"
        fac = entry.get("faculty_name") or "Unassigned"
        timetable_summary.append(f"- {day} {time_str}: {subj} by {fac}")

    prompt = (
        f"You are an expert academic coordinator. Review the following generated timetable and its automated quality metrics.\n\n"
        f"Timetable Details:\n" + "\n".join(timetable_summary) + "\n\n"
        f"Human Score: {human_score}/100\n"
        f"Identified Issues:\n" + "\n".join([f"- {issue}" for issue in issues]) + "\n\n"
        f"Instructions:\n"
        f"1. Evaluate if the schedule is comfortable for students and faculty.\n"
        f"2. Suggest structural changes for the next manual update.\n"
        f"3. Return your review observations in a strict JSON format with fields: 'score', 'issues', and 'suggestions'.\n"
        f"4. Do NOT output anything else except the raw JSON. Do not attempt to regenerate or modify the timetable."
    )

    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": "json"
    }

    try:
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(
            f"{OLLAMA_URL}/api/generate",
            data=data,
            headers={'Content-Type': 'application/json'}
        )
        
        with urllib.request.urlopen(req, timeout=10) as response:
            if response.status == 200:
                result = json.loads(response.read().decode('utf-8'))
                response_text = result.get("response", "").strip()
                logger.info("LLM Review succeeded.")
                # Attempt to parse Ollama JSON response
                try:
                    review_data = json.loads(response_text)
                    return {
                        "status": "success",
                        "model": model,
                        "review": {
                            "score": review_data.get("score", human_score),
                            "issues": review_data.get("issues", []),
                            "suggestions": review_data.get("suggestions", [])
                        }
                    }
                except json.JSONDecodeError:
                    # Fallback if LLM output was not valid JSON
                    return {
                        "status": "success",
                        "model": model,
                        "review": {
                            "score": human_score,
                            "issues": issues,
                            "suggestions": [response_text]
                        }
                    }
            else:
                logger.warning(f"Ollama returned non-200 status code: {response.status}")
    except urllib.error.URLError as e:
        logger.warning(f"Ollama not reachable at {OLLAMA_URL}: {e.reason}")
    except Exception as e:
        logger.warning(f"Failed to fetch LLM review: {e}")

    return {
        "status": "skipped",
        "reason": "Ollama service unavailable or disabled"
    }
