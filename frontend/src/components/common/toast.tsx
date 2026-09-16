/** Global Toast notification component. */
import { useUIStore } from "@/stores/ui-store";
import { CheckCircle2, AlertCircle, Sparkles, X } from "lucide-react";

export function ToastContainer() {
  const { toast, hideToast } = useUIStore();

  if (!toast) return null;

  return (
    <div className="fixed bottom-6 right-6 z-50 max-w-sm w-full animate-in fade-in slide-in-from-bottom-4 duration-200">
      <div
        className={`p-4 rounded-2xl border shadow-2xl backdrop-blur-2xl flex items-start gap-3 ${
          toast.type === "error"
            ? "bg-destructive/15 border-destructive/30 text-destructive-foreground"
            : toast.type === "success"
            ? "bg-emerald-950/80 border-emerald-500/30 text-emerald-100"
            : "bg-card/95 border-border text-foreground"
        }`}
      >
        <div className="shrink-0 mt-0.5">
          {toast.type === "error" && <AlertCircle className="w-4 h-4 text-red-400" />}
          {toast.type === "success" && <CheckCircle2 className="w-4 h-4 text-emerald-400" />}
          {(!toast.type || toast.type === "info") && (
            <Sparkles className="w-4 h-4 text-fuchsia-400" />
          )}
        </div>

        <div className="flex-1 text-xs font-medium leading-relaxed select-text">
          {toast.message}
        </div>

        <button
          onClick={hideToast}
          className="shrink-0 p-1 rounded-lg text-muted-foreground hover:text-foreground hover:bg-secondary/50 transition-colors"
          title="ปิดการแจ้งเตือน"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  );
}
