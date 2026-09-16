import { useState, useRef, useEffect, useCallback } from "react";
import {
  X,
  Paintbrush,
  Pipette,
  Type,
  RotateCcw,
  Sparkles,
  Save,
  Check,
  ZoomIn,
  ZoomOut,
  Loader2,
} from "lucide-react";
import { touchupPage, recleanPage } from "@/api/client";

interface TouchupModalProps {
  isOpen: boolean;
  onClose: () => void;
  chapterSlug: string;
  pageNumber: number;
  imageUrl: string;
  onSaved: () => void;
}

type ActiveTool = "brush" | "picker" | "text";

export default function TouchupModal({
  isOpen,
  onClose,
  chapterSlug,
  pageNumber,
  imageUrl,
  onSaved,
}: TouchupModalProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);

  const [tool, setTool] = useState<ActiveTool>("brush");
  const [brushSize, setBrushSize] = useState(20);
  const [brushColor, setBrushColor] = useState("#FFFFFF");
  const [isDrawing, setIsDrawing] = useState(false);
  const [history, setHistory] = useState<ImageData[]>([]);
  const [isSaving, setIsSaving] = useState(false);
  const [isReCleaning, setIsReCleaning] = useState(false);
  const [textInput, setTextInput] = useState("");
  const [textSize, setTextSize] = useState(24);
  const [scale, setScale] = useState(1);
  const [statusMsg, setStatusMsg] = useState("");

  // Load image onto canvas
  useEffect(() => {
    if (!isOpen) return;

    const img = new Image();
    img.crossOrigin = "anonymous";
    img.src = `${imageUrl}?t=${Date.now()}`;
    img.onload = () => {
      const canvas = canvasRef.current;
      if (!canvas) return;
      canvas.width = img.naturalWidth;
      canvas.height = img.naturalHeight;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      ctx.drawImage(img, 0, 0);

      // Save initial state for undo
      const initial = ctx.getImageData(0, 0, canvas.width, canvas.height);
      setHistory([initial]);
    };
  }, [isOpen, imageUrl]);

  // Push current state to undo history
  const pushHistory = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const state = ctx.getImageData(0, 0, canvas.width, canvas.height);
    setHistory((prev) => [...prev.slice(-15), state]);
  }, []);

  const handleUndo = useCallback(() => {
    if (history.length <= 1) return;
    const newHistory = [...history];
    newHistory.pop(); // Remove current
    const previous = newHistory[newHistory.length - 1];
    setHistory(newHistory);

    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx || !previous) return;
    ctx.putImageData(previous, 0, 0);
  }, [history]);

  // Coordinate mapping from mouse event to natural canvas pixels
  const getCanvasCoords = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    if (!canvas) return { x: 0, y: 0 };
    const rect = canvas.getBoundingClientRect();
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;
    return {
      x: (e.clientX - rect.left) * scaleX,
      y: (e.clientY - rect.top) * scaleY,
    };
  };

  const handleMouseDown = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const { x, y } = getCanvasCoords(e);
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    if (tool === "picker") {
      const pixel = ctx.getImageData(x, y, 1, 1).data;
      const hex = `#${((1 << 24) + (pixel[0] << 16) + (pixel[1] << 8) + pixel[2])
        .toString(16)
        .slice(1)
        .toUpperCase()}`;
      setBrushColor(hex);
      setTool("brush");
      setStatusMsg(`เลือกสี: ${hex}`);
      setTimeout(() => setStatusMsg(""), 2000);
      return;
    }

    if (tool === "text") {
      if (!textInput.trim()) {
        setStatusMsg("กรุณาพิมพ์ข้อความก่อนคลิกวางบนภาพ");
        setTimeout(() => setStatusMsg(""), 2500);
        return;
      }
      ctx.save();
      ctx.font = `600 ${textSize}px 'Sarabun', 'Prompt', sans-serif`;
      ctx.fillStyle = "#000000";
      ctx.strokeStyle = "#FFFFFF";
      ctx.lineWidth = 4;
      ctx.lineJoin = "round";
      ctx.strokeText(textInput, x, y);
      ctx.fillText(textInput, x, y);
      ctx.restore();
      pushHistory();
      return;
    }

    if (tool === "brush") {
      setIsDrawing(true);
      ctx.beginPath();
      ctx.moveTo(x, y);
      ctx.lineCap = "round";
      ctx.lineJoin = "round";
      ctx.strokeStyle = brushColor;
      ctx.lineWidth = brushSize;
      ctx.lineTo(x, y);
      ctx.stroke();
    }
  };

  const handleMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!isDrawing || tool !== "brush") return;
    const { x, y } = getCanvasCoords(e);
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    ctx.lineTo(x, y);
    ctx.stroke();
  };

  const handleMouseUp = () => {
    if (isDrawing) {
      setIsDrawing(false);
      pushHistory();
    }
  };

  // Automated Re-Clean via Backend OpenCV
  const handleAutoClean = async () => {
    setIsReCleaning(true);
    setStatusMsg("กำลังประมวลผล Inpainting ลบคราบอัตโนมัติ...");
    try {
      await recleanPage(chapterSlug, pageNumber);
      // Reload updated image on canvas
      const img = new Image();
      img.crossOrigin = "anonymous";
      img.src = `${imageUrl}?t=${Date.now()}`;
      img.onload = () => {
        const canvas = canvasRef.current;
        if (!canvas) return;
        const ctx = canvas.getContext("2d");
        if (!ctx) return;
        ctx.drawImage(img, 0, 0);
        pushHistory();
        setStatusMsg("ลบคราบและ Inpainting เรียบร้อย!");
        setTimeout(() => setStatusMsg(""), 3000);
      };
    } catch (err: any) {
      setStatusMsg(`เกิดข้อผิดพลาด: ${err.message || err}`);
    } finally {
      setIsReCleaning(false);
    }
  };

  // Save changes to backend
  const handleSave = async () => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    setIsSaving(true);
    setStatusMsg("กำลังบันทึกภาพ...");
    try {
      const dataUrl = canvas.toDataURL("image/png");
      await touchupPage(chapterSlug, pageNumber, dataUrl);
      setStatusMsg("บันทึกสำเร็จ!");
      setTimeout(() => {
        onSaved();
        onClose();
      }, 500);
    } catch (err: any) {
      setStatusMsg(`บันทึกไม่สำเร็จ: ${err.message || err}`);
    } finally {
      setIsSaving(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-md p-4 animate-in fade-in duration-200">
      <div className="relative flex flex-col w-full max-w-6xl h-[90vh] bg-neutral-900/95 border border-neutral-700/60 rounded-2xl shadow-2xl overflow-hidden">
        {/* Header Toolbar */}
        <div className="flex items-center justify-between px-5 py-3 border-b border-neutral-800 bg-neutral-950/60">
          <div className="flex items-center gap-3">
            <h3 className="text-base font-semibold text-neutral-100 flex items-center gap-2">
              <Paintbrush className="w-4 h-4 text-emerald-400" />
              Touch-up Studio — หน้า {pageNumber}
            </h3>
            {statusMsg && (
              <span className="text-xs px-2.5 py-1 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 animate-pulse">
                {statusMsg}
              </span>
            )}
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={handleAutoClean}
              disabled={isReCleaning}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-indigo-600/20 text-indigo-300 border border-indigo-500/30 rounded-lg hover:bg-indigo-600/30 transition-all disabled:opacity-50 cursor-pointer"
              title="สั่ง OpenCV Inpaint ลบคราบและกล่องขาวอัตโนมัติ"
            >
              {isReCleaning ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Sparkles className="w-3.5 h-3.5 text-indigo-400" />
              )}
              Auto Re-Clean
            </button>

            <button
              onClick={handleUndo}
              disabled={history.length <= 1}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-neutral-800 text-neutral-300 border border-neutral-700 rounded-lg hover:bg-neutral-700 transition-all disabled:opacity-40 cursor-pointer"
              title="ย้อนกลับ (Undo)"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              Undo
            </button>

            <button
              onClick={handleSave}
              disabled={isSaving}
              className="flex items-center gap-1.5 px-4 py-1.5 text-xs font-semibold bg-emerald-600 text-white rounded-lg hover:bg-emerald-500 transition-all shadow-lg shadow-emerald-900/30 disabled:opacity-50 cursor-pointer"
            >
              {isSaving ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Save className="w-3.5 h-3.5" />
              )}
              บันทึกภาพ
            </button>

            <button
              onClick={onClose}
              className="p-1.5 text-neutral-400 hover:text-neutral-100 rounded-lg hover:bg-neutral-800 transition-colors cursor-pointer"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Workspace Body */}
        <div className="flex flex-1 overflow-hidden">
          {/* Left Toolbox */}
          <div className="w-64 p-4 border-r border-neutral-800 bg-neutral-950/40 flex flex-col gap-5 text-neutral-300 text-xs">
            {/* Tool Selection */}
            <div>
              <label className="block text-[11px] font-medium text-neutral-400 uppercase tracking-wider mb-2">
                เครื่องมือ (Tools)
              </label>
              <div className="grid grid-cols-3 gap-2">
                <button
                  onClick={() => setTool("brush")}
                  className={`flex flex-col items-center gap-1.5 p-2.5 rounded-xl border transition-all cursor-pointer ${
                    tool === "brush"
                      ? "bg-emerald-500/15 border-emerald-500/50 text-emerald-300 shadow-sm"
                      : "bg-neutral-800/60 border-neutral-700/50 text-neutral-400 hover:bg-neutral-800"
                  }`}
                >
                  <Paintbrush className="w-4 h-4" />
                  <span>แปรงลบ</span>
                </button>

                <button
                  onClick={() => setTool("picker")}
                  className={`flex flex-col items-center gap-1.5 p-2.5 rounded-xl border transition-all cursor-pointer ${
                    tool === "picker"
                      ? "bg-emerald-500/15 border-emerald-500/50 text-emerald-300 shadow-sm"
                      : "bg-neutral-800/60 border-neutral-700/50 text-neutral-400 hover:bg-neutral-800"
                  }`}
                >
                  <Pipette className="w-4 h-4" />
                  <span>ดูดสี</span>
                </button>

                <button
                  onClick={() => setTool("text")}
                  className={`flex flex-col items-center gap-1.5 p-2.5 rounded-xl border transition-all cursor-pointer ${
                    tool === "text"
                      ? "bg-emerald-500/15 border-emerald-500/50 text-emerald-300 shadow-sm"
                      : "bg-neutral-800/60 border-neutral-700/50 text-neutral-400 hover:bg-neutral-800"
                  }`}
                >
                  <Type className="w-4 h-4" />
                  <span>ข้อความ</span>
                </button>
              </div>
            </div>

            {/* Brush Controls */}
            {tool === "brush" && (
              <div className="flex flex-col gap-4 p-3 bg-neutral-900/60 border border-neutral-800/80 rounded-xl">
                <div>
                  <div className="flex justify-between mb-1.5">
                    <span className="text-neutral-400">ขนาดแปรง (Brush Size)</span>
                    <span className="font-mono text-neutral-200">{brushSize}px</span>
                  </div>
                  <input
                    type="range"
                    min="4"
                    max="80"
                    value={brushSize}
                    onChange={(e) => setBrushSize(Number(e.target.value))}
                    className="w-full accent-emerald-500 cursor-pointer"
                  />
                </div>

                <div>
                  <span className="block text-neutral-400 mb-1.5">สีแปรง (Brush Color)</span>
                  <div className="flex items-center gap-2">
                    <input
                      type="color"
                      value={brushColor}
                      onChange={(e) => setBrushColor(e.target.value)}
                      className="w-8 h-8 rounded-lg cursor-pointer border border-neutral-700 bg-transparent"
                    />
                    <div className="flex gap-1">
                      {["#FFFFFF", "#F7F5EE", "#EAE6DF", "#000000"].map((c) => (
                        <button
                          key={c}
                          onClick={() => setBrushColor(c)}
                          style={{ backgroundColor: c }}
                          className="w-6 h-6 rounded-md border border-neutral-600 hover:scale-110 transition-transform cursor-pointer"
                          title={c}
                        />
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Text Tool Controls */}
            {tool === "text" && (
              <div className="flex flex-col gap-3 p-3 bg-neutral-900/60 border border-neutral-800/80 rounded-xl">
                <div>
                  <label className="block text-neutral-400 mb-1">ข้อความภาษาไทย</label>
                  <textarea
                    value={textInput}
                    onChange={(e) => setTextInput(e.target.value)}
                    placeholder="พิมพ์ข้อความ..."
                    rows={3}
                    className="w-full p-2 bg-neutral-950 border border-neutral-700 rounded-lg text-neutral-100 text-xs focus:border-emerald-500 focus:outline-none resize-none"
                  />
                </div>
                <div>
                  <div className="flex justify-between mb-1">
                    <span className="text-neutral-400">ขนาดตัวอักษร</span>
                    <span className="font-mono text-neutral-200">{textSize}px</span>
                  </div>
                  <input
                    type="range"
                    min="14"
                    max="60"
                    value={textSize}
                    onChange={(e) => setTextSize(Number(e.target.value))}
                    className="w-full accent-emerald-500 cursor-pointer"
                  />
                </div>
                <p className="text-[11px] text-neutral-400 italic">
                  💡 พิมพ์ข้อความแล้วคลิกบนภาพตำแหน่งที่ต้องการวาง
                </p>
              </div>
            )}

            {/* Zoom Controls */}
            <div className="mt-auto flex items-center justify-between p-2.5 bg-neutral-900/40 rounded-xl border border-neutral-800">
              <span className="text-neutral-400">มุมมอง ({Math.round(scale * 100)}%)</span>
              <div className="flex items-center gap-1">
                <button
                  onClick={() => setScale((s) => Math.max(0.4, s - 0.15))}
                  className="p-1 hover:bg-neutral-800 rounded text-neutral-300 cursor-pointer"
                  title="ย่อ"
                >
                  <ZoomOut className="w-3.5 h-3.5" />
                </button>
                <button
                  onClick={() => setScale(1)}
                  className="px-1.5 py-0.5 text-[10px] hover:bg-neutral-800 rounded text-neutral-400 cursor-pointer"
                  title="พอดี"
                >
                  100%
                </button>
                <button
                  onClick={() => setScale((s) => Math.min(2.5, s + 0.15))}
                  className="p-1 hover:bg-neutral-800 rounded text-neutral-300 cursor-pointer"
                  title="ขยาย"
                >
                  <ZoomIn className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          </div>

          {/* Canvas Viewport */}
          <div
            ref={containerRef}
            className="flex-1 overflow-auto bg-neutral-950 p-6 flex items-center justify-center cursor-crosshair select-none"
          >
            <div
              style={{
                transform: `scale(${scale})`,
                transformOrigin: "center center",
                transition: "transform 0.1s ease-out",
              }}
              className="shadow-2xl rounded-sm border border-neutral-800 overflow-hidden"
            >
              <canvas
                ref={canvasRef}
                onMouseDown={handleMouseDown}
                onMouseMove={handleMouseMove}
                onMouseUp={handleMouseUp}
                onMouseLeave={handleMouseUp}
                className="max-w-none block"
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
