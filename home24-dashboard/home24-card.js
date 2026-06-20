const HOME24_DEFAULTS = {
  outdoor_temperature: "sensor.wh2650a_outdoor_temperature",
  humidity: "sensor.wh2650a_humidity",
  wind: "sensor.wh2650a_wind_speed",
  solar_power: "sensor.pv_power_total",
  solar_today: "sensor.pv_production_totale_j",
  solar_peak: "sensor.pv_power_max",
  house_power: "sensor.multiplus_2_conso_totale",
  grid_power: "sensor.multiplus_2_reseau_puissance",
  battery_soc: "sensor.cerbo_gx_battery_soc",
  battery_voltage: "sensor.multiplus_2_dc_voltage",
  battery_power: "sensor.multiplus_2_dc_power",
  battery_capacity: "sensor.cerbo_gx_battery_remaining_capacity",
};

const HOME24_NAV = [
  ["Accueil", "Vue générale", "mdi:home-variant", "accueil"],
  ["Énergie", "Production et flux", "mdi:lightning-bolt", "energie"],
  ["Batterie", "État et réglages", "mdi:battery-heart", "batterie"],
  ["Climat", "Température et air", "mdi:thermometer", "climat"],
  ["Sécurité", "Alarmes et caméras", "mdi:shield-home", "securite"],
  ["Automatisations", "Scènes et routines", "mdi:robot", "automatisations"],
  ["Éclairage", "Lumières et ambiance", "mdi:lightbulb-group", "eclairage"],
  ["Système", "État et préférences", "mdi:cog", "systeme"],
];

class Home24Card extends HTMLElement {
  setConfig(config) {
    this.config = config || {};
    this.entities = { ...HOME24_DEFAULTS, ...(config.entities || {}) };
    this.backgrounds = config.backgrounds || {};
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    this.renderShell();
    this.updateClock();
  }

  connectedCallback() {
    this.clockTimer = window.setInterval(() => this.updateClock(), 30000);
    this.shadowRoot?.addEventListener("click", this.handleClick);
    this.updateClock();
  }

  disconnectedCallback() {
    window.clearInterval(this.clockTimer);
    this.shadowRoot?.removeEventListener("click", this.handleClick);
  }

  set hass(hass) {
    this._hass = hass;
    if (!this.shadowRoot?.querySelector(".home24")) this.renderShell();
    this.updateValues();
  }

  getCardSize() { return 12; }
  getGridOptions() { return { columns: 12, rows: 12, min_columns: 6, min_rows: 8 }; }

  handleClick = (event) => {
    const target = event.target.closest("[data-path]");
    if (!target) return;
    const path = `/tdb-dashboard/${target.dataset.path}`;
    history.pushState(null, "", path);
    window.dispatchEvent(new CustomEvent("location-changed"));
  };

  state(entity) {
    return this._hass?.states?.[entity];
  }

  number(key, fallback = 0) {
    const value = Number.parseFloat(this.state(this.entities[key])?.state);
    return Number.isFinite(value) ? value : fallback;
  }

  unit(key, fallback = "") {
    return this.state(this.entities[key])?.attributes?.unit_of_measurement || fallback;
  }

  format(key, digits = 0, fallbackUnit = "") {
    const value = this.number(key);
    const unit = this.unit(key, fallbackUnit);
    return `${new Intl.NumberFormat("fr-FR", {
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
    }).format(value)}${unit ? ` ${unit}` : ""}`;
  }

  weatherState() {
    const configured = this.config.weather_entity;
    if (configured && configured !== "auto") return this.state(configured);
    return Object.values(this._hass?.states || {}).find((item) => item.entity_id.startsWith("weather."));
  }

  scene() {
    const condition = this.weatherState()?.state || "";
    const hour = new Date().getHours();
    const sunDown = this.state("sun.sun")?.state === "below_horizon";
    if (sunDown || hour < 6 || hour >= 22) return "night";
    if (["rainy", "pouring", "lightning", "lightning-rainy", "hail"].includes(condition)) return "rain";
    if (["cloudy", "fog", "partlycloudy", "snowy", "snowy-rainy"].includes(condition)) return "cloudy";
    if (hour < 8 || hour >= 18) return "sunset";
    return "day";
  }

