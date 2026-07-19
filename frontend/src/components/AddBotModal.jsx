import { useState } from "react";
import api, { formatApiErrorDetail } from "@/lib/api";
import { X, UploadSimple, FileZip, FilePy } from "@phosphor-icons/react";

export default function AddBotModal({ onClose, onCreated }) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [autoRestart, setAutoRestart] = useState(true);
  const [file, setFile] = useState(null);
  const [entryFile, setEntryFile] = useState("");
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");
  const [pendingChoice, setPendingChoice] = useState(null); // {bot_id, py_files}

  const submit = async (chosenEntry) => {
    setLoading(true);
    setErr("");
    try {
      const fd = new FormData();
      fd.append("name", name.trim());
      fd.append("description", description.trim());
      fd.append("auto_restart", autoRestart ? "true" : "false");
      if (chosenEntry) fd.append("entry_file", chosenEntry);
      else if (entryFile.trim()) fd.append("entry_file", entryFile.trim());
      fd.append("file", file);
      const { data } = await api.post("/bots", fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      if (data.needs_entry_selection) {
        setPendingChoice(data);
      } else {
        onCreated(data);
      }
    } catch (e) {
      setErr(formatApiErrorDetail(e.response?.data?.detail) || e.message);
    } finally {
      setLoading(false);
    }
  };

  const onSubmit = async (e) => {
    e.preventDefault();
    if (!file) {
      setErr("Lütfen bir .py veya .zip dosyası seç.");
      return;
    }
    await submit();
  };

  const confirmEntry = async (entry) => {
    // Pending choice — call PUT /api/bots/{id} to set entry_file
    try {
      setLoading(true);
      await api.put(`/bots/${pendingChoice.id}`, { entry_file: entry });
      onCreated({ ...pendingChoice, entry_file: entry });
    } catch (e) {
      setErr(formatApiErrorDetail(e.response?.data?.detail) || e.message);
    } finally {
      setLoading(false);
    }
  };

  const cancelPending = async () => {
    if (!pendingChoice) return;
    try {
      await api.delete(`/bots/${pendingChoice.id}`);
    } catch {}
    setPendingChoice(null);
    setFile(null);
    setEntryFile("");
  };

  const isZip = file && /\.zip$/i.test(file.name);

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal"
        onClick={(e) => e.stopPropagation()}
        data-testid="add-bot-modal"
      >
        <div className="flex items-center justify-between p-5 divider-strong">
          <div>
            <div className="label-mini">// yeni bot</div>
            <h3 className="font-display text-2xl font-black mt-1">
              {pendingChoice ? "Giriş dosyasını seç" : "Bot ekle"}
            </h3>
          </div>
          <button onClick={onClose} className="btn btn-ghost btn-icon" data-testid="add-bot-modal-close">
            <X size={18} weight="bold" />
          </button>
        </div>

        {pendingChoice ? (
          <div className="p-5 flex flex-col gap-4">
            <p className="text-sm text-zinc-600">
              ZIP içinde birden fazla <code className="font-mono">.py</code>{" "}
              dosyası bulundu. Botun başlangıç (entry) dosyasını seç:
            </p>
            <div className="flex flex-col gap-2" data-testid="entry-picker">
              {pendingChoice.py_files.map((p) => (
                <button
                  key={p}
                  type="button"
                  data-testid={`entry-option-${p}`}
                  onClick={() => confirmEntry(p)}
                  disabled={loading}
                  className="card card-hover p-3 text-left font-mono text-sm flex items-center gap-3"
                >
                  <FilePy size={20} weight="duotone" />
                  {p}
                </button>
              ))}
            </div>
            {err && (
              <div className="font-mono text-xs px-4 py-3"
                style={{ background: "#fef2f2", border: "1px solid #ef4444", color: "#991b1b" }}>
                ! {err}
              </div>
            )}
            <div className="flex justify-end">
              <button onClick={cancelPending} className="btn btn-secondary">
                İptal et ve sil
              </button>
            </div>
          </div>
        ) : (
          <form onSubmit={onSubmit} className="p-5 flex flex-col gap-5">
            <div className="field">
              <label>Bot adı</label>
              <input
                data-testid="add-bot-name-input"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="örn. müşteri-destek-botu"
                required
              />
            </div>
            <div className="field">
              <label>Açıklama (opsiyonel)</label>
              <textarea
                data-testid="add-bot-description-input"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={2}
                placeholder="Bu bot ne yapıyor?"
              />
            </div>
            <div className="field">
              <label>Bot dosyası (.py veya .zip)</label>
              <label
                htmlFor="bot-file"
                className="card card-hover p-5 cursor-pointer flex items-center gap-3"
                data-testid="add-bot-file-dropzone"
                style={{ background: "var(--surface)" }}
              >
                {isZip ? (
                  <FileZip size={22} weight="duotone" />
                ) : (
                  <UploadSimple size={22} weight="bold" />
                )}
                <div className="flex-1">
                  <div className="font-mono text-sm">
                    {file ? file.name : "Tek .py dosyası ya da çoklu dosya için .zip yükle"}
                  </div>
                  <div className="text-xs text-zinc-500 mt-1">
                    Zip içinde session, json, media gibi yardımcı dosyalar olabilir
                  </div>
                </div>
              </label>
              <input
                id="bot-file"
                data-testid="add-bot-file-input"
                type="file"
                accept=".py,.zip"
                onChange={(e) => setFile(e.target.files?.[0] || null)}
                style={{ display: "none" }}
              />
            </div>

            {isZip && (
              <div className="field">
                <label>Giriş dosyası (opsiyonel)</label>
                <input
                  data-testid="add-bot-entry-input"
                  value={entryFile}
                  onChange={(e) => setEntryFile(e.target.value)}
                  placeholder="örn. main.py — boş bırakırsan sana sorulacak"
                />
              </div>
            )}

            <label className="flex items-center justify-between cursor-pointer">
              <div>
                <div className="text-sm font-semibold">Çöktüğünde yeniden başlat</div>
                <div className="text-xs text-zinc-500">
                  Bot beklenmedik şekilde kapanırsa otomatik yeniden başlatılır
                </div>
              </div>
              <span
                data-testid="add-bot-autorestart-toggle"
                onClick={() => setAutoRestart(!autoRestart)}
                className={`toggle ${autoRestart ? "on" : ""}`}
              />
            </label>

            {err && (
              <div className="font-mono text-xs px-4 py-3"
                style={{ background: "#fef2f2", border: "1px solid #ef4444", color: "#991b1b" }}>
                ! {err}
              </div>
            )}

            <div className="flex justify-end gap-3 pt-2">
              <button type="button" onClick={onClose} className="btn btn-secondary">
                İptal
              </button>
              <button
                data-testid="add-bot-submit"
                type="submit"
                disabled={loading}
                className="btn btn-primary"
              >
                {loading ? "Yükleniyor..." : "Bot ekle"}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
