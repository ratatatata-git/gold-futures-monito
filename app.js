const state = {
  data: [],
  options: [],
  period: "1M",
  selected: null,
  optionsDate: null
};

const $ = id => document.getElementById(id);

const fmtInt = n => {
  if (n === null || n === undefined || !Number.isFinite(Number(n))) {
    return "—";
  }
  return Number(n).toLocaleString("en-US");
};

const fmtPrice = n => {
  if (n === null || n === undefined || !Number.isFinite(Number(n))) {
    return "—";
  }

  return Number(n).toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  });
};

const fmtDate = s => {
  if (!s) return "—";

  return new Date(s + "T00:00:00").toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric"
  });
};

async function init() {
  try {
    const [futuresResponse, optionsResponse] = await Promise.all([
      fetch(
        "data/cme-gc-history.json?v=4",
        { cache: "no-store" }
      ),
      fetch(
        "data/cme-gold-options-history.json?v=1",
        { cache: "no-store" }
      )
    ]);

    if (!futuresResponse.ok) {
      throw new Error(`Futures HTTP ${futuresResponse.status}`);
    }

    if (!optionsResponse.ok) {
      throw new Error(`Options HTTP ${optionsResponse.status}`);
    }

    const futuresJson = await futuresResponse.json();
    const optionsJson = await optionsResponse.json();

    const candles = Array.isArray(futuresJson.candles)
      ? futuresJson.candles
      : [];

    state.data = candles
      .filter(row => row.is_active === true)
      .filter(row =>
        row.date &&
        Number.isFinite(Number(row.settlement))
      )
      .sort((a, b) => a.date.localeCompare(b.date));

    state.options =
      Array.isArray(optionsJson.options)
        ? optionsJson.options
        : [];

    state.optionsDate =
      Array.isArray(optionsJson.dates) &&
      optionsJson.dates.length
        ? optionsJson.dates[
            optionsJson.dates.length - 1
          ]
        : null;

    if (!state.data.length) {
      throw new Error("No active-contract CME data found.");
    }

    state.selected =
      state.data[state.data.length - 1];

    updateLiveStatus();
    bind();
    render();
    renderOptions();

  } catch (error) {
    console.error(error);
    showError(error.message || "CME data could not be loaded.");
  }
}

function updateLiveStatus() {
  const status = document.querySelector(".status");

  if (status) {
    status.innerHTML =
      '<span class="dot"></span> CME PDF';
  }

  const footer = document.querySelector("footer");

  if (footer) {
    footer.textContent =
      "CME Daily Bulletin PG62 · Manual PDF import · Active Contract = highest GC volume";
  }
}

function showError(message) {
  const status = document.querySelector(".status");

  if (status) {
    status.textContent = "ERROR";
  }

  const settlement = $("settlement");

  if (settlement) {
    settlement.textContent = "—";
  }

  const settlementDate = $("settlementDate");

  if (settlementDate) {
    settlementDate.textContent = message;
  }
}

function bind() {
  document
    .querySelectorAll(".periods button")
    .forEach(btn => {
      btn.addEventListener("click", () => {

        document
          .querySelectorAll(".periods button")
          .forEach(b => b.classList.remove("active"));

        btn.classList.add("active");

        state.period = btn.dataset.period;
        state.selected = state.data[state.data.length - 1];

        render();
      });
    });

  [
    "priceChart",
    "volumeChart",
    "oiChart"
  ].forEach(id => {

    const canvas = $(id);

    if (!canvas) return;

    canvas.addEventListener("click", event => {
      selectFromChart(id, event);
    });
  });
}

function sliceData() {
  const counts = {
    "1M": 22,
    "3M": 66,
    "6M": 132,
    "1Y": 252
  };

  return state.data.slice(-counts[state.period]);
}

function render() {
  if (!state.data.length) return;

  const latest =
    state.data[state.data.length - 1];

  $("contract").textContent =
    latest.contract;

  const contractName =
    document.querySelector(".contract-name");

  if (contractName) {
    contractName.textContent =
      `Gold Futures · ${contractMonthName(latest.contract)}`;
  }

  $("settlement").textContent =
    "$" + fmtPrice(latest.settlement);

  $("settlementDate").textContent =
    fmtDate(latest.date);

  $("volume").textContent =
    fmtInt(latest.volume);

  $("oi").textContent =
    fmtInt(latest.open_interest);

  const oiChange =
    Number(latest.oi_change || 0);

  $("oiChange").textContent =
    (oiChange >= 0 ? "+" : "") +
    fmtInt(oiChange);

  const rows = sliceData();

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
    state.selected = latest;
  }

  showDetail(state.selected);
renderOptions();

function contractMonthName(contract) {
  if (!contract || contract.length < 5) {
    return contract || "Gold Futures";
  }

  const monthCode = contract.slice(0, 3);

  const year =
    2000 + Number(contract.slice(3));

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

  return `${names[monthCode] || monthCode} ${year}`;
}

