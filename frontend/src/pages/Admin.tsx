import { useI18n, LanguageSwitcher } from "../i18n";
import { useEffect, useState } from "react";
import {
  Activity,
  ArrowLeft,
  AudioLines,
  BarChart3,
  Check,
  ChevronRight,
  Database,
  Globe2,
  Layers,
  LogOut,
  Plus,
  RefreshCw,
  Route,
  Save,
  Settings,
  ShieldCheck,
  Terminal,
  X,
} from "lucide-react";
import { api, setCsrf } from "../services/api";
import CorrectionSettings from "../components/CorrectionSettings";
const nav = [
  ["Overview", Activity],
  ["AI Models", Layers],
  ["Languages", Globe2],
  ["Providers", Database],
  ["Routing", Route],
  ["Analytics", BarChart3],
  ["Logs", Terminal],
  ["Settings", Settings],
  ["Transcript Correction", Layers],
] as const;
const kinds: Record<string, string> = {
  "AI Models": "models",
  Languages: "languages",
  Providers: "providers",
  Routing: "routing",
};
const defaults: Record<string, any> = {
  models: {
    name: "",
    model_type: "translation",
    provider_type: "local_nllb",
    model_id: "facebook/nllb-200-distilled-600M",
    local_path: "",
    adapter_path: "",
    version: "1",
    description: "",
    languages: ["ar", "en", "fr", "zh"],
    device: "auto",
    precision: "auto",
    enabled: true,
    default: false,
    provider_id: null,
  },
  languages: {
    name: "",
    native: "",
    iso: "",
    nllb: "",
    stt: "",
    tts: "",
    direction: "ltr",
    enabled: true,
  },
  providers: {
    name: "",
    provider_type: "openai_compatible",
    base_url: "https://",
    model_name: "",
    api_key: "",
    timeout: 30,
    enabled: true,
    priority: 10,
  },
  routing: {
    source: "en",
    target: "ar",
    model_id: 0,
    fallback_model_id: null,
    enabled: true,
  },
};
const choices: Record<string, string[]> = {
  model_type: ["translation", "stt", "tts"],
  provider_type: [
    "local_nllb",
    "whisper",
    "edge_tts",
    "custom_http",
    "openai_compatible",
  ],
  device: ["auto", "cpu", "cuda"],
  precision: ["auto", "float16", "float32"],
  direction: ["ltr", "rtl"],
};
function title(s: string) {
  return s.replaceAll("_", " ").replace(/\b\w/g, (c) => c.toUpperCase());
}
function Chart({
  name,
  data,
  unit = "",
}: {
  name: string;
  data: Record<string, number>;
  unit?: string;
}) {
  const { t } = useI18n();
  const rows = Object.entries(data);
  const max = Math.max(1, ...rows.map(([, v]) => v));
  return (
    <section className="admin-card chart">
      <h3>{name}</h3>
      {!rows.length ? (
        <p className="muted">
          {t(
            "No requests yet. Analytics will appear after the first translation.",
          )}
        </p>
      ) : (
        rows.map(([label, value]) => (
          <div className="chart-row" key={t(label)}>
            <div>
              <span>{t(label)}</span>
              <strong>
                {value.toLocaleString()}
                {unit}
              </strong>
            </div>
            <div className="bar-track">
              <i style={{ width: Math.max(2, (value / max) * 100) + "%" }} />
            </div>
          </div>
        ))
      )}
    </section>
  );
}
export default function Admin() {
  const { t, locale } = useI18n();
  const [authenticated, setAuthenticated] = useState(false),
    [checking, setChecking] = useState(true),
    [username, setUsername] = useState("admin"),
    [password, setPassword] = useState("");
  const [page, setPage] = useState("Overview"),
    [dashboard, setDashboard] = useState<any>(null),
    [rows, setRows] = useState<any[]>([]),
    [settings, setSettings] = useState<any>(null),
    [edit, setEdit] = useState<any>(null),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [busy, setBusy] = useState(false),
    [filter, setFilter] = useState("");
  const [models, setModels] = useState<any[]>([]);
  useEffect(() => {
    api("/admin/session")
      .then((data) => {
        setCsrf(data.csrf);
        setAuthenticated(true);
      })
      .catch(() => {})
      .finally(() => setChecking(false));
  }, []);
  async function load() {
    setError("");
    setBusy(true);
    try {
      if (page === "Transcript Correction") return;
      if (page === "Overview" || page === "Analytics")
        setDashboard(await api("/admin/dashboard"));
      else if (page === "Settings") setSettings(await api("/admin/settings"));
      else if (page === "Logs")
        setRows(
          await api("/admin/logs?category=" + encodeURIComponent(filter)),
        );
      else {
        setRows(await api("/admin/" + kinds[page]));
        setModels(await api("/admin/models"));
      }
    } catch (e) {
      setError((e as Error).message);
      if ((e as Error).message.includes("sign-in")) setAuthenticated(false);
    } finally {
      setBusy(false);
    }
  }
  useEffect(() => {
    if (authenticated) void load();
  }, [authenticated, page, filter]);
  async function login(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const data = await api("/admin/login", {
        method: "POST",
        body: JSON.stringify({ username, password }),
      });
      setCsrf(data.csrf);
      setAuthenticated(true);
      setPassword("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function save() {
    setBusy(true);
    setError("");
    try {
      const kind = kinds[page],
        { id, api_key_mask, ...body } = edit;
      if (kind === "models" && typeof body.languages === "string")
        body.languages = body.languages
          .split(",")
          .map((s: string) => s.trim())
          .filter(Boolean);
      if (kind === "providers" && !body.api_key) delete body.api_key;
      await api("/admin/" + kind + (id ? "/" + id : ""), {
        method: id ? "PATCH" : "POST",
        body: JSON.stringify(body),
      });
      setEdit(null);
      setNotice("Configuration saved.");
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  function editorField(key: string, value: any) {
    if (["id", "api_key_mask"].includes(key)) return null;
    const selectOptions =
      key === "provider_type" && page === "Providers"
        ? ["custom_http", "openai_compatible"]
        : choices[key];
    const isModel =
      page === "Routing" && ["model_id", "fallback_model_id"].includes(key);
    return (
      <label className="form-field" key={key}>
        <span>{t(title(key))}</span>
        {typeof value === "boolean" ? (
          <input
            type="checkbox"
            checked={value}
            onChange={(e) => setEdit({ ...edit, [key]: e.target.checked })}
          />
        ) : isModel ? (
          <select
            value={value ?? ""}
            onChange={(e) =>
              setEdit({
                ...edit,
                [key]: e.target.value ? Number(e.target.value) : null,
              })
            }
          >
            <option value="">{t("None")}</option>
            {models
              .filter((m) => m.model_type === "translation")
              .map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name}
                </option>
              ))}
          </select>
        ) : selectOptions ? (
          <select
            value={value}
            onChange={(e) => setEdit({ ...edit, [key]: e.target.value })}
          >
            {selectOptions.map((v) => (
              <option key={v} value={v}>
                {t(v)}
              </option>
            ))}
          </select>
        ) : (
          <input
            type={
              key === "api_key"
                ? "password"
                : typeof value === "number" || key === "provider_id"
                  ? "number"
                  : "text"
            }
            autoComplete={key === "api_key" ? "new-password" : "off"}
            value={Array.isArray(value) ? value.join(", ") : (value ?? "")}
            onChange={(e) =>
              setEdit({
                ...edit,
                [key]:
                  typeof value === "number" || key === "provider_id"
                    ? e.target.value
                      ? Number(e.target.value)
                      : null
                    : e.target.value,
              })
            }
          />
        )}
      </label>
    );
  }
  if (checking)
    return (
      <div className="admin-loading">
        <span className="spinner" />
        {t("Checking session\u2026")}
      </div>
    );
  if (!authenticated)
    return (
      <div className="login-page">
        <LanguageSwitcher />
        <a className="brand" href="/">
          <AudioLines />
          PolyLingo<span className="brand-ai">AI</span>
        </a>
        <form onSubmit={login} className="login-card">
          <ShieldCheck size={30} />
          <div className="eyebrow">{t("RESTRICTED WORKSPACE")}</div>
          <h1>{t("Administrator access")}</h1>
          <p>{t("Manage the intelligence behind every connection.")}</p>
          <label className="form-field">
            <span>{t("Username")}</span>
            <input
              value={username}
              autoComplete="username"
              onChange={(e) => setUsername(e.target.value)}
              required
            />
          </label>
          <label className="form-field">
            <span>{t("Password")}</span>
            <input
              type="password"
              value={password}
              autoComplete="current-password"
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </label>
          {error && (
            <p className="error" role="alert">
              {t(error)}
            </p>
          )}
          <button className="primary" disabled={busy}>
            {t("Sign in securely")}
            <ChevronRight size={16} />
          </button>
          <a className="text-link" href="/">
            <ArrowLeft size={14} />
            {t("Back to translator")}
          </a>
        </form>
      </div>
    );
  return (
    <div className="admin-app">
      <aside className="admin-sidebar">
        <a className="brand" href="/">
          <AudioLines />
          PolyLingo<span className="brand-ai">AI</span>
        </a>
        <div className="admin-badge">
          <ShieldCheck size={13} />
          {t("ADMINISTRATION")}
        </div>
        <nav>
          {nav.map(([label, Icon]) => (
            <button
              key={t(label)}
              className={page === label ? "selected" : ""}
              onClick={() => {
                setPage(label);
                setNotice("");
                setEdit(null);
              }}
            >
              <Icon size={17} />
              {t(label)}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <a className="text-link" href="/">
            <ArrowLeft size={15} />
            {t("Translator")}
          </a>
          <button
            className="text-link"
            onClick={async () => {
              try {
                await api("/admin/logout", { method: "POST" });
                setAuthenticated(false);
                setCsrf("");
              } catch (e) {
                setError((e as Error).message);
              }
            }}
          >
            <LogOut size={15} />
            {t("Sign out")}
          </button>
        </div>
      </aside>
      <main className="admin-main">
        <header className="admin-header">
          <div>
            <span className="eyebrow">{t("POLYLINGO / CONTROL CENTER")}</span>
            <h1>{t(page)}</h1>
          </div>
          <button
            className="secondary"
            disabled={busy}
            onClick={() => void load()}
          >
            <RefreshCw size={15} />
            {t("Refresh")}
          </button>
          <LanguageSwitcher />
        </header>
        {error && (
          <div className="error" role="alert">
            {t(error)}
          </div>
        )}
        {notice && (
          <div className="notice" role="status">
            <Check size={15} />
            {t(notice)}
          </div>
        )}
        {busy && <div className="loading-line" />}
        {dashboard && (page === "Overview" || page === "Analytics") && (
          <>
            <div className="stats-grid">
              {[
                ["Translation requests", dashboard.total_requests],
                ["Requests today", dashboard.today],
                ["Average latency", dashboard.average_ms + " ms"],
                ["Failed requests", dashboard.failures],
              ].map(([label, value]) => (
                <article className="admin-card stat" key={t(label)}>
                  <span>{t(label)}</span>
                  <strong>{value}</strong>
                </article>
              ))}
            </div>
            {page === "Overview" && (
              <div className="admin-grid">
                <section className="admin-card">
                  <h3>{t("Inference environment")}</h3>
                  {Object.entries({
                    Device: dashboard.device,
                    CUDA: dashboard.cuda ? t("Available") : t("Unavailable"),
                    "GPU memory":
                      dashboard.gpu_memory_mb === null
                        ? "—"
                        : dashboard.gpu_memory_mb + " MB",
                    "Resident model":
                      dashboard.model_health.loaded_model_id ||
                      "None · lazy loading",
                    "Model status": dashboard.model_health.status,
                    "Last used":
                      dashboard.model_health.last_used || "Not yet used",
                    "Enabled languages": dashboard.languages,
                    "Admin sessions": dashboard.active_sessions,
                    "App version": dashboard.version,
                  }).map(([k, v]) => (
                    <div className="key-value" key={t(k)}>
                      <span>{t(k)}</span>
                      <strong>{t(String(v))}</strong>
                    </div>
                  ))}
                </section>
                <section className="admin-card">
                  <h3>{t("Active AI providers")}</h3>
                  {Object.entries(dashboard.active_models).map(([k, v]) => (
                    <div className="model-summary" key={t(k)}>
                      <Layers size={19} />
                      <div>
                        <span>{t(k)}</span>
                        <strong>
                          {t(String(v || "No default configured"))}
                        </strong>
                      </div>
                      <span className="tag">{t("DEFAULT")}</span>
                    </div>
                  ))}
                  <p className="muted">
                    {t(
                      "Provider health is verified on demand in AI Models. A running API does not imply downloaded models are ready.",
                    )}
                  </p>
                </section>
              </div>
            )}
            <div className="admin-grid">
              <Chart
                name={t("Requests over time")}
                data={dashboard.requests_by_day}
              />
              <Chart
                name={t("Target language usage")}
                data={dashboard.languages_usage}
              />
              <Chart
                name={t("Translation directions")}
                data={dashboard.directions}
              />
              <Chart name={t("Provider usage")} data={dashboard.providers} />
              <Chart
                name={t("Average latency by day")}
                data={dashboard.latency_by_day}
                unit=" ms"
              />
              <Chart
                name={t("Failures over time")}
                data={dashboard.failures_by_day}
              />
            </div>
            <p className="muted">
              {t(dashboard.window)}{" "}
              {t(
                ". No source or translated text is retained in server analytics.",
              )}
            </p>
          </>
        )}
        {kinds[page] && (
          <>
            <div className="registry-heading">
              <p className="muted">
                {page === "Routing"
                  ? t(
                      "Assign a translation model and an explicit fallback to each language pair.",
                    )
                  : page === "Providers"
                    ? t(
                        "Keys are encrypted on the server. Provider hosts must be allowed in server configuration.",
                      )
                    : page === "AI Models"
                      ? t(
                          "Register models, choose defaults, and verify inference health.",
                        )
                      : t(
                          "Language metadata drives every selector and provider mapping.",
                        )}
              </p>
              <button
                className="primary"
                onClick={() => {
                  setError("");
                  setEdit({ ...defaults[kinds[page]] });
                }}
              >
                <Plus size={16} />
                {t("Add")}{" "}
                {page === "AI Models"
                  ? t("model")
                  : page === "Languages"
                    ? t("language")
                    : page === "Routing"
                      ? t("rule")
                      : t("provider")}
              </button>
            </div>
            <div className="admin-card table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>{page === "Routing" ? t("Direction") : t("Name")}</th>
                    <th>{t("Configuration")}</th>
                    <th>{t("Status")}</th>
                    <th>{t("Actions")}</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr key={row.id}>
                      <td>
                        <strong>
                          {row.name || row.source + " → " + row.target}
                        </strong>
                        <small>
                          {t("Registry #")}
                          {row.id}
                        </small>
                      </td>
                      <td>
                        {row.model_type ||
                          row.nllb ||
                          row.provider_type ||
                          "Model #" + row.model_id}
                        <small>
                          {row.model_id && page === "AI Models"
                            ? row.model_id
                            : row.base_url ||
                              row.native ||
                              "Fallback: " + (row.fallback_model_id || "none")}
                        </small>
                      </td>
                      <td>
                        <span
                          className={"tag " + (row.enabled ? "enabled" : "")}
                        >
                          {row.enabled ? t("Enabled") : t("Disabled")}
                        </span>
                        {row.default && (
                          <span className="tag">{t("Default")}</span>
                        )}
                      </td>
                      <td>
                        <button
                          className="secondary"
                          onClick={() => {
                            setError("");
                            setEdit({
                              ...row,
                              ...(page === "Providers" ? { api_key: "" } : {}),
                            });
                          }}
                        >
                          {t("Edit")}
                        </button>
                        {page === "AI Models" && (
                          <button
                            className="text-link"
                            disabled={busy}
                            onClick={async () => {
                              setBusy(true);
                              setError("");
                              try {
                                const res = await api(
                                  "/admin/models/" + row.id + "/test",
                                  { method: "POST" },
                                );
                                setNotice(res.detail);
                              } catch (e) {
                                setError((e as Error).message);
                              } finally {
                                setBusy(false);
                              }
                            }}
                          >
                            {t("Test")}
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!rows.length && (
                <div className="empty">
                  <Database size={28} />
                  <p>{t("No configurations yet. Add the first one above.")}</p>
                </div>
              )}
            </div>
          </>
        )}
        {page === "Logs" && (
          <>
            <div className="registry-heading">
              <p className="muted">
                {t(
                  "Operational messages exclude submitted text, credentials, and stack traces.",
                )}
              </p>
              <select
                aria-label={t("Filter logs by category")}
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
              >
                <option value="">{t("All categories")}</option>
                {["request", "translation", "speech", "model"].map((v) => (
                  <option key={v} value={v}>
                    {t(v)}
                  </option>
                ))}
              </select>
            </div>
            <section className="admin-card">
              {rows.length ? (
                rows.map((row) => (
                  <div className="log-row" key={row.id}>
                    <time>
                      {new Date(row.timestamp).toLocaleString(
                        locale === "ar" ? "ar-SA" : "en-GB",
                      )}
                    </time>
                    <span className="tag">{t(row.category)}</span>
                    <p>{t(row.message)}</p>
                  </div>
                ))
              ) : (
                <div className="empty">
                  <ShieldCheck size={30} />
                  <p>{t("No operational errors recorded.")}</p>
                </div>
              )}
            </section>
          </>
        )}
        {page === "Transcript Correction" && <CorrectionSettings />}
        {page === "Settings" && settings && (
          <form
            className="admin-card settings-form"
            onSubmit={async (e) => {
              e.preventDefault();
              setBusy(true);
              setError("");
              try {
                await api("/admin/settings", {
                  method: "PATCH",
                  body: JSON.stringify(settings),
                });
                setNotice("System settings saved.");
              } catch (e) {
                setError((e as Error).message);
              } finally {
                setBusy(false);
              }
            }}
          >
            <h3>{t("Application behavior")}</h3>
            <div className="form-grid">
              {Object.entries(settings)
                .filter(
                  ([key]) =>
                    !key.startsWith("correction_") &&
                    !key.startsWith("transcript_correction") &&
                    key !== "auto_translate_voice",
                )
                .map(([key, value]) => (
                  <label className="form-field" key={key}>
                    <span>{t(title(key))}</span>
                    <input
                      type={
                        typeof value === "boolean"
                          ? "checkbox"
                          : typeof value === "number"
                            ? "number"
                            : "text"
                      }
                      checked={typeof value === "boolean" ? value : undefined}
                      value={
                        typeof value === "boolean" ? undefined : String(value)
                      }
                      onChange={(e) =>
                        setSettings({
                          ...settings,
                          [key]:
                            typeof value === "boolean"
                              ? e.target.checked
                              : typeof value === "number"
                                ? Number(e.target.value)
                                : e.target.value,
                        })
                      }
                    />
                  </label>
                ))}
            </div>
            <p className="muted">
              {t(
                "Set default translation, STT, and TTS providers in AI Models using the Default field.",
              )}
            </p>
            <button className="primary" disabled={busy}>
              <Save size={15} />
              {t("Save settings")}
            </button>
          </form>
        )}
      </main>
      {edit && (
        <div className="modal-backdrop">
          <form
            className="config-modal"
            onSubmit={(e) => {
              e.preventDefault();
              void save();
            }}
          >
            <div className="section-heading">
              <h2>
                {edit.id ? t("Edit") : t("Add")} {t("configuration")}
              </h2>
              <button
                type="button"
                className="icon-button"
                aria-label={t("Close editor")}
                onClick={() => setEdit(null)}
              >
                <X />
              </button>
            </div>
            {error && (
              <p className="error" role="alert">
                {t(error)}
              </p>
            )}
            <div className="form-grid">
              {Object.entries(edit).map(([k, v]) => editorField(k, v))}
            </div>
            {page === "Providers" && (
              <p className="muted">
                {t(
                  "Leave API key blank to preserve the saved key. Saved keys are never returned to this browser.",
                )}
              </p>
            )}
            {page === "AI Models" && (
              <p className="muted">
                {t(
                  "Languages: comma-separated ISO codes. External models require the registered provider ID. Local paths are resolved only by the server.",
                )}
              </p>
            )}
            <button className="primary" disabled={busy}>
              <Save size={15} />
              {t("Save configuration")}
            </button>
          </form>
        </div>
      )}
    </div>
  );
}