  weatherLabel(condition) {
    const labels = {
      sunny: "Ensoleillé", clear: "Dégagé", "clear-night": "Nuit claire",
      cloudy: "Nuageux", partlycloudy: "Éclaircies", rainy: "Pluie",
      pouring: "Forte pluie", lightning: "Orage", "lightning-rainy": "Orage et pluie",
      fog: "Brouillard", snowy: "Neige", windy: "Venteux", exceptional: "Conditions inhabituelles",
    };
    return labels[condition] || "Conditions locales";
  }

  renderShell() {
    if (!this.shadowRoot) return;
    this.shadowRoot.innerHTML = `
      <style>${Home24Card.styles}</style>
      <main class="home24 scene-day">
        <div class="scene-image"></div><div class="scene-shade"></div><div class="weather-fx"></div>
        <header class="brand">
          <div class="brand-name">HOME24</div>
          <div class="brand-line">ÉNERGIE · AUTOMATISATION · SÉCURITÉ · CONFORT</div>
        </header>
        <section class="datetime panel-clear">
          <strong data-clock>--:--</strong><span data-day>--</span><small data-date>--</small>
        </section>
        <section class="weather panel-clear">
          <ha-icon icon="mdi:weather-partly-cloudy"></ha-icon>
          <div><strong data-temperature>-- °C</strong><span data-condition>--</span><small data-wind>--</small></div>
        </section>
        <nav class="nav">${HOME24_NAV.map(([name, sub, icon, path], index) => `
          <button data-path="${path}" class="nav-item ${index === 0 ? "active" : ""}">
            <ha-icon icon="${icon}"></ha-icon><span><strong>${name}</strong><small>${sub}</small></span>
          </button>`).join("")}</nav>
        <section class="hero">
          <div class="sun-track"><span>Lever</span><i></i><span>Maintenant</span><i></i><span>Coucher</span></div>
          <div class="flow-grid">
            <article class="flow-card grid"><ha-icon icon="mdi:transmission-tower"></ha-icon><span>Réseau</span><strong data-grid>-- W</strong></article>
            <article class="flow-card solar"><ha-icon icon="mdi:solar-panel-large"></ha-icon><span>Solaire</span><strong data-solar>-- W</strong></article>
            <article class="flow-card home"><ha-icon icon="mdi:home-lightning-bolt"></ha-icon><span>Maison</span><strong data-home>-- W</strong></article>
          </div>
          <div class="energy-bars">
            <div><span>PV</span><b><i data-pv-bar></i></b><strong data-pv-percent>0%</strong></div>
            <div><span>Charge</span><b><i data-load-bar></i></b><strong data-load-percent>0%</strong></div>
          </div>
        </section>
        <aside class="battery glass">
          <div class="mode"><span>MODE BATTERIE</span><strong data-battery-mode>--</strong></div>
          <div class="battery-visual"><div class="battery-cap"></div><div class="battery-body"><div class="battery-fill" data-battery-fill></div><strong data-soc-big>--%</strong></div></div>
          <div class="battery-data">
            <span>Tension</span><strong data-voltage>-- V</strong>
            <span>Puissance</span><strong data-battery-power>-- W</strong>
            <span>État de charge</span><strong data-soc>-- %</strong>
            <span>Capacité restante</span><strong data-capacity>-- Ah</strong>
          </div>
        </aside>
        <section class="production glass">
          <header><span>PRODUCTION DU JOUR</span><strong data-solar-today>-- kWh</strong></header>
          <div class="spark"><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i></div>
          <div class="stats"><span>Production instantanée<strong data-solar-2>--</strong></span><span>Pic du jour<strong data-solar-peak>--</strong></span></div>
        </section>
        <section class="summary glass">
          <article><ha-icon icon="mdi:home-lightning-bolt"></ha-icon><span>Charge maison</span><strong data-home-2>--</strong></article>
          <article><ha-icon icon="mdi:transmission-tower"></ha-icon><span>Échange réseau</span><strong data-grid-2>--</strong></article>
          <article><ha-icon icon="mdi:battery-charging"></ha-icon><span>Flux batterie</span><strong data-battery-power-2>--</strong></article>
          <article><ha-icon icon="mdi:lightbulb-group"></ha-icon><span>Lumières actives</span><strong data-lights>--</strong></article>
        </section>
        <footer class="quick glass">
          ${[
            ["Caméras", "mdi:cctv", "securite"], ["Éclairage", "mdi:lightbulb-group", "eclairage"],
            ["Climat", "mdi:thermometer", "climat"], ["Batteries", "mdi:battery-heart", "batterie"],
            ["Énergie", "mdi:solar-power-variant", "energie"], ["Système", "mdi:cog", "systeme"],
          ].map(([name, icon, path]) => `<button data-path="${path}"><ha-icon icon="${icon}"></ha-icon><span>${name}</span></button>`).join("")}
        </footer>
      </main>`;
  }

