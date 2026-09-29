"""
LLM integration service for diagnosis assistance
"""
import json
import logging
from datetime import date
from typing import Dict, List, Any, Optional

from ai_settings.client import chat_json, parse_json_object
from ai_settings.services import DEFAULT_TEMPERATURES, ROLE_DIAGNOSIS, get_ai_config
from utils.report_redaction import Redactor

logger = logging.getLogger(__name__)

# The condition name stored when the model is unavailable; it is not an assessment of the patient.
PLACEHOLDER_CONDITION = 'LLM Service Not Configured'
GENDER_LABELS = {'M': 'Male', 'F': 'Female', 'O': 'Other'}
# A differential with reasoning does not fit in the 1000 tokens the diagnosis service defaults to; a reply
# cut off mid-object is not parseable at all, so every diagnosis call asks for at least this much room.
DIAGNOSIS_REPLY_TOKENS = 4000
MAX_DIFFERENTIAL = 5

DIAGNOSIS_SYSTEM_PROMPT = (
    "You are an experienced clinician thinking aloud for the person whose health data this is.\n"
    "Work the way a differential diagnosis is worked: read the evidence, hold several explanations at "
    "once, and say what each rests on. Rank by what the evidence supports, not by what is most alarming "
    "or most common.\n"
    "Be specific. Cite the dates, values, and reference ranges you are reasoning from; a claim that names "
    "nothing in the data is worth less than no claim.\n"
    "Say what argues against each possibility as readily as what argues for it, and be plain about what "
    "the data cannot settle. Where a finding has a dull explanation — a lab's own variation, a known "
    "medicine effect, a single unrepeated result — say so rather than reaching for a diagnosis.\n"
    "You are not the person's doctor and this is not a diagnosis: it is reading meant to make their next "
    "conversation with a clinician a better one. Never tell them to start, stop, or change a treatment.\n"
    "Always respond with valid JSON and nothing else."
)

DIAGNOSIS_REPLY_FORMAT = """{
  "summary": "A few sentences in plain language: what this data looks like overall, and how confident you are",
  "differential": [
    {
      "condition": "The condition you are considering",
      "likelihood": "most likely | possible | less likely",
      "confidence": 3,
      "reasoning": "Why this explanation fits, citing the dates, values, and ranges it rests on",
      "supporting": ["A specific finding that points to it"],
      "against": ["A specific finding that argues against it, or what is missing that you would expect"],
      "confirm_with": ["A test or observation that would make this much more likely"],
      "rule_out_with": ["A test or observation that would largely exclude it"]
    }
  ],
  "false_positives": [
    {
      "condition": "Which of your own candidates is most likely to be wrong, or a mimic you may have latched onto",
      "why_it_might_be_wrong": "The dull explanation you cannot exclude: lab variation, a medicine effect, one unrepeated result, an incidental finding",
      "how_to_tell": "What would settle whether it is real"
    }
  ],
  "patterns": ["Something in the data worth noticing that a quick look would miss: a trend, a coincidence in timing, a relationship between two results"],
  "cautions": ["Something to watch out for, or a reading of this data that would be a mistake to act on"],
  "red_flags": ["A finding that warrants prompt medical attention, if any"],
  "recommendations": "Next steps: which tests to repeat and when, what to track, what to raise with their doctor",
  "follow_up_required": true,
  "follow_up_notes": "Follow-up instructions"
}"""

DIAGNOSIS_TASK = f"""Work through this as a differential, and answer in JSON.

- differential: up to {MAX_DIFFERENTIAL} explanations, ranked by what the evidence supports. Include the
  ordinary explanations, not only the interesting ones. For each, give your reasoning and both what
  supports it and what argues against it. Where the data cannot separate two candidates, say so in both.
- false_positives: be your own sceptic. Which of your candidates is most likely a false alarm, and what
  would show that? A single out-of-range result, a value drifting inside its reference range, a change
  that followed a new medicine, a finding a lab flags routinely — these mislead most often.
- patterns: what you noticed that a quick look would miss. Timing that lines up, two results moving
  together, something that changed when a medicine did, a gap in the record worth filling.
- cautions: what to watch out for, including any way this reading could be misused.
- red_flags: only findings that genuinely warrant prompt attention. An empty list is the right answer when
  there are none; inventing one is a harm of its own.

Confidence is 1 to 5. Use the low end freely: thin evidence honestly labelled is more useful than a
confident guess."""


