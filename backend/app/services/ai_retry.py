import time
import logging
from typing import Callable, Any, Type, Optional
from sqlalchemy.orm import Session as SqlSession

logger = logging.getLogger("jam_analyzer")

def execute_with_retry(
    db: SqlSession,
    job_model: Type[Any],
    job_id: str,
    fn: Callable[[], Any],
    max_retries: int = 4,
    base_delay: float = 2.0
) -> Any:
    """
    Executes an LLM API call (fn) and automatically handles rate limits (HTTP 429)
    with exponential backoff.
    
    If HTTP 429 is encountered:
      - Marks job/session status to 'retrying'
      - Increments retry_count in DB
      - Saves last_error/error in DB
      - Sleeps with exponential backoff and retries.
    """
    retry_count = 0
    
    def update_job_status(status_str: str, err_msg: Optional[str] = None):
        try:
            # Query fresh job instance to avoid session conflicts
            job = db.query(job_model).filter(job_model.id == job_id).first()
            if job:
                # Update status (Session & DocumentSession use analysis_status, BackgroundJob uses status)
                if hasattr(job, "analysis_status"):
                    job.analysis_status = status_str.lower()
                elif hasattr(job, "status"):
                    job.status = status_str.lower()
                
                # Update retry columns
                if hasattr(job, "retry_count"):
                    job.retry_count = retry_count
                if hasattr(job, "last_error"):
                    job.last_error = err_msg or ""
                
                # Standard error field fallback
                if hasattr(job, "error"):
                    job.error = err_msg or ""
                
                db.commit()
                db.refresh(job)
        except Exception as exc:
            logger.error(f"[LLM] Database status update failed: {exc}")
            db.rollback()

    while True:
        try:
            logger.info(f"[LLM] Request Started (attempt={retry_count + 1})")
            result = fn()
            logger.info(f"[LLM] Response Received (attempt={retry_count + 1})")
            return result
        except Exception as e:
            err_msg = str(e)
            is_rate_limit = "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg or "quota" in err_msg.lower()
            
            if is_rate_limit:
                retry_count += 1
                logger.warning(f"[LLM] Quota Error (HTTP 429) on attempt {retry_count}/{max_retries}")
                
                if retry_count >= max_retries:
                    logger.error(f"[LLM] Job Failed: Max retries ({max_retries}) exceeded.")
                    update_job_status("failed", f"Max retries exceeded. Last error: {err_msg}")
                    raise RuntimeError(f"LLM API rate limit exceeded. Max retries reached. Error: {err_msg}") from e
                
                # Update database state to RETRYING and log retry attempt
                logger.warning(f"[LLM] Retry Attempt {retry_count} scheduled. Error: {err_msg}")
                update_job_status("retrying", err_msg)
                
                # Calculate backoff delay
                delay = base_delay * (2 ** (retry_count - 1))
                logger.info(f"[LLM] Sleeping for {delay:.2f}s (exponential backoff)...")
                time.sleep(delay)
            else:
                # Other non-429 error (invalid model, bad request etc.) - mark failed and raise
                logger.error(f"[LLM] Non-retryable error: {err_msg}")
                update_job_status("failed", err_msg)
                raise e
