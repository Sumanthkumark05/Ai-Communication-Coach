const API_BASE = process.env.NEXT_PUBLIC_API_URL
  ? `${process.env.NEXT_PUBLIC_API_URL}/api`
  : "http://localhost:8000/api";

const BACKEND_ROOT = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

console.log(`[API] Base URL configured as: ${API_BASE}`);


export function setToken(token: string) {
  if (typeof window !== "undefined") {
    if (!token || token === "undefined" || token === "null") {
      localStorage.removeItem("access_token");
      console.log("Token Cleared");
      return;
    }
    let sanitizedToken = token;
    if (sanitizedToken.startsWith('"') && sanitizedToken.endsWith('"')) {
      sanitizedToken = sanitizedToken.slice(1, -1);
    } else if (sanitizedToken.startsWith("'") && sanitizedToken.endsWith("'")) {
      sanitizedToken = sanitizedToken.slice(1, -1);
    }
    localStorage.setItem("access_token", sanitizedToken);
    console.log("Token Stored");
  }
}

function isTokenExpired(token: string): boolean {
  try {
    const parts = token.split('.');
    if (parts.length !== 3) return true;
    const payload = JSON.parse(atob(parts[1].replace(/-/g, '+').replace(/_/g, '/')));
    if (payload.exp) {
      const currentTime = Math.floor(Date.now() / 1000);
      return payload.exp < currentTime;
    }
  } catch (e) {
    return true;
  }
  return false;
}

export function getToken(): string | null {
  if (typeof window !== "undefined") {
    let token = localStorage.getItem("access_token");
    if (token) {
      if (token === "undefined" || token === "null" || token.trim() === "") {
        localStorage.removeItem("access_token");
        return null;
      }
      if (token.startsWith('"') && token.endsWith('"')) {
        token = token.slice(1, -1);
      } else if (token.startsWith("'") && token.endsWith("'")) {
        token = token.slice(1, -1);
      }
      
      if (isTokenExpired(token)) {
        localStorage.removeItem("access_token");
        console.log("Expired token detected locally and cleared");
        return null;
      }
      
      console.log("Token Loaded");
      return token;
    }
  }
  return null;
}

export function logout() {
  if (typeof window !== "undefined") {
    localStorage.removeItem("access_token");
  }
}

const inFlightRequests = new Map<string, Promise<any>>();

async function fetchRaw(endpoint: string, options: RequestInit & { timeout?: number } = {}) {
  const { timeout, ...fetchOptions } = options;
  const token = getToken();
  
  // Construct plain object headers to ensure safe serialization
  const headers: Record<string, string> = {};
  if (fetchOptions.headers) {
    if (fetchOptions.headers instanceof Headers) {
      fetchOptions.headers.forEach((value, key) => {
        headers[key] = value;
      });
    } else if (Array.isArray(fetchOptions.headers)) {
      fetchOptions.headers.forEach(([key, value]) => {
        headers[key] = value;
      });
    } else {
      Object.assign(headers, fetchOptions.headers);
    }
  }

  if (token && !headers["Authorization"]) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const controller = new AbortController();
  const timeoutMs = timeout ?? 120000; // Increased to 120 seconds default
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  const fullUrl = `${API_BASE}${endpoint}`;
  const method = (fetchOptions.method || "GET").toUpperCase();
  const payloadSize = fetchOptions.body instanceof FormData
    ? "[FormData — size unknown at fetch time]"
    : fetchOptions.body
      ? `${String(fetchOptions.body).length} bytes`
      : "no body";

  console.log(`[API] ▶ Request started: ${method} ${fullUrl} | payload: ${payloadSize}`);

  let res: Response;
  try {
    res = await fetch(fullUrl, {
      ...fetchOptions,
      headers,
      signal: controller.signal,
    });
    clearTimeout(timeoutId);
  } catch (err: any) {
    clearTimeout(timeoutId);
    if (err.name === "AbortError") {
      const msg = `[API] ✗ TIMEOUT after ${timeoutMs}ms — ${method} ${fullUrl}`;
      console.error(msg);
      throw new Error(`Request timed out after ${timeoutMs / 1000}s. The backend may still be processing — please wait and refresh.`);
    }
    // Network-level failure
    const networkMsg = err.message || "Unknown network error";
    console.error(`[API] ✗ NETWORK ERROR — ${method} ${fullUrl}\n  └─ ${networkMsg}`);
    if (networkMsg.includes("Failed to fetch") || networkMsg.includes("NetworkError")) {
      throw new Error(
        `Cannot reach backend at ${BACKEND_ROOT}. ` +
        `Verify the backend is running (uvicorn main:app --port 8000) and CORS allows http://localhost:3000.`
      );
    }
    throw new Error(`Network error: ${networkMsg}`);
  }

  console.log(`[API] ◀ Response: ${method} ${fullUrl} → HTTP ${res.status} ${res.statusText}`);

  if (res.status === 401) {
    logout();
    if (typeof window !== "undefined") {
      window.dispatchEvent(new Event("auth-expired"));
    }
  }

  if (!res.ok) {
    let rawBody = "";
    try {
      rawBody = await res.text();
    } catch (_) {
      rawBody = "<could not read response body>";
    }
    console.error(
      `[API] ✗ HTTP ${res.status} — ${method} ${fullUrl}\n` +
      `  └─ Response body: ${rawBody.slice(0, 500)}`
    );
    let errorMessage = `HTTP ${res.status} error`;
    try {
      const errorData = JSON.parse(rawBody);
      if (typeof errorData.detail === "string") {
        errorMessage = errorData.detail;
      } else if (Array.isArray(errorData.detail)) {
        errorMessage = errorData.detail
          .map((err: any) => {
            const field = err.loc && err.loc.length > 1 ? err.loc.slice(1).join(".") : (err.loc ? err.loc.join(".") : "");
            return field ? `${field}: ${err.msg}` : err.msg;
          })
          .join(", ");
      } else if (errorData.detail && typeof errorData.detail === "object") {
        errorMessage = JSON.stringify(errorData.detail);
      } else if (errorData.message) {
        errorMessage = errorData.message;
      }
    } catch (_) {
      errorMessage = rawBody.slice(0, 300) || `HTTP ${res.status}`;
    }
    throw new Error(errorMessage);
  }

  return res.json();
}