class LLMError(Exception):
    """The AI diagnosis model gave no answer; the message is safe to show to the user."""


def prepare_timeline_prompt(
    age: Optional[int], gender: Optional[str], summary: str, symptoms: List[str], timeline_text: str
) -> str:
    """A diagnosis prompt that asks the model to follow the patient's health over a dated timeline."""
    asked = '\n'.join(f"- {symptom}" for symptom in symptoms) or (
        '- No new symptoms; review how their health has changed over the timeline.'
    )
    return (
        "You are a medical AI assistant helping a patient understand how their health has changed over time.\n\n"
        "Patient information:\n"
        f"- Age: {age if age is not None else 'Not provided'}\n"
        f"- Gender: {gender or 'Not provided'}\n\n"
        "The patient's own summary:\n"
        f"{summary or 'None given.'}\n\n"
        "What the patient is asking about now:\n"
        f"{asked}\n\n"
        f"{timeline_text}\n\n"
        "Read the whole timeline in date order. Relate symptoms, lab results, and medicines by when they happened: "
        "what changed after a medicine started or stopped, which results moved into or out of their reference range, "
        "and whether a long-running condition is improving, stable, or getting worse. A single result is weaker "
        "evidence than a trend, and a value drifting within its reference range is usually not a finding at all. "
        "Earlier AI assessments are not a doctor's diagnoses and carry no weight of their own. Personal details are "
        "shown as [REDACTED].\n\n"
        f"{DIAGNOSIS_TASK}\n\n"
        "Answer as a JSON object with this structure:\n"
        f"{DIAGNOSIS_REPLY_FORMAT}\n\n"
        "IMPORTANT: This is for informational purposes only. The patient should always consult with a qualified "
        "healthcare professional for proper diagnosis and treatment."
    )


def _texts(value: Any, limit: int = 12) -> List[str]:
    """A list of short strings from whatever the model put there, dropping blanks."""
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    out = []
    for item in value:
        text = str(item.get('text') if isinstance(item, dict) else item or '').strip()
        if text:
            out.append(text[:600])
    return out[:limit]


def _confidence(value: Any, default: int = 3) -> int:
    try:
        return max(1, min(5, int(float(value))))
    except (TypeError, ValueError):
        return default


def _candidate(item: Any) -> Optional[Dict[str, Any]]:
    """One entry of the differential, with only the fields the app shows."""
    if not isinstance(item, dict):
        return None
    condition = str(item.get('condition') or item.get('condition_name') or '').strip()
    if not condition:
        return None
    likelihood = str(item.get('likelihood') or '').strip().lower()
    return {
        'condition': condition[:200],
        'likelihood': likelihood if likelihood in ('most likely', 'possible', 'less likely') else 'possible',
        'confidence': _confidence(item.get('confidence')),
        'reasoning': str(item.get('reasoning') or '').strip()[:2000],
        'supporting': _texts(item.get('supporting')),
        'against': _texts(item.get('against')),
        'confirm_with': _texts(item.get('confirm_with')),
        'rule_out_with': _texts(item.get('rule_out_with')),
    }


def _false_positive(item: Any) -> Optional[Dict[str, str]]:
    if not isinstance(item, dict):
        text = str(item or '').strip()
        return {'condition': text[:200], 'why_it_might_be_wrong': '', 'how_to_tell': ''} if text else None
    condition = str(item.get('condition') or '').strip()
    if not condition:
        return None
    return {
        'condition': condition[:200],
        'why_it_might_be_wrong': str(item.get('why_it_might_be_wrong') or item.get('why') or '').strip()[:1000],
        'how_to_tell': str(item.get('how_to_tell') or item.get('how_to_tell_apart') or '').strip()[:1000],
    }


