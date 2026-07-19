import { useEffect, useRef, useState } from "react";
import api from "@/lib/api";
import { X, Broom, ArrowsClockwise } from "@phosphor-icons/react";

export default function LogsModal({ bot, onClose }) {
  const [logs, setLogs] = useState("");
  const [autoScroll, setAutoScroll] = useState(true);
  const [loading, setLoading] = useState(true);
  const termRef = useRef(null);
  const intervalRef = useRef(null);

  const fetchLogs = async () => {
    try {
      const { data } = await api.get(`/bots/${bot.id}/logs?lines=500`);
      setLogs(data.logs || "");
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchLogs();
    intervalRef.current = setInterval(fetchLogs, 2000);
    return () => clearInterval(intervalRef.current);
    // eslint-disable-next-line
  }, [bot.id]);

  useEffect(() => {
    if (autoScroll && termRef.current) {
      termRef.current.scrollTop = termRef.current.scrollHeight;
    }
  }, [logs, autoScroll]);

  const clearLogs = async () => {
    await api.post(`/bots/${bot.id}/logs/clear`);
    setLogs("");
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal modal-wide"
        onClick={(e) => e.stopPropagation()}
        data-testid="logs-modal"
      >
        <div className="flex items-center justify-between p-5 divider-strong">
          <div>
            <div className="label-mini">// canlı çıktı</div>
            <h3 className="font-display text-2xl font-black mt-1">
              {bot.name}
            </h3>
            <div className="font-mono text-xs text-zinc-500 mt-1">
              {bot.entry_file}
            </div>
          </div>
          <button
            data-testid="logs-modal-close"
            onClick={onClose}
            className="btn btn-ghost btn-icon"
          >
            <X size={18} weight="bold" />
          </button>
        </div>

        <div className="px-5 py-3 divider-strong flex items-center gap-3 flex-wrap">
          <button
            data-testid="logs-refresh"
            onClick={fetchLogs}
            className="btn btn-secondary btn-sm"
          >
            <ArrowsClockwise size={14} weight="bold" /> Yenile
          </button>
          <button
            data-testid="logs-clear"
            onClick={clearLogs}
            className="btn btn-danger btn-sm"
          >
            <Broom size={14} weight="bold" /> Temizle
          </button>
          <label className="ml-auto flex items-center gap-2 text-xs font-bold uppercase tracking-widest cursor-pointer">
            <span>Otomatik kaydır</span>
            <span
              data-testid="logs-autoscroll-toggle"
              onClick={() => setAutoScroll(!autoScroll)}
              className={`toggle ${autoScroll ? "on" : ""}`}
            />
          </label>
        </div>

        <div className="p-5">
          <div
            data-testid="log-terminal-output"
            ref={termRef}
            className="terminal"
          >
            {loading
              ? "$ logs yükleniyor..."
              : logs || "$ henüz log yok. Botu başlattığında çıktılar burada görünecek."}
            <span className="cursor-blink">▌</span>
          </div>
        </div>
      </div>
    </div>
  );
}