  setText(selector, text) {
    const node = this.shadowRoot?.querySelector(selector);
    if (node) node.textContent = text;
  }

  updateClock() {
    const now = new Date();
    this.setText("[data-clock]", new Intl.DateTimeFormat("fr-FR", { hour: "2-digit", minute: "2-digit" }).format(now));
    this.setText("[data-day]", new Intl.DateTimeFormat("fr-FR", { weekday: "long" }).format(now));
    this.setText("[data-date]", new Intl.DateTimeFormat("fr-FR", { day: "2-digit", month: "long", year: "numeric" }).format(now));
  }

  updateValues() {
    const weather = this.weatherState();
    const scene = this.scene();
    const root = this.shadowRoot.querySelector(".home24");
    root.className = `home24 scene-${scene}`;
    const cameraPicture = this.config.background_camera
      ? this.state(this.config.background_camera)?.attributes?.entity_picture
      : null;
    const url = cameraPicture || this.backgrounds[scene];
    root.style.setProperty("--scene-image", url ? `url('${url}')` : "none");
    this.setText("[data-temperature]", this.format("outdoor_temperature", 1, "°C"));
    this.setText("[data-condition]", this.weatherLabel(weather?.state));
    this.setText("[data-wind]", `Vent ${this.format("wind", 1, "km/h")} · Humidité ${this.format("humidity", 0, "%")}`);
    this.setText("[data-grid]", this.format("grid_power", 0, "W"));
    this.setText("[data-grid-2]", this.format("grid_power", 0, "W"));
    this.setText("[data-solar]", this.format("solar_power", 0, "W"));
    this.setText("[data-solar-2]", this.format("solar_power", 0, "W"));
    this.setText("[data-home]", this.format("house_power", 0, "W"));
    this.setText("[data-home-2]", this.format("house_power", 0, "W"));
    this.setText("[data-solar-today]", this.format("solar_today", 0, "Wh"));
    this.setText("[data-solar-peak]", this.format("solar_peak", 0, "W"));
    this.setText("[data-voltage]", this.format("battery_voltage", 2, "V"));
    this.setText("[data-battery-power]", this.format("battery_power", 0, "W"));
    this.setText("[data-battery-power-2]", this.format("battery_power", 0, "W"));
    this.setText("[data-capacity]", this.format("battery_capacity", 0, "Ah"));
    const soc = Math.max(0, Math.min(100, this.number("battery_soc")));
    const batteryPower = this.number("battery_power");
    const solar = Math.max(0, this.number("solar_power"));
    const load = Math.max(0, this.number("house_power"));
    this.setText("[data-soc]", `${Math.round(soc)} %`);
    this.setText("[data-soc-big]", `${Math.round(soc)}%`);
    this.setText("[data-battery-mode]", batteryPower > 40 ? "CHARGE" : batteryPower < -40 ? "DÉCHARGE" : "VEILLE");
    this.shadowRoot.querySelector("[data-battery-fill]").style.height = `${soc}%`;
    const pvPercent = Math.min(100, solar / 40);
    const loadPercent = Math.min(100, load / 40);
    this.shadowRoot.querySelector("[data-pv-bar]").style.width = `${pvPercent}%`;
    this.shadowRoot.querySelector("[data-load-bar]").style.width = `${loadPercent}%`;
    this.setText("[data-pv-percent]", `${Math.round(pvPercent)}%`);
    this.setText("[data-load-percent]", `${Math.round(loadPercent)}%`);
    const lights = Object.values(this._hass?.states || {}).filter((item) => item.entity_id.startsWith("light.") && item.state === "on").length;
    this.setText("[data-lights]", String(lights));
  }
}