def normalize_diagnosis(reply: Dict[str, Any]) -> Dict[str, Any]:
    """The model's answer in the shape the app stores and shows.

    The differential is the substance; `condition_name`, `description`, and `confidence_score` are filled
    from its first entry so that everything written before this existed — the list, the history, the
    timeline sent to later diagnoses — keeps working unchanged.
    """
    differential = [item for item in (_candidate(row) for row in reply.get('differential') or []) if item]
    differential = differential[:MAX_DIFFERENTIAL]
    leading = differential[0] if differential else None

    summary = str(reply.get('summary') or reply.get('description') or '').strip()
    condition_name = str(reply.get('condition_name') or (leading['condition'] if leading else '')).strip()
    description = summary or (leading['reasoning'] if leading else '')
    confidence = reply.get('confidence_score')
    if confidence is None and leading:
        confidence = leading['confidence']

    return {
        'condition_name': (condition_name or 'Unknown Condition')[:200],
        'description': description,
        'confidence_score': _confidence(confidence),
        'recommendations': str(reply.get('recommendations') or 'Consult with a healthcare professional.').strip(),
        'follow_up_required': bool(reply.get('follow_up_required', True)),
        'follow_up_notes': str(reply.get('follow_up_notes') or '').strip(),
        'analysis': {
            'summary': summary,
            'differential': differential,
            'false_positives': [
                item for item in (_false_positive(row) for row in reply.get('false_positives') or []) if item
            ][:MAX_DIFFERENTIAL],
            'patterns': _texts(reply.get('patterns')),
            'cautions': _texts(reply.get('cautions')),
            'red_flags': _texts(reply.get('red_flags')),
        },
    }


