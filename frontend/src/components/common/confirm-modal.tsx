import { useEffect, useState } from "react";
import { AlertTriangle, AlertCircle, Loader2, X } from "lucide-react";

interface ConfirmModalProps {
  isOpen: boolean;
  title: string;
  description: string;
  confirmText?: string;
  cancelText?: string;
  isDestructive?: boolean;
  isLoading?: boolean;
  errorMessage?: string | null;
  onConfirm: () => void | Promise<void>;
  onClose: () => void;
}

export function ConfirmModal({
  isOpen,
  title,
  description,
  confirmText = "ยืนยัน",
  cancelText = "ยกเลิก",
  isDestructive = false,
  isLoading = false,
  errorMessage = null,
  onConfirm,
  onClose,
}: ConfirmModalProps) {
  const [internalError, setInternalError] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen) {
      setInternalError(null);
    }
  }, [isOpen]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (!isOpen || isLoading) return;
      if (e.key === "Escape") {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, isLoading, onClose]);

  if (!isOpen) return null;

  const displayError = errorMessage || internalError;

  const handleConfirmClick = async () => {
    try {
      setInternalError(null);
      await onConfirm();
    } catch (err: any) {
      setInternalError(err.message || "เกิดข้อผิดพลาดในการทำรายการ");
    }
  };

  return (
    <div
      id="confirm-modal-backdrop"
      className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-background/80 backdrop-blur-md animate-in fade-in duration-200"
      onClick={(e) => {
        if (e.target === e.currentTarget && !isLoading) {
          onClose();
        }
      }}
    >
      <div
        id="confirm-modal-dialog"
        className="relative w-full max-w-md rounded-2xl bg-card border border-border/80 shadow-2xl p-6 space-y-4 glass-panel animate-in zoom-in-95 duration-200"
      >
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-3">
            <div
              className={`w-10 h-10 rounded-xl flex items-center justify-center shrink-0 border ${
                isDestructive
                  ? "bg-destructive/15 text-destructive border-destructive/30"
                  : "bg-amber-500/15 text-amber-400 border-amber-500/30"
              }`}
            >
              {isDestructive ? (
                <AlertCircle className="w-5 h-5" />
              ) : (
                <AlertTriangle className="w-5 h-5" />
              )}
            </div>
            <div>
              <h3 className="text-base font-bold text-foreground">{title}</h3>
              <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed">
                {description}
              </p>
            </div>
          </div>

          <button
            id="btn-confirm-modal-close"
            onClick={onClose}
            disabled={isLoading}
            className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-secondary transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {displayError && (
          <div className="p-3 rounded-xl bg-destructive/10 border border-destructive/30 text-destructive text-xs flex items-center gap-2">
            <AlertCircle className="w-4 h-4 shrink-0" />
            <span>{displayError}</span>
          </div>
        )}

        <div className="flex justify-end gap-2.5 pt-3 border-t border-border/60">
          <button
            id="btn-confirm-modal-cancel"
            type="button"
            onClick={onClose}
            disabled={isLoading}
            className="px-4 py-2 rounded-xl border border-border text-xs font-semibold text-muted-foreground hover:text-foreground hover:bg-secondary transition-all"
          >
            {cancelText}
          </button>

          <button
            id="btn-confirm-modal-confirm"
            type="button"
            onClick={handleConfirmClick}
            disabled={isLoading}
            className={`flex items-center gap-1.5 px-5 py-2 rounded-xl text-xs font-semibold shadow-lg transition-all cursor-pointer disabled:opacity-50 ${
              isDestructive
                ? "bg-destructive text-white hover:brightness-110 shadow-destructive/20"
                : "bg-primary text-white hover:brightness-110 shadow-primary/20"
            }`}
          >
            {isLoading ? (
              <>
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                กำลังดำเนินการ...
              </>
            ) : (
              confirmText
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
