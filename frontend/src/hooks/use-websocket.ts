/** WebSocket hook for real-time job progress updates. */
import { useEffect, useRef, useCallback } from "react";
import { queryClient } from "@/api/client";

export interface WSEvent {
  type: "job_update" | "chapter_changed" | "job_complete";
  data: Record<string, unknown>;
}

export function useWebSocket() {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<number | undefined>(undefined);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const ws = new WebSocket(`${protocol}//${window.location.host}/ws/progress`);

    ws.onopen = () => {
      console.log("[WS] Connected");
    };

    ws.onmessage = (ev) => {
      try {
        const msg: WSEvent = JSON.parse(ev.data);
        if (msg.type === "job_update") {
          // Invalidate jobs query to trigger re-render
          queryClient.invalidateQueries({ queryKey: ["jobs"] });

          // Show browser notification on job completion
          const status = msg.data.status as string;
          if (status === "done" || status === "error") {
            const title = (msg.data.title as string) || "Manga Translate";
            const message = (msg.data.message as string) || (status === "done" ? "เสร็จแล้ว!" : "เกิดข้อผิดพลาด");
            if (Notification.permission === "granted") {
              new Notification(title, {
                body: message,
                icon: status === "done" ? "✅" : "❌",
              });
            }
          }
        }
        if (msg.type === "chapter_changed") {
          queryClient.invalidateQueries({ queryKey: ["chapters"] });
        }
      } catch {
        // ignore parse errors
      }
    };

    ws.onclose = () => {
      console.log("[WS] Disconnected — reconnecting in 3s");
      reconnectTimer.current = setTimeout(connect, 3000);
    };

    ws.onerror = () => {
      ws.close();
    };

    wsRef.current = ws;
  }, []);

  useEffect(() => {
    // Request notification permission
    if ("Notification" in window && Notification.permission === "default") {
      Notification.requestPermission();
    }
    connect();
    return () => {
      clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
    };
  }, [connect]);
}