function chartGeometry(canvas) {
  const dpr =
    Math.max(1, window.devicePixelRatio || 1);

  const rect =
    canvas.getBoundingClientRect();

  canvas.width =
    Math.round(rect.width * dpr);

  canvas.height =
    Math.round(rect.height * dpr);

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

function makeScale(min, max, y0, y1) {
  return value => {
    return y1 -
      ((value - min) /
      (max - min || 1)) *
      (y1 - y0);
  };
}

function baseChart(canvas, rows, min, max, formatter) {
  const g = chartGeometry(canvas);

  const {
    ctx,
    w,
    h,
    pad
  } = g;

  ctx.clearRect(0, 0, w, h);

  const y =
    makeScale(
      min,
      max,
      pad.t,
      h - pad.b
    );

  const x = index => {
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

  ctx.strokeStyle = "#252b33";
  ctx.fillStyle = "#737e8c";
  ctx.lineWidth = 1;

  for (let j = 0; j < 4; j++) {

    const yy =
      pad.t +
      j *
      ((h - pad.t - pad.b) / 3);

    ctx.beginPath();
    ctx.moveTo(pad.l, yy);
    ctx.lineTo(w - pad.r, yy);
    ctx.stroke();

    const value =
      max -
      ((max - min) * j / 3);

    ctx.textAlign = "left";

    ctx.fillText(
      formatter(value),
      3,
      yy + 3
    );
  }

  const labelCount =
    Math.min(5, rows.length);

  const indexes = new Set();

  if (labelCount === 1) {
    indexes.add(0);
  } else {
    for (let j = 0; j < labelCount; j++) {
      indexes.add(
        Math.round(
          j *
          ((rows.length - 1) /
          (labelCount - 1))
        )
      );
    }
  }

  [...indexes]
    .sort((a, b) => a - b)
    .forEach(index => {

      const xx = x(index);

      if (index === 0) {
        ctx.textAlign = "left";
      } else if (index === rows.length - 1) {
        ctx.textAlign = "right";
      } else {
        ctx.textAlign = "center";
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

function drawCandles(canvas, rows) {
  if (!rows.length) return;

  const valid = rows.filter(row =>
    Number.isFinite(Number(row.high)) &&
    Number.isFinite(Number(row.low)) &&
    Number.isFinite(Number(row.open)) &&
    Number.isFinite(Number(row.close))
  );

  if (!valid.length) return;

  let min =
    Math.min(...valid.map(r => Number(r.low)));

  let max =
    Math.max(...valid.map(r => Number(r.high)));

  if (min === max) {
    min -= 1;
    max += 1;
  }

  const range = max - min;

  min -= range * 0.08;
  max += range * 0.08;

  const {
    g,
    x,
    y
  } = baseChart(
    canvas,
    valid,
    min,
    max,
    fmtPrice
  );

  const ctx = g.ctx;

  const slot =
    (g.w - g.pad.l - g.pad.r) /
    Math.max(1, valid.length);

  const bodyWidth =
    Math.max(
      5,
      Math.min(14, slot * 0.45)
    );

  valid.forEach((row, index) => {

    const open =
      Number(row.open);

    const high =
      Number(row.high);

    const low =
      Number(row.low);

    const close =
      Number(row.close);

    const xx = x(index);

    const yHigh = y(high);
    const yLow = y(low);
    const yOpen = y(open);
    const yClose = y(close);

    const up = close >= open;

    ctx.strokeStyle =
      up ? "#62d49a" : "#ef767a";

    ctx.fillStyle =
      up ? "#62d49a" : "#ef767a";

    ctx.lineWidth = 1.5;

    /* wick */
    ctx.beginPath();
    ctx.moveTo(xx, yHigh);
    ctx.lineTo(xx, yLow);
    ctx.stroke();

    /* body */
    let top =
      Math.min(yOpen, yClose);

    let bottom =
      Math.max(yOpen, yClose);

    /* Minimum visible body */
    if (bottom - top < 3) {
      const center =
        (top + bottom) / 2;

      top = center - 1.5;
      bottom = center + 1.5;
    }

    ctx.fillRect(
      xx - bodyWidth / 2,
      top,
      bodyWidth,
      bottom - top
    );
  });
}


/* =========================
   VOLUME
   ========================= */

function drawBars(canvas, rows, key) {
  const valid =
    rows.filter(row =>
      Number.isFinite(Number(row[key]))
    );

  if (!valid.length) return;

  const values =
    valid.map(row => Number(row[key]));

  let min = 0;
  let max = Math.max(...values);

  if (max === 0) max = 1;

  const {
    g,
    x,
    y
  } = baseChart(
    canvas,
    valid,
    min,
    max,
    value => fmtInt(Math.round(value))
  );

  const ctx = g.ctx;

  const slot =
    (g.w - g.pad.l - g.pad.r) /
    Math.max(1, valid.length);

  /* Narrow bars */
  const barWidth =
    Math.max(
      4,
      Math.min(12, slot * 0.35)
    );

  const bottom =
    g.h - g.pad.b;

  valid.forEach((row, index) => {

    const value =
      Number(row[key]);

    const yy =
      y(value);

    ctx.fillStyle =
      "#7f8b99";

    ctx.fillRect(
      x(index) - barWidth / 2,
      yy,
      barWidth,
      Math.max(2, bottom - yy)
    );
  });
}


/* =========================
   OPEN INTEREST
   ========================= */

function drawLine(canvas, rows, key) {
  const valid =
    rows.filter(row =>
      Number.isFinite(Number(row[key]))
    );

  if (!valid.length) return;

  let min =
    Math.min(...valid.map(r => Number(r[key])));

  let max =
    Math.max(...valid.map(r => Number(r[key])));

  if (min === max) {
    const padding =
      Math.max(Math.abs(min) * 0.01, 1);

    min -= padding;
    max += padding;
  }

  const {
    g,
    x,
    y
  } = baseChart(
    canvas,
    valid,
    min,
    max,
    value => fmtInt(Math.round(value))
  );

  const ctx = g.ctx;

  ctx.strokeStyle =
    "#d8b46a";

  ctx.lineWidth = 2;

  ctx.beginPath();

  valid.forEach((row, index) => {

    const xx = x(index);

    const yy =
      y(Number(row[key]));

    if (index === 0) {
      ctx.moveTo(xx, yy);
    } else {
      ctx.lineTo(xx, yy);
    }
  });

  ctx.stroke();

  const last =
    valid.length - 1;

  ctx.fillStyle =
    "#f4f6f8";

  ctx.beginPath();

  ctx.arc(
    x(last),
    y(Number(valid[last][key])),
    3.5,
    0,
    Math.PI * 2
  );

  ctx.fill();
}


/* =========================
   TAP
   ========================= */

function selectFromChart(id, event) {
  const rows = sliceData();

  if (!rows.length) return;

  const canvas = $(id);

  const rect =
    canvas.getBoundingClientRect();

  const px =
    event.clientX - rect.left;

  const left = 48;
  const right = 8;

  let index;

  if (rows.length === 1) {
    index = 0;
  } else {
    index =
      Math.round(
        ((px - left) /
        (rect.width - left - right)) *
        (rows.length - 1)
      );
  }

  if (
    index >= 0 &&
    index < rows.length
  ) {
    state.selected = rows[index];
    showDetail(rows[index]);
  }
}


/* =========================
   DETAIL
   ========================= */

function showDetail(d) {
  if (!d) return;

  const oiChange =
    Number(d.oi_change || 0);

  const values = {
    date: fmtDate(d.date),
    contract: d.contract || "—",
    open: fmtPrice(d.open),
    high: fmtPrice(d.high),
    low: fmtPrice(d.low),
    close: fmtPrice(d.close),
    settlement: "$" + fmtPrice(d.settlement),
    volume: fmtInt(d.volume),
    oi: fmtInt(d.open_interest),
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

function renderOptions() {
  const container = $("optionsStructure");

  if (!container) return;

  if (!state.options.length) {
    container.innerHTML = `
      <div class="options-empty">
        No CME PG64 options data.
      </div>
    `;
    return;
  }

  const dates =
    [...new Set(
      state.options
        .map(row => row.date)
        .filter(Boolean)
    )].sort();

  const latestDate =
    dates[dates.length - 1];

  const rows =
    state.options.filter(
      row => row.date === latestDate
    );

  const callRows =
    rows.filter(
      row => row.option_type === "CALL"
    );

  const putRows =
    rows.filter(
      row => row.option_type === "PUT"
    );

  const totalCallOI =
    callRows.reduce(
      (sum, row) =>
        sum + (Number(row.open_interest) || 0),
      0
    );

  const totalPutOI =
    putRows.reduce(
      (sum, row) =>
        sum + (Number(row.open_interest) || 0),
      0
    );

  const largestCall =
    [...callRows]
      .sort(
        (a, b) =>
          (Number(b.open_interest) || 0) -
          (Number(a.open_interest) || 0)
      )[0];

  const largestPut =
    [...putRows]
      .sort(
        (a, b) =>
          (Number(b.open_interest) || 0) -
          (Number(a.open_interest) || 0)
      )[0];

  container.innerHTML = `
    <div class="options-date">
      CME PG64 · ${fmtDate(latestDate)}
    </div>

    <div class="options-grid">

      <div class="option-stat">
        <span>Total Call OI</span>
        <b>${fmtInt(totalCallOI)}</b>
      </div>

      <div class="option-stat">
        <span>Total Put OI</span>
        <b>${fmtInt(totalPutOI)}</b>
      </div>

      <div class="option-stat">
        <span>Largest Call OI</span>
        <b>
          ${
            largestCall
              ? `${fmtPrice(largestCall.strike)} · ${fmtInt(largestCall.open_interest)}`
              : "—"
          }
        </b>
      </div>

      <div class="option-stat">
        <span>Largest Put OI</span>
        <b>
          ${
            largestPut
              ? `${fmtPrice(largestPut.strike)} · ${fmtInt(largestPut.open_interest)}`
              : "—"
          }
        </b>
      </div>

    </div>
  `;
}
window.addEventListener(
  "resize",
  () => render()
);

init();
