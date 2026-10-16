const state = {
  data: [],
  cot: [],
  cotMeta: null,
  fred: [],
  fredMeta: null,
  options: [],
  period: "1M",
  selected: null,
  optionsDate: null
};

const $ = id => document.getElementById(id);

const fmtInt = n => {
  if (
    n === null ||
    n === undefined ||
    !Number.isFinite(Number(n))
  ) {
    return "—";
  }

  return Number(n).toLocaleString("en-US");
};

const fmtPrice = n => {
  if (
    n === null ||
    n === undefined ||
    !Number.isFinite(Number(n))
  ) {
    return "—";
  }

  return Number(n).toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  });
};

const fmtDate = s => {
  if (!s) return "—";

  return new Date(s + "T00:00:00").toLocaleDateString(
    "en-US",
    {
      month: "short",
      day: "numeric",
      year: "numeric"
    }
  );
};


/* =========================
   INIT
   ========================= */

async function init() {

  /*
   * Futures and Options are loaded independently.
   * PG64 failure must never break PG62.
   */

  await initFutures();
  await initOptions();
  await initCOT();
  await initFRED();

  bind();
  render();
  renderOptions();
  renderCOT();
  renderFRED();
}


/* =========================
   FUTURES
   ========================= */

async function initFutures() {

  try {

    const response = await fetch(
      "data/cme-gc-history.json?v=4",
      {
        cache: "no-store"
      }
    );

    if (!response.ok) {
      throw new Error(
        `Futures HTTP ${response.status}`
      );
    }

    const json =
      await response.json();

    const candles =
      Array.isArray(json.candles)
        ? json.candles
        : [];

    state.data =
      candles
        .filter(row =>
          row.is_active === true
        )
        .filter(row =>
          row.date &&
          Number.isFinite(
            Number(row.settlement)
          )
        )
        .sort(
          (a, b) =>
            a.date.localeCompare(b.date)
        );

    if (!state.data.length) {
      throw new Error(
        "No active-contract CME data found."
      );
    }

    state.selected =
      state.data[state.data.length - 1];

    updateLiveStatus(json);

  } catch (error) {

    console.error(
      "Futures load error:",
      error
    );

    showFuturesError(
      error.message ||
      "CME Futures data could not be loaded."
    );
  }
}


/* =========================
   COT — DISAGGREGATED FUTURES ONLY
   ========================= */

async function initCOT() {
  try {
    const response = await fetch(
      "data/cot/gold-disaggregated-futures-only.json?v=1",
      { cache: "no-store" }
    );
    if (!response.ok) {
      throw new Error(`COT HTTP ${response.status}`);
    }

    const json = await response.json();
    if (!Array.isArray(json.records) || !json.records.length) {
      throw new Error("No COT history records found.");
    }

    state.cot = json.records
      .filter(row =>
        row.report_date_as_yyyy_mm_dd &&
        row.cftc_contract_market_code === "088691"
      )
      .sort((x, y) =>
        String(x.report_date_as_yyyy_mm_dd).localeCompare(
          String(y.report_date_as_yyyy_mm_dd)
        )
      );
    state.cotMeta = json;
  } catch (error) {
    console.warn("COT load unavailable:", error.message);
    state.cot = [];
    state.cotMeta = null;
  }
}