async function fetchAPI(endpoint: string, options: RequestInit & { timeout?: number } = {}): Promise<any> {
  const method = (options.method || "GET").toUpperCase();
  const key = `${method}:${endpoint}:${options.body ? String(options.body) : ""}`;

  if (inFlightRequests.has(key)) {
    console.log(`[API] ⚡ Deduplicating in-flight request: ${method} ${endpoint}`);
    return inFlightRequests.get(key);
  }

  const promise = (async () => {
    let lastError: any = null;
    const maxRetries = 3;

    for (let attempt = 0; attempt <= maxRetries; attempt++) {
      try {
        if (attempt > 0) {
          // Exponential backoff: 2^attempt * 1000ms + random jitter up to 500ms
          const delay = Math.min(10000, Math.pow(2, attempt) * 1000 + Math.random() * 500);
          console.log(`[API] 🔄 Retrying request (attempt ${attempt}/${maxRetries}) in ${Math.round(delay)}ms: ${method} ${endpoint}`);
          await new Promise((resolve) => setTimeout(resolve, delay));
        }

        return await fetchRaw(endpoint, options);
      } catch (err: any) {
        lastError = err;
        console.warn(`[API] Attempt ${attempt} failed: ${err.message}`);

        // Never retry 404 — the resource does not exist; retrying wastes time
        // and causes "Job not found" loops in the coach polling flow.
        if (err.message && (err.message.includes("404") || err.message === "Job not found.")) {
          throw err;
        }

        // Do not retry on client errors (4xx) except for timeout/rate limit issues (408, 429)
        const isClientError = err.message &&
          !err.message.startsWith("Cannot reach") &&
          !err.message.includes("500") && !err.message.includes("502") &&
          !err.message.includes("503") && !err.message.includes("504") &&
          !err.message.includes("408") && !err.message.includes("429");

        if (isClientError) {
          throw err;
        }
      }
    }
    throw lastError;
  })();

  inFlightRequests.set(key, promise);

  try {
    return await promise;
  } finally {
    inFlightRequests.delete(key);
  }
}

