const state = {
  data: [],
  period: "1M",
  selected: null
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

    const response = await fetch(
      "data/cme-gc-history.json",
      { cache: "no-store" }
    );

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const json = await response.json();

    /*
     * 各日付の Active Contract だけをチャートに使用。
     */
    state.data = (json.candles || [])
      .filter(row => row.is_active === true)
      .filter(row => row.date)
      .sort((a, b) =>
        a.date.localeCompare(b.date)
      );

    if (!state.data.length) {
      throw new Error("No active-contract CME data found.");
    }

    const status = document.querySelector(".status");

    if (status) {
      status.innerHTML =
        '<span class="dot"></span> CME PDF';
    }

    bind();
    render();

    if ("serviceWorker" in navigator) {
      navigator.serviceWorker
        .register("sw.js")
        .catch(() => {});
    }

  } catch (error) {
    console.error(error);

    const status =
      document.querySelector(".status");

    if (status) {
      status.textContent = "ERROR";
    }
  }
}


function bind() {

  document
    .querySelectorAll(".periods button")
    .forEach(btn => {

      btn.addEventListener("click", () => {

        document
          .querySelectorAll(".periods button")
          .forEach(b =>
            b.classList.remove("active")
          );

        btn.classList.add("active");

        state.period =
          btn.dataset.period;

        state.selected = null;

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

    canvas.addEventListener(
      "click",
      e => selectFromChart(id, e)
    );
  });
}


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
      `Gold Futures · ${contractMonthName(
        latest.contract
      )}`;
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


  /*
   * ① ローソク足
   */
  drawCandles(
    $("priceChart"),
    rows
  );


  /*
   * ② Volume
   */
  drawBars(
    $("volumeChart"),
    rows,
    "volume"
  );


  /*
   * ③ Open Interest
   */
  drawLine(
    $("oiChart"),
    rows,
    "open_interest"
  );


  if (state.selected) {
    showDetail(state.selected);
  }
}


function contractMonthName(contract) {

  if (!contract || contract.length < 5) {
    return contract || "Gold Futures";
  }

  const month =
    contract.slice(0, 3);

  const year =
    2000 + Number(
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

  return `${names[month] || month} ${year}`;
}


/*
 * ---------------------------------------------------------
 * Chart geometry
 * ---------------------------------------------------------
 */

function chartGeometry(canvas) {

  const dpr =
    Math.max(
      1,
      window.devicePixelRatio || 1
    );

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
      t: 6,
      b: 22
    }
  };
}


function drawGrid(
  ctx,
  w,
  h,
  pad,
  min,
  max
) {

  ctx.font =
    "10px -apple-system,BlinkMacSystemFont,sans-serif";

  ctx.strokeStyle =
    "#252b33";

  ctx.fillStyle =
    "#737e8c";

  ctx.lineWidth = 1;


  for (let j = 0; j < 4; j++) {

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

    ctx.textAlign = "left";

    ctx.fillText(
      fmtPrice(value),
      3,
      yy + 3
    );
  }
}


