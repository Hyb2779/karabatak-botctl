import { useState } from "react";
import { useNavigate, Navigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { formatApiErrorDetail } from "@/lib/api";
import { ArrowRight, Terminal } from "@phosphor-icons/react";

const HERO_IMG =
  "https://images.unsplash.com/photo-1683322499436-f4383dd59f5a?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjA1MDV8MHwxfHNlYXJjaHwxfHxhYnN0cmFjdCUyMHRlY2hub2xvZ3klMjBzZXJ2ZXIlMjBuZXR3b3JrfGVufDB8fHx8MTc4MjI0NTkzNHww&ixlib=rb-4.1.0&q=85";

export default function Login() {
  const { user, login } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");
  const navigate = useNavigate();

  if (user && user !== false) return <Navigate to="/" replace />;

  const onSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setErr("");
    try {
      await login(username.trim(), password);
      navigate("/", { replace: true });
    } catch (e) {
      setErr(formatApiErrorDetail(e.response?.data?.detail) || e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen grid lg:grid-cols-2">
      {/* LEFT: hero */}
      <div
        className="relative hidden lg:flex items-end p-10"
        style={{
          backgroundImage: `linear-gradient(rgba(10,10,10,0.55), rgba(10,10,10,0.55)), url(${HERO_IMG})`,
          backgroundSize: "cover",
          backgroundPosition: "center",
        }}
      >
        <div className="text-white max-w-md">
          <div className="flex items-center gap-3 mb-8">
            <Terminal size={28} weight="bold" />
            <span className="label-mini" style={{ color: "#a1a1aa" }}>
              v1.0 / ubuntu edition
            </span>
          </div>
          <h1 className="font-display text-6xl xl:text-7xl font-black leading-[0.95]">
            BOT.<span style={{ color: "#4ade80" }}>CTL</span>
          </h1>
          <p className="mt-6 font-mono text-sm text-white/70 max-w-sm leading-relaxed">
            Telegram botlarını tek bir kontrol panelinden başlat, durdur, izle
            ve zamanla. Sunucunda çalışan her process tek yerden yönetilir.
          </p>
          <div className="mt-12 grid grid-cols-3 gap-4 font-mono text-xs text-white/60">
            <div>
              <div className="text-white text-2xl font-black">01</div>
              <div className="uppercase tracking-widest">Process</div>
            </div>
            <div>
              <div className="text-white text-2xl font-black">02</div>
              <div className="uppercase tracking-widest">Schedule</div>
            </div>
            <div>
              <div className="text-white text-2xl font-black">03</div>
              <div className="uppercase tracking-widest">Restart</div>
            </div>
          </div>
        </div>
      </div>

      {/* RIGHT: form */}
      <div className="flex flex-col justify-center px-8 sm:px-14 lg:px-20 py-12">
        <div className="lg:hidden flex items-center gap-3 mb-10">
          <Terminal size={26} weight="bold" />
          <span className="font-display text-3xl font-black">
            BOT.<span style={{ color: "#10b981" }}>CTL</span>
          </span>
        </div>
        <div className="label-mini mb-3">// admin oturum açma</div>
        <h2 className="font-display text-4xl sm:text-5xl font-black mb-2">
          Sunucu kontrol
          <br />
          merkezi.
        </h2>
        <p className="text-sm text-zinc-500 mb-10 max-w-sm">
          Botlarına erişmek için sysadmin kimlik bilgilerini gir.
        </p>

        <form onSubmit={onSubmit} className="flex flex-col gap-6 max-w-md">
          <div className="field">
            <label htmlFor="u">Kullanıcı adı</label>
            <input
              id="u"
              data-testid="login-username-input"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="admin"
              autoFocus
            />
          </div>
          <div className="field">
            <label htmlFor="p">Şifre</label>
            <input
              id="p"
              data-testid="login-password-input"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••••"
            />
          </div>

          {err && (
            <div
              data-testid="login-error"
              className="font-mono text-xs px-4 py-3"
              style={{
                background: "#fef2f2",
                border: "1px solid #ef4444",
                color: "#991b1b",
              }}
            >
              ! {err}
            </div>
          )}

          <button
            data-testid="login-submit-button"
            type="submit"
            disabled={loading}
            className="btn btn-primary"
            style={{ alignSelf: "flex-start" }}
          >
            {loading ? "Doğrulanıyor..." : "Giriş yap"}
            <ArrowRight size={16} weight="bold" />
          </button>
        </form>

        <div className="mt-16 font-mono text-xs text-zinc-400">
          $ ssh admin@bot.ctl <span className="cursor-blink">▌</span>
        </div>
      </div>
    </div>
  );
}
