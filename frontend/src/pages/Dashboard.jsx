import { useEffect, useState, useRef } from "react";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import AddBotModal from "@/components/AddBotModal";
import LogsModal from "@/components/LogsModal";
import BotSettingsModal from "@/components/BotSettingsModal";
import {
  Plus,
  Play,
  Stop,
  ArrowsClockwise,
  TerminalWindow,
  GearSix,
  Trash,
  Terminal,
  SignOut,
  Cpu,
  Memory,
  Robot,
} from "@phosphor-icons/react";

function fmtUptime(s) {
  if (!s || s <= 0) return "—";
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  if (h) return `${h}h ${m}m`;
  if (m) return `${m}m ${sec}s`;
  return `${sec}s`;
}

export default function Dashboard() {
  const { user, logout } = useAuth();
  const [bots, setBots] = useState([]);
  const [statsMap, setStatsMap] = useState({});
  const [sys, setSys] = useState(null);
  const [showAdd, setShowAdd] = useState(false);
  const [logBot, setLogBot] = useState(null);
  const [settingsBot, setSettingsBot] = useState(null);
  const [confirmDel, setConfirmDel] = useState(null);
  const pollRef = useRef(null);

  const load = async () => {
    try {
      const [b, s] = await Promise.all([api.get("/bots"), api.get("/system/stats")]);
      setBots(b.data);
      setSys(s.data);
      // Update stats per bot
      const stats = {};
      await Promise.all(
        b.data.map(async (bot) => {
          try {
            const r = await api.get(`/bots/${bot.id}/stats`);
            stats[bot.id] = r.data;
          } catch {
            stats[bot.id] = { status: "stopped", cpu: 0, ram_mb: 0, uptime: 0 };
          }
        })
      );
      setStatsMap(stats);
    } catch (e) {
      // unauth handled by interceptor
    }
  };

  useEffect(() => {
    load();
    pollRef.current = setInterval(load, 3000);
    return () => clearInterval(pollRef.current);
  }, []);

  const action = async (botId, act) => {
    await api.post(`/bots/${botId}/${act}`);
    await load();
  };

  const onDelete = async (botId) => {
    await api.delete(`/bots/${botId}`);
    setConfirmDel(null);
    await load();
  };

  return (
    <div className="min-h-screen" style={{ background: "var(--surface)" }}>
      {/* HEADER */}
      <header
        className="bg-white px-6 md:px-10 py-5 flex items-center justify-between"
        style={{ borderBottom: "1px solid var(--border)" }}
      >
        <div className="flex items-center gap-3">
          <Terminal size={24} weight="bold" />
          <span className="font-display text-2xl font-black tracking-tighter">
            BOT.<span style={{ color: "#10b981" }}>CTL</span>
          </span>
          <span className="hidden md:inline label-mini ml-3">
            // ubuntu telegram bot manager
          </span>
        </div>
        <div className="flex items-center gap-3">
          <div className="hidden md:flex flex-col items-end">
            <span className="label-mini">admin</span>
            <span className="font-mono text-sm">{user?.username || "—"}</span>
          </div>
          <button
            data-testid="logout-button"
            onClick={logout}
            className="btn btn-secondary btn-sm"
          >
            <SignOut size={14} weight="bold" /> Çıkış
          </button>
        </div>
      </header>

      <main className="px-6 md:px-10 py-8 max-w-[1400px] mx-auto">
        {/* PAGE TITLE */}
        <div className="flex items-end justify-between mb-8 gap-4 flex-wrap">
          <div>
            <div className="label-mini">// kontrol paneli</div>
            <h1 className="font-display text-4xl sm:text-5xl font-black tracking-tighter mt-1">
              Botlar.
            </h1>
            <p className="text-sm text-zinc-500 mt-2">
              Sunucundaki Python Telegram botlarını başlat, durdur ve zamanla.
            </p>
          </div>
          <button
            data-testid="add-bot-button"
            onClick={() => setShowAdd(true)}
            className="btn btn-primary"
          >
            <Plus size={16} weight="bold" /> Bot Ekle
          </button>
        </div>

        {/* METRICS */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-10">
          <MetricCard
            label="Aktif Bot"
            value={sys ? `${sys.running_bots} / ${sys.total_bots}` : "—"}
            icon={<Robot size={20} weight="duotone" />}
            testid="metric-active-bots"
          />
          <MetricCard
            label="Bot CPU Toplam"
            value={sys ? `${sys.total_cpu_percent}%` : "—"}
            icon={<Cpu size={20} weight="duotone" />}
            testid="metric-cpu"
          />
          <MetricCard
            label="Bot RAM Toplam"
            value={sys ? `${sys.total_ram_mb} MB` : "—"}
            icon={<Memory size={20} weight="duotone" />}
            testid="metric-ram"
          />
          <MetricCard
            label="Sistem CPU / RAM"
            value={sys ? `${sys.system_cpu_percent}% / ${sys.system_ram_percent}%` : "—"}
            icon={<Cpu size={20} weight="duotone" />}
            testid="metric-system"
          />
        </div>

        {/* BOT LIST */}
        <div className="bg-white" style={{ border: "1px solid var(--border)" }}>
          <div
            className="px-5 py-4 flex items-center justify-between"
            style={{ borderBottom: "1px solid var(--border)" }}
          >
            <div className="label-mini">// process listesi</div>
            <div className="font-mono text-xs text-zinc-500">
              {bots.length} bot kayıtlı
            </div>
          </div>

          {bots.length === 0 && (
            <div className="p-14 text-center" data-testid="empty-state">
              <Robot
                size={42}
                weight="duotone"
                style={{ margin: "0 auto", color: "#a1a1aa" }}
              />
              <div className="font-display text-2xl font-black mt-4">
                Henüz bot yok
              </div>
              <p className="text-sm text-zinc-500 mt-2 max-w-sm mx-auto">
                İlk Telegram botunu yüklemek için sağ üstteki "Bot Ekle"
                düğmesine bas. .py dosyanı seç, isim ver, başla.
              </p>
            </div>
          )}

          {bots.map((bot) => {
            const s = statsMap[bot.id] || { status: "stopped", cpu: 0, ram_mb: 0, uptime: 0 };
            const running = s.status === "running";
            return (
              <div
                key={bot.id}
                data-testid={`bot-row-${bot.id}`}
                className="px-5 py-5 grid grid-cols-1 md:grid-cols-12 gap-4 items-center"
                style={{ borderBottom: "1px solid var(--border-light)" }}
              >
                {/* NAME + STATUS */}
                <div className="md:col-span-4">
                  <div className="flex items-center">
                    <span
                      className={`status-square ${running ? "status-running" : "status-stopped"}`}
                    />
                    <span
                      className="font-mono text-xs uppercase font-bold tracking-widest"
                      style={{ color: running ? "var(--running)" : "var(--stopped)" }}
                      data-testid={`bot-status-${bot.id}`}
                    >
                      {running ? "running" : "stopped"}
                    </span>
                    {bot.auto_restart && (
                      <span
                        className="ml-3 label-mini"
                        style={{ color: "var(--primary)" }}
                        title="Auto-restart enabled"
                      >
                        ↺ auto
                      </span>
                    )}
                    {(bot.start_cron || bot.stop_cron) && (
                      <span className="ml-3 label-mini" title="Scheduled">
                        ⏱ cron
                      </span>
                    )}
                  </div>
                  <div className="font-display text-xl font-black tracking-tight mt-1">
                    {bot.name}
                  </div>
                  <div className="font-mono text-xs text-zinc-500 truncate">
                    {bot.entry_file}
                  </div>
                </div>

                {/* METRICS */}
                <div className="md:col-span-4 grid grid-cols-3 gap-3 text-center md:text-left">
                  <div>
                    <div className="label-mini">cpu</div>
                    <div className="font-mono font-semibold mt-1">
                      {s.cpu}%
                    </div>
                  </div>
                  <div>
                    <div className="label-mini">ram</div>
                    <div className="font-mono font-semibold mt-1">
                      {s.ram_mb} MB
                    </div>
                  </div>
                  <div>
                    <div className="label-mini">uptime</div>
                    <div className="font-mono font-semibold mt-1">
                      {fmtUptime(s.uptime)}
                    </div>
                  </div>
                </div>

                {/* ACTIONS */}
                <div className="md:col-span-4 flex flex-wrap items-center justify-start md:justify-end gap-2">
                  {!running ? (
                    <button
                      data-testid={`start-bot-button-${bot.id}`}
                      onClick={() => action(bot.id, "start")}
                      className="btn btn-success btn-sm"
                    >
                      <Play size={14} weight="fill" /> Başlat
                    </button>
                  ) : (
                    <button
                      data-testid={`stop-bot-button-${bot.id}`}
                      onClick={() => action(bot.id, "stop")}
                      className="btn btn-danger btn-sm"
                    >
                      <Stop size={14} weight="fill" /> Durdur
                    </button>
                  )}
                  <button
                    data-testid={`restart-bot-button-${bot.id}`}
                    onClick={() => action(bot.id, "restart")}
                    className="btn btn-secondary btn-sm"
                    title="Yeniden başlat"
                  >
                    <ArrowsClockwise size={14} weight="bold" />
                  </button>
                  <button
                    data-testid={`view-logs-button-${bot.id}`}
                    onClick={() => setLogBot(bot)}
                    className="btn btn-secondary btn-sm"
                    title="Loglar"
                  >
                    <TerminalWindow size={14} weight="bold" />
                  </button>
                  <button
                    data-testid={`settings-bot-button-${bot.id}`}
                    onClick={() => setSettingsBot(bot)}
                    className="btn btn-secondary btn-sm"
                    title="Ayarlar"
                  >
                    <GearSix size={14} weight="bold" />
                  </button>
                  <button
                    data-testid={`delete-bot-button-${bot.id}`}
                    onClick={() => setConfirmDel(bot)}
                    className="btn btn-secondary btn-sm"
                    title="Sil"
                    style={{ color: "var(--stopped)" }}
                  >
                    <Trash size={14} weight="bold" />
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      </main>

      {showAdd && (
        <AddBotModal
          onClose={() => setShowAdd(false)}
          onCreated={async () => {
            setShowAdd(false);
            await load();
          }}
        />
      )}
      {logBot && <LogsModal bot={logBot} onClose={() => setLogBot(null)} />}
      {settingsBot && (
        <BotSettingsModal
          bot={settingsBot}
          onClose={() => setSettingsBot(null)}
          onSaved={load}
        />
      )}
      {confirmDel && (
        <div className="modal-backdrop" onClick={() => setConfirmDel(null)}>
          <div
            className="modal"
            onClick={(e) => e.stopPropagation()}
            data-testid="delete-confirm-modal"
            style={{ maxWidth: 420 }}
          >
            <div className="p-6">
              <div className="label-mini">// onayla</div>
              <h3 className="font-display text-2xl font-black mt-1">
                Botu sil?
              </h3>
              <p className="text-sm text-zinc-600 mt-3">
                <span className="font-mono">{confirmDel.name}</span> ve tüm
                dosyaları kalıcı olarak silinecek. Bu işlem geri alınamaz.
              </p>
              <div className="flex justify-end gap-3 mt-6">
                <button
                  onClick={() => setConfirmDel(null)}
                  className="btn btn-secondary"
                >
                  Vazgeç
                </button>
                <button
                  data-testid="confirm-delete-button"
                  onClick={() => onDelete(confirmDel.id)}
                  className="btn btn-danger"
                >
                  Evet, sil
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function MetricCard({ label, value, icon, testid }) {
  return (
    <div className="card p-5" data-testid={testid}>
      <div className="flex items-center justify-between">
        <div className="label-mini">{label}</div>
        <div style={{ color: "var(--text-muted)" }}>{icon}</div>
      </div>
      <div className="font-display text-3xl font-black tracking-tighter mt-2">
        {value}
      </div>
    </div>
  );
}
