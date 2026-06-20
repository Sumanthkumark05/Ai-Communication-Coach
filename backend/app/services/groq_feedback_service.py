import time
import json
import logging
import requests
import re
from typing import Dict, Any, List, Optional
from app.config import settings

logger = logging.getLogger("jam_analyzer")

class GroqFeedbackService:
    def __init__(self):
        self.api_key = settings.GROQ_API_KEY
        self.model = settings.GROQ_MODEL or "llama-3.3-70b-versatile"
        
        if not self.api_key:
            logger.error("[GroqFeedbackService] GROQ_API_KEY is not configured in settings.")
        else:
            logger.info("LLM Client Initialized")
            logger.info(f"[GroqFeedbackService] Initialized with model: {self.model}")

    def call_groq_json(self, prompt: str, system_prompt: str = "You are an elite speech intelligence advisor. Output clean JSON only.", force_schema: bool = True) -> Dict[str, Any]:
        """
        Sends request to Groq API and strictly returns a JSON object.
        If force_schema is True, it forces the structured qualitative feedback response format.
        """
        start_time = time.time()
        prompt_len = len(prompt)
        logger.info("LLM Request Sent")
        logger.info(f"[GroqFeedbackService] Groq Request Started. Model: {self.model}, Prompt Length: {prompt_len} chars")

        fallback_result = {
            "executive_summary": "Analysis completed but detailed AI feedback could not be generated.",
            "strengths": ["Analysis completed but detailed AI feedback could not be generated."],
            "areas_for_improvement": ["Analysis completed but detailed AI feedback could not be generated."],
            "recommendations": ["Analysis completed but detailed AI feedback could not be generated."],
            "action_plan": ["Analysis completed but detailed AI feedback could not be generated."],
            "expert_response": "Analysis completed but detailed AI feedback could not be generated.",
            "missing_concepts": ["Analysis completed but detailed AI feedback could not be generated."],
            "coaching_feedback": "Analysis completed but detailed AI feedback could not be generated."
        }

        if not self.api_key:
            logger.error("[GroqFeedbackService] Request cancelled: GROQ_API_KEY is missing.")
            return fallback_result

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        if force_schema:
            # Make sure the prompt instructs the model to return the specific JSON fields
            schema_instruction = """
            You must output your response as a valid JSON object matching this EXACT key schema:
            {
              "executive_summary": "string summary of the candidate's speech and performance details",
              "strengths": ["list of observed communication strengths (at least 2-3 items)"],
              "areas_for_improvement": ["list of observed communication areas of improvement (at least 2-3 items)"],
              "recommendations": ["list of actionable coaching recommendations"],
              "action_plan": ["list of immediate and short term practice steps"],
              "expert_response": "a comprehensive, expert-level response to the topic question",
              "missing_concepts": ["key concepts/definitions relevant to the topic that the user completely missed"],
              "coaching_feedback": "detailed communication twin mentor coaching feedback regarding delivery metrics, pacing, eye contact, and enunciation"
            }
            """
            full_prompt = f"{prompt}\n\n{schema_instruction}\nReturn ONLY clean, raw JSON matching this schema."
        else:
            full_prompt = prompt

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": full_prompt}
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.2
        }

        try:
            res = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=30
            )
            execution_time = time.time() - start_time
            
            if res.status_code != 200:
                logger.error(f"[GroqFeedbackService] Groq API returned status code {res.status_code}: {res.text}")
                return fallback_result if force_schema else {}

            res_json = res.json()
            raw_response = res_json["choices"][0]["message"]["content"]
            response_len = len(raw_response)
            logger.info("LLM Response Received")
            logger.info(f"[GroqFeedbackService] Groq Response Received. Length: {response_len} chars. Execution Time: {execution_time:.2f}s")

            # JSON parsing
            try:
                parsed_data = json.loads(raw_response.strip())
                logger.info("[GroqFeedbackService] JSON Parsed Successfully.")
            except Exception:
                # Try fallback regex extraction of json block
                match = re.search(r"(\{.*\})", raw_response, re.DOTALL)
                if match:
                    parsed_data = json.loads(match.group(1).strip())
                    logger.info("[GroqFeedbackService] JSON Parsed Successfully via regex extraction.")
                else:
                    raise ValueError("Could not locate JSON brackets in raw content.")

            # Validate keys and replace missing/blank ones with defaults (only when forcing qualitative schema)
            if force_schema:
                for key in fallback_result.keys():
                    if key not in parsed_data or parsed_data[key] is None or parsed_data[key] == "" or (isinstance(parsed_data[key], list) and not parsed_data[key]):
                        parsed_data[key] = fallback_result[key]

            return parsed_data

        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"[GroqFeedbackService] Groq call or parse failed: {e}. Execution Time: {execution_time:.2f}s")
            return fallback_result if force_schema else {}

    def call_groq_text(self, prompt: str, system_prompt: str = "You are an expert speaker.") -> str:
        """
        Fallback simple text completion method using openai/gpt-oss-120b for tasks like generating questions or rebuttals.
        """
        start_time = time.time()
        prompt_len = len(prompt)
        logger.info("LLM Request Sent")
        logger.info(f"[GroqFeedbackService] Groq Text Request Started. Model: {self.model}, Prompt Length: {prompt_len} chars")

        fallback_text = "Analysis completed but detailed AI feedback could not be generated."

        if not self.api_key:
            logger.error("[GroqFeedbackService] Text Request cancelled: GROQ_API_KEY is missing.")
            return fallback_text

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.7
        }

        try:
            res = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=20
            )
            execution_time = time.time() - start_time
            
            if res.status_code != 200:
                logger.error(f"[GroqFeedbackService] Groq Text API returned status code {res.status_code}: {res.text}")
                return fallback_text

            res_json = res.json()
            raw_response = res_json["choices"][0]["message"]["content"].strip()
            response_len = len(raw_response)
            logger.info("LLM Response Received")
            logger.info(f"[GroqFeedbackService] Groq Text Response Received. Length: {response_len} chars. Execution Time: {execution_time:.2f}s")
            return raw_response

        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"[GroqFeedbackService] Groq Text call failed: {e}. Execution Time: {execution_time:.2f}s")
            return fallback_text

    async def call_groq_json_async(self, prompt: str, system_prompt: str = "You are an elite speech intelligence advisor. Output clean JSON only.", force_schema: bool = True) -> Dict[str, Any]:
        """
        Asynchronously sends request to Groq API and strictly returns a JSON object.
        If force_schema is True, it forces the structured qualitative feedback response format.
        """
        import httpx
        import asyncio
        start_time = time.time()
        prompt_len = len(prompt)
        logger.info("LLM Request Sent")
        logger.info(f"[GroqFeedbackService] Async Groq Request Started. Model: {self.model}, Prompt Length: {prompt_len} chars")

        fallback_result = {
            "executive_summary": "Analysis completed but detailed AI feedback could not be generated.",
            "strengths": ["Analysis completed but detailed AI feedback could not be generated."],
            "areas_for_improvement": ["Analysis completed but detailed AI feedback could not be generated."],
            "recommendations": ["Analysis completed but detailed AI feedback could not be generated."],
            "action_plan": ["Analysis completed but detailed AI feedback could not be generated."],
            "expert_response": "Analysis completed but detailed AI feedback could not be generated.",
            "missing_concepts": ["Analysis completed but detailed AI feedback could not be generated."],
            "coaching_feedback": "Analysis completed but detailed AI feedback could not be generated."
        }

        if not self.api_key:
            logger.error("[GroqFeedbackService] Request cancelled: GROQ_API_KEY is missing.")
            return fallback_result

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        if force_schema:
            schema_instruction = """
            You must output your response as a valid JSON object matching this EXACT key schema:
            {
              "executive_summary": "string summary of the candidate's speech and performance details",
              "strengths": ["list of observed communication strengths (at least 2-3 items)"],
              "areas_for_improvement": ["list of observed communication areas of improvement (at least 2-3 items)"],
              "recommendations": ["list of actionable coaching recommendations"],
              "action_plan": ["list of immediate and short term practice steps"],
              "expert_response": "a comprehensive, expert-level response to the topic question",
              "missing_concepts": ["key concepts/definitions relevant to the topic that the user completely missed"],
              "coaching_feedback": "detailed communication twin mentor coaching feedback regarding delivery metrics, pacing, eye contact, and enunciation"
            }
            """
            full_prompt = f"{prompt}\n\n{schema_instruction}\nReturn ONLY clean, raw JSON matching this schema."
        else:
            full_prompt = prompt

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": full_prompt}
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.2
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                res = await client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers=headers,
                    json=payload
                )
            execution_time = time.time() - start_time
            
            if res.status_code != 200:
                logger.error(f"[GroqFeedbackService] Groq Async API returned status code {res.status_code}: {res.text}")
                return fallback_result if force_schema else {}

            res_json = res.json()
            raw_response = res_json["choices"][0]["message"]["content"]
            response_len = len(raw_response)
            logger.info("LLM Response Received")
            logger.info(f"[GroqFeedbackService] Groq Async Response Received. Length: {response_len} chars. Execution Time: {execution_time:.2f}s")

            # JSON parsing
            try:
                parsed_data = json.loads(raw_response.strip())
                logger.info("[GroqFeedbackService] JSON Parsed Successfully (Async).")
            except Exception:
                # Try fallback regex extraction of json block
                match = re.search(r"(\{.*\})", raw_response, re.DOTALL)
                if match:
                    parsed_data = json.loads(match.group(1).strip())
                    logger.info("[GroqFeedbackService] JSON Parsed Successfully via regex extraction (Async).")
                else:
                    raise ValueError("Could not locate JSON brackets in raw content.")

            # Validate keys
            if force_schema:
                for key in fallback_result.keys():
                    if key not in parsed_data or parsed_data[key] is None or parsed_data[key] == "" or (isinstance(parsed_data[key], list) and not parsed_data[key]):
                        parsed_data[key] = fallback_result[key]

            return parsed_data

        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"[GroqFeedbackService] Groq Async call or parse failed: {e}. Execution Time: {execution_time:.2f}s")
            return fallback_result if force_schema else {}

    async def call_groq_text_async(self, prompt: str, system_prompt: str = "You are an expert speaker.") -> str:
        """
        Asynchronously sends text completion requests to Groq.
        """
        import httpx
        start_time = time.time()
        prompt_len = len(prompt)
        logger.info("LLM Request Sent")
        logger.info(f"[GroqFeedbackService] Groq Async Text Request Started. Model: {self.model}, Prompt Length: {prompt_len} chars")

        fallback_text = "Analysis completed but detailed AI feedback could not be generated."

        if not self.api_key:
            logger.error("[GroqFeedbackService] Text Request cancelled: GROQ_API_KEY is missing.")
            return fallback_text

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.7
        }

        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                res = await client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers=headers,
                    json=payload
                )
            execution_time = time.time() - start_time
            
            if res.status_code != 200:
                logger.error(f"[GroqFeedbackService] Groq Async Text API returned status code {res.status_code}: {res.text}")
                return fallback_text

            res_json = res.json()
            raw_response = res_json["choices"][0]["message"]["content"].strip()
            response_len = len(raw_response)
            logger.info("LLM Response Received")
            logger.info(f"[GroqFeedbackService] Groq Async Text Response Received. Length: {response_len} chars. Execution Time: {execution_time:.2f}s")
            return raw_response

        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"[GroqFeedbackService] Groq Async Text call failed: {e}. Execution Time: {execution_time:.2f}s")
            return fallback_text
