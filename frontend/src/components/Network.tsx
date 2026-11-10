import { useI18n } from "../i18n";
export default function Network() {
  const { t } = useI18n();
  return (
    <div className="network" aria-hidden="true">
      <div className="orbit orbit-one" />
      <div className="orbit orbit-two" />
      <div className="globe-grid" />
      <svg viewBox="0 0 460 320">
        <defs>
          <linearGradient id="signal">
            <stop stopColor="#58e7d5" />
            <stop offset="1" stopColor="#8d7dff" />
          </linearGradient>
        </defs>
        {[
          [75, 95, 225, 160],
          [225, 160, 375, 75],
          [225, 160, 355, 265],
          [225, 160, 85, 255],
          [75, 95, 375, 75],
          [85, 255, 355, 265],
        ].map((a, i) => (
          <g key={i}>
            <path
              d={`M ${a[0]} ${a[1]} Q 230 65 ${a[2]} ${a[3]}`}
              stroke="url(#signal)"
              fill="none"
              opacity=".35"
            />
            <circle r="3" fill="#65e5d4">
              <animateMotion
                dur={`${3 + i}s`}
                repeatCount="indefinite"
                path={`M ${a[0]} ${a[1]} Q 230 65 ${a[2]} ${a[3]}`}
              />
            </circle>
          </g>
        ))}
      </svg>
      <div className="node n-ar">
        ع<span>{t("Arabic")}</span>
      </div>
      <div className="node n-en">
        Aa<span>{t("English")}</span>
      </div>
      <div className="node n-fr">
        É<span>{t("French")}</span>
      </div>
      <div className="node n-zh">
        文<span>{t("Chinese")}</span>
      </div>
      <div className="network-core">
        P<span>{t("NEURAL CORE")}</span>
      </div>
      <div className="network-caption">
        <i />
        {t("LANGUAGE HAS NO BORDERS")}
      </div>
    </div>
  );
}