function drawDateLabels(
  ctx,
  rows,
  x,
  w,
  h,
  pad
) {

  if (!rows.length) return;

  const count =
    Math.min(5, rows.length);

  const indexes = [];

  if (count === 1) {

    indexes.push(0);

  } else {

    for (
      let i = 0;
      i < count;
      i++
    ) {

      indexes.push(
        Math.round(
          i *
          (
            (rows.length - 1) /
            (count - 1)
          )
        )
      );
    }
  }


  ctx.font =
    "10px -apple-system,BlinkMacSystemFont,sans-serif";

  ctx.fillStyle =
    "#737e8c";


  indexes.forEach(index => {

    const xx = x(index);

    if (index === 0) {
      ctx.textAlign = "left";
    } else if (
      index === rows.length - 1
    ) {
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
}


/*
 * ---------------------------------------------------------
 * Candlestick
 * ---------------------------------------------------------
 */

function drawCandles(
  canvas,
  rows
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


  if (!rows.length) return;


  const valid =
    rows.filter(row =>
      Number.isFinite(Number(row.high)) &&
      Number.isFinite(Number(row.low)) &&
      Number.isFinite(Number(row.open)) &&
      Number.isFinite(Number(row.close))
    );


  if (!valid.length) return;


  let min =
    Math.min(
      ...valid.map(r =>
        Number(r.low)
      )
    );

  let max =
    Math.max(
      ...valid.map(r =>
        Number(r.high)
      )
    );


  /*
   * 少し上下に余白を作る。
   */
  const range =
    Math.max(
      1,
      max - min
    );

  min -= range * 0.08;
  max += range * 0.08;


  const y = value =>
    h -
    pad.b -
    (
      (value - min) /
      (max - min)
    ) *
    (
      h - pad.t - pad.b
    );


  const x = index =>
    pad.l +
    index *
    (
      (w - pad.l - pad.r) /
      Math.max(
        1,
        valid.length - 1
      )
    );


  drawGrid(
    ctx,
    w,
    h,
    pad,
    min,
    max
  );


  drawDateLabels(
    ctx,
    valid,
    x,
    w,
    h,
    pad
  );


  /*
   * 1日だけの場合でも巨大なローソクにならないよう、
   * 本体幅に上限を設定。
   */
  const slot =
    (
      w - pad.l - pad.r
    ) /
    Math.max(
      1,
      valid.length
    );

  const candleWidth =
    Math.max(
      5,
      Math.min(
        14,
        slot * 0.42
      )
    );


  valid.forEach(
    (row, index) => {

      const xx =
        x(index);

      const open =
        Number(row.open);

      const close =
        Number(row.close);

      const high =
        Number(row.high);

      const low =
        Number(row.low);


      const up =
        close >= open;


      /*
       * Wick
       */
      ctx.strokeStyle =
        up
          ? "#62d49a"
          : "#ef767a";

      ctx.lineWidth = 1.2;

      ctx.beginPath();

      ctx.moveTo(
        xx,
        y(high)
      );

      ctx.lineTo(
        xx,
        y(low)
      );

      ctx.stroke();


      /*
       * Body
       */
      const top =
        Math.min(
          y(open),
          y(close)
        );

      const bottom =
        Math.max(
          y(open),
          y(close)
        );

      const bodyHeight =
        Math.max(
          2,
          bottom - top
        );


      ctx.fillStyle =
        up
          ? "#62d49a"
          : "#ef767a";


      ctx.fillRect(
        xx - candleWidth / 2,
        top,
        candleWidth,
        bodyHeight
      );
    }
  );
}


/*
 * ---------------------------------------------------------
 * Volume
 * ---------------------------------------------------------
 */

function drawBars(
  canvas,
  rows,
  key
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


  if (!rows.length) return;


  const values =
    rows.map(row =>
      Number(row[key] || 0)
    );


  let min =
    Math.min(...values);

  let max =
    Math.max(...values);


  if (min === max) {

    const padding =
      Math.max(
        1,
        max * 0.03
      );

    min = Math.max(
      0,
      min - padding
    );

    max += padding;
  }


  const y = value =>
    h -
    pad.b -
    (
      (value - min) /
      (max - min)
    ) *
    (
      h - pad.t - pad.b
    );


  const x = index =>
    pad.l +
    index *
    (
      (w - pad.l - pad.r) /
      Math.max(
        1,
        rows.length - 1
      )
    );


  drawGrid(
    ctx,
    w,
    h,
    pad,
    min,
    max
  );


  drawDateLabels(
    ctx,
    rows,
    x,
    w,
    h,
    pad
  );


  /*
   * ★ ここが今回のVolume修正。
   *
   * 1本しかない場合でも、
   * 画面いっぱいに伸びない。
   */
  const slot =
    (
      w - pad.l - pad.r
    ) /
    Math.max(
      1,
      rows.length
    );


  const barWidth =
    Math.max(
      4,
      Math.min(
        14,
        slot * 0.5
      )
    );


  const bottom =
    h - pad.b;


  rows.forEach(
    (row, index) => {

      const value =
        Number(row[key] || 0);

      const top =
        y(value);


      ctx.fillStyle =
        "#7f8b99";


      ctx.fillRect(
        x(index) - barWidth / 2,
        top,
        barWidth,
        Math.max(
          1,
          bottom - top
        )
      );
    }
  );
}


/*
 * ---------------------------------------------------------
 * Open Interest
 * ---------------------------------------------------------
 */

function drawLine(
  canvas,
  rows,
  key
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


  const valid =
    rows.filter(row =>
      Number.isFinite(
        Number(row[key])
      )
    );


  if (!valid.length) return;


  let min =
    Math.min(
      ...valid.map(row =>
        Number(row[key])
      )
    );

  let max =
    Math.max(
      ...valid.map(row =>
        Number(row[key])
      )
    );


  if (min === max) {

    const padding =
      Math.max(
        1,
        min * 0.01
      );

    min -= padding;
    max += padding;
  }


  const y = value =>
    h -
    pad.b -
    (
      (value - min) /
      (max - min)
    ) *
    (
      h - pad.t - pad.b
    );


  const x = index =>
    pad.l +
    index *
    (
      (w - pad.l - pad.r) /
      Math.max(
        1,
        valid.length - 1
      )
    );


  drawGrid(
    ctx,
    w,
    h,
    pad,
    min,
    max
  );


  drawDateLabels(
    ctx,
    valid,
    x,
    w,
    h,
    pad
  );


  /*
   * OI line
   */
  ctx.strokeStyle =
    "#d8b46a";

  ctx.lineWidth = 2;

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


  /*
   * 最終ポイント
   */
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
    3,
    0,
    Math.PI * 2
  );

  ctx.fill();
}


/*
 * ---------------------------------------------------------
 * Tap
 * ---------------------------------------------------------
 */

function selectFromChart(
  id,
  event
) {

  const rows =
    sliceData();

  const canvas =
    $(id);

  if (!canvas || !rows.length) {
    return;
  }


  const rect =
    canvas.getBoundingClientRect();


  const px =
    event.clientX -
    rect.left;


  const usableWidth =
    rect.width - 48 - 8;


  const idx =
    Math.round(
      (
        px - 48
      ) /
      usableWidth *
      Math.max(
        0,
        rows.length - 1
      )
    );


  if (
    idx >= 0 &&
    idx < rows.length
  ) {

    state.selected =
      rows[idx];

    showDetail(
      rows[idx]
    );
  }
}


function showDetail(d) {

  const oiChange =
    Number(
      d.oi_change || 0
    );


  document
    .querySelector(
      "#detail .detail-grid"
    )
    .innerHTML = `
      <span>Date</span>
      <b>${fmtDate(d.date)}</b>

      <span>Contract</span>
      <b>${d.contract}</b>

      <span>Settlement</span>
      <b>$${fmtPrice(d.settlement)}</b>

      <span>Volume</span>
      <b>${fmtInt(d.volume)}</b>

      <span>Open Interest</span>
      <b>${fmtInt(d.open_interest)}</b>

      <span>OI Change</span>
      <b>${oiChange >= 0 ? "+" : ""}${fmtInt(oiChange)}</b>
    `;
}


window.addEventListener(
  "resize",
  () => render()
);


init();