export const api = {
  // Auth API
  logout,

  /**
   * Verifies the backend is reachable and healthy.
   * Returns true when healthy, false when unreachable.
   */
  async checkHealth(): Promise<{ ok: boolean; status?: string; error?: string }> {
    try {
      const res = await fetch(`${BACKEND_ROOT}/health`, { method: "GET" });
      if (res.ok) {
        const data = await res.json();
        console.log(`[API] ✓ Health check passed — backend status: ${data.status}`);
        return { ok: true, status: data.status };
      }
      return { ok: false, error: `HTTP ${res.status}` };
    } catch (err: any) {
      console.error(`[API] ✗ Health check failed — backend may be down: ${err.message}`);
      return { ok: false, error: err.message };
    }
  },

  /**
   * Fetches the debug/system module availability report.
   */
  async checkSystemModules() {
    try {
      const res = await fetch(`${BACKEND_ROOT}/debug/system`, { method: "GET" });
      const data = await res.json();
      console.log(`[API] System module check:`, data);
      return data;
    } catch (err: any) {
      console.error(`[API] System module check failed:`, err.message);
      return null;
    }
  },

  async signup(email: string, name: string, password: string) {
    return fetchAPI("/auth/signup", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, name, password }),
    });
  },

  async login(email: string, password: string) {
    const data = await fetchAPI("/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    if (data.access_token) {
      console.log("User Logged In");
      setToken(data.access_token);
    }
    return data;
  },

  async getMe() {
    return fetchAPI("/auth/me");
  },

  // JAM API
  async generateTopic(category?: string, difficulty?: string) {
    const params = new URLSearchParams();
    if (category) params.append("category", category);
    if (difficulty) params.append("difficulty", difficulty);
    const query = params.toString() ? `?${params.toString()}` : "";
    return fetchAPI(`/generate-topic${query}`);
  },

  async getTopic(category?: string, difficulty?: string) {
    return this.generateTopic(category, difficulty);
  },

  async createSession(
    topic: string,
    category: string,
    difficulty = "Medium",
    instantStart = false,
    preparationMode = false,
    skipPreparation = false
  ) {
    return fetchAPI("/jam/session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        topic,
        category,
        difficulty,
        instant_start: instantStart,
        preparation_mode: preparationMode,
        skip_preparation: skipPreparation
      }),
    });
  },

  async uploadVideo(sessionId: string, videoBlob: Blob, filename = "recording.webm") {
    const formData = new FormData();
    formData.append("file", videoBlob, filename);

    return fetchAPI(`/jam/session/${sessionId}/upload`, {
      method: "POST",
      body: formData,
      timeout: 180000, // 180s
    });
  },

  /**
   * Polls GET /jam/session/{sessionId} every intervalMs until
   * analysis_status is 'completed' or 'failed', or maxWaitMs is exceeded.
   * Throws if timed out or analysis failed.
   */
  async pollUntilComplete(
    sessionId: string,
    onProgress?: (status: string, elapsed: number) => void,
    intervalMs = 3000,
    maxWaitMs = 600000  // 10 minutes
  ): Promise<any> {
    const start = Date.now();
    console.log(`[POLLING_STARTED] session=${sessionId}`);
    let consecutiveErrors = 0;
    while (true) {
      const elapsed = Date.now() - start;
      if (elapsed > maxWaitMs) {
        // Fallback recovery: attempt to load latest completed report
        try {
          console.warn(`[POLLING_TIMEOUT] Polling timed out. Attempting fallback recovery...`);
          const history = await this.getHistory(5);
          const recovered = history.find((s: any) => s.id === sessionId && s.final_score > 0);
          if (recovered) {
            console.info(`[RECOVERY_SUCCESS] Recovered completed session ${sessionId} from history.`);
            const fullSession = await this.getSession(sessionId);
            return fullSession;
          }
          const anyRecovered = history.find((s: any) => s.final_score > 0);
          if (anyRecovered) {
            console.info(`[RECOVERY_SUCCESS] Recovered latest completed session ${anyRecovered.id} from history.`);
            const fullSession = await this.getSession(anyRecovered.id);
            return fullSession;
          }
        } catch (recErr) {
          console.error(`[RECOVERY_FAILED] Failed to recover:`, recErr);
        }
        throw new Error(`Analysis timed out after ${Math.round(maxWaitMs / 1000)}s. Please try again.`);
      }

      let session: any;
      try {
        session = await fetchAPI(`/jam/session/${sessionId}`, { timeout: 15000 });
        consecutiveErrors = 0;
      } catch (err: any) {
        consecutiveErrors++;
        console.warn(`[POLLING] Error fetching session state (consecutive: ${consecutiveErrors}): ${err.message}`);
        if (consecutiveErrors >= 5) {
          try {
            const history = await this.getHistory(5);
            const recovered = history.find((s: any) => s.id === sessionId && s.final_score > 0);
            if (recovered) {
              const fullSession = await this.getSession(sessionId);
              return fullSession;
            }
          } catch (_) {}
          throw err;
        }
        await new Promise(r => setTimeout(r, intervalMs));
        continue;
      }

      const status: string = session.analysis_status ?? "processing";
      console.log(`[POLLING_RESPONSE] status=${status} elapsed=${Math.round(elapsed / 1000)}s progress=${session.progress ?? 0}%`);
      onProgress?.(status, elapsed);
      if (status === "completed") {
        console.log(`[REPORT_RECEIVED] session=${sessionId} score=${session.final_score ?? 0}`);
        return session;
      }
      if (status === "failed") {
        // Attempt report recovery: check if a report was saved despite status=failed
        if (session.reports && session.reports.length > 0 && session.reports[0].summary) {
          console.warn(`[POLLING_RESPONSE] Status=failed but report exists. Using saved report.`);
          session.analysis_status = "completed";
          return session;
        }
        console.error(`[POLLING_RESPONSE] Analysis failed: ${session.message}`);
        throw new Error(session.message || "Analysis failed on the server. Please re-record and try again.");
      }
      await new Promise(r => setTimeout(r, intervalMs));
    }
  },

  /**
   * Polls GET /document/session/{sessionId} every intervalMs until
   * analysis_status is 'completed' or 'failed', or maxWaitMs is exceeded.
   */
  async pollDocSessionUntilComplete(
    sessionId: string,
    onProgress?: (status: string, elapsed: number) => void,
    intervalMs = 3000,
    maxWaitMs = 600000
  ): Promise<any> {
    const start = Date.now();
    let consecutiveErrors = 0;
    while (true) {
      const elapsed = Date.now() - start;
      if (elapsed > maxWaitMs) {
        throw new Error(`Analysis timed out after ${Math.round(maxWaitMs / 1000)}s. Please try again.`);
      }

      let session: any;
      try {
        session = await fetchAPI(`/document/session/${sessionId}`, { timeout: 15000 });
        consecutiveErrors = 0;
      } catch (err: any) {
        consecutiveErrors++;
        console.warn(`[POLLING] Document session polling error (consecutive: ${consecutiveErrors}): ${err.message}`);
        if (consecutiveErrors >= 5) {
          throw err;
        }
        await new Promise(r => setTimeout(r, intervalMs));
        continue;
      }

      const status: string = session.analysis_status ?? "processing";
      onProgress?.(status, elapsed);
      if (status === "completed") return session;
      if (status === "failed") throw new Error("Analysis failed on the server. Please re-record and try again.");
      await new Promise(r => setTimeout(r, intervalMs));
    }
  },

  async getSession(sessionId: string) {
    return fetchAPI(`/jam/session/${sessionId}`);
  },

  async getSessionVideo(sessionId: string): Promise<{ video_url: string }> {
    return fetchAPI(`/interviews/${sessionId}/video-info`);
  },

  async getHistory(limit?: number) {
    const query = limit !== undefined ? `?limit=${limit}` : "";
    return fetchAPI(`/jam/history${query}`);
  },

  async getLeaderboard() {
    return fetchAPI("/jam/leaderboard");
  },

  async getAnalytics() {
    return fetchAPI("/jam/analytics");
  },

  // Debate Arena API
  async startDebate(topic: string, difficulty: string) {
    return fetchAPI(`/debate/start?topic=${encodeURIComponent(topic)}&difficulty=${encodeURIComponent(difficulty)}`, {
      method: "POST"
    });
  },

  async submitDebateArgument(sessionId: string, argument: string) {
    return fetchAPI(`/debate/${sessionId}/argue?user_argument=${encodeURIComponent(argument)}`, {
      method: "POST"
    });
  },

  async uploadDebateVideo(sessionId: string, videoBlob: Blob, filename = "debate.webm") {
    const formData = new FormData();
    formData.append("file", videoBlob, filename);
    return fetchAPI(`/debate/session/${sessionId}/upload`, {
      method: "POST",
      body: formData,
      timeout: 180000,
    });
  },

  // Interview Simulator API
  async startInterview(role: string, roundType: string) {
    return fetchAPI(`/interview/start?role=${encodeURIComponent(role)}&round_type=${encodeURIComponent(roundType)}`, {
      method: "POST"
    });
  },

  async submitInterviewAnswer(sessionId: string, answer: string) {
    return fetchAPI(`/interview/${sessionId}/answer?user_answer=${encodeURIComponent(answer)}`, {
      method: "POST"
    });
  },

  /**
   * Uploads a recorded interview video/audio blob for full evidence-based analysis.
   * Uses the same pipeline as JAM Analyzer (Whisper + MediaPipe + Groq).
   * Returns a full SessionOut with 10-section report.
   */
  async uploadInterviewVideo(sessionId: string, videoBlob: Blob, filename = "interview.webm") {
    const formData = new FormData();
    formData.append("file", videoBlob, filename);
    console.log(`[API] ▶ Uploading interview recording — session: ${sessionId}, size: ${videoBlob.size} bytes`);
    return fetchAPI(`/interview/session/${sessionId}/upload`, {
      method: "POST",
      body: formData,
      timeout: 180000, // 3 minutes — interview analysis may take longer
    });
  },

  // AI Coach API
  async getDNA() {
    return fetchAPI("/coach/dna");
  },

  async getCoachRecommendations() {
    return fetchAPI("/coach/recommendations");
  },

  async pollCoachJob(
    jobId: string,
    onProgress?: (status: string, progress: number, message: string) => void,
    intervalMs = 2000,
    maxWaitMs = 120000
  ): Promise<any> {
    const start = Date.now();
    while (true) {
      const elapsed = Date.now() - start;
      if (elapsed > maxWaitMs) {
        throw new Error(`Coaching analysis timed out after ${Math.round(maxWaitMs / 1000)}s.`);
      }

      let job: any;
      try {
        job = await fetchAPI(`/job-status/${jobId}`);
      } catch (err: any) {
        // If the job no longer exists (404) or backend is down, stop polling immediately.
        // This prevents infinite error loops when the backend restarts and wipes in-memory jobs.
        const msg = err.message || "";
        if (
          msg === "Job not found." ||
          msg.includes("404") ||
          msg.includes("Cannot reach backend")
        ) {
          console.warn(`[Coach] Stopping poll — job ${jobId} is unreachable: ${msg}`);
          throw err;
        }
        // Transient network error — wait and retry
        console.warn(`[Coach] Transient poll error, will retry: ${msg}`);
        await new Promise(r => setTimeout(r, intervalMs));
        continue;
      }

      const status: string = job.status ?? "pending";
      const progress: number = job.progress ?? 0;
      const message: string = job.message ?? "";
      
      onProgress?.(status, progress, message);
      
      if (status === "completed") {
        return job.result;
      }
      if (status === "failed") {
        throw new Error(job.error || "Coaching recommendation generation failed on the server.");
      }
      await new Promise(r => setTimeout(r, intervalMs));
    }
  },

  async getChallenges() {
    return fetchAPI("/coach/challenges");
  },

  async attemptChallenge(challenge_id: string, score: number) {
    return fetchAPI(`/coach/challenge/${challenge_id}/attempt?score=${score}`, {
      method: "POST"
    });
  },

  // Document-Based Communication Analyzer API
  async uploadDocument(file: File) {
    console.log("Document Upload Started");
    const formData = new FormData();
    formData.append("file", file);
    return fetchAPI("/document/upload", {
      method: "POST",
      body: formData,
      timeout: 180000,
    });
  },

  async createDocSession(
    documentId: string,
    topicId: string | null,
    topicTitle: string,
    category: string,
    instantStart = false,
    preparationMode = false,
    skipPreparation = false
  ) {
    return fetchAPI("/document/session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        document_id: documentId,
        topic_id: topicId,
        topic_title: topicTitle,
        category,
        instant_start: instantStart,
        preparation_mode: preparationMode,
        skip_preparation: skipPreparation
      }),
    });
  },

  async uploadDocVideo(sessionId: string, videoBlob: Blob, filename = "doc_recording.webm") {
    const formData = new FormData();
    formData.append("file", videoBlob, filename);
    return fetchAPI(`/document/session/${sessionId}/upload`, {
      method: "POST",
      body: formData,
      timeout: 180000,
    });
  },

  async getDocSession(sessionId: string) {
    return fetchAPI(`/document/session/${sessionId}`);
  },

  async startViva(documentId: string, mode: string) {
    return fetchAPI("/document/viva/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ document_id: documentId, mode }),
    });
  },

  async submitVivaAnswer(vivaId: string, questionIndex: number, videoBlob: Blob, filename = "viva_recording.webm") {
    const formData = new FormData();
    formData.append("file", videoBlob, filename);
    return fetchAPI(`/document/viva/${vivaId}/answer?question_index=${questionIndex}`, {
      method: "POST",
      body: formData,
      timeout: 180000,
    });
  },

  async getVivaSession(vivaId: string) {
    return fetchAPI(`/document/viva/${vivaId}`);
  }
};