Home24Card.styles = `
  :host{display:block;min-height:100vh;color:#f8fbff;font-family:Inter,Roboto,Arial,sans-serif;letter-spacing:0}
  *{box-sizing:border-box}button{font:inherit;letter-spacing:0}
  .home24{--cyan:#2fd5ff;--blue:#338bff;--green:#8be04e;--amber:#ffc54a;position:relative;isolation:isolate;min-height:calc(100vh - 48px);padding:18px;display:grid;grid-template-columns:250px minmax(460px,1fr) 310px;grid-template-rows:auto 1fr auto auto;grid-template-areas:"datetime brand weather" "nav hero battery" "nav summary production" "nav quick production";gap:12px;overflow:hidden;background:#06152d}
  .scene-image,.scene-shade,.weather-fx{position:absolute;inset:0;z-index:-3;pointer-events:none}.scene-image{background-image:var(--scene-image);background-size:cover;background-position:center;transition:filter .8s ease,opacity .8s ease}.scene-shade{z-index:-2;background:linear-gradient(90deg,rgba(2,12,31,.88) 0%,rgba(5,21,51,.34) 32%,rgba(5,17,43,.24) 65%,rgba(2,10,28,.88) 100%),linear-gradient(0deg,rgba(2,10,28,.74),transparent 50%)}
  .scene-night .scene-image{filter:brightness(.47) saturate(.85) hue-rotate(8deg)}.scene-sunset .scene-image{filter:brightness(.78) saturate(1.2) sepia(.18)}.scene-cloudy .scene-image{filter:brightness(.68) saturate(.65)}.scene-rain .scene-image{filter:brightness(.48) saturate(.62) contrast(1.08)}
  .scene-rain .weather-fx{z-index:-1;opacity:.22;background-image:repeating-linear-gradient(105deg,transparent 0 18px,rgba(190,231,255,.7) 19px 20px,transparent 21px 34px);animation:rain .8s linear infinite}@keyframes rain{to{transform:translate(-24px,38px)}}
  .glass,.nav-item,.flow-card{border:1px solid rgba(141,202,255,.25);border-radius:8px;background:linear-gradient(145deg,rgba(14,55,105,.78),rgba(5,24,57,.88));box-shadow:inset 0 1px rgba(255,255,255,.08),0 8px 22px rgba(0,6,20,.24);backdrop-filter:blur(10px)}
  .brand{grid-area:brand;text-align:center;align-self:start}.brand-name{font-size:48px;font-weight:800;line-height:1;letter-spacing:8px;text-shadow:0 0 18px rgba(121,200,255,.65)}.brand-line{margin-top:7px;font-size:11px;letter-spacing:4px;color:#bcd8f7}
  .datetime{grid-area:datetime;display:grid;align-content:center}.datetime strong{font-size:38px;line-height:1}.datetime span{text-transform:capitalize;font-weight:700;margin-top:5px}.datetime small{color:#9eb8d8;margin-top:3px}.weather{grid-area:weather;display:flex;align-items:center;gap:12px}.weather ha-icon{--mdc-icon-size:44px;color:var(--amber);filter:drop-shadow(0 0 10px rgba(255,197,74,.5))}.weather div{display:grid}.weather strong{font-size:24px}.weather span{font-weight:700}.weather small{color:#b7cbe3;margin-top:4px}
  .nav{grid-area:nav;display:grid;gap:7px;align-content:start}.nav-item{min-height:66px;border-color:rgba(135,202,255,.24);color:#fff;display:flex;align-items:center;gap:13px;padding:10px 14px;text-align:left;cursor:pointer;transition:transform .16s ease,border-color .16s ease,background .16s ease}.nav-item:hover{transform:translateX(3px);border-color:var(--cyan)}.nav-item.active{background:linear-gradient(145deg,rgba(34,111,190,.84),rgba(8,42,89,.9));border-color:rgba(84,199,255,.62)}.nav-item ha-icon{--mdc-icon-size:29px;color:var(--cyan)}.nav-item:nth-child(2) ha-icon{color:var(--amber)}.nav-item:nth-child(3) ha-icon{color:var(--green)}.nav-item span{display:grid}.nav-item strong{text-transform:uppercase;font-size:14px}.nav-item small{font-size:11px;color:#a9c1de;margin-top:2px}
  .hero{grid-area:hero;min-height:420px;display:grid;align-content:space-between;padding:12px 18px}.sun-track{display:grid;grid-template-columns:auto 1fr auto 1fr auto;align-items:center;gap:8px;font-size:10px;color:#c4d8ec}.sun-track i{height:1px;background:rgba(161,217,255,.45)}.flow-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;align-items:end}.flow-card{min-height:108px;padding:14px;display:grid;place-items:center;text-align:center}.flow-card ha-icon{--mdc-icon-size:35px;color:var(--cyan)}.flow-card.solar ha-icon{color:var(--amber)}.flow-card.home ha-icon{color:var(--green)}.flow-card span{font-size:11px;text-transform:uppercase;color:#b8cee7}.flow-card strong{font-size:20px}.energy-bars{display:grid;grid-template-columns:1fr 1fr;gap:16px}.energy-bars>div{display:grid;grid-template-columns:50px 1fr 42px;align-items:center;gap:8px;padding:9px 13px;border:1px solid rgba(141,202,255,.24);border-radius:999px;background:rgba(5,28,63,.75)}.energy-bars span,.energy-bars strong{font-size:12px}.energy-bars b{height:12px;border-radius:3px;background:rgba(150,190,225,.2);overflow:hidden}.energy-bars i{display:block;height:100%;background:linear-gradient(90deg,var(--cyan),var(--green));border-radius:3px}
  .battery{grid-area:battery;padding:14px;display:grid;grid-template-columns:120px 1fr;grid-template-rows:auto 1fr;gap:10px}.mode{grid-column:1/-1;display:grid}.mode span,.production header span{font-size:10px;color:#aec7e1}.mode strong{color:var(--green);font-size:18px}.battery-visual{display:grid;place-items:center}.battery-cap{width:38px;height:8px;border-radius:4px 4px 0 0;background:#9fb3c8}.battery-body{position:relative;width:88px;height:180px;border:5px solid #9fb3c8;border-radius:8px;background:#061325;overflow:hidden;display:grid;place-items:center}.battery-fill{position:absolute;inset:auto 0 0;background:linear-gradient(0deg,#2cbaff,#5de2ff);transition:height .5s}.battery-body strong{z-index:1;font-size:27px;text-shadow:0 2px 6px #001}.battery-data{display:grid;align-content:center;grid-template-columns:1fr;gap:2px}.battery-data span{font-size:10px;color:#9fb7d1;margin-top:7px}.battery-data strong{font-size:16px}
  .production{grid-area:production;padding:14px;display:grid;align-content:start;gap:10px}.production header{display:flex;justify-content:space-between;align-items:center}.production header strong{color:var(--green)}.spark{height:64px;background:#030d1f;border-radius:6px;padding:12px;display:flex;align-items:end;gap:6px}.spark i{flex:1;height:38%;background:var(--cyan);border-radius:2px 2px 0 0;opacity:.7}.spark i:nth-child(2){height:55%}.spark i:nth-child(3){height:32%}.spark i:nth-child(4){height:78%}.spark i:nth-child(5){height:60%}.spark i:nth-child(6){height:92%;background:var(--green)}.spark i:nth-child(7){height:72%}.spark i:nth-child(8){height:45%}.stats{display:grid;grid-template-columns:1fr 1fr;gap:8px}.stats span{font-size:10px;color:#9fb7d1}.stats strong{display:block;margin-top:4px;color:var(--amber);font-size:15px}
  .summary{grid-area:summary;display:grid;grid-template-columns:repeat(4,1fr);overflow:hidden}.summary article{min-height:100px;padding:12px;display:grid;place-items:center;text-align:center;border-right:1px solid rgba(141,202,255,.18)}.summary article:last-child{border-right:0}.summary ha-icon{color:var(--cyan);--mdc-icon-size:24px}.summary span{font-size:10px;color:#a9bfd8;text-transform:uppercase}.summary strong{font-size:17px}.quick{grid-area:quick;display:grid;grid-template-columns:repeat(6,1fr);overflow:hidden}.quick button{min-height:76px;border:0;border-right:1px solid rgba(141,202,255,.18);background:transparent;color:#fff;display:grid;place-items:center;align-content:center;gap:6px;cursor:pointer}.quick button:last-child{border-right:0}.quick button:hover{background:rgba(47,213,255,.1)}.quick ha-icon{color:var(--cyan);--mdc-icon-size:24px}.quick span{font-size:11px}
  @media(max-width:1100px){.home24{grid-template-columns:210px 1fr;grid-template-rows:auto auto auto auto auto;grid-template-areas:"brand brand" "datetime weather" "nav hero" "battery production" "summary summary" "quick quick"}.nav-item{min-height:58px}.hero{min-height:400px}.battery{min-height:280px}}
  @media(max-width:700px){:host{min-height:auto}.home24{min-height:100vh;padding:10px;display:flex;flex-direction:column;gap:10px;background:#06152d}.scene-image{position:fixed}.scene-shade{position:fixed;background:linear-gradient(0deg,rgba(2,10,28,.92),rgba(4,19,46,.58))}.brand{order:1;padding-top:8px}.brand-name{font-size:34px;letter-spacing:5px}.brand-line{font-size:8px;letter-spacing:2px}.datetime{order:2;position:absolute;top:13px;left:13px}.datetime strong{font-size:22px}.datetime span,.datetime small{display:none}.weather{order:3;position:absolute;top:12px;right:12px}.weather ha-icon{--mdc-icon-size:27px}.weather strong{font-size:15px}.weather span{font-size:10px}.weather small{display:none}.nav{order:4;display:flex;overflow-x:auto;padding:2px 0 5px;scrollbar-width:none}.nav-item{flex:0 0 96px;min-height:66px;padding:7px;display:grid;place-items:center;text-align:center}.nav-item:hover{transform:none}.nav-item ha-icon{--mdc-icon-size:23px}.nav-item strong{font-size:10px}.nav-item small{display:none}.hero{order:5;min-height:330px;padding:8px 0}.flow-grid{gap:6px}.flow-card{min-height:88px;padding:8px}.flow-card strong{font-size:14px}.energy-bars{grid-template-columns:1fr;gap:6px}.battery{order:6;min-height:260px;grid-template-columns:110px 1fr}.production{order:7}.summary{order:8;grid-template-columns:1fr 1fr}.summary article:nth-child(2){border-right:0}.quick{order:9;grid-template-columns:repeat(3,1fr)}.quick button:nth-child(3){border-right:0}}
`;

if (!customElements.get("home24-card")) customElements.define("home24-card", Home24Card);
window.customCards = window.customCards || [];
window.customCards.push({ type: "home24-card", name: "HOME24", description: "Accueil immersif et responsive pour HOME24" });