function cotNumber(value) {
  if (value === null || value === undefined || value === "") return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function renderCOT() {
  const panel = $("cotPanel");
  const chart = $("cotChart");
  const latestEl = $("cotLatestDate");
  const summary = $("cotSummary");
  const table = $("cotRows");

  if (!panel || !chart || !latestEl || !summary || !table) return;

  if (!Array.isArray(state.cot) || !state.cot.length) {
    latestEl.textContent = "History not loaded";
    summary.innerHTML =
      '<div class="cot-empty">COT history is not in this deployment yet. ' +
      'Run <code>python scripts/fetch_cot_gold.py</code> and add the generated history file ' +
      '<code>data/cot/gold-disaggregated-futures-only.json</code> to the deployment after reviewing data-publication terms.</div>';
    table.innerHTML = "";
    const ctx = chart.getContext("2d");
    ctx.clearRect(0, 0, chart.width, chart.height);
    return;
  }

  const rows = state.cot.filter(row =>
    cotNumber(row.m_money_positions_long_all) !== null &&
    cotNumber(row.m_money_positions_short_all) !== null
  );
  const latest = rows[rows.length - 1];
  if (!latest) {
    latestEl.textContent = "No managed-money values";
    summary.innerHTML = '<div class="cot-empty">Managed Money position fields are unavailable in the source rows.</div>';
    table.innerHTML = "";
    return;
  }

  const long = cotNumber(latest.m_money_positions_long_all);
  const short = cotNumber(latest.m_money_positions_short_all);
  const net = long - short;
  latestEl.textContent = "Report date: " + fmtDate(String(latest.report_date_as_yyyy_mm_dd).slice(0, 10));

  summary.innerHTML = [
    ["Managed Money Long", long],
    ["Managed Money Short", short],
    ["Net (Long − Short)", net]
  ].map(([label, value]) =>
    '<div class="cot-stat"><span>' + label + '</span><strong>' +
    fmtInt(value) + '</strong></div>'
  ).join("");

  const recent = rows.slice(-8).reverse();
  table.innerHTML = recent.map(row => {
    const l = cotNumber(row.m_money_positions_long_all);
    const s = cotNumber(row.m_money_positions_short_all);
    const n = l - s;
    return '<div class="cot-row"><span>' +
      fmtDate(String(row.report_date_as_yyyy_mm_dd).slice(0, 10)) +
      '</span><span>' + fmtInt(l) + '</span><span>' +
      fmtInt(s) + '</span><strong class="' + (n >= 0 ? "cot-positive" : "cot-negative") +
      '">' + (n > 0 ? "+" : "") + fmtInt(n) + '</strong></div>';
  }).join("");

  drawCOTChart(chart, rows.slice(-26));
}

function drawCOTChart(canvas, rows) {
  const rect = canvas.getBoundingClientRect();
  const dpr = Math.max(1, window.devicePixelRatio || 1);
  canvas.width = Math.max(1, Math.round(rect.width * dpr));
  canvas.height = Math.max(1, Math.round(rect.height * dpr));
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  const w = rect.width;
  const h = rect.height;
  ctx.clearRect(0, 0, w, h);

  const values = rows.map(row =>
    cotNumber(row.m_money_positions_long_all) -
    cotNumber(row.m_money_positions_short_all)
  ).filter(Number.isFinite);
  if (!values.length) return;

  const maxAbs = Math.max(1, ...values.map(Math.abs));
  const mid = Math.round(h / 2);
  const left = 5;
  const right = w - 5;
  const slot = (right - left) / values.length;
  ctx.strokeStyle = "#39414b";
  ctx.beginPath();
  ctx.moveTo(left, mid);
  ctx.lineTo(right, mid);
  ctx.stroke();

  values.forEach((value, i) => {
    const barH = Math.max(1, Math.abs(value) / maxAbs * (h / 2 - 8));
    const x = left + i * slot + slot * 0.15;
    ctx.fillStyle = value >= 0 ? "#62d49a" : "#ef767a";
    ctx.fillRect(x, value >= 0 ? mid - barH : mid, Math.max(2, slot * 0.7), barH);
  });
}


/* =========================
   FRED — MACRO CONTEXT
   ========================= */

async function initFRED() {
  try {
    const response = await fetch(
      "data/fred/gold-macro-context.json?v=1",
      { cache: "no-store" }
    );
    if (!response.ok) {
      throw new Error(`FRED HTTP ${response.status}`);
    }

    const json = await response.json();
    if (!Array.isArray(json.records) || !json.records.length) {
      throw new Error("No FRED macro context records found.");
    }

    state.fred = json.records
      .filter(row => row.observation_date && row.values && typeof row.values === "object")
      .sort((a, b) => String(a.observation_date).localeCompare(String(b.observation_date)));
    state.fredMeta = json;
  } catch (error) {
    console.warn("FRED macro context unavailable:", error.message);
    state.fred = [];
    state.fredMeta = null;
  }
}

function fredNumber(value) {
  if (value === null || value === undefined || value === "") return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function renderFRED() {
  const latestEl = $("fredLatestDate");
  const summary = $("fredSummary");
  const table = $("fredRows");
  if (!latestEl || !summary || !table) return;

  const series = [
    { id: "DFII10", label: "10Y Real Yield Proxy", unit: "%", digits: 2 },
    { id: "DGS10", label: "10Y Treasury Yield", unit: "%", digits: 2 },
    { id: "DTWEXBGS", label: "Broad USD Index", unit: "", digits: 2 }
  ];

  if (!Array.isArray(state.fred) || !state.fred.length) {
    latestEl.textContent = "History not loaded";
    summary.innerHTML =
      '<div class="cot-empty">FRED macro history is not in this deployment yet. ' +
      'Run <code>python scripts/fetch_fred_context.py</code> and review publication terms before deploying ' +
      '<code>data/fred/gold-macro-context.json</code>.</div>';
    table.innerHTML = "";
    return;
  }

  summary.innerHTML = series.map(item => {
    const validRows = state.fred.filter(row => fredNumber(row.values[item.id]) !== null);
    const latest = validRows[validRows.length - 1];
    const value = latest ? fredNumber(latest.values[item.id]) : null;
    const display = value === null ? "—" : value.toFixed(item.digits) + item.unit;
    const date = latest ? fmtDate(latest.observation_date) : "No observation";
    return '<div class="fred-stat"><span>' + item.label +
      '</span><strong>' + display + '</strong><small>' + date + '</small></div>';
  }).join("");

  latestEl.textContent = "Latest available observation dates · values may be revised by FRED";

  const recent = state.fred.slice(-8).reverse();
  table.innerHTML = recent.map(row => {
    const values = series.map(item => {
      const n = fredNumber(row.values[item.id]);
      return n === null ? "—" : n.toFixed(item.digits) + item.unit;
    });
    return '<div class="fred-row"><span>' + fmtDate(row.observation_date) +
      '</span><span>' + values[0] + '</span><span>' + values[1] +
      '</span><span>' + values[2] + '</span></div>';
  }).join("");
}


/* =========================
   OPTIONS
   ========================= */

async function initOptions() {

  try {

    const response = await fetch(
      "data/cme-gold-options-2026-09-21.json?v=1",
      {
        cache: "no-store"
      }
    );

    if (!response.ok) {
      throw new Error(
        `Options HTTP ${response.status}`
      );
    }

    const json =
      await response.json();

    state.options =
      Array.isArray(json.options)
        ? json.options
        : [];

    state.optionsDate =
      Array.isArray(json.dates) &&
      json.dates.length
        ? json.dates[
            json.dates.length - 1
          ]
        : null;

  } catch (error) {

    console.error(
      "Options load error:",
      error
    );

    /*
     * Important:
     * Options failure does NOT affect Futures.
     */

    state.options = [];
    state.optionsDate = null;
  }
}


/* =========================
   STATUS
   ========================= */

function updateLiveStatus(sourceMeta = {}) {

  const latestDate =
    state.selected && state.selected.date
      ? state.selected.date
      : sourceMeta.latest_date || null;

  const latestDateMs =
    latestDate
      ? new Date(latestDate + "T00:00:00").getTime()
      : NaN;

  const ageDays =
    Number.isFinite(latestDateMs)
      ? Math.floor(
          (Date.now() - latestDateMs) /
          86400000
        )
      : NaN;

  // Calendar-day threshold is a visible heuristic, not an exchange calendar.
  const isStale =
    Number.isFinite(ageDays) &&
    ageDays > 7;

  const processedAt =
    sourceMeta.updated_at
      ? new Date(sourceMeta.updated_at)
      : null;

  const processedAtLabel =
    processedAt && !Number.isNaN(processedAt.getTime())
      ? processedAt.toLocaleString("en-US", {
          dateStyle: "medium",
          timeStyle: "short"
        })
      : "unknown";

  const status =
    document.querySelector(".status");

  if (status) {
    status.classList.toggle("stale", isStale);
    status.innerHTML =
      '<span class="dot"></span> ' +
      (isStale ? "STALE DATA" : "CME PDF");
  }

  const freshness =
    $("dataFreshness");

  if (freshness) {
    freshness.classList.toggle("stale", isStale);
    freshness.textContent =
      (isStale ? "Data may be stale — " : "Data status — ") +
      "latest trading date: " + (latestDate || "unknown") +
      " · file processed: " + processedAtLabel +
      (isStale ? " · older than 7 calendar days" : "");
  }

  const footer =
    document.querySelector("footer");

  if (footer) {
    footer.textContent =
      "CME Daily Bulletin PG62 + PG64 · Manual PDF import · Stale warning uses a 7-calendar-day heuristic";
  }
}


function showFuturesError(message) {

  const status =
    document.querySelector(".status");

  if (status) {
    status.textContent = "ERROR";
    status.classList.add("stale");
  }

  const freshness =
    $("dataFreshness");

  if (freshness) {
    freshness.classList.add("stale");
    freshness.textContent =
      "Futures data unavailable — " + message;
  }

  const settlement =
    $("settlement");

  if (settlement) {
    settlement.textContent = "—";
  }

  const settlementDate =
    $("settlementDate");

  if (settlementDate) {
    settlementDate.textContent =
      message;
  }
}


/* =========================
   BIND
   ========================= */

function bind() {

  document
    .querySelectorAll(".periods button")
    .forEach(btn => {

      btn.addEventListener(
        "click",
        () => {

          document
            .querySelectorAll(
              ".periods button"
            )
            .forEach(b =>
              b.classList.remove(
                "active"
              )
            );

          btn.classList.add(
            "active"
          );

          state.period =
            btn.dataset.period;

          state.selected =
            state.data[
              state.data.length - 1
            ];

          render();

        }
      );

    });


  [
    "priceChart",
    "volumeChart",
    "oiChart"
  ].forEach(id => {

    const canvas = $(id);

    if (!canvas) return;

    canvas.addEventListener(
      "click",
      event => {
        selectFromChart(
          id,
          event
        );
      }
    );

  });
}


/* =========================
   DATA SLICE
   ========================= */

function sliceData() {

  const counts = {
    "1M": 22,
    "3M": 66,
    "6M": 132,
    "1Y": 252
  };

  return state.data.slice(
    -counts[state.period]
  );
}


/* =========================
   RENDER FUTURES
   ========================= */

function render() {

  if (!state.data.length) {
    return;
  }

  const latest =
    state.data[
      state.data.length - 1
    ];

  $("contract").textContent =
    latest.contract;

  const contractName =
    document.querySelector(
      ".contract-name"
    );

  if (contractName) {

    contractName.textContent =
      `Gold Futures · ${contractMonthName(
        latest.contract
      )}`;

  }

  $("settlement").textContent =
    "$" +
    fmtPrice(
      latest.settlement
    );

  $("settlementDate").textContent =
    fmtDate(
      latest.date
    );

  $("volume").textContent =
    fmtInt(
      latest.volume
    );

  $("oi").textContent =
    fmtInt(
      latest.open_interest
    );

  const oiChange =
    Number(
      latest.oi_change || 0
    );

  $("oiChange").textContent =
    (oiChange >= 0 ? "+" : "") +
    fmtInt(oiChange);


  const rows =
    sliceData();

  drawCandles(
    $("priceChart"),
    rows
  );

  drawBars(
    $("volumeChart"),
    rows,
    "volume"
  );

  drawLine(
    $("oiChart"),
    rows,
    "open_interest"
  );


  if (!state.selected) {
    state.selected =
      latest;
  }

  showDetail(
    state.selected
  );

  renderOptions();
  renderCOT();
  renderFRED();
}


/* =========================
   CONTRACT NAME
   ========================= */

function contractMonthName(
  contract
) {

  if (
    !contract ||
    contract.length < 5
  ) {
    return contract ||
      "Gold Futures";
  }

  const monthCode =
    contract.slice(0, 3);

  const year =
    2000 +
    Number(
      contract.slice(3)
    );

  const names = {
    JAN: "Jan",
    FEB: "Feb",
    MAR: "Mar",
    APR: "Apr",
    MAY: "May",
    JUN: "Jun",
    JUL: "Jul",
    AUG: "Aug",
    SEP: "Sep",
    OCT: "Oct",
    NOV: "Nov",
    DEC: "Dec"
  };

  return `${
    names[monthCode] ||
    monthCode
  } ${year}`;
}


/* =========================
   CHART GEOMETRY
   ========================= */

function chartGeometry(canvas) {

  const dpr =
    Math.max(
      1,
      window.devicePixelRatio || 1
    );

  const rect =
    canvas.getBoundingClientRect();

  canvas.width =
    Math.round(
      rect.width * dpr
    );

  canvas.height =
    Math.round(
      rect.height * dpr
    );

  const ctx =
    canvas.getContext("2d");

  ctx.setTransform(
    dpr,
    0,
    0,
    dpr,
    0,
    0
  );

  return {
    ctx,
    w: rect.width,
    h: rect.height,
    pad: {
      l: 48,
      r: 8,
      t: 8,
      b: 23
    }
  };
}


function makeScale(
  min,
  max,
  y0,
  y1
) {

  return value => {

    return y1 -
      (
        (value - min) /
        (max - min || 1)
      ) *
      (y1 - y0);

  };
}


function baseChart(
  canvas,
  rows,
  min,
  max,
  formatter
) {

  const g =
    chartGeometry(canvas);

  const {
    ctx,
    w,
    h,
    pad
  } = g;

  ctx.clearRect(
    0,
    0,
    w,
    h
  );

  const y =
    makeScale(
      min,
      max,
      pad.t,
      h - pad.b
    );


  const x = index => {

    /*
     * One-day chart:
     * put the data point at the left edge.
     */

    if (rows.length === 1) {
      return pad.l;
    }

    return pad.l +
      index *
      (
        (w - pad.l - pad.r) /
        (rows.length - 1)
      );

  };


  ctx.font =
    "10px -apple-system,BlinkMacSystemFont,sans-serif";

  ctx.strokeStyle =
    "#252b33";

  ctx.fillStyle =
    "#737e8c";

  ctx.lineWidth = 1;


  for (
    let j = 0;
    j < 4;
    j++
  ) {

    const yy =
      pad.t +
      j *
      (
        (h - pad.t - pad.b) /
        3
      );

    ctx.beginPath();

    ctx.moveTo(
      pad.l,
      yy
    );

    ctx.lineTo(
      w - pad.r,
      yy
    );

    ctx.stroke();


    const value =
      max -
      (
        (max - min) *
        j /
        3
      );

    ctx.textAlign =
      "left";

    ctx.fillText(
      formatter(value),
      3,
      yy + 3
    );

  }


  const labelCount =
    Math.min(
      5,
      rows.length
    );

  const indexes =
    new Set();


  if (labelCount === 1) {

    indexes.add(0);

  } else {

    for (
      let j = 0;
      j < labelCount;
      j++
    ) {

      indexes.add(
        Math.round(
          j *
          (
            (rows.length - 1) /
            (labelCount - 1)
          )
        )
      );

    }

  }


  [
    ...indexes
  ]
    .sort(
      (a, b) => a - b
    )
    .forEach(index => {

      const xx =
        x(index);

      if (index === 0) {

        ctx.textAlign =
          "left";

      } else if (
        index ===
        rows.length - 1
      ) {

        ctx.textAlign =
          "right";

      } else {

        ctx.textAlign =
          "center";

      }

      ctx.fillText(
        rows[index].date.slice(5),
        xx,
        h - 5
      );

    });


  return {
    g,
    x,
    y,
    min,
    max
  };
}


/* =========================
   CANDLESTICK
   ========================= */

function drawCandles(
  canvas,
  rows
) {

  if (!rows.length) return;

  const valid =
    rows.filter(row =>
      Number.isFinite(
        Number(row.high)
      ) &&
      Number.isFinite(
        Number(row.low)
      ) &&
      Number.isFinite(
        Number(row.open)
      ) &&
      Number.isFinite(
        Number(row.close)
      )
    );

  if (!valid.length) return;


  let min =
    Math.min(
      ...valid.map(
        r => Number(r.low)
      )
    );

  let max =
    Math.max(
      ...valid.map(
        r => Number(r.high)
      )
    );


  if (min === max) {

    min -= 1;
    max += 1;

  }


  const range =
    max - min;

  min -=
    range * 0.08;

  max +=
    range * 0.08;


  const {
    g,
    x,
    y
  } =
    baseChart(
      canvas,
      valid,
      min,
      max,
      fmtPrice
    );


  const ctx =
    g.ctx;


  const slot =
    (
      g.w -
      g.pad.l -
      g.pad.r
    ) /
    Math.max(
      1,
      valid.length
    );


  const bodyWidth =
    Math.max(
      5,
      Math.min(
        14,
        slot * 0.45
      )
    );


  valid.forEach(
    (row, index) => {

      const open =
        Number(row.open);

      const high =
        Number(row.high);

      const low =
        Number(row.low);

      const close =
        Number(row.close);

      const xx =
        x(index);

      const yHigh =
        y(high);

      const yLow =
        y(low);

      const yOpen =
        y(open);

      const yClose =
        y(close);

      const up =
        close >= open;


      ctx.strokeStyle =
        up
          ? "#62d49a"
          : "#ef767a";

      ctx.fillStyle =
        up
          ? "#62d49a"
          : "#ef767a";

      ctx.lineWidth =
        1.5;


      /* wick */

      ctx.beginPath();

      ctx.moveTo(
        xx,
        yHigh
      );

      ctx.lineTo(
        xx,
        yLow
      );

      ctx.stroke();


      /* body */

      let top =
        Math.min(
          yOpen,
          yClose
        );

      let bottom =
        Math.max(
          yOpen,
          yClose
        );


      if (
        bottom - top < 3
      ) {

        const center =
          (top + bottom) /
          2;

        top =
          center - 1.5;

        bottom =
          center + 1.5;

      }


      ctx.fillRect(
        xx -
        bodyWidth / 2,
        top,
        bodyWidth,
        bottom - top
      );

    }
  );
}


/* =========================
   VOLUME
   ========================= */

function drawBars(
  canvas,
  rows,
  key
) {

  const valid =
    rows.filter(row =>
      Number.isFinite(
        Number(row[key])
      )
    );

  if (!valid.length) return;


  const values =
    valid.map(
      row => Number(row[key])
    );


  let min = 0;

  let max =
    Math.max(...values);


  if (max === 0) {
    max = 1;
  }


  const {
    g,
    x,
    y
  } =
    baseChart(
      canvas,
      valid,
      min,
      max,
      value =>
        fmtInt(
          Math.round(value)
        )
    );


  const ctx =
    g.ctx;


  const slot =
    (
      g.w -
      g.pad.l -
      g.pad.r
    ) /
    Math.max(
      1,
      valid.length
    );


  const barWidth =
    Math.max(
      4,
      Math.min(
        12,
        slot * 0.35
      )
    );


  const bottom =
    g.h -
    g.pad.b;


  valid.forEach(
    (row, index) => {

      const value =
        Number(row[key]);

      const yy =
        y(value);

      ctx.fillStyle =
        "#7f8b99";

      ctx.fillRect(
        x(index) -
        barWidth / 2,
        yy,
        barWidth,
        Math.max(
          2,
          bottom - yy
        )
      );

    }
  );
}


/* =========================
   OPEN INTEREST
   ========================= */

function drawLine(
  canvas,
  rows,
  key
) {

  const valid =
    rows.filter(row =>
      Number.isFinite(
        Number(row[key])
      )
    );

  if (!valid.length) return;


  let min =
    Math.min(
      ...valid.map(
        r => Number(r[key])
      )
    );

  let max =
    Math.max(
      ...valid.map(
        r => Number(r[key])
      )
    );


  if (min === max) {

    const padding =
      Math.max(
        Math.abs(min) * 0.01,
        1
      );

    min -= padding;
    max += padding;

  }


  const {
    g,
    x,
    y
  } =
    baseChart(
      canvas,
      valid,
      min,
      max,
      value =>
        fmtInt(
          Math.round(value)
        )
    );


  const ctx =
    g.ctx;


  ctx.strokeStyle =
    "#d8b46a";

  ctx.lineWidth =
    2;

  ctx.beginPath();


  valid.forEach(
    (row, index) => {

      const xx =
        x(index);

      const yy =
        y(
          Number(row[key])
        );

      if (index === 0) {

        ctx.moveTo(
          xx,
          yy
        );

      } else {

        ctx.lineTo(
          xx,
          yy
        );

      }

    }
  );


  ctx.stroke();


  const last =
    valid.length - 1;


  ctx.fillStyle =
    "#f4f6f8";

  ctx.beginPath();

  ctx.arc(
    x(last),
    y(
      Number(
        valid[last][key]
      )
    ),
    3.5,
    0,
    Math.PI * 2
  );

  ctx.fill();
}


/* =========================
   TAP
   ========================= */

function selectFromChart(
  id,
  event
) {

  const rows =
    sliceData();

  if (!rows.length) return;


  const canvas =
    $(id);

  const rect =
    canvas.getBoundingClientRect();


  const px =
    event.clientX -
    rect.left;


  const left = 48;
  const right = 8;


  let index;


  if (rows.length === 1) {

    index = 0;

  } else {

    index =
      Math.round(
        (
          (px - left) /
          (
            rect.width -
            left -
            right
          )
        ) *
        (rows.length - 1)
      );

  }


  if (
    index >= 0 &&
    index < rows.length
  ) {

    state.selected =
      rows[index];

    showDetail(
      rows[index]
    );

  }
}


/* =========================
   DETAIL
   ========================= */

function showDetail(d) {

  if (!d) return;


  const oiChange =
    Number(
      d.oi_change || 0
    );


  const values = {

    date:
      fmtDate(d.date),

    contract:
      d.contract || "—",

    open:
      fmtPrice(d.open),

    high:
      fmtPrice(d.high),

    low:
      fmtPrice(d.low),

    close:
      fmtPrice(d.close),

    settlement:
      "$" +
      fmtPrice(d.settlement),

    volume:
      fmtInt(d.volume),

    oi:
      fmtInt(d.open_interest),

    oiChange:
      (oiChange >= 0 ? "+" : "") +
      fmtInt(oiChange)

  };


  const grid =
    document.querySelector(
      "#detail .detail-grid"
    );

  if (!grid) return;


  grid.innerHTML = `

    <span>Date</span>
    <b>${values.date}</b>

    <span>Contract</span>
    <b>${values.contract}</b>

    <span>Open</span>
    <b>${values.open}</b>

    <span>High</span>
    <b>${values.high}</b>

    <span>Low</span>
    <b>${values.low}</b>

    <span>Close</span>
    <b>${values.close}</b>

    <span>Settlement</span>
    <b>${values.settlement}</b>

    <span>Volume</span>
    <b>${values.volume}</b>

    <span>Open Interest</span>
    <b>${values.oi}</b>

    <span>OI Change</span>
    <b>${values.oiChange}</b>

  `;
}


/* =========================
   OPTIONS
   ========================= */

function renderOptions() {

  const container =
    $("optionsStructure");

  if (!container) return;


  if (!state.options.length) {

    container.innerHTML = `
      <div class="options-empty">
        CME PG64 data unavailable.
      </div>
    `;

    return;
  }


  const dates =
    [
      ...new Set(
        state.options
          .map(
            row => row.date
          )
          .filter(Boolean)
      )
    ].sort();


  const latestDate =
    dates[
      dates.length - 1
    ];


  const rows =
    state.options.filter(
      row =>
        row.date ===
        latestDate
    );


  const callRows =
    rows.filter(
      row =>
        row.option_type ===
        "CALL"
    );


  const putRows =
    rows.filter(
      row =>
        row.option_type ===
        "PUT"
    );


  const totalCallOI =
    callRows.reduce(
      (sum, row) =>
        sum +
        (
          Number(
            row.open_interest
          ) || 0
        ),
      0
    );


  const totalPutOI =
    putRows.reduce(
      (sum, row) =>
        sum +
        (
          Number(
            row.open_interest
          ) || 0
        ),
      0
    );


  const largestCall =
    [
      ...callRows
    ].sort(
      (a, b) =>
        (
          Number(
            b.open_interest
          ) || 0
        ) -
        (
          Number(
            a.open_interest
          ) || 0
        )
    )[0];


  const largestPut =
    [
      ...putRows
    ].sort(
      (a, b) =>
        (
          Number(
            b.open_interest
          ) || 0
        ) -
        (
          Number(
            a.open_interest
          ) || 0
        )
    )[0];


  container.innerHTML = `

    <div class="options-date">
      CME PG64 · ${fmtDate(
        latestDate
      )}
    </div>

    <div class="options-grid">

      <div class="option-stat">

        <span>Total Call OI</span>

        <b>
          ${fmtInt(
            totalCallOI
          )}
        </b>

      </div>


      <div class="option-stat">

        <span>Total Put OI</span>

        <b>
          ${fmtInt(
            totalPutOI
          )}
        </b>

      </div>


      <div class="option-stat">

        <span>Largest Call OI</span>

        <b>
          ${
            largestCall
              ? `${fmtPrice(
                  largestCall.strike
                )} · ${fmtInt(
                  largestCall.open_interest
                )}`
              : "—"
          }
        </b>

      </div>


      <div class="option-stat">

        <span>Largest Put OI</span>

        <b>
          ${
            largestPut
              ? `${fmtPrice(
                  largestPut.strike
                )} · ${fmtInt(
                  largestPut.open_interest
                )}`
              : "—"
          }
        </b>

      </div>

    </div>
  `;
}


/* =========================
   RESIZE
   ========================= */

window.addEventListener(
  "resize",
  () => render()
);


/* =========================
   START
   ========================= */

init();
