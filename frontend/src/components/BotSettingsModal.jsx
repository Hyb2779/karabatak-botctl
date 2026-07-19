import { useEffect, useState } from "react";
import api, { formatApiErrorDetail } from "@/lib/api";
import {
  X,
  UploadSimple,
  FloppyDisk,
  Trash,
  File as FileIcon,
  FilePy,
  CheckCircle,
} from "@phosphor-icons/react";

function fmtSize(b) {
  if (b < 1024) return `${b} B`;
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`;
  return `${(b / (1024 * 1024)).toFixed(1)} MB`;
}

export default function BotSettingsModal({ bot, onClose, onSaved }) {
  const [name, setName] = useState(bot.name);
  const [description, setDescription] = useState(bot.description || "");
  const [autoRestart, setAutoRestart] = useState(!!bot.auto_restart);
  const [startCron, setStartCron] = useState(bot.start_cron || "");
  const [stopCron, setStopCron] = useState(bot.stop_cron || "");
  const [entryFile, setEntryFile] = useState(bot.entry_file || "");
  const [files, setFiles] = useState([]);
  const [pyFiles, setPyFiles] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");

  const loadFiles = async () => {
    try {
      const { data } = await api.get(`/bots/${bot.id}/files`);
      setFiles(data.files);
      setPyFiles(data.py_files);
    } catch (e) {
      // ignore
    }
  };

  useEffect(() => {
    loadFiles();
    // eslint-disable-next-line
  }, [bot.id]);

  const save = async (e) => {
    e?.preventDefault();
    setSaving(true);
    setErr("");
    setMsg("");
    try {
      await api.put(`/bots/${bot.id}`, {
        name: name.trim(),
        description: description.trim(),
        auto_restart: autoRestart,
        start_cron: startCron.trim() || null,
        stop_cron: stopCron.trim() || null,
        entry_file: entryFile,
      });
      setMsg("Ayarlar kaydedildi.");
      onSaved?.();
    } catch (e) {
      setErr(formatApiErrorDetail(e.response?.data?.detail) || e.message);
    } finally {
      setSaving(false);
    }
  };

  const uploadFile = async (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    setUploading(true);
    setErr("");
    try {
      const fd = new FormData();
      fd.append("file", f);
      await api.post(`/bots/${bot.id}/files`, fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      await loadFiles();
      onSaved?.();
    } catch (e) {
      setErr(formatApiErrorDetail(e.response?.data?.detail) || e.message);
    } finally {
      setUploading(false);
      e.target.value = "";
    }
  };

  const deleteFile = async (path) => {
    if (!window.confirm(`${path} dosyasını silmek istediğine emin misin?`)) return;
    try {
      await api.delete(`/bots/${bot.id}/files`, { params: { path } });
      await loadFiles();
    } catch (e) {
      setErr(formatApiErrorDetail(e.response?.data?.detail) || e.message);
    }
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal modal-wide"
        onClick={(e) => e.stopPropagation()}
        data-testid="bot-settings-modal"
      >
        <div className="flex items-center justify-between p-5 divider-strong">
          <div>
            <div className="label-mini">// yapılandırma</div>
            <h3 className="font-display text-2xl font-black mt-1">{bot.name}</h3>
            <div className="font-mono text-xs text-zinc-500 mt-1 truncate">
              {bot.id} · entry: {entryFile || "—"}
            </div>
          </div>
          <button onClick={onClose} className="btn btn-ghost btn-icon" data-testid="bot-settings-close">
            <X size={18} weight="bold" />
          </button>
        </div>

        <form onSubmit={save} className="p-5 grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* LEFT: meta */}
          <div className="flex flex-col gap-5">
            <div className="field">
              <label>Bot adı</label>
              <input data-testid="settings-name-input" value={name} onChange={(e) => setName(e.target.value)} />
            </div>
            <div className="field">
              <label>Açıklama</label>
              <textarea
                data-testid="settings-description-input"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={2}
              />
            </div>

            <div className="field">
              <label>Giriş dosyası (.py)</label>
              <select
                data-testid="settings-entry-select"
                value={entryFile}
                onChange={(e) => setEntryFile(e.target.value)}
              >
                <option value="">— seçilmemiş —</option>
                {pyFiles.map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </select>
            </div>

            <label className="flex items-center justify-between cursor-pointer">
              <div>
                <div className="text-sm font-semibold">Çöktüğünde yeniden başlat</div>
                <div className="text-xs text-zinc-500">
                  İzleyici her 5 saniyede crash kontrolü yapar
                </div>
              </div>
              <span
                data-testid="settings-autorestart-toggle"
                onClick={() => setAutoRestart(!autoRestart)}
                className={`toggle ${autoRestart ? "on" : ""}`}
              />
            </label>

            <div className="card p-4" style={{ background: "var(--surface)" }}>
              <div className="label-mini mb-3">// zamanlama (cron)</div>
              <div className="grid grid-cols-1 gap-3">
                <div className="field">
                  <label>Başlat</label>
                  <input
                    data-testid="settings-start-cron-input"
                    value={startCron}
                    onChange={(e) => setStartCron(e.target.value)}
                    placeholder="0 9 * * *  (her gün 09:00)"
                  />
                </div>
                <div className="field">
                  <label>Durdur</label>
                  <input
                    data-testid="settings-stop-cron-input"
                    value={stopCron}
                    onChange={(e) => setStopCron(e.target.value)}
                    placeholder="0 23 * * *  (her gün 23:00)"
                  />
                </div>
              </div>
              <div className="text-xs text-zinc-500 mt-3 font-mono">
                format: dakika saat gün ay haftaiçigünü
              </div>
            </div>
          </div>

          {/* RIGHT: files */}
          <div className="flex flex-col gap-4">
            <div className="flex items-center justify-between">
              <div className="label-mini">// bot dosyaları ({files.length})</div>
              <label
                htmlFor="bot-extra-file"
                className="btn btn-secondary btn-sm cursor-pointer"
                data-testid="settings-upload-file-btn"
              >
                <UploadSimple size={14} weight="bold" /> Dosya ekle
              </label>
              <input
                id="bot-extra-file"
                data-testid="settings-upload-file-input"
                type="file"
                onChange={uploadFile}
                style={{ display: "none" }}
                disabled={uploading}
              />
            </div>

            <div
              className="card overflow-auto"
              style={{ maxHeight: 360, background: "#fff" }}
            >
              {files.length === 0 && (
                <div className="p-6 text-center text-sm text-zinc-500">
                  Henüz dosya yok.
                </div>
              )}
              {files.map((f) => {
                const isEntry = f.path === entryFile;
                return (
                  <div
                    key={f.path}
                    data-testid={`settings-file-${f.path}`}
                    className="px-3 py-2 flex items-center gap-3 text-sm"
                    style={{ borderBottom: "1px solid var(--border-light)" }}
                  >
                    {f.is_py ? (
                      <FilePy size={16} weight="duotone" />
                    ) : (
                      <FileIcon size={16} weight="duotone" />
                    )}
                    <div className="flex-1 min-w-0">
                      <div className="font-mono truncate flex items-center gap-2">
                        {f.path}
                        {isEntry && (
                          <span
                            className="font-bold uppercase tracking-widest text-[10px]"
                            style={{ color: "var(--running)" }}
                          >
                            <CheckCircle size={12} weight="fill" className="inline" /> entry
                          </span>
                        )}
                      </div>
                      <div className="text-xs text-zinc-500 font-mono">
                        {fmtSize(f.size)}
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => deleteFile(f.path)}
                      className="btn btn-ghost btn-icon btn-sm"
                      style={{ color: "var(--stopped)" }}
                      disabled={isEntry}
                      title={isEntry ? "Entry dosyası — önce başkasını seç" : "Sil"}
                    >
                      <Trash size={14} weight="bold" />
                    </button>
                  </div>
                );
              })}
            </div>
            <div className="text-xs text-zinc-500 font-mono">
              Bot çalışırken bot klasörü:{" "}
              <span className="text-zinc-800">
                /app/bot_storage/bots/{bot.id}/
              </span>
            </div>
          </div>

          {/* Bottom row spans 2 cols */}
          <div className="md:col-span-2 flex flex-col gap-3">
            {err && (
              <div className="font-mono text-xs px-4 py-3"
                style={{ background: "#fef2f2", border: "1px solid #ef4444", color: "#991b1b" }}>
                ! {err}
              </div>
            )}
            {msg && (
              <div className="font-mono text-xs px-4 py-3"
                style={{ background: "#ecfdf5", border: "1px solid #10b981", color: "#065f46" }}>
                ✓ {msg}
              </div>
            )}
            <div className="flex justify-end gap-3">
              <button type="button" onClick={onClose} className="btn btn-secondary">
                Kapat
              </button>
              <button
                data-testid="settings-save-button"
                type="submit"
                disabled={saving}
                className="btn btn-primary"
              >
                <FloppyDisk size={16} weight="bold" />
                {saving ? "Kaydediliyor..." : "Kaydet"}
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
}
