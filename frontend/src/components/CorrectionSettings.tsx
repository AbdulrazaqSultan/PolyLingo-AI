import { useEffect, useState } from "react";
import { api } from "../services/api";
import { useI18n } from "../i18n";
export default function CorrectionSettings() {
  const { t } = useI18n();
  const [settings, setSettings] = useState<any>(null),
    [providers, setProviders] = useState<any[]>([]),
    [languages, setLanguages] = useState<any[]>([]);
  const [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [saving, setSaving] = useState(false);
  useEffect(() => {
    Promise.all([
      api("/admin/settings"),
      api("/admin/providers"),
      api("/admin/languages"),
    ])
      .then(([opts, p, langs]) => {
        setSettings(opts);
        setProviders(p);
        setLanguages(langs);
      })
      .catch((e) => setError(e.message));
  }, []);
  const field = (key: string, value: unknown) =>
    setSettings({ ...settings, [key]: value });
  if (!settings)
    return <p className="muted">{t(error || "Loading settings…")}</p>;
  return (
    <form
      className="admin-card settings-form"
      onSubmit={async (e) => {
        e.preventDefault();
        setSaving(true);
        setError("");
        setNotice("");
        try {
          await api("/admin/settings", {
            method: "PATCH",
            body: JSON.stringify(settings),
          });
          setNotice("System settings saved.");
        } catch (e) {
          setError((e as Error).message);
        } finally {
          setSaving(false);
        }
      }}
    >
      <h3>{t("Transcript Correction")}</h3>
      <p className="muted">
        {t(
          "Conservative refinement preserves names, numbers and technical content. Uncertain corrections always fall back to the original transcript.",
        )}
      </p>
      {error && (
        <p className="error" role="alert">
          {t(error)}
        </p>
      )}
      {notice && (
        <p className="notice" role="status">
          {t(notice)}
        </p>
      )}
      <div className="form-grid">
        <label className="form-field">
          <span>{t("Correction enabled")}</span>
          <input
            type="checkbox"
            checked={settings.transcript_correction_enabled}
            onChange={(e) =>
              field("transcript_correction_enabled", e.target.checked)
            }
          />
        </label>
        <label className="form-field">
          <span>{t("Automatic voice translation")}</span>
          <input
            type="checkbox"
            checked={settings.auto_translate_voice}
            onChange={(e) => field("auto_translate_voice", e.target.checked)}
          />
        </label>
        <label className="form-field">
          <span>{t("Correction provider")}</span>
          <select
            value={settings.transcript_correction_provider}
            onChange={(e) =>
              field("transcript_correction_provider", e.target.value)
            }
          >
            {["hybrid", "rule_based", "llm"].map((v) => (
              <option key={v} value={v}>
                {t(v)}
              </option>
            ))}
          </select>
        </label>
        <label className="form-field">
          <span>{t("Correction API provider")}</span>
          <select
            value={settings.correction_api_provider_id ?? ""}
            onChange={(e) =>
              field(
                "correction_api_provider_id",
                e.target.value ? Number(e.target.value) : null,
              )
            }
          >
            <option value="">{t("None · local rules only")}</option>
            {providers
              .filter((p) => p.enabled)
              .map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
          </select>
        </label>
        <label className="form-field">
          <span>{t("Correction model identifier")}</span>
          <input
            dir="auto"
            value={settings.correction_model_id}
            onChange={(e) => field("correction_model_id", e.target.value)}
          />
        </label>
        <label className="form-field">
          <span>{t("Correction threshold")}</span>
          <input
            type="number"
            min=".8"
            max="1"
            step=".01"
            value={settings.correction_confidence_threshold}
            onChange={(e) =>
              field("correction_confidence_threshold", Number(e.target.value))
            }
          />
        </label>
        <label className="form-field">
          <span>{t("Correction timeout (seconds)")}</span>
          <input
            type="number"
            min=".1"
            max="30"
            step=".1"
            value={settings.correction_timeout}
            onChange={(e) =>
              field("correction_timeout", Number(e.target.value))
            }
          />
        </label>
        <label className="form-field">
          <span>{t("Fallback behavior")}</span>
          <input readOnly value={t("Keep raw transcript")} />
        </label>
      </div>
      <fieldset className="correction-languages">
        <legend>{t("Enabled correction languages")}</legend>
        {languages.map((l) => (
          <label key={l.iso}>
            <input
              type="checkbox"
              checked={settings.correction_languages.includes(l.iso)}
              onChange={(e) =>
                field(
                  "correction_languages",
                  e.target.checked
                    ? [...settings.correction_languages, l.iso]
                    : settings.correction_languages.filter(
                        (iso: string) => iso !== l.iso,
                      ),
                )
              }
            />
            {t(l.name)}
          </label>
        ))}
      </fieldset>
      <p className="muted">
        {t(
          "The threshold is a conservative safety score, not calibrated model confidence. External correction is optional and uses the saved server-side API credentials.",
        )}
      </p>
      <button className="primary" disabled={saving}>
        {t("Save settings")}
      </button>
    </form>
  );
}