class LLMService:
    """Service for integrating with LLM APIs for diagnosis assistance"""

    def __init__(self):
        # Saved AI settings, falling back to OPENAI_* environment variables.
        self.config = get_ai_config(ROLE_DIAGNOSIS)

    def anonymize_health_data(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Remove contact details and the account holder's name from every free-text value."""
        redactor = Redactor(user_data.get('_redaction_names') or ())

        def redact(value: Any) -> Any:
            if isinstance(value, str):
                return redactor.line(value)
            if isinstance(value, list):
                return [redact(item) for item in value]
            if isinstance(value, tuple):
                return [redact(item) for item in value]
            if isinstance(value, dict):
                return {key: redact(item) for key, item in value.items()}
            return value

        anonymized = {
            'age': user_data.get('age'),
            'gender': user_data.get('gender'),
            'symptoms': redact(user_data.get('symptoms', [])),
            'test_results': redact(user_data.get('test_results', [])),
            'medications': redact(user_data.get('medications', [])),
            'medical_history': redact(user_data.get('medical_history', [])),
        }

        return anonymized

    def prepare_diagnosis_prompt(self, anonymized_data: Dict[str, Any]) -> str:
        """Prepare a prompt for LLM diagnosis"""
        prompt = f"""Read this anonymized health data and work through what could explain it.

Patient Information:
- Age: {anonymized_data.get('age', 'Not provided')}
- Gender: {anonymized_data.get('gender', 'Not provided')}

Symptoms:
{self._format_symptoms(anonymized_data.get('symptoms', []))}

Test Results:
{self._format_test_results(anonymized_data.get('test_results', []))}

Current Medications:
{self._format_medications(anonymized_data.get('medications', []))}

{DIAGNOSIS_TASK}

Answer as a JSON object with this structure:
{DIAGNOSIS_REPLY_FORMAT}

IMPORTANT: This is for informational purposes only. The patient should always consult with a qualified healthcare professional for proper diagnosis and treatment.
"""
        return prompt

    def _format_symptoms(self, symptoms: List[Dict[str, Any]]) -> str:
        """Format symptoms for the prompt"""
        if not symptoms:
            return "No symptoms reported"

        formatted = []
        for symptom in symptoms:
            if isinstance(symptom, dict):
                formatted.append(f"- {symptom.get('description', 'Unknown symptom')} (Severity: {symptom.get('severity', 'Unknown')}, Duration: {symptom.get('duration', 'Unknown')})")
            else:
                formatted.append(f"- {symptom}")

        return "\n".join(formatted)

    def _format_test_results(self, test_results: List[Dict[str, Any]]) -> str:
        """Format test results for the prompt"""
        if not test_results:
            return "No test results available"

        formatted = []
        for result in test_results:
            if isinstance(result, dict):
                status = result.get('status', 'Unknown')
                ref_range = result.get('reference_range', 'No reference range')
                formatted.append(f"- {result.get('test_name', 'Unknown test')}: {result.get('value', 'N/A')} {result.get('unit', '')} (Status: {status}, Reference: {ref_range})")
            else:
                formatted.append(f"- {result}")

        return "\n".join(formatted)

    def _format_medications(self, medications: List[Dict[str, Any]]) -> str:
        """Format medications for the prompt"""
        if not medications:
            return "No current medications"

        formatted = []
        for med in medications:
            if isinstance(med, dict):
                formatted.append(f"- {med.get('medication_name', 'Unknown medication')} ({med.get('dosage', 'Unknown dosage')})")
            else:
                formatted.append(f"- {med}")

        return "\n".join(formatted)

    def generate_diagnosis(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Generate diagnosis using LLM"""
        if not self.config.is_configured:
            logger.warning("AI diagnosis is not configured")
            return self._get_placeholder_diagnosis()

        try:
            anonymized_data = self.anonymize_health_data(user_data)
            prompt = self.prepare_diagnosis_prompt(anonymized_data)

            return self._call_llm_api(prompt)

        except Exception as e:
            logger.error(f"Error calling LLM API: {e}")
            return self._get_placeholder_diagnosis()

    def _call_llm_api(self, prompt: str) -> Dict[str, Any]:
        """Call the configured OpenAI-compatible chat API"""
        try:
            return self._diagnosis_from_reply(self._ask(prompt))
        except Exception as e:
            logger.error(f"AI diagnosis API error: {e}")
            return self._get_placeholder_diagnosis()

    def generate_timeline_diagnosis(self, prompt: str) -> Dict[str, Any]:
        """Ask for a diagnosis from a timeline prompt; raises LLMError instead of returning a placeholder."""
        if not self.config.is_configured:
            raise LLMError('AI diagnosis is not set up. Configure it in AI settings.')
        try:
            content = self._ask(prompt)
        except Exception as exc:
            logger.error("AI diagnosis API error: %s", exc)
            raise LLMError(f'The AI diagnosis model did not respond ({type(exc).__name__}).') from exc
        return self._diagnosis_from_reply(content)

    def _ask(self, prompt: str) -> str:
        return chat_json(
            self.config,
            [{"role": "system", "content": DIAGNOSIS_SYSTEM_PROMPT}, {"role": "user", "content": prompt}],
            max_tokens=max(self.config.max_tokens, DIAGNOSIS_REPLY_TOKENS),
            temperature=self.config.temperature_or(DEFAULT_TEMPERATURES[ROLE_DIAGNOSIS]),
        )

    def _diagnosis_from_reply(self, content: str) -> Dict[str, Any]:
        try:
            result = normalize_diagnosis(parse_json_object(content))
            result['raw_response'] = content
            return result
        except ValueError:
            logger.error(f"LLM returned invalid JSON: {content[:200]}")
            return {
                **normalize_diagnosis({
                    'condition_name': 'Analysis Complete',
                    'description': content[:500],
                    'confidence_score': 2,
                    'recommendations': 'Consult with a healthcare professional for proper diagnosis.',
                    'follow_up_notes': 'Schedule follow-up appointment with your doctor.',
                }),
                'raw_response': content,
            }

    def _get_placeholder_diagnosis(self) -> Dict[str, Any]:
        """Get placeholder diagnosis when LLM is not available"""
        return {
            'condition_name': PLACEHOLDER_CONDITION,
            'description': (
                'The AI diagnosis service is not configured or not reachable. '
                'An administrator can set it up under AI settings. '
                'This is not a medical diagnosis - please consult with a healthcare professional.'
            ),
            'confidence_score': 1,
            'recommendations': 'Please consult with a healthcare professional for proper diagnosis and treatment.',
            'follow_up_required': True,
            'follow_up_notes': 'Configure AI diagnosis in AI settings to enable AI diagnosis features.',
            'red_flags': [],
            'raw_response': 'LLM service not available - not configured or unreachable.'
        }

    def analyze_health_trends(self, trend_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze health trends over time using LLM"""
        if not trend_data:
            return {'analysis': 'No trend data available'}

        if not self.config.is_configured:
            return self._simple_trend_analysis(trend_data)

        try:
            prompt = f"""
Analyze the following health trend data and provide insights:

Parameter: {trend_data[0].get('parameter_name', 'Unknown')}
Data points:
{json.dumps(trend_data, indent=2)}

Please provide your response as a JSON object with:
{{
  "trend_type": "IMPROVING|STABLE|DETERIORATING|FLUCTUATING",
  "analysis": "Detailed analysis of the trend",
  "recommendations": "Recommendations based on the trend"
}}
"""
            content = chat_json(
                self.config,
                [
                    {"role": "system", "content": "You are a medical data analyst. Always respond with valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=500,
                temperature=self.config.temperature_or(DEFAULT_TEMPERATURES[ROLE_DIAGNOSIS]),
            )
            result = parse_json_object(content)
            result.setdefault('trend_type', 'STABLE')
            result.setdefault('analysis', 'Trend analysis complete.')
            result.setdefault('recommendations', 'Continue monitoring with your healthcare provider.')
            return result

        except Exception as e:
            logger.error(f"Error analyzing trends with LLM: {e}")
            return self._simple_trend_analysis(trend_data)

    def _simple_trend_analysis(self, trend_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Simple rule-based trend analysis when LLM is not available"""
        if len(trend_data) < 2:
            return {
                'trend_type': 'STABLE',
                'analysis': 'Insufficient data points for trend analysis.',
                'recommendations': 'Continue monitoring with your healthcare provider.'
            }

        values = []
        for point in trend_data:
            try:
                val = float(point.get('value', 0))
                values.append(val)
            except (ValueError, TypeError):
                continue

        if len(values) < 2:
            return {
                'trend_type': 'STABLE',
                'analysis': 'Could not extract numeric values for trend analysis.',
                'recommendations': 'Continue monitoring with your healthcare provider.'
            }

        avg_first_half = sum(values[:len(values)//2]) / (len(values)//2)
        avg_second_half = sum(values[len(values)//2:]) / (len(values) - len(values)//2)

        change_pct = ((avg_second_half - avg_first_half) / avg_first_half * 100) if avg_first_half else 0

        if abs(change_pct) < 5:
            trend_type = 'STABLE'
            analysis = f'Values are stable (change: {change_pct:.1f}%).'
        elif change_pct > 0:
            trend_type = 'IMPROVING' if trend_data[0].get('higher_is_better', False) else 'DETERIORATING'
            analysis = f'Values show an increasing trend (change: {change_pct:.1f}%).'
        else:
            trend_type = 'DETERIORATING' if trend_data[0].get('higher_is_better', False) else 'IMPROVING'
            analysis = f'Values show a decreasing trend (change: {change_pct:.1f}%).'

        return {
            'trend_type': trend_type,
            'analysis': analysis,
            'recommendations': 'Continue monitoring with your healthcare provider.'
        }


def calculate_age(birth_date) -> Optional[int]:
    """Calculate age from a date object"""
    if not birth_date:
        return None
    if isinstance(birth_date, str):
        try:
            birth_date = date.fromisoformat(birth_date)
        except ValueError:
            return None
    if isinstance(birth_date, date):
        today = date.today()
        age = today.year - birth_date.year
        if (today.month, today.day) < (birth_date.month, birth_date.day):
            age -= 1
        return age
    return None


# Convenience functions
def generate_diagnosis(user_data: Dict[str, Any]) -> Dict[str, Any]:
    """Generate diagnosis using LLM service"""
    service = LLMService()
    return service.generate_diagnosis(user_data)


def analyze_health_trends(trend_data: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Analyze health trends using LLM service"""
    service = LLMService()
    return service.analyze_health_trends(trend_data)
