import { useCallback, useEffect, useMemo, useState } from "react";


export interface SessionSnapshot {
  questionText: string;
  sourceKind: string;
  lessonJson: string;
  status: string;
  errorMessage: string;
  revision: number;
  lastStudentMessage: string;
  generation: number;
}

export interface ChatMessage {
  id: string;
  role: string;
  text: string;
  lessonJson: string;
  sourceKind: string;
  generation: number;
  status: string;
}

export interface SessionView {
  snapshot: SessionSnapshot;
  messages: ChatMessage[];
}

export interface VoiceToken {
  ok: boolean;
  accessToken: string;
  expiresIn: number;
  ttsModel: string;
  message: string;
}

const API_URL = ((import.meta.env.VITE_API_URL as string | undefined) || "").replace(/\/$/, "");

async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    credentials: "include",
    ...init,
    headers: {
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...init?.headers,
    },
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => undefined) as { detail?: unknown } | undefined;
    const detail = typeof payload?.detail === "string"
      ? payload.detail
      : response.status === 422
        ? "The submitted lesson data was not valid."
        : `The tutor API returned ${response.status}.`;
    throw new Error(detail);
  }
  return response.json() as Promise<T>;
}

export function useTutorSession() {
  const [view, setView] = useState<SessionView>();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    try {
      const next = await apiRequest<SessionView>("/api/session");
      setView(next);
      setError("");
      return next;
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : String(loadError));
      throw loadError;
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh().catch(() => undefined);
  }, [refresh]);

  const mutate = useCallback(async (path: string, body?: object, method = "POST") => {
    const next = await apiRequest<SessionView>(path, {
      method,
      body: body ? JSON.stringify(body) : undefined,
    });
    setView(next);
    setError("");
    return next;
  }, []);

  return useMemo(() => ({
    snapshot: view?.snapshot,
    messages: view?.messages ?? [],
    loading,
    error,
    refresh,
    startLesson: (body: object) => mutate("/api/lesson", body),
    replan: (body: object) => mutate("/api/replan", body),
    checkWork: (body: object) => mutate("/api/check-work", body),
    reset: () => mutate("/api/session/reset"),
    voiceToken: () => apiRequest<VoiceToken>("/api/voice-token", { method: "POST" }),
    forget: async () => {
      const response = await apiRequest<{ messagesErased: number }>("/api/session", { method: "DELETE" });
      await refresh();
      return response.messagesErased;
    },
  }), [error, loading, mutate, refresh, view]);
}
